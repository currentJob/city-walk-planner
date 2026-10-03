"""Same-origin GitHub OAuth and owner-scoped personal notebooks.

No GitHub token or itinerary is shipped to the public Pages application.
"""

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from city_walk_planner.api.deps import Conn
from city_walk_planner.services.external.github_oauth import exchange_identity
from city_walk_planner.storage.db import transaction

router = APIRouter()
COOKIE = '__Host-cwp_session'
STATE_COOKIE = '__Host-cwp_oauth'
ASSETS = {'index.html': 'text/html', 'account.js': 'text/javascript', 'account.css': 'text/css'}


def config():
    origin = os.environ.get('CWP_AUTH_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    client_id = os.environ.get('CWP_GITHUB_CLIENT_ID', '')
    secret = os.environ.get('CWP_GITHUB_CLIENT_SECRET', '')
    allowed = {x.strip() for x in os.environ.get('CWP_GITHUB_ALLOWED_IDS', '').split(',') if x.strip()}
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query
            or parsed.fragment or parsed.username or not client_id or not secret
            or not allowed or not all(x.isdigit() for x in allowed)):
        raise HTTPException(503, 'GitHub 로그인 설정이 아직 완료되지 않았습니다.')
    return origin, client_id, secret, allowed


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now(request):
    return int(request.app.state.clock.now_utc().timestamp())


def session(request, conn):
    origin, _, _, allowed = config()
    row = conn.execute('SELECT * FROM github_sessions WHERE digest = ? AND expires > ?',
                       (digest(request.cookies.get(COOKIE, '')), now(request))).fetchone()
    if row is None or row['github_id'] not in allowed:
        raise HTTPException(401, 'GitHub 로그인이 필요합니다.')
    if request.method not in ('GET', 'HEAD'):
        csrf = request.headers.get('x-csrf-token', '')
        if request.headers.get('origin') != origin or not secrets.compare_digest(csrf.encode(), row['csrf'].encode()):
            raise HTTPException(403, '페이지를 새로 열고 다시 시도하세요.')
    return row


def cookie(response, name, value, age):
    response.set_cookie(name, value, max_age=age, secure=True, httponly=True, samesite='lax', path='/')


@router.get('/auth/github/start', status_code=303, responses={429: {}, 503: {}})
def start(request: Request, conn: Conn):
    origin, client_id, _, _ = config()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)

    def create_state():
        conn.execute('DELETE FROM github_oauth_states WHERE expires <= ? OR digest = ?',
                     (now(request), digest(request.cookies.get(STATE_COOKIE, ''))))
        # Bound anonymous temporary storage, even if cookies are deliberately discarded.
        count = conn.execute('SELECT count(*) AS n FROM github_oauth_states').fetchone()['n']
        if count >= 1000:
            raise HTTPException(429, '잠시 후 다시 로그인하세요.')
        conn.execute('INSERT INTO github_oauth_states VALUES (?, ?, ?)',
                     (digest(state), verifier, now(request) + 600))
    transaction(conn, create_state)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    response = RedirectResponse('https://github.com/login/oauth/authorize?' + urlencode({
        'client_id': client_id, 'redirect_uri': origin + '/auth/github/callback',
        'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'scope': ''}), 303)
    cookie(response, STATE_COOKIE, state, 600)
    return response


@router.get('/auth/github/callback', status_code=303, responses={400: {}, 403: {}, 502: {}, 503: {}})
def callback(request: Request, conn: Conn, state: str = '', code: str = ''):
    origin, client_id, secret, allowed = config()
    if (not state or len(state) > 200 or not code or len(code) > 512
            or not secrets.compare_digest(state.encode(), request.cookies.get(STATE_COOKIE, '').encode())):
        raise HTTPException(400, '로그인을 처음부터 다시 시도하세요.')

    def consume():
        row = conn.execute('SELECT * FROM github_oauth_states WHERE digest = ? AND expires > ?',
                           (digest(state), now(request))).fetchone()
        conn.execute('DELETE FROM github_oauth_states WHERE digest = ?', (digest(state),))
        return row
    pending = transaction(conn, consume)
    if pending is None:
        raise HTTPException(400, '로그인 요청이 만료되었거나 이미 사용되었습니다.')
    provider = getattr(request.app.state, 'github_identity_provider', exchange_identity)
    try:
        identity = provider(client_id=client_id, client_secret=secret, code=code,
                            verifier=pending['verifier'], callback=origin + '/auth/github/callback')
    except Exception as exc:
        raise HTTPException(502, 'GitHub 확인에 실패했습니다. 다시 로그인하세요.') from exc
    if str(identity['id']) not in allowed:
        raise HTTPException(403, '이 개인 페이지에 허용된 GitHub 계정이 아닙니다.')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    def create_session():
        conn.execute('DELETE FROM github_sessions WHERE expires <= ? OR digest = ?',
                     (now(request), digest(request.cookies.get(COOKIE, ''))))
        conn.execute('INSERT INTO github_sessions VALUES (?, ?, ?, ?, ?)',
                     (digest(token), str(identity['id']), identity['login'], csrf, now(request) + 604800))
    transaction(conn, create_session)
    response = RedirectResponse(origin + '/account/', 303)
    cookie(response, COOKIE, token, 604800)
    cookie(response, STATE_COOKIE, '', 0)
    return response


@router.get('/auth/me', responses={401: {}, 503: {}})
def me(request: Request, conn: Conn):
    user = session(request, conn)
    return {'login': user['login'], 'csrf': user['csrf']}


@router.post('/auth/logout', status_code=204, responses={401: {}, 403: {}, 503: {}})
def logout(request: Request, conn: Conn):
    user = session(request, conn)
    conn.execute('DELETE FROM github_sessions WHERE digest = ?', (user['digest'],))
    response = Response(status_code=204)
    cookie(response, COOKIE, '', 0)
    return response


@router.get('/api/private/journey', responses={401: {}, 503: {}})
def get_journey(request: Request, conn: Conn):
    user = session(request, conn)
    row = conn.execute('SELECT * FROM private_journeys WHERE github_id = ?', (user['github_id'],)).fetchone()
    return {'payload': json.loads(row['payload']) if row else None, 'revision': row['revision'] if row else 0}


def valid_payload(payload):
    """Validate displayed structures without discarding imported source metadata."""
    if not isinstance(payload, dict) or not set(payload) <= {'journey', 'state'}:
        return False
    j, state = payload.get('journey'), payload.get('state', {})
    if not isinstance(j, dict) or not isinstance(state, dict):
        return False
    if (not isinstance(j.get('title'), str)
            or any(not isinstance(state.get(k, ''), str) for k in ('notes', 'hotel', 'flightTime', 'variant'))):
        return False
    checked = state.get('checked', {})
    if not isinstance(checked, dict) or not all(type(v) is bool for v in checked.values()):
        return False
    if not isinstance(j.get('days'), list) or len(j['days']) > 31:
        return False
    for key in ('summary', 'checked_at'):
        if not isinstance(j.get(key, ''), str):
            return False
    for key in ('assumptions',):
        if not isinstance(j.get(key, []), list) or not all(isinstance(x, str) for x in j.get(key, [])):
            return False
    fields = {'checklist': ('id', 'text'), 'activities': ('id', 'name', 'query'),
              'sources': ('name', 'url'), 'tips': ('title', 'body')}
    for key, names in fields.items():
        if not isinstance(j.get(key, []), list):
            return False
        if any(not isinstance(x, dict) or any(not isinstance(x.get(n, ''), str) for n in names)
               for x in j.get(key, [])):
            return False
    variants = j.get('variants', [])
    if not isinstance(variants, list) or len(variants) > 10:
        return False
    all_days = list(j['days'])
    for variant in variants:
        if (not isinstance(variant, dict) or not isinstance(variant.get('id'), str)
                or not isinstance(variant.get('label'), str)
                or not isinstance(variant.get('days'), list) or len(variant['days']) > 31):
            return False
        all_days.extend(variant['days'])
    for day in all_days:
        if not isinstance(day, dict):
            return False
        if any(not isinstance(day.get(k, ''), str) for k in ('date', 'label', 'theme')):
            return False
        if not isinstance(day.get('notes', []), list) or not all(isinstance(x, str) for x in day.get('notes', [])):
            return False
        if not isinstance(day.get('stops', []), list):
            return False
        if any(not isinstance(x, dict) or any(not isinstance(x.get(k, ''), str)
               for k in ('id', 'name', 'time', 'note', 'query')) for x in day.get('stops', [])):
            return False
    return True


@router.put('/api/private/journey', responses={401: {}, 403: {}, 409: {}, 413: {}, 422: {}, 503: {}})
async def put_journey(request: Request, conn: Conn):
    user = session(request, conn)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 256_000:
            raise HTTPException(413, '일정 파일은 256 KB 이하여야 합니다.')
    try:
        body = json.loads(raw)
        payload, revision = body['payload'], body['revision']
        if type(revision) is not int or revision < 0 or not valid_payload(payload):
            raise ValueError('Invalid notebook')
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise HTTPException(422, '올바른 여행수첩 JSON 파일이 아닙니다.') from exc

    def save():
        row = conn.execute('SELECT revision FROM private_journeys WHERE github_id = ?',
                           (user['github_id'],)).fetchone()
        current = row['revision'] if row else 0
        if current != revision:
            raise HTTPException(409, '다른 기기에서 변경했습니다. 백업 후 새로고침하세요.')
        conn.execute('INSERT INTO private_journeys (github_id, payload, revision) VALUES (?, ?, ?) '
                     'ON CONFLICT(github_id) DO UPDATE SET payload = excluded.payload, revision = excluded.revision',
                     (user['github_id'], serialized, current + 1))
        return {'revision': current + 1}
    return transaction(conn, save)


def asset(name):
    root = Path(__file__).resolve().parents[2]
    bundle = root / '_account_assets.json'
    content = json.loads(bundle.read_text())[name] if bundle.exists() else (root / 'private_ui' / name).read_text()
    return Response(content, media_type=ASSETS[name])


@router.get('/account/', response_class=HTMLResponse)
def account_page():
    return asset('index.html')


@router.get('/account/assets/{name}', responses={404: {}})
def account_asset(name: str):
    if name not in ASSETS or name == 'index.html':
        raise HTTPException(404)
    return asset(name)

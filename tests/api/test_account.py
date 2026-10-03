"""Identity, CSRF, session expiry and owner isolation, with no live GitHub calls."""
import base64
import hashlib
import os
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from city_walk_planner.api.app import create_app

ORIGIN = 'https://account.example'


@pytest.fixture
def account(monkeypatch, settings, fixed_clock):
    clock = fixed_clock
    for key, value in {'AUTH_ORIGIN': ORIGIN, 'GITHUB_CLIENT_ID': 'test-id',
                       'GITHUB_CLIENT_SECRET': 'test-secret', 'GITHUB_ALLOWED_IDS': '101,202'}.items():
        monkeypatch.setenv('CWP_' + key, value)
    kwargs = {}
    if os.environ.get('CWP_TEST_STORAGE') == 'durable-object':
        from tests.do_fake import durable_database
        kwargs['db'] = durable_database()
    app = create_app(settings=settings, clock=clock, **kwargs)
    app.state.github_identity_provider = lambda **kwargs: {'id': '101', 'login': 'owner'}
    return app, TestClient(app, base_url=ORIGIN, follow_redirects=False), clock


def login(app, client, ident='101'):
    captured = {}
    def provider(**kwargs):
        captured.update(kwargs)
        return {'id': ident, 'login': 'user-' + ident}
    app.state.github_identity_provider = provider
    start = client.get('/auth/github/start')
    assert start.status_code == 303
    query = parse_qs(urlsplit(start.headers['location']).query)
    state = query['state'][0]
    response = client.get('/auth/github/callback', params={'state': state, 'code': 'temporary-code'})
    return response, captured, query


def headers(client):
    return {'Origin': ORIGIN, 'X-CSRF-Token': client.get('/auth/me').json()['csrf']}


def body(title='Private test journey', revision=0):
    return {'payload': {'journey': {'title': title, 'days': []}, 'state': {}}, 'revision': revision}


def test_unconfigured_fails_closed(account, monkeypatch):
    _, client, _ = account
    monkeypatch.delenv('CWP_GITHUB_ALLOWED_IDS')
    assert client.get('/auth/github/start').status_code == 503
    assert client.get('/api/private/journey').status_code == 503
    assert client.get('/account/').status_code == 200


def test_cookie_pkce_state_and_replay(account):
    app, client, _ = account
    response, captured, query = login(app, client)
    assert response.status_code == 303
    expected = base64.urlsafe_b64encode(hashlib.sha256(captured['verifier'].encode()).digest()).decode().rstrip('=')
    assert query['code_challenge'] == [expected]
    assert query['code_challenge_method'] == ['S256']
    assert captured['callback'] == ORIGIN + '/auth/github/callback'
    cookie = response.headers['set-cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert client.get('/auth/me').json()['login'] == 'user-101'
    client.cookies.set('__Host-cwp_oauth', query['state'][0])
    assert client.get('/auth/github/callback', params={'state': query['state'][0], 'code': 'x'}).status_code == 400


def test_mismatched_and_expired_state(account):
    _, client, clock = account
    start = client.get('/auth/github/start')
    state = parse_qs(urlsplit(start.headers['location']).query)['state'][0]
    assert client.get('/auth/github/callback', params={'state': 'wrong', 'code': 'x'}).status_code == 400
    clock.advance(601)
    assert client.get('/auth/github/callback', params={'state': state, 'code': 'x'}).status_code == 400


def test_unauthorized_identity(account):
    app, client, _ = account
    assert login(app, client, '999')[0].status_code == 403
    assert client.get('/api/private/journey').status_code == 401


def test_isolation_csrf_conflict_and_logout(account):
    app, client, _ = account
    assert client.get('/api/private/journey').status_code == 401
    login(app, client)
    assert client.put('/api/private/journey', json=body()).status_code == 403
    h = headers(client)
    assert client.put('/api/private/journey', json=body(),
                      headers={**h, 'Origin': 'https://evil.example'}).status_code == 403
    assert client.put('/api/private/journey', json=body(), headers=h).json() == {'revision': 1}
    assert client.put('/api/private/journey', json=body(), headers=h).status_code == 409
    other = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    login(app, other, '202')
    assert other.get('/api/private/journey').json()['payload'] is None
    assert other.put('/api/private/journey', json=body('Other'), headers=headers(other)).status_code == 200
    assert client.get('/api/private/journey').json()['payload']['journey']['title'] == 'Private test journey'
    old_token = client.cookies.get('__Host-cwp_session')
    assert client.post('/auth/logout', headers=h).status_code == 204
    client.cookies.set('__Host-cwp_session', old_token)
    assert client.get('/auth/me').status_code == 401


def test_expired_and_revoked_allowlist(account, monkeypatch):
    app, client, clock = account
    login(app, client)
    monkeypatch.setenv('CWP_GITHUB_ALLOWED_IDS', '202')
    assert client.get('/auth/me').status_code == 401
    monkeypatch.setenv('CWP_GITHUB_ALLOWED_IDS', '101,202')
    clock.advance(604801)
    assert client.get('/auth/me').status_code == 401


def test_limits_security_headers_and_assets(account):
    app, client, _ = account
    login(app, client)
    assert client.put('/api/private/journey', content='x' * 256001, headers=headers(client)).status_code == 413
    assert client.put('/api/private/journey', json={'payload': {}}, headers=headers(client)).status_code == 422
    for path in ['/account/', '/account/assets/account.js', '/auth/me', '/api/private/journey']:
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers['cache-control'] == 'no-store'
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert client.get('/account/assets/unknown.json').status_code == 404
    assert client.get('/private_ui/index.html').status_code == 404



def test_reject_malformed_notebook_and_store_only_hashed_session(account):
    app, client, _ = account
    login(app, client)
    invalid = body()
    invalid['payload']['journey']['days'] = [None]
    assert client.put('/api/private/journey', json=invalid, headers=headers(client)).status_code == 422
    invalid = body()
    invalid['payload']['journey']['variants'] = [{'id': 'x', 'label': 'x', 'days': [None]}]
    assert client.put('/api/private/journey', json=invalid, headers=headers(client)).status_code == 422
    with app.state.db.connection() as conn:
        row = conn.execute('SELECT * FROM github_sessions').fetchone()
        assert row['digest'] != client.cookies.get('__Host-cwp_session')
        assert len(row['digest']) == 64
        assert 'access_token' not in row.keys()

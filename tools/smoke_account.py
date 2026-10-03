"""Check that the deployed Worker actually includes the account application."""

import json

import httpx

HOST = 'city-walk-planner-api.currentjob.workers.dev'
PATHS = {'/account/', '/account/assets/account.js', '/account/assets/account.css',
         '/auth/me', '/api/private/journey'}


def read(path):
    if path not in PATHS:
        raise ValueError('Unexpected account check path')
    with httpx.Client(base_url='https://' + HOST, timeout=30, follow_redirects=False) as client:
        response = client.get(path, headers={'User-Agent': 'CityWalkPlanner-DeploymentCheck/1.0'})
        return response.status_code, response.text


def main():
    status, page = read('/account/')
    if status != 200 or '/account/assets/account.js' not in page:
        raise SystemExit(f'Account page unavailable: HTTP {status}. Check Worker deployment and edge access rules.')
    for asset in ('account.js', 'account.css'):
        status, _ = read('/account/assets/' + asset)
        if status != 200:
            raise SystemExit(f'Account asset {asset}: HTTP {status}')
    for path in ('/auth/me', '/api/private/journey'):
        status, body = read(path)
        if status not in (401, 503):
            raise SystemExit(f'{path}: expected unauthenticated 401 or unconfigured 503; got {status}')
        if status == 503:
            detail = json.loads(body).get('detail', '')
            if detail != 'GitHub 로그인 설정이 아직 완료되지 않았습니다.':
                raise SystemExit(f'{path}: unexpected 503 response')
            print('::warning::Account routes are deployed; GitHub OAuth configuration is still required.')
    print('PASS: account HTML/assets deployed; anonymous private data access denied.')


if __name__ == '__main__':
    main()

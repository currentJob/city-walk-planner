"""Server-only GitHub identity exchange; never retain the upstream access token."""

import httpx


def exchange_identity(*, client_id: str, client_secret: str, code: str,
                      verifier: str, callback: str) -> dict:
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post('https://github.com/login/oauth/access_token',
                               headers={'Accept': 'application/json'}, data={
                                   'client_id': client_id, 'client_secret': client_secret,
                                   'code': code, 'code_verifier': verifier, 'redirect_uri': callback})
        response.raise_for_status()
        token = response.json().get('access_token')
        if not isinstance(token, str) or not token:
            raise ValueError('GitHub rejected authorization')
        response = client.get('https://api.github.com/user', headers={
            'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
            'User-Agent': 'city-walk-planner'})
        response.raise_for_status()
        identity = response.json()
        if type(identity.get('id')) is not int or not isinstance(identity.get('login'), str):
            raise ValueError('Invalid GitHub identity')
        return {'id': str(identity['id']), 'login': identity['login']}

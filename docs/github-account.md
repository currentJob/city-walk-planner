# GitHub 로그인 활성화

공개 사이트: https://currentjob.github.io/city-walk-planner/#trend

개인 페이지(아래 배포 완료 후): https://city-walk-planner-api.currentjob.workers.dev/account/

## 1. GitHub OAuth App 등록

GitHub 본인 계정에서 https://github.com/settings/applications/new 를 엽니다.

| 항목 | 값 |
|---|---|
| Application name | City Walk Planner Private |
| Homepage URL | `https://city-walk-planner-api.currentjob.workers.dev/account/` |
| Authorization callback URL | `https://city-walk-planner-api.currentjob.workers.dev/auth/github/callback` |

Client ID를 복사하고 Client Secret을 발급합니다. **Client Secret은 채팅·소스 코드·커밋에 넣지 마세요.**
이 앱은 저장소 권한이나 이메일 scope를 요청하지 않습니다. 로그인에 필요한 공개 프로필의 ID와 로그인명을 확인합니다.

## 2. Cloudflare 설정

`worker/wrangler.jsonc`의 `vars`에는 origin과 허용 계정 ID가 설정되어 있습니다. 다음과 같이 발급받은 Client ID만 추가합니다. 기존 값은 유지하세요.

```json
"CWP_AUTH_ORIGIN": "https://city-walk-planner-api.currentjob.workers.dev",
"CWP_GITHUB_CLIENT_ID": "발급받은 Client ID",
"CWP_GITHUB_ALLOWED_IDS": "78770258"
```

`78770258`은 저장소 소유자 `currentJob`의 숫자 GitHub ID입니다.
사용자명 변경과 무관하게 이 ID로 접근을 제한합니다. 본인의 다른 계정을 허용하려면
그 계정의 검증된 숫자 ID로 수정하세요. 비어 있거나 설정이 잘못되면 로그인·개인 데이터 API는 503으로 닫힙니다.

저장소 루트에서:

```bash
uv sync --frozen
uv run python tools/build_worker.py
cd worker
npm ci
uv sync --frozen
uv run pywrangler secret put CWP_GITHUB_CLIENT_SECRET
# 대화형 입력에 Client Secret 붙여넣기
uv run pywrangler deploy
```

Cloudflare 로그인/권한이 이미 준비되어 있어야 합니다. `secret put` 명령의 대화형 입력 외에
비밀키를 명령 인수나 파일에 기록하지 마세요. Worker는 기존 SQLite Durable Object의 같은
`main` 인스턴스에 계정용 테이블을 멱등 생성하므로 기존 공유 여행 데이터는 유지됩니다.

## 3. 확인과 개인 일정 가져오기

1. 개인 페이지를 열어 GitHub 로그인을 진행합니다.
2. `@currentJob · 비공개` 표시를 확인합니다.
3. 별도로 제공된 개인 일정 JSON을 **일정 파일 가져오기**에서 선택합니다.
4. 체크·메모를 저장하고 다른 기기에서 로그인해 같은 내용이 보이는지 확인합니다.
5. 로그아웃 후 `/api/private/journey`가 401로 거절되는지 확인합니다.

서버는 일정을 공유용 `/api/trips`에 복사하지 않습니다. URL을 다른 사람에게 보내도
일정은 공개되지 않습니다. 같은 계정으로 여러 기기에서 동시에 변경하면, 뒤늦은 저장은
409로 거절됩니다. 메모를 백업한 뒤 새로고침하면 최신 상태를 다시 불러옵니다.

## 보안 구조와 범위

- OAuth authorization code + state + S256 PKCE, 10분 만료·1회용 state.
- GitHub 토큰은 프로필을 확인한 직후 폐기하고 저장하거나 브라우저로 전송하지 않음.
- 앱 세션은 서버에 SHA-256 해시로 보관. 쿠키는 host-only `__Host-`, Secure, HttpOnly, SameSite=Lax.
- 세션 7일 만료, 로그아웃 즉시 폐기. 매 요청에 계정 허용 목록 재검사.
- 모든 쓰기에 동일 origin 및 세션 CSRF 토큰 검사. GitHub Pages에서 인증 API를 교차 출처로 호출하지 않음.
- 모든 개인 데이터 응답은 `Cache-Control: no-store`. 프레임 삽입 차단, 엄격한 CSP, 개인 화면 DOM에서 textContent 사용.
- 데이터 소유자는 세션에서 결정. 클라이언트가 보낸 소유자 ID는 받지 않음.
- 개인 데이터는 서버 저장소의 관리자에게도 숨겨지는 종단간 암호화 형태는 아님.
- 현재 공개 배포에서 제거해도 이전 Git 커밋, 다운로드본, 브라우저 캐시에 있던 사본은 소급 삭제되지 않음.
  과거 기록 삭제는 별도 이력 재작성 작업이며 이 변경에는 포함되지 않음.

로컬 HTTP에서는 Secure 쿠키가 동작하지 않습니다. HTTPS 개발 주소와 별도 OAuth App을 사용하세요.

공식 참고: [GitHub OAuth 웹 흐름](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps),
[OAuth App 등록](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app).

# GitHub 로그인 활성화

공개 사이트(로그인 불필요): https://currentjob.github.io/city-walk-planner/#trend

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

## `/account/`가 404일 때: API 배포

GitHub Pages 배포와 API Worker 배포는 별개입니다. Pages만 배포하면
링크는 보여도 이전 Worker에는 `/account/` 경로가 없어 404가 납니다.
OAuth 앱 설정 누락은 새 Worker에서 **503**으로 표시됩니다. 404와 원인이 다릅니다.

GitHub에서 배포하려면:

1. Cloudflare에서 이 Worker의 계정에 한정한 **Edit Cloudflare Workers** API Token을 발급합니다.
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**에
   `CLOUDFLARE_API_TOKEN`과 `CLOUDFLARE_ACCOUNT_ID`를 등록합니다.
   토큰은 채팅이나 코드에 붙여넣지 않습니다.
3. **Actions → Deploy API Worker → Run workflow → main**을 실행합니다.
4. CI 성공 후 기존 Worker에 배포하고, 마지막 단계에서 `/account/`와 자산이 200인지,
   익명 개인 데이터 접근이 거부되는지 검사합니다. OAuth 미설정은 경고로 구분합니다.
5. OAuth 설정은 이 문서의 1~3단계를 따릅니다. 배포 자체는 로그인 활성화와 별도입니다.

로컬에서 이미 Cloudflare 로그인이 되어 있다면 기존 2단계의 배포 명령을 실행해도 됩니다.
이 워크플로는 main의 백엔드·계정 화면 변경 시 자동 실행되며 수동 실행도 가능합니다. 배포 인증이 설정돼 있어야 합니다.

공식 배포 인증 안내: https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/

## 공개 트렌드 탭과 별도 계정 페이지

`#trend`는 소유자가 공개를 승인한 2026년 10월 4~8일 홍콩·마카오 여행수첩을 Pages에서 바로 표시합니다.
GitHub 로그인이나 Worker 배포 없이 볼 수 있습니다. 체크·숙소·귀국편 설정은 방문자별 브라우저에만 저장됩니다.
공개 추천 코스·맛집·명소는 `#trend-guide`로 바로 열 수 있습니다.

`/account/`의 로그인과 계정별 데이터 보호는 유지합니다. 해당 숫자 GitHub ID의 개인 일정만 읽고 저장하며,
서버 계정 데이터는 공개 여행수첩에 자동 반영되지 않습니다.

개인 페이지에서 날짜·장소·시간·메모를 편집하고, 기존 JSON을 가져오거나 새 일정을 만들 수 있습니다. 최신 내용 불러오기는 서버의 현재 revision을 다시 읽습니다. 저장하지 않은 변경은 버리기 전에 확인하고, 동시 편집 충돌은 기존 409 보호를 유지합니다. 개인 데이터를 공개 페이지나 localStorage로 옮기지 않습니다.

# 백엔드를 Cloudflare Worker 로 이전

사용자 요청: PC 가 꺼져도 동작하도록 백엔드를 Cloudflare 로 옮긴다. 무료 요금제로 시도하고, 도시 가이드·일정·맛집(1단계)과 동행 일정(2단계)을 한 번에 옮긴다.

## 설계 판단

- D1 은 비동기이고 대화식 트랜잭션이 없어 서비스 계층 전체를 다시 써야 한다. SQLite 기반 Durable Object 는 SQL 이 동기이고 `transactionSync` 로 롤백을 지원하며 요청을 한 번에 하나씩 처리한다. 그래서 기존 FastAPI 앱을 Durable Object 하나(`AppDO`) 안에서 그대로 돌리는 방식을 골랐다.
- 기존 코드 변경은 연결 지점만 한다.
  - 트랜잭션 12곳을 `transaction(conn, work)` 콜백 형태로 바꿨다. 로컬에서는 `BEGIN IMMEDIATE`, Worker 에서는 `transactionSync` 로 실행된다.
  - 데이터 경로를 `config.seed_dir()` 로 모았다. 번들 안에서는 `_seed` 를 쓴다.
  - `create_app(db=...)` 로 저장소를 주입할 수 있게 했다. 화면 폴더가 없으면 정적 파일 연결을 건너뛴다.
  - 리뷰 조회는 스레드가 없으면 순차 실행한다.
- Worker 전용 코드(`worker/src`):
  - `do_sqlite.py`: sqlite3 형태의 어댑터. `Row`, `rowcount`, `executescript`(PRAGMA 제거), 제약 오류를 `sqlite3.IntegrityError` 로 변환.
  - `fetch_transport.py`: httpx 요청을 `run_sync(fetch)` 로 보낸다.
  - `entry.py`: 모든 요청을 `getByName("main")` 으로 넘긴다. 부팅 시 환경변수 복사, `time.sleep` 을 비동기 대기로, `anyio.to_thread.run_sync` 를 현재 흐름에서 바로 실행하도록 바꾼다(스레드 없음).
- 빌드: `tools/build_worker.py` 가 앱과 `seed/` 를 `worker/src` 로 복사한다(git 제외). `wrangler.jsonc` 에 JSON 을 Data 모듈로 싣는 규칙을 넣었다.
- 화면: Pages 빌드의 기본 서버 주소를 Worker 로 바꿨다. 기기에 저장된 `trycloudflare.com` 임시 주소는 고정 서버 기본값이 있을 때 버린다.

## 검증

- PASS `PYTHONUTF8=1 uv run pytest -q`: 937 passed.
  - 신규 `tests/test_worker_storage.py`: 스키마 적용, Row, 트랜잭션 커밋·롤백, 제약 오류 변환, 어댑터 사용 여부를 검사한다.
  - 신규 `tests/static/test_api_base.py`: 죽은 터널 주소는 버리고 직접 지정한 주소는 유지한다.
- PASS `CWP_TEST_STORAGE=durable-object uv run pytest -q tests/api`: API 테스트 260 passed. `tests/do_fake.py` 가짜 Durable Object 저장소는 `BEGIN`/`SAVEPOINT` 를 거부해서, 앱이 트랜잭션 문을 직접 보내지 않음을 증명한다.
- PASS ruff, `.github/quality/gate.py` 4/4.
- PASS 로컬 workerd(`pywrangler dev`)와 배포 서버에서 `tools/smoke_api.py` 17개 항목. 배포 서버 응답은 한국에서 250~420ms.
  - 가이드 29곳, 일정, 날씨·환율(외부 fetch)
  - 여행 생성 → 상태 조회 → 304
  - 참여, 같은 이름 409, 방문 체크, 옛 버전 수정 409
  - 경비 생성 → 정산 → 삭제(CASCADE)
- 배포: `https://city-walk-planner-api.currentjob.workers.dev`. 시작 시간 820ms(한도 1초), 업로드 11.4 MiB(gzip 2.7 MiB).
- CPU 실측(`wrangler tail`, AppDO): 요청당 6~31ms, 첫 요청 90ms. 무료 한도 10ms 를 자주 넘지만 전부 `ok` 로 처리됐다(일시 초과 허용). 계속 넘으면 1102 가 날 수 있다.
- NOT-RUN: 장소 검색(Overpass/Nominatim)과 Google 리뷰는 배포 서버에서 호출하지 않았다. 무료 요금제는 요청당 외부 호출이 50건으로 제한되고, 리뷰 조회는 최대 40곳이라 한도 근처다.

## 남은 일

- 무료 CPU 한도 초과가 잦다. 1102 오류가 보이면 Workers Paid($5/월)로 올리거나 무거운 요청(`/state` 재계산, 여행 생성 시드 주입)을 최적화한다.
- 기존 PC DB 의 동행 여행 데이터는 옮기지 않았다. 새 서버는 빈 DB 에서 시작한다.
- 저장소 변수 `HL_API_BASE` 는 더 이상 쓰지 않으므로 지워도 된다.

## 배포 · 2026-09-29

- `0cf559a` 를 main 에 푸시했다. CI 성공([run 36510378408](https://github.com/currentJob/city-walk-planner/actions/runs/36510378408)), Pages 성공([run 36510378502](https://github.com/currentJob/city-walk-planner/actions/runs/36510378502)). 배포된 `config.js` 의 `apiBase` 가 Worker 주소다.
- PASS https://currentjob.github.io/city-walk-planner/ 확인:
  - 예전 임시 터널 주소를 저장해 둔 상태에서 새로 불러오면 저장값이 지워지고 Worker 로 연결된다.
  - 도시 29곳, 홍콩 상세 49곳, 추천 일정(3일·방문지 15·핀 15) 표시, 콘솔 오류 없음.
- 관찰: 한동안 요청이 없다가 온 첫 요청은 4.8초(Durable Object 와 Python 콜드 스타트), 이후 요청은 0.3~0.7초.

## 추가: 로컬 Docker 실행 · 2026-09-29

- 요청: 클라우드에 올린 구조와 같게 Docker 로 로컬에서 프론트와 백엔드를 띄운다.
- `docker/api.Dockerfile`:
  - node 22 + uv 0.12.20 이미지다.
  - 배포와 같은 `tools/build_worker.py` 번들을 `pywrangler dev`(workerd)로 실행한다.
  - Durable Object 데이터는 `/data` 볼륨(`--persist-to`)에 저장한다.
  - wrangler 와 파이썬 패키지는 빌드할 때 미리 받아 둔다.
- `docker/web.Dockerfile`: nginx 가 `web/` 를 서빙하고 `/api/` 를 api 컨테이너로 넘긴다. `config.js` 의 `apiBase` 를 비워 같은 출처로 요청한다.
- `docker-compose.yml`: api 에 health check(`/api/health`)를 두고, web 은 api 가 healthy 가 된 뒤 뜬다.
- 검증:
  - PASS `docker compose build` / `up -d`: api 는 20초 안에 healthy 가 됐다. 첫 health 응답은 7.4초(Python 부팅).
  - PASS `tools/smoke_api.py http://localhost:8080`(nginx 경유)와 `:8787`(직접) 17개 항목.
  - PASS `docker compose restart api` 뒤에도 앞서 만든 여행(스팟 27)이 그대로 조회된다(볼륨 유지).
  - PASS 브라우저 http://localhost:8080: 도시 상세 49곳과 추천 일정(방문지 15)이 nginx 로그상 `/api/explore/*` 로 로컬 Worker 에서 왔다. 콘솔 오류 없음.
  - PASS `PYTHONUTF8=1 uv run pytest -q` 937 passed, ruff.
  - NOT-RUN: CI 에서 Docker 이미지 빌드는 하지 않는다(워크플로 변경 없음).

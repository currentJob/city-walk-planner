# City Walk Planner · 도시를 걷는 여행

도시를 고르고 날짜를 정하면 지도 위에 하루 동선을 짜 주는 여행 플래너입니다. 동행과 함께 일정·경비를 편집하는 공유 여행도 지원합니다.

- 사이트: https://currentjob.github.io/city-walk-planner/

## 기능

| 기능 | 내용 |
|---|---|
| 도시 가이드 | 미리 조사해 저장소에 넣은 29개 도시(완전 26 · 부분 3). 스팟별 한국어 이름·원어명·위키백과 설명과 출처, 하루 테마 |
| 일정 만들기 | 나라·도시를 검색하고 날짜를 고르면 영업시간·거리를 고려해 날짜별 동선을 만든다. 장소 추가·제외, 순서·날짜 이동, 체류시간 편집, 지도와 목록 연결 |
| 평점 반영 | Trip.com 조사 자료 131곳의 평점·리뷰 수를 보정 점수로 반영(조회 시점 스냅샷). Google 평점·후기는 서버에 `CWP_GOOGLE_PLACES_API_KEY` 가 있을 때만 |
| 주변 맛집 | 현재 위치나 여행지 기준 OpenStreetMap 음식점·카페 검색, 거리·평점 정렬, SNS·트렌드 맛집(홍콩) |
| 홍콩·마카오 트렌드 코스 | 날짜·숙소에 맞춘 코스 배치, OpenRice 반응 요약, 영업시간, 꿀팁 |
| 동행과 함께 | 초대코드로 참여하는 공유 여행(홍콩 3박 4일): 완료 체크 공유, 경비 기록·정산, 영수증 사진으로 경비 입력, 영업시간·시간 충돌 경고, 날씨·환율 |
| 내 여행 | 브라우저에 최근 10개 보관, 삭제·되돌리기, 일정 파일 내려받기·불러오기 |
| 화면 | 밝은/어두운 테마, 강조 색상 선택, 모바일 레이아웃 |

영수증 인식은 [OCR 프로젝트](https://github.com/currentJob/ocr-llm-page)가 배포한 모듈을 브라우저에서 불러 쓰며, 사진은 기기 밖으로 나가지 않습니다(`CWP_CONFIG.ocrModule` 이 비어 있으면 버튼이 숨겨집니다).

## 실행

Python 3.12+ 와 [uv](https://docs.astral.sh/uv/) 가 필요합니다.

```powershell
uv sync --frozen
uv run python -m city_walk_planner      # http://127.0.0.1:8080
```

| 환경변수 | 기본값 | 뜻 |
|---|---|---|
| `CWP_DB_PATH` | `city-walk-planner.db` | SQLite 파일 경로 |
| `CWP_HOST` · `CWP_PORT` | `127.0.0.1` · `8080` | 바인딩 주소 |
| `CWP_ALLOWED_ORIGINS` | (비어 있음) | CORS 허용 출처. 화면을 다른 호스트에 올릴 때만 |
| `CWP_GOOGLE_PLACES_API_KEY` | (비어 있음) | Google 평점·후기 조회(선택, 과금 발생 가능) |
| `CWP_CLIENT_IP_HEADER` | (비어 있음) | 프록시 뒤에서 실제 접속 주소를 읽을 헤더 |

날씨(Open-Meteo)·환율(Frankfurter)·주변 장소(OpenStreetMap)는 API 키가 필요 없습니다. 도시 가이드 데이터를 다시 만들려면 `uv run python tools/bake_city_guides.py --help`.

## Docker

```powershell
docker compose up --build     # 화면 http://localhost:8080 · API http://localhost:8787
```

배포와 같은 Cloudflare Worker 번들을 로컬 workerd 로 실행합니다. 데이터는 `api-data` 볼륨에 남고, `docker compose down -v` 로 초기화합니다.

## 셀프 호스팅

도메인의 DNS 를 서버로 향하게 하고 80·443 포트를 연 뒤, 파일 하나로 실행합니다.

```bash
curl -fsSLO https://raw.githubusercontent.com/currentJob/city-walk-planner/main/docker-compose.selfhost.yml
DOMAIN=trips.example.com docker compose -f docker-compose.selfhost.yml up -d
```

- `app`: `ghcr.io/currentjob/city-walk-planner` (FastAPI + SQLite, 화면과 API). `proxy`: Caddy 가 HTTPS 인증서를 자동 발급합니다.
- 백업:

```bash
docker compose -f docker-compose.selfhost.yml exec app /app/.venv/bin/python -c "import sqlite3; sqlite3.connect('/data/city-walk-planner.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose -f docker-compose.selfhost.yml cp app:/data/backup.db ./city-walk-planner-backup.db
```

- 복원(파일 소유자를 앱 사용자로 되돌립니다):

```bash
docker compose -f docker-compose.selfhost.yml stop app
docker compose -f docker-compose.selfhost.yml run --rm --no-deps -u root -v "$PWD:/restore" app sh -c "cp /restore/city-walk-planner-backup.db /data/city-walk-planner.db && rm -f /data/city-walk-planner.db-wal /data/city-walk-planner.db-shm && chown 10001 /data/city-walk-planner.db"
docker compose -f docker-compose.selfhost.yml start app
```

## 배포 (GitHub Pages + Cloudflare Worker)

화면은 `main` 에 push 하면 `.github/workflows/pages.yml` 이 GitHub Pages 에 올립니다. 서버 주소(`CWP_API_BASE`)와 영수증 인식 모듈(`CWP_OCR_MODULE`)은 저장소 변수로 바꿀 수 있습니다.

API 는 Python Worker 하나와 SQLite 기반 Durable Object(`AppDO`)에서 FastAPI 앱을 그대로 실행합니다.

```powershell
uv run python tools/build_worker.py      # 앱 코드·데이터를 worker/src 로 복사
cd worker; npm ci; uv sync
uv run pywrangler deploy                 # 처음 한 번 npx wrangler login
uv run python ../tools/smoke_api.py https://city-walk-planner-api.currentjob.workers.dev
```

## 테스트

```powershell
uv run pytest -q
uv run ruff check .
uv run python tools/vendor_check.py      # Leaflet 벤더 파일 SHA256 대조
```

테스트는 네트워크 없이 돌며, 외부 공급자는 가짜로 대체됩니다. `CWP_TEST_STORAGE=durable-object` 로 API 테스트를 Durable Object 어댑터 위에서 다시 돌릴 수 있습니다.

## 알아 둘 점

- 초대코드를 아는 사람은 공유 여행 전체를 편집할 수 있습니다.
- 이동시간·도착 시각은 직선거리 기반 추정치이고, 영업시간은 근사치입니다. 공휴일·임시 휴업은 반영하지 않습니다.
- 도시 가이드와 평점은 조사 시점의 스냅샷이며 자동으로 갱신되지 않습니다.
- 공유 여행의 통화는 HKD 입니다.

## 라이선스

코드는 MIT([`LICENSE`](LICENSE)). 도시 가이드의 스팟 설명은 위키백과 본문으로 CC BY-SA 4.0 이며, 화면에 출처 링크를 표시합니다. 영업시간·지도·주변 장소는 OpenStreetMap(ODbL 1.0) 기여자의 자료입니다.

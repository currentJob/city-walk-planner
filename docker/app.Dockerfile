# City Walk Planner — self-hosted image: FastAPI (uvicorn) + SQLite, serving the web front end and the API.
#
# Published as ghcr.io/currentjob/city-walk-planner by .github/workflows/image.yml.
# Run it behind the HTTPS proxy in docker-compose.selfhost.yml; data lives in /data (mount a volume).
FROM python:3.12.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first (cached layer), pinned by uv.lock; no dev tools in the image.
COPY pyproject.toml uv.lock LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY seed ./seed
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --home /app app && mkdir -p /data && chown app /data
USER app
ENV CWP_DB_PATH=/data/city-walk-planner.db \
    CWP_HOST=0.0.0.0 \
    CWP_PORT=8000
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["/app/.venv/bin/python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]
# The container port is reachable only from the proxy on the compose network, so the proxy's
# X-Forwarded-For is trusted: the join rate limit then counts real client addresses.
CMD ["/app/.venv/bin/uvicorn", "city_walk_planner.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

# City Walk Planner API — the same Cloudflare Worker that is deployed, run locally.
#
# `pywrangler dev` runs the Python Worker and its SQLite-backed Durable Object on workerd
# (the open-source Workers runtime), so this container executes the exact bundle
# `pywrangler deploy` uploads. Durable Object data persists in /data (mount a volume).
FROM node:22.23.3-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    WRANGLER_SEND_METRICS=false \
    CI=1

WORKDIR /app
COPY src ./src
COPY seed ./seed
COPY tools/build_worker.py ./tools/build_worker.py
COPY worker/pyproject.toml worker/uv.lock worker/pylock.toml worker/wrangler.jsonc \
     worker/package.json worker/package-lock.json ./worker/
COPY worker/src/entry.py worker/src/do_sqlite.py worker/src/fetch_transport.py ./worker/src/

# Same bundle as deploy: app package + baked data copied into worker/src.
RUN uv run --no-project --python 3.13 python tools/build_worker.py

WORKDIR /app/worker
# Pinned toolchain: wrangler from worker/package-lock.json (npx prefers this local copy),
# pywrangler and Python packages from worker/uv.lock and worker/pylock.toml.
RUN npm ci --no-audit --no-fund && uv sync --frozen
# Vendor the Worker's Python packages at build time so the container starts offline.
RUN npx wrangler --version && uv run pywrangler sync

EXPOSE 8787
# Allowed browser origin for direct API calls (the bundled web container proxies /api, so it is same-origin).
ENV CWP_ALLOWED_ORIGINS=http://localhost:8080
CMD ["sh", "-c", "exec uv run pywrangler dev --ip 0.0.0.0 --port 8787 --persist-to /data --var CWP_ALLOWED_ORIGINS:${CWP_ALLOWED_ORIGINS}"]

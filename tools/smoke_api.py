"""End-to-end smoke test against a running API (local `pywrangler dev`, the deployed Worker, or uvicorn).

    uv run python tools/smoke_api.py http://127.0.0.1:8787

Creates one trip and exercises the shared-trip flow (join, sync/304, visit, conflict, expenses,
cascade, rollback-free conflict) plus guides/plan/weather/fx. Prints one line per check with its
latency and exits non-zero on the first failure. It writes a throwaway trip into that API's storage.
"""

from __future__ import annotations

import sys
import time

import httpx

ORIGIN = "https://currentjob.github.io"


def main(base: str) -> int:
    # `https://localhost` is Caddy's self-signed local certificate (docker-compose.selfhost.yml with DOMAIN=localhost).
    verify = not base.startswith("https://localhost")
    client = httpx.Client(base_url=base.rstrip("/"), timeout=90, headers={"Origin": ORIGIN}, verify=verify)
    failures = 0

    def check(label: str, method: str, url: str, expect: int, **kwargs) -> httpx.Response:
        nonlocal failures
        started = time.perf_counter()
        response = client.request(method, url, **kwargs)
        ms = (time.perf_counter() - started) * 1000
        ok = response.status_code == expect
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} {label:34s} {response.status_code} {ms:7.0f}ms"
              + ("" if ok else f"  {response.text[:200]}"))
        return response

    check("health", "GET", "/api/health", 200)
    guides = check("guides", "GET", "/api/explore/guides", 200).json()
    print(f"     cities={len(guides.get('cities', []))}")
    check("plan hong-kong 4d", "POST", "/api/explore/plan", 200,
          json={"city_id": "hong-kong", "start_date": "2026-10-05", "end_date": "2026-10-08"})
    check("weather", "GET", "/api/weather", 200)
    check("fx", "GET", "/api/fx", 200)

    created = check("create trip", "POST", "/api/trips", 201, json={"organizer_display_name": "smoke"}).json()
    trip_id, code = created["trip"]["id"], created["trip"]["invite_code"]
    owner = {"X-Participant-Token": created["participant_token"]}
    state = check("state", "GET", f"/api/trips/{trip_id}/state", 200, headers=owner)
    body = state.json()
    print(f"     days={len(body['days'])} spots={sum(len(d['spots']) for d in body['days'])}")
    check("state unchanged -> 304", "GET", f"/api/trips/{trip_id}/state", 304,
          headers={**owner, "If-None-Match": state.headers["etag"]})

    joined = check("join", "POST", "/api/join", 200, json={"invite_code": code, "display_name": "friend"}).json()
    friend = {"X-Participant-Token": joined["participant_token"]}
    check("join same name -> 409", "POST", "/api/join", 409, json={"invite_code": code, "display_name": "friend"})

    spot = body["days"][0]["spots"][0]
    check("visit done", "PUT", f"/api/trips/{trip_id}/spots/{spot['id']}/done", 200,
          headers=friend, json={"done": True})
    check("stale edit -> 409", "PATCH", f"/api/trips/{trip_id}/spots/{spot['id']}", 409, headers=owner,
          json={"version": 999, "tip": "x"})
    check("edit", "PATCH", f"/api/trips/{trip_id}/spots/{spot['id']}", 200, headers=owner,
          json={"version": spot["version"], "tip": "smoke tip"})

    expense = check("expense create", "POST", f"/api/trips/{trip_id}/expenses", 201, headers=owner, json={
        "amount_minor": 30000, "payer_id": created["participant"]["id"], "note": "smoke",
        "share_participant_ids": [created["participant"]["id"], joined["participant"]["id"]]}).json()
    settlement = check("settlement", "GET", f"/api/trips/{trip_id}/settlement", 200, headers=owner).json()
    print(f"     transfers={settlement.get('transfers')}")
    check("expense delete (cascade shares)", "DELETE", f"/api/trips/{trip_id}/expenses/{expense['id']}", 204,
          headers=owner)
    check("settlement after delete", "GET", f"/api/trips/{trip_id}/settlement", 200, headers=owner)
    print("OK" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"))

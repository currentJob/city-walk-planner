"""참여 시도 IP 레이트 리밋 — DSN-08 (설계서 §6.17 · NFR-006 · AC-040).

**코드 유효성을 보기 전에** 막는다. 순서가 뒤집히면 공격자는 429 를 받기 전에 코드가
맞는지 아닌지를 이미 알게 된다.

카운터는 인메모리가 아니라 **DB 테이블**이다. 이유 둘: 시계를 주입하면 그대로 결정론
테스트가 되고, 프로세스 재시작으로 카운터가 리셋되지 않는다.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from city_walk_planner.api.errors import RateLimitedError
from city_walk_planner.clock import Clock
from city_walk_planner.config import Settings, env_value
from city_walk_planner.domain.util import format_iso_utc, parse_iso_utc
from city_walk_planner.storage import repo_cache

__all__ = ["client_ip", "enforce_join_rate_limit"]


def client_ip(request: object) -> str:
    """기본은 소켓 주소다 — 클라이언트가 마음대로 쓸 수 있는 헤더로 리밋을 걸면 리밋이 없는 것과 같다.

    다만 앞단(프록시·엣지) 뒤에서는 소켓 주소가 전부 그 앞단 하나라, 모든 사용자가 리밋 하나를
    나눠 쓰게 된다. 그래서 `CWP_CLIENT_IP_HEADER` 로 **앞단이 직접 덮어쓰는** 헤더 하나만
    믿도록 연다(Cloudflare `CF-Connecting-IP`, 로컬 nginx `X-Real-IP`). 그 앞단을 거치지 않고
    서버에 바로 닿을 수 있는 배치에서는 설정하지 않는다.
    """
    header = env_value("CLIENT_IP_HEADER")
    headers = getattr(request, "headers", None)
    if header and headers is not None:
        value = str(headers.get(header) or "").split(",")[0].strip()
        if value:
            return value
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host) if host else "unknown"


def enforce_join_rate_limit(
    conn: sqlite3.Connection,
    clock: Clock,
    settings: Settings,
    ip: str,
) -> None:
    """임계 초과면 `RateLimitedError`(429 + `Retry-After`). 통과하면 시도를 기록한다.

    기록은 **자동 커밋**으로 남긴다(트랜잭션 안에서 하면 뒤의 실패와 함께 롤백돼
    실패한 시도가 세어지지 않는다 — 그러면 리밋이 아무것도 막지 못한다).
    """
    now = clock.now_utc()
    window_start = format_iso_utc(now - timedelta(seconds=settings.join_rate_limit_window_s))
    repo_cache.prune_attempts(conn, window_start)

    attempts = repo_cache.count_recent_attempts(conn, ip, window_start)
    if attempts >= settings.join_rate_limit_n:
        oldest = repo_cache.oldest_attempt_at(conn, ip, window_start)
        elapsed = 0.0 if oldest is None else (now - parse_iso_utc(oldest)).total_seconds()
        retry_after = max(1, int(settings.join_rate_limit_window_s - elapsed) + 1)
        raise RateLimitedError(retry_after)

    repo_cache.record_attempt(conn, ip, format_iso_utc(now))

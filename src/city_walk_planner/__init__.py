"""City Walk Planner — 도시를 걷는 여행 플래너 (도시 가이드·일정·맛집·홍콩/마카오 트렌드 코스·동행 일정 공유).

정적 HTML 한 장(`reference/original-static-page.html`)을 서버 기반 공유 가이드로 옮긴 것이다.
배포 단위는 파이썬 프로세스 하나이고, FastAPI 가 API 와 정적 프론트를 함께 서빙한다.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"

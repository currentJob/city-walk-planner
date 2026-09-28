"""Run the local City Walk Planner backend."""

import uvicorn

from city_walk_planner.config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("city_walk_planner.api.app:create_app", factory=True,
                host=settings.host, port=settings.port, proxy_headers=False)

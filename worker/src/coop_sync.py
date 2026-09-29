"""Lock primitives for the Durable Object, where requests interleave on one thread.

The app guards its caches and the 1 request/second Nominatim spacing with `threading` locks. In the
Worker there are no threads, but a request that waits on an outbound `fetch` (via `run_sync`) lets the
next request start. If that request then blocks on a `threading.Lock` the first one holds, nothing
can ever release it — the object hangs (seen as "Network connection lost" / timeouts under
concurrent place searches).

These drop-in replacements keep the same exclusion but, while contended, yield to the event loop
(`pause`) so the holder can finish its fetch and release. `pause` is injected; the Worker passes a
`run_sync(asyncio.sleep(...))` based one, tests pass their own.
"""

from __future__ import annotations

import time
import types
from collections.abc import Callable
from typing import Any


class Lock:
    def __init__(self, pause: Callable[[], None]) -> None:
        self._pause = pause
        self._held = False

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        deadline = None if timeout is None or timeout < 0 else time.monotonic() + timeout
        while self._held:
            if not blocking or (deadline is not None and time.monotonic() >= deadline):
                return False
            self._pause()
        self._held = True
        return True

    def release(self) -> None:
        if not self._held:
            raise RuntimeError("release unlocked lock")
        self._held = False

    def locked(self) -> bool:
        return self._held

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


class BoundedSemaphore:
    def __init__(self, value: int, pause: Callable[[], None]) -> None:
        self._pause = pause
        self._value = self._initial = value

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        deadline = None if timeout is None or timeout < 0 else time.monotonic() + timeout
        while self._value <= 0:
            if not blocking or (deadline is not None and time.monotonic() >= deadline):
                return False
            self._pause()
        self._value -= 1
        return True

    def release(self) -> None:
        if self._value >= self._initial:
            raise ValueError("Semaphore released too many times")
        self._value += 1

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


def threading_module(pause: Callable[[], None]) -> Any:
    """A stand-in for the `threading` names the app uses (`Lock`, `BoundedSemaphore`)."""
    return types.SimpleNamespace(Lock=lambda: Lock(pause),
                                 BoundedSemaphore=lambda value=1: BoundedSemaphore(value, pause))


def install(pause: Callable[[], None]) -> None:
    """Point the app's lock users at the cooperative primitives. Call before `create_app()`."""
    from city_walk_planner.api.routes import explore
    from city_walk_planner.services.external import cache, discovery, nearby, reviews

    coop = threading_module(pause)
    for module in (discovery, nearby, cache):  # these create locks when providers are built
        module.threading = coop
    explore._slots = coop.BoundedSemaphore(2)  # module-level, created at import
    reviews._slots = coop.BoundedSemaphore(1)

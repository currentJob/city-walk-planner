"""Cooperative locks used inside the Durable Object: same exclusion, but a contended acquire yields."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker" / "src"))

import coop_sync  # noqa: E402


def test_contended_lock_yields_until_the_holder_releases():
    pauses = []
    lock = coop_sync.Lock(lambda: (pauses.append(1), lock.release() if len(pauses) == 3 else None))
    assert lock.acquire()
    assert not lock.acquire(blocking=False)
    assert lock.acquire()  # yields three times; the "other request" releases on the third
    assert len(pauses) == 3 and lock.locked()
    lock.release()
    with pytest.raises(RuntimeError):
        lock.release()


def test_bounded_semaphore_counts_and_refuses_extra_release():
    slots = coop_sync.BoundedSemaphore(2, lambda: None)
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    assert not slots.acquire(blocking=False)  # the app's "busy" path
    slots.release()
    slots.release()
    with pytest.raises(ValueError):
        slots.release()


def test_install_rewires_every_app_lock(monkeypatch):
    from city_walk_planner.api.routes import explore
    from city_walk_planner.services.external import cache, discovery, nearby, reviews

    for module in (discovery, nearby, cache):
        monkeypatch.setattr(module, "threading", module.threading)
    monkeypatch.setattr(explore, "_slots", explore._slots)
    monkeypatch.setattr(reviews, "_slots", reviews._slots)
    coop_sync.install(lambda: None)
    assert isinstance(discovery.DiscoveryProvider()._lock, coop_sync.Lock)
    assert isinstance(explore._slots, coop_sync.BoundedSemaphore)
    assert isinstance(reviews._slots, coop_sync.BoundedSemaphore)

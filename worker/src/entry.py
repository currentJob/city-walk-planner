"""Cloudflare Worker entry: every request goes to one Durable Object that runs the FastAPI app.

Why one object: the app keeps its state in SQLite and expects one writer at a time. A single
SQLite-backed Durable Object gives exactly that (requests are serialized, storage is transactional),
so the existing services and repositories run unchanged on top of `do_sqlite.DODatabase`.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import types

from workers import DurableObject, WorkerEntrypoint, asgi  # type: ignore[import-not-found]

# String settings copied from Worker vars/secrets into os.environ, where the app reads them.
ENV_KEYS = ("CWP_ALLOWED_ORIGINS", "CWP_GOOGLE_PLACES_API_KEY", "CWP_DISCOVERY_OVERPASS_URL")
OBJECT_NAME = "main"


def _install_sqlite3_stub() -> None:
    """The app imports `sqlite3` for types and `IntegrityError`; Pyodide may not ship the module."""
    try:
        import sqlite3  # noqa: F401
        return
    except ImportError:
        pass
    from do_sqlite import Row

    stub = types.ModuleType("sqlite3")

    class Error(Exception): ...
    class DatabaseError(Error): ...
    class IntegrityError(DatabaseError): ...
    class OperationalError(DatabaseError): ...
    class Connection: ...

    def connect(*_args, **_kwargs):
        raise OperationalError("sqlite3 files are not available in the Worker; storage is the Durable Object")

    for name, value in dict(Error=Error, DatabaseError=DatabaseError, IntegrityError=IntegrityError,
                            OperationalError=OperationalError, Connection=Connection, Row=Row,
                            connect=connect).items():
        setattr(stub, name, value)
    sys.modules["sqlite3"] = stub


def _bootstrap(env) -> None:
    from pyodide.ffi import run_sync  # type: ignore[import-not-found]

    for key in ENV_KEYS:
        value = getattr(env, key, None)
        if isinstance(value, str) and value:
            os.environ[key] = value
    _install_sqlite3_stub()
    import fetch_transport

    fetch_transport.install()
    # Rate-limit pauses (e.g. 1 request/second to Nominatim) must wait, not spin the CPU.
    time.sleep = lambda seconds: run_sync(asyncio.sleep(seconds))
    # FastAPI runs sync handlers/dependencies via anyio worker threads; Workers have no threads.
    # The Durable Object serializes requests anyway, so run them inline on the event loop.
    import anyio.to_thread

    async def run_inline(func, *args, abandon_on_cancel=False, cancellable=None, limiter=None):
        return func(*args)

    anyio.to_thread.run_sync = run_inline


class AppDO(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.app = None

    def _build(self):
        _bootstrap(self.env)
        from do_sqlite import DODatabase
        from pyodide.ffi import create_once_callable, jsnull  # type: ignore[import-not-found]

        from city_walk_planner.api.app import create_app
        from city_walk_planner.config import load_settings
        from city_walk_planner.storage.db import SCHEMA_PATH

        db = DODatabase(
            self.ctx.storage,
            SCHEMA_PATH,
            to_py=lambda value: value.to_py() if hasattr(value, "to_py") else value,
            to_js=lambda value: jsnull if value is None else value,
            once=create_once_callable,
        )
        return create_app(settings=load_settings(env=dict(os.environ)), db=db)

    async def fetch(self, request):
        if self.app is None:
            self.app = self._build()
        return await asgi.fetch(self.app, request, self.env)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        stub = self.env.APP.getByName(OBJECT_NAME)
        return await stub.fetch(getattr(request, "js_object", request))

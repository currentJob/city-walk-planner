"""A CPython stand-in for a Durable Object's `ctx.storage`, backed by an in-memory sqlite3 database.

It mirrors the parts of the Workers API that `worker/src/do_sqlite.py` relies on and, like the real
runtime, refuses transaction statements in `sql.exec` — so a test run with this fake proves the app
never sends `BEGIN`/`SAVEPOINT` itself and that `transactionSync` rollback semantics hold.
Run the API suite on it with `CWP_TEST_STORAGE=durable-object`.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker" / "src"))

from do_sqlite import DODatabase  # noqa: E402

_FORBIDDEN = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|END)\b", re.I)


class _Cursor:
    def __init__(self, cols: list[str], rows: list[tuple[Any, ...]], written: int) -> None:
        self.columnNames = cols
        self.rowsWritten = written
        self._rows = rows

    def raw(self) -> _Cursor:
        return self

    def toArray(self) -> list[list[Any]]:  # noqa: N802 — Workers API name
        return [list(row) for row in self._rows]


class _Sql:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def exec(self, query: str, *params: Any) -> _Cursor:
        if _FORBIDDEN.match(query):
            raise RuntimeError("Error: To execute a transaction, please use the state.storage.transaction() API")
        before = self._conn.total_changes
        try:
            try:
                cur = self._conn.execute(query, params)
            except sqlite3.ProgrammingError:
                if params:
                    raise
                self._conn.executescript(query)  # like the runtime, several statements without bindings
                return _Cursor([], [], self._conn.total_changes - before)
        except sqlite3.Error as exc:  # the runtime surfaces SQLite errors as plain JS errors
            raise RuntimeError(f"Error: {exc}") from None
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return _Cursor(cols, rows, self._conn.total_changes - before)


class FakeDurableStorage:
    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")  # Durable Object SQLite enforces foreign keys
        self.sql = _Sql(self._conn)
        self._depth = 0

    def transactionSync(self, callback: Any) -> Any:  # noqa: N802 — Workers API name
        name = f"tx{self._depth}"
        self._conn.execute(f"SAVEPOINT {name}")
        self._depth += 1
        try:
            result = callback()
        except BaseException:
            self._conn.execute(f"ROLLBACK TO {name}")
            self._conn.execute(f"RELEASE {name}")
            raise
        finally:
            self._depth -= 1
        self._conn.execute(f"RELEASE {name}")
        return result


def durable_database() -> DODatabase:
    from city_walk_planner.storage.db import SCHEMA_PATH

    return DODatabase(FakeDurableStorage(), SCHEMA_PATH)

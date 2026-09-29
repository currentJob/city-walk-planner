"""A sqlite3-shaped adapter over a Cloudflare Durable Object's SQLite storage (`ctx.storage`).

The app's repositories speak a small slice of `sqlite3`: `execute` → `fetchone`/`fetchall`/`rowcount`,
`executemany`, `executescript`, rows addressable by column name. Durable Object SQL is synchronous
too (`ctx.storage.sql.exec`), so this adapter lets the existing code run unchanged.

Differences it absorbs:
- `BEGIN`/`COMMIT` and connection PRAGMAs are not accepted by `sql.exec` → transactions go through
  `storage.transactionSync(callback)` (see `storage.db.transaction`), PRAGMAs become no-ops.
- Constraint failures surface as JS errors → re-raised as `sqlite3.IntegrityError` so the app's
  `except sqlite3.IntegrityError` keeps working.

`to_py` / `to_js` / `once` are injected by the Worker (Pyodide FFI); plain Python fakes use the defaults,
which is how tests exercise this module under CPython.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_NO_OP = re.compile(r"^\s*(PRAGMA\b|BEGIN\b|COMMIT\b|END\b|ROLLBACK\b|SAVEPOINT\b|RELEASE\b)", re.I)
_PRAGMA_STATEMENT = re.compile(r"^\s*PRAGMA\b[^;]*;", re.I | re.M)


def _identity(value: Any) -> Any:
    return value


class Row:
    """Behaves like `sqlite3.Row`: index or column name, `keys()`, `dict(row)`."""

    __slots__ = ("_cols", "_index", "_vals")

    def __init__(self, cols: Sequence[str], vals: Sequence[Any]) -> None:
        self._cols = tuple(cols)
        self._vals = tuple(vals)
        self._index = {name.lower(): i for i, name in enumerate(self._cols)}

    def __getitem__(self, key: int | slice | str) -> Any:
        if isinstance(key, str):
            try:
                return self._vals[self._index[key.lower()]]
            except KeyError:
                raise IndexError(f"No item with that key: {key}") from None
        return self._vals[key]

    def keys(self) -> list[str]:
        return list(self._cols)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._vals)

    def __len__(self) -> int:
        return len(self._vals)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Row) and (self._cols, self._vals) == (other._cols, other._vals)

    def __hash__(self) -> int:
        return hash((self._cols, self._vals))

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._cols, self._vals, strict=True))!r})"


class Cursor:
    __slots__ = ("_rows", "lastrowid", "rowcount")

    def __init__(self, rows: list[Row], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = None

    def fetchone(self) -> Row | None:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[Row]:
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self) -> Iterator[Row]:
        return iter(self.fetchall())


def _integrity_error(exc: BaseException) -> BaseException:
    import sqlite3  # resolved lazily: the Worker may install a stub module under this name

    text = str(exc)
    if "constraint failed" in text.lower():
        return sqlite3.IntegrityError(text)
    return sqlite3.DatabaseError(text)


class DOConnection:
    """One long-lived connection per Durable Object instance (requests are serialized by the object)."""

    row_factory: Any = None  # accepted and ignored — rows are always `Row`

    def __init__(self, storage: Any, *, to_py: Callable[[Any], Any] = _identity,
                 to_js: Callable[[Any], Any] = _identity, once: Callable[[Any], Any] = _identity) -> None:
        self._storage = storage
        self._sql = storage.sql
        self._to_py = to_py
        self._to_js = to_js
        self._once = once

    def _param(self, value: Any) -> Any:
        if isinstance(value, bool):  # SQLite has no boolean; sqlite3 stores 0/1
            return int(value)
        return self._to_js(value)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Cursor:
        if _NO_OP.match(sql):
            return Cursor([], -1)
        try:
            cursor = self._sql.exec(sql, *[self._param(p) for p in (params or ())])
            cols = list(self._to_py(cursor.columnNames))
            raw = self._to_py(cursor.raw().toArray())
            written = int(self._to_py(cursor.rowsWritten))
        except Exception as exc:  # noqa: BLE001 — the runtime raises JS errors, not sqlite3 ones
            raise _integrity_error(exc) from exc
        return Cursor([Row(cols, list(values)) for values in raw], written)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> Cursor:
        total = 0
        for params in seq:
            total += max(self.execute(sql, params).rowcount, 0)
        return Cursor([], total)

    def executescript(self, script: str) -> None:
        body = _PRAGMA_STATEMENT.sub("", script)
        try:
            self._sql.exec(body)
        except Exception as exc:  # noqa: BLE001
            raise _integrity_error(exc) from exc

    def run_in_transaction[T](self, work: Callable[[], T]) -> T:
        """`storage.transactionSync`: commits if `work` returns, rolls back if it raises."""
        box: dict[str, Any] = {}

        def callback() -> None:
            try:
                box["value"] = work()
            except BaseException as exc:
                box["error"] = exc
                raise

        try:
            self._storage.transactionSync(self._once(callback))
        except BaseException:
            if "error" in box:
                raise box["error"] from None
            raise
        return box.get("value")  # type: ignore[return-value]

    def commit(self) -> None:  # autocommit outside transactionSync
        pass

    def rollback(self) -> None:  # only used to end a read snapshot; nothing to undo
        pass

    def close(self) -> None:
        pass


class DODatabase:
    """Stands in for `storage.db.Database`."""

    path = None

    def __init__(self, storage: Any, schema_path: Path, **hooks: Callable[[Any], Any]) -> None:
        self._conn = DOConnection(storage, **hooks)
        self._schema_path = schema_path

    def connect(self) -> DOConnection:
        return self._conn

    @contextmanager
    def connection(self) -> Iterator[DOConnection]:
        yield self._conn

    def apply_schema(self) -> None:
        self._conn.executescript(self._schema_path.read_text(encoding="utf-8"))

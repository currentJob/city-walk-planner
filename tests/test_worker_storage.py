"""The Cloudflare Worker storage adapter keeps sqlite3 semantics the services rely on."""
import sqlite3

import pytest

from city_walk_planner.storage.db import transaction
from tests.do_fake import FakeDurableStorage, durable_database

INSERT = "INSERT INTO trip (id, name, start_date, invite_code, revision, created_at) VALUES (?, ?, ?, ?, 0, 'x')"


def _db():
    db = durable_database()
    db.apply_schema()
    return db


def test_schema_applies_without_pragmas_and_rows_behave_like_sqlite_rows():
    with _db().connection() as conn:
        conn.execute(INSERT, ("t1", "여행", "2026-10-05", "ABCD-EFGH-JKLM"))
        row = conn.execute("SELECT id, name FROM trip WHERE id = ?", ("t1",)).fetchone()
        assert row["id"] == "t1" and row[1] == "여행"
        assert dict(zip(row.keys(), row, strict=True)) == {"id": "t1", "name": "여행"}
        assert conn.execute("UPDATE trip SET name = ? WHERE id = ?", ("새 이름", "t1")).rowcount == 1


def test_transaction_commits_value_and_rolls_back_on_error():
    with _db().connection() as conn:
        insert = INSERT
        assert transaction(conn, lambda: conn.execute(insert, ("a", "A", "2026-10-05", "AAAA-AAAA-AAAA")).rowcount) == 1

        def fails():
            conn.execute(insert, ("b", "B", "2026-10-05", "BBBB-BBBB-BBBB"))
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):  # the original exception, not a runtime wrapper
            transaction(conn, fails)
        assert conn.execute("SELECT COUNT(*) AS n FROM trip").fetchone()["n"] == 1


def test_constraint_failures_raise_sqlite_integrity_error_and_transactions_are_never_sent_as_sql():
    with _db().connection() as conn:
        insert = INSERT
        conn.execute(insert, ("a", "A", "2026-10-05", "SAME-CODE-0000"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("b", "B", "2026-10-05", "SAME-CODE-0000"))
        assert conn.execute("BEGIN IMMEDIATE").rowcount == -1  # swallowed by the adapter
    with pytest.raises(RuntimeError, match="transaction"):
        FakeDurableStorage().sql.exec("BEGIN")  # what the real runtime would do if it leaked through


def test_api_suite_switch_really_uses_the_adapter(monkeypatch, settings, fixed_clock):
    from do_sqlite import DODatabase

    from city_walk_planner.api.app import create_app

    app = create_app(settings=settings, clock=fixed_clock, db=durable_database())
    assert isinstance(app.state.db, DODatabase)

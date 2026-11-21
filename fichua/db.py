"""Tiny database layer: one API over SQLite (local) and Postgres (Supabase / AWS RDS).

Write SQL once with `:name` parameters. Results are plain dicts with JSON-friendly
values (dates -> ISO strings, decimals -> float, binary -> bytes) so both engines behave
the same. No ORM on purpose: the schema in `schema.sql` is plain, portable Postgres SQL.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_PARAM = re.compile(r"(?<![:\w]):([a-zA-Z_]\w*)")

# Columns added after the first release. Postgres and SQLite differ in how "add if missing"
# works, so they are applied here instead of in schema.sql. Append only; never edit old lines.
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("media", "thumb", "BYTEA"),
    ("messages", "template", "TEXT"),
    ("messages", "params", "TEXT"),
    ("hotels", "status", "TEXT DEFAULT 'live'"),
    ("hotels", "owner_id", "TEXT"),
    ("hotels", "commission_pct", "NUMERIC(5,2)"),
    ("hotels", "phone", "TEXT"),
    ("hotels", "whatsapp", "TEXT"),
    ("hotels", "email", "TEXT"),
    ("hotels", "area", "TEXT"),
    ("hotels", "cancellation_policy", "TEXT DEFAULT 'flexible'"),
    ("hotels", "children_allowed", "BOOLEAN DEFAULT TRUE"),
    ("hotels", "pets_allowed", "BOOLEAN DEFAULT FALSE"),
    ("hotels", "smoking_allowed", "BOOLEAN DEFAULT FALSE"),
    ("hotels", "review_note", "TEXT"),
    ("hotels", "submitted_at", "TIMESTAMP"),
    ("hotels", "approved_at", "TIMESTAMP"),
    ("hotels", "plan", "TEXT DEFAULT 'listing'"),
    ("hotels", "manager_free_until", "DATE"),
    ("hotels", "terms_accepted_at", "TIMESTAMP"),
    ("room_types", "total_rooms", "INTEGER"),
    ("room_types", "base_price", "NUMERIC(10,2)"),
    ("room_types", "weekend_price", "NUMERIC(10,2)"),
    ("room_types", "room_kind", "TEXT"),
    ("bookings", "source", "TEXT DEFAULT 'fichua'"),
    ("bookings", "payment_status", "TEXT DEFAULT 'n/a'"),
    ("bookings", "hold_expires_at", "TIMESTAMP"),
    ("bookings", "paid_at", "TIMESTAMP"),
    ("bookings", "commission_pct", "NUMERIC(5,2)"),
    ("bookings", "commission_amount", "NUMERIC(10,2)"),
    ("bookings", "payout_amount", "NUMERIC(10,2)"),
    ("bookings", "offline_source", "TEXT"),
    ("bookings", "guest_language", "TEXT"),
    ("bookings", "stripe_session_id", "TEXT"),
]


def utcnow() -> datetime:
    """Naive UTC timestamp — what both engines store in TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _clean(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, memoryview):
        return value.tobytes()
    return value


def _sqlite_param(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


class Connection:
    """Wraps a DB-API connection with `all / one / scalar / run / run_many`."""

    def __init__(self, raw: Any, dialect: str):
        self.raw = raw
        self.dialect = dialect

    def _prepare(self, sql: str, params: Mapping[str, Any] | None):
        params = dict(params or {})
        if self.dialect == "postgres":
            return _PARAM.sub(r"%(\1)s", sql), params
        return sql, {k: _sqlite_param(v) for k, v in params.items()}

    def _rows(self, cursor) -> list[dict]:
        if cursor.description is None:
            return []
        cols = [c[0] for c in cursor.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cursor.fetchall()]

    def all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict]:
        cur = self.raw.cursor()
        cur.execute(*self._prepare(sql, params))
        return self._rows(cur)

    def one(self, sql: str, params: Mapping[str, Any] | None = None) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def run(self, sql: str, params: Mapping[str, Any] | None = None) -> int:
        cur = self.raw.cursor()
        cur.execute(*self._prepare(sql, params))
        return cur.rowcount

    def run_many(self, sql: str, rows: Iterable[Mapping[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        query, _ = self._prepare(sql, rows[0])
        if self.dialect == "sqlite":
            rows = [{k: _sqlite_param(v) for k, v in r.items()} for r in rows]
        self.raw.cursor().executemany(query, rows)

    def lock_clause(self) -> str:
        """Row-lock suffix for SELECTs that guard inventory or money (Postgres only)."""
        return " FOR UPDATE" if self.dialect == "postgres" else ""

    def in_params(self, values: Iterable[Any], prefix: str = "p") -> tuple[str, dict]:
        """`IN (...)` placeholders + params for a list of values."""
        params = {f"{prefix}{i}": v for i, v in enumerate(values)}
        return ", ".join(f":{k}" for k in params) or "NULL", params


class Database:
    def __init__(self, url: str):
        self.url = url
        self.dialect = "sqlite" if url.startswith("sqlite") else "postgres"
        self._migrated = not settings.auto_migrate

    def _open(self):
        if not self._migrated:
            self._migrated = True  # set first: migrate() itself opens connections
            self.migrate()
        return self._open_raw()

    def _open_raw(self):
        if self.dialect == "sqlite":
            path = self.url.split("sqlite:///", 1)[1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            raw = sqlite3.connect(path, timeout=10)
            raw.execute("PRAGMA foreign_keys = ON")
            return raw
        import psycopg  # imported lazily so local SQLite dev needs no Postgres driver

        # prepare_threshold=None keeps us compatible with Supabase's pgbouncer pooler.
        return psycopg.connect(self.url, prepare_threshold=None, connect_timeout=10)

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """One transaction: commits on success, rolls back on error."""
        raw = self._open()
        try:
            yield Connection(raw, self.dialect)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    def _existing_columns(self, raw, table: str) -> set[str]:
        if self.dialect == "sqlite":
            return {row[1] for row in raw.execute(f"PRAGMA table_info({table})").fetchall()}
        cur = raw.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
        return {row[0] for row in cur.fetchall()}

    def migrate(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        raw = self._open_raw()
        try:
            if self.dialect == "sqlite":
                raw.executescript(sql)
            else:
                raw.execute(sql)
            cache: dict[str, set[str]] = {}
            for table, column, ddl in COLUMN_MIGRATIONS:
                cols = cache.setdefault(table, self._existing_columns(raw, table))
                if column not in cols:
                    raw.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                    cols.add(column)
            raw.commit()
        finally:
            raw.close()


db = Database(settings.database_url)

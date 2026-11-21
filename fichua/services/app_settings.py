"""Business settings the Fichua admin changes from the Settings page (stored in the DB)."""
from __future__ import annotations

from ..db import Connection

DEFAULTS: dict[str, str] = {
    "commission_pct": "7",             # default commission on Fichua bookings
    "payout_timing": "immediate",      # immediate | after_checkin | weekly
    "payout_delay_hours": "24",        # used when payout_timing = after_checkin
    "rate_RWF": "1450",                # 1 USD in Rwandan francs (set by admin)
    "rate_XOF": "565",                 # 1 USD in CFA francs (BCEAO, Benin + Côte d'Ivoire)
    "admin_whatsapp": "",              # where Fichua's own payment alerts go
    "manager_fee_usd": "0",            # monthly Hotel Manager fee (not charged yet)
    "hold_minutes": "35",              # how long an unpaid checkout holds the room
    "company_name": "Fichua",          # legal name shown on the terms and privacy pages
    "contact_email": "",               # where guests and hotels write about bookings and their data
    "company_address": "",             # optional postal address for the legal pages
}

PAYOUT_TIMINGS = {
    "immediate": "Right after the guest pays",
    "after_checkin": "After the guest checks in",
    "weekly": "Every Monday",
}


def all_settings(conn: Connection) -> dict[str, str]:
    values = dict(DEFAULTS)
    for row in conn.all("SELECT key, value FROM settings"):
        if row["value"] is not None:
            values[row["key"]] = row["value"]
    return values


def get(conn: Connection, key: str) -> str:
    row = conn.one("SELECT value FROM settings WHERE key = :k", {"k": key})
    return row["value"] if row and row["value"] is not None else DEFAULTS.get(key, "")


def get_float(conn: Connection, key: str) -> float:
    try:
        return float(get(conn, key))
    except ValueError:
        return float(DEFAULTS.get(key, "0") or 0)


def put(conn: Connection, key: str, value: str) -> None:
    conn.run("INSERT INTO settings (key, value) VALUES (:k, :v) "
             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", {"k": key, "v": value})


def next_number(conn: Connection, key: str, start: int = 1) -> int:
    """A simple counter in settings (used for hotel IDs like FH-00042)."""
    current = int(get(conn, key) or start - 1)
    put(conn, key, str(current + 1))
    return current + 1

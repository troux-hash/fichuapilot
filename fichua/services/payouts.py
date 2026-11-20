"""Hotel payouts: scheduled when a guest pays, released on the timing set in admin.

Methods today:
  test   — Fichua's test checkout: the payout is marked sent instantly (no real money).
  manual — real payments without automated transfers yet: the payout becomes 'due' and the
           admin pays the hotel (bank / mobile money) and marks it sent.
Automated transfers to hotel bank accounts (Stripe Global Payouts) plug in at `release()`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from ..db import Connection, utcnow
from . import app_settings, payments


def due_time(conn: Connection, check_in: str) -> datetime:
    timing = app_settings.get(conn, "payout_timing")
    now = utcnow()
    if timing == "after_checkin":
        hours = app_settings.get_float(conn, "payout_delay_hours")
        start = datetime.fromisoformat(check_in[:10]).replace(hour=12)
        return max(now, start + timedelta(hours=hours))
    if timing == "weekly":
        days = (7 - now.weekday()) % 7 or 7  # next Monday
        return (now + timedelta(days=days)).replace(hour=8, minute=0, second=0)
    return now


def schedule(conn: Connection, booking: dict) -> str:
    payout_id = str(uuid.uuid4())
    conn.run("INSERT INTO payouts (id, booking_id, hotel_id, amount, currency, status, due_at) "
             "VALUES (:id, :b, :h, :a, 'USD', 'scheduled', :due)",
             {"id": payout_id, "b": booking["id"], "h": booking["hotel_id"], "a": booking["payout_amount"],
              "due": due_time(conn, booking["check_in"])})
    return payout_id


def release(conn: Connection, payout_id: str) -> None:
    method = "test" if payments.provider() == "test" else "manual"
    if method == "test":
        conn.run("UPDATE payouts SET status = 'sent', sent_at = :t, method = 'test', "
                 "note = 'Test mode: no real money moved' WHERE id = :id", {"t": utcnow(), "id": payout_id})
    else:
        conn.run("UPDATE payouts SET status = 'due', method = 'manual', "
                 "note = 'Pay the hotel, then mark as sent' WHERE id = :id", {"id": payout_id})


def process_due(conn: Connection) -> int:
    due = conn.all("SELECT id FROM payouts WHERE status = 'scheduled' AND due_at <= :now", {"now": utcnow()})
    for p in due:
        release(conn, p["id"])
    return len(due)


def mark_sent(conn: Connection, payout_id: str, note: str = "") -> None:
    conn.run("UPDATE payouts SET status = 'sent', sent_at = :t, method = COALESCE(method, 'manual'), "
             "note = :n WHERE id = :id AND status IN ('due', 'scheduled')",
             {"t": utcnow(), "n": note or "Paid by Fichua admin", "id": payout_id})


def on_cancel(conn: Connection, booking_id: str) -> None:
    """Cancel a payout that hasn't gone out; flag one that has, so the admin can recover it."""
    conn.run("UPDATE payouts SET status = 'cancelled' WHERE booking_id = :b AND status IN ('scheduled', 'due')",
             {"b": booking_id})
    conn.run("UPDATE payouts SET status = 'recover', note = 'Guest refunded after payout: recover from hotel' "
             "WHERE booking_id = :b AND status = 'sent' AND method <> 'test'", {"b": booking_id})
    conn.run("UPDATE payouts SET status = 'cancelled', note = 'Test payout reversed' "
             "WHERE booking_id = :b AND status = 'sent' AND method = 'test'", {"b": booking_id})

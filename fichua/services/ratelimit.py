"""Rate limits kept in the database, so they hold across every Vercel instance."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import Request

from ..db import Connection, utcnow

# scope: (attempts allowed, window in minutes)
LIMITS = {
    "admin": (5, 15),     # failed admin sign-ins per IP
    "partner": (8, 15),   # failed partner sign-ins per IP and email
    "join": (10, 60),     # failed partner sign-ups (wrong access codes) per IP
    "booking": (30, 10),  # checkouts started per IP: each one holds a room
    "ask": (20, 10),      # 'Ask the hotel' enquiries recorded per IP (past it, WhatsApp still opens, unrecorded)
}
MESSAGES = {
    "admin": "Too many failed sign-ins. Try again in 15 minutes.",
    "partner": "Too many failed sign-ins. Try again in 15 minutes, or ask the Fichua team to reset your password.",
    "join": "Too many attempts with a wrong code. Try again in an hour, or ask the Fichua team for your code.",
    "booking": "Too many bookings from this connection. Please wait a few minutes and try again.",
}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def blocked(conn: Connection, scope: str, key: str) -> bool:
    limit, minutes = LIMITS[scope]
    since = utcnow() - timedelta(minutes=minutes)
    count = conn.scalar("SELECT COUNT(*) FROM login_attempts WHERE scope = :s AND key = :k AND created_at > :t",
                        {"s": scope, "k": key[:200], "t": since})
    return (count or 0) >= limit


def record(conn: Connection, scope: str, key: str) -> None:
    now = utcnow()
    conn.run("INSERT INTO login_attempts (id, scope, key, created_at) VALUES (:id, :s, :k, :t)",
             {"id": str(uuid.uuid4()), "s": scope, "k": key[:200], "t": now})
    conn.run("DELETE FROM login_attempts WHERE created_at < :old", {"old": now - timedelta(days=1)})


def clear(conn: Connection, scope: str, key: str) -> None:
    conn.run("DELETE FROM login_attempts WHERE scope = :s AND key = :k", {"s": scope, "k": key[:200]})

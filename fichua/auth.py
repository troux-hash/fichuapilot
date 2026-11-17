"""Admin auth: one password (env var) → signed, expiring cookie. Stdlib only.

Replace with Supabase Auth / magic links when hotel partners get their own logins (backlog #15).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Request

from .config import settings

COOKIE = "fichua_admin"
TTL_SECONDS = 60 * 60 * 12


def _sign(payload: str) -> str:
    return hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def check_password(password: str) -> bool:
    if not settings.admin_password:
        return False  # admin disabled until ADMIN_PASSWORD is set
    return hmac.compare_digest(password.encode(), settings.admin_password.encode())


def make_token() -> str:
    payload = f"admin.{int(time.time()) + TTL_SECONDS}"
    return f"{payload}.{_sign(payload)}"


def is_admin(request: Request) -> bool:
    token = request.cookies.get(COOKIE, "")
    try:
        role, expires, sig = token.split(".")
    except ValueError:
        return False
    payload = f"{role}.{expires}"
    return (role == "admin" and expires.isdigit() and int(expires) > time.time()
            and hmac.compare_digest(sig, _sign(payload)))

"""Sessions as signed, expiring cookies (stdlib HMAC). Admin: one password from env.
Partners: email + password accounts (see services/partners.py)."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Request

from .config import settings

COOKIE = "fichua_admin"
PARTNER_COOKIE = "fichua_partner"
TTL_SECONDS = 60 * 60 * 12
PARTNER_TTL_SECONDS = 60 * 60 * 24 * 30


def _sign(payload: str) -> str:
    return hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _token(subject: str, ttl: int) -> str:
    payload = f"{subject}.{int(time.time()) + ttl}"
    return f"{payload}.{_sign(payload)}"


def _read(token: str) -> str | None:
    try:
        subject, expires, sig = token.rsplit(".", 2)
    except ValueError:
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    return subject if hmac.compare_digest(sig, _sign(f"{subject}.{expires}")) else None


def check_password(password: str) -> bool:
    if not settings.admin_password:
        return False  # admin disabled until ADMIN_PASSWORD is set
    return hmac.compare_digest(password.encode(), settings.admin_password.encode())


def make_token() -> str:
    return _token("admin", TTL_SECONDS)


def is_admin(request: Request) -> bool:
    return _read(request.cookies.get(COOKIE, "")) == "admin"


def make_partner_token(user_id: str) -> str:
    return _token(f"partner:{user_id}", PARTNER_TTL_SECONDS)


def partner_user_id(request: Request) -> str | None:
    subject = _read(request.cookies.get(PARTNER_COOKIE, ""))
    return subject.split(":", 1)[1] if subject and subject.startswith("partner:") else None

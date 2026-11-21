"""Time-based one-time codes (RFC 6238): the 6-digit codes Google Authenticator, Authy or 1Password show."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, at: float | None = None, digits: int = DIGITS) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // STEP)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return f"{value:0{digits}d}"


def verify(secret: str | None, code: str | None, at: float | None = None) -> bool:
    """Accepts the current code and the ones just before and after it (phone clocks drift)."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if not secret or len(code) != DIGITS:
        return False
    now = time.time() if at is None else at
    return any(hmac.compare_digest(code_at(secret, now + drift * STEP), code) for drift in (-1, 0, 1))


def setup_uri(secret: str, email: str, issuer: str = "Fichua") -> str:
    """otpauth:// link: on a phone it opens the authenticator app with the account filled in."""
    return (f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}"
            f"&digits={DIGITS}&period={STEP}")


def grouped(secret: str) -> str:
    """'ABCD EFGH …' is easier to type into an authenticator app."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))

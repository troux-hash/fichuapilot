"""Named Fichua admin accounts, with optional two-step login.

Until the first account exists, the shared ADMIN_PASSWORD signs in, so the owner can create it. From then
on only named accounts sign in, and a session made with the shared password stops working. Lost access?
`python scripts/admin_users.py reset <email>` sets a new password from the owner's machine.
"""
from __future__ import annotations

import re
import uuid

from ..db import Connection, utcnow
from . import totp
from .partners import check_password, hash_password

MIN_PASSWORD = 10
SHARED = {"id": None, "name": "Shared admin password", "email": "", "shared": True}


class AdminError(Exception):
    pass


def count_active(conn: Connection) -> int:
    return conn.scalar("SELECT COUNT(*) FROM admin_users WHERE is_active = TRUE") or 0


def get(conn: Connection, user_id: str) -> dict | None:
    return conn.one("SELECT * FROM admin_users WHERE id = :id", {"id": user_id})


def all_users(conn: Connection) -> list[dict]:
    return conn.all("SELECT * FROM admin_users ORDER BY created_at")


def current(conn: Connection, subject: str | None) -> dict | None:
    """The admin behind a session: 'admin' is the shared password, 'admin:<id>' a named account."""
    if subject == "admin":
        return SHARED if count_active(conn) == 0 else None
    if subject and subject.startswith("admin:"):
        user = get(conn, subject.split(":", 1)[1])
        return {**user, "shared": False} if user and user["is_active"] else None
    return None


def _check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AdminError(f"Use a password of at least {MIN_PASSWORD} characters.")


def create(conn: Connection, name: str, email: str, password: str) -> dict:
    name, email = (name or "").strip(), (email or "").strip().lower()
    if len(name) < 2:
        raise AdminError("Enter the person's name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AdminError("Enter an email like name@company.com.")
    _check_password(password)
    if conn.one("SELECT id FROM admin_users WHERE email = :e", {"e": email}):
        raise AdminError("There is already an admin with that email.")
    user_id = str(uuid.uuid4())
    conn.run("INSERT INTO admin_users (id, email, name, password_hash, is_active, created_at) "
             "VALUES (:id, :email, :name, :hash, TRUE, :t)",
             {"id": user_id, "email": email, "name": name, "hash": hash_password(password), "t": utcnow()})
    return get(conn, user_id)


def authenticate(conn: Connection, email: str, password: str, code: str) -> dict | None:
    user = conn.one("SELECT * FROM admin_users WHERE email = :e AND is_active = TRUE",
                    {"e": (email or "").strip().lower()})
    if not user or not check_password(password or "", user["password_hash"]):
        return None
    if user["totp_secret"] and not totp.verify(user["totp_secret"], code):
        return None
    conn.run("UPDATE admin_users SET last_login_at = :t WHERE id = :id", {"t": utcnow(), "id": user["id"]})
    return user


def change_password(conn: Connection, user: dict, current_password: str, new_password: str) -> None:
    if not check_password(current_password or "", user["password_hash"]):
        raise AdminError("Your current password is wrong.")
    _check_password(new_password)
    conn.run("UPDATE admin_users SET password_hash = :h WHERE id = :id",
             {"h": hash_password(new_password), "id": user["id"]})


def set_active(conn: Connection, actor: dict, user_id: str, active: bool) -> None:
    if not active and actor.get("id") == user_id:
        raise AdminError("You can't turn off your own account.")
    if not active and count_active(conn) <= 1:
        raise AdminError("Keep at least one active admin.")
    conn.run("UPDATE admin_users SET is_active = :a WHERE id = :id", {"a": active, "id": user_id})


def start_two_step(conn: Connection, user: dict) -> str:
    secret = totp.new_secret()
    conn.run("UPDATE admin_users SET totp_pending = :s WHERE id = :id", {"s": secret, "id": user["id"]})
    return secret


def confirm_two_step(conn: Connection, user: dict, code: str) -> None:
    if not totp.verify(user.get("totp_pending"), code):
        raise AdminError("That code didn't match. Type the newest code from the app (it changes every 30 seconds).")
    conn.run("UPDATE admin_users SET totp_secret = totp_pending, totp_pending = NULL WHERE id = :id",
             {"id": user["id"]})


def stop_two_step(conn: Connection, user: dict, code: str) -> None:
    if not totp.verify(user.get("totp_secret"), code):
        raise AdminError("That code didn't match. Type the newest code from your authenticator app.")
    conn.run("UPDATE admin_users SET totp_secret = NULL, totp_pending = NULL WHERE id = :id", {"id": user["id"]})


def reset(conn: Connection, email: str, new_password: str) -> bool:
    """Recovery from the command line: new password, two-step login off, account on."""
    _check_password(new_password)
    found = conn.one("SELECT id FROM admin_users WHERE email = :e", {"e": (email or "").strip().lower()})
    if not found:
        return False
    conn.run("UPDATE admin_users SET password_hash = :h, totp_secret = NULL, totp_pending = NULL, "
             "is_active = TRUE WHERE id = :id", {"h": hash_password(new_password), "id": found["id"]})
    return True

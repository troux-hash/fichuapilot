"""Fichua admin accounts from the command line, for when nobody can sign in.

Uses DATABASE_URL from .env, which is the LIVE database.

    python scripts/admin_users.py list
    python scripts/admin_users.py reset you@example.com   # new temporary password, two-step login off

The new password is printed once, here in your terminal. Sign in with it, then change it under Team.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fichua.db import db  # noqa: E402  (also loads .env)
from fichua.services import admins  # noqa: E402


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    with db.connect() as conn:
        if command == "list":
            for u in admins.all_users(conn):
                state = "active" if u["is_active"] else "off"
                print(f"{u['email']:<36} {u['name']:<24} {state:<7} two-step {'on' if u['totp_secret'] else 'off'}")
            if not admins.all_users(conn):
                print("No named admins yet: the shared ADMIN_PASSWORD signs in.")
        elif command == "reset" and len(sys.argv) == 3:
            password = secrets.token_urlsafe(12)
            if admins.reset(conn, sys.argv[2], password):
                print(f"New temporary password for {sys.argv[2]}: {password}")
                print("Two-step login is off for this account; turn it back on under Team.")
            else:
                print(f"No admin with the email {sys.argv[2]}.")
        else:
            print(__doc__)


if __name__ == "__main__":
    main()

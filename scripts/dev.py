"""Local dev server on http://localhost:8000 with auto-reload.

    python scripts/dev.py          # uses the local SQLite copy (data/fichua.db) — safe for test bookings
    python scripts/dev.py --prod   # uses DATABASE_URL from .env, i.e. the LIVE database (read carefully)

.env holds the production DATABASE_URL (for scripts/import_excel.py and Vercel parity), so
without this launcher a local preview would read and write live data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent

if "--prod" not in sys.argv:
    os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'fichua.db').as_posix()}"
    # Local admin uses a local password, never the live one from .env.
    os.environ["ADMIN_PASSWORD"] = os.getenv("LOCAL_ADMIN_PASSWORD", "admin")
    # Local runs never charge real cards or message real phones.
    os.environ["STRIPE_SECRET_KEY"] = os.getenv("LOCAL_STRIPE_SECRET_KEY", "")
    os.environ["WHATSAPP_TOKEN"] = os.getenv("LOCAL_WHATSAPP_TOKEN", "")

if __name__ == "__main__":
    os.chdir(ROOT)
    uvicorn.run("fichua.main:app", host="127.0.0.1", port=8000, reload=True, app_dir=str(ROOT))

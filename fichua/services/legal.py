"""Facts the terms, privacy and partner-terms pages show. They come from Settings, so the text stays true
when the commission, the booking hold or the company details change."""
from __future__ import annotations

from datetime import date

from ..db import Connection
from . import app_settings
from .partners import POLICIES

LAST_UPDATED = date(2026, 11, 21)


def facts(conn: Connection) -> dict:
    s = app_settings.all_settings(conn)
    return {
        "company": (s.get("company_name") or "").strip() or "Fichua",
        "email": (s.get("contact_email") or "").strip(),
        "address": (s.get("company_address") or "").strip(),
        "commission": s.get("commission_pct") or app_settings.DEFAULTS["commission_pct"],
        "hold_minutes": s.get("hold_minutes") or app_settings.DEFAULTS["hold_minutes"],
        "policies": POLICIES,
        "updated": LAST_UPDATED,
    }

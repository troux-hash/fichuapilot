"""Shared template setup and view helpers (filters, query-string builders)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .config import settings

templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "KES": "KSh ", "TZS": "TSh ", "ZAR": "R", "AED": "AED "}


def money(value, currency: str = "USD", decimals: bool = False) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency or "USD", f"{currency} ")
    amount = float(value or 0)
    return f"{symbol}{amount:,.2f}" if decimals else f"{symbol}{amount:,.0f}"


def nice_date(value, fmt: str = "%a %d %b") -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return d.strftime(fmt)


def qs(params: dict, **overrides) -> str:
    """Build a query string, dropping empty values; lists become repeated keys."""
    merged = {**params, **overrides}
    items = []
    for k, v in merged.items():
        if v in (None, "", False, []):
            continue
        if isinstance(v, (list, tuple)):
            items.extend((k, x) for x in v)
        else:
            items.append((k, v))
    return urlencode(items)


STATIC_DIR = Path(__file__).resolve().parent.parent / "public"
_DEPLOY_ID = (os.getenv("VERCEL_GIT_COMMIT_SHA") or "")[:8]


def asset(path: str) -> str:
    """Cache-busted static URL: file mtime locally, commit SHA on Vercel."""
    file = STATIC_DIR / path.lstrip("/")
    version = _DEPLOY_ID or (str(int(file.stat().st_mtime)) if file.exists() else "1")
    return f"{path}?v={version}"


templates.env.globals["asset"] = asset
templates.env.filters["money"] = money
templates.env.filters["nice_date"] = nice_date
templates.env.globals["qs"] = qs
templates.env.globals["app_name"] = settings.app_name


def render(request: Request, name: str, status_code: int = 200, **context):
    return templates.TemplateResponse(request, name, context, status_code=status_code)

"""Shared template setup and view helpers (filters, query-string builders, asset URLs)."""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates

from . import i18n
from .config import settings
from .services import currency, kinds

templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "RWF": "RWF ", "XOF": "FCFA "}


def money(value, currency_code: str = "USD", decimals: bool = False) -> str:
    code = currency_code or "USD"
    if code == "USD":
        return currency.usd(value, decimals)
    symbol = CURRENCY_SYMBOLS.get(code, f"{code} ")
    amount = float(value or 0)
    return f"{symbol}{amount:,.2f}" if decimals else f"{symbol}{amount:,.0f}"


def nice_date(value, fmt: str = "%a %d %b") -> str:
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value) if "T" in value or " " in value else date.fromisoformat(value)
    return value.strftime(fmt.replace("%d", str(value.day)))  # "Fri 4 Dec", not "Fri 04 Dec"


_WIDTH = re.compile(r"([?&])w=\d+")


def card_img(url: str | None) -> str | None:
    """A smaller copy of a photo (about 800 px) for cards and thumbnails, to save phone data.

    Partner photos have an 800 px version saved at upload (`/media/<id>?size=card`); Unsplash
    resizes on request. Anything else is returned as it is.
    """
    if not url:
        return url
    if url.startswith("/media/"):
        return f"{url}{'&' if '?' in url else '?'}size=card"
    if "images.unsplash.com" in url:
        return _WIDTH.sub(r"\1w=800", url) if _WIDTH.search(url) else f"{url}{'&' if '?' in url else '?'}w=800"
    return url


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


# Exchange rates change rarely; cache them briefly instead of querying on every price.
_rates: dict = {"at": 0.0, "values": {}}


def rates() -> dict[str, str]:
    if time.time() - _rates["at"] > 60:
        from .db import db
        from .services import app_settings
        with db.connect() as conn:
            _rates["values"] = app_settings.all_settings(conn)
        _rates["at"] = time.time()
    return _rates["values"]


def forget_rates() -> None:
    _rates["at"] = 0.0


def local(amount, country) -> str:
    return currency.local_text(amount, country, rates())


def base_url(request: Request) -> str:
    if settings.public_url:
        return settings.public_url
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


STATIC_DIR = Path(__file__).resolve().parent.parent / "public"
_DEPLOY_ID = (os.getenv("VERCEL_GIT_COMMIT_SHA") or "")[:8]


def asset(path: str) -> str:
    """Cache-busted static URL: file mtime locally, commit SHA on Vercel."""
    file = STATIC_DIR / path.lstrip("/")
    version = _DEPLOY_ID or (str(int(file.stat().st_mtime)) if file.exists() else "1")
    return f"{path}?v={version}"


# "Built at MIT" trust section. Official logo files go in public/static/img/trust/ (only with
# permission; see docs/BRAND_ASSETS.md). Without a file, the name is shown as text.
TRUST_PARTNERS = [
    {"key": "mit", "name": "MIT", "full": "Massachusetts Institute of Technology", "href": "https://www.mit.edu"},
    {"key": "mit-sandbox", "name": "MIT Sandbox", "full": "MIT Sandbox Innovation Fund", "href": "https://sandbox.mit.edu"},
    {"key": "kuo-sharper", "name": "MIT Kuo Sharper Center", "full": "MIT Kuo Sharper Center for Prosperity and Entrepreneurship",
     "href": "https://kuosharper.mit.edu"},
]
TRUST_LOGO_EXTS = ("svg", "png", "webp")


def trust_partners() -> list[dict]:
    """`<key>.svg|png|webp` shows on a white plate; `<key>-white.<ext>` (a reversed logo) on a dark plate."""
    folder = STATIC_DIR / "static" / "img" / "trust"
    out = []
    for p in TRUST_PARTNERS:
        logo, plate = None, "light"
        for name, tone in ((p["key"], "light"), (f"{p['key']}-white", "dark")):
            ext = next((e for e in TRUST_LOGO_EXTS if (folder / f"{name}.{e}").exists()), None)
            if ext:
                logo, plate = asset(f"/static/img/trust/{name}.{ext}"), tone
                break
        out.append({**p, "logo": logo, "plate": plate})
    return out


def local_price(amount, country) -> str:
    """'≈ 232,000 RWF' beside a dollar price, with French spacing in French."""
    found = currency.local_amount(amount, country, rates())
    if not found:
        return ""
    value, code = found
    return f"≈ {i18n.number(value)} {code}"


def money_split(total, commission_pct) -> dict:
    """Where the traveller's money goes (Brief 3 v3): what the host receives and Fichua's fee, paid by the host."""
    pct = float(commission_pct if commission_pct is not None else 7)
    fee = round(float(total or 0) * pct / 100, 2) if total else None
    return {"pct": pct, "host_pct": round(100 - pct, 2), "total": total, "fee": fee,
            "host": round(float(total) - fee, 2) if total else None}


def here(request: Request) -> str:
    """This page's path and query without ?lang=, for the EN/FR switch to come back to."""
    items = [(k, v) for k, v in request.query_params.multi_items() if k != "lang"]
    return request.url.path + (("?" + urlencode(items)) if items else "")


templates.env.globals["here"] = here
templates.env.globals["asset"] = asset
templates.env.globals["trust_partners"] = trust_partners
templates.env.globals.update(
    t=i18n.t, tn=i18n.tn, pick=i18n.pick, fdate=i18n.fdate, frange=i18n.frange, price=i18n.money,
    number=i18n.number, pct=i18n.pct, join_words=i18n.join, local_price=local_price, money_split=money_split,
    kinds=kinds, KINDS=kinds.KINDS, TAGS=kinds.TAGS,
    kind_name=lambda k: kinds.kind_name(k, i18n.current()), tag_name=lambda tg: kinds.tag_name(tg, i18n.current()))
templates.env.filters["money"] = money
templates.env.filters["usd"] = currency.usd
templates.env.filters["local"] = local
templates.env.filters["nice_date"] = nice_date
templates.env.filters["card_img"] = card_img
templates.env.globals["qs"] = qs
templates.env.globals["app_name"] = settings.app_name


def render(request: Request, name: str, status_code: int = 200, **context):
    # Templates render right here, so every t() in them (and in their macros) sees this page's language.
    context["lang"] = i18n.use(context.get("lang") or i18n.lang_of(request))
    return templates.TemplateResponse(request, name, context, status_code=status_code)

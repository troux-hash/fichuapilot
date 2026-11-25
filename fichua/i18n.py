"""English and French for the traveller pages (Brief 3 v3: both complete and written by people, not machines).

Templates write the English sentence and wrap it: {{ t("Kind of place") }}, or with values,
{{ t("Ask {name}", name=host.name) }}. French comes from FR below; a sentence missing there shows in English.
The language is the visitor's choice (the EN/FR switch sets a cookie), else ?lang=, else the browser's first
language. The partner portal and admin stay in English for now.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime

from .fr import FR

LANGS = ("en", "fr")
_current: ContextVar[str] = ContextVar("lang", default="en")

_MONTHS = {"en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
           "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]}
_MONTHS_LONG = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                       "October", "November", "December"],
                "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                       "octobre", "novembre", "décembre"]}
_DAYS = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
         "fr": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]}
_DAYS_LONG = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
              "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]}
NBSP = " "  # thin no-break space before French ; : ! ? and %


def lang_of(request) -> str:
    path = request.url.path
    if path.startswith(("/partners", "/admin")):
        return "en"
    asked = request.query_params.get("lang")
    if asked in LANGS:
        return asked
    saved = request.cookies.get("lang")
    if saved in LANGS:
        return saved
    first = (request.headers.get("accept-language") or "").split(",")[0].strip().lower()
    return "fr" if first.startswith("fr") else "en"


def use(lang: str) -> str:
    lang = lang if lang in LANGS else "en"
    _current.set(lang)
    return lang


def current() -> str:
    return _current.get()


def t(text: str, **values) -> str:
    out = FR.get(text, text) if current() == "fr" else text
    return out.format(**values) if values else out


def tn(n: int, one: str, many: str, **values) -> str:
    """'1 night' / '3 nights', translated: t(one or many) with n filled in."""
    return t(one if n == 1 else many, n=n, **values)


def pick(value: dict) -> str:
    """{'en': …, 'fr': …} in the current language."""
    return value.get(current()) or value.get("en", "")


def fdate(value, style: str = "week") -> str:
    """week 'Thu 17 Dec' · short '17 Dec' · long '17 Dec 2026' · weeklong 'Thu 17 Dec 2026' · full 'Thursday 17 December'."""
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = value.date()
    lang = current()
    day, month = value.day, _MONTHS[lang][value.month - 1]
    wk = _DAYS[lang][value.weekday()]
    if style == "short":
        return f"{day} {month}"
    if style == "long":
        return f"{day} {month} {value.year}"
    if style == "weeklong":
        return f"{wk} {day} {month} {value.year}"
    if style == "full":
        return f"{_DAYS_LONG[lang][value.weekday()]} {day} {_MONTHS_LONG[lang][value.month - 1]}"
    return f"{wk} {day} {month}"


def frange(start, end) -> str:
    """'17–20 Dec' in one month, '30 Dec – 2 Jan' across two (French: '17–20 déc.')."""
    if not start or not end:
        return ""
    if isinstance(start, str):
        start, end = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{fdate(end, 'short')}"
    return f"{fdate(start, 'short')} – {fdate(end, 'short')}"


def money(value, cents: bool | None = None) -> str:
    """'$1,280' or '$455.40'; in French '1 280 $' or '455,40 $'."""
    if value is None:
        return ""
    amount = float(value)
    whole = abs(amount - round(amount)) < 0.005
    digits = 0 if (whole if cents is None else not cents) else 2
    text = f"{amount:,.{digits}f}"
    if current() == "fr":
        return text.replace(",", " ").replace(".", ",") + " $"
    return "$" + text


def number(value) -> str:
    text = f"{int(round(float(value))):,}"
    return text.replace(",", " ") if current() == "fr" else text


def pct(value) -> str:
    value = float(value)
    text = f"{value:g}"
    return (text.replace(".", ",") + NBSP + "%") if current() == "fr" else text + "%"


def join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + (" et " if current() == "fr" else " and ") + items[-1]

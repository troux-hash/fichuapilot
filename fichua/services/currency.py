"""USD is Fichua's master currency. Guests and hotels also see their local equivalent.

Also the other facts Fichua needs per market: WhatsApp language, phone country code, time zone.
"""
from __future__ import annotations

import re

# Country (as stored on hotels) → ISO code, local currency, label, WhatsApp language, dialling code,
# and UTC offset in hours (none of the three changes clocks in summer).
COUNTRIES = {
    "Rwanda": {"iso": "RW", "currency": "RWF", "label": "RWF", "lang": "en", "dial": "250", "utc_offset": 2},
    "Benin": {"iso": "BJ", "currency": "XOF", "label": "FCFA", "lang": "fr", "dial": "229", "utc_offset": 1},
    "Côte d'Ivoire": {"iso": "CI", "currency": "XOF", "label": "FCFA", "lang": "fr", "dial": "225", "utc_offset": 0},
}
ALIASES = {"cote d'ivoire": "Côte d'Ivoire", "côte d’ivoire": "Côte d'Ivoire", "ivory coast": "Côte d'Ivoire",
           "bénin": "Benin", "rwanda": "Rwanda", "benin": "Benin", "côte d'ivoire": "Côte d'Ivoire"}
MARKETS = list(COUNTRIES)  # countries partners can register in


def normalize_country(name: str | None) -> str | None:
    if not name:
        return name
    return ALIASES.get(name.strip().lower(), name.strip())


def country_info(name: str | None) -> dict | None:
    return COUNTRIES.get(normalize_country(name) or "")


def language_for(country: str | None) -> str:
    info = country_info(country)
    return info["lang"] if info else "en"


def utc_offset(country: str | None) -> int:
    info = country_info(country)
    return info["utc_offset"] if info else 0


def international_phone(phone: str | None, country: str | None = None) -> str:
    """Digits with the country code, as WhatsApp needs ('250788000000'), from what a hotel typed.

    '+250 788 000 000' and '00250…' are already international. A local number gets its country's code:
    Rwanda drops the leading 0 ('0788…' → '250788…'); Benin and Côte d'Ivoire keep it, because their
    10-digit numbers start with 0 after the code ('01 97…' → '2290197…').
    """
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits or raw.startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    info = country_info(country)
    if not info:
        return digits
    dial = info["dial"]
    if digits.startswith(dial) and len(digits) >= len(dial) + 8:
        return digits
    if info["iso"] == "RW":
        return dial + digits.lstrip("0")
    return dial + digits


def usd(amount, decimals: bool = False) -> str:
    value = float(amount or 0)
    if decimals or value != int(value):
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def local_amount(amount, country: str | None, rates: dict[str, str]) -> tuple[float, str] | None:
    info = country_info(country)
    if not info:
        return None
    try:
        rate = float(rates.get(f"rate_{info['currency']}") or 0)
    except ValueError:
        return None
    if rate <= 0:
        return None
    return float(amount or 0) * rate, info["label"]


def local_text(amount, country: str | None, rates: dict[str, str]) -> str:
    """'≈ 116,000 RWF' / '≈ 45 200 FCFA' (French spacing for CFA), or '' if no local currency."""
    converted = local_amount(amount, country, rates)
    if not converted:
        return ""
    value, label = converted
    # Round to something a person would quote: nearest 100 (RWF/CFA have no cents).
    rounded = int(round(value / 100.0) * 100)
    if label == "FCFA":
        return "≈ " + f"{rounded:,}".replace(",", " ") + " FCFA"
    return f"≈ {rounded:,} {label}"

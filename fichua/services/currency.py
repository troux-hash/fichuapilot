"""USD is Fichua's master currency. Guests and hotels also see their local equivalent."""
from __future__ import annotations

# Country (as stored on hotels) → ISO code, local currency, label, WhatsApp language.
COUNTRIES = {
    "Rwanda": {"iso": "RW", "currency": "RWF", "label": "RWF", "lang": "en"},
    "Benin": {"iso": "BJ", "currency": "XOF", "label": "FCFA", "lang": "fr"},
    "Côte d'Ivoire": {"iso": "CI", "currency": "XOF", "label": "FCFA", "lang": "fr"},
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

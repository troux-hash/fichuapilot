"""The five kinds of place travellers choose from (Brief 3 v3), the "good for" tags, the five checks Fichua
makes before a place goes live, and the record of how a place runs.

A hotel's kind is what its owner picked and Fichua confirmed (hotels.category). Places listed before kinds
existed get one inferred from their type and name until someone sets it, so none drops out of search.
Ranking never uses price, fees or reply speed: kind first, then verification (see search.py).
"""
from __future__ import annotations

from datetime import date

from ..db import Connection

KINDS = [
    {"id": "urban",
     "short": {"en": "Small, calm hotels in the city", "fr": "Petits hôtels calmes en ville"},
     "name": {"en": "Urban oasis & city boutique", "fr": "Oasis urbaine et boutique-hôtel"},
     "line": {"en": "A small, design-led hotel in the city, calm and local.",
              "fr": "Un petit hôtel de caractère en ville, calme et ancré dans son quartier."},
     "reason": {"en": "The reason to stay is the city, in a place that feels local.",
                "fr": "On y vient pour la ville, dans un lieu qui a l’âme du quartier."},
     "plural": {"en": "city boutiques", "fr": "boutiques-hôtels en ville"}},
    {"id": "eco",
     "short": {"en": "Farms, gardens and green lodges", "fr": "Fermes, jardins et lodges verts"},
     "name": {"en": "Ecolodges & agro-tourism", "fr": "Écolodges et agrotourisme"},
     "line": {"en": "A stay on working land, run with care for people, place and money.",
              "fr": "Un séjour sur une terre cultivée, tenu avec soin pour les gens, le lieu et l’argent."},
     "reason": {"en": "The reason to stay is the land, the food and the way it is run.",
                "fr": "On y vient pour la terre, la table et la façon de faire."},
     "plural": {"en": "ecolodges and farm stays", "fr": "écolodges et séjours à la ferme"}},
    {"id": "heritage",
     "short": {"en": "Historic buildings with a story", "fr": "Des lieux chargés d’histoire"},
     "name": {"en": "History & heritage", "fr": "Histoire et patrimoine"},
     "line": {"en": "A small hotel in a historic building, where the owner tells its story.",
              "fr": "Un petit hôtel dans un bâtiment historique, dont le propriétaire raconte l’histoire."},
     "reason": {"en": "The reason to stay is the building and its story.",
                "fr": "On y vient pour le bâtiment et son histoire."},
     "plural": {"en": "heritage stays", "fr": "séjours patrimoine"}},
    {"id": "wild",
     "short": {"en": "Parks, forests and local communities", "fr": "Parcs, forêts et communautés locales"},
     "name": {"en": "Wild, nature & community", "fr": "Nature sauvage et communauté"},
     "line": {"en": "A lodge beside a park or forest, or run with the local community.",
              "fr": "Un lodge au bord d’un parc ou d’une forêt, ou tenu avec la communauté locale."},
     "reason": {"en": "The reason to stay is the wild place or the community.",
                "fr": "On y vient pour la nature ou pour la communauté."},
     "plural": {"en": "nature and community lodges", "fr": "lodges nature et communauté"}},
    {"id": "water",
     "short": {"en": "By the water, at a slow pace", "fr": "Au bord de l’eau, sans se presser"},
     "name": {"en": "Beach, lakes & lagoons", "fr": "Plages, lacs et lagunes"},
     "line": {"en": "A stay on a shore, where the water and a slow pace lead.",
              "fr": "Un séjour au bord de l’eau, au rythme lent."},
     "reason": {"en": "The reason to stay is the water.", "fr": "On y vient pour l’eau."},
     "plural": {"en": "stays by the water", "fr": "séjours au bord de l’eau"}},
]
KIND_IDS = [k["id"] for k in KINDS]
_KIND = {k["id"]: k for k in KINDS}

TAGS = [
    {"id": "family", "name": {"en": "Family & homecoming", "fr": "Famille et retour au pays"},
     "typical": ["heritage", "urban", "water"]},
    {"id": "work", "name": {"en": "Work & meetings", "fr": "Travail et réunions"}, "typical": ["urban", "water"]},
    {"id": "slow", "name": {"en": "Slow & long stays", "fr": "Longs séjours, rythme lent"},
     "typical": ["urban", "eco", "heritage"]},
    {"id": "rest", "name": {"en": "Rest & disconnect", "fr": "Repos et déconnexion"}, "typical": ["eco", "wild", "water"]},
    {"id": "culture", "name": {"en": "Culture, food & creativity", "fr": "Culture, cuisine et création"},
     "typical": ["urban", "eco", "heritage"]},
]
TAG_IDS = [t["id"] for t in TAGS]
_TAG = {t["id"]: t for t in TAGS}
MAX_TAGS = 3

CHECKS = [
    {"id": "identity", "name": {"en": "Owner’s identity", "fr": "Identité du propriétaire"}},
    {"id": "licence", "name": {"en": "Business licence", "fr": "Licence d’exploitation"}},
    {"id": "location", "name": {"en": "Location visited", "fr": "Lieu visité"}},
    {"id": "photos", "name": {"en": "Photos taken on site", "fr": "Photos prises sur place"}},
    {"id": "whatsapp", "name": {"en": "WhatsApp tested", "fr": "WhatsApp testé"}},
]
CHECK_IDS = [c["id"] for c in CHECKS]

PRACTICE = [  # "How this place runs": each line is evidence Fichua saw, with its date in the words
    {"id": "people", "field": "practice_people", "name": {"en": "People", "fr": "Les personnes"}},
    {"id": "place", "field": "practice_place", "name": {"en": "Place", "fr": "Le lieu"}},
    {"id": "money", "field": "practice_money", "name": {"en": "Money", "fr": "L’argent"}},
]

_WATER_WORDS = ("beach", "plage", "lagoon", "lagune", "lake", "lac ", "bungalow", "shore", "island")


def pick(value: dict, lang: str) -> str:
    return value.get(lang) or value["en"]


def kind(kind_id: str | None) -> dict | None:
    return _KIND.get(kind_id or "")


def kind_name(kind_id: str | None, lang: str = "en") -> str:
    k = kind(kind_id)
    return pick(k["name"], lang) if k else ""


def tag_name(tag_id: str, lang: str = "en") -> str:
    t = _TAG.get(tag_id)
    return pick(t["name"], lang) if t else tag_id


def typical_tags(kind_id: str) -> list[str]:
    return [t["id"] for t in TAGS if kind_id in t["typical"]]


def guess_kind(hotel: dict) -> str:
    """A kind for places listed before kinds existed, from their type and name (an owner or admin can change it)."""
    name = f" {(hotel.get('name') or '').lower()} "
    text = f"{name} {(hotel.get('description') or '').lower()}"
    ptype = (hotel.get("property_type") or "").lower()
    if "heritage" in text or "historic" in text:
        return "heritage"
    if " eco " in name or "eco lodge" in text or "ecolodge" in text or " farm" in name:
        return "eco"
    water = any(w in name for w in _WATER_WORDS)
    if ptype in ("lodge", "resort", "camp", "bungalow") or (water and ptype not in ("hotel", "apartment")):
        return "water" if water else "wild"
    if (hotel.get("city") or "").lower() in ("ouidah", "nyanza") and ptype in ("guesthouse", "boutique"):
        return "heritage"
    return "urban"


def guess_tags(hotel: dict) -> list[str]:
    ptype = (hotel.get("property_type") or "").lower()
    return {"apartment": ["family", "slow"], "hotel": ["work"], "boutique": ["culture", "work"],
            "guesthouse": ["family", "culture"], "lodge": ["rest", "family"], "resort": ["rest", "family"],
            }.get(ptype, ["rest"])


def clean_kind(value) -> str | None:
    value = (value or "").strip()
    return value if value in _KIND else None


def clean_tags(values) -> list[str]:
    out = []
    for v in values or []:
        if v in _TAG and v not in out:
            out.append(v)
    return out[:MAX_TAGS]


def apply(hotel: dict) -> dict:
    """Add kind, second kind, tags and the practice record to a hydrated hotel row."""
    hotel["kind"] = clean_kind(hotel.get("category")) or guess_kind(hotel)
    also = clean_kind(hotel.get("category_also"))
    hotel["kind_also"] = also if also != hotel["kind"] else None
    tags = clean_tags((hotel.get("good_for") or "").split(","))
    hotel["tags"] = tags or guess_tags(hotel)
    lines = {p["id"]: (hotel.get(p["field"]) or "").strip() for p in PRACTICE}
    hotel["practice"] = {**lines, "any": any(lines.values()), "badge": all(lines.values())}
    return hotel


def matches(hotel: dict, kinds: list[str]) -> int:
    """2 when the place's main kind was picked, 1 when its second kind was, 0 otherwise (or nothing picked)."""
    if not kinds:
        return 0
    if hotel["kind"] in kinds:
        return 2
    return 1 if hotel.get("kind_also") in kinds else 0


# ------------------------------------------------------------------ the five checks

def checks_by_hotel(conn: Connection, hotel_ids: list[str]) -> dict[str, dict[str, dict]]:
    if not hotel_ids:
        return {}
    marks, params = conn.in_params(hotel_ids, "c")
    rows = conn.all(f"SELECT hotel_id, check_id, done_on, note FROM hotel_checks WHERE hotel_id IN ({marks})", params)
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        done = r["done_on"]
        if isinstance(done, str):
            done = date.fromisoformat(done[:10])
        out.setdefault(r["hotel_id"], {})[r["check_id"]] = {"done_on": done, "note": r["note"] or ""}
    return out


def verification(hotel: dict, done: dict[str, dict] | None) -> dict:
    """What travellers see: each check with its date, how many of five are done, and the latest date."""
    done = done or {}
    items = [{"id": c["id"], "name": c["name"], "done_on": (done.get(c["id"]) or {}).get("done_on"),
              "note": (done.get(c["id"]) or {}).get("note", "")} for c in CHECKS]
    dates = [i["done_on"] for i in items if i["done_on"]]
    count = len(dates)
    approved = hotel.get("approved_at")
    if isinstance(approved, str) and approved:
        approved = date.fromisoformat(approved[:10])
    elif approved is not None and hasattr(approved, "date"):
        approved = approved.date()
    return {"items": items, "count": count, "full": count == len(CHECKS), "latest": max(dates) if dates else None,
            "reviewed_on": approved}


def save_checks(conn: Connection, hotel_id: str, form: dict) -> list[str]:
    """Record or clear each check from the admin form: check_<id> = a date, note_<id> = what was seen."""
    errors = []
    for c in CHECKS:
        raw = (form.get(f"check_{c['id']}") or "").strip()
        note = (form.get(f"note_{c['id']}") or "").strip()[:200]
        conn.run("DELETE FROM hotel_checks WHERE hotel_id = :h AND check_id = :c", {"h": hotel_id, "c": c["id"]})
        if not raw:
            continue
        try:
            done = date.fromisoformat(raw)
        except ValueError:
            errors.append(f"{c['name']['en']}: pick a valid date.")
            continue
        if done > date.today():
            errors.append(f"{c['name']['en']}: the date can't be in the future.")
            continue
        conn.run("INSERT INTO hotel_checks (hotel_id, check_id, done_on, note) VALUES (:h, :c, :d, :n)",
                 {"h": hotel_id, "c": c["id"], "d": done, "n": note})
    return errors


def depth(hotels: list[dict]) -> dict:
    """Live places by kind and country, for the admin's catalogue-depth table."""
    countries = sorted({h.get("country") or "" for h in hotels if h.get("country")})
    rows = []
    for k in KINDS:
        counts = {c: sum(1 for h in hotels if h["kind"] == k["id"] and h.get("country") == c) for c in countries}
        rows.append({"kind": k, "counts": counts, "total": sum(counts.values())})
    return {"countries": countries, "rows": rows}

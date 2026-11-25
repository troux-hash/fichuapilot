"""Search: availability → one best offer per hotel → filters → sort → facets.

Filtering and sorting are pure Python over a small result set, which keeps the SQL
portable and makes every rule trivially testable and easy to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..db import Connection
from . import catalog, enquiries, kinds, policies
from .dates import Stay

# No "Top rated" sort or rating filter: imported guest ratings are not shown or used (Brief 2 allows only
# reviews from verified Fichua stays). Properties cannot pay to rank higher.
SORTS = {
    "recommended": "Recommended",
    "price": "Lowest price",
    "stars": "Most stars",
}


@dataclass
class Filters:
    price_max: float | None = None          # per night
    stars: list[int] = field(default_factory=list)
    free_cancellation: bool = False
    breakfast: bool = False
    amenities: list[str] = field(default_factory=list)
    property_types: list[str] = field(default_factory=list)
    sort: str = "recommended"

    @classmethod
    def from_query(cls, q) -> "Filters":
        """Build from a Starlette QueryParams/MultiDict (or any .get/.getlist object)."""
        def num(name):
            try:
                return float(q.get(name)) if q.get(name) not in (None, "") else None
            except ValueError:
                return None

        sort = q.get("sort") or "recommended"
        return cls(
            price_max=num("price_max"),
            stars=[int(s) for s in q.getlist("stars") if s.isdigit()],
            free_cancellation=q.get("free_cancellation") == "1",
            breakfast=q.get("breakfast") == "1",
            amenities=[a for a in q.getlist("amenity") if a],
            property_types=[p for p in q.getlist("type") if p],
            sort=sort if sort in SORTS else "recommended",
        )

    @property
    def active_count(self) -> int:
        return sum([
            self.price_max is not None, bool(self.stars),
            self.free_cancellation, self.breakfast, bool(self.amenities), bool(self.property_types),
        ])


def _offers(conn: Connection, stay: Stay, destination: str | None) -> list[dict]:
    """Every bookable room for the stay, joined with its hotel and room details."""
    avail = catalog.availability(conn, stay, destination=destination)
    hotels = catalog.hotels_by_ids(conn, sorted({a["hotel_id"] for a in avail}))
    rooms = catalog.rooms_by_ids(conn, [a["room_type_id"] for a in avail])
    offers = []
    for a in avail:
        room, hotel = rooms[a["room_type_id"]], hotels[a["hotel_id"]]
        offers.append({
            "hotel": hotel,
            "room": room,
            "total_price": round(a["total_price"], 2),
            "per_night": round(a["total_price"] / stay.nights, 2),
            # Every night at the same price: "$165/night"; otherwise the card says it is an average.
            "even_nights": len(set(a.get("nightly") or [])) <= 1,
            "rooms_left": int(a["rooms_left"]),
            # The last day to cancel for free, or None (non-refundable, or too close to check-in).
            "free_until": policies.open_until(hotel.get("cancellation_policy"), room["free_cancellation"],
                                              stay.check_in),
        })
    return offers


def _best_per_hotel(offers: list[dict], f: Filters) -> list[dict]:
    best: dict[str, dict] = {}
    for o in offers:
        if f.free_cancellation and not o["free_until"]:
            continue
        if f.breakfast and not o["room"]["breakfast_included"]:
            continue
        hid = o["hotel"]["id"]
        if hid not in best or o["total_price"] < best[hid]["total_price"]:
            best[hid] = o
    return list(best.values())


def _matches(o: dict, f: Filters) -> bool:
    h = o["hotel"]
    if f.price_max is not None and o["per_night"] > f.price_max:
        return False
    if f.stars and (h.get("star_rating") or 0) not in f.stars:
        return False
    if f.property_types and h.get("property_type") not in f.property_types:
        return False
    have = {a.lower() for a in h["amenities"]}
    return all(a.lower() in have for a in f.amenities)


def _sort(results: list[dict], sort: str) -> list[dict]:
    if sort == "price":
        return sorted(results, key=lambda o: o["per_night"])
    if sort == "stars":
        return sorted(results, key=lambda o: (-(o["hotel"].get("star_rating") or 0), o["per_night"]))
    if not results:
        return results
    # Recommended: value for the class — stars up, price relative to the set down. Nothing paid,
    # and no imported guest ratings.
    prices = sorted(o["per_night"] for o in results)
    median = prices[len(prices) // 2] or 1

    def score(o):
        return 0.4 * (o["hotel"].get("star_rating") or 3) - 1.5 * (o["per_night"] / median)
    return sorted(results, key=score, reverse=True)


# ------------------------------------------------------------------ kind-first search (Brief 3 v3)

def in_where(hotel: dict, where: str | None) -> bool:
    """'all', 'country:Benin', 'city:Kigali', or typed text matched against city, country and name."""
    where = (where or "").strip()
    if not where or where == "all":
        return True
    if where.startswith("country:"):
        return (hotel.get("country") or "").lower() == where[8:].lower()
    if where.startswith("city:"):
        return (hotel.get("city") or "").lower() == where[5:].lower()
    text = where.lower()
    return any(text in (hotel.get(k) or "").lower() for k in ("city", "country", "name", "area"))


def where_options(conn: Connection, picked: list[str]) -> list[dict]:
    """Every country and city with a matching live place, with how many there are."""
    hotels = [h for h in catalog.live_hotels(conn) if not picked or kinds.matches(h, picked)]
    options = [{"value": "all", "country": None, "city": None, "count": len(hotels), "level": 0}]
    for country in sorted({h["country"] for h in hotels if h.get("country")}):
        in_country = [h for h in hotels if h.get("country") == country]
        options.append({"value": f"country:{country}", "country": country, "city": None,
                        "count": len(in_country), "level": 1})
        for city in sorted({h["city"] for h in in_country if h.get("city")}):
            options.append({"value": f"city:{city}", "country": country, "city": city,
                            "count": sum(1 for h in in_country if h.get("city") == city), "level": 2})
    return options


def _rank(item: dict, picked: list[str]) -> tuple:
    """Fit, then verification: never price, fees or reply speed (Brief 3 v3, and the 25 Nov 2026 decision)."""
    h, v = item["hotel"], item["verification"]
    return (-kinds.matches(h, picked), -int(v["full"]), -v["count"], h["name"].lower())


def discover(conn: Connection, picked: list[str], where: str | None, stay: Stay, dated: bool) -> dict:
    """Live places of the picked kinds in a place, priced for the stay (or 'from' a night without dates)."""
    hotels = [h for h in catalog.live_hotels(conn)
              if in_where(h, where) and (not picked or kinds.matches(h, picked))]
    ids = [h["id"] for h in hotels]
    checks = kinds.checks_by_hotel(conn, ids)
    offers: dict[str, dict] = {}
    if dated and ids:
        wanted = set(ids)
        for o in _offers(conn, stay, None):  # the cheapest room per place is the one shown, not used to rank
            hid = o["hotel"]["id"]
            if hid in wanted and (hid not in offers or o["total_price"] < offers[hid]["total_price"]):
                offers[hid] = o
    from_prices = catalog.from_prices(conn, ids, stay.guests, stay.rooms)
    items, full = [], 0
    for h in hotels:
        if h["id"] not in from_prices:  # no room sleeps the party
            continue
        offer = offers.get(h["id"])
        if dated and not offer:
            full += 1
            continue
        items.append({"hotel": h, "offer": offer, "from": from_prices[h["id"]],
                      "can_ask": bool(enquiries.hotel_number(h)),
                      "verification": kinds.verification(h, checks.get(h["id"]))})
    items.sort(key=lambda i: _rank(i, picked))
    if len(picked) == 2:
        groups = [{"kind": k, "places": [i for i in items if i["hotel"]["kind"] == k
                                         or (i["hotel"]["kind"] not in picked and i["hotel"].get("kind_also") == k)]}
                  for k in picked]
        groups = [g for g in groups if g["places"]]
    else:
        groups = [{"kind": None, "places": items}] if items else []
    return {"groups": groups, "count": len(items), "full": full}


def largest_room(conn: Connection, picked: list[str], where: str | None) -> int:
    """How many guests the biggest room sleeps among matching places (0 if none): explains an empty search
    for a big group, and offers the same search with enough rooms (FIX-15, IMP-18)."""
    ids = [h["id"] for h in catalog.live_hotels(conn)
           if in_where(h, where) and (not picked or kinds.matches(h, picked))]
    if not ids:
        return 0
    marks, params = conn.in_params(ids, "l")
    return int(conn.scalar(f"SELECT MAX(max_guests) FROM room_types WHERE hotel_id IN ({marks})", params) or 0)


def search(conn: Connection, stay: Stay, destination: str | None, f: Filters) -> dict:
    offers = _offers(conn, stay, destination)
    unfiltered = _best_per_hotel(offers, Filters())
    candidates = _best_per_hotel(offers, f)
    results = _sort([o for o in candidates if _matches(o, f)], f.sort)

    amenity_counts: dict[str, int] = {}
    for o in unfiltered:
        for a in o["hotel"]["amenities"]:
            amenity_counts[a] = amenity_counts.get(a, 0) + 1
    facets = {
        # Rounded up to the slider's step (5) so an untouched slider sits exactly at max.
        "price_ceiling": (int(max((o["per_night"] for o in unfiltered), default=0)) // 5 + 1) * 5,
        "amenities": sorted(amenity_counts, key=lambda a: -amenity_counts[a])[:8],
        "property_types": sorted({o["hotel"]["property_type"] for o in unfiltered
                                  if o["hotel"].get("property_type")}),
        "total": len(unfiltered),
    }
    return {"results": results, "facets": facets}

"""Hotels, rooms and live availability — the read side of the catalogue.

Price and inventory for a room type on a night, in order of precedence:
  1. rate_overrides  — what the partner set in the calendar (price, rooms to sell, closed)
  2. room_rates      — nightly rows from an Excel upload
  3. room_types      — the standing rule: base price (weekend price on Fri/Sat) and total rooms
Rooms left = rooms to sell − confirmed bookings − unpaid checkouts still inside their hold.
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlencode

from ..db import Connection, utcnow
from . import policies
from .dates import Stay

PLACEHOLDER_IMAGE = "/static/img/placeholder.svg"
WEEKEND = (4, 5)  # Friday and Saturday nights


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def media_urls(conn: Connection, owner_type: str, ids: list[str]) -> dict[str, list[str]]:
    if not ids:
        return {}
    marks, params = conn.in_params(ids)
    rows = conn.all(f"SELECT id, owner_id FROM media WHERE owner_type = :t AND owner_id IN ({marks}) "
                    "ORDER BY sort, created_at", {"t": owner_type, **params})
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["owner_id"], []).append(f"/media/{r['id']}")
    return out


def full_address(hotel: dict) -> str:
    """'KG 7 Ave, Kimihurura, Kigali, Rwanda': the street address, plus the area, city and country
    when it doesn't already say them."""
    parts = [p for p in [(hotel.get("address") or "").strip()] if p]
    for extra in (hotel.get("area"), hotel.get("city"), hotel.get("country")):
        extra = (extra or "").strip()
        if extra and extra.lower() not in ", ".join(parts).lower():
            parts.append(extra)
    return ", ".join(parts)


def map_links(hotel: dict) -> dict:
    """A Google Maps link (it opens the Maps app on phones) and, when the hotel dropped a pin, a small
    OpenStreetMap embed centred on it."""
    lat, lng = hotel.get("lat"), hotel.get("lng")
    if lat is not None and lng is not None:
        lat, lng = float(lat), float(lng)
        query = f"{lat:.6f},{lng:.6f}"
        box = f"{lng - 0.006:.6f},{lat - 0.004:.6f},{lng + 0.006:.6f},{lat + 0.004:.6f}"
        embed = "https://www.openstreetmap.org/export/embed.html?" + urlencode(
            {"bbox": box, "layer": "mapnik", "marker": query})
    else:
        query, embed = full_address(hotel), None
    url = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query}) if query else None
    return {"map_url": url, "map_embed": embed}


def hydrate_hotel(row: dict, photos: list[str] | None = None) -> dict:
    row = dict(row)
    row["amenities"] = split_list(row.get("amenities"))
    row["images"] = (photos or []) + split_list(row.get("image_urls")) or [PLACEHOLDER_IMAGE]
    row["full_address"] = full_address(row)
    row.update(map_links(row))
    return row


def hydrate_room(row: dict, photos: list[str] | None = None) -> dict:
    row = dict(row)
    row["amenities"] = split_list(row.get("amenities"))
    row["images"] = (photos or []) + split_list(row.get("image_urls")) or [PLACEHOLDER_IMAGE]
    return row


# What the public JSON API may show. Everything else on a hotel or room row (owner, commission, contact
# details, review notes, plan, stock) is internal: add a field here only if a guest may see it.
PUBLIC_HOTEL_FIELDS = ("id", "name", "property_type", "star_rating", "guest_rating", "review_count", "city", "area",
                       "country", "address", "lat", "lng", "description", "amenities", "images", "currency",
                       "check_in_time", "check_out_time", "cancellation_policy", "children_allowed",
                       "pets_allowed", "smoking_allowed")
PUBLIC_ROOM_FIELDS = ("id", "hotel_id", "name", "room_kind", "max_guests", "bed_type", "size_sqm", "description",
                      "amenities", "images", "breakfast_included", "free_cancellation")


def public_hotel(hotel: dict) -> dict:
    return {k: hotel.get(k) for k in PUBLIC_HOTEL_FIELDS}


def public_room(room: dict) -> dict:
    return {k: room.get(k) for k in PUBLIC_ROOM_FIELDS}


def night_grid(conn: Connection, rooms: list[dict], start: date, end: date,
               exclude_booking_id: str | None = None) -> dict[tuple[str, str], dict]:
    """Price, rooms to sell, closed flag and rooms booked for every room × night in [start, end)."""
    if not rooms or end <= start:
        return {}
    marks, params = conn.in_params([r["id"] for r in rooms], "rt")
    params.update({"s": start, "e": end})
    nightly = {(r["room_type_id"], r["stay_date"]): r for r in conn.all(
        f"SELECT room_type_id, stay_date, price, units FROM room_rates WHERE room_type_id IN ({marks}) "
        "AND stay_date >= :s AND stay_date < :e", params)}
    overrides = {(r["room_type_id"], r["stay_date"]): r for r in conn.all(
        f"SELECT room_type_id, stay_date, price, units, closed FROM rate_overrides "
        f"WHERE room_type_id IN ({marks}) AND stay_date >= :s AND stay_date < :e", params)}
    exclude = " AND b.id <> :exclude" if exclude_booking_id else ""
    booked = {(r["room_type_id"], r["stay_date"]): int(r["n"]) for r in conn.all(
        "SELECT bn.room_type_id, bn.stay_date, SUM(COALESCE(bn.units, 1)) AS n FROM booking_nights bn "
        "JOIN bookings b ON b.id = bn.booking_id "
        f"WHERE bn.room_type_id IN ({marks}) AND bn.stay_date >= :s AND bn.stay_date < :e "
        "AND (b.status = 'confirmed' OR (b.status = 'pending' AND b.hold_expires_at > :now))"
        f"{exclude} GROUP BY bn.room_type_id, bn.stay_date",
        {**params, "now": utcnow(), "exclude": exclude_booking_id})}

    grid: dict[tuple[str, str], dict] = {}
    days = (end - start).days
    for room in rooms:
        for i in range(days):
            d = start + timedelta(days=i)
            key = (room["id"], d.isoformat())
            o, n = overrides.get(key), nightly.get(key)
            weekend = d.weekday() in WEEKEND
            rule_price = room.get("weekend_price") if weekend and room.get("weekend_price") else room.get("base_price")
            price = (o["price"] if o and o.get("price") is not None
                     else n["price"] if n else rule_price)
            units = (o["units"] if o and o.get("units") is not None
                     else n["units"] if n else room.get("total_rooms"))
            grid[key] = {
                "date": d,
                "price": float(price) if price is not None else None,
                "rule_price": float(rule_price) if rule_price is not None else None,
                "units": int(units) if units is not None else None,
                "closed": bool(o and o.get("closed")),
                "booked": booked.get(key, 0),
                "changed": bool(o),
                "weekend": weekend,
            }
    return grid


def availability(conn: Connection, stay: Stay, *, destination: str | None = None,
                 hotel_id: str | None = None, room_type_id: str | None = None,
                 include_inactive: bool = False, exclude_booking_id: str | None = None) -> list[dict]:
    """Room types that fit the party in the stay's rooms and have that many rooms free every night.

    The price is for all the rooms; "nightly" lists one room's price for each night.
    """
    params: dict = {"guests": stay.guests, "rooms": stay.rooms}
    where = ["rt.max_guests * :rooms >= :guests"]
    if not include_inactive:
        where.append("h.is_active = TRUE")
    if destination:
        where.append("(LOWER(h.city) LIKE :q OR LOWER(h.country) LIKE :q OR LOWER(h.name) LIKE :q)")
        params["q"] = f"%{destination.strip().lower()}%"
    if hotel_id:
        where.append("h.id = :hotel_id")
        params["hotel_id"] = hotel_id
    if room_type_id:
        where.append("rt.id = :room_type_id")
        params["room_type_id"] = room_type_id
    rooms = conn.all("SELECT rt.id, rt.hotel_id, rt.total_rooms, rt.base_price, rt.weekend_price "
                     "FROM room_types rt JOIN hotels h ON h.id = rt.hotel_id WHERE " + " AND ".join(where), params)
    grid = night_grid(conn, rooms, stay.check_in, stay.check_out, exclude_booking_id)
    out = []
    for room in rooms:
        total, left, nightly = 0.0, None, []
        for i in range(stay.nights):
            night = grid[(room["id"], (stay.check_in + timedelta(days=i)).isoformat())]
            if night["closed"] or night["price"] is None or night["units"] is None:
                break
            free = night["units"] - night["booked"]
            if free < stay.rooms:
                break
            total += night["price"] * stay.rooms
            nightly.append(night["price"])
            left = free if left is None else min(left, free)
        else:
            out.append({"room_type_id": room["id"], "hotel_id": room["hotel_id"],
                        "total_price": round(total, 2), "rooms_left": left, "nightly": nightly,
                        "rooms": stay.rooms})
    return out


def largest_room(conn: Connection, destination: str | None = None) -> int:
    """How many guests the biggest live room sleeps, in a destination or anywhere (0 if none)."""
    params: dict = {}
    where = ["h.is_active = TRUE"]
    if destination:
        where.append("(LOWER(h.city) LIKE :q OR LOWER(h.country) LIKE :q OR LOWER(h.name) LIKE :q)")
        params["q"] = f"%{destination.strip().lower()}%"
    return int(conn.scalar("SELECT MAX(rt.max_guests) FROM room_types rt JOIN hotels h ON h.id = rt.hotel_id "
                           "WHERE " + " AND ".join(where), params) or 0)


def hotels_by_ids(conn: Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    marks, params = conn.in_params(ids, "h")
    rows = conn.all(f"SELECT * FROM hotels WHERE id IN ({marks})", params)
    photos = media_urls(conn, "hotel", [r["id"] for r in rows])
    return {r["id"]: hydrate_hotel(r, photos.get(r["id"])) for r in rows}


def rooms_by_ids(conn: Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    marks, params = conn.in_params(ids, "r")
    rows = conn.all(f"SELECT * FROM room_types WHERE id IN ({marks})", params)
    photos = media_urls(conn, "room", [r["id"] for r in rows])
    return {r["id"]: hydrate_room(r, photos.get(r["id"])) for r in rows}


def get_hotel(conn: Connection, hotel_id: str, include_inactive: bool = False) -> dict | None:
    sql = "SELECT * FROM hotels WHERE id = :id" + ("" if include_inactive else " AND is_active = TRUE")
    row = conn.one(sql, {"id": hotel_id})
    if not row:
        return None
    return hydrate_hotel(row, media_urls(conn, "hotel", [hotel_id]).get(hotel_id))


def hotel_rooms(conn: Connection, hotel_id: str, stay: Stay) -> list[dict]:
    """All room types for a hotel, priced and flagged available/unavailable for the stay."""
    rows = conn.all("SELECT * FROM room_types WHERE hotel_id = :id ORDER BY max_guests, name", {"id": hotel_id})
    photos = media_urls(conn, "room", [r["id"] for r in rows])
    live = {a["room_type_id"]: a for a in availability(conn, stay, hotel_id=hotel_id)}
    policy = conn.scalar("SELECT cancellation_policy FROM hotels WHERE id = :id", {"id": hotel_id})
    rooms = []
    for row in rows:
        room = hydrate_room(row, photos.get(row["id"]))
        a = live.get(room["id"])
        room["available"] = a is not None
        room["fits_party"] = room["max_guests"] * stay.rooms >= stay.guests
        room["rooms_needed"] = -(-stay.guests // max(1, room["max_guests"]))  # to sleep everyone in this type
        room["free_until"] = policies.open_until(policy, room["free_cancellation"], stay.check_in)
        if a:
            room["total_price"] = round(a["total_price"], 2)
            room["per_night"] = round(a["total_price"] / stay.nights, 2)
            room["rooms_left"] = int(a["rooms_left"])
        rooms.append(room)
    rooms.sort(key=lambda r: (not r["available"], r.get("total_price") or 0))
    return rooms


def destinations(conn: Connection) -> list[dict]:
    """Cities with live hotels, most hotels first, each with a cover image."""
    rows = conn.all("SELECT id, city, country, image_urls FROM hotels WHERE is_active = TRUE "
                    "ORDER BY guest_rating DESC")
    photos = media_urls(conn, "hotel", [r["id"] for r in rows])
    cities: dict[tuple, dict] = {}
    used: set[str] = set()
    for r in rows:
        key = (r["city"], r["country"])
        city = cities.setdefault(key, {"city": r["city"], "country": r["country"], "hotels": 0, "image": None})
        city["hotels"] += 1
        if city["image"] is None:
            fresh = [i for i in photos.get(r["id"], []) + split_list(r["image_urls"]) if i not in used]
            if fresh:
                city["image"] = fresh[0]
                used.add(fresh[0])
    for c in cities.values():
        c["image"] = c["image"] or PLACEHOLDER_IMAGE
    return sorted(cities.values(), key=lambda c: (-c["hotels"], c["city"]))

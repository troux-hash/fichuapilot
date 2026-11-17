"""Hotels, rooms and live availability — the read side of the catalogue."""
from __future__ import annotations

from ..db import Connection
from .dates import Stay

PLACEHOLDER_IMAGE = "/static/img/placeholder.svg"

AVAILABILITY_SQL = """
SELECT rt.id AS room_type_id,
       rt.hotel_id AS hotel_id,
       SUM(r.price) AS total_price,
       MIN(r.units - COALESCE(b.booked, 0)) AS rooms_left
FROM room_types rt
JOIN hotels h ON h.id = rt.hotel_id
JOIN room_rates r ON r.room_type_id = rt.id
LEFT JOIN (
    SELECT bn.room_type_id, bn.stay_date, COUNT(*) AS booked
    FROM booking_nights bn
    JOIN bookings bk ON bk.id = bn.booking_id
    WHERE bk.status = 'confirmed'
      AND bn.stay_date >= :check_in AND bn.stay_date < :check_out
    GROUP BY bn.room_type_id, bn.stay_date
) b ON b.room_type_id = r.room_type_id AND b.stay_date = r.stay_date
WHERE h.is_active = TRUE
  AND rt.max_guests >= :guests
  AND r.stay_date >= :check_in AND r.stay_date < :check_out
  {scope}
GROUP BY rt.id, rt.hotel_id
HAVING COUNT(*) = :nights AND MIN(r.units - COALESCE(b.booked, 0)) > 0
"""


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def hydrate_hotel(row: dict) -> dict:
    row = dict(row)
    row["amenities"] = split_list(row.get("amenities"))
    row["images"] = split_list(row.get("image_urls")) or [PLACEHOLDER_IMAGE]
    return row


def hydrate_room(row: dict) -> dict:
    row = dict(row)
    row["amenities"] = split_list(row.get("amenities"))
    row["images"] = split_list(row.get("image_urls")) or [PLACEHOLDER_IMAGE]
    return row


def availability(conn: Connection, stay: Stay, *, destination: str | None = None,
                 hotel_id: str | None = None, room_type_id: str | None = None) -> list[dict]:
    """Room types that fit the party and have inventory every night of the stay."""
    params = {
        "check_in": stay.check_in,
        "check_out": stay.check_out,
        "guests": stay.guests,
        "nights": stay.nights,
    }
    scope = ""
    if destination:
        scope = ("AND (LOWER(h.city) LIKE :q OR LOWER(h.country) LIKE :q "
                 "OR LOWER(h.name) LIKE :q)")
        params["q"] = f"%{destination.strip().lower()}%"
    if hotel_id:
        scope += " AND h.id = :hotel_id"
        params["hotel_id"] = hotel_id
    if room_type_id:
        scope += " AND rt.id = :room_type_id"
        params["room_type_id"] = room_type_id
    return conn.all(AVAILABILITY_SQL.format(scope=scope), params)


def hotels_by_ids(conn: Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    keys = {f"h{i}": v for i, v in enumerate(ids)}
    placeholders = ", ".join(f":{k}" for k in keys)
    rows = conn.all(f"SELECT * FROM hotels WHERE id IN ({placeholders})", keys)
    return {r["id"]: hydrate_hotel(r) for r in rows}


def rooms_by_ids(conn: Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    keys = {f"r{i}": v for i, v in enumerate(ids)}
    placeholders = ", ".join(f":{k}" for k in keys)
    rows = conn.all(f"SELECT * FROM room_types WHERE id IN ({placeholders})", keys)
    return {r["id"]: hydrate_room(r) for r in rows}


def get_hotel(conn: Connection, hotel_id: str) -> dict | None:
    row = conn.one("SELECT * FROM hotels WHERE id = :id AND is_active = TRUE", {"id": hotel_id})
    return hydrate_hotel(row) if row else None


def hotel_rooms(conn: Connection, hotel_id: str, stay: Stay) -> list[dict]:
    """All room types for a hotel, priced and flagged available/unavailable for the stay."""
    rows = conn.all("SELECT * FROM room_types WHERE hotel_id = :id ORDER BY max_guests, name",
                    {"id": hotel_id})
    live = {a["room_type_id"]: a for a in availability(conn, stay, hotel_id=hotel_id)}
    rooms = []
    for row in rows:
        room = hydrate_room(row)
        a = live.get(room["id"])
        room["available"] = a is not None
        room["fits_party"] = room["max_guests"] >= stay.guests
        if a:
            room["total_price"] = round(a["total_price"], 2)
            room["per_night"] = round(a["total_price"] / stay.nights, 2)
            room["rooms_left"] = int(a["rooms_left"])
        rooms.append(room)
    rooms.sort(key=lambda r: (not r["available"], r.get("total_price") or 0))
    return rooms


def destinations(conn: Connection) -> list[dict]:
    """Cities with active hotels, most hotels first, with a cover image."""
    rows = conn.all("SELECT city, country, image_urls FROM hotels WHERE is_active = TRUE "
                    "ORDER BY guest_rating DESC")
    cities: dict[tuple, dict] = {}
    used: set[str] = set()
    for r in rows:
        key = (r["city"], r["country"])
        city = cities.setdefault(key, {"city": r["city"], "country": r["country"], "hotels": 0, "image": None})
        city["hotels"] += 1
        if city["image"] is None:  # best-rated hotel's first photo not already used by another city
            images = split_list(r["image_urls"])
            fresh = [i for i in images if i not in used]
            if fresh:
                city["image"] = fresh[0]
                used.add(fresh[0])
    for c in cities.values():
        c["image"] = c["image"] or PLACEHOLDER_IMAGE
    return sorted(cities.values(), key=lambda c: (-c["hotels"], c["city"]))

"""What search engines, AI assistants and link previews read (Brief 2 §10).

Facts only: no ratings (Fichua shows only reviews from verified stays, and none exist yet) and no offer
markup, since a bookable price depends on the dates someone picks.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from ..db import Connection
from . import catalog, currency

LODGING_TYPES = {"Hotel": "Hotel", "Boutique": "Hotel", "Resort": "Resort"}  # everything else: LodgingBusiness
PUBLIC_PAGES = ["/", "/partners", "/terms", "/privacy", "/partners/terms"]
PRIVATE_PATHS = ["/admin", "/partners/", "/book", "/pay/", "/bookings/", "/manage", "/api/"]


def absolute(url: str | None, base: str) -> str | None:
    if not url:
        return None
    return url if url.startswith(("http://", "https://")) else base.rstrip("/") + "/" + url.lstrip("/")


def summary(hotel: dict) -> str:
    """One quotable sentence: what the place is and where, in the words a search result or assistant shows."""
    kind = (hotel.get("property_type") or "hotel").lower()
    stars = f"{hotel['star_rating']}-star " if hotel.get("star_rating") else ""
    where = ", ".join(p for p in (hotel.get("city"), hotel.get("country")) if p)
    return f"{hotel['name']} is a {stars}{kind} in {where}, reviewed by the Fichua team. Book at one all-in price."


def lodging(hotel: dict, rooms: list[dict], url: str, base: str) -> dict:
    """schema.org data for a hotel page."""
    prices = sorted(r["base_price"] for r in rooms if r.get("base_price"))
    data = {
        "@context": "https://schema.org",
        "@type": LODGING_TYPES.get(hotel.get("property_type") or "Hotel", "LodgingBusiness"),
        "name": hotel["name"],
        "url": url,
        "description": hotel.get("description") or None,
        "image": [absolute(i, base) for i in (hotel.get("images") or [])[:5]] or None,
        "address": {"@type": "PostalAddress", "streetAddress": hotel.get("address") or None,
                    "addressLocality": hotel.get("city"), "addressCountry": hotel.get("country")},
        "checkinTime": hotel.get("check_in_time") or None,
        "checkoutTime": hotel.get("check_out_time") or None,
        "petsAllowed": bool(hotel.get("pets_allowed")),
        "smokingAllowed": bool(hotel.get("smoking_allowed")),
        "amenityFeature": [{"@type": "LocationFeatureSpecification", "name": a, "value": True}
                           for a in hotel.get("amenities") or []] or None,
    }
    if hotel.get("lat") is not None and hotel.get("lng") is not None:
        data["geo"] = {"@type": "GeoCoordinates", "latitude": hotel["lat"], "longitude": hotel["lng"]}
    if hotel.get("star_rating"):
        data["starRating"] = {"@type": "Rating", "ratingValue": hotel["star_rating"]}
    if prices:
        low, high = currency.usd(prices[0]), currency.usd(prices[-1])
        data["priceRange"] = f"{low}–{high} a night" if low != high else f"{low} a night"
    return {k: v for k, v in data.items() if v is not None}


def sitemap(conn: Connection, base: str) -> str:
    rows = conn.all("SELECT id, name, city, country, updated_at FROM hotels WHERE is_active = TRUE ORDER BY id")
    urls = [(base + path, None) for path in PUBLIC_PAGES]
    urls += [(base + catalog.hotel_path(r), str(r.get("updated_at") or "")[:10] or None) for r in rows]
    items = []
    for loc, modified in urls:
        lastmod = f"<lastmod>{modified}</lastmod>" if modified else ""
        items.append(f"<url><loc>{escape(loc)}</loc>{lastmod}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(items) + "</urlset>\n")


def robots(base: str) -> str:
    """Crawlers and assistants welcome on public pages; bookings, payments and the portals stay out."""
    lines = ["User-agent: *", "Allow: /"] + [f"Disallow: {p}" for p in PRIVATE_PATHS]
    return "\n".join(lines + [f"Sitemap: {base}/sitemap.xml", ""])

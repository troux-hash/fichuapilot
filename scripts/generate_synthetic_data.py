"""Generate realistic synthetic hotel data as upload-ready Excel files.

    python scripts/generate_synthetic_data.py            # rates for the next 120 days
    python scripts/generate_synthetic_data.py --days 180

Writes one workbook per hotel group plus an all-in-one file to data/samples/.
Deterministic (seeded) so the same command gives the same hotels — only dates move.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fichua.services.importer import SHEETS, template_workbook  # noqa: E402

U = "https://images.unsplash.com/photo-{}?auto=format&fit=crop&w=1200&q=70"
HOTEL_PHOTOS = [
    "1566073771259-6a8506099945", "1551882547-ff40c63fe5fa", "1542314831-068cd1dbfeeb",
    "1520250497591-112f2f40a3f4", "1564501049412-61c2a3083791", "1571896349842-33c89424de2d",
    "1596394516093-501ba68a0ba6", "1445019980597-93fa8acb246c", "1455587734955-081b22074882",
    "1540541338287-41700207dee6", "1563911302283-d2bc129e7570", "1549294413-26f195200c16",
    "1625244724120-1fd1d34d00f6", "1615460549969-36fa19521a4f", "1522708323590-d24dbb6b0267",
]
ROOM_PHOTOS = [
    "1582719478250-c89cae4dc85b", "1611892440504-42a792e24d32", "1590490360182-c33d57733427",
    "1631049307264-da0ec9d70304", "1618773928121-c32242e63f39", "1595576508898-0ad5c879a061",
    "1566665797739-1674de7a421a", "1578683010236-d716f9a3f461", "1584132967334-10e028bd69f7",
]

GROUPS = {
    "Savanna Hotels Group": {
        "Nairobi": ("Kenya", "NBO", -1.2864, 36.8172, [
            ("The Acacia House", "Boutique", 5, 120), ("Karura Forest Lodge", "Lodge", 4, 95),
            ("Westlands Skyline Hotel", "Hotel", 4, 110), ("Kilimani Garden Suites", "Apartment", 3, 70)]),
        "Mombasa": ("Kenya", "MBA", -4.0435, 39.6682, [
            ("Nyali Reef Resort", "Resort", 5, 180), ("Old Town Coral Inn", "Boutique", 3, 65),
            ("Bamburi Palm Beach Hotel", "Resort", 4, 130), ("Tudor Creek Residences", "Apartment", 3, 60)]),
    },
    "Coastline Collection": {
        "Zanzibar": ("Tanzania", "ZNZ", -6.1659, 39.2026, [
            ("Stone Town Spice House", "Boutique", 4, 115), ("Nungwi Sunset Villas", "Resort", 5, 240),
            ("Paje Kite Beach Lodge", "Lodge", 3, 80), ("Kendwa Turquoise Resort", "Resort", 4, 160)]),
        "Cape Town": ("South Africa", "CPT", -33.9249, 18.4241, [
            ("Table Mountain View Hotel", "Hotel", 4, 140), ("Camps Bay Ocean Suites", "Hotel", 5, 260),
            ("Bo-Kaap Colour House", "Boutique", 3, 85), ("V&A Harbour Hotel", "Hotel", 4, 170)]),
    },
    "Meridian Urban Stays": {
        "Lisbon": ("Portugal", "LIS", 38.7223, -9.1393, [
            ("Alfama Azulejo Hotel", "Boutique", 4, 135), ("Chiado Grand", "Hotel", 5, 220),
            ("Belém Riverside Inn", "Hotel", 3, 90), ("Príncipe Real Apartments", "Apartment", 4, 120)]),
        "Dubai": ("United Arab Emirates", "DXB", 25.2048, 55.2708, [
            ("Marina Skyline Tower", "Hotel", 5, 250), ("Old Dubai Creek Hotel", "Boutique", 4, 120),
            ("Palm Jumeirah Beach Resort", "Resort", 5, 340), ("Downtown Urban Stay", "Hotel", 3, 95)]),
    },
}

AMENITIES = ["Free WiFi", "Pool", "Spa", "Gym", "Restaurant", "Bar", "Airport shuttle", "Free parking",
             "Air conditioning", "Beachfront", "Rooftop terrace", "Family rooms", "24h front desk",
             "Pet friendly", "Kitchen", "Ocean view"]
ROOM_AMENITIES = ["Air conditioning", "Smart TV", "Rain shower", "Minibar", "Balcony", "Desk",
                  "Coffee machine", "Bathtub", "Sea view", "Kitchenette", "Safe", "Blackout curtains"]
ROOMS = [  # name, max guests, bed, size, price factor
    ("Standard Double Room", 2, "1 Double bed", 22, 1.0),
    ("Deluxe King Room", 2, "1 King bed", 30, 1.35),
    ("Family Suite", 4, "1 King + 2 Single beds", 48, 1.9),
]
DESCRIPTIONS = {
    "Boutique": "An intimate, design-led {type} in the heart of {city}, with handcrafted interiors and a team that knows every hidden gem nearby.",
    "Lodge": "A calm, nature-wrapped lodge in {city} — wake up to birdsong, unwind by the fire, and explore at your own pace.",
    "Hotel": "A polished city hotel in {city} with generous rooms, fast WiFi and everything you need for business or a long weekend.",
    "Resort": "A sun-soaked resort on the edge of {city} with pools, spa treatments and long, lazy days built in.",
    "Apartment": "Spacious serviced apartments in {city} with full kitchens — perfect for families and longer stays.",
}


def build(days: int, seed: int = 7) -> dict[str, dict[str, list[list]]]:
    rng = random.Random(seed)
    start = date.today()
    out: dict[str, dict[str, list[list]]] = {}
    photo_i = 0
    for group, cities in GROUPS.items():
        sheets = {"Hotels": [], "Rooms": [], "Rates": []}
        for city, (country, code, lat, lng, hotels) in cities.items():
            for n, (name, ptype, stars, base) in enumerate(hotels, start=1):
                hcode = f"{code}-{n:03d}"
                photos = [U.format(HOTEL_PHOTOS[(photo_i + k) % len(HOTEL_PHOTOS)]) for k in range(5)]
                photo_i += 2
                amen = rng.sample(AMENITIES, rng.randint(6, 9))
                if ptype == "Resort" and "Pool" not in amen:
                    amen.insert(0, "Pool")
                if "Free WiFi" not in amen:
                    amen.insert(0, "Free WiFi")
                sheets["Hotels"].append([
                    hcode, group, name, city, country, f"{rng.randint(1, 240)} {name.split()[0]} Road, {city}",
                    round(lat + rng.uniform(-0.04, 0.04), 5), round(lng + rng.uniform(-0.04, 0.04), 5),
                    stars, round(min(9.8, rng.uniform(7.2, 8.4) + (stars - 3) * 0.35), 1),
                    rng.randint(80, 2400), ptype, DESCRIPTIONS[ptype].format(type=ptype.lower(), city=city),
                    ", ".join(amen), ", ".join(photos), "USD", "14:00", "11:00", "yes",
                ])
                for rname, guests, bed, size, factor in ROOMS:
                    rcode = f"{hcode}-{rname.split()[0][:3].upper()}"
                    rphotos = [U.format(ROOM_PHOTOS[rng.randrange(len(ROOM_PHOTOS))]) for _ in range(2)]
                    sheets["Rooms"].append([
                        rcode, hcode, rname, guests, bed, size + rng.randint(-2, 6),
                        f"{rname} with {bed.lower()} and {size}m² of calm.",
                        ", ".join(rng.sample(ROOM_AMENITIES, 4)), ", ".join(rphotos),
                        "yes" if rng.random() < 0.4 else "no",
                        "no" if rng.random() < 0.2 else "yes",
                    ])
                    weekday_price = round(base * factor * rng.uniform(0.92, 1.08))
                    # Weekly rows: Mon-Thu and Fri-Sun prices, with occasional sold-out nights.
                    d = start - timedelta(days=start.weekday())
                    while d < start + timedelta(days=days):
                        season = 1 + 0.12 * ((d - start).days // 30 % 2)
                        units = rng.choice([0, 1, 2, 3, 4, 5, 6, 8]) if rng.random() < 0.08 else rng.randint(2, 8)
                        sheets["Rates"].append([rcode, max(d, start), d + timedelta(days=3),
                                                round(weekday_price * season), units])
                        sheets["Rates"].append([rcode, d + timedelta(days=4), d + timedelta(days=6),
                                                round(weekday_price * season * 1.25), rng.randint(1, 6)])
                        d += timedelta(days=7)
        out[group] = sheets
    # Drop week rows whose start was clipped past their end (first partial week).
    for sheets in out.values():
        sheets["Rates"] = [r for r in sheets["Rates"] if r[1] <= r[2]]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "samples")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    groups = build(args.days)
    combined = {name: [] for name in SHEETS}
    for group, sheets in groups.items():
        slug = group.lower().replace(" ", "_")
        path = args.out / f"{slug}.xlsx"
        path.write_bytes(template_workbook(sheets))
        print(f"  {path.relative_to(ROOT)}  ({len(sheets['Hotels'])} hotels)")
        for k in combined:
            combined[k].extend(sheets[k])
    path = args.out / "all_hotels_synthetic.xlsx"
    path.write_bytes(template_workbook(combined))
    print(f"  {path.relative_to(ROOT)}  ({len(combined['Hotels'])} hotels, all groups)")


if __name__ == "__main__":
    main()

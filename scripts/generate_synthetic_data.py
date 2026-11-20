"""Generate realistic synthetic hotels for Fichua's launch markets as upload-ready Excel files.

    python scripts/generate_synthetic_data.py

Writes one workbook per (fictional) hotel group plus an all-in-one file to data/samples/.
Prices are in USD. Rooms carry a standard + weekend price and a room count, so every night is
open without rate rows; the Rates sheet only adds the Christmas season.
Phone/WhatsApp are left empty on purpose: no real number ever receives a test message.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date
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

# group → city → (country, code, lat, lng, [(name, type, stars, base USD)])
GROUPS = {
    "Imena Hospitality": {
        "Kigali": ("Rwanda", "KGL", -1.9441, 30.0619, [
            ("Kigali Hills Hotel", "Hotel", 4, 85), ("Nyarutarama Garden Suites", "Apartment", 4, 110),
            ("Kimihurura Boutique House", "Boutique", 4, 95), ("Kacyiru Business Hotel", "Hotel", 3, 60)]),
        "Musanze": ("Rwanda", "MUS", -1.4994, 29.6347, [
            ("Volcano View Lodge", "Lodge", 5, 240), ("Twin Lakes Retreat", "Lodge", 4, 150),
            ("Kinigi Forest Cabins", "Lodge", 3, 90), ("Musanze Town Inn", "Guesthouse", 2, 40)]),
    },
    "Atlantique Collection": {
        "Cotonou": ("Benin", "COO", 6.3703, 2.3912, [
            ("Hôtel Lagune Bleue", "Hotel", 4, 95), ("Résidence Haie Vive", "Apartment", 4, 80),
            ("Fidjrossè Beach Hotel", "Resort", 4, 120), ("Ganhi Business Inn", "Hotel", 3, 55)]),
        "Ouidah": ("Benin", "OUI", 6.3631, 2.0851, [
            ("Ouidah Plage Lodge", "Lodge", 3, 65), ("Jardin de Ouidah", "Guesthouse", 3, 45),
            ("Bouche du Roy Eco Lodge", "Lodge", 4, 110), ("Casa Ouidah", "Boutique", 4, 75)]),
    },
    "Lagune Stays": {
        "Abidjan": ("Côte d'Ivoire", "ABJ", 5.3600, -4.0083, [
            ("Plateau Skyline Hotel", "Hotel", 5, 190), ("Cocody Riviera Suites", "Apartment", 4, 130),
            ("Zone 4 Boutique Hotel", "Boutique", 4, 115), ("Marcory Lagoon Residence", "Hotel", 3, 70)]),
        "Grand-Bassam": ("Côte d'Ivoire", "GBA", 5.1950, -3.7380, [
            ("Bassam Plage Hotel", "Resort", 4, 105), ("Quartier France Heritage Inn", "Boutique", 3, 70),
            ("Comoé Beach Bungalows", "Lodge", 3, 60), ("Bassam Lagoon Lodge", "Lodge", 4, 95)]),
    },
}

AMENITIES = ["Free WiFi", "Pool", "Restaurant", "Bar", "Breakfast", "Free parking", "Airport shuttle", "Gym",
             "Spa", "Air conditioning", "Generator / backup power", "24h front desk", "Garden", "Rooftop terrace",
             "Beachfront", "Family rooms", "Laundry", "Conference room"]
ROOM_AMENITIES = ["Wi-Fi", "Hot shower", "TV", "Desk", "Air conditioning", "Fan", "Mosquito net", "Balcony",
                  "Minibar", "Safe", "Kettle"]
ROOMS = [  # name, max guests, bed, size, price factor, (min, max) rooms
    ("Standard Double Room", 2, "1 double bed", 20, 1.0, (6, 14)),
    ("Deluxe King Room", 2, "1 king bed", 28, 1.35, (3, 8)),
    ("Family Suite", 4, "1 king + 2 single beds", 45, 1.9, (1, 4)),
]
DESCRIPTIONS = {
    "Boutique": "An intimate, design-led stay in {city}, with handcrafted interiors and a team that knows every hidden gem nearby.",
    "Lodge": "A calm, nature-wrapped lodge near {city}. Wake up to birdsong, unwind by the fire and explore at your own pace.",
    "Hotel": "A polished hotel in {city} with generous rooms, reliable WiFi and backup power, for business trips or a long weekend.",
    "Resort": "A sun-soaked resort near {city} with a pool, beach access and long, lazy days built in.",
    "Apartment": "Spacious serviced apartments in {city} with kitchens, for families and longer stays.",
    "Guesthouse": "A friendly, family-run guesthouse in {city}: simple rooms, a warm welcome and great local tips.",
}


def season_window(today: date) -> tuple[date, date]:
    year = today.year - 1 if today <= date(today.year, 1, 3) else today.year
    return date(year, 12, 20), date(year + 1, 1, 3)


def build(seed: int = 11) -> dict[str, dict[str, list[list]]]:
    rng = random.Random(seed)
    s_from, s_to = season_window(date.today())
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
                for must in ("Free WiFi", "Generator / backup power"):
                    if must not in amen:
                        amen.insert(0, must)
                if ptype == "Resort" and "Pool" not in amen:
                    amen.insert(0, "Pool")
                sheets["Hotels"].append([
                    hcode, group, name, city, country, f"{rng.randint(1, 240)} {name.split()[0]} Road, {city}",
                    round(lat + rng.uniform(-0.03, 0.03), 5), round(lng + rng.uniform(-0.03, 0.03), 5),
                    stars, round(min(9.7, rng.uniform(7.3, 8.4) + (stars - 3) * 0.35), 1), rng.randint(40, 1800),
                    ptype, DESCRIPTIONS[ptype].format(city=city), ", ".join(amen), ", ".join(photos),
                    "USD", "14:00", "11:00", "yes", "", "", "",
                ])
                weekend_factor = 1.2 if ptype in ("Resort", "Lodge") else 1.1
                for rname, guests, bed, size, factor, (lo, hi) in ROOMS:
                    rcode = f"{hcode}-{rname.split()[0][:3].upper()}"
                    price = round(base * factor * rng.uniform(0.95, 1.05))
                    total = rng.randint(lo, hi)
                    sheets["Rooms"].append([
                        rcode, hcode, rname, guests, bed, size + rng.randint(-2, 6),
                        f"{rname} with {bed} and {size} m² of calm.",
                        ", ".join(rng.sample(ROOM_AMENITIES, 4)),
                        ", ".join(U.format(ROOM_PHOTOS[rng.randrange(len(ROOM_PHOTOS))]) for _ in range(2)),
                        "yes" if rng.random() < 0.45 else "no", "no" if rng.random() < 0.15 else "yes",
                        total, price, round(price * weekend_factor),
                    ])
                    sheets["Rates"].append([rcode, s_from, s_to, round(price * 1.25), total])
        out[group] = sheets
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "samples")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.xlsx"):
        old.unlink()  # previous sample files (old markets) — regenerated below
    groups = build()
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

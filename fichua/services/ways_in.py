"""Ways in by trip purpose (Brief 2 §7): travellers pick why they are travelling, never who they are.

Each way in is a search (a destination, a filter, or both). One whose destination has no live hotels
stays hidden. Update the list as the founding properties arrive.
"""
from __future__ import annotations

WAYS_IN = [
    {"title": "Gorilla trek nights", "line": "Lodges near Volcanoes National Park and the Kinigi trailheads.",
     "params": {"destination": "Musanze"}},
    {"title": "Coming home", "line": "Family rooms and calm bases for December and July returns.",
     "params": {"amenity": "Family rooms", "guests": 4}},
    {"title": "Work trip, plus a weekend", "line": "Wi-Fi and backup power in Kigali, a quieter weekend after.",
     "params": {"destination": "Kigali"}},
    {"title": "Heritage and roots", "line": "Ouidah, its Afro-Brazilian houses and the Route des Esclaves.",
     "params": {"destination": "Ouidah"}},
    {"title": "A weekend by the sea", "line": "Grand-Bassam's old town and beaches, about an hour from Abidjan.",
     "params": {"destination": "Grand-Bassam"}},
    {"title": "A team retreat", "line": "A meeting room and space for the whole group.",
     "params": {"amenity": "Conference room", "guests": 10, "rooms": 5}},
]


def available(destinations: list[dict]) -> list[dict]:
    """The ways in whose destination has live hotels; those without a destination always show."""
    cities = {d["city"].lower() for d in destinations}
    return [w for w in WAYS_IN
            if not w["params"].get("destination") or w["params"]["destination"].lower() in cities]

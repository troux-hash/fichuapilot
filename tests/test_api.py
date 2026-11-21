"""The public JSON API only shows what a guest may see (QA finding FIX-01)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from fichua.main import app
from fichua.services import catalog

CI = date.today() + timedelta(days=30)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat(), "guests": 2}
PRIVATE = {"owner_id", "commission_pct", "phone", "whatsapp", "email", "review_note", "status", "plan",
           "manager_free_until", "terms_accepted_at", "submitted_at", "approved_at", "hotel_group", "image_urls",
           "total_rooms", "base_price", "weekend_price"}


def test_search_api_returns_public_fields_only():
    data = TestClient(app).get("/api/search", params={"destination": "Kigali", **STAY}).json()
    assert data["results"], "expected Kigali results"
    for offer in data["results"]:
        assert set(offer) == {"hotel", "room", "total_price", "per_night", "rooms_left"}
        assert set(offer["hotel"]) == set(catalog.PUBLIC_HOTEL_FIELDS)
        assert set(offer["room"]) == set(catalog.PUBLIC_ROOM_FIELDS)
        assert not PRIVATE & (set(offer["hotel"]) | set(offer["room"]))

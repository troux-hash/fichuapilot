"""Partner side end to end: access code → onboarding → admin approval → live in search →
calendar changes and offline bookings change availability → paid booking shows in finance."""
import base64
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import catalog, dates, payouts

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
CI = date.today() + timedelta(days=20)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat(), "guests": 2}
state: dict = {}


def test_access_code_gates_sign_up(admin):
    r = admin.post("/admin/codes", data={"code": "kigali-pilot", "plan": "manager", "max_uses": "1",
                                         "free_until": "2027-06-30"}, follow_redirects=False)
    assert r.status_code == 303 and "KIGALI-PILOT" in r.headers["location"]
    partner = TestClient(app)
    bad = partner.post("/partners/join", data={"code": "NOPE", "name": "Grace", "hotel_name": "Ubuntu Stay",
                                               "email": "grace@example.com", "phone": "+250788000333", "password": "secret123"})
    assert bad.status_code == 422 and "Check it with the Fichua team" in bad.text
    ok = partner.post("/partners/join", data={"code": "kigali-pilot", "name": "Grace", "hotel_name": "Ubuntu Stay",
                                              "email": "grace@example.com", "phone": "+250788000333",
                                              "password": "secret123"}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/partners/hotel"
    reused = TestClient(app).post("/partners/join", data={"code": "KIGALI-PILOT", "name": "Eve", "hotel_name": "Eve Lodge",
                                                          "email": "eve@example.com", "phone": "+250788000444",
                                                          "password": "secret123"})
    assert reused.status_code == 422 and "already been used" in reused.text
    state["partner"] = partner
    with db.connect() as conn:
        hotel = conn.one("SELECT * FROM hotels WHERE email = 'grace@example.com'")
    assert hotel["status"] == "draft" and not hotel["is_active"] and re.match(r"FH-\d{5}", hotel["id"])
    assert hotel["plan"] == "manager" and hotel["manager_free_until"] == "2027-06-30"
    state["hotel_id"] = hotel["id"]


def test_onboarding_steps_then_submit():
    p = state["partner"]
    r = p.post("/partners/hotel", data={"name": "Ubuntu Stay", "property_type": "Guesthouse", "country": "Rwanda",
                                        "city": "Huye", "address": "12 University Ave", "lat": "-2.5967", "lng": "29.7394",
                                        "phone": "+250788000333", "whatsapp": "+250788000333", "description": "Calm.",
                                        "amenities": ["Free WiFi", "Garden"]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/partners/photos"
    for i in range(3):
        r = p.post("/partners/photos", files={"files": (f"p{i}.png", PNG, "image/png")}, follow_redirects=False)
        assert r.status_code == 303
    r = p.post("/partners/rooms/new", data={"name": "Basic room", "room_kind": "Double", "total_rooms": "2",
                                            "max_guests": "2", "base_price": "50", "weekend_price": "60"},
               files={"files": ("room.png", PNG, "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    bad = p.post("/partners/rooms/new", data={"name": "", "total_rooms": "0", "max_guests": "2", "base_price": ""})
    assert bad.status_code == 422 and "standard price" in bad.text
    assert p.post("/partners/review").status_code in (200, 405)  # GET only page
    early = p.post("/partners/submit")
    assert early.status_code == 422  # policies not accepted yet
    r = p.post("/partners/policies", data={"cancellation_policy": "flexible", "children_allowed": "1",
                                           "accept_terms": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/partners/review"
    assert p.post("/partners/submit", follow_redirects=False).status_code == 303
    with db.connect() as conn:
        h = conn.one("SELECT status, is_active FROM hotels WHERE id = :id", {"id": state["hotel_id"]})
        state["room_id"] = conn.scalar("SELECT id FROM room_types WHERE hotel_id = :id", {"id": state["hotel_id"]})
        media_id = conn.scalar("SELECT id FROM media WHERE owner_id = :id", {"id": state["hotel_id"]})
    assert h["status"] == "pending" and not h["is_active"]
    assert TestClient(app).get(f"/media/{media_id}").content == PNG
    assert not TestClient(app).get("/api/search", params={"destination": "Huye", **STAY}).json()["results"]


def test_admin_approves_with_custom_commission(admin):
    page = admin.get("/admin/approvals")
    assert "Ubuntu Stay" in page.text
    detail = admin.get(f"/admin/approvals/{state['hotel_id']}")
    assert "Map pin is inside Rwanda" in detail.text
    r = admin.post(f"/admin/approvals/{state['hotel_id']}", data={"action": "approve", "commission": "10"},
                   follow_redirects=False)
    assert r.status_code == 303
    results = TestClient(app).get("/api/search", params={"destination": "Huye", **STAY}).json()["results"]
    assert len(results) == 1 and results[0]["total_price"] in (100, 110, 120)
    with db.connect() as conn:
        kinds = [m["kind"] for m in conn.all("SELECT kind FROM messages WHERE hotel_id = :h", {"h": state["hotel_id"]})]
    assert "hotel_approved" in kinds


def test_calendar_price_and_closing_change_search():
    p = state["partner"]
    assert p.get("/partners/calendar").status_code == 200
    night = CI.isoformat()
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "date_to": night,
                                       "apply_to": "all", "price": "80"})
    with db.connect() as conn:
        stay = dates.Stay(CI, CI + timedelta(days=1), 2)
        assert catalog.availability(conn, stay, hotel_id=state["hotel_id"])[0]["total_price"] == 80
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "date_to": night,
                                       "apply_to": "all", "closed": "1"})
    with db.connect() as conn:
        assert catalog.availability(conn, dates.Stay(CI, CI + timedelta(days=1), 2), hotel_id=state["hotel_id"]) == []
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "date_to": night,
                                       "apply_to": "all", "reset": "1"})
    with db.connect() as conn:
        assert catalog.availability(conn, dates.Stay(CI, CI + timedelta(days=1), 2), hotel_id=state["hotel_id"])


def test_calendar_empty_boxes_keep_existing_prices():
    p = state["partner"]
    night = (CI + timedelta(days=30)).isoformat()
    one = dates.Stay(CI + timedelta(days=30), CI + timedelta(days=31), 2)
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "apply_to": "all", "price": "99"})
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "apply_to": "all", "closed": "1"})
    with db.connect() as conn:
        assert catalog.availability(conn, one, hotel_id=state["hotel_id"]) == []
    p.post("/partners/calendar", data={"room": state["room_id"], "date_from": night, "apply_to": "all"})  # reopen
    with db.connect() as conn:
        assert catalog.availability(conn, one, hotel_id=state["hotel_id"])[0]["total_price"] == 99


def test_offline_booking_blocks_rooms():
    p = state["partner"]
    day = CI + timedelta(days=5)
    r = p.post("/partners/bookings/new", data={"room": state["room_id"], "check_in": day.isoformat(),
                                               "check_out": (day + timedelta(days=1)).isoformat(), "guests": "2",
                                               "guest_name": "Walk-in guest", "source": "Walk-in", "rooms_count": "2"},
               follow_redirects=False)
    assert r.status_code == 303
    with db.connect() as conn:
        assert catalog.availability(conn, dates.Stay(day, day + timedelta(days=1), 2), hotel_id=state["hotel_id"]) == []
    too_many = p.post("/partners/bookings/new", data={"room": state["room_id"], "check_in": day.isoformat(),
                                                      "check_out": (day + timedelta(days=1)).isoformat(),
                                                      "guest_name": "Another", "rooms_count": "1"})
    assert too_many.status_code == 422
    assert "Walk-in guest" in p.get("/partners/bookings").text


def test_guest_booking_pays_hotel_with_its_commission(admin):
    guest = TestClient(app)
    form = {"room": state["room_id"], **STAY, "guest_name": "Jo Doe", "guest_email": "jo@example.com",
            "guest_phone": "+250788000555"}
    loc = guest.post("/book", data=form, follow_redirects=False).headers["location"]
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", loc).groups()
    guest.post(f"/pay/{ref}", data={"t": token})
    with db.connect() as conn:
        b = conn.one("SELECT * FROM bookings WHERE reference = :r", {"r": ref})
    assert b["commission_pct"] == 10 and b["commission_amount"] == pytest.approx(b["total_price"] * 0.10)
    assert ref in state["partner"].get("/partners/bookings").text
    fin = admin.get("/admin/finance", params={"hotel": state["hotel_id"], "period": "all"})
    assert fin.status_code == 200 and ref in fin.text and "Ubuntu Stay" in fin.text
    assert admin.get("/admin/messages").status_code == 200


def test_payout_timing_setting(admin):
    r = admin.post("/admin/settings", data={"commission_pct": "7", "payout_timing": "after_checkin",
                                            "payout_delay_hours": "24", "rate_RWF": "1450", "rate_XOF": "565",
                                            "manager_fee_usd": "0", "hold_minutes": "35", "admin_whatsapp": ""},
                   follow_redirects=False)
    assert r.status_code == 303
    guest = TestClient(app)
    offer = guest.get("/api/search", params={"destination": "Musanze", **STAY}).json()["results"][0]
    loc = guest.post("/book", data={"room": offer["room"]["id"], **STAY, "guest_name": "Sam", "guest_email": "s@example.com",
                                    "guest_phone": "+250788000666"}, follow_redirects=False).headers["location"]
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", loc).groups()
    guest.post(f"/pay/{ref}", data={"t": token})
    with db.connect() as conn:
        b = conn.one("SELECT id FROM bookings WHERE reference = :r", {"r": ref})
        assert conn.scalar("SELECT status FROM payouts WHERE booking_id = :b", {"b": b["id"]}) == "scheduled"
        payouts.process_due(conn)
        assert conn.scalar("SELECT status FROM payouts WHERE booking_id = :b", {"b": b["id"]}) == "scheduled"
    bad = admin.post("/admin/settings", data={"commission_pct": "abc", "payout_timing": "immediate"})
    assert bad.status_code == 422
    admin.post("/admin/settings", data={"commission_pct": "7", "payout_timing": "immediate", "payout_delay_hours": "24",
                                        "rate_RWF": "1450", "rate_XOF": "565", "manager_fee_usd": "0", "hold_minutes": "35"})


def test_partner_login_and_pages():
    c = TestClient(app)
    assert c.post("/partners/login", data={"email": "grace@example.com", "password": "wrong"}).status_code == 401
    r = c.post("/partners/login", data={"email": "GRACE@example.com", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303
    for path in ("/partners/hotel", "/partners/photos", "/partners/rooms", "/partners/policies", "/partners/review",
                 "/partners/calendar", "/partners/bookings", "/partners/bookings/new", f"/partners/rooms/{state['room_id']}"):
        assert c.get(path).status_code == 200, path
    assert "Built at MIT" in c.get("/partners/calendar").text
    assert TestClient(app).get("/partners/calendar", follow_redirects=False).status_code == 303


def test_admin_pages_render(admin):
    for path in ("/admin", "/admin/approvals", "/admin/hotels", "/admin/finance", "/admin/finance?period=week",
                 "/admin/finance?period=custom&from=2026-01-01&to=2027-12-31&source=all", "/admin/messages",
                 "/admin/messages?role=hotel", "/admin/codes", "/admin/settings"):
        assert admin.get(path).status_code == 200, path

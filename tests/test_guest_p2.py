"""Guest-side P2 improvements from the 21 Nov QA test: date notes (IMP-01), arrival-day details on the
booking page (IMP-02), address and map (IMP-03), cancellation dates (IMP-04), small card photos (IMP-07)
and wording (IMP-08)."""
import base64
import re
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.routes.public import _nights_text
from fichua.services import bookings, catalog, currency, dates, partners, policies, stay_calendar
from fichua.web import card_img

guest = TestClient(app)
CI = date.today() + timedelta(days=15)
CO = CI + timedelta(days=2)
STAY = {"check_in": CI.isoformat(), "check_out": CO.isoformat(), "guests": 2}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _book(room_id: str, stay: dict) -> tuple[str, str]:
    form = {"room": room_id, **stay, "guest_name": "Grace Hopper", "guest_email": "grace@example.com",
            "guest_phone": "+250 788 000 555", "guest_language": "en"}
    r = guest.post("/book", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text[-600:]
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", r.headers["location"]).groups()
    assert guest.post(f"/pay/{ref}", data={"t": token}, follow_redirects=False).status_code == 303
    return ref, token


def test_impossible_dates_are_explained():  # IMP-01
    today = date(2026, 11, 21)

    def note(ci, co, guests=2):
        return dates.adjustment(ci, co, guests, dates.parse_stay(ci, co, guests, today=today), today=today)

    assert note("2026-11-01", "2026-11-03").startswith("We changed your dates to ")
    assert "can't be in the past" in note("2026-11-01", "2026-11-03")
    assert "after check-in" in note("2026-12-10", "2026-12-08")
    assert "30 nights" in note("2026-12-01", "2027-02-01")
    assert "couldn't read" in note("2026-13-45", "2026-12-08")
    assert "to 12" in note("2026-12-01", "2026-12-03", 40)
    assert note("2026-12-01", "2026-12-03") is None
    assert note(None, None, None) is None  # nothing asked, nothing to explain
    past = (date.today() - timedelta(days=3)).isoformat()
    page = guest.get("/search", params={"destination": "Kigali", "check_in": past, "check_out": CO.isoformat()})
    assert "We changed your dates to" in page.text
    assert "We changed your dates" not in guest.get("/search", params={"destination": "Kigali", **STAY}).text
    room = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]["room"]["id"]
    checkout = guest.get("/book", params={"room": room, "check_in": past, "check_out": CO.isoformat()})
    assert "We changed your dates to" in checkout.text  # never pay for other dates without being told


def test_cancellation_deadlines():  # IMP-04
    ci = date(2026, 12, 4)
    assert policies.free_until("moderate", True, ci) == date(2026, 11, 29)
    assert policies.free_until("flexible", True, "2026-12-04") == date(2026, 12, 3)
    assert policies.free_until(None, True, ci) == date(2026, 12, 3)  # Excel hotels default to flexible
    assert policies.free_until("strict", True, ci) is None
    assert policies.free_until("flexible", False, ci) is None
    assert policies.open_until("flexible", True, ci, today=date(2026, 12, 3)) == date(2026, 12, 3)
    assert policies.open_until("flexible", True, ci, today=date(2026, 12, 4)) is None  # too late to book it free
    page = guest.get("/search", params={"destination": "Kigali", **STAY})
    assert "Free cancellation until" in page.text


def test_cancel_button_follows_the_policy():  # IMP-04: what the badge promised is what Cancel allows
    soon = date.today() + timedelta(days=3)
    stay = {"check_in": soon.isoformat(), "check_out": (soon + timedelta(days=1)).isoformat(), "guests": 2}
    offer = guest.get("/api/search", params={"destination": "Abidjan", **stay, "free_cancellation": "1",
                                             "sort": "price"}).json()["results"][0]
    hotel_id = offer["hotel"]["id"]
    with db.connect() as conn:
        before = conn.scalar("SELECT cancellation_policy FROM hotels WHERE id = :h", {"h": hotel_id})
        conn.run("UPDATE hotels SET cancellation_policy = 'moderate' WHERE id = :h", {"h": hotel_id})
    try:
        ref, token = _book(offer["room"]["id"], stay)
        page = guest.get(f"/bookings/{ref}", params={"t": token})
        assert "Cancel and refund" not in page.text and "Free cancellation ended on" in page.text
        refused = guest.post(f"/bookings/{ref}/cancel", data={"t": token})
        assert "can no longer be cancelled online" in refused.text
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET cancellation_policy = :p WHERE id = :h", {"p": before, "h": hotel_id})


def test_address_and_map():  # IMP-03
    h = {"address": "KG 7 Ave", "area": "Kimihurura", "city": "Kigali", "country": "Rwanda", "lat": -1.95, "lng": 30.09}
    assert catalog.full_address(h) == "KG 7 Ave, Kimihurura, Kigali, Rwanda"
    assert catalog.full_address({**h, "address": "KG 7 Ave, Kigali"}).count("Kigali") == 1
    links = catalog.map_links(h)
    assert "openstreetmap.org/export/embed.html" in links["map_embed"] and "marker=-1.950000%2C30.090000" in links["map_embed"]
    assert links["map_url"] == "https://www.google.com/maps/search/?api=1&query=-1.950000%2C30.090000"
    no_pin = catalog.map_links({"address": "KG 7 Ave", "city": "Kigali"})
    assert no_pin["map_embed"] is None and "KG+7+Ave" in no_pin["map_url"]
    hotel_id = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]["hotel"]["id"]
    page = guest.get(f"/hotels/{hotel_id}", params=STAY)
    assert "Where you'll stay" in page.text and 'class="map-embed"' in page.text and "Open in Google Maps" in page.text


def test_card_photos_are_small():  # IMP-07
    assert card_img("https://images.unsplash.com/photo-1?auto=format&w=1200&q=70") == \
        "https://images.unsplash.com/photo-1?auto=format&w=800&q=70"
    assert card_img("/media/abc") == "/media/abc?size=card"
    assert card_img("/static/img/placeholder.svg") == "/static/img/placeholder.svg"
    cards = guest.get("/search", params={"destination": "Kigali", **STAY}).text
    assert "w=800" in cards and "w=1200" not in cards
    jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"small copy"
    with db.connect() as conn:
        with_copy = partners.add_photo(conn, "hotel", "TEST-THUMBS", PNG, "image/png", thumb=jpeg)
        odd_copy = partners.add_photo(conn, "hotel", "TEST-THUMBS", PNG, "image/png", thumb=b"not a jpeg")
    try:
        assert guest.get(f"/media/{with_copy}", params={"size": "card"}).content == jpeg
        assert guest.get(f"/media/{with_copy}").content == PNG
        assert guest.get(f"/media/{odd_copy}", params={"size": "card"}).content == PNG  # falls back to the photo
    finally:
        with db.connect() as conn:
            conn.run("DELETE FROM media WHERE owner_id = 'TEST-THUMBS'")


def test_wording():  # IMP-08
    one = dates.Stay(date(2026, 12, 1), date(2026, 12, 2), 2)
    three = dates.Stay(date(2026, 12, 1), date(2026, 12, 4), 2)
    assert _nights_text(one, {"nightly": [65.0], "total_price": 65.0}) == "1 night × $65"
    assert _nights_text(three, {"nightly": [60.0, 60.0, 90.0], "total_price": 210.0}) == "3 nights (average $70)"
    assert _nights_text(one, None) == "1 night"
    room = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]["room"]["id"]
    checkout = guest.get("/book", params={"room": room, **STAY}).text
    assert "2 nights × $" in checkout or "2 nights (average $" in checkout
    assert "average" not in checkout or "2 nights (average" in checkout


def test_phone_numbers_with_country_codes():  # IMP-02: WhatsApp and call links need them
    assert currency.international_phone("0788 123 456", "Rwanda") == "250788123456"
    assert currency.international_phone("+250 788 123 456", "Benin") == "250788123456"
    assert currency.international_phone("0025 0788 123 456", None) == "250788123456"
    assert currency.international_phone("01 97 00 00 00", "Benin") == "2290197000000"
    assert currency.international_phone("07 07 07 07 07", "Côte d'Ivoire") == "2250707070707"
    assert currency.international_phone("", "Rwanda") == ""
    links = bookings.contact_links({"hotel_phone": "0788 123 456", "hotel_whatsapp": "", "country": "Rwanda",
                                    "hotel_name": "Ubuntu Stay", "reference": "FCH-ABC123",
                                    "check_in": "2026-12-04", "check_out": "2026-12-06"})
    assert links["hotel_tel"] == "+250788123456"
    assert links["hotel_wa"].startswith("https://wa.me/250788123456?text=Hello")
    assert bookings.contact_links({"country": "Rwanda", "check_in": "2026-12-04", "check_out": "2026-12-06"}) == \
        {"hotel_tel": None, "hotel_wa": None}


def test_calendar_event_in_the_hotels_time():  # IMP-02
    b = {"id": "b1", "reference": "FCH-TEST01", "hotel_name": "Kigali Hills, Hotel", "room_name": "Deluxe; Double",
         "guests": 2, "check_in": "2026-12-04", "check_out": "2026-12-06", "check_in_time": "14:00",
         "check_out_time": "11:00", "country": "Rwanda", "full_address": "KG 7 Ave, Kigali, Rwanda",
         "hotel_phone": "+250 788 000 000"}
    text = stay_calendar.ics(b, "https://fichua.example/manage", now=datetime(2026, 11, 21, 8, 0))
    assert "DTSTART:20261204T120000Z" in text and "DTEND:20261206T090000Z" in text  # Kigali is UTC+2
    assert "SUMMARY:Stay at Kigali Hills\\, Hotel" in text and text.endswith("END:VCALENDAR\r\n")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    abidjan = stay_calendar.google_link({**b, "country": "Côte d'Ivoire"}, "https://fichua.example/manage")
    assert "dates=20261204T140000Z%2F20261206T110000Z" in abidjan  # Abidjan is UTC+0


def test_booking_page_has_what_guests_need_on_arrival():  # IMP-02
    offer = guest.get("/api/search", params={"destination": "Cotonou", **STAY, "sort": "price"}).json()["results"][0]
    ref, token = _book(offer["room"]["id"], STAY)
    page = guest.get(f"/bookings/{ref}", params={"t": token}).text
    assert "Directions" in page and "google.com/maps/search" in page and "Add to calendar" in page
    assert "calendar.google.com" in page
    ics = guest.get(f"/bookings/{ref}/calendar.ics", params={"t": token})
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in ics.text and ref in ics.text and token not in ics.text
    assert guest.get(f"/bookings/{ref}/calendar.ics", params={"t": "wrong"}).status_code == 404
    pay = guest.get(f"/pay/{ref}", params={"t": token}, follow_redirects=False)
    assert pay.status_code == 303  # paid already: the reference sits on one line on the pay page (IMP-08)

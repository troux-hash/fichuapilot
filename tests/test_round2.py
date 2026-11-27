"""Bugs from the second end-to-end check (21 Nov 2026): prices without stray cents, the sticky bar on phones,
the calendar reopening on the month that changed, and the approval page showing what goes public."""
import base64
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app

guest = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _thursday(weeks: int = 5) -> date:
    """A Thursday at least `weeks` ahead and outside the seed's 20 Dec – 3 Jan season, where every night costs the same."""
    d = date.today() + timedelta(weeks=weeks)
    d += timedelta(days=(3 - d.weekday()) % 7)
    while (d.month == 12 and d.day >= 17) or (d.month == 1 and d.day <= 3):
        d += timedelta(weeks=1)
    return d


def test_prices_show_the_total_and_no_stray_cents():  # R2-B2
    ci = _thursday()
    stay = {"check_in": ci.isoformat(), "check_out": (ci + timedelta(days=3)).isoformat(), "guests": 2}
    offers = guest.get("/api/search", params={"destination": "Kigali", **stay}).json()["results"]
    uneven = next(o for o in offers if o["per_night"] != int(o["per_night"]))  # Thu + Fri + Sat at two prices
    results = guest.get("/search", params={"destination": "Kigali", **stay}).text
    page = guest.get(uneven["hotel"]["path"], params=stay).text
    for html in (results, page):
        assert not re.search(r"\$\d[\d,]*\.\d\d(/night| a night)", html), "a nightly price with cents"
        assert "avg $" in html
    assert "for 3 nights" in page and "From</div>" not in page


def test_sticky_bar_on_phones_puts_two_actions_under_the_price():  # R2-B1
    offer = guest.get("/api/search", params={"destination": "Kigali"}).json()["results"][0]
    with db.connect() as conn:
        before = conn.scalar("SELECT phone FROM hotels WHERE id = :id", {"id": offer["hotel"]["id"]})
        conn.run("UPDATE hotels SET phone = '0788 123 456' WHERE id = :id", {"id": offer["hotel"]["id"]})
    try:
        page = guest.get(offer["hotel"]["path"]).text
        assert 'class="sticky-cta sticky-cta--two"' in page and "See rooms and book" in page
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET phone = :p WHERE id = :id", {"p": before, "id": offer["hotel"]["id"]})


def _partner(admin, code: str, email: str) -> tuple[TestClient, str]:
    assert admin.post("/admin/codes", data={"code": code, "plan": "manager", "max_uses": "1"},
                      follow_redirects=False).status_code == 303
    p = TestClient(app)
    assert p.post("/partners/join", data={"code": code, "name": "Eric", "hotel_name": "Round Two Lodge", "email": email,
                                          "phone": "0788 000 999", "password": "secret123"},
                  follow_redirects=False).status_code == 303
    with db.connect() as conn:
        hotel_id = conn.scalar("SELECT id FROM hotels WHERE email = :e", {"e": email})
    p.post("/partners/hotel", data={"name": "Round Two Lodge", "property_type": "Lodge", "country": "Rwanda",
                                    "city": "Rubavu", "address": "Lake road 1", "lat": "-1.69", "lng": "29.25",
                                    "phone": "0788 000 999", "whatsapp": "0788 000 999", "email": email,
                                    "legal_name": "Round Two Ltd", "tax_id": "TIN 555"})
    for i in range(3):
        p.post("/partners/photos", files={"files": (f"p{i}.png", PNG, "image/png")})
    p.post("/partners/rooms/new", data={"name": "Lake Double", "room_kind": "Double", "total_rooms": "3",
                                        "max_guests": "2", "base_price": "150"})
    return p, hotel_id


def test_calendar_reopens_on_the_month_that_changed(admin):  # R2-B5
    p, _ = _partner(admin, "ROUND2-CAL", "round2cal@example.com")
    room = re.search(r'name="room" value="([^"]+)"', p.get("/partners/calendar").text).group(1)
    start = date.today().replace(day=1) + timedelta(days=70)  # two or three months ahead
    r = p.post("/partners/calendar", data={"room": room, "month": f"{date.today():%Y-%m}", "date_from": start.isoformat(),
                                           "date_to": (start + timedelta(days=2)).isoformat(), "price": "190"},
               follow_redirects=False)
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert r.status_code == 303 and query["month"] == [f"{start:%Y-%m}"] and query["saved"] == ["3"]
    bad = p.post("/partners/calendar", data={"room": room, "month": "2026-11", "date_from": "nope"}, follow_redirects=False)
    assert parse_qs(urlparse(bad.headers["location"]).query)["error"] == ["Pick valid dates."]


def test_approval_page_shows_what_goes_public(admin):  # R2-B6
    p, hotel_id = _partner(admin, "ROUND2-HOST", "round2host@example.com")
    page = admin.get(f"/admin/approvals/{hotel_id}").text
    assert "No host profile" in page and "Round Two Ltd" in page and "tax no. TIN 555" in page
    p.post("/partners/host", data={"host_name": "Eric", "host_role": "Owner", "host_languages": ["English"],
                                   "host_welcome": "Welcome to the lake."})
    hidden = admin.get(f"/admin/approvals/{hotel_id}").text
    assert "Hidden: no consent yet" in hidden and "Welcome to the lake." in hidden
    p.post("/partners/host", data={"host_name": "Eric", "host_role": "Owner", "host_welcome": "Welcome to the lake.",
                                   "host_consent": "1"})
    assert "Shown to guests" in admin.get(f"/admin/approvals/{hotel_id}").text


def test_partner_copy_makes_no_unproven_claims():  # R2-B3 and R2-B4
    import pathlib
    templates = pathlib.Path(__file__).resolve().parent.parent / "fichua" / "templates" / "partners"
    assert "get more bookings" not in (templates / "photos.html").read_text(encoding="utf-8")
    rooms = (templates / "rooms.html").read_text(encoding="utf-8")
    assert rooms.index("loc }})") < rooms.index("Fri and Sat")  # the RWF figure follows the price it converts

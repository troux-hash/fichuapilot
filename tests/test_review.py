"""The ten changes from the design review of 25 Nov 2026: honest signals (demo places, pilot notice, MIT in words),
WhatsApp on every card, the home grid, compact cards, local money, the seal and receipt, laptop layouts with
compare, the owners' front door and step 1 in three parts, and lighter photos."""
import re
from datetime import date, timedelta

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import app_settings

guest = TestClient(app)
CI = date.today() + timedelta(days=30)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat(), "guests": 2}
state: dict = {}


def _live(country: str | None = None) -> list[dict]:
    with db.connect() as conn:
        sql = "SELECT id, name, country FROM hotels WHERE is_active = TRUE AND status = 'live'"
        rows = conn.all(sql + (" AND country = :c" if country else "") + " ORDER BY name",
                        {"c": country} if country else {})
    return rows


def c_demo(card: str) -> bool:
    return "place-card--demo" in card and "Demo place" in card and "Fichua Verified" not in card


def test_demo_place_is_labelled_and_never_called_verified():
    hotel = _live()[0]
    with db.connect() as conn:
        conn.run("UPDATE hotels SET is_demo = TRUE WHERE id = :id", {"id": hotel["id"]})
    try:
        page = guest.get(f"/hotels/{hotel['id']}", params=STAY).text
        assert "Demo place" in page and "not a real listing" in page
        assert "Fichua Verified" not in page and "seal--demo" in page
        results = guest.get("/search", params={"where": "all", **STAY}).text
        card = next(c for c in results.split('<article class="place-card')[1:] if hotel["name"] in c)
        assert c_demo(card)
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET is_demo = FALSE WHERE id = :id", {"id": hotel["id"]})


def test_pilot_notice_while_payments_are_tests():
    home = guest.get("/").text
    assert "pilot-strip" in home and "Bookings are tests for now" in home
    hotel = _live()[0]
    page = guest.get(f"/hotels/{hotel['id']}", params=STAY).text
    rooms = re.findall(r'href="/book\?([^"]+)"', page)
    if rooms:
        checkout = guest.get("/book?" + rooms[0].replace("&amp;", "&")).text
        assert "pilot-banner" in checkout and "pilot-strip" not in checkout  # one notice, beside the pay button
        assert "Mobile money" in checkout and "Coming soon" in checkout and 'value="card" checked' in checkout


def test_header_menu_keeps_list_your_place_in_reach():
    home = guest.get("/").text
    menu = home.split('<details class="menu">', 1)[1].split("</details>", 1)[0]
    assert 'href="/partners"' in menu and "List your place" in menu and 'href="/manage"' in menu


def test_home_shows_five_kinds_and_a_way_to_ask():
    home = guest.get("/").text
    assert home.count('class="kind-tile__input"') == 5
    assert "The money shown" in home and "WhatsApp the host" in home
    assert "data-kind-submit" not in home  # the button always works: no pick means every kind
    with db.connect() as conn:
        app_settings.put(conn, "admin_whatsapp", "+250788000999")
    try:
        assert "Not sure? Ask us on WhatsApp" in guest.get("/").text
    finally:
        with db.connect() as conn:
            app_settings.put(conn, "admin_whatsapp", "")


def test_cards_carry_whatsapp_money_bar_and_compare():
    hotel = _live()[0]
    with db.connect() as conn:
        before = conn.scalar("SELECT phone FROM hotels WHERE id = :id", {"id": hotel["id"]})
        conn.run("UPDATE hotels SET phone = '0788 123 456' WHERE id = :id", {"id": hotel["id"]})
    try:
        page = guest.get("/search", params={"where": "all", **STAY}).text
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET phone = :p WHERE id = :id", {"p": before, "id": hotel["id"]})
    cards = page.split('<article class="place-card')[1:]
    assert len(cards) >= 2
    for card in cards:
        assert "money-bar" in card and "Host gets" in card
        assert 'width="800" height="600"' in card  # space kept while photos load
    assert any("Ask on WhatsApp" in c for c in cards)
    assert 'data-compare-form' in page and page.count('data-compare>') == len(cards)
    assert "w=1200" not in page and "1600w" not in page


def test_compare_up_to_three_places():
    ids = [h["id"] for h in _live()][:4]
    r = guest.get("/compare", params={"id": ids, **STAY})
    assert r.status_code == 200 and "Compare side by side" in r.text
    names = {h["id"]: h["name"] for h in _live()}
    shown = [i for i in ids if names[i] in r.text]
    assert len(shown) <= 3 and ids[3] not in shown
    assert "Where your money goes" in r.text and "Mobile money is coming soon" in r.text
    empty = guest.get("/compare").text
    assert "Tick two or three places" in empty


def test_local_money_first_for_local_visitors():
    rw = _live("Rwanda")
    assert rw, "seed has Rwandan places"
    url = f"/hotels/{rw[0]['id']}"
    local = guest.get(url, params={**STAY, "visitor": "RW"}).text
    visitor = guest.get(url, params={**STAY, "visitor": "FR"}).text
    first = lambda html: html.split('class="price-box__main"', 1)[1].split("</p>", 1)[0]  # noqa: E731
    assert "RWF" in first(local) and "$" not in first(local)
    assert "$" in first(visitor) and "RWF" not in first(visitor)
    assert "Cards are charged in US dollars" in local


def test_place_page_has_sticky_box_for_laptops_and_inline_box_for_phones():
    hotel = _live()[0]
    page = guest.get(f"/hotels/{hotel['id']}", params=STAY).text
    assert 'class="place-aside only-laptop"' in page and 'class="only-phone"' in page
    assert page.count("booking-box-v2") >= 2 and "money-panel--receipt" in page
    assert len(re.findall(r'id="price-title-[pl]"', page)) == 2  # no duplicate ids between the two boxes


def test_owner_front_door_price_and_no_code_route():
    landing = TestClient(app).get("/partners").text
    assert "7% of the bookings Fichua brings. Nothing else." in landing.replace("<strong>", "").replace("</strong>", "")
    assert "No code? Ask on WhatsApp" not in landing  # hidden while Fichua's number is not set
    with db.connect() as conn:
        app_settings.put(conn, "admin_whatsapp", "+250788000999")
    try:
        landing = TestClient(app).get("/partners").text
        assert "No code? Ask on WhatsApp" in landing and "wa.me/250788000999" in landing
    finally:
        with db.connect() as conn:
            app_settings.put(conn, "admin_whatsapp", "")


def test_step_one_in_three_short_parts(admin):
    r = admin.post("/admin/codes", data={"code": "review-pilot", "plan": "manager", "max_uses": "1",
                                         "free_until": "2027-06-30"}, follow_redirects=False)
    assert r.status_code == 303
    p = TestClient(app)
    ok = p.post("/partners/join", data={"code": "review-pilot", "name": "Aline", "hotel_name": "Lake View Rooms",
                                        "email": "aline@example.com", "phone": "+250788000555",
                                        "password": "secret123"}, follow_redirects=False)
    assert ok.status_code == 303
    first = p.get("/partners/hotel").text
    assert "Part 1 of 3" in first and 'name="part" value="1"' in first and "data-map" not in first
    r = p.post("/partners/hotel", data={"part": "1", "name": "Lake View Rooms", "property_type": "Guesthouse",
                                        "category": "water", "good_for_sent": "1", "good_for": ["family"],
                                        "description": "Rooms over Lake Kivu."}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/partners/hotel?part=2"
    second = p.get("/partners/hotel?part=2").text
    assert "Where it is" in second and "data-map" in second and "leaflet" in second
    missing = p.post("/partners/hotel", data={"part": "2", "country": "Rwanda", "city": "Gisenyi", "address": ""})
    assert missing.status_code == 422 and "Enter the street address." in missing.text
    assert "Enter the reception phone." not in missing.text  # only this part's problems
    r = p.post("/partners/hotel", data={"part": "2", "country": "Rwanda", "city": "Gisenyi", "address": "Lake Rd 4",
                                        "lat": "-1.70", "lng": "29.26", "later": "1"}, follow_redirects=False)
    assert r.headers["location"] == "/partners/hotel?part=2&saved=1"
    r = p.post("/partners/hotel", data={"part": "3", "phone": "+250788000555", "whatsapp": "",
                                        "email": "aline@example.com", "check_in_time": "14:00",
                                        "check_out_time": "11:00", "star_rating": "", "amenities": ["Garden"],
                                        "legal_name": "", "tax_id": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/partners/photos"
    with db.connect() as conn:
        h = conn.one("SELECT * FROM hotels WHERE name = 'Lake View Rooms'")
    assert (h["name"], h["category"], h["city"], h["address"]) == ("Lake View Rooms", "water", "Gisenyi", "Lake Rd 4")
    assert h["description"] == "Rooms over Lake Kivu." and h["good_for"] == "family"
    assert h["whatsapp"] == "+250788000555"  # one number is enough
    assert "Garden" in (h["amenities"] or "")


def test_vetting_promise_and_dated_seal_need_five_dated_checks():
    hotel = _live()[0]
    with db.connect() as conn:
        conn.run("DELETE FROM hotel_checks WHERE hotel_id = :h", {"h": hotel["id"]})
    home = guest.get("/").text
    if "Verified hosts" not in home:  # no other place in the test data is fully checked
        assert "Places reviewed by our team" in home and "We review every place" in home
        assert "We vet every host" not in home
    seen = date.today() - timedelta(days=2)
    with db.connect() as conn:
        for check in ("identity", "licence", "location", "photos", "whatsapp"):
            conn.run("INSERT INTO hotel_checks (hotel_id, check_id, done_on, note) VALUES (:h, :c, :d, '')",
                     {"h": hotel["id"], "c": check, "d": seen})
    try:
        home = guest.get("/").text
        assert "Verified hosts" in home and "We vet every host" in home
        page = guest.get(f"/hotels/{hotel['id']}", params=STAY).text
        seal = page.split('class="seal seal--full"', 1)[1].split("</a>", 1)[0]
        assert "Fichua Verified · 5/5 · " in seal and str(seen.year) in seal
        assert re.search(r'<a class="seal seal--full" href="#checks"', page)
    finally:
        with db.connect() as conn:
            conn.run("DELETE FROM hotel_checks WHERE hotel_id = :h", {"h": hotel["id"]})


def test_demo_places_never_take_real_money(monkeypatch):
    import dataclasses

    import pytest

    from fichua.services import bookings, catalog, dates, payments
    hotel = _live()[0]
    with db.connect() as conn:
        room = conn.scalar("SELECT id FROM room_types WHERE hotel_id = :h ORDER BY id", {"h": hotel["id"]})
        conn.run("UPDATE hotels SET is_demo = TRUE WHERE id = :id", {"id": hotel["id"]})
    stay = dates.Stay(CI + timedelta(days=60), CI + timedelta(days=61), 1)
    try:
        monkeypatch.setattr(payments, "settings", dataclasses.replace(payments.settings, stripe_secret_key="sk_live_x"))
        with db.connect() as conn:
            if catalog.availability(conn, stay, room_type_id=room):
                with pytest.raises(bookings.BookingError, match="demo place"):
                    bookings.create_booking(conn, stay, room, guest_name="Test Guest", guest_email="t@example.com",
                                            guest_phone="+250788000111")
                conn.raw.rollback()
        page = guest.get(f"/hotels/{hotel['id']}", params={"check_in": stay.check_in.isoformat(),
                                                          "check_out": stay.check_out.isoformat(), "guests": 1}).text
        assert "Demo place: not bookable" in page and "pilot-strip" not in page
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET is_demo = FALSE WHERE id = :id", {"id": hotel["id"]})

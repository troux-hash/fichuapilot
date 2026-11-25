"""Brief 3 v3, built 25 Nov 2026: search by kind of place, the five dated checks, the money shown to travellers,
asking the host before booking, English and French, and the owner's home. Ranking never uses price, fees or
reply speed (decision of 25 Nov 2026)."""
import re
from datetime import date, timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import catalog, kinds, search
from fichua.services.dates import Stay

guest = TestClient(app)
CI = date.today() + timedelta(days=40)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat(), "guests": 2}


def _live():
    with db.connect() as conn:
        return catalog.live_hotels(conn)


def test_every_live_place_has_a_kind_and_the_search_keeps_to_it():
    hotels = _live()
    assert hotels and all(h["kind"] in kinds.KIND_IDS for h in hotels)
    water = [h for h in hotels if kinds.matches(h, ["water"])]
    assert water, "the seed has places by the water"
    with db.connect() as conn:
        found = search.discover(conn, ["water"], "all", Stay(CI, CI + timedelta(days=2), 2), dated=False)
    ids = {i["hotel"]["id"] for g in found["groups"] for i in g["places"]}
    assert ids and ids <= {h["id"] for h in water}
    page = guest.get("/search", params={"kind": "water", "dates": "any"}).text
    assert "From $" in page and " for 2 nights" not in page  # no dates: prices from, not a total


def test_two_kinds_are_grouped_under_their_own_heading():
    page = guest.get("/search", params={"kind": ["urban", "heritage"], "dates": "any"}).text
    assert 'id="group-urban"' in page and 'id="group-heritage"' in page
    assert page.index('id="group-urban"') < page.index('id="group-heritage"')


def test_ranking_puts_verified_places_first_never_the_cheapest():
    urban = [h for h in _live() if h["kind"] == "urban"]
    with db.connect() as conn:
        prices = catalog.from_prices(conn, [h["id"] for h in urban])
    dearest = max(urban, key=lambda h: prices.get(h["id"], 0))
    with db.connect() as conn:
        kinds.save_checks(conn, dearest["id"], {f"check_{c}": date.today().isoformat() for c in kinds.CHECK_IDS})
    try:
        with db.connect() as conn:
            found = search.discover(conn, ["urban"], "all", Stay(CI, CI + timedelta(days=2), 2), dated=False)
        first = found["groups"][0]["places"][0]
        assert first["hotel"]["id"] == dearest["id"] and first["verification"]["full"]
    finally:
        with db.connect() as conn:
            conn.run("DELETE FROM hotel_checks WHERE hotel_id = :h", {"h": dearest["id"]})


def test_admin_records_the_five_checks_and_travellers_see_their_dates(admin):
    hotel = _live()[0]
    day = (date.today() - timedelta(days=3)).isoformat()
    form = {"category": "heritage", "good_for": ["family", "culture"], "practice_people": "5 staff from the town (seen)",
            "practice_place": "Solar water (seen)", "practice_money": "Buys from local farms (receipts seen)"}
    form.update({f"check_{c}": day for c in kinds.CHECK_IDS})
    r = admin.post(f"/admin/approvals/{hotel['id']}/trust", data=form, follow_redirects=False)
    assert r.status_code == 303 and "decided=trust" in r.headers["location"]
    try:
        page = guest.get(hotel["path"]).text
        assert "5 of 5 checks" in page and "History &amp; heritage" in page and "Responsible practice" in page
        assert "Solar water (seen)" in page
        future = (date.today() + timedelta(days=2)).isoformat()
        bad = admin.post(f"/admin/approvals/{hotel['id']}/trust", data={**form, "check_identity": future},
                         follow_redirects=False)
        assert "trust-errors" in bad.headers["location"]  # a check can't be dated in the future
    finally:
        with db.connect() as conn:
            conn.run("DELETE FROM hotel_checks WHERE hotel_id = :h", {"h": hotel["id"]})
            conn.run("UPDATE hotels SET category = NULL, good_for = NULL, practice_people = NULL, practice_place = NULL, "
                     "practice_money = NULL WHERE id = :h", {"h": hotel["id"]})


def test_the_money_panel_shows_the_split_travellers_and_hosts_see():
    offer = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]
    page = guest.get(offer["hotel"]["path"], params=STAY).text
    assert "Where your money goes" in page and "Your host receives" in page and "Fichua’s fee" in page
    assert "It is not added to your price" in page


def test_ask_the_host_first_then_whatsapp_with_the_question_in_their_language():
    offer = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]
    hotel_id = offer["hotel"]["id"]
    with db.connect() as conn:
        before = conn.scalar("SELECT phone FROM hotels WHERE id = :id", {"id": hotel_id})
        conn.run("UPDATE hotels SET phone = '0788 123 456' WHERE id = :id", {"id": hotel_id})
    try:
        ask = guest.get(f"/hotels/{hotel_id}/ask", params=STAY).text
        assert "Fichua handles the booking" in ask and "Nothing is booked yet." in ask
        fr = TestClient(app)
        r = fr.post(f"/hotels/{hotel_id}/ask?lang=fr", data={**STAY, "question": "Avez-vous un parking ?"},
                    follow_redirects=False)
        text = unquote(r.headers["location"])
        assert "sur Fichua" in text and "Avez-vous un parking ?" in text and re.search(r"Réf\. ASK-\w{6}$", text)
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET phone = :p WHERE id = :id", {"p": before, "id": hotel_id})


def test_english_and_french_with_a_remembered_choice():
    assert "Quel type de séjour cherchez-vous" in guest.get("/?lang=fr").text
    browser = TestClient(app)
    r = browser.get("/lang/fr", params={"next": "/where?kind=water"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/where?kind=water" and "lang=fr" in r.headers["set-cookie"]
    browser.cookies.set("lang", "fr")
    assert "Où et quand" in browser.get("/where", params={"kind": "water"}).text
    assert "Voir les lieux correspondants" in browser.get("/").text
    assert browser.get("/lang/fr", params={"next": "https://evil.example"}, follow_redirects=False).headers["location"] == "/"
    # Accept-Language decides for a first visit; the partner portal stays in English for now.
    assert "Quel type de séjour" in TestClient(app, headers={"Accept-Language": "fr-FR,fr;q=0.9"}).get("/").text
    assert 'lang="en"' in browser.get("/partners").text


def test_countries_line_and_mit_line_on_the_home_page():
    home = guest.get("/").text
    assert "Starting in Rwanda, Benin and Côte d’Ivoire" in home and "Built at MIT, for Africa and the World" in home


def test_owners_pick_a_kind_and_see_their_home(admin):
    code = "KINDS-HOME"
    assert admin.post("/admin/codes", data={"code": code, "plan": "manager", "max_uses": "1"},
                      follow_redirects=False).status_code == 303
    p = TestClient(app)
    p.post("/partners/join", data={"code": code, "name": "Mariette", "hotel_name": "Maison Test", "email": "kinds@example.com",
                                   "phone": "0197 000 111", "password": "secret123"})
    form = {"name": "Maison Test", "property_type": "Guesthouse", "country": "Benin", "city": "Ouidah", "address": "Rue 1",
            "lat": "6.36", "lng": "2.08", "phone": "0197 000 111", "whatsapp": "0197 000 111", "category": "heritage",
            "category_also": "urban", "good_for_sent": "1", "good_for": ["family", "culture", "slow", "work"]}
    p.post("/partners/hotel", data=form)
    with db.connect() as conn:
        row = conn.one("SELECT id, category, category_also, good_for FROM hotels WHERE email = 'kinds@example.com' "
                       "OR name = 'Maison Test'", {})
    assert row["category"] == "heritage" and row["category_also"] == "urban"
    assert row["good_for"].split(",") == ["family", "culture", "slow"]  # three at most
    home = p.get("/partners/home").text
    assert "so far" in home and "Questions from travellers" in home and "Every Fichua booking is paid on Fichua" in home

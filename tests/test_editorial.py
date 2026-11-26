"""Persona-led redesign: no fake social proof, the rules beside the price, 'Ask the hotel' with a reference."""
import json
import re
from datetime import date, timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import catalog, kinds, policies

guest = TestClient(app)
CI = date.today() + timedelta(days=30)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat(), "guests": 2}


def _offer(city="Kigali"):
    return guest.get("/api/search", params={"destination": city, **STAY}).json()["results"][0]


def test_no_generated_ratings_or_pressure():
    offer = _offer()
    assert "guest_rating" not in offer["hotel"] and "review_count" not in offer["hotel"]
    results = guest.get("/search", params={"destination": "Kigali", **STAY}).text
    page = guest.get(f"/hotels/{offer['hotel']['id']}", params=STAY).text
    for html in (results, page):
        assert "Top rated" not in html and "Guest rating" not in html
        assert not re.search(r"Only \d+ left", html)
        assert not re.search(r"(Exceptional|Excellent|Very good|Pleasant)</strong>", html)
    assert "Free cancellation on most rooms" not in guest.get("/").text


def test_cancellation_rules_beside_the_price():
    today = date(2026, 11, 21)
    flexible = policies.timeline("flexible", True, date(2026, 12, 20), 147.0, today=today)
    assert [p["kind"] for p in flexible] == ["free", "none"]
    assert flexible[0]["until"] == date(2026, 12, 19) and flexible[0]["refund"] == 147.0
    assert flexible[1]["starts"] == date(2026, 12, 20) and flexible[1]["refund"] == 0
    assert [p["kind"] for p in policies.timeline("strict", True, date(2026, 12, 20), 147.0, today=today)] == ["none"]
    # Too close to check-in for free cancellation: one part, "No refund".
    assert [p["kind"] for p in policies.timeline("moderate", True, date(2026, 11, 23), 90.0, today=today)] == ["none"]
    page = guest.get(f"/hotels/{_offer()['hotel']['id']}", params=STAY).text
    assert "If you cancel" in page and ("full refund of $" in page or "No refund" in page)


def test_ask_the_hotel_records_an_enquiry_with_a_reference():
    hotel_id = _offer()["hotel"]["id"]
    with db.connect() as conn:
        before = conn.scalar("SELECT phone FROM hotels WHERE id = :id", {"id": hotel_id})
        conn.run("UPDATE hotels SET phone = :p WHERE id = :id", {"p": "0788 123 456", "id": hotel_id})
    try:
        page = guest.get(f"/hotels/{hotel_id}", params=STAY).text
        assert f'href="/hotels/{hotel_id}/ask?' in page and "Ask the host" in page
        # The ask page shows the message first and says booking stays on Fichua (no codes from hosts).
        ask = guest.get(f"/hotels/{hotel_id}/ask", params=STAY).text
        assert f'action="/hotels/{hotel_id}/ask"' in ask and "Hosts never take payment outside Fichua" in ask
        r = guest.post(f"/hotels/{hotel_id}/ask", data=STAY, follow_redirects=False)
        assert r.status_code == 303
        link = r.headers["location"]
        assert link.startswith("https://wa.me/250788123456?text=") and "+" not in link.split("?", 1)[1]
        text = unquote(link)
        ref = re.search(r"Ref (ASK-[A-Z2-9]{6})$", text).group(1)
        assert "on Fichua" in text and "2 guests" in text
        with db.connect() as conn:
            e = conn.one("SELECT * FROM enquiries WHERE reference = :r", {"r": ref})
        assert e["hotel_id"] == hotel_id and e["guests"] == 2 and str(e["check_in"])[:10] == STAY["check_in"]
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET phone = :p WHERE id = :id", {"p": before, "id": hotel_id})
    # No reception number: no button, and the route refuses.
    if not before:
        assert f"/hotels/{hotel_id}/ask" not in guest.get(f"/hotels/{hotel_id}", params=STAY).text
        assert guest.post(f"/hotels/{hotel_id}/ask", data=STAY, follow_redirects=False).status_code == 404


def test_pages_are_readable_by_search_engines_and_assistants():
    hotel_id = _offer()["hotel"]["id"]
    page = guest.get(f"/hotels/{hotel_id}", params=STAY).text
    data = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', page, re.S).group(1))
    assert data["@context"] == "https://schema.org"
    assert data["address"]["addressCountry"] and "aggregateRating" not in data and "review" not in data
    path = _offer()["hotel"]["path"]
    assert data["url"] == f"http://testserver{path}"
    assert f'rel="canonical" href="http://testserver{path}"' in page and 'property="og:title"' in page
    sitemap = guest.get("/sitemap.xml")
    assert sitemap.headers["content-type"].startswith("application/xml") and f"{path}</loc>" in sitemap.text
    robots = guest.get("/robots.txt").text
    assert "Disallow: /admin" in robots and "Sitemap: http://testserver/sitemap.xml" in robots


def test_readable_hotel_addresses():
    assert catalog.slugify("Hôtel Lagune Bleue") == "hotel-lagune-bleue"
    assert catalog.slugify("Côte d'Ivoire") == "cote-d-ivoire"
    hotel = _offer()["hotel"]
    path = hotel["path"]
    assert re.fullmatch(r"/stays/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+", path) and path.endswith(catalog.slugify(hotel["id"]))
    # Old links and admin links move to the readable address, dates kept.
    r = guest.get(f"/hotels/{hotel['id']}", params=STAY, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].startswith(path + "?") and STAY["check_in"] in r.headers["location"]
    page = guest.get(path, params=STAY)
    assert page.status_code == 200 and "Choose your room" in page.text and f'action="{path}"' in page.text
    # A wrong city or an old name in the link still finds the hotel by its id, and redirects.
    old = f"/stays/{path.split('/')[2]}/somewhere/old-name-{catalog.slugify(hotel['id'])}"
    moved = guest.get(old, follow_redirects=False)
    assert moved.status_code == 301 and moved.headers["location"] == path
    assert guest.get("/stays/rwanda/kigali/no-such-hotel-xyz-999").status_code == 404
    results = guest.get("/search", params={"destination": "Kigali", **STAY}).text
    assert f'href="{path}?' in results


def test_home_starts_with_the_five_kinds_of_place():  # Brief 3 v3
    home = guest.get("/").text
    assert "What kind of stay are you looking for?" in home
    for k in kinds.KINDS:
        assert f'name="kind" value="{k["id"]}"' in home
    assert "Starting in Rwanda, Benin and Côte d’Ivoire" in home and "Built at MIT, for Africa first and the World" in home
    where = guest.get("/where", params={"kind": ["urban", "water"]}).text
    assert 'value="all"' in where and "Show me without dates" in where
    results = guest.get("/search", params={"kind": "urban", "dates": "any"}).text
    assert "Ordered by fit and verification" in results and "From $" in results

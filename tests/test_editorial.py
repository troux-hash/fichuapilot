"""Persona-led redesign: no fake social proof, the rules beside the price, 'Ask the hotel' with a reference."""
import json
import re
from datetime import date, timedelta
from urllib.parse import unquote

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import policies, ways_in

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
        assert f'action="/hotels/{hotel_id}/ask"' in page and "Ask the hotel on WhatsApp" in page
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
        assert "Ask the hotel on WhatsApp" not in guest.get(f"/hotels/{hotel_id}", params=STAY).text
        assert guest.post(f"/hotels/{hotel_id}/ask", data=STAY, follow_redirects=False).status_code == 404


def test_pages_are_readable_by_search_engines_and_assistants():
    hotel_id = _offer()["hotel"]["id"]
    page = guest.get(f"/hotels/{hotel_id}", params=STAY).text
    data = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', page, re.S).group(1))
    assert data["@context"] == "https://schema.org" and data["url"].endswith(f"/hotels/{hotel_id}")
    assert data["address"]["addressCountry"] and "aggregateRating" not in data and "review" not in data
    assert f'rel="canonical" href="http://testserver/hotels/{hotel_id}"' in page and 'property="og:title"' in page
    sitemap = guest.get("/sitemap.xml")
    assert sitemap.headers["content-type"].startswith("application/xml") and f"/hotels/{hotel_id}</loc>" in sitemap.text
    robots = guest.get("/robots.txt").text
    assert "Disallow: /admin" in robots and "Sitemap: http://testserver/sitemap.xml" in robots


def test_ways_in_lead_to_searches_that_exist():
    home = guest.get("/").text
    assert "What brings you?" in home
    links = re.findall(r'<a class="way" href="/search\?([^"]+)"', home)
    assert links, "expected trip-purpose ways in on the home page"
    for query in links:
        assert guest.get("/search?" + query.replace("&amp;", "&")).status_code == 200
    assert all(w["params"].get("destination") != "Atlantis" for w in ways_in.available([{"city": "Kigali"}]))

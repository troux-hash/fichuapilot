"""Host profiles shown only with consent, invoice details and receipts, and the 'Show at the door' card."""
import base64
import re
from datetime import date, timedelta

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app

guest = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"portrait"
CI = date.today() + timedelta(days=40)
STAY = {"check_in": CI.isoformat(), "check_out": (CI + timedelta(days=2)).isoformat()}


def _join(admin, code: str, email: str, hotel_name: str) -> TestClient:
    r = admin.post("/admin/codes", data={"code": code, "plan": "manager", "max_uses": "1"}, follow_redirects=False)
    assert r.status_code == 303
    partner = TestClient(app)
    r = partner.post("/partners/join", data={"code": code, "name": "Eric", "hotel_name": hotel_name, "email": email,
                                             "phone": "0788 000 555", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303
    return partner


def _offer(city="Kigali"):
    return guest.get("/api/search", params={"destination": city, **STAY, "guests": 2}).json()["results"][0]


def test_partner_saves_a_host_profile_shown_only_with_consent(admin):
    partner = _join(admin, "HOST-TEST", "host@example.com", "Host Lodge")
    assert "Who guests will meet" in partner.get("/partners/host").text
    profile = {"host_name": "Eric", "host_role": "Owner", "host_languages": ["English", "Kinyarwanda", "Klingon"],
               "host_welcome": "I grew up here.   My brother and I built the lodge in 2011."}
    assert partner.post("/partners/host", data=profile, follow_redirects=False).status_code == 303
    with db.connect() as conn:
        h = conn.one("SELECT * FROM hotels WHERE email = :e", {"e": "host@example.com"})
    assert h["host_name"] == "Eric" and h["host_languages"] == "English, Kinyarwanda" and h["host_consent_at"] is None
    assert h["host_welcome"] == "I grew up here. My brother and I built the lodge in 2011."
    assert "Hidden. Tick the box" in partner.get("/partners/host").text

    no_name = partner.post("/partners/host", data={**profile, "host_name": "", "host_consent": "1"})
    assert no_name.status_code == 422 and "first name guests will see" in no_name.text

    for _ in range(2):  # a new portrait replaces the old one
        r = partner.post("/partners/host", data={**profile, "host_consent": "1"},
                         files=[("files", ("me.png", PNG, "image/png")), ("thumbs", ("me.jpg", JPEG, "image/jpeg"))],
                         follow_redirects=False)
        assert r.status_code == 303
    with db.connect() as conn:
        h = conn.one("SELECT * FROM hotels WHERE email = :e", {"e": "host@example.com"})
        photos = conn.all("SELECT id FROM media WHERE owner_type = 'host' AND owner_id = :h", {"h": h["id"]})
    assert h["host_consent_at"] and len(photos) == 1
    page = partner.get("/partners/host").text
    assert 'class="host"' in page and "Your host" in page and f"/media/{photos[0]['id']}" in page
    assert partner.post("/partners/host/photo/delete", follow_redirects=False).status_code == 303
    with db.connect() as conn:
        assert not conn.scalar("SELECT COUNT(*) FROM media WHERE owner_type = 'host' AND owner_id = :h", {"h": h["id"]})


def test_guests_meet_the_host_only_with_consent():
    offer = _offer()
    hotel_id = offer["hotel"]["id"]
    with db.connect() as conn:
        conn.run("UPDATE hotels SET host_name = 'Divine', host_role = 'Owner', host_languages = 'English, French', "
                 "host_welcome = 'The art in the lobby changes every month.', host_consent_at = CURRENT_TIMESTAMP "
                 "WHERE id = :id", {"id": hotel_id})
    try:
        page = guest.get(offer["hotel"]["path"], params={**STAY, "guests": 2}).text
        assert "Your host" in page and "Divine" in page and "The art in the lobby changes every month." in page
        results = guest.get("/search", params={"destination": "Kigali", **STAY, "guests": 2}).text
        assert "With Divine · English, French" in results
        with db.connect() as conn:
            conn.run("UPDATE hotels SET host_consent_at = NULL WHERE id = :id", {"id": hotel_id})
        hidden = guest.get(offer["hotel"]["path"], params={**STAY, "guests": 2}).text
        assert "Your host" not in hidden and "Divine" not in hidden
    finally:
        with db.connect() as conn:
            conn.run("UPDATE hotels SET host_name = NULL, host_role = NULL, host_languages = NULL, host_welcome = NULL, "
                     "host_consent_at = NULL WHERE id = :id", {"id": hotel_id})


def _book(offer, **extra):
    form = {"room": offer["room"]["id"], **STAY, "guests": 2, "guest_name": "Sarah Okafor",
            "guest_email": "sarah@example.com", "guest_phone": "+234 803 000 1111", "guest_language": "en", **extra}
    return guest.post("/book", data=form, follow_redirects=False)


def test_invoice_details_receipt_and_the_door_card():
    offer = _offer()
    hotel_id = offer["hotel"]["id"]
    missing = _book(offer, invoice_tax_id="TIN-123")
    assert missing.status_code == 422 and "company name for the invoice" in missing.text

    r = _book(offer, invoice_company="Okafor Consulting Ltd", invoice_tax_id="TIN-123",
              invoice_address="12 Marina Road, Lagos", invoice_reference="PO-77")
    assert r.status_code == 303
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", r.headers["location"]).groups()
    # Before payment: no receipt and no door card.
    assert guest.get(f"/bookings/{ref}/receipt", params={"t": token}).status_code == 404
    assert guest.get(f"/bookings/{ref}/door", params={"t": token}).status_code == 404
    assert guest.post(f"/pay/{ref}", data={"t": token}, follow_redirects=False).status_code == 303
    with db.connect() as conn:
        b = conn.one("SELECT * FROM bookings WHERE reference = :r", {"r": ref})
        conn.run("UPDATE hotels SET legal_name = 'Kigali Hills Ltd', tax_id = 'TIN-999' WHERE id = :id", {"id": hotel_id})
    assert (b["invoice_company"], b["invoice_tax_id"], b["invoice_reference"]) == ("Okafor Consulting Ltd", "TIN-123", "PO-77")

    page = guest.get(f"/bookings/{ref}", params={"t": token}).text
    assert "Invoice for:" in page and "Okafor Consulting Ltd" in page and f"/bookings/{ref}/door?t=" in page
    receipt = guest.get(f"/bookings/{ref}/receipt", params={"t": token})
    assert receipt.status_code == 200 and "Payment receipt" in receipt.text and "Okafor Consulting Ltd" in receipt.text
    assert "Tax number TIN-123" in receipt.text and "Kigali Hills Ltd" in receipt.text and "Tax number TIN-999" in receipt.text
    assert 'name="robots" content="noindex"' in receipt.text
    door = guest.get(f"/bookings/{ref}/door", params={"t": token}).text
    assert ref in door and "Paid in full" in door and "Sarah Okafor" in door
    assert guest.get(f"/bookings/{ref}/door", params={"t": "wrong"}).status_code == 404

    with db.connect() as conn:  # a cancelled booking's card says so, whatever its rate allowed
        conn.run("UPDATE bookings SET status = 'cancelled' WHERE reference = :r", {"r": ref})
    void = guest.get(f"/bookings/{ref}/door", params={"t": token}).text
    assert "not valid for a stay" in void and "Paid in full" not in void
    with db.connect() as conn:
        conn.run("UPDATE hotels SET legal_name = NULL, tax_id = NULL WHERE id = :id", {"id": hotel_id})

"""Guest side: search → hotel → checkout → full payment → commission, payout, WhatsApp → cancel/refund."""
import hashlib
import hmac
import io
import json
import re
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from fichua.db import db, utcnow
from fichua.main import app
from fichua.services import bookings, catalog, currency, dates, payments
from fichua.services.importer import template_workbook

CI = date.today() + timedelta(days=12)
CO = CI + timedelta(days=2)
STAY = {"check_in": CI.isoformat(), "check_out": CO.isoformat()}
guest = TestClient(app)


def _book_and_pay(destination="Kigali", guests=2, phone="+250 788 000 111"):
    offer = guest.get("/api/search", params={"destination": destination, **STAY, "guests": guests,
                                             "sort": "price"}).json()["results"][0]
    form = {"room": offer["room"]["id"], **STAY, "guests": guests, "guest_name": "Ada Lovelace",
            "guest_email": "ada@example.com", "guest_phone": phone, "guest_language": "en"}
    r = guest.post("/book", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/pay/"), r.text[-800:]
    pay_url = r.headers["location"]
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", pay_url).groups()
    assert guest.get(pay_url).status_code == 200
    r = guest.post(f"/pay/{ref}", data={"t": token}, follow_redirects=False)
    assert r.status_code == 303
    return offer, ref, token, r.headers["location"]


def test_admin_requires_login():
    anon = TestClient(app)
    assert anon.get("/admin", follow_redirects=False).status_code == 303
    assert anon.post("/admin/login", data={"password": "nope"}).status_code == 401


def test_bad_upload_reports_rows_and_saves_nothing(admin):
    wb = template_workbook({
        "Hotels": [["BAD-1", "", "Bad Hotel", "Nowhere", "", "", "", "", 9]],
        "Rooms": [["BAD-1-STD", "MISSING", "Room", "two"]],
    })
    r = admin.post("/admin/upload", files={"file": ("bad.xlsx", io.BytesIO(wb))})
    assert r.status_code == 422 and "Rooms row 2" in r.text and "Nothing was imported" in r.text
    assert "Nowhere" not in guest.get("/api/destinations").text


def test_search_new_markets_in_usd_with_local_currency():
    for city in ("Kigali", "Cotonou", "Abidjan"):
        data = guest.get("/api/search", params={"destination": city, **STAY, "guests": 2}).json()
        assert data["results"], f"no availability in {city}"
        first = data["results"][0]
        assert first["total_price"] == pytest.approx(sum([first["per_night"]] * 2), abs=0.02)
    page = guest.get("/search", params={"destination": "Kigali", **STAY})
    assert page.status_code == 200 and "RWF" in page.text and "$" in page.text
    page = guest.get("/search", params={"destination": "Cotonou", **STAY})
    assert "FCFA" in page.text
    four = guest.get("/api/search", params={"destination": "Abidjan", **STAY, "guests": 4}).json()
    assert all(o["room"]["max_guests"] >= 4 for o in four["results"])


def test_weekend_and_season_prices():
    friday = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 + 7)
    with db.connect() as conn:
        room = conn.one("SELECT * FROM room_types WHERE id = 'KGL-001-STA'")
        weekday = catalog.availability(conn, dates.Stay(friday - timedelta(days=3), friday - timedelta(days=2), 2),
                                       room_type_id=room["id"])[0]
        weekend = catalog.availability(conn, dates.Stay(friday, friday + timedelta(days=1), 2), room_type_id=room["id"])[0]
    assert weekday["total_price"] == room["base_price"]
    assert weekend["total_price"] == room["weekend_price"]


def test_pages_render():
    home = guest.get("/").text
    assert "What kind of stay are you looking for?" in home and "We handle the booking" in home
    hotel_id = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]["hotel"]["id"]
    r = guest.get(f"/hotels/{hotel_id}", params=STAY)
    assert r.status_code == 200 and "Choose your room" in r.text
    assert guest.get("/hotels/NOPE").status_code == 404
    assert guest.get("/partners").status_code == 200


def test_checkout_requires_whatsapp_number():
    offer = guest.get("/api/search", params={"destination": "Kigali", **STAY}).json()["results"][0]
    r = guest.post("/book", data={"room": offer["room"]["id"], **STAY, "guests": 2, "guest_name": "Ada",
                                  "guest_email": "ada@example.com", "guest_phone": ""})
    assert r.status_code == 422 and "WhatsApp number" in r.text


def test_full_payment_commission_payout_and_messages():
    offer, ref, token, location = _book_and_pay("Kigali")
    page = guest.get(location)
    assert "Paid · confirmed" in page.text and "You’re booked through Fichua." in page.text and "is expecting you on" in page.text
    with db.connect() as conn:
        b = conn.one("SELECT * FROM bookings WHERE reference = :r", {"r": ref})
        payout = conn.one("SELECT * FROM payouts WHERE booking_id = :b", {"b": b["id"]})
        msgs = conn.all("SELECT role, status, body FROM messages WHERE booking_id = :b", {"b": b["id"]})
        payment = conn.one("SELECT * FROM payments WHERE booking_id = :b", {"b": b["id"]})
    assert b["status"] == "confirmed" and b["payment_status"] == "paid"
    assert b["commission_pct"] == 7
    assert b["commission_amount"] == pytest.approx(round(b["total_price"] * 0.07, 2))
    assert b["payout_amount"] == pytest.approx(b["total_price"] - b["commission_amount"])
    assert payout["status"] == "sent" and payout["method"] == "test"   # default timing: right after payment
    assert payment["provider"] == "test" and payment["status"] == "paid"
    assert sorted(m["role"] for m in msgs) == ["admin", "guest", "hotel"]
    guest_msg = next(m for m in msgs if m["role"] == "guest")
    assert "Paid in full" in guest_msg["body"] and "RWF" in guest_msg["body"]
    hotel_msg = next(m for m in msgs if m["role"] == "hotel")
    assert "Fichua commission: 7% · $" in hotel_msg["body"]
    assert all(m["status"] == "not_sent" for m in msgs)  # WhatsApp not connected in tests


def test_cancel_refunds_and_reverses_payout():
    _, ref, token, location = _book_and_pay("Cotonou")
    page = guest.get(location)
    if "Cancel and refund" not in page.text:
        pytest.skip("cheapest Cotonou room is non-refundable in this seed")
    r = guest.post(f"/bookings/{ref}/cancel", data={"t": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("&cancelled=1")  # reload-safe (FIX-07)
    page = guest.get(r.headers["location"])
    assert "refunded" in page.text and "5 to 10 working days" in page.text
    with db.connect() as conn:
        b = conn.one("SELECT * FROM bookings WHERE reference = :r", {"r": ref})
        payout = conn.one("SELECT status FROM payouts WHERE booking_id = :b", {"b": b["id"]})
        kinds = [m["kind"] for m in conn.all("SELECT kind FROM messages WHERE booking_id = :b", {"b": b["id"]})]
    assert b["status"] == "cancelled" and b["payment_status"] == "refunded"
    assert payout["status"] == "cancelled"
    assert kinds.count("booking_cancelled") == 3


def test_unpaid_checkout_holds_room_until_expiry():
    stay = dates.Stay(CI + timedelta(days=40), CI + timedelta(days=41), 2)
    with db.connect() as conn:
        room = conn.one("SELECT * FROM room_types WHERE id = 'MUS-004-FAM'")
        before = catalog.availability(conn, stay, room_type_id=room["id"])[0]["rooms_left"]
        holds = [bookings.create_booking(conn, stay, room["id"], guest_name="Hold", guest_email="h@example.com",
                                         guest_phone="+250788000222") for _ in range(before)]
        assert catalog.availability(conn, stay, room_type_id=room["id"]) == []  # all held
        conn.run("UPDATE bookings SET hold_expires_at = :t WHERE id = :id",
                 {"t": utcnow() - timedelta(minutes=1), "id": holds[0]["id"]})
        assert catalog.availability(conn, stay, room_type_id=room["id"])[0]["rooms_left"] == 1


def test_manage_lookup():
    _, ref, token, _ = _book_and_pay("Abidjan")
    found = guest.post("/manage", data={"reference": ref.lower(), "email": "ADA@example.com"}, follow_redirects=False)
    assert found.status_code == 303 and ref in found.headers["location"]
    assert guest.post("/manage", data={"reference": ref, "email": "x@y.z"}).status_code == 404


def test_template_download(admin):
    wb = load_workbook(io.BytesIO(admin.get("/admin/template.xlsx").content))
    assert {"Instructions", "Hotels", "Rooms", "Rates"} <= set(wb.sheetnames)
    assert "base_price" in [c.value for c in wb["Rooms"][1]]


def test_stripe_webhook_signature():
    secret, body = "whsec_test", json.dumps({"id": "evt_1"}).encode()
    t = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    assert payments.verify_webhook(body, f"t={t},v1={sig}", secret)
    assert not payments.verify_webhook(body + b"x", f"t={t},v1={sig}", secret)
    assert not payments.verify_webhook(body, f"t={int(t) - 1000},v1={sig}", secret)
    flat = dict(payments._flatten({"line_items": [{"price_data": {"unit_amount": 100}}], "metadata": {"a": "b"}}))
    assert flat == {"line_items[0][price_data][unit_amount]": "100", "metadata[a]": "b"}


def test_local_currency_text():
    rates = {"rate_RWF": "1450", "rate_XOF": "565"}
    assert currency.local_text(100, "Rwanda", rates) == "≈ 145,000 RWF"
    assert currency.local_text(100, "Benin", rates) == "≈ 56 500 FCFA"
    assert currency.local_text(100, "Portugal", rates) == ""


def test_friendly_error_pages():
    page = guest.get("/this-page-does-not-exist")
    assert page.status_code == 404 and "We couldn’t find that page" in page.text  # FIX-08
    api = guest.get("/api/nope")
    assert api.status_code == 404 and api.json() == {"detail": "Not Found"}
    wrong_method = guest.get("/bookings/FCH-XXXXXX/cancel")
    assert wrong_method.status_code == 405 and "only works from a button" in wrong_method.text
    assert guest.get("/favicon.ico", follow_redirects=False).status_code == 301


def test_big_group_search_explains_room_size():
    page = guest.get("/search", params={"destination": "Kigali", **STAY, "guests": 12})
    assert "sleeps 12 guests" in page.text and "Search for" in page.text  # FIX-15

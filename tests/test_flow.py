"""End-to-end: admin uploads Excel → guest searches, filters, books, manages, cancels."""
import io
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["ADMIN_PASSWORD"] = "test-pass"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from fichua.main import app  # noqa: E402
from fichua.services.importer import template_workbook  # noqa: E402
from scripts.generate_synthetic_data import build  # noqa: E402

client = TestClient(app)
CI = date.today() + timedelta(days=10)
CO = CI + timedelta(days=2)
STAY = {"check_in": CI.isoformat(), "check_out": CO.isoformat()}


def _login():
    r = client.post("/admin/login", data={"password": "test-pass"}, follow_redirects=False)
    assert r.status_code == 303


def _upload(content: bytes, name="hotels.xlsx"):
    return client.post("/admin/upload", files={"file": (name, io.BytesIO(content))})


@pytest.fixture(scope="module", autouse=True)
def seeded():
    _login()
    data = build(days=60)["Savanna Hotels Group"]
    r = _upload(template_workbook(data))
    assert r.status_code == 200 and "Imported" in r.text, r.text[-2000:]


def test_admin_requires_login():
    anon = TestClient(app)
    assert anon.get("/admin", follow_redirects=False).status_code == 303
    assert anon.post("/admin/login", data={"password": "nope"}).status_code == 401


def test_bad_upload_reports_rows_and_saves_nothing():
    wb = template_workbook({
        "Hotels": [["BAD-1", "", "Bad Hotel", "Nowhere", "", "", "", "", 9, "", "", "", "", "", "", "", "", "", ""]],
        "Rooms": [["BAD-1-STD", "MISSING", "Room", "two"]],
    })
    r = _upload(wb)
    assert r.status_code == 422
    assert "Rooms row 2" in r.text and "Nothing was imported" in r.text
    assert "Nowhere" not in client.get("/api/destinations").text


def test_search_and_filters():
    data = client.get("/api/search", params={"destination": "nairobi", **STAY, "guests": 2}).json()
    assert data["results"], "expected availability in Nairobi"
    assert all(o["hotel"]["city"] == "Nairobi" for o in data["results"])
    first = data["results"][0]
    assert first["total_price"] == pytest.approx(first["per_night"] * 2, abs=0.02)

    cheap = client.get("/api/search", params={"destination": "nairobi", **STAY, "sort": "price"}).json()
    prices = [o["per_night"] for o in cheap["results"]]
    assert prices == sorted(prices)

    four_plus = client.get("/api/search", params={"destination": "nairobi", **STAY, "guests": 4}).json()
    assert all(o["room"]["max_guests"] >= 4 for o in four_plus["results"])

    page = client.get("/search", params={"destination": "Mombasa", **STAY, "free_cancellation": "1"})
    assert page.status_code == 200 and "stays in Mombasa" in page.text


def test_pages_render():
    assert "found in seconds" in client.get("/").text
    hotel_id = client.get("/api/search", params={"destination": "nairobi", **STAY}).json()["results"][0]["hotel"]["id"]
    r = client.get(f"/hotels/{hotel_id}", params=STAY)
    assert r.status_code == 200 and "Choose your room" in r.text
    assert client.get("/hotels/NOPE").status_code == 404


def test_book_manage_cancel_and_inventory():
    offer = client.get("/api/search", params={"destination": "mombasa", **STAY}).json()["results"][0]
    room = offer["room"]["id"]
    left = offer["rooms_left"]
    form = {"room": room, **STAY, "guests": 2, "guest_name": "Ada Lovelace",
            "guest_email": "ada@example.com", "guest_phone": "+254700000000"}

    assert client.get("/book", params={"room": room, **STAY, "guests": 2}).status_code == 200
    bad = client.post("/book", data={**form, "guest_email": "nope"})
    assert bad.status_code == 422 and "valid email" in bad.text

    refs = []
    for _ in range(left):
        r = client.post("/book", data=form, follow_redirects=False)
        assert r.status_code == 303
        refs.append(r.headers["location"])
    sold_out = client.post("/book", data=form)
    assert sold_out.status_code == 422 and "sold out" in sold_out.text

    page = client.get(refs[0])
    assert "You're going to Mombasa" in page.text
    ref = re.search(r"/bookings/(FCH-\w+)", refs[0]).group(1)

    found = client.post("/manage", data={"reference": ref.lower(), "email": "ADA@example.com"}, follow_redirects=False)
    assert found.status_code == 303 and ref in found.headers["location"]
    assert client.post("/manage", data={"reference": ref, "email": "x@y.z"}).status_code == 404

    token = re.search(r"t=([^&]+)", refs[0]).group(1)
    if "Cancel booking" in page.text:
        cancelled = client.post(f"/bookings/{ref}/cancel", data={"t": token})
        assert "has been cancelled" in cancelled.text
        again = client.post("/book", data=form, follow_redirects=False)
        assert again.status_code == 303, "cancelled night should be bookable again"

    admin = client.get("/admin/bookings")
    assert ref in admin.text


def test_template_download_and_samples():
    r = client.get("/admin/template.xlsx")
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Instructions", "Hotels", "Rooms", "Rates"} <= set(wb.sheetnames)

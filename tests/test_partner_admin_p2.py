"""Partner and admin P2 improvements from the 21 Nov QA test: sign-up errors in view (IMP-09), one-tap photo
upload (IMP-10), "we received it" and review alerts on submit (IMP-13), live-hotel actions (IMP-12),
hotel search and filters (IMP-14) and sending access codes on WhatsApp (IMP-15)."""
import base64
import json
import re
from urllib.parse import unquote

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"card copy"


def _code(admin, code: str) -> None:
    r = admin.post("/admin/codes", data={"code": code, "plan": "manager", "max_uses": "1"}, follow_redirects=False)
    assert r.status_code == 303


def _join(admin, code: str, email: str, hotel_name: str) -> TestClient:
    _code(admin, code)
    partner = TestClient(app)
    r = partner.post("/partners/join", data={"code": code, "name": "Aline", "hotel_name": hotel_name, "email": email,
                                             "phone": "0788 000 777", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303
    return partner


def _hotel_id(email: str) -> str:
    with db.connect() as conn:
        return conn.scalar("SELECT id FROM hotels WHERE email = :e", {"e": email})


def test_sign_up_errors_point_at_the_field(admin):  # IMP-09
    guest = TestClient(app)
    missing_name = guest.post("/partners/join", data={"code": "WHATEVER", "name": "", "hotel_name": "Lodge",
                                                      "email": "a@example.com", "phone": "+250788000000",
                                                      "password": "secret123"})
    assert missing_name.status_code == 422
    assert re.search(r'id="name"[^>]*data-error-focus', missing_name.text)
    bad_code = guest.post("/partners/join", data={"code": "NOPE-NOPE", "name": "Aline", "hotel_name": "Lodge",
                                                  "email": "a@example.com", "phone": "+250788000000",
                                                  "password": "secret123"})
    assert re.search(r'id="code"[^>]*data-error-focus', bad_code.text)
    assert bad_code.text.count("data-error-focus") == 1
    wrong = guest.post("/partners/login", data={"email": "nobody@example.com", "password": "nope"})
    assert wrong.status_code == 401 and re.search(r'id="login_password"[^>]*data-error-focus', wrong.text)
    with db.connect() as conn:
        conn.run("DELETE FROM login_attempts")


def test_photos_upload_in_one_tap_with_a_card_copy(admin):  # IMP-10 and IMP-07
    p = _join(admin, "PHOTO-TEST", "photos@example.com", "Photo Lodge")
    page = p.get("/partners/photos").text
    assert 'data-autoupload' in page and "Choose photos" in page and "js-hide" in page
    assert re.search(r'class="btn btn-secondary" href="/partners/rooms">Continue', page)  # 0 photos: not the main button
    r = p.post("/partners/photos", files=[("files", ("a.jpg", PNG, "image/png")), ("thumbs", ("a.jpg", JPEG, "image/jpeg")),
                                          ("files", ("b.png", PNG, "image/png")), ("thumbs", ("", b"", "application/octet-stream")),
                                          ("files", ("c.png", PNG, "image/png"))], follow_redirects=False)
    assert r.status_code == 303
    hotel_id = _hotel_id("photos@example.com")
    with db.connect() as conn:
        rows = conn.all("SELECT id, thumb FROM media WHERE owner_id = :h ORDER BY sort", {"h": hotel_id})
    assert len(rows) == 3 and rows[0]["thumb"] == JPEG and rows[1]["thumb"] is None and rows[2]["thumb"] is None
    assert TestClient(app).get(f"/media/{rows[0]['id']}?size=card").content == JPEG
    page = p.get("/partners/photos").text
    assert re.search(r'class="btn btn-primary" href="/partners/rooms">Continue', page)  # 3 photos: carry on


def _onboard(admin, code: str, email: str, name: str) -> tuple[TestClient, str]:
    p = _join(admin, code, email, name)
    hotel_id = _hotel_id(email)  # before the details step, which sets the bookings email
    p.post("/partners/hotel", data={"name": name, "property_type": "Hotel", "country": "Benin", "city": "Cotonou",
                                    "area": "Haie Vive", "address": "Rue 12", "lat": "6.3600", "lng": "2.4100",
                                    "phone": "01 97 00 00 11", "whatsapp": "01 97 00 00 11", "email": email})
    for i in range(3):
        p.post("/partners/photos", files={"files": (f"p{i}.png", PNG, "image/png")})
    p.post("/partners/rooms/new", data={"name": "Chambre Double", "room_kind": "Double", "total_rooms": "4",
                                        "max_guests": "2", "base_price": "70"})
    p.post("/partners/policies", data={"cancellation_policy": "moderate", "accept_terms": "1"})
    return p, hotel_id


def test_submit_tells_the_hotel_and_fichua(admin):  # IMP-13
    p, hotel_id = _onboard(admin, "SUBMIT-TEST", "submit@example.com", "Hôtel Haie Vive")
    assert p.post("/partners/submit", follow_redirects=False).status_code == 303
    assert p.post("/partners/submit", follow_redirects=False).status_code == 303  # pressed twice: one set of messages
    with db.connect() as conn:
        rows = conn.all("SELECT role, template, language, to_phone, params, body FROM messages "
                        "WHERE hotel_id = :h AND kind = 'hotel_submitted' ORDER BY role", {"h": hotel_id})
    assert [r["role"] for r in rows] == ["admin", "hotel"]
    admin_msg, hotel_msg = rows
    assert hotel_msg["template"] == "fichua_hotel_submitted" and hotel_msg["language"] == "fr"  # Benin: French
    assert hotel_msg["to_phone"] == "2290197000011" and hotel_msg["body"].startswith("Annonce reçue")
    assert admin_msg["template"] == "fichua_review_needed"
    assert json.loads(admin_msg["params"]) == ["Hôtel Haie Vive", hotel_id, "Cotonou, Benin", "Aline · 0788 000 777",
                                               "1 room type · 4 rooms"]


def test_live_hotel_page_offers_hide_and_commission(admin):  # IMP-12
    _, hotel_id = _onboard(admin, "LIVE-TEST", "live@example.com", "Live Lodge")
    with db.connect() as conn:
        conn.run("UPDATE hotels SET status = 'live', is_active = TRUE WHERE id = :h", {"h": hotel_id})
    page = admin.get(f"/admin/approvals/{hotel_id}").text
    assert "Live hotel" in page and "Hide from guests" in page and "Save commission" in page
    assert "Approve and publish" not in page and "Ask for changes" not in page
    url = f"/admin/approvals/{hotel_id}"
    bad = admin.post(url, data={"action": "commission", "commission": "55"}, follow_redirects=False)
    assert bad.headers["location"].endswith("decided=bad-commission")
    admin.post(url, data={"action": "commission", "commission": "9.5"})
    admin.post(url, data={"action": "hide"})
    with db.connect() as conn:
        h = conn.one("SELECT commission_pct, is_active, status FROM hotels WHERE id = :h", {"h": hotel_id})
    assert h["commission_pct"] == 9.5 and not h["is_active"] and h["status"] == "live"
    assert "Show to guests again" in admin.get(url).text
    assert admin.post(url, data={"action": "approve"}, follow_redirects=False).headers["location"] == url  # no re-approve
    admin.post(url, data={"action": "show"})
    with db.connect() as conn:
        assert conn.scalar("SELECT is_active FROM hotels WHERE id = :h", {"h": hotel_id})


def test_hotel_search_and_filters(admin):  # IMP-14
    everything = admin.get("/admin/hotels").text
    assert 'name="q"' in everything and "Any status" in everything
    by_name = admin.get("/admin/hotels", params={"q": "kigali hills"}).text
    assert "Kigali Hills Hotel" in by_name and "Abidjan" not in by_name and " of " in by_name
    by_id = admin.get("/admin/hotels", params={"q": "kgl-001"}).text
    assert "KGL-001" in by_id
    benin = admin.get("/admin/hotels", params={"country": "Benin"}).text
    assert "Cotonou" in benin and "Kigali" not in benin.split("<tbody>")[1]
    nothing = admin.get("/admin/hotels", params={"q": "no such hotel"}).text
    assert "No hotels match" in nothing
    pending = admin.get("/admin/hotels", params={"status": "draft"}).text.split("<tbody>")[1]
    assert "Onboarding" in pending and "Kigali Hills Hotel" not in pending


def test_send_access_codes_on_whatsapp(admin):  # IMP-15
    r = admin.post("/admin/codes", data={"code": "WA-INVITE", "plan": "manager", "max_uses": "1"}, follow_redirects=False)
    page = admin.get(r.headers["location"]).text
    links = re.findall(r'href="(https://wa\.me/\?text=[^"]+)"', page)
    assert links, "no Send on WhatsApp link"
    text = unquote(links[0].split("text=", 1)[1].replace("&amp;", "&"))
    assert "WA-INVITE" in text and "/partners?code=WA-INVITE" in text and "Votre code d’accès" in text
    admin.post("/admin/codes/WA-INVITE/toggle")  # disabled codes can't be sent
    rows = admin.get("/admin/codes").text.split("WA-INVITE</strong>")[1].split("</tr>")[0]
    assert "wa.me" not in rows

"""Bug from the third end-to-end check (25 Nov 2026): the live host refuses requests over 4.5 MB, so the partner pages
send photos in batches, and a new room's later batches go to the room the first one created (R3-B1)."""
import base64
import pathlib
import re

from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import partners

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JS = (pathlib.Path(__file__).resolve().parent.parent / "public" / "static" / "js" / "partners.js").read_text(encoding="utf-8")
ROOM = {"name": "Garden Twin", "room_kind": "Twin", "total_rooms": "2", "max_guests": "2", "base_price": "120"}


def _partner(admin, code: str, email: str) -> tuple[TestClient, str]:
    assert admin.post("/admin/codes", data={"code": code, "plan": "manager", "max_uses": "1"},
                      follow_redirects=False).status_code == 303
    p = TestClient(app)
    assert p.post("/partners/join", data={"code": code, "name": "Eric", "hotel_name": "Round Three Lodge", "email": email,
                                          "phone": "0788 000 333", "password": "secret123"},
                  follow_redirects=False).status_code == 303
    with db.connect() as conn:
        return p, conn.scalar("SELECT id FROM hotels WHERE email = :e", {"e": email})


def _photo(name: str):
    return [("files", (name, PNG, "image/png"))]


def test_a_new_room_takes_its_photos_in_batches(admin):
    p, hotel_id = _partner(admin, "ROUND3-ROOM", "round3room@example.com")
    first = p.post("/partners/rooms/new", data={**ROOM, "stay": "1"}, files=_photo("a.png"), follow_redirects=False)
    assert first.status_code == 303 and re.fullmatch(r"/partners/rooms/[\w-]+", first.headers["location"])
    middle = p.post(first.headers["location"], data={**ROOM, "stay": "1"}, files=_photo("b.png"), follow_redirects=False)
    assert middle.headers["location"] == first.headers["location"]
    last = p.post(first.headers["location"], data=ROOM, files=_photo("c.png"), follow_redirects=False)
    assert last.status_code == 303 and last.headers["location"] == "/partners/rooms"
    room_id = first.headers["location"].rsplit("/", 1)[1]
    with db.connect() as conn:
        assert conn.scalar("SELECT COUNT(*) FROM room_types WHERE hotel_id = :h", {"h": hotel_id}) == 1
        assert conn.scalar("SELECT COUNT(*) FROM media WHERE owner_type = 'room' AND owner_id = :r", {"r": room_id}) == 3


def test_room_errors_stop_the_batches(admin):
    p, hotel_id = _partner(admin, "ROUND3-ERR", "round3err@example.com")
    r = p.post("/partners/rooms/new", data={**ROOM, "name": "", "stay": "1"}, files=_photo("a.png"), follow_redirects=False)
    assert r.status_code == 422 and "Give the room type a name" in r.text  # the page shows it; no batch follows
    with db.connect() as conn:
        assert conn.scalar("SELECT COUNT(*) FROM room_types WHERE hotel_id = :h", {"h": hotel_id}) == 0


def test_batches_stay_under_the_hosting_limit():
    budget = float(re.search(r"REQUEST_BUDGET = ([\d.]+) \* 1024 \* 1024", JS).group(1))
    limit = int(re.search(r"PHOTO_LIMIT = (\d+) \* 1024 \* 1024", JS).group(1)) * 1024 * 1024
    assert budget <= 4  # Vercel refuses request bodies over 4.5 MB
    assert limit == partners.MAX_PHOTO_BYTES
    assert limit + partners.MAX_THUMB_BYTES < 4.5 * 1024 * 1024  # one photo and its small copy always fit

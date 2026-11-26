"""Photo uploads from owners' real phones (27 Nov 2026). On iPhones before iOS 16, choosing photos did nothing
(form.requestSubmit is missing there); phones also label files inconsistently. What a file is decides, not its label."""
import base64
from pathlib import Path

import pytest

from fichua.db import db
from fichua.services import partners

ROOT = Path(__file__).resolve().parent.parent
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + bytes(64)
WEBP = b"RIFF" + bytes(4) + b"WEBPVP8 " + bytes(32)
HEIC = bytes([0, 0, 0, 0x18]) + b"ftypheic" + bytes(32)


def _hotel(conn) -> str:
    return conn.scalar("SELECT id FROM hotels ORDER BY id LIMIT 1")


@pytest.mark.parametrize("data, label, stored", [
    (JPEG, "image/jpg", "image/jpeg"),                  # a label some Android browsers use
    (JPEG, "application/octet-stream", "image/jpeg"),   # a file shared from another app
    (PNG, "", "image/png"),                             # no label at all
    (WEBP, "image/webp", "image/webp"),
])
def test_real_photos_are_accepted_whatever_the_phone_calls_them(data, label, stored):
    with db.connect() as conn:
        media_id = partners.add_photo(conn, "hotel", _hotel(conn), data, label)
        assert conn.scalar("SELECT content_type FROM media WHERE id = :id", {"id": media_id}) == stored
        conn.run("DELETE FROM media WHERE id = :id", {"id": media_id})


def test_heic_and_other_files_get_a_clear_message():
    with db.connect() as conn:
        hotel = _hotel(conn)
        with pytest.raises(partners.PartnerError, match="HEIC"):
            partners.add_photo(conn, "hotel", hotel, HEIC, "image/heic")
        with pytest.raises(partners.PartnerError, match="JPG, PNG or WebP"):
            partners.add_photo(conn, "hotel", hotel, b"not a photo at all", "image/jpeg")


def test_choosing_photos_works_on_older_phones():
    script = (ROOT / "public/static/js/partners.js").read_text(encoding="utf-8")
    assert "function submitForm" in script and "input.form.requestSubmit()" not in script
    assert "is an iPhone HEIC photo" in script and "The upload stopped" in script  # never a silent failure
    page = (ROOT / "fichua/templates/partners/photos.html").read_text(encoding="utf-8")
    assert "js-hide" not in page and "Upload photos</button>" in page  # the button stays as a fallback
    for name in ("app.js", "partners.js"):  # older phones can't read ?. or ?? and would skip the whole file
        text = (ROOT / "public/static/js" / name).read_text(encoding="utf-8")
        assert "?." not in text and "??" not in text, name

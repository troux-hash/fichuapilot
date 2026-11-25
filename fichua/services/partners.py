"""Partner side: accounts, access codes, hotel onboarding, rooms, photos and the calendar."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import date, timedelta

from ..db import Connection, utcnow
from . import app_settings, catalog, kinds
from .currency import MARKETS, normalize_country
from .policies import POLICIES  # noqa: F401  (partners.POLICIES is used by the routes)

PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_THUMB_BYTES = 600 * 1024  # the ~800 px card copy the browser makes next to each photo
JPEG_START = bytes([0xFF, 0xD8, 0xFF])
MIN_HOTEL_PHOTOS = 3
ROOM_KINDS = ["Single", "Double", "Twin", "Suite", "Family", "Dormitory"]
PROPERTY_TYPES = ["Hotel", "Guesthouse", "Lodge", "Apartment", "Resort", "Boutique"]
AMENITIES = ["Free WiFi", "Pool", "Restaurant", "Bar", "Breakfast", "Free parking", "Airport shuttle", "Gym",
             "Spa", "Air conditioning", "Generator / backup power", "24h front desk", "Garden", "Rooftop terrace",
             "Beachfront", "Family rooms", "Laundry", "Conference room"]
ROOM_AMENITIES = ["Wi-Fi", "Hot shower", "TV", "Desk", "Air conditioning", "Fan", "Mosquito net", "Balcony",
                  "Minibar", "Safe", "Kettle", "Bathtub"]
HOST_ROLES = ["Owner", "Co-owner", "General manager", "Manager", "Host"]
HOST_LANGUAGES = ["English", "French", "Kinyarwanda", "Swahili", "Fon", "Yoruba", "Baoulé", "Dioula",
                  "Spanish", "German", "Italian", "Portuguese", "Arabic"]
MAX_HOST_WELCOME = 300
# Rough bounding boxes (lat_min, lat_max, lng_min, lng_max) for the "pin is in the country" check.
COUNTRY_BOXES = {
    "Rwanda": (-2.95, -1.0, 28.8, 30.95),
    "Benin": (6.1, 12.5, 0.7, 3.9),
    "Côte d'Ivoire": (4.3, 10.8, -8.7, -2.4),
}


class PartnerError(Exception):
    """A problem to show the partner; `field` names the form field to fix, when there is one."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


# --------------------------------------------------------------------------- accounts & codes

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", code or "").upper()


def create_code(conn: Connection, *, code: str = "", plan: str = "manager", free_until: date | None = None,
                max_uses: int = 1, expires_on: date | None = None, note: str = "") -> str:
    code = normalize_code(code) or "FICHUA-" + "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(6))
    if conn.scalar("SELECT COUNT(*) FROM access_codes WHERE code = :c", {"c": code}):
        raise PartnerError(f"The code {code} already exists.")
    conn.run("INSERT INTO access_codes (code, plan, free_until, max_uses, expires_on, note) "
             "VALUES (:c, :p, :f, :m, :e, :n)",
             {"c": code, "p": plan if plan in ("listing", "manager") else "manager", "f": free_until,
              "m": max(1, int(max_uses or 1)), "e": expires_on, "n": note.strip()[:200]})
    return code


def check_code(conn: Connection, code: str) -> dict:
    row = conn.one("SELECT * FROM access_codes WHERE code = :c", {"c": normalize_code(code)})
    if not row or not row["is_active"]:
        raise PartnerError("That code isn't valid. Check it with the Fichua team.", "code")
    if row["expires_on"] and row["expires_on"] < date.today().isoformat():
        raise PartnerError("That code has expired. Ask the Fichua team for a new one.", "code")
    if row["uses"] >= row["max_uses"]:
        raise PartnerError("That code has already been used. Ask the Fichua team for a new one.", "code")
    return row


def join(conn: Connection, *, code: str, name: str, hotel_name: str, email: str, phone: str,
         password: str) -> dict:
    errors = []  # (field, message), in the order the form shows them
    if len(name.strip()) < 2:
        errors.append(("name", "Enter your name."))
    if len(hotel_name.strip()) < 2:
        errors.append(("hotel_name", "Enter your hotel's name."))
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        errors.append(("email", "Enter a valid email address."))
    if len(re.sub(r"\D", "", phone)) < 8:
        errors.append(("phone", "Enter your WhatsApp number with the country code."))
    if len(password) < 8:
        errors.append(("password", "Choose a password of at least 8 characters."))
    if errors:
        raise PartnerError(" ".join(message for _, message in errors), errors[0][0])
    access = check_code(conn, code)
    email = email.strip().lower()
    if conn.scalar("SELECT COUNT(*) FROM partner_users WHERE email = :e", {"e": email}):
        raise PartnerError("An account with this email already exists. Log in instead.", "email")
    user_id = str(uuid.uuid4())
    conn.run("INSERT INTO partner_users (id, email, password_hash, name, phone, access_code) "
             "VALUES (:id, :e, :pw, :n, :ph, :c)", {"id": user_id, "e": email, "pw": hash_password(password),
                                                   "n": name.strip(), "ph": phone.strip(), "c": access["code"]})
    conn.run("UPDATE access_codes SET uses = uses + 1 WHERE code = :c", {"c": access["code"]})
    hotel_id = f"FH-{app_settings.next_number(conn, 'hotel_counter'):05d}"
    conn.run("INSERT INTO hotels (id, name, city, country, phone, whatsapp, email, owner_id, status, is_active, "
             "plan, manager_free_until, currency) VALUES (:id, :n, '', 'Rwanda', :ph, :ph, :e, :o, 'draft', FALSE, "
             ":plan, :free, 'USD')", {"id": hotel_id, "n": hotel_name.strip(), "ph": phone.strip(), "e": email,
                                      "o": user_id, "plan": access["plan"], "free": access["free_until"]})
    return {"user_id": user_id, "hotel_id": hotel_id}


def authenticate(conn: Connection, email: str, password: str) -> dict | None:
    user = conn.one("SELECT * FROM partner_users WHERE email = :e", {"e": email.strip().lower()})
    if user and check_password(password, user["password_hash"]):
        return user
    return None


def user_hotel(conn: Connection, user_id: str) -> dict | None:
    row = conn.one("SELECT * FROM hotels WHERE owner_id = :u ORDER BY created_at LIMIT 1", {"u": user_id})
    if not row:
        return None
    return catalog.hydrate_hotel(row, catalog.media_urls(conn, "hotel", [row["id"]]).get(row["id"]))


def set_password(conn: Connection, user_id: str, password: str) -> None:
    conn.run("UPDATE partner_users SET password_hash = :p WHERE id = :id",
             {"p": hash_password(password), "id": user_id})


# --------------------------------------------------------------------------- hotel profile

def _float(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip()) if str(value).strip() else None
    except ValueError:
        return None


def _int(value) -> int | None:
    v = _float(value)
    return int(v) if v is not None else None


def update_identity(conn: Connection, hotel_id: str, form: dict) -> list[str]:
    errors = []
    country = normalize_country(form.get("country"))
    if country not in MARKETS:
        errors.append("Choose Rwanda, Benin or Côte d'Ivoire.")
    for key, label in [("name", "hotel name"), ("city", "city"), ("address", "street address"),
                       ("phone", "reception phone"), ("whatsapp", "WhatsApp number")]:
        if not (form.get(key) or "").strip():
            errors.append(f"Enter the {label}.")
    lat, lng = _float(form.get("lat")), _float(form.get("lng"))
    if lat is None or lng is None:
        errors.append("Drop the pin on your entrance on the map.")
    amenities = ", ".join(a for a in form.get("amenities", []) if a in AMENITIES)
    conn.run("UPDATE hotels SET legal_name = :legal, tax_id = :tax WHERE id = :id",
             {"legal": (form.get("legal_name") or "").strip()[:120] or None,
              "tax": (form.get("tax_id") or "").strip()[:40] or None, "id": hotel_id})
    # The kind of place travellers find it under (Brief 3 v3). The form asks for it; an older form that
    # doesn't send one keeps what is stored, else the kind inferred from the type and name.
    stored = conn.one("SELECT category, good_for FROM hotels WHERE id = :id", {"id": hotel_id}) or {}
    category = (kinds.clean_kind(form.get("category")) or kinds.clean_kind(stored.get("category"))
                or kinds.guess_kind({"name": form.get("name"), "property_type": form.get("property_type"),
                                     "city": form.get("city"), "description": form.get("description")}))
    also = kinds.clean_kind(form.get("category_also"))
    tags = kinds.clean_tags(form.get("good_for") or []) if form.get("good_for_sent") else kinds.clean_tags(
        (stored.get("good_for") or "").split(","))
    conn.run("UPDATE hotels SET category = :c, category_also = :a, good_for = :g WHERE id = :id",
             {"c": category, "a": also if also != category else None, "g": ",".join(tags) or None, "id": hotel_id})
    conn.run("UPDATE hotels SET name = :name, property_type = :ptype, country = :country, city = :city, area = :area, "
             "address = :address, lat = :lat, lng = :lng, phone = :phone, whatsapp = :whatsapp, email = :email, "
             "check_in_time = :cin, check_out_time = :cout, description = :description, amenities = :amenities, "
             "star_rating = :stars, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
             {"name": (form.get("name") or "").strip(), "ptype": form.get("property_type") or "Hotel",
              "country": country or "Rwanda", "city": (form.get("city") or "").strip(),
              "area": (form.get("area") or "").strip(), "address": (form.get("address") or "").strip(),
              "lat": lat, "lng": lng, "phone": (form.get("phone") or "").strip(),
              "whatsapp": (form.get("whatsapp") or form.get("phone") or "").strip(),
              "email": (form.get("email") or "").strip(), "cin": form.get("check_in_time") or "14:00",
              "cout": form.get("check_out_time") or "11:00", "description": (form.get("description") or "").strip()[:1200],
              "amenities": amenities, "stars": _int(form.get("star_rating")), "id": hotel_id})
    return errors


def update_policies(conn: Connection, hotel_id: str, form: dict) -> list[str]:
    errors = []
    policy = form.get("cancellation_policy") if form.get("cancellation_policy") in POLICIES else "flexible"
    accepted = form.get("accept_terms") == "1"
    if not accepted:
        errors.append("Please accept the partner terms and commission.")
    conn.run("UPDATE hotels SET cancellation_policy = :p, children_allowed = :c, pets_allowed = :pets, "
             "smoking_allowed = :s, terms_accepted_at = CASE WHEN :acc THEN COALESCE(terms_accepted_at, :now) "
             "ELSE terms_accepted_at END WHERE id = :id",
             {"p": policy, "c": form.get("children_allowed") == "1", "pets": form.get("pets_allowed") == "1",
              "s": form.get("smoking_allowed") == "1", "acc": accepted, "now": utcnow(), "id": hotel_id})
    # Rooms follow the hotel policy unless set to non-refundable.
    conn.run("UPDATE room_types SET free_cancellation = :fc WHERE hotel_id = :id",
             {"fc": policy != "strict", "id": hotel_id})
    return errors


# --------------------------------------------------------------------------- rooms

def save_room(conn: Connection, hotel_id: str, form: dict, room_id: str | None = None) -> tuple[str | None, list[str]]:
    errors = []
    name = (form.get("name") or "").strip()
    total = _int(form.get("total_rooms"))
    guests = _int(form.get("max_guests"))
    base = _float(form.get("base_price"))
    weekend = _float(form.get("weekend_price"))
    if len(name) < 2:
        errors.append("Give the room type a name guests will see, e.g. Basic room.")
    if not total or total < 1:
        errors.append("Enter how many rooms of this type you have.")
    if not guests or guests < 1:
        errors.append("Enter how many guests fit in one room.")
    if not base or base <= 0:
        errors.append("Enter the standard price per night in USD.")
    if errors:
        return room_id, errors
    values = {
        "name": name, "kind": form.get("room_kind") if form.get("room_kind") in ROOM_KINDS else "Double",
        "total": total, "guests": guests, "bed": (form.get("bed_type") or "").strip(), "size": _int(form.get("size_sqm")),
        "base": round(base, 2), "weekend": round(weekend, 2) if weekend else None,
        "breakfast": form.get("breakfast_included") == "1",
        "amenities": ", ".join(a for a in form.get("amenities", []) if a in ROOM_AMENITIES),
        "description": (form.get("description") or "").strip()[:600], "hotel": hotel_id,
    }
    if room_id:
        values["id"] = room_id
        conn.run("UPDATE room_types SET name = :name, room_kind = :kind, total_rooms = :total, max_guests = :guests, "
                 "bed_type = :bed, size_sqm = :size, base_price = :base, weekend_price = :weekend, "
                 "breakfast_included = :breakfast, amenities = :amenities, description = :description "
                 "WHERE id = :id AND hotel_id = :hotel", values)
    else:
        policy = conn.scalar("SELECT cancellation_policy FROM hotels WHERE id = :h", {"h": hotel_id})
        values["id"] = f"{hotel_id}-{secrets.token_hex(2).upper()}"
        values["free_cancel"] = policy != "strict"
        conn.run("INSERT INTO room_types (id, hotel_id, name, room_kind, total_rooms, max_guests, bed_type, size_sqm, "
                 "base_price, weekend_price, breakfast_included, free_cancellation, amenities, description) VALUES "
                 "(:id, :hotel, :name, :kind, :total, :guests, :bed, :size, :base, :weekend, :breakfast, "
                 ":free_cancel, :amenities, :description)", values)
    return values["id"], []


def hotel_room_list(conn: Connection, hotel_id: str) -> list[dict]:
    rows = conn.all("SELECT * FROM room_types WHERE hotel_id = :h ORDER BY base_price, name", {"h": hotel_id})
    photos = catalog.media_urls(conn, "room", [r["id"] for r in rows])
    return [catalog.hydrate_room(r, photos.get(r["id"])) | {"photo_count": len(photos.get(r["id"], []))} for r in rows]


def get_room(conn: Connection, hotel_id: str, room_id: str) -> dict | None:
    row = conn.one("SELECT * FROM room_types WHERE id = :id AND hotel_id = :h", {"id": room_id, "h": hotel_id})
    if not row:
        return None
    return catalog.hydrate_room(row) | {"photos": media_list(conn, "room", room_id)}


def delete_room(conn: Connection, hotel_id: str, room_id: str) -> str | None:
    if conn.scalar("SELECT COUNT(*) FROM bookings WHERE room_type_id = :r", {"r": room_id}):
        return "This room type has bookings, so it can't be deleted. Set its rooms to sell to 0 in the calendar instead."
    conn.run("DELETE FROM media WHERE owner_type = 'room' AND owner_id = :r", {"r": room_id})
    conn.run("DELETE FROM room_types WHERE id = :r AND hotel_id = :h", {"r": room_id, "h": hotel_id})
    return None


# --------------------------------------------------------------------------- photos

def update_host(conn: Connection, hotel: dict, form: dict) -> list[str]:
    """The host guests meet on the hotel page. Saved either way; shown only while consent is ticked."""
    name = (form.get("host_name") or "").strip()[:40]
    welcome = " ".join((form.get("host_welcome") or "").split())
    consent = form.get("host_consent") == "1"
    errors = []
    if consent and not name:
        errors.append("Enter the first name guests will see, or untick the box to keep the profile hidden.")
    if len(welcome) > MAX_HOST_WELCOME:
        errors.append(f"Keep the welcome to {MAX_HOST_WELCOME} characters: two sentences is plenty.")
    if errors:
        return errors
    role = form.get("host_role") if form.get("host_role") in HOST_ROLES else None
    languages = ", ".join(lang for lang in HOST_LANGUAGES if lang in form.get("host_languages", []))
    conn.run("UPDATE hotels SET host_name = :n, host_role = :r, host_languages = :l, host_welcome = :w, "
             "host_consent_at = :c, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
             {"n": name or None, "r": role, "l": languages or None, "w": welcome or None,
              "c": (hotel.get("host_consent_at") or utcnow()) if consent else None, "id": hotel["id"]})
    return []


def media_list(conn: Connection, owner_type: str, owner_id: str) -> list[dict]:
    return conn.all("SELECT id, label, sort FROM media WHERE owner_type = :t AND owner_id = :o "
                    "ORDER BY sort, created_at", {"t": owner_type, "o": owner_id})


def add_photo(conn: Connection, owner_type: str, owner_id: str, data: bytes, content_type: str,
              label: str = "", thumb: bytes | None = None) -> str:
    """Store a photo, and its small card copy when the browser made one (it is skipped if odd)."""
    if content_type not in PHOTO_TYPES:
        raise PartnerError("Upload JPG, PNG or WebP photos.")
    if len(data) > MAX_PHOTO_BYTES:
        raise PartnerError("That photo is too large (over 3 MB). Try again: the page shrinks photos before upload.")
    if thumb is not None and not (0 < len(thumb) <= MAX_THUMB_BYTES and thumb[:3] == JPEG_START):
        thumb = None  # the card copy is always a JPEG; anything else falls back to the full photo
    sort = (conn.scalar("SELECT MAX(sort) FROM media WHERE owner_type = :t AND owner_id = :o",
                        {"t": owner_type, "o": owner_id}) or 0) + 1
    media_id = uuid.uuid4().hex
    conn.run("INSERT INTO media (id, owner_type, owner_id, content_type, data, label, sort, thumb) "
             "VALUES (:id, :t, :o, :ct, :d, :l, :s, :thumb)",
             {"id": media_id, "t": owner_type, "o": owner_id, "ct": content_type, "d": data,
              "l": label.strip()[:60], "s": sort, "thumb": thumb})
    return media_id


def delete_photo(conn: Connection, media_id: str, owner_ids: list[str]) -> None:
    marks, params = conn.in_params(owner_ids)
    conn.run(f"DELETE FROM media WHERE id = :id AND owner_id IN ({marks})", {"id": media_id, **params})


def make_cover(conn: Connection, media_id: str, hotel_id: str) -> None:
    conn.run("UPDATE media SET sort = sort + 1 WHERE owner_type = 'hotel' AND owner_id = :h", {"h": hotel_id})
    conn.run("UPDATE media SET sort = 0 WHERE id = :id AND owner_id = :h", {"id": media_id, "h": hotel_id})


def get_media(conn: Connection, media_id: str, card: bool = False) -> dict | None:
    """A photo; with card=True its ~800 px copy when there is one (photos uploaded before it existed
    have none, so they get the full photo)."""
    if card:
        small = conn.one("SELECT thumb FROM media WHERE id = :id AND thumb IS NOT NULL", {"id": media_id})
        if small:
            return {"content_type": "image/jpeg", "data": small["thumb"]}
    return conn.one("SELECT content_type, data FROM media WHERE id = :id", {"id": media_id})


# --------------------------------------------------------------------------- readiness & checks

def onboarding_status(conn: Connection, hotel: dict) -> dict:
    photos = conn.scalar("SELECT COUNT(*) FROM media WHERE owner_type = 'hotel' AND owner_id = :h",
                         {"h": hotel["id"]}) or 0
    rooms = conn.all("SELECT base_price, total_rooms FROM room_types WHERE hotel_id = :h", {"h": hotel["id"]})
    steps = {
        "identity": bool(hotel.get("city") and hotel.get("address") and hotel.get("phone")
                         and hotel.get("lat") is not None and hotel.get("country") in MARKETS),
        "photos": photos >= MIN_HOTEL_PHOTOS,
        "rooms": any(r["base_price"] and r["total_rooms"] for r in rooms),
        "policies": bool(hotel.get("terms_accepted_at")),
    }
    return {"steps": steps, "ready": all(steps.values()), "photos": photos, "rooms": len(rooms),
            "room_units": sum(int(r["total_rooms"] or 0) for r in rooms)}


def home_stats(conn: Connection, hotel: dict, today: date | None = None) -> dict:
    """The owner's home page (Brief 3 v3): this month's questions and bookings, the money, where bookings came
    from and who arrives next. The same figures the traveller's money panel shows."""
    today = today or date.today()
    start = date(today.year, today.month, 1)
    since = {"h": hotel["id"], "s": f"{start.isoformat()} 00:00:00"}
    questions = conn.scalar("SELECT COUNT(*) FROM enquiries WHERE hotel_id = :h AND created_at >= :s", since) or 0
    paid = conn.all("SELECT total_price, commission_amount, payout_amount FROM bookings WHERE hotel_id = :h "
                    "AND COALESCE(source, 'fichua') = 'fichua' AND status = 'confirmed' AND payment_status = 'paid' "
                    "AND paid_at >= :s", since)
    offline = conn.all("SELECT COALESCE(offline_source, 'walk-in') AS src, COUNT(*) AS n FROM bookings "
                       "WHERE hotel_id = :h AND source = 'offline' AND status = 'confirmed' AND created_at >= :s "
                       "GROUP BY COALESCE(offline_source, 'walk-in')", since)
    arrivals = conn.all("SELECT reference, guest_name, check_in, nights, guests, rooms, source, payment_status "
                        "FROM bookings WHERE hotel_id = :h AND status = 'confirmed' AND check_in >= :d "
                        "ORDER BY check_in, created_at LIMIT 5", {"h": hotel["id"], "d": today.isoformat()})
    sources = [{"label": "Fichua", "n": len(paid)}] + [{"label": r["src"], "n": int(r["n"])} for r in offline]
    return {
        "month": start, "questions": int(questions), "bookings": len(paid),
        "paid": round(sum(float(r["total_price"] or 0) for r in paid), 2),
        "received": round(sum(float(r["payout_amount"] or 0) for r in paid), 2),
        "fee": round(sum(float(r["commission_amount"] or 0) for r in paid), 2),
        "sources": [s for s in sources if s["n"]] or sources[:1],
        "arrivals": [{**dict(a), "guest_short": _short_name(a["guest_name"])} for a in arrivals],
    }


def _short_name(name: str | None) -> str:
    """'Priya Raman' → 'Priya R.': enough for the front desk, no more."""
    parts = (name or "").split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else (parts[0] if parts else "")


def share_text(hotel: dict, link: str) -> str:
    """The message owners send their contacts once they are live: book safely on Fichua, in either language."""
    return (f"{hotel['name']} is now on Fichua. Book with us safely, in English or French: {link}\n"
            f"{hotel['name']} est maintenant sur Fichua. Réservez chez nous en toute sécurité, en français ou en anglais : {link}")


def submit(conn: Connection, hotel: dict) -> bool:
    """Send the hotel for review. True when it was waiting to be sent (draft, or changes asked)."""
    if not onboarding_status(conn, hotel)["ready"]:
        raise PartnerError("Finish every step before submitting.")
    return conn.run("UPDATE hotels SET status = 'pending', submitted_at = :t WHERE id = :id AND status IN "
                    "('draft', 'changes')", {"t": utcnow(), "id": hotel["id"]}) > 0


def invite_text(code: str, link: str) -> str:
    """What Fichua sends a hotel with its access code (English and French: Rwanda, Benin, Côte d'Ivoire)."""
    return "\n".join([
        "Fichua Partners",
        f"Your access code: {code}",
        f"List your hotel here: {link}",
        "",
        f"Votre code d’accès : {code}",
        f"Inscrivez votre hôtel ici : {link}",
    ])


def review_checks(conn: Connection, hotel: dict) -> list[dict]:
    """Automatic checks shown to the admin before approving (anti-scam / quality)."""
    status = onboarding_status(conn, hotel)
    checks = []

    def add(ok: bool, good: str, bad: str, warn: bool = False):
        checks.append({"ok": ok, "text": good if ok else bad, "level": "ok" if ok else ("warn" if warn else "bad")})

    box = COUNTRY_BOXES.get(hotel.get("country") or "")
    lat, lng = hotel.get("lat"), hotel.get("lng")
    in_box = bool(box and lat is not None and lng is not None and box[0] <= lat <= box[1] and box[2] <= lng <= box[3])
    add(in_box, f"Map pin is inside {hotel.get('country')}", f"Map pin is not inside {hotel.get('country') or 'the country'}")
    add(bool(hotel.get("whatsapp")), "WhatsApp number given", "No WhatsApp number")
    dupes = conn.scalar("SELECT COUNT(*) FROM hotels WHERE id <> :id AND (phone = :p OR whatsapp = :w "
                        "OR (LOWER(name) = LOWER(:n) AND LOWER(city) = LOWER(:c)))",
                        {"id": hotel["id"], "p": hotel.get("phone") or "-", "w": hotel.get("whatsapp") or "-",
                         "n": hotel.get("name") or "", "c": hotel.get("city") or ""})
    add(not dupes, "No other hotel on Fichua uses this phone number or name",
        "Another hotel uses the same phone number or name: check it is not a duplicate")
    add(status["photos"] >= 5, f"{status['photos']} hotel photos",
        f"Only {status['photos']} hotel photos (we recommend at least 5)", warn=True)
    prices = [r["base_price"] for r in conn.all("SELECT base_price FROM room_types WHERE hotel_id = :h",
                                                {"h": hotel["id"]}) if r["base_price"]]
    sane = bool(prices) and all(10 <= p <= 2000 for p in prices)
    add(sane, "Room prices look normal ($10–$2,000 a night)", "Check the room prices: some look unusual", warn=True)
    add(bool(hotel.get("terms_accepted_at")), "Partner terms accepted", "Partner terms not accepted")
    return checks


# --------------------------------------------------------------------------- calendar

def month_grid(conn: Connection, room: dict, year: int, month: int) -> list[dict]:
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    end = nxt + timedelta(days=(7 - nxt.weekday()) % 7)
    grid = catalog.night_grid(conn, [room], start, end)
    today = date.today()
    days = []
    for i in range((end - start).days):
        d = start + timedelta(days=i)
        n = grid[(room["id"], d.isoformat())]
        left = (n["units"] or 0) - n["booked"]
        if n["closed"]:
            state = "closed"
        elif n["units"] is None or n["price"] is None:
            state = "unset"
        elif left <= 0:
            state = "sold"
        elif left == 1:
            state = "few"
        else:
            state = "open"
        days.append({"date": d.isoformat(), "day": d.day, "in_month": d.month == month, "past": d < today,
                     "price": n["price"], "units": n["units"], "booked": n["booked"], "left": max(0, left),
                     "state": state, "changed": n["changed"], "weekend": n["weekend"]})
    return days


def update_calendar(conn: Connection, room: dict, start: date, end: date, *, apply_to: str, price: str,
                    units: str, closed: bool, reset: bool) -> int:
    """Apply a change to every night from start to end (inclusive) matching apply_to."""
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        raise PartnerError("Change at most one year at a time.")
    grid = catalog.night_grid(conn, [room], start, end + timedelta(days=1))
    existing = {r["stay_date"]: r for r in conn.all(
        "SELECT stay_date, price, units FROM rate_overrides WHERE room_type_id = :r AND stay_date >= :s "
        "AND stay_date <= :e", {"r": room["id"], "s": start, "e": end})}
    # An empty price or rooms box means "keep what each night has now".
    p, u = _float(price), _int(units)
    count = 0
    for i in range((end - start).days + 1):
        d = start + timedelta(days=i)
        if apply_to == "weekdays" and d.weekday() in catalog.WEEKEND:
            continue
        if apply_to == "weekends" and d.weekday() not in catalog.WEEKEND:
            continue
        count += 1
        night = grid[(room["id"], d.isoformat())]
        old = existing.get(d.isoformat()) or {}
        if p and p > 0:
            new_price = round(p, 2) if p != night["rule_price"] else None
        else:
            new_price = old.get("price")
        if u is not None:
            new_units = max(night["booked"], u) if u != room.get("total_rooms") else None
        else:
            new_units = old.get("units")
        if reset or (new_price is None and new_units is None and not closed):
            conn.run("DELETE FROM rate_overrides WHERE room_type_id = :r AND stay_date = :d", {"r": room["id"], "d": d})
            continue
        conn.run("INSERT INTO rate_overrides (room_type_id, stay_date, price, units, closed) VALUES (:r, :d, :p, :u, :c) "
                 "ON CONFLICT (room_type_id, stay_date) DO UPDATE SET price = excluded.price, units = excluded.units, "
                 "closed = excluded.closed", {"r": room["id"], "d": d, "p": new_price, "u": new_units, "c": closed})
    return count

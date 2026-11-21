"""Bookings: hold → pay in full → confirm (commission, payout, WhatsApp) → manage / cancel.

Guest bookings start 'pending' and hold the room for a few minutes while the guest pays.
Offline bookings (walk-in, phone, ...) are added by the hotel, confirmed at once, and only
block inventory: no payment, no commission, no payout.
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import date, timedelta

from urllib.parse import quote, urlencode

from ..db import Connection, utcnow
from . import app_settings, catalog, currency, notify, payments, payouts, policies
from .dates import Stay

_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L confusion
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OFFLINE_SOURCES = ["Walk-in", "Phone", "WhatsApp", "Booking.com", "Other website"]


class BookingError(Exception):
    """User-facing booking problem (validation or sold out)."""


def new_reference() -> str:
    return "FCH-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def validate_guest(name: str, email: str, phone: str, phone_required: bool = True) -> dict[str, str]:
    errors = {}
    if len(name.strip()) < 2:
        errors["guest_name"] = "Please enter the lead guest's full name."
    if not EMAIL_RE.match(email.strip()):
        errors["guest_email"] = "Please enter a valid email so we can find your booking."
    digits = re.sub(r"\D", "", phone or "")
    if phone_required and len(digits) < 8:
        errors["guest_phone"] = "Please enter your WhatsApp number with the country code, e.g. +250 788 000 000."
    elif phone and len(digits) < 8:
        errors["guest_phone"] = "That phone number looks too short."
    return errors


def create_booking(conn: Connection, stay: Stay, room_type_id: str, *, guest_name: str, guest_email: str = "",
                   guest_phone: str = "", special_requests: str = "", guest_language: str = "en",
                   source: str = "fichua", offline_source: str | None = None,
                   agreed_amount: float | None = None) -> dict:
    # Lock the room type so two checkouts can't take the last room at once (Postgres).
    room = conn.one("SELECT id, hotel_id FROM room_types WHERE id = :rt" + conn.lock_clause(), {"rt": room_type_id})
    if not room:
        raise BookingError("That room type no longer exists.")
    live = catalog.availability(conn, stay, room_type_id=room_type_id, include_inactive=(source == "offline"))
    if not live:
        raise BookingError("Sorry — this room just sold out for these dates. Please pick another.")
    offline = source == "offline"
    total = round(float(agreed_amount), 2) if offline and agreed_amount else round(live[0]["total_price"], 2)
    hold = int(app_settings.get_float(conn, "hold_minutes") or 35)
    booking = {
        "id": str(uuid.uuid4()),
        "reference": new_reference(),
        "access_token": secrets.token_urlsafe(16),
        "hotel_id": room["hotel_id"],
        "room_type_id": room_type_id,
        "check_in": stay.check_in,
        "check_out": stay.check_out,
        "nights": stay.nights,
        "guests": stay.guests,
        "total_price": total,
        "currency": "USD",
        "guest_name": guest_name.strip(),
        "guest_email": guest_email.strip().lower(),
        "guest_phone": guest_phone.strip(),
        "special_requests": special_requests.strip()[:1000],
        "status": "confirmed" if offline else "pending",
        "source": "offline" if offline else "fichua",
        "payment_status": "n/a" if offline else "pending",
        "hold_expires_at": None if offline else utcnow() + timedelta(minutes=hold),
        "offline_source": offline_source if offline else None,
        "guest_language": guest_language if guest_language in ("en", "fr") else "en",
    }
    conn.run(
        "INSERT INTO bookings (id, reference, access_token, hotel_id, room_type_id, check_in, check_out, nights, "
        "guests, total_price, currency, guest_name, guest_email, guest_phone, special_requests, status, source, "
        "payment_status, hold_expires_at, offline_source, guest_language) VALUES (:id, :reference, :access_token, "
        ":hotel_id, :room_type_id, :check_in, :check_out, :nights, :guests, :total_price, :currency, :guest_name, "
        ":guest_email, :guest_phone, :special_requests, :status, :source, :payment_status, :hold_expires_at, "
        ":offline_source, :guest_language)", booking)
    conn.run_many(
        "INSERT INTO booking_nights (booking_id, room_type_id, stay_date) VALUES (:b, :rt, :d)",
        [{"b": booking["id"], "rt": room_type_id, "d": stay.check_in + timedelta(days=i)}
         for i in range(stay.nights)])
    return booking


def _load(conn: Connection, booking_id: str, lock: bool = False) -> dict | None:
    return conn.one("SELECT * FROM bookings WHERE id = :id" + (conn.lock_clause() if lock else ""), {"id": booking_id})


def confirm_payment(conn: Connection, booking_id: str, *, provider: str, provider_ref: str) -> dict | None:
    """Idempotent: safe to call from the success page and the Stripe webhook."""
    b = _load(conn, booking_id, lock=True)
    if not b or b["payment_status"] == "paid":
        return b
    hotel = conn.one("SELECT * FROM hotels WHERE id = :id", {"id": b["hotel_id"]})
    room = conn.one("SELECT name FROM room_types WHERE id = :id", {"id": b["room_type_id"]})
    pct = hotel.get("commission_pct")
    pct = float(pct) if pct is not None else app_settings.get_float(conn, "commission_pct")
    total = float(b["total_price"])
    commission = round(total * pct / 100.0, 2)
    conn.run("UPDATE bookings SET status = 'confirmed', payment_status = 'paid', paid_at = :t, "
             "hold_expires_at = NULL, commission_pct = :pct, commission_amount = :c, payout_amount = :p "
             "WHERE id = :id", {"t": utcnow(), "pct": pct, "c": commission, "p": round(total - commission, 2),
                                "id": booking_id})
    conn.run("INSERT INTO payments (id, booking_id, provider, provider_ref, amount, currency, status) "
             "VALUES (:id, :b, :prov, :ref, :a, 'USD', 'paid')",
             {"id": str(uuid.uuid4()), "b": booking_id, "prov": provider, "ref": provider_ref, "a": total})
    b = _load(conn, booking_id)
    payout_id = payouts.schedule(conn, b)
    if app_settings.get(conn, "payout_timing") == "immediate":
        payouts.release(conn, payout_id)
    notify.booking_paid(conn, b, hotel, room["name"] if room else "Room")
    return b


BOOKING_DETAIL_SQL = """
SELECT b.*, h.name AS hotel_name, h.city, h.country, h.address, h.area, h.lat, h.lng, h.image_urls,
       h.whatsapp AS hotel_whatsapp, h.phone AS hotel_phone, h.cancellation_policy,
       h.check_in_time, h.check_out_time, rt.name AS room_name,
       rt.free_cancellation, rt.breakfast_included
FROM bookings b
JOIN hotels h ON h.id = b.hotel_id
JOIN room_types rt ON rt.id = b.room_type_id
"""


def get_booking(conn: Connection, reference: str, token: str) -> dict | None:
    row = conn.one(BOOKING_DETAIL_SQL + " WHERE b.reference = :ref", {"ref": reference.upper()})
    if not row or not secrets.compare_digest(row["access_token"], token or ""):
        return None
    return _decorate(conn, row)


def find_booking(conn: Connection, reference: str, email: str) -> dict | None:
    row = conn.one(BOOKING_DETAIL_SQL + " WHERE b.reference = :ref AND b.guest_email = :email",
                   {"ref": reference.strip().upper(), "email": email.strip().lower()})
    return _decorate(conn, row) if row else None


def _decorate(conn: Connection, row: dict) -> dict:
    photos = catalog.media_urls(conn, "hotel", [row["hotel_id"]]).get(row["hotel_id"], [])
    row["image"] = (photos + catalog.split_list(row.pop("image_urls")) or [catalog.PLACEHOLDER_IMAGE])[0]
    expired = (row["status"] == "pending" and row.get("hold_expires_at")
               and row["hold_expires_at"] <= utcnow().isoformat())
    row["is_expired"] = bool(expired)
    row["awaiting_payment"] = row["status"] == "pending" and not expired
    # The same rule as the badge the guest saw before paying (services/policies.py).
    row["free_until"] = policies.free_until(row.get("cancellation_policy"), row["free_cancellation"], row["check_in"])
    row["can_cancel"] = (row["status"] == "confirmed" and row["free_until"] is not None
                         and date.today() <= row["free_until"])
    row["full_address"] = catalog.full_address(row)
    row["map_url"] = catalog.map_links(row)["map_url"]
    row.update(contact_links(row))
    return row


def contact_links(row: dict) -> dict:
    """Call and WhatsApp links for the hotel, in the international format phones need."""
    phone = currency.international_phone(row.get("hotel_phone"), row.get("country"))
    whatsapp = currency.international_phone(row.get("hotel_whatsapp") or row.get("hotel_phone"), row.get("country"))
    day = lambda value: date.fromisoformat(value[:10]).strftime("%d %b")  # noqa: E731
    hello = (f"Hello, I have a Fichua booking at {row.get('hotel_name')}: {row.get('reference')}, "
             f"{day(row['check_in'])} to {day(row['check_out'])}.")
    return {"hotel_tel": f"+{phone}" if phone else None,
            # %20 rather than +: WhatsApp documents percent-encoding for the message text.
            "hotel_wa": f"https://wa.me/{whatsapp}?" + urlencode({"text": hello}, quote_via=quote) if whatsapp else None}


def cancel_booking(conn: Connection, reference: str, token: str) -> dict:
    booking = get_booking(conn, reference, token)
    if not booking:
        raise BookingError("Booking not found.")
    if not booking["can_cancel"]:
        raise BookingError("This booking can no longer be cancelled online. Please contact the hotel.")
    refunded = False
    if booking["payment_status"] == "paid":
        payment = conn.one("SELECT * FROM payments WHERE booking_id = :b AND status = 'paid'", {"b": booking["id"]})
        if payment and payment["provider"] == "stripe":
            payments.refund(payment["provider_ref"])
        if payment:
            conn.run("UPDATE payments SET status = 'refunded' WHERE id = :id", {"id": payment["id"]})
        refunded = True
    conn.run("UPDATE bookings SET status = 'cancelled', payment_status = :ps WHERE id = :id",
             {"ps": "refunded" if refunded else booking["payment_status"], "id": booking["id"]})
    payouts.on_cancel(conn, booking["id"])
    hotel = conn.one("SELECT * FROM hotels WHERE id = :id", {"id": booking["hotel_id"]})
    notify.booking_cancelled(conn, booking, hotel, refunded)
    booking.update(status="cancelled", can_cancel=False, payment_status="refunded" if refunded else booking["payment_status"])
    return booking


def cancel_offline(conn: Connection, booking_id: str, hotel_id: str) -> bool:
    return conn.run("UPDATE bookings SET status = 'cancelled' WHERE id = :id AND hotel_id = :h "
                    "AND source = 'offline'", {"id": booking_id, "h": hotel_id}) > 0


def hotel_bookings(conn: Connection, hotel_id: str, show: str = "upcoming") -> list[dict]:
    where = "b.hotel_id = :h AND (b.status = 'confirmed' OR b.status = 'cancelled')"
    if show == "upcoming":
        where += " AND b.check_out >= :today AND b.status = 'confirmed'"
    elif show == "past":
        where += " AND b.check_out < :today"
    elif show == "cancelled":
        where += " AND b.status = 'cancelled'"
    return conn.all(
        "SELECT b.*, rt.name AS room_name, p.status AS payout_status FROM bookings b "
        "JOIN room_types rt ON rt.id = b.room_type_id LEFT JOIN payouts p ON p.booking_id = b.id "
        f"WHERE {where} ORDER BY b.check_in", {"h": hotel_id, "today": date.today()})

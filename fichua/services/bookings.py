"""Booking write side: create (with inventory re-check), look up, cancel."""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import date, timedelta

from ..db import Connection
from . import catalog
from .dates import Stay

_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L confusion
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BookingError(Exception):
    """User-facing booking problem (validation or sold out)."""


def new_reference() -> str:
    return "FCH-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def validate_guest(name: str, email: str, phone: str) -> dict[str, str]:
    errors = {}
    if len(name.strip()) < 2:
        errors["guest_name"] = "Please enter the lead guest's full name."
    if not EMAIL_RE.match(email.strip()):
        errors["guest_email"] = "Please enter a valid email so we can send your confirmation."
    if phone and len(re.sub(r"\D", "", phone)) < 7:
        errors["guest_phone"] = "That phone number looks too short."
    return errors


def create_booking(conn: Connection, stay: Stay, room_type_id: str, *, guest_name: str,
                   guest_email: str, guest_phone: str = "", special_requests: str = "") -> dict:
    # Lock this room's rate rows for the stay so two guests can't take the last room (Postgres).
    conn.all(
        "SELECT stay_date FROM room_rates WHERE room_type_id = :rt "
        "AND stay_date >= :ci AND stay_date < :co" + conn.lock_clause(),
        {"rt": room_type_id, "ci": stay.check_in, "co": stay.check_out},
    )
    live = catalog.availability(conn, stay, room_type_id=room_type_id)
    if not live:
        raise BookingError("Sorry — this room just sold out for your dates. Please pick another.")
    offer = live[0]
    room = conn.one("SELECT hotel_id FROM room_types WHERE id = :id", {"id": room_type_id})
    hotel = conn.one("SELECT currency FROM hotels WHERE id = :id", {"id": room["hotel_id"]})

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
        "total_price": round(offer["total_price"], 2),
        "currency": hotel.get("currency") or "USD",
        "guest_name": guest_name.strip(),
        "guest_email": guest_email.strip().lower(),
        "guest_phone": guest_phone.strip(),
        "special_requests": special_requests.strip()[:1000],
    }
    conn.run(
        "INSERT INTO bookings (id, reference, access_token, hotel_id, room_type_id, check_in, "
        "check_out, nights, guests, total_price, currency, guest_name, guest_email, guest_phone, "
        "special_requests) VALUES (:id, :reference, :access_token, :hotel_id, :room_type_id, "
        ":check_in, :check_out, :nights, :guests, :total_price, :currency, :guest_name, "
        ":guest_email, :guest_phone, :special_requests)",
        booking,
    )
    conn.run_many(
        "INSERT INTO booking_nights (booking_id, room_type_id, stay_date) VALUES (:b, :rt, :d)",
        [{"b": booking["id"], "rt": room_type_id, "d": stay.check_in + timedelta(days=i)}
         for i in range(stay.nights)],
    )
    return booking


BOOKING_DETAIL_SQL = """
SELECT b.*, h.name AS hotel_name, h.city, h.country, h.address, h.image_urls,
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
    return _decorate(row)


def find_booking(conn: Connection, reference: str, email: str) -> dict | None:
    row = conn.one(BOOKING_DETAIL_SQL + " WHERE b.reference = :ref AND b.guest_email = :email",
                   {"ref": reference.strip().upper(), "email": email.strip().lower()})
    return _decorate(row) if row else None


def _decorate(row: dict) -> dict:
    row["image"] = (catalog.split_list(row.pop("image_urls")) or [catalog.PLACEHOLDER_IMAGE])[0]
    row["can_cancel"] = (row["status"] == "confirmed" and bool(row["free_cancellation"])
                         and date.fromisoformat(row["check_in"]) > date.today())
    return row


def cancel_booking(conn: Connection, reference: str, token: str) -> dict:
    booking = get_booking(conn, reference, token)
    if not booking:
        raise BookingError("Booking not found.")
    if not booking["can_cancel"]:
        raise BookingError("This booking can no longer be cancelled online. Please contact the hotel.")
    conn.run("UPDATE bookings SET status = 'cancelled' WHERE id = :id", {"id": booking["id"]})
    booking["status"] = "cancelled"
    booking["can_cancel"] = False
    return booking


def list_bookings(conn: Connection, limit: int = 200) -> list[dict]:
    return conn.all(
        "SELECT b.reference, b.status, b.check_in, b.check_out, b.guests, b.total_price, "
        "b.currency, b.guest_name, b.guest_email, b.guest_phone, b.created_at, "
        "h.name AS hotel_name, rt.name AS room_name "
        "FROM bookings b JOIN hotels h ON h.id = b.hotel_id "
        "JOIN room_types rt ON rt.id = b.room_type_id "
        "ORDER BY b.created_at DESC LIMIT :limit", {"limit": limit})

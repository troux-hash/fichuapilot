"""Ask the hotel before booking (Brief 2 §6.2): WhatsApp opens with the stay and a reference code.

Each tap is recorded under its own code, so the hotel and Fichua can later count what Fichua brought in
(Brief 1 attributes by reference code). The guest messages the hotel's reception number, which the
partner form says guests may call or message.
"""
from __future__ import annotations

import secrets
import uuid
from urllib.parse import quote, urlencode

from ..db import Connection
from . import currency
from .dates import Stay

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread


def new_reference() -> str:
    return "ASK-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def hotel_number(hotel: dict) -> str:
    """The reception number in the international digits WhatsApp needs, or '' when there is none."""
    return currency.international_phone(hotel.get("phone"), hotel.get("country"))


def message(hotel: dict, stay: Stay, reference: str | None) -> str:
    day = lambda d: f"{d.day} {d.strftime('%b')}"  # noqa: E731
    who = f"{stay.guests} guest{'' if stay.guests == 1 else 's'}"
    if stay.rooms > 1:
        who += f" in {stay.rooms} rooms"
    text = (f"Hello, I found {hotel['name']} on Fichua. I would like to stay "
            f"{day(stay.check_in)} to {day(stay.check_out)}, {who}.")
    return f"{text} Ref {reference}" if reference else text


def whatsapp_link(hotel: dict, stay: Stay, reference: str | None) -> str:
    # %20 rather than +: WhatsApp documents percent-encoding for the message text.
    return (f"https://wa.me/{hotel_number(hotel)}?"
            + urlencode({"text": message(hotel, stay, reference)}, quote_via=quote))


def create(conn: Connection, hotel: dict, stay: Stay) -> str:
    """Record the enquiry and return its reference."""
    reference = new_reference()
    conn.run("INSERT INTO enquiries (id, reference, hotel_id, check_in, check_out, guests, rooms, channel) "
             "VALUES (:id, :ref, :h, :ci, :co, :g, :r, 'whatsapp')",
             {"id": str(uuid.uuid4()), "ref": reference, "h": hotel["id"], "ci": stay.check_in.isoformat(),
              "co": stay.check_out.isoformat(), "g": stay.guests, "r": stay.rooms})
    return reference

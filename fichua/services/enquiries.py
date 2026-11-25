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
from . import app_settings, currency
from .dates import Stay

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread


def new_reference() -> str:
    return "ASK-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def hotel_number(hotel: dict) -> str:
    """The reception number in the international digits WhatsApp needs, or '' when there is none."""
    return currency.international_phone(hotel.get("phone"), hotel.get("country"))


_FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def message(hotel: dict, stay: Stay, reference: str | None, question: str = "", lang: str = "en") -> str:
    """The message WhatsApp opens with, in the traveller's language, with their own question if they wrote one."""
    question = " ".join((question or "").split())[:500]
    if lang == "fr":
        day = lambda d: f"{d.day} {_FR_MONTHS[d.month - 1]}"  # noqa: E731
        who = f"{stay.guests} personne{'' if stay.guests == 1 else 's'}"
        if stay.rooms > 1:
            who += f" en {stay.rooms} chambres"
        text = (f"Bonjour, j’ai trouvé {hotel['name']} sur Fichua. Je souhaite séjourner "
                f"du {day(stay.check_in)} au {day(stay.check_out)}, {who}.")
        ref = f"Réf. {reference}" if reference else ""
    else:
        day = lambda d: f"{d.day} {d.strftime('%b')}"  # noqa: E731
        who = f"{stay.guests} guest{'' if stay.guests == 1 else 's'}"
        if stay.rooms > 1:
            who += f" in {stay.rooms} rooms"
        text = (f"Hello, I found {hotel['name']} on Fichua. I would like to stay "
                f"{day(stay.check_in)} to {day(stay.check_out)}, {who}.")
        ref = f"Ref {reference}" if reference else ""
    return " ".join(p for p in (text, question, ref) if p)


def whatsapp_link(hotel: dict, stay: Stay, reference: str | None, question: str = "", lang: str = "en") -> str:
    # %20 rather than +: WhatsApp documents percent-encoding for the message text.
    return (f"https://wa.me/{hotel_number(hotel)}?"
            + urlencode({"text": message(hotel, stay, reference, question, lang)}, quote_via=quote))


def fichua_link(conn: Connection, text: str) -> str | None:
    """'Message us on WhatsApp': Fichua's own number from Settings, or None while it isn't set."""
    number = currency.international_phone(app_settings.get(conn, "admin_whatsapp"), None)
    if not number:
        return None
    return f"https://wa.me/{number}?" + urlencode({"text": text}, quote_via=quote)


def create(conn: Connection, hotel: dict, stay: Stay) -> str:
    """Record the enquiry and return its reference."""
    reference = new_reference()
    conn.run("INSERT INTO enquiries (id, reference, hotel_id, check_in, check_out, guests, rooms, channel) "
             "VALUES (:id, :ref, :h, :ci, :co, :g, :r, 'whatsapp')",
             {"id": str(uuid.uuid4()), "ref": reference, "h": hotel["id"], "ci": stay.check_in.isoformat(),
              "co": stay.check_out.isoformat(), "g": stay.guests, "r": stay.rooms})
    return reference

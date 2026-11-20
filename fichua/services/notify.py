"""WhatsApp notifications: every message is written to the `messages` table first (the admin
outbox), then sent through Meta's WhatsApp Cloud API when it is configured.

Testing tip: with Meta's free test number, recipients must be added in the Meta dashboard,
and free-text messages reach a phone that has messaged the business in the last 24 hours.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid

from ..config import settings
from ..db import Connection, utcnow
from . import app_settings, currency
from .currency import usd

FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
FR_DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _date(value: str, lang: str) -> str:
    from datetime import date
    d = date.fromisoformat(value[:10])
    if lang == "fr":
        return f"{FR_DAYS[d.weekday()]} {d.day} {FR_MONTHS[d.month - 1]}"
    return d.strftime("%a %d %b")


def _money(amount, country, rates, lang: str) -> str:
    text = usd(amount, decimals=float(amount) != int(float(amount)))
    local = currency.local_text(amount, country, rates)
    return f"{text} ({local.replace('≈ ', '≈')})" if local else text


def whatsapp_ready() -> bool:
    return bool(settings.whatsapp_token and settings.whatsapp_phone_id)


def normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def queue(conn: Connection, *, role: str, to_phone: str | None, language: str, kind: str, body: str,
          booking_id: str | None = None, hotel_id: str | None = None) -> str:
    message_id = str(uuid.uuid4())
    conn.run("INSERT INTO messages (id, booking_id, hotel_id, role, to_phone, language, kind, body, status) "
             "VALUES (:id, :b, :h, :role, :to, :lang, :kind, :body, 'queued')",
             {"id": message_id, "b": booking_id, "h": hotel_id, "role": role, "to": normalize_phone(to_phone),
              "lang": language, "kind": kind, "body": body})
    return message_id


def _send_whatsapp(to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_id}/messages"
    payload = json.dumps({"messaging_product": "whatsapp", "to": to, "type": "text",
                          "text": {"preview_url": False, "body": body}}).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {settings.whatsapp_token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise RuntimeError(detail or f"WhatsApp error {exc.code}") from exc


def flush(conn: Connection, limit: int = 20) -> int:
    """Send queued messages. Without WhatsApp keys they are marked 'not_sent' (visible in admin)."""
    sent = 0
    for m in conn.all("SELECT id, to_phone, body FROM messages WHERE status = 'queued' "
                      "ORDER BY created_at LIMIT :n", {"n": limit}):
        if not m["to_phone"]:
            status, error = "not_sent", "No phone number"
        elif not whatsapp_ready():
            status, error = "not_sent", "WhatsApp not connected yet"
        else:
            try:
                _send_whatsapp(m["to_phone"], m["body"])
                status, error = "sent", None
                sent += 1
            except Exception as exc:  # network or Meta error: keep it visible in the outbox
                status, error = "failed", str(exc)[:300]
        conn.run("UPDATE messages SET status = :s, error = :e, sent_at = :t WHERE id = :id",
                 {"s": status, "e": error, "t": utcnow(), "id": m["id"]})
    return sent


# ---------------------------------------------------------------------------------------------
# Message templates (EN / FR). Kept short: they are read on a phone lock screen.
# ---------------------------------------------------------------------------------------------

def booking_paid(conn: Connection, booking: dict, hotel: dict, room_name: str) -> None:
    rates = app_settings.all_settings(conn)
    country = hotel.get("country")
    guest_lang = booking.get("guest_language") or "en"
    hotel_lang = currency.language_for(country)
    nights = int(booking["nights"])
    total, commission, payout = booking["total_price"], booking["commission_amount"], booking["payout_amount"]
    pct = f"{float(booking['commission_pct']):g}"

    def stay(lang):
        word = ("nuit" if nights == 1 else "nuits") if lang == "fr" else ("night" if nights == 1 else "nights")
        return f"{_date(booking['check_in'], lang)} → {_date(booking['check_out'], lang)} ({nights} {word})"

    guest = {
        "en": (f"Booking confirmed\nHi {booking['guest_name'].split()[0]}, your stay at {hotel['name']} is reserved.\n\n"
               f"Reference: {booking['reference']}\nRoom: {room_name}, {booking['guests']} guests\n"
               f"Dates: {stay('en')}\nPaid in full: {_money(total, country, rates, 'en')}\n"
               f"Nothing more to pay at the hotel.\n\nCheck-in from {hotel.get('check_in_time') or '14:00'} · "
               f"{hotel.get('address') or hotel['city']}"),
        "fr": (f"Réservation confirmée\nBonjour {booking['guest_name'].split()[0]}, votre séjour à {hotel['name']} est réservé.\n\n"
               f"Référence : {booking['reference']}\nChambre : {room_name}, {booking['guests']} personnes\n"
               f"Dates : {stay('fr')}\nPayé en totalité : {_money(total, country, rates, 'fr')}\n"
               f"Rien de plus à payer à l’hôtel.\n\nArrivée à partir de {hotel.get('check_in_time') or '14:00'} · "
               f"{hotel.get('address') or hotel['city']}"),
    }
    to_hotel = {
        "en": (f"New booking, paid\n{hotel['name']}, you have a new Fichua booking.\n\n"
               f"Reference: {booking['reference']}\nGuest: {booking['guest_name']}, {booking['guests']} guests"
               f"{' · ' + booking['guest_phone'] if booking.get('guest_phone') else ''}\n"
               f"Room: {room_name} × 1\nDates: {stay('en')}\n\n"
               f"Guest paid Fichua: {_money(total, country, rates, 'en')}\n"
               f"Fichua commission ({pct}%): {usd(commission, True)}\n"
               f"Your payout: {_money(payout, country, rates, 'en')}"),
        "fr": (f"Nouvelle réservation payée\n{hotel['name']}, vous avez une nouvelle réservation Fichua.\n\n"
               f"Référence : {booking['reference']}\nClient : {booking['guest_name']}, {booking['guests']} personnes"
               f"{' · ' + booking['guest_phone'] if booking.get('guest_phone') else ''}\n"
               f"Chambre : {room_name} × 1\nDates : {stay('fr')}\n\n"
               f"Payé par le client à Fichua : {_money(total, country, rates, 'fr')}\n"
               f"Commission Fichua ({pct} %) : {usd(commission, True)}\n"
               f"Votre versement : {_money(payout, country, rates, 'fr')}"),
    }
    admin = (f"Payment received\n{booking['reference']} · {hotel['name']} ({hotel['id']})\n\n"
             f"Amount: {usd(total, True)} by card\nFichua commission ({pct}%): {usd(commission, True)}\n"
             f"Owed to the hotel: {usd(payout, True)}\nStay: {stay('en')}")

    queue(conn, role="guest", to_phone=booking.get("guest_phone"), language=guest_lang, kind="booking_paid",
          body=guest.get(guest_lang, guest["en"]), booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="hotel", to_phone=hotel.get("whatsapp") or hotel.get("phone"), language=hotel_lang,
          kind="booking_paid", body=to_hotel[hotel_lang], booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="admin", to_phone=app_settings.get(conn, "admin_whatsapp"), language="en",
          kind="booking_paid", body=admin, booking_id=booking["id"], hotel_id=hotel["id"])


def booking_cancelled(conn: Connection, booking: dict, hotel: dict, refunded: bool) -> None:
    hotel_lang = currency.language_for(hotel.get("country"))
    guest_lang = booking.get("guest_language") or "en"
    amount = usd(booking["total_price"], True)
    guest = {
        "en": f"Booking cancelled\n{booking['reference']} at {hotel['name']} is cancelled."
              + (f" {amount} is being refunded to your card." if refunded else ""),
        "fr": f"Réservation annulée\n{booking['reference']} au {hotel['name']} est annulée."
              + (f" {amount} vous sera remboursé sur votre carte." if refunded else ""),
    }
    to_hotel = {
        "en": f"Booking cancelled\n{booking['reference']} ({booking['guest_name']}, "
              f"{_date(booking['check_in'], 'en')}) is cancelled. The room is back on sale.",
        "fr": f"Réservation annulée\n{booking['reference']} ({booking['guest_name']}, "
              f"{_date(booking['check_in'], 'fr')}) est annulée. La chambre est de nouveau en vente.",
    }
    queue(conn, role="guest", to_phone=booking.get("guest_phone"), language=guest_lang, kind="booking_cancelled",
          body=guest.get(guest_lang, guest["en"]), booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="hotel", to_phone=hotel.get("whatsapp") or hotel.get("phone"), language=hotel_lang,
          kind="booking_cancelled", body=to_hotel[hotel_lang], booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="admin", to_phone=app_settings.get(conn, "admin_whatsapp"), language="en",
          kind="booking_cancelled", body=f"Cancelled: {booking['reference']} · {hotel['name']}"
          + (f" · refund {amount}" if refunded else ""), booking_id=booking["id"], hotel_id=hotel["id"])


def hotel_decision(conn: Connection, hotel: dict, decision: str, note: str = "") -> None:
    lang = currency.language_for(hotel.get("country"))
    texts = {
        "approved": {
            "en": f"Welcome to Fichua!\n{hotel['name']} ({hotel['id']}) is approved and now live. "
                  "Guests can book you from today. Manage your calendar in Fichua Partners.",
            "fr": f"Bienvenue sur Fichua !\n{hotel['name']} ({hotel['id']}) est approuvé et en ligne. "
                  "Les clients peuvent réserver dès aujourd’hui. Gérez votre calendrier dans Fichua Partners.",
        },
        "changes": {
            "en": f"Fichua review: a few changes needed\n{hotel['name']} ({hotel['id']})\n\n{note}",
            "fr": f"Vérification Fichua : quelques modifications\n{hotel['name']} ({hotel['id']})\n\n{note}",
        },
        "rejected": {
            "en": f"Fichua review\n{hotel['name']} ({hotel['id']}) was not approved.\n\n{note}",
            "fr": f"Vérification Fichua\n{hotel['name']} ({hotel['id']}) n’a pas été approuvé.\n\n{note}",
        },
    }
    queue(conn, role="hotel", to_phone=hotel.get("whatsapp") or hotel.get("phone"), language=lang,
          kind=f"hotel_{decision}", body=texts[decision][lang].strip(), hotel_id=hotel["id"])

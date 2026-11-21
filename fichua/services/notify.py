"""WhatsApp notifications: every message is written to the `messages` table first (the admin
outbox), then sent through Meta's WhatsApp Cloud API when it is configured.

Messages go out as approved templates (services/whatsapp_templates.py), because Meta only delivers
free text to someone who wrote to the business in the last 24 hours. The outbox keeps the template,
its parameters and the exact text the person receives. WHATSAPP_SEND_MODE=text sends that same text
as a free-form message instead: handy for a first test with Meta's test number.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import date

from ..config import settings
from ..db import Connection, utcnow
from . import app_settings, currency
from . import whatsapp_templates as wt
from .currency import usd

FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
FR_DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _date(value: str, lang: str) -> str:
    d = date.fromisoformat(value[:10])
    if lang == "fr":
        return f"{FR_DAYS[d.weekday()]} {d.day} {FR_MONTHS[d.month - 1]}"
    return d.strftime("%a %d %b")


def _usd(amount, lang: str, decimals: bool = False) -> str:
    """'$1,234.50' in English, '1 234,50 $' in French."""
    if lang != "fr":
        return usd(amount, decimals)
    value = float(amount or 0)
    text = f"{value:,.2f}" if decimals or value != int(value) else f"{value:,.0f}"
    return text.replace(",", " ").replace(".", ",") + " $"


def _money(amount, country, rates, lang: str) -> str:
    """'$160 (≈232,000 RWF)' in English, '160 $ (≈ 232 000 RWF)' in French."""
    text = _usd(amount, lang)
    local = currency.local_text(amount, country, rates)
    if not local:
        return text
    if lang == "fr":  # plain spaces: WhatsApp parameters are cleaned to plain spaces anyway
        return f"{text} ({local.replace(',', ' ').replace(chr(0x202F), ' ')})"
    return f"{text} ({local.replace('≈ ', '≈')})"


def _guests(count, lang: str) -> str:
    n = int(count or 1)
    if lang == "fr":
        return f"{n} personne{'s' if n > 1 else ''}"
    return f"{n} guest{'' if n == 1 else 's'}"


def _hotel_phone(hotel: dict) -> str:
    """The hotel's WhatsApp (or reception) number with its country code: Meta needs it international."""
    return currency.international_phone(hotel.get("whatsapp") or hotel.get("phone"), hotel.get("country"))


def whatsapp_ready() -> bool:
    return bool(settings.whatsapp_token and settings.whatsapp_phone_id)


def normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def queue(conn: Connection, *, role: str, to_phone: str | None, language: str, kind: str, template: str,
          params: list, booking_id: str | None = None, hotel_id: str | None = None) -> str:
    lang = wt.language(template, language)
    values = [wt.clean(p) for p in params]
    message_id = str(uuid.uuid4())
    conn.run("INSERT INTO messages (id, booking_id, hotel_id, role, to_phone, language, kind, body, status, "
             "template, params) VALUES (:id, :b, :h, :role, :to, :lang, :kind, :body, 'queued', :tpl, :params)",
             {"id": message_id, "b": booking_id, "h": hotel_id, "role": role, "to": normalize_phone(to_phone),
              "lang": lang, "kind": kind, "body": wt.render(template, lang, values), "tpl": template,
              "params": json.dumps(values, ensure_ascii=False)})
    return message_id


def payload(message: dict) -> dict:
    """The Cloud API request for one outbox row: its template, or its text in text mode (and for rows
    written before templates existed)."""
    if settings.whatsapp_send_mode != "text" and message.get("template"):
        return wt.send_payload(message["to_phone"], message["template"], message.get("language") or "en",
                               json.loads(message.get("params") or "[]"))
    return {"messaging_product": "whatsapp", "to": message["to_phone"], "type": "text",
            "text": {"preview_url": False, "body": message["body"]}}


def _send_whatsapp(message: dict) -> None:
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_id}/messages"
    req = urllib.request.Request(url, data=json.dumps(payload(message)).encode(), method="POST", headers={
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
    for m in conn.all("SELECT id, to_phone, body, language, template, params FROM messages "
                      "WHERE status = 'queued' ORDER BY created_at LIMIT :n", {"n": limit}):
        if not m["to_phone"]:
            status, error = "not_sent", "No phone number"
        elif not whatsapp_ready():
            status, error = "not_sent", "WhatsApp not connected yet"
        else:
            try:
                _send_whatsapp(dict(m))
                status, error = "sent", None
                sent += 1
            except Exception as exc:  # network or Meta error: keep it visible in the outbox
                status, error = "failed", str(exc)[:300]
        conn.run("UPDATE messages SET status = :s, error = :e, sent_at = :t WHERE id = :id",
                 {"s": status, "e": error, "t": utcnow(), "id": m["id"]})
    return sent


# ---------------------------------------------------------------------------------------------
# What each message says. The wording lives in whatsapp_templates.py; this fills in the details.
# ---------------------------------------------------------------------------------------------

def booking_paid(conn: Connection, booking: dict, hotel: dict, room_name: str) -> None:
    rates = app_settings.all_settings(conn)
    country = hotel.get("country")
    guest_lang = wt.language("fichua_booking_confirmed", booking.get("guest_language") or "en")
    hotel_lang = wt.language("fichua_new_booking", currency.language_for(country))
    nights = int(booking["nights"])
    total, commission, payout = booking["total_price"], booking["commission_amount"], booking["payout_amount"]
    pct = f"{float(booking['commission_pct']):g}"
    name = (booking.get("guest_name") or "").strip()

    def stay(lang):
        word = ("nuit" if nights == 1 else "nuits") if lang == "fr" else ("night" if nights == 1 else "nights")
        return f"{_date(booking['check_in'], lang)} → {_date(booking['check_out'], lang)} ({nights} {word})"

    def fee(lang):
        return f"{pct} % · {_usd(commission, 'fr', True)}" if lang == "fr" else f"{pct}% · {usd(commission, True)}"

    phone = f" · {booking['guest_phone']}" if booking.get("guest_phone") else ""
    queue(conn, role="guest", to_phone=booking.get("guest_phone"), language=guest_lang, kind="booking_paid",
          template="fichua_booking_confirmed",
          params=[(name.split() or ["there"])[0], hotel["name"], booking["reference"],
                  f"{room_name}, {_guests(booking['guests'], guest_lang)}", stay(guest_lang),
                  _money(total, country, rates, guest_lang), hotel.get("check_in_time") or "14:00",
                  hotel.get("address") or hotel.get("city") or "-"],
          booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="hotel", to_phone=_hotel_phone(hotel), language=hotel_lang,
          kind="booking_paid", template="fichua_new_booking",
          params=[hotel["name"], booking["reference"], f"{name}, {_guests(booking['guests'], hotel_lang)}{phone}",
                  f"{room_name} × 1", stay(hotel_lang), _money(total, country, rates, hotel_lang), fee(hotel_lang),
                  _money(payout, country, rates, hotel_lang)],
          booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="admin", to_phone=app_settings.get(conn, "admin_whatsapp"), language="en",
          kind="booking_paid", template="fichua_payment_received",
          params=[booking["reference"], f"{hotel['name']} ({hotel['id']})", usd(total, True), fee("en"),
                  usd(payout, True), stay("en")],
          booking_id=booking["id"], hotel_id=hotel["id"])


def booking_cancelled(conn: Connection, booking: dict, hotel: dict, refunded: bool) -> None:
    hotel_lang = wt.language("fichua_booking_cancelled_hotel", currency.language_for(hotel.get("country")))
    guest_lang = wt.language("fichua_booking_cancelled", booking.get("guest_language") or "en")
    total = booking["total_price"]

    def refund(lang):
        if not refunded:
            return "aucun, ce tarif n’était pas remboursable" if lang == "fr" else "none, this rate was non-refundable"
        if lang == "fr":
            return f"{_usd(total, 'fr', True)} sur votre carte, sous 5 à 10 jours ouvrés"
        return f"{usd(total, True)} to your card, within 5 to 10 working days"

    queue(conn, role="guest", to_phone=booking.get("guest_phone"), language=guest_lang, kind="booking_cancelled",
          template="fichua_booking_cancelled", params=[booking["reference"], hotel["name"], refund(guest_lang)],
          booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="hotel", to_phone=_hotel_phone(hotel), language=hotel_lang,
          kind="booking_cancelled", template="fichua_booking_cancelled_hotel",
          params=[booking["reference"], booking.get("guest_name") or "-", _date(booking["check_in"], hotel_lang)],
          booking_id=booking["id"], hotel_id=hotel["id"])
    queue(conn, role="admin", to_phone=app_settings.get(conn, "admin_whatsapp"), language="en",
          kind="booking_cancelled", template="fichua_booking_cancelled_admin",
          params=[booking["reference"], f"{hotel['name']} ({hotel['id']})", usd(total, True) if refunded else "none"],
          booking_id=booking["id"], hotel_id=hotel["id"])


def hotel_decision(conn: Connection, hotel: dict, decision: str, note: str = "") -> None:
    template = f"fichua_hotel_{decision}"
    lang = wt.language(template, currency.language_for(hotel.get("country")))
    params = [hotel["name"], hotel["id"]]
    if decision != "approved":
        default = {"changes": ("Please review your listing.", "Merci de revoir votre annonce."),
                   "rejected": ("No reason was given.", "Aucune raison n’a été donnée.")}[decision]
        params.append(note.strip() or (default[1] if lang == "fr" else default[0]))
    queue(conn, role="hotel", to_phone=_hotel_phone(hotel), language=lang,
          kind=f"hotel_{decision}", template=template, params=params, hotel_id=hotel["id"])

"""'Add to calendar' for a confirmed booking: an .ics file (iPhone, Outlook, most phones) and a
Google Calendar link. The event runs from check-in time to check-out time in the hotel's own time
zone, written in UTC so it shows at the right hour wherever the guest's phone is.

The event links to Manage booking, never to the booking's private link: calendars get shared, and
that link can cancel the stay."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode

from . import currency


def _at(day: str, clock: str | None, fallback: str, country: str | None) -> datetime:
    """The hotel's local day and time, as naive UTC."""
    try:
        hh, mm = (int(x) for x in (clock or fallback).split(":")[:2])
    except ValueError:
        hh, mm = (int(x) for x in fallback.split(":"))
    local = datetime.combine(date.fromisoformat(day[:10]), time(hh, mm))
    return local - timedelta(hours=currency.utc_offset(country))


def _utc(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def event(booking: dict, manage_url: str) -> dict:
    guests = int(booking.get("guests") or 1)
    rooms = int(booking.get("rooms") or 1)
    room = (booking.get("room_name") or "Room") + (f" × {rooms}" if rooms > 1 else "")
    check_in = booking.get("check_in_time") or "14:00"
    check_out = booking.get("check_out_time") or "11:00"
    details = [f"Fichua booking {booking['reference']}: {room}, "
               f"{guests} guest{'' if guests == 1 else 's'}. Paid in full.",
               f"Check-in from {check_in}, check-out until {check_out}."]
    if booking.get("hotel_phone"):
        details.append(f"Hotel phone: {booking['hotel_phone']}")
    details.append(f"Manage your booking: {manage_url} (reference {booking['reference']} and your email)")
    return {
        "uid": f"{booking['id']}@fichua",
        "title": f"Stay at {booking['hotel_name']}",
        "start": _at(booking["check_in"], check_in, "14:00", booking.get("country")),
        "end": _at(booking["check_out"], check_out, "11:00", booking.get("country")),
        "location": booking.get("full_address") or booking.get("city") or "",
        "details": "\n".join(details),
    }


def _text(value: str) -> str:
    """RFC 5545 TEXT escaping."""
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Lines longer than 75 bytes continue on the next line after a space (RFC 5545 §3.1)."""
    parts, current = [], ""
    for ch in line:
        if len((current + ch).encode("utf-8")) > 75:
            parts.append(current)
            current = " " + ch
        else:
            current += ch
    parts.append(current)
    return "\r\n".join(parts)


def ics(booking: dict, manage_url: str, now: datetime | None = None) -> str:
    e = event(booking, manage_url)
    stamp = _utc(now or datetime.now(timezone.utc).replace(tzinfo=None))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Fichua//Bookings//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
             f"DTSTART:{_utc(e['start'])}", f"DTEND:{_utc(e['end'])}", f"SUMMARY:{_text(e['title'])}",
             f"LOCATION:{_text(e['location'])}", f"DESCRIPTION:{_text(e['details'])}", f"URL:{manage_url}",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def google_link(booking: dict, manage_url: str) -> str:
    e = event(booking, manage_url)
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": e["title"], "dates": f"{_utc(e['start'])}/{_utc(e['end'])}",
        "details": e["details"], "location": e["location"]})

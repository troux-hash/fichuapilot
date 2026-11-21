"""Stay-date logic: parsing, validation and the one-tap presets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MAX_NIGHTS = 30
MAX_GUESTS = 12
MAX_ROOMS = 8


@dataclass(frozen=True)
class Stay:
    check_in: date
    check_out: date
    guests: int
    rooms: int = 1  # rooms of the same type in one booking (IMP-18); the guests share them

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def as_params(self) -> dict:
        params = {
            "check_in": self.check_in.isoformat(),
            "check_out": self.check_out.isoformat(),
            "guests": self.guests,
        }
        if self.rooms > 1:  # one room is the default: links stay as they were
            params["rooms"] = self.rooms
        return params


def this_weekend(today: date) -> tuple[date, date]:
    """Friday→Sunday of this week; on Saturday it's tonight→Sunday; on Sunday, next weekend."""
    wd = today.weekday()  # Mon=0 … Sun=6
    if wd == 5:
        return today, today + timedelta(days=1)
    friday = today + timedelta(days=(4 - wd) % 7)
    return friday, friday + timedelta(days=2)


def presets(today: date | None = None) -> list[dict]:
    today = today or date.today()
    wk_in, wk_out = this_weekend(today)
    tomorrow = today + timedelta(days=1)
    items = [
        ("Tonight", today, tomorrow),
        ("This weekend", wk_in, wk_out),
        ("Next weekend", wk_in + timedelta(days=7), wk_out + timedelta(days=7)),
        ("A week away", tomorrow, tomorrow + timedelta(days=7)),
    ]
    return [{"label": l, "check_in": a.isoformat(), "check_out": b.isoformat()} for l, a, b in items]


def _parse(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_stay(check_in: str | None, check_out: str | None, guests: str | int | None,
               rooms: str | int | None = None, today: date | None = None) -> Stay:
    """Never fails: invalid or missing input falls back to sensible defaults."""
    today = today or date.today()
    ci, co = _parse(check_in), _parse(check_out)
    if ci is None or ci < today:
        ci, default_out = this_weekend(today)
        co = co if co and co > ci else default_out
    if co is None or co <= ci:
        co = ci + timedelta(days=1)
    if (co - ci).days > MAX_NIGHTS:
        co = ci + timedelta(days=MAX_NIGHTS)
    try:
        g = max(1, min(MAX_GUESTS, int(guests or 2)))
    except (TypeError, ValueError):
        g = 2
    try:
        r = int(rooms or 1)
    except (TypeError, ValueError):
        r = 1
    return Stay(ci, co, g, max(1, min(MAX_ROOMS, g, r)))  # every room has at least one guest


def _label(d: date) -> str:
    return d.strftime(f"%a {d.day} %b")


def adjustment(check_in: str | None, check_out: str | None, guests, stay: Stay,
               today: date | None = None, rooms=None) -> str | None:
    """One line saying how parse_stay changed what the guest asked for, or None if it kept it.

    parse_stay never fails, so impossible dates (in the past, check-out first, over 30 nights)
    quietly become a valid stay. Pages show this line so the guest knows which dates they see.
    """
    today = today or date.today()
    asked_in, asked_out = _parse(check_in), _parse(check_out)
    why = None
    if (check_in and asked_in is None) or (check_out and asked_out is None):
        why = "we couldn't read the dates"
    elif asked_in and asked_in < today:
        why = "check-in can't be in the past"
    elif asked_in and asked_out and asked_out <= asked_in:
        why = "check-out has to be after check-in"
    elif asked_in and asked_out and (asked_out - asked_in).days > MAX_NIGHTS:
        why = f"one booking covers up to {MAX_NIGHTS} nights"
    if why:
        return f"We changed your dates to {_label(stay.check_in)} – {_label(stay.check_out)}: {why}."
    try:
        asked_guests = int(guests) if guests not in (None, "") else None
    except (TypeError, ValueError):
        asked_guests = None
    if asked_guests is not None and asked_guests != stay.guests:
        return f"We changed the number of guests to {stay.guests}: one booking is for 1 to {MAX_GUESTS} guests."
    try:
        asked_rooms = int(rooms) if rooms not in (None, "") else None
    except (TypeError, ValueError):
        asked_rooms = None
    if asked_rooms is not None and asked_rooms != stay.rooms:
        why = (f"one booking is for up to {MAX_ROOMS} rooms" if asked_rooms > MAX_ROOMS
               else "each room needs at least one guest" if asked_rooms > stay.guests
               else "a booking has at least one room")
        return f"We changed the number of rooms to {stay.rooms}: {why}."
    return None

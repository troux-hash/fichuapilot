"""Stay-date logic: parsing, validation and the one-tap presets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MAX_NIGHTS = 30
MAX_GUESTS = 12


@dataclass(frozen=True)
class Stay:
    check_in: date
    check_out: date
    guests: int

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def as_params(self) -> dict:
        return {
            "check_in": self.check_in.isoformat(),
            "check_out": self.check_out.isoformat(),
            "guests": self.guests,
        }


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
               today: date | None = None) -> Stay:
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
        g = int(guests or 2)
    except (TypeError, ValueError):
        g = 2
    return Stay(ci, co, max(1, min(MAX_GUESTS, g)))

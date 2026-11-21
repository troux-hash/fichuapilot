"""Cancellation policies: what each one says, and the last day a stay can still be cancelled for free.

One rule for every page: the badge on a room, the checkout text, the guest's Cancel button and the
terms all come from here, so what Fichua promises is exactly what the Cancel button allows.
"""
from __future__ import annotations

from datetime import date, timedelta

POLICIES = {
    "flexible": ("Flexible", "Free cancellation until 24 hours before check-in."),
    "moderate": ("Moderate", "Free cancellation until 5 days before check-in."),
    "strict": ("Non-refundable", "No refund once booked."),
}
DAYS_BEFORE = {"flexible": 1, "moderate": 5}  # "strict" never has free cancellation


def _day(value: date | str) -> date:
    return date.fromisoformat(value[:10]) if isinstance(value, str) else value


def free_until(policy: str | None, free_cancellation, check_in: date | str) -> date | None:
    """The last day the guest can cancel for a full refund, or None when the rate is non-refundable.

    Dates, not hours: "24 hours before check-in" becomes the whole day before, so the guest gets
    a few hours more than the policy promises, never less.
    """
    if not free_cancellation:
        return None
    days = DAYS_BEFORE.get(policy or "flexible")
    if days is None:
        return None
    return _day(check_in) - timedelta(days=days)


def open_until(policy: str | None, free_cancellation, check_in: date | str,
               today: date | None = None) -> date | None:
    """free_until, but only while that day hasn't passed: what someone booking or cancelling today gets."""
    until = free_until(policy, free_cancellation, check_in)
    return until if until is not None and until >= (today or date.today()) else None


def timeline(policy: str | None, free_cancellation, check_in: date | str, total: float,
             today: date | None = None) -> list[dict]:
    """The rules beside the price, drawn as a bar (Brief 2: "plain rules beside the price"): what a
    cancellation refunds, in dollars, and until when. Each part's `days` sizes its share of the bar."""
    today = today or date.today()
    arrival = _day(check_in)
    until = open_until(policy, free_cancellation, arrival, today)
    parts = []
    if until:
        parts.append({"kind": "free", "label": "Free cancellation", "refund": total, "until": until,
                      "days": max(1, (until - today).days + 1)})
        after = until + timedelta(days=1)
        parts.append({"kind": "none", "label": "No refund", "refund": 0, "starts": after,
                      "days": max(1, (arrival - after).days)})
    else:
        parts.append({"kind": "none", "label": "No refund", "refund": 0, "starts": None, "days": 1})
    return parts

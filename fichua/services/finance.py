"""Admin finance: filters by hotel / country / period / source, totals and payouts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..db import Connection
from . import payments

PERIODS = {"week": "This week", "month": "This month", "last_month": "Last month", "all": "All time",
           "custom": "Custom dates"}


@dataclass
class FinanceFilter:
    period: str = "month"
    date_from: str = ""
    date_to: str = ""
    hotel_id: str = ""
    country: str = ""
    source: str = "fichua"   # fichua | offline | all

    @classmethod
    def from_query(cls, q) -> "FinanceFilter":
        period = q.get("period") or "month"
        return cls(period=period if period in PERIODS else "month", date_from=q.get("from") or "",
                   date_to=q.get("to") or "", hotel_id=q.get("hotel") or "", country=q.get("country") or "",
                   source=q.get("source") if q.get("source") in ("fichua", "offline", "all") else "fichua")

    def window(self) -> tuple[date | None, date | None]:
        today = date.today()
        if self.period == "week":
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=7)
        if self.period == "month":
            start = today.replace(day=1)
            return start, (start + timedelta(days=32)).replace(day=1)
        if self.period == "last_month":
            end = today.replace(day=1)
            return (end - timedelta(days=1)).replace(day=1), end
        if self.period == "custom":
            try:
                a = date.fromisoformat(self.date_from) if self.date_from else None
                b = date.fromisoformat(self.date_to) + timedelta(days=1) if self.date_to else None
                return a, b
            except ValueError:
                return None, None
        return None, None

    def label(self) -> str:
        start, end = self.window()
        if not start and not end:
            return PERIODS.get(self.period, "All time")
        end_incl = (end - timedelta(days=1)) if end else None
        return f"{start.strftime('%d %b %Y') if start else '…'} – {end_incl.strftime('%d %b %Y') if end_incl else '…'}"


def report(conn: Connection, f: FinanceFilter) -> dict:
    where = ["b.status IN ('confirmed', 'cancelled')"]
    params: dict = {}
    # Fichua bookings are counted when paid; offline ones when created.
    date_col = "COALESCE(b.paid_at, b.created_at)"
    start, end = f.window()
    # Plain dates compare correctly against both engines' timestamp formats.
    if start:
        where.append(f"{date_col} >= :start")
        params["start"] = start
    if end:
        where.append(f"{date_col} < :end")
        params["end"] = end
    if f.hotel_id:
        where.append("b.hotel_id = :hotel")
        params["hotel"] = f.hotel_id
    if f.country:
        where.append("h.country = :country")
        params["country"] = f.country
    if f.source in ("fichua", "offline"):
        where.append("b.source = :source")
        params["source"] = f.source
    rows = conn.all(
        "SELECT b.id, b.reference, b.status, b.source, b.payment_status, b.check_in, b.check_out, b.nights, b.rooms, "
        "b.total_price, b.commission_amount, b.payout_amount, b.commission_pct, b.paid_at, b.created_at, "
        "b.guest_name, b.offline_source, h.id AS hotel_id, h.name AS hotel_name, h.country, rt.name AS room_name, "
        "p.id AS payout_id, p.status AS payout_status, p.due_at AS payout_due, p.method AS payout_method, "
        "pay.provider, pay.provider_ref "
        "FROM bookings b JOIN hotels h ON h.id = b.hotel_id JOIN room_types rt ON rt.id = b.room_type_id "
        "LEFT JOIN payouts p ON p.booking_id = b.id LEFT JOIN payments pay ON pay.booking_id = b.id "
        f"WHERE {' AND '.join(where)} ORDER BY {date_col} DESC", params)
    totals = {"bookings": 0, "nights": 0, "gross": 0.0, "commission": 0.0, "payout_sent": 0.0,
              "payout_pending": 0.0, "refunded": 0.0, "offline_value": 0.0}
    for r in rows:
        r["stripe_url"] = payments.dashboard_url(r.get("provider_ref"))
        if r["source"] == "offline":
            if r["status"] == "confirmed":
                totals["offline_value"] += float(r["total_price"] or 0)
                totals["bookings"] += 1
                totals["nights"] += int(r["nights"])
            continue
        if r["payment_status"] == "refunded":
            totals["refunded"] += float(r["total_price"] or 0)
            continue
        if r["payment_status"] != "paid":
            continue
        totals["bookings"] += 1
        totals["nights"] += int(r["nights"])
        totals["gross"] += float(r["total_price"] or 0)
        totals["commission"] += float(r["commission_amount"] or 0)
        if r["payout_status"] == "sent":
            totals["payout_sent"] += float(r["payout_amount"] or 0)
        elif r["payout_status"] in ("scheduled", "due"):
            totals["payout_pending"] += float(r["payout_amount"] or 0)
    by_hotel: dict[str, dict] = {}
    for r in rows:
        if r["payment_status"] != "paid":
            continue
        h = by_hotel.setdefault(r["hotel_id"], {"hotel_name": r["hotel_name"], "country": r["country"],
                                                "bookings": 0, "gross": 0.0, "commission": 0.0})
        h["bookings"] += 1
        h["gross"] += float(r["total_price"] or 0)
        h["commission"] += float(r["commission_amount"] or 0)
    return {"rows": rows, "totals": totals,
            "by_hotel": sorted(by_hotel.values(), key=lambda h: -h["gross"])}


def payouts_due(conn: Connection) -> list[dict]:
    return conn.all(
        "SELECT p.*, h.name AS hotel_name, h.country, b.reference, b.check_in FROM payouts p "
        "JOIN hotels h ON h.id = p.hotel_id JOIN bookings b ON b.id = p.booking_id "
        "WHERE p.status IN ('scheduled', 'due', 'recover') ORDER BY p.due_at")

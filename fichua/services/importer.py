"""Excel import for hotel groups: Hotels / Rooms / Rates sheets → database.

All-or-nothing: the workbook is fully validated first; if any row is wrong nothing is
written and every problem is reported with its sheet and row number. Re-uploading the
same codes updates records (upsert), so hotels can send corrected files any time.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from ..db import Connection

MAX_RATE_SPAN_DAYS = 400

# column -> (required, type, help). Types: str, int, float, bool, date, list
SHEETS: dict[str, dict[str, tuple[bool, str, str]]] = {
    "Hotels": {
        "hotel_code": (True, "str", "Unique code you choose, e.g. NBO-001"),
        "hotel_group": (False, "str", "Owner group / chain"),
        "name": (True, "str", "Hotel name"),
        "city": (True, "str", "City guests search for"),
        "country": (False, "str", ""),
        "address": (False, "str", ""),
        "lat": (False, "float", "Latitude (for maps later)"),
        "lng": (False, "float", "Longitude"),
        "star_rating": (False, "int", "1-5"),
        "guest_rating": (False, "float", "0-10"),
        "review_count": (False, "int", ""),
        "property_type": (False, "str", "Hotel, Resort, Boutique, Apartment, Lodge…"),
        "description": (False, "str", ""),
        "amenities": (False, "list", "Comma separated: Pool, Free WiFi, Spa…"),
        "image_urls": (False, "list", "Comma separated image links"),
        "currency": (False, "str", "ISO code, default USD"),
        "check_in_time": (False, "str", "e.g. 14:00"),
        "check_out_time": (False, "str", "e.g. 11:00"),
        "is_active": (False, "bool", "yes/no, default yes"),
    },
    "Rooms": {
        "room_code": (True, "str", "Unique code, e.g. NBO-001-DLX"),
        "hotel_code": (True, "str", "Must exist in Hotels sheet or database"),
        "name": (True, "str", "Deluxe King Room"),
        "max_guests": (True, "int", "Max people in the room"),
        "bed_type": (False, "str", "1 King bed"),
        "size_sqm": (False, "int", ""),
        "description": (False, "str", ""),
        "amenities": (False, "list", "Comma separated"),
        "image_urls": (False, "list", "Comma separated"),
        "breakfast_included": (False, "bool", "yes/no"),
        "free_cancellation": (False, "bool", "yes/no, default yes"),
    },
    "Rates": {
        "room_code": (True, "str", "Must exist in Rooms sheet or database"),
        "date_from": (True, "date", "First night, YYYY-MM-DD"),
        "date_to": (True, "date", "Last night (inclusive)"),
        "price": (True, "float", "Price per night"),
        "units": (True, "int", "Rooms available to sell each night"),
    },
}


@dataclass
class ImportResult:
    errors: list[str] = field(default_factory=list)
    hotels: int = 0
    rooms: int = 0
    rate_nights: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _norm_header(value) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _convert(value, kind: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if kind == "str":
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()
    if kind == "int":
        f = float(value)
        if not f.is_integer():
            raise ValueError("must be a whole number")
        return int(f)
    if kind == "float":
        return float(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"yes", "y", "true", "1"}:
            return True
        if s in {"no", "n", "false", "0"}:
            return False
        raise ValueError("must be yes or no")
    if kind == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value).strip()[:10])
    if kind == "list":
        return ", ".join(v.strip() for v in str(value).split(",") if v.strip())
    raise ValueError(kind)


def _read_sheet(wb, name: str, result: ImportResult) -> list[tuple[int, dict]]:
    spec = SHEETS[name]
    sheet_name = next((s for s in wb.sheetnames if s.strip().lower() == name.lower()), None)
    if sheet_name is None:
        if name == "Rates":
            return []  # rates are optional on an upload that only updates hotel info
        result.errors.append(f"Missing sheet '{name}'.")
        return []
    rows = wb[sheet_name].iter_rows(values_only=True)
    headers = [_norm_header(h) for h in next(rows, [])]
    missing = [c for c, (req, _, _) in spec.items() if req and c not in headers]
    if missing:
        result.errors.append(f"{name}: missing column(s) {', '.join(missing)}.")
        return []
    out = []
    for i, raw in enumerate(rows, start=2):
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        record, bad = {}, False
        for col, (req, kind, _) in spec.items():
            if col not in headers:
                continue
            idx = headers.index(col)
            value = raw[idx] if idx < len(raw) else None
            try:
                record[col] = _convert(value, kind)
            except (ValueError, TypeError) as exc:
                result.errors.append(f"{name} row {i}: '{col}' {exc if str(exc) else 'is invalid'} (got {value!r}).")
                bad = True
                continue
            if req and record[col] is None:
                result.errors.append(f"{name} row {i}: '{col}' is required.")
                bad = True
        if not bad:
            out.append((i, record))
    return out


def _validate(hotels, rooms, rates, conn: Connection, result: ImportResult) -> None:
    hotel_codes = {h["hotel_code"] for _, h in hotels}
    room_codes = {r["room_code"] for _, r in rooms}
    for i, h in hotels:
        sr, gr = h.get("star_rating"), h.get("guest_rating")
        if sr is not None and not 1 <= sr <= 5:
            result.errors.append(f"Hotels row {i}: star_rating must be 1-5.")
        if gr is not None and not 0 <= gr <= 10:
            result.errors.append(f"Hotels row {i}: guest_rating must be 0-10.")
    for i, r in rooms:
        if r["hotel_code"] not in hotel_codes and not conn.scalar(
                "SELECT COUNT(*) FROM hotels WHERE id = :id", {"id": r["hotel_code"]}):
            result.errors.append(f"Rooms row {i}: unknown hotel_code '{r['hotel_code']}'.")
        if r["max_guests"] < 1:
            result.errors.append(f"Rooms row {i}: max_guests must be at least 1.")
    for i, r in rates:
        if r["room_code"] not in room_codes and not conn.scalar(
                "SELECT COUNT(*) FROM room_types WHERE id = :id", {"id": r["room_code"]}):
            result.errors.append(f"Rates row {i}: unknown room_code '{r['room_code']}'.")
        span = (r["date_to"] - r["date_from"]).days
        if span < 0:
            result.errors.append(f"Rates row {i}: date_to is before date_from.")
        elif span > MAX_RATE_SPAN_DAYS:
            result.errors.append(f"Rates row {i}: range longer than {MAX_RATE_SPAN_DAYS} days.")
        if r["price"] <= 0:
            result.errors.append(f"Rates row {i}: price must be positive.")
        if r["units"] < 0:
            result.errors.append(f"Rates row {i}: units cannot be negative.")


HOTEL_UPSERT = """
INSERT INTO hotels (id, hotel_group, name, city, country, address, lat, lng, star_rating,
    guest_rating, review_count, property_type, description, amenities, image_urls, currency,
    check_in_time, check_out_time, is_active)
VALUES (:hotel_code, :hotel_group, :name, :city, :country, :address, :lat, :lng, :star_rating,
    :guest_rating, :review_count, :property_type, :description, :amenities, :image_urls,
    :currency, :check_in_time, :check_out_time, :is_active)
ON CONFLICT (id) DO UPDATE SET hotel_group = excluded.hotel_group, name = excluded.name,
    city = excluded.city, country = excluded.country, address = excluded.address,
    lat = excluded.lat, lng = excluded.lng, star_rating = excluded.star_rating,
    guest_rating = excluded.guest_rating, review_count = excluded.review_count,
    property_type = excluded.property_type, description = excluded.description,
    amenities = excluded.amenities, image_urls = excluded.image_urls,
    currency = excluded.currency, check_in_time = excluded.check_in_time,
    check_out_time = excluded.check_out_time, is_active = excluded.is_active,
    updated_at = CURRENT_TIMESTAMP
"""

ROOM_UPSERT = """
INSERT INTO room_types (id, hotel_id, name, max_guests, bed_type, size_sqm, description,
    amenities, image_urls, breakfast_included, free_cancellation)
VALUES (:room_code, :hotel_code, :name, :max_guests, :bed_type, :size_sqm, :description,
    :amenities, :image_urls, :breakfast_included, :free_cancellation)
ON CONFLICT (id) DO UPDATE SET hotel_id = excluded.hotel_id, name = excluded.name,
    max_guests = excluded.max_guests, bed_type = excluded.bed_type,
    size_sqm = excluded.size_sqm, description = excluded.description,
    amenities = excluded.amenities, image_urls = excluded.image_urls,
    breakfast_included = excluded.breakfast_included,
    free_cancellation = excluded.free_cancellation
"""

RATE_UPSERT = """
INSERT INTO room_rates (room_type_id, stay_date, price, units)
VALUES (:room_code, :stay_date, :price, :units)
ON CONFLICT (room_type_id, stay_date) DO UPDATE SET price = excluded.price, units = excluded.units
"""


def _with_defaults(record: dict, spec: dict, defaults: dict) -> dict:
    full = {col: record.get(col) for col in spec}
    for k, v in defaults.items():
        if full.get(k) is None:
            full[k] = v
    return full


def import_workbook(conn: Connection, data: bytes) -> ImportResult:
    result = ImportResult()
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        result.errors.append("That file isn't a readable .xlsx workbook.")
        return result

    hotels = _read_sheet(wb, "Hotels", result)
    rooms = _read_sheet(wb, "Rooms", result)
    rates = _read_sheet(wb, "Rates", result)
    if not result.errors:
        _validate(hotels, rooms, rates, conn, result)
    if result.errors:
        return result

    conn.run_many(HOTEL_UPSERT, [
        _with_defaults(h, SHEETS["Hotels"], {"is_active": True, "currency": "USD", "review_count": 0})
        for _, h in hotels])
    conn.run_many(ROOM_UPSERT, [
        _with_defaults(r, SHEETS["Rooms"], {"breakfast_included": False, "free_cancellation": True})
        for _, r in rooms])
    nights = []
    for _, r in rates:
        d = r["date_from"]
        while d <= r["date_to"]:
            nights.append({"room_code": r["room_code"], "stay_date": d,
                           "price": round(r["price"], 2), "units": r["units"]})
            d += timedelta(days=1)
    conn.run_many(RATE_UPSERT, nights)

    result.hotels, result.rooms, result.rate_nights = len(hotels), len(rooms), len(nights)
    return result


def template_workbook(examples: dict[str, list[list]] | None = None) -> bytes:
    """An .xlsx with the three sheets, styled headers, a help row-comment and optional rows."""
    wb = Workbook()
    wb.remove(wb.active)
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="0E1B33")
    req_fill = PatternFill("solid", fgColor="FF5A3C")

    readme = wb.create_sheet("Instructions")
    lines = [
        "Fichua hotel data template",
        "",
        "1. Fill the Hotels, Rooms and Rates sheets. Orange headers are required.",
        "2. Codes (hotel_code, room_code) are yours to choose and must be unique. Re-uploading a code updates it.",
        "3. Rates: one row per room per date range. Price is per night; units = rooms you can sell each night.",
        "4. Lists (amenities, image_urls) are comma separated.",
        "5. Upload in Admin → Upload Excel. Nothing is saved if any row has an error; you'll see exactly which.",
        "",
        "Column guide:",
    ]
    for line in lines:
        readme.append([line])
    for sheet, spec in SHEETS.items():
        for col, (req, kind, help_) in spec.items():
            readme.append([f"{sheet}.{col}", "required" if req else "optional", kind, help_])
    readme["A1"].font = Font(bold=True, size=14)
    readme.column_dimensions["A"].width = 32
    readme.column_dimensions["D"].width = 50

    for sheet, spec in SHEETS.items():
        ws = wb.create_sheet(sheet)
        ws.append(list(spec))
        for cell, (req, _, _) in zip(ws[1], spec.values()):
            cell.font = head_font
            cell.fill = req_fill if req else head_fill
            ws.column_dimensions[cell.column_letter].width = max(14, len(cell.value) + 4)
        for row in (examples or {}).get(sheet, []):
            ws.append(row)
        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

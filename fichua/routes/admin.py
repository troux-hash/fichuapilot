"""Back-office: login, Excel upload, template download, hotels and bookings."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from .. import auth
from ..config import settings
from ..db import db
from ..services import bookings, importer
from ..web import render

router = APIRouter(prefix="/admin")


def _guard(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _stats(conn) -> dict:
    return {
        "hotels": conn.scalar("SELECT COUNT(*) FROM hotels"),
        "rooms": conn.scalar("SELECT COUNT(*) FROM room_types"),
        "rate_nights": conn.scalar("SELECT COUNT(*) FROM room_rates"),
        "bookings": conn.scalar("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'"),
        "last_rate_date": conn.scalar("SELECT MAX(stay_date) FROM room_rates"),
    }


@router.get("/login")
def login_form(request: Request):
    return render(request, "admin/login.html", error=None,
                  disabled=not settings.admin_password)


@router.post("/login")
def login(request: Request, password: str = Form("")):
    if not auth.check_password(password):
        return render(request, "admin/login.html", status_code=401,
                      error="Wrong password.", disabled=not settings.admin_password)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.TTL_SECONDS, httponly=True,
                    samesite="lax", secure=settings.is_production)
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


@router.get("")
def dashboard(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        stats = _stats(conn)
    return render(request, "admin/dashboard.html", stats=stats, result=None,
                  max_mb=settings.max_upload_mb)


@router.post("/upload")
async def upload(request: Request, file: UploadFile):
    if (r := _guard(request)):
        return r
    data = await file.read()
    result = importer.ImportResult()
    if not (file.filename or "").lower().endswith(".xlsx"):
        result.errors.append("Please upload an .xlsx file (Excel 2007+).")
    elif len(data) > settings.max_upload_mb * 1024 * 1024:
        result.errors.append(f"File is larger than {settings.max_upload_mb} MB. Split it into smaller files.")
    with db.connect() as conn:
        if not result.errors:
            result = importer.import_workbook(conn, data)
            if not result.ok:
                conn.raw.rollback()
        stats = _stats(conn)
    return render(request, "admin/dashboard.html", stats=stats, result=result,
                  filename=file.filename, max_mb=settings.max_upload_mb,
                  status_code=200 if result.ok else 422)


@router.get("/template.xlsx")
def template(request: Request):
    if (r := _guard(request)):
        return r
    return Response(importer.template_workbook(), headers={
        "Content-Disposition": 'attachment; filename="fichua_hotel_template.xlsx"'},
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/hotels")
def hotels(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = conn.all(
            "SELECT h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, h.guest_rating, "
            "h.is_active, COUNT(rt.id) AS rooms FROM hotels h "
            "LEFT JOIN room_types rt ON rt.hotel_id = h.id "
            "GROUP BY h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, "
            "h.guest_rating, h.is_active ORDER BY h.city, h.name")
    return render(request, "admin/hotels.html", hotels=rows)


@router.post("/hotels/{hotel_id}/toggle")
def toggle_hotel(request: Request, hotel_id: str):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        conn.run("UPDATE hotels SET is_active = NOT is_active WHERE id = :id", {"id": hotel_id})
    return RedirectResponse("/admin/hotels", status_code=303)


@router.get("/bookings")
def booking_list(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = bookings.list_bookings(conn)
    return render(request, "admin/bookings.html", bookings=rows)

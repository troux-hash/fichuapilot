"""Fichua Admin: dashboard, approvals, hotels, finance, messages, access codes, settings, Excel."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from .. import auth
from ..config import settings
from ..db import db, utcnow
from ..services import app_settings, currency, finance, importer, notify, partners, payments, payouts
from ..web import forget_rates, render

router = APIRouter(prefix="/admin")


def _guard(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _pending_count(conn) -> int:
    return conn.scalar("SELECT COUNT(*) FROM hotels WHERE status = 'pending'") or 0


def _page(request: Request, conn, template: str, active: str, status_code: int = 200, **ctx):
    return render(request, template, status_code=status_code, active=active, pending=_pending_count(conn),
                  payments_mode=payments.provider(), whatsapp_ready=notify.whatsapp_ready(), **ctx)


@router.get("/login")
def login_form(request: Request):
    return render(request, "admin/login.html", error=None, disabled=not settings.admin_password)


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


# --------------------------------------------------------------------------- dashboard & Excel

def _stats(conn) -> dict:
    month = finance.report(conn, finance.FinanceFilter(period="month"))["totals"]
    return {
        "live_hotels": conn.scalar("SELECT COUNT(*) FROM hotels WHERE is_active = TRUE"),
        "pending": _pending_count(conn),
        "rooms": conn.scalar("SELECT COALESCE(SUM(total_rooms), 0) FROM room_types rt JOIN hotels h "
                             "ON h.id = rt.hotel_id WHERE h.is_active = TRUE"),
        "month": month,
        "payouts_due": len(finance.payouts_due(conn)),
    }


@router.get("")
def dashboard(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        payouts.process_due(conn)
        return _page(request, conn, "admin/dashboard.html", "dashboard", stats=_stats(conn), result=None,
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
        return _page(request, conn, "admin/dashboard.html", "dashboard", stats=_stats(conn), result=result,
                     filename=file.filename, max_mb=settings.max_upload_mb, status_code=200 if result.ok else 422)


@router.get("/template.xlsx")
def template(request: Request):
    if (r := _guard(request)):
        return r
    return Response(importer.template_workbook(), headers={
        "Content-Disposition": 'attachment; filename="fichua_hotel_template.xlsx"'},
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# --------------------------------------------------------------------------- approvals

@router.get("/approvals")
def approvals(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = conn.all("SELECT h.*, u.name AS owner_name, u.email AS owner_email FROM hotels h "
                        "LEFT JOIN partner_users u ON u.id = h.owner_id WHERE h.status IN ('pending', 'changes', 'draft') "
                        "ORDER BY CASE h.status WHEN 'pending' THEN 0 WHEN 'changes' THEN 1 ELSE 2 END, h.submitted_at")
        return _page(request, conn, "admin/approvals.html", "approvals", hotels=rows)


def _review_context(conn, hotel_id: str) -> dict | None:
    hotel = conn.one("SELECT h.*, u.name AS owner_name, u.email AS owner_email, u.phone AS owner_phone, "
                     "u.access_code FROM hotels h LEFT JOIN partner_users u ON u.id = h.owner_id WHERE h.id = :id",
                     {"id": hotel_id})
    if not hotel:
        return None
    from ..services import catalog
    hotel = catalog.hydrate_hotel(hotel, catalog.media_urls(conn, "hotel", [hotel_id]).get(hotel_id))
    return {"hotel": hotel, "rooms": partners.hotel_room_list(conn, hotel_id),
            "checks": partners.review_checks(conn, hotel), "status": partners.onboarding_status(conn, hotel),
            "default_commission": app_settings.get(conn, "commission_pct"), "policies": partners.POLICIES}


@router.get("/approvals/{hotel_id}")
def approval_detail(request: Request, hotel_id: str):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        ctx = _review_context(conn, hotel_id)
        if not ctx:
            return RedirectResponse("/admin/approvals", status_code=303)
        return _page(request, conn, "admin/approval_detail.html", "approvals", decided=request.query_params.get("decided"), **ctx)


@router.post("/approvals/{hotel_id}")
def approval_decide(request: Request, hotel_id: str, action: str = Form(...), commission: str = Form(""),
                    note: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        hotel = conn.one("SELECT * FROM hotels WHERE id = :id", {"id": hotel_id})
        if not hotel or action not in ("approve", "changes", "reject"):
            return RedirectResponse("/admin/approvals", status_code=303)
        try:
            pct = float(commission) if commission.strip() else None
        except ValueError:
            pct = None
        if action == "approve":
            conn.run("UPDATE hotels SET status = 'live', is_active = TRUE, approved_at = :t, commission_pct = :p, "
                     "review_note = :n WHERE id = :id", {"t": utcnow(), "p": pct, "n": note.strip(), "id": hotel_id})
            notify.hotel_decision(conn, hotel, "approved")
        elif action == "changes":
            conn.run("UPDATE hotels SET status = 'changes', is_active = FALSE, review_note = :n WHERE id = :id",
                     {"n": note.strip() or "Please review your listing.", "id": hotel_id})
            notify.hotel_decision(conn, hotel, "changes", note.strip() or "Please review your listing.")
        else:
            conn.run("UPDATE hotels SET status = 'rejected', is_active = FALSE, review_note = :n WHERE id = :id",
                     {"n": note.strip(), "id": hotel_id})
            notify.hotel_decision(conn, hotel, "rejected", note.strip())
    with db.connect() as conn:
        notify.flush(conn)
    return RedirectResponse(f"/admin/approvals/{hotel_id}?decided={action}", status_code=303)


# --------------------------------------------------------------------------- hotels

@router.get("/hotels")
def hotels(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = conn.all(
            "SELECT h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, h.guest_rating, h.status, "
            "h.is_active, h.commission_pct, h.plan, h.manager_free_until, COUNT(rt.id) AS rooms FROM hotels h "
            "LEFT JOIN room_types rt ON rt.hotel_id = h.id "
            "GROUP BY h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, h.guest_rating, h.status, "
            "h.is_active, h.commission_pct, h.plan, h.manager_free_until ORDER BY h.country, h.city, h.name")
        return _page(request, conn, "admin/hotels.html", "hotels", hotels=rows,
                     default_commission=app_settings.get(conn, "commission_pct"))


@router.post("/hotels/{hotel_id}/toggle")
def toggle_hotel(request: Request, hotel_id: str):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        conn.run("UPDATE hotels SET is_active = NOT is_active WHERE id = :id AND status = 'live'", {"id": hotel_id})
    return RedirectResponse("/admin/hotels", status_code=303)


# --------------------------------------------------------------------------- finance & payouts

@router.get("/finance")
def finance_page(request: Request):
    if (r := _guard(request)):
        return r
    f = finance.FinanceFilter.from_query(request.query_params)
    with db.connect() as conn:
        payouts.process_due(conn)
        data = finance.report(conn, f)
        hotels_list = conn.all("SELECT id, name, country FROM hotels WHERE status = 'live' ORDER BY name")
        return _page(request, conn, "admin/finance.html", "finance", f=f, periods=finance.PERIODS,
                     hotels=hotels_list, countries=currency.MARKETS, due=finance.payouts_due(conn),
                     stripe_test=payments.is_stripe_test_mode(), **data)


@router.post("/payouts/{payout_id}/sent")
def payout_sent(request: Request, payout_id: str, note: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        payouts.mark_sent(conn, payout_id, note)
    return RedirectResponse("/admin/finance", status_code=303)


@router.post("/payouts/run")
def payouts_run(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        payouts.process_due(conn)
    return RedirectResponse("/admin/finance", status_code=303)


# --------------------------------------------------------------------------- messages

@router.get("/messages")
def messages(request: Request):
    if (r := _guard(request)):
        return r
    role = request.query_params.get("role") or ""
    with db.connect() as conn:
        sql = "SELECT m.*, h.name AS hotel_name FROM messages m LEFT JOIN hotels h ON h.id = m.hotel_id"
        params = {}
        if role in ("guest", "hotel", "admin"):
            sql += " WHERE m.role = :role"
            params["role"] = role
        rows = conn.all(sql + " ORDER BY m.created_at DESC LIMIT 200", params)
        return _page(request, conn, "admin/messages.html", "messages", rows=rows, role=role,
                     admin_whatsapp=app_settings.get(conn, "admin_whatsapp"))


@router.post("/messages/retry")
def messages_retry(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        conn.run("UPDATE messages SET status = 'queued' WHERE status IN ('failed', 'not_sent')")
        notify.flush(conn, limit=50)
    return RedirectResponse("/admin/messages", status_code=303)


# --------------------------------------------------------------------------- access codes

@router.get("/codes")
def codes(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = conn.all("SELECT * FROM access_codes ORDER BY created_at DESC")
        return _page(request, conn, "admin/codes.html", "codes", codes=rows, error=None, created=request.query_params.get("created"))


@router.post("/codes")
def codes_create(request: Request, code: str = Form(""), plan: str = Form("manager"), free_until: str = Form(""),
                 max_uses: str = Form("1"), expires_on: str = Form(""), note: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        try:
            created = partners.create_code(
                conn, code=code, plan=plan, max_uses=int(max_uses or 1), note=note,
                free_until=date.fromisoformat(free_until) if free_until else None,
                expires_on=date.fromisoformat(expires_on) if expires_on else None)
        except (partners.PartnerError, ValueError) as exc:
            conn.raw.rollback()
            rows = conn.all("SELECT * FROM access_codes ORDER BY created_at DESC")
            return _page(request, conn, "admin/codes.html", "codes", status_code=422, codes=rows, created=None,
                         error=str(exc) if isinstance(exc, partners.PartnerError) else "Check the dates and number of uses.")
    return RedirectResponse(f"/admin/codes?created={created}", status_code=303)


@router.post("/codes/{code}/toggle")
def codes_toggle(request: Request, code: str):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        conn.run("UPDATE access_codes SET is_active = NOT is_active WHERE code = :c", {"c": code})
    return RedirectResponse("/admin/codes", status_code=303)


# --------------------------------------------------------------------------- settings

@router.get("/settings")
def settings_page(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        return _page(request, conn, "admin/settings.html", "settings", values=app_settings.all_settings(conn),
                     timings=app_settings.PAYOUT_TIMINGS, saved=request.query_params.get("saved"), errors=[])


@router.post("/settings")
async def settings_save(request: Request):
    if (r := _guard(request)):
        return r
    form = await request.form()
    errors = []
    numeric = {"commission_pct": (0, 50), "payout_delay_hours": (0, 720), "rate_RWF": (1, 100000),
               "rate_XOF": (1, 100000), "manager_fee_usd": (0, 10000), "hold_minutes": (10, 120)}
    with db.connect() as conn:
        for key, (lo, hi) in numeric.items():
            raw = (form.get(key) or "").replace(",", "").strip()
            try:
                value = float(raw)
                if not lo <= value <= hi:
                    raise ValueError
                app_settings.put(conn, key, f"{value:g}")
            except ValueError:
                errors.append(f"{key.replace('_', ' ').capitalize()} must be a number between {lo} and {hi}.")
        timing = form.get("payout_timing")
        if timing in app_settings.PAYOUT_TIMINGS:
            app_settings.put(conn, "payout_timing", timing)
        app_settings.put(conn, "admin_whatsapp", (form.get("admin_whatsapp") or "").strip())
        if errors:
            conn.raw.rollback()
            return _page(request, conn, "admin/settings.html", "settings", status_code=422, errors=errors,
                         values={**app_settings.all_settings(conn), **{k: form.get(k) for k in form.keys()}},
                         timings=app_settings.PAYOUT_TIMINGS, saved=None)
    forget_rates()
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.post("/partners/{hotel_id}/password")
def reset_partner_password(request: Request, hotel_id: str, password: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        owner = conn.scalar("SELECT owner_id FROM hotels WHERE id = :id", {"id": hotel_id})
        if owner and len(password) >= 8:
            partners.set_password(conn, owner, password)
    return RedirectResponse(f"/admin/approvals/{hotel_id}?decided=password", status_code=303)

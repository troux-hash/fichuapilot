"""Fichua Admin: dashboard, approvals, hotels, finance, messages, access codes, settings, Excel."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from .. import auth
from ..config import settings
from ..db import db, utcnow
from ..services import (admins, app_settings, currency, finance, importer, notify, partners, payments, payouts,
                        ratelimit, totp)
from ..web import base_url, forget_rates, render

router = APIRouter(prefix="/admin")


def _me(conn, request: Request) -> dict | None:
    return admins.current(conn, auth.admin_subject(request))


def _guard(request: Request):
    with db.connect() as conn:
        if _me(conn, request) is None:
            return RedirectResponse("/admin/login", status_code=303)
    return None


def _pending_count(conn) -> int:
    return conn.scalar("SELECT COUNT(*) FROM hotels WHERE status = 'pending'") or 0


def _page(request: Request, conn, template: str, active: str, status_code: int = 200, **ctx):
    return render(request, template, status_code=status_code, active=active, pending=_pending_count(conn),
                  payments_mode=payments.provider(), whatsapp_ready=notify.whatsapp_ready(),
                  me=_me(conn, request), **ctx)


def _login_page(request: Request, conn, status_code: int = 200, error: str | None = None, email: str = ""):
    named = admins.count_active(conn) > 0
    return render(request, "admin/login.html", status_code=status_code, error=error, named=named, email=email,
                  created=request.query_params.get("created"), disabled=not named and not settings.admin_password)


@router.get("/login")
def login_form(request: Request):
    with db.connect() as conn:
        return _login_page(request, conn)


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form(""), code: str = Form("")):
    ip = ratelimit.client_ip(request)
    with db.connect() as conn:
        if ratelimit.blocked(conn, "admin", ip):
            return _login_page(request, conn, 429, ratelimit.MESSAGES["admin"], email)
        if admins.count_active(conn):  # named accounts only, from the first one on
            user = admins.authenticate(conn, email, password, code)
            user_id = user["id"] if user else None
            ok, error = bool(user), "Wrong email, password or code."
        else:
            user_id, ok, error = None, auth.check_password(password), "Wrong password."
        if not ok:
            ratelimit.record(conn, "admin", ip)
            return _login_page(request, conn, 401, error, email)
        ratelimit.clear(conn, "admin", ip)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(auth.COOKIE, auth.make_token(user_id), max_age=auth.TTL_SECONDS, httponly=True,
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
    # The host profile goes public once the owner ticks consent: the reviewer sees it either way.
    host = None
    if (hotel.get("host_name") or "").strip():
        host = catalog.host_profile({**hotel, "host_consent_at": hotel.get("host_consent_at") or "pending"},
                                    (catalog.media_urls(conn, "host", [hotel_id]).get(hotel_id) or [None])[0])
        host["public"] = bool(hotel.get("host_consent_at"))
    return {"hotel": hotel, "host": host, "rooms": partners.hotel_room_list(conn, hotel_id),
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


def _commission(text: str) -> tuple[float | None, bool]:
    """(percentage or None for the default, True if the text isn't a valid 0-50% commission)."""
    if not text.strip():
        return None, False
    try:
        pct = float(text.replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None, True
    return (pct, False) if 0 <= pct <= 50 else (None, True)


DECISIONS = ("approve", "changes", "reject")
LIVE_ACTIONS = ("commission", "hide", "show")  # what a live hotel's page offers instead (IMP-12)


@router.post("/approvals/{hotel_id}")
def approval_decide(request: Request, hotel_id: str, action: str = Form(...), commission: str = Form(""),
                    note: str = Form("")):
    if (r := _guard(request)):
        return r
    back = f"/admin/approvals/{hotel_id}"
    with db.connect() as conn:
        hotel = conn.one("SELECT * FROM hotels WHERE id = :id", {"id": hotel_id})
        if not hotel or action not in DECISIONS + LIVE_ACTIONS:
            return RedirectResponse("/admin/approvals", status_code=303)
        live = hotel["status"] == "live"
        if (action in LIVE_ACTIONS) != live or (action == "approve" and live):
            return RedirectResponse(back, status_code=303)  # stale page: show what applies now
        pct, bad = _commission(commission)
        if bad and action in ("approve", "commission"):
            return RedirectResponse(f"{back}?decided=bad-commission", status_code=303)
        if action in LIVE_ACTIONS:
            if action == "commission":
                conn.run("UPDATE hotels SET commission_pct = :p WHERE id = :id", {"p": pct, "id": hotel_id})
            else:
                conn.run("UPDATE hotels SET is_active = :on WHERE id = :id", {"on": action == "show", "id": hotel_id})
            return RedirectResponse(f"{back}?decided={action}", status_code=303)
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

HOTEL_STATUSES = {"live": "Live", "hidden": "Hidden", "pending": "Waiting for approval",
                  "changes": "Changes requested", "draft": "Onboarding", "rejected": "Rejected"}


@router.get("/hotels")
def hotels(request: Request):
    if (r := _guard(request)):
        return r
    q = request.query_params
    f = {"q": (q.get("q") or "").strip(), "status": q.get("status") or "", "country": q.get("country") or "",
         "group": q.get("group") or ""}
    where, params = [], {}
    if f["q"]:  # name, hotel ID or city
        where.append("(LOWER(h.name) LIKE :q OR LOWER(h.id) LIKE :q OR LOWER(h.city) LIKE :q)")
        params["q"] = f"%{f['q'].lower()}%"
    if f["status"] == "live":
        where.append("h.status = 'live' AND h.is_active = TRUE")
    elif f["status"] == "hidden":
        where.append("h.status = 'live' AND h.is_active = FALSE")
    elif f["status"] in HOTEL_STATUSES:
        where.append("h.status = :status")
        params["status"] = f["status"]
    if f["country"]:
        where.append("h.country = :country")
        params["country"] = f["country"]
    if f["group"]:
        where.append("h.hotel_group = :grp")
        params["grp"] = f["group"]
    with db.connect() as conn:
        rows = conn.all(
            "SELECT h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, h.guest_rating, h.status, "
            "h.is_active, h.commission_pct, h.plan, h.manager_free_until, COUNT(rt.id) AS rooms FROM hotels h "
            "LEFT JOIN room_types rt ON rt.hotel_id = h.id "
            + (f"WHERE {' AND '.join(where)} " if where else "")
            + "GROUP BY h.id, h.name, h.city, h.country, h.hotel_group, h.star_rating, h.guest_rating, h.status, "
            "h.is_active, h.commission_pct, h.plan, h.manager_free_until ORDER BY h.country, h.city, h.name", params)
        countries = [r["country"] for r in conn.all(
            "SELECT DISTINCT country FROM hotels WHERE country IS NOT NULL AND country <> '' ORDER BY country")]
        groups = [r["hotel_group"] for r in conn.all(
            "SELECT DISTINCT hotel_group FROM hotels WHERE hotel_group IS NOT NULL AND hotel_group <> '' "
            "ORDER BY hotel_group")]
        return _page(request, conn, "admin/hotels.html", "hotels", hotels=rows, f=f, filtered=any(f.values()),
                     total=conn.scalar("SELECT COUNT(*) FROM hotels"), statuses=HOTEL_STATUSES,
                     countries=countries, groups=groups, default_commission=app_settings.get(conn, "commission_pct"))


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

def _with_invites(request: Request, rows: list[dict]) -> list[dict]:
    """Each code's partner link, and a WhatsApp link that opens a chat with the invite written (IMP-15)."""
    base, today = base_url(request), date.today().isoformat()
    for c in rows:
        c["invite_url"] = f"{base}/partners?{urlencode({'code': c['code']})}"
        c["whatsapp_url"] = "https://wa.me/?" + urlencode(
            {"text": partners.invite_text(c["code"], c["invite_url"])}, quote_via=quote)
        c["can_share"] = bool(c["is_active"]) and c["uses"] < c["max_uses"] and not (
            c["expires_on"] and c["expires_on"] < today)
    return rows


@router.get("/codes")
def codes(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        rows = _with_invites(request, conn.all("SELECT * FROM access_codes ORDER BY created_at DESC"))
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
            rows = _with_invites(request, conn.all("SELECT * FROM access_codes ORDER BY created_at DESC"))
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
    # key: (label, lowest, highest, unit) — the label and unit make the error read like the form.
    numeric = {"commission_pct": ("Default commission", 0, 50, "%"),
               "payout_delay_hours": ("Hours after check-in", 0, 720, " hours"),
               "rate_RWF": ("The Rwandan franc rate", 1, 100000, ""),
               "rate_XOF": ("The CFA franc rate", 1, 100000, ""),
               "manager_fee_usd": ("The Hotel Manager fee", 0, 10000, " USD"),
               "hold_minutes": ("The room hold", 10, 120, " minutes")}
    with db.connect() as conn:
        for key, (label, lo, hi, unit) in numeric.items():
            raw = (form.get(key) or "").replace(",", "").strip()
            try:
                value = float(raw)
                if not lo <= value <= hi:
                    raise ValueError
                app_settings.put(conn, key, f"{value:g}")
            except ValueError:
                errors.append(f"{label} must be between {lo}{unit} and {hi}{unit}.")
        timing = form.get("payout_timing")
        if timing in app_settings.PAYOUT_TIMINGS:
            app_settings.put(conn, "payout_timing", timing)
        app_settings.put(conn, "admin_whatsapp", (form.get("admin_whatsapp") or "").strip())
        email = (form.get("contact_email") or "").strip()
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("Enter the contact email like name@company.com.")
        app_settings.put(conn, "contact_email", email[:160])
        app_settings.put(conn, "company_name", (form.get("company_name") or "").strip()[:120] or "Fichua")
        app_settings.put(conn, "company_address", (form.get("company_address") or "").strip()[:200])
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


# --------------------------------------------------------------------------- team (named admins, two-step login)

def _team(request: Request, conn, status_code: int = 200, errors: list | None = None, setup: dict | None = None,
          form: dict | None = None):
    return _page(request, conn, "admin/team.html", "team", status_code=status_code, users=admins.all_users(conn),
                 errors=errors or [], setup=setup, form=form or {}, done=request.query_params.get("done"))


@router.get("/team")
def team_page(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        return _team(request, conn)


@router.post("/team/add")
def team_add(request: Request, name: str = Form(""), email: str = Form(""), password: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me = _me(conn, request)
        try:
            admins.create(conn, name, email, password)
        except admins.AdminError as exc:
            conn.raw.rollback()
            return _team(request, conn, 422, [str(exc)], form={"name": name, "email": email})
    if me and me.get("shared"):  # the shared password is now closed: sign in with the new account
        resp = RedirectResponse("/admin/login?created=1", status_code=303)
        resp.delete_cookie(auth.COOKIE)
        return resp
    return RedirectResponse("/admin/team?done=added", status_code=303)


@router.post("/team/{user_id}/toggle")
def team_toggle(request: Request, user_id: str):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me, user = _me(conn, request), admins.get(conn, user_id)
        if not user or me.get("shared"):
            return RedirectResponse("/admin/team", status_code=303)
        try:
            admins.set_active(conn, me, user_id, not user["is_active"])
        except admins.AdminError as exc:
            return _team(request, conn, 422, [str(exc)])
    return RedirectResponse("/admin/team?done=updated", status_code=303)


@router.post("/team/password")
def team_password(request: Request, current: str = Form(""), new: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me = _me(conn, request)
        if me.get("shared"):
            return RedirectResponse("/admin/team", status_code=303)
        try:
            admins.change_password(conn, me, current, new)
        except admins.AdminError as exc:
            return _team(request, conn, 422, [str(exc)])
    return RedirectResponse("/admin/team?done=password", status_code=303)


@router.post("/team/two-step/start")
def two_step_start(request: Request):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me = _me(conn, request)
        if me.get("shared"):
            return RedirectResponse("/admin/team", status_code=303)
        secret = admins.start_two_step(conn, me)
        return _team(request, conn, setup={"key": totp.grouped(secret), "uri": totp.setup_uri(secret, me["email"])})


@router.post("/team/two-step/confirm")
def two_step_confirm(request: Request, code: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me = _me(conn, request)
        try:
            admins.confirm_two_step(conn, me, code)
        except admins.AdminError as exc:
            pending = me.get("totp_pending")
            setup = {"key": totp.grouped(pending), "uri": totp.setup_uri(pending, me["email"])} if pending else None
            return _team(request, conn, 422, [str(exc)], setup=setup)
    return RedirectResponse("/admin/team?done=two-step-on", status_code=303)


@router.post("/team/two-step/stop")
def two_step_stop(request: Request, code: str = Form("")):
    if (r := _guard(request)):
        return r
    with db.connect() as conn:
        me = _me(conn, request)
        try:
            admins.stop_two_step(conn, me, code)
        except admins.AdminError as exc:
            return _team(request, conn, 422, [str(exc)])
    return RedirectResponse("/admin/team?done=two-step-off", status_code=303)

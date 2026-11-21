"""Fichua Partners: join with a code → onboard the hotel → manage calendar, prices and bookings."""
from __future__ import annotations

import dataclasses
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from .. import auth
from ..config import settings
from ..db import db
from ..services import app_settings, bookings, catalog, currency, dates, notify, partners, ratelimit
from ..web import render

router = APIRouter(prefix="/partners")

STEPS = [("hotel", "Hotel details"), ("photos", "Photos"), ("rooms", "Rooms and prices"),
         ("policies", "Policies and payment"), ("review", "Review and submit")]


def _current(conn, request: Request):
    user_id = auth.partner_user_id(request)
    if not user_id:
        return None, None
    user = conn.one("SELECT id, email, name, phone FROM partner_users WHERE id = :id", {"id": user_id})
    return (user, partners.user_hotel(conn, user_id)) if user else (None, None)


def _login_redirect():
    return RedirectResponse("/partners", status_code=303)


def _page(request: Request, conn, user, hotel, template: str, active: str, status_code: int = 200, **ctx):
    status = partners.onboarding_status(conn, hotel)
    info = currency.country_info(hotel.get("country"))
    rates = app_settings.all_settings(conn)
    local_rate = float(rates.get(f"rate_{info['currency']}") or 0) if info else 0
    return render(request, template, status_code=status_code, user=user, hotel=hotel, status=status,
                  steps=STEPS, active=active, local_label=info["label"] if info else "",
                  local_rate=local_rate, commission=hotel.get("commission_pct") or rates["commission_pct"], **ctx)


def _form_dict(form) -> dict:
    data = {k: form.get(k) for k in form.keys()}
    data["amenities"] = form.getlist("amenities")
    return data


# --------------------------------------------------------------------------- access

@router.get("")
def home(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not user or not hotel:
            return render(request, "partners/landing.html", join_error=None, login_error=None, form={})
        if hotel["status"] in ("draft", "changes"):
            steps = partners.onboarding_status(conn, hotel)["steps"]
            for key, _ in STEPS[:-1]:
                if not steps.get("identity" if key == "hotel" else key):
                    return RedirectResponse(f"/partners/{key}", status_code=303)
            return RedirectResponse("/partners/review", status_code=303)
    return RedirectResponse("/partners/calendar", status_code=303)


def _start_session(user_id: str, to: str):
    resp = RedirectResponse(to, status_code=303)
    resp.set_cookie(auth.PARTNER_COOKIE, auth.make_partner_token(user_id), max_age=auth.PARTNER_TTL_SECONDS,
                    httponly=True, samesite="lax", secure=settings.is_production)
    return resp


@router.post("/join")
def join(request: Request, code: str = Form(""), name: str = Form(""), hotel_name: str = Form(""),
         email: str = Form(""), phone: str = Form(""), password: str = Form("")):
    form = {"code": code, "name": name, "hotel_name": hotel_name, "email": email, "phone": phone}
    ip = ratelimit.client_ip(request)
    with db.connect() as conn:
        if ratelimit.blocked(conn, "join", ip):
            return render(request, "partners/landing.html", status_code=429, join_error=ratelimit.MESSAGES["join"],
                          login_error=None, form=form)
        try:
            created = partners.join(conn, code=code, name=name, hotel_name=hotel_name, email=email,
                                    phone=phone, password=password)
        except partners.PartnerError as exc:
            conn.raw.rollback()
            ratelimit.record(conn, "join", ip)  # after the rollback, so the attempt is kept
            return render(request, "partners/landing.html", status_code=422, join_error=str(exc),
                          join_field=exc.field, login_error=None, form=form)
    return _start_session(created["user_id"], "/partners/hotel")


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form("")):
    key = f"{ratelimit.client_ip(request)}|{email.strip().lower()}"
    with db.connect() as conn:
        if ratelimit.blocked(conn, "partner", key):
            return render(request, "partners/landing.html", status_code=429, join_error=None,
                          login_error=ratelimit.MESSAGES["partner"], form={"login_email": email})
        user = partners.authenticate(conn, email, password)
        if not user:
            ratelimit.record(conn, "partner", key)
        else:
            ratelimit.clear(conn, "partner", key)
    if not user:
        return render(request, "partners/landing.html", status_code=401, join_error=None,
                      login_error="Wrong email or password.", login_field="login_password" if email.strip()
                      else "login_email", form={"login_email": email})
    return _start_session(user["id"], "/partners")


@router.post("/logout")
def logout():
    resp = RedirectResponse("/partners", status_code=303)
    resp.delete_cookie(auth.PARTNER_COOKIE)
    return resp


# --------------------------------------------------------------------------- onboarding steps

@router.get("/hotel")
def identity_form(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _page(request, conn, user, hotel, "partners/identity.html", "hotel", errors=[],
                     markets=currency.MARKETS, property_types=partners.PROPERTY_TYPES,
                     amenities=partners.AMENITIES)


@router.post("/hotel")
async def identity_save(request: Request):
    data = _form_dict(await request.form())
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        errors = partners.update_identity(conn, hotel["id"], data)
        if not errors:
            return RedirectResponse("/partners/photos" if hotel["status"] in ("draft", "changes")
                                    else "/partners/hotel?saved=1", status_code=303)
        hotel = partners.user_hotel(conn, user["id"])
        return _page(request, conn, user, hotel, "partners/identity.html", "hotel", status_code=422,
                     errors=errors, markets=currency.MARKETS, property_types=partners.PROPERTY_TYPES,
                     amenities=partners.AMENITIES)


@router.get("/photos")
def photos(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _page(request, conn, user, hotel, "partners/photos.html", "photos", error=None,
                     photos=partners.media_list(conn, "hotel", hotel["id"]), min_photos=partners.MIN_HOTEL_PHOTOS)


async def _save_uploads(conn, owner_type: str, owner_id: str, files: list, thumbs: list | None = None) -> str | None:
    """Save each photo with the small card copy the browser sent in the same position (IMP-07)."""
    thumbs = list(thumbs or [])
    for i, f in enumerate(files):
        if not getattr(f, "filename", ""):
            continue
        small = thumbs[i] if i < len(thumbs) and getattr(thumbs[i], "filename", "") else None
        try:
            partners.add_photo(conn, owner_type, owner_id, await f.read(), f.content_type or "", label="",
                               thumb=await small.read() if small else None)
        except partners.PartnerError as exc:
            return str(exc)
    return None


@router.post("/photos")
async def photos_upload(request: Request):
    # Read the form by hand: a photo without a card copy sends an empty "thumbs" entry to keep the pairs in step.
    form = await request.form()
    files, thumbs = form.getlist("files"), form.getlist("thumbs")
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        error = await _save_uploads(conn, "hotel", hotel["id"], files, thumbs)
        if error:
            return _page(request, conn, user, hotel, "partners/photos.html", "photos", status_code=422, error=error,
                         photos=partners.media_list(conn, "hotel", hotel["id"]), min_photos=partners.MIN_HOTEL_PHOTOS)
    return RedirectResponse("/partners/photos", status_code=303)


@router.post("/photos/{media_id}/delete")
def photo_delete(request: Request, media_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        partners.delete_photo(conn, media_id, [hotel["id"]])
    return RedirectResponse("/partners/photos", status_code=303)


@router.post("/photos/{media_id}/cover")
def photo_cover(request: Request, media_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        partners.make_cover(conn, media_id, hotel["id"])
    return RedirectResponse("/partners/photos", status_code=303)


# --------------------------------------------------------------------------- host profile (optional)

def _host_page(request: Request, conn, user, hotel, status_code: int = 200, errors=None, form=None):
    photo = (catalog.media_urls(conn, "host", [hotel["id"]]).get(hotel["id"]) or [None])[0]
    preview = catalog.host_profile(hotel, photo)
    return _page(request, conn, user, hotel, "partners/host.html", "host", status_code=status_code,
                 errors=errors or [], form=form, photo=photo, preview=preview,
                 roles=partners.HOST_ROLES, languages=partners.HOST_LANGUAGES, max_welcome=partners.MAX_HOST_WELCOME)


@router.get("/host")
def host_form(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _host_page(request, conn, user, hotel)


@router.post("/host")
async def host_save(request: Request):
    form = await request.form()
    data = {k: form.get(k) for k in form.keys()}
    data["host_languages"] = form.getlist("host_languages")
    files, thumbs = [f for f in form.getlist("files") if getattr(f, "filename", "")], form.getlist("thumbs")
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        errors = partners.update_host(conn, hotel, data)
        if not errors and files:
            old = [m["id"] for m in partners.media_list(conn, "host", hotel["id"])]
            error = await _save_uploads(conn, "host", hotel["id"], files[:1], thumbs[:1])
            if error:
                errors = [error]
            else:  # one portrait: the new one replaces the old
                for media_id in old:
                    partners.delete_photo(conn, media_id, [hotel["id"]])
        if errors:
            conn.raw.rollback()
            return _host_page(request, conn, user, hotel, status_code=422, errors=errors, form=data)
    return RedirectResponse("/partners/host?saved=1", status_code=303)


@router.post("/host/photo/delete")
def host_photo_delete(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        for media in partners.media_list(conn, "host", hotel["id"]):
            partners.delete_photo(conn, media["id"], [hotel["id"]])
    return RedirectResponse("/partners/host?saved=1", status_code=303)


@router.get("/rooms")
def rooms(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _page(request, conn, user, hotel, "partners/rooms.html", "rooms",
                     rooms=partners.hotel_room_list(conn, hotel["id"]), error=request.query_params.get("error"))


def _room_page(request, conn, user, hotel, room, errors, status_code=200):
    return _page(request, conn, user, hotel, "partners/room_form.html", "rooms", status_code=status_code,
                 room=room, errors=errors, kinds=partners.ROOM_KINDS, room_amenities=partners.ROOM_AMENITIES)


@router.get("/rooms/new")
def room_new(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        room = {"name": "", "room_kind": "Double", "total_rooms": 1, "max_guests": 2, "amenities": [],
                "photos": [], "base_price": "", "weekend_price": "", "breakfast_included": False}
        return _room_page(request, conn, user, hotel, room, [])


@router.get("/rooms/{room_id}")
def room_edit(request: Request, room_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        room = partners.get_room(conn, hotel["id"], room_id)
        if not room:
            return RedirectResponse("/partners/rooms", status_code=303)
        return _room_page(request, conn, user, hotel, room, [])


@router.post("/rooms/new")
@router.post("/rooms/{room_id}")
async def room_save(request: Request, room_id: str | None = None):
    if room_id == "new":  # both routes share this handler; "/rooms/new" can match "/rooms/{room_id}"
        room_id = None
    form = await request.form()
    data = _form_dict(form)
    files = form.getlist("files")
    thumbs = form.getlist("thumbs")
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        if room_id and not partners.get_room(conn, hotel["id"], room_id):
            return RedirectResponse("/partners/rooms", status_code=303)
        saved_id, errors = partners.save_room(conn, hotel["id"], data, room_id)
        if not errors and any(getattr(f, "filename", "") for f in files):
            error = await _save_uploads(conn, "room", saved_id, files, thumbs)
            if error:
                errors = [error]
        if errors:
            conn.raw.rollback()
            room = {**data, "id": room_id, "photos": partners.media_list(conn, "room", room_id) if room_id else [],
                    "breakfast_included": data.get("breakfast_included") == "1"}
            return _room_page(request, conn, user, hotel, room, errors, status_code=422)
    return RedirectResponse("/partners/rooms", status_code=303)


@router.post("/rooms/{room_id}/delete")
def room_delete(request: Request, room_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        error = partners.delete_room(conn, hotel["id"], room_id)
    return RedirectResponse("/partners/rooms" + (f"?error={error}" if error else ""), status_code=303)


@router.post("/rooms/{room_id}/photos/{media_id}/delete")
def room_photo_delete(request: Request, room_id: str, media_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        if partners.get_room(conn, hotel["id"], room_id):
            partners.delete_photo(conn, media_id, [room_id])
    return RedirectResponse(f"/partners/rooms/{room_id}", status_code=303)


@router.get("/policies")
def policies(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _page(request, conn, user, hotel, "partners/policies.html", "policies", errors=[],
                     policies=partners.POLICIES)


@router.post("/policies")
async def policies_save(request: Request):
    data = _form_dict(await request.form())
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        errors = partners.update_policies(conn, hotel["id"], data)
        if not errors:
            return RedirectResponse("/partners/review", status_code=303)
        hotel = partners.user_hotel(conn, user["id"])
        return _page(request, conn, user, hotel, "partners/policies.html", "policies", status_code=422,
                     errors=errors, policies=partners.POLICIES)


@router.get("/review")
def review(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        return _page(request, conn, user, hotel, "partners/review.html", "review", error=None,
                     rooms=partners.hotel_room_list(conn, hotel["id"]))


@router.post("/submit")
def submit(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        try:
            sent = partners.submit(conn, hotel)
        except partners.PartnerError as exc:
            return _page(request, conn, user, hotel, "partners/review.html", "review", status_code=422,
                         error=str(exc), rooms=partners.hotel_room_list(conn, hotel["id"]))
        if sent:  # "we received it" to the hotel, "a hotel to review" to Fichua (IMP-13)
            notify.hotel_submitted(conn, hotel, user)
    if sent:
        with db.connect() as conn:  # after the commit, like every other message
            notify.flush(conn)
    return RedirectResponse("/partners/review", status_code=303)


# --------------------------------------------------------------------------- hotel manager

def _month(value: str | None) -> tuple[int, int]:
    try:
        y, m = (int(x) for x in (value or "").split("-"))
        date(y, m, 1)
        return y, m
    except (ValueError, TypeError):
        today = date.today()
        return today.year, today.month


@router.get("/calendar")
def calendar(request: Request):
    q = request.query_params
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        rooms = partners.hotel_room_list(conn, hotel["id"])
        if not rooms:
            return RedirectResponse("/partners/rooms", status_code=303)
        room = next((r for r in rooms if r["id"] == q.get("room")), rooms[0])
        year, month = _month(q.get("month"))
        days = partners.month_grid(conn, room, year, month)
        prev_m = f"{year - (month == 1)}-{(month - 2) % 12 + 1:02d}"
        next_m = f"{year + (month == 12)}-{month % 12 + 1:02d}"
        return _page(request, conn, user, hotel, "partners/calendar.html", "calendar", rooms=rooms, room=room,
                     days=days, month_label=date(year, month, 1).strftime("%B %Y"), prev_m=prev_m, next_m=next_m,
                     month_value=f"{year}-{month:02d}", saved=q.get("saved"), error=q.get("error"))


@router.post("/calendar")
def calendar_update(request: Request, room: str = Form(...), date_from: str = Form(...), date_to: str = Form(""),
                    apply_to: str = Form("all"), price: str = Form(""), units: str = Form(""),
                    closed: str = Form(""), reset: str = Form(""), month: str = Form("")):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        room_row = conn.one("SELECT * FROM room_types WHERE id = :id AND hotel_id = :h", {"id": room, "h": hotel["id"]})
        if not room_row:
            return RedirectResponse("/partners/calendar", status_code=303)
        query = {"room": room, "month": month}
        try:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to) if date_to else start
            n = partners.update_calendar(conn, room_row, start, end, apply_to=apply_to, price=price, units=units,
                                         closed=closed == "1", reset=reset == "1")
            query.update(saved=n, month=f"{start:%Y-%m}")  # reopen on the month that changed, so the owner sees it
        except (ValueError, partners.PartnerError) as exc:
            query["error"] = str(exc) if isinstance(exc, partners.PartnerError) else "Pick valid dates."
    return RedirectResponse("/partners/calendar?" + urlencode(query), status_code=303)


@router.get("/bookings")
def hotel_bookings(request: Request):
    show = request.query_params.get("show") or "upcoming"
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        rows = bookings.hotel_bookings(conn, hotel["id"], show)
        return _page(request, conn, user, hotel, "partners/bookings.html", "bookings", rows=rows, show=show,
                     added=request.query_params.get("added"))


@router.get("/bookings/new")
def offline_form(request: Request):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        rooms = partners.hotel_room_list(conn, hotel["id"])
        stay = dates.parse_stay(None, None, 2)
        return _page(request, conn, user, hotel, "partners/offline.html", "bookings", rooms=rooms, errors=[],
                     form={"check_in": stay.check_in.isoformat(), "check_out": stay.check_out.isoformat(),
                           "guests": 2, "source": "Walk-in"}, sources=bookings.OFFLINE_SOURCES)


@router.post("/bookings/new")
def offline_save(request: Request, room: str = Form(""), check_in: str = Form(""), check_out: str = Form(""),
                 guests: str = Form("2"), guest_name: str = Form(""), guest_phone: str = Form(""),
                 source: str = Form("Walk-in"), amount: str = Form(""), rooms_count: str = Form("1")):
    form = {"room": room, "check_in": check_in, "check_out": check_out, "guests": guests, "guest_name": guest_name,
            "guest_phone": guest_phone, "source": source, "amount": amount, "rooms_count": rooms_count}
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        errors = []
        stay = dates.parse_stay(check_in, check_out, guests)
        room_type = conn.one("SELECT name, max_guests FROM room_types WHERE id = :r AND hotel_id = :h",
                             {"r": room, "h": hotel["id"]})
        if not room_type:
            errors.append("Choose a room type.")
        if len(guest_name.strip()) < 2:
            errors.append("Enter the guest's name.")
        count = max(1, min(20, int(rooms_count or 1))) if str(rooms_count).isdigit() else 1
        # "Guests" is the whole group, shared over the rooms: every room must fit its share.
        group = dataclasses.replace(stay, rooms=count)
        if room_type and room_type["max_guests"] * count < stay.guests:
            fits = room_type["max_guests"] or 1
            errors.append(f"A {room_type['name']} sleeps {fits}, so {stay.guests} guests need at least "
                          f"{-(-stay.guests // fits)} rooms.")
        if not errors:
            one = dataclasses.replace(stay, rooms=1, guests=min(stay.guests, room_type["max_guests"] or 1))
            live = catalog.availability(conn, one, room_type_id=room, include_inactive=True)
            left = live[0]["rooms_left"] if live else 0
            if left < count:
                errors.append(f"Only {left} room{'' if left == 1 else 's'} left for those dates." if left
                              else "No rooms left for those dates (sold out or closed).")
        agreed = None
        if not errors and amount.strip():
            try:
                agreed = float(amount.replace(",", ""))
            except ValueError:
                errors.append("Enter the amount as a number.")
        if not errors:
            try:  # one booking for all the rooms, so the list shows it once with one Cancel button (IMP-11)
                bookings.create_booking(conn, group, room, guest_name=guest_name, guest_phone=guest_phone,
                                        source="offline", offline_source=source if source in bookings.OFFLINE_SOURCES
                                        else "Other website", agreed_amount=agreed)
            except bookings.BookingError:
                conn.raw.rollback()
                errors.append("Those rooms were just booked by someone else. Check the calendar and try again.")
        if errors:
            return _page(request, conn, user, hotel, "partners/offline.html", "bookings", status_code=422,
                         rooms=partners.hotel_room_list(conn, hotel["id"]), errors=errors, form=form,
                         sources=bookings.OFFLINE_SOURCES)
    return RedirectResponse(f"/partners/bookings?added={count}", status_code=303)


@router.post("/bookings/{booking_id}/cancel")
def offline_cancel(request: Request, booking_id: str):
    with db.connect() as conn:
        user, hotel = _current(conn, request)
        if not hotel:
            return _login_redirect()
        bookings.cancel_offline(conn, booking_id, hotel["id"])
    return RedirectResponse("/partners/bookings", status_code=303)

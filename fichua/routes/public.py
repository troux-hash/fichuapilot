"""Guest-facing pages: home → results → hotel → checkout → pay → confirmation / manage."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from .. import i18n
from ..db import db
from ..services import (app_settings, bookings, catalog, currency, dates, enquiries, kinds, legal, notify, partners,
                        payments, policies, ratelimit, seo, stay_calendar)
from ..services.search import discover, largest_room, where_options
from ..web import base_url, qs, render

router = APIRouter()


def _stay_from(request: Request) -> dates.Stay:
    q = request.query_params
    return dates.parse_stay(q.get("check_in"), q.get("check_out"), q.get("guests"), q.get("rooms"))


def _date_note(request: Request, stay: dates.Stay) -> str | None:
    """'We changed your dates to …' when the link asked for impossible dates (IMP-01)."""
    q = request.query_params
    return dates.adjustment(q.get("check_in"), q.get("check_out"), q.get("guests"), stay, rooms=q.get("rooms"))


def _flush_messages() -> None:
    """Send queued WhatsApp messages after the booking transaction has committed."""
    with db.connect() as conn:
        notify.flush(conn)


def _picked(request: Request) -> list[str]:
    """The kinds of place chosen on the home page: one or two (Brief 3 v3)."""
    out = []
    for k in request.query_params.getlist("kind"):
        if k in kinds.KIND_IDS and k not in out:
            out.append(k)
    return out[:2]


def _dated(request: Request) -> bool:
    q = request.query_params
    return bool(q.get("check_in") and q.get("check_out")) and q.get("dates") != "any"


@router.get("/")
def home(request: Request):
    i18n.use(i18n.lang_of(request))
    with db.connect() as conn:
        fichua_wa = enquiries.fichua_link(conn, i18n.t("Hello Fichua, I’m not sure which type of stay suits my trip. Can you help?"))
        hotels = catalog.live_hotels(conn)
        checks = kinds.checks_by_hotel(conn, [h["id"] for h in hotels])
    # Each kind's tile shows a real photo from a fully checked real place of that kind (design review F05, F06; the
    # five checks include the photos). Until one exists, the kind's own free photo from the region (kinds.py), credited
    # under the tiles. Demo places never stand in.
    kind_photos, credits = {}, []
    for h in hotels:
        photo = next((img for img in h["images"] if img != catalog.PLACEHOLDER_IMAGE), None)
        full = len(checks.get(h["id"], {})) >= len(kinds.CHECKS)
        if photo and full and not h["demo"] and h["kind"] not in kind_photos:
            kind_photos[h["kind"]] = photo
    for k in kinds.KINDS:
        if k["id"] not in kind_photos and k.get("photo"):
            kind_photos[k["id"]] = k["photo"]
            credits.append(k["photo_credit"])
    # "We check each place" only once a real place shows five dated checks; until then "Reviewed by our team" (F04).
    proven = any(not h["demo"] and len(checks.get(h["id"], {})) >= len(kinds.CHECKS) for h in hotels)
    return render(request, "pages/home.html", picked=_picked(request), fichua_wa=fichua_wa, kind_photos=kind_photos,
                  photo_credits=credits, proven=proven)


@router.get("/lang/{code}")
def set_language(request: Request, code: str):
    """The EN/FR switch: remember the choice and go back to the same page."""
    back = request.query_params.get("next") or "/"
    if not back.startswith("/") or back.startswith("//"):
        back = "/"
    resp = RedirectResponse(back, status_code=303)
    if code in i18n.LANGS:
        resp.set_cookie("lang", code, max_age=365 * 86400, samesite="lax")
    return resp


@router.get("/where")
def where(request: Request):
    picked = _picked(request)
    q = request.query_params
    stay = _stay_from(request)
    with db.connect() as conn:
        options = where_options(conn, picked)
    chosen = q.get("where") or "all"
    if chosen not in {o["value"] for o in options}:
        chosen = "all"
    return render(request, "pages/where.html", picked=picked, options=options, chosen=chosen, stay=stay,
                  no_dates=q.get("dates") == "any", presets=dates.presets())


@router.get("/search")
def results(request: Request):
    q = request.query_params
    i18n.use(i18n.lang_of(request))
    picked = _picked(request)
    where_value = (q.get("where") or q.get("destination") or "").strip() or "all"
    stay = _stay_from(request)
    dated = _dated(request)
    with db.connect() as conn:
        data = discover(conn, picked, where_value, stay, dated)
        widen = []
        if data["count"] < 2:  # few or none: offer the nearest wider searches, with their counts
            if picked:
                n = discover(conn, [], where_value, stay, dated)["count"]
                if n > data["count"]:
                    widen.append({"kind": "all_kinds", "count": n})
            if where_value != "all":
                n = discover(conn, picked, "all", stay, dated)["count"]
                if n > data["count"]:
                    widen.append({"kind": "everywhere", "count": n})
            if dated:
                n = discover(conn, picked, where_value, stay, False)["count"]
                if n > data["count"]:
                    widen.append({"kind": "any_dates", "count": n})
        fichua_wa = enquiries.fichua_link(conn, i18n.t("Hello Fichua, I’m looking for a place to stay and haven’t found one yet. Can you help?"))
        commission = app_settings.get_float(conn, "commission_pct")
        # A big group with nothing found: say no single room fits, and offer the search with enough rooms.
        largest = largest_room(conn, picked, where_value) if not data["count"] else 0
    rooms_hint = -(-stay.guests // largest) if largest and stay.guests > largest * stay.rooms else 0
    if rooms_hint > dates.MAX_ROOMS:
        rooms_hint = 0
    base = {"kind": picked, "where": where_value if where_value != "all" else None,
            "guests": stay.guests, "rooms": stay.rooms}
    if dated:
        base.update(check_in=stay.check_in.isoformat(), check_out=stay.check_out.isoformat())
    else:
        base["dates"] = "any"
    return render(request, "pages/results.html", picked=picked, where=where_value, stay=stay, dated=dated,
                  base=base, widen=widen, fichua_wa=fichua_wa, commission=commission, largest_room=largest,
                  rooms_hint=rooms_hint, date_note=_date_note(request, stay) if dated else None, **data)


@router.get("/compare")
def compare(request: Request):
    """Up to three ticked places side by side (design review F15), priced for the same stay."""
    q = request.query_params
    ids = []
    for i in q.getlist("id"):
        if i and i not in ids:
            ids.append(i)
    ids = ids[:3]
    stay = _stay_from(request)
    dated = _dated(request)
    with db.connect() as conn:
        found = discover(conn, [], "all", stay, dated) if ids else {"groups": []}
        commission = app_settings.get_float(conn, "commission_pct")
    by_id = {it["hotel"]["id"]: it for g in found["groups"] for it in g["places"]}
    items = [by_id[i] for i in ids if i in by_id]
    base = {"guests": stay.guests, "rooms": stay.rooms}
    if dated:
        base.update(check_in=stay.check_in.isoformat(), check_out=stay.check_out.isoformat())
    else:
        base["dates"] = "any"
    back = {**base, "where": q.get("where"), "kind": [k for k in q.getlist("kind") if k]}
    return render(request, "pages/compare.html", items=items, stay=stay, dated=dated, base=base, back_qs=qs(back),
                  commission=commission, policies=policies.POLICIES)


def _same_query(path: str, request: Request) -> str:
    return f"{path}?{request.url.query}" if request.url.query else path


@router.get("/hotels/{hotel_id}")
def hotel(request: Request, hotel_id: str):
    """Old and admin links: on to the hotel's readable address, dates kept."""
    with db.connect() as conn:
        h = catalog.get_hotel(conn, hotel_id)
    if not h:
        return render(request, "pages/not_found.html", status_code=404)
    return RedirectResponse(_same_query(h["path"], request), status_code=301)


@router.get("/stays/{country}/{city}/{slug}")
def hotel_page(request: Request, country: str, city: str, slug: str):
    stay = _stay_from(request)
    with db.connect() as conn:
        h = catalog.hotel_by_slug(conn, slug)
        if not h:
            return render(request, "pages/not_found.html", status_code=404)
        if request.url.path != h["path"]:  # renamed, or the country or city in the link is off
            return RedirectResponse(_same_query(h["path"], request), status_code=301)
        rooms = catalog.hotel_rooms(conn, h["id"], stay)
        verification = kinds.verification(h, kinds.checks_by_hotel(conn, [h["id"]]).get(h["id"]))
        similar = catalog.similar(conn, h)
        commission = h.get("commission_pct")
        if commission is None:
            commission = app_settings.get_float(conn, "commission_pct")
    picked = _picked(request)
    cheapest = next((r for r in rooms if r["available"]), None)
    rules = (policies.timeline(h.get("cancellation_policy"), cheapest["free_cancellation"], stay.check_in,
                               cheapest["total_price"]) if cheapest else [])
    base = base_url(request)
    canonical = base + h["path"]  # one address per hotel, whatever dates are in the link
    back = {"kind": picked, "where": request.query_params.get("where"), **stay.as_params()}
    return render(request, "pages/hotel.html", hotel=h, rooms=rooms, stay=stay, cheapest=cheapest, rules=rules,
                  can_ask=bool(enquiries.hotel_number(h)), canonical=canonical, summary=seo.summary(h),
                  share_image=seo.absolute((h.get("images") or [None])[0], base),
                  structured=seo.lodging(h, rooms, canonical, base), verification=verification,
                  similar=similar, commission=commission, picked=picked, dated=_dated(request),
                  policy=policies.POLICIES.get(h.get("cancellation_policy") or "flexible", policies.POLICIES["flexible"]),
                  back_qs=qs(back), date_note=_date_note(request, stay))


@router.get("/sitemap.xml")
def sitemap_xml(request: Request):
    with db.connect() as conn:
        body = seo.sitemap(conn, base_url(request))
    return Response(body, media_type="application/xml")


@router.get("/robots.txt")
def robots_txt(request: Request):
    return Response(seo.robots(base_url(request)), media_type="text/plain")


@router.get("/hotels/{hotel_id}/ask")
def ask_page(request: Request, hotel_id: str):
    """Before WhatsApp opens: the message that will be sent, and the rule that booking happens on Fichua."""
    stay = _stay_from(request)
    with db.connect() as conn:
        h = catalog.get_hotel(conn, hotel_id)
    if not h or not enquiries.hotel_number(h):
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/ask.html", hotel=h, stay=stay, dated=_dated(request),
                  preview=enquiries.message(h, stay, None, lang=i18n.lang_of(request)))


@router.post("/hotels/{hotel_id}/ask")
def ask_hotel(request: Request, hotel_id: str, check_in: str = Form(""), check_out: str = Form(""),
              guests: str = Form("2"), rooms: str = Form("1"), question: str = Form("")):
    """'Ask your host on WhatsApp': record an enquiry with a reference, then open WhatsApp (Brief 2 §6.2).
    The traveller talks to the host directly; booking and payment still happen on Fichua."""
    stay = dates.parse_stay(check_in, check_out, guests, rooms)
    ip = ratelimit.client_ip(request)
    with db.connect() as conn:
        h = catalog.get_hotel(conn, hotel_id)
        if not h or not enquiries.hotel_number(h):
            return render(request, "pages/not_found.html", status_code=404)
        reference = None
        if not ratelimit.blocked(conn, "ask", ip):  # past the limit, WhatsApp still opens, unrecorded
            reference = enquiries.create(conn, h, stay)
            ratelimit.record(conn, "ask", ip)
    return RedirectResponse(enquiries.whatsapp_link(h, stay, reference, question=question,
                                                    lang=i18n.lang_of(request)), status_code=303)


def _nights_text(stay: dates.Stay, offer: dict | None) -> str:
    """'2 nights × $65' when every night costs the same, '3 nights (average $70)' when they differ;
    with several rooms, '2 rooms × 2 nights × $65'."""
    nights = f"{stay.nights} night{'' if stay.nights == 1 else 's'}"
    if stay.rooms > 1:
        nights = f"{stay.rooms} rooms × {nights}"
    prices = (offer or {}).get("nightly") or []
    if not prices:
        return nights
    if len(set(prices)) == 1:
        return f"{nights} × {currency.usd(prices[0])}"
    return f"{nights} (average {currency.usd(round(sum(prices) / len(prices), 2))})"


def _checkout_context(conn, stay: dates.Stay, room_id: str):
    room = catalog.rooms_by_ids(conn, [room_id]).get(room_id)
    if not room:
        return None
    hotel = catalog.get_hotel(conn, room["hotel_id"])
    live = catalog.availability(conn, stay, room_type_id=room_id)
    offer = live[0] if live else None
    policy = (hotel or {}).get("cancellation_policy")
    commission = (hotel or {}).get("commission_pct")
    if commission is None:
        commission = app_settings.get_float(conn, "commission_pct")
    return {"room": room, "hotel": hotel, "offer": offer, "stay": stay, "commission": commission,
            "policy": partners.POLICIES.get(policy or "flexible"), "nights_text": _nights_text(stay, offer),
            "free_until": policies.open_until(policy, room["free_cancellation"], stay.check_in),
            "rules": policies.timeline(policy, room["free_cancellation"], stay.check_in,
                                       offer["total_price"]) if offer else []}


@router.get("/book")
def checkout(request: Request, room: str):
    stay = _stay_from(request)
    with db.connect() as conn:
        ctx = _checkout_context(conn, stay, room)
    if not ctx or not ctx["hotel"]:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/checkout.html", form={"guest_language": "en"}, errors={},
                  date_note=_date_note(request, stay), **ctx)


@router.post("/book")
def place_booking(request: Request, room: str = Form(...), check_in: str = Form(...),
                  check_out: str = Form(...), guests: int = Form(...), rooms: int = Form(1),
                  guest_name: str = Form(""), guest_email: str = Form(""),
                  guest_phone: str = Form(""), special_requests: str = Form(""),
                  guest_language: str = Form("en"), invoice_company: str = Form(""), invoice_tax_id: str = Form(""),
                  invoice_address: str = Form(""), invoice_reference: str = Form("")):
    stay = dates.parse_stay(check_in, check_out, guests, rooms)
    form = {"guest_name": guest_name, "guest_email": guest_email, "guest_phone": guest_phone,
            "special_requests": special_requests, "guest_language": guest_language,
            "invoice_company": invoice_company, "invoice_tax_id": invoice_tax_id,
            "invoice_address": invoice_address, "invoice_reference": invoice_reference}
    errors = {**bookings.validate_guest(guest_name, guest_email, guest_phone), **bookings.validate_invoice(form)}
    redirect_to = None
    ip = ratelimit.client_ip(request)
    with db.connect() as conn:
        if not errors and ratelimit.blocked(conn, "booking", ip):
            errors["general"] = ratelimit.MESSAGES["booking"]
        if not errors:
            try:
                b = bookings.create_booking(conn, stay, room, **form)
                ratelimit.record(conn, "booking", ip)  # each checkout holds a room: cap them per connection
                if payments.provider() == "stripe":
                    hotel = catalog.get_hotel(conn, b["hotel_id"])
                    room_row = catalog.rooms_by_ids(conn, [room])[room]
                    base = base_url(request)
                    booking_url = f"{base}/bookings/{b['reference']}?t={b['access_token']}"
                    session = payments.create_checkout(
                        booking={**b, "check_in": stay.check_in.isoformat(), "check_out": stay.check_out.isoformat()},
                        hotel_name=hotel["name"], room_name=bookings.room_label(room_row["name"], stay.rooms),
                        success_url=booking_url + "&session_id={CHECKOUT_SESSION_ID}",
                        cancel_url=f"{base}/book?{qs(stay.as_params(), room=room)}")
                    conn.run("UPDATE bookings SET stripe_session_id = :s WHERE id = :id",
                             {"s": session["id"], "id": b["id"]})
                    redirect_to = session["url"]
                else:
                    redirect_to = f"/pay/{b['reference']}?t={b['access_token']}"
            except bookings.BookingError as exc:
                errors["general"] = str(exc)
            except payments.PaymentError as exc:
                conn.raw.rollback()
                errors["general"] = f"We couldn't start the payment: {exc}"
        if redirect_to:
            return RedirectResponse(redirect_to, status_code=303)
        ctx = _checkout_context(conn, stay, room)
    if not ctx:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/checkout.html", form=form, errors=errors, status_code=422, **ctx)


@router.get("/pay/{reference}")
def test_checkout(request: Request, reference: str, t: str = ""):
    """Fichua's built-in test checkout, used until a Stripe key is configured."""
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
    if not b or payments.provider() != "test":
        return render(request, "pages/not_found.html", status_code=404)
    if b["payment_status"] == "paid":
        return RedirectResponse(f"/bookings/{b['reference']}?t={t}", status_code=303)
    return render(request, "pages/pay.html", booking=b, token=t)


@router.post("/pay/{reference}")
def test_checkout_pay(request: Request, reference: str, t: str = Form("")):
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
        if not b or payments.provider() != "test":
            return render(request, "pages/not_found.html", status_code=404)
        if b["is_expired"]:
            return render(request, "pages/pay.html", booking=b, token=t, status_code=410,
                          error="This checkout expired and the room was released. Please book again.")
        bookings.confirm_payment(conn, b["id"], provider="test", provider_ref="test_" + secrets.token_hex(8))
    _flush_messages()
    return RedirectResponse(f"/bookings/{b['reference']}?t={t}&new=1", status_code=303)


@router.get("/bookings/{reference}")
def booking_detail(request: Request, reference: str, t: str = "", new: int = 0, session_id: str = "",
                   cancelled: int = 0):
    confirmed_now = False
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
        if b and session_id and b["payment_status"] != "paid" and payments.provider() == "stripe":
            try:
                session = payments.fetch_checkout(session_id)
                if session.get("payment_status") == "paid" and session.get("client_reference_id") == b["id"]:
                    bookings.confirm_payment(conn, b["id"], provider="stripe",
                                             provider_ref=session.get("payment_intent") or session_id)
                    confirmed_now = True
            except payments.PaymentError:
                pass
            b = bookings.get_booking(conn, reference, t)
    if confirmed_now:
        _flush_messages()
    if not b:
        return render(request, "pages/not_found.html", status_code=404)
    pay_url = f"/pay/{b['reference']}?t={t}" if payments.provider() == "test" else None
    message = None
    if cancelled and b["status"] == "cancelled":
        message = ("Your booking is cancelled and your payment is being refunded. Refunds reach your card in "
                   "5 to 10 working days." if b["payment_status"] == "refunded" else "Your booking is cancelled.")
    calendar = None
    if b["status"] == "confirmed":
        calendar = {"ics": f"/bookings/{b['reference']}/calendar.ics?{qs({'t': t})}",
                    "google": stay_calendar.google_link(b, f"{base_url(request)}/manage")}
    return render(request, "pages/booking.html", booking=b, token=t, is_new=bool(new) or confirmed_now,
                  pay_url=pay_url, whatsapp_ready=notify.whatsapp_ready(), message=message, calendar=calendar)


@router.get("/bookings/{reference}/calendar.ics")
def booking_calendar(request: Request, reference: str, t: str = ""):
    """The stay as a calendar event (IMP-02): check-in to check-out at the hotel's local times."""
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
    if not b or b["status"] != "confirmed":
        return render(request, "pages/not_found.html", status_code=404)
    return Response(stay_calendar.ics(b, f"{base_url(request)}/manage"), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="fichua-{b["reference"]}.ics"'})


@router.get("/bookings/{reference}/door")
def booking_door(request: Request, reference: str, t: str = ""):
    """'Show at the door' (Brief 2, D2): the booking on one screen, big enough to read across a desk."""
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
    if not b or b["status"] == "pending":
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/door.html", booking=b, token=t)


@router.get("/bookings/{reference}/receipt")
def booking_receipt(request: Request, reference: str, t: str = ""):
    """A printable payment receipt, with the guest's company details when they gave them (Brief 2, D3)."""
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
        if not b or b["payment_status"] not in ("paid", "refunded"):
            return render(request, "pages/not_found.html", status_code=404)
        payment = conn.one("SELECT provider, amount, currency, status, created_at FROM payments "
                           "WHERE booking_id = :b ORDER BY created_at DESC", {"b": b["id"]})
        company = legal.facts(conn)
    return render(request, "pages/receipt.html", booking=b, token=t, payment=payment, company=company)


@router.post("/bookings/{reference}/cancel")
def booking_cancel(request: Request, reference: str, t: str = Form("")):
    error = None
    with db.connect() as conn:
        try:
            b = bookings.cancel_booking(conn, reference, t)
        except (bookings.BookingError, payments.PaymentError) as exc:
            conn.raw.rollback()
            b = bookings.get_booking(conn, reference, t)
            error = str(exc)
    _flush_messages()
    if not b:
        return render(request, "pages/not_found.html", status_code=404)
    if error is None:  # back to the booking's own page, so a reload or a shared link still works
        return RedirectResponse(f"/bookings/{b['reference']}?t={t}&cancelled=1", status_code=303)
    return render(request, "pages/booking.html", booking=b, token=t, is_new=False, message=error, pay_url=None)


@router.get("/favicon.ico")
def favicon():
    return RedirectResponse("/static/img/favicon.svg", status_code=301)


@router.get("/manage")
def manage_form(request: Request):
    return render(request, "pages/manage.html", error=None, form={})


@router.post("/manage")
def manage_lookup(request: Request, reference: str = Form(""), email: str = Form("")):
    with db.connect() as conn:
        b = bookings.find_booking(conn, reference, email)
    if not b:
        return render(request, "pages/manage.html", status_code=404,
                      error="We couldn't find a booking with that reference and email.",
                      form={"reference": reference, "email": email})
    return RedirectResponse(f"/bookings/{b['reference']}?t={b['access_token']}", status_code=303)


@router.get("/terms")
def terms_page(request: Request):
    with db.connect() as conn:
        return render(request, "legal/terms.html", legal=legal.facts(conn))


@router.get("/privacy")
def privacy_page(request: Request):
    with db.connect() as conn:
        return render(request, "legal/privacy.html", legal=legal.facts(conn))


@router.get("/partners/terms")
def partner_terms_page(request: Request):
    with db.connect() as conn:
        return render(request, "legal/partner_terms.html", legal=legal.facts(conn))


@router.get("/media/{media_id}")
def media(media_id: str, size: str = ""):
    with db.connect() as conn:
        m = partners.get_media(conn, media_id, card=size == "card")
    if not m:
        return Response(status_code=404)
    return Response(content=m["data"], media_type=m["content_type"],
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})

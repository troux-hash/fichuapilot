"""Guest-facing pages: home → results → hotel → checkout → pay → confirmation / manage."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from ..db import db
from ..services import bookings, catalog, dates, legal, notify, partners, payments
from ..services.search import SORTS, Filters, search
from ..web import base_url, qs, render

router = APIRouter()


def _stay_from(request: Request) -> dates.Stay:
    q = request.query_params
    return dates.parse_stay(q.get("check_in"), q.get("check_out"), q.get("guests"))


def _flush_messages() -> None:
    """Send queued WhatsApp messages after the booking transaction has committed."""
    with db.connect() as conn:
        notify.flush(conn)


@router.get("/")
def home(request: Request):
    with db.connect() as conn:
        destinations = catalog.destinations(conn)
    stay = dates.parse_stay(None, None, 2)
    return render(request, "pages/home.html", destinations=destinations, stay=stay, presets=dates.presets())


@router.get("/search")
def results(request: Request):
    q = request.query_params
    destination = (q.get("destination") or "").strip()
    stay = _stay_from(request)
    filters = Filters.from_query(q)
    with db.connect() as conn:
        data = search(conn, stay, destination or None, filters)
        destinations = catalog.destinations(conn)
    base = {"destination": destination, **stay.as_params()}
    return render(request, "pages/results.html", destination=destination, stay=stay,
                  filters=filters, sorts=SORTS, base=base, presets=dates.presets(),
                  destinations=destinations, **data)


@router.get("/hotels/{hotel_id}")
def hotel(request: Request, hotel_id: str):
    stay = _stay_from(request)
    with db.connect() as conn:
        h = catalog.get_hotel(conn, hotel_id)
        if not h:
            return render(request, "pages/not_found.html", status_code=404)
        rooms = catalog.hotel_rooms(conn, hotel_id, stay)
    back = request.query_params.get("destination") or h["city"]
    return render(request, "pages/hotel.html", hotel=h, rooms=rooms, stay=stay,
                  back_qs=qs({"destination": back, **stay.as_params()}))


def _checkout_context(conn, stay: dates.Stay, room_id: str):
    room = catalog.rooms_by_ids(conn, [room_id]).get(room_id)
    if not room:
        return None
    hotel = catalog.get_hotel(conn, room["hotel_id"])
    live = catalog.availability(conn, stay, room_type_id=room_id)
    return {"room": room, "hotel": hotel, "offer": live[0] if live else None, "stay": stay,
            "policy": partners.POLICIES.get((hotel or {}).get("cancellation_policy") or "flexible")}


@router.get("/book")
def checkout(request: Request, room: str):
    stay = _stay_from(request)
    with db.connect() as conn:
        ctx = _checkout_context(conn, stay, room)
    if not ctx or not ctx["hotel"]:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/checkout.html", form={"guest_language": "en"}, errors={}, **ctx)


@router.post("/book")
def place_booking(request: Request, room: str = Form(...), check_in: str = Form(...),
                  check_out: str = Form(...), guests: int = Form(...),
                  guest_name: str = Form(""), guest_email: str = Form(""),
                  guest_phone: str = Form(""), special_requests: str = Form(""),
                  guest_language: str = Form("en")):
    stay = dates.parse_stay(check_in, check_out, guests)
    form = {"guest_name": guest_name, "guest_email": guest_email, "guest_phone": guest_phone,
            "special_requests": special_requests, "guest_language": guest_language}
    errors = bookings.validate_guest(guest_name, guest_email, guest_phone)
    redirect_to = None
    with db.connect() as conn:
        if not errors:
            try:
                b = bookings.create_booking(conn, stay, room, **form)
                if payments.provider() == "stripe":
                    hotel = catalog.get_hotel(conn, b["hotel_id"])
                    room_row = catalog.rooms_by_ids(conn, [room])[room]
                    base = base_url(request)
                    booking_url = f"{base}/bookings/{b['reference']}?t={b['access_token']}"
                    session = payments.create_checkout(
                        booking={**b, "check_in": stay.check_in.isoformat(), "check_out": stay.check_out.isoformat()},
                        hotel_name=hotel["name"], room_name=room_row["name"],
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
def booking_detail(request: Request, reference: str, t: str = "", new: int = 0, session_id: str = ""):
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
    return render(request, "pages/booking.html", booking=b, token=t, is_new=bool(new) or confirmed_now,
                  pay_url=pay_url, whatsapp_ready=notify.whatsapp_ready())


@router.post("/bookings/{reference}/cancel")
def booking_cancel(request: Request, reference: str, t: str = Form("")):
    with db.connect() as conn:
        try:
            b = bookings.cancel_booking(conn, reference, t)
            message = ("Your booking is cancelled and your payment is being refunded."
                       if b["payment_status"] == "refunded" else "Your booking is cancelled.")
        except (bookings.BookingError, payments.PaymentError) as exc:
            conn.raw.rollback()
            b = bookings.get_booking(conn, reference, t)
            message = str(exc)
    _flush_messages()
    if not b:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/booking.html", booking=b, token=t, is_new=False, message=message, pay_url=None)


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
def media(media_id: str):
    with db.connect() as conn:
        m = partners.get_media(conn, media_id)
    if not m:
        return Response(status_code=404)
    return Response(content=m["data"], media_type=m["content_type"],
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})

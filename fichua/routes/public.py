"""Guest-facing pages: home → results → hotel → checkout → confirmation / manage."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..db import db
from ..services import bookings, catalog, dates
from ..services.search import SORTS, Filters, search
from ..web import qs, render

router = APIRouter()


def _stay_from(request: Request) -> dates.Stay:
    q = request.query_params
    return dates.parse_stay(q.get("check_in"), q.get("check_out"), q.get("guests"))


@router.get("/")
def home(request: Request):
    with db.connect() as conn:
        destinations = catalog.destinations(conn)
    stay = dates.parse_stay(None, None, 2)
    return render(request, "pages/home.html", destinations=destinations, stay=stay,
                  presets=dates.presets())


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
    offer = live[0] if live else None
    return {"room": room, "hotel": hotel, "offer": offer, "stay": stay}


@router.get("/book")
def checkout(request: Request, room: str):
    stay = _stay_from(request)
    with db.connect() as conn:
        ctx = _checkout_context(conn, stay, room)
    if not ctx or not ctx["hotel"]:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/checkout.html", form={}, errors={}, **ctx)


@router.post("/book")
def place_booking(request: Request, room: str = Form(...), check_in: str = Form(...),
                  check_out: str = Form(...), guests: int = Form(...),
                  guest_name: str = Form(""), guest_email: str = Form(""),
                  guest_phone: str = Form(""), special_requests: str = Form("")):
    stay = dates.parse_stay(check_in, check_out, guests)
    form = {"guest_name": guest_name, "guest_email": guest_email,
            "guest_phone": guest_phone, "special_requests": special_requests}
    errors = bookings.validate_guest(guest_name, guest_email, guest_phone)
    with db.connect() as conn:
        if not errors:
            try:
                b = bookings.create_booking(conn, stay, room, **form)
                return RedirectResponse(f"/bookings/{b['reference']}?t={b['access_token']}&new=1",
                                        status_code=303)
            except bookings.BookingError as exc:
                errors["general"] = str(exc)
        ctx = _checkout_context(conn, stay, room)
    if not ctx:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/checkout.html", form=form, errors=errors, status_code=422, **ctx)


@router.get("/bookings/{reference}")
def booking_detail(request: Request, reference: str, t: str = "", new: int = 0):
    with db.connect() as conn:
        b = bookings.get_booking(conn, reference, t)
    if not b:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/booking.html", booking=b, token=t, is_new=bool(new))


@router.post("/bookings/{reference}/cancel")
def booking_cancel(request: Request, reference: str, t: str = Form("")):
    with db.connect() as conn:
        try:
            b = bookings.cancel_booking(conn, reference, t)
            message = "Your booking has been cancelled. No charge was made."
        except bookings.BookingError as exc:
            b = bookings.get_booking(conn, reference, t)
            message = str(exc)
    if not b:
        return render(request, "pages/not_found.html", status_code=404)
    return render(request, "pages/booking.html", booking=b, token=t, is_new=False, message=message)


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

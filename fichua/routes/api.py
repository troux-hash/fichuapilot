"""JSON API, Stripe webhook and the daily payouts job."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..db import db
from ..services import bookings, catalog, dates, notify, payments, payouts
from ..services.search import Filters, search

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    with db.connect() as conn:
        conn.scalar("SELECT 1")
    return {"status": "ok", "database": db.dialect, "payments": payments.provider(),
            "whatsapp": "connected" if notify.whatsapp_ready() else "not connected"}


@router.get("/destinations")
def destinations():
    with db.connect() as conn:
        return catalog.destinations(conn)


@router.get("/search")
def api_search(request: Request):
    q = request.query_params
    stay = dates.parse_stay(q.get("check_in"), q.get("check_out"), q.get("guests"), q.get("rooms"))
    with db.connect() as conn:
        data = search(conn, stay, q.get("destination") or None, Filters.from_query(q))
    results = [{"hotel": catalog.public_hotel(o["hotel"]), "room": catalog.public_room(o["room"]),
                "total_price": o["total_price"], "per_night": o["per_night"], "rooms_left": o["rooms_left"],
                "rooms": stay.rooms} for o in data["results"]]
    return {"stay": {**stay.as_params(), "rooms": stay.rooms, "nights": stay.nights}, "results": results,
            "facets": data["facets"]}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    if not payments.verify_webhook(payload, request.headers.get("stripe-signature", ""),
                                   settings.stripe_webhook_secret):
        return JSONResponse({"error": "bad signature"}, status_code=400)
    event = json.loads(payload)
    if event.get("type") in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = event["data"]["object"]
        if session.get("payment_status") == "paid" and session.get("client_reference_id"):
            with db.connect() as conn:
                bookings.confirm_payment(conn, session["client_reference_id"], provider="stripe",
                                         provider_ref=session.get("payment_intent") or session.get("id"))
            with db.connect() as conn:
                notify.flush(conn)
    return {"received": True}


@router.get("/cron/payouts")
def cron_payouts(request: Request):
    """Called daily by Vercel Cron (Authorization: Bearer CRON_SECRET)."""
    if settings.cron_secret and request.headers.get("authorization") != f"Bearer {settings.cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    with db.connect() as conn:
        released = payouts.process_due(conn)
        sent = notify.flush(conn)
    return {"payouts_released": released, "messages_sent": sent}

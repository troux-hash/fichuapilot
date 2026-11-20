"""Card payments. Stripe Checkout when STRIPE_SECRET_KEY is set; otherwise Fichua's own
test checkout, so the whole booking → payment → payout → WhatsApp chain works without keys.

Stripe is called over its plain HTTPS API with the standard library (no SDK dependency).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import settings

STRIPE_API = "https://api.stripe.com/v1"


class PaymentError(Exception):
    pass


def provider() -> str:
    return "stripe" if settings.stripe_secret_key else "test"


def is_stripe_test_mode() -> bool:
    return settings.stripe_secret_key.startswith("sk_test_")


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Stripe's form encoding: nested dicts/lists become a[b][0][c]=v."""
    items: list[tuple[str, str]] = []
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            items.extend(_flatten(value, name))
        elif isinstance(value, list):
            for i, v in enumerate(value):
                items.extend(_flatten({str(i): v}, name) if isinstance(v, (dict, list)) else [(f"{name}[{i}]", str(v))])
        elif value is not None:
            items.append((name, str(value).lower() if isinstance(value, bool) else str(value)))
    return items


def stripe_request(method: str, path: str, data: dict | None = None) -> dict:
    if not settings.stripe_secret_key:
        raise PaymentError("Stripe is not configured.")
    body = urllib.parse.urlencode(_flatten(data or {})).encode() if data else None
    token = base64.b64encode(f"{settings.stripe_secret_key}:".encode()).decode()
    req = urllib.request.Request(STRIPE_API + path, data=body, method=method, headers={
        "Authorization": f"Basic {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get("error", {}).get("message", "")
        except Exception:
            message = ""
        raise PaymentError(message or f"Stripe error {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PaymentError("Could not reach Stripe. Please try again.") from exc


def create_checkout(*, booking: dict, hotel_name: str, room_name: str, success_url: str,
                    cancel_url: str) -> dict:
    """Returns {'id', 'url'} of a Stripe Checkout Session for the full booking amount."""
    cents = int(round(float(booking["total_price"]) * 100))
    return stripe_request("POST", "/checkout/sessions", {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": booking["id"],
        "customer_email": booking["guest_email"],
        "expires_at": int(time.time()) + 31 * 60,  # Stripe's minimum is 30 minutes
        "metadata": {"booking_id": booking["id"], "reference": booking["reference"]},
        "payment_intent_data": {"metadata": {"booking_id": booking["id"], "reference": booking["reference"]},
                                "description": f"{booking['reference']} · {hotel_name}"},
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": cents,
                "product_data": {
                    "name": f"{hotel_name} · {room_name}",
                    "description": f"{booking['check_in']} to {booking['check_out']} · {booking['nights']} nights",
                },
            },
        }],
    })


def fetch_checkout(session_id: str) -> dict:
    return stripe_request("GET", f"/checkout/sessions/{urllib.parse.quote(session_id)}")


def refund(payment_ref: str) -> dict:
    return stripe_request("POST", "/refunds", {"payment_intent": payment_ref})


def verify_webhook(payload: bytes, signature_header: str, secret: str, tolerance: int = 300) -> bool:
    """Checks Stripe's `Stripe-Signature` header (HMAC-SHA256 of 't.payload')."""
    if not secret or not signature_header:
        return False
    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp = parts.get("t", "")
    signatures = [v for k, v in (p.split("=", 1) for p in signature_header.split(",") if "=" in p) if k == "v1"]
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)


def dashboard_url(payment_ref: str | None) -> str | None:
    if not payment_ref or not payment_ref.startswith("pi_"):
        return None
    mode = "test/" if is_stripe_test_mode() else ""
    return f"https://dashboard.stripe.com/{mode}payments/{payment_ref}"

"""WhatsApp message templates (Meta "utility" templates, English and French).

Meta only delivers free text to someone who wrote to the business in the last 24 hours, so every
message Fichua starts (booking confirmations, hotel alerts, review decisions) goes out as one of these
approved templates. The text here is exactly what Meta approves: create the templates once with
`python scripts/whatsapp_templates.py create`, and change a text here only together with Meta.

Meta's rules, checked by tests/test_whatsapp.py: variables are {{1}}..{{n}} in order, a body may not
start or end with a variable, and a parameter may not contain new lines, tabs or runs of spaces.
"""
from __future__ import annotations

import re

TEMPLATES: dict[str, dict] = {
    "fichua_booking_confirmed": {  # to the guest
        "en": "Booking confirmed\nHi {{1}}, your stay at {{2}} is reserved.\n\nReference: {{3}}\nRoom: {{4}}\n"
              "Dates: {{5}}\nPaid in full: {{6}}\nNothing more to pay at the hotel.\n\n"
              "Check-in from {{7}} at {{8}}. See you soon!",
        "fr": "Réservation confirmée\nBonjour {{1}}, votre séjour à {{2}} est réservé.\n\nRéférence : {{3}}\n"
              "Chambre : {{4}}\nDates : {{5}}\nPayé en totalité : {{6}}\nRien de plus à payer à l’hôtel.\n\n"
              "Arrivée à partir de {{7}} à l’adresse {{8}}. À bientôt !",
        "example": {
            "en": ["Amina", "Kigali Hills Hotel", "FCH-7QX2KD", "Deluxe Double, 2 guests",
                   "Fri 04 Dec → Sun 06 Dec (2 nights)", "$160 (≈232,000 RWF)", "14:00", "KG 7 Ave, Kigali"],
            "fr": ["Amina", "Hôtel Lagune Bleue", "FCH-7QX2KD", "Chambre Double, 2 personnes",
                   "ven. 4 déc. → dim. 6 déc. (2 nuits)", "160 $ (≈ 90 400 FCFA)", "14:00", "Haie Vive, Cotonou"],
        },
    },
    "fichua_new_booking": {  # to the hotel
        "en": "New booking, paid\n{{1}}, you have a new Fichua booking.\n\nReference: {{2}}\nGuest: {{3}}\n"
              "Room: {{4}}\nDates: {{5}}\n\nGuest paid Fichua: {{6}}\nFichua commission: {{7}}\n"
              "Your payout: {{8}}\n\nSee it in Fichua Partners.",
        "fr": "Nouvelle réservation payée\n{{1}}, vous avez une nouvelle réservation Fichua.\n\nRéférence : {{2}}\n"
              "Client : {{3}}\nChambre : {{4}}\nDates : {{5}}\n\nPayé par le client à Fichua : {{6}}\n"
              "Commission Fichua : {{7}}\nVotre versement : {{8}}\n\nVoir dans Fichua Partners.",
        "example": {
            "en": ["Kigali Hills Hotel", "FCH-7QX2KD", "Amina Diallo, 2 guests · +250 788 000 000", "Deluxe Double × 1",
                   "Fri 04 Dec → Sun 06 Dec (2 nights)", "$160 (≈232,000 RWF)", "7% · $11.20",
                   "$148.80 (≈215,800 RWF)"],
            "fr": ["Hôtel Lagune Bleue", "FCH-7QX2KD", "Amina Diallo, 2 personnes · +229 01 97 00 00 00",
                   "Chambre Double × 1", "ven. 4 déc. → dim. 6 déc. (2 nuits)", "160 $ (≈ 90 400 FCFA)",
                   "7 % · 11,20 $", "148,80 $ (≈ 84 100 FCFA)"],
        },
    },
    "fichua_payment_received": {  # to Fichua
        "en": "Payment received\nReference: {{1}}\nHotel: {{2}}\n\nAmount: {{3}} by card\nFichua commission: {{4}}\n"
              "Owed to the hotel: {{5}}\nStay: {{6}}\n\nSee it in Fichua Admin.",
        "example": {"en": ["FCH-7QX2KD", "Kigali Hills Hotel (FH-00012)", "$160.00", "7% · $11.20", "$148.80",
                           "Fri 04 Dec → Sun 06 Dec (2 nights)"]},
    },
    "fichua_booking_cancelled": {  # to the guest
        "en": "Booking cancelled\nYour booking {{1}} at {{2}} is cancelled.\nRefund: {{3}}.\n\n"
              "You can still see it in Manage booking on Fichua.",
        "fr": "Réservation annulée\nVotre réservation {{1}} au {{2}} est annulée.\nRemboursement : {{3}}.\n\n"
              "Vous la retrouvez dans Gérer ma réservation sur Fichua.",
        "example": {
            "en": ["FCH-7QX2KD", "Kigali Hills Hotel", "$160.00 to your card, within 5 to 10 working days"],
            "fr": ["FCH-7QX2KD", "Hôtel Lagune Bleue", "160,00 $ sur votre carte, sous 5 à 10 jours ouvrés"],
        },
    },
    "fichua_booking_cancelled_hotel": {  # to the hotel
        "en": "Booking cancelled\nReference: {{1}}\nGuest: {{2}}\nArrival: {{3}}\n\n"
              "The booking is cancelled and the room is back on sale.",
        "fr": "Réservation annulée\nRéférence : {{1}}\nClient : {{2}}\nArrivée : {{3}}\n\n"
              "La réservation est annulée et la chambre est de nouveau en vente.",
        "example": {"en": ["FCH-7QX2KD", "Amina Diallo", "Fri 04 Dec"],
                    "fr": ["FCH-7QX2KD", "Amina Diallo", "ven. 4 déc."]},
    },
    "fichua_booking_cancelled_admin": {  # to Fichua
        "en": "Booking cancelled\nReference: {{1}}\nHotel: {{2}}\nRefund: {{3}}.\n\nSee it in Fichua Admin.",
        "example": {"en": ["FCH-7QX2KD", "Kigali Hills Hotel (FH-00012)", "$160.00"]},
    },
    "fichua_hotel_approved": {  # to the hotel
        "en": "Welcome to Fichua!\n{{1}} ({{2}}) is approved and now live. Guests can book you from today. "
              "Manage your calendar in Fichua Partners.",
        "fr": "Bienvenue sur Fichua !\n{{1}} ({{2}}) est approuvé et en ligne. Les clients peuvent réserver dès "
              "aujourd’hui. Gérez votre calendrier dans Fichua Partners.",
        "example": {"en": ["Kigali Hills Hotel", "FH-00012"], "fr": ["Hôtel Lagune Bleue", "FH-00012"]},
    },
    "fichua_hotel_changes": {  # to the hotel
        "en": "Fichua review: a few changes needed\n{{1}} ({{2}})\n\n{{3}}\n\n"
              "Update your listing in Fichua Partners, then submit it again.",
        "fr": "Vérification Fichua : quelques modifications\n{{1}} ({{2}})\n\n{{3}}\n\n"
              "Mettez à jour votre annonce dans Fichua Partners, puis soumettez-la à nouveau.",
        "example": {"en": ["Kigali Hills Hotel", "FH-00012", "Please add two photos of the bathroom."],
                    "fr": ["Hôtel Lagune Bleue", "FH-00012", "Merci d’ajouter deux photos de la salle de bain."]},
    },
    "fichua_hotel_rejected": {  # to the hotel
        "en": "Fichua review\n{{1}} ({{2}}) was not approved.\n\n{{3}}\n\nReply to this message if you have questions.",
        "fr": "Vérification Fichua\n{{1}} ({{2}}) n’a pas été approuvé.\n\n{{3}}\n\n"
              "Répondez à ce message si vous avez des questions.",
        "example": {"en": ["Kigali Hills Hotel", "FH-00012", "We could not confirm the hotel at this address."],
                    "fr": ["Hôtel Lagune Bleue", "FH-00012", "Nous n’avons pas pu confirmer l’hôtel à cette adresse."]},
    },
}


def languages(name: str) -> list[str]:
    return [key for key in TEMPLATES[name] if key != "example"]


def all_versions() -> list[tuple[str, str]]:
    return [(name, lang) for name in TEMPLATES for lang in languages(name)]


def language(name: str, wanted: str | None) -> str:
    """The template's version in the wanted language, or English when it has none."""
    return wanted if wanted in languages(name) else "en"


def clean(value) -> str:
    """Meta refuses parameters with new lines, tabs or runs of spaces, and empty ones."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()[:600] or "-"


def render(name: str, lang: str, params: list[str]) -> str:
    text = TEMPLATES[name][lang]
    for number, value in enumerate(params, start=1):
        text = text.replace("{{%d}}" % number, value)
    return text


def send_payload(to: str, name: str, lang: str, params: list[str]) -> dict:
    """Cloud API body for sending one template message."""
    return {"messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": name, "language": {"code": lang},
                         "components": [{"type": "body",
                                         "parameters": [{"type": "text", "text": p} for p in params]}]}}


def create_payload(name: str, lang: str) -> dict:
    """Business Management API body for creating one template in one language."""
    return {"name": name, "language": lang, "category": "UTILITY",
            "components": [{"type": "BODY", "text": TEMPLATES[name][lang],
                            "example": {"body_text": [TEMPLATES[name]["example"][lang]]}}]}

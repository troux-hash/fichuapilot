"""The site-wide copy rewrite of 27 Nov 2026 (docs/VOICE.md): one word for one thing, labels that match the
WhatsApp messages, and French that counts like French."""
from fastapi.testclient import TestClient

from fichua import i18n
from fichua.main import app
from fichua.services import whatsapp_templates

guest = TestClient(app)
guest.cookies.set("lang", "en")
visiteur = TestClient(app)
visiteur.cookies.set("lang", "fr")


def test_the_menu_says_what_the_whatsapp_message_says():
    # The cancellation message is a Meta-approved template that sends travellers to "Manage booking".
    message = whatsapp_templates.TEMPLATES["fichua_booking_cancelled"]
    assert "Manage booking" in message["en"] and "Gérer ma réservation" in message["fr"]
    home = guest.get("/").text
    assert ">Manage booking<" in home and "Kind of place" not in home and "Type of stay" in home
    home_fr = visiteur.get("/").text
    assert ">Gérer ma réservation<" in home_fr and "Type de séjour" in home_fr


def test_search_engines_read_what_travellers_type():
    home = guest.get("/").text
    assert "<title>Independent hotels &amp; lodges in Rwanda, Benin and Côte d’Ivoire · Fichua</title>" in home
    assert 'name="description" content="Book small, independent hotels and lodges' in home


def test_french_counts_zero_as_singular():
    i18n.use("fr")
    try:
        assert [i18n.tn(n, "1 place", "{n} places") for n in (0, 1, 2)] == ["0 lieu", "1 lieu", "2 lieux"]
        assert i18n.tn(0, "1 night", "{n} nights") == "0 nuit"
        assert i18n.tn(0, "1 more place is full on these dates.", "{n} more places are full on these dates.").startswith("0")
    finally:
        i18n.use("en")
    assert [i18n.tn(n, "1 place", "{n} places") for n in (0, 1, 2)] == ["0 places", "1 place", "2 places"]


def test_the_test_mode_notice_is_one_label_and_one_fact():
    home = guest.get("/").text
    assert "<strong>Test mode</strong><span>Bookings aren’t real yet, and no money is taken.</span>" in home

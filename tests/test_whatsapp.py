"""WhatsApp messages go out as approved templates (QA finding FIX-03), with correct plurals (FIX-09)
and French number formats (IMP-16)."""
import dataclasses
import json
import re

from fichua.db import db
from fichua.services import notify
from fichua.services import whatsapp_templates as wt

VAR = re.compile(r"\{\{(\d+)\}\}")


def test_templates_follow_meta_rules():
    for name, spec in wt.TEMPLATES.items():
        assert re.fullmatch(r"[a-z0-9_]{1,512}", name)
        assert "en" in wt.languages(name)
        counts = set()
        for lang in wt.languages(name):
            body = spec[lang]
            numbers = [int(n) for n in VAR.findall(body)]
            assert numbers == list(range(1, len(numbers) + 1)), (name, lang)  # in order, no gaps or repeats
            assert not body.startswith("{{") and not body.rstrip().endswith("}}"), (name, lang)
            assert len(body) <= 1024
            assert len(spec["example"][lang]) == len(numbers), (name, lang)
            counts.add(len(numbers))
        assert len(counts) == 1, name  # every language takes the same parameters


def test_parameters_are_cleaned_and_rendered():
    assert wt.clean("Line one\nline\ttwo     three") == "Line one line two three"
    assert wt.clean("") == "-"
    body = wt.render("fichua_hotel_changes", "en", ["Lodge", "FH-1", "Add a photo."])
    assert "{{" not in body and "Add a photo." in body
    assert wt.language("fichua_payment_received", "fr") == "en"  # Fichua's own alerts are English only


def test_payload_sends_the_template(monkeypatch):
    message = {"to_phone": "250788000000", "template": "fichua_hotel_approved", "language": "fr",
               "params": json.dumps(["Lodge", "FH-1"]), "body": "Bienvenue sur Fichua !"}
    payload = notify.payload(message)
    assert payload["type"] == "template" and payload["template"]["name"] == "fichua_hotel_approved"
    assert payload["template"]["language"] == {"code": "fr"}
    assert [p["text"] for p in payload["template"]["components"][0]["parameters"]] == ["Lodge", "FH-1"]
    monkeypatch.setattr(notify, "settings", dataclasses.replace(notify.settings, whatsapp_send_mode="text"))
    assert notify.payload(message) == {"messaging_product": "whatsapp", "to": "250788000000", "type": "text",
                                       "text": {"preview_url": False, "body": "Bienvenue sur Fichua !"}}


def test_outbox_keeps_template_parameters_and_text():
    hotel = {"id": "FH-TPL01", "name": "Test Lodge", "country": "Benin", "whatsapp": "+229 01 00 00 00 01"}
    with db.connect() as conn:
        notify.hotel_decision(conn, hotel, "changes", "Add a bathroom photo,\nplease.")
        row = conn.one("SELECT * FROM messages WHERE hotel_id = 'FH-TPL01'")
    assert row["template"] == "fichua_hotel_changes" and row["language"] == "fr"
    assert json.loads(row["params"]) == ["Test Lodge", "FH-TPL01", "Add a bathroom photo, please."]
    assert row["body"].startswith("Vérification Fichua") and "{{" not in row["body"]
    assert row["to_phone"] == "22901000000" + "01"


def test_plurals_and_french_numbers():
    assert notify._guests(1, "en") == "1 guest" and notify._guests(2, "en") == "2 guests"
    assert notify._guests(1, "fr") == "1 personne" and notify._guests(3, "fr") == "3 personnes"
    rates = {"rate_RWF": "1450", "rate_XOF": "565"}
    assert notify._money(160, "Rwanda", rates, "en") == "$160 (≈232,000 RWF)"
    assert notify._money(160, "Rwanda", rates, "fr") == "160 $ (≈ 232 000 RWF)"
    assert notify._money(160, "Benin", rates, "fr") == "160 $ (≈ 90 400 FCFA)"
    assert notify._usd(1234.5, "fr") == "1 234,50 $"

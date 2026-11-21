"""Terms, privacy policy and partner terms exist, are linked where people agree to them, and show the
company details set in Admin -> Settings (QA finding FIX-02)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from fichua.main import app

guest = TestClient(app)
SETTINGS = {"commission_pct": "7", "payout_timing": "immediate", "payout_delay_hours": "24", "rate_RWF": "1450",
            "rate_XOF": "565", "manager_fee_usd": "0", "hold_minutes": "35", "admin_whatsapp": ""}


def test_legal_pages_render_and_link_each_other():
    for path, title in (("/terms", "Terms of service"), ("/privacy", "Privacy policy"),
                        ("/partners/terms", "Partner terms")):
        page = guest.get(path)
        assert page.status_code == 200, path
        assert title in page.text and 'href="/privacy"' in page.text and 'href="/partners/terms"' in page.text
    assert "Free cancellation until 5 days before check-in." in guest.get("/terms").text
    assert "Autorité de Protection des Données Personnelles" in guest.get("/privacy").text


def test_legal_links_where_people_agree():
    home = guest.get("/").text
    assert 'href="/terms"' in home and 'href="/privacy"' in home
    assert 'href="/partners/terms"' in guest.get("/partners").text
    ci = date.today() + timedelta(days=40)
    offer = guest.get("/api/search", params={"destination": "Kigali", "check_in": ci.isoformat(),
                                              "check_out": (ci + timedelta(days=1)).isoformat()}).json()["results"][0]
    checkout = guest.get("/book", params={"room": offer["room"]["id"], "check_in": ci.isoformat(),
                                          "check_out": (ci + timedelta(days=1)).isoformat(), "guests": 2}).text
    assert "By paying, you accept the" in checkout and 'href="/terms"' in checkout


def test_company_details_from_settings(admin):
    r = admin.post("/admin/settings", data={**SETTINGS, "company_name": "Fichua Test Inc.",
                                            "contact_email": "help@fichua.test", "company_address": "1 Test Street"},
                   follow_redirects=False)
    assert r.status_code == 303
    terms = guest.get("/terms").text
    assert "Fichua Test Inc." in terms and "help@fichua.test" in terms and "1 Test Street" in terms
    bad = admin.post("/admin/settings", data={**SETTINGS, "commission_pct": "150", "contact_email": "nope"})
    assert bad.status_code == 422
    assert "Default commission must be between 0% and 50%." in bad.text
    assert "Enter the contact email like name@company.com." in bad.text
    admin.post("/admin/settings", data={**SETTINGS, "company_name": "", "contact_email": "", "company_address": ""})
    assert "Write to" not in guest.get("/terms").text

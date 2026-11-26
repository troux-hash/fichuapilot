"""The "Built at MIT" trust section: on guest pages and the partner landing page, with names as text
until official logo files are added (a `-white` file means a reversed logo on a dark plate)."""
import dataclasses

from fastapi.testclient import TestClient

from fichua import web
from fichua.main import app

CENTER = "MIT Kuo Sharper Center for Prosperity and Entrepreneurship"


def test_trust_section_on_guest_and_partner_pages():
    c = TestClient(app)
    for path in ("/", "/manage", "/partners"):
        html = c.get(path).text
        assert "Built at MIT" in html, path
        assert "MIT Sandbox Innovation Fund" in html, path
        assert CENTER in html, path
        assert "https://kuosharper.mit.edu" in html, path


def test_the_three_mit_logos_show_now_that_mit_said_yes(monkeypatch):
    assert web.settings.mit_logos_approved  # MIT's written OK arrived on 26 Nov 2026
    html = TestClient(app).get("/").text
    for name in ("mit.png", "mit-sandbox.png", "kuo-sharper-white.png"):
        assert f"/static/img/trust/{name}" in html, name
    # The switch still turns them off (MIT_LOGOS_APPROVED=0): names only, as words.
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, mit_logos_approved=False))
    assert all(p["logo"] is None for p in web.trust_partners())
    html = TestClient(app).get("/").text
    assert "/static/img/trust/mit.png" not in html and "MIT Sandbox Innovation Fund" in html


def test_supplied_logo_files_are_used(monkeypatch):
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, mit_logos_approved=True))
    found = {p["key"]: p for p in web.trust_partners()}
    assert found["mit"]["logo"].startswith("/static/img/trust/mit.png?v=") and found["mit"]["plate"] == "light"
    assert found["mit-sandbox"]["logo"].startswith("/static/img/trust/mit-sandbox.png?v=")
    assert found["kuo-sharper"]["logo"].startswith("/static/img/trust/kuo-sharper-white.png?v=")
    assert found["kuo-sharper"]["plate"] == "dark"
    for name in ("mit.png", "mit-sandbox.png", "kuo-sharper-white.png"):
        assert (web.STATIC_DIR / "static" / "img" / "trust" / name).read_bytes()[:4] == b"\x89PNG", name


def test_logos_switch_on_when_official_files_are_added(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "settings", dataclasses.replace(web.settings, mit_logos_approved=True))
    monkeypatch.setattr(web, "STATIC_DIR", tmp_path)
    assert all(p["logo"] is None and p["plate"] == "light" for p in web.trust_partners())

    folder = tmp_path / "static" / "img" / "trust"
    folder.mkdir(parents=True)
    (folder / "mit.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (folder / "kuo-sharper-white.png").write_bytes(b"\x89PNG")
    found = {p["key"]: p for p in web.trust_partners()}
    assert found["mit"]["logo"].startswith("/static/img/trust/mit.svg?v=") and found["mit"]["plate"] == "light"
    assert found["kuo-sharper"]["logo"].startswith("/static/img/trust/kuo-sharper-white.png?v=")
    assert found["kuo-sharper"]["plate"] == "dark"
    assert found["mit-sandbox"]["logo"] is None

    html = TestClient(app).get("/").text
    assert 'alt="Massachusetts Institute of Technology"' in html
    assert "trust__plate--dark" in html

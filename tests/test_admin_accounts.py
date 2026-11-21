"""Named admin accounts, two-step login and rate limits (QA finding FIX-14)."""
import pytest
from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import ratelimit, totp

ADA = {"name": "Ada Admin", "email": "ada@fichua.test", "password": "correct-horse-1"}


@pytest.fixture(autouse=True)
def back_to_shared_password():
    """Each test starts and ends with no named admins, as the rest of the suite expects."""
    def wipe():
        with db.connect() as conn:
            conn.run("DELETE FROM admin_users")
            conn.run("DELETE FROM login_attempts")
    wipe()
    yield
    wipe()


def _create_ada() -> TestClient:
    shared = TestClient(app)
    assert shared.post("/admin/login", data={"password": "test-pass"}, follow_redirects=False).status_code == 303
    r = shared.post("/admin/team/add", data=ADA, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login?created=1"
    return shared


def test_totp_matches_rfc_6238():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # the RFC's key, "12345678901234567890"
    assert totp.code_at(secret, 59, digits=8) == "94287082"
    assert totp.code_at(secret, 1111111109, digits=8) == "07081804"
    assert totp.verify(secret, totp.code_at(secret, 1000), at=1030)  # one step of clock drift is fine
    assert not totp.verify(secret, totp.code_at(secret, 1000), at=1100)
    assert not totp.verify(secret, "12345", at=1000)


def test_shared_password_only_until_the_first_named_admin():
    shared = TestClient(app)
    shared.post("/admin/login", data={"password": "test-pass"})
    assert "Create your own admin account" in shared.get("/admin").text
    _create_ada()
    assert shared.get("/admin", follow_redirects=False).status_code == 303  # that session is over
    assert TestClient(app).post("/admin/login", data={"password": "test-pass"}).status_code == 401
    ada = TestClient(app)
    r = ada.post("/admin/login", data={"email": "ADA@fichua.test", "password": ADA["password"]}, follow_redirects=False)
    assert r.status_code == 303
    team = ada.get("/admin/team").text
    assert "Ada Admin" in team and "(you)" in team and "Set up two-step login" in team


def test_two_step_login():
    _create_ada()
    ada = TestClient(app)
    ada.post("/admin/login", data={"email": ADA["email"], "password": ADA["password"]})
    assert "setup key" in ada.post("/admin/team/two-step/start").text
    with db.connect() as conn:
        secret = conn.scalar("SELECT totp_pending FROM admin_users WHERE email = :e", {"e": ADA["email"]})
    assert ada.post("/admin/team/two-step/confirm", data={"code": "000000"}).status_code == 422
    r = ada.post("/admin/team/two-step/confirm", data={"code": totp.code_at(secret)}, follow_redirects=False)
    assert r.status_code == 303
    no_code = TestClient(app).post("/admin/login", data={"email": ADA["email"], "password": ADA["password"]})
    assert no_code.status_code == 401
    with_code = TestClient(app).post("/admin/login", data={"email": ADA["email"], "password": ADA["password"],
                                                           "code": totp.code_at(secret)}, follow_redirects=False)
    assert with_code.status_code == 303


def test_failed_sign_ins_are_rate_limited():
    client = TestClient(app)
    for _ in range(ratelimit.LIMITS["admin"][0]):
        assert client.post("/admin/login", data={"password": "wrong"}).status_code == 401
    blocked = client.post("/admin/login", data={"password": "test-pass"})
    assert blocked.status_code == 429 and "Too many failed sign-ins" in blocked.text


def test_limits_are_per_scope_and_key():
    with db.connect() as conn:
        for _ in range(ratelimit.LIMITS["booking"][0]):
            ratelimit.record(conn, "booking", "203.0.113.7")
        assert ratelimit.blocked(conn, "booking", "203.0.113.7")
        assert not ratelimit.blocked(conn, "booking", "203.0.113.8")
        assert not ratelimit.blocked(conn, "admin", "203.0.113.7")

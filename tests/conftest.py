"""Test setup: a throw-away SQLite database and no external services (test checkout, no WhatsApp)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp()
# Real env vars win over .env, so these keep tests away from the live database and services.
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["ADMIN_PASSWORD"] = "test-pass"
os.environ["STRIPE_SECRET_KEY"] = ""
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["APP_ENV"] = "test"

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from fichua.main import app  # noqa: E402
from fichua.services.importer import template_workbook  # noqa: E402
from scripts.generate_synthetic_data import build  # noqa: E402


def admin_client() -> TestClient:
    c = TestClient(app)
    r = c.post("/admin/login", data={"password": "test-pass"}, follow_redirects=False)
    assert r.status_code == 303
    return c


@pytest.fixture(scope="session")
def admin() -> TestClient:
    return admin_client()


@pytest.fixture(scope="session", autouse=True)
def seeded(admin):
    combined = {"Hotels": [], "Rooms": [], "Rates": []}
    for group in build().values():
        for k in combined:
            combined[k].extend(group[k])
    r = admin.post("/admin/upload", files={"file": ("hotels.xlsx", io.BytesIO(template_workbook(combined)))})
    assert r.status_code == 200 and "Imported" in r.text, r.text[-1500:]
    return combined

"""Settings, read once from environment variables (and a local `.env` file if present).

Every knob the app has lives here so deployments differ only by env vars.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Real env vars always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    admin_password: str
    secret_key: str
    is_production: bool
    auto_migrate: bool
    default_currency: str
    max_upload_mb: int
    mit_logos_approved: bool
    public_url: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    whatsapp_token: str
    whatsapp_phone_id: str
    whatsapp_api_version: str
    whatsapp_send_mode: str
    cron_secret: str


def _default_database_url(is_production: bool) -> str:
    if is_production:
        # Vercel's filesystem is read-only except /tmp. This keeps a demo running,
        # but data is lost on every cold start — set DATABASE_URL to Supabase.
        return "sqlite:////tmp/fichua.db"
    return f"sqlite:///{(ROOT_DIR / 'data' / 'fichua.db').as_posix()}"


def load_settings() -> Settings:
    is_production = bool(os.getenv("VERCEL")) or os.getenv("APP_ENV") == "production"
    return Settings(
        app_name=os.getenv("APP_NAME", "Fichua"),
        database_url=os.getenv("DATABASE_URL") or _default_database_url(is_production),
        # In production an unset password disables admin login entirely (see auth.py).
        admin_password=os.getenv("ADMIN_PASSWORD", "" if is_production else "admin"),
        secret_key=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        is_production=is_production,
        auto_migrate=_bool("AUTO_MIGRATE", True),
        default_currency=os.getenv("DEFAULT_CURRENCY", "USD"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "4")),
        # MIT's logos stay off until MIT's written OK is on file (backlog P1 #7); "Built at MIT" shows as words.
        mit_logos_approved=_bool("MIT_LOGOS_APPROVED", False),
        public_url=os.getenv("PUBLIC_URL", "").rstrip("/"),
        # Payments: without a Stripe key the site uses Fichua's built-in test checkout.
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", "").strip(),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", "").strip(),
        # WhatsApp Cloud API (Meta). Without these, messages are logged in admin, not sent.
        whatsapp_token=os.getenv("WHATSAPP_TOKEN", "").strip(),
        whatsapp_phone_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v23.0").strip(),
        # "template" (default): approved templates, delivered to anyone. "text": free text, which Meta
        # only delivers within 24 h of the person's last message (useful for a first test).
        whatsapp_send_mode=os.getenv("WHATSAPP_SEND_MODE", "template").strip().lower(),
        cron_secret=os.getenv("CRON_SECRET", "").strip(),
    )


settings = load_settings()

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
    )


settings = load_settings()

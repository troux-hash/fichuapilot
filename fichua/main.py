"""App factory: wires config, database migration, static files and routers."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import ROOT_DIR, settings
from .db import db
from .routes import admin, api, public

log = logging.getLogger("fichua")

if settings.is_production and db.dialect == "sqlite":
    log.warning("DATABASE_URL not set: using ephemeral SQLite in /tmp. Data will not persist.")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")
    # On Vercel, /static is served by the CDN straight from public/; this mount is for local dev.
    app.mount("/static", StaticFiles(directory=ROOT_DIR / "public" / "static", check_dir=False),
              name="static")
    app.include_router(public.router)
    app.include_router(admin.router)
    app.include_router(api.router)
    return app


app = create_app()

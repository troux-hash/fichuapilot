"""App factory: wires config, database migration, static files, routers and error pages."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ROOT_DIR, settings
from .db import db
from .routes import admin, api, partners, public
from .web import render

log = logging.getLogger("fichua")

if settings.is_production and db.dialect == "sqlite":
    log.warning("DATABASE_URL not set: using ephemeral SQLite in /tmp. Data will not persist.")


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _error_page(request: Request, status: int, detail, headers=None):
    """People get a friendly page; the JSON API keeps JSON errors."""
    if _wants_json(request):
        return JSONResponse({"detail": detail}, status_code=status, headers=headers)
    template = "pages/not_found.html" if status == 404 else "pages/error.html"
    return render(request, template, status_code=status, code=status)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")
    # On Vercel, /static is served by the CDN straight from public/; this mount is for local dev.
    app.mount("/static", StaticFiles(directory=ROOT_DIR / "public" / "static", check_dir=False),
              name="static")
    app.include_router(public.router)
    app.include_router(partners.router)
    app.include_router(admin.router)
    app.include_router(api.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _error_page(request, exc.status_code, exc.detail, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return _error_page(request, 400 if not _wants_json(request) else 422, exc.errors())

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_page(request, 500, "Internal Server Error")

    return app


app = create_app()

"""JSON API — the same services as the pages, ready for a future mobile app or partner widget."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..db import db
from ..services import catalog, dates
from ..services.search import Filters, search

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    with db.connect() as conn:
        conn.scalar("SELECT 1")
    return {"status": "ok", "database": db.dialect}


@router.get("/destinations")
def destinations():
    with db.connect() as conn:
        return catalog.destinations(conn)


@router.get("/search")
def api_search(request: Request):
    q = request.query_params
    stay = dates.parse_stay(q.get("check_in"), q.get("check_out"), q.get("guests"))
    with db.connect() as conn:
        data = search(conn, stay, q.get("destination") or None, Filters.from_query(q))
    return {"stay": {**stay.as_params(), "nights": stay.nights}, **data}

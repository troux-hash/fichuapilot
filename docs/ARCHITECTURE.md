# Architecture

One small Python app, server-rendered HTML, progressively enhanced with ~150 lines of vanilla JS.
No Node build, no ORM, no frontend framework — five production dependencies.

```
Browser ──▶ Vercel CDN ── /static/* ──▶ public/static (CSS, JS, images)
                 │
                 └── everything else ──▶ api/index.py (Python function) ──▶ fichua.main:app (FastAPI)
                                                                              │
                                    routes/  (HTTP only: parse request, call service, render)
                                    services/ (business rules: search, bookings, import, dates)
                                    db.py     (SQLite locally ⇄ Postgres in prod, same SQL)
                                                                              │
                                                                   Supabase Postgres (or AWS RDS)
```

## Folder map

| Path | What lives there | Change it when… |
|---|---|---|
| `fichua/config.py` | All settings from env vars | adding a knob |
| `fichua/db.py` | Tiny DB adapter (`all / one / scalar / run / run_many`) | switching DB engines (rarely) |
| `fichua/schema.sql` | The data model — portable Postgres | adding tables/columns (use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) |
| `fichua/services/` | Business logic, no HTTP | changing search ranking, booking rules, import format |
| `fichua/routes/` | `public.py` (guest pages), `admin.py`, `api.py` (JSON) | adding pages/endpoints |
| `fichua/templates/` | Jinja pages + `components/ui.html` macros | changing markup |
| `public/static/css/tokens.css` | **Design tokens** (colours, fonts, radii) | re-skinning — see `design/DESIGN_PRINCIPLES.md` |
| `public/static/css/components.css` | Component styles | changing a component |
| `public/static/js/app.js` | Progressive enhancement | changing interactions |
| `scripts/` | Synthetic data generator, CLI importer | — |
| `tests/` | End-to-end flow tests | always, with any change |

## Key decisions

- **Server-rendered + JSON API.** Pages are fast on any phone and SEO-friendly. `/api/search` exposes the same service for a future mobile app or partner widget (docs at `/api/docs`).
- **Availability is computed, not stored.** `room_rates.units` is what the hotel can sell; bookings consume nights in `booking_nights`. Re-uploading an Excel never wipes bookings.
- **Inventory re-check at booking time** with row locks (`FOR UPDATE`) on Postgres prevents double-selling the last room.
- **Excel import is all-or-nothing** with row-level errors, and idempotent (upsert by code).
- **No secrets in URLs.** Guests reach their booking via an opaque access token; manage-booking uses reference + email in a POST.
- **Partner logins later:** `hotels.hotel_group` already scopes data per group; swap `auth.py` for Supabase Auth when needed.

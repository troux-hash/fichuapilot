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
| `fichua/services/` | Business logic, no HTTP: `catalog` (availability), `search`, `bookings` (hold → pay → confirm → cancel), `payments` (test checkout / Stripe), `payouts`, `notify` (WhatsApp outbox), `partners` (accounts, codes, onboarding, calendar), `finance`, `app_settings`, `currency`, `importer` | changing rules |
| `fichua/routes/` | `public.py` (guest pages), `partners.py` (partner portal), `admin.py`, `api.py` (JSON, Stripe webhook, payout cron) | adding pages/endpoints |
| `fichua/templates/` | Jinja pages + `components/ui.html` macros | changing markup |
| `public/static/css/tokens.css` | **Design tokens** (colours, fonts, radii) | re-skinning — see `design/DESIGN_PRINCIPLES.md` |
| `public/static/css/components.css` | Component styles | changing a component |
| `public/static/js/app.js` | Progressive enhancement | changing interactions |
| `scripts/` | Synthetic data generator, CLI importer | — |
| `tests/` | End-to-end flow tests | always, with any change |

## The money and message flow

1. Guest checks out → booking `pending`, room held for `hold_minutes` (unpaid holds count against inventory).
2. Payment succeeds (test checkout, or Stripe success page / webhook — idempotent) → booking `confirmed`,
   commission = hotel's % (or default 7%), payout scheduled per the admin's payout timing.
3. Three WhatsApp messages (guest, hotel, Fichua) are written to `messages`, then sent if WhatsApp is connected.
4. Cancellation inside the free window → Stripe refund, payout cancelled (or flagged "recover").
5. Partners' calendar changes live in `rate_overrides` and win over Excel rates and the room's standard price.

## Key decisions

- **Server-rendered + JSON API.** Pages are fast on any phone and SEO-friendly. `/api/search` exposes the same service for a future mobile app or partner widget (docs at `/api/docs`).
- **Availability is computed, not stored.** `room_rates.units` is what the hotel can sell; bookings consume nights in `booking_nights`. Re-uploading an Excel never wipes bookings.
- **Inventory re-check at booking time** with row locks (`FOR UPDATE`) on Postgres prevents double-selling the last room.
- **Excel import is all-or-nothing** with row-level errors, and idempotent (upsert by code).
- **No secrets in URLs.** Guests reach their booking via an opaque access token; manage-booking uses reference + email in a POST.
- **Partner logins later:** `hotels.hotel_group` already scopes data per group; swap `auth.py` for Supabase Auth when needed.

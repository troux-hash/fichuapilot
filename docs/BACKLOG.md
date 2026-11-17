# Fichua Product Backlog

Prioritisation: **MoSCoW** + effort (S/M/L). The MVP is "Must" — shipped in v0.1.
Move items up/down freely; each item is written so it can become a GitHub Issue.

## ✅ v0.1 MVP (built)

| # | Feature | Notes |
|---|---|---|
| 1 | Three-question search (where / when / who) | Destination autocomplete, date presets (Tonight, This weekend, Next weekend, 1 week), guest stepper, defaults always filled |
| 2 | One-tap popular destinations + recent searches | Recent searches in browser localStorage |
| 3 | Results with total stay price + per-night | Only hotels with a room that fits the party and has inventory every night |
| 4 | Instant filters | Price max, stars, guest rating, free cancellation, breakfast, amenities; sort by recommended/price/rating |
| 5 | Hotel page | Gallery, description, amenities, rooms priced for the dates, sticky reserve bar |
| 6 | Guest checkout (no account, no payment today) | Name, email, phone, requests; inventory re-checked at booking time |
| 7 | Confirmation + manage booking lookup | Reference code + email → view or cancel |
| 8 | Admin: password login | Single admin via env var |
| 9 | Admin: Excel upload (Hotels / Rooms / Rates sheets) | Validation with row-level errors, upsert (re-upload safe), downloadable template |
| 10 | Admin: hotels & bookings lists | Read-only tables |
| 11 | Synthetic data | 24 hotels across 6 cities, 90 days of rates |
| 12 | Responsive: phone, iPad, laptop + dark mode | Design tokens in one file |
| 13 | Portable Postgres schema | Same SQL on Supabase, AWS RDS, or SQLite locally |

## 🔜 Should — next 2–4 iterations

| # | Feature | Effort | Why |
|---|---|---|---|
| 14 | Booking confirmation email (Resend free tier) | S | Trust; guests expect it |
| 15 | Hotel partner login (each group manages its own hotels) | M | Your stated v2 — Supabase Auth or magic links; `hotel_group` column already in schema |
| 16 | Admin web form to edit a hotel/room/rate inline | M | Fix typos without re-uploading Excel |
| 17 | Image upload to Supabase Storage | M | Replace placeholder URLs |
| 18 | Map view on results (Leaflet + OpenStreetMap, free) | M | `lat`/`lng` already in schema |
| 19 | Payments (Stripe Checkout) + deposit/pay-at-hotel option | L | Revenue; needs Vercel Pro (commercial use) |
| 20 | Hotel notification on new booking (email) | S | Hotels must know they have a booking |
| 21 | Analytics (Vercel Web Analytics free / Plausible) | S | Funnel: search → hotel → checkout → booked |
| 22 | SEO city landing pages (`/stays/lisbon`) | S | Free acquisition |

## 💡 Could — later

| # | Feature | Effort |
|---|---|---|
| 23 | Price-coloured calendar (cheapest dates) | M |
| 24 | Guest reviews after stay | M |
| 25 | Wishlists / saved hotels | S |
| 26 | Multi-room bookings (families/groups) | M |
| 27 | Multi-currency + i18n (FR / SW / ...) | M |
| 28 | Channel manager / PMS API integrations (replace Excel) | L |
| 29 | Natural-language search ("quiet beach hotel under $150 next weekend") with Claude | M |
| 30 | Promo codes / member prices | M |
| 31 | Guest accounts, trips history | M |
| 32 | Dynamic pricing suggestions for hotels | L |

## ❌ Won't (for now)

Flights/cars bundling · loyalty points · price-prediction ("book now or wait") · chat with hotel.

## Tech debt / ops

- Rate-limit booking & admin login endpoints.
- Automated DB backups (Supabase free tier has none — schedule `pg_dump` via GitHub Actions).
- E2E tests (Playwright) for the booking funnel.
- Replace single admin password with real auth once partners log in (#15).

# Fichua Product Backlog

Prioritisation: P1 = now, P2 = later. Each item is written so it can become a GitHub Issue.
Markets: Rwanda, Benin, Côte d'Ivoire. Master currency USD (RWF / CFA shown alongside).

## ✅ Shipped

| Area | Feature |
|---|---|
| Guest site | Three-question search, date presets, one-tap cities, recent searches, instant filters, hotel pages |
| Guest site | Futuristic "Aurora" design: dark glass, gradients, Sora + Manrope; responsive phone → laptop |
| Guest site | Full payment at booking (built-in test checkout; Stripe Checkout when a key is set), refunds on cancel |
| Guest site | Prices in USD with RWF / CFA equivalents; WhatsApp number at checkout; EN / FR message language |
| Partners | Join with an access code (email + password), hotel ID `FH-xxxxx` |
| Partners | Onboarding: details + map pin, photos (shrunk on the phone), room types + prices, policies, submit |
| Partners | Hotel Manager: calendar (prices, rooms to sell, closed dates, ranges, Fri/Sat), offline bookings, bookings list with payouts |
| Admin | Approvals with automatic anti-scam checks, per-hotel commission, request changes / reject |
| Admin | Finance: filters by period / hotel / country / source, totals, by-hotel table, payouts to send, Stripe links |
| Admin | Settings: default commission (7%), payout timing (immediate / after check-in / weekly), exchange rates, admin WhatsApp |
| Admin | Access codes (free Hotel Manager licence), WhatsApp outbox, Excel bulk upload |
| Platform | WhatsApp 3-way messages (guest, hotel, Fichua) after payment, cancellations, approval decisions |
| Platform | Daily payout job (Vercel Cron), portable Postgres schema with automatic column migrations |
| Trust | "Built at MIT" section with the MIT, MIT Sandbox and MIT Kuo Sharper Center logos in the guest footer, partner landing page and partner portal ([guide](BRAND_ASSETS.md)) |

## 🧪 QA findings — end-to-end test, 21 Nov 2026

Traveler, hotel operator and admin journeys tested on the local copy (videos in `qa/2026-11-21/`, kept out of git).
Full list with status tracking: [Fichua QA Backlog](https://claude.ai/artifact/HKnXLZX4Q9WQNiXj2Ct9ab) (34 items).

| ID | Priority | Fix |
|---|---|---|
| FIX-01 | **P0** | Public `/api/search` returns private hotel fields (owner ID, commission, owner contacts, review note, plan): return public fields only |
| FIX-02 | **P0** | Guest terms, privacy policy and readable partner terms, linked at checkout, join, policies step and footer |
| FIX-03 | **P0** | WhatsApp: send approved EN / FR utility templates instead of free text (needed before connecting WhatsApp) |
| FIX-04 | P1 | Partner review step wider than a phone (Edit links and prices cut off) |
| FIX-05 | P1 | Partner room list squeezes details on phones |
| FIX-06 | P1 | Multi-room walk-in fails when "Guests" is the group total, with a wrong "not enough rooms" message |
| FIX-07 | P1 | After cancelling, reopening the page shows a raw 405: redirect to the booking page |
| FIX-08 | P1 | App-wide friendly 404 / 405 / 500 pages (unknown links show raw JSON) |
| FIX-09 | P1 | Plurals: "1 bookings", "1 room types", "1 guests" |
| FIX-10 | P1 | Partner calendar on phones: range picking jumps away; booked nights not shown |
| FIX-11 | P1 | Partner bookings list as cards on phones |
| FIX-12 | P1 | Sticky "See rooms" bar covers Reserve on the hotel page |
| FIX-13 | P1 | Admin tables cut off at laptop width |
| FIX-14 | P1 | Named admin accounts, two-step login, rate limits |
| FIX-15 | P1 | Big-group searches: explain that no room fits, instead of "nothing available" |

Plus 18 smaller improvements (IMP-01 to IMP-18) and one setup task (SET-01) in the sheet.

## 🔜 P1 — next

| # | Feature | Needs |
|---|---|---|
| 1 | Switch Stripe from test mode to live (test mode is connected and working) | US company, Stripe account activation, `sk_live_` key |
| 2 | Connect WhatsApp (Meta test number, then verified business number + message templates) | Meta developer app |
| 3 | French for the partner portal and guest site (Benin, Côte d'Ivoire) | — |
| 4 | Automatic payouts to hotel bank accounts (Stripe Global Payouts: Benin + CI; Rwanda on request) | Stripe access |
| 5 | Map view on the guest results page (hotels already have pins) | — |
| 6 | Email confirmations (needs a verified domain) | Domain |
| 7 | Get written OK from MIT for the logos, and swap in official SVG files when they arrive | ioc-useofname@mit.edu, sandbox@mit.edu, kuosharper@mit.edu ([guide](BRAND_ASSETS.md)) |

## 💡 P2 — later

| # | Feature |
|---|---|
| 8 | Deposit / pay-at-hotel options per hotel |
| 9 | Mobile money (MTN MoMo, Orange Money, Moov, Wave, Airtel) via one regional aggregator |
| 10 | Hotel Manager subscription billing (monthly fee, deducted from payouts) |
| 11 | Several users per hotel; one login for hotel groups |
| 12 | Rate options: non-refundable discount, minimum stay, promotions |
| 13 | Calendar sync with Booking.com / Airbnb (iCal) |
| 14 | Reviews after stay, wishlists, guest accounts |
| 15 | Request-to-book for hotels with unreliable calendars |
| 16 | Photos to object storage (Supabase Storage / S3) instead of the database |
| 17 | Password reset by email / WhatsApp code; Google sign-in |

## Tech debt / ops

- Rate-limit login, join and booking endpoints.
- Automated database backups (Supabase free tier has none): nightly `pg_dump` via GitHub Actions.
- Browser end-to-end tests (Playwright) for the booking and onboarding funnels.

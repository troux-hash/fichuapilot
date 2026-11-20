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

## 🔜 P1 — next

| # | Feature | Needs |
|---|---|---|
| 1 | Switch payments to Stripe test mode, then live | `STRIPE_SECRET_KEY` + webhook secret |
| 2 | Connect WhatsApp (Meta test number, then verified business number + message templates) | Meta developer app |
| 3 | French for the partner portal and guest site (Benin, Côte d'Ivoire) | — |
| 4 | Automatic payouts to hotel bank accounts (Stripe Global Payouts: Benin + CI; Rwanda on request) | Stripe access |
| 5 | Map view on the guest results page (hotels already have pins) | — |
| 6 | Email confirmations (needs a verified domain) | Domain |

## 💡 P2 — later

| # | Feature |
|---|---|
| 7 | Deposit / pay-at-hotel options per hotel |
| 8 | Mobile money (MTN MoMo, Orange Money, Moov, Wave, Airtel) via one regional aggregator |
| 9 | Hotel Manager subscription billing (monthly fee, deducted from payouts) |
| 10 | Several users per hotel; one login for hotel groups |
| 11 | Rate options: non-refundable discount, minimum stay, promotions |
| 12 | Calendar sync with Booking.com / Airbnb (iCal) |
| 13 | Reviews after stay, wishlists, guest accounts |
| 14 | Request-to-book for hotels with unreliable calendars |
| 15 | Photos to object storage (Supabase Storage / S3) instead of the database |
| 16 | Password reset by email / WhatsApp code; Google sign-in |

## Tech debt / ops

- Rate-limit login, join and booking endpoints.
- Automated database backups (Supabase free tier has none): nightly `pg_dump` via GitHub Actions.
- Browser end-to-end tests (Playwright) for the booking and onboarding funnels.

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

All 3 P0 and 12 P1 fixes shipped on 21 Nov 2026:

| ID | Priority | Fix | Status |
|---|---|---|---|
| FIX-01 | **P0** | Public `/api/search` returns public hotel and room fields only | ✅ Shipped |
| FIX-02 | **P0** | Terms of service, privacy policy and partner terms, linked at checkout, join, policies step and footer (company details in Admin → Settings; lawyer review still to do) | ✅ Shipped |
| FIX-03 | **P0** | WhatsApp sends approved EN / FR utility templates (create them with `scripts/whatsapp_templates.py`) | ✅ Shipped |
| FIX-04 | P1 | Partner review step fits a phone | ✅ Shipped |
| FIX-05 | P1 | Partner room list fits a phone | ✅ Shipped |
| FIX-06 | P1 | Walk-in "Guests" is the group total, shared over the rooms, with the real reason when it can't fit | ✅ Shipped |
| FIX-07 | P1 | Cancelling redirects to the booking page (reload-safe) | ✅ Shipped |
| FIX-08 | P1 | Friendly 404 / 405 / 400 / 500 pages; `/api` keeps JSON | ✅ Shipped |
| FIX-09 | P1 | Plurals fixed ("1 booking", "1 room type", "1 guest") | ✅ Shipped |
| FIX-10 | P1 | Partner calendar on phones: stays on the calendar while picking a range; nights with bookings marked | ✅ Shipped |
| FIX-11 | P1 | Partner bookings as cards on phones | ✅ Shipped |
| FIX-12 | P1 | Hotel page: sticky "See rooms" bar hides while the rooms are on screen | ✅ Shipped |
| FIX-13 | P1 | Admin tables fit a 1280 px laptop | ✅ Shipped |
| FIX-14 | P1 | Named admin accounts, two-step login (TOTP), rate limits on sign-in, sign-up and checkout | ✅ Shipped |
| FIX-15 | P1 | Big-group searches explain that no room fits that many guests | ✅ Shipped |

P2 improvements:

| ID | Improvement | Status |
|---|---|---|
| IMP-01 | Search, hotel and checkout pages say "We changed your dates to …" when a link asked for impossible dates | ✅ Shipped |
| IMP-02 | Booking page: directions, call or WhatsApp the hotel, add to calendar (.ics and Google Calendar) | ✅ Shipped |
| IMP-03 | Hotel page: full address (area, city) and a map from the hotel's pin | ✅ Shipped |
| IMP-04 | "Free cancellation until 29 Nov" everywhere; the guest's Cancel button follows the same date | ✅ Shipped |
| IMP-05 | Checkout errors clear as soon as the guest fixes the field | ✅ Shipped |
| IMP-06 | Refund timing in the cancel message | ✅ Shipped |
| IMP-07 | Result cards and thumbnails load an ~800 px photo (partner uploads keep a small copy) | ✅ Shipped |
| IMP-08 | Wording: "2 nights × $65", reference on one line, "Tap or click" map, "Pin set" | ✅ Shipped |
| IMP-09 | Partner sign-up and log-in errors scroll into view and put the cursor in the field to fix | ✅ Shipped |
| IMP-10 | Photos: styled "Choose photos" button, upload starts on choosing, "Continue" is the main button from 3 photos | ✅ Shipped |
| IMP-11 | A walk-in for several rooms is one booking (one row, one Cancel), with "× 3" on the room | ✅ Shipped |
| IMP-12 | A live hotel's admin page offers "Save commission" and "Hide from guests" / "Show to guests again" | ✅ Shipped |
| IMP-13 | On submit, the hotel gets "Listing received" and Fichua gets "New hotel to review" (two new WhatsApp templates) | ✅ Shipped |
| IMP-14 | Admin hotels list: search by name, city or ID; filter by status, country and group | ✅ Shipped |
| IMP-15 | Access codes: "WhatsApp" link opens a chat with the code and partner link written (English and French) | ✅ Shipped |
| IMP-16 | French number formats in WhatsApp | ✅ Shipped |
| IMP-17 | Settings error wording | ✅ Shipped |
| IMP-18 | Several rooms of one type in one booking: "Rooms" in search and on the hotel page, prices for every room, big groups get a "5 guests in 3 rooms" search | ✅ Shipped |

All 18 improvements are shipped. Still open: one setup task (SET-01: Fichua's WhatsApp number in Admin → Settings, once WhatsApp is connected).
Not covered by IMP-18: mixing room types in one booking (e.g. 1 Double + 1 Family), which needs a booking-lines table.

## 🎨 Persona-led redesign — 21 Nov 2026

From the operator and traveller briefs and the 18 premium-tier personas. Recommendations and decisions for the founders:
[Fichua — Persona-led experience and go-to-market](https://claude.ai/artifact/LJyFZLKbs8hfWLJH58t8rG).

Shipped now (needed no decision):

| Area | Change |
|---|---|
| Look | Editorial theme: white pages, Ink / Clay / Verified green / Surface, Newsreader headings; the dark Aurora look stays at `?theme=aurora` |
| Trust | No generated guest ratings or review counts anywhere (cards, hotel page, checkout, API, "Top rated" sort, rating filter); no "Only N left"; no unprovable claims |
| Home | "Know who's behind the door": ways in by trip purpose, "What we check before a place goes live", how booking works, a line for owners |
| Hotel page | "Reviewed by the Fichua team" strip, "Good to know", price and cancellation rules first on phones, the rules drawn as a bar with dates and dollars (also at checkout) |
| Ask the hotel | "Ask the hotel on WhatsApp" before booking, with the dates and an `ASK-` reference recorded in `enquiries` (needs the hotel's reception phone) |
| Confirmation | "You're booked. {Hotel} is expecting you on {date}." |
| Search and AI | schema.org Hotel data (no ratings), canonical address, link previews for WhatsApp and social, `/sitemap.xml`, `/robots.txt` |
| Partners | Landing rewritten for owners: their story and control first, agents and tour operators kept; reception-phone hint says guests may call or WhatsApp |
| Addresses | Readable hotel addresses, e.g. `/stays/rwanda/musanze/volcano-view-lodge-mus-002`; the id at the end keeps them unique and rename-proof; old `/hotels/<id>` links redirect |
| Hosts | Optional "Host profile" in the partner portal (first name, role, languages, welcome, photo), shown only while the owner's consent box is ticked: "Your host" on the hotel page, "With Eric" on result cards, the host's name on the confirmation |
| Business travel | "I need an invoice" at checkout (company, tax number, address, PO), shown to the hotel in its bookings list; a printable payment receipt; the hotel's registered name and tax number (optional, in Hotel details) printed on it |
| Arrival | "Show at the door": the booking on one screen, big enough to read across a desk, and plainly void when cancelled |

Waiting on founder decisions: money flow ("Fichua never holds your money" or "held until you arrive"), cancellation presets
(7 / 14 / 30 days), one pricing rule for owners, Côte d'Ivoire in the pilot, the founding properties (real photos, host
portraits and stories to replace the demo catalogue). Waiting on WhatsApp: the build-first "reveal" flow for owners.

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

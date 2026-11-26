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
| Partners | Onboarding: details + map pin, photos (shrunk on the phone, sent in batches under the host's 4.5 MB request limit), room types + prices, policies, submit |
| Partners | Hotel Manager: calendar (prices, rooms to sell, closed dates, ranges, Fri/Sat), offline bookings, bookings list with payouts |
| Admin | Approvals with automatic anti-scam checks, per-hotel commission, request changes / reject |
| Admin | Finance: filters by period / hotel / country / source, totals, by-hotel table, payouts to send, Stripe links |
| Admin | Settings: default commission (7%), payout timing (immediate / after check-in / weekly), exchange rates, admin WhatsApp |
| Admin | Access codes (free Hotel Manager licence), WhatsApp outbox, Excel bulk upload |
| Platform | WhatsApp 3-way messages (guest, hotel, Fichua) after payment, cancellations, approval decisions |
| Platform | Daily payout job (Vercel Cron), portable Postgres schema with automatic column migrations |
| Trust | "Built at MIT" section with the MIT, MIT Sandbox and MIT Kuo Sharper Center logos in the guest footer, partner landing page and partner portal ([guide](BRAND_ASSETS.md)) |
| Guest site | Brief 3 v3: search starts with the kind of stay (five kinds), then where and when with dates optional; results grouped by kind, ranked by fit then verification (never price, fees or reply speed) |
| Guest site | Each place shows the five checks with their dates, its host, price and terms, where the money goes (host's share, Fichua's fee paid by the host) and how it runs (people, place, money) |
| Guest site | "Ask your host" page before WhatsApp: the message, the traveller's question, and the rule that booking and payment stay on Fichua |
| Guest site | Every traveller page in English and French (EN/FR switch, remembered; the browser's language on a first visit) |
| Guest site | "Starting in Rwanda, Benin and Côte d'Ivoire", with "Built at MIT, for Africa first and the World" in small type below |
| Partners | Kind of place and "good for" tags on the hotel details step; a home page with this month's questions, bookings, money, next arrivals and a share kit |
| Admin | The kind of place, the five checks with dates and how the place runs, recorded on the review page; catalogue depth by kind and country on the dashboard |

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

Decided on 21 Nov 2026: Fichua is built from Africa for the world, and the pilot starts in Rwanda, Benin and Côte d'Ivoire
together, each market with its own lead (Rwanda: park lodges and Kigali boutiques; Côte d'Ivoire: the largest premium pool
and Abidjan weekenders; Benin: heritage and diaspora travel around the January Vodun festival).

Waiting on founder decisions: money flow ("Fichua never holds your money" or "held until you arrive"), cancellation presets
(7 / 14 / 30 days), one pricing rule for owners, the founding properties (real photos, host portraits and stories to replace
the demo catalogue). Waiting on WhatsApp: the build-first "reveal" flow for owners.

## 🧭 Brief 3 v3 build and decisions (25 Nov 2026)

The traveller, operator and admin prototypes were built into the sites, with three decisions taken the same day:

- **Countries:** say only "Starting in Rwanda, Benin and Côte d'Ivoire", with "Built at MIT, for Africa first and the World"
  in small type below (home page, footer, video end cards).
- **Payment:** Fichua secures the payment (today's card checkout; the money panel says the fee is paid by the host).
- **Ranking by reply speed:** removed for good, not a feature to build. Results rank by fit, then verification.
  The "I reply within …" host promise (R2-O6) is dropped with it: no reply-speed features at all.

Places listed before kinds existed get a kind inferred from their type and name (owners and the team can change it).
Places reviewed before the five checks show "Reviewed by Fichua" until the team records the checks.

Still in the prototypes, not built (each needs a decision or a service first):

| ID | Priority | Side | From the prototypes | Needs |
|---|---|---|---|---|
| B3-01 | P2 | Owners | Sign in with a code sent on WhatsApp, no password | WhatsApp connected (SET-02) |
| B3-02 | P2 | Owners | Fichua drafts the page from what the owner shared; the owner approves each item ("Looks right" / "Change") | Decision on concierge onboarding |
| B3-03 | P2 | Travellers | Partly verified places take booking requests, paid once the host accepts | Decision, then a request flow |
| B3-04 | P2 | Travellers | 30% deposit and mobile money (MTN MoMo, Airtel, Moov) | Payment decision and a provider |
| B3-05 | P2 | Travellers | "Tell me when one joins" for searches with no place yet, listed for the team | — |
| B3-06 | P2 | Travellers | Facts with their source, "Nearby", and "Why you haven't seen it elsewhere" on each page | Owner and team content |
| B3-07 | P2 | Everyone | Partner portal and admin in French (the traveller pages already are) | — |
| B3-08 | P3 | Admin | Search health: the friction map from Brief 3 with targets | Analytics (R2-T1) |
| B3-09 | P3 | Owners | First 10 bookings free, then 7–12% | Pricing decision |

## 🧪 QA findings — round 4, the Brief 3 v3 build (25 Nov 2026)

A fourth end-to-end run on the local copy, rewritten for the new journeys: 55 steps in headless Edge (the traveller
picks a kind of stay, then where and when, reads the dated checks and the money panel, asks the host, books, pays and
cancels a second stay; the owner picks a kind of place and opens the new home; the team records the five checks and
approves). No JavaScript errors, no failed requests and no sideways scrolling. 88 automated tests pass (9 new in
`tests/test_kinds.py`). Narrated walkthrough videos are in `qa/2026-11-25-round4/`, kept out of git.

| ID | Priority | Bug | Fix | Status |
|---|---|---|---|---|
| R4-B1 | P1 | The redesign dropped the big-group help ("no single room sleeps 12", with a one-tap search for enough rooms) | Restored on the new results page (caught by the tests before release) | ✅ Live 25 Nov |
| R4-B2 | P2 | French header on phones: "Gérer une réservation" was cut off next to the EN/FR switch | Header links hide under 480 px; both are in the footer | ✅ Live 25 Nov |
| R4-B3 | P2 | Owner home and bookings: three number tiles squeezed into one row on phones (also R2-O4) | Two tiles per row on phones | ✅ Live 25 Nov |
| R4-B4 | P2 | The new owner-home and dashboard counts compared timestamps with text: fine on SQLite, risky on Postgres | Real timestamps in the queries | ✅ Live 25 Nov |
| R4-B5 | P3 | French "why it matches" read with two colons in a row | "Kind. Reason." in both languages | ✅ Live 25 Nov |
| R4-B6 | P3 | Admin check dates and notes used the browser's plain inputs | Styled like every other field | ✅ Live 25 Nov |

## 🧪 QA findings — round 3, before going live (25 Nov 2026)

A third end-to-end run on the local copy with the round-2 fixes in: the same 44 steps in headless Edge (phones at
390 × 844, admin at 1280 × 800), then a page-by-page check of the guest site, the partner portal and admin at phone and
laptop widths (124 page views). No JavaScript errors, no failed requests and no sideways scrolling, and each round-2 fix
was checked on screen. The one bug below shows only on the live host, so it was confirmed there with a test upload sent
without signing in, which stored nothing. Walkthrough videos (traveller, operator, admin) are in `qa/2026-11-25-round3/`,
kept out of git. Tests are in `tests/test_round3.py`.

| ID | Priority | Bug | Fix | Status |
|---|---|---|---|---|
| R3-B1 | **P1** | Photos and room pages sent every chosen photo in one request. Vercel refuses requests over 4.5 MB (on the live site a 4 MB upload got through and a 5 MB one was refused), so choosing a handful of phone photos at once (roughly 6 to 15, depending on the photos) ended on a bare "Request Entity Too Large" page | Photos go up in batches under 3.5 MB, each with its card copy. A new room's later batches go to the room the first batch created. Each photo is decoded once instead of twice, and a phone that stalls while resizing gets 20 seconds before the photo goes as it is; a photo still over 3 MB is stopped before sending, with a plain message. Checked in a normal browser: 12 photos went in 3 batches, 9 room photos in 3, and a host photo in 1 | ✅ Live 25 Nov |

Test tool, not the product: in long headless sessions the test browser froze while resizing photos, which never happened
in single runs or a normal browser. The test now sends its photos directly, and the batch upload above was checked
separately in a normal browser.

## 🧪 QA findings — round 2, after the redesign (21 Nov 2026)

A second end-to-end run on the local copy after the persona-led redesign: 44 steps in headless Edge (phones at
390 × 844, admin at 1280 × 800). It ran from the admin's invitation through the owner's listing, approval, a traveller's
booking, door card, receipt and refund, then the owner's and the admin's follow-up. Automatic checks on every step found no
JavaScript errors, no failed requests and no sideways scrolling; the bugs below came from reviewing each screen.
Walkthrough videos (traveller, operator, admin) are in `qa/2026-11-21-round2/`, kept out of git. Tracking:
[Fichua QA Backlog](https://claude.ai/artifact/HKnXLZX4Q9WQNiXj2Ct9ab) (62 items after round 3).

Bugs, fixed in commit `96412ac` (tests in `tests/test_round2.py`), checked again in round 3 and live since 25 Nov 2026:

| ID | Priority | Bug | Fix | Status |
|---|---|---|---|---|
| R2-B1 | P1 | Hotel page on phones: the sticky bar grows to a third of the screen once the WhatsApp button is there | Two rows: total and dates, then WhatsApp and See rooms side by side | ✅ Live 25 Nov |
| R2-B2 | P1 | Multi-night prices with cents and a misleading "From $178.33 / night" (an average, not a minimum) | The total for the stay first; the nightly figure in whole dollars, "avg" when nights differ | ✅ Live 25 Nov |
| R2-B3 | P2 | The photos step claims "8 or more photos get more bookings" with no data behind it | Plain guidance on what to photograph | ✅ Live 25 Nov |
| R2-B4 | P2 | Room list: the RWF figure follows the Fri–Sat price, so it reads as the weekend price | RWF sits next to the standard price it converts | ✅ Live 25 Nov |
| R2-B5 | P2 | The calendar reopens on the current month after saving another month's prices | It reopens on the month that changed | ✅ Live 25 Nov |
| R2-B6 | P1 | The approval page hides the host profile and the business details, though both reach guests | Both shown before approving, with the host's consent state | ✅ Live 25 Nov |
| R2-B7 | P3 | Admin sign-in still sets the old navy browser colour on phones | Ink | ✅ Live 25 Nov |

Improvements to build (not started):

| ID | Priority | Side | Improvement | Why |
|---|---|---|---|---|
| R2-T1 | **P1** | Travellers | Funnel analytics: search → hotel view → ask → checkout → paid, with the channel (`utm_source`), stored in Fichua's own database and shown in admin; no third-party tracker | No go-to-market decision can rest on data today |
| R2-T2 | **P1** | Travellers | Destination pages ("Where to stay near Volcanoes National Park", "Lake Kivu", "Ouidah") listing reviewed places with plain facts, in the sitemap with schema.org data | Travellers decide in AI answers and search before they reach a booking site |
| R2-O1 | **P1** | Owners | Owners see their "Ask on WhatsApp" enquiries (`ASK-` codes) and a monthly count (the count is on the new owner home; the list is still to do) | The first proof of value, before any booking |
| R2-A1 | **P1** | Admin | Dashboard: enquiries, enquiry-to-booking rate, hotels with a host profile, approvals as a list (enquiries and verified places are on the dashboard; the rate and the list are still to do) | The numbers that run the pilot |
| R2-T3 | P2 | Travellers | One WhatsApp button per phone screen (the sticky bar); the others become text links | Three equal calls to action dilute the path to booking |
| R2-T4 | P2 | Travellers | "Share with family" on WhatsApp, with the dates and the total | Many trips are decided with family on WhatsApp |
| R2-T5 | P2 | Travellers | Shortlist and compare up to three places, no account | Travellers compare in tabs and lose track |
| R2-T6 | P2 | Travellers | Confirmation email matching the booking page (same as P1 #6; needs a domain) | Today the booking lives on a bookmarked page |
| R2-T7 | P2 | Travellers | Search suggestions for regions, parks and lakes | People type "Lake Kivu", not "Rubavu" |
| R2-O2 | P2 | Owners | The review step suggests the optional host profile | Owners may submit without ever seeing it |
| R2-O3 | P2 | Owners | A caption on each photo, also used as alt text | Guests and search engines read captions |
| R2-O4 | P2 | Owners | Bookings totals two per row on phones (✅ done in round 4) | "after commission" wraps over three lines |
| R2-O5 | P2 | Owners | A "Join with my code" button at the top of the partner page on phones | The form starts below a full screen of pitch |
| R2-O6 | ~~P2~~ | Owners | ~~"I reply within …", shown to guests once reply times are measured~~ **Dropped 25 Nov 2026** with ranking by reply speed: no reply-speed features | — |
| R2-A2 | P2 | Admin | Finance export (CSV) | Month-end work happens in a spreadsheet |
| R2-A3 | P2 | Admin | Audit trail for approvals, commission changes and hiding a hotel | Needed once several people use admin |
| R2-T8 | P3 | Travellers | An occasion at checkout (anniversary, birthday), passed to the host | A personal touch the host can act on |

Setup still blocking (SET-02 to SET-04 in the sheet): the WhatsApp access token (messages wait in the outbox), the
founder decisions above, and real photos and host stories for the founding properties.

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

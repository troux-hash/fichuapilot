# Customer Journey Teardown — Hotel Search & Booking

Competitors reviewed: **Airbnb, Booking.com, Kayak, Expedia, Google Hotels, Hopper**.
Purpose: steal the best patterns, drop the friction, and define the Fichua journey.

> Method: product teardown based on the current public web/mobile flows of each product
> (search → results → property → checkout → confirmation → post-booking).
> Re-validate quarterly; these products A/B test constantly.

---

## 1. Journey stages compared

| Stage | Airbnb | Booking.com | Kayak | Expedia | Google Hotels | Hopper |
|---|---|---|---|---|---|---|
| **Entry / search** | 3-part pill: *Where · When · Who*. Expands into a guided sheet on mobile. Flexible dates ("weekend", "a week", month picker). | Single long bar: destination, dates, guests/rooms. Strong autocomplete with recent searches. | Bar + "flexible ±3 days" toggle. Compare-across-sites checkboxes. | Tabbed (Stays/Flights/Cars/Packages). Bundling nudges. | Search starts from Google itself — the query *is* the search ("hotels in Lisbon this weekend"). | Mobile-first. Destination → calendar coloured by price (green = cheap). |
| **Dates** | Calendar + "flexible" mode; shows nights count. | Two-month calendar; price hints on some markets. | Calendar + ±1/2/3 day flexibility. | Calendar with flexible-dates option. | Inline date chips, prices shown per date. | **Price-coloured calendar** — best-in-class for date choice. |
| **Results** | Map + cards, big photos, **total price incl. fees** toggle. Category carousels. | Dense list, many badges (Genius, "only 2 left"), heavy filters. | Aggregated prices from many sites; "best deal" scoring; price-history hints. | List + map; member prices; points. | Clean list + map, price comparison per provider, ratings from Google reviews. | Card list with "buy now or wait" price prediction. |
| **Filters** | Price histogram, type of place, rooms/beds, amenities, instant book. | Most comprehensive: budget, popular filters (learned), stars, review score, meals, free cancellation, distance. | Price, stars, review score, freebies (breakfast, wifi), neighbourhood. | Popular filters, price, guest rating, payment type (pay later), amenities. | Price, rating, class, amenities, "deals". | Minimal. |
| **Property page** | Photo grid hero → highlights → amenities → reviews → map → host. Sticky price & "Reserve" box. | Very long: photos, room table, facilities, house rules, Q&A, reviews. Room table is the key booking surface. | Mostly redirects to provider. | Room cards with pictures, refundable vs non-refundable price pair. | Overview → prices per provider → reviews → location. | Simple room list with predicted savings. |
| **Room selection** | N/A (whole listing). | Table: room type, sleeps, price, choices (breakfast, cancellation), select qty. | Provider-side. | **Room cards with clear "Refundable / Non-refundable" option pricing** — best clarity. | Provider-side. | Simple cards. |
| **Checkout** | 1 page: trip summary + price breakdown + payment + "Confirm and pay". Login required. | 3 steps: your details → final details → confirmation. **No account needed**, "no payment needed today" options. | Redirect to OTA/hotel. | 1 long page: traveller, payment, protection upsells. | Redirect. | Native, Apple/Google Pay. |
| **Confirmation** | Itinerary + messaging host. | Email + app, PIN to manage booking. | N/A | Itinerary + loyalty points. | N/A | Itinerary, price-freeze info. |
| **Post-booking** | Messaging, check-in instructions, reviews. | Manage booking (dates, cancel), reviews. | Price alerts. | Trips, change/cancel, rewards. | — | Price freeze, alerts. |

## 2. Best-in-class patterns to copy

1. **Three-question search** (Airbnb): *Where? When? Who?* — nothing else on the first screen.
2. **One-tap destinations and date presets** (Airbnb flexible dates / Google chips): "This weekend", "Next weekend", "1 week" — no calendar needed for 80% of trips.
3. **Recent searches** (Booking.com): returning users repeat a search in one tap.
4. **Total price, always** (Airbnb's total-price toggle, now regulation in many markets): show *total for the stay* first, per-night second. Builds trust, kills checkout shock.
5. **Refundable clarity** (Expedia): free cancellation shown as a first-class badge and filter.
6. **Instant filters** (Booking.com popular filters): apply without a "submit" button; show counts.
7. **Sticky price/CTA box** (Airbnb): the "Reserve" action is always visible on the property page; on mobile it is a bottom bar.
8. **Guest checkout, no account** (Booking.com): asking for an account before paying loses conversions.
9. **"No payment needed today"** (Booking.com): reduces risk for the guest — and fits an MVP without payments.
10. **Confirmation reference + email lookup** (Booking.com PIN): manage booking without a password.
11. **Price-coloured calendar** (Hopper/Google): backlog — needs rate data density first.
12. **Map view** (all): backlog — high value, but needs geodata and a map provider.

## 3. Friction to remove

| Friction seen | Where | Fichua answer |
|---|---|---|
| Urgency/scarcity dark patterns ("3 people looking!") | Booking.com, Expedia | Only factual signals ("2 rooms left" from real inventory). Trust > pressure. |
| Fees revealed at checkout | Expedia, older Airbnb | All-in total on every card. |
| Account wall before booking | Airbnb | Guest checkout. |
| 3-step checkout | Booking.com | One page, 4 fields (name, email, phone, requests). |
| Bundle/upsell noise | Expedia | None in MVP. |
| Redirect to third parties | Kayak, Google | Native booking end-to-end. |
| Overloaded filter panels | Booking.com | 6 filters that matter; rest in backlog. |
| Rooms selector separate from guests | Booking.com | Guests drive the room match; system picks rooms that fit. |

## 4. The Fichua journey (target: results in < 10 seconds, booking in < 60 seconds)

```
HOME  ──(1 tap: popular city chip  ─or─  type 2 letters + pick date preset)──▶  RESULTS
RESULTS ──(instant filters, sort, total price visible)──▶ HOTEL
HOTEL ──(rooms already priced for your dates; tap "Reserve")──▶ CHECKOUT
CHECKOUT ──(4 fields, no payment today)──▶ CONFIRMATION (reference + manage link)
```

- **Fastest path**: tap "Lisbon" chip → results for next weekend, 2 adults (2 taps to see prices).
- **Typical path**: type "Na" → "Nairobi" → tap "This weekend" → Search (4 taps).
- Defaults are always filled: dates = next weekend, guests = 2 adults. The search button is never disabled.
- Every screen works one-handed on a phone; tablet and laptop get wider grids and a filter sidebar.

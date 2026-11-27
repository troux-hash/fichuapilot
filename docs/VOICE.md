# How Fichua speaks

Written 27 Nov 2026, with the site-wide copy rewrite. Use it for every new sentence, in English and French.

## Who reads us, and when

Travellers decide in steps: **what kind of stay → where and when → which place → can I trust it → book**.
Each page answers the question of its step, and nothing else. The doubt that stops a booking (the total,
the fee, the refund, "is this real?") is answered where it comes up, in one sentence.

Owners read us between guests, often on a phone. They want to know: will it bring bookings, what does it
cost, what do I keep control of, how much work is it.

## Rules

1. **Travellers' words, not ours.** Hotel, lodge, stay, room, price, booking. Never inventory, listing,
   OTA, conversion. Travellers see "Fichua’s fee"; owners see "commission".
2. **One word for one thing** (table below). A second word makes people think it is a second thing.
3. **Buttons say what happens next**: verb + object. "See rooms and book", "Pay $160 and confirm",
   "Next: where and when". Never "Submit", "Continue" or "Click here".
4. **Short.** One idea per sentence, about 20 words at most. Contractions are fine (you’re, it’s,
   don’t). No "please", "simply", "just", "seamless", "unique".
5. **We is the Fichua team; your host is the person who runs the place.** Speak to "you".
6. **Only promise what is live.** Mobile money says "coming soon". No urgency we can’t prove, no claim
   about ranking beyond the rule: best match first, then the most checked, and no one can pay to rank higher.
7. **Typography.** Curly apostrophes and quotes (’ “ ”). British spelling (travellers, cancelled). Prices
   as $160. In `fr.py`, the space before : ; ? ! is typed as an ordinary space; the table adds the thin
   no-break space French needs.
8. **French uses vous**, and the same one-word-per-thing rule: séjour, hôte, réservation, référence Fichua,
   commission de Fichua.

## Vocabulary

| Say | Not | French |
|---|---|---|
| type of stay (the five) | kind of place, category | type de séjour |
| place (a hotel or lodge) | property, listing | lieu |
| host | operator, owner (to travellers) | hôte |
| Manage booking (menu, WhatsApp) | My trips, Bookings | Gérer ma réservation |
| Find your booking (the form) | Look up | Retrouver votre réservation |
| Fichua reference | booking code, PNR | référence Fichua |
| total price, all-in | rate, from-price | prix total, tout compris |
| Fichua’s fee | commission, service charge | commission de Fichua |
| Test mode | pilot, sandbox, demo | Mode test |
| Fichua Verified, the five checks | vetted, certified | Vérifié par Fichua, les cinq contrôles |
| invitation code (owners) | access code | — (owner pages are English) |

## Search and sharing

Page titles lead with what people type into a search engine: "Independent hotels & lodges in Rwanda,
Benin and Côte d’Ivoire"; a place is "Name, City"; results are "Type of stay · Where". The description
under a search result names the benefit in one line: talk to your host, pay securely, see every fee.

## Change with care

- **WhatsApp messages are Meta-approved templates** (`fichua/services/whatsapp_templates.py`). New wording
  needs a new template version and Meta’s approval (`scripts/whatsapp_templates.py`). That is why the menu
  says "Manage booking": the cancellation message points travellers there.
- **The founder’s lines stay word for word**: the mission and "Fichua is Swahili for…", "What kind of stay
  are you looking for?", "Talk to your host directly. We take care of the rest.", "Built at MIT, for Africa
  first and the World", "Starting in Rwanda, Benin and Côte d’Ivoire", and the 7% line for owners.

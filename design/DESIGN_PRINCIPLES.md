# Fichua Design Principles

The single source of truth for **look and feel** is one file:
[`public/static/css/tokens.css`](../public/static/css/tokens.css). Change a token there and the product follows;
no component contains a raw colour, font or radius.

The direction comes from the two experience briefs (operator sign-up, traveller discovery) and the premium-tier
personas: a page that reads like a well-edited travel magazine, where the place and the people come before the price.
*Fichua* is Swahili for "to reveal": the brand line is **Know who's behind the door.**

## Two themes, one palette

| | Guest site ("Editorial") | Partners + Admin ("Pro") |
|---|---|---|
| Mood | Warm, calm, photo-led | Quiet and practical; the owner's page is the hero |
| Background | White pages, Surface `#F1F3F1` bands between sections | Surface `#F1F3F1`, white cards, Ink sidebar |
| Text | Ink `#2B1D19` | Ink `#2B1D19` |
| Primary action | Clay `#B5462F`, white text, 8 px radius, once per screen | Same |
| Trust and success | Verified green `#2F5D46` | Same |
| WhatsApp | WhatsApp green `#1F7A4D`, always labelled | Same |

Theme switch: the guest pages use `:root` tokens; partner and admin pages add `class="theme-pro"` to `<body>`.

## Principles

1. **Face before price.** The place, its story and (once collected) its host come before the price.
2. **One honest number.** The total for the stay, in US dollars with local currency beside it; no booking fees.
3. **Plain rules beside the price.** Cancellation is drawn as a bar with dates and dollar amounts, from one rule
   (`services/policies.py`) shared by the badge, checkout, the Cancel button and the terms.
4. **A person is one tap away.** "Ask the hotel on WhatsApp" with the dates and a reference code, before booking.
5. **No dark patterns.** No generated ratings, no "only N left", no countdowns, no claims we cannot show.
6. **Thumb-first and accessible.** Designed at 375 px first; touch targets ≥ 44 px; WCAG AA contrast; works without JavaScript.

## Typography

- **Newsreader** (serif): property names, headings, stories. Warm and editorial; carries French accents.
- **Manrope** (sans): interface, labels, forms and prices (tabular figures).
- The hotel class is written as words ("4-star"): the star symbol is kept for Fichua's own mark.
- Before launch, test the Fon and Baoulé letters (ɛ, ɔ, ɖ) with real names in both families.
- Swap fonts in `templates/base.html` (Google Fonts link) and the `--font-*` tokens.

## Photography

Real photos of the place, captioned with what they show; a host portrait at the property; no stock images
in production. Overlays on photos stay light enough for the photo to lead.

## Experiments

Open any guest page with `?theme=aurora` to compare with the earlier dark glass look. Add more variants as
`[data-theme="name"] { … }` blocks in `tokens.css`.

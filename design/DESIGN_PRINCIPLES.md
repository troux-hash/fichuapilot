# Fichua Design Principles

The single source of truth for **look and feel**. Values live in code in one file:
[`public/static/css/tokens.css`](../public/static/css/tokens.css). Change a token there and the whole product follows —
no component file contains a raw colour, font or radius.

## 1. Principles

1. **Three questions, then answers.** Where, when, who. Everything else is optional and pre-filled.
2. **Trust is the product.** Total prices up front, real inventory signals only, no dark patterns, calm confident typography.
3. **Warm, not boring.** Deep ink navy says "safe"; a sunset coral accent says "holiday". Accent is used sparingly — one primary action per screen.
4. **Thumb-first.** Designed at 375px first; primary actions sit in the bottom half on mobile. Touch targets ≥ 44px.
5. **Instant feedback.** Filters apply without a submit button; every action shows state within 100ms.
6. **Photos sell.** Large, consistent 4:3 imagery with rounded corners. UI chrome stays quiet around them.
7. **Accessible by default.** WCAG AA contrast, visible focus rings, semantic HTML, works without JavaScript (JS enhances).

## 2. Brand tokens (defaults)

| Token | Value | Use |
|---|---|---|
| `--color-ink` | `#0E1B33` | Text, header, trust surfaces |
| `--color-primary` | `#1F3A8A` | Links, selected states |
| `--color-accent` | `#FF5A3C` | The one primary CTA per screen |
| `--color-success` | `#0F8A5F` | Free cancellation, confirmations |
| `--color-surface` | `#FFFFFF` / `--color-bg` `#F7F5F2` | Warm off-white background, white cards |
| `--font-display` | **Fraunces** (serif, optical) | Headlines, hotel names — personality |
| `--font-body` | **Plus Jakarta Sans** | All UI text — modern, highly legible |
| `--radius-*` | 8 / 14 / 22 / pill | Soft, friendly geometry |

## 3. Theming & experiments

- **Re-skin**: edit `tokens.css` only. A dark theme is already defined (`prefers-color-scheme`).
- **A/B test a theme**: add a block like `[data-theme="sunrise"] { --color-accent: #F59E0B; }` to `tokens.css`, then append `?theme=sunrise` to any URL — the base template sets `data-theme` from the query string so you can compare variants side by side.
- **Fonts**: swap the Google Fonts link in `fichua/templates/base.html` and the two `--font-*` tokens.

## 4. Layout

| Breakpoint | Width | Layout |
|---|---|---|
| Mobile | < 720px | Single column, filters in a bottom sheet, sticky bottom CTA |
| Tablet | 720–1079px | 2-column results grid, filters in sheet |
| Laptop | ≥ 1080px | Filter sidebar + 2–3 column grid, sticky booking box |

Spacing scale is 4px-based (`--space-1` … `--space-9`). Content max width 1200px.

## 5. Components (in `public/static/css/components.css`)

Search pill · date-preset chips · guest stepper · hotel card · filter group · rating badge · price block (total + per night) · room card · sticky CTA bar · form field · toast/alert · admin table.

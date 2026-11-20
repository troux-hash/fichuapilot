# Fichua Design Principles

The single source of truth for **look and feel** is one file:
[`public/static/css/tokens.css`](../public/static/css/tokens.css). Change a token there and the product follows;
no component contains a raw colour, font or radius.

## Two themes, one brand

| | Guest site ("Aurora") | Partners + Admin ("Pro") |
|---|---|---|
| Mood | Futuristic, exciting, made for phones | Calm, professional, data-dense |
| Background | Deep space navy with violet / cyan / pink aurora glows and a faint horizon grid | Cool light grey `#F3F5FA`, white panels |
| Surfaces | Frosted glass: translucent white + blur + hairline border | Solid white cards, soft shadow; dark navy sidebar |
| Primary action | Gradient pill (violet → pink → peach) with dark text and a glow | Solid violet `#5B4BFF`, white text |
| Accents | Mint for success and ratings, cyan for focus | Same brand gradient, used only for the logo and active nav |

Theme switch: the guest pages use `:root` tokens; partner and admin pages add `class="theme-pro"` to `<body>`.

## Principles

1. **Three questions, then answers.** Where, when, who. Everything else is optional and pre-filled.
2. **Trust is the product.** Total prices up front (USD + local currency), real inventory only, no dark patterns.
3. **One bold thing per screen.** The gradient appears on one primary action; everything else stays quiet.
4. **Thumb-first.** Designed at 375 px first; touch targets ≥ 44 px; no horizontal scrolling at any width.
5. **Instant feedback.** Filters apply without a submit button; calendar edits show up immediately.
6. **Accessible by default.** WCAG AA contrast (dark text on the bright gradient), visible focus rings, works without JavaScript.

## Typography

- **Sora** (display): headlines, hotel names, prices. Geometric and slightly futuristic.
- **Manrope** (body): all UI text. Highly legible at small sizes.
- Swap both in `templates/base.html` (Google Fonts link) and the `--font-*` tokens.

## Experiments

Open any guest page with `?theme=daylight` to preview the light glass variant. Add more variants as
`[data-theme="name"] { … }` blocks in `tokens.css`.

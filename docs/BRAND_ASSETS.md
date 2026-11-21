# Brand assets: the "Built at MIT" section

The guest footer, the partner landing page and the partner portal show a "Built at MIT" section
(`fichua/templates/components/trust.html`, list in `fichua/web.py` → `TRUST_PARTNERS`).

| Key | Shown as | Full name | Links to | Ask for the files |
|---|---|---|---|---|
| `mit` | MIT | Massachusetts Institute of Technology | https://www.mit.edu | ioc-useofname@mit.edu |
| `mit-sandbox` | MIT Sandbox | MIT Sandbox Innovation Fund | https://sandbox.mit.edu | sandbox@mit.edu |
| `kuo-sharper` | MIT Kuo Sharper Center | MIT Kuo Sharper Center for Prosperity and Entrepreneurship | https://kuosharper.mit.edu | kuosharper@mit.edu |

## Logo files (live since 21 Nov 2026, supplied by the Fichua team)

| File | Tile | How it was prepared |
|---|---|---|
| `public/static/img/trust/mit.png` | white | Trimmed, scaled to 132 px tall, white background made transparent |
| `public/static/img/trust/mit-sandbox.png` | white | Trimmed only |
| `public/static/img/trust/kuo-sharper-white.png` | navy `#113A69` | Trimmed, navy background made transparent (the white logo on the centre's own navy) |

None of the marks were redrawn or recoloured.

## Replacing or adding a logo (no code change)

Drop the file in `public/static/img/trust/`, named after its key, then commit and push:

- `<key>.svg|png|webp` shows on a white tile; `<key>-white.<ext>` (a reversed logo) on the navy tile.
- Order of preference: `<key>.svg`, `.png`, `.webp`, then the `-white` versions. An official `mit.svg` would
  therefore replace `mit.png` without deleting it.
- SVG is best; PNG or WebP need a transparent background and at least 120 px of height.
- Removing every file for a key switches that tile back to the name as text.

## Rules (read before adding a logo)

- **Permission first.** MIT controls its name and logos. MIT's brand site says an outside organisation must ask
  permission to use the MIT logo (ioc-useofname@mit.edu), and its logo downloads are behind MIT Touchstone.
  The MIT Sandbox and Kuo Sharper Center publish no public usage rules, so ask each team for approved files.
- **Official files only, untouched.** No recolouring, stretching, cropping, shadows or redrawing. The tiles exist
  so every logo sits on a plain background in every theme.
- **Factual wording.** "Built at MIT, with support from …" is a statement of fact. Never write "MIT-approved",
  "certified by MIT", "MIT partner" or anything that suggests MIT endorses Fichua, its hotels or its bookings.
- **Kept apart.** Each logo stays in its own tile. Never merge it into the Fichua logo or into a combined lock-up.

Sources: [MIT logo](https://brand.mit.edu/logos-marks/mit-logo) and [brand contact](https://brand.mit.edu/contact),
[use of MIT's name](https://comms.mit.edu/brand/institute-use-name), [MIT policy on the Institute's name](https://policies.mit.edu/node/223),
[licensing MIT's trademarks](https://tlo.mit.edu/industry-entrepreneurs/license/license-mits-trademark),
[MIT VMS: promoting your venture](https://vms.mit.edu/promote-your-venture).

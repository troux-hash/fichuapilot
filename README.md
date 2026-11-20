# Fichua — hotel search & booking MVP

Search → filter → book in under a minute, on phone, tablet and laptop.
Hotels are loaded from Excel through a password-protected admin.

**Stack:** Python 3.12 · FastAPI · Jinja · vanilla CSS/JS · Postgres (Supabase) · Vercel · GitHub

## Run locally (Windows PowerShell)

```bash
python -m venv .venv
```
```bash
.venv\Scripts\pip install -r requirements-dev.txt
```
```bash
.venv\Scripts\python scripts\generate_synthetic_data.py
```
```bash
.venv\Scripts\python scripts\import_excel.py data\samples\all_hotels_synthetic.xlsx
```
```bash
.venv\Scripts\python scripts\dev.py
```

Open http://localhost:8000 · Partners at `/partners` · Admin at `/admin` (local password: `admin`) · API docs at `/api/docs`.
The dev server always uses the local SQLite copy in `data/fichua.db`, the test checkout and no WhatsApp,
even though `.env` holds the live settings (add `--prod` to point it at the live database on purpose).

Run tests: `.venv\Scripts\python -m pytest -q`

## Docs

- [Deployment: GitHub → Vercel + Supabase](docs/DEPLOYMENT.md)
- [Architecture & folder map](docs/ARCHITECTURE.md)
- [Product backlog](docs/BACKLOG.md)
- [Competitor customer-journey teardown](docs/research/customer-journeys.md)
- [Design principles & theming](design/DESIGN_PRINCIPLES.md)

## Loading hotel data

Admin → **Download template** → fill the `Hotels`, `Rooms`, `Rates` sheets → **Upload**.
Sample files for three hotel groups are in `data/samples/`. Synthetic rates start from the day they're generated —
re-run `scripts/generate_synthetic_data.py` and re-upload to roll the dates forward.

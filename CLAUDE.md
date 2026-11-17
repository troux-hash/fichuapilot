# Fichua — notes for Claude

- Python 3.12 venv at `.venv`. Run tests with `.venv\Scripts\python -m pytest -q` after every change.
- Dev server: launch config `fichua` in `.claude/launch.json` (uvicorn on :8000, local SQLite `data/fichua.db`).
- Layering: routes (HTTP only) → services (rules) → `db.py` (SQL with `:name` params). Keep SQL portable Postgres; it must also run on SQLite.
- Styling: never hard-code colours/fonts/radii in components — add or use tokens in `public/static/css/tokens.css`.
- Keep dependencies minimal; justify any addition to `requirements.txt`.
- Schema changes: edit `fichua/schema.sql` idempotently (`IF NOT EXISTS`); it runs on every cold start.
- Product scope lives in `docs/BACKLOG.md` — update it when a backlog item ships.

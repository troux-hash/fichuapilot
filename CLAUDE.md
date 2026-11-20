# Fichua — notes for Claude

- Python 3.12 venv at `.venv`. Run tests with `.venv\Scripts\python -m pytest -q` after every change.
- Dev server: launch config `fichua` in `.claude/launch.json` (uvicorn on :8000, local SQLite `data/fichua.db`).
- Layering: routes (HTTP only) → services (rules) → `db.py` (SQL with `:name` params). Keep SQL portable Postgres; it must also run on SQLite.
- Styling: never hard-code colours/fonts/radii in components — add or use tokens in `public/static/css/tokens.css`.
- Keep dependencies minimal; justify any addition to `requirements.txt`.
- Schema changes: edit `fichua/schema.sql` idempotently (`IF NOT EXISTS`); it runs on every cold start.
- Product scope lives in `docs/BACKLOG.md` — update it when a backlog item ships.

## Shipping a change (the user wants this fully automated)
1. Make the change, run the tests, check it in the local preview.
2. Commit and `git push` to `main` (GitHub: troux-hash/fichuapilot). Vercel deploys production automatically.
3. `.venv\Scripts\python scripts\vercel_status.py --wait` → must end `READY` (use `--logs` if it fails).
4. Smoke-check https://fichuapilot.vercel.app (`/api/health` must say `postgres`).
- Secrets live only in the gitignored `.env` (DATABASE_URL = Supabase pooler, VERCEL_TOKEN, SECRET_KEY, ADMIN_PASSWORD). Never print or commit them.
- Vercel functions run in `pdx1` to sit next to the Supabase database in us-west-2; keep them together if either moves.

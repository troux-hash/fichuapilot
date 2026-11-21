# Deploying Fichua (GitHub → Vercel + Supabase)

## Current setup (live)

| | |
|---|---|
| Live site | https://fichuapilot.vercel.app |
| Code | github.com/troux-hash/fichuapilot (branch `main` = production) |
| Hosting | Vercel project `fichuapilot`, functions in `pdx1` (Oregon) |
| Database | Supabase Postgres, us-west-2 (Oregon), via the transaction pooler |
| Payments | Stripe, **test mode** (US account, USD). Webhook `https://fichuapilot.vercel.app/api/stripe/webhook` (checkout.session.completed / async_payment_succeeded), created through the API; its signing secret is `STRIPE_WEBHOOK_SECRET` |
| WhatsApp | Not connected yet (messages are logged in Admin → WhatsApp messages) |
| Payout job | Vercel Cron, daily 06:00 UTC → `/api/cron/payouts` (protected by `CRON_SECRET`) |

**Every push to `main` deploys automatically.** Check a deploy with
`python scripts/vercel_status.py --wait` (needs `VERCEL_TOKEN` in `.env`).

The steps below are how this was set up — only needed for a fresh environment.

Total cost to start: **$0**. Read the cost notes at the bottom before you take real bookings.

## 1. Supabase (database) — 5 minutes

1. Create a project at supabase.com (pick the region closest to your guests, e.g. Frankfurt/eu-central-1 for East Africa + Europe).
2. Save the database password somewhere safe.
3. Click **Connect** (top bar) → **Transaction pooler** → copy the URI. It looks like:
   `postgresql://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:6543/postgres`
   - Use the **pooler (port 6543)**, not the direct connection: Vercel functions are short-lived and IPv4-only.
4. Tables are created automatically on the first request. (Or paste `fichua/schema.sql` into the SQL editor.)
5. Load the sample hotels, either:
   - **Admin UI**: after deploy, go to `/admin` → upload `data/samples/all_hotels_synthetic.xlsx`, or
   - **CLI**: `DATABASE_URL="<uri>" python scripts/import_excel.py data/samples/all_hotels_synthetic.xlsx`

## 2. GitHub — 2 minutes

Create an **empty private** repo (no README), then from this folder:

```bash
git remote add origin https://github.com/<you>/fichua.git
git push -u origin main
```

## 3. Vercel — 3 minutes

1. vercel.com → **Add New → Project** → import the GitHub repo. Framework preset: **Other**. No build command.
2. **Environment Variables** (Production + Preview):
   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Supabase pooler URI from step 1 |
   | `ADMIN_PASSWORD` | a strong password |
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
3. Deploy. Check `https://<project>.vercel.app/api/health` → `{"status":"ok","database":"postgres"}`.

From now on: **every `git push` to `main` deploys to production; every other branch / PR gets its own preview URL.**

## 4. Iterating

```bash
git checkout -b feature/map-view    # work on a branch
# ...change code, run tests...
git push -u origin feature/map-view # Vercel posts a preview URL on the PR
# merge the PR → production deploy
```

## Moving to AWS later

The app only needs `DATABASE_URL`. To move the data:

```bash
pg_dump --no-owner --no-acl "<supabase direct URI>" > fichua.sql
psql "<aws rds URI>" < fichua.sql
```

Then change `DATABASE_URL`. The app itself runs anywhere Python runs (`uvicorn fichua.main:app`) — AWS App Runner, ECS, Lambda (via Mangum), or a VM.

## Cost & limits (checked Nov 2026 — re-verify on the pricing pages)

| Service | Free tier | Watch out for |
|---|---|---|
| **Vercel Hobby** | Free, generous bandwidth & function time | **Non-commercial use only.** Once Fichua takes real bookings as a business, Vercel's terms require **Pro (~$20/user/month)**. Max request body 4.5 MB (Excel uploads are capped at 4 MB). |
| **Supabase Free** | 500 MB database, 2 projects | **Pauses after 7 days without activity** (one click to resume). **No automatic backups** — see backlog. Pro is ~$25/month. |
| **GitHub** | Free private repos | — |
| Images (Unsplash hot-links) | Free | Fine for a demo; replace with your own photos in Supabase Storage before launch (backlog #16). |

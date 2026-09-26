# Trading Journal

Fintech dashboard for trade lifecycle + analytics. Telegram bot is the live
ingestion path, web modals cover manual open/close, Immich stores screenshots.

## Stack

- **Backend:** FastAPI + SQLModel, SQLite WAL (`journal.db`), `venv` +
  `requirements.txt`. Entry `app.main:app` on `127.0.0.1:8000` (dev may use
  `:9000` via `PORT`).
- **Frontend:** SvelteKit + Tailwind, adapter-node (`out: build`), Node 20 LTS.
  Entry `node build` on `:3000` with `ORIGIN`.
- **External:** Immich REST (monthly `YYYY-MM Trades` albums, server-side proxy
  only), Telegram bot.

## Setup

```bash
# backend
cd backend
python -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env  # then fill secrets (never commit .env)

# frontend
cd frontend
npm install
cp .env.example .env  # set PUBLIC_API_BASE to a browser-reachable backend URL
```

## Env vars

Backend (`backend/.env`):

| Key | Purpose |
|---|---|
| `DATABASE_URL` | e.g. `sqlite:////root/trading-journal/backend/journal.db` (prod uses the deploy path) |
| `TG_BOT_TOKEN` / `TG_ALLOWED_USER_ID` | Telegram bot auth (fail-closed without allowlist) |
| `IMMICH_BASE_URL` / `IMMICH_API_KEY` | Screenshot storage (**server-side only**, never expose the key) |
| `PORT` | API port |
| `MAX_DAILY_LOSS` / `MAX_DAILY_TRADES` | Guardrail caps |
| `STALE_TRADE_HOURS` / `EOD_PROMPT_HOUR` | Scheduler tuning |
| `TG_BOT_CSV_PATH` | Legacy one-shot CSV import only |
| `CORS_ORIGINS` | Comma-separated extra browser origins |

Frontend (`frontend/.env`):

| Key | Purpose |
|---|---|
| `PUBLIC_API_BASE` | Browser-reachable backend URL |

## Run

```bash
# backend (from backend/)
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (from frontend/)
npm run build
PORT=3000 ORIGIN=http://127.0.0.1:3000 node build
```

Services (prod): `journal-backend.service`, `journal-frontend.service`, plus
existing `tg-logger.service`. See `AGENTS.md` for service commands.

## Data rules

- Timestamps are **naive UTC** (`app/services/timeutils.py` is the single
  source: `as_naive_utc`, `trade_close_day`).
- Breakeven is `|net_pnl| <= 0.01` — applied in `summary`, `kpi-dashboard`,
  `long-short-stats`, monthly calendar, streaks, tag/radar stats.
- Long ↔ `buy`, Short ↔ `sell` (`long`/`short` aliases accepted, unknown
  directions ignored).
- Close without `gross_pnl` falls back to a price-based estimate for known
  symbols (FX 100k, GOLD 100, BTC 1, USDJPY via exit rate); unknown symbols
  keep `null` rather than guessing. `net = gross - fees` whenever gross is
  known; `r_multiple` recomputes on close/patch/backfill.
- Trades list paginates (`page`/`page_size`, default 500, max 5000, `total`
  always the full filtered count). Frontend `listAllTrades()` loops until
  `items.length === total`.

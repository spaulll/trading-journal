<div align="center">

# 📈 Trading Journal

**A full trade-lifecycle journal and analytics dashboard, driven from Telegram or the web.**

Log trades in one line of chat, attach chart screenshots automatically, and review performance per account.

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![SvelteKit](https://img.shields.io/badge/SvelteKit-FF3E00?style=flat-square&logo=svelte&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite_WAL-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Immich](https://img.shields.io/badge/Immich-4250AF?style=flat-square&logo=immich&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram_Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)

[Highlights](#-highlights) · [Features](#-features) · [Quickstart](#-quickstart) · [Configuration](#%EF%B8%8F-configuration) · [Telegram syntax](#-telegram-syntax) · [Data rules](#-data-rules) · [API](#-api)

</div>

---

## ✨ Highlights

| | |
|---|---|
| 🖼️ **Immich screenshot integration** | Chart screenshots are stored in your self-hosted [Immich](https://immich.app) instance, auto-organized into monthly `YYYY-MM Trades` albums, with SHA-based dedupe. Credentials never leave the server. |
| 🤖 **Telegram-first logging** | Open, trail, and close trades with one-line messages and inline buttons. Send a photo and it attaches to the open trade. |
| 🏦 **Prop-firm account tracking** | Challenge / funded / personal accounts with percent-based daily-loss, max-loss (static or trailing), and profit-target limits, plus live room-left and breach status. |
| 📊 **Deep analytics** | Equity curve, underwater drawdown, R distribution, heatmap calendars, tag performance, streaks, and session profiles, filterable per account. |
| 🔔 **Automation & guardrails** | Stale-trade nudges, a nightly EOD recap prompt, and breach alerts when you hit your daily limits. |

> ### 🖼️ Immich integration
> Screenshots are the backbone of a good trade review, so they get first-class treatment:
>
> - **Organized automatically:** uploads land in monthly `YYYY-MM Trades` albums.
> - **Server-side only:** `IMMICH_API_KEY` is never exposed to the browser.
> - **Fast in the UI:** the web app serves cached thumbnails with full-size zoom.
> - **No duplicates:** SHA-based dedupe prevents re-uploading the same image.
> - **Frictionless capture:** send a photo to the Telegram bot and it is attached to your open trade.

---

## 🚀 Features

### Trade lifecycle
- Open, trailing-stop, close, and backfill flows
- Tag editing with `#setup` and `!mistake` conventions
- Review notes and per-trade screenshots
- Bulk account moves and delete
- Ledger summary: net realized, win rate, average R, and an open-now ribbon

### Symbol contracts
- One registry of contract sizes, pip sizes and quote currencies, editable over the API
- Every registered symbol gets a real dollar P&L — FX, metals, crypto and indices
- Risk per trade: the dollars planned and the dollars actually carried
- An unregistered symbol stays unpriced and is flagged, never guessed

### Telegram bot
- Live ingestion with inline buttons: **Move to BE**, **Update TSL**, **Close**, **Attach Chart**
- `@account` routing with last-account memory
- Photo-to-trade screenshot pipeline
- Commands: `/open`, `/accounts`, `/stats_daily`, `/brokertime`, `/help`
- Guardrail breach alerts

See [Telegram syntax](#-telegram-syntax).

### Analytics
- Equity curve and underwater drawdown
- R distribution and outcome donut
- Tag-performance bars
- Yearly heatmap calendar and monthly calendar
- KPI dashboard, activity streaks, long/short splits, session and radar profiles
- Per-account filtering with offline snapshots

### Accounts
- Prop-firm tracking (challenge / funded / personal)
- Percent-based daily-loss, max-loss (static or trailing), and profit-target limits
- Live balance, daily and max room-left, and breach status

### Journal
- Daily notes with pre-market plan, EOD review, and a discipline-breach flag
- Day panel that rolls up that day's trades

### Automation
- Snoozable stale-trade nudges
- Nightly EOD recap prompt; replying to it saves your journal review
- Broker-clock calibration so `MT5` timestamps resolve to UTC

### Accessibility
- Keyboard-complete dialogs: Tab stays inside, Escape closes only the topmost layer, and focus returns to the trigger
- `/` focuses ledger search; Space or Enter opens ledger rows and trade cards
- Focusable resize handles respond to Left/Right arrows (Shift for a larger step) and Home, and expose their value through ARIA
- Named search fields and polite, atomic autosave announcements

---

## ⚡ Quickstart

### One command

```bash
./run.sh --install --build
```

Starts the backend and frontend with health checks. Run `./run.sh --help` for `--backend-only`, `--frontend-only`, and port options.

### Manual setup

**Backend**

```bash
cd backend
python -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in secrets (never commit .env)
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run build
PORT=3000 ORIGIN=http://127.0.0.1:3000 node build
```

### Tests

The backend suite runs against a throwaway SQLite database, so it never
touches your journal and needs no secrets.

```bash
cd backend
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest -q          # close pipeline, parsers, analytics, API
```

```bash
cd frontend
npm run check                 # svelte-check, the type gate
```

Both run in CI on every push and pull request (`.github/workflows/checks.yml`).

### LAN access

Browsers fetch the API directly, so to use the app from other devices on your network:

1. Bind the backend with `BACKEND_HOST=0.0.0.0`.
2. Point `PUBLIC_API_BASE` at a reachable backend URL.
3. Add the page origin to `CORS_ORIGINS`.

---

## ⚙️ Configuration

### Backend (`backend/.env`)

Copy `backend/.env.example` and fill in secrets.

| Key | Purpose |
|---|---|
| `APP_ENV` | Deployment label (`development` / `production`); informational |
| `DATABASE_URL` | SQLite URL, e.g. `sqlite:////opt/trading-journal/backend/journal.db` |
| `PORT` | API port |
| `CORS_ORIGINS` | Comma-separated extra browser origins for LAN access |
| `TG_BOT_TOKEN` | Telegram bot token; the bot is disabled when empty |
| `TG_ALLOWED_USER_ID` | Allowlisted Telegram user (**fail-closed** without it) |
| `TG_BOT_CSV_PATH` | Legacy CSV path for the one-shot history importer only |
| `IMMICH_BASE_URL` | Your Immich server URL |
| `IMMICH_API_KEY` | Immich API key (**server-side only**) |
| `MAX_DAILY_LOSS` / `MAX_DAILY_TRADES` | Guardrail caps checked when a trade opens |
| `STALE_TRADE_HOURS` | Hours before a stale-trade nudge |
| `EOD_PROMPT_HOUR` / `EOD_PROMPT_MINUTE` / `EOD_TZ` | EOD prompt timing (tradeless days are skipped) |
| `WEEKLY_REVIEW_DOW` / `WEEKLY_REVIEW_HOUR` / `WEEKLY_REVIEW_MINUTE` | Weekly review schedule in `EOD_TZ`; `mon` = Monday |
| `MIN_SAMPLE_SIZE` | Closed trades a setup/tag needs before it is ranked |
| `FX_BASE_CURRENCY` | Currency for account balances and analytics totals |
| `FX_RATE_SOURCE` | Label stored on manually entered FX rates |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible endpoint for weekend-review summaries (**API key server-side only**) |
| `LLM_MAX_TOKENS` / `LLM_REASONING_EFFORT` | Output budget and reasoning effort for reasoning-capable models |
| `LLM_TIMEOUT_S` / `LLM_RETRIES` | Per-request timeout and retries for rate limits or empty/truncated answers |

### Frontend (`frontend/.env` and runtime)

| Key | Purpose |
|---|---|
| `PUBLIC_API_BASE` | Browser-reachable backend URL |
| `PORT` | adapter-node listen port (default `3000`) |
| `ORIGIN` | Public page origin used by SvelteKit for form/CSRF checks |

---

## 💬 Telegram syntax

```text
buy gold, 0.1, 4000, 3990, 4020, #fvg @ftmo100k-f1   # open (sell = short)
tsl gold, 4005                                        # move stop
close gold, 4015, +150, fee: 3.5, !early              # close (gross estimated from price when omitted)
past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, date: 2026-09-20 14:30
```

- Append `time: HH:MM [MT5|IST|UTC]` to open at a past time.
- Photos sent to the bot attach to the open trade.
- Run `/help` in chat for the full guide.

---

## 📐 Data rules

- **Timestamps** are naive UTC. Broker `MT5` times resolve via the calibrated offset (`/brokertime`).
- **Contract sizes** live in the symbol registry (`GET /api/symbols`): 100k units per FX lot, 100 oz for gold, 5000 oz for silver, 1 coin for crypto, 1 contract for indices. The server prices every trade from it; the browser never re-derives a dollar amount.
- **Breakeven** is `|net_pnl| <= $5`, applied consistently across stats, calendars, and streaks.
- **Unpriced** is not breakeven. A closed trade with no P&L — because its symbol had no contract — is counted separately and excluded from the win rate, the streaks and the day buckets. The ledger flags it `UNPRICED`.
- **Net P&L:** `net = gross − fees` when gross is known.
- **Risk** is recorded per trade: `initial_risk` from the planned stop, `realized_risk` from the stop it was actually carried to.
- **R-multiple** recomputes on close, edit, and backfill, against the risk actually taken — a trailed stop changes the R.
- **Closes without gross** fall back to a price-based estimate for registered symbols, otherwise stay `null`.
- **Pagination:** the trades list is paginated (`page` / `page_size`, max 5000); the frontend fetches all pages for full-set stats.

---

## 🔌 API

FastAPI publishes the live schema at `/docs` (Swagger UI) and `/openapi.json`; every application route is under `/api`. This table is a route map — use `/docs` for request bodies, query parameters, and response schemas.

| Area | Routes |
|---|---|
| Health | `GET /api/health` |
| Trades | `GET /api/trades`; `POST /api/trades/open`; `POST /api/trades/backfill` (batch, up to 500 records); `POST /api/trades/bulk-account`; `GET /api/trades/export`; `GET /api/trades/ids`; `POST /api/trades/import/mt5`; `GET /api/trades/imports`; `POST /api/trades/repair/unpriced`; `GET/PATCH/DELETE /api/trades/{trade_id}`; `POST /api/trades/{trade_id}/close`; `POST /api/trades/{trade_id}/tsl`; `POST /api/trades/{trade_id}/screenshots` |
| Accounts | `GET/POST /api/accounts`; `GET/PATCH/DELETE /api/accounts/{account_id}`; `GET /api/accounts/{account_id}/prop-status`; `GET /api/accounts/{account_id}/rules`; `POST /api/accounts/{account_id}/rules/{kind}/check`; `GET /api/accounts/{account_id}/timeline` |
| Symbols | `GET/POST /api/symbols`; `GET /api/symbols/preview`; `PATCH /api/symbols/{spec_id}` |
| FX | `GET/POST /api/fx-rates`; `GET /api/fx-rates/effective`; `GET /api/fx-rates/pivot` |
| Tags | `GET /api/tags`; `POST /api/tags/merge`; `PATCH/DELETE /api/tags/{tag_id}` |
| Screenshots | `GET /api/screenshots/{asset_id}/thumbnail`; `GET /api/screenshots/{asset_id}/full`; `PATCH /api/screenshots/{screenshot_id}`; `DELETE /api/screenshots/{screenshot_id}` (also deletes the Immich asset) |
| Analytics | All `GET` under `/api/analytics/`: `summary`, `equity-curve`, `drawdown`, `r-distribution`, `tag-performance`, `calendar`, `monthly-calendar`, `kpi-dashboard`, `activity-and-streaks`, `long-short-stats`, `radar-profiles`, `symbol-performance`, `setup-confidence`, `setup-matrix`, `risk-of-ruin` |
| Settings | `GET /api/settings/broker-offset`; `GET/PUT /api/settings/trading-day` |
| Daily notes | `GET /api/daily-notes`; `GET/PUT/DELETE /api/daily-notes/{day}`; `GET /api/daily-notes/{day}/adherence` |
| Insights | `GET /api/insights/reports`; `DELETE /api/insights/reports/{report_id}`; `POST /api/insights/weekend-review` |
| Telegram | `GET /api/telegram/commands` |

The bot is the live ingestion path; `POST /api/trades/sync-bot` was removed in v2. Historical data goes through `python -m app.services.migrate_csv` (one-shot) or `POST /api/trades/backfill`.

---

## 🚢 Deployment

On the target host, from the repo root:

```bash
./deploy.sh
```

Pulls the latest code, rebuilds only what changed, and restarts the `journal-backend` and `journal-frontend` systemd units.

---

<div align="center">

Built with FastAPI, SvelteKit, and Immich.

</div>

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

[Highlights](#-highlights) · [Features](#-features) · [Quickstart](#-quickstart) · [Configuration](#%EF%B8%8F-configuration) · [Telegram syntax](#-telegram-syntax) · [Data rules](#-data-rules)

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

### LAN access

Browsers fetch the API directly, so to use the app from other devices on your network:

1. Bind the backend with `BACKEND_HOST=0.0.0.0`.
2. Point `PUBLIC_API_BASE` at a reachable backend URL.
3. Add the page origin to `CORS_ORIGINS`.

---

## ⚙️ Configuration

### Backend (`backend/.env`)

| Key | Purpose |
|---|---|
| `DATABASE_URL` | Database location, e.g. `sqlite:///<path>/journal.db` |
| `TG_BOT_TOKEN` | Telegram bot token |
| `TG_ALLOWED_USER_ID` | Allowlisted Telegram user (**fail-closed** without it) |
| `IMMICH_BASE_URL` | Your Immich server URL |
| `IMMICH_API_KEY` | Immich API key (**server-side only**) |
| `PORT` | API port |
| `MAX_DAILY_LOSS` / `MAX_DAILY_TRADES` | Guardrail caps |
| `STALE_TRADE_HOURS` | Hours before a stale-trade nudge |
| `EOD_PROMPT_HOUR` / `EOD_PROMPT_MINUTE` / `EOD_TZ` | EOD prompt timing (tradeless days are skipped) |
| `CORS_ORIGINS` | Extra browser origins for LAN access |

### Frontend (`frontend/.env`)

| Key | Purpose |
|---|---|
| `PUBLIC_API_BASE` | Browser-reachable backend URL |

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
- **Breakeven** is `|net_pnl| <= $5`, applied consistently across stats, calendars, and streaks.
- **Net P&L:** `net = gross − fees` when gross is known.
- **R-multiple** recomputes on close, edit, and backfill.
- **Closes without gross** fall back to a price-based estimate for known symbols, otherwise stay `null`.
- **Pagination:** the trades list is paginated (`page` / `page_size`, max 5000); the frontend fetches all pages for full-set stats.

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

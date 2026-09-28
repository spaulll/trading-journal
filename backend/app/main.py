"""Trading Journal API entrypoint: `uvicorn app.main:app`."""

import asyncio
import logging
from contextlib import asynccontextmanager

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.database import create_db_and_tables  # noqa: E402
from app.routers import analytics, daily_notes, screenshots, settings, trades  # noqa: E402
from app.services import scheduler, telegram_bot  # noqa: E402

log = logging.getLogger("journal")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    create_db_and_tables()
    bot_task: asyncio.Task | None = None
    if telegram_bot.is_configured():
        if not telegram_bot._allowed_user():
            log.error("TG_BOT_TOKEN is set but TG_ALLOWED_USER_ID is missing — bot updates will be refused")
        bot_task = asyncio.create_task(telegram_bot.run_polling())
    else:
        log.warning("TG_BOT_TOKEN not set — Telegram bot disabled")
    sched = scheduler.build_scheduler()
    sched.start()
    log.info("scheduler started: %s", scheduler.job_summary(sched))
    yield
    sched.shutdown(wait=False)
    if bot_task is not None:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Trading Journal", lifespan=lifespan)

# Comma-separated extra origins for LAN access, e.g.
# CORS_ORIGINS=http://10.10.10.162:3100,http://10.10.10.162:5173
_extra_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *_extra_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router)
app.include_router(screenshots.router)
app.include_router(analytics.router)
app.include_router(settings.router)
app.include_router(daily_notes.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

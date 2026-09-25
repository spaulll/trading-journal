"""Trading Journal API entrypoint: `uvicorn app.main:app`."""

from contextlib import asynccontextmanager

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.database import create_db_and_tables  # noqa: E402
from app.routers import screenshots, trades  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    create_db_and_tables()
    yield


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


@app.get("/api/health")
def health():
    return {"status": "ok"}

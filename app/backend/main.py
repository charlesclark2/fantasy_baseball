"""Credence Sports API — FastAPI application entry point.

Deployed on AWS Lambda via Mangum (ASGI adapter). API Gateway validates Cognito JWTs
before invoking the Lambda handler, so no auth code is needed here.

Local dev:
    uv run uvicorn app.backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import time

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

load_dotenv()  # no-op in Lambda (env vars already injected); loads .env for local uvicorn
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

_SENTRY_DSN = os.getenv("SENTRY_DSN")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        traces_sample_rate=0.1,
    )

from app.backend.routers import admin, alerts, auth, bets, finances, picks, performance, pipeline, portfolio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TARGET_ENV = os.getenv("TARGET_ENV", "dev")

app = FastAPI(
    title="Credence Sports API",
    version="0.1.0",
    description="Backend API for the Credence Sports MLB analytics platform.",
    docs_url="/docs" if _TARGET_ENV != "prod" else None,
    redoc_url="/redoc" if _TARGET_ENV != "prod" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://credencesports.com",
        "https://www.credencesports.com",
        "https://app.credencesports.com",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s → %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(picks.router)
app.include_router(performance.router)
app.include_router(alerts.router)
app.include_router(bets.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(finances.router)
app.include_router(pipeline.router)
app.include_router(portfolio.router)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health() -> dict:
    return {"status": "ok", "environment": _TARGET_ENV}


# Lambda handler — Mangum wraps the ASGI app for API Gateway HTTP API (payload v2).
handler = Mangum(app, lifespan="off")

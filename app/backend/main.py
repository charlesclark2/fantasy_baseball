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
from fastapi import Depends, FastAPI, Request, Response

load_dotenv()  # no-op in Lambda (env vars already injected); loads .env for local uvicorn
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

_SENTRY_DSN = os.getenv("SENTRY_DSN")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        traces_sample_rate=0.1,
    )

from app.backend.routers import admin, alerts, auth, bankroll, bets, blog, fantasy, fantasy_import, feedback, finances, parlay, picks, performance, pipeline, players, portfolio, stripe, teams, users
from app.backend.routers.auth import require_subscriber_mfa

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


# Server-side subscriber-MFA guard (E9.8): applied to the paid content routers as
# defense-in-depth for E9.19's (frontend-only) MFA enforcement. It's a no-op unless
# ENFORCE_SUBSCRIBER_MFA=1 and only gates callers already in the `subscriber` group,
# so free/beta/anon traffic passes through untouched with no extra Cognito read.
_paid = [Depends(require_subscriber_mfa)]

app.include_router(bankroll.router, dependencies=_paid)
app.include_router(blog.router)
app.include_router(feedback.router)
app.include_router(picks.router, dependencies=_paid)
app.include_router(performance.router, dependencies=_paid)
app.include_router(alerts.router, dependencies=_paid)
app.include_router(bets.router, dependencies=_paid)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(finances.router, dependencies=_paid)
app.include_router(pipeline.router)
app.include_router(portfolio.router, dependencies=_paid)
app.include_router(teams.router, dependencies=_paid)
app.include_router(players.router, dependencies=_paid)
app.include_router(parlay.router, dependencies=_paid)
app.include_router(users.router)
app.include_router(stripe.router)
# Fantasy data endpoints carry their OWN entitlement gate (require_fantasy_access,
# subscriber/admin/fantasy_comp → else 403). `_paid` adds the subscriber-MFA guard
# for consistency with the other paid content (a no-op unless ENFORCE_SUBSCRIBER_MFA=1).
app.include_router(fantasy.router, dependencies=_paid)
# NF-C0 platform league import. The authenticated half gates on require_fantasy_beta_access
# (per-route, like NF-C0b's editor). The `public_router` carries EXACTLY ONE route — Yahoo's OAuth
# callback — which the user's BROWSER enters on a redirect back from Yahoo and so cannot present a
# bearer token; it authenticates on the HMAC-signed `state` instead (see the router's docstring).
# It is mounted separately so that exemption stays one visible route rather than a hole in the gate.
app.include_router(fantasy_import.router, dependencies=_paid)
app.include_router(fantasy_import.public_router)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health() -> dict:
    return {"status": "ok", "environment": _TARGET_ENV}


# Lambda handler — Mangum wraps the ASGI app for API Gateway HTTP API (payload v2).
handler = Mangum(app, lifespan="off")

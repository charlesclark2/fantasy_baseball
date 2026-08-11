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

from app.backend.routers import admin, alerts, auth, bankroll, bets, blog, email_otp, fantasy, fantasy_import, fantasy_mlb_league, fantasy_public, feedback, finances, parlay, picks, performance, pipeline, players, portfolio, stripe, teams, users
from app.backend.routers.auth import require_subscriber_mfa
from app.backend.services import cost_guardrails

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

# G100-D1 — cost guardrails (per-IP rate limit + the degrade kill switch + cache headers).
#
# ⚠️ REGISTERED BEFORE `CORSMiddleware` ON PURPOSE. Starlette makes the LAST-added middleware the
# OUTERMOST one, so adding this first puts it INSIDE CORS. That ordering is load-bearing: a 429 or
# 503 short-circuits here without calling the inner app, and it must still travel back out through
# CORSMiddleware to pick up its headers. A throttled response with no CORS headers is not visible to
# the browser as a 429 at all — JS gets an opaque network error and cannot distinguish "slow down"
# from "the API is down". Moving this line below the CORS block silently breaks that.
app.middleware("http")(cost_guardrails.cost_guardrail_middleware)

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
# G100-C0 — passwordless email sign-in. PUBLIC by design and public in the FastAPI layer
# (no auth dependency: a caller signing in has no token yet, by definition). As always that
# is NOT sufficient — the API Gateway JWT authorizer sits in front of the Lambda, so both
# routes need an explicit `--authorization-type NONE` route or the whole feature 401s while
# every test passes (NF3.2). Steps in infrastructure/aws_resources.md.
app.include_router(email_otp.router)
app.include_router(admin.router)
app.include_router(finances.router, dependencies=_paid)
app.include_router(pipeline.router)
app.include_router(portfolio.router, dependencies=_paid)
app.include_router(teams.router, dependencies=_paid)
app.include_router(players.router, dependencies=_paid)
app.include_router(parlay.router, dependencies=_paid)
app.include_router(users.router)
app.include_router(stripe.router)
# E9.59 — the public pricing read, on its own router object so the exemption is structural
# rather than a flag inside the gated one (mirrors fantasy_import.public_router). It carries
# EXACTLY ONE route and no auth dependency; the API Gateway per-route authorizer must also be
# set to NONE for it (see infrastructure/aws_resources.md — a router with no Depends() is not
# sufficient on its own, per NF3.2).
app.include_router(stripe.public_router)
# Fantasy data endpoints carry their OWN entitlement gate (require_fantasy_access,
# subscriber/admin/fantasy_comp → else 403). `_paid` adds the subscriber-MFA guard
# for consistency with the other paid content (a no-op unless ENFORCE_SUBSCRIBER_MFA=1).
app.include_router(fantasy.router, dependencies=_paid)
# E9.56 — the entitlement-AWARE NFL board reads (manifest / projections / board). Mounted from a
# SEPARATE router object that carries no `require_fantasy_access`: instead of 403-ing a non-entitled
# caller, these serve a LOCKED payload (public identity + market ADP, re-ordered, `locked: true`,
# every model value removed) so the "subscribe to unlock" CTA can render. `_paid` still applies —
# `require_subscriber_mfa` resolves identity OPTIONALLY, so an anonymous caller passes through it
# untouched while a subscriber still gets the MFA backstop.
app.include_router(fantasy.board_router, dependencies=_paid)
# ⭐ G100-C1 — the SAVED-LEAGUE surface (league CRUD + `/nfl/my-teams`), on its own router object
# because its gate is WIDER than `fantasy.router`'s, not narrower. A per-route dependency can only
# tighten a router-level one, and a free signed-in account has a personalization QUOTA but no
# fantasy entitlement — so these had to move off `fantasy.router` to be reachable at all.
# `require_personalized_league_access` gates on that quota (401 anonymous, 403 at quota 0).
# ⚠️ Every response here is PER-CALLER, so it must never join the CDN allowlist or the public cache
# rules; `cache_control_for` already forces `private, no-store` on any request carrying a token.
app.include_router(fantasy.personal_router, dependencies=_paid)
# NF-C0 platform league import. The authenticated half gates on require_personalized_league_access
# (per-route) — widened from `require_fantasy_beta_access` at G100-C1, because import is one of the
# two ways a free account configures its one league. The `public_router` carries EXACTLY ONE route — Yahoo's OAuth
# callback — which the user's BROWSER enters on a redirect back from Yahoo and so cannot present a
# bearer token; it authenticates on the HMAC-signed `state` instead (see the router's docstring).
# It is mounted separately so that exemption stays one visible route rather than a hole in the gate.
app.include_router(fantasy_import.router, dependencies=_paid)
app.include_router(fantasy_import.public_router)
# E8.2 — MLB dynasty league rosters + the board availability overlay. Same gate as the E8.1 board
# it overlays: require_fantasy_access at the router, `get_admin_user` per route (admin-only dogfood
# until 2027). Authenticated throughout, so it needs NO API-Gateway route change — it inherits the
# Cognito authorizer, and adding an explicit route would UN-gate it (NF3.2, in reverse).
app.include_router(fantasy_mlb_league.router, dependencies=_paid)
# NF3.2 — the past-season track-record ("receipts") surface, deliberately PUBLIC (no
# require_fantasy_access, no _paid). See fantasy_public.py's module docstring: the public/paid split
# is enforced by what the export writer will ever emit, not by a runtime check on this router.
app.include_router(fantasy_public.router)
# E9.46 — the ONE public current-season fantasy player, for the homepage card. Mounted from its own
# router object for the same reason as `stripe.public_router`: the exemption stays a visible,
# single-route mount rather than a flag inside a gated router.
#
# ⚠️ THIS ONE IS DIFFERENT FROM EVERY OTHER PUBLIC MOUNT ABOVE and the difference is worth stating
# here, where someone auditing the gate list will see it: the routers above are public because the
# DATA behind them is public (a past season the exporter will never write a locked value into).
# This one reads the LOCKED season's projections and serves real model output. What keeps it safe
# is bounded scope, not the data layer — exactly one player, a fixed field allow-list, and no
# caller-supplied parameters. The full argument is in `fantasy_public.py`'s module docstring; ⛔ do
# not widen it (a player_id/position/limit parameter would turn one public player into the board).
#
# 🔒 OPERATOR: like every public route here, the API-Gateway per-route authorizer must ALSO be set
# to NONE or this 401s before the Lambda is invoked (NF3.2). See infrastructure/aws_resources.md.
app.include_router(fantasy_public.featured_router)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health() -> dict:
    return {"status": "ok", "environment": _TARGET_ENV}


# Lambda handler — Mangum wraps the ASGI app for API Gateway HTTP API (payload v2).
handler = Mangum(app, lifespan="off")

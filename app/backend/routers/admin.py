"""Admin endpoints.

POST /admin/cache/invalidate    — invalidate today's S3 cache
GET  /admin/pipeline-runs       — last 14 Dagster run entries (two jobs)
GET  /admin/model-freshness     — champion model freshness from model_registry
GET  /admin/snowflake-credits   — month-by-month Snowflake credit usage (last 6 months)
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import re
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.backend.dependencies import get_admin_user
from app.backend.services import serving_cache
from app.backend.services.s3_cache import invalidate_game as s3_invalidate_game
from app.backend.services.s3_cache import invalidate_permanent_picks as s3_invalidate_permanent_picks
from app.backend.services.s3_cache import invalidate_today
from app.backend.services.snowflake import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# Post-INC-16: Dagster is self-hosted on EC2 behind Caddy (HTTPS + basic-auth), not
# Dagster+ Cloud. Endpoint + auth are env-configurable and mirror scripts/ops/dagster_runs.py.
_DAGSTER_ENDPOINT = os.getenv("DAGSTER_GRAPHQL_URL", "https://dagster.credencesports.com/graphql")
_REGISTRY = "baseball_data.betting_ml.model_registry"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PipelineRun(BaseModel):
    run_id: str
    timestamp_et: str
    job_name: str
    duration_seconds: int | None
    status: str  # "success" | "warning" | "failed" | "running"
    notes: str


class ModelFreshness(BaseModel):
    model_name: str
    target: str
    version: str            # version actually serving (from daily_model_predictions when available)
    registry_version: str   # version the promotion ledger (model_registry) marks current
    ledger_behind: bool     # True when the serving version is ahead of the registry ledger
    last_trained_date: str
    days_since_training: int
    status: str  # "healthy" | "watch" | "stale"


class SnowflakeCredits(BaseModel):
    month: str          # "2026-06" formatted
    month_label: str    # "Jun 2026" formatted
    compute_credits: float        # raw warehouse compute credits (informational)
    cloud_service_credits: float  # raw cloud-services credits before the 10% adjustment
    billed_credits: float         # compute + DAILY-applied cloud-services excess (what Snowflake bills)


# ---------------------------------------------------------------------------
# Cache invalidation (unchanged)
# ---------------------------------------------------------------------------


@router.post("/cache/invalidate")
def invalidate_cache(
    game_pk: int | None = None,
    _: str = Depends(get_admin_user),
) -> dict:
    """Invalidates today's cache (DynamoDB + S3).

    If game_pk is provided, invalidates only that game's detail blob.
    Otherwise invalidates the full day's non-permanent cache.
    """
    today_str = datetime.date.today().isoformat()
    if game_pk is not None:
        serving_cache.invalidate_game(game_pk, today_str)
        s3_invalidate_game(game_pk)
        return {"status": "ok", "message": f"Game {game_pk} cache invalidated"}
    invalidate_today()
    serving_cache.invalidate_today(today_str)
    return {"status": "ok", "message": "Cache invalidated — next request will re-query Snowflake"}


@router.post("/cache/invalidate-permanent")
def invalidate_permanent_cache(_: str = Depends(get_admin_user)) -> dict:
    """Purge permanent-tier picks/game/* caches from both S3 and DynamoDB.

    Use after a champion promotion to clear stale Final-game detail blobs that
    day-scoped invalidations never touch (the is_permanent=TRUE blobs from
    api-cache/permanent/ and the corresponding DynamoDB items). Stale blobs
    regenerate lazily on the next page load. Idempotent — safe to re-run.
    """
    s3_deleted = s3_invalidate_permanent_picks()
    ddb_deleted = serving_cache.invalidate_permanent_picks()
    return {
        "status": "ok",
        "s3_objects_deleted": s3_deleted,
        "ddb_items_deleted": ddb_deleted,
        "message": (
            f"Permanent picks/game cache cleared: {s3_deleted} S3 objects, "
            f"{ddb_deleted} DynamoDB items. Stale Final-game blobs will regen on next page load."
        ),
    }


# ---------------------------------------------------------------------------
# Pipeline runs (Dagster+ GraphQL)
# ---------------------------------------------------------------------------


def _dagster_headers() -> dict:
    """Build request headers for the configured Dagster GraphQL endpoint.

    Mirrors scripts/ops/dagster_runs.py auth precedence:
      • legacy Dagster+ Cloud (`*.dagster.plus` URL) + DAGSTER_CLOUD_API_TOKEN
      • self-hosted EC2 dagit behind Caddy basic-auth (DAGIT_BASIC_AUTH_USER/_PASSWORD)
      • neither → no auth (e.g. localhost on the box)
    Operator supplies the basic-auth creds via env/secret — never hard-coded here.
    """
    h = {"Content-Type": "application/json"}
    token = os.getenv("DAGSTER_CLOUD_API_TOKEN")
    if token and "dagster.plus" in _DAGSTER_ENDPOINT:
        h["Dagster-Cloud-Api-Token"] = token.strip()
        return h
    user = os.getenv("DAGIT_BASIC_AUTH_USER")
    pw = os.getenv("DAGIT_BASIC_AUTH_PASSWORD")
    if user and pw:
        h["Authorization"] = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    return h


def _dagster_runs_for_job(job: str, limit: int = 8) -> list[dict]:
    query = (
        "query($f:RunsFilter,$n:Int){"
        "runsOrError(filter:$f,limit:$n){"
        "__typename "
        "...on Runs{results{runId status startTime endTime "
        "tags{key value}}}"
        "...on PythonError{message}}}"
    )
    body = json.dumps({"query": query, "variables": {"f": {"pipelineName": job}, "n": limit}}).encode()
    req = urllib.request.Request(_DAGSTER_ENDPOINT, data=body, headers=_dagster_headers())
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    node = resp.get("data", {}).get("runsOrError", {})
    if node.get("__typename") != "Runs":
        logger.warning("Dagster GraphQL error for %s: %s", job, str(resp)[:400])
        return []
    # Stamp the job we queried — OSS dagit doesn't return the `dagster/job_name` tag
    # the Cloud API did, and we already know the job from the filtered query.
    results = node["results"]
    for r in results:
        r["_queried_job"] = job
    return results


def _dagster_status(dagster_status: str) -> str:
    mapping = {"SUCCESS": "success", "FAILURE": "failed", "STARTED": "running", "CANCELED": "warning"}
    return mapping.get(dagster_status, "warning")


def _format_ts(unix: float | None) -> str:
    if not unix:
        return "—"
    dt = datetime.datetime.fromtimestamp(unix, tz=datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-4))  # EDT
    )
    return dt.strftime("%b %-d, %-I:%M %p")


@router.get("/pipeline-runs", response_model=list[PipelineRun])
def pipeline_runs(_: str = Depends(get_admin_user)) -> list[PipelineRun]:
    """Last 14 Dagster run entries across daily_ingestion_job and lineup_monitor_sensor.

    Reads the self-hosted EC2 dagit (DAGSTER_GRAPHQL_URL). Caddy basic-auth creds
    (DAGIT_BASIC_AUTH_USER/_PASSWORD) are operator-supplied via env; if the endpoint
    requires auth and none is configured the upstream call returns 401 → surfaced as 502.
    """
    try:
        raw = (
            _dagster_runs_for_job("daily_ingestion_job", 8)
            + _dagster_runs_for_job("lineup_monitor_job", 8)
        )
    except Exception as exc:
        logger.exception("Dagster API error")
        raise HTTPException(status_code=502, detail=f"Dagster API error: {exc}") from exc

    raw.sort(key=lambda r: r.get("startTime") or 0, reverse=True)
    raw = raw[:14]

    runs: list[PipelineRun] = []
    for r in raw:
        start = r.get("startTime")
        end = r.get("endTime")
        duration = int(end - start) if (start and end) else None
        tags = {t["key"]: t["value"] for t in (r.get("tags") or [])}
        job = tags.get("dagster/job_name") or r.get("_queried_job") or r.get("pipelineName") or "—"
        status = _dagster_status(r["status"])
        notes = ""
        if status == "failed":
            notes = "Run failed — check Dagster logs"
        runs.append(PipelineRun(
            run_id=r["runId"],
            timestamp_et=_format_ts(start),
            job_name=job,
            duration_seconds=duration,
            status=status,
            notes=notes,
        ))

    return runs


# ---------------------------------------------------------------------------
# Model freshness (Snowflake model_registry)
# ---------------------------------------------------------------------------


def _live_served_version() -> str | None:
    """Champion bundle version actually stamped on recent served predictions.

    model_registry is a promotion ledger that can lag a champion swap (E13.11 shipped
    v6 to S3/serving but the registry still marks v5 current). daily_model_predictions
    records the version predict_today actually used, so it's the truthful "what's live"
    source. Returns the highest vN seen on the last ~14 days of predictions — both
    tiers ('pre_lineup_v6' and 'v6') normalize to v6 — or None if unavailable.
    """
    try:
        rows = execute_query(
            """
            SELECT DISTINCT model_version
            FROM baseball_data.betting_ml.daily_model_predictions
            WHERE game_date >= DATEADD('day', -14, CURRENT_DATE())
            """
        )
    except Exception:
        logger.warning("daily_model_predictions version lookup failed — falling back to registry")
        return None
    best: int | None = None
    for r in rows:
        m = re.search(r"v(\d+)", str(r.get("MODEL_VERSION") or ""))
        if m:
            n = int(m.group(1))
            best = n if best is None else max(best, n)
    return f"v{best}" if best is not None else None


@router.get("/model-freshness", response_model=list[ModelFreshness])
def model_freshness(_: str = Depends(get_admin_user)) -> list[ModelFreshness]:
    """Current champion models with days_since_training.

    Version shown is the LIVE served version (from daily_model_predictions) so the
    panel reflects what's actually serving even when the promotion ledger lags; the
    registry version + a `ledger_behind` flag surface any mismatch for reconciliation.
    """
    try:
        rows = execute_query(
            f"""
            SELECT
                target,
                model_name,
                model_version,
                promoted_date,
                DATEDIFF('day', promoted_date, CURRENT_DATE) AS days_since
            FROM {_REGISTRY}
            WHERE is_current = TRUE
            ORDER BY target
            """
        )
    except Exception:
        logger.exception("model_registry query failed")
        return []

    live_version = _live_served_version()

    results: list[ModelFreshness] = []
    for row in rows:
        days = int(row.get("DAYS_SINCE") or 0)
        registry_version = str(row.get("MODEL_VERSION") or "—")
        served_version = live_version or registry_version
        ledger_behind = bool(live_version and live_version != registry_version)

        if ledger_behind:
            # Serving a version the ledger hasn't recorded — flag for reconciliation.
            freshness_status = "watch"
        elif days < 30:
            freshness_status = "healthy"
        elif days <= 60:
            freshness_status = "watch"
        else:
            freshness_status = "stale"

        results.append(ModelFreshness(
            model_name=str(row.get("MODEL_NAME") or "—"),
            target=str(row.get("TARGET") or "—"),
            version=served_version,
            registry_version=registry_version,
            ledger_behind=ledger_behind,
            last_trained_date=str(row.get("PROMOTED_DATE") or "—"),
            days_since_training=days,
            status=freshness_status,
        ))

    return results


# ---------------------------------------------------------------------------
# Snowflake credit usage (ACCOUNT_USAGE.METERING_DAILY_HISTORY)
# ---------------------------------------------------------------------------


@router.get("/snowflake-credits", response_model=list[SnowflakeCredits])
def snowflake_credits(_: str = Depends(get_admin_user)) -> list[SnowflakeCredits]:
    """Month-by-month Snowflake credit consumption for the last 6 months.

    Applies Snowflake's cloud-services billing rule: cloud-services credits are
    only billed for the portion that exceeds 10% of the day's COMPUTE credits.
    The adjustment is applied DAILY (aggregate per day first, then sum the month) —
    applying it to the period total under-counts, since a free day cannot offset a
    heavy day. So billed ≈ SUM_day(compute + MAX(0, cloud_services − 0.10·compute)).

    Requires the Lambda's Snowflake role to have IMPORTED PRIVILEGES on the
    SNOWFLAKE database (i.e. GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO
    ROLE <lambda_role>). Returns [] gracefully if the role lacks access.
    """
    try:
        rows = execute_query(
            """
            WITH daily AS (
                SELECT
                    USAGE_DATE,
                    SUM(CREDITS_USED_COMPUTE)        AS compute_c,
                    SUM(CREDITS_USED_CLOUD_SERVICES) AS cloud_c
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
                WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE())
                GROUP BY USAGE_DATE
            )
            SELECT
                DATE_TRUNC('month', USAGE_DATE)                                  AS month,
                SUM(compute_c)                                                   AS compute_credits,
                SUM(cloud_c)                                                     AS cloud_service_credits,
                SUM(compute_c + GREATEST(0, cloud_c - 0.10 * compute_c))         AS billed_credits
            FROM daily
            GROUP BY 1
            ORDER BY 1 DESC
            """
        )
    except Exception:
        logger.warning("snowflake_credits query failed — role may lack IMPORTED PRIVILEGES")
        return []

    results: list[SnowflakeCredits] = []
    for row in rows:
        month_dt = row.get("MONTH")
        if month_dt is None:
            continue
        if hasattr(month_dt, "strftime"):
            month_key = month_dt.strftime("%Y-%m")
            month_label = month_dt.strftime("%b %Y")
        else:
            month_key = str(month_dt)[:7]
            month_label = str(month_dt)[:7]
        results.append(SnowflakeCredits(
            month=month_key,
            month_label=month_label,
            compute_credits=round(float(row.get("COMPUTE_CREDITS") or 0), 2),
            cloud_service_credits=round(float(row.get("CLOUD_SERVICE_CREDITS") or 0), 2),
            billed_credits=round(float(row.get("BILLED_CREDITS") or 0), 2),
        ))

    return results

"""Admin endpoints.

POST /admin/cache/invalidate    — invalidate today's S3 cache
GET  /admin/pipeline-runs       — last 14 Dagster run entries (two jobs)
GET  /admin/model-freshness     — champion model freshness from model_registry
GET  /admin/snowflake-credits   — month-by-month Snowflake credit usage (last 6 months)
"""

from __future__ import annotations

import datetime
import json
import logging
import os
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

_DAGSTER_ENDPOINT = "https://penumbra-partners.dagster.plus/prod/graphql"
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
    version: str
    last_trained_date: str
    days_since_training: int
    status: str  # "healthy" | "watch" | "stale"


class SnowflakeCredits(BaseModel):
    month: str          # "2026-06" formatted
    month_label: str    # "Jun 2026" formatted
    compute_credits: float
    cloud_service_credits: float
    total_credits: float


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


def _dagster_runs_for_job(token: str, job: str, limit: int = 8) -> list[dict]:
    query = (
        "query($f:RunsFilter,$n:Int){"
        "runsOrError(filter:$f,limit:$n){"
        "__typename "
        "...on Runs{results{runId status startTime endTime "
        "tags{key value}}}"
        "...on PythonError{message}}}"
    )
    body = json.dumps({"query": query, "variables": {"f": {"pipelineName": job}, "n": limit}}).encode()
    req = urllib.request.Request(
        _DAGSTER_ENDPOINT,
        data=body,
        headers={"Dagster-Cloud-Api-Token": token, "Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    node = resp.get("data", {}).get("runsOrError", {})
    if node.get("__typename") != "Runs":
        logger.warning("Dagster GraphQL error for %s: %s", job, str(resp)[:400])
        return []
    return node["results"]


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
    """Last 14 Dagster run entries across daily_ingestion_job and lineup_monitor_sensor."""
    token = os.getenv("DAGSTER_CLOUD_API_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="DAGSTER_CLOUD_API_TOKEN not configured")

    try:
        raw = (
            _dagster_runs_for_job(token, "daily_ingestion_job", 8)
            + _dagster_runs_for_job(token, "lineup_monitor_job", 8)
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
        job = tags.get("dagster/job_name") or r.get("pipelineName", "—")
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


@router.get("/model-freshness", response_model=list[ModelFreshness])
def model_freshness(_: str = Depends(get_admin_user)) -> list[ModelFreshness]:
    """Current champion models from model_registry with days_since_training."""
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

    results: list[ModelFreshness] = []
    for row in rows:
        days = int(row.get("DAYS_SINCE") or 0)
        if days < 30:
            freshness_status = "healthy"
        elif days <= 60:
            freshness_status = "watch"
        else:
            freshness_status = "stale"

        results.append(ModelFreshness(
            model_name=str(row.get("MODEL_NAME") or "—"),
            target=str(row.get("TARGET") or "—"),
            version=str(row.get("MODEL_VERSION") or "—"),
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

    Requires the Lambda's Snowflake role to have IMPORTED PRIVILEGES on the
    SNOWFLAKE database (i.e. GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO
    ROLE <lambda_role>). Returns [] gracefully if the role lacks access.
    """
    try:
        rows = execute_query(
            """
            SELECT
                DATE_TRUNC('month', USAGE_DATE)              AS month,
                SUM(CREDITS_USED_COMPUTE)                    AS compute_credits,
                SUM(CREDITS_USED_CLOUD_SERVICES)             AS cloud_service_credits,
                SUM(CREDITS_USED_COMPUTE
                    + CREDITS_USED_CLOUD_SERVICES)           AS total_credits
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
            WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE())
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
            total_credits=round(float(row.get("TOTAL_CREDITS") or 0), 2),
        ))

    return results

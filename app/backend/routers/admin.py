"""Admin endpoints.

POST /admin/cache/invalidate  — invalidate today's S3 cache
GET  /admin/pipeline-runs     — last 14 Dagster run entries (two jobs)
GET  /admin/model-freshness   — champion model freshness from model_registry
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Cache invalidation (unchanged)
# ---------------------------------------------------------------------------


@router.post("/cache/invalidate")
def invalidate_cache() -> dict:
    """Invalidates today's S3 cache — forces next request to re-query Snowflake."""
    invalidate_today()
    return {"status": "ok", "message": "Cache invalidated — next request will re-query Snowflake"}


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
def pipeline_runs() -> list[PipelineRun]:
    """Last 14 Dagster run entries across daily_ingestion_job and lineup_monitor_sensor."""
    token = os.getenv("DAGSTER_CLOUD_API_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="DAGSTER_CLOUD_API_TOKEN not configured")

    try:
        raw = (
            _dagster_runs_for_job(token, "daily_ingestion_job", 8)
            + _dagster_runs_for_job(token, "lineup_monitor_sensor", 8)
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
def model_freshness() -> list[ModelFreshness]:
    """Current champion models from model_registry with days_since_training."""
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

    results: list[ModelFreshness] = []
    for row in rows:
        days = int(row.get("days_since") or 0)
        if days < 30:
            freshness_status = "healthy"
        elif days <= 60:
            freshness_status = "watch"
        else:
            freshness_status = "stale"

        results.append(ModelFreshness(
            model_name=str(row.get("model_name") or "—"),
            target=str(row.get("target") or "—"),
            version=str(row.get("model_version") or "—"),
            last_trained_date=str(row.get("promoted_date") or "—"),
            days_since_training=days,
            status=freshness_status,
        ))

    return results

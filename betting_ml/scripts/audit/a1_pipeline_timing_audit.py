#!/usr/bin/env python3
"""
A1.1 — Pipeline Timing Audit

Pulls the last N days of daily_ingestion_job run history from two sources:
  1. Dagster Cloud GraphQL API  — op-level step timing and failure metadata
  2. Snowflake                  — first pitch times, prediction insertion timestamps

Produces: quant_sports_intel_models/baseball/runbooks/dagster_pipeline_sla_analysis.md

Usage:
    python a1_pipeline_timing_audit.py \
        --dagster-url https://myorg.dagster.cloud/prod \
        --days 14

Required environment variables:
    DAGSTER_CLOUD_API_TOKEN   User token from Dagster Cloud → Settings → User tokens
                              (NOT the agent token in dagster.yaml)
    DAGSTER_CLOUD_URL         Deployment URL, e.g. https://myorg.dagster.cloud/prod
                              (can also be passed via --dagster-url)

    Snowflake (standard project vars):
    SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_WAREHOUSE / SNOWFLAKE_ROLE
    SNOWFLAKE_PRIVATE_KEY_PATH
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

# ── Project layout ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "quant_sports_intel_models"
    / "baseball"
    / "runbooks"
    / "dagster_pipeline_sla_analysis.md"
)

# ── SLA parameters ─────────────────────────────────────────────────────────────

SLA_LEAD_MINUTES = 30          # predictions must be ready this many minutes before first pitch
JOB_SCHEDULE_UTC = "12:00"     # 0 12 * * * = 08:00 EDT = 12:00 UTC
JOB_NAME = "daily_ingestion_job"

# Canonical op order (used for timing table columns and duration summary)
KEY_OPS_ORDERED = [
    "ingest_parlay_events",
    "ingest_parlay_canonical_events",
    "ingest_parlay_odds",
    "ingest_action_network",
    "ingest_statcast",
    "ingest_statsapi_schedule",
    "ingest_weather",
    "ingest_umpires_early",
    "ingest_fangraphs_stuff_plus",
    "ingest_fangraphs_hitting_leaderboard",
    "ingest_transactions",
    "ingest_oaa",
    "compute_elo",
    "check_data_freshness",
    "dbt_daily_build",
    "generate_run_env_signals_op",
    "generate_offense_signals_op",
    "generate_starter_signals_op",
    "generate_starter_ip_signals_op",
    "generate_bullpen_signals_op",
    "generate_matchup_signals_op",
    "dbt_sub_model_signals_rebuild",
    "signal_freshness_check",
    "update_market_features_scd2",
    "dbt_pregame_odds_rebuild",
    "update_lineup_state_scd2",
    "dbt_lineup_feature_rebuild",
    "ingest_umpires_late",
    "compute_eb_bullpen_posteriors_op",
    "update_player_posteriors_op",
    "update_team_posteriors_op",
    "update_matchup_cell_posteriors_op",
    "dbt_umpire_feature_rebuild",
    "predict_today_morning",
    "check_prediction_coverage",
    "dbt_mart_prediction_clv",
    "compute_model_health",
    "backfill_prediction_log",
]

# ── Dagster Cloud GraphQL ──────────────────────────────────────────────────────

# Batch query: list runs with embedded step stats.
# Works in Dagster ≥1.5; step stats are in the same response to avoid N+1 queries.
RUNS_QUERY = """
query AuditRuns($filter: RunsFilter!, $limit: Int) {
  runsOrError(filter: $filter, limit: $limit) {
    __typename
    ... on Runs {
      results {
        runId
        pipelineName
        status
        startTime
        endTime
        tags { key value }
        stepStats {
          stepKey
          startTime
          endTime
          status
        }
      }
    }
    ... on InvalidPipelineRunsFilterError { message }
    ... on PythonError { message stack }
  }
}
"""

# Fallback: fetch step stats for a single run by ID.
RUN_DETAIL_QUERY = """
query AuditRunDetail($runId: ID!) {
  pipelineRunOrError(runId: $runId) {
    __typename
    ... on PipelineRun {
      runId
      stepStats {
        stepKey
        startTime
        endTime
        status
      }
    }
    ... on PipelineRunNotFoundError { message }
    ... on PythonError { message }
  }
}
"""


def _deployment_name_from_url(url: str) -> str:
    """Extract deployment name from URL path, e.g. https://org.dagster.plus/prod -> 'prod'."""
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    # last path segment is the deployment name; if empty, assume 'prod'
    return path.split("/")[-1] if path else "prod"


def _dagster_request(
    url: str,
    token: str,
    query: str,
    variables: dict[str, Any],
    label: str = "",
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if "dagster.plus" in url or "dagster.cloud" in url:   # legacy Dagster+ Cloud
        deployment = _deployment_name_from_url(url)
        headers["Dagster-Cloud-Api-Token"] = token
        # Required by Dagster Plus to route to the correct deployment
        headers["Dagster-Cloud-Scope"] = "deployment"
        headers["Dagster-Cloud-Deployment"] = deployment
    else:                                                  # self-hosted OSS (INC-16): Caddy basic-auth / none
        ba_user = os.environ.get("DAGIT_BASIC_AUTH_USER")
        ba_pw = os.environ.get("DAGIT_BASIC_AUTH_PASSWORD")
        if ba_user and ba_pw:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{ba_user}:{ba_pw}".encode()).decode()
    payload = {"query": query, "variables": variables}
    resp = requests.post(f"{url.rstrip('/')}/graphql", headers=headers, json=payload, timeout=60)
    # Dagster Plus returns HTTP 400 for GraphQL validation errors; parse body before raising
    try:
        body = resp.json()
    except Exception:
        resp.raise_for_status()
        raise
    # A 400 with a GraphQL errors array is a query/variable problem, not an auth failure —
    # surface it as a RuntimeError so callers can handle it gracefully
    if "errors" in body:
        msgs = "; ".join(e.get("message", str(e)) for e in body["errors"])
        raise RuntimeError(f"GraphQL errors{' (' + label + ')' if label else ''}: {msgs}")
    if not resp.ok:
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} for url: {resp.url}",
            response=resp,
        )
    return body.get("data", {})


def fetch_dagster_runs(url: str, token: str, days: int) -> list[dict[str, Any]]:
    """Return all daily_ingestion_job runs from the last `days` days with step stats."""
    cutoff_epoch = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).timestamp()

    base_filter = {"updatedAfter": cutoff_epoch}
    limit = days * 3  # allow multiple runs per day (reruns, manual triggers)

    # Dagster Plus remote schema only exposes pipelineName; local schema also has jobName.
    # Try pipelineName first (works everywhere), fall back to jobName for older local instances.
    result = None
    for name_field in ("pipelineName", "jobName"):
        variables: dict[str, Any] = {
            "filter": {name_field: JOB_NAME, **base_filter},
            "limit": limit,
        }
        try:
            data = _dagster_request(url, token, RUNS_QUERY, variables, label=f"runs list ({name_field})")
            result = data.get("runsOrError", {})
            if result.get("__typename") == "Runs":
                break
            msg = result.get("message", "unknown")
            print(f"  {name_field} filter returned non-Runs ({msg}), trying next …", file=sys.stderr)
        except RuntimeError as exc:
            print(f"  {name_field} filter failed ({exc}), trying next …", file=sys.stderr)
            result = None

    if not result or result.get("__typename") != "Runs":
        raise RuntimeError(f"Could not fetch runs: {result}")

    runs = result["results"]
    print(f"  Fetched {len(runs)} runs from Dagster Cloud.", file=sys.stderr)

    # Back-fill step stats for any runs where they came back empty
    enriched = []
    for run in runs:
        if not run.get("stepStats"):
            print(
                f"  Fetching step stats for run {run['runId'][:8]}… (stepStats missing in batch)",
                file=sys.stderr,
            )
            try:
                detail = _dagster_request(
                    url, token, RUN_DETAIL_QUERY,
                    {"runId": run["runId"]}, label="run detail"
                )
                inner = detail.get("pipelineRunOrError", {})
                if inner.get("__typename") == "PipelineRun":
                    run["stepStats"] = inner.get("stepStats", [])
            except Exception as exc:
                print(f"    Warning: could not fetch detail for {run['runId'][:8]}: {exc}", file=sys.stderr)
        enriched.append(run)

    return enriched


# ── Snowflake ──────────────────────────────────────────────────────────────────

def _sf_connect() -> snowflake.connector.SnowflakeConnection:
    key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    with open(key_path, "rb") as f:
        private_key = load_pem_private_key(f.read(), password=None, backend=default_backend())
    private_key_bytes = private_key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=private_key_bytes,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
    )


def fetch_first_pitch_times(conn: snowflake.connector.SnowflakeConnection, days: int) -> dict[str, datetime]:
    """Return {official_date_str: earliest_first_pitch_utc} for the last `days` days."""
    # GAME_DATE is TIMESTAMP_TZ (UTC-based). Use it directly; the Snowflake connector
    # returns it as a timezone-aware datetime.  Do NOT apply CONVERT_TIMEZONE here —
    # that would produce an ET value and cause SLA comparisons to be off by 4-5 hours.
    sql = f"""
        SELECT
            official_date,
            MIN(game_date) AS earliest_fp_utc
        FROM baseball_data.betting.stg_statsapi_games
        WHERE official_date >= DATEADD(day, -{days + 2}, CURRENT_DATE())
          AND official_date <= CURRENT_DATE()
          AND game_type = 'R'
        GROUP BY official_date
        ORDER BY official_date
    """
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    result = {}
    for row in rows:
        date_key = str(row["OFFICIAL_DATE"])
        fp = row["EARLIEST_FP_UTC"]
        if isinstance(fp, datetime):
            if fp.tzinfo is None:
                # TIMESTAMP_TZ with UTC offset — treat as UTC
                fp = fp.replace(tzinfo=timezone.utc)
            else:
                # Normalize to UTC regardless of what tz the connector attached
                fp = fp.astimezone(timezone.utc)
            result[date_key] = fp
        elif isinstance(fp, str):
            result[date_key] = datetime.fromisoformat(fp).astimezone(timezone.utc)
    return result


def fetch_prediction_timing(
    conn: snowflake.connector.SnowflakeConnection, days: int
) -> dict[str, dict[str, datetime | None]]:
    """Return {score_date_str: {morning: first_ts, post_lineup: first_ts}} for last `days` days."""
    sql = f"""
        SELECT
            score_date,
            prediction_type,
            MIN(inserted_at) AS first_inserted_utc
        FROM baseball_data.betting_ml.daily_model_predictions
        WHERE score_date >= DATEADD(day, -{days + 2}, CURRENT_DATE())
          AND score_date <= CURRENT_DATE()
        GROUP BY score_date, prediction_type
        ORDER BY score_date, prediction_type
    """
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    result: dict[str, dict[str, datetime | None]] = defaultdict(lambda: {"morning": None, "post_lineup": None})
    for row in rows:
        date_key = str(row["SCORE_DATE"])
        ptype = (row["PREDICTION_TYPE"] or "").lower()
        ts = row["FIRST_INSERTED_UTC"]
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        elif isinstance(ts, str):
            ts = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        result[date_key][ptype] = ts
    return result


# ── Analysis ───────────────────────────────────────────────────────────────────

def _epoch_to_utc(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _fmt_ts(dt: datetime | None, fmt: str = "%H:%M:%S UTC") -> str:
    if dt is None:
        return "—"
    return dt.strftime(fmt)


def _fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(int(seconds), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def _run_date(run: dict[str, Any]) -> str:
    """Infer the game date this run was predicting (= calendar date of job start in ET)."""
    start_epoch = run.get("startTime")
    if not start_epoch:
        return "unknown"
    start_utc = _epoch_to_utc(start_epoch)
    # Job starts at 12:00 UTC = 08:00 EDT. The game date is the same calendar date.
    et_offset = timedelta(hours=-4)  # EDT (UTC-4); close enough for date inference
    start_et = start_utc + et_offset
    return start_et.strftime("%Y-%m-%d")


def build_run_timing(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten each run into a dict with key op timings and durations."""
    records = []
    for run in runs:
        run_date = _run_date(run)
        start_utc = _epoch_to_utc(run.get("startTime"))
        end_utc = _epoch_to_utc(run.get("endTime"))
        total_sec = (end_utc - start_utc).total_seconds() if (start_utc and end_utc) else None

        # Build step lookup: stepKey → {start, end, status, duration_sec}
        steps: dict[str, dict[str, Any]] = {}
        for ss in run.get("stepStats") or []:
            key = ss["stepKey"]
            s = _epoch_to_utc(ss.get("startTime"))
            e = _epoch_to_utc(ss.get("endTime"))
            dur = (e - s).total_seconds() if (s and e) else None
            steps[key] = {"start": s, "end": e, "status": ss.get("status"), "duration_sec": dur}

        predict_step = steps.get("predict_today_morning") or steps.get("predict_today_op")
        dbt_step = steps.get("dbt_daily_build")

        records.append({
            "run_date": run_date,
            "run_id": run["runId"],
            "run_status": run.get("status", "UNKNOWN"),
            "job_start_utc": start_utc,
            "job_end_utc": end_utc,
            "total_duration_sec": total_sec,
            "predict_complete_utc": predict_step["end"] if predict_step else None,
            "predict_status": predict_step["status"] if predict_step else "MISSING",
            "dbt_build_duration_sec": dbt_step["duration_sec"] if dbt_step else None,
            "steps": steps,
            "failed_ops": [
                k for k, v in steps.items()
                if v["status"] in ("FAILURE", "FAILED")
            ],
            "skipped_ops": [
                k for k, v in steps.items()
                if v["status"] in ("SKIPPED",)
            ],
        })

    return records


def compute_sla(
    run_records: list[dict[str, Any]],
    first_pitch_times: dict[str, datetime],
    pred_timing: dict[str, dict[str, datetime | None]],
    sla_lead_min: int,
) -> list[dict[str, Any]]:
    """Attach SLA metrics to each run record."""
    results = []
    for rec in run_records:
        date = rec["run_date"]
        fp = first_pitch_times.get(date)
        sla_deadline = (fp - timedelta(minutes=sla_lead_min)) if fp else None

        # Morning prediction timestamp: prefer Dagster step end, fall back to Snowflake INSERTED_AT
        dagster_predict_end = rec.get("predict_complete_utc")
        sf_morning_ts = pred_timing.get(date, {}).get("morning")
        sf_postlineup_ts = pred_timing.get(date, {}).get("post_lineup")

        # Best estimate of when morning predictions were ready
        morning_ready = dagster_predict_end or sf_morning_ts

        sla_margin_min: float | None = None
        sla_met: bool | None = None
        if sla_deadline and morning_ready:
            sla_margin_min = (sla_deadline - morning_ready).total_seconds() / 60
            sla_met = sla_margin_min >= 0

        results.append({
            **rec,
            "earliest_first_pitch_utc": fp,
            "sla_deadline_utc": sla_deadline,
            "morning_ready_utc": morning_ready,
            "sf_morning_ts": sf_morning_ts,
            "sf_postlineup_ts": sf_postlineup_ts,
            "has_post_lineup": sf_postlineup_ts is not None,
            "sla_margin_min": sla_margin_min,
            "sla_met": sla_met,
        })

    return results


def build_op_duration_summary(
    run_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-op stats: mean/max/p90 duration, failure rate, across all runs."""
    op_data: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in run_records:
        for op_key, step in rec["steps"].items():
            op_data[op_key].append(step)

    summary = []
    for op_key in KEY_OPS_ORDERED:
        samples = op_data.get(op_key, [])
        if not samples:
            summary.append({"op": op_key, "runs": 0, "mean_sec": None, "max_sec": None,
                             "p90_sec": None, "failure_rate": None})
            continue
        durations = [s["duration_sec"] for s in samples if s["duration_sec"] is not None]
        statuses = [s["status"] for s in samples]
        n_failed = sum(1 for s in statuses if s in ("FAILURE", "FAILED"))
        durations_sorted = sorted(durations)
        mean_sec = sum(durations) / len(durations) if durations else None
        max_sec = max(durations) if durations else None
        p90_sec = (
            durations_sorted[int(len(durations_sorted) * 0.9)]
            if len(durations_sorted) >= 2
            else (durations_sorted[-1] if durations_sorted else None)
        )
        summary.append({
            "op": op_key,
            "runs": len(samples),
            "mean_sec": mean_sec,
            "max_sec": max_sec,
            "p90_sec": p90_sec,
            "failure_rate": n_failed / len(samples) if samples else 0.0,
        })

    # Also append any ops NOT in KEY_OPS_ORDERED that appeared in actual runs
    known = set(KEY_OPS_ORDERED)
    for op_key in sorted(op_data.keys()):
        if op_key not in known:
            samples = op_data[op_key]
            durations = [s["duration_sec"] for s in samples if s["duration_sec"] is not None]
            n_failed = sum(1 for s in samples if s["status"] in ("FAILURE", "FAILED"))
            summary.append({
                "op": f"{op_key} *",
                "runs": len(samples),
                "mean_sec": sum(durations) / len(durations) if durations else None,
                "max_sec": max(durations) if durations else None,
                "p90_sec": None,
                "failure_rate": n_failed / len(samples) if samples else 0.0,
            })

    return summary


def identify_failure_modes(sla_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank failure modes by frequency and impact."""
    modes: list[dict[str, Any]] = []

    # FM-1: Morning run entirely missing
    missing_morning = [r for r in sla_records if r.get("sf_morning_ts") is None]
    if missing_morning:
        modes.append({
            "id": "FM-1",
            "name": "Morning run absent",
            "description": (
                "daily_ingestion_job completed but no 'morning' predictions were inserted. "
                "Either predict_today_morning op was skipped/failed, or the job itself did not run."
            ),
            "occurrences": len(missing_morning),
            "affected_dates": [r["run_date"] for r in missing_morning],
            "sla_impact": "CRITICAL — no predictions available at all for those game days",
        })

    # FM-2: Morning run present but SLA missed
    sla_failed_with_morning = [
        r for r in sla_records
        if r.get("sf_morning_ts") and r.get("sla_met") is False
    ]
    if sla_failed_with_morning:
        modes.append({
            "id": "FM-2",
            "name": "Morning predictions arrived after SLA deadline",
            "description": (
                "Morning predictions were inserted but AFTER the 30-minute-before-first-pitch deadline. "
                "Likely caused by slow upstream ops delaying predict_today_morning."
            ),
            "occurrences": len(sla_failed_with_morning),
            "affected_dates": [r["run_date"] for r in sla_failed_with_morning],
            "avg_miss_min": (
                abs(sum(r["sla_margin_min"] for r in sla_failed_with_morning
                        if r["sla_margin_min"] is not None))
                / len(sla_failed_with_morning)
            ),
            "sla_impact": "HIGH — predictions available but after games started",
        })

    # FM-3: No post-lineup re-run
    no_postlineup = [r for r in sla_records if not r.get("has_post_lineup")]
    if no_postlineup:
        modes.append({
            "id": "FM-3",
            "name": "Post-lineup re-run absent",
            "description": (
                "lineup_monitor sensor did not trigger a post-lineup prediction re-run. "
                "Predictions served to the app may be based on projected lineups, not confirmed lineups."
            ),
            "occurrences": len(no_postlineup),
            "affected_dates": [r["run_date"] for r in no_postlineup],
            "sla_impact": "MEDIUM — morning predictions available but lineup accuracy degraded",
        })

    # FM-4: Ops that failed across runs (from Dagster step data)
    all_failed_ops: dict[str, int] = defaultdict(int)
    for r in sla_records:
        for op in r.get("failed_ops", []):
            all_failed_ops[op] += 1
    for op, count in sorted(all_failed_ops.items(), key=lambda x: -x[1]):
        modes.append({
            "id": "FM-4",
            "name": f"Op failure: {op}",
            "description": f"{op} failed in {count} of {len(sla_records)} runs.",
            "occurrences": count,
            "affected_dates": [
                r["run_date"] for r in sla_records if op in r.get("failed_ops", [])
            ],
            "sla_impact": "VARIABLE — depends on whether op is on the critical path to predict_today_morning",
        })

    # FM-5: Delayed job start
    delayed_starts = [
        r for r in sla_records
        if r.get("job_start_utc")
        and r["job_start_utc"].strftime("%H:%M") > "13:00"  # >1h past scheduled start
    ]
    if delayed_starts:
        modes.append({
            "id": "FM-5",
            "name": "Job start significantly delayed",
            "description": (
                "daily_ingestion_job did not start until >1h after the scheduled 12:00 UTC start time. "
                "This compresses the available window for all downstream ops."
            ),
            "occurrences": len(delayed_starts),
            "affected_dates": [r["run_date"] for r in delayed_starts],
            "sla_impact": "HIGH — entire pipeline shifted later; early-game SLA at risk",
        })

    return modes


# ── Report generation ─────────────────────────────────────────────────────────

def _sla_badge(met: bool | None) -> str:
    if met is True:
        return "✅ PASS"
    if met is False:
        return "❌ FAIL"
    return "⚠️  UNKNOWN"


def render_report(
    sla_records: list[dict[str, Any]],
    op_summary: list[dict[str, Any]],
    failure_modes: list[dict[str, Any]],
    days: int,
    dagster_available: bool,
    run_ts: datetime,
) -> str:
    # ── Header ─────────────────────────────────────────────────────────────────
    lines: list[str] = []
    lines += [
        "# Epic A1.1 — Pipeline Timing Audit",
        "",
        f"**Generated:** {run_ts.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Audit window:** Last {days} days  ",
        f"**SLA definition:** morning predictions inserted ≥{SLA_LEAD_MINUTES} min before earliest scheduled first pitch  ",
        f"**Dagster Cloud data:** {'✅ Available' if dagster_available else '⚠️  Not available — Snowflake-only analysis'}  ",
        "",
        "---",
        "",
    ]

    # ── Executive summary ─────────────────────────────────────────────────────
    with_sla = [r for r in sla_records if r.get("sla_met") is not None]
    n_pass = sum(1 for r in with_sla if r["sla_met"])
    n_fail = sum(1 for r in with_sla if not r["sla_met"])
    compliance_pct = 100 * n_pass / len(with_sla) if with_sla else 0
    no_postlineup_days = sum(1 for r in sla_records if not r.get("has_post_lineup"))
    postlineup_pct = 100 * (len(sla_records) - no_postlineup_days) / len(sla_records) if sla_records else 0

    top_mode = failure_modes[0] if failure_modes else None
    top_mode_name = top_mode["name"] if top_mode else "none identified"

    lines += [
        "## Executive Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Days audited | {len(sla_records)} |",
        f"| **Morning SLA compliance (≥30 min before first pitch)** | **{n_pass}/{len(with_sla)} days ({compliance_pct:.0f}%)** |",
        f"| SLA failures | {n_fail} day(s) |",
        f"| Days with post-lineup re-run | {len(sla_records) - no_postlineup_days}/{len(sla_records)} ({postlineup_pct:.0f}%) |",
        f"| Failure modes identified | {len(failure_modes)} |",
        f"| Top failure mode | {top_mode_name} |",
        "",
    ]

    if n_fail > 0 or compliance_pct < 95:
        lines += [
            f"> ⚠️  **SLA compliance is {compliance_pct:.0f}%** — below the 95% target required for beta launch.",
            "",
        ]
    else:
        lines += [
            f"> ✅ Morning SLA compliance meets the 95% beta-launch target.",
            "",
        ]

    if postlineup_pct < 95:
        lines += [
            f"> ⚠️  **Post-lineup re-run fires on only {postlineup_pct:.0f}% of days** — A1.2 is required before beta launch.",
            "",
        ]

    lines += ["---", ""]

    # ── Per-day SLA table ──────────────────────────────────────────────────────
    lines += [
        "## Per-Day SLA Table",
        "",
        "All timestamps UTC. `Morning ready` = Dagster `predict_today_morning` step end (if available) "
        "or earliest `INSERTED_AT` from `daily_model_predictions`.",
        "",
        "| Date | Job Start | Morning Ready | Earliest 1st Pitch | SLA Deadline | Margin | SLA | Post-Lineup? | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in sorted(sla_records, key=lambda x: x["run_date"]):
        margin_str = (
            f"+{r['sla_margin_min']:.0f}m"
            if r.get("sla_margin_min") is not None and r["sla_margin_min"] >= 0
            else (f"{r['sla_margin_min']:.0f}m" if r.get("sla_margin_min") is not None else "—")
        )
        notes_parts = []
        if r.get("run_status") and r["run_status"] not in ("SUCCESS", ""):
            notes_parts.append(f"job={r['run_status']}")
        if r.get("failed_ops"):
            notes_parts.append(f"failed: {', '.join(r['failed_ops'][:3])}")
        # Flag predictions inserted before the scheduled 12:00 UTC job start (likely a backfill/manual run)
        morning_ts = r.get("sf_morning_ts")
        if morning_ts and morning_ts.hour < 11:
            notes_parts.append("⚠️ pre-job-start insertion (backfill?)")
        postlineup_icon = "✅" if r.get("has_post_lineup") else "❌"
        lines.append(
            f"| {r['run_date']} "
            f"| {_fmt_ts(r.get('job_start_utc'))} "
            f"| {_fmt_ts(r.get('morning_ready_utc'))} "
            f"| {_fmt_ts(r.get('earliest_first_pitch_utc'))} "
            f"| {_fmt_ts(r.get('sla_deadline_utc'))} "
            f"| {margin_str} "
            f"| {_sla_badge(r.get('sla_met'))} "
            f"| {postlineup_icon} "
            f"| {'; '.join(notes_parts) or '—'} |"
        )

    lines += ["", "---", ""]

    # ── Op duration summary (only if Dagster data available) ──────────────────
    if dagster_available:
        lines += [
            "## Op Duration Summary",
            "",
            "Durations measured from Dagster Cloud step stats. Ops not observed in any run are omitted.",
            "",
            "| Op | Runs | Mean | p90 | Max | Fail Rate |",
            "|---|---|---|---|---|---|",
        ]
        for row in op_summary:
            if row["runs"] == 0:
                continue
            fail_pct = f"{row['failure_rate'] * 100:.0f}%" if row["failure_rate"] is not None else "—"
            lines.append(
                f"| `{row['op']}` "
                f"| {row['runs']} "
                f"| {_fmt_dur(row.get('mean_sec'))} "
                f"| {_fmt_dur(row.get('p90_sec'))} "
                f"| {_fmt_dur(row.get('max_sec'))} "
                f"| {fail_pct} |"
            )
        lines += ["", "---", ""]

    # ── Failure mode analysis ──────────────────────────────────────────────────
    lines += [
        "## Failure Mode Analysis",
        "",
        "Ranked by occurrence count descending.",
        "",
    ]

    if not failure_modes:
        lines += ["No failure modes identified in the audit window.", ""]
    else:
        for fm in sorted(failure_modes, key=lambda x: -x["occurrences"]):
            lines += [
                f"### {fm['id']} — {fm['name']}",
                "",
                f"**Occurrences:** {fm['occurrences']} / {len(sla_records)} days  ",
                f"**Affected dates:** {', '.join(fm['affected_dates'])}  ",
                f"**SLA impact:** {fm['sla_impact']}  ",
                "",
                fm["description"],
                "",
            ]
            if "avg_miss_min" in fm:
                lines += [f"**Average miss by:** {fm['avg_miss_min']:.0f} minutes", ""]

    lines += ["---", ""]

    # ── Story sequencing recommendation ───────────────────────────────────────
    lines += [
        "## A1.2–A1.5 Sequencing Recommendation",
        "",
        "Based on this audit, the following stories are most urgent:",
        "",
    ]

    recommendations = []
    fm_ids = {fm["id"] for fm in failure_modes}

    # A1.2 — consolidate into a single recommendation regardless of which FM triggered it
    a12_reasons = []
    if "FM-1" in fm_ids:
        a12_reasons.append("morning run was absent on at least one day")
    if "FM-2" in fm_ids:
        a12_reasons.append("morning predictions arrived after the SLA deadline on at least one day")
    if "FM-3" in fm_ids:
        a12_reasons.append(
            f"post-lineup re-run fires on only {postlineup_pct:.0f}% of days — "
            "lineup_monitor sensor may not be triggering the post-predict op"
        )
    if a12_reasons:
        reason_str = "; ".join(a12_reasons)
        recommendations.append(
            f"**A1.2 (Post-lineup re-run) — REQUIRED.** {reason_str.capitalize()}. "
            "A reliable post-lineup trigger is the highest-leverage fix: it ensures at least one "
            "confirmed-lineup prediction exists before game time even when the morning run is delayed."
        )

    if "FM-1" in fm_ids or "FM-4" in fm_ids:
        recommendations.append(
            "**A1.3 (Signal freshness gate) — HIGH PRIORITY.** "
            "Ops are failing or the morning run is missing entirely on some days. "
            "The non-blocking `signal_freshness_check_op` means `predict_today_morning` can run on "
            "stale signals — or be silently skipped — without any alert surfaced to the operator."
        )

    if not recommendations:
        recommendations.append(
            "Pipeline is meeting SLA. Proceed with A1.4 (freshness indicator) and "
            "A1.5 (alerting) to add operational visibility before beta launch."
        )

    for rec in recommendations:
        lines += [f"- {rec}", ""]

    lines += ["---", ""]

    # ── Raw data appendix (Snowflake-sourced) ─────────────────────────────────
    lines += [
        "## Appendix — Raw Per-Day Data",
        "",
        "| Date | Score Date Morning Ins. | Score Date Post-Lineup Ins. | Dagster Run ID | Dagster Status |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(sla_records, key=lambda x: x["run_date"]):
        run_id_short = r["run_id"][:8] + "…" if r.get("run_id") else "—"
        lines.append(
            f"| {r['run_date']} "
            f"| {_fmt_ts(r.get('sf_morning_ts'), '%H:%M:%S UTC')} "
            f"| {_fmt_ts(r.get('sf_postlineup_ts'), '%H:%M:%S UTC')} "
            f"| {run_id_short} "
            f"| {r.get('run_status', '—')} |"
        )

    lines += [""]
    return "\n".join(lines)


# ── Snowflake-only fallback ────────────────────────────────────────────────────

def build_snowflake_only_records(
    first_pitch_times: dict[str, datetime],
    pred_timing: dict[str, dict[str, datetime | None]],
    days: int,
) -> list[dict[str, Any]]:
    """Build SLA records from Snowflake alone when Dagster API is unavailable."""
    today = datetime.now(timezone.utc).date()
    records = []
    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        fp = first_pitch_times.get(date)
        sla_deadline = (fp - timedelta(minutes=SLA_LEAD_MINUTES)) if fp else None
        morning_ts = pred_timing.get(date, {}).get("morning")
        postlineup_ts = pred_timing.get(date, {}).get("post_lineup")

        sla_margin_min: float | None = None
        sla_met: bool | None = None
        if sla_deadline and morning_ts:
            sla_margin_min = (sla_deadline - morning_ts).total_seconds() / 60
            sla_met = sla_margin_min >= 0
        elif sla_deadline and morning_ts is None:
            sla_met = False  # no morning predictions = definite SLA fail

        records.append({
            "run_date": date,
            "run_id": None,
            "run_status": "",
            "job_start_utc": None,
            "job_end_utc": None,
            "total_duration_sec": None,
            "predict_complete_utc": None,
            "predict_status": "UNKNOWN",
            "dbt_build_duration_sec": None,
            "steps": {},
            "failed_ops": [],
            "skipped_ops": [],
            "earliest_first_pitch_utc": fp,
            "sla_deadline_utc": sla_deadline,
            "morning_ready_utc": morning_ts,
            "sf_morning_ts": morning_ts,
            "sf_postlineup_ts": postlineup_ts,
            "has_post_lineup": postlineup_ts is not None,
            "sla_margin_min": sla_margin_min,
            "sla_met": sla_met,
        })

    return [r for r in records if r["earliest_first_pitch_utc"] is not None]


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dagster-url", default=os.environ.get("DAGSTER_CLOUD_URL", ""),
                   help="Dagster Cloud deployment URL, e.g. https://myorg.dagster.cloud/prod")
    p.add_argument("--dagster-token", default=os.environ.get("DAGSTER_CLOUD_API_TOKEN", ""),
                   help="Dagster Cloud user token (Settings → User tokens)")
    p.add_argument("--days", type=int, default=14,
                   help="Number of days to audit (default: 14)")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT),
                   help=("Report destination: a local path (default), '-' for stdout "
                         "(no file — best on the ephemeral container), or an s3://bucket/key URI. "
                         f"Default: {DEFAULT_OUTPUT}"))
    p.add_argument("--skip-dagster", action="store_true",
                   help="Skip Dagster API query and use Snowflake-only analysis")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = datetime.now(timezone.utc)
    print(f"A1.1 Pipeline Timing Audit — {run_ts.strftime('%Y-%m-%d %H:%M UTC')}", file=sys.stderr)

    # ── Snowflake ──────────────────────────────────────────────────────────────
    print("Connecting to Snowflake …", file=sys.stderr)
    conn = _sf_connect()
    try:
        print("  Fetching first pitch times …", file=sys.stderr)
        first_pitch_times = fetch_first_pitch_times(conn, args.days)
        print(f"  Got {len(first_pitch_times)} game dates.", file=sys.stderr)

        print("  Fetching prediction timing …", file=sys.stderr)
        pred_timing = fetch_prediction_timing(conn, args.days)
        print(f"  Got prediction records for {len(pred_timing)} score dates.", file=sys.stderr)
    finally:
        conn.close()

    # ── Dagster Cloud ──────────────────────────────────────────────────────────
    dagster_available = False
    run_records: list[dict[str, Any]] = []

    _is_cloud = bool(args.dagster_url) and ("dagster.plus" in args.dagster_url or "dagster.cloud" in args.dagster_url)
    # Self-hosted OSS (INC-16) needs no token — auth is Caddy basic-auth (env) or none.
    if not args.skip_dagster and args.dagster_url and (args.dagster_token or not _is_cloud):
        print(f"Querying Dagster: {args.dagster_url} …", file=sys.stderr)
        try:
            runs = fetch_dagster_runs(args.dagster_url, args.dagster_token, args.days)
            run_records = build_run_timing(runs)
            dagster_available = True
            print(f"  Built timing records for {len(run_records)} runs.", file=sys.stderr)
        except Exception as exc:
            print(f"  ⚠️  Dagster API unavailable: {exc}", file=sys.stderr)
            print("  Falling back to Snowflake-only analysis.", file=sys.stderr)
    else:
        if not args.skip_dagster:
            missing = []
            if not args.dagster_url:
                missing.append("DAGSTER_CLOUD_URL / --dagster-url")
            if not args.dagster_token:
                missing.append("DAGSTER_CLOUD_API_TOKEN / --dagster-token")
            print(
                f"  ⚠️  Skipping Dagster API (missing: {', '.join(missing)}). "
                "Set these to get op-level timing data.",
                file=sys.stderr,
            )

    # ── Build unified SLA records ──────────────────────────────────────────────
    if dagster_available and run_records:
        sla_records = compute_sla(run_records, first_pitch_times, pred_timing, SLA_LEAD_MINUTES)
    else:
        print("Building Snowflake-only SLA records …", file=sys.stderr)
        sla_records = build_snowflake_only_records(first_pitch_times, pred_timing, args.days)

    # Deduplicate: keep one record per run_date (most recent run if multiple)
    _EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)
    seen_dates: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in sorted(sla_records, key=lambda x: (x["run_date"], x.get("job_start_utc") or _EPOCH_MIN), reverse=True):
        if r["run_date"] not in seen_dates:
            deduped.append(r)
            seen_dates.add(r["run_date"])
    sla_records = sorted(deduped, key=lambda x: x["run_date"])

    # ── Analysis ───────────────────────────────────────────────────────────────
    op_summary = build_op_duration_summary(run_records) if dagster_available else []
    failure_modes = identify_failure_modes(sla_records)

    # ── Render & write report ──────────────────────────────────────────────────
    report = render_report(sla_records, op_summary, failure_modes, args.days, dagster_available, run_ts)

    # Destination: "-" → stdout (no file; ideal on the container — its FS is ephemeral);
    # "s3://bucket/key" → durable S3; else a local path (dev default).
    dest = args.output
    if dest == "-":
        print(report)
    elif dest.startswith("s3://"):
        import boto3
        bucket, key = dest[5:].split("/", 1)
        boto3.client("s3").put_object(
            Bucket=bucket, Key=key, Body=report.encode("utf-8"),
            ContentType="text/markdown")
        print(f"\nReport written to: {dest}", file=sys.stderr)
    else:
        out_path = Path(dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\nReport written to: {out_path}", file=sys.stderr)

    # Print quick summary to stdout
    with_sla = [r for r in sla_records if r.get("sla_met") is not None]
    n_pass = sum(1 for r in with_sla if r["sla_met"])
    n_fail = len(with_sla) - n_pass
    no_postlineup = sum(1 for r in sla_records if not r.get("has_post_lineup"))

    print(f"\n{'='*60}")
    print(f"  SLA compliance: {n_pass}/{len(with_sla)} days ({100*n_pass/len(with_sla):.0f}%)")
    print(f"  SLA failures:   {n_fail} day(s)")
    print(f"  No post-lineup: {no_postlineup} day(s)")
    print(f"  Failure modes:  {len(failure_modes)} identified")
    print(f"{'='*60}")
    if failure_modes:
        print(f"\n  Top failure modes:")
        for fm in sorted(failure_modes, key=lambda x: -x["occurrences"])[:3]:
            print(f"    {fm['id']} — {fm['name']} ({fm['occurrences']} occurrences)")
    print()


if __name__ == "__main__":
    main()

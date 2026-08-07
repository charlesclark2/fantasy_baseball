"""INC-41 — the OFF-CYCLE serving-artifact freshness job.

WHY A SECOND, OFF-CYCLE RUNNER (and not just the daily-job fan-out).
    INC-41's freeze was INTRADAY: `stg_statsapi_lineups_wide` stopped advancing at 20:08Z, hours
    after the 12:00 UTC daily job had finished green. A check that only runs inside the daily job
    could not have caught it before the next morning — by which time the slate is over and the
    three unscored games are permanently unscored. The daily fan-out
    (`check_artifact_freshness_op`) guards the build the daily job itself performs; THIS job is
    what closes the window BETWEEN daily runs.

    It is deliberately dependency-free: it reads S3 and pages, nothing more. That is what lets it
    run on the writer's own cadence without touching the serving path.

Snowflake-FREE by construction (DuckDB over S3), so it can tick every 30 minutes without waking
    COMPUTE_WH — which matters while the E11.24 wake/idle cost soak is live.
"""

from dagster import job

from pipeline.ops.daily_ingestion_ops import artifact_freshness_standalone_op


@job(
    name="artifact_freshness_job",
    description=(
        "INC-41: assert every registered serving-critical parquet has advanced within its "
        "declared freshness SLA (content timestamp inside the data, off-hours aware). "
        "ALERT-tier — pages via send_alert, never HALTs."
    ),
    tags={"tier": "alert", "snowflake_free": "true"},
)
def artifact_freshness_job():
    artifact_freshness_standalone_op()

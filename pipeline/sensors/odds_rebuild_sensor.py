"""odds_rebuild_sensor — Story 12.3.7 / A2.18.

The live Odds API capture runs on a Railway cron container (off the Dagster+ run-minute
bill) and appends to `baseball_data.oddsapi.mlb_odds_raw`. This sensor watches that table
and fires `odds_oddsapi_rebuild_job` ONLY when a new capture lands — so Dagster pays for the
(quick) warehouse dbt rebuild, never the I/O-bound HTTP poll. Cursor = the latest
`ingestion_ts` seen; `run_key` = that timestamp, so duplicate ticks dedupe to one run.
"""
import os

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

from pipeline.jobs.intraday_jobs import odds_oddsapi_rebuild_job

_MAX_TS_SQL = "SELECT MAX(ingestion_ts) FROM baseball_data.oddsapi.mlb_odds_raw"


def _latest_ingestion_ts() -> str | None:
    """Return the max ingestion_ts in mlb_odds_raw as an ISO string (key-pair auth)."""
    import snowflake.connector
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, load_pem_private_key,
    )

    with open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"], "rb") as f:
        key = load_pem_private_key(f.read(), password=None, backend=default_backend())
    pk = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role=os.environ.get("SNOWFLAKE_ROLE", ""),
        database="baseball_data",
        private_key=pk,
    )
    try:
        cur = conn.cursor()
        cur.execute(_MAX_TS_SQL)
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return row[0].isoformat() if row and row[0] is not None else None


@sensor(job=odds_oddsapi_rebuild_job, minimum_interval_seconds=300)
def odds_rebuild_sensor(context: SensorEvaluationContext):
    """Fire the Odds-API dbt rebuild when the Railway capture appends new rows.

    Transient Snowflake errors → SkipReason (don't cascade a flaky connection into a
    failed sensor tick), matching pregame_snapshot_sensor.
    """
    try:
        latest = _latest_ingestion_ts()
    except Exception as exc:  # noqa: BLE001 — transient infra; skip, retry next tick
        yield SkipReason(f"Could not read mlb_odds_raw max ingestion_ts: {exc}")
        return

    if latest is None:
        yield SkipReason("mlb_odds_raw is empty — nothing to rebuild.")
        return

    if context.cursor == latest:
        yield SkipReason(f"No new Odds-API capture since {latest}.")
        return

    context.update_cursor(latest)
    yield RunRequest(run_key=latest, tags={"odds_capture_ts": latest})

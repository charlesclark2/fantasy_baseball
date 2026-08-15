from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    ingest_player_profiles_update,
    reexport_player_profiles_op,
)


@job(executor_def=in_process_executor)
def weekly_player_profiles_job():
    profiles = ingest_player_profiles_update()
    # 🩸 E11.24 Bundle (2026-08-14) — the S3 player_profiles_raw mirror had NO scheduled writer at
    # all: ingest_player_profiles.py writes only Snowflake, and the mirror's sole writer
    # (export_w4_raw_to_s3.py) is a hand-run W4 build precursor. It had frozen at 2026-06-28,
    # ~47 days (~1,133h) against this table's own 192h freshness threshold, and nothing loud read
    # it — the duckdb branch of stg_statsapi_player_profiles just silently omits recent call-ups.
    # A FAN-OUT LEAF: nothing consumes its output, so a mirror failure can never fail the weekly
    # ingest. It pages instead (ALERT tier). This is the ONLY job that runs the writer, so it is
    # the whole INC-38 caller set — pinned by test_e11_24_bundle_freshness_reexports.py.
    reexport_player_profiles_op(start=profiles)

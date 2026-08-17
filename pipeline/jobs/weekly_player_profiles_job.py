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
    # ⛔ E5.10 follow-up — build_ref_players_dimension_op is DELIBERATELY NOT wired here, and the
    # reason is worth recording because chaining it off the mirror is the obvious thing to do.
    # The dimension builder reads the S3 player_profiles_raw mirror this job refreshes, so INC-25
    # would want it strictly downstream of that leaf — but binding the leaf's output destroys the
    # property test_the_reexport_is_a_fan_out_leaf defends: an unbound leaf structurally cannot
    # withhold anything chained behind it. Wiring it upstream instead would leave the two ops
    # unordered relative to each other under a topological executor, which is the INC-25 hazard.
    # Neither option is acceptable, and neither is needed: the builder runs as a leaf of the DAILY
    # job, which fires ~2h after this one on the same day, so the freshest mirror reaches the
    # dimension within hours and every other day of the week the daily pass is the only cadence
    # that matters anyway (mlb_played_first/last track nightly Statcast appearances, not the
    # weekly profile refresh). Keeping this job a two-op chain preserves the leaf invariant.

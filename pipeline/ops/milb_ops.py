"""E7.1 — MiLB incremental ingest op (WARN-tier, ISOLATED from MLB serving).

Keeps the MiLB Delta lakehouse (baseball/milb/{schedule,player_game_logs}) fresh after the
one-time 2005→2026 backfill: a daily re-pull of the CURRENT month (+ the prior month in the
first 3 days of a month) so overnight finals + late box revisions land. `--incremental`
re-pulls those month partitions idempotently (delete-then-write per (season, sport_id, month)).

TIER = WARN-but-continue (E11.7 / CLAUDE.md op-tier map): MiLB data is NOT on any MLB
serving/predict path — it is the research substrate for E7.3 (MLE) + E8 (Dynasty). A Stats-API
hiccup, an S3 blip, or an empty-slate day must degrade QUIETLY (log a WARNING, op succeeds) and
never affect anything MLB-serving. This op lives in its OWN job (milb_ingest_job) so a failure
fails only its own isolated run, mirroring the sport-vertical isolation (sport_data_platform.md).

INC-32 discipline: the subprocess carries a finite wall-clock timeout so a stalled S3/httpfs read
can never wedge the Dagster worker (an un-timed subprocess on a daemon path is the INC-32 class).
"""
import os

from dagster import Nothing, Out, op

from pipeline.ops.daily_ingestion_ops import _run_script

# A current-month re-pull is ~1–2k free Stats-API boxscore calls (~8 min mid-season); give it a
# generous ceiling so a genuinely-hung read fails LOUD instead of hanging the worker forever.
MILB_INGEST_TIMEOUT_SECONDS = int(os.environ.get("MILB_INGEST_TIMEOUT_SECONDS", "3600"))


@op(out=Out(Nothing))
def milb_incremental_ingest_op(context):
    """Daily MiLB incremental refresh (WARN-tier — never raises into the run)."""
    try:
        _run_script(
            context,
            "ingest_milb_to_s3.py",
            ["--incremental"],
            timeout=MILB_INGEST_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001 — WARN-tier: MiLB is off the MLB serving path
        context.log.warning(
            f"MiLB incremental ingest failed (non-fatal — MiLB data is research-only, off the "
            f"MLB serving path; the next daily run re-pulls the same month idempotently): {e}"
        )

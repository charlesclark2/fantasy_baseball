"""E7.1/E7.2 — MiLB incremental ingest ops (WARN-tier, ISOLATED from MLB serving).

Keeps the MiLB Delta lakehouse fresh after the one-time backfills: a daily re-pull of the
CURRENT month (+ the prior month in the first 3 days of a month) so overnight finals + late
revisions land. `--incremental` re-pulls those month partitions idempotently.

  • milb_incremental_ingest_op   → baseball/milb/{schedule,player_game_logs}      (E7.1)
  • statcast_aaa_incremental_ingest_op → baseball/milb/statcast_aaa (AAA, Hawk-Eye)  (E7.2)
  • fangraphs_prospects_ingest_op → baseball/milb/the_board (FanGraphs THE BOARD)   (E7.7)
  • fangraphs_milb_leaderboards_ingest_op → baseball/milb/fg_leaderboards (all minors) (E7.7)

TIER = WARN-but-continue (E11.7 / CLAUDE.md op-tier map): MiLB data is NOT on any MLB
serving/predict path — it is the research substrate for E7.3 (MLE) + E8 (Dynasty). A Stats-API
hiccup, an S3 blip, or an empty-slate day must degrade QUIETLY (log a WARNING, op succeeds) and
never affect anything MLB-serving. Both ops live in the SAME isolated job (milb_ingest_job) —
each catches its own exceptions internally, so one script's failure never blocks the other or
fails the run; a wholly separate job/schedule per script would just duplicate scaffolding for
what is operationally one "keep MiLB data topped up" duty, mirroring the sport-vertical
isolation (sport_data_platform.md) without multiplying it.

INC-32 discipline: every subprocess carries a finite wall-clock timeout so a stalled S3/httpfs
read can never wedge the Dagster worker (an un-timed subprocess on a daemon path is the INC-32
class).
"""
import os

from dagster import Nothing, Out, op

from pipeline.ops.daily_ingestion_ops import _run_script

# A current-month re-pull is ~1–2k free Stats-API boxscore calls (~8 min mid-season); give it a
# generous ceiling so a genuinely-hung read fails LOUD instead of hanging the worker forever.
MILB_INGEST_TIMEOUT_SECONDS = int(os.environ.get("MILB_INGEST_TIMEOUT_SECONDS", "3600"))

# The AAA Statcast incremental (2 Savant requests/month: batter + pitcher) is far cheaper than
# the boxscore-per-game MiLB pull above, but still gets a generous ceiling per INC-32 discipline.
STATCAST_AAA_INGEST_TIMEOUT_SECONDS = int(
    os.environ.get("STATCAST_AAA_INGEST_TIMEOUT_SECONDS", "900")
)

# The FanGraphs prospect board is ONE FlareSolverr-routed request (~1,300 rows). A generous
# ceiling (default 300s) covers a slow Cloudflare solve + origin compute; INC-32 discipline.
FANGRAPHS_PROSPECTS_TIMEOUT_SECONDS = int(
    os.environ.get("FANGRAPHS_PROSPECTS_TIMEOUT_SECONDS", "300")
)

# The MiLB leaderboards are two paginated FlareSolverr-routed pulls (bat + pit, ~thousands of
# minor leaguers each). A generous ceiling covers the multi-page solves; INC-32 discipline.
FANGRAPHS_MILB_LEADERBOARDS_TIMEOUT_SECONDS = int(
    os.environ.get("FANGRAPHS_MILB_LEADERBOARDS_TIMEOUT_SECONDS", "900")
)


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


@op(out=Out(Nothing))
def statcast_aaa_incremental_ingest_op(context):
    """Daily AAA Statcast incremental refresh (WARN-tier — never raises into the run)."""
    try:
        _run_script(
            context,
            "ingest_statcast_aaa_to_s3.py",
            ["--incremental"],
            timeout=STATCAST_AAA_INGEST_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001 — WARN-tier: MiLB is off the MLB serving path
        context.log.warning(
            f"AAA Statcast incremental ingest failed (non-fatal — research-only, off the MLB "
            f"serving path; the next daily run re-pulls the same month idempotently): {e}"
        )


@op(out=Out(Nothing))
def fangraphs_prospects_ingest_op(context):
    """Daily FanGraphs THE BOARD snapshot → baseball/milb/the_board (E7.7).

    WARN-tier: prospect data is research substrate for E7.4/E7.8 + the E8.0 draft board, NOT on
    any MLB serving/predict path. A Cloudflare block, an unset FLARESOLVERR_URL, or an S3 blip
    must degrade QUIETLY (log a WARNING, op succeeds) — the write is idempotent per
    (season, as_of_date), so the next daily run re-snaps cleanly. Snowflake-FREE."""
    try:
        _run_script(
            context,
            "ingest_fangraphs_prospects_to_s3.py",
            [],  # defaults: --season <current year>, --as-of <today>
            timeout=FANGRAPHS_PROSPECTS_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001 — WARN-tier: prospect data is off the MLB serving path
        context.log.warning(
            f"FanGraphs prospect board ingest failed (non-fatal — research-only, off the MLB "
            f"serving path; needs FLARESOLVERR_URL on the box, and the next daily run re-snaps "
            f"idempotently per as_of_date): {e}"
        )


@op(out=Out(Nothing))
def fangraphs_milb_leaderboards_ingest_op(context):
    """Daily FanGraphs MiLB leaderboards (bat + pit) → baseball/milb/fg_leaderboards (E7.7).

    WARN-tier: this is the `fg_minor_id` POPULATION feed (every minor leaguer, ranked or not —
    the coverage THE BOARD's graded-only list can't give) for E7.4/E8.0. Off the MLB
    serving/predict path; a Cloudflare block, unset FLARESOLVERR_URL, or S3 blip must degrade
    QUIETLY (log a WARNING, op succeeds); the write is idempotent per (season, stats, as_of_date).
    Snowflake-FREE."""
    try:
        _run_script(
            context,
            "ingest_fangraphs_milb_leaderboards_to_s3.py",
            [],  # defaults: --season <current year>, --stats bat,pit, --as-of <today>
            timeout=FANGRAPHS_MILB_LEADERBOARDS_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001 — WARN-tier: prospect data is off the MLB serving path
        context.log.warning(
            f"FanGraphs MiLB leaderboard ingest failed (non-fatal — research-only, off the MLB "
            f"serving path; needs FLARESOLVERR_URL on the box, and the next daily run re-snaps "
            f"idempotently per (season, stats, as_of_date)): {e}"
        )

"""NCAAF-P0.7 — the PRE-SEASON season-roll-forward schedule.

A weekly PRE-SEASON refresh of the upcoming season's schedule + covariates so the P1.5 futures
board + the live P1.4 board can RUN before kickoff. Fires the `sports_ncaaf_roll_forward_job`
(ingest → mart rebuild) on a clock-derived `current_season()` — the exact same schedule lands 2027
next August with no code change (the annual cadence; NEVER pin the season — the P0.6 landmine).

⏰ WINDOW: weekly Mondays, FEBRUARY–AUGUST. That is the pre-season churn window — CFBD publishes /
moves games and fills covariates (returning production, talent, coaches, roster) on a rolling basis
from late winter through fall camp (verified 2026-07-24: half the covariates were still unpublished
in July). Once the season opens (Sep+), the game-day `sports_ncaaf_dbt_schedule` takes over the
mart rebuilds off real game data, so the roll-forward pull stops for the season and resumes the next
February for the following season.

⛔ SHIPS `default_status=STOPPED` — the SAME operator-gated exception the sports dbt schedules take
(E11.23 carves out operator-gated schedules that need a prereq / can spend an external budget): this
job calls CFBD (needs `CFBD_API_KEY` on the box) and there is nothing to roll forward until an
operator has verified the upcoming season's CFBD availability + provisioned the key. The cost of
STOPPED is the "silently never runs" class, so the intended state is recorded in
`BOX_OPERATIONS.md §10` and the P0.7 handoff makes ENABLING THIS the launch-critical action —
turn it ON in Dagit well before the Aug-29 opener.

Cron 06:00 America/Los_Angeles Monday, Feb–Aug: a quiet-hours weekly pull; ~8 cheap CFBD calls.

═══════════════════════════════════════════════════════════════════════════════════════════════
NF-D1 — the NFL season roll-forward schedule (below): a weekly refresh of rosters/schedule/
depth_charts/injuries/rookie-class so MVP-1's fantasy board can sharpen off REAL 2026 data.
Fires `sports_nfl_roll_forward_job` (ingest → mart rebuild) on a clock-derived `current_season()`
— same annual-cadence pattern as NCAAF's, re-runnable next spring with no code change.

⏰ WINDOW (widened by NF-FRESH2 P0, 2026-08-15): weekly Mondays, MARCH → the following FEBRUARY —
one full NFL season cycle: free agency (mid-March) → the draft (April) → OTAs/camp/roster cuts
(Aug) → the regular season and playoffs (Sep–Feb). It USED to be March–August, which meant every
NFL raw feed froze on 09-01 — through the opener and the entire season. UNLIKE NCAAF, nflverse
needs no API key, so the only reason this ships STOPPED is the shared
`sports_nfl_dbt_build_job`/`sports_nfl_dbt_schedule` box-readiness gate (dbt-duckdb + S3
instance-role read) the rebuild step depends on — see `BOX_OPERATIONS.md §10`.

⭐ WHY RUNNING IT IN-SEASON IS SAFE (audited before the widening, NF-FRESH2 P0): nothing in the
repo assumes these raw feeds are quiet in-season. The raw tier is a LATEST-SNAPSHOT tier by
construction (`replaceWhere season=YYYY` — an idempotent full-season overwrite), which is exactly
WHY the NF-W0a point-in-time capture (`sports_nfl_pit_*_job`) exists and writes to its OWN store
with its OWN `capture_timestamp`; a raw overwrite cannot damage PIT fidelity. The one prose claim
that the pull "stops for the season" belongs to the NCAAF schedule above, whose game-day
`sports_ncaaf_dbt_schedule` genuinely takes over — the NFL analog does NOT, because the NFL
game-day schedule rebuilds MARTS and ingests NOTHING. Clock-wise the three NFL crons stay
disjoint (roll-forward 06:15 Mon, Sleeper 06:30 daily, the game-day mart rebuild 11:00 daily), so
widening the window introduces no new concurrent-dbt writer.

═══════════════════════════════════════════════════════════════════════════════════════════════
NF-D5 — the Sleeper forward-availability schedule (below): a DAILY (not weekly — the story's
"cheap daily through camp" cadence) refresh of Sleeper's `v1/players/nfl` snapshot, continuing
NF-D2 slice 5's roster-status unavailability flag with an earlier, offseason-covering source. Fires
`sports_nfl_sleeper_injuries_job` (ingest → refresh just the sleeper-injuries staging model) —
WARN-tier throughout, advisory/non-serving (see the job's own docstring).

⏰ WINDOW (widened by NF-FRESH2 P0): daily, MARCH → the following FEBRUARY — the same full-season
cycle as NF-D1's roll-forward. It used to be March–August; availability designations churn
HARDEST in-season, so the old window excluded exactly the months this feed is most useful.

🚨 THE NF-FRESH1 BREAK (2026-08-15) — widening the window did NOT fix it: `sports_nfl_sleeper_
injuries_job`'s ingest op died at `duckdb.connect(read_only=True)` in ~114ms on the box (the sports
DuckDB is gitignored, so it was absent from the `COPY . .` image) and its bare `except` returned
SUCCESS — 19 consecutive green runs that wrote nothing. NF-INFRA1 (same day) fixed it: the file now
lives on the `sports_duckdb` named volume at one authoritative `SPORTS_DUCKDB_PATH`, and the ingest
op pages+raises instead of swallowing. The operator confirmed this schedule RUNNING on the box.

⭐ NF-INFRA1 FOLLOW-UP (2026-08-15): ships `default_status=RUNNING` and joined
`check_monitors_healthy_op`'s required-RUNNING set
(`betting_ml.monitoring.monitor_health.CRITICAL_SCHEDULES`). It used to ship STOPPED (an
operator-gated exception shared with NF-D1, on the theory the staging-model refresh needed the
`sports_nfl_dbt_build_job` box-readiness prereq) and its ON state lived ONLY in the Dagster
Postgres from the operator's manual toggle — so a volume reset / box re-host would have silently
reverted it to STOPPED with nothing paging, the exact "silently never runs" class (the INC-16
default-status-revert + E11.23 family) this flip + the heartbeat entry close.

═══════════════════════════════════════════════════════════════════════════════════════════════
NF-FRESH2 — the draft-board publish schedule (below): the cadence that makes the SERVED board
move. See `pipeline/jobs/sports_nfl_board_publish_job.py` for the ordering rationale (INC-25).

⭐ NF-INFRA1 FOLLOW-UP (2026-08-15): ships `default_status=RUNNING` and joined
`check_monitors_healthy_op`'s required-RUNNING set. NF-INFRA1 turned it ON in Dagit once the
`sports_duckdb` volume prereq was materialized, but that ON state lived only in the Dagster
Postgres; this flip + the heartbeat entry are the belt-and-suspenders cure — the exact
silent-board-freeze failure this whole schedule exists to prevent, one level up.
"""

from datetime import date

from dagster import (
    DefaultScheduleStatus,
    RunRequest,
    ScheduleEvaluationContext,
    SkipReason,
    schedule,
)

from pipeline.jobs.sports_ncaaf_rollforward_job import sports_ncaaf_roll_forward_job
from pipeline.jobs.sports_nfl_board_publish_job import sports_nfl_board_publish_job
from pipeline.jobs.sports_nfl_rollforward_job import sports_nfl_roll_forward_job
from pipeline.jobs.sports_nfl_sleeper_injuries_job import sports_nfl_sleeper_injuries_job

# Weekly Monday 06:00 PT, months February–August (the pre-season roll-forward window).
NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"
# Weekly Monday 06:15 PT (offset from the NCAAF pull), months March → the following February —
# i.e. ONE FULL NFL SEASON CYCLE, free agency (Mar) through the Super Bowl (Feb).
# ⚠️ NF-FRESH2 P0 — this used to be `3-8` (March–August) and that was a SEASONAL BOUNDARY HOLE of
# exactly the E9.48(c) / INC-37 class: on 09-01 every NFL raw feed (rosters, weekly_rosters,
# depth_charts, injuries, schedules) would have STOPPED advancing — through the 2026-09-09 opener
# and the whole season — while the Sep–Feb `sports_nfl_dbt_schedule` kept rebuilding MARTS over
# frozen raw, and the nflverse `injuries` report (in-season-only upstream, so it FIRST PUBLISHES
# in September) would never have been ingested at all. A month-range cron is a seasonal hole;
# grep a schedule's month range before trusting it covers the season you need.
NFL_ROLL_FORWARD_CRON = "15 6 * 3-12,1-2 1"
# Daily 06:30 PT (offset from the weekly NFL pull), same March → February season cycle — the
# NF-D5 cheap daily forward-availability capture (one unauthenticated HTTP GET + a single-model
# dbt rebuild). Same NF-FRESH2 P0 widening, same reason: IR/PUP/practice designations churn
# HARDEST in-season, which is precisely the window the old `3-8` window excluded.
NFL_SLEEPER_INJURIES_CRON = "30 6 * 3-12,1-2 *"


@schedule(
    job=sports_ncaaf_roll_forward_job,
    cron_schedule=NCAAF_ROLL_FORWARD_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_roll_forward_schedule(context: ScheduleEvaluationContext):
    """Weekly pre-season refresh of the upcoming season's schedule + covariates."""
    context.log.info(
        "[ncaaf roll-forward] firing pre-season schedule + covariate refresh for the "
        "clock-derived current_season()")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "roll_forward"})


@schedule(
    job=sports_nfl_roll_forward_job,
    cron_schedule=NFL_ROLL_FORWARD_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_nfl_roll_forward_schedule(context: ScheduleEvaluationContext):
    """Weekly refresh of the upcoming NFL season's rosters/schedule/depth_charts/injuries/rookie
    class."""
    context.log.info(
        "[nfl roll-forward] firing season roster/schedule/depth_chart/injuries/draft/combine "
        "refresh for the clock-derived current_season()")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "roll_forward"})


@schedule(
    job=sports_nfl_sleeper_injuries_job,
    cron_schedule=NFL_SLEEPER_INJURIES_CRON,
    execution_timezone="America/Los_Angeles",
    # NF-INFRA1 follow-up (2026-08-15): self-starts + heartbeat-checked — see module docstring.
    default_status=DefaultScheduleStatus.RUNNING,
)
def sports_nfl_sleeper_injuries_schedule(context: ScheduleEvaluationContext):
    """Daily (through camp) refresh of Sleeper's forward-availability snapshot (NF-D5)."""
    context.log.info(
        "[nfl sleeper-injuries] firing daily forward-availability capture")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "sleeper_injuries"})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-FRESH2 P2 — the draft-board publish cadence
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Daily 07:15 PT, EVERY MONTH. The hour is deliberate: it sits AFTER the 06:15 weekly roll-forward
# and the 06:30 daily Sleeper capture, so on a Monday the board is published downstream of both.
# ⚠️ That offset is a courtesy, NOT the ordering guarantee — the guarantee is the graph edge inside
# `sports_nfl_board_publish_job` (its own daily depth-chart/roster ingest runs upstream of the
# publish op, in the same run). INC-25 was learned the hard way: an ordering that lives only in two
# crons is one slow ingest away from publishing a board built before its own inputs landed.
#
# ⛔ NO MONTH RANGE. Every other NFL schedule in this file carries one, and P0 in this same story
# had to widen two of them after a `3-8` window would have frozen the whole vertical on 09-01. A
# publish cadence has no reason to have a seasonal cliff at all, so it does not get one.
NFL_BOARD_PUBLISH_CRON = "15 7 * * *"


def is_draft_season(today: date) -> bool:
    """August 1 → September 15: the window in which fantasy drafts actually happen.

    Clock-derived and injectable, never a pinned year — the NCAAF-P0.6 stale-by-a-season landmine
    that `current_season()` exists to avoid, applied to a cadence instead of a season. The end
    bound reaches past the ~Sep-9 opener because leagues keep drafting through week 1.

    The window is intentionally GENEROUS at both ends. Being wrong toward "daily" costs one cheap
    rebuild; being wrong toward "weekly" costs a drafting user a board built on a market up to six
    days old, which is the entire defect this story exists to fix."""
    return today.month == 8 or (today.month == 9 and today.day <= 15)


@schedule(
    job=sports_nfl_board_publish_job,
    cron_schedule=NFL_BOARD_PUBLISH_CRON,
    execution_timezone="America/Los_Angeles",
    # NF-INFRA1 follow-up (2026-08-15): self-starts + heartbeat-checked — see below.
    default_status=DefaultScheduleStatus.RUNNING,
)
def sports_nfl_board_publish_schedule(context: ScheduleEvaluationContext):
    """DAILY through draft season, WEEKLY (Mondays) the rest of the year.

    ⭐ ONE SCHEDULE, NOT TWO. The obvious alternative — a daily cron for Aug–Sep beside a weekly one
    for the rest — gives one logical job two execution owners that OVERLAP in exactly the window
    that matters, i.e. a double publish every August day. That is the INC-30 (crontab under two
    users) / INC-36 (two concurrent deploys) / INC-38 (a flag on one caller of four) shape this repo
    keeps paying for. A single owner that decides its own cadence cannot collide with itself.

    ⭐ Ships `default_status=RUNNING` (NF-INFRA1 follow-up, 2026-08-15): it used to ship STOPPED,
    and unlike its siblings that was NOT merely convention — the job's build chain needs the box's
    sports DuckDB, which is gitignored and absent from the image until `sports_nfl_dbt_build_job`
    has materialized it. Enabling this before that prereq holds produces a daily CRITICAL page (by
    design — the publish op refuses to report success on a run that published nothing). NF-INFRA1
    landed the prereq (the `sports_duckdb` named volume) and the operator confirmed it materialized
    + toggled this ON in Dagit — but that ON state lived ONLY in the Dagster Postgres, so a volume
    reset / box re-host would have silently reverted it to STOPPED (the board freezes) with nothing
    paging. This flip + the `check_monitors_healthy_op` required-RUNNING entry are the structural
    cure. The intended state belongs in `BOX_OPERATIONS.md §10`.
    """
    today = context.scheduled_execution_time.date()
    if is_draft_season(today):
        context.log.info("[nfl board publish] draft season (%s) — publishing daily", today)
    elif today.weekday() == 0:
        context.log.info("[nfl board publish] out of draft season (%s) — the Monday publish", today)
    else:
        return SkipReason(
            f"{today} is outside draft season (Aug 1 – Sep 15) and is not a Monday — the board "
            "publishes weekly off-season. The previously published board keeps serving.")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "board_publish"})

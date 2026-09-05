"""NCAAF-P0.7 — the PRE-SEASON season-roll-forward schedule.

A weekly PRE-SEASON refresh of the upcoming season's schedule + covariates so the P1.5 futures
board + the live P1.4 board can RUN before kickoff. Fires the `sports_ncaaf_roll_forward_job`
(ingest → mart rebuild) on a clock-derived `current_season()` — the exact same schedule lands 2027
next August with no code change (the annual cadence; NEVER pin the season — the P0.6 landmine).

⏰ WINDOW (widened by NCAAF-RF1, 2026-08-24): weekly Mondays, FEBRUARY → the following JANUARY —
one full NCAAF season cycle. Feb–Aug is the pre-season churn window (CFBD publishes / moves games
and fills covariates — returning production, talent, coaches, roster — on a rolling basis from late
winter through fall camp; verified 2026-07-24: half the covariates were still unpublished in July),
and Sep–Jan carries that same refresh through the regular season, bowls and the CFP.

It USED to be FEBRUARY–AUGUST, on the reasoning that once the season opens the game-day
`sports_ncaaf_dbt_schedule` takes over the mart rebuilds off real game data. That is true of the
REBUILD and false of the INGEST: the game-day schedule rebuilds MARTS and ingests NOTHING, so under
the old window every roll-forward feed would have frozen after Mon 2026-08-31 until February 2027.
See the ⚠️ NCAAF-RF1 note at `NCAAF_ROLL_FORWARD_CRON` for the leg that made that bite (`talent`)
and for the in-season-safety audit.

⛔ SHIPS `default_status=STOPPED` — the SAME operator-gated exception the sports dbt schedules take
(E11.23 carves out operator-gated schedules that need a prereq / can spend an external budget): this
job calls CFBD (needs `CFBD_API_KEY` on the box) and there is nothing to roll forward until an
operator has verified the upcoming season's CFBD availability + provisioned the key. The cost of
STOPPED is the "silently never runs" class, so the intended state is recorded in
`BOX_OPERATIONS.md §10` and the P0.7 handoff makes ENABLING THIS the launch-critical action —
turn it ON in Dagit well before the Aug-29 opener.

Cron 06:00 America/Los_Angeles Monday, Feb → the following Jan: a quiet-hours weekly pull;
~8 cheap CFBD calls.

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


from dagster import (
    DefaultScheduleStatus,
    RunRequest,
    ScheduleEvaluationContext,
    SkipReason,
    schedule,
)

from pipeline.jobs.sports_ncaaf_rollforward_job import sports_ncaaf_roll_forward_job
from betting_ml.monitoring.nfl_board_freshness import is_draft_season
from pipeline.jobs.sports_nfl_board_publish_job import sports_nfl_board_publish_job
from pipeline.jobs.sports_nfl_weekly_serving_job import sports_nfl_weekly_serving_job
from pipeline.jobs.sports_nfl_rollforward_job import sports_nfl_roll_forward_job
from pipeline.jobs.sports_nfl_sleeper_injuries_job import sports_nfl_sleeper_injuries_job

# Weekly Monday 06:00 PT, months February → the following January — i.e. ONE FULL NCAAF SEASON
# CYCLE, pre-season churn (Feb–Aug) straight through the regular season, bowls and the CFP
# (Sep–Jan). The `2-12,1` form is the Aug–Jan convention every other NCAAF schedule in this repo
# writes (`NCAAF_CRON = "0 11 * 8-12,1 *"`), rotated to this cadence's own start month.
# ⚠️ NCAAF-RF1 (2026-08-24) — this used to be `2-8` (Feb–August) and that was a SEASONAL BOUNDARY
# HOLE of exactly the E9.48(c) / INC-37 month-scoped-cron class, caught BEFORE it fired: the last
# fire under the old window was Mon 2026-08-31, after which every roll-forward feed would have
# STOPPED advancing until February 2027 — through the whole season. The leg that made it bite is
# `talent`: it is in `ROLL_FORWARD_SOURCES` and is an honest upstream absence today (verified live
# 2026-08-24: CFBD `/talent?year=2026` → HTTP 200 with 0 rows, while 2024/2025 return 134 each),
# so if CFBD publishes 2026 talent in September NOTHING would have ingested it all season — and
# because the NCAAF-PS pre-kickoff snapshots are IMMUTABLE, the forward track record would have
# been permanently talent-free. A month-range cron is a seasonal hole; grep a schedule's month
# range before trusting it covers the season you need.
# ⭐ WHY RUNNING IT IN-SEASON IS SAFE (audited, NCAAF-RF1 — the same audit NF-FRESH2 P0 ran for
# the NFL analog): the raw tier is a LATEST-SNAPSHOT tier by construction — `run_roll_forward`
# does NOT pass `skip_existing`, so every fire is a value-identical `replaceWhere season = YYYY`
# partition overwrite (`s3io.write_season_partition`), and a source CFBD has not published lands
# 0 records, which `s3io.write_records` SKIPS outright rather than overwriting a good partition
# with an empty one. So an in-season fire on already-ingested sources is a clean no-op-in-effect,
# and the talent leg starts landing rows the first Monday after CFBD publishes them.
NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-12,1 1"
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


# ⭐ NF-INFRA2 — `is_draft_season` now lives in `betting_ml.monitoring.nfl_board_freshness`, which
# is the ONE owner of this cadence. It is re-exported here unchanged so every existing caller and
# guard is untouched. WHY IT MOVED: the published-board freshness SLA has to know which cadence
# governs the board it is judging, and an SLA pinned separately from the cadence it judges is the
# "one logical thing, many owners" shape (INC-30/INC-36/INC-38) — it would false-page every
# off-season Tuesday the moment either side changed. The monitor cannot import `pipeline` (E11.23:
# the fast gate would break), so the shared predicate lives on the `betting_ml` side and the
# schedule reads it, not the other way round.


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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-C6-PH2 — the WEEKLY serving build
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# 08:30 PT daily, 45 minutes after the board publish. The offset is a COURTESY and not an ordering
# guarantee — the two jobs share no artifact, so there is nothing here for a cron offset to lose
# (INC-25 is about a consumer racing its own producer, which this is not). It simply keeps two
# lightgbm builds off the box's two vCPUs at the same moment.
#
# ⛔ SHIPS STOPPED, AND THAT IS THIS STORY'S DEPLOY-HELD POSTURE RATHER THAN AN OVERSIGHT. Enabling
# it is an OPERATOR step taken after the gateway routes exist and `deploy.sh` has shipped the
# backend — a schedule that starts publishing weekly blobs to an api-cache no route can read would
# be spending box CPU on an artifact nobody can fetch.
#
# ⚠️ NF-INFRA1's WARNING APPLIES THE MOMENT IT IS TURNED ON: a schedule toggled ON in Dagit holds
# that state ONLY in the Dagster Postgres, so a volume reset or a box re-host silently reverts it to
# STOPPED and the weekly artifact freezes with nothing paging. When the operator enables this, it
# belongs in `BOX_OPERATIONS.md §10` and in `check_monitors_healthy_op`'s required-RUNNING set in the
# same change — otherwise the cure for a silent freeze is itself silently revertible.
NFL_WEEKLY_SERVING_CRON = "30 8 * * *"


@schedule(
    job=sports_nfl_weekly_serving_job,
    cron_schedule=NFL_WEEKLY_SERVING_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,
)
def sports_nfl_weekly_serving_schedule(context: ScheduleEvaluationContext):
    """Daily in-season rebuild of the next unplayed week's projection.

    DAILY rather than weekly even though the TARGET week changes once a week: the inputs (rosters,
    depth charts, snaps, the injury feed) move every day, and a Tuesday build is what carries a
    Monday-night result into Sunday's projection. The builder resolves its own target week from the
    published schedule, so a rebuild on a day when nothing changed is idempotent rather than wrong.

    ⭐ IT DOES NOT SELF-SKIP OUT OF SEASON, and that is deliberate. `resolve_target_week` RAISES
    when no REG week is upcoming, which fails the run loudly instead of publishing a projection for
    a season that is over — the same fail-closed shape as the rest of this path. A skip predicate
    here would be a second owner of "is there a week to project", and the builder already answers
    that from the schedule itself (the INC-30/36/38 one-logical-thing-many-owners shape).
    """
    context.log.info("[nfl weekly] building the next unplayed week (%s)",
                     context.scheduled_execution_time.date())
    return {}

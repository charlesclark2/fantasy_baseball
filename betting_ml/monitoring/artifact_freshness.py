"""artifact_freshness.py — per-artifact freshness SLAs on serving-critical parquet (INC-41).

WHY THIS EXISTS
    On 2026-08-06 a vendor INT32_MIN odds price crashed the `--w3pre-only` build. Because
    `--w3pre-only` and `--w7b-only` shared ONE try block, the lineups rebuild never ran:
    `stg_statsapi_lineups_wide` FROZE at 20:08Z and the lineup monitor read that frozen parquet
    for **6.5 hours across ~40 ticks**, reporting "No newly confirmed lineups" while the op
    returned SUCCESS every 30 minutes. Three games went unscored past first pitch.

    ⭐ THE THING THAT MADE IT INVISIBLE: **the FEED was healthy the whole time.** Every existing
    check watches a SOURCE (is the capture running? is the raw mirror advancing? did the op
    raise?) and every one of them was correctly green. Nothing asserted that the DERIVED artifact
    the serving path actually reads had ADVANCED. That is the INC-37 / E9.48 / Byparr class: a
    frozen derived artifact is structurally invisible to a freshness check on its source, and to
    a liveness check on the job that builds it.

    PR #638 fixed the two proximate causes (the bigint parse; the shared try block, which now
    pages per leg). Neither closes the general hole: a leg that FAILS now pages, but a build that
    is SKIPPED, gated off, never scheduled, or whose sensor stopped ticking still freezes the
    artifact in total silence. This module asserts the artifact itself.

⛔ WHY NOT S3 `LastModified` — the obvious implementation, and it is wrong twice over.
    (1) `aws s3 ls` prints LastModified in the SHELL'S LOCAL TIME, not UTC (E11.20 phase-2a),
        so diffing it against a UTC clock manufactures a ~5-6h phantom staleness.
    (2) More fundamentally, PR #638 made the S3 writes ATOMIC via a server-side copy — so a
        re-copied object carries a FRESH mtime even when the DATA inside it is unchanged. An
        mtime check would have read GREEN through the very incident it was meant to catch.
    ⇒ freshness is read from a CONTENT timestamp INSIDE the parquet, always.

⏰ THE CORE MECHANISM — ACTIVE-MINUTE LAG, not wall-clock lag.
    A naive `now - content_ts > SLA` false-pages every night. The schedule-capture writer runs
    `*/30 14-23` + `0,30 0-3` UTC (verified in pipeline/schedules/intraday_schedules.py), so its
    last write of the day is 03:30 UTC and the next is 14:00 UTC — a DELIBERATE 10.5-hour gap in
    which a frozen-looking artifact is perfectly healthy. Measured live 2026-08-07 05:00 UTC:
    every schedule-derived artifact sat at 03:30 UTC, a 90-minute raw lag, entirely correct.

    So lag is accumulated ONLY over the writer's DECLARED ACTIVE WINDOWS:

        active_lag = |{ minutes in [content_ts, now) whose UTC hour is an active hour }|

    - Overnight gap (froze 03:30, now 05:00): active lag = 30 min ⇒ SILENT. Correct.
    - INC-41 (froze 20:08, now 02:38): active lag = 390 min ⇒ CRITICAL. Correct.
    - Band reopens (froze 03:30, now 14:05): active lag = 35 min ⇒ silent; by 15:30 it is 120 min
      ⇒ pages. Correct — nothing writing 90 min INTO the band is a real freeze.

    This is the W12/W9 lesson ("the check cadence must match the WRITE cadence") made declarative
    instead of per-monitor folklore. An artifact with no off-hours (`active_hours_utc=None`) just
    gets plain wall-clock lag, which falls out of the same function.

🪞 PROXY TIMESTAMPS — declared, never silent.
    `stg_statsapi_lineups_wide` — the INC-41 victim itself — carries NO timestamp column: the
    pivot `group by game_pk, official_date, home_away` drops the source's `ingestion_ts` (verified
    against the live parquet: 30 columns, the only temporal one is `official_date`, a DATE).
    Rather than change a serving-coupled dual-branch model's column contract (read by
    `write_serving_store`, `picks.py`, three feature models and a generated ext-table DDL) to add
    one, its contract declares a PROXY: `stg_statsapi_lineups`, which IS timestamped and which
    `_build_w7b` rebuilds from raw in the SAME `--w7b-only` invocation, immediately before the
    pivot (INC-31-B2). The proxy is labelled PROXY in the table, the metrics and the page body —
    it is never presented as the artifact's own reading.

    ⚠️ ITS ONE BLIND SPOT, STATED: if the flatten succeeds and the PIVOT alone raises, the proxy
    reads fresh while `lineups_wide` is stale. That case is NOT silent — the `--w7b-only`
    subprocess exits non-zero and `intraday_ops` pages CRITICAL on the failing leg (PR #638). The
    class this module exists to catch is the opposite one: a build that never runs and reports
    SUCCESS, where the proxy freezes in lockstep with the artifact. Between the two, the freeze is
    covered; the residual is a known, loud-elsewhere gap, not an unexamined assumption.

TIER (E11.7): ALERT-loud-but-continue. A stale artifact PAGES via `send_alert` and never HALTs —
    observability only (`best_alpha=0`), and a monitor must never withhold a slate. An artifact
    that cannot be evaluated (absent, unreadable, null timestamp) is WARN and is NEVER scored
    healthy: an anchor that fails to evaluate makes its assertion vacuously true (NF1.7 (a)).

Lives in betting_ml/ (not pipeline/) so the fast gate can import it — `pipeline/__init__.py`
    reads the dbt manifest, absent in CI, so a fast-gate test importing `pipeline` dies at
    COLLECTION (E11.23). Same shape as `w11_tail_coverage.py` / `spine_horizon.py`. PURE stdlib:
    no duckdb / boto3 / pandas at import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# ── Declared writer cadences ────────────────────────────────────────────────────────────
# UTC hours in which each writer is expected to run. Sourced from the deployed crons, not from
# intent: pipeline/schedules/intraday_schedules.py declares
#   intraday_schedule_capture_daytime    "*/30 14-23 * * *"
#   intraday_schedule_capture_overnight  "0,30 0-3  * * *"
# so the band is [14..23] ∪ [0..3]; the last fire is 03:30 UTC and the next is 14:00 UTC.
#
# ⚠️ HOUR 4 IS DELIBERATELY EXCLUDED, and getting this wrong is a nightly false page. The
# tempting reasoning is "include hour 4 so the 03:30 fire gets its 30-minute interval before lag
# counts against it" — but an HOUR-granularity window cannot express 30 minutes: including hour 4
# adds a full 60. Measured live 2026-08-07 05:04Z with hour 4 included, every schedule-derived
# artifact read a lag of EXACTLY 90 against an SLA of 90, passing only because the comparison is
# strictly `>`. Hour 3 already supplies the grace (the 03:30 fire's own interval runs 03:30-04:00,
# inside hour 3), so excluding hour 4 caps the overnight lag at 30 against the 90 SLA — 3x
# headroom instead of none.
SCHEDULE_CAPTURE_HOURS = (0, 1, 2, 3, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)

# `None` = always active (plain wall-clock lag) — for artifacts on a once-daily build.
ALWAYS = None

# ── NFL point-in-time capture cadence (NF-CAP1) ─────────────────────────────────────────
# Sourced from the deployed crons in pipeline/schedules/sports_nfl_pit_capture_schedules.py:
#   sports_nfl_pit_metadata_schedule  "0  9 * 9-12,1-2 2,5"   Tue+Fri 09:00 PT, Sep-Feb
#   sports_nfl_pit_market_schedule    "15 9 * 9-12,1-2 2,5"   Tue+Fri 09:15 PT, Sep-Feb
# and CONFIRMED against the live store: `nfl/pit/market` carries capture_timestamps of
# 2026-09-01T16:15:19Z and 2026-09-04T16:15:19Z — 09:15 PDT to the second.
#
# ⭐ `active_hours_utc` is deliberately None for these, and that is a DST decision rather than a
# shortcut. 09:00 PT is 16:00 UTC in PDT and 17:00 UTC in PST, and an NFL season spans the
# switch — so an hour-granularity UTC window would be right in September and wrong in January,
# the exact "plausible but wrong" shape pit/schedule.py refuses to guess at for kickoffs. The
# DAY axis carries all the information needed here: whole Tue/Fri days in-season, nothing else.
NFL_PIT_TUE_FRI = (1, 4)                        # datetime.weekday(): Mon=0 … Tue=1, Fri=4
NFL_SEASON_MONTHS = (9, 10, 11, 12, 1, 2)       # Sep-Feb, the crons' own month gate

#: ⏱️ DERIVED, not chosen. Under NFL_PIT_TUE_FRI + NFL_SEASON_MONTHS one cadence interval is
#: EXACTLY 24.00 active hours in both directions (measured: Tue 16:15 -> Fri 16:15 = 24.00h;
#: Fri -> Tue = 24.00h; and 24.00h again in January, because there is no hour filter to shift),
#: and one fully missed fire is exactly 48.00. 36 sits halfway: 12h of headroom above the
#: healthy maximum, and a missed fire crosses it ~12h before the following capture, so the next
#: freshness tick pages rather than the one after. A tighter SLA would page on a slow run; a
#: looser one would let a missed fire hide behind the next healthy one.
NFL_PIT_TUE_FRI_SLA_MINUTES = 36 * 60


@dataclass(frozen=True)
class FreshnessContract:
    """One serving-critical artifact's declared freshness SLA.

    `ts_expr` is a SQL expression over `ts_table` returning that artifact's CONTENT timestamp
    (never an S3 mtime). It is cast at the use-site because the lakehouse stores every TIMESTAMP
    as ISO VARCHAR (the INC-23 binary-timestamp cure), so a bare comparison would bind wrong.
    """

    name: str                       # the artifact whose freshness is being asserted
    ts_table: str                   # the table the timestamp is READ from (== name, unless proxied)
    ts_expr: str                    # SQL over ts_table -> content timestamp
    max_lag_minutes: int            # SLA, in ACTIVE minutes (see module docstring)
    active_hours_utc: tuple[int, ...] | None
    cadence: str                    # human description of the writer's cadence
    why: str                        # what breaks downstream when this artifact freezes
    remediate: str                  # the first thing an operator should do
    # ── NF-CAP1: the other two axes of a writer's active window ──────────────────────────
    # Hours alone cannot express a WEEKLY or SEASONAL writer, and both exist now: the NFL
    # point-in-time captures fire Tue+Fri and only from September to February. Without these a
    # Tue/Fri contract false-pages every Wednesday, and a Sep-Feb one false-pages all summer —
    # the same defect the hour axis was added to prevent, one and two periods up. `None` = every
    # weekday / every month, so every pre-existing contract is unchanged by construction.
    active_weekdays: tuple[int, ...] | None = None   # Mon=0 … Sun=6 (datetime.weekday())
    active_months: tuple[int, ...] | None = None     # 1..12
    # The NFL point-in-time store is a Delta table under `nfl/pit/<source>`, not an MLB lakehouse
    # view, so the READ differs even though every line of policy below is shared. Set this to the
    # pit source name to route the read; `ts_table` still equals `name`, so `is_proxied` keeps
    # meaning exactly what it meant.
    pit_source: str | None = None

    @property
    def is_proxied(self) -> bool:
        """True when the timestamp comes from a DIFFERENT artifact than the one being asserted."""
        return self.ts_table != self.name


# ── The registry ────────────────────────────────────────────────────────────────────────
# Ordered most-serving-critical first. Every entry's `ts_expr` was verified against the LIVE
# parquet on 2026-08-07 before being registered — `feature_pregame_game_features_raw` was
# CONSIDERED and REJECTED here: its only temporal column, `odds_ingestion_ts`, measured 40 HOURS
# stale on a healthy store (it records when the joined odds were captured, not when the store was
# built), so registering it would have produced a permanent false page. A registry entry is a
# claim about a column's behaviour and has to be measured, not assumed.
REGISTRY: tuple[FreshnessContract, ...] = (
    FreshnessContract(
        name="stg_statsapi_lineups_wide",
        # PROXY: the pivot drops ingestion_ts (see the module docstring). Its co-built sibling is
        # rebuilt from raw in the same --w7b-only invocation, immediately before the pivot.
        ts_table="stg_statsapi_lineups",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        # 3 missed 30-minute ticks. Tight enough that INC-41's 6.5h freeze pages on the FIRST
        # off-cycle check after ~90 minutes instead of never; loose enough that one skipped tick
        # (a slow build, a redeploy) is not a page.
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "the lineup monitor detects confirmed lineups from this parquet, and the --s3 serving "
            "reads build the pick-detail lineup card from it. Frozen = post_lineup re-scores "
            "silently stop for the rest of the slate (INC-41: 6.5h, ~40 ticks, 3 games unscored "
            "past first pitch, every op reporting SUCCESS)"
        ),
        remediate=(
            "check intraday_schedule_capture is ticking and its --w7b-only leg is running, then "
            "rebuild: run_w1_lakehouse.py --w7b-only"
        ),
    ),
    FreshnessContract(
        name="stg_statsapi_games",
        ts_table="stg_statsapi_games",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "served game state (Preview/Live/Final) and the game universe every downstream build "
            "scopes itself to. This is the leg that actually raised in INC-41 (--w3pre-only); "
            "frozen = prod serves day-stale game states"
        ),
        remediate="rebuild: run_w1_lakehouse.py --w3pre-only",
    ),
    FreshnessContract(
        name="stg_statsapi_probable_pitchers",
        ts_table="stg_statsapi_probable_pitchers",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "the pregame starter block. On 2026-07-23 this froze at a retired native source and "
            "games whose starters were announced afterwards served both-NULL probables, so the "
            "starter block could not build and those games got NO prediction at all"
        ),
        remediate="rebuild: run_w1_lakehouse.py --w7b-only",
    ),
    FreshnessContract(
        name="feature_pregame_lineup_features",
        ts_table="feature_pregame_lineup_features",
        # A genuine BUILD stamp (not an inherited feed timestamp) — the only feature block that
        # carries one; the other five blocks predict_today gates on have no temporal column at all.
        ts_expr="max(try_cast(computed_at as timestamp))",
        # A once-per-day contract: the intraday rebuild of this block is gated
        # (LINEUP_INTRADAY_S3_REBUILD, default OFF), so the DAILY build (12:00 UTC) is the only
        # cadence that can be asserted without false-paging. 26h admits a late/slow daily run and
        # still catches the multi-day freeze class (the E11.20 spine-freeze shape).
        max_lag_minutes=26 * 60,
        active_hours_utc=ALWAYS,
        cadence="at least once daily (W8a in the 12:00 UTC daily build)",
        why=(
            "the lineup feature block predict_today reads. Frozen = the feature store loses the "
            "current slate and predict silently degrades to intraday_fallback"
        ),
        remediate="check the daily job's W8a step, then rebuild: run_w1_lakehouse.py --w8a-only",
    ),
    FreshnessContract(
        name="stg_ref_players",
        ts_table="stg_ref_players",
        # A genuine BUILD stamp written by build_ref_players_dimension.py at publish — NOT an
        # inherited feed timestamp (the trap that got feature_pregame_game_features_raw REJECTED
        # from this registry: its only temporal column recorded when the joined odds were
        # captured, so it measured 40h stale on a healthy store).
        ts_expr="max(try_cast(built_at as timestamp))",
        # Rebuilt as a leaf of the 12:00 UTC daily job AND of the weekly profiles job. 30h admits
        # a late or slow daily run — this leaf sits at the end of a long chain — while still
        # catching the multi-DAY freeze class, which is the only class that has ever bitten here.
        max_lag_minutes=30 * 60,
        active_hours_utc=ALWAYS,
        cadence="daily (leaf of the 12:00 UTC daily_ingestion_job) + weekly_player_profiles_job",
        why=(
            "the player-name dimension ~11 consumers read directly from S3 — the two mart_pitch_* "
            "name-enrichment marts, the batter/pitcher clustering scripts, the prop name→id "
            "bridges and the zone-overlay name lookups. This is the artifact whose silent rot "
            "E5.10 found: no scheduled writer at all, 53 days stale, ZERO players at "
            "mlb_played_last=2026, and a serving writer quietly skipping 34 batters. ⭐ THE POINT "
            "OF THIS ENTRY IS THAT THE OLD FAILURE WAS INVISIBLE TO EVERY SOURCE-WATCHING CHECK: "
            "the feed was fine, the marts built, nothing raised — only an assertion on the "
            "DERIVED artifact can see it. Frozen = new players resolve to no name; no slate is "
            "withheld and no prediction changes"
        ),
        remediate=(
            "rebuild: uv run python scripts/build_ref_players_dimension.py — and if it REFUSES on "
            "the current-season coverage floor, that is the guard working: check player_profiles_raw "
            "and stg_batter_pitches are current and that the stg_ref_players_archive/ prefix exists"
        ),
    ),
    # ── NFL point-in-time forward captures (NF-CAP1) ────────────────────────────────────
    # These are NOT serving-critical — nothing downstream reads them yet, and best_alpha=0. They
    # are here because their failure mode is STRICTLY WORSE than a serving outage: a serving
    # artifact that freezes can be rebuilt, and a point-in-time capture that does not happen is
    # gone forever (the Open-Meteo archive returns observations rather than the forecast that
    # stood at the time, and the odds history retains only closing lines). A frozen capture is
    # also invisible to every source-watching check by construction — the nflverse release and
    # the Odds API are both perfectly healthy while we simply fail to look.
    FreshnessContract(
        name="nfl_pit_market",
        ts_table="nfl_pit_market",
        pit_source="market",
        ts_expr="max(try_cast(capture_timestamp as timestamp))",
        max_lag_minutes=NFL_PIT_TUE_FRI_SLA_MINUTES,
        active_hours_utc=ALWAYS,
        active_weekdays=NFL_PIT_TUE_FRI,
        active_months=NFL_SEASON_MONTHS,
        cadence="Tue+Fri 09:15 PT, Sep-Feb (sports_nfl_pit_market_schedule)",
        why=(
            "the Tue/Fri point-in-time NFL market board — the ONLY source from which an "
            "early-week market feature can ever be backtested, because the Odds API's history "
            "retains closing lines only. A frozen capture is not a delayed feature, it is a "
            "permanently absent one: every week not captured is a week missing from the training "
            "frame forever, and no later fetch reconstructs it"
        ),
        remediate=(
            "confirm sports_nfl_pit_market_schedule is RUNNING in Dagit (it ships STOPPED, so its "
            "ON state lives only in the Dagster Postgres and a volume reset reverts it), then "
            "re-run the leg while the slate is still pre-kickoff: python -m "
            "quant_sports_intel_models.football.nfl.pit.run_capture --leg market"
        ),
    ),
    FreshnessContract(
        name="nfl_pit_injuries",
        ts_table="nfl_pit_injuries",
        pit_source="injuries",
        ts_expr="max(try_cast(capture_timestamp as timestamp))",
        max_lag_minutes=NFL_PIT_TUE_FRI_SLA_MINUTES,
        active_hours_utc=ALWAYS,
        active_weekdays=NFL_PIT_TUE_FRI,
        # ⚠️ ARMED FROM OCTOBER, NOT SEPTEMBER, and this is the INC-45 rule ("do NOT put a
        # freshness SLA on an artifact that should not advance") applied to a WINDOW rather than
        # to a whole artifact. nflverse publishes `injuries_<season>.parquet` only once injury
        # reports exist — week 1's practice reports — so through September the artifact CANNOT
        # advance and a Sep-armed SLA would page daily on a leg working exactly as designed.
        # Measured 2026-09-05: the 2026 asset 404s, and the leg's two September fires correctly
        # captured nothing.
        #
        # September is not left uncovered, it is covered by the two mechanisms that can actually
        # see it: the leg PAGES ITSELF once its own `data_expected_from` bar passes (week 2's
        # first kickoff, ~mid-September) if the asset is still absent OR lands zero rows, and
        # check_monitors_healthy pages IMMEDIATELY, all year, if the schedule drifts STOPPED.
        # Arming here from October puts this backstop strictly downstream of the leg's own bar,
        # so the two never double-page over the same ambiguous window.
        active_months=(10, 11, 12, 1, 2),
        cadence="Tue+Fri 09:00 PT, Oct-Feb armed (sports_nfl_pit_metadata_schedule; Sep covered by the leg's own bar)",
        why=(
            "nflverse DELETED injuries.date_modified in 2025, so OUR capture_timestamp is the "
            "only as-of bound that will ever exist for a 2025+ injury report — and one cannot be "
            "manufactured after the fact. A frozen capture means every downstream injury study "
            "is either leaking or unrunnable, and the leakage guard has no original to enforce a "
            "vendor revision against"
        ),
        remediate=(
            "confirm sports_nfl_pit_metadata_schedule is RUNNING in Dagit, then re-run: python -m "
            "quant_sports_intel_models.football.nfl.pit.run_capture --leg injuries . If it "
            "reports expected_absent, nflverse has not published the season asset yet and there "
            "is nothing to capture — check the leg's own escalation instead"
        ),
    ),
)


# ── The core: active-minute lag ─────────────────────────────────────────────────────────
# A gap longer than this is reported at the cap rather than accumulated minute by minute. It only
# affects the NUMBER printed for an already-catastrophic freeze, never a verdict.
#
# ⚠️ NF-CAP1 RAISED IT 45 -> 400 DAYS, and the reason is a correctness bug, not performance. The
# cap returned a FLAT `days * 24 * 60` regardless of which minutes were active — fine when the
# only filter was hour-of-day (every day contributes, so a long gap is stale under any reading),
# and WRONG the moment a contract is seasonal. A Sep-Feb artifact frozen on 2026-08-05 and read
# on 2026-09-20 is 46 days out: under the old cap that returned 64,800 minutes and paged, when
# the TRUE active lag is ZERO because September is not in its active months. The scan is now
# DAY-bucketed, so an inactive day costs one comparison instead of 24 — cheap enough to scan a
# year exactly rather than guess past 45 days.
_MAX_SCAN_DAYS = 400


def active_minutes_between(
    start: datetime,
    end: datetime,
    active_hours: tuple[int, ...] | None,
    active_weekdays: tuple[int, ...] | None = None,
    active_months: tuple[int, ...] | None = None,
) -> float:
    """Minutes in ``[start, end)`` that fall inside the writer's declared active window.

    A minute is active when its UTC hour is in ``active_hours``, its weekday in
    ``active_weekdays`` and its month in ``active_months``; ``None`` on any axis means "every
    value" on that axis. With all three ``None`` this is plain wall-clock lag.

    PURE. This is the whole off-hours-awareness mechanism — see the module docstring for why a
    raw wall-clock lag is unusable against a writer with a deliberate 10.5-hour overnight gap.
    Returns 0.0 when ``end <= start`` (a content timestamp AHEAD of now is not negative lag; the
    caller treats a materially future timestamp as unevaluable).
    """
    if end <= start:
        return 0.0
    if active_hours is None and active_weekdays is None and active_months is None:
        return (end - start).total_seconds() / 60.0

    hours = None if active_hours is None else frozenset(active_hours)
    weekdays = None if active_weekdays is None else frozenset(active_weekdays)
    months = None if active_months is None else frozenset(active_months)

    total = 0.0
    scanned_days = 0
    # Walk DAY buckets; an inactive day is skipped whole. Inside an active day, walk hour buckets,
    # clamping the first and last to the true bounds.
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        next_day = day + timedelta(days=1)
        scanned_days += 1
        if scanned_days > _MAX_SCAN_DAYS:
            # Anything this stale is far past every SLA in the registry; report at the cap.
            return float(_MAX_SCAN_DAYS * 24 * 60)
        if (weekdays is None or day.weekday() in weekdays) and (
            months is None or day.month in months
        ):
            if hours is None:
                lo, hi = max(day, start), min(next_day, end)
                if hi > lo:
                    total += (hi - lo).total_seconds() / 60.0
            else:
                cursor = day
                while cursor < next_day and cursor < end:
                    nxt = cursor + timedelta(hours=1)
                    if cursor.hour in hours:
                        lo, hi = max(cursor, start), min(nxt, end)
                        if hi > lo:
                            total += (hi - lo).total_seconds() / 60.0
                    cursor = nxt
        day = next_day
    return total


# ── Verdicts ────────────────────────────────────────────────────────────────────────────
OK = "OK"
STALE = "STALE"
UNEVALUABLE = "UNEVALUABLE"


@dataclass(frozen=True)
class FreshnessReading:
    """One contract's evaluated state."""

    contract: FreshnessContract
    content_ts: datetime | None
    active_lag_minutes: float | None
    verdict: str
    detail: str = ""

    @property
    def is_problem(self) -> bool:
        return self.verdict in (STALE, UNEVALUABLE)


def evaluate(
    contract: FreshnessContract, content_ts: datetime | None, now: datetime
) -> FreshnessReading:
    """PURE. Map a contract + the content timestamp read for it to a verdict.

    A missing timestamp is UNEVALUABLE, never OK (NF1.7 (a)): the artifact may be absent, empty,
    unreadable, or its timestamp column all-NULL — every one of those is a thing to look at, and
    none of them is evidence of freshness.
    """
    if content_ts is None:
        return FreshnessReading(
            contract, None, None, UNEVALUABLE,
            "no content timestamp could be read (absent / empty / unreadable / all-NULL)",
        )

    if content_ts.tzinfo is None:
        content_ts = content_ts.replace(tzinfo=timezone.utc)
    else:
        content_ts = content_ts.astimezone(timezone.utc)

    # A timestamp materially in the FUTURE is a corrupt clock or a typo'd upstream date (the
    # E9.48-b class, where a keying error dated a row 900 years out and silently DISABLED a
    # max()-based freshness guard by making its lag hugely negative). Refuse to score it healthy.
    if content_ts > now + timedelta(minutes=15):
        return FreshnessReading(
            contract, content_ts, None, UNEVALUABLE,
            f"content timestamp {content_ts:%Y-%m-%d %H:%M}Z is in the FUTURE relative to "
            f"{now:%Y-%m-%d %H:%M}Z — a future-dated max() disables the guard rather than "
            "passing it (E9.48-b)",
        )

    lag = active_minutes_between(
        content_ts, now, contract.active_hours_utc,
        contract.active_weekdays, contract.active_months,
    )
    if lag > contract.max_lag_minutes:
        return FreshnessReading(
            contract, content_ts, lag, STALE,
            f"{lag:.0f} active min since {content_ts:%Y-%m-%d %H:%M}Z "
            f"(SLA {contract.max_lag_minutes})",
        )
    return FreshnessReading(
        contract, content_ts, lag, OK,
        f"{lag:.0f} active min (SLA {contract.max_lag_minutes})",
    )


# ── [METRIC] protocol ───────────────────────────────────────────────────────────────────
# The op parses these rather than re-reading S3, mirroring check_w11_tail_coverage.
_EVALUATED_PREFIX = "[METRIC] artifact_freshness_evaluated="
_NOW_PREFIX = "[METRIC] artifact_freshness_now="
_ARTIFACT_RE = re.compile(
    r"^\[METRIC\]\s+artifact_freshness_(?P<name>[a-z0-9_]+)="
    r"(?P<verdict>OK|STALE|UNEVALUABLE)\s+lag_min=(?P<lag>-?\d+|NA)\s+sla=(?P<sla>\d+)\s*$"
)


def parse_evaluated(stdout: str) -> bool | None:
    """True/False from the last `artifact_freshness_evaluated` line; None when it never appeared.

    None and False are both "unverified" to `classify`, but they differ in cause: False = the
    script ran and its read raised; None = it never got far enough to print, or output was lost.
    """
    value: bool | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_EVALUATED_PREFIX):
            value = line[len(_EVALUATED_PREFIX):].strip() == "1"
    return value


def parse_now(stdout: str) -> datetime | None:
    """The instant the script says its readings describe, from `artifact_freshness_now=`.

    INC-39: freshness output is the single most replay-sensitive thing a monitor can parse — a
    stale/synthetic/replayed stdout parses byte-identically to a live read, and every number in it
    is individually real. Stamped on EVERY exit path so the op's skew cross-check can never be
    vacuously satisfied by an absent line (NF1.7 (a)).
    """
    value: datetime | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_NOW_PREFIX):
            raw = line[len(_NOW_PREFIX):].strip()
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            value = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return value


def parse_verdicts(stdout: str) -> dict[str, tuple[str, float | None, int]]:
    """Map artifact -> (verdict, active_lag_minutes|None, sla_minutes). Later lines win."""
    out: dict[str, tuple[str, float | None, int]] = {}
    for line in stdout.splitlines():
        m = _ARTIFACT_RE.match(line.strip())
        if m:
            lag_raw = m.group("lag")
            out[m.group("name")] = (
                m.group("verdict"),
                None if lag_raw == "NA" else float(lag_raw),
                int(m.group("sla")),
            )
    return out


# How far the script's stamped `now` may drift from the op's own clock before the whole reading is
# treated as not-about-this-moment. The script runs as a subprocess of the op, so a legitimate
# skew is seconds; 30 minutes is generous and still far tighter than the tightest SLA (90 min).
MAX_CLOCK_SKEW_MINUTES = 30


def classify(
    stdout: str, now: datetime, registry: tuple[FreshnessContract, ...] = REGISTRY
) -> tuple[str | None, str]:
    """PURE. Map the script's stdout to (severity, message). severity None = do not page.

    CRITICAL for a STALE serving-critical artifact; WARN for anything that could not be evaluated
    — including an artifact the script never reported on at all, which is the shape a partial
    crash takes and must not read as healthy.
    """
    evaluated = parse_evaluated(stdout)
    reported_now = parse_now(stdout)
    verdicts = parse_verdicts(stdout)

    # INC-39 — the readings must be ABOUT this moment. Freshness numbers from an earlier run are
    # all individually real and would page (or, worse, reassure) about a moment nobody checked.
    skewed = (
        reported_now is not None
        and abs((now - reported_now).total_seconds()) / 60.0 > MAX_CLOCK_SKEW_MINUTES
    )

    stale: list[str] = []
    unverified: list[str] = []

    for contract in registry:
        if skewed:
            unverified.append(
                f"{contract.name} (output is stamped {reported_now:%Y-%m-%d %H:%M}Z, "
                f"this run is {now:%Y-%m-%d %H:%M}Z)"
            )
            continue
        entry = verdicts.get(contract.name)
        if not evaluated or entry is None:
            unverified.append(f"{contract.name} (no reading)")
            continue
        verdict, lag, sla = entry
        if verdict == STALE:
            proxy = f" [ts via PROXY {contract.ts_table}]" if contract.is_proxied else ""
            lag_txt = "unknown" if lag is None else f"{lag:.0f}"
            stale.append(
                f"{contract.name}: {lag_txt} active min behind (SLA {sla}; {contract.cadence})"
                f"{proxy} — {contract.why}. FIX: {contract.remediate}"
            )
        elif verdict == UNEVALUABLE:
            unverified.append(f"{contract.name} (unevaluable)")

    if not stale and not unverified:
        return None, (
            "Artifact freshness OK — every registered serving-critical parquet has advanced "
            "within its declared SLA (lag counted only across each writer's active hours)."
        )

    parts: list[str] = []
    if stale:
        parts.append("STALE: " + " | ".join(stale))
    if unverified:
        parts.append("UNVERIFIED (not evaluated — NOT verified healthy): " + "; ".join(unverified))

    msg = (
        "SERVING ARTIFACT FRESHNESS (INC-41): " + " || ".join(parts) + ". "
        "A STALE artifact means the build that writes it has stopped advancing it while every "
        "upstream feed and every op may still read green — that is exactly INC-41 (2026-08-06), "
        "where stg_statsapi_lineups_wide froze for 6.5h across ~40 ticks, the lineup monitor "
        "reported 'No newly confirmed lineups' the whole time, and the op returned SUCCESS. Lag "
        "is measured from a CONTENT timestamp inside the parquet (never the S3 mtime, which the "
        "atomic-copy write refreshes even when the data is unchanged) and is accumulated ONLY "
        "across the writer's declared active hours, so an overnight gap is not a breach."
    )
    if stale:
        return "CRITICAL", msg
    return "WARN", msg

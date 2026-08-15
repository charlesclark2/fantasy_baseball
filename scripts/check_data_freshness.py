"""
check_data_freshness.py
-----------------------
Verify that all ingestion source tables have been updated within their expected
freshness windows. Exits non-zero if any threshold is breached.

Usage:
    uv run python scripts/check_data_freshness.py
    uv run python scripts/check_data_freshness.py --date 2026-05-01
    uv run python scripts/check_data_freshness.py --dry-run

Snowflake auth env vars (same pattern as other scripts):
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE              (optional)

DATA SOURCE — repointed to S3 in three passes: E11.24 target 3 (2026-08-08), the INC-25
player-seq export-ordering fix (2026-08-09), and the E11.24 Bundle (2026-08-14) which cleared
the last three blockers. READ THIS BEFORE CHANGING AN ENTRY'S ``source``:
    Every entry carries an explicit ``source`` ("snowflake" | "s3"). The Snowflake connection
    is opened LAZILY and only if at least one entry (or the game-day probe) still needs it —
    so the day the last entry flips, this script becomes Snowflake-free with no further edit.
    That day is the Bundle's deploy: with PR #772's two cheap flips (eb_bullpen_team_posteriors,
    eb_park_factors_raw) and the Bundle's three, EVERY entry reads S3, ``needs_snowflake()``
    returns False, and ``run()`` opens no Snowflake connection at all.

    ⛔ THE WAKE CREDIT IS NOT ADDITIVE ACROSS FLIPS, WHICH IS WHY THEY SHIPPED AS A BUNDLE.
    E11.24 #679's lesson: on an auto-suspending warehouse only the FIRST occupying statement
    after a suspend pays the resume — wake is a QUEUE, not a sum. The census attributed
    ~2.3 resumes/day to ``_is_game_day`` simply because it is the FIRST statement this script
    runs; repointing it did not delete that wake, it PROMOTED the next statement (the first
    remaining Snowflake ``MAX()``) to pay it. Each earlier flip was made because it was
    individually CORRECT, and each honestly booked ZERO credit. Only the LAST flip in the set
    converts any of it into a real resume reduction — do not re-derive a per-flip saving from
    this file's history and conclude the earlier passes under-delivered.

    ⛔ AND THIS CLEARS **THIS SCRIPT ONLY** — it is not "Snowflake-free serving". The other
    named COMPUTE_WH wakers (the feature_pregame_team_features view, the lineup_state SCD-2
    writes, CI_WH, CREDENCE_API) are untouched, and the queue simply moves to whichever of them
    fires first. Literal-zero resume needs all of them.

    MEASURED 2026-08-08 (laptop; Snowflake side on MONITOR_WH so the target-6 COMPUTE_WH soak
    was untouched), with the three blockers RE-measured 2026-08-14 — max(ts_col) on each side,
    which is exactly what this check reads:

      table                             SF max            S3 max            → source
      mart_player_archetype_posteriors  2026-07-05 (!)    2026-08-07        → S3   (see below)
      player_sequential_posteriors      08-08 13:02:18    08-07 13:02:08    → S3   (UNBLOCKED 08-09)
      eb_bullpen_team_posteriors        2026-08-08        2026-08-08        → S3   (PR #772)
      eb_park_factors_raw               2026-05-27        2026-05-27        → S3   (PR #772)
      team_sequential_posteriors        08-14 13:03:04    08-14 10:16:26    → S3   (UNBLOCKED 08-14)
      player_profiles_raw               08-02 10:00:31    2026-06-28 (!)    → S3   (UNBLOCKED 08-14)
      matchup_cell_sequential_posteriors 08-08 13:03:15   <NO S3 TABLE>     → S3   (UNBLOCKED 08-14)

    ⭐ HOW THE LAST THREE WERE CLEARED (E11.24 Bundle, 2026-08-14) — each was a DIFFERENT defect
    wearing the same "the mirror is stale" costume, and reading them as one problem is the trap:
      • ``team_sequential_posteriors`` — an INC-25 ORDERING TRAIL, the #693 defect one table
        over. ``lakehouse_w8b_aggregator_op`` mirrors it at lk10 while
        ``update_team_posteriors_op`` writes ~40 min later. ⚠️ The 08-08 row above read
        "identical" and made this look like a safe cheap flip; that reading was taken at the
        moment this docstring already warned is BLIND (see the two-callers note below).
        Re-measured 2026-08-14: SF 13:03:04 / 83,636 rows vs S3 10:16:26 / 83,619 — 2.78h and
        17 rows behind. PR #772 therefore REFUSED this flip and carded the fix.
        CURE: ``reexport_team_seq_posteriors_op``, a fan-out leaf downstream of the writer in
        BOTH jobs that run it. The lk10 mirror STAYS (the ``--w8b`` build reads it) and the
        order cannot be swapped — a genuine cycle, documented at
        ``sensor_ops.lineup_intraday_s3_feature_rebuild`` (E9.53).
      • ``player_profiles_raw`` — a WRITER GAP, not a trail. ``ingest_player_profiles.py``
        writes ONLY Snowflake; the mirror's sole writer, ``export_w4_raw_to_s3.py``, is a
        hand-run W4 build precursor that no job schedules, so it froze at 2026-06-28 (~1,133h
        by 08-14 against a 192h threshold). It hid because nothing LOUD reads the mirror — the
        duckdb branch of ``stg_statsapi_player_profiles`` silently omits recent call-ups rather
        than erroring. CURE: ``reexport_player_profiles_op`` in ``weekly_player_profiles_job``.
      • ``matchup_cell_sequential_posteriors`` — NO MIRROR AT ALL (a DuckDB IOException, not a
        stale read), so the export had to be BUILT. CURE: an ON-DEMAND-ONLY entry in
        ``export_w8b_precursors_to_s3.py`` plus ``reexport_matchup_cell_posteriors_op``, wired
        downstream of its writer FROM DAY ONE. Adding it to that exporter's default (lk10) set
        would have been one line cheaper and would have created the mirror with the INC-25 trail
        ALREADY INSTALLED — the fourth member of the family this bundle exists to close.

    ⚠️ THE BUNDLE'S FLIPS AND ITS OPS MUST DEPLOY TOGETHER, and the mirrors need PRIMING. An
    S3-sourced entry on a box still running the un-reordered graph is a guaranteed false STALE
    (guarded). Separately, the re-export leaves only heal a mirror when their job next RUNS:
    team_seq/matchup_cell heal at the next daily run, but ``player_profiles_raw`` would report a
    false STALE for up to SEVEN DAYS (its writer is weekly). ⇒ the deploy is accompanied by a
    one-time operator prime of all three exports; see the Bundle's handoff.

    ⭐ ``player_sequential_posteriors`` — UNBLOCKED 2026-08-09 (the INC-25 export-ordering fix).
    Target 3 recorded this entry as blocked by a STRUCTURAL 24h lag and estimated "~12h of
    headroom on a 36h threshold". Re-measured at 03:45 UTC the same night, the mirror was
    **38.72h** stale — the threshold was already BREACHED, so the entry was worse than recorded,
    not better. The reason the defect looked survivable is a reading-time artifact worth
    keeping: this script has TWO callers (the INC-38 every-caller lesson, on the READ side) —
    the in-job ``check_data_freshness`` op at s15 AND a host cron at ``30 12,17 * * *`` UTC
    (services/dagster/aws/capture.crontab). At s15 the writer has not run yet either, so
    Snowflake and S3 return the SAME value and the lag is INVISIBLE; the 17:30 cron sees
    Snowflake at ~4.5h and the mirror at ~28.5h, and anything past ~01:00 UTC breaches outright.
    ⇒ measure a mirror's lag at the reader's WORST moment, not at an arbitrary one.
    THE FIX (not a reader repoint): ``reexport_player_seq_posteriors_op`` re-mirrors the table
    DOWNSTREAM of ``update_player_posteriors_op``, in BOTH jobs that run that writer
    (daily_ingestion_job and statcast_catchup_job), as a fan-out leaf that pages on failure and
    can never block the chain. Pinned by test_e11_24_player_seq_reexport_ordering.py.
    ⚠️ THE FLIP AND THE FIX MUST DEPLOY TOGETHER — this entry reading S3 while the box still runs
    the un-reordered graph is a guaranteed daily false STALE.

    NO ENTRY IS BLOCKED ANY LONGER — the "WHY EACH REMAINING ENTRY IS BLOCKED" list that stood
    here was fully discharged on 2026-08-14 (see the per-blocker cures above). The Snowflake
    branch below is DELIBERATELY RETAINED rather than deleted, even though nothing exercises it:
    it is the escape hatch for a future feed that is genuinely Snowflake-resident, and
    ``_DEFAULT_SOURCE`` stays "snowflake" so a new entry that forgets to declare a source fails
    loudly toward the store that certainly exists rather than silently toward a mirror that may
    not. ⚠️ A NEW ``source="snowflake"`` ENTRY SILENTLY RE-OPENS THE CONNECTION and re-adds this
    script to the COMPUTE_WH wake queue — that is the cost to weigh, and it is guarded
    (test_e11_24_bundle_freshness_reexports.py fails on any Snowflake-sourced entry, so the
    decision has to be argued rather than drifted into).

    ⭐ WHY ``mart_player_archetype_posteriors`` WAS FLIPPED — this is a LIVE BUG FIX, not a
    cost repoint. Its Snowflake table has been FROZEN since 2026-07-05 because
    ``update_archetype_posteriors_op`` went S3-ONLY at W7a; CLAUDE.md's op→tier table already
    records that "the W7a S3-only write means the SF-watching freshness monitor cannot see it
    fail" (which is why that op was promoted WARN→ALERT on 2026-07-06 — the day after the
    freeze). So this entry has been printing STALE (~800h > 48h) on EVERY game day for a
    month: a monitor that cries wolf daily is a monitor nobody reads. It is the FOURTH
    instance of the retired-Snowflake-writer class this very file already documents three
    times (mlb_odds_raw 07-05, monthly_schedule 07-23, derivative_odds_raw 07-29). Those
    three were REMOVED because their data left Snowflake entirely; this one is REPOINTED
    instead, because the data is alive and current on S3 — repointing RESTORES the monitor
    where removing it would delete coverage.
    ⚠️ AND THE 48h THRESHOLD STILL FITS — checked before flipping, because restoring a monitor
    that then cries wolf for a DIFFERENT reason would be no better. ``as_of_date`` is an EVENT
    date (the last game_date processed), and the S3 cadence is unbroken daily
    (2026-07-27..08-07, every date present). This script runs at ~12:00 UTC (the daily op) and
    12:30/17:30 UTC (`capture.crontab`), where the newest ``as_of_date`` is D-1 or D-2 ⇒ a lag
    of 12.5–36.5h, i.e. ≥11.5h of headroom; 48h is breached only after ~two consecutive missed
    builds, which is the intent. ⚠️ Running it OFF-schedule near 00:00 UTC legitimately reads
    ~48.3h and can trip — that is the event-date column behaving as designed, not a regression.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------

FRESHNESS_THRESHOLDS: dict[str, dict] = {
    # ⛔ savant.batter_pitches REMOVED 2026-07-06 — the raw Snowflake table was DROPPED in the
    # E11.1 lakehouse decommission (Statcast pitch data now lives as year-partitioned S3 parquet
    # `stg_batter_pitches`). A SF-table freshness check here raised `002003 … Object … does not
    # exist` and CRASHED the whole freshness run (blinding every OTHER check). Pitch freshness is
    # owned by the HARD-ALERT statcast_freshness_sensor (E11.1-W12), which reads the S3 parquet via
    # DuckDB and is the authoritative "is today's pitch data here?" monitor. Do NOT re-add a
    # SF-table pitch entry. (The per-table try/except below now also degrades a future dropped
    # object to a WARN instead of a total crash.)
    # ⛔ E11.22 DECOMMISSION (2026-07-09) — the following raw SF tables were DROPPED and their
    # freshness entries REMOVED here. A SF-table freshness check on a dropped object false-alarms
    # (QUERY ERROR / NO DATA) forever, so keeping them would just re-noise the daily summary:
    #   fangraphs.fg_stuff_plus_raw, fangraphs.fg_hitting_leaderboard_raw,
    #   savant.sprint_speed_raw, savant.catcher_framing_raw, external.oaa_team_season_raw,
    #   statsapi.player_transactions, statsapi.umpire_game_log (both data_source scopes),
    #   actionnetwork.public_betting_raw.
    # These feeds are now S3-native (lakehouse_raw/ via the W11 leg-gated writers). Their SERVED
    # freshness is owned by check_feature_block_coverage_op (per feature-block coverage vs its own
    # trailing baseline) + each ingest op's WARN-tier logging. Do NOT re-add a SF-table entry for
    # any of them — the raw no longer exists.
    # E11.12 antipattern note: month_end_date is a calendar-month boundary, NOT an
    # ingest heartbeat. It cannot detect mid-month feed failures — if the current
    # month's schedule was already loaded, month_end_date stays in the future
    # (always appears fresh) even if the schedule_capture cron breaks for days.
    # This check only catches a missed MONTHLY load (month_end_date is weeks stale).
    # The HARD-ALERT schedule_freshness_alert_sensor is the authoritative monitor for
    # daily feed continuity (stale > 4h OR 0 games on game day after 14:30 UTC).
    # ⛔ monthly_schedule REMOVED 2026-07-23 — schedule capture is now S3-NATIVE (writer retired
    # 2026-07-20, same class as the mlb_odds_raw removal below), so the Snowflake
    # statsapi.monthly_schedule table is FROZEN by design and a SF-table staleness check here would
    # false-warn once month_end_date lapses (7/31). Daily schedule continuity is owned by the
    # HARD-ALERT schedule_freshness_alert_sensor (reads the fresh S3 feed). Do NOT re-add a SF-table
    # schedule entry unless capture is reverted to write Snowflake. (_is_game_day now reads the S3
    # lakehouse_ext.stg_statsapi_games ext table — see its note.)
    # ⛔ actionnetwork.public_betting_raw REMOVED 2026-07-09 (E11.22 decommission — see the
    # consolidated note above). Public-betting is S3-native now; the raw SF table was dropped.
    # ── Odds ingestion (INC-2, 2026-06-22) ──────────────────────────────────
    # ⛔ mlb_odds_raw REMOVED 2026-07-05 — odds capture is now S3-NATIVE (LAKEHOUSE_RAW_WRITE_MODE=s3),
    # so the Snowflake oddsapi.mlb_odds_raw table is FROZEN by design and a SF-table staleness check here
    # would false-warn forever. Odds freshness is now owned by the odds-freshness sensor (E11.1-W12),
    # which reads the S3 lakehouse_raw/mlb_odds_raw/ mirror the writer lands directly. Do NOT re-add a
    # SF-table odds entry unless odds capture is reverted to write Snowflake.
    # ── Model-feature posteriors (INC-2 sweep, 2026-06-22) ──────────────────
    # These archetype / sequential / EB posteriors feed the matchup + bullpen
    # contract blocks but were UNMONITORED. The sweep found
    # mart_player_archetype_posteriors DEAD since 2026-05-31
    # (compute_archetype_posteriors.py stalled) → 3-week-stale clusters served for
    # all June games. ALERT-ONLY (non_blocking) so a stall surfaces in the summary
    # without red-failing the daily ingestion job — the model still serves
    # degraded-but-present via stale/imputed posteriors, not a hard outage.
    # Promote archetype to blocking once its backfill + daily re-wire is confirmed.
    # E11.12 antipattern fix: as_of_date = MAX(game_date) of completed games processed,
    # NOT the date the computation ran (event-date antipattern). On off-days the
    # computation still fires but as_of_date stays at the last game date — false
    # staleness after 2+ consecutive off-days. game_day_only=True avoids false positives;
    # the check only fires on game days when posteriors should have advanced to yesterday.
    # E11.24 target 3 — SOURCE = S3. The Snowflake table froze 2026-07-05 when the writer went
    # S3-only (W7a), so this entry had been reporting a FALSE STALE every game day for a month.
    # Full rationale in the DATA SOURCE block at the top of this module.
    "baseball_data.betting.mart_player_archetype_posteriors": {
        "ts_col": "as_of_date",   # DATE = last game_date included — event-date; see note above
        # ⭐ 72, NOT 48 — DERIVED FROM A LIVE READ (2026-08-13), which overturned the figure this
        # PR was originally written with. `as_of_date` is an EVENT date, and the writer sets it to
        # D−1 (today's games are unplayed), so a HEALTHY store never reads less than ~41h:
        #   · measured: `run_timestamp` 2026-08-12 13:11 UTC, `max(as_of_date)` 2026-08-11
        #   · this check runs 12:30 + 17:30 UTC (`30 12,17` in capture.crontab)
        #   · 17:30, i.e. AFTER the 13:11 write → as_of = D−1 → **41.5 h**
        #   · 12:30, i.e. BEFORE it            → as_of = D−2 → **60.5 h**
        # So the healthy band is 41.5–60.5 h and a 48 h threshold is STALE at every 12:30 run.
        # The original "12.5–36.5 h, ≥11.5 h of headroom" assumed the write lands BEFORE the 12:30
        # check; measured, it lands 41 min after — the verdict turned on a race nobody had timed.
        # 72 h clears the structural worst case (60.5) with ~11.5 h of real margin, and still
        # catches what this entry is for: a writer that stops for two days reads ≥84 h.
        # ⛔ Do not lower this without re-measuring `run_timestamp` vs the cron times — the number
        # is a property of that RACE, not of the data.
        "max_stale_hours": 72,
        "game_day_only": True,    # E11.12 fix: was False; event-date col → only check on game days
        "non_blocking": True,
        "source": "s3",
    },
    # SOURCE = S3. UNBLOCKED 2026-08-09 by the INC-25 export-ordering fix: the mirror is now
    # re-exported by `reexport_player_seq_posteriors_op`, a fan-out leaf DOWNSTREAM of
    # `update_player_posteriors_op` in BOTH jobs that run that writer (daily_ingestion_job and
    # statcast_catchup_job), so it no longer trails Snowflake by a writer cycle. Before the fix
    # the mirror measured 38.72h stale against this 36h threshold — an outright BREACH, not the
    # "~12h of headroom" a single reading had suggested. See the DATA SOURCE block.
    "baseball_data.betting.player_sequential_posteriors": {
        "ts_col": "update_ts",
        "max_stale_hours": 36,
        "game_day_only": False,
        "non_blocking": True,
        "source": "s3",
    },
    # SOURCE = S3. UNBLOCKED 2026-08-14 by the E11.24 Bundle's `reexport_team_seq_posteriors_op`,
    # the INC-25 export-ordering fix #693 applied to `player_sequential_posteriors` but did not
    # sweep up here. The 2026-08-08 "parity EXACT" reading that made this look like a safe cheap
    # flip was taken at the moment this module's own docstring warns is BLIND (in-job, before
    # either side advances); re-measured 2026-08-14 the mirror trailed by 2.78h / 17 rows, which
    # is why PR #772 refused the flip and carded the op instead. See the DATA SOURCE block.
    "baseball_data.betting.team_sequential_posteriors": {
        "ts_col": "update_ts",
        "max_stale_hours": 36,
        "game_day_only": False,
        "non_blocking": True,
        "source": "s3",
    },
    # SOURCE = Snowflake. Parity EXACT on S3 (measured 2026-08-08) — safe future flip.
    "baseball_data.betting.eb_bullpen_team_posteriors": {
        "ts_col": "fit_date",   # DATE; compute_bullpen_posteriors writes this table
        "max_stale_hours": 48,
        "game_day_only": False,
        "non_blocking": True,
        "source": "snowflake",
    },
    # ── E11.8 additions (2026-06-22) ────────────────────────────────────────
    # ⛔ derivative_odds_raw REMOVED 2026-07-29 — THIRD instance of the retired-SF-writer class
    # (after mlb_odds_raw 2026-07-05 and monthly_schedule 2026-07-23, both noted above).
    # Derivative capture went S3-NATIVE ~2026-07-07 (`derivative_odds_backfill.py`: "retires the
    # daily export bridge once mode='s3'"), so the Snowflake oddsapi.derivative_odds_raw table is
    # FROZEN BY DESIGN — verified 2026-07-29: SF max(ingestion_ts) = 2026-07-07 00:00:07 (543h
    # "stale" against a 4h threshold) while S3 lakehouse_raw/derivative_odds_raw/ has partitions
    # through dt=2026-07-29. ⇒ this entry had emitted a FALSE stale-WARN on every run for 22 days.
    # Derivative odds are EVAL/CLV-only (never a model-training input) and the live feed is healthy;
    # freshness for it belongs on the S3 mirror, not this SF table. Do NOT re-add a SF-table entry
    # unless derivative capture is reverted to write Snowflake.
    # ⭐ PATTERN (three for three): when a capture flips S3-native, its SF staleness entry must be
    # removed IN THE SAME CHANGE — otherwise the monitor cries wolf forever and real breaches in the
    # same summary stop being read. Sibling of the retired-source guard registry
    # (betting_ml/tests/test_retired_source_guard.py).
    # Park factors — annual source (game_year-1), updated once at season start via
    # betting_ml/scripts/eb_priors/fit_park_priors.py (hand-run). Feeds
    # feature_pregame_park_features → feature_pregame_game_features_raw → serving.
    # Very loose threshold (180 days) catches a missed season-start update while
    # never false-alarming mid-season (data legitimately unchanged since spring).
    # SOURCE = Snowflake. Parity EXACT on S3 (measured 2026-08-08) — safe future flip.
    "baseball_data.betting.eb_park_factors_raw": {
        "ts_col": "fit_date",   # DATE; annual update at season start
        "max_stale_hours": 4320,   # 180 days
        "game_day_only": False,
        "non_blocking": True,
        "source": "snowflake",
    },
    # ── E11.12 additions — feeds with no prior monitor ───────────────────────
    # ⛔ savant.sprint_speed_raw, savant.catcher_framing_raw, external.oaa_team_season_raw REMOVED
    # 2026-07-09 (E11.22 decommission — see the consolidated note above). All three are S3-native
    # now; their raw SF tables were dropped. Served freshness → check_feature_block_coverage_op.
    # Player profiles — weekly update mode (weekly_player_profiles_job, ingest_player_profiles.py update).
    # last_fetched_at = TIMESTAMP_NTZ ingest heartbeat set on every write. 192h = 8 days.
    # WARN only: player height/weight/position is slow-changing; a missed weekly run is
    # non-critical but a 2-week outage (call-up detection broken) should surface.
    # SOURCE = S3. UNBLOCKED 2026-08-14 by the E11.24 Bundle's `reexport_player_profiles_op`.
    # This was a WRITER gap, not an ordering trail: `ingest_player_profiles.py` writes only
    # Snowflake, and the mirror's only writer (`export_w4_raw_to_s3.py`) is a hand-run W4 build
    # precursor no job ever scheduled — so it had frozen at 2026-06-28 (~1,133h by 08-14, against
    # this 192h threshold). The re-export leaf now runs it downstream of the weekly ingest, so the
    # two sides agree. The 192h threshold is UNCHANGED and still fits: the writer is weekly
    # (`0 10 * * 0` UTC) so a healthy mirror reads ≤~168h, and `last_fetched_at` only advances
    # when a week's people/changes call actually writes rows — exactly as on the Snowflake side.
    "baseball_data.statsapi.player_profiles_raw": {
        "ts_col": "last_fetched_at",  # TIMESTAMP_NTZ; ingest heartbeat
        "max_stale_hours": 192,       # 8 days — weekly update
        "game_day_only": False,
        "non_blocking": True,
        "source": "s3",
    },
    # Matchup-cell sequential posteriors — daily update (update_matchup_cell_posteriors_op).
    # update_ts = datetime.now(UTC) at write time (true ingest heartbeat). 36h mirrors
    # player/team sequential posteriors. WARN only: matchup-cell coverage is sparse
    # mid-season (archetype pairs with thin history) and predictions degrade gracefully.
    # SOURCE = S3. UNBLOCKED 2026-08-14 by the E11.24 Bundle's `reexport_matchup_cell_posteriors_op`
    # + the new `matchup_cell_sequential_posteriors` entry in export_w8b_precursors_to_s3.py. This
    # table had NO S3 prefix at all (verified 2026-08-08: a DuckDB IOException, not a stale read),
    # so the export had to be BUILT. It is ON-DEMAND-ONLY in that exporter and written solely by
    # the re-export leaf, downstream of its writer — adding it to the lk10 default set instead
    # would have created the mirror with the INC-25 trail already installed. See the DATA SOURCE
    # block.
    "baseball_data.betting.matchup_cell_sequential_posteriors": {
        "ts_col": "update_ts",   # TIMESTAMP_NTZ; ingest heartbeat
        "max_stale_hours": 36,
        "game_day_only": False,
        "non_blocking": True,
        "source": "s3",
    },
}

# Entries with no explicit ``source`` default here. Snowflake is the deliberate default: a new
# feed is Snowflake-resident until someone proves an S3 mirror is current, and defaulting the
# OTHER way would silently point a new monitor at a mirror that may not exist.
_DEFAULT_SOURCE = "snowflake"


def entry_source(cfg: dict) -> str:
    return cfg.get("source", _DEFAULT_SOURCE)


def needs_snowflake(thresholds: dict[str, dict] | None = None) -> bool:
    """True if ANY freshness entry still reads Snowflake.

    ``_is_game_day`` is S3 since E11.24 target 3, so once every entry carries
    ``source="s3"`` this returns False and ``run()`` never opens a Snowflake connection —
    the script becomes Snowflake-free (and stops waking COMPUTE_WH) with no further edit.
    """
    cfgs = (thresholds if thresholds is not None else FRESHNESS_THRESHOLDS).values()
    return any(entry_source(cfg) == "snowflake" for cfg in cfgs)


def lakehouse_name(table: str) -> str:
    """``baseball_data.<schema>.<t>`` → ``<t>`` — the bare name the lakehouse stores every
    table under, regardless of which Snowflake schema its native twin lived in."""
    return table.rsplit(".", 1)[-1]

# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------


def _get_connection():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _duck_connection(tables):
    """A registered, Snowflake-free DuckDB connection over the S3 lakehouse.

    ⚠️ PER-TABLE ISOLATION AT **REGISTRATION**, not only at query time (2026-08-14). The batch
    ``register_lakehouse_views`` helper registers every view in one loop, and DuckDB binds a view
    AT CREATE TIME — measured on duckdb 1.5.3, ``CREATE OR REPLACE VIEW … read_parquet(<missing
    prefix>)`` raises ``IOException: No files found that match the pattern`` immediately, it is
    NOT lazy. So a single absent/unreadable S3 prefix used to abort ``_duck_connection`` before
    the first entry was even read, blinding EVERY check — the exact failure the per-table
    try/except in ``run()`` was added to prevent (the savant.batter_pitches decommission
    straggler, 2026-07-06), reproduced one layer earlier where that guard cannot reach.

    This is a live risk for any newly-flipped entry, because a mirror written by a re-export leaf
    does not exist until that leaf's job first RUNS. Registration failures are therefore isolated:
    the offending view is left unregistered, and the per-table read below reports QUERY ERROR for
    that entry ALONE — never a silent OK (a check that did not run is not a pass, NF1.7 (a)).
    ``stg_statsapi_games`` is deliberately NOT special-cased: if the game-day probe cannot be
    registered, ``_is_game_day`` raises and the run fails loudly, which is correct — every
    ``game_day_only`` entry would otherwise be skipped and the monitor would go quietly blind.
    """
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.lakehouse_monitor import duck

    return _register_views_isolated(duck(), tables)


def _register_views_isolated(conn, tables):
    """The isolated registration loop — split out from ``_duck_connection`` so it is TESTABLE.

    ``duck()`` creates a DuckDB S3 SECRET, which needs a live AWS credential chain and therefore
    cannot run in the fast gate (CI mocks all IO). Keeping the loop in a function that takes an
    ALREADY-BUILT connection lets the guard drive this exact code against a plain local DuckDB —
    the real loop, not a re-description of it. Nothing here touches S3; that is ``duck()``'s job.
    """
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils import delta_lakehouse as _dl

    _dl.ensure_delta_extension(conn)
    for name in sorted(set(tables)):
        try:
            # module-attribute lookup, not `from … import` — so the view SQL stays patchable
            conn.execute(f"CREATE OR REPLACE VIEW {name} AS {_dl.lakehouse_view_sql(name)}")
        except Exception as e:  # noqa: BLE001 — one unreadable prefix must not blind the rest
            log.warning(
                "  %-55s VIEW REGISTRATION FAILED (%s) — this table will report QUERY ERROR; "
                "every other check still runs", name, str(e).splitlines()[0][:120])
    return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_game_day(check_date: date, duck_con) -> bool:
    """Return True if there are scheduled games on check_date.

    Reads ``stg_statsapi_games`` — NOT the native statsapi.monthly_schedule, whose writer was
    RETIRED 2026-07-20 when schedule capture went S3-native. Querying the frozen native table
    here would silently return "not a game day" once the last snapshot's forward coverage
    lapsed (~early August) → every game_day_only freshness check would skip → the monitor goes
    blind.

    E11.24 target 3: reads the S3 lakehouse parquet DIRECTLY via DuckDB rather than through the
    Snowflake ``lakehouse_ext.stg_statsapi_games`` external table over that same parquet — same
    artifact, one fewer warehouse hop. ``official_date`` is a real DATE in the parquet (not one
    of the INC-23 VARCHAR-wrapped timestamp columns), but it is cast anyway so a future writer
    type change cannot silently turn this into a string comparison.
    Verdict parity measured 2026-08-08 over 14 consecutive dates (2026-07-26..08-08): identical
    game counts and identical game-day booleans on every one.
    """
    row = duck_con.execute(
        """
        SELECT COUNT(*)
        FROM stg_statsapi_games
        WHERE official_date::date = $d::date
          AND game_type = 'R'
        """,
        {"d": check_date.isoformat()},
    ).fetchone()
    return bool(row and row[0] > 0)


def _max_ingestion_timestamp_s3(
    table: str,
    ts_col: str,
    duck_con,
    eod_offset_hours: int = 0,
    where: str | None = None,
) -> datetime | None:
    """DuckDB-over-S3 twin of ``_max_ingestion_timestamp`` — same contract, same UTC labelling.

    ``table`` is the FQN key from FRESHNESS_THRESHOLDS; the lakehouse stores it under its bare
    name. ``where`` is a trusted constant from FRESHNESS_THRESHOLDS, never user input (same
    contract as the Snowflake twin)."""
    inner = f"MAX({ts_col}::timestamp)"
    if eod_offset_hours:
        inner = f"{inner} + INTERVAL {int(eod_offset_hours)} HOUR"
    sql = f"SELECT {inner} FROM {lakehouse_name(table)}"
    if where:
        sql += f" WHERE {where}"
    row = duck_con.execute(sql).fetchone()
    if row and row[0] is not None:
        ts = row[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


def _max_ingestion_timestamp(
    table: str,
    ts_col: str,
    con,
    eod_offset_hours: int = 0,
    where: str | None = None,
) -> datetime | None:
    """Query MAX of the table's freshness column, optionally offset by eod_offset_hours.

    DATE columns store a calendar date (no timezone). eod_offset_hours shifts the reference
    forward to approximate when the data is actually available — e.g. for game_date columns
    where Statcast publishes the following morning rather than at UTC midnight.

    ``where`` scopes the MAX to a subset of rows — used for SOURCE-scoped freshness
    (e.g. one check per ``data_source`` in a multi-source table), so a single source
    going stale isn't masked by another source keeping the table-level MAX fresh.
    The clause is a trusted constant from FRESHNESS_THRESHOLDS, never user input.

    ✅ ZONE ASSUMPTION — AUDITED AND CONFIRMED CORRECT 2026-07-29 (do not "fix" it).
    The caller labels a naive result UTC (``ts.replace(tzinfo=timezone.utc)``) and diffs it
    against ``now_utc``. That is right only if every ``ts_col`` is UTC-stored, which the
    E11.20 phase-2b freshness-gate defect made worth re-checking (there, a session-local PT
    value was compared against a UTC one and inflated the lag by exactly 7h).
    VERIFIED at the WRITERS, not by inference: all three ``*_sequential_posteriors``
    ``update_ts`` columns are written by
    ``datetime.now(timezone.utc).replace(tzinfo=None)`` (update_{player,team,matchup_cell}
    _posteriors.py) ⇒ naive UTC ⇒ this function is correct as written.
    ⚠️ A wall-clock reading ALONE cannot settle this: max(update_ts)=08:15 with a PT session
    at 08:50 and UTC at 15:50 is equally consistent with "PT, 35 min ago" and "UTC, 7h35m
    ago" — the second is the truth here (the daily writes these ~08:15 UTC). Always confirm
    at the writer before converting a timezone.
    DATE columns (``fit_date``/``as_of_date``) are calendar dates and are unaffected.
    """
    cur = con.cursor()
    inner = f"MAX({ts_col}::TIMESTAMP_NTZ)"
    if eod_offset_hours:
        inner = f"DATEADD(hour, {int(eod_offset_hours)}, {inner})"
    sql = f"SELECT {inner} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    cur.execute(sql)
    row = cur.fetchone()
    if row and row[0] is not None:
        ts = row[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(check_date: date, dry_run: bool = False) -> None:
    now_utc = datetime.now(timezone.utc)

    if dry_run:
        log.info("[DRY RUN] Would check freshness thresholds for date=%s", check_date)
        for table, cfg in FRESHNESS_THRESHOLDS.items():
            log.info("  %s — max_stale_hours=%s game_day_only=%s source=%s",
                     table, cfg["max_stale_hours"], cfg["game_day_only"], entry_source(cfg))
        return

    # E11.24 target 3 — one DuckDB connection for the game-day probe + every source="s3" entry;
    # the Snowflake connection is opened ONLY if an entry still needs it (see needs_snowflake).
    s3_tables = [lakehouse_name(t) for t, c in FRESHNESS_THRESHOLDS.items()
                 if entry_source(c) == "s3"]
    duck_con = _duck_connection(["stg_statsapi_games", *s3_tables])
    con = _get_connection() if needs_snowflake() else None
    if con is None:
        log.info("All freshness entries are S3-sourced — no Snowflake connection opened.")
    try:
        game_day = _is_game_day(check_date, duck_con)
        log.info("Check date: %s — game day: %s", check_date, game_day)

        results: list[dict] = []
        breaches: list[str] = []

        for table, cfg in FRESHNESS_THRESHOLDS.items():
            max_stale_hours: int = cfg["max_stale_hours"]
            game_day_only: bool = cfg["game_day_only"]
            ts_col: str = cfg["ts_col"]
            eod_offset_hours: int = cfg.get("eod_offset_hours", 0)
            non_blocking: bool = cfg.get("non_blocking", False)
            # `table` is the display label / key; `query_table` is the physical table
            # (defaults to the key) and `where` scopes the MAX for source-scoped checks.
            query_table: str = cfg.get("table", table)
            where: str | None = cfg.get("where")
            source: str = entry_source(cfg)

            if game_day_only and not game_day:
                log.info("  %-55s SKIP (off day)", table)
                results.append({"table": table, "status": "SKIP (off day)",
                                "hours_stale": None, "source": source})
                continue

            # Per-table isolation (2026-07-06): a single dropped/renamed/unauthorized object
            # used to raise an uncaught ProgrammingError and crash the WHOLE run — one dead
            # table blinded every other freshness check (the savant.batter_pitches decommission
            # straggler). Catch per-table: record QUERY ERROR, breach only if blocking, continue.
            try:
                if source == "s3":
                    max_ts = _max_ingestion_timestamp_s3(
                        query_table, ts_col, duck_con, eod_offset_hours, where)
                else:
                    max_ts = _max_ingestion_timestamp(
                        query_table, ts_col, con, eod_offset_hours, where)
            except Exception as e:
                log.warning("  %-55s QUERY ERROR (%s)", table, str(e).splitlines()[0][:120])
                results.append({"table": table, "status": "QUERY ERROR",
                                "hours_stale": None, "source": source})
                if not non_blocking:
                    breaches.append(table)
                continue
            if max_ts is None:
                log.warning("  %-55s NO DATA", table)
                results.append({"table": table, "status": "NO DATA",
                                "hours_stale": None, "source": source})
                if not non_blocking:
                    breaches.append(table)
                continue

            hours_stale = (now_utc - max_ts).total_seconds() / 3600
            threshold_exceeded = hours_stale > max_stale_hours
            stale_label = f"STALE ({hours_stale:.1f}h > {max_stale_hours}h)"
            if threshold_exceeded and non_blocking:
                stale_label += " [non-blocking — handled downstream]"
            status = stale_label if threshold_exceeded else f"OK ({hours_stale:.1f}h)"

            log.info("  %-55s [%s] %s", table, source, status)
            results.append({"table": table, "status": status, "hours_stale": hours_stale,
                            "source": source})

            if threshold_exceeded and not non_blocking:
                breaches.append(table)
    finally:
        if con is not None:
            con.close()
        duck_con.close()

    print("\n--- Data Freshness Summary ---")
    col_w = 55
    print(f"{'Table':<{col_w}}  {'Src':<5}  {'Status'}")
    print("-" * (col_w + 37))
    for r in results:
        print(f"{r['table']:<{col_w}}  {r.get('source', '?'):<5}  {r['status']}")

    if breaches:
        print(f"\nFRESHNESS ALERT: {len(breaches)} table(s) exceeded threshold:")
        for t in breaches:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("\nAll freshness checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check ingestion source table freshness against expected thresholds."
    )
    parser.add_argument("--date", default=None,
                        help="Check date in YYYY-MM-DD format (default: today ET)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print thresholds without querying Snowflake")
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        check_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(check_date=check_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

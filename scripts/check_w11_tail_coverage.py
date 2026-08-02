"""
check_w11_tail_coverage.py — the current-slate check for the three blocks the feature-store
coverage gate CANNOT see (INC-37, 2026-08-01).

WHY THIS EXISTS
    `_FEATURE_STORE_COVERAGE_BLOCKS` (the gate `predict_today` runs, and the one
    `check_feature_block_coverage_op` asserts over) covers exactly six blocks — lineup, starter,
    team_rolling, bullpen_eb, sequential, odds. It does NOT cover **umpire, weather or public
    betting**. On 2026-08-01 the month-boundary schedule hole (INC-37) built the whole W11 tail on
    a July-only game universe, so `feature_pregame_weather_features` and
    `feature_pregame_public_betting_features` held **0 of 15** slate games and a front-end table
    had no rows at all — while the coverage gate read a healthy **0.878** and every other monitor
    stayed silent. `check_feature_block_coverage.py` is structurally unable to catch it: it
    EXCLUDES the anchor date and asserts only over dates already in the store, so it is a
    store-HISTORY guard, never a TODAY guard.

    ⇒ "the gate is green" is NOT "the slate is complete". This script is the missing today-guard,
    and it is the mandatory post-step verification after any E11.24 umpire-chain repoint (target
    6a) or ext-table drop (target 7), and after any targeted lakehouse rebuild.

⭐ THE DISCRIMINATION THAT MAKES IT USABLE — a raw feed that has not posted yet is NOT a defect.
    A naive "umpire 0/15 ⇒ CRITICAL" pages every single morning, because the HP-umpire assignment
    is posted in the afternoon; a monitor that cries wolf daily gets muted and is worse than
    nothing (the E11.27 / injury-feed-freshness lesson). So each block is read TWO-sided:

      raw rows for the slate | feature rows for the slate | verdict
      ---------------------- | -------------------------- | -----------------------------------
      > 0                    | 0                          | **BUILD_GAP** — the INC-37 fingerprint:
                             |                            | the feed HAS the slate, the built
                             |                            | feature table does not ⇒ the build ran
                             |                            | on a stale game universe.
      > 0                    | 0 < n < raw-covered        | PARTIAL — degraded, worth a look.
      > 0                    | ≥ raw-covered              | OK
      0                      | 0                          | FEED_PENDING — informational only
                             |                            | (normal pre-assignment / pre-capture).
      0                      | > 0                        | OK (carried from an earlier capture)

    The BUILD_GAP verdict is the one that fires on INC-37 and stays silent on a normal morning.

⏳ WHICH SLATE A BLOCK CAN BE JUDGED ON — read this before wiring a page onto a block.
    "The built table has not caught up with the feed" is a DEFECT only for a block whose feed
    lands BEFORE the build that consumes it. In the daily job the W11 tail is built by
    `lakehouse_w11_nightly_op` (s5c) and two of the three feeds land AFTER it (measured
    2026-08-01 UTC): public_betting's ActionNetwork ingest at 12:00 (s4) precedes the ~12:40
    build, but `ingest_weather` (s7) writes `forecast_pregame` at 12:50 and
    `ingest_umpires.py --date today` (s8/s17) lands at 12:0x–16:39 — both AFTER it. So umpire and
    weather populate the current slate one build cycle late BY DESIGN, and only public_betting is
    a valid same-day assertion. `betting_ml/monitoring/w11_tail_coverage.py` owns that policy for
    the daily op (same-day for public_betting, the PRIOR slate for umpire/weather) — the same
    exemption `check_feature_block_coverage._DATE_OUTAGE_SKIP_NEWEST` already makes for the same
    reason. This CLI still reports every block for whatever date you give it: as a post-rebuild
    acceptance gate you are asking "did the rebuild I just ran cover this slate", which is a
    different (and legitimately stricter) question than the daily monitor's.

TIER (E11.7): ALERT-loud-but-continue by default — it never exits non-zero, because a blank
    transparency panel must not withhold a slate's predictions. `--strict` escalates to exit 1 for
    an operator running it as an explicit acceptance gate after a rebuild/flip. The daily
    `check_w11_tail_coverage_op` runs this script and pages via send_alert on the same verdicts.

Snowflake-FREE: DuckDB over the S3 lakehouse (`register_lakehouse_views` for the built tables — a
    hardcoded glob is the 2026-07-20 phase-1.5 P0 — and `lh_raw()` for the raw mirrors).

Usage (LAPTOP or BOX; add `-e AWS_DEFAULT_REGION=us-east-2` when exec'ing on the box):
    uv run python scripts/check_w11_tail_coverage.py
    uv run python scripts/check_w11_tail_coverage.py --date 2026-08-01
    uv run python scripts/check_w11_tail_coverage.py --date 2026-08-01 --strict
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.game_day import current_game_date  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# The three feature blocks the six-block coverage gate does not measure, each with the raw mirror
# that proves whether the feed has the slate at all. `raw_key` is the join column against the
# slate: umpire/weather carry game_pk; public_betting_raw carries only ActionNetwork's own id and
# a game_date, so it is matched on the date.
#
# ⚠️ `raw_filter` must match what the FEATURE BUILD actually consumes, or the two-sided read is
# broken from the raw side. weather_raw holds three observation types and
# `stg_weather_raw_snapshots` (the model feeding feature_pregame_weather_features) selects
# `weather_observation_type='forecast_pregame'` ONLY — the 00:00–02:00 UTC `forecast_intraday`
# rows are rejected by design. Counting them as "the feed has the slate" would report a
# permanent BUILD_GAP/PARTIAL against a table that was never going to contain them.
BLOCKS = (
    ("umpire", "feature_pregame_umpire_features", "umpire_game_log", "game_pk", None),
    ("weather", "feature_pregame_weather_features", "weather_raw", "game_pk",
     "weather_observation_type = 'forecast_pregame'"),
    ("public_betting", "feature_pregame_public_betting_features", "public_betting_raw",
     "game_date", None),
)


@dataclass
class BlockCoverage:
    """One W11-tail block's two-sided read of a single slate."""
    block: str
    slate_games: int
    raw_games: int      # slate games the RAW feed has (or raw rows for the date, when date-keyed)
    feature_games: int  # slate games present in the BUILT feature table

    @property
    def verdict(self) -> str:
        if self.slate_games == 0:
            return "NO_SLATE"
        if self.feature_games == 0 and self.raw_games > 0:
            return "BUILD_GAP"        # ⬅ the INC-37 fingerprint
        if self.feature_games == 0:
            return "FEED_PENDING"     # informational — the feed simply has not posted yet
        if self.raw_games > 0 and self.feature_games < self.raw_games:
            return "PARTIAL"
        return "OK"

    @property
    def is_problem(self) -> bool:
        """Only BUILD_GAP and PARTIAL are defects. FEED_PENDING is the normal morning state and
        must never page, or the monitor gets muted (see the module docstring)."""
        return self.verdict in ("BUILD_GAP", "PARTIAL")


def _fetch(served_date: date) -> list[BlockCoverage]:
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck, lh_raw

    conn = duck()
    out: list[BlockCoverage] = []
    try:
        register_lakehouse_views(conn, ["stg_statsapi_games", *(b[1] for b in BLOCKS)])
        # The slate. `official_date` is a real DATE (the INC-23 VARCHAR bite is on `game_date`),
        # and POSTPONED rows are excluded — a rained-out game is abstractGameState='Final' and
        # its makeup REUSES the gamePk, so counting it inflates the denominator (2026-07-19).
        slate_sql = """
            select distinct game_pk from stg_statsapi_games
            where official_date::date = ?::date
              and coalesce(detailed_state, '') <> 'Postponed'
        """
        slate_games = conn.execute(
            f"select count(*) from ({slate_sql})", [served_date.isoformat()]
        ).fetchone()[0]

        for block, feature_table, raw_table, raw_key, raw_filter in BLOCKS:
            where_raw = f"where {raw_filter}" if raw_filter else ""
            if raw_key == "game_pk":
                raw_games = conn.execute(
                    f"""select count(distinct s.game_pk) from ({slate_sql}) s
                        where s.game_pk in (
                          select game_pk from read_parquet('{lh_raw(raw_table)}', union_by_name=true)
                          {where_raw}
                        )""",
                    [served_date.isoformat()],
                ).fetchone()[0]
            else:
                # Date-keyed raw (public_betting_raw has no game_pk). `game_date` in a raw mirror
                # may be a string-wrapped timestamp — cast at the use-site (INC-23).
                raw_rows = conn.execute(
                    f"""select count(*) from read_parquet('{lh_raw(raw_table)}', union_by_name=true)
                        where try_cast(game_date as date) = ?::date
                        {f'and {raw_filter}' if raw_filter else ''}""",
                    [served_date.isoformat()],
                ).fetchone()[0]
                # Cap at the slate so the "feature < raw" PARTIAL test compares like with like.
                raw_games = min(raw_rows, slate_games)

            feature_games = conn.execute(
                f"""select count(distinct s.game_pk) from ({slate_sql}) s
                    where s.game_pk in (select game_pk from {feature_table})""",
                [served_date.isoformat()],
            ).fetchone()[0]

            out.append(BlockCoverage(block, slate_games, raw_games, feature_games))
    finally:
        conn.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="game date (default: today's US baseball day)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on a BUILD_GAP/PARTIAL block (acceptance-gate mode)")
    args = ap.parse_args()

    served = date.fromisoformat(args.date) if args.date else current_game_date()
    # INC-39 — STAMP THE SLATE THIS OUTPUT IS ABOUT, on EVERY exit path.
    # The per-block `[METRIC]` lines carry no date, so a consumer parsing them could not tell
    # WHICH slate they described: replayed, stale or synthetic output parsed identically to a
    # live read of the requested date, and `check_w11_tail_coverage_op` would page CRITICAL on
    # it. (That is how a 2026-08-02 CRITICAL "public_betting BUILD_GAP 0/15" reached the inbox
    # while the built table actually held 15/15 — the numbers were real, the SLATE was not.)
    # Printed before the read so it survives a failure, and unconditionally so the op's
    # cross-check can never be vacuously satisfied by an absent line (NF1.7 (a)).
    print(f"[METRIC] w11_tail_date={served.isoformat()}")
    try:
        blocks = _fetch(served)
    except Exception as exc:  # noqa: BLE001 — ALERT tier: report loudly, never take a slate down
        log.warning("[ALERT] w11_tail check could not run for %s: %s", served, exc)
        print("[METRIC] w11_tail_evaluated=0")
        return 1 if args.strict else 0

    print(f"\nW11 serving tail — {served} (the three blocks the coverage gate cannot see)\n")
    print(f"  {'block':<16}{'slate':>7}{'raw':>7}{'feature':>9}   verdict")
    for b in blocks:
        print(f"  {b.block:<16}{b.slate_games:>7}{b.raw_games:>7}{b.feature_games:>9}   {b.verdict}")

    problems = [b for b in blocks if b.is_problem]
    print("\n[METRIC] w11_tail_evaluated=1")
    print(f"[METRIC] w11_tail_problem_count={len(problems)}")
    for b in blocks:
        print(f"[METRIC] w11_tail_{b.block}_covered={b.feature_games}/{b.slate_games} "
              f"verdict={b.verdict}")

    if problems:
        for b in problems:
            log.warning(
                "[ALERT] W11 tail %s: %d/%d slate games in %s while the raw feed has %d — %s",
                b.block, b.feature_games, b.slate_games,
                {x[0]: x[1] for x in BLOCKS}[b.block], b.raw_games,
                "the BUILD ran on a stale game universe (the INC-37 fingerprint)"
                if b.verdict == "BUILD_GAP" else "partially built",
            )
        return 1 if args.strict else 0

    log.info("W11 tail OK for %s (pending feeds are informational, not defects)", served)
    return 0


if __name__ == "__main__":
    sys.exit(main())

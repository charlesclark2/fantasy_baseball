"""
check_odds_coverage.py — durable odds-coverage data-quality guard.

WHY THIS EXISTS (2026-07-02 incident):
    After the E11.1 lakehouse cutover, `mart_game_odds_bridge` silently froze at
    2026-06-30 while its two inputs stayed fresh — `mart_game_spine` reached
    2026-07-04 and `mart_odds_outcomes` reached 2026-07-02. The bridge is the join
    that attaches odds `event_id`s to scheduled games, so a frozen bridge means
    `has_odds = false` for the entire current slate → predictions run MARKET-BLIND
    with no error, no null-alert, nothing. The odds were physically present on both
    sides of the join; only the bridge parquet had not been rebuilt (its last build
    happened while the spine was itself frozen, so it carried the spine's old
    horizon). See E1_11_BUG_feature_correctness.md (Defect 3).

WHAT IT CHECKS:
    For today's US baseball date (game_day.current_game_date) and a short forward
    horizon (the spine schedules a few days ahead), per date D:
        spine_games      = scheduled regular-season games in mart_game_spine
        odds_events      = distinct Odds-API events in mart_odds_outcomes
        bridge_games     = rows in mart_game_odds_bridge
        bridge_with_odds = rows with has_odds = true
    and classifies D:
        FREEZE       spine_games>0 AND odds_events>0 AND bridge_with_odds=0
                     → odds AND games exist but NOTHING attached. This is the
                       incident signature — an unambiguous pipeline failure (the
                       bridge did not rebuild), NOT a books-haven't-posted timing
                       issue. Fatal under --strict.
        PARTIAL      0 < bridge_with_odds < min_coverage * spine_games  → WARN.
        NO_ODDS_YET  spine_games>0 AND odds_events=0 → books have not posted for D
                     yet (normal for forward dates / very early morning). Benign.
        OK           bridge_with_odds >= min_coverage * spine_games.

    The FREEZE test keys off `odds_events > 0`, so it can NEVER false-fire when odds
    simply have not posted — that path is NO_ODDS_YET. This is what makes it safe to
    eventually run at HALT tier.

TIER (pipeline failure-handling contract):
    Default = ALERT-loud-but-continue: prints a loud stderr WARNING but exits 0, so
    it can never take down serving during rollout (RUNTIME GATE — validate on the box
    first). Pass --strict (or set ODDS_COVERAGE_STRICT=1) to exit 1 on a FREEZE of the
    CURRENT slate, promoting it to HALT once validated. Forward-date issues are always
    non-fatal (they are dominated by NO_ODDS_YET).

Usage:
    uv run python scripts/check_odds_coverage.py --env prod
    uv run python scripts/check_odds_coverage.py --env prod --strict
    uv run python scripts/check_odds_coverage.py --env dev --date 2026-07-02 --horizon 2
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.game_day import current_game_date

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# A date is "covered" when at least this fraction of its scheduled games carry odds.
# Books do not always post every game simultaneously, so a small shortfall is normal;
# a hard floor catches the catastrophic 0-attach (FREEZE) and gross partials.
_MIN_COVERAGE = 0.50


def _mart_schema(env: str) -> str:
    """Served mart schema (the odds/spine marts are VIEWS over lakehouse_ext here)."""
    return "baseball_data.betting" if env == "prod" else "baseball_data.dev_betting"


def _classify(spine_games: int, odds_events: int, bridge_with_odds: int) -> str:
    if spine_games == 0:
        return "OFF_DAY"
    if odds_events == 0:
        return "NO_ODDS_YET"
    if bridge_with_odds == 0:
        return "FREEZE"
    if bridge_with_odds < _MIN_COVERAGE * spine_games:
        return "PARTIAL"
    return "OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="Odds-coverage DQ guard (bridge freeze detector)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod",
                        help="Environment whose served mart schema to check. Default: prod.")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Anchor date (the current slate). Default: current US baseball date.")
    parser.add_argument("--horizon", type=int, default=2,
                        help="Forward days to also report (the spine schedules ahead). Default: 2.")
    parser.add_argument("--strict", action="store_true",
                        default=os.environ.get("ODDS_COVERAGE_STRICT") == "1",
                        help="Exit 1 (HALT) on a FREEZE of the CURRENT slate. "
                             "Default from ODDS_COVERAGE_STRICT env (=1 to enable).")
    args = parser.parse_args()

    anchor = date.fromisoformat(args.date) if args.date else current_game_date()
    end = anchor + timedelta(days=max(0, args.horizon))
    mart = _mart_schema(args.env)
    log.info(f"[{args.env.upper()}] odds-coverage check — anchor {anchor}, "
             f"window {anchor}..{end}, min_coverage {_MIN_COVERAGE:.0%}, strict={args.strict}")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            with spine as (
                select game_date::date as d, count(*) as spine_games
                from {mart}.mart_game_spine
                where game_type = 'R' and game_date >= '{anchor}' and game_date <= '{end}'
                group by 1
            ),
            outcomes as (
                select commence_date::date as d, count(distinct event_id) as odds_events
                from {mart}.mart_odds_outcomes
                where commence_date >= '{anchor}' and commence_date <= '{end}'
                group by 1
            ),
            bridge as (
                select game_date::date as d,
                       count(*) as bridge_games,
                       sum(case when has_odds then 1 else 0 end) as bridge_with_odds
                from {mart}.mart_game_odds_bridge
                where game_date >= '{anchor}' and game_date <= '{end}'
                group by 1
            )
            select coalesce(s.d, o.d, b.d) as d,
                   coalesce(s.spine_games, 0)      as spine_games,
                   coalesce(o.odds_events, 0)      as odds_events,
                   coalesce(b.bridge_games, 0)     as bridge_games,
                   coalesce(b.bridge_with_odds, 0) as bridge_with_odds
            from spine s
            full outer join outcomes o on s.d = o.d
            full outer join bridge   b on coalesce(s.d, o.d) = b.d
            order by 1
        """)
        rows = [dict(zip([c[0].lower() for c in cur.description], r)) for r in cur.fetchall()]
    finally:
        conn.close()

    by_date = {str(r["d"]): r for r in rows}
    anchor_iso = anchor.isoformat()

    current_freeze = False
    for d_iso in sorted(by_date):
        r = by_date[d_iso]
        sg, oe = int(r["spine_games"]), int(r["odds_events"])
        bg, bo = int(r["bridge_games"]), int(r["bridge_with_odds"])
        status = _classify(sg, oe, bo)
        is_current = d_iso == anchor_iso
        tag = " <== CURRENT SLATE" if is_current else ""
        msg = (f"  {d_iso}: spine={sg:2d} games, odds_events={oe:2d}, "
               f"bridge={bg:2d} ({bo:2d} w/odds)  [{status}]{tag}")
        if status == "FREEZE":
            log.error(msg + " — odds & games EXIST but ZERO attached (bridge did not rebuild)")
            if is_current:
                current_freeze = True
        elif status == "PARTIAL":
            log.warning(msg + f" — below {_MIN_COVERAGE:.0%} coverage")
        elif status == "NO_ODDS_YET":
            (log.warning if is_current else log.info)(msg + " — books have not posted yet")
        else:
            log.info(msg)

    # Coverage score for the current slate (Dagster metadata / observability).
    cur_row = by_date.get(anchor_iso)
    if cur_row and int(cur_row["spine_games"]) > 0:
        score = int(cur_row["bridge_with_odds"]) / int(cur_row["spine_games"])
    else:
        score = 1.0  # off-day / no slate → nothing to attach; not a failure.
    print(f"[METRIC] odds_coverage_score={score:.4f}")

    if current_freeze:
        banner = ("ODDS BRIDGE FREEZE on the CURRENT slate — mart_game_odds_bridge has 0 "
                  "has_odds rows for today despite fresh spine + outcomes. Predictions will run "
                  "MARKET-BLIND. Remediate: rebuild the bridge off the fresh spine "
                  "(run_w1_lakehouse.py --w6-odds-current + refresh_w1_external_tables.py --w6-odds) "
                  "and confirm the spine (--w5-group-a) rebuild runs daily BEFORE --w6.")
        if args.strict:
            log.error("[HALT] " + banner)
            return 1
        log.warning("[ALERT] " + banner + "  (non-blocking: set ODDS_COVERAGE_STRICT=1 to HALT.)")
        return 0

    log.info("Odds coverage OK for the current slate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

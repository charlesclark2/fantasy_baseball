"""
check_served_prediction_integrity.py — E11.22 served-prediction integrity gate.

WHY THIS EXISTS (E11.22 capstone / INC-24):
    The lakehouse migration's recurring failure mode is SILENT feature corruption at
    SERVE time that row-count parity does NOT catch and the standing 30-day model-health
    sensor only surfaces WEEKS later (downstream, via a discrimination collapse):
      - INC-22  → served the WRONG game-date (box UTC "today" rolled to tomorrow after
                  ~00:00 UTC) → an empty / mis-dated slate.
      - INC-25 / spine-freeze → load_todays_features fails its coverage gate → predict
                  SILENTLY falls back to intraday assembly (data_source='intraday_fallback'),
                  a degraded, patchy slate — no HALT, no alarm.
      - INC-17-P2 → a lineup-gated block goes NULL on post_lineup → feature_coverage_score
                  collapses → the classifier's discrimination collapses.
      - INC-24  → market-blind / constant-imputed features → the model output goes FLAT
                  (the observed signature: total_runs spread 0.447, home_win at the no-skill
                  floor over the migration window with odds capture down).
    Every one of these shows up in TODAY's written `daily_model_predictions` the day it
    happens. This guard reads that table immediately after predict and ALARMS at the
    input/output boundary — PER SERVING TIER — so the next silent null/zero/stale/mis-date
    is caught the SAME MORNING, not discovered downstream weeks later. It is the permanent
    "input-integrity monitor" DO #5 of E11.22, complementing the feature-STORE block guard
    (check_feature_block_coverage.py, which watches the store) and the 30-day model-health
    sensor (which lags): this one watches what the model ACTUALLY served today.

WHAT IT CHECKS (per prediction_type / serving tier that has rows for the served date):
    1. DATE      no predictions dated beyond the current US baseball date (INC-22 — the
                 UTC-roll "served tomorrow" signature; the correct date is anchored by
                 game_day.current_game_date(), never utcnow().date()).
    2. FALLBACK  fraction of the slate served from the feature store
                 (data_source='feature_store') ≥ MIN_FEATURE_STORE_FRAC — a slate that
                 fell to intraday_fallback is degraded (INC-25 / spine-freeze class).
    3. COVERAGE  (post_lineup only) avg feature_coverage_score ≥ the tier floor — a
                 lineup-gated block going null is the INC-17-P2 signature. Reuses the
                 model-health POST_LINEUP_AVG_COVERAGE_THRESHOLD verbatim.
    4. FLAT      std of each target's prediction across the slate ≥ the model-health
                 MIN_SPREAD_* floor (the INC-24 flat-output signature). An all-NULL target
                 column on an otherwise-serving tier is flagged as "target not served".

    Thresholds are IMPORTED from betting_ml.monitoring.model_health_metrics so this
    serve-time guard and the standing 30-day gate can NEVER drift apart.

TIER (E11.7 pipeline failure-handling contract):
    Default = ALERT-loud-but-continue (RUNTIME-GATE-safe rollout): a loud stderr WARNING,
    exit 0 — it can never take down serving during rollout. Pass --strict (or set
    SERVED_INTEGRITY_STRICT=1) to exit 1 (HALT) once validated on the box.

Usage:
    uv run python scripts/check_served_prediction_integrity.py --env prod
    uv run python scripts/check_served_prediction_integrity.py --env prod --strict
    uv run python scripts/check_served_prediction_integrity.py --env dev --date 2026-07-06
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.game_day import current_game_date
# Import the EXACT thresholds the standing 30-day gate uses so serve-time and 30-day
# can never disagree about what "flat" / "coverage collapse" means.
from betting_ml.monitoring.model_health_metrics import (
    MIN_SPREAD_PROB,
    MIN_SPREAD_TOTALS,
    MIN_SPREAD_RUNDIFF,
    POST_LINEUP_AVG_COVERAGE_THRESHOLD,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# A tier needs at least this many served games before we assess it — a tiny/empty slate
# (early season, doubleheader-only, an off-morning re-score) can't support a spread verdict.
MIN_GAMES_FOR_CHECK = 5
# Below this fraction served from the feature store, the slate degraded to intraday_fallback.
MIN_FEATURE_STORE_FRAC = 0.80


@dataclass
class TierStat:
    """Per-serving-tier aggregate over today's served slate (one prediction_type)."""
    tier: str
    n: int
    feature_store_frac: float | None
    avg_coverage: float | None
    spread_win_prob: float | None      # std(calibrated_win_prob)
    spread_total_runs: float | None    # std(pred_total_runs)
    spread_run_diff: float | None      # std(pred_run_diff_loc)


def evaluate_tier(
    stat: TierStat,
    *,
    min_games: int = MIN_GAMES_FOR_CHECK,
    min_feature_store_frac: float = MIN_FEATURE_STORE_FRAC,
    min_coverage: float = POST_LINEUP_AVG_COVERAGE_THRESHOLD,
    min_spread_prob: float = MIN_SPREAD_PROB,
    min_spread_totals: float = MIN_SPREAD_TOTALS,
    min_spread_rundiff: float = MIN_SPREAD_RUNDIFF,
) -> list[str]:
    """Pure classifier: given one tier's aggregates, return the list of integrity problems
    (empty = healthy). No IO — unit-tested directly with synthetic TierStats."""
    problems: list[str] = []
    if stat.n < min_games:
        return problems  # too few served games to assess this tier

    # (2) FALLBACK — INC-25 / spine-freeze: the slate silently dropped to intraday assembly.
    if stat.feature_store_frac is not None and stat.feature_store_frac < min_feature_store_frac:
        problems.append(
            f"{stat.tier}: only {stat.feature_store_frac:.0%} of the slate served from the "
            f"feature store (< {min_feature_store_frac:.0%}) — it fell to intraday_fallback "
            f"(INC-25 / spine-freeze class: a served S3 parquet froze / the store coverage gate failed)"
        )

    # (3) COVERAGE — INC-17-P2: a lineup-gated block went null on post_lineup.
    if stat.tier == "post_lineup" and stat.avg_coverage is not None and stat.avg_coverage < min_coverage:
        problems.append(
            f"{stat.tier}: avg feature_coverage_score {stat.avg_coverage:.2f} < {min_coverage:.2f} "
            f"— a lineup/matchup block went null (INC-17-P2 class)"
        )

    # (4) FLAT — INC-24: near-constant / all-null target output on the served slate.
    # A tier is genuinely serving if at least one core target has a real (non-null) spread;
    # only then is an all-null column on another target a corruption (vs a tier that simply
    # doesn't emit that target).
    spreads = {
        "home_win(calibrated_win_prob)": (stat.spread_win_prob, min_spread_prob),
        "total_runs(pred_total_runs)": (stat.spread_total_runs, min_spread_totals),
        "run_differential(pred_run_diff_loc)": (stat.spread_run_diff, min_spread_rundiff),
    }
    tier_is_serving = any(s is not None for s, _ in spreads.values())
    for label, (spread, floor) in spreads.items():
        if spread is None:
            if tier_is_serving:
                problems.append(
                    f"{stat.tier}: {label} is ALL-NULL across the served slate — target not served "
                    f"(a served target column materialized 100% NULL)"
                )
        elif spread < floor:
            problems.append(
                f"{stat.tier}: {label} spread {spread:.3f} < {floor} (FLAT output — market-blind / "
                f"constant-imputed features, the INC-24 signature)"
            )
    return problems


def _pred_schema(env: str) -> str:
    # daily_model_predictions is a KEPT Snowflake table (the Cortex decision carrier — on the
    # decommission STAY list), so it is read directly from Snowflake here, not the S3 mirror
    # (which is written later in the daily job and would lag the just-written rows).
    return "baseball_data.betting_ml" if env == "prod" else "baseball_data.dev_betting_ml"


def _fetch_tier_stats(conn, schema: str, served_date: date) -> tuple[list[TierStat], int]:
    """Per-prediction_type aggregates for the served date, plus the count of any rows dated
    BEYOND the served date (the INC-22 'served tomorrow' signature)."""
    cur = conn.cursor()
    cur.execute(
        f"""
        select
            prediction_type,
            count(*)                                            as n,
            avg(iff(data_source = 'feature_store', 1, 0))       as feature_store_frac,
            avg(feature_coverage_score)                         as avg_coverage,
            stddev(calibrated_win_prob)                         as spread_win_prob,
            stddev(pred_total_runs)                             as spread_total_runs,
            stddev(pred_run_diff_loc)                           as spread_run_diff
        from {schema}.daily_model_predictions
        where score_date = %(d)s
        group by prediction_type
        """,
        {"d": served_date},
    )
    stats: list[TierStat] = []
    for row in cur.fetchall():
        (tier, n, fsf, cov, sw, st, sr) = row
        stats.append(TierStat(
            tier=str(tier),
            n=int(n),
            feature_store_frac=None if fsf is None else float(fsf),
            avg_coverage=None if cov is None else float(cov),
            spread_win_prob=None if sw is None else float(sw),
            spread_total_runs=None if st is None else float(st),
            spread_run_diff=None if sr is None else float(sr),
        ))
    # INC-22: any prediction dated after the current US baseball date is a clock/date-roll bug.
    cur.execute(
        f"""
        select count(*)
        from {schema}.daily_model_predictions
        where score_date > %(d)s
        """,
        {"d": served_date},
    )
    future_rows = int(cur.fetchone()[0])
    cur.close()
    return stats, future_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Served-prediction integrity gate (per-tier flat/fallback/coverage/date guard)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Served date to inspect. Default: current US baseball date.")
    parser.add_argument("--strict", action="store_true",
                        default=os.environ.get("SERVED_INTEGRITY_STRICT") == "1",
                        help="Exit 1 (HALT) on any integrity problem. "
                             "Default from SERVED_INTEGRITY_STRICT env (=1 to enable).")
    args = parser.parse_args()

    served_date = date.fromisoformat(args.date) if args.date else current_game_date()
    schema = _pred_schema(args.env)
    log.info(f"[{args.env.upper()}] served-prediction integrity — served_date={served_date}; "
             f"strict={args.strict}")

    conn = get_snowflake_connection()
    try:
        stats, future_rows = _fetch_tier_stats(conn, schema, served_date)
    finally:
        conn.close()

    problems: list[str] = []

    # (1) DATE — INC-22: predictions dated beyond today = a UTC-roll / clock bug.
    if future_rows > 0:
        problems.append(
            f"{future_rows} prediction row(s) dated AFTER {served_date} — a served-date roll "
            f"(INC-22: the box served a future/UTC 'today' instead of the US baseball date)"
        )

    if not stats:
        # No predictions for today. This is either a genuine off-day or an empty serve; the
        # empty-serve-vs-off-day distinction is check_prediction_coverage's job (it joins the
        # schedule). Here we only assess integrity of rows that DO exist — benign, never a HALT.
        print("[METRIC] served_integrity_problem_count=%d" % len(problems))
        if problems:
            _emit(problems, args.strict)
            return 1 if args.strict else 0
        log.info(f"No predictions for {served_date} yet — nothing to assess "
                 f"(coverage/off-day is check_prediction_coverage's domain).")
        print("[METRIC] served_integrity_problem_count=0")
        return 0

    assessed = 0
    for stat in sorted(stats, key=lambda s: s.tier):
        tier_problems = evaluate_tier(stat)
        if stat.n < MIN_GAMES_FOR_CHECK:
            log.info(f"  tier '{stat.tier}': n={stat.n} (< {MIN_GAMES_FOR_CHECK}) — too small to assess.")
            continue
        assessed += 1
        cov = "—" if stat.avg_coverage is None else f"{stat.avg_coverage:.2f}"
        fsf = "—" if stat.feature_store_frac is None else f"{stat.feature_store_frac:.0%}"
        sw = "—" if stat.spread_win_prob is None else f"{stat.spread_win_prob:.3f}"
        st = "—" if stat.spread_total_runs is None else f"{stat.spread_total_runs:.2f}"
        sr = "—" if stat.spread_run_diff is None else f"{stat.spread_run_diff:.2f}"
        head = (f"  tier '{stat.tier}': n={stat.n}, feature_store={fsf}, coverage={cov}, "
                f"spread[win_prob={sw}, total_runs={st}, run_diff={sr}]")
        if tier_problems:
            log.error(head + "  [PROBLEM]")
            problems.extend(tier_problems)
        else:
            log.info(head + "  [OK]")

    print(f"[METRIC] served_integrity_problem_count={len(problems)}")
    print(f"[METRIC] served_integrity_tiers_assessed={assessed}")

    if problems:
        _emit(problems, args.strict)
        return 1 if args.strict else 0

    log.info(f"Served-prediction integrity OK across {assessed} tier(s) for {served_date}.")
    return 0


def _emit(problems: list[str], strict: bool) -> None:
    banner = (
        "SERVED-PREDICTION INTEGRITY problem(s) on today's slate — the model served a "
        "degraded/flat/mis-dated feature vector (E11.22 input-integrity guard): "
        + " | ".join(problems)
        + ". Investigate with: rescore_audit --since <date> --compare-live (serving-gap vs "
        "genuine-flat), check load_todays_features coverage gate + the W8a/W8b served parquet "
        "freshness, and the odds/feature-block coverage guards."
    )
    if strict:
        log.error("[HALT] " + banner)
    else:
        log.warning("[ALERT] " + banner + "  (non-blocking: set SERVED_INTEGRITY_STRICT=1 to HALT.)")


if __name__ == "__main__":
    sys.exit(main())

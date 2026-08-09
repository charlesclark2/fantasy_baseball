"""
check_prediction_coverage.py
-----------------------------
Verify that daily_model_predictions has a row for every scheduled game with
has_full_lineup = true. Exits non-zero if coverage < 90%.

Usage:
    uv run python scripts/check_prediction_coverage.py
    uv run python scripts/check_prediction_coverage.py --date 2026-05-01
    uv run python scripts/check_prediction_coverage.py --min-coverage 0.85

DATA SOURCE — Snowflake-FREE since E11.24 target 3 (2026-08-08):
    Reads the schedule (`stg_statsapi_games`) and the served predictions
    (`daily_model_predictions`) from the S3 lakehouse parquet via DuckDB. It ran at 100%
    wake (~1.1 COMPUTE_WH resumes/day — essentially every execution RESUMED the warehouse),
    which is what E11.24 is retiring.

    ⚠️ THIS IS THE HIGHEST-CONSEQUENCE GUARD IN THE CLUSTER — it is HALT-tier and
    UNCONDITIONAL (no --strict gate, no try/except in its op), so a wrong verdict FAILS
    `daily_ingestion_job` and pages CRITICAL. Verdict parity was measured before the
    repoint, SF-vs-S3, on 8 consecutive real slates (2026-08-01..08-08): identical
    expected/scored counts, identical coverage verdict, and identical
    feature_coverage_score / data_source breakdown on every one — including 08-01 (the
    INC-37 month-boundary slate, where BOTH sides agree n_feature_store=2 of 15).

    ⭐ WHY READING THE MIRROR IS THE RIGHT SOURCE, not merely an equivalent one: the S3
    `daily_model_predictions` parquet is what `write_serving_store --s3` / `write_api_cache`
    actually SERVE from (predict_today writes Snowflake, then re-exports to S3 inside the
    same op). Asserting coverage on the parquet therefore asserts on the artifact the user
    sees, one step closer to the truth than the Snowflake table did.
    ⚠️ ORDERING (INC-25): that re-export runs INSIDE `predict_today_morning`, and this check
    is `s20`, downstream of it — so the mirror is always fresh by the time we read. It is
    gated on `_w7b_mirror_on()` (`W7B_LAKEHOUSE_S3=1`, which is enforced via `env.required`
    + the `check_monitors_healthy_op` heartbeat). If that flag is ever rolled back, serving
    reverts to Snowflake AND the mirror stops advancing → this guard would report 0 scored
    games. That is not silent: the zero-coverage banner below explicitly names the mirror as
    a candidate cause so the operator is not sent hunting for a predict failure that did not
    happen.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DEFAULT_MIN_COVERAGE = 0.90
# A1.10 — non-blocking warn threshold on the mean feature_coverage_score. Set
# below the intraday-assembly steady-state (~0.77 — carry-forward team blocks +
# overlaid lineup/starter) so it fires on genuine regression, not every day. The
# durable schedule-spined feature store (A1.11) should reach ~1.0.
DEFAULT_MIN_FEATURE_COVERAGE = 0.70

_TABLES = ("stg_statsapi_games", "daily_model_predictions")

# ---------------------------------------------------------------------------
# S3 lakehouse reads (DuckDB) — see the DATA SOURCE note in the module docstring
# ---------------------------------------------------------------------------

# A1.10 — expected games come from the SCHEDULE (forward-looking), not
# feature_pregame_game_features. The feature mart is spined on completed games and has zero
# rows for today, which previously made this check a silent daily no-op
# (expected_games == 0 → "skipped").
_EXPECTED_SQL = """
    SELECT COUNT(DISTINCT game_pk) AS expected_games
    FROM stg_statsapi_games
    WHERE official_date::date = $d::date
      AND game_type = 'R'
"""

_SCORED_SQL = """
    SELECT COUNT(DISTINCT game_pk) AS scored_games
    FROM daily_model_predictions
    WHERE game_date::date = $d::date
"""

# Summarize the LATEST row per game (what the app actually serves) so the counts reflect the
# current prediction set, not stale earlier runs (morning / a prior intraday_fallback) that
# also exist for the date.
_FEATURE_SQL = """
    WITH latest AS (
        SELECT game_pk, data_source, feature_coverage_score
        FROM daily_model_predictions
        WHERE game_date::date = $d::date
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY game_pk ORDER BY inserted_at DESC
        ) = 1
    )
    SELECT
        AVG(feature_coverage_score)                      AS avg_cov,
        MIN(feature_coverage_score)                      AS min_cov,
        COUNT_IF(data_source = 'feature_store')          AS n_feature_store,
        COUNT_IF(data_source = 'intraday_assembly')      AS n_assembly,
        COUNT_IF(data_source = 'intraday_fallback')      AS n_fallback,
        COUNT(DISTINCT game_pk)                          AS n_games
    FROM latest
"""

# Only read when coverage is ZERO — turns "predict never ran" into a distinguishable
# diagnosis from "the S3 predictions mirror stopped advancing" (see the ORDERING note).
_MIRROR_HORIZON_SQL = "SELECT MAX(game_date::date) FROM daily_model_predictions"


def _connect():
    """A registered, Snowflake-free DuckDB connection over the S3 lakehouse."""
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, _TABLES)
    return conn


def _feature_source_summary(conn, check_date: date) -> dict | None:
    """A1.10 — mean feature_coverage_score + data_source breakdown for the date.

    Returns None when the columns don't exist yet (first deploy) so the core
    coverage check still runs. Defensive: any error degrades to None.
    """
    try:
        r = conn.execute(_FEATURE_SQL, {"d": check_date.isoformat()}).fetchone()
        if not r or not r[5]:
            return None
        return {
            "avg_cov": r[0], "min_cov": r[1],
            "n_feature_store": r[2], "n_assembly": r[3], "n_fallback": r[4],
            "n_games": r[5],
        }
    except Exception as exc:  # column not yet present, etc.
        log.warning("feature-source summary unavailable (%s)", exc)
        return None


def run(
    check_date: date,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    min_feature_coverage: float = DEFAULT_MIN_FEATURE_COVERAGE,
    conn=None,
) -> None:
    """``conn`` is an OPTIONAL pre-registered DuckDB connection — the seam the guard tests use
    to drive this EXACT code path over seeded fixtures (so the negative verdict is proven, not
    assumed). Production passes nothing and gets the S3 lakehouse."""
    owned = conn is None
    if owned:
        conn = _connect()
    try:
        row = conn.execute(_EXPECTED_SQL, {"d": check_date.isoformat()}).fetchone()
        expected_games = row[0] if row else 0

        if expected_games == 0:
            log.info("No regular-season games scheduled on %s — skipping coverage check.", check_date)
            print(f"No games scheduled on {check_date}. Coverage check skipped.")
            return

        row = conn.execute(_SCORED_SQL, {"d": check_date.isoformat()}).fetchone()
        scored_games = row[0] if row else 0

        feat = _feature_source_summary(conn, check_date)

        mirror_max = None
        if scored_games == 0:
            try:
                mirror_max = conn.execute(_MIRROR_HORIZON_SQL).fetchone()[0]
            except Exception as exc:  # noqa: BLE001 — diagnostic only, never gates the verdict
                log.warning("predictions-mirror horizon unavailable (%s)", exc)
    finally:
        if owned:
            conn.close()

    coverage = scored_games / expected_games

    print(f"\n--- Prediction Coverage for {check_date} ---")
    print(f"  Scheduled regular-season games: {expected_games}")
    print(f"  Scored games in daily_model_predictions: {scored_games}")
    print(f"  Coverage: {coverage:.1%} (threshold: {min_coverage:.0%})")

    # A1.10 — feature-source observability. Emit a [METRIC] line for Dagster
    # metadata and warn (non-blocking) on a degraded feature set / fallback days.
    if feat is not None:
        avg_cov = feat["avg_cov"] or 0.0
        print(
            f"  Feature source: feature_store={feat['n_feature_store']} "
            f"intraday_assembly={feat['n_assembly']} intraday_fallback={feat['n_fallback']}"
        )
        print(f"  Mean feature_coverage_score: {avg_cov:.3f} (min {feat['min_cov']}) "
              f"(warn threshold: {min_feature_coverage:.2f})")
        print(f"[METRIC] feature_coverage_score={avg_cov:.4f}")
        if feat["n_fallback"] > 0:
            log.warning(
                "WARN: %d game(s) on %s served via intraday_fallback "
                "(team rolling stats only — no lineup/starter overlay).",
                feat["n_fallback"], check_date,
            )
        if avg_cov < min_feature_coverage:
            log.warning(
                "WARN: mean feature_coverage_score %.3f below threshold %.2f on %s — "
                "the live feature set is degraded.",
                avg_cov, min_feature_coverage, check_date,
            )

    if coverage < min_coverage:
        log.error(
            "ALERT: Prediction coverage %.1f%% is below threshold %.0f%% on %s",
            coverage * 100, min_coverage * 100, check_date,
        )
        # E11.24 target 3 — a ZERO-coverage reading has two very different causes and the
        # operator should not have to guess which. `predict_today` writes Snowflake and then
        # re-exports the S3 mirror this check reads; if that mirror's own horizon has not
        # reached the checked date, the likely fault is the EXPORT (or a W7B_LAKEHOUSE_S3
        # rollback that stops it), not the scoring. Diagnostic only — the verdict and exit
        # code are unchanged either way, so this cannot alter parity.
        if scored_games == 0:
            if mirror_max is not None and mirror_max < check_date:
                log.error(
                    "  ZERO predictions for %s AND the S3 daily_model_predictions mirror only "
                    "reaches %s — suspect the post-predict S3 re-export (export_w6_raw_to_s3.py "
                    "--table daily_model_predictions, inside predict_today_morning) or a "
                    "W7B_LAKEHOUSE_S3 rollback, BEFORE suspecting predict itself. The served "
                    "store reads this same parquet, so a frozen mirror is a real serving outage.",
                    check_date, mirror_max,
                )
            else:
                log.error(
                    "  ZERO predictions for %s and the S3 mirror horizon is %s (not behind) — "
                    "the mirror is current, so this is a genuine scoring/serving gap.",
                    check_date, mirror_max,
                )
        sys.exit(1)

    print(f"\nCoverage check passed ({coverage:.1%}).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that daily_model_predictions covers all scheduled games."
    )
    parser.add_argument("--date", default=None,
                        help="Game date in YYYY-MM-DD format (default: today ET)")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE,
                        help=f"Minimum coverage fraction to pass (default: {DEFAULT_MIN_COVERAGE})")
    parser.add_argument("--min-feature-coverage", type=float, default=DEFAULT_MIN_FEATURE_COVERAGE,
                        help=f"Non-blocking warn threshold on mean feature_coverage_score "
                             f"(default: {DEFAULT_MIN_FEATURE_COVERAGE})")
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        check_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(check_date=check_date, min_coverage=args.min_coverage,
        min_feature_coverage=args.min_feature_coverage)


if __name__ == "__main__":
    main()

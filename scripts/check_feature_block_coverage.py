"""
check_feature_block_coverage.py — durable served-feature-block coverage guard.

WHY THIS EXISTS (F2, fired TWICE — 2026-07-02 and again 2026-07-03):
    The E11.1 lakehouse cutover can silently drop a whole FEATURE BLOCK from the
    served `feature_pregame_game_features` while leaving every other block intact and
    every row COUNT unchanged. Mechanism: a block (e.g. the umpire z-scores) is sourced
    through an external table / precursor parquet whose DDL reads the VARIANT with the
    wrong KEY CASE, or whose native build isn't wired into the daily job (the deferred
    W11b umpire cutover) — so the column materializes 100% NULL even though the upstream
    model is fully populated. Predictions then run on a quietly amputated feature set.
    The 7/2 "fix" (regenerate the ext DDL) patched the symptom on a fragile mirror and
    REGRESSED within a day → a standing, self-calibrating guard is required.
    See E1_11_BUG_feature_correctness.md (F2 / F2-recurrence).

WHAT IT CHECKS:
    For each configured feature BLOCK (a representative not-null column), it compares
    coverage on RECENTLY-COMPLETED slates against an older BASELINE window — both over
    games that have already been played, so it is immune to day-of posting timing
    (umpire assignments, lineups, and odds post hours before first pitch; a current-slate
    check would false-fire every morning). Per block:
        base_cov   = notnull-rate over [anchor-45 .. anchor-9]   (the normal level)
        recent_cov = notnull-rate over [anchor-8  .. anchor-1]   (the last ~week played)
    and classifies:
        DEGRADED   base_cov >= WELL_COVERED AND recent_cov < REL_DROP * base_cov
                   → a normally-populated block silently collapsed. This is the F2
                     signature (umpire: base ~0.97 → recent ~0.50 and falling). Fatal
                     under --strict.
        OK         recent_cov holds near the baseline.
        SKIPPED    base_cov < WELL_COVERED → the block is legitimately partial
                   (coverage-gapped by era/source, e.g. bat-tracking pre-2023, odds
                   ~0.7); a drop can't be asserted against a soft baseline. Reported,
                   never fatal. (Odds freeze is covered separately by check_odds_coverage.)

    Keying the assertion off the block's OWN trailing baseline (not a hardcoded floor)
    makes it self-calibrating: it only fires when a block that WAS near-full goes sparse.

TIER (pipeline failure-handling contract):
    Default = ALERT-loud-but-continue: prints a loud stderr WARNING but exits 0, so it
    can never take down serving during rollout (RUNTIME GATE — validate on the box first).
    Pass --strict (or set FEATURE_COVERAGE_STRICT=1) to exit 1 on any DEGRADED block,
    promoting it to HALT once validated.

Usage:
    uv run python scripts/check_feature_block_coverage.py --env prod
    uv run python scripts/check_feature_block_coverage.py --env prod --strict
    uv run python scripts/check_feature_block_coverage.py --env dev --date 2026-07-03
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

# A block must have been at least this well covered on the baseline window before we will
# assert a collapse against it (below this it is a coverage-gapped block — reported, not fatal).
_WELL_COVERED = 0.85
# DEGRADED when recent coverage falls below this fraction of the block's own baseline.
_REL_DROP = 0.70

# Feature BLOCK -> a representative column that is near-fully populated on played games when
# the block is healthy. Column absence is handled gracefully (skipped with a warning), so this
# list can be extended without breaking older stores. Blocks known to be coverage-gapped by era
# (bat-tracking, weather pre-2021) are intentionally omitted — the baseline gate would SKIP them
# anyway, and including them only adds noise.
_BLOCKS: dict[str, str] = {
    "umpire": "ump_accuracy_zscore",           # the F2 regression (both occurrences)
    "odds_metadata": "market_bookmaker_count",  # Defect-3 class at the feature level
    "starter_form_l3": "home_starter_sp_k_pct_l3",   # F1 start-indexed form
    "starter_quality": "home_starter_stuff_plus",
    "lineup_woba": "home_lineup_woba_vs_starter_archetype",
    "park": "park_run_factor_3yr",
    "rest": "home_starter_days_rest",
}


def _mart_schema(env: str) -> str:
    return "baseball_data.betting_features" if env == "prod" else "baseball_data.dev_betting_features"


def _present_columns(cur, schema: str, table: str, wanted: list[str]) -> set[str]:
    """Lowercased set of the wanted columns that actually exist on the served table (so a
    renamed/absent block column is SKIPPED with a warning, never a crash)."""
    db, sch = schema.split(".", 1)
    cur.execute(f"""
        select lower(column_name) as c
        from {db}.information_schema.columns
        where table_schema = upper('{sch}') and table_name = upper('{table}')
    """)
    have = {r[0] for r in cur.fetchall()}
    return {c for c in wanted if c.lower() in have}


def _classify(base_cov: float | None, recent_cov: float | None) -> str:
    if base_cov is None or recent_cov is None:
        return "NO_DATA"
    if base_cov < _WELL_COVERED:
        return "SKIPPED"
    if recent_cov < _REL_DROP * base_cov:
        return "DEGRADED"
    return "OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="Served-feature-block coverage guard (block-zeroing detector)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Anchor date. Default: current US baseball date.")
    parser.add_argument("--strict", action="store_true",
                        default=os.environ.get("FEATURE_COVERAGE_STRICT") == "1",
                        help="Exit 1 (HALT) on any DEGRADED block. "
                             "Default from FEATURE_COVERAGE_STRICT env (=1 to enable).")
    args = parser.parse_args()

    anchor = date.fromisoformat(args.date) if args.date else current_game_date()
    base_lo, base_hi = anchor - timedelta(days=45), anchor - timedelta(days=9)
    rec_lo, rec_hi = anchor - timedelta(days=8), anchor - timedelta(days=1)
    schema = _mart_schema(args.env)
    table = "feature_pregame_game_features"
    log.info(f"[{args.env.upper()}] feature-block coverage — anchor {anchor}; "
             f"baseline {base_lo}..{base_hi}, recent {rec_lo}..{rec_hi}; strict={args.strict}")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        present = _present_columns(cur, schema, table, list(_BLOCKS.values()))
        blocks = {b: c for b, c in _BLOCKS.items() if c.lower() in {p.lower() for p in present}}
        for b, c in _BLOCKS.items():
            if b not in blocks:
                log.warning(f"  block '{b}': column {c} absent from {table} — SKIPPED "
                            f"(store predates this column, or it was renamed)")
        if not blocks:
            print("[METRIC] feature_block_min_cov_ratio=1.0000")
            log.warning("[ALERT] no configured block columns present — nothing to check.")
            return 0

        sel = [
            f"count_if(game_date between '{base_lo}' and '{base_hi}') as base_n",
            f"count_if(game_date between '{rec_lo}' and '{rec_hi}') as recent_n",
        ]
        for b, c in blocks.items():
            sel.append(f"count_if(game_date between '{base_lo}' and '{base_hi}' and {c} is not null) as base_{b}")
            sel.append(f"count_if(game_date between '{rec_lo}' and '{rec_hi}' and {c} is not null) as recent_{b}")
        cur.execute(f"""
            select {', '.join(sel)}
            from {schema}.{table}
            where game_date between '{base_lo}' and '{rec_hi}'
        """)
        row = dict(zip([d[0].lower() for d in cur.description], cur.fetchone()))
    finally:
        conn.close()

    base_n, recent_n = int(row["base_n"]), int(row["recent_n"])
    if base_n == 0 or recent_n == 0:
        print("[METRIC] feature_block_min_cov_ratio=1.0000")
        log.warning(f"[ALERT] insufficient played games in the windows "
                    f"(baseline n={base_n}, recent n={recent_n}) — cannot assess. "
                    f"Check that the feature store is fresh.")
        return 0

    degraded: list[str] = []
    worst_ratio = 1.0
    for b in blocks:
        base_cov = int(row[f"base_{b}"]) / base_n
        recent_cov = int(row[f"recent_{b}"]) / recent_n
        status = _classify(base_cov, recent_cov)
        ratio = recent_cov / base_cov if base_cov else 1.0
        msg = f"  block '{b}': baseline {base_cov:.1%} → recent {recent_cov:.1%}  [{status}]"
        if status == "DEGRADED":
            worst_ratio = min(worst_ratio, ratio)
            degraded.append(b)
            log.error(msg + f" — recent < {_REL_DROP:.0%} of baseline; block SILENTLY COLLAPSED")
        elif status == "SKIPPED":
            log.info(msg + f" — baseline < {_WELL_COVERED:.0%}; coverage-gapped, not asserted")
        else:
            log.info(msg)

    print(f"[METRIC] feature_block_min_cov_ratio={worst_ratio:.4f}")

    if degraded:
        banner = (f"FEATURE BLOCK(S) SILENTLY COLLAPSED in served {table}: {', '.join(degraded)}. "
                  f"A normally-populated block went sparse on recently-played slates — predictions "
                  f"run on an amputated feature set. Likely an ext-table VALUE:-case mismatch or a "
                  f"precursor build not wired into the daily job (e.g. the W11b umpire cutover: enable "
                  f"W11B_UMPIRE_NIGHTLY, run --w11b-only + refresh --w11b, then --w8b + regen/refresh "
                  f"the w8b ext DDL, and per-ROW verify).")
        if args.strict:
            log.error("[HALT] " + banner)
            return 1
        log.warning("[ALERT] " + banner + "  (non-blocking: set FEATURE_COVERAGE_STRICT=1 to HALT.)")
        return 0

    log.info("All well-covered feature blocks hold near baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

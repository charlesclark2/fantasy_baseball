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

    BLIND SPOT CLOSED (INC-31, 2026-07-09): the trailing-baseline check above SKIPS a
    block that is dead across the WHOLE trailing window — both the baseline AND recent
    windows read ~0, so base_cov < WELL_COVERED and the collapse "can't be asserted
    against a soft baseline." That let a persistently-/born-dead block hide (umpire
    ump_accuracy_zscore 100% NULL 07-02..07-08: the ext-table read broke, so the served
    aggregator merged NULL on every recently-played slate → base_cov=0 → SKIPPED). The
    served SF aggregator is an incremental MERGE, so rows merged BEFORE the break stay
    populated — i.e. a HISTORICAL window (further back than the baseline) still shows the
    block's true healthy level. So we add a third window and a rescue rule:
        hist_cov = notnull-rate over [anchor-HIST_HI .. anchor-HIST_LO]  (well before baseline)
        DEGRADED (collapsed-vs-history)  hist_cov >= WELL_COVERED AND recent_cov < REL_DROP * hist_cov
    A block SKIPPED by the trailing baseline is RESCUED to DEGRADED when it was healthy
    historically and is now sparse — so the next born-dead / whole-trailing-window-dead
    block ALARMS instead of hiding.

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

# A block must have been at least this well covered on the (trailing or historical) baseline
# window before we will assert a collapse against it (below this it is a coverage-gapped block —
# reported, not fatal).
_WELL_COVERED = 0.85
# DEGRADED when recent coverage falls below this fraction of the block's own baseline.
_REL_DROP = 0.70
# INC-31 historical window (well BEFORE the trailing baseline) — catches a block dead across the
# WHOLE trailing window (base_cov≈0), which the trailing-baseline check alone would SKIP. The SF
# aggregator is an incremental MERGE, so rows from this far back retain the block's pre-break level.
_HIST_LO_DAYS = 120  # window start = anchor - 120d
_HIST_HI_DAYS = 46   # window end   = anchor - 46d  (abuts the baseline's anchor-45 start)

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
    # bullpen EB posteriors (mart_bullpen_effectiveness → team_features → aggregator). Collapsed to
    # NULL for the 2026-06-30..07-02 outage window — the serving-guard/30.13-gate abstained on it but
    # the coverage guard missed it because this block was not represented here. Now guarded so a
    # future silent collapse of the bullpen-EB chain is caught.
    "bullpen_eb": "home_bp_eb_xwoba",
    # E9.53 — the team sequential posteriors (Epic 16.3). UNCONDITIONAL-CORE DISCRIMINATIVE
    # (predict_today._DISCRIMINATIVE_RE matches `team_sequential`), so a whole-block zero sets
    # is_degraded on every served pick. THREE separate blocks because the producer writes the
    # three metric chains INDEPENDENTLY and they demonstrably failed independently:
    # `*_team_sequential_bullpen_xwoba` was 0 games on 2026-07-22/23/24/27/28 while `_woba` and
    # `_win_prob` were fine on those same dates. A single representative column would have
    # missed the bullpen-metric hole entirely.
    "team_sequential_off": "home_team_sequential_woba",
    "team_sequential_bullpen": "home_team_sequential_bullpen_xwoba",
    "team_sequential_win": "home_team_sequential_win_prob",
}

# E9.53 — a `_seasonnorm` column can NEVER be a block's representative column.
# feature_pregame_game_features derives each `<col>_seasonnorm` from its raw twin through a bare
# `coalesce(..., 0)`, so a NULL raw becomes a FABRICATED 0.0 and the _seasonnorm column reads
# 100% NOT-NULL straight through a TOTAL outage of its own block. That is precisely how the
# 07-22..07-28 team_sequential outage looked like "the _seasonnorm variants are computed from a
# different path" — they are not; the coalesce is the whole difference.
# ⏭️ That masking is a KNOWN DEFECT whose fix is DEFERRED TO E1.12 (it changes a served model
# input, so it ships with the retrain). Until then this guard is the DETECTOR for the class, and
# it must assert on RAW columns only. Even after E1.12 a not-null-rate check keyed off a
# _seasonnorm column stays a category error (it measures the coalesce, not the block), so refuse
# it OUTRIGHT rather than trusting the upstream to stay honest.
_FORBIDDEN_COLUMN_SUFFIX = "_seasonnorm"


def _assert_representative_columns_are_raw(blocks: dict[str, str]) -> None:
    """RAISE if any block is represented by a derived `_seasonnorm` column (see above).

    Deliberately a hard failure, not a warning: a guard configured with a structurally
    non-null column is a guard that silently passes forever, which is worse than no guard.
    """
    bad = {b: c for b, c in blocks.items() if c.lower().endswith(_FORBIDDEN_COLUMN_SUFFIX)}
    if bad:
        raise ValueError(
            f"check_feature_block_coverage: {len(bad)} block(s) are configured with a "
            f"`{_FORBIDDEN_COLUMN_SUFFIX}` representative column: {bad}. A _seasonnorm column is "
            f"derived from its raw twin and cannot be used as a coverage probe — use the RAW "
            f"column (e.g. 'home_bp_eb_xwoba', not 'home_bp_eb_xwoba_seasonnorm')."
        )


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


def _classify(base_cov: float | None, recent_cov: float | None,
              hist_cov: float | None = None) -> str:
    if base_cov is None or recent_cov is None:
        return "NO_DATA"
    if base_cov >= _WELL_COVERED:
        # Normal path: assert the recent trailing week against the trailing baseline.
        return "DEGRADED" if recent_cov < _REL_DROP * base_cov else "OK"
    # base_cov < WELL_COVERED → the trailing baseline is too weak to assert against; the block is
    # either legitimately partial OR dead across the WHOLE trailing window. Before SKIPPING, RESCUE
    # the persistently-/born-dead case (INC-31): if the block was healthy in the HISTORICAL window
    # but is now sparse, it collapsed vs history — a real, silent block-zeroing. DEGRADED.
    if hist_cov is not None and hist_cov >= _WELL_COVERED and recent_cov < _REL_DROP * hist_cov:
        return "DEGRADED"
    return "SKIPPED"


# ── E9.53: the PER-DATE check (the blind spot that let 07-22..07-28 through) ───────────
#
# BLIND SPOT: every classification above is a WINDOW AGGREGATE. The recent window is 8 days
# ([anchor-8 .. anchor-1]), so ONE fully-dead date dilutes to recent_cov ≈ 7/8 = 0.875 of
# baseline — comfortably above _REL_DROP (0.70). TWO dead dates ≈ 0.750, still above. It takes
# THREE of eight dates fully dead before the aggregate check fires. So an INTERMITTENT
# whole-slate block outage — exactly the E9.53 signature (team_sequential_bullpen_xwoba dead on
# 07-22/23/24/27/28, i.e. never 3 consecutive within one 8-day window as observed on 07-29's
# anchor) is structurally INVISIBLE to the aggregate guard. That is the answer to "did the guard
# fire?": it did NOT, and it COULD not — a blind spot, not a missed alert.
#
# CURE: assert PER PLAYED DATE. A date whose coverage collapses to ~0 for a block that is
# well-covered on the baseline (or historically) is a whole-slate block outage, full stop — the
# aggregate is irrelevant. Thresholded ABSOLUTELY and low (not relatively) so this fires only on
# a genuine zeroing and never on a thin/partial day: a single date is a small sample (~15 games),
# so a relative test at that n would be noisy.
_DATE_OUTAGE_MAX = 0.20      # a played date below this notnull-rate is "the block is dead here"
_DATE_MIN_GAMES = 4         # ignore tiny dates (all-star break, a 2-game slate) — too small to judge


def find_date_outages(
    per_date: list[tuple[object, int, int]],
    baseline_cov: float | None,
    hist_cov: float | None = None,
) -> list[tuple[str, float]]:
    """PURE. Played dates on which a normally-populated block is DEAD.

    `per_date` is [(game_date, n_games, n_notnull), ...] over the recent window. Returns
    [(date_str, cov), ...] for every date whose coverage is <= _DATE_OUTAGE_MAX while the block's
    own baseline (or, INC-31-style, its history) shows it is normally well-covered. Empty when the
    block has no healthy reference level — a coverage-gapped block cannot have an "outage".
    """
    reference = max(
        baseline_cov if baseline_cov is not None else 0.0,
        hist_cov if hist_cov is not None else 0.0,
    )
    if reference < _WELL_COVERED:
        return []
    out: list[tuple[str, float]] = []
    for game_date, n_games, n_notnull in per_date:
        if n_games < _DATE_MIN_GAMES:
            continue
        cov = n_notnull / n_games
        if cov <= _DATE_OUTAGE_MAX:
            out.append((str(game_date)[:10], round(cov, 3)))
    return sorted(out)


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
    hist_lo, hist_hi = anchor - timedelta(days=_HIST_LO_DAYS), anchor - timedelta(days=_HIST_HI_DAYS)
    schema = _mart_schema(args.env)
    table = "feature_pregame_game_features"
    log.info(f"[{args.env.upper()}] feature-block coverage — anchor {anchor}; "
             f"history {hist_lo}..{hist_hi}, baseline {base_lo}..{base_hi}, "
             f"recent {rec_lo}..{rec_hi}; strict={args.strict}")

    # E9.53 — refuse a structurally-non-null probe column before touching the warehouse.
    _assert_representative_columns_are_raw(_BLOCKS)

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

        # E9.53 — ONE per-date query now feeds BOTH views: the three window aggregates (summed in
        # Python, byte-identical to the old count_if aggregate) AND the per-date outage check the
        # aggregates are blind to. ~120 rows, so this is not measurably more expensive.
        sel = ["game_date", "count(*) as n_games"]
        for b, c in blocks.items():
            sel.append(f"count_if({c} is not null) as cov_{b}")
        cur.execute(f"""
            select {', '.join(sel)}
            from {schema}.{table}
            where game_date between '{hist_lo}' and '{rec_hi}'
            group by game_date
            order by game_date
        """)
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    def _d(v) -> date:
        return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])

    def _window(lo: date, hi: date) -> list[dict]:
        return [r for r in rows if lo <= _d(r["game_date"]) <= hi]

    hist_rows, base_rows, recent_rows = (
        _window(hist_lo, hist_hi), _window(base_lo, base_hi), _window(rec_lo, rec_hi)
    )
    hist_n = sum(int(r["n_games"]) for r in hist_rows)
    base_n = sum(int(r["n_games"]) for r in base_rows)
    recent_n = sum(int(r["n_games"]) for r in recent_rows)
    if base_n == 0 or recent_n == 0:
        print("[METRIC] feature_block_min_cov_ratio=1.0000")
        log.warning(f"[ALERT] insufficient played games in the windows "
                    f"(baseline n={base_n}, recent n={recent_n}) — cannot assess. "
                    f"Check that the feature store is fresh.")
        return 0

    degraded: list[str] = []
    date_outages: dict[str, list[tuple[str, float]]] = {}
    worst_ratio = 1.0
    for b in blocks:
        base_cov = sum(int(r[f"cov_{b}"]) for r in base_rows) / base_n
        recent_cov = sum(int(r[f"cov_{b}"]) for r in recent_rows) / recent_n
        # hist_cov only defined when the historical window has played games (early-season guard).
        hist_cov = (sum(int(r[f"cov_{b}"]) for r in hist_rows) / hist_n) if hist_n else None
        status = _classify(base_cov, recent_cov, hist_cov)

        # E9.53 PER-DATE check — a whole-slate zeroing on any individual played date, which the
        # 8-day aggregate above dilutes to ~0.875 (needs 3 of 8 dead before it can fire).
        outages = find_date_outages(
            [(r["game_date"], int(r["n_games"]), int(r[f"cov_{b}"])) for r in recent_rows],
            base_cov, hist_cov,
        )
        if outages:
            date_outages[b] = outages
            if status != "DEGRADED":
                status = "DEGRADED"
                # The aggregate ratio understates an intermittent outage; report the worst DATE.
                worst_ratio = min(worst_ratio, min(cov for _d_, cov in outages))

        # For a block SKIPPED by the trailing baseline but collapsed vs history, the meaningful
        # ratio is recent/hist (recent/base would be ~1.0 when both trailing windows are dead).
        collapsed_vs_hist = status == "DEGRADED" and base_cov < _WELL_COVERED
        denom = hist_cov if collapsed_vs_hist else base_cov
        ratio = recent_cov / denom if denom else 1.0
        hist_str = f", history {hist_cov:.1%}" if hist_cov is not None else ""
        msg = f"  block '{b}': baseline {base_cov:.1%} → recent {recent_cov:.1%}{hist_str}  [{status}]"
        if status == "DEGRADED":
            if b not in date_outages:
                worst_ratio = min(worst_ratio, ratio)
            degraded.append(b)
            if outages:
                dates_str = ", ".join(f"{d} ({cov:.0%})" for d, cov in outages)
                log.error(msg + f" — WHOLE-SLATE OUTAGE on {len(outages)} played date(s): "
                                f"{dates_str}. The block is dead for EVERY game on those dates "
                                f"(the 8-day aggregate alone cannot see this — E9.53).")
            elif collapsed_vs_hist:
                log.error(msg + f" — dead across the whole trailing window but was "
                                f"{hist_cov:.0%} historically; block SILENTLY COLLAPSED vs history (INC-31)")
            else:
                log.error(msg + f" — recent < {_REL_DROP:.0%} of baseline; block SILENTLY COLLAPSED")
        elif status == "SKIPPED":
            log.info(msg + f" — baseline < {_WELL_COVERED:.0%} and no healthy history; "
                           f"coverage-gapped, not asserted")
        else:
            log.info(msg)

    print(f"[METRIC] feature_block_min_cov_ratio={worst_ratio:.4f}")
    print(f"[METRIC] feature_block_date_outage_count={sum(len(v) for v in date_outages.values())}")

    if degraded:
        banner = (f"FEATURE BLOCK(S) SILENTLY COLLAPSED in served {table}: {', '.join(degraded)}. "
                  f"A normally-populated block went sparse on recently-played slates — predictions "
                  f"run on an amputated feature set. Likely an ext-table VALUE:-case mismatch or a "
                  f"precursor build not wired into the daily job (e.g. the W11b umpire cutover: enable "
                  f"W11B_UMPIRE_NIGHTLY, run --w11b-only + refresh --w11b, then --w8b + regen/refresh "
                  f"the w8b ext DDL, and per-ROW verify).")
        if date_outages:
            banner += (" WHOLE-SLATE date outages: "
                       + "; ".join(f"{b}: {[d for d, _c in v]}" for b, v in sorted(date_outages.items()))
                       + ". A per-DATE zeroing usually means the block's PRODUCER skipped that date "
                         "(e.g. E9.53: the sequential catch-up frontier advancing past a date whose "
                         "source wasn't ready), not an ext-table/case problem.")
        if args.strict:
            log.error("[HALT] " + banner)
            return 1
        log.warning("[ALERT] " + banner + "  (non-blocking: set FEATURE_COVERAGE_STRICT=1 to HALT.)")
        return 0

    log.info("All well-covered feature blocks hold near baseline, on every played date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""ci_shards.py — the single source of truth for how the FAST GATE is split across CI jobs.

WHY (2026-07-27 CI-hygiene profile): the fast gate is the merge bar every session runs. It had
grown to ~2,360 tests / ~90s of serial work, and profiling showed the bottleneck is NOT slow
tests (the slowest single test is 4.5s, comfortably under the `@slow` >5s rule) — it is
per-worker COLLECTION. Every xdist worker imports all ~175 test modules before running its
share, so on an 11-core box `-n auto` burned 287s of CPU to do 90s of work and was SLOWER than
`-n 4`. Duplicated collection is a fixed cost per process, so the only way to actually cut it is
to give each process FEWER TESTS TO COLLECT — i.e. shard.

Sharding by DOMAIN (rather than round-robin) also makes a red check self-describing: "football
shard failed" localises the blame before you open the log.

THE INVARIANT — every test file belongs to EXACTLY ONE shard, and no file can escape the gate.
`core` is the computed catch-all: it is defined as "every collected test file not claimed by a
named shard", so a NEW test file is covered by the merge bar the moment it is added, with zero
maintenance. `betting_ml/tests/test_fast_gate_hygiene.py` proves the partition holds.

Adding a shard rule is an optimisation (move an expensive new family off `core`), never a
correctness requirement.

Usage (CI):
    uv run python scripts/ci_shards.py --shard football   # -> space-separated pytest targets
    uv run python scripts/ci_shards.py --list             # -> shard names, one per line
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories pytest collects from (mirrors [tool.pytest.ini_options] testpaths in pyproject.toml).
TEST_ROOTS = ("betting_ml/tests", "scripts/tests")

# The computed catch-all. Never listed in _RULES — it is whatever the named shards don't claim.
CATCH_ALL = "core"

# Ordered (shard, filename-prefix) rules; FIRST match wins, so put the more specific prefix first.
# Prefix matching (not exact names) is deliberate: a new test_ncaaf_*.py joins the football shard
# automatically instead of silently inflating `core`.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ── football vertical: NFL + NCAAF models, fantasy engine, draft ──────────────────────
    ("football", (
        "test_ncaaf_", "test_nfl_", "test_nf1_",
        "test_fantasy_", "test_draft_", "test_sports_",
    )),
    # ── repo-scanning lint/contract guards: each rglobs the whole tree, so they are IO-heavy
    #    and cheap to isolate (boto3-credential lint, retired-source, type contracts, …) ────
    ("guards", (
        "test_boto3_credential_lint", "test_snowflake_resolver_lint", "test_retired_source_guard",
        "test_decommission_orphan_guard", "test_the_board_reader_guard",
        "test_phase15_straggler_repoint", "test_type_contract_guard", "test_timestamp_wrap_guard",
        "test_changelog_guard", "test_lean_capture_images_selfcontained",
        "test_delta_lakehouse_guard", "test_lakehouse_reader_delta_routing",
        "test_book_odds_leakage_guard", "test_export_mirror_int_pin",
        "test_postponed_dh_dedup_guard", "test_serving_parity_guard",
        "test_parity_check_w8b_tolerance", "test_season_norm_parity",
        "test_sample_uniqueness", "test_seq_asof_guard", "test_fast_gate_hygiene",
    )),
    # ── pipeline / serving / ops: Dagster ops + sensors, lakehouse waves, ingest, writers ──
    ("serving-ops", (
        "test_e11_", "test_e9_", "test_inc25_", "test_inc32_", "test_w11",
        "test_lineup_", "test_intraday_", "test_freshness_gate_", "test_predict_today_",
        "test_serving_", "test_monitor_", "test_signal_generator_", "test_spine_",
        "test_lakehouse_", "test_ingest_", "test_savant_ingestion", "test_fangraphs_",
        "test_scd2_writer", "test_monthly_schedule_s3_writer", "test_k_projection_",
        "test_props_", "test_odds_coverage_guard", "test_feature_", "test_alert",
        "test_deadman_lambda", "test_push_sender_lambda", "test_qualified_bet_notifier",
        "test_settlement_cadence", "test_finalize_", "test_eb_starter_", "test_game_spine_",
        "test_served_prediction_integrity_guard", "test_dbt_runner", "test_cost_wake_gates",
        "test_pick_narrative_guard", "test_picks_stale_slate_guard",
        "test_invalidate_permanent_cache", "test_model_skill_cache_antifreeze_guard",
        "test_lineup_cache_antifreeze_guard", "test_parlay_serving",
        "test_sensor_utc_coercion_routing", "test_sequential_catchup",
    )),
    # ── prospect / MiLB translation MLEs (E7.x). Split out of baseball-models purely for
    #    BALANCE — together they were the longest shard and set the gate's wall-clock. ──────
    # (`test_ingest_milb` is deliberately NOT here — `serving-ops`'s `test_ingest_` prefix is
    #  declared first and claims it, which is correct: it guards an ingest op, not an MLE.)
    ("prospect-milb", (
        "test_milb_", "test_e7_", "test_prospect_", "test_mlb_pipeline_",
    )),
    # ── baseball predictive models: the Monte-Carlo / bake-off / pricing families that
    #    dominate the gate's execution time (copula, per-side, totals, …) ──────────────────
    ("baseball-models", (
        "test_copula", "test_perside_", "test_totals_", "test_prop_pricing",
        "test_f5_distribution", "test_derivative_", "test_cross_market_eval",
        "test_model_bakeoff", "test_market_blind", "test_cv", "test_overfitting",
        "test_preprocessing", "test_bullpen_v3", "test_h2h_calibration",
        "test_win_prob_uncertainty", "test_run_env_regime", "test_line_microstructure",
        "test_zone_matchup", "test_pa_outcome_features", "test_stuff_plus_deleak",
        "test_scorecard", "test_incremental_lift_eval", "test_derive_clustered_contract",
        "test_model_health_guard", "test_v6_lineage_on_promote", "test_sub_model_registry",
        "test_pick_explanations_linear", "test_calibration_artifact",
    )),
)

# Named shards in declaration order, then the catch-all.
SHARD_NAMES: tuple[str, ...] = tuple(dict.fromkeys(name for name, _ in _RULES)) + (CATCH_ALL,)


def all_test_files(repo_root: Path | None = None) -> list[Path]:
    """Every test file pytest would collect, repo-relative, sorted."""
    root = repo_root or _REPO_ROOT
    files: list[Path] = []
    for test_root in TEST_ROOTS:
        base = root / test_root
        if base.exists():
            files.extend(p.relative_to(root) for p in base.rglob("test_*.py"))
    return sorted(files)


def shard_of(path: Path | str) -> str:
    """The single shard owning `path`. Unclaimed files fall to the catch-all."""
    name = Path(path).name
    for shard, prefixes in _RULES:
        if name.startswith(prefixes):
            return shard
    return CATCH_ALL


def shard_files(shard: str, repo_root: Path | None = None) -> list[Path]:
    if shard not in SHARD_NAMES:
        raise SystemExit(f"unknown shard {shard!r} — expected one of {', '.join(SHARD_NAMES)}")
    return [p for p in all_test_files(repo_root) if shard_of(p) == shard]


#: The marker whose files the SLOW gate needs. Kept as a constant so the guard test and this
#: scanner cannot disagree about which word they are looking for.
SLOW_MARKER = "slow"


def _uses_marker(path: Path, marker: str) -> bool:
    """True when `path` mentions `pytest.mark.<marker>` in ANY form.

    ⭐ AST, NOT GREP, and the difference is the whole safety argument. The three forms a slow test
    can arrive in — a `@pytest.mark.slow` decorator, a module-level `pytestmark = pytest.mark.slow`,
    and `pytest.param(..., marks=pytest.mark.slow)` — all parse to the same attribute chain, so one
    check covers every one of them. A regex would have to enumerate the spellings and would miss the
    next one somebody invents.

    ⚠️ A syntax error returns True, deliberately. This function decides whether a file is HANDED to
    the slow gate; an unparseable file must be handed over (where pytest reports the error) rather
    than silently dropped from the run.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return True
    for node in ast.walk(tree):
        # `pytest.mark.slow` → Attribute(attr='slow', value=Attribute(attr='mark', ...))
        if (
            isinstance(node, ast.Attribute)
            and node.attr == marker
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
        ):
            return True
    return False


def slow_files(repo_root: Path | None = None) -> list[Path]:
    """Every test file that carries a `slow` marker, repo-relative, sorted.

    ⭐ WHY THE SLOW GATE NEEDS THIS. `pytest -m "slow and not research"` with no path arguments
    collects `testpaths` — measured 2026-08-20, that is **10,659 tests imported to find 79**, and
    xdist pays it ONCE PER WORKER (the duplicated-collection cost `docs/ci_fast_gate_profile.md`
    documents). Handing pytest only the files that carry the marker drops collection from 11.04s to
    1.30s and the whole gate's wall clock by 36% (106.8s → 68.8s locally), with the SAME 79 tests
    selected by the SAME `-m` expression.

    ⚠️ THE `-m` EXPRESSION REMAINS THE SELECTOR. This list only narrows what is IMPORTED; it never
    decides what RUNS. So a file that lands here without a slow test costs a little import time and
    changes no result, while a file with a slow test that is missing here would silently escape the
    gate — which is why the scan is derived from the marker itself rather than maintained by hand,
    and why `test_fast_gate_hygiene.py` pins it.
    """
    root = repo_root or _REPO_ROOT
    return [p for p in all_test_files(root) if _uses_marker(root / p, SLOW_MARKER)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", help="print this shard's pytest targets, space-separated")
    ap.add_argument("--list", action="store_true", help="print every shard name")
    ap.add_argument("--slow-paths", action="store_true",
                    help="print the pytest targets for the SLOW gate, space-separated")
    args = ap.parse_args()

    if args.list:
        print("\n".join(SHARD_NAMES))
        return
    if args.slow_paths:
        files = slow_files()
        if not files:
            # Same reasoning as the empty-shard guard below: no arguments makes pytest fall back to
            # `testpaths`, so an empty list would quietly restore the slow, whole-suite collection
            # this flag exists to remove — a silent regression rather than a failure.
            raise SystemExit("no test file carries a slow marker — the scanner is broken")
        print(" ".join(p.as_posix() for p in files))
        return
    if not args.shard:
        ap.error("pass --shard <name> or --list")

    files = shard_files(args.shard)
    if not files:
        # An empty target list would make pytest run the WHOLE suite (no args = testpaths),
        # silently turning one shard into a duplicate full run. Fail loudly instead.
        raise SystemExit(f"shard {args.shard!r} matched no test files — the rules are stale")
    print(" ".join(p.as_posix() for p in files))


if __name__ == "__main__":
    sys.exit(main())

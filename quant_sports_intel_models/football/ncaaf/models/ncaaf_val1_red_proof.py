"""ncaaf_val1_red_proof.py — prove NCAAF-VAL1's guards can FAIL.

A guard that cannot go RED is not a guard (NF1.7(a)/INC-38/E9.64). This harness applies each
deliberate break to the real source, runs the named guards, and asserts they FAIL.

Four ways a RED proof itself lies, all defended against here:
  #682 — the mutation silently NO-OPs           → assert the file CHANGED on disk
  E11.24 — the anchor is not unique             → assert the anchor occurs EXACTLY once
  #815 — it lands but doesn't move the assertion → assert the anchor is GONE afterwards
  E11.26 — a signal skips `finally`             → restore stale `.redbak` files at START-UP

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val1_red_proof
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_MOD = _ROOT / "quant_sports_intel_models/football/ncaaf/models/ncaaf_val1_clv_week_strat.py"
_TEST = "betting_ml/tests/test_ncaaf_val1_clv_week_strat.py"

#: (name, target file, anchor, replacement, the guards that MUST go red)
BREAKS: list[tuple[str, Path, str, str, list[str]]] = [
    ("bucket on RAW week (the P1.1 postseason collision)", _MOD,
     'WEEK_COL = "season_order_week"', 'WEEK_COL = "week"',
     ["test_buckets_are_cut_on_season_order_week_never_raw_week"]),
    ("a hole in the bucket partition", _MOD,
     '("wk7+", 7, 999)', '("wk7+", 8, 999)',
     ["test_buckets_partition_every_week_exactly_once"]),
    ("BH degraded to a naive per-test comparison", _MOD,
     '''    k = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= rank / m * alpha:
            k = rank
    out = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= k:
            out[int(idx)] = True
    return out''',
     '''    out = [False] * m
    for rank, idx in enumerate(order, start=1):
        out[int(idx)] = p_values[idx] <= rank / m * alpha
    return out''',
     ["test_bh_is_a_step_up_procedure_not_a_naive_per_test_comparison"]),
    ("the band correction deleted (raw GENUINE_ABSENCE stands)", _MOD,
     '    elif r["upper_bound_bonf"] < MEANINGFUL:',
     '    elif False:',
     ["test_a_below_bar_bucket_whose_interval_excludes_the_meaningful_effect_is_decisive",
      "test_the_band_correction_is_two_sided_at_its_own_boundary"]),
    ("the band correction OVERWRITES an INACTIVE verdict", _MOD,
     '''    if not active:
        corr, why, trigger = v.state, v.reason, v.retest_trigger
    elif r["hit_rate"] >= BREAKEVEN:''',
     '''    if r["hit_rate"] >= BREAKEVEN:''',
     ["test_an_inactive_bucket_is_never_scored_as_a_result"]),
    ("a power-limited trigger quoted in p-decimals, not games", _MOD,
     '''        trigger = (f"{need:,} non-push games at 80% power vs {r['n']:,} here "''',
     '''        trigger = (f"p={r['p_one_sided']:.3f} "''',
     ["test_a_below_bar_bucket_whose_interval_still_admits_the_effect_is_power_limited"]),
    ("a decisive result publishes a re-test trigger anyway (NF-D18)", _MOD,
     '''               f"the interval already excludes it, which is the sharper post-data question.)")
        trigger = None''',
     '''               f"the interval already excludes it, which is the sharper post-data question.)")
        trigger = "come back with more seasons"''',
     ["test_a_below_bar_bucket_whose_interval_excludes_the_meaningful_effect_is_decisive"]),
    ("the raw classify_null state is replaced instead of preserved", _MOD,
     '    return {"raw": raw, "corrected": {"state": corr, "reason": why, "retest_trigger": trigger},',
     '    return {"raw": {**raw, "state": corr}, "corrected": {"state": corr, "reason": why, "retest_trigger": trigger},',
     ["test_the_raw_classify_null_state_is_always_preserved_beside_the_correction"]),
    ("the meaningful effect re-derived from the result, not the price", _MOD,
     'MEANINGFUL = BREAKEVEN + VIG_WIDTH', 'MEANINGFUL = BREAKEVEN + 0.005',
     ["test_the_meaningful_effect_is_one_vig_width_above_breakeven"]),
    ("clause 4 (side-bias degenerates) dropped from the pass criterion", _MOD,
     '"4_beats_degenerates": bool(r["hit_rate"] > best_anchor),',
     '"4_beats_degenerates": True,',
     ["test_each_pass_clause_can_independently_refuse"]),
    ("clause 6 (activity) dropped from the pass criterion", _MOD,
     '"6_active": bool(r["side_balance"] >= MIN_SIDE_BALANCE),', '"6_active": True,',
     ["test_each_pass_clause_can_independently_refuse"]),
    ("the ineligible secondary config made eligible to pass (E2.1-r)", _MOD,
     'c["CLEARS"] = bool(binding and all(', 'c["CLEARS"] = bool(all(',
     ["test_the_secondary_config_cannot_pass_by_construction"]),
    ("the family dispersion allowed to be silently absent", _MOD,
     '''        if len(srs) < 2:
            raise SystemExit(''',
     '''        if False:
            raise SystemExit(''',
     ["test_evaluate_raises_rather_than_classify_without_the_deflation_leg"]),
    ("the reproduction pin degraded so a changed population passes", _MOD,
     '"ats_n": (pooled["ats"]["n"], PIN["ats_n"], pooled["ats"]["n"] == PIN["ats_n"]),',
     '"ats_n": (pooled["ats"]["n"], PIN["ats_n"], True),',
     ["test_the_reproduction_pin_halts_on_a_population_that_is_not_the_recorded_one"]),
    ("a serving write smuggled into a query-only story", _MOD,
     'def main(argv: list[str] | None = None) -> int:',
     'def main(argv=None) -> int:\n    _sneak = "to_parquet"',
     ["test_the_story_is_query_only"]),
    ("the exact binomial swapped for a normal approximation", _MOD,
     'return float(stats.binom.sf(wins - 1, n, p0))',
     'return float(stats.norm.sf((wins / n - p0) / (p0 * (1 - p0) / n) ** 0.5))',
     ["test_one_sided_p_is_the_exact_binomial_not_a_normal_approximation"]),
]


def _restore_all() -> None:
    """E11.26: a signal skips `finally`, so a previous run can leave a mutated file on disk.
    Restore any stale backup BEFORE doing anything else — never after."""
    for bak in _ROOT.rglob("*.redbak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        print(f"  [restore] stale mutation reverted: {target.name}")


def _run(tests: list[str]) -> bool:
    """True if pytest reports a FAILURE for the named guards."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "--no-header", "-x",
         *[f"{_TEST}::{t}" for t in tests]],
        cwd=_ROOT, capture_output=True, text=True)
    return r.returncode != 0


def main() -> int:
    _restore_all()
    red = green = 0
    print(f"=== NCAAF-VAL1 RED PROOF — {len(BREAKS)} deliberate breaks ===")
    for name, path, anchor, repl, tests in BREAKS:
        original = path.read_text()
        # #682 / E11.24 / #815 — the anchor must be UNIQUE, the write must LAND, and the anchor
        # must be GONE afterwards, or "the guard caught it" and "the break never bit" are
        # indistinguishable and the harness reports a FALSE result in either direction.
        occurrences = original.count(anchor)
        if occurrences != 1:
            print(f"  ✗ ANCHOR NOT UNIQUE ({occurrences}×) — {name}")
            green += 1
            continue
        mutated = original.replace(anchor, repl, 1)
        assert mutated != original, f"mutation is a no-op: {name}"
        bak = path.with_suffix(path.suffix + ".redbak")
        bak.write_text(original)
        try:
            path.write_text(mutated)
            on_disk = path.read_text()
            if on_disk != mutated or anchor in on_disk:
                # A harness defect, NOT a guard result — and it is reported per break rather than
                # raised, so one bad anchor cannot leave the remaining breaks unrun (and silently
                # unproven).
                failed, defect = None, ("did not land" if on_disk != mutated
                                        else "anchor survived")
            else:
                failed, defect = _run(tests), None
        finally:
            path.write_text(original)
            bak.unlink(missing_ok=True)
        if defect:
            green += 1
            print(f"  ✗ HARNESS DEFECT ({defect}) — {name}")
        elif failed:
            red += 1
            print(f"  ✅ RED   {name}")
        else:
            green += 1
            print(f"  ❌ GREEN {name}  ← the guard did not catch this: {tests}")
    print(f"\n  {red}/{len(BREAKS)} breaks caught; {green} missed")
    return 0 if green == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""ncaaf_val2_red_proof.py — prove NCAAF-VAL2's guards can FAIL.

A guard that cannot go RED is not a guard (NF1.7(a)/INC-38/E9.64). This harness applies each
deliberate break to the real source, runs the named guards, and asserts they FAIL.

Four ways a RED proof itself lies, all defended against here (the harness is VAL1's, verbatim):
  #682   — the mutation silently NO-OPs            → assert the file CHANGED on disk
  E11.24 — the anchor is not unique                → assert the anchor occurs EXACTLY once
  #815   — it lands but doesn't move the assertion  → assert the anchor is GONE afterwards
  E11.26 — a signal skips `finally`                → restore stale `.redbak` files at START-UP

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val2_red_proof
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_MOD = _ROOT / "quant_sports_intel_models/football/ncaaf/models/ncaaf_val2_mu_total_offset.py"
_TEST = "betting_ml/tests/test_ncaaf_val2_mu_total_offset.py"

#: (name, target file, anchor, replacement, the guards that MUST go red)
BREAKS: list[tuple[str, Path, str, str, list[str]]] = [
    ("the week axis becomes RAW week (the P1.1 postseason collision)", _MOD,
     "WEEK_COL = V.WEEK_COL", 'WEEK_COL = "week"',
     ["test_the_week_axis_is_season_order_week_never_raw_week"]),
    ("the served config is restated as a literal instead of imported", _MOD,
     "SERVED = V.PRIMARY",
     'SERVED = {"label": "served_v2", "mc": "ridge", "contract": "strength_pace",\n'
     '          "form": "strength_posterior", "binding": True}',
     ["test_the_served_config_is_imported_from_val1_not_restated"]),
    ("the decomposition identity is no longer enforced", _MOD,
     '''    if resid > 1e-9:
        raise SystemExit(f"[{_STORY}] the decomposition identity does not hold (max |resid| "
                         f"{resid:.3e}); the two halves do not sum to the offset.")''',
     "    _ = resid",
     ["test_build_offset_frame_raises_if_the_identity_does_not_hold"]),
    ("a positional read into the draw array creeps outside the control", _MOD,
     '        s = term_stats(frame[name].to_numpy(), frame["season"].to_numpy())',
     '        s = term_stats(dists["total"][0], frame["season"].to_numpy())',
     ["test_the_offset_read_never_indexes_a_draw_array_positionally"]),
    ("the alignment control loses its NEGATIVE leg (cannot tell broken from fixed)", _MOD,
     '''    if not out["negative_control_ok"]:
        raise SystemExit(''',
     '''    if False:
        raise SystemExit(''',
     ["test_the_alignment_control_is_two_sided"]),
    ("the two control bars stop discriminating (floor <= ceiling)", _MOD,
     "MISALIGNED_CEILING = 0.90", "MISALIGNED_CEILING = 0.99",
     ["test_the_alignment_control_is_two_sided"]),
    ("the MC flip band becomes a constant fudge factor", _MOD,
     '''        "mc_flip_band_pts": float(stats.norm.ppf(0.5 + 1.0 / np.sqrt(4.0 * n_draws))
                                  * off.sigma_total),''',
     '        "mc_flip_band_pts": 0.33,',
     ["test_the_mc_flip_band_shrinks_as_draws_grow"]),
    ("the clustered SE collapses to the naive one", _MOD,
     'cse = float(per.std(ddof=1) / np.sqrt(k)) if k > 1 else float("nan")',
     'cse = naive_se if k > 1 else float("nan")',
     ["test_the_clustered_se_is_reported_beside_the_naive_one_and_is_larger_when_seasons_differ"]),
    ("`demonstrated` is collapsed into `resolvable` (the NF-W7i defect)", _MOD,
     '"demonstrated": bool(np.isfinite(lo) and (lo > 0 or hi < 0)),',
     '"demonstrated": bool(np.isfinite(mde) and abs(cm) >= mde),',
     ["test_demonstrated_and_resolvable_answer_different_questions_and_can_disagree"]),
    ("the band reading loses its lower side", _MOD,
     '"band_decisive_below": bool(np.isfinite(hi) and hi < MATERIAL_PTS),',
     '"band_decisive_below": False,',
     ["test_the_band_reading_is_two_sided_at_its_own_boundary"]),
    ("the cold-start contrast stops pairing within season", _MOD,
     "    d = np.array([e[s] - l[s] for s in common], float)",
     "    d = np.array([e[s] for s in common], float)",
     ["test_the_matched_contrast_cancels_a_season_wide_level"]),
    ("the contrast scores a single season instead of refusing", _MOD,
     "    if len(common) < 2:", "    if False:",
     ["test_the_matched_contrast_refuses_rather_than_score_one_season"]),
    ("the below-MDE injection is raised above it (the control always says yes)", _MOD,
     "    small = term_stats(centred + 0.4 * mde, c)",
     "    small = term_stats(centred + 1.5 * mde, c)",
     ["test_the_injection_controls_discriminate_in_both_directions"]),
    ("the level-in-disguise clause is removed from the verdict (NF-D10)", _MOD,
     '    if scoped and not (contrast["demonstrated"] and contrast["material"]):',
     "    if False:",
     ["test_a_level_in_disguise_is_refused_by_the_contrast_clause_alone"]),
    ("the sign test is smuggled back in as a hidden verdict clause", _MOD,
     '        rows[cell]["HANDS_TO_VAL3"] = bool(rows[cell]["material"] and rows[cell]["demonstrated"])',
     '        rows[cell]["HANDS_TO_VAL3"] = bool(rows[cell]["material"] and rows[cell]["demonstrated"]\n'
     '                                           and s["seasons_positive"] in (0, s["n_clusters"]))',
     ["test_the_sign_test_is_reported_but_is_not_a_verdict_clause"]),
    ("the pooled cell is made to answer the within-season contrast", _MOD,
     '    if "pooled" in winners:', '    if "pooled" in winners and contrast["demonstrated"]:',
     ["test_the_pooled_cell_is_exempt_from_the_contrast_clause"]),
    ("the two readings stop being disclosed side by side", _MOD,
     '            "verdict_under_mde_rule": ("HAND_TO_VAL3_SCOPED"',
     '            "verdict_under_mde_rule_REMOVED": ("HAND_TO_VAL3_SCOPED"',
     ["test_both_readings_are_disclosed_so_a_reader_can_apply_either_rule"]),
    ("the materiality band becomes a computed value (the E2.1-r inversion)", _MOD,
     "MATERIAL_PTS = 1.0", "MATERIAL_PTS = float(abs(-1.0))",
     ["test_the_materiality_band_is_stated_forward_as_a_constant"]),
    ("a cache of the wrong vintage is silently scored as VAL1's population", _MOD,
     '        "matches_val1_population": bool(matches),',
     '        "matches_val1_population": True,',
     ["test_a_cache_that_is_not_val1s_population_is_flagged_not_silently_used"]),
    ("a missing pace source degrades to a silently pace-free frame (NF1.7 a)", _MOD,
     "    out = derive_pace_composites(df)                      # RAISES if the source columns are absent",
     "    try:\n        out = derive_pace_composites(df)\n    except KeyError:\n"
     "        return df, feat, {'pace_derived_in_session': False}",
     ["test_a_missing_pace_source_raises_rather_than_producing_a_pace_free_frame"]),
    ("pushes are counted in the close's median reading", _MOD,
     '    nonpush = ~frame["is_push"].to_numpy()',
     "    nonpush = np.ones(len(frame), dtype=bool)",
     ["test_the_close_unit_reading_uses_non_push_rows_for_the_side_statistic"]),
    ("the query-only scope is breached", _MOD,
     "def main(argv: list[str] | None = None) -> int:",
     'def main(argv=None) -> int:\n    _sneak = "to_parquet("',
     ["test_the_study_is_query_only"]),
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
    print(f"=== NCAAF-VAL2 RED PROOF — {len(BREAKS)} deliberate breaks ===")
    for name, path, anchor, repl, tests in BREAKS:
        original = path.read_text()
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

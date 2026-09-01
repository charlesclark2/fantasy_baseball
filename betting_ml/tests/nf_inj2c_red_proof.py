"""nf_inj2c_red_proof.py — prove NF-INJ2c's node-1 guards actually FAIL on deliberately broken source.

    uv run python betting_ml/tests/nf_inj2c_red_proof.py

⛔ NOT a pytest module (no `test_` name) — it MUTATES source on disk. It restores every file in a
`finally`, and — the E11.26 lesson — it also restores any stale backup left by a previous run AT
STARTUP, because its own worst case is being killed mid-mutation.

THREE WAYS A RED PROOF LIES, all closed here:
  * #682 — the mutation NEVER LANDED (a quoting bug) and the pass was read as "the guard is
    vacuous". Every break asserts the file CHANGED on disk before pytest is invoked.
  * #815 — the mutation landed but did not move the ASSERTED predicate. Every break asserts its
    `gone` token is ABSENT afterwards, not merely that the file differs.
  * E11.24 `prediction_log` — `replace(old, new, 1)` landed on the WRONG symbol because two
    functions had byte-identical tails, and the harness reported a FALSE vacuity, which is the
    dangerous direction (it invites weakening a correct guard). Every anchor is asserted UNIQUE in
    its file before it is applied.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DIAG = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_nf_inj2c_coherence_diagnosis.py"
_INJ2_MD = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                    "nf_inj2_rate_permutation.md")
_CLAUDE = _REPO / "CLAUDE.md"
_SUITE = "betting_ml/tests/test_nf_inj2c_coherence_diagnosis.py"

#: (label, file, anchor, replacement, token that must be GONE afterwards, the guard(s) it must break)
BREAKS: list[tuple[str, Path, str, str, str, str]] = [
    ("the kernel-floor count silently narrows to the recorded definition", _DIAG,
     'moved = np.where(np.isfinite(g), gsafe != g, True)',
     'moved = np.where(np.isfinite(g), gsafe != g, False)',
     # ⚠️ the `gone` token must be as SPECIFIC as the anchor: `attribute()` carries the identical
     # expression under the name `floored`, so a loose token survives the mutation and the harness
     # (correctly) refuses the break rather than reporting a false vacuity (#815 / E11.24).
     'moved = np.where(np.isfinite(g), gsafe != g, True)',
     "test_the_recorded_binding_count_misses_a_non_finite_row_the_kernel_does_floor"),

    ("an inactive floor stops refuting the hypothesis", _DIAG,
     '    if not can_act:\n        state = "REFUTED"',
     '    if not can_act:\n        state = "ESTABLISHED"',
     'if not can_act:\n        state = "REFUTED"',
     "test_a_floor_that_cannot_act_refutes_the_hypothesis"),

    ("a floor-attributed violation stops ESTABLISHING it", _DIAG,
     '        state = "ESTABLISHED"\n        why = (f"{m1} of {total}',
     '        state = "REFUTED"\n        why = (f"{m1} of {total}',
     '        state = "ESTABLISHED"\n        why = (f"{m1} of {total}',
     "test_one_floor_attributed_violation_establishes_it"),

    ("the pre-existing CONTROL stops outranking the floor in attribution", _DIAG,
     '    if pre_existing:\n        return "M4_PRE_EXISTING"\n    if floored:',
     '    if floored:\n        return "M1_GAMES_FLOOR"\n    if pre_existing:',
     '    if pre_existing:\n        return "M4_PRE_EXISTING"',
     "test_attribution_by_control_outranks_the_floor_when_both_clauses_are_true"),

    ("the unexplained residual defaults to the hypothesis under test", _DIAG,
     '    return "M3_STAT_MIX_OR_PROMOTION"',
     '    return "M1_GAMES_FLOOR"',
     '    return "M3_STAT_MIX_OR_PROMOTION"',
     "test_a_row_no_clause_explains_falls_to_stat_mix_rather_than_to_the_hypothesis"),

    ("the under-2-games share is computed over the board instead of the violating rows", _DIAG,
     'acc["share_rows_under_2_games"] = round(sum(1 for x in g if x < 2.0) / len(g), 4) if g else None',
     'acc["share_rows_under_2_games"] = round(sum(1 for x in g if x < 2.0) / (len(g) + 100), 4) if g else None',
     '/ len(g), 4) if g else None',
     "test_the_under_two_games_share_is_over_the_violating_rows_not_the_board"),

    ("an arm with no violation reports a clean 0.0 worst breach instead of None", _DIAG,
     'acc["max_times_over"] = round(max(t), 3) if t else None',
     'acc["max_times_over"] = round(max(t), 3) if t else 0.0',
     'round(max(t), 3) if t else None',
     "test_an_arm_with_no_violation_profiles_as_empty_rather_than_as_clean_numbers"),

    ("the D4 annotation loses its POST-HOC marker", _INJ2_MD,
     "> This block is a POST-HOC ANNOTATION",
     "> This block is a note",
     "POST-HOC ANNOTATION",
     "test_the_d4_annotation_is_on_nf_inj2s_record_and_is_marked_as_an_annotation"),

    ("the D4 annotation drops the measurement and keeps only the suspicion", _INJ2_MD,
     "`served_giveback_pct` is **33.96 on all seven arms**",
     "`served_giveback_pct` may be the arm's own number",
     "33.96 on all seven arms",
     "test_the_d4_annotation_records_the_measurement_that_settles_the_baseline_question"),

    ("the D3 landmine loses the measurement that makes it actionable", _CLAUDE,
     "**FAILED at a worst absolute difference of 40.58 over 797 rows**",
     "**FAILED**",
     "40.58 over 797 rows",
     "test_the_d3_pin_against_capture_landmine_is_in_claude_md"),

    ("the fresh-worktree cache landmine is removed", _CLAUDE,
     "SILENTLY REBUILDS THE GITIGNORED FEATURE CACHES FROM A LIVE UPSTREAM",
     "rebuilds caches",
     "SILENTLY REBUILDS THE GITIGNORED FEATURE CACHES FROM A LIVE UPSTREAM",
     "test_the_fresh_worktree_cache_rebuild_landmine_is_in_claude_md"),
]


def _bak(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".redproof.bak")


def _restore_stale() -> None:
    """A previous run killed mid-mutation would leave a .bak beside a BROKEN file. Restore first —
    a red proof whose own failure mode is leaving deliberately broken source on disk is worse than
    no red proof (E11.26)."""
    for path in {b[1] for b in BREAKS}:
        b = _bak(path)
        if b.exists():
            print(f"  ⚠️  restoring a STALE backup left by an earlier run: {path.name}")
            path.write_text(b.read_text())
            b.unlink()


def _run(node_id: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", f"{_SUITE}::{node_id}", "-q",
                        "--no-header", "-p", "no:cacheprovider"],
                       cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    _restore_stale()
    reds, greens = 0, []
    for label, path, anchor, repl, gone, node in BREAKS:
        src = path.read_text()
        # ⭐ the E11.24 lesson: a non-unique anchor makes `replace(..., 1)` land on the wrong symbol
        # and the harness reports a FALSE vacuity.
        n = src.count(anchor)
        if n != 1:
            print(f"  ✗ ANCHOR NOT UNIQUE ({n} occurrences) for {label!r} — the break cannot be "
                  f"trusted to land where it is aimed")
            greens.append(label)
            continue
        _bak(path).write_text(src)
        try:
            path.write_text(src.replace(anchor, repl, 1))
            after = path.read_text()
            assert after != src, f"the mutation for {label!r} did not LAND on disk (#682)"
            assert gone not in after, (
                f"the mutation for {label!r} landed but the asserted token {gone!r} SURVIVED, so it "
                f"cannot move the predicate the guard reads (#815)")
            if _run(node):
                print(f"  ✗ GREEN on broken source — {label}  →  {node}")
                greens.append(label)
            else:
                print(f"  ✓ RED — {label}")
                reds += 1
        finally:
            path.write_text(_bak(path).read_text())
            _bak(path).unlink()
    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    if greens:
        print("VACUOUS GUARDS:")
        for g in greens:
            print(f"  - {g}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

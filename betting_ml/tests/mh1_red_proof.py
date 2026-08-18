"""mh1_red_proof.py — prove every MH1 guard actually FAILS on a deliberately broken world.

Not collected by pytest (no `test_` prefix): run it directly.

    uv run python betting_ml/tests/mh1_red_proof.py

⚠️ **FIVE WAYS A RED PROOF LIES, ALL OF WHICH THIS REPO HAS SHIPPED, ALL GUARDED HERE:**
  1. the mutation never LANDS on disk (#682)          → assert the file bytes changed
  2. it lands but does not MOVE the asserted token    → assert the token is GONE after (#815)
  3. it lands on the WRONG symbol (a duplicated tail) → assert the anchor is UNIQUE in the file
  4. `except Exception` misses pytest's `Failed`      → subprocess + exit code, no in-process raises
  5. a stale `__pycache__` serves the pre-mutation module → `PYTHONDONTWRITEBYTECODE` + no cache

Several MH1 guards assert on RECORDED ARTIFACTS, not on source, so a source mutation cannot make
them red. Those cases mutate the ARTIFACT instead, and every case that can write to the corpus
snapshots the affected files up front and restores them byte-for-byte in `finally`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = "betting_ml/tests/test_mh1_margin_attribution.py"

_CORPUS = [
    ROOT / "betting_ml/evaluation/feature_selection/bakeoff",
    ROOT / "quant_sports_intel_models/baseball/ablation_results",
    ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results",
]


@dataclass
class Break:
    name: str
    path: str
    old: str
    new: str
    expect_red: list[str]
    writes_corpus: bool = False
    extra: list[tuple[str, str, str]] = field(default_factory=list)  # (path, old, new)


BREAKS = [
    Break("sign flip is never flagged",
          "betting_ml/utils/margin_attribution.py",
          '"sign_flip": bool(total != 0 and contract != 0 and (contract > 0) != (total > 0)),',
          '"sign_flip": False,',
          ["test_a_contract_that_is_worse_holding_the_learner_fixed_is_flagged_as_a_SIGN_FLIP"]),
    Break("a sub-noise share is never marked unreliable",
          "betting_ml/utils/margin_attribution.py",
          "meaningful = None if floor is None else bool(abs(total) > floor)",
          "meaningful = None",
          ["test_the_share_is_marked_unreliable_when_its_denominator_is_inside_the_noise_floor",
           "test_the_renderer_refuses_to_print_a_percentage_it_has_just_called_unreliable"]),
    Break("the renderer prints a percentage it just called unreliable",
          "betting_ml/utils/margin_attribution.py",
          "show_share = share is not None and meaningful is not False",
          "show_share = share is not None",
          ["test_the_renderer_refuses_to_print_a_percentage_it_has_just_called_unreliable"]),
    Break("an unavailable decomposition stops naming its reason",
          "betting_ml/utils/margin_attribution.py",
          '        return {"available": False,\n'
          '                "reason": f"arm(s) absent from the scored table: '
          '{\', \'.join(missing)}"}',
          '        return {"available": False}',
          ["test_an_unavailable_decomposition_always_names_its_reason"]),
    Break("a higher-is-better metric silently inverts",
          "betting_ml/utils/margin_attribution.py",
          "    sign = 1.0 if lower_is_better else -1.0\n    total = sign * (inc - lead)",
          "    sign = 1.0\n    total = sign * (inc - lead)",
          ["test_a_higher_is_better_metric_does_not_silently_invert_the_split"]),
    Break("E7.9 keeps a second implementation instead of delegating",
          "betting_ml/scripts/e7_9_train_serve_consistency.py",
          "    return _shared_margin_decomposition(table_rows, incumbent_arm, leader_arm, metric,\n"
          "                                        noise_floor=noise_floor)",
          "    key = f'{metric}_mean'\n"
          "    scores = {r['arm']: r[key] for r in table_rows}\n"
          "    same_learner_ref = 'incumbent::' + leader_arm.partition('::')[2]\n"
          "    ref = scores.get(same_learner_ref)\n"
          "    return {'available': ref is not None}",
          ["test_e7_9_delegates_rather_than_keeping_a_second_implementation"]),
    Break("the shared owner's legacy arithmetic moves",
          "betting_ml/utils/margin_attribution.py",
          "    learner = sign * (inc - ref)",
          "    learner = sign * (ref - inc)",
          ["test_the_shared_owner_reproduces_every_recorded_E7_9_block_byte_for_byte",
           "test_the_components_sum_to_the_reported_margin_exactly"]),
    Break("the harness stops pairing the variant run with its incumbent",
          "betting_ml/scripts/model_bakeoff.py",
          "    inc = _load_run(target, tier, None, smoke)",
          "    inc = None",
          ["test_the_harness_still_pairs_a_variant_run_with_its_incumbent_run_LIVE"]),
    Break("the harness stops refusing an uncontrolled contrast",
          "betting_ml/scripts/model_bakeoff.py",
          '                if _cmp(inc, k) != _cmp(result, k)]',
          '                if False]',
          ["test_the_harness_refuses_to_pair_two_runs_that_are_not_a_controlled_contrast"]),
    Break("a recorded pairing silently goes inactive",
          "betting_ml/evaluation/feature_selection/bakeoff/"
          "bakeoff_home_win_post_lineup_home_win_post_reprune_glm.json",
          '"available": true',
          '"available": false',
          ["test_the_paired_runs_are_the_ones_the_decomposition_actually_acts_on"]),
    # ── artifact-side breaks: these guards read the RECORDED corpus, so source cannot move them ──
    Break("a report loses its attribution section",
          "quant_sports_intel_models/baseball/ablation_results/bakeoff_run_diff_post_lineup.md",
          "## ⚠️ Margin attribution — learner swap vs contract",
          "## Notes",
          ["test_every_recorded_bakeoff_report_carries_the_attribution_block"]),
    Break("an inactive report stops explaining WHY it is inactive",
          "quant_sports_intel_models/baseball/ablation_results/bakeoff_run_diff_post_lineup.md",
          "this run scores a single contract, so it has NO contract axis",
          "not applicable",
          ["test_a_report_that_cannot_decompose_says_so_in_words_a_reader_will_see"]),
    Break("a stored decision field moves",
          "betting_ml/evaluation/feature_selection/bakeoff/bakeoff_run_diff_post_lineup.json",
          '"winner": "ngboost_normal"',
          '"winner": "catboost"',
          ["test_no_verdict_gate_or_selection_moved_across_the_whole_migration"]),
    Break("the recorded sign flip is quietly erased",
          "betting_ml/evaluation/feature_selection/bakeoff/"
          "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.json",
          '"sign_flip": true',
          '"sign_flip": false',
          ["test_the_recorded_sign_flip_is_on_the_record"]),
]


def _snapshot() -> dict[Path, bytes]:
    snap: dict[Path, bytes] = {}
    for d in _CORPUS:
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".md"):
                snap[p] = p.read_bytes()
    return snap


def _restore(snap: dict[Path, bytes]) -> None:
    for p, b in snap.items():
        if p.read_bytes() != b:
            p.write_bytes(b)


def _run_guard(names: list[str]) -> tuple[set[str], str]:
    """Run the guard file in a SUBPROCESS and return the set of tests that FAILED.

    A subprocess is not stylistic: pytest's own `Failed` derives from `BaseException`, so an
    in-process `except Exception` would let a deliberate break sail through and report success
    (NF-W6c). An exit code cannot lie about that.
    """
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-m", "pytest", GUARD, "-q", "-p", "no:cacheprovider", "--no-header",
         "-rf"],
        cwd=ROOT, capture_output=True, text=True, env=env)
    failed = {n for n in names if f"::{n}" in out.stdout}
    return failed, out.stdout


def main() -> int:
    assert BREAKS, "no breaks declared — this proof would pass on nothing"
    baseline_snap = _snapshot()
    problems: list[str] = []
    checked = 0

    for br in BREAKS:
        path = ROOT / br.path
        original = path.read_text()
        # (3) the anchor must be UNIQUE, or the mutation can land on the wrong symbol
        n = original.count(br.old)
        if n != 1:
            problems.append(f"[{br.name}] anchor occurs {n}× in {br.path} (must be exactly 1)")
            continue
        snap = _snapshot() if br.writes_corpus else {}
        try:
            path.write_text(original.replace(br.old, br.new, 1))
            mutated = path.read_text()
            # (1) it LANDED, and (2) the asserted token is GONE
            if mutated == original:
                problems.append(f"[{br.name}] mutation did not land on disk")
                continue
            if br.old in mutated:
                problems.append(f"[{br.name}] mutation landed but the token survives — the "
                                f"assertion may not have moved")
                continue
            failed, log = _run_guard(br.expect_red)
            checked += 1
            missing = [t for t in br.expect_red if t not in failed]
            if missing:
                problems.append(f"[{br.name}] guard stayed GREEN on broken source: "
                                f"{', '.join(missing)}")
            else:
                print(f"  RED  {br.name}  → {', '.join(sorted(failed))}")
        finally:
            path.write_text(original)
            if snap:
                _restore(snap)

    _restore(baseline_snap)
    # the world must be exactly as we found it
    residue = [str(p) for p, b in baseline_snap.items() if p.read_bytes() != b]
    if residue:
        problems.append(f"corpus NOT restored: {residue}")

    print(f"\nbreaks exercised: {checked}/{len(BREAKS)}")
    if checked != len(BREAKS):
        problems.append("a break was skipped — a proof that skips is a proof that passes")
    if problems:
        print("\n".join(f"❌ {p}" for p in problems))
        return 1
    # a final green run proves the restore really restored
    final = subprocess.run([sys.executable, "-m", "pytest", GUARD, "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, capture_output=True, text=True)
    if final.returncode != 0:
        print("❌ guard is RED after restore — the world was not put back")
        print(final.stdout[-3000:])
        return 1
    print("✅ every declared break turned its guard RED, and the corpus was restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

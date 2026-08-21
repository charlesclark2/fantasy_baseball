"""RED proof for the NF-TR2b placement guards — every clause must FAIL on a deliberately broken
source, or it is decoration (NF1.7 (a) / INC-38 / INC-39).

THIS HARNESS DEFENDS AGAINST THE FOUR WAYS A RED PROOF ITSELF LIES:
  1. the mutation never LANDS            -> the file content is asserted to have CHANGED (#682)
  2. it lands but does not move the      -> the mutated token is asserted ABSENT afterwards (#815)
     asserted predicate
  3. it lands on the WRONG symbol        -> the anchor is asserted UNIQUE in the file
  4. `pytest.raises` raises `Failed`,    -> the runner catches BaseException, never Exception
     a BaseException subclass                (NF-W6c)

It also RESTORES stale backups at start-up: its own worst case is being killed mid-mutation, and a
signal skips `finally` (E11.26).

RUN (LAPTOP, seconds):  uv run python betting_ml/tests/nf_tr2b_placement_red_proof.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PL = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/nf_tr2b_placement.py"
_RUN = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_nf_tr2b_placement_read.py"
_TESTS = _ROOT / "betting_ml/tests/test_nf_tr2b_placement_read.py"

# (label, target file, unique anchor to replace, replacement, test that MUST go red)
BREAKS: list[tuple[str, pathlib.Path, str, str, str]] = [
    ("reconstruction ignores the ROOKIE leg (scales rookies too)", _PL,
     "    touched = is_vet & at_recal_pos",
     "    touched = at_recal_pos",
     "test_reconstruction_divides_only_veterans_at_recalibrated_positions"),

    ("G1 can no longer fail (pass hard-wired True)", _PL,
     "            if a != b:\n                out[\"pass\"] = False",
     "            if False:\n                out[\"pass\"] = False",
     "test_g1_goes_red_on_a_non_monotone_transform"),

    ("G1 reverts to a WHOLE-position claim (leg scoping dropped)", _PL,
     "        rec_pos[\"whole_position_order_identical\"] = bool(whole)",
     "        rec_pos[\"whole_position_order_identical\"] = bool(whole)\n"
     "        out[\"pass\"] = bool(out[\"pass\"] and whole)",
     "test_g1_passes_when_each_leg_keeps_its_own_order_and_reports_the_cross_leg_break"),

    ("G2 transcribes the cap instead of delegating it", _PL,
     "    verdict = rookie_placement_breach(best)",
     "    verdict = rookie_placement_breach(best)\n"
     "    verdict = {**verdict, \"breach\": bool(best is not None and best < 9)}",
     "test_g2_delegates_the_cap_and_transcribes_no_threshold_of_its_own"),

    ("G2 direction inverted (a rookie at #1 no longer breaches)", _PL,
     "    return {\"best_rookie_overall_rank\": best, \"verdict\": verdict,\n"
     "            \"pass\": verdict.get(\"breach\") is not True}",
     "    return {\"best_rookie_overall_rank\": best, \"verdict\": verdict,\n"
     "            \"pass\": True}",
     "test_g2_is_two_sided_a_rookie_placed_too_high_trips_it_and_moving_it_down_clears_it"),

    ("an UNEVALUABLE gate is scored HEALTHY (NF1.7 (a) violated)", _PL,
     "        detail[name] = \"PASS\" if p is True else (\"FAIL\" if p is False else \"UNEVALUABLE\")",
     "        detail[name] = \"FAIL\" if p is False else \"PASS\"",
     "test_g2_is_unevaluable_rather_than_healthy_on_a_board_with_no_rookies"),

    ("G3 can no longer fail (survival hard-wired)", _PL,
     "            \"wiped_out\": missing, \"pass\": not missing}",
     "            \"wiped_out\": missing, \"pass\": True}",
     "test_g3_trips_when_a_recalibrated_position_is_wiped_out_of_the_top_n"),

    ("G4 stops checking that the point sits inside its own band", _PL,
     "\"pass\": bool(bad_order == 0 and above == 0 and below == 0)}",
     "\"pass\": bool(bad_order == 0)}",
     "test_g4_catches_an_inverted_band_and_a_point_outside_its_own_band"),

    ("the runner writes OUTSIDE the checkout (the parents[5] bug)", _RUN,
     "_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]",
     "_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]",
     "test_the_runner_writes_only_inside_the_repo_and_only_its_own_paths"),

    ("an optional `adp` column becomes REQUIRED (a board without it crashes)", _PL,
     "        \"adp\": (pd.to_numeric(b[\"adp\"], errors=\"coerce\").to_numpy()\n"
     "                if \"adp\" in b.columns else np.full(len(b), np.nan)),",
     "        \"adp\": pd.to_numeric(b.get(\"adp\"), errors=\"coerce\").to_numpy(),",
     "test_a_board_without_an_adp_column_still_produces_a_read"),

    ("a stamp-less payload DEFAULTS instead of raising", _RUN,
     "    if not k:\n        raise RuntimeError(",
     "    if not k:\n        k = {\"QB\": 1.0, \"RB\": 1.0, \"WR\": 1.0, \"TE\": 1.0}\n"
     "    if False:\n        raise RuntimeError(",
     "test_k_is_read_from_the_served_artifact_and_a_missing_stamp_raises"),
]


def _restore_stale() -> None:
    for f in (_PL, _RUN):
        bak = f.with_suffix(f.suffix + ".redproof.bak")
        if bak.exists():
            print(f"  [restore] stale backup found for {f.name} — restoring before starting")
            f.write_text(bak.read_text()); bak.unlink()


def _run_test(node: str) -> bool:
    """True == the test went RED (which is what a break must produce)."""
    r = subprocess.run([sys.executable, "-m", "pytest", f"{_TESTS}::{node}", "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       cwd=_ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode != 0


def main() -> int:
    _restore_stale()
    print(f"NF-TR2b placement RED proof — {len(BREAKS)} deliberate breaks\n")
    # a break is only meaningful if the suite is GREEN to begin with
    base = subprocess.run([sys.executable, "-m", "pytest", str(_TESTS), "-q", "--no-header",
                           "-p", "no:cacheprovider"],
                          cwd=_ROOT, capture_output=True, text=True, timeout=600)
    if base.returncode != 0:
        print("BASELINE IS ALREADY RED — a RED proof over a failing suite proves nothing.")
        print(base.stdout[-2000:])
        return 2
    print("baseline: GREEN\n")

    reds = 0
    for label, target, anchor, repl, node in BREAKS:
        original = target.read_text()
        # (3) the anchor must be UNIQUE, or the break can land on the wrong symbol
        n = original.count(anchor)
        if n != 1:
            print(f"  ✗ {label}\n      ANCHOR NOT UNIQUE in {target.name} (found {n}) — "
                  f"cannot prove which symbol was mutated"); continue
        bak = target.with_suffix(target.suffix + ".redproof.bak")
        bak.write_text(original)
        try:
            mutated = original.replace(anchor, repl, 1)
            target.write_text(mutated)
            # (1) the mutation must have LANDED and (2) must have MOVED the asserted token
            landed = target.read_text() != original
            gone = anchor not in target.read_text() or repl.startswith(anchor)
            if not landed:
                print(f"  ✗ {label}\n      MUTATION DID NOT LAND — result is meaningless"); continue
            if not gone:
                print(f"  ✗ {label}\n      mutation landed but the anchor SURVIVES — the asserted "
                      f"predicate may not have moved"); continue
            red = _run_test(node)
        except BaseException as exc:                      # (4) pytest's Failed is a BaseException
            print(f"  ✗ {label}\n      harness error: {exc!r}")
            red = False
        finally:
            target.write_text(bak.read_text()); bak.unlink()
        reds += bool(red)
        print(f"  {'✓ RED' if red else '✗ GREEN (VACUOUS GUARD)'}  {label}\n      -> {node}")

    print(f"\n{reds}/{len(BREAKS)} breaks produced RED")
    after = subprocess.run([sys.executable, "-m", "pytest", str(_TESTS), "-q", "--no-header",
                           "-p", "no:cacheprovider"],
                          cwd=_ROOT, capture_output=True, text=True, timeout=600)
    print(f"source restored + suite green again: {after.returncode == 0}")
    return 0 if (reds == len(BREAKS) and after.returncode == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())

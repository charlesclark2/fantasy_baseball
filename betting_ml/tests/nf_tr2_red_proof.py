"""RED proof for NF-TR2 / NF-TR2b's guards — `uv run python betting_ml/tests/nf_tr2_red_proof.py`.

Each claim in `test_nf_tr2_level_recalibration.py` is proved by re-introducing the defect it
guards against and requiring the named test to go RED. Applies each break to the SOURCE FILE,
asserts the mutation LANDED (a red proof whose mutation no-ops reports a false "caught it" —
E11.24 #682), runs pytest in a SUBPROCESS (so `pytest.raises`' `Failed`, a BaseException, cannot
leak past a too-narrow `except` — NF-W6c), and restores the file in a `finally`.

⚠️ Only pytest exit code 1 (tests FAILED) counts as RED. 2/3/4/5 (interrupted / internal / usage /
nothing collected) is a BROKEN HARNESS, never a caught break — a missing-module non-zero exit reads
as "the guard caught it" otherwise (NF-INFRA1).

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~40s.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_tr2_level_recalibration.py"
_SLR = "quant_sports_intel_models/football/nfl/fantasy/season_level_recalibration.py"
_SP = "quant_sports_intel_models/football/nfl/fantasy/season_projection.py"
_RSP = "quant_sports_intel_models/football/nfl/fantasy/run_season_projection.py"
_EX = "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
_VLP = "quant_sports_intel_models/football/nfl/fantasy/veteran_level_policy.py"

BREAKS = [
    ("estimator: mean-of-ratios instead of the mean-match (NF-RECAL1's estimator)", _SLR,
     "            out[q] = float(np.clip(y[sel].sum() / p[sel].sum(), *clip))",
     "            out[q] = float(np.clip(np.mean(y[sel] / p[sel]), *clip))",
     "estimator_targets_realized or ratio_of_sums"),
    ("estimator: a thin position gets ZERO instead of being left alone", _SLR,
     "        else:\n            out[q] = 1.0\n    return out",
     "        else:\n            out[q] = 0.0\n    return out",
     "thin_position_is_left_alone"),
    ("invert_level: the incumbent-equivalent is the served point (no inversion)", _SLR,
     "            if k > 0:\n                out[pos == q] = n[pos == q] / k",
     "            if k > 0:\n                out[pos == q] = n[pos == q]",
     "byte_identical_under_the_level_shift or preserves_within_position_order_exactly_and_inverts"),
    ("attach_season_interval: query the band at the SERVED point (the naive re-derivation)", _SP,
     '        if "veteran_level_form" in df.columns:\n            forms = df["veteran_level_form"]',
     '        if False and "veteran_level_form" in df.columns:\n            forms = df["veteran_level_form"]',
     "byte_identical_under_the_level_shift"),
    ("attach_season_interval: invert ROOKIE rows too (the board-wide stamp misread)", _SP,
     '            if "is_rookie" in df.columns:      # the stamp is board-wide; the correction is veteran-only\n'
     '                forms = forms.where(~df["is_rookie"].fillna(False).astype(bool), "")',
     '            pass',
     "rookie_rows_are_never_inverted"),
    ("recalibrate_projected_frame: silently allow proj_games to move (L4)", _SLR,
     "    if not np.array_equal(games_before, games_after, equal_nan=True):",
     "    if False:",
     "raises_if_games_move"),
    ("recalibrate_projected_frame: move the point but NOT the stat line", _SLR,
     "    for col in _SCALED_LINE_COLS:\n        if col in out.columns:",
     "    for col in _SCALED_LINE_COLS:\n        if False:",
     "scales_the_line_and_leaves_games_untouched"),
    ("level_gate: L1 always passes", _SLR,
     "    l1 = bool(abs(b_win) <= (1.0 - reduction_min) * abs(b_inc) + 1e-12)",
     "    l1 = True",
     "L1_fails_alone"),
    ("level_gate: L2 always passes", _SLR,
     "        l2[q] = bool(bw <= max((1.0 - reduction_min) * bi, se_mult * s) + 1e-12)",
     "        l2[q] = True",
     "L2_fails_alone"),
    ("level_gate: L3 ignores 'significantly hot' AND over_scale (no-inflation guard removed)", _SLR,
     "    l3 = bool(l3_not_hot and (over_scale_loses is True))",
     "    l3 = True",
     "L3_fails_alone"),
    ("level_gate: L4 ignores the games check", _SLR,
     '        "pass": bool(l1 and all(l2.values()) and l3 and games_untouched),',
     '        "pass": bool(l1 and all(l2.values()) and l3),',
     "L4_fails_alone"),
    ("window: the derivation returns the pinned constant regardless of the tier composition", _SLR,
     "    thin = min(float(v) for v in rows_per_position_per_season.values())\n"
     "    return int(np.ceil(min_rows / max(thin, 1e-9)))",
     "    return int(WINDOW_SEASONS)",
     "window_is_derived"),
    ("window_mask: drop the strictly-before clause (a fit could see its own season)", _SLR,
     "    keep = s < float(target_season)\n    if window is not None:",
     "    keep = np.ones(len(s), dtype=bool)\n    if window is not None:",
     "window_is_derived"),
    ("decomposition: the rate term is charged to zero-game rows too", _SLR,
     "    rate = np.where(gr > 0, gr * (rh - r_row), 0.0)",
     "    rate = gh * (rh - r_row)",
     "decomposition_identity"),
    ("project_veterans: apply the level but drop the stamp columns (the band would re-derive wrong)",
     _SP,
     '        df["veteran_level_form"] = lvl_form\n        df["veteran_level_params"] = _SLR.params_to_json(lvl_params)',
     '        pass',
     "project_veterans_applies_the_level"),
    ("OUTPUT_COLS: drop level_model_version (the governance stamp)", _RSP,
     '    "veteran_level_statistically_selected", "level_model_version",\n]',
     '    "veteran_level_statistically_selected",\n]',
     "output_cols_carry"),
    ("exporter: publish the params as a string-in-a-string (no decode)", _EX,
     '        if col == "veteran_level_params" and isinstance(v, str):',
     '        if False:',
     "exporter_reads_the_stamp"),
    ("policy: assert_coherent no longer refuses an incoherent flip", _VLP,
     '    if SERVING_ENABLED and DISPOSITION != "SHIP":',
     '    if False:',
     "policy_flip_is_one_read"),
    ("policy: the window drifts from the registration", _VLP,
     "WINDOW_SEASONS = 5 ",
     "WINDOW_SEASONS = 3 ",
     "policy_reads_the_registration"),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            failures.append(f"{name}: MUTATION TARGET NOT FOUND in {rel}")
            print(f"{'BROKEN ❌':26} {name} — mutation target not found")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name  # the mutation must actually land
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:26} {name}\n{'':26} -> {tail}")
        finally:
            path.write_text(original)
    print()
    if failures:
        print("VACUOUS / BROKEN:", *failures, sep="\n  - ")
        return 1
    print(f"All {len(BREAKS)} deliberate breaks were caught.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

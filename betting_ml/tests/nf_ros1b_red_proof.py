"""nf_ros1b_red_proof.py — prove every NF-ROS1b guard can actually FAIL (⛔ NOT a pytest module).

Reuses the parent's RED-proof machinery (`nf_ros1_red_proof.py`: baseline-pass, resolve-every-node,
NOT-SELECTED ⇒ only pytest exit 1 is a red, unique anchors, token-gone, stale-backup restore) by
pointing its module globals at this story's tests, sources and breaks — one owner of the harness.

    uv run python betting_ml/tests/nf_ros1b_red_proof.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nf_ros1_red_proof as P  # noqa: E402

ROOT = P.ROOT
FANT = ROOT / "quant_sports_intel_models/football/nfl/fantasy"
RI = FANT / "ros_interval.py"
RUN = FANT / "run_nf_ros1.py"
B = FANT / "run_nf_ros1b.py"
Break = P.Break

BREAKS: tuple[Break, ...] = (
    Break("the atom is ignored (every level reads the ratio)", RI,
          "    q = np.where((tau <= pi[:, None]) | (pred[:, None] <= 0), 0.0, q)",
          "    q = np.where(pred[:, None] <= 0, 0.0, q)",
          gone="(tau <= pi[:, None]) |",
          tests=("test_hurdle_positive_control_reads_flat",
                 "test_mixture_is_monotone_and_the_atom_levels_are_exactly_zero")),
    Break("the conditional level is not renormalized by (1 − π)", RI,
          "    u = (tau - pi[:, None]) / denom",
          "    u = tau + 0.0 * pi[:, None]",
          gone="(tau - pi[:, None]) / denom",
          tests=("test_hurdle_positive_control_reads_flat",)),
    Break("the spread is additive, not scaled by the projection", RI,
          "    q = pred[:, None] * eps", "    q = pred[:, None] + eps",
          gone="pred[:, None] * eps",
          tests=("test_scale_equivariance", "test_a_zero_point_is_a_point_mass_at_zero")),
    Break("the ratio table stores residuals, not ratios", RI,
          "    ratio = np.where(pos_rows, y / np.where(pred > 0, pred, 1.0), np.nan)",
          "    ratio = np.where(pos_rows, y - pred, np.nan)",
          gone="y / np.where(pred > 0, pred, 1.0)",
          tests=("test_hurdle_positive_control_reads_flat",)),
    Break("zero-point rows are counted as needing a ratio", RI,
          "        mp = np.where((pos == P) & (pred > 0))[0]",
          "        mp = np.where(pos == P)[0]",
          gone="mp = np.where((pos == P) & (pred > 0))[0]",
          tests=("test_ratio_fallback_is_counted_only_where_a_ratio_is_needed",)),
    Break("the foil's features read the REAL miss_streak", RI,
          '        "miss_streak": df[f"{prefix}miss_streak"].to_numpy(dtype=float),',
          '        "miss_streak": df["miss_streak"].to_numpy(dtype=float),',
          gone='df[f"{prefix}miss_streak"]',
          tests=("test_pi_features_are_the_registered_set_in_order",)),
    Break("the hurdle event becomes y < 0", RI,
          '            zt = (train[f"y_{preset}"].to_numpy(dtype=float) <= 0).astype(int)',
          '            zt = (train[f"y_{preset}"].to_numpy(dtype=float) < 0).astype(int)',
          gone="dtype=float) <= 0).astype(int)",
          tests=("test_the_hurdle_event_is_y_at_or_below_zero",)),
    Break("the logistic regularization drifts", RI,
          "LOGIT_C = 1.0\n", "LOGIT_C = 0.5\n", gone="LOGIT_C = 1.0\n",
          tests=("test_the_registered_constants",)),
    Break("miss_streak never resets when he plays", RI,
          "            if n[i] > pn[i]:\n                s = 0.0\n",
          "            if n[i] > pn[i]:\n                pass\n",
          gone="                s = 0.0\n            elif",
          tests=("test_miss_streak_counts_missed_team_games_and_skips_the_bye",)),
    Break("a bye counts as a missed game", RI,
          "            elif t[i] > pt[i]:", "            else:",
          gone="elif t[i] > pt[i]:",
          tests=("test_miss_streak_counts_missed_team_games_and_skips_the_bye",)),
    # the first cut (pn = the NEXT row's n) only stopped resets — it never made a row depend on a
    # later week, so the leak clause rightly stayed green. This break reads the season's last row.
    Break("miss_streak reads the season's last row (future leak)", RI,
          "            if n[i] > pn[i]:\n",
          "            if n[-1] > pn[i]:\n",
          gone="if n[i] > pn[i]:",
          tests=("test_miss_streak_reads_no_week_after_k",)),
    Break("ros_interval grows an IO import", RI,
          "import numpy as np\nimport pandas as pd\n\nfrom quant_sports_intel_models",
          "import numpy as np\nimport pandas as pd\nimport requests  # noqa: F401\n\n"
          "from quant_sports_intel_models",
          gone="import pandas as pd\n\nfrom quant_sports_intel_models",
          tests=("test_ros_interval_never_imports_pipeline_or_does_io",)),
    Break("the foil stops carrying the donor's miss_streak", RUN,
          '        if carry_streak:\n            f.loc[idx, "perm_miss_streak"]',
          '        if False:\n            f.loc[idx, "perm_miss_streak"]',
          gone='if carry_streak:\n            f.loc[idx',
          tests=("test_the_foil_carries_the_donors_streak",)),
    Break("the hook is not inert (a reference is built without an interval)", RUN,
          '    if interval is not None:\n        out["reference"] = {}',
          '    if True:\n        out["reference"] = {}',
          gone='if interval is not None:\n        out["reference"]',
          tests=("test_the_hook_is_inert_when_no_interval_is_passed",)),
    Break("hurdle mode silently keeps the parent residual table", RUN,
          "            if interval is None:\n                q, fb = V.apply_residual_table(table, test",
          "            if True:\n                q, fb = V.apply_residual_table(table, test",
          gone="if interval is None:\n                q, fb = V.apply_residual_table(table, test",
          tests=("test_the_hurdle_replaces_every_predictors_interval_but_not_its_point",)),
    Break("the reference is built with the hurdle table", RUN,
          "                ref_q, _ = V.apply_residual_table(_loso_residual_table(train, arm, preset),",
          "                ref_q, _ = V.apply_residual_table(_loso_residual_table(train, arm, preset,"
          " interval=interval),",
          gone="_loso_residual_table(train, arm, preset),",
          tests=("test_the_hurdle_replaces_every_predictors_interval_but_not_its_point",)),
    Break("the foil is handed the REAL π", RUN,
          'ptable,\n            prefix="perm_")', "ptable)",
          gone='ptable,\n            prefix="perm_")',
          tests=("test_every_predictor_reads_its_own_hurdle_probability",)),
    Break("the successor writes over the parent's record", B,
          'STEM = "nf_ros1b_walkforward"', 'STEM = "nf_ros1_walkforward"',
          gone='STEM = "nf_ros1b_walkforward"',
          tests=("test_the_successor_never_writes_the_parents_record",)),
    Break("the reference label is dropped from the report", B,
          "`{RI.REFERENCE_KEY}` — **{RI.REFERENCE_LABEL}**", "`{RI.REFERENCE_KEY}`",
          gone="**{RI.REFERENCE_LABEL}**",
          tests=("test_the_full_evaluate_runs_and_writes_a_labelled_report",)),
    Break("the interval leaks into the compared result", B,
          "            result[\"hurdle\"] = hurdle_extras(result, interval)\n    return result\n",
          "            result[\"hurdle\"] = hurdle_extras(result, interval)\n"
          "    result[\"interval\"] = interval_name\n    return result\n",
          gone="hurdle_extras(result, interval)\n    return result\n",
          tests=("test_the_full_evaluate_runs_and_writes_a_labelled_report",)),
    Break("the reproduction comparison ignores non-numeric mismatches", B,
          "    return (0.0, []) if a == b else (0.0, [f\"{path}: {a!r} != {b!r}\"])",
          "    return (0.0, [])",
          gone="if a == b else",
          tests=("test_max_abs_diff_sees_numbers_structure_and_ignores_meta",)),
    Break("a WRONG join reads as CORRECT", B,
          '        return "CORRECT" if rid == auth else "WRONG"',
          '        return "CORRECT"',
          gone='if rid == auth else "WRONG"',
          tests=("test_a_wrong_join_is_never_correct",)),
    Break("the pick key is trusted without the position check", B,
          'bool(len(hit) == 1 and LS.normalize_position(\n'
          '                           hit["position"].iloc[0]) == LS.normalize_position(r["position"])),',
          "bool(len(hit) == 1),",
          gone='hit["position"].iloc[0]) == LS.normalize_position',
          tests=("test_the_pick_key_is_refused_when_a_position_disagrees",)),
)


def _batched_collects_one(nodes):
    """One collect-only call for every node (the parent checks one node per subprocess); the
    same rule — each named node resolves to exactly one collected test."""
    r = P._pytest(["--collect-only", *[f"{P.TESTS}::{n}" for n in nodes]])
    got = [ln.split("::", 1)[1] for ln in r.stdout.splitlines() if "::" in ln]
    return {n: got.count(n) == 1 for n in nodes} if r.returncode == 0 else {n: False for n in nodes}


def main() -> int:
    P.TESTS = "betting_ml/tests/test_nf_ros1b_interval.py"
    nodes = sorted({t for b in BREAKS for t in b.tests})
    resolved = _batched_collects_one(nodes)
    P._collects_one = lambda node: resolved.get(node, False)
    P.PATHS = (RI, RUN, B)
    P.BREAKS = BREAKS
    return P.main()


if __name__ == "__main__":
    raise SystemExit(main())

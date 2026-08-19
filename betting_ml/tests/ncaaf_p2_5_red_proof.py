"""RED proof for NCAAF-P2.5's guards — `uv run python betting_ml/tests/ncaaf_p2_5_red_proof.py`.

Every claim in `test_ncaaf_p2_5_shapes.py` is proved by RE-INTRODUCING the defect it guards against
and requiring the named test to go RED. Harness contract (a red proof has at least five ways to lie,
and this repo has been burned by four of them):

  * the mutation anchor must be **UNIQUE** in the file — two byte-identical tails make a
    `replace(old, new, 1)` land on the WRONG symbol and the run comes back GREEN reporting a FALSE
    "the guard is vacuous", which invites weakening a correct guard (E11.24 prediction_log);
  * the mutation must be asserted to have **LANDED** — a silently no-op'd break reads as "the guard
    caught it" (E11.24 #682);
  * where a guard asserts on a TOKEN, that token must be asserted **GONE** after the mutation. A
    break that lands but leaves the assertion satisfied is a false GREEN (E11.24 #815);
  * pytest runs in a **SUBPROCESS**, so `pytest.raises`' `Failed` (a `BaseException`, not an
    `Exception`) cannot leak past a too-narrow `except` and be read as a pass (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED. 2/3/4/5 is a BROKEN HARNESS, never a caught
    break — otherwise a syntax error reads as "the guard caught it" (NF-INFRA1);
  * every file is restored in a `finally`.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~90 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_ncaaf_p2_5_shapes.py"
_S = "quant_sports_intel_models/football/ncaaf/models/p2_5_shapes.py"
_H = "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_p2_5.py"
_P = "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p2_5_preregistration.md"

#: (name, file, old, new, `pytest -k` selector, a token that must be GONE after the mutation | None)
BREAKS: list[tuple[str, str, str, str, str, str | None]] = [
    # ── the declared field + the anchor/trial separation ────────────────────────────────────────
    ("field: silently drop an arm from the declared field (MH2.2 post-hoc trim)", _S,
     '    Shape("mixture", "Gaussian / regime mixture", True, "shift = 0 and s1 = s2", False),\n',
     "",
     "declared_field_is_the_ten_registered_shapes", '"Gaussian / regime mixture"'),
    ("anchors: let a diagnostic anchor join the trial field (MH2.1 a)", _S,
     'GENERIC_ANCHORS: tuple[str, ...] = ("permute", "zero_width", "max_width", "coverage_target")',
     'GENERIC_ANCHORS: tuple[str, ...] = ("permute", "zero_width", "max_width", "coverage_target",\n'
     '                                   "incumbent")',
     "anchors_are_excluded_from_the_declared_field", None),
    ("DSR: measure V over EVERY arm, so the anchors set the gate's own bar", _H,
     "    series = {a: fold_series(foil, arms[a]) for a in real}",
     "    series = {a: fold_series(foil, arms[a]) for a in list(arms) if a != shp.FOIL_ARM}",
     "V_is_measured_over_the_real_arms_only",
     "series = {a: fold_series(foil, arms[a]) for a in real}"),
    ("DSR: n_trials stops being the declared field", _H,
     "    n_trials = shp.DECLARED_FIELD_SIZE",
     "    n_trials = len(real)",
     "n_trials_is_the_declared_field_size", "n_trials = shp.DECLARED_FIELD_SIZE"),
    ("classify_null: fall back to the GAUSSIAN moment default (S1b defect 1)", _H,
     '            skew=r["series_skew"], kurt=r["series_kurt"],\n',
     "",
     "classify_null_gets_the_declared_field_size_and_the_measured_moments",
     'skew=r["series_skew"], kurt=r["series_kurt"]'),

    # ── the frozen-mean invariant (C7) ──────────────────────────────────────────────────────────
    ("C7: widen the mean tolerance until a mean-shifted arm passes", _S,
     "MEAN_PRESERVATION_TOL: float = 0.15",
     "MEAN_PRESERVATION_TOL: float = 50.0",
     "mean_preservation_flags_an_arm_that_moved_the_mean", "MEAN_PRESERVATION_TOL: float = 0.15"),
    ("C7: check the mean on a RE-DERIVED sample instead of the scored one (NF-W7d)", _H,
     "    mean_ok = shp.mean_preservation(m_s, t_s, c.mu_m_ev, c.mu_t_ev)",
     "    mean_ok = shp.mean_preservation(*draw_arm(arm, c, np.random.default_rng(1), 64)[:2],\n"
     "                                    c.mu_m_ev, c.mu_t_ev)",
     "the_mean_check_runs_on_the_scored_samples_not_a_re_derivation",
     "mean_ok = shp.mean_preservation(m_s, t_s, c.mu_m_ev, c.mu_t_ev)"),

    # ── the amended arms (A8.1 / A8.2 / A8.4 / A8.5) ────────────────────────────────────────────
    ("A8.1: treat the tilt bandwidth as the resulting sd again (the straw-man arm)", _S,
     "        _, _, var = _moments(c, inv_b2)          # outer: land the VARIANCE at v_target\n"
     "        inv_b2 = np.clip(inv_b2 + (1.0 / v_t - 1.0 / var), 1e-6, 1.0)",
     "        inv_b2 = np.clip(1.0 / v_t, 1e-6, 1.0)",
     "the_lattice_tilt_hits_the_target_variance_not_the_bandwidth",
     "inv_b2 + (1.0 / v_t - 1.0 / var)"),
    ("A8.1: never solve the tilt centre, so the mean drifts off the frozen mean", _S,
     "        c = _solve_mean(c, inv_b2)               # inner: land the MEAN at \u03bc",
     "        pass",
     "the_lattice_tilt_hits_the_target_variance_not_the_bandwidth",
     "c = _solve_mean(c, inv_b2)               # inner"),
    ("A8.4: restore knots the sample size cannot estimate (1/α > leaf size)", _S,
     "QB_LEVELS: np.ndarray = np.array(\n"
     "    [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95])",
     "QB_LEVELS: np.ndarray = np.array(\n"
     "    [0.005, 0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.80, 0.90, 0.95, 0.99, 0.995])",
     "quantile_foil_collapses_to_the_marginal_on_informationless_drivers", None),
    ("A8.5: re-introduce the lower-tail SIGN error (the tail folds inward)", _S,
     "        out[lo] = g[0] + lo_scale * np.log(np.clip(u[lo] / lo_t, 1e-12, 1.0))",
     "        out[lo] = g[0] - lo_scale * np.log(np.clip(u[lo] / lo_t, 1e-12, 1.0))",
     "grid_tails_are_exponential_never_flat",
     "out[lo] = g[0] + lo_scale"),
    ("A8.2: let the re-centring disagree with the sampler about the tails (E9.61)", _S,
     "    return trap + t0 * Q[:, 0] - lo_s * t0 + (1.0 - tk) * Q[:, -1] + hi_s * (1.0 - tk)",
     "    return trap",
     "quantile_function_mean_matches_what_the_sampler_actually_draws",
     "- lo_s * t0 + (1.0 - tk)"),

    # ── the oracle construction (A8.6 / A8.7) ───────────────────────────────────────────────────
    ("A8.6: score the ceiling against SELF-CONSISTENT truth instead of peeking", _H,
     "    _, t_peek, _ = draw_arm(arm, peek if peek is not None else oracle_context(c), orng, n_draws)\n"
     "    oracle_crps_t = float(shp.crps_ensemble(c.y_t_ev, t_peek).mean())",
     "    _, t_peek, _ = draw_arm(arm, c, orng, n_draws)\n"
     "    oracle_crps_t = float(shp.crps_ensemble(np.rint(t_peek[:, 0]), t_s).mean())",
     "per_form_oracle_peeks_by_swapping_the_context",
     "peek if peek is not None else oracle_context(c)"),
    ("A8.6: build the peek INSIDE draw_arm, defeating the leakage guard's structure", _H,
     "def oracle_context(c: FoldContext) -> FoldContext:",
     "def _unused_oracle_context(c: FoldContext) -> FoldContext:",
     "per_form_oracle_peeks_by_swapping_the_context", "def oracle_context(c: FoldContext)"),
    ("A8.7a: give the peek a 6x SMALLER lattice (an unmatched-n 'ceiling')", _H,
     "        disp=d2, sig_m_ev=sm, sig_t_ev=st, sig_m_ho=sm, sig_t_ho=st,\n    )",
     "        disp=d2, sig_m_ev=sm, sig_t_ev=st, sig_m_ho=sm, sig_t_ho=st,\n"
     "        train_home_pts=(c.y_t_ev + c.y_m_ev) / 2.0,\n"
     "        train_away_pts=(c.y_t_ev - c.y_m_ev) / 2.0,\n    )",
     "peek_swaps_what_is_fitted_and_holds_the_empirical_substrate", None),
    ("A8.7a: stop the peek refitting the dispersion (an inactive ceiling for sigma-consumers)", _H,
     "        disp=d2, sig_m_ev=sm, sig_t_ev=st, sig_m_ho=sm, sig_t_ho=st,",
     "        sig_m_ho=c.sig_m_ev, sig_t_ho=c.sig_t_ev,",
     "peek_swaps_what_is_fitted_and_holds_the_empirical_substrate", "disp=d2, sig_m_ev=sm"),
    ("A8.7b: put `permute` back into the MEASUREMENT-validity flag (NF-D20)", _H,
     "    mv = out[\"oracle_floor_ok_field_sanity\"]\n"
     "    mv = mv and out.get(\"zero_width\", {}).get(\"loses_the_metric\", True)",
     "    mv = out[\"oracle_floor_ok_field_sanity\"]\n"
     "    mv = mv and out.get(\"permute\", {}).get(\"loses_to_cond_het\", True)\n"
     "    mv = mv and out.get(\"zero_width\", {}).get(\"loses_the_metric\", True)",
     "permute_is_a_mechanism_finding_not_a_validity_gate", None),
    ("A8.6: let the self-consistency diagnostic set the oracle STATE", _H,
     '                      "own_form_peeking_oracle": v["oracle_crps_total"],',
     '                      "own_form_peeking_oracle": v["self_consistency_crps_total"],',
     "self_consistency_figure_is_a_diagnostic_and_gates_nothing",
     '"own_form_peeking_oracle": v["oracle_crps_total"]'),
    ("A8.8: let one beaten ceiling veto the whole run (a field-wide ceiling)", _H,
     '    mv = out["oracle_floor_ok_field_sanity"]',
     '    mv = out["oracle_floor_ok"]',
     "beaten_ceiling_is_per_arm_ineligibility_not_a_run_wide_veto",
     'mv = out["oracle_floor_ok_field_sanity"]'),
    ("A8.8: stop C8 binding, so a not-floor-verified arm can still ship", _H,
     '        rows[a]["clauses"]["all_ok"] = bool(\n'
     '            rows[a]["clauses"]["all_ok"] and rows[a]["clauses"]["C8_own_form_floor"]["ok"])',
     "        pass",
     "beaten_ceiling_is_per_arm_ineligibility_not_a_run_wide_veto",
     'rows[a]["clauses"]["C8_own_form_floor"]["ok"])'),
    ("oracle: read a TIE as a refusal instead of INACTIVE (NF-W6d)", _H,
     '        state = "BEATEN" if gap < -_TIE_BAND else ("INACTIVE_TIE" if abs(gap) <= _TIE_BAND else "OK")',
     '        state = "BEATEN" if gap < _TIE_BAND else "OK"',
     "an_oracle_tie_is_inactive_never_a_refusal", '"INACTIVE_TIE" if abs(gap) <= _TIE_BAND'),

    # ── the scoring instruments ─────────────────────────────────────────────────────────────────
    ("C5: make tail-CRPS integrate the BULK, so a truncated tail is invisible", _S,
     "    grid = np.concatenate([\n"
     "        np.linspace(lo - 1.5 * span, lo, n_grid // 2),\n"
     "        np.linspace(hi, hi + 1.5 * span, n_grid // 2),\n"
     "    ])",
     "    grid = np.linspace(lo, hi, n_grid)",
     "tail_crps_reads_the_tails_and_prefers", "np.linspace(lo - 1.5 * span, lo, n_grid // 2)"),
    ("C6: score the joint on the two MARGINALS instead of the 45° projections", _S,
     "    hp_s = (total_s + margin_s) / 2.0\n    ap_s = (total_s - margin_s) / 2.0",
     "    hp_s = total_s\n    ap_s = margin_s",
     "joint_pit_reads_the_pair_not_the_two_marginals",
     "hp_s = (total_s + margin_s) / 2.0"),
    ("CRPS: let the vendored copy drift from the shared implementation (E9.61)", _S,
     "    return term1 - 0.5 * term2",
     "    return term1 - 0.45 * term2",
     "vendored_crps_agrees_with_the_shared_implementation", "return term1 - 0.5 * term2"),
    ("student_t: let the per-game t diverge from the shipped scalar-σ sampler", _S,
     "    var_scale = np.sqrt(dof / (dof - 2.0)) if dof > 2.0 else 1.0\n"
     "    m_std = z1 * w / var_scale\n"
     "    t_std = (rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2) * w / var_scale\n"
     "    sm = np.asarray(sig_m, float)",
     "    var_scale = 1.0\n"
     "    m_std = z1 * w / var_scale\n"
     "    t_std = (rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2) * w / var_scale\n"
     "    sm = np.asarray(sig_m, float)",
     "per_game_bivariate_t_agrees_with_the_shipped_scalar_sigma_form", None),

    # ── estimation + leakage + hygiene ──────────────────────────────────────────────────────────
    ("leakage: fit the conditional variance on the EVAL drivers", _H,
     "        th_m = shp.fit_log_variance(c.resid_m, Z_fit)",
     "        th_m = shp.fit_log_variance(c.y_m_ev - c.mu_m_ev, c.Z_ev)",
     "every_shape_parameter_is_fitted_on_the_inner_holdout_never_on_eval",
     "shp.fit_log_variance(c.resid_m, Z_fit)"),
    ("leakage: expose an EVAL residual on the fold context for a fit to reach", _H,
     "    resid_m: np.ndarray\n    resid_t: np.ndarray",
     "    resid_m: np.ndarray\n    resid_t: np.ndarray\n    resid_m_ev: np.ndarray\n"
     "    resid_t_ev: np.ndarray",
     "fold_context_carries_no_eval_residual", None),
    ("CV: sort the folds by RAW week (the P1.1 postseason-reset leak)", _H,
     'df.sort_values([_YEAR, "season_order_week", _DATE])',
     'df.sort_values([_YEAR, "week", _DATE])',
     "cv_axis_is_the_season_order_never_raw_week",
     'sort_values([_YEAR, "season_order_week", _DATE])'),
    ("weather: register a fabricated weather driver the lakehouse does not have", _S,
     '    "environment_proxy": ("game_venue_is_dome", "game_venue_elevation_m"),',
     '    "environment_proxy": ("game_venue_is_dome", "game_venue_elevation_m"),\n'
     '    "weather": ("game_wind_mph", "game_temp_f"),',
     "weather_drivers_are_recorded_absent", None),
    ("collapse: stop declaring a family's collapse parameter (§5.3 tie rule)", _S,
     '    Shape("skew_t", "skew-t", True, "alpha = 0 and dof → ∞", False),',
     '    Shape("skew_t", "skew-t", True, "", False),',
     "every_family_declares_its_collapse_parameter", '"alpha = 0 and dof → ∞"'),
    ("paths: write a DECIDED story's artifact (the S1-serve defect-3 class)", _H,
     '_DECISION_MD = _RESULTS_DIR / "ncaaf_p2_5_distribution_shape.md"',
     '_DECISION_MD = _RESULTS_DIR / "ncaaf_p1_4_game_model.md"',
     "story_never_writes_a_decided_storys_artifacts",
     'ncaaf_p2_5_distribution_shape.md"'),
    ("foil: point gate R at the SUPERSEDED P1.4 record instead of what serves", _H,
     '_SERVED_CALIB = _RESULTS_DIR / "ncaaf_s1_serve_calibration.json"',
     '_SERVED_CALIB = _RESULTS_DIR / "ncaaf_p1_4_calibration.json"',
     "foil_is_the_served_contract_not_the_cards_superseded_one",
     '_SERVED_CALIB = _RESULTS_DIR / "ncaaf_s1_serve_calibration.json"'),
    ("prereg: delete the weather-absence record from the pre-registration", _P,
     "**ABSENT. Dropped from the driver set.**", "TBD",
     "preregistration_records_the_weather_absence",
     "**ABSENT. Dropped from the driver set.**"),
]


def _run(selector: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", TEST, "-k", selector, "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True).returncode


def main() -> int:
    baseline = _run("")
    if baseline != 0:
        print(f"✗ HARNESS BROKEN — the suite is not green before any mutation (exit {baseline})")
        return 2

    failures: list[str] = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if original.count(old) != 1:
            failures.append(f"{name}: anchor is NOT UNIQUE ({original.count(old)} matches) — a "
                            "replace would land on the wrong symbol and report a FALSE vacuity")
            continue
        try:
            mutated = original.replace(old, new, 1)
            path.write_text(mutated)
            if path.read_text() == original:
                failures.append(f"{name}: the mutation did not LAND on disk")
                continue
            if gone is not None and gone in path.read_text():
                failures.append(f"{name}: the mutation landed but {gone!r} is still present — the "
                                "asserted predicate did not move, so a GREEN proves nothing")
                continue
            code = _run(selector)
            if code == 1:
                print(f"  RED ✅  {name}")
            elif code == 0:
                failures.append(f"{name}: the guard stayed GREEN on deliberately-broken source")
            else:
                failures.append(f"{name}: BROKEN HARNESS (exit {code}) — not a caught break")
        finally:
            path.write_text(original)

    if failures:
        print("\n✗ RED PROOF FAILED:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"\n✓ all {len(BREAKS)} deliberate breaks went RED; the suite is green again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

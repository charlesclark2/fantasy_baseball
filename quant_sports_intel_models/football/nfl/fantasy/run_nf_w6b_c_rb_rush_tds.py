"""run_nf_w6b_c_rb_rush_tds.py — NF-W6b-C: RB rushing_tds fresh-family successor — the §0.5
bake-off PM Decision C deferred and this story runs.

Everything decidable in advance lives as a CONSTANT in `stat_distributions_c.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w6b_c_preregistration.md` BEFORE the full run. ⭐ FRESH REGISTRATION
(MH2.2): a new field, a new seed — ⛔ not a re-score and not a trim of NF-W6b's field.

PIPELINE
  MATRIX: the NF-W6 certified build, verbatim (`run_nf_w6_efficiency_marginals.build_matrix_w6`
  — the NF-W1 matrix + conservation-guarded TD labels; the NF-W0a PIT gate on EVERY load).

  ONE CELL (RB|rushing_tds): 3 atom-aware real arms (lgbm_hurdle_tail / knn_quantile /
  count_negbin — ⛔ no linear-residual arm), 1 foil (inc_climatology, the W6b binding
  incumbent), and 12 diagnostic anchors (3 degenerates, the permuted kNN, and FOUR per-form
  oracle/matched-n pairs — NF-D16 (g‴)). Metric: `crps_q199`. Gates: paired lift, calibrated
  fold clause, PBO<0.2 over the eligible field, DSR≥0.95, single-cell BH (p ≤ q), one-sided
  coverage floor, degenerates, permutation, the foil-tie guard, the winner's own-form floor.
  Null states: CONSTRAINT_REFUSED by hand; statistical nulls via `cv_power.classify_null`
  (`declared_field_size=3`; read `field_remedy_admissible`, never the prose — MH2.7).

🟥 RUNTIME GATE — N/A, stated: no serving path (no --publish / deploy.sh / Dagster op /
S3 / registry / dbt write); local artifacts read by governance only. Deploy-held.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts; full run >2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_c_rb_rush_tds --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_c_rb_rush_tds
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_c_rb_rush_tds --rewrite-report
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_c as SDC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6_efficiency_marginals as W6R,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_w6b_c")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = W6R.SEASONS
FEATURES = list(WP.FEATURES)     # the champion feature set — ⛔ no exotic features (prereg §1)
#: ⛔ the closed TD-NO cells, quoted in the prereg block (imported so the record can't drift)
SD_CLOSED = SDC.SD.CLOSED_CELLS

#: The W6b record's figures for this cell, quoted for the comparison narrative (REPORT-ONLY).
W6B_REFERENCE = {
    "winner": "knn_quantile", "delta": 0.0194, "lift_pct": 12.966, "winner_sr": 6.474,
    "field_sr0_approx": 7.32, "dsr": 0.2131,
    "inflating_arm": "enet_residual", "inflating_arm_sr": -9.199,
    "note": ("NF-W6b (seed 20260815): the SAME winner could not clear DSR because the "
             "linear-residual arm's huge consistent loss inflated the cross-trial dispersion "
             "(sr0 ≈ 7.32 > sr 6.47). This fresh field removes that class up front."),
}


def _y(df: pd.DataFrame) -> np.ndarray:
    return pd.to_numeric(df[SDC.STAT], errors="coerce").fillna(0.0).to_numpy(dtype=float)


# ── One fold: every construction, scored on the RB cell ─────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    y_tr, y_te = _y(train), _y(test)

    clim = EM.climatology_bank(y_tr, train["position"].to_numpy())
    inc_cl = EM.apply_bank199(np.zeros(len(test)), test_pos, clim)

    hurdle, _ = SDC.arm_lgbm_hurdle_tail(train, test, FEATURES, SDC.STAT)
    knn = SDC.arm_knn_quantile(train, test, FEATURES, SDC.STAT)
    negbin, nb_note = SDC.arm_count_negbin(train, test, FEATURES, SDC.STAT)

    # the permuted anchor runs the declared kNN form's IDENTICAL code path on permuted labels
    train_perm = train.copy()
    train_perm[SDC.STAT] = SDC.permute_stat_within_pos_week(train)
    permuted = SDC.arm_knn_quantile(train_perm, test, FEATURES, SDC.STAT)

    banks: dict[str, np.ndarray] = {
        "lgbm_hurdle_tail": hurdle,
        "knn_quantile": knn,
        "count_negbin": negbin,
        "inc_climatology": inc_cl,
        "nihilist_zero": EM.anchor_nihilist(len(test)),
        # sharpness degenerates derive from the FOIL bank (the field's only foil — declared;
        # zero_width numerically coincides with the nihilist on this 86%-atom cell, recorded)
        "zero_width": EM.anchor_zero_width(inc_cl),
        "max_width": EM.anchor_max_width(inc_cl),
        "permuted_knn": permuted,
        "oracle_marginal": EM.oracle_climatology(test, SDC.STAT),
        "matched_marginal": EM.matched_climatology(train, test, SDC.STAT),
        "oracle_knn": SDC.oracle_knn(test, FEATURES, SDC.STAT, fold.label),
        "matched_knn": SDC.matched_knn(train, test, FEATURES, SDC.STAT),
        "oracle_hurdle": SDC.oracle_hurdle(test, FEATURES, SDC.STAT, fold.label),
        "matched_hurdle": SDC.matched_hurdle(train, test, FEATURES, SDC.STAT),
        "oracle_negbin": SDC.oracle_negbin(test, FEATURES, SDC.STAT, fold.label),
        "matched_negbin": SDC.matched_negbin(train, test, FEATURES, SDC.STAT),
    }
    assert set(banks) == set(SDC.all_labels()), "fold banks drifted from the declared field"

    sel = test_pos == SDC.POSITION
    scores = {lab: SDC.score_bank(b[sel], y_te[sel]) for lab, b in banks.items()}
    log.info("[W6b-C] fold %s complete in %.1fs (%d RB rows)", fold.label,
             time.time() - t0, int(sel.sum()))
    return {"label": fold.label, "n_test": int(sel.sum()),
            "cells": {SDC.CELL: {"scores": scores, "nb_note": nb_note}}}


# ── Selection (deflation lives here; the pure module owns the gate logic) ───────────────────────
def select_cell(fold_results: list[dict], n_folds: int) -> dict:
    crps = SDC.cell_crps_matrix(fold_results, SDC.CELL)
    mean_crps = crps.mean(axis=0)
    winner = str(mean_crps[list(SDC.REAL_ARMS)].idxmin())
    binding_foil = str(mean_crps[list(SDC.FOILS)].idxmin())
    deltas = (crps[binding_foil] - crps[winner]).to_numpy(dtype=float)   # >0 = winner better
    mean_d, lo, hi = SDC.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    pval = M14.onesided_paired_pvalue(deltas)

    eligible = SDC.eligible_labels()
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in SDC.REAL_ARMS:
        d = (crps[binding_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))

    perm_lift = (crps[binding_foil] - crps["permuted_knn"]).to_numpy(dtype=float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)

    # per-form oracle/matched pairs (NF-D16 (g‴)): the winner's OWN pair gates; all reported
    winner_form = winner if winner in SDC.ORACLE_PAIRS else "marginal"
    pair_reads = {}
    for form, (orc, mat) in SDC.ORACLE_PAIRS.items():
        pair_reads[form] = {
            "oracle_crps": round(float(mean_crps[orc]), 5),
            "matched_crps": round(float(mean_crps[mat]), 5),
            "oracle_beats_matched": bool(mean_crps[mat] > mean_crps[orc]),
        }
    own_orc, _own_mat = SDC.ORACLE_PAIRS[winner_form]
    anchors = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps["permuted_knn"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "winner_own_form_oracle_beats_matched": bool(
            pair_reads[winner_form]["oracle_beats_matched"]),
        # REPORT-ONLY: beating one's own block peek is legitimate capacity at unmatched n
        # (NF1.9 (f)) — the matched control above is what makes the floor admissible.
        "winner_beats_own_form_oracle": bool(mean_crps[own_orc] > mean_crps[winner]),
        "oracle_pairs": pair_reads,
    }

    def _pooled(label: str, key: str) -> tuple[float, int]:
        parts = [fr["cells"][SDC.CELL]["scores"][label] for fr in fold_results]
        n = sum(s["n"] for s in parts)
        v = (sum(s[key] * s["n"] for s in parts) / n) if n else float("nan")
        return float(v), int(n)

    cov, n_tot = _pooled(winner, "coverage_80")
    foil_cov, _ = _pooled(binding_foil, "coverage_80")
    real_p0, _ = _pooled(winner, "real_p0")
    pred_p0_w, _ = _pooled(winner, "pred_p0")
    pred_p0_f, _ = _pooled(binding_foil, "pred_p0")
    se = (float(np.sqrt(SDC.COVERAGE_FLOOR * (1 - SDC.COVERAGE_FLOOR) / n_tot))
          if n_tot else float("nan"))
    coverage = {
        "winner_coverage_80": round(cov, 4), "binding_foil_coverage_80": round(foil_cov, 4),
        "structural_expectation": SDC.structural_coverage_note(real_p0),
        "n_rows": n_tot, "binomial_se": round(se, 4),
        # the FLOOR (one-sided — prereg §2; two-sidedness lives in the sharpness degenerates)
        "blocking_shortfall": bool(
            n_tot and (SDC.COVERAGE_FLOOR - cov) > SDC.COVERAGE_BLOCK_SE * se),
    }

    fold_labels = [fr["label"] for fr in fold_results]
    cap = [i for i, lbl in enumerate(fold_labels) if lbl in SDC.CAPTURE_ERA_FOLDS]
    leg = [i for i, lbl in enumerate(fold_labels) if lbl not in SDC.CAPTURE_ERA_FOLDS]

    sd_d = float(np.nanstd(deltas, ddof=1))
    observed_sr = float(np.nanmean(deltas)) / sd_d if sd_d > 1e-12 else None
    return {
        "cell": SDC.CELL, "winner": winner, "winner_form": winner_form,
        "binding_foil": binding_foil,
        "selection_metric": SDC.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()
                      if k != "oracle_pairs"},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "lift_pct_of_foil": (None if mean_d is None else
                             round(100.0 * mean_d / float(mean_crps[binding_foil]), 3)),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "p_one_sided": pval,
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "trial_srs": [round(t, 3) for t in trial_srs],
        "sr0_this_field": SDC.benchmark_sr0(trial_srs),
        "observed_sr": None if observed_sr is None else round(observed_sr, 3),
        "anchors": anchors, "coverage": coverage,
        "atom_calibration": {
            "real_p0": round(real_p0, 4),
            "winner_pred_p0": round(pred_p0_w, 4),
            "binding_foil_pred_p0": round(pred_p0_f, 4),
            "note": "REPORT-ONLY — the licensed mechanism made visible, never a criterion.",
        },
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 5) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 5) if leg else None),
            "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
        },
        "w6b_reference": W6B_REFERENCE,
    }


# ── Verdict layer (derived, shared with --rewrite-report — NF-W2e one level up) ─────────────────
def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored fold scores — no refit (NF-W2e/W3 rule)."""
    n_folds = out["n_folds"]
    sel = select_cell(out["fold_results"], n_folds)
    fdr = SDC.fdr_single_cell(sel["p_one_sided"])
    gate = SDC.compose_gate_w6bc(sel, fdr["pass"])
    null_state = SDC.classify_w6bc_null(sel, gate["checks"], n_folds)
    sensitivity = (SDC.gate_sensitivity(gate["checks"], waived=("dsr_ok",))
                   if not gate["ship"] else None)
    verdict_word = "SHIP" if gate["ship"] else (null_state or {}).get("state", "NULL")
    return {
        "selection": sel, "fdr": fdr, "gate": gate, "null_state": null_state,
        "gate_sensitivity_dsr_waived": sensitivity,
        "ppr_note": SDC.ppr_points_note(sel["mean_delta"]),
        "verdict": {SDC.CELL: verdict_word},
        "headline": f"RB-RUSHTD-FRESH {verdict_word}",
    }


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    s = out["selection"]
    g = out["gate"]
    p("# NF-W6b-C — RB rushing_tds fresh-family successor (§0.5 bake-off; PM Decision C)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**rows:** {out['n_rows']} player-weeks · **cell:** {SDC.CELL} (one)")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** "
      "(research-only, no changelog). ⭐ FRESH registration (MH2.2/E2.1-r): a NEW field, seed "
      f"{SDC._SEED} — ⛔ not a re-score and not a trim of NF-W6b's field; the W6b record "
      "stands. The declared family is coherent and atom-aware ONLY (⛔ no linear-residual "
      "arm — the W6b field-inflating class is excluded up front on mechanistic grounds). "
      "Coverage is a one-sided FLOOR (NF1.9 (e)); the two-sidedness lives in the sharpness "
      "degenerates. Verdict words are three-way and derived, failing closed to TIES (NF-W2e).")
    p("")
    p("> 🟥 **Runtime gate: N/A, stated** — no serving path is touched (no `--publish`, no "
      "`deploy.sh`, no Dagster op, no S3/registry/dbt write); local artifacts read by "
      "governance only. **Serving:** RB|rushing_tds stays guard-pinned OUT of NF-W6c's "
      "dispatch (`WITHHELD_NULL_CELLS`) regardless of this verdict; a SHIP licenses a future "
      "wiring story under NF-G0, it does not execute one.")
    p("")
    pit = out["pit_audit"]
    p(f"**PIT gate (NF-W0a `assert_point_in_time`):** {pit['weeks_checked']} weeks / "
      f"{pit['records_checked']} records checked; {pit['rows_dropped']} rows dropped.")
    p("")
    p(f"## Verdict: **{out['headline']}**")
    p("")
    lo, hi = (s["ci95"] or [None, None])[:2]
    p(f"- {SDC.verdict_sentence(s['winner'], s['binding_foil'], s['mean_delta'], lo, hi)}")
    p(f"- lift {s['lift_pct_of_foil']}% of foil CRPS · fold wins {s['fold_wins']}/"
      f"{out['n_folds']} (required {s['fold_clause']['required']}) · p {s['p_one_sided']} · "
      f"PBO {s['pbo']} · **DSR {s['dsr']}** · cov80 {s['coverage']['winner_coverage_80']} "
      f"(floor {SDC.COVERAGE_FLOOR}, one-sided)")
    p("")
    p("## The DSR mechanism, W6b → W6b-C (the reason this field exists)")
    p("")
    w6b = s["w6b_reference"]
    p(f"- NF-W6b (the retired field): winner `{w6b['winner']}` Δ {w6b['delta']} "
      f"({w6b['lift_pct']}%), per-fold Sharpe {w6b['winner_sr']}, **DSR {w6b['dsr']}** — "
      f"refused because `{w6b['inflating_arm']}` (trial Sharpe {w6b['inflating_arm_sr']}) "
      f"inflated the field's dispersion to sr0 ≈ {w6b['field_sr0_approx']}.")
    p(f"- THIS field (fresh, coherent, atom-aware): trial Sharpes {s['trial_srs']} → "
      f"**sr0 {s['sr0_this_field']}** vs the winner's observed Sharpe {s['observed_sr']} → "
      f"**DSR {s['dsr']}**. ⛔ This is NOT a trim of the W6b field (MH2.2) — it is a fresh "
      f"registration whose family excludes the incoherent class on mechanistic grounds, "
      f"declared before scoring.")
    p("")
    p("## Leaderboard (mean CRPS over folds; anchors indented — never trials)")
    p("")
    rows = [{"label": k, "mean_crps": v} for k, v in
            sorted(s["mean_crps"].items(), key=lambda kv: kv[1])]
    p(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".5f"))
    p("")
    p(f"- gates: {json.dumps(g['checks'])}")
    anchors_flat = {k: v for k, v in s["anchors"].items() if k != "oracle_pairs"}
    p(f"- anchors: {json.dumps(anchors_flat)}")
    p(f"- per-form oracle/matched pairs (NF-D16 (g‴) — winner's own form `{s['winner_form']}` "
      f"gates; others reported): {json.dumps(s['anchors']['oracle_pairs'])}")
    p(f"- coverage: {json.dumps(s['coverage'])} (floor one-sided by prereg §2; structural "
      f"expectation shown — NF1.9 (e))")
    p(f"- atom calibration (report-only): {json.dumps(s['atom_calibration'])}")
    p(f"- era (report-only): capture Δ {s['era_note']['capture_mean_delta']} vs legacy Δ "
      f"{s['era_note']['legacy_mean_delta']}")
    p(f"- PBO companions (NF1.8): os_gap {s['os_gap_pct']}% · contender spread "
      f"{s['contender_spread_pct']}% · flips {json.dumps(s['flips'])}")
    p(f"- fdr (single-cell family, m=1 ⇒ cutoff = q): {json.dumps(out['fdr'])}")
    p(f"- points-units note: {json.dumps(out['ppr_note'])}")
    p("")
    if out.get("null_state"):
        p("## Null state (recorded)")
        p("")
        p(f"```json\n{json.dumps(out['null_state'], indent=2, default=str)}\n```")
        p("")
        if out.get("gate_sensitivity_dsr_waived"):
            p(f"- gate sensitivity (DSR waived — NF-D15 (g″)): "
              f"{json.dumps(out['gate_sensitivity_dsr_waived'])}")
            p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- cell: {pre['cells']} (⛔ closed TD-NO cells stay closed: {pre['closed_cells']}); "
      f"arms: {pre['real_arms']} (declared_field_size={pre['declared_field_size']}); "
      f"banned classes: {list(pre['banned_arm_classes'])}; foil: {pre['foils']}; "
      f"anchors: {pre['anchors']}.")
    p(f"- gates: paired lift vs foil ∧ `fold_consistency_clause({out['n_folds']})` ∧ "
      f"PBO<{pre['pbo_max']} over the eligible field ∧ DSR≥{pre['dsr_min']} ∧ single-cell BH "
      f"(p ≤ {pre['fdr_q']}) ∧ coverage floor (one-sided) ∧ degenerates lose ∧ permutation "
      f"behaves ∧ not_a_foil_tie (eps {pre['tie_eps_crps']}) ∧ winner_own_form_floor. "
      f"Fails closed.")
    p("- null classification: CONSTRAINT_REFUSED by hand (the cv_power gap); statistical "
      "nulls via `cv_power.classify_null(declared_field_size=3, "
      "degenerates_excluded_from_v=True)`; the record reads `field_remedy_admissible`, "
      "never the prose (MH2.7; guide §0.5.4 rules 5/5b).")
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix cache key "
      f"{out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6b-C RB rushing_tds fresh-family bake-off")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds; degenerate movability HARD-asserted; artifacts _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w6b_c_rb_rush_tds{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored fold scores without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved, default=str))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w6b_c_rb_rush_tds{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2, default=str))
        return 0

    t_start = time.time()
    feat, pit_audit, td_audit = W6R.build_matrix_w6(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-W6b-C: %d folds over %d player-weeks; cell %s; labels = %d",
             n_folds, len(feat), SDC.CELL, len(SDC.all_labels()))

    frs = [run_fold(f, feat) for f in folds]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": SDC.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": SDC.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(len(feat)),
        "matrix_key": W6R.w6_matrix_key(SEASONS),
        "pit_audit": pit_audit, "td_attach_audit": td_audit,
        "preregistration": {
            "cells": list(SDC.cells()), "closed_cells": list(SD_CLOSED),
            "real_arms": list(SDC.REAL_ARMS), "foils": list(SDC.FOILS),
            "anchors": list(SDC.ANCHORS),
            "banned_arm_classes": dict(SDC.BANNED_ARM_CLASSES),
            "declared_field_size": SDC.DECLARED_FIELD_SIZE,
            "tie_eps_crps": SDC.TIE_EPS_CRPS,
            "primary_metric": SDC.PRIMARY_METRIC,
            "pbo_max": SDC.PBO_MAX, "dsr_min": SDC.DSR_MIN, "fdr_q": SDC.FDR_Q,
            "coverage_floor": SDC.COVERAGE_FLOOR, "coverage_block_se": SDC.COVERAGE_BLOCK_SE,
            "ppr_weight_rush_td": SDC.PPR_WEIGHT_RUSH_TD, "knn_k": SDC.KNN_K,
            "fit_levels": list(SDC.FIT_LEVELS),
            "test_blocks": [list(t) for t in SDC.TEST_BLOCKS],
            "purge_weeks": SDC.PURGE_WEEKS,
            "capture_era_folds": list(SDC.CAPTURE_ERA_FOLDS),
            "features": FEATURES, "seed": SDC._SEED,
        },
        "fold_results": frs,
    }
    out.update(derive_verdict_layer(out))

    if args.smoke:
        # ⭐ MH2.1 (d) movability control: the instrument must SEE the known defects lose —
        # the all-zero nihilist (CRPS soundness on an 86%-atom cell — NF-D11) and BOTH
        # sharpness degenerates. HARD assert — a blind instrument refuses the smoke.
        bad = [k for k, v in out["selection"]["anchors"].items()
               if k in ("nihilist_loses", "zero_width_loses", "max_width_loses") and not v]
        if bad:
            raise SystemExit(f"POSITIVE CONTROL FAILED — degenerate anchors do not lose: {bad} "
                             f"(refusing the smoke)")
        log.info("positive control OK: all degenerates lose")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6b_c_rb_rush_tds{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "null_state": out.get("null_state"),
                      "runtime_seconds": out["runtime_seconds"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

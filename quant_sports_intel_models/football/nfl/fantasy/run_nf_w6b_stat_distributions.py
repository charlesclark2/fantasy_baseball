"""run_nf_w6b_stat_distributions.py — NF-W6b: the per-stat distributional successor — the
§0.5 bake-off NF-W6's CEILING-GATE[BUILD] licensed.

Everything decidable in advance lives as a CONSTANT in `stat_distributions.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w6b_preregistration.md` BEFORE the full run. ⭐ FRESH REGISTRATION (MH2.2):
nothing from NF-W6's oracle field is promoted into this field.

PIPELINE
  MATRIX: the NF-W6 certified build, verbatim (`run_nf_w6_efficiency_marginals.build_matrix_w6`
  — the NF-W1 matrix + conservation-guarded TD labels; the NF-W0a PIT gate runs on EVERY load,
  cache hit or not).

  PER CELL (8 = QB×3, RB×3, WR×1, TE×1 — ⛔ the 4 TD-NO cells stay closed): 4 real arms
  (lgbm_quantile_tail / lgbm_hurdle_tail / enet_residual / knn_quantile), 2 foils (the
  champion-faithful `inc_head_bank` + `inc_climatology`; the BINDING one sets the bar), and 6
  diagnostic anchors (nihilist / zero_width / max_width / permuted_quantile / oracle_marginal /
  matched_marginal — scored, never trials). Metric: `crps_q199`. Gates: paired lift vs the
  binding foil, calibrated fold clause, PBO<0.2 over the eligible field, DSR≥0.95, two-family
  BH-FDR (own AND pooled), coverage floor, degenerate + permutation anchors.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts; >2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_stat_distributions --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_stat_distributions
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_stat_distributions --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6_efficiency_marginals as W6R,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_w6b")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = W6R.SEASONS
FEATURES = list(WP.FEATURES)     # the champion feature set — ⛔ no exotic features (prereg §0)


# ── One fold: every construction per stat, scored per cell ──────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, stats: tuple[str, ...]) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    cells_out: dict[str, dict] = {}

    for stat in stats:
        pos_for_stat = [p for p in SD.POSITIONS if stat in SD.POSITION_STATS[p]]
        if not pos_for_stat:
            continue
        t_stat = time.time()
        y_tr = pd.to_numeric(train[stat], errors="coerce").fillna(0.0).to_numpy(float)
        y_te = pd.to_numeric(test[stat], errors="coerce").fillna(0.0).to_numpy(float)

        inc_hb, cal_note = EM.inc_head_bank(train, test, FEATURES, stat)
        clim_tr = EM.climatology_bank(y_tr, train["position"].to_numpy())

        q_tail, _ = SD.arm_lgbm_quantile_tail(train, test, FEATURES, stat)
        hurdle, _ = SD.arm_lgbm_hurdle_tail(train, test, FEATURES, stat)
        enet, _ = SD.arm_enet_residual(train, test, FEATURES, stat)

        # the permuted anchor runs the IDENTICAL winner-form code path on permuted labels
        train_perm = train.copy()
        train_perm[stat] = SD.permute_stat_within_pos_week(train, stat)
        permuted, _ = SD.arm_lgbm_quantile_tail(train_perm, test, FEATURES, stat)

        banks: dict[str, np.ndarray] = {
            "lgbm_quantile_tail": q_tail,
            "lgbm_hurdle_tail": hurdle,
            "enet_residual": enet,
            "knn_quantile": SD.arm_knn_quantile(train, test, FEATURES, stat),
            "inc_head_bank": inc_hb,
            "inc_climatology": EM.apply_bank199(np.zeros(len(test)), test_pos, clim_tr),
            "nihilist_zero": EM.anchor_nihilist(len(test)),
            "zero_width": EM.anchor_zero_width(inc_hb),
            "max_width": EM.anchor_max_width(inc_hb),
            "permuted_quantile": permuted,
            "oracle_marginal": EM.oracle_climatology(test, stat),
            "matched_marginal": EM.matched_climatology(train, test, stat),
        }
        assert set(banks) == set(SD.all_labels()), "fold banks drifted from the declared field"

        for p in pos_for_stat:
            sel = test_pos == p
            scores = {lab: SD.score_bank(b[sel], y_te[sel]) for lab, b in banks.items()}
            cells_out[SD.cell_key(p, stat)] = {"scores": scores, "cal_split": cal_note}
        log.info("[W6b] fold %s stat %s in %.1fs", fold.label, stat, time.time() - t_stat)

    log.info("[W6b] fold %s complete in %.1fs (%d cells)", fold.label, time.time() - t0,
             len(cells_out))
    return {"label": fold.label, "n_test": int(len(test)), "cells": cells_out}


# ── Selection per cell (deflation lives here; the pure module owns the gate logic) ──────────────
def select_cell(fold_results: list[dict], cell: str, n_folds: int) -> dict:
    crps = SD.cell_crps_matrix(fold_results, cell)
    mean_crps = crps.mean(axis=0)
    winner = str(mean_crps[list(SD.REAL_ARMS)].idxmin())
    binding_foil = str(mean_crps[list(SD.FOILS)].idxmin())
    deltas = (crps[binding_foil] - crps[winner]).to_numpy(dtype=float)   # >0 = winner better
    mean_d, lo, hi = SD.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    pval = M14.onesided_paired_pvalue(deltas)

    eligible = SD.eligible_labels()
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in SD.REAL_ARMS:
        d = (crps[binding_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))

    perm_lift = (crps[binding_foil] - crps["permuted_quantile"]).to_numpy(dtype=float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps["permuted_quantile"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # REPORT-ONLY (NF-W1 stance): a conditional winner may legitimately beat the marginal
        # peeker cross-form; the matched pair makes the reading attributable (NF1.9 (f)).
        "winner_beats_oracle_marginal": bool(mean_crps["oracle_marginal"] > mean_crps[winner]),
        "oracle_marginal_beats_matched": bool(mean_crps["matched_marginal"]
                                              > mean_crps["oracle_marginal"]),
    }

    def _pooled(label: str, key: str) -> tuple[float, int]:
        parts = [fr["cells"][cell]["scores"][label] for fr in fold_results]
        n = sum(s["n"] for s in parts)
        v = (sum(s[key] * s["n"] for s in parts) / n) if n else float("nan")
        return float(v), int(n)

    cov, n_tot = _pooled(winner, "coverage_80")
    foil_cov, _ = _pooled(binding_foil, "coverage_80")
    real_p0, _ = _pooled(winner, "real_p0")
    pred_p0_w, _ = _pooled(winner, "pred_p0")
    pred_p0_f, _ = _pooled(binding_foil, "pred_p0")
    se = float(np.sqrt(SD.COVERAGE_FLOOR * (1 - SD.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")
    coverage = {
        "winner_coverage_80": round(cov, 4), "binding_foil_coverage_80": round(foil_cov, 4),
        "structural_expectation": SD.structural_coverage_note(real_p0),
        "n_rows": n_tot, "binomial_se": round(se, 4),
        # the FLOOR (one-sided — prereg §2; the two-sidedness lives in the sharpness degenerates)
        "blocking_shortfall": bool(
            n_tot and (SD.COVERAGE_FLOOR - cov) > SD.COVERAGE_BLOCK_SE * se),
    }

    fold_labels = [fr["label"] for fr in fold_results]
    cap = [i for i, lbl in enumerate(fold_labels) if lbl in SD.CAPTURE_ERA_FOLDS]
    leg = [i for i, lbl in enumerate(fold_labels) if lbl not in SD.CAPTURE_ERA_FOLDS]

    sd_d = float(np.nanstd(deltas, ddof=1))
    observed_sr = float(np.nanmean(deltas)) / sd_d if sd_d > 1e-12 else None
    return {
        "cell": cell, "winner": winner, "binding_foil": binding_foil,
        "selection_metric": SD.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
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
    }


# ── Verdict layer (derived, shared with --rewrite-report — NF-W2e one level up) ─────────────────
def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored fold scores — no refit (NF-W2e/W3 rule)."""
    n_folds = out["n_folds"]
    frs = out["fold_results"]
    present = sorted(frs[0]["cells"].keys())
    sels = {c: select_cell(frs, c, n_folds) for c in present}

    fams = SD.fdr_families()
    yards_p = {k: sels[k.removeprefix("w6b_arm_")]["p_one_sided"]
               for k in fams["yards"] if k.removeprefix("w6b_arm_") in sels}
    tds_p = {k: sels[k.removeprefix("w6b_arm_")]["p_one_sided"]
             for k in fams["tds"] if k.removeprefix("w6b_arm_") in sels}
    fdr = SD.fdr_two_families(yards_p, tds_p)
    for c in sels:
        sels[c]["fdr_binding"] = bool(fdr["binding"].get(f"w6b_arm_{c}", False))

    gates = {c: SD.compose_gate_w6b(sels[c], sels[c]["fdr_binding"]) for c in sels}
    null_states = {c: SD.classify_cell_null(sels[c], gates[c]["checks"], n_folds)
                   for c in sels}
    null_states = {c: v for c, v in null_states.items() if v is not None}
    sensitivity = {c: SD.gate_sensitivity(gates[c]["checks"], waived=("dsr_ok",))
                   for c in sels if not gates[c]["ship"]}
    story = SD.decide_story(gates)
    verdict = {"story": story["headline"],
               "cells": {c: ("SHIP" if gates[c]["ship"]
                             else null_states.get(c, {}).get("state", "NULL"))
                         for c in sorted(gates)}}
    return {"selections": sels, "fdr": fdr, "gates": gates, "null_states": null_states,
            "gate_sensitivity_dsr_waived": sensitivity,
            "story_decision": story, "ppr_report": SD.ppr_report(sels),
            "verdict": verdict, "headline": story["headline"]}


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W6b — the per-stat distributional successor (§0.5 bake-off; the "
      "CEILING-GATE[BUILD] license)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**rows:** {out['n_rows']} player-weeks · **cells:** {len(out['selections'])}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** "
      "(research-only, no changelog). FRESH registration (MH2.2) licensed by NF-W6's "
      "CEILING-GATE[BUILD]. DoD = per-stat marginal CRPS (`crps_q199`); the assembled-PPR "
      "effect is REPORT-ONLY (PM ruling). Coverage is a FLOOR, one-sided by pre-registration "
      "(NF1.9 (e) — the zero atom makes an upper coverage gate structurally inverted); the "
      "two-sidedness lives in the sharpness degenerates. Every direction word is three-way and "
      "derived at report time, failing closed to `TIES` (NF-W2e).")
    p("")
    pit = out["pit_audit"]
    p(f"**PIT gate (NF-W0a `assert_point_in_time`):** {pit['weeks_checked']} weeks / "
      f"{pit['records_checked']} records checked; {pit['rows_dropped']} rows dropped.")
    p("")
    p(f"## Verdict: **{out['headline']}**")
    p("")
    p(out["story_decision"]["reason"])
    p("")
    p("## Per-cell contests (winner vs the BINDING champion-faithful incumbent)")
    p("")
    p("| cell | winner | foil | foil CRPS | Δ | Δ% | CI95 | wins | p | PBO | DSR | BH | "
      "cov80 (floor 0.80) | verdict |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        g = out["gates"][c]
        lo, hi = (s["ci95"] or [None, None])[:2]
        ci = f"[{lo}, {hi}]" if lo is not None else "n/a"
        v = "SHIP" if g["ship"] else out["null_states"].get(c, {}).get("state", "NULL")
        p(f"| {c} | {s['winner']} | {s['binding_foil']} | "
          f"{s['mean_crps'][s['binding_foil']]} | {s['mean_delta']} | {s['lift_pct_of_foil']} | "
          f"{ci} | {s['fold_wins']}/{out['n_folds']} | {s['p_one_sided']} | {s['pbo']} | "
          f"{s['dsr']} | {s['fdr_binding']} | {s['coverage']['winner_coverage_80']} | **{v}** |")
    p("")
    p("## Per-cell detail")
    p("")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        g = out["gates"][c]
        p(f"### {c}")
        p("")
        rows = [{"label": k, "mean_crps": v} for k, v in
                sorted(s["mean_crps"].items(), key=lambda kv: kv[1])]
        p(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".5f"))
        p("")
        p(f"- verdict: {SD.verdict_sentence(s['winner'], s['binding_foil'], s['mean_delta'], *(s['ci95'] or [None, None]))}")
        p(f"- gates: {json.dumps(g['checks'])}")
        p(f"- anchors: {json.dumps(s['anchors'])}")
        p(f"- coverage: {json.dumps(s['coverage'])} (floor one-sided by prereg §2; "
          f"structural expectation shown — NF1.9 (e))")
        p(f"- atom calibration (report-only): {json.dumps(s['atom_calibration'])}")
        p(f"- era (report-only): capture Δ {s['era_note']['capture_mean_delta']} vs legacy Δ "
          f"{s['era_note']['legacy_mean_delta']}")
        if c in out["null_states"]:
            p(f"- null state: {json.dumps(out['null_states'][c], default=str)}")
        if c in out.get("gate_sensitivity_dsr_waived", {}):
            p(f"- gate sensitivity (DSR waived — NF-D15 (g″)): "
              f"{json.dumps(out['gate_sensitivity_dsr_waived'][c])}")
        p("")
    p("## Assembled-PPR effect — REPORT-ONLY (PM ruling; never a gate)")
    p("")
    p("```json")
    p(json.dumps(out["ppr_report"], indent=2))
    p("```")
    p("")
    if out.get("pm_rulings"):
        pm = out["pm_rulings"]
        p(f"## PM rulings ({pm['ruled_at']}) — recorded post-run; preserved by --rewrite-report")
        p("")
        for key in ("decision_a", "decision_b", "decision_c"):
            d = pm[key]
            p(f"### {d['title']}")
            p("")
            p(d["ruling"])
            p("")
        p("### Wiring hand-off pins (Decision A — so NF-W6c is a lift-and-serve, "
          "not a re-derivation)")
        p("")
        p(pm["wiring_handoff"]["preamble"])
        p("")
        p("| cell | winning form | constructing function (the pinned code path) |")
        p("|---|---|---|")
        for row in pm["wiring_handoff"]["cells"]:
            p(f"| {row['cell']} | {row['winner']} | {row['construction']} |")
        p("")
        for note in pm["wiring_handoff"]["notes"]:
            p(f"- {note}")
        p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- cells: {pre['cells']} (⛔ closed: {pre['closed_cells']}); arms: {pre['real_arms']}; "
      f"foils: {pre['foils']} (binding sets the bar); anchors: {pre['anchors']}.")
    p(f"- gates: paired lift vs binding foil ∧ `fold_consistency_clause({out['n_folds']})` ∧ "
      f"PBO<{pre['pbo_max']} over the eligible field ∧ DSR≥{pre['dsr_min']} ∧ BH q={pre['fdr_q']} "
      f"(two families, own AND pooled) ∧ coverage floor (one-sided, prereg §2) ∧ degenerates "
      f"lose ∧ permutation behaves. Fails closed.")
    p(f"- FDR families: yards={len(pre['fdr_families']['yards'])} cells, "
      f"tds={len(pre['fdr_families']['tds'])} cells.")
    p("- null classification is HAND-derived (GENUINE_ABSENCE / POWER_LIMITED / "
      "CONSTRAINT_REFUSED); `classify_null` is NOT invoked (the n_arms mis-render — NF-W3 (c)).")
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix cache key "
      f"{out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6b per-stat distributional bake-off")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds, all cells; degenerate movability HARD-asserted; "
                         "artifacts suffixed _smoke")
    ap.add_argument("--only-stat", default=None, choices=list(SD.STATS),
                    help="restrict to one stat's cells — a harness PATH PROOF, never a "
                         "decision artifact (suffixed, loud warning)")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = ("_smoke" if args.smoke else "") + (
        f"_only_{args.only_stat}" if args.only_stat else "")
    json_path = _REPORT_DIR / f"nf_w6b_stat_distributions{suffix}.json"

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
        write_report(out, _REPORT_DIR / f"nf_w6b_stat_distributions{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2, default=str))
        return 0

    if args.only_stat:
        log.warning("⚠️ --only-stat %s: a harness PATH PROOF — partial field, partial FDR "
                    "families; NOT a decision artifact (NF-W2c partial-run rule; artifacts "
                    "suffixed %s)", args.only_stat, suffix)

    t_start = time.time()
    feat, pit_audit, td_audit = W6R.build_matrix_w6(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    stats = (args.only_stat,) if args.only_stat else SD.STATS
    log.info("NF-W6b: %d folds over %d player-weeks; cells %s; labels per cell = %d",
             n_folds, len(feat), SD.cells(), len(SD.all_labels()))

    frs = [run_fold(f, feat, stats) for f in folds]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": SD.STORY, "smoke": bool(args.smoke), "only_stat": args.only_stat,
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": SD.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(len(feat)),
        "matrix_key": W6R.w6_matrix_key(SEASONS),
        "pit_audit": pit_audit, "td_attach_audit": td_audit,
        "preregistration": {
            "cells": list(SD.cells()), "closed_cells": list(SD.CLOSED_CELLS),
            "real_arms": list(SD.REAL_ARMS), "foils": list(SD.FOILS),
            "anchors": list(SD.ANCHORS),
            "primary_metric": SD.PRIMARY_METRIC,
            "pbo_max": SD.PBO_MAX, "dsr_min": SD.DSR_MIN, "fdr_q": SD.FDR_Q,
            "coverage_floor": SD.COVERAGE_FLOOR, "coverage_block_se": SD.COVERAGE_BLOCK_SE,
            "ppr_weights": SD.PPR_WEIGHTS, "knn_k": SD.KNN_K,
            "fit_levels": list(SD.FIT_LEVELS),
            "test_blocks": [list(t) for t in SD.TEST_BLOCKS],
            "purge_weeks": SD.PURGE_WEEKS,
            "fdr_families": {k: list(v) for k, v in SD.fdr_families().items()},
            "capture_era_folds": list(SD.CAPTURE_ERA_FOLDS),
            "features": FEATURES, "seed": SD._SEED,
        },
        "fold_results": frs,
    }
    out.update(derive_verdict_layer(out))

    if args.smoke:
        # ⭐ MH2.1 (d) two-sided movability control: the instrument must SEE both known defects
        # (zero_width = under-dispersion, max_width = over-dispersion) LOSE in every scored
        # cell, and the all-zero nihilist must lose (CRPS-soundness on atom-heavy cells —
        # NF-D11). HARD assert — a blind instrument refuses the smoke.
        bad = {c: [k for k, v in out["selections"][c]["anchors"].items()
                   if k in ("nihilist_loses", "zero_width_loses", "max_width_loses") and not v]
               for c in out["selections"]}
        bad = {c: ks for c, ks in bad.items() if ks}
        if bad:
            raise SystemExit(f"POSITIVE CONTROL FAILED — degenerate anchors do not lose: {bad} "
                             f"(refusing the smoke)")
        log.info("positive control OK: all degenerates lose in every scored cell")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6b_stat_distributions{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "story_decision": out["story_decision"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

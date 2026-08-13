"""run_nf_margin2_tail_extension.py — NF-MARGIN2 §0.5 study: tail-extension-ONLY recalibration
vs the injury-aware `lgbm_hurdle` champion, per position.

THE SINGLE PRE-REGISTERED CONTRAST (the MH2.2-legitimate successor to NF-MARGIN1): the
per-position exponential mean-excess tail model attached to the RAW champion bank (`tail_ext` —
identity map within the grid, exponential extension beyond it; the exact serving-shaped object)
vs the champion as served (`incumbent`). NF-MARGIN1 demonstrated the tail channel at all four
positions (8/8 folds, CIs excluding zero, BH-binding) but its arms were refused by the
field-composition DSR tax; ⛔ that field is NOT shrunk here — this is a fresh registration of a
construction NF-MARGIN1 never scored.

Everything decidable in advance lives as a CONSTANT in `margin2_tail_extension.py`; this runner
READS it (NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_margin2_preregistration.md` BEFORE the full run.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin2_tail_extension --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin2_tail_extension
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin2_tail_extension --rewrite-report
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import margin2_tail_extension as M2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
# ⭐ the matrix build, the champion bank, the incumbent pin and the capture-era fold list are
# IMPORTED from the stories that shipped them (NF-W2d discipline).
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate import (  # noqa: E402
    build_matrix_w2d,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff import (  # noqa: E402
    CAPTURE_ERA_FOLDS,
    assert_incumbents_match_the_w2d_artifact,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w5_opportunity_allocation import (  # noqa: E402
    champion_qmat,
)

log = logging.getLogger("nfl.fantasy.nf_margin2")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = (2016, 2025)

#: Labels whose 199-level randomized-PIT accounting is kept per fold.
PIT_LABELS: tuple[str, ...] = ("incumbent", "tail_ext", "permuted_tail", "pooled_tail",
                               "over_ext")
#: NF-MARGIN1's measured incumbent team-total coverage(80) — a REPORT-ONLY reproduction anchor
#: (same CRN base, same folds, same marginals ⇒ expected to reproduce; LightGBM thread scheduling
#: is the only admissible wiggle, hence a tolerance and never a gate).
M1_INCUMBENT_TEAM_TOTAL = 0.6794
M1_REPRO_TOL = 0.005


# ── Fold-level fitting ──────────────────────────────────────────────────────────────────────────
def _fold_rng(fold_label: str, stream: int) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence([M2._SEED, zlib.crc32(fold_label.encode()), stream]))


def fit_position_params(pos: str, cal: pd.DataFrame, q_cal_sorted: np.ndarray,
                        y_cal_perm: np.ndarray, test: pd.DataFrame,
                        q_test_sorted: np.ndarray, pooled_tail: dict) -> dict:
    """Every construction's parameters for one position. The arm + permuted anchor fit on the
    CAL slice (honest OOS exceedances); the oracle PEEKS at the test fold's own exceedances
    (NF-D16 (g‴)); matched-n refits the arm on the most recent min(n_test, n_cal) CAL rows
    (NF1.9 (f)). `over_ext` carries the ARM's params (scaled inside the construction)."""
    cal_sel = (cal["position"] == pos).to_numpy()
    te_sel = (test["position"] == pos).to_numpy()
    y_cal = cal.loc[cal_sel, "fantasy_points"].to_numpy(dtype=float)
    y_te = test.loc[te_sel, "fantasy_points"].to_numpy(dtype=float)
    qc, qt = q_cal_sorted[cal_sel], q_test_sorted[te_sel]

    tail = M2.fit_tail_betas(qc, y_cal)
    params: dict[str, object] = {
        "incumbent": None, "zero_width": None, "max_width": None,
        "tail_ext": tail,
        "over_ext": tail,                       # scaled by OVER_SCALE inside build_bank_m2
        "permuted_tail": M2.fit_tail_betas(qc, y_cal_perm[cal_sel]),
        "pooled_tail": pooled_tail,
        M2.oracle_of("tail_ext"): M2.fit_tail_betas(qt, y_te),
    }
    order = np.argsort(cal.loc[cal_sel, "gw"].to_numpy())
    take = order[-min(len(y_te), len(y_cal)):]
    params[M2.matched_n_of("tail_ext")] = M2.fit_tail_betas(qc[take], y_cal[take])
    params["_matched_note"] = {"n_cal": int(len(y_cal)), "n_test": int(len(y_te)),
                               "n_matched": int(len(take)),
                               "matched_equals_arm": bool(len(take) == len(y_cal))}
    return params


# ── One fold ────────────────────────────────────────────────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    y_te_all = test["fantasy_points"].to_numpy(dtype=float)
    champ_test_sorted = np.sort(champion_qmat(train, test), axis=1)
    groups, excl = OA.build_team_weeks(test, min_k=M2.MIN_TEAM_K)

    core, cal, cal_note = M2.calibration_split(train)
    champ_cal_sorted = np.sort(champion_qmat(core, cal), axis=1)
    y_cal_all = cal["fantasy_points"].to_numpy(dtype=float)
    y_cal_perm = M2.permute_within_pos_week(cal, _fold_rng(fold.label, 5))
    pooled_tail = M2.fit_tail_betas(champ_cal_sorted, y_cal_all)

    params: dict[str, dict] = {}
    for pos in M2.POSITIONS:
        params[pos] = fit_position_params(pos, cal, champ_cal_sorted, y_cal_perm,
                                          test, champ_test_sorted, pooled_tail)

    scores: dict[str, dict[str, dict]] = {p: {} for p in M2.POSITIONS}
    pit: dict[str, dict[str, dict]] = {p: {} for p in M2.POSITIONS}
    team_total: dict[str, dict] = {}
    eligible = set(M2.eligible_labels())
    # the incumbent banks are built FIRST — every tail-family construction is asserted against
    # them (the structural invariant behind every declared-inactive clause, NF-D20 (g⁗)).
    inc_banks: dict[str, np.ndarray] = {
        pos: M2.build_bank_m2("incumbent", None,
                              champ_test_sorted[(test["position"] == pos).to_numpy()])
        for pos in M2.POSITIONS}
    for label in M2.all_labels():
        full_bank = np.empty((len(test), len(M2.EVAL_LEVELS))) if label in eligible else None
        for pos in M2.POSITIONS:
            sel = (test["position"] == pos).to_numpy()
            bank = (inc_banks[pos] if label == "incumbent"
                    else M2.build_bank_m2(label, params[pos][label], champ_test_sorted[sel]))
            if M2.form_of(label) in ("tail_ext", "permuted_tail", "pooled_tail", "over_ext"):
                M2.assert_within_grid_identity(bank, inc_banks[pos], label)
            scores[pos][label] = M2.score_bank(bank, y_te_all[sel])
            if label in PIT_LABELS:
                rng = np.random.default_rng(np.random.SeedSequence(
                    [M2._SEED, zlib.crc32(f"{fold.label}|{label}|{pos}".encode()), 4]))
                pit[pos][label] = M2.pit_stats_m2(
                    M2.randomized_pit_levels(bank, y_te_all[sel], rng))
            if full_bank is not None:
                full_bank[sel] = bank
        if full_bank is not None:
            team_total[label] = M2.team_total_check(groups, full_bank, y_te_all, fold.label)

    out = {
        "label": fold.label, "exclusions": excl, "cal_note": cal_note,
        "scores": scores, "pit": pit, "team_total": team_total,
        "params_digest": {
            pos: {"tail": {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in params[pos]["tail_ext"].items()},
                  "permuted_tail": {k: (round(v, 4) if isinstance(v, float) else v)
                                    for k, v in params[pos]["permuted_tail"].items()},
                  "pooled_tail": {k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in pooled_tail.items()},
                  "matched_note": params[pos]["_matched_note"]}
            for pos in M2.POSITIONS},
        "runtime_seconds": round(time.time() - t0, 1),
    }
    log.info("[M2] fold %s in %.1fs (%d test rows, %d team-weeks) — beta_hi (arm): %s",
             fold.label, out["runtime_seconds"], len(test), excl["n_groups"],
             {p: out["params_digest"][p]["tail"]["beta_hi"] for p in M2.POSITIONS})
    return out


# ── Selection per position ──────────────────────────────────────────────────────────────────────
def _metric_matrix(frs: list[dict], pos: str, metric: str = M2.PRIMARY_METRIC) -> pd.DataFrame:
    return pd.DataFrame({fr["label"]: {lab: fr["scores"][pos][lab][metric]
                                       for lab in fr["scores"][pos]} for fr in frs}).T


def _pooled_pit(frs: list[dict], pos: str, label: str) -> dict:
    return M2.pool_pit_stats_m2([fr["pit"][pos][label] for fr in frs])


def _pooled_coverage(frs: list[dict], pos: str, label: str) -> dict:
    n = sum(fr["scores"][pos][label]["n"] for fr in frs)
    cov = (sum(fr["scores"][pos][label]["coverage_80"] * fr["scores"][pos][label]["n"]
               for fr in frs) / n) if n else float("nan")
    se = float(np.sqrt(M2.COVERAGE_FLOOR * (1 - M2.COVERAGE_FLOOR) / n)) if n else float("nan")
    return {"coverage_80": round(cov, 4), "n_rows": int(n), "binomial_se": round(se, 4),
            "blocking_shortfall": bool(n and (M2.COVERAGE_FLOOR - cov)
                                       > M2.COVERAGE_BLOCK_SE * se)}


def _ci_block(deltas: np.ndarray) -> dict:
    m, lo, hi = M2.paired_ci95(deltas)
    return {"mean_delta": None if m is None else round(m, 5),
            "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
            "fold_wins": int((deltas > 0).sum()),
            "p_one_sided": M14.onesided_paired_pvalue(deltas)}


def select_position(frs: list[dict], pos: str, n_folds: int) -> dict:
    crps = _metric_matrix(frs, pos)
    mean_crps = crps.mean(axis=0)
    winner, foil = "tail_ext", "incumbent"
    deltas = (crps[foil] - crps[winner]).to_numpy(dtype=float)
    mean_d, lo, hi = M2.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    sd = float(np.nanstd(deltas, ddof=1))
    sr = float(np.nanmean(deltas)) / sd if sd > 1e-12 else None
    # ⭐ a 1-arm field: SR0 = 0 inside deflated_sharpe (nothing to deflate) ⇒ DSR = the PSR of
    # the pre-registered contrast. Anchors never enter the trial field (MH2.1 (a) — automatic).
    dsr = M14.deflated_sharpe(deltas, np.asarray([sr if sr is not None else 0.0]))
    pval = M14.onesided_paired_pvalue(deltas)

    d_perm_better = (crps[winner] - crps["permuted_tail"]).to_numpy(dtype=float)
    mean_pb = float(np.nanmean(d_perm_better))
    p_pb = M14.onesided_paired_pvalue(d_perm_better)
    anchors = {
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        # ⭐ NF1.8: the floor is proved a CONSTRAINT by the degenerate SATISFYING it while losing
        # the primary — reported, never a ship condition.
        "max_width_satisfies_floor": not _pooled_coverage(frs, pos,
                                                          "max_width")["blocking_shortfall"],
        # ⭐ NF-D20: the magnitude degenerate, registered to LOSE. If it wins, the mean-excess
        # fit UNDER-extends — a refuted magnitude hypothesis, decomposed in the report.
        "over_ext_loses": bool(mean_crps["over_ext"] > mean_crps[winner]),
        # report-only — the permutation shares the marginal mechanism BY EXPECTATION (NF-D16 (2));
        # the gate clause is only that it must not significantly BEAT the arm (fail-closed).
        "winner_beats_permuted": bool(mean_crps["permuted_tail"] > mean_crps[winner]),
        "permuted_not_significantly_better": M2.permuted_not_significantly_better(mean_pb, p_pb),
        "no_arm_beats_own_oracle": bool(
            mean_crps[winner] > mean_crps[M2.oracle_of("tail_ext")]),
        # ⭐ the GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n.
        "oracle_floor_respected_at_matched_n": bool(
            (mean_crps[winner] > mean_crps[M2.oracle_of("tail_ext")])
            or (mean_crps[M2.oracle_of("tail_ext")]
                < mean_crps[M2.matched_n_of("tail_ext")])),
    }
    oracle_detail = {
        "arm": round(float(mean_crps[winner]), 5),
        "own_form_oracle": round(float(mean_crps[M2.oracle_of("tail_ext")]), 5),
        "matched_n": round(float(mean_crps[M2.matched_n_of("tail_ext")]), 5),
        "oracle_beats_matched_n": bool(mean_crps[M2.matched_n_of("tail_ext")]
                                       > mean_crps[M2.oracle_of("tail_ext")]),
    }

    # ── the pre-registered attribution decomposition (report-only) ──
    attribution = {
        "marginal_share": _ci_block((crps[foil] - crps["permuted_tail"]).to_numpy(dtype=float)),
        "alignment_share": _ci_block(d_perm_better * -1.0),
        "conditioning_margin": _ci_block(
            (crps["pooled_tail"] - crps[winner]).to_numpy(dtype=float)),
        "note": ("marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; "
                 "EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; "
                 "conditioning_margin = pooled_tail − tail_ext (per-position conditioning's "
                 "earn in the tail; informs the serving object)."),
    }

    # ── the two-sided calibration gate, vs the INCUMBENT, on the 199-level PIT ──
    pit_inc = _pooled_pit(frs, pos, "incumbent")
    pit_win = _pooled_pit(frs, pos, winner)
    dev_inc, dev_win = M2.tail_mass_deviation(pit_inc), M2.tail_mass_deviation(pit_win)
    calibration = {
        "tail_mass_delta_vs_incumbent": round(dev_inc - dev_win, 5),
        "dev_incumbent": round(dev_inc, 5), "dev_winner": round(dev_win, 5),
        "incumbent_pit": pit_inc, "winner_pit": pit_win,
    }

    # ── declared-inactive clauses: proved zero, recorded as construction FACTS (NF-D20 (g⁗)) ──
    wink = _metric_matrix(frs, pos, "winkler_80")
    wink_delta = float((wink[foil] - wink[winner]).mean())
    cov80_delta = float(np.mean([fr["scores"][pos][foil]["coverage_80"]
                                 - fr["scores"][pos][winner]["coverage_80"] for fr in frs]))
    cov95_delta = float(np.mean([fr["scores"][pos][foil]["coverage_95"]
                                 - fr["scores"][pos][winner]["coverage_95"] for fr in frs]))
    if max(abs(wink_delta), abs(cov80_delta), abs(cov95_delta)) > 1e-9:
        raise ValueError(
            f"{pos}: a declared-inactive metric moved (winkler {wink_delta}, cov80 "
            f"{cov80_delta}, cov95 {cov95_delta}) — the arm is not tail-only; harness bug")
    construction_facts = {
        "winkler_80_delta": 0.0, "coverage_80_delta": 0.0, "coverage_95_delta": 0.0,
        "note": ("IDENTICALLY ZERO BY CONSTRUCTION (within-grid identity asserted every fold) — "
                 "these clauses are structurally INACTIVE for a tail-only arm and are recorded "
                 "as facts, never counted as passing gates (NF-D20 (g⁗))."),
    }

    cov_map = {m: {lab: round(float(np.mean([fr["scores"][pos][lab][m] for fr in frs])), 4)
                   for lab in (winner, "incumbent", "over_ext", "max_width")}
               for m in ("coverage_80", "coverage_95", "coverage_99")}
    fingerprint = {
        "incumbent_cov95_equals_cov99": bool(
            abs(cov_map["coverage_95"]["incumbent"] - cov_map["coverage_99"]["incumbent"])
            < 1e-9),
        "winner_cov99_exceeds_cov95": bool(cov_map["coverage_99"][winner]
                                           > cov_map["coverage_95"][winner]),
        "note": "the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and "
                "BREAK for the winner — a construction sanity read, report-only.",
    }

    thin_cells = {
        "n_fold_positions_thin_hi": int(sum(fr["params_digest"][pos]["tail"]["thin_hi"]
                                            for fr in frs)),
        "n_fold_positions_thin_lo": int(sum(fr["params_digest"][pos]["tail"]["thin_lo"]
                                            for fr in frs)),
    }

    fold_labels = [fr["label"] for fr in frs]
    cap = [i for i, lb in enumerate(fold_labels) if lb in CAPTURE_ERA_FOLDS]
    leg = [i for i, lb in enumerate(fold_labels) if lb not in CAPTURE_ERA_FOLDS]
    return {
        "position": pos, "winner": winner, "best_foil": foil,
        "selection_metric": M2.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        # ⭐ PBO is UNDEFINED BY DESIGN for a one-contrast field (GE.pbo_is_evaluable) — declared
        # in advance, never a gate (the NF-W4 Layer-B precedent; NF-W3's error not repeated).
        "pbo": None,
        "pbo_state": ("UNDEFINED — CSCV resamples a FIELD; NF-MARGIN2 fields ONE pre-registered "
                      "contrast, so there was no search to overfit. Declared before the run; "
                      "deliberately NOT a gate."),
        "dsr": dsr, "p_one_sided": pval,
        "observed_sr": None if sr is None else round(sr, 3),
        "var_trials_sr": None,
        "anchors": anchors, "oracle_detail": oracle_detail,
        "permutation_detail": {"permuted_better_mean": round(mean_pb, 5),
                               "permuted_better_p_one_sided": p_pb},
        "attribution": attribution,
        "calibration": calibration, "construction_facts": construction_facts,
        "coverage": {**_pooled_coverage(frs, pos, winner),
                     "structurally_inactive": True,
                     "inactive_note": "identical to the incumbent's by construction — passing "
                                      "the floor is NOT evidence (NF-D20 (g⁗))."},
        "coverage_map": cov_map, "tail_fingerprint": fingerprint,
        "thin_tail_cells": thin_cells,
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 4) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 4) if leg else None),
            "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
        },
    }


# ── Verdict layer (derived, shared with --rewrite-report — the NF-W3/W5 rule) ───────────────────
def _classify_position(sel: dict, n_folds: int, checks: dict) -> dict:
    hand = M2.hand_classify_refusal_margin2(checks)
    if hand is not None:
        return hand
    # the instrument's verdict is RECORDED beside the hand classification, never discarded —
    # its n_arms=1 rendering is the known bug (NF-W3/NF-W4, 4th/5th occurrences).
    v = cv_power.classify_null(
        metric=f"nf_margin2_{sel['position']}_crps", n_folds=n_folds,
        n_arms=len(M2.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=M2.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    return M2.classify_layer_b(
        sel, n_folds=n_folds,
        instrument_verdict={"state": v.state, "reason": v.reason,
                            "retest_trigger": v.retest_trigger})


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored selections — no refit (NF-W2e one level up)."""
    n_folds = out["n_folds"]
    pvals = {f"margin2_tail_{p}": out["selections"][p]["p_one_sided"] for p in M2.POSITIONS}
    fdr = {"family": M14.bh_fdr(pvals, q=M2.FDR_Q), "pvals": pvals,
           "note": "ONE pre-registered family (own-family IS the pooled correction)"}
    gates, null_states, verdict = {}, {}, {}
    for p in M2.POSITIONS:
        sel = out["selections"][p]
        gate = M2.compose_gate_margin2(sel, fdr["family"].get(f"margin2_tail_{p}", False))
        gates[p] = gate
        if gate["ship"]:
            verdict[p] = "SHIP"
        else:
            null_states[p] = _classify_position(sel, n_folds, gate["checks"])
            verdict[p] = null_states[p].get("state", "NULL")
    headline = " ".join(f"{p}[{verdict[p]}]" for p in M2.POSITIONS)
    return {"fdr": fdr, "gates": gates, "null_states": null_states, "verdict": verdict,
            "headline": headline}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-MARGIN2 — tail-extension-ONLY recalibration vs the champion (§0.5, 1-arm family)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis on the NF-W2d two-era "
      f"matrix) · **player-weeks:** {out['n_rows']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a "
      "clearing arm's serving path — attach the per-position tail betas to the served bank, no "
      "refit — is blocked on NF-C6 Ph2 + NF-G0). The MH2.2-legitimate successor to NF-MARGIN1: "
      "a FRESH registration of the single demonstrated contrast, on a construction NF-MARGIN1 "
      f"never scored. Selection metric `{M2.PRIMARY_METRIC}`; PIT accounting on the 199-level "
      "bank (the 39-level instrument is structurally blind to this arm). PBO UNDEFINED by "
      "design; DSR = PSR at a 1-arm field. Every direction word below is three-way and derived "
      "at report time, failing closed to `TIES` (NF-W2e).")
    p("")
    pa = out["pit_audit"]
    p(f"**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN2):** "
      f"{pa['game_groups_checked']} game-groups / {pa['records_checked']} records checked; "
      f"{pa['rows_dropped']} rows dropped fail-closed.")
    p("")
    p(f"**Verdict:** {out['headline']}")
    p("")
    p("## Construction facts (declared structurally INACTIVE — never counted as evidence)")
    p("")
    p("Within-grid identity asserted every fold: Winkler-80, coverage(50/80/95) deltas vs the "
      "incumbent are IDENTICALLY ZERO by construction; only 8 of 199 eval columns (4/side beyond "
      "the champion grid) can differ. The coverage floor therefore cannot newly fire "
      "(NF-D20 (g⁗) — the active-clause count is what the gate's evidence rests on).")
    p("")
    p("## Team-total re-check (independence copula, report-only — the NF-W5 loop)")
    p("")
    tt = out["team_total_pooled"]
    p(pd.DataFrame([{"label": k, **v} for k, v in tt.items()]).to_markdown(index=False))
    p("")
    ra = out["reproduction_anchor"]
    ra_word = ("REPRODUCED" if ra["reproduced"]
               else "⚠️ NOT reproduced (investigate before trusting cross-story comparability)")
    p(f"Reproduction anchor (report-only): incumbent team-total coverage(80) measured "
      f"{ra['measured']} vs NF-MARGIN1's {ra['expected']} — {ra_word} (tol {M1_REPRO_TOL}).")
    p("")
    for pos in M2.POSITIONS:
        sel = out["selections"][pos]
        p(f"## {pos} — **{out['verdict'][pos]}**")
        p("")
        p(M2.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps_q199": v}
                        for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps_q199").to_markdown(index=False, floatfmt=".5f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} (UNDEFINED by design) · "
          f"DSR(=PSR, 1-arm) {sel['dsr']} · p {sel['p_one_sided']} · BH "
          f"{out['fdr']['family'].get('margin2_tail_' + pos)}")
        c = sel["calibration"]
        p(f"- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal {M2.NOMINAL_EXTREME}"
          f"/side): dev {c['dev_incumbent']} → {c['dev_winner']} (delta "
          f"{c['tail_mass_delta_vs_incumbent']:+}) · p_below_eval/p_above_eval incumbent "
          f"{c['incumbent_pit']['p_below_eval']}/{c['incumbent_pit']['p_above_eval']} → winner "
          f"{c['winner_pit']['p_below_eval']}/{c['winner_pit']['p_above_eval']} · "
          f"beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal {M2.NOMINAL_TAIL}/side) "
          f"{c['incumbent_pit']['p_below_grid']}/{c['incumbent_pit']['p_above_grid']}")
        p(f"- coverage (floor {M2.COVERAGE_FLOOR}, structurally inactive here): {sel['coverage']}"
          f" · map {sel['coverage_map']} · fingerprint {sel['tail_fingerprint']}")
        p(f"- attribution (pre-registered, report-only): {sel['attribution']}")
        p(f"- anchors: {sel['anchors']}")
        if not sel["anchors"]["over_ext_loses"]:
            p("- ⚠️ **REFUTED MAGNITUDE HYPOTHESIS (NF-D20):** `over_ext` (betas × "
              f"{M2.OVER_SCALE}, registered to lose) BEAT the fitted arm — the mean-excess fit "
              "UNDER-extends and the metric optimum lies beyond the fitted magnitude. Recorded "
              "as a decomposed refutation; the anchor stays an anchor (⛔ never re-labelled).")
        p(f"- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {sel['oracle_detail']}")
        p(f"- permutation: {sel['permutation_detail']} · thin tail cells: "
          f"{sel['thin_tail_cells']}")
        p(f"- 📅 era note: {sel['era_note']}")
        p(f"- gate: {out['gates'][pos]['checks']}")
        p("")
    p("## Null-state classification")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    p("## Pre-registration echo")
    p("")
    p("```json")
    p(json.dumps(out["preregistration"], indent=2, default=str))
    p("```")
    path.write_text("\n".join(a))


def preregistration_echo() -> dict:
    return {
        "real_arms": list(M2.REAL_ARMS), "foils": list(M2.FOILS),
        "anchors": list(M2.anchors()), "eligible": M2.eligible_labels(),
        "primary_metric": M2.PRIMARY_METRIC,
        "pit_instrument": "randomized_pit_levels on the 199-level bank (the 39-level PIT is "
                          "structurally blind to a beyond-grid-only arm)",
        "eval_levels": {"n": int(len(M2.EVAL_LEVELS)),
                        "lo": float(M2.EVAL_LEVELS[0]), "hi": float(M2.EVAL_LEVELS[-1])},
        "over_scale": M2.OVER_SCALE, "min_tail_n": M2.MIN_TAIL_N,
        "nominal_tail": M2.NOMINAL_TAIL,
        "cal_split": {"target_fraction": MC.CAL_TARGET_FRACTION, "min_rows": MC.CAL_MIN_ROWS,
                      "purge_weeks": M2.PURGE_WEEKS},
        "test_blocks": [list(t) for t in M2.TEST_BLOCKS],
        "pbo": "UNDEFINED by design (1-arm family — GE.pbo_is_evaluable)",
        "dsr_min": M2.DSR_MIN, "fdr_q": M2.FDR_Q,
        "fdr_family": list(M2.FDR_FAMILY),
        "coverage_floor": M2.COVERAGE_FLOOR,
        "declared_inactive_clauses": ["winkler_80", "coverage_50", "coverage_80", "coverage_95"],
        "team_total_samples": M2.TEAM_TOTAL_SAMPLES,
        "capture_era_folds": list(CAPTURE_ERA_FOLDS),
        "seed": M2._SEED,
    }


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-MARGIN2 tail-extension-only study")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_margin2_tail_extension{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored selections without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_margin2_tail_extension{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    assert_incumbents_match_the_w2d_artifact()
    feat, pit_audit, _store_raw = build_matrix_w2d(SEASONS, rebuild_cache=args.rebuild_cache)
    if "team" not in feat.columns:
        raise ValueError("the W2d matrix carries no `team` column — the team-total re-check "
                         "cannot be grouped; refusing to proceed")
    folds = W2.build_folds_w2(feat, M2.TEST_BLOCKS)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-MARGIN2: %d folds over %d player-weeks; field = %d arm + %d foil + %d anchors; "
             "eval grid %d levels (8 beyond-grid columns carry the whole channel)",
             n_folds, len(feat), len(M2.REAL_ARMS), len(M2.FOILS), len(M2.anchors()),
             len(M2.EVAL_LEVELS))

    frs = [run_fold(f, feat) for f in folds]

    selections = {pos: select_position(frs, pos, n_folds) for pos in M2.POSITIONS}
    tt_pooled = {lab: M2.pool_team_total([fr["team_total"][lab] for fr in frs])
                 for lab in M2.eligible_labels()}
    inc_tt = tt_pooled["incumbent"].get("coverage_80")
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": M2.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": M2.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(sum(len(f.test_idx) for f in folds)),
        "pit_audit": pit_audit,
        "preregistration": preregistration_echo(),
        "selections": selections,
        "team_total_pooled": tt_pooled,
        "reproduction_anchor": {
            "expected": M1_INCUMBENT_TEAM_TOTAL, "measured": inc_tt,
            "reproduced": bool(inc_tt is not None
                               and abs(inc_tt - M1_INCUMBENT_TEAM_TOTAL) <= M1_REPRO_TOL),
            "note": ("REPORT-ONLY: same CRN base + folds + marginals as NF-MARGIN1 ⇒ the "
                     "incumbent row should reproduce; valid only on the full 8-fold run."),
        },
        "fold_results": [{k: fr[k] for k in ("label", "scores", "cal_note", "team_total",
                                             "params_digest", "exclusions",
                                             "runtime_seconds")} for fr in frs],
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_margin2_tail_extension{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "team_total_pooled": out["team_total_pooled"],
                      "reproduction_anchor": out["reproduction_anchor"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""run_nf_margin3_tail_estimator.py — NF-MARGIN3 §0.5 study: a better QB/WR tail-magnitude
estimator vs `tail_ext`, per position.

THE SINGLE PRE-REGISTERED CONTRAST (the successor NF-MARGIN2 named): per-position, per-side
EMPIRICAL-QUANTILE tail offsets calibrated on the eval-end exceedance rates of the purged
calibration slice (`eq_tail` — the pooled pinball optimum at each beyond-grid eval level, i.e.
the exact quantity NF-MARGIN2's `over_ext`/`permuted_tail` anchors proved the mean-excess proxy
under-estimates) vs `tail_ext` — ⭐ the STANDING OBJECT at every position (shipped at RB/TE),
⛔ not the flat-tail incumbent. FAMILY = QB + WR (the two refused positions); RB/TE run and are
reported but are registered NON-SHIPPABLE — `tail_ext` stands there.

Everything decidable in advance lives as a CONSTANT in `margin3_tail_estimator.py`; this runner
READS it (NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_margin3_preregistration.md` BEFORE the full run.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin3_tail_estimator --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin3_tail_estimator
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin3_tail_estimator --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import margin3_tail_estimator as M3  # noqa: E402
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

log = logging.getLogger("nfl.fantasy.nf_margin3")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = (2016, 2025)

#: Labels whose 199-level randomized-PIT accounting is kept per fold.
PIT_LABELS: tuple[str, ...] = ("incumbent", "tail_ext", "eq_tail", "permuted_eq", "pooled_eq",
                               "over_ext_eq")
#: Constructions whose full-slate bank feeds the team-total re-check: the eligible field plus
#: the incumbent REFERENCE row (needed only for the cross-story reproduction anchor).
TEAM_TOTAL_LABELS: tuple[str, ...] = ("eq_tail", "tail_ext", "incumbent")

#: ⭐ Cross-story reproduction anchors (REPORT-ONLY, full 8-fold run only): the foil and the
#: reference are byte-identical CONSTRUCTIONS to NF-MARGIN2's (the builder delegates), so their
#: pooled numbers must reproduce that record. LightGBM thread scheduling is the only admissible
#: wiggle, hence tolerances and never gates. A miss says the substrate moved — investigate
#: before trusting any cross-story comparison (NF-D10's cache_is_current, one story over).
M2_TEAM_TOTAL = {"incumbent": 0.6794, "tail_ext": 0.7052}
M2_TEAM_TOTAL_TOL = 0.005
M2_MEAN_CRPS = {
    "tail_ext": {"QB": 2.41015, "RB": 2.35729, "WR": 2.51102, "TE": 1.72813},
    "incumbent": {"QB": 2.41416, "RB": 2.36012, "WR": 2.51426, "TE": 1.72963},
}
M2_MEAN_CRPS_TOL = 0.002


# ── Fold-level fitting ──────────────────────────────────────────────────────────────────────────
def _fold_rng(fold_label: str, stream: int) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence([M3._SEED, zlib.crc32(fold_label.encode()), stream]))


def _eq_digest(p: dict) -> dict:
    return {"t_hi": [round(float(t), 3) for t in np.asarray(p["t_hi"], dtype=float)],
            "t_lo": [round(float(t), 3) for t in np.asarray(p["t_lo"], dtype=float)],
            "n_hi": p["n_hi"], "n_lo": p["n_lo"],
            "m_hi": round(p["m_hi"], 4), "m_lo": round(p["m_lo"], 4),
            "thin_hi": p["thin_hi"], "thin_lo": p["thin_lo"],
            "clamped_hi": p["clamped_hi"], "clamped_lo": p["clamped_lo"]}


def fit_position_params(pos: str, cal: pd.DataFrame, q_cal_sorted: np.ndarray,
                        y_cal_perm: np.ndarray, test: pd.DataFrame,
                        q_test_sorted: np.ndarray, pooled_eq: dict) -> dict:
    """Every construction's parameters for one position. The arm + permuted anchor fit on the
    CAL slice (honest OOS exceedances); the FOIL `tail_ext` is fit exactly as NF-MARGIN2 fit it
    (mean-excess betas on the same slice — reproduction by construction); the oracle PEEKS at
    the test fold's own exceedances; matched-n refits the arm on the most recent
    min(n_test, n_cal) CAL rows (NF1.9 (f)). `over_ext_eq` carries the ARM's params (scaled
    inside the construction)."""
    cal_sel = (cal["position"] == pos).to_numpy()
    te_sel = (test["position"] == pos).to_numpy()
    y_cal = cal.loc[cal_sel, "fantasy_points"].to_numpy(dtype=float)
    y_te = test.loc[te_sel, "fantasy_points"].to_numpy(dtype=float)
    qc, qt = q_cal_sorted[cal_sel], q_test_sorted[te_sel]

    eq = M3.fit_eq_tail(qc, y_cal)
    params: dict[str, object] = {
        "incumbent": None, "zero_width": None, "max_width": None,
        "eq_tail": eq,
        "over_ext_eq": eq,                      # scaled by OVER_SCALE inside build_bank_m3
        "tail_ext": M2.fit_tail_betas(qc, y_cal),
        "permuted_eq": M3.fit_eq_tail(qc, y_cal_perm[cal_sel]),
        "pooled_eq": pooled_eq,
        M3.oracle_of("eq_tail"): M3.fit_eq_tail(qt, y_te),
    }
    order = np.argsort(cal.loc[cal_sel, "gw"].to_numpy())
    take = order[-min(len(y_te), len(y_cal)):]
    params[M3.matched_n_of("eq_tail")] = M3.fit_eq_tail(qc[take], y_cal[take])
    params["_matched_note"] = {"n_cal": int(len(y_cal)), "n_test": int(len(y_te)),
                               "n_matched": int(len(take)),
                               "matched_equals_arm": bool(len(take) == len(y_cal))}
    return params


def _offsets_vs_exponential(eq: dict, tail: dict) -> dict:
    """Report-only: how the calibrated offsets compare to the foil's exponential-implied
    t_exp(u) = beta·ln(0.025/(1−u)) at the far level (0.995 / 0.005) — the pre-registered
    'the fit under-extends' read, made quantitative per fold."""
    ln5 = float(np.log(M3.NOMINAL_TAIL / M3.NOMINAL_EXTREME))
    t_hi = float(np.asarray(eq["t_hi"], dtype=float)[-1])
    t_lo = float(np.asarray(eq["t_lo"], dtype=float)[0])
    exp_hi = float(tail["beta_hi"]) * ln5
    exp_lo = float(tail["beta_lo"]) * ln5
    return {"t_hi_995": round(t_hi, 3), "exp_hi_995": round(exp_hi, 3),
            "ratio_hi_995": round(t_hi / exp_hi, 3) if exp_hi > 0 else None,
            "t_lo_005": round(t_lo, 3), "exp_lo_005": round(exp_lo, 3),
            "ratio_lo_005": round(t_lo / exp_lo, 3) if exp_lo > 0 else None}


# ── One fold ────────────────────────────────────────────────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    y_te_all = test["fantasy_points"].to_numpy(dtype=float)
    champ_test_sorted = np.sort(champion_qmat(train, test), axis=1)
    groups, excl = OA.build_team_weeks(test, min_k=M3.MIN_TEAM_K)

    core, cal, cal_note = M3.calibration_split(train)
    champ_cal_sorted = np.sort(champion_qmat(core, cal), axis=1)
    y_cal_all = cal["fantasy_points"].to_numpy(dtype=float)
    y_cal_perm = M3.permute_within_pos_week(cal, _fold_rng(fold.label, 5))
    pooled_eq = M3.fit_eq_tail(champ_cal_sorted, y_cal_all)

    params: dict[str, dict] = {}
    for pos in M3.POSITIONS:
        params[pos] = fit_position_params(pos, cal, champ_cal_sorted, y_cal_perm,
                                          test, champ_test_sorted, pooled_eq)

    scores: dict[str, dict[str, dict]] = {p: {} for p in M3.POSITIONS}
    pit: dict[str, dict[str, dict]] = {p: {} for p in M3.POSITIONS}
    team_total: dict[str, dict] = {}
    # the incumbent banks are built FIRST — every tail-family construction (arm AND foil) is
    # asserted against them (the invariant behind every declared-inactive clause, NF-D20 (g⁗)).
    inc_banks: dict[str, np.ndarray] = {
        pos: M3.build_bank_m3("incumbent", None,
                              champ_test_sorted[(test["position"] == pos).to_numpy()])
        for pos in M3.POSITIONS}
    for label in M3.all_labels():
        full_bank = (np.empty((len(test), len(M3.EVAL_LEVELS)))
                     if label in TEAM_TOTAL_LABELS else None)
        for pos in M3.POSITIONS:
            sel = (test["position"] == pos).to_numpy()
            bank = (inc_banks[pos] if label == "incumbent"
                    else M3.build_bank_m3(label, params[pos][label], champ_test_sorted[sel]))
            if M3.form_of(label) in ("tail_ext", *M3._EQ_FAMILY, "over_ext_eq"):
                M3.assert_within_grid_identity(bank, inc_banks[pos], label)
            scores[pos][label] = M3.score_bank(bank, y_te_all[sel])
            if label in PIT_LABELS:
                rng = np.random.default_rng(np.random.SeedSequence(
                    [M3._SEED, zlib.crc32(f"{fold.label}|{label}|{pos}".encode()), 4]))
                pit[pos][label] = M3.pit_stats_m2(
                    M3.randomized_pit_levels(bank, y_te_all[sel], rng))
            if full_bank is not None:
                full_bank[sel] = bank
        if full_bank is not None:
            team_total[label] = M3.team_total_check(groups, full_bank, y_te_all, fold.label)

    out = {
        "label": fold.label, "exclusions": excl, "cal_note": cal_note,
        "scores": scores, "pit": pit, "team_total": team_total,
        "params_digest": {
            pos: {"eq": _eq_digest(params[pos]["eq_tail"]),
                  "permuted_eq": _eq_digest(params[pos]["permuted_eq"]),
                  "pooled_eq": _eq_digest(pooled_eq),
                  "foil_tail": {k: (round(v, 4) if isinstance(v, float) else v)
                                for k, v in params[pos]["tail_ext"].items()},
                  "offsets_vs_exponential": _offsets_vs_exponential(
                      params[pos]["eq_tail"], params[pos]["tail_ext"]),
                  "matched_note": params[pos]["_matched_note"]}
            for pos in M3.POSITIONS},
        "runtime_seconds": round(time.time() - t0, 1),
    }
    log.info("[M3] fold %s in %.1fs (%d test rows, %d team-weeks) — t_hi@0.995 (arm): %s",
             fold.label, out["runtime_seconds"], len(test), excl["n_groups"],
             {p: out["params_digest"][p]["eq"]["t_hi"][-1] for p in M3.POSITIONS})
    return out


# ── Selection per position ──────────────────────────────────────────────────────────────────────
def _metric_matrix(frs: list[dict], pos: str, metric: str = M3.PRIMARY_METRIC) -> pd.DataFrame:
    return pd.DataFrame({fr["label"]: {lab: fr["scores"][pos][lab][metric]
                                       for lab in fr["scores"][pos]} for fr in frs}).T


def _pooled_pit(frs: list[dict], pos: str, label: str) -> dict:
    return M3.pool_pit_stats_m2([fr["pit"][pos][label] for fr in frs])


def _pooled_coverage(frs: list[dict], pos: str, label: str) -> dict:
    n = sum(fr["scores"][pos][label]["n"] for fr in frs)
    cov = (sum(fr["scores"][pos][label]["coverage_80"] * fr["scores"][pos][label]["n"]
               for fr in frs) / n) if n else float("nan")
    se = float(np.sqrt(M3.COVERAGE_FLOOR * (1 - M3.COVERAGE_FLOOR) / n)) if n else float("nan")
    return {"coverage_80": round(cov, 4), "n_rows": int(n), "binomial_se": round(se, 4),
            "blocking_shortfall": bool(n and (M3.COVERAGE_FLOOR - cov)
                                       > M3.COVERAGE_BLOCK_SE * se)}


def _ci_block(deltas: np.ndarray) -> dict:
    m, lo, hi = M3.paired_ci95(deltas)
    return {"mean_delta": None if m is None else round(m, 5),
            "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
            "fold_wins": int((deltas > 0).sum()),
            "p_one_sided": M14.onesided_paired_pvalue(deltas)}


def select_position(frs: list[dict], pos: str, n_folds: int) -> dict:
    crps = _metric_matrix(frs, pos)
    mean_crps = crps.mean(axis=0)
    winner, foil = "eq_tail", "tail_ext"
    deltas = (crps[foil] - crps[winner]).to_numpy(dtype=float)
    mean_d, lo, hi = M3.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    sd = float(np.nanstd(deltas, ddof=1))
    sr = float(np.nanmean(deltas)) / sd if sd > 1e-12 else None
    # ⭐ a 1-arm field: SR0 = 0 inside deflated_sharpe ⇒ DSR = the PSR of the pre-registered
    # contrast. Anchors + the incumbent reference never enter the trial field (MH2.1 (a)).
    dsr = M14.deflated_sharpe(deltas, np.asarray([sr if sr is not None else 0.0]))
    pval = M14.onesided_paired_pvalue(deltas)

    d_perm_better = (crps[winner] - crps["permuted_eq"]).to_numpy(dtype=float)
    mean_pb = float(np.nanmean(d_perm_better))
    p_pb = M14.onesided_paired_pvalue(d_perm_better)
    anchors = {
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        # ⭐ NF1.8: the floor is proved a CONSTRAINT by the degenerate SATISFYING it while
        # losing the primary — reported, never a ship condition.
        "max_width_satisfies_floor": not _pooled_coverage(frs, pos,
                                                          "max_width")["blocking_shortfall"],
        # ⭐ NF-D20: the magnitude degenerate, registered to LOSE. The offsets sit AT the
        # calibration pinball optimum, so a win for ×3 refutes the calibrated-optimum
        # hypothesis itself — decomposed in the report, never re-labelled.
        "over_ext_eq_loses": bool(mean_crps["over_ext_eq"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps["permuted_eq"] > mean_crps[winner]),
        "permuted_not_significantly_better": M3.permuted_not_significantly_better(mean_pb, p_pb),
        "no_arm_beats_own_oracle": bool(
            mean_crps[winner] > mean_crps[M3.oracle_of("eq_tail")]),
        # ⭐ the GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n.
        "oracle_floor_respected_at_matched_n": bool(
            (mean_crps[winner] > mean_crps[M3.oracle_of("eq_tail")])
            or (mean_crps[M3.oracle_of("eq_tail")]
                < mean_crps[M3.matched_n_of("eq_tail")])),
    }
    oracle_detail = {
        "arm": round(float(mean_crps[winner]), 5),
        "own_form_oracle": round(float(mean_crps[M3.oracle_of("eq_tail")]), 5),
        "matched_n": round(float(mean_crps[M3.matched_n_of("eq_tail")]), 5),
        "oracle_beats_matched_n": bool(mean_crps[M3.matched_n_of("eq_tail")]
                                       > mean_crps[M3.oracle_of("eq_tail")]),
    }

    # ── the pre-registered attribution reads (report-only) ──
    attribution = {
        "vs_incumbent_total": _ci_block((crps["incumbent"] - crps[winner]).to_numpy(dtype=float)),
        "magnitude_channel": _ci_block(deltas),
        "conditioning_margin": _ci_block(
            (crps["pooled_eq"] - crps[winner]).to_numpy(dtype=float)),
        "note": ("vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole "
                 "tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what "
                 "the successor estimator adds over the shipped exponential); "
                 "conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; "
                 "informs the serving object)."),
    }

    # ── the tail-mass gate, vs the FOIL, on the 199-level PIT (incumbent co-reported) ──
    pit_inc = _pooled_pit(frs, pos, "incumbent")
    pit_foil = _pooled_pit(frs, pos, foil)
    pit_win = _pooled_pit(frs, pos, winner)
    dev_inc = M3.tail_mass_deviation(pit_inc)
    dev_foil = M3.tail_mass_deviation(pit_foil)
    dev_win = M3.tail_mass_deviation(pit_win)
    calibration = {
        "tail_mass_delta_vs_foil": round(dev_foil - dev_win, 5),
        "dev_incumbent": round(dev_inc, 5), "dev_foil": round(dev_foil, 5),
        "dev_winner": round(dev_win, 5),
        "incumbent_pit": pit_inc, "foil_pit": pit_foil, "winner_pit": pit_win,
    }

    # ── declared-inactive clauses: proved zero for BOTH arm and foil (NF-D20 (g⁗)) ──
    wink = _metric_matrix(frs, pos, "winkler_80")
    for lab in (winner, foil):
        wink_delta = float((wink["incumbent"] - wink[lab]).mean())
        cov80_delta = float(np.mean([fr["scores"][pos]["incumbent"]["coverage_80"]
                                     - fr["scores"][pos][lab]["coverage_80"] for fr in frs]))
        cov95_delta = float(np.mean([fr["scores"][pos]["incumbent"]["coverage_95"]
                                     - fr["scores"][pos][lab]["coverage_95"] for fr in frs]))
        if max(abs(wink_delta), abs(cov80_delta), abs(cov95_delta)) > 1e-9:
            raise ValueError(
                f"{pos}/{lab}: a declared-inactive metric moved (winkler {wink_delta}, cov80 "
                f"{cov80_delta}, cov95 {cov95_delta}) — the construction is not tail-only; "
                f"harness bug")
    construction_facts = {
        "winkler_80_delta": 0.0, "coverage_80_delta": 0.0, "coverage_95_delta": 0.0,
        "note": ("IDENTICALLY ZERO BY CONSTRUCTION for BOTH arm and foil (within-grid identity "
                 "asserted every fold) — structurally INACTIVE clauses, recorded as facts, "
                 "never counted as passing gates (NF-D20 (g⁗))."),
    }

    cov_map = {m: {lab: round(float(np.mean([fr["scores"][pos][lab][m] for fr in frs])), 4)
                   for lab in (winner, foil, "incumbent", "over_ext_eq", "max_width")}
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
        "n_fold_positions_thin_hi": int(sum(fr["params_digest"][pos]["eq"]["thin_hi"]
                                            for fr in frs)),
        "n_fold_positions_thin_lo": int(sum(fr["params_digest"][pos]["eq"]["thin_lo"]
                                            for fr in frs)),
        "n_fold_levels_clamped_hi": int(sum(fr["params_digest"][pos]["eq"]["clamped_hi"]
                                            for fr in frs)),
        "n_fold_levels_clamped_lo": int(sum(fr["params_digest"][pos]["eq"]["clamped_lo"]
                                            for fr in frs)),
    }
    offsets_read = {
        "per_fold": [fr["params_digest"][pos]["offsets_vs_exponential"] for fr in frs],
        "note": ("report-only: the calibrated far-level offsets vs the foil's "
                 "exponential-implied t_exp = beta·ln(5) — the pre-registered under-extension "
                 "read, quantitative (§8 expectations)."),
    }

    fold_labels = [fr["label"] for fr in frs]
    cap = [i for i, lb in enumerate(fold_labels) if lb in CAPTURE_ERA_FOLDS]
    leg = [i for i, lb in enumerate(fold_labels) if lb not in CAPTURE_ERA_FOLDS]
    return {
        "position": pos, "winner": winner, "best_foil": foil,
        "registered_shippable": pos in M3.LIVE_POSITIONS,
        "selection_metric": M3.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        # ⭐ PBO is UNDEFINED BY DESIGN for a one-contrast field (GE.pbo_is_evaluable) — declared
        # in advance, never a gate (the NF-W4 Layer-B precedent, carried from NF-MARGIN2).
        "pbo": None,
        "pbo_state": ("UNDEFINED — CSCV resamples a FIELD; NF-MARGIN3 fields ONE pre-registered "
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
        "thin_tail_cells": thin_cells, "offsets_vs_exponential": offsets_read,
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 4) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 4) if leg else None),
            "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
        },
    }


# ── Verdict layer (derived, shared with --rewrite-report — the NF-W3/W5 rule) ───────────────────
def _classify_position(sel: dict, n_folds: int, checks: dict) -> dict:
    hand = M3.hand_classify_refusal_margin3(checks)
    if hand is not None:
        return hand
    # the instrument's verdict is RECORDED beside the hand classification, never discarded —
    # its n_arms=1 rendering is the known bug (NF-W3/NF-W4, 4th/5th occurrences).
    v = cv_power.classify_null(
        metric=f"nf_margin3_{sel['position']}_crps", n_folds=n_folds,
        n_arms=len(M3.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=M3.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    return M3.classify_layer_b(
        sel, n_folds=n_folds,
        instrument_verdict={"state": v.state, "reason": v.reason,
                            "retest_trigger": v.retest_trigger})


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored selections — no refit (NF-W2e one level up).
    Gates compose ONLY for the LIVE positions; RB/TE are REPORT_ONLY by registration."""
    n_folds = out["n_folds"]
    pvals = {f"margin3_tail_{p}": out["selections"][p]["p_one_sided"]
             for p in M3.LIVE_POSITIONS}
    fdr = {"family": M14.bh_fdr(pvals, q=M3.FDR_Q), "pvals": pvals,
           "note": ("ONE pre-registered family over the LIVE positions (QB, WR) — RB/TE are "
                    "report-only by registration and contribute no hypotheses")}
    gates, null_states, verdict = {}, {}, {}
    for p in M3.POSITIONS:
        sel = out["selections"][p]
        if p in M3.REPORT_ONLY_POSITIONS:
            verdict[p] = "REPORT_ONLY"
            continue
        gate = M3.compose_gate_margin3(sel, fdr["family"].get(f"margin3_tail_{p}", False))
        gates[p] = gate
        if gate["ship"]:
            verdict[p] = "SHIP"
        else:
            null_states[p] = _classify_position(sel, n_folds, gate["checks"])
            verdict[p] = null_states[p].get("state", "NULL")
    headline = (" ".join(f"{p}[{verdict[p]}]" for p in M3.LIVE_POSITIONS)
                + " · RB/TE report-only (tail_ext stands)")
    return {"fdr": fdr, "gates": gates, "null_states": null_states, "verdict": verdict,
            "headline": headline}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-MARGIN3 — a better QB/WR tail-magnitude estimator vs `tail_ext` (§0.5, 1-arm "
      "family)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis on the NF-W2d two-era "
      f"matrix) · **player-weeks:** {out['n_rows']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a "
      "clearing arm's serving path — attach the QB/WR tail offsets to the served bank, no "
      "refit, completing the tail fix at all four positions — is blocked on NF-C6 Ph2 + "
      "NF-G0). The successor NF-MARGIN2 named: a FRESH registration of a magnitude estimator "
      "that targets the refuted quantity directly (per-side empirical-quantile offsets "
      "calibrated on eval-end exceedance rates = the pooled pinball optimum per level). ⭐ THE "
      f"BAR IS `tail_ext`, not the incumbent. Selection metric `{M3.PRIMARY_METRIC}`; PIT "
      "accounting on the 199-level bank. PBO UNDEFINED by design; DSR = PSR at a 1-arm field. "
      "FAMILY = QB + WR; RB/TE report-only (registered non-shippable — `tail_ext` stands). "
      "Every direction word below is three-way and derived at report time, failing closed to "
      "`TIES` (NF-W2e).")
    p("")
    pa = out["pit_audit"]
    p(f"**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN3):** "
      f"{pa['game_groups_checked']} game-groups / {pa['records_checked']} records checked; "
      f"{pa['rows_dropped']} rows dropped fail-closed.")
    p("")
    p(f"**Verdict:** {out['headline']}")
    p("")
    p("## Construction facts (declared structurally INACTIVE — never counted as evidence)")
    p("")
    p("Within-grid identity asserted every fold for BOTH arm and foil: Winkler-80, "
      "coverage(50/80/95) deltas vs the incumbent are IDENTICALLY ZERO by construction; only "
      "8 of 199 eval columns (4/side beyond the champion grid) can differ between `eq_tail` "
      "and `tail_ext` — the contrast isolates the magnitude estimator and nothing else "
      "(NF-D20 (g⁗)).")
    p("")
    p("## Team-total re-check (independence copula, report-only — the NF-W5 loop)")
    p("")
    tt = out["team_total_pooled"]
    p(pd.DataFrame([{"label": k, **v} for k, v in tt.items()]).to_markdown(index=False))
    p("")
    for ra in out["reproduction_anchors"]["team_total"]:
        # ⚠️ an anchor that is UNEVALUABLE (smoke pooling ≠ the 8-fold record) must say so —
        # never print a false "NOT reproduced" alarm (NF1.7 (a), facing the report).
        word = ("n/a on a partial run (anchors are valid only on the full 8-fold pooling)"
                if not ra["evaluable"] else
                "REPRODUCED" if ra["reproduced"]
                else "⚠️ NOT reproduced (investigate before trusting cross-story comparability)")
        p(f"Reproduction anchor (report-only): {ra['label']} team-total coverage(80) measured "
          f"{ra['measured']} vs NF-MARGIN2's {ra['expected']} — {word} (tol "
          f"{M2_TEAM_TOTAL_TOL}).")
    p("")
    crps_ra = out["reproduction_anchors"]["mean_crps"]
    if crps_ra:
        misses = [r for r in crps_ra if not r["reproduced"]]
        p(f"Per-position mean-CRPS reproduction anchors vs the NF-MARGIN2 record (tol "
          f"{M2_MEAN_CRPS_TOL}, report-only): {len(crps_ra) - len(misses)}/{len(crps_ra)} "
          f"reproduced{'' if not misses else ' — ⚠️ MISSES: ' + str(misses)}.")
        p("")
    for pos in M3.POSITIONS:
        sel = out["selections"][pos]
        tag = out["verdict"][pos]
        p(f"## {pos} — **{tag}**"
          + (" (registered non-shippable — `tail_ext` stands here)"
             if pos in M3.REPORT_ONLY_POSITIONS else ""))
        p("")
        p(M3.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps_q199": v}
                        for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps_q199").to_markdown(index=False, floatfmt=".5f"))
        p("")
        bh = out["fdr"]["family"].get("margin3_tail_" + pos)
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} (UNDEFINED by design) · "
          f"DSR(=PSR, 1-arm) {sel['dsr']} · p {sel['p_one_sided']} · BH "
          f"{bh if pos in M3.LIVE_POSITIONS else 'n/a (out of family)'}")
        c = sel["calibration"]
        p(f"- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal {M3.NOMINAL_EXTREME}"
          f"/side, ⭐ vs the FOIL): dev foil {c['dev_foil']} → winner {c['dev_winner']} (delta "
          f"{c['tail_mass_delta_vs_foil']:+}) · incumbent dev {c['dev_incumbent']} "
          f"(continuity, report-only) · p_below_eval/p_above_eval foil "
          f"{c['foil_pit']['p_below_eval']}/{c['foil_pit']['p_above_eval']} → winner "
          f"{c['winner_pit']['p_below_eval']}/{c['winner_pit']['p_above_eval']}")
        p(f"- coverage (floor {M3.COVERAGE_FLOOR}, structurally inactive here): {sel['coverage']}"
          f" · map {sel['coverage_map']} · fingerprint {sel['tail_fingerprint']}")
        p(f"- attribution (pre-registered, report-only): {sel['attribution']}")
        p(f"- anchors: {sel['anchors']}")
        if not sel["anchors"]["over_ext_eq_loses"]:
            p("- ⚠️ **REFUTED CALIBRATED-OPTIMUM HYPOTHESIS (NF-D20):** `over_ext_eq` (offsets "
              f"× {M3.OVER_SCALE}, registered to lose) BEAT the calibrated arm — the metric "
              "optimum lies beyond the calibration pinball optimum, i.e. the shared-offset "
              "FAMILY (not the estimator) under-fits here. Recorded as a decomposed "
              "refutation; the anchor stays an anchor (⛔ never re-labelled).")
        p(f"- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {sel['oracle_detail']}")
        p(f"- permutation: {sel['permutation_detail']} · thin/clamped cells: "
          f"{sel['thin_tail_cells']}")
        p(f"- offsets vs the exponential (report-only, §8): "
          f"{sel['offsets_vs_exponential']['per_fold']}")
        p(f"- 📅 era note: {sel['era_note']}")
        if pos in M3.LIVE_POSITIONS:
            p(f"- gate: {out['gates'][pos]['checks']}")
        else:
            p("- gate: NOT COMPOSED — registered non-shippable (NF-D20 decision-shape: "
              "eligibility, not a threshold, separates this null from a ship; a win here is "
              "an out-of-family observation for a future registration).")
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
        "real_arms": list(M3.REAL_ARMS), "foils": list(M3.FOILS),
        "reference": list(M3.REFERENCE),
        "anchors": list(M3.anchors()), "eligible": M3.eligible_labels(),
        "live_positions": list(M3.LIVE_POSITIONS),
        "report_only_positions": list(M3.REPORT_ONLY_POSITIONS),
        "primary_metric": M3.PRIMARY_METRIC,
        "estimator": ("per-side empirical-quantile tail offsets calibrated on the eval-end "
                      "exceedance rates of the purged calibration slice — the pooled pinball "
                      "optimum at each beyond-grid eval level (GPD considered and declined at "
                      "design time; see the pre-registration §2)"),
        "the_bar": "tail_ext (the standing object; the incumbent is reference-only)",
        "pit_instrument": "randomized_pit_levels on the 199-level bank (NF-MARGIN2 verbatim)",
        "eval_levels": {"n": int(len(M3.EVAL_LEVELS)),
                        "lo": float(M3.EVAL_LEVELS[0]), "hi": float(M3.EVAL_LEVELS[-1])},
        "over_scale": M3.OVER_SCALE, "min_tail_n": M3.MIN_TAIL_N,
        "nominal_tail": M3.NOMINAL_TAIL,
        "cal_split": {"target_fraction": MC.CAL_TARGET_FRACTION, "min_rows": MC.CAL_MIN_ROWS,
                      "purge_weeks": M3.PURGE_WEEKS},
        "test_blocks": [list(t) for t in M3.TEST_BLOCKS],
        "pbo": "UNDEFINED by design (1-arm family — GE.pbo_is_evaluable)",
        "dsr_min": M3.DSR_MIN, "fdr_q": M3.FDR_Q,
        "fdr_family": list(M3.FDR_FAMILY),
        "coverage_floor": M3.COVERAGE_FLOOR,
        "declared_inactive_clauses": ["winkler_80", "coverage_50", "coverage_80", "coverage_95"],
        "tail_mass_gate": "vs the FOIL (tail_ext), beyond-EVAL-grid deviation, strict fall; "
                          "arm-movability proved at design time (guard-tested)",
        "team_total_samples": M3.TEAM_TOTAL_SAMPLES,
        "capture_era_folds": list(CAPTURE_ERA_FOLDS),
        "reproduction_anchors": {"team_total": M2_TEAM_TOTAL, "mean_crps": M2_MEAN_CRPS},
        "seed": M3._SEED,
    }


def _reproduction_anchors(out: dict) -> dict:
    """REPORT-ONLY cross-story anchors — meaningful only on the full 8-fold run (the smoke's
    2-fold means are a different pooling and are flagged as such, never compared)."""
    full_run = out["n_folds"] == len(M3.TEST_BLOCKS)
    tt = []
    for lab, expected in M2_TEAM_TOTAL.items():
        measured = out["team_total_pooled"].get(lab, {}).get("coverage_80")
        tt.append({"label": lab, "expected": expected, "measured": measured,
                   "evaluable": bool(full_run),
                   "reproduced": bool(full_run and measured is not None
                                      and abs(measured - expected) <= M2_TEAM_TOTAL_TOL)})
    crps = []
    if full_run:
        for lab, by_pos in M2_MEAN_CRPS.items():
            for pos, expected in by_pos.items():
                measured = out["selections"][pos]["mean_crps"].get(lab)
                crps.append({"label": lab, "position": pos, "expected": expected,
                             "measured": measured,
                             "reproduced": bool(measured is not None
                                                and abs(measured - expected)
                                                <= M2_MEAN_CRPS_TOL)})
    return {"team_total": tt, "mean_crps": crps,
            "note": ("REPORT-ONLY: the foil + reference are byte-identical constructions to "
                     "NF-MARGIN2's (the builder delegates), so on the full 8-fold run their "
                     "numbers must reproduce that record; valid only on the full run.")}


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-MARGIN3 tail-magnitude-estimator study")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_margin3_tail_estimator{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        out["reproduction_anchors"] = _reproduction_anchors(out)
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored selections without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_margin3_tail_estimator{suffix}.md")
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
    folds = W2.build_folds_w2(feat, M3.TEST_BLOCKS)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-MARGIN3: %d folds over %d player-weeks; field = %d arm + %d foil (+%d "
             "reference) + %d anchors; family = %s; 8 beyond-grid eval columns carry the whole "
             "contrast", n_folds, len(feat), len(M3.REAL_ARMS), len(M3.FOILS),
             len(M3.REFERENCE), len(M3.anchors()), list(M3.LIVE_POSITIONS))

    frs = [run_fold(f, feat) for f in folds]

    selections = {pos: select_position(frs, pos, n_folds) for pos in M3.POSITIONS}
    tt_pooled = {lab: M3.pool_team_total([fr["team_total"][lab] for fr in frs])
                 for lab in TEAM_TOTAL_LABELS}
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": M3.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": M3.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(sum(len(f.test_idx) for f in folds)),
        "pit_audit": pit_audit,
        "preregistration": preregistration_echo(),
        "selections": selections,
        "team_total_pooled": tt_pooled,
        "fold_results": [{k: fr[k] for k in ("label", "scores", "cal_note", "team_total",
                                             "params_digest", "exclusions",
                                             "runtime_seconds")} for fr in frs],
    }
    out.update(derive_verdict_layer(out))
    out["reproduction_anchors"] = _reproduction_anchors(out)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_margin3_tail_estimator{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "team_total_pooled": out["team_total_pooled"],
                      "reproduction_anchors": {
                          "team_total": out["reproduction_anchors"]["team_total"]},
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

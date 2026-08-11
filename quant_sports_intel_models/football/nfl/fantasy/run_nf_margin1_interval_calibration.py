"""run_nf_margin1_interval_calibration.py — NF-MARGIN1 §0.5 study: per-player interval/tail
calibration of the injury-aware `lgbm_hurdle` champion, per position.

MOTIVATION (NF-W5's diagnostic that outlives its null): the assembled champion's TEAM-TOTAL
predictive under-covers — coverage(80) 0.706 vs the 0.80 floor (n=2,174, ~11 binomial SE) —
under EVERY copula including the peeking oracles ⇒ a MARGINAL-SHAPE defect in the per-player
predictive, not missing correlation. The structural suspect is visible in the code: the champion
fits 9 quantile knots ending at 0.05/0.95 and extends them FLAT — no tail model at all.

TWO STAGES, ordered by the story card:
  1. DIAGNOSE (`--diagnose`): per-position randomized-PIT accounting of the champion's honest
     OOS predictive — decile flatness, beyond-grid tail mass (nominal 2.5%/side), Var(z),
     coverage at 4 central widths, the zero-atom check, and the team-total reproduction of the
     NF-W5 coverage number with its below-q10/above-q90 asymmetry.
  2. BAKE-OFF: 4 pre-registered recalibration classes + 2 foils + anchors (2 sharpness
     degenerates, a permutation map, ⭐ one peeking oracle per parametrized form at matched n).
     Selection on `crps_q199`; the story's two-sided calibration gate (Winkler-80 improves AND
     randomized-PIT flatness improves) sits beside the standard deflation battery. Coverage
     stays a FLOOR (NF1.8) — nothing fits or selects on |coverage − 0.80|.

Everything decidable in advance lives as a CONSTANT in `margin_calibration.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_margin1_preregistration.md` BEFORE the full run.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin1_interval_calibration --diagnose --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin1_interval_calibration --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin1_interval_calibration
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_margin1_interval_calibration --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
# ⭐ the matrix build, the champion bank, the two-family FDR composer, the incumbent pin and the
# capture-era fold list are IMPORTED from the stories that shipped them (NF-W2d discipline).
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate import (  # noqa: E402
    build_matrix_w2d,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment import (  # noqa: E402
    fdr_two_families,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff import (  # noqa: E402
    CAPTURE_ERA_FOLDS,
    assert_incumbents_match_the_w2d_artifact,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w5_opportunity_allocation import (  # noqa: E402
    champion_qmat,
)

log = logging.getLogger("nfl.fantasy.nf_margin1")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = (2016, 2025)

#: Labels whose randomized-PIT accounting is kept per fold (the eligible field — anchors are
#: excluded except through their scores).
PIT_LABELS: tuple[str, ...] = (*MC.REAL_ARMS, *MC.FOILS)


# ── Fold-level fitting ──────────────────────────────────────────────────────────────────────────
def _fold_rng(fold_label: str, stream: int) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence([MC._SEED, zlib.crc32(fold_label.encode()), stream]))


permute_within_pos_week = MC.permute_within_pos_week


def fit_position_params(pos: str, cal: pd.DataFrame, q_cal_sorted: np.ndarray,
                        u_cal: np.ndarray, u_cal_perm: np.ndarray,
                        test: pd.DataFrame, q_test_sorted: np.ndarray,
                        u_test: np.ndarray) -> dict:
    """Every construction's parameters for one position. Real arms + foils fit on the CAL slice
    (honest OOS PITs); oracles PEEK at the test fold's own PITs (NF-D16 (g‴)); matched-n refits
    each real form on the most recent min(n_test, n_cal) CAL rows (NF1.9 (f))."""
    cal_sel = (cal["position"] == pos).to_numpy()
    te_sel = (test["position"] == pos).to_numpy()
    y_cal = cal.loc[cal_sel, "fantasy_points"].to_numpy(dtype=float)
    y_te = test.loc[te_sel, "fantasy_points"].to_numpy(dtype=float)
    qc, qt = q_cal_sorted[cal_sel], q_test_sorted[te_sel]
    uc, ut = u_cal[cal_sel], u_test[te_sel]

    params: dict[str, object] = {"incumbent": None, "zero_width": None, "max_width": None,
                                 "pit_recal_global": MC.fit_recal_levels(u_cal),
                                 "permuted_recal": MC.fit_recal_levels(u_cal_perm[cal_sel])}
    for form in MC.REAL_ARMS:
        params[form] = MC.fit_form(form, uc, qc, y_cal)
        params[MC.oracle_of(form)] = MC.fit_form(form, ut, qt, y_te)
    params[MC.oracle_of("pit_recal_global")] = MC.fit_recal_levels(u_test)

    # matched-n capacity controls: the most recent min(n_test, n_cal) CAL rows of this position.
    order = np.argsort(cal.loc[cal_sel, "gw"].to_numpy())
    take = order[-min(len(y_te), len(y_cal)):]
    matched_note = {"n_cal": int(len(y_cal)), "n_test": int(len(y_te)),
                    "n_matched": int(len(take)),
                    "matched_equals_arm": bool(len(take) == len(y_cal))}
    for form in MC.REAL_ARMS:
        params[MC.matched_n_of(form)] = MC.fit_form(form, uc[take], qc[take], y_cal[take])
    params["_matched_note"] = matched_note
    return params


# ── One fold ────────────────────────────────────────────────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, *, diagnose_only: bool = False) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    y_te_all = test["fantasy_points"].to_numpy(dtype=float)
    champ_test_sorted = np.sort(champion_qmat(train, test), axis=1)
    u_test_all = MC.randomized_pit(champ_test_sorted, y_te_all, _fold_rng(fold.label, 3))
    groups, excl = OA.build_team_weeks(test, min_k=MC.MIN_TEAM_K)

    # ── diagnosis of the incumbent (always computed; the whole story in --diagnose mode) ──
    diagnosis: dict[str, dict] = {}
    inc_banks: dict[str, np.ndarray] = {}
    for pos in MC.POSITIONS:
        sel = (test["position"] == pos).to_numpy()
        bank = MC.build_eval_bank("incumbent", None, champ_test_sorted[sel])
        inc_banks[pos] = bank
        y = y_te_all[sel]
        atom_pred = float(np.mean((np.abs(bank) < 1e-12).mean(axis=1)))
        diagnosis[pos] = {"pit": MC.pit_stats(u_test_all[sel]),
                          "scores": MC.score_bank(bank, y),
                          "atom": {"predicted_p0_grid": round(atom_pred, 4),
                                   "realized_zero_share": round(float((y == 0.0).mean()), 4),
                                   "n": int(sel.sum())}}

    out: dict = {"label": fold.label, "exclusions": excl,
                 "runtime_seconds": None, "diagnosis": diagnosis}

    if diagnose_only:
        full_inc = np.empty((len(test), len(MC.EVAL_LEVELS)))
        for pos in MC.POSITIONS:
            full_inc[(test["position"] == pos).to_numpy()] = inc_banks[pos]
        out["team_total"] = {"incumbent": MC.team_total_check(groups, full_inc, y_te_all,
                                                              fold.label)}
        out["runtime_seconds"] = round(time.time() - t0, 1)
        log.info("[D] fold %s in %.1fs — per-position beyond-grid PIT mass (nominal 0.025/side): %s",
                 fold.label, out["runtime_seconds"],
                 {p: {"lo": round(d['pit']['n_below_grid'] / d['pit']['n'], 4),
                      "hi": round(d['pit']['n_above_grid'] / d['pit']['n'], 4)}
                  for p, d in diagnosis.items()})
        return out

    # ── calibration split + map fitting ──
    core, cal, cal_note = MC.calibration_split(train)
    champ_cal_sorted = np.sort(champion_qmat(core, cal), axis=1)
    y_cal_all = cal["fantasy_points"].to_numpy(dtype=float)
    u_cal_all = MC.randomized_pit(champ_cal_sorted, y_cal_all, _fold_rng(fold.label, 2))
    y_perm = permute_within_pos_week(cal, _fold_rng(fold.label, 5))
    u_cal_perm = MC.randomized_pit(champ_cal_sorted, y_perm, _fold_rng(fold.label, 6))

    params: dict[str, dict] = {}
    for pos in MC.POSITIONS:
        params[pos] = fit_position_params(pos, cal, champ_cal_sorted, u_cal_all, u_cal_perm,
                                          test, champ_test_sorted, u_test_all)

    # ── score every construction, per position; team totals for the eligible field ──
    scores: dict[str, dict[str, dict]] = {p: {} for p in MC.POSITIONS}
    pit: dict[str, dict[str, dict]] = {p: {} for p in MC.POSITIONS}
    team_total: dict[str, dict] = {}
    eligible = set(MC.eligible_labels())
    for label in MC.all_labels():
        full_bank = np.empty((len(test), len(MC.EVAL_LEVELS))) if label in eligible else None
        for pos in MC.POSITIONS:
            sel = (test["position"] == pos).to_numpy()
            bank = (inc_banks[pos] if label == "incumbent"
                    else MC.build_eval_bank(label, params[pos][label], champ_test_sorted[sel]))
            scores[pos][label] = MC.score_bank(bank, y_te_all[sel])
            if label in PIT_LABELS:
                rng = np.random.default_rng(np.random.SeedSequence(
                    [MC._SEED, zlib.crc32(f"{fold.label}|{label}|{pos}".encode()), 4]))
                pit[pos][label] = MC.pit_stats(
                    MC.randomized_pit(bank[:, MC.IDX_Q39], y_te_all[sel], rng))
            if full_bank is not None:
                full_bank[sel] = bank
        if full_bank is not None:
            team_total[label] = MC.team_total_check(groups, full_bank, y_te_all, fold.label)

    out.update({
        "cal_note": cal_note, "scores": scores, "pit": pit, "team_total": team_total,
        "params_digest": {
            pos: {"level_widen_w": params[pos]["level_widen"],
                  "zscore_affine": {k: round(v, 4)
                                    for k, v in params[pos]["zscore_affine"].items()},
                  "tail": {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in params[pos]["pit_recal_tail"]["tail"].items()},
                  "matched_note": params[pos]["_matched_note"]}
            for pos in MC.POSITIONS},
    })
    out["runtime_seconds"] = round(time.time() - t0, 1)
    log.info("[M] fold %s in %.1fs (%d test rows, %d team-weeks) — widen w: %s · tail beta_hi: %s",
             fold.label, out["runtime_seconds"], len(test), excl["n_groups"],
             {p: out['params_digest'][p]['level_widen_w'] for p in MC.POSITIONS},
             {p: out['params_digest'][p]['tail']['beta_hi'] for p in MC.POSITIONS})
    return out


# ── Selection per position ──────────────────────────────────────────────────────────────────────
def _metric_matrix(frs: list[dict], pos: str, metric: str = MC.PRIMARY_METRIC) -> pd.DataFrame:
    return pd.DataFrame({fr["label"]: {lab: fr["scores"][pos][lab][metric]
                                       for lab in fr["scores"][pos]} for fr in frs}).T


def _pooled_pit(frs: list[dict], pos: str, label: str) -> dict:
    return MC.pool_pit_stats([fr["pit"][pos][label] for fr in frs])


def _pooled_coverage(frs: list[dict], pos: str, label: str) -> dict:
    n = sum(fr["scores"][pos][label]["n"] for fr in frs)
    cov = (sum(fr["scores"][pos][label]["coverage_80"] * fr["scores"][pos][label]["n"]
               for fr in frs) / n) if n else float("nan")
    se = float(np.sqrt(MC.COVERAGE_FLOOR * (1 - MC.COVERAGE_FLOOR) / n)) if n else float("nan")
    return {"coverage_80": round(cov, 4), "n_rows": int(n), "binomial_se": round(se, 4),
            "blocking_shortfall": bool(n and (MC.COVERAGE_FLOOR - cov)
                                       > MC.COVERAGE_BLOCK_SE * se)}


def select_position(frs: list[dict], pos: str, n_folds: int) -> dict:
    crps = _metric_matrix(frs, pos)
    mean_crps = crps.mean(axis=0)
    arms = list(MC.REAL_ARMS)
    winner = str(mean_crps[arms].idxmin())
    best_foil = str(mean_crps[list(MC.FOILS)].idxmin())
    deltas = (crps[best_foil] - crps[winner]).to_numpy(dtype=float)
    mean_d, lo, hi = MC.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = MC.eligible_labels()
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (crps[best_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    perm_lift = (crps["incumbent"] - crps["permuted_recal"]).to_numpy(dtype=float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        # ⭐ NF1.8: the floor is proved a CONSTRAINT (not a criterion) by the degenerate
        # SATISFYING it while losing the primary — reported, never a ship condition.
        "max_width_satisfies_floor": not _pooled_coverage(frs, pos,
                                                          "max_width")["blocking_shortfall"],
        "winner_beats_permuted": bool(mean_crps["permuted_recal"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[a] > mean_crps[MC.oracle_of(a)] for a in arms)),
        # ⭐ THE GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n.
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_crps[a] > mean_crps[MC.oracle_of(a)])
            or (mean_crps[MC.oracle_of(a)] < mean_crps[MC.matched_n_of(a)])
            for a in arms)),
        "foil_respects_own_oracle": bool(
            mean_crps["pit_recal_global"] > mean_crps[MC.oracle_of("pit_recal_global")]),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_crps[a]), 5),
            "own_form_oracle": round(float(mean_crps[MC.oracle_of(a)]), 5),
            "matched_n": round(float(mean_crps[MC.matched_n_of(a)]), 5),
            "oracle_beats_matched_n": bool(mean_crps[MC.matched_n_of(a)]
                                           > mean_crps[MC.oracle_of(a)])}
        for a in arms
    }

    # ── the story's two-sided calibration gate, vs the INCUMBENT (not the best foil) ──
    wink = _metric_matrix(frs, pos, "winkler_80")
    winkler_delta = float((wink["incumbent"] - wink[winner]).mean())
    pit_inc = _pooled_pit(frs, pos, "incumbent")
    pit_win = _pooled_pit(frs, pos, winner)
    calibration = {
        "winkler_delta_vs_incumbent": round(winkler_delta, 5),
        "flatness_delta_vs_incumbent": round(pit_inc["max_decile_dev"]
                                             - pit_win["max_decile_dev"], 5),
        "incumbent_pit": pit_inc, "winner_pit": pit_win,
    }

    # ── the pre-registered tail-channel contrast (NF-D10 (g) attribution) ──
    d_tail = (crps["pit_recal_pos"] - crps["pit_recal_tail"]).to_numpy(dtype=float)
    tm, tlo, thi = MC.paired_ci95(d_tail)
    tail_channel = {
        "mean_delta": None if tm is None else round(tm, 5),
        "ci95": [None if tlo is None else round(tlo, 5), None if thi is None else round(thi, 5)],
        "fold_wins": int((d_tail > 0).sum()),
        "p_one_sided": M14.onesided_paired_pvalue(d_tail),
    }

    sd = float(np.nanstd(deltas, ddof=1))
    cov_map = {m: {lab: round(float(np.mean([fr["scores"][pos][lab][m] for fr in frs])), 4)
                   for lab in (winner, "incumbent", "max_width")}
               for m in ("coverage_50", "coverage_80", "coverage_95", "coverage_99")}

    fold_labels = [fr["label"] for fr in frs]
    cap = [i for i, lb in enumerate(fold_labels) if lb in CAPTURE_ERA_FOLDS]
    leg = [i for i, lb in enumerate(fold_labels) if lb not in CAPTURE_ERA_FOLDS]
    return {
        "position": pos, "winner": winner, "best_foil": best_foil,
        "selection_metric": MC.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "winkler_mean": {lab: round(float(wink[lab].mean()), 5)
                         for lab in (winner, "incumbent", "max_width", "zero_width")},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval, "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": (round(float(np.var(np.asarray(trial_srs), ddof=1)), 5)
                          if len(trial_srs) > 1 else None),
        "anchors": anchors, "oracle_detail": oracle_detail,
        "permutation_detail": {"permuted_lift_vs_incumbent_mean":
                               round(float(np.nanmean(perm_lift)), 5),
                               "permuted_lift_p_one_sided": p_perm},
        "calibration": calibration, "tail_channel": tail_channel,
        "coverage": _pooled_coverage(frs, pos, winner), "coverage_map": cov_map,
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 4) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 4) if leg else None),
            "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
        },
    }


# ── Verdict layer (derived, shared with --rewrite-report — the NF-W3/W5 rule) ───────────────────
def _classify_position(sel: dict, n_folds: int, checks: dict) -> dict:
    hand = MC.hand_classify_refusal_margin(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric=f"nf_margin1_{sel['position']}_crps", n_folds=n_folds,
        n_arms=len(MC.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=MC.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    return MC.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger},
        len(MC.REAL_ARMS))


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored selections — no refit (NF-W2e one level up)."""
    n_folds = out["n_folds"]
    arm_p = {f"margin_arm_{p}": out["selections"][p]["p_one_sided"] for p in MC.POSITIONS}
    tail_p = {f"margin_tail_{p}": out["selections"][p]["tail_channel"]["p_one_sided"]
              for p in MC.POSITIONS}
    fdr = fdr_two_families(arm_p, tail_p)
    gates, null_states, verdict = {}, {}, {}
    for p in MC.POSITIONS:
        sel = out["selections"][p]
        gate = MC.compose_gate_margin(sel, fdr["binding"].get(f"margin_arm_{p}", False))
        gates[p] = gate
        if gate["ship"]:
            verdict[p] = "SHIP"
        else:
            null_states[p] = _classify_position(sel, n_folds, gate["checks"])
            verdict[p] = null_states[p].get("state", "NULL")
    headline = " ".join(f"{p}[{verdict[p]}]" for p in MC.POSITIONS)
    return {"fdr": fdr, "gates": gates, "null_states": null_states, "verdict": verdict,
            "headline": headline}


# ── Pooled diagnosis assembly ───────────────────────────────────────────────────────────────────
def pool_diagnosis(frs: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for pos in MC.POSITIONS:
        pit = MC.pool_pit_stats([fr["diagnosis"][pos]["pit"] for fr in frs])
        n = sum(fr["diagnosis"][pos]["scores"]["n"] for fr in frs)
        cov = {m: round(sum(fr["diagnosis"][pos]["scores"][m]
                            * fr["diagnosis"][pos]["scores"]["n"] for fr in frs) / n, 4)
               for m in ("coverage_50", "coverage_80", "coverage_95", "coverage_99")}
        atom_n = sum(fr["diagnosis"][pos]["atom"]["n"] for fr in frs)
        atom = {
            "predicted_p0_grid": round(sum(fr["diagnosis"][pos]["atom"]["predicted_p0_grid"]
                                           * fr["diagnosis"][pos]["atom"]["n"]
                                           for fr in frs) / atom_n, 4),
            "realized_zero_share": round(sum(fr["diagnosis"][pos]["atom"]["realized_zero_share"]
                                             * fr["diagnosis"][pos]["atom"]["n"]
                                             for fr in frs) / atom_n, 4)}
        out[pos] = {"pit": pit, "coverage": cov, "atom": atom, "n_rows": int(n)}
    return out


# ── Reports ─────────────────────────────────────────────────────────────────────────────────────
def _diag_table(diag: dict) -> pd.DataFrame:
    rows = []
    for pos, d in diag.items():
        rows.append({
            "position": pos, "n": d["n_rows"],
            "p_below_grid": d["pit"]["p_below_grid"], "p_above_grid": d["pit"]["p_above_grid"],
            "max_decile_dev": d["pit"]["max_decile_dev"], "var_z": d["pit"]["var_z"],
            "cov_50": d["coverage"]["coverage_50"], "cov_80": d["coverage"]["coverage_80"],
            "cov_95": d["coverage"]["coverage_95"], "cov_99": d["coverage"]["coverage_99"],
            "pred_p0": d["atom"]["predicted_p0_grid"],
            "zero_share": d["atom"]["realized_zero_share"],
        })
    return pd.DataFrame(rows)


def write_diagnosis_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-MARGIN1 — diagnosis: WHERE the champion's per-player predictive is miscalibrated")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} "
      f"({', '.join(out['fold_labels'])}) · **player-weeks:** {out['n_rows']}")
    p("")
    p("> Motivation: NF-W5's team-total coverage(80) 0.706 vs the 0.80 floor under every copula "
      "⇒ a marginal-shape defect. Nominal beyond-grid PIT mass is 0.025/side (the champion's "
      "39-level grid ends at 0.025/0.975, themselves FLAT extensions of the 0.05/0.95 knots).")
    p("")
    p(_diag_table(out["diagnosis"]).to_markdown(index=False))
    p("")
    p("## PIT decile frequencies (nominal 0.1 each)")
    p("")
    p(pd.DataFrame({pos: d["pit"]["decile_freq"] for pos, d in out["diagnosis"].items()},
                   index=[f"{i / 10:.1f}–{(i + 1) / 10:.1f}" for i in range(10)]).to_markdown())
    p("")
    if "team_total" in out:
        p("## Team-total (independence copula, the NF-W5 machinery verbatim)")
        p("")
        p(json.dumps(out["team_total"], indent=2))
        p("")
    path.write_text("\n".join(a))


def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-MARGIN1 — per-player interval/tail calibration of the hurdle champion "
      "(§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis on the NF-W2d two-era "
      f"matrix) · **player-weeks:** {out['n_rows']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a "
      "clearing arm's retrain/promote path is blocked on NF-C6 Ph2 + NF-G0). Selection metric "
      f"is `{MC.PRIMARY_METRIC}` (199-level pinball CRPS — the grid the tail fix is VISIBLE on); "
      "Winkler-80 + randomized-PIT flatness form the story's two-sided calibration gate; "
      "coverage stays a FLOOR (NF1.8). Every direction word below is three-way and **derived "
      "from the interval at report time**, failing closed to `TIES` (NF-W2e).")
    p("")
    pa = out["pit_audit"]
    p(f"**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN1):** "
      f"{pa['game_groups_checked']} game-groups / {pa['records_checked']} records checked; "
      f"{pa['rows_dropped']} rows dropped fail-closed.")
    p("")
    p(f"**Verdict:** {out['headline']}")
    p("")
    p("## The diagnosis (motivating measurement: NF-W5 team-total coverage(80) 0.706, ~11 SE "
      "below the floor)")
    p("")
    p(_diag_table(out["diagnosis"]).to_markdown(index=False))
    p("")
    p("## Team-total re-check (independence copula, report-only — the loop closed)")
    p("")
    tt = out["team_total_pooled"]
    p(pd.DataFrame([{"label": k, **v} for k, v in tt.items()]).to_markdown(index=False))
    p("")
    for pos in MC.POSITIONS:
        sel = out["selections"][pos]
        p(f"## {pos} — **{out['verdict'][pos]}**")
        p("")
        p(MC.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps_q199": v}
                        for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps_q199").to_markdown(index=False, floatfmt=".5f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · BH binding "
          f"{out['fdr']['binding'].get('margin_arm_' + pos)}")
        p(f"- calibration gate: Winkler-80 delta vs incumbent {sel['calibration']['winkler_delta_vs_incumbent']:+.4f} "
          f"(incumbent {sel['winkler_mean']['incumbent']} → winner "
          f"{sel['winkler_mean'][sel['winner']]}) · PIT max-decile-dev "
          f"{sel['calibration']['incumbent_pit']['max_decile_dev']} → "
          f"{sel['calibration']['winner_pit']['max_decile_dev']}")
        p(f"- coverage (floor {MC.COVERAGE_FLOOR}, never a target): {sel['coverage']} · map "
          f"{sel['coverage_map']}")
        p(f"- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): "
          f"{sel['tail_channel']} · BH binding "
          f"{out['fdr']['binding'].get('margin_tail_' + pos)}")
        p(f"- anchors: {sel['anchors']}")
        p(f"- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): "
          f"{sel['oracle_detail']}")
        p(f"- permutation: {sel['permutation_detail']}")
        p(f"- 📅 era note: {sel['era_note']}")
        p(f"- gate: {out['gates'][pos]['checks']}")
        ns = out["null_states"].get(pos, {})
        if ns.get("field_shrink_flag"):
            f = ns["field_shrink_flag"]
            p(f"- ⚠️ **field-shrink remedy is {f['status']}** — {f['note']}")
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
        "real_arms": list(MC.REAL_ARMS), "foils": list(MC.FOILS),
        "anchors": list(MC.anchors()), "eligible": MC.eligible_labels(),
        "parametrized_forms": list(MC.PARAMETRIZED_FORMS),
        "primary_metric": MC.PRIMARY_METRIC, "co_metrics": list(MC.CO_METRICS),
        "eval_levels": {"n": int(len(MC.EVAL_LEVELS)),
                        "lo": float(MC.EVAL_LEVELS[0]), "hi": float(MC.EVAL_LEVELS[-1])},
        "widen_grid": list(MC.WIDEN_GRID), "max_width_scale": MC.MAX_WIDTH_SCALE,
        "min_tail_n": MC.MIN_TAIL_N,
        "cal_split": {"target_fraction": MC.CAL_TARGET_FRACTION, "min_rows": MC.CAL_MIN_ROWS,
                      "purge_weeks": MC.PURGE_WEEKS},
        "test_blocks": [list(t) for t in MC.TEST_BLOCKS],
        "pbo_max": MC.PBO_MAX, "dsr_min": MC.DSR_MIN, "fdr_q": MC.FDR_Q,
        "fdr_families": {k: list(v) for k, v in MC.FDR_FAMILIES.items()},
        "coverage_floor": MC.COVERAGE_FLOOR,
        "team_total_samples": MC.TEAM_TOTAL_SAMPLES,
        "capture_era_folds": list(CAPTURE_ERA_FOLDS),
        "seed": MC._SEED,
    }


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-MARGIN1 interval/tail calibration study")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--diagnose", action="store_true",
                    help="diagnosis only — no arms, artifacts nf_margin1_diagnosis*")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_margin1_interval_calibration{suffix}.json"

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
        write_report(out, _REPORT_DIR / f"nf_margin1_interval_calibration{suffix}.md")
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
    folds = W2.build_folds_w2(feat, MC.TEST_BLOCKS)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-MARGIN1%s: %d folds over %d player-weeks; field = %d arms + %d foils + %d "
             "anchors; eval grid %d levels",
             " (diagnose)" if args.diagnose else "", n_folds, len(feat), len(MC.REAL_ARMS),
             len(MC.FOILS), len(MC.anchors()), len(MC.EVAL_LEVELS))

    frs = [run_fold(f, feat, diagnose_only=args.diagnose) for f in folds]

    if args.diagnose:
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "story": MC.STORY, "smoke": bool(args.smoke), "mode": "diagnose",
            "runtime_seconds": round(time.time() - t_start, 1),
            "n_folds": n_folds, "fold_labels": [f.label for f in folds],
            "n_rows": int(sum(len(f.test_idx) for f in folds)),
            "pit_audit": pit_audit,
            "diagnosis": pool_diagnosis(frs),
            "team_total": {"incumbent":
                           MC.pool_team_total([fr["team_total"]["incumbent"] for fr in frs])},
            "fold_results": [{k: fr[k] for k in ("label", "diagnosis", "team_total",
                                                 "exclusions", "runtime_seconds")}
                             for fr in frs],
        }
        dj = _REPORT_DIR / f"nf_margin1_diagnosis{suffix}.json"
        dj.write_text(json.dumps(out, indent=2, default=float))
        write_diagnosis_report(out, _REPORT_DIR / f"nf_margin1_diagnosis{suffix}.md")
        log.info("diagnosis written (%.1fs): team-total incumbent %s",
                 out["runtime_seconds"], out["team_total"]["incumbent"])
        print(json.dumps({"diagnosis": {p: {"p_below_grid": d["pit"]["p_below_grid"],
                                            "p_above_grid": d["pit"]["p_above_grid"],
                                            "var_z": d["pit"]["var_z"],
                                            "coverage": d["coverage"]}
                                        for p, d in out["diagnosis"].items()},
                          "team_total": out["team_total"],
                          "runtime_seconds": out["runtime_seconds"]}, indent=2))
        return 0

    selections = {pos: select_position(frs, pos, n_folds) for pos in MC.POSITIONS}
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": MC.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": MC.PRIMARY_METRIC, "co_metrics": list(MC.CO_METRICS),
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(sum(len(f.test_idx) for f in folds)),
        "pit_audit": pit_audit,
        "preregistration": preregistration_echo(),
        "diagnosis": pool_diagnosis(frs),
        "selections": selections,
        "team_total_pooled": {lab: MC.pool_team_total([fr["team_total"][lab] for fr in frs])
                              for lab in MC.eligible_labels()},
        "fold_results": [{k: fr[k] for k in ("label", "scores", "cal_note", "team_total",
                                             "params_digest", "exclusions",
                                             "runtime_seconds")} for fr in frs],
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_margin1_interval_calibration{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "team_total_pooled": out["team_total_pooled"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

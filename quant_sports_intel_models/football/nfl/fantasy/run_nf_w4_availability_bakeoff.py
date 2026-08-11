"""run_nf_w4_availability_bakeoff.py — NF-W4 §0.5 bake-off: the availability & playing-time
mixture (P(active) × P(plays | active) × snap/usage share), and ⭐ the gate that decides whether
it is worth anything — does injecting the PROJECTED availability into the assembled player
projection beat the INJURY-AWARE champion (the NF-W2b/W2d certified per-position winners) on
held-out weeks?

Everything decidable in advance lives as a CONSTANT in `availability_mixture.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w4_preregistration.md` BEFORE the full run.

PIPELINE
  MATRIX: the NF-W2d two-era matrix (NF-W1 engineering + injury_report + injury_rate across the
  nflverse-stamp era ≤2024 and the wayback-capture era 2025), through the W2d assembly boundary —
  provenance + the NF-W0a PIT gate with source-aware provenance shapes. NF-W4 introduces NO new
  source; ⭐ the injury family is CONSUMED, never re-derived.

  LAYER A (player-week, the component grain): two targets — `played` (the zero-atom generator;
  scored by the exact Bernoulli CRPS, the dense-grid limit of `crps_q39`) and `snap_share`
  (conditional on played, measured-only, exclusions counted; `crps_q39`). 4 arms + 2 climatology
  foils + anchors (incl. ONE PEEKING ORACLE PER ARM'S OWN FORM) per target.

  LAYER B (player-week — THE GATE): `champion_inj` (the per-position NF-W2d certified incumbent,
  refit per fold) vs `champion_avail` (the identical estimator + the availability block from the
  Layer-A winners, produced EXPANDING-WINDOW inside the training span so a train row's block is
  out-of-sample for the availability model too), with three anchors: `champion_avail_foil` (block
  from the climatology+designation foil — the matched foil-availability arm),
  `champion_avail_shuffled` (block permuted across players within position×week) and
  ⭐ `champion_avail_oracle` (REALIZED played + measured share substituted — the peeking upper
  bound on the whole availability channel, SCORED AND LOGGED FIRST, per position, every run).

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import availability_mixture as AV  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
# ⭐ the matrix build, the per-position player reducer and the two-family FDR composer are
# IMPORTED from the stories that shipped them, never re-implemented (NF-W2d discipline).
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (  # noqa: E402
    score_qmat,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate import (  # noqa: E402
    build_matrix_w2d,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment import (  # noqa: E402
    fdr_two_families,
)

log = logging.getLogger("nfl.fantasy.nf_w4")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_W2D_ARTIFACT = _REPORT_DIR / "nf_w2d_2025_regate.json"
SEASONS = (2016, 2025)

#: The 2025 as-of-capture folds — reported SEPARATELY for lift sizing (NF-W2d/W2e: quote the
#: capture era, not the legacy stamp era). Report-only; never a gate.
CAPTURE_ERA_FOLDS: tuple[str, ...] = ("2025H1", "2025H2")


def _form_suffix(incumbent_form: str) -> str:
    return {"inj_zero_leg": "zero_leg", "inj_both": "both"}[incumbent_form]


def assert_incumbents_match_the_w2d_artifact() -> None:
    """The Layer-B foil spec must be what the W2d gates actually certified — pinned to the
    committed artifact (MH2.1 (b): serve/register the object that was validated). Skipped
    loudly (never silently) if the artifact is absent in a fresh worktree."""
    if not _W2D_ARTIFACT.exists():
        raise FileNotFoundError(
            f"{_W2D_ARTIFACT.name} not found — the Layer-B incumbent spec cannot be verified "
            f"against the certified W2d winners; refusing to run against an unpinned foil"
        )
    art = json.loads(_W2D_ARTIFACT.read_text())
    winners = {pos: art["positions"][pos]["winner"] for pos in WP.POSITIONS}
    if winners != AV.INCUMBENT_OF_POSITION:
        raise ValueError(
            f"INCUMBENT_OF_POSITION {AV.INCUMBENT_OF_POSITION} does not match the W2d-certified "
            f"winners {winners} — the foil must be the validated object, not a remembered one"
        )


# ── Layer A: one fold, target `played` ──────────────────────────────────────────────────────────
def run_layer_a_fold_t1(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    t0 = time.time()
    y = test["_t_played"].to_numpy(dtype=float)
    feats = list(AV.AVAIL_FEATURES)

    pos_rate = AV.train_pos_played_rate(train)
    class_p, fallbacks = AV.fit_class_p_t1(train)
    probs: dict[str, np.ndarray] = {
        "foil_clim": AV.foil_point_t1(test, pos_rate),
        "foil_clim_inj": AV.foil_point_t1_inj(test, pos_rate, class_p),
        "nihilist_zero": np.zeros(len(test)),
        "marginal_train": test["position"].map(pos_rate).astype(float).to_numpy(),
    }
    for arm in AV.REAL_ARMS["played"]:
        fit = AV.T1_PROB_FITTERS[arm]
        probs[arm] = AV.assert_finite_p(fit(train, test, feats), arm)
        # NF-D16 (g‴): the peeking ceiling of THIS arm's OWN form (fit ON the test block).
        probs[AV.oracle_of(arm)] = AV.assert_finite_p(fit(test, test, feats), AV.oracle_of(arm))
        # NF1.9 (f): the same form at the oracle's sample scale — the capacity control.
        probs[AV.matched_n_of(arm)] = AV.assert_finite_p(
            fit(AV.matched_n_train(train, test), test, feats), AV.matched_n_of(arm))
    # the foils' own-form oracles: the climatology re-fit on the TEST block (peeking).
    te_rate = AV.train_pos_played_rate(test)
    te_class_p, _ = AV.fit_class_p_t1(test)
    probs[AV.oracle_of("foil_clim")] = AV.foil_point_t1(test, te_rate)
    probs[AV.oracle_of("foil_clim_inj")] = AV.foil_point_t1_inj(test, te_rate, te_class_p)
    # permutation anchor — pre-registered on the plain boosting class, target shuffled within
    # position × global week in TRAIN.
    probs["permuted_within"] = AV.assert_finite_p(
        AV.fit_t1_lgbm(train, test, feats,
                       y_train=AV.permute_within_pos_week(
                           train, train["_t_played"].to_numpy(float))),
        "permuted_within")

    scores: dict[str, dict] = {}
    for label, p in probs.items():
        c = AV.crps_bernoulli(p, y)
        med = (np.asarray(p, float) > 0.5).astype(float)
        scores[label] = {"crps": float(np.mean(c)),
                         "mae_report_only": float(np.mean(np.abs(y - med)))}
    # the sharpness degenerates in their OWN closed forms (the same CRPS functional)
    scores["zero_width"] = {"crps": float(np.mean(AV.crps_point(probs["foil_clim"], y))),
                            "mae_report_only": float(np.mean(np.abs(y - probs["foil_clim"])))}
    scores["max_width"] = {"crps": AV.CRPS_UNIFORM01,
                           "mae_report_only": float(np.mean(np.abs(y - 0.5)))}
    coverage = {k: AV.t1_interval_coverage(probs[k], y)
                for k in (*AV.REAL_ARMS["played"], *AV.FOILS)}
    log.info("[A/played] fold %s in %.1fs (train %d / test %d; class-cell fallbacks %s)",
             fold.label, time.time() - t0, len(train), len(test), fallbacks or "none")
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "class_cell_fallbacks": fallbacks,
            "n_train": int(len(train)), "n_test": int(len(test))}


# ── Layer A: one fold, target `snap_share` ──────────────────────────────────────────────────────
def run_layer_a_fold_t2(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    t0 = time.time()
    tr = train.loc[AV.t2_mask(train)]
    te = test.loc[AV.t2_mask(test)]
    excl = AV.t2_exclusion_counts(test)
    y = te["_t_share"].to_numpy(dtype=float)
    feats = list(AV.AVAIL_FEATURES)

    pos_share = AV.train_pos_share(tr)
    mult, fallbacks = AV.fit_class_mult_t2(tr)
    foil_pt = AV.foil_point_t2(te, pos_share)
    foil_pt_inj = AV.foil_point_t2_inj(te, pos_share, mult)
    bank = AV.residual_bank_t2(tr["_t_share"].to_numpy(float), AV.foil_point_t2(tr, pos_share))
    bank_inj = AV.residual_bank_t2(tr["_t_share"].to_numpy(float),
                                   AV.foil_point_t2_inj(tr, pos_share, mult))

    qmats: dict[str, np.ndarray] = {
        "foil_clim": AV.apply_bank_t2(foil_pt, bank),
        "foil_clim_inj": AV.apply_bank_t2(foil_pt_inj, bank_inj),
        "nihilist_zero": np.zeros((len(te), len(AV.Q_LEVELS))),
        "zero_width": np.repeat(foil_pt[:, None], len(AV.Q_LEVELS), axis=1),
        "max_width": AV.apply_bank_t2(foil_pt, bank * 3.0),
    }
    marg = np.full((len(te), len(AV.Q_LEVELS)), np.nan)
    for pos in WP.POSITIONS:
        sel = (te["position"] == pos).to_numpy()
        src = tr.loc[tr["position"] == pos, "_t_share"]
        if sel.any():
            base = src if len(src) else tr["_t_share"]
            marg[sel] = np.quantile(base.to_numpy(float), AV.Q_LEVELS)[None, :]
    qmats["marginal_train"] = marg

    for arm in AV.REAL_ARMS["snap_share"]:
        fit = AV.T2_QMAT_FITTERS[arm]
        qmats[arm] = fit(tr, te, feats)
        qmats[AV.oracle_of(arm)] = fit(te, te, feats)
        qmats[AV.matched_n_of(arm)] = fit(AV.matched_n_train(tr, te), te, feats)
    te_share = AV.train_pos_share(te)
    te_mult, _ = AV.fit_class_mult_t2(te)
    pt_o = AV.foil_point_t2(te, te_share)
    pt_oi = AV.foil_point_t2_inj(te, te_share, te_mult)
    qmats[AV.oracle_of("foil_clim")] = AV.apply_bank_t2(
        pt_o, AV.residual_bank_t2(y, pt_o))
    qmats[AV.oracle_of("foil_clim_inj")] = AV.apply_bank_t2(
        pt_oi, AV.residual_bank_t2(y, pt_oi))
    qmats["permuted_within"] = AV.fit_t2_lgbm_quantile(
        tr, te, feats,
        y_train=AV.permute_within_pos_week(tr, tr["_t_share"].to_numpy(float)))

    scores: dict[str, dict] = {}
    for label, m in qmats.items():
        AV.assert_finite_predictive(m, label)
        c = WP.crps_from_quantiles(m, y)
        med = np.sort(m, axis=1)[:, len(AV.Q_LEVELS) // 2]
        scores[label] = {"crps": float(np.mean(c)),
                         "mae_report_only": float(np.mean(np.abs(y - med)))}
    coverage = {k: WP.interval_coverage(qmats[k], y)
                for k in (*AV.REAL_ARMS["snap_share"], *AV.FOILS)}
    log.info("[A/snap_share] fold %s in %.1fs (fit %d / scored %d; %d played-unmeasured "
             "excluded; mult fallbacks %s)", fold.label, time.time() - t0, len(tr), len(te),
             excl["n_played_unmeasured_excluded"], fallbacks or "none")
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "exclusions": excl, "class_cell_fallbacks": fallbacks,
            "n_train": int(len(tr)), "n_test": int(len(te))}


# ── Layer A selection (mirrors NF-W3's; AV constants; GE gate composer reused) ──────────────────
def select_layer_a(target: str, fold_results: list[dict], n_folds: int) -> dict:
    crps = pd.DataFrame({fr["label"]: {k: fr["scores"][k]["crps"] for k in fr["scores"]}
                         for fr in fold_results}).T
    mean_crps = crps.mean(axis=0)
    arms = list(AV.REAL_ARMS[target])
    winner = str(mean_crps[arms].idxmin())
    best_foil = str(mean_crps[list(AV.FOILS)].idxmin())
    deltas = (crps[best_foil] - crps[winner]).to_numpy(float)
    mean_d, lo, hi = AV.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = AV.eligible_labels(target)
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (crps[best_foil] - crps[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    perm_lift = (crps[best_foil] - crps["permuted_within"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "marginal_loses": bool(mean_crps["marginal_train"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps["permuted_within"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # NF-D16 (g‴) per-form floors; ⭐ STRICT reading reported, NOT the gate:
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[a] > mean_crps[AV.oracle_of(a)] for a in arms)),
        # ⭐ THE GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n.
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_crps[a] > mean_crps[AV.oracle_of(a)])
            or (mean_crps[AV.oracle_of(a)] < mean_crps[AV.matched_n_of(a)])
            for a in arms)),
        "foils_respect_own_oracle": bool(all(
            mean_crps[f] > mean_crps[AV.oracle_of(f)] for f in AV.FOILS)),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_crps[a]), 5),
            "own_form_oracle": round(float(mean_crps[AV.oracle_of(a)]), 5),
            "matched_n": round(float(mean_crps[AV.matched_n_of(a)]), 5),
            "oracle_beats_matched_n": bool(mean_crps[AV.matched_n_of(a)]
                                           > mean_crps[AV.oracle_of(a)])}
        for a in arms
    }

    covs = [fr["coverage"][winner] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(AV.COVERAGE_FLOOR * (1 - AV.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")

    sd = float(np.nanstd(deltas, ddof=1))
    sel = {
        "target": target, "winner": winner, "best_foil": best_foil,
        "selection_metric": (AV.T1_SELECTION_METRIC if target == "played"
                             else AV.SELECTION_METRIC),
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "mean_mae_report_only": {
            k: round(float(np.mean([fr["scores"][k]["mae_report_only"] for fr in fold_results])), 5)
            for k in (winner, best_foil, "nihilist_zero", "marginal_train")},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
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
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 5),
                               "permuted_lift_p_one_sided": p_perm},
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (AV.COVERAGE_FLOOR - cov)
                                                > AV.COVERAGE_BLOCK_SE * se),
                     # NF-D20: T1's floor is STRUCTURALLY NEAR-INACTIVE (two-point band) —
                     # recorded, never credited as a pass.
                     "structurally_inactive": bool(target == "played")},
        "class_cell_fallbacks": sorted({fb for fr in fold_results
                                        for fb in fr.get("class_cell_fallbacks", [])}),
    }
    if target == "snap_share":
        sel["exclusions_total"] = {
            k: int(sum(fr["exclusions"][k] for fr in fold_results))
            for k in ("n_rows", "n_played", "n_scored", "n_played_unmeasured_excluded")}
    return sel


# ── Layer B: availability into the injury-aware champion ────────────────────────────────────────
def run_layer_b_fold(fold: WP.Fold, feat: pd.DataFrame, forms: dict[str, str]) -> dict:
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    t0 = time.time()
    proj = AV.avail_projection_frame(feat, fold, forms)
    proj_foil = AV.avail_projection_frame(feat, fold, AV.FOIL_FORMS)
    frames = {
        "avail": AV.attach_avail_features(feat, proj),
        "avail_foil": AV.attach_avail_features(feat, proj_foil),
        "avail_shuffled": AV.attach_avail_features(feat, proj, shuffle_seed=AV._SEED),
        "avail_oracle": AV.attach_avail_features(feat, proj, realized=True),
    }
    AV.assert_feature_provenance_w4(AV.AVAIL_PROJ_FEATURES)
    scope = np.concatenate([fold.train_idx, fold.test_idx])
    block_coverage = AV.assert_avail_block_attached(frames, scope, fold.label)

    full_feats = list(W2D.FEATURES_W2D)
    rate_feats = list(W2D.FEATURES_BASE_RATE_W2D)
    afull = full_feats + list(AV.AVAIL_PROJ_FEATURES)
    arate = rate_feats + list(AV.AVAIL_PROJ_FEATURES)

    qmats: dict[str, np.ndarray] = {}
    p0_full, cond_full = W2.hurdle_parts(train, test, full_feats, full_feats)
    _, cond_rate = W2.hurdle_parts(train, test, full_feats, rate_feats)
    qmats["inj_both"] = W2.mix_parts(p0_full, cond_full)
    qmats["inj_zero_leg"] = W2.mix_parts(p0_full, cond_rate)
    for v, frame in frames.items():
        tr, te = frame.loc[fold.train_idx], frame.loc[fold.test_idx]
        p0v, cfullv = W2.hurdle_parts(tr, te, afull, afull)
        _, cratev = W2.hurdle_parts(tr, te, afull, arate)
        qmats[f"{v}_both"] = W2.mix_parts(p0v, cfullv)
        qmats[f"{v}_zero_leg"] = W2.mix_parts(p0v, cratev)

    scores, coverage = {}, {}
    for label, m in qmats.items():
        AV.assert_finite_predictive(m, label)
        scores[label] = score_qmat(m, test)
        coverage[label] = {p: WP.interval_coverage(
            m[(test["position"] == p).to_numpy()],
            test.loc[test["position"] == p, "fantasy_points"].to_numpy(dtype=float))
            for p in WP.POSITIONS}
    # ⭐ ORACLE FIRST (NF-W3's discipline): the realized-availability ceiling is logged per
    # position BEFORE any arm is judged — it bounds the whole channel from above.
    ceiling = {
        pos: round(scores[AV.INCUMBENT_OF_POSITION[pos]][pos]
                   - scores[f"avail_oracle_{_form_suffix(AV.INCUMBENT_OF_POSITION[pos])}"][pos], 4)
        for pos in WP.POSITIONS
    }
    log.info("[B] fold %s in %.1fs — ⭐ realized-availability ORACLE ceiling (CRPS the champion "
             "leaves on the table): %s", fold.label, time.time() - t0, ceiling)
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "block_coverage": block_coverage, "oracle_ceiling_by_pos": ceiling}


def select_layer_b(pos: str, fold_results: list[dict], n_folds: int) -> dict:
    form = AV.INCUMBENT_OF_POSITION[pos]
    sfx = _form_suffix(form)
    foil, winner = form, f"avail_{sfx}"
    shuffled, oracle, avail_foil = (f"avail_shuffled_{sfx}", f"avail_oracle_{sfx}",
                                    f"avail_foil_{sfx}")
    crps = pd.DataFrame({fr["label"]: {k: fr["scores"][k][pos] for k in fr["scores"]}
                         for fr in fold_results}).T
    mean_crps = crps.mean(axis=0)
    deltas = (crps[foil] - crps[winner]).to_numpy(float)
    mean_d, lo, hi = AV.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    sd = float(np.nanstd(deltas, ddof=1))
    sr = float(np.nanmean(deltas)) / sd if sd > 1e-12 else None
    dsr = M14.deflated_sharpe(deltas, np.asarray([sr if sr is not None else 0.0]))
    pval = M14.onesided_paired_pvalue(deltas)

    shuf_lift = (crps[foil] - crps[shuffled]).to_numpy(float)
    p_shuf = M14.onesided_paired_pvalue(shuf_lift)
    oracle_d = (crps[foil] - crps[oracle]).to_numpy(float)
    o_mean, o_lo, o_hi = AV.paired_ci95(oracle_d)
    foilav_d = (crps[foil] - crps[avail_foil]).to_numpy(float)
    f_mean, f_lo, f_hi = AV.paired_ci95(foilav_d)

    anchors = {
        "winner_beats_shuffled": bool(mean_crps[shuffled] > mean_crps[winner]),
        # ⛔ fails CLOSED on an unevaluable p (NF1.7 (a))
        "shuffled_lift_not_significant": bool(
            float(np.nanmean(shuf_lift)) <= 0 or (p_shuf is not None and p_shuf >= 0.05)),
        "respects_realized_oracle": bool(mean_crps[winner] >= mean_crps[oracle]),
    }
    covs = [fr["coverage"][winner][pos] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(AV.COVERAGE_FLOOR * (1 - AV.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")

    fold_labels = [fr["label"] for fr in fold_results]
    capture_idx = [i for i, lbl in enumerate(fold_labels) if lbl in CAPTURE_ERA_FOLDS]
    legacy_idx = [i for i, lbl in enumerate(fold_labels) if lbl not in CAPTURE_ERA_FOLDS]
    era_note = {
        "capture_folds": [fold_labels[i] for i in capture_idx],
        "capture_mean_delta": (round(float(np.mean(deltas[capture_idx])), 4)
                               if capture_idx else None),
        "legacy_mean_delta": (round(float(np.mean(deltas[legacy_idx])), 4)
                              if legacy_idx else None),
        "note": ("REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): "
                 "forward-looking lift sizing quotes the capture era (NF-W2d/W2e)."),
    }

    return {
        "position": pos, "winner": "champion_avail", "best_foil": AV.LAYER_B_FOIL,
        "incumbent_form": form,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        # ⭐ PBO is UNDEFINED BY DESIGN for a one-contrast field — declared in advance, never a
        # gate (the NF-W3 mis-specification, not repeated).
        "pbo": None,
        "pbo_state": ("UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered "
                      "contrast, so there was no search to overfit. Declared before the run; "
                      "deliberately NOT a gate."),
        "dsr": dsr, "p_one_sided": pval,
        "observed_sr": None if sr is None else round(sr, 3),
        "var_trials_sr": None,
        "anchors": anchors,
        "oracle_ceiling": {"mean_delta": None if o_mean is None else round(o_mean, 4),
                           "ci95": [None if o_lo is None else round(o_lo, 4),
                                    None if o_hi is None else round(o_hi, 4)],
                           "fold_wins": int((oracle_d > 0).sum())},
        "foil_avail_anchor": {"mean_delta": None if f_mean is None else round(f_mean, 4),
                              "ci95": [None if f_lo is None else round(f_lo, 4),
                                       None if f_hi is None else round(f_hi, 4)]},
        "shuffle_detail": {"shuffled_lift_mean": round(float(np.nanmean(shuf_lift)), 4),
                           "shuffled_lift_p_one_sided": p_shuf},
        "era_note": era_note,
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (AV.COVERAGE_FLOOR - cov)
                                                > AV.COVERAGE_BLOCK_SE * se)},
    }


# ── Verdict layer (derived, shared with --rewrite-report — NF-W2e one level up) ─────────────────
def _classify_layer_a(key: str, sel: dict, n_folds: int, n_arms: int, checks: dict) -> dict:
    hand = AV.hand_classify_refusal(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric=key, n_folds=n_folds, n_arms=n_arms, beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=AV.FDR_Q,
        # factual provenance: anchors/degenerates never enter trial_srs (MH2.1 (a)).
        degenerates_excluded_from_v=True,
    )
    return AV.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger}, n_arms)


def _classify_layer_b(pos: str, sel: dict, n_folds: int, checks: dict) -> dict:
    hand = AV.hand_classify_layer_b_refusal(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric=f"nf_w4_downstream_crps_{pos}", n_folds=n_folds,
        n_arms=len(AV.LAYER_B_REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=AV.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    out = AV.classify_layer_b(
        sel, n_folds=n_folds,
        instrument_verdict={"state": v.state, "reason": v.reason,
                            "retest_trigger": v.retest_trigger})
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored selections — no refit (NF-W2e one level up:
    the VERDICT, not just its sentence, must be re-derivable without a re-run)."""
    n_folds = out["n_folds"]
    component_p = {t: out["layer_a"][t]["p_one_sided"] for t in out["targets"]}
    downstream_p = {p: out["layer_b"][p]["p_one_sided"] for p in out.get("layer_b", {})}
    fdr = fdr_two_families(component_p, downstream_p)

    gates_a = {t: AV.compose_gate(out["layer_a"][t], fdr["binding"].get(t, False))
               for t in out["targets"]}
    gates_b = {p: AV.layer_b_gate_w4(out["layer_b"][p], fdr["binding"].get(p, False))
               for p in out.get("layer_b", {})}

    null_states: dict[str, dict] = {}
    for t in out["targets"]:
        if not gates_a[t]["ship"]:
            null_states[f"layer_a::{t}"] = _classify_layer_a(
                f"nf_w4_{t}_crps", out["layer_a"][t], n_folds,
                len(AV.REAL_ARMS[t]), gates_a[t]["checks"])
    for p in out.get("layer_b", {}):
        if not gates_b[p]["ship"]:
            null_states[f"layer_b::{p}"] = _classify_layer_b(
                p, out["layer_b"][p], n_folds, gates_b[p]["checks"])

    verdict = {
        "layer_a": {t: ("SHIP" if gates_a[t]["ship"]
                        else null_states.get(f"layer_a::{t}", {}).get("state", "NULL"))
                    for t in out["targets"]},
        "layer_b": {p: ("SHIP" if gates_b[p]["ship"]
                        else null_states.get(f"layer_b::{p}", {}).get("state", "NULL"))
                    for p in out.get("layer_b", {})},
    }
    headline = ("A[" + " ".join(f"{t}:{v}" for t, v in verdict["layer_a"].items()) + "] "
                "B[" + " ".join(f"{p}:{v}" for p, v in verdict["layer_b"].items()) + "]")
    return {"fdr": fdr, "gates_a": gates_a, "gates_b": gates_b,
            "null_states": null_states, "verdict": verdict, "headline": headline}


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W4 — availability & playing-time: the availability mixture (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis on the NF-W2d two-era "
      f"matrix) · **player-weeks:** {out['n_rows']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving "
      "is NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`; T1 in exact Bernoulli closed "
      "form — the dense-grid limit of the same identity); MAE is reported and NEVER selects. "
      "Every direction word below is three-way and **derived from the interval at report time**, "
      "failing closed to `TIES` (NF-W2e).")
    p("")
    pa = out["pit_audit"]
    p(f"**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W4):** "
      f"{pa['game_groups_checked']} game-groups / {pa['records_checked']} records "
      f"({pa['injury_records_checked']} injury, {pa['rate_records_checked']} rate, "
      f"{pa['wayback_records_checked']} wayback-provenance) checked; {pa['rows_dropped']} rows "
      f"dropped fail-closed.")
    p("")
    p("## ⭐ Oracle first — the realized-availability ceiling")
    p("")
    p("Scored BEFORE any arm is judged (NF-W3's transferable discipline): the peeking "
      "substitution of the target week's realized played indicator + measured snap share into "
      "the injury-aware champion. This bounds the whole availability channel from above.")
    p("")
    lb = out.get("layer_b") or {}
    if lb:
        rows = []
        for pos in WP.POSITIONS:
            oc = lb[pos]["oracle_ceiling"]
            champ = lb[pos]["mean_crps"][lb[pos]["incumbent_form"]]
            rows.append({
                "position": pos,
                "champion_crps": champ,
                "oracle_ceiling_delta": oc["mean_delta"],
                "ceiling_pct_of_champion": (None if oc["mean_delta"] is None or not champ
                                            else round(100 * oc["mean_delta"] / champ, 2)),
                "ceiling_ci95": str(oc["ci95"]), "fold_wins": f"{oc['fold_wins']}/{out['n_folds']}",
            })
        p(pd.DataFrame(rows).to_markdown(index=False))
        p("")
    p("## ⭐ Headline")
    p("")
    p(f"- **Layer A (does the availability component beat its own climatology?)** — "
      + " · ".join(f"{t}: **{out['verdict']['layer_a'][t]}**" for t in out["targets"]))
    p(f"- **Layer B (does PROJECTED availability improve the assembled projection vs the "
      f"INJURY-AWARE champion?)** — "
      + (" · ".join(f"{pos}: **{lb_v}**" for pos, lb_v in out["verdict"]["layer_b"].items())
         if out["verdict"].get("layer_b")
         else "**NOT RUN** (`--skip-layer-b`) — ⛔ a run without Layer B is a development "
              "artifact, never a verdict."))
    p("")
    p("## Layer A — the component bake-offs")
    p("")
    for t in out["targets"]:
        sel, gate = out["layer_a"][t], out["gates_a"][t]
        p(f"### `{t}` — **{out['verdict']['layer_a'][t]}** (metric `{sel['selection_metric']}`)")
        p("")
        p(AV.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps": v} for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps").to_markdown(index=False, floatfmt=".5f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · BH own-family {out['fdr']['own_family'].get(t)} / pooled "
          f"{out['fdr']['pooled'].get(t)} (binding {out['fdr']['binding'].get(t)})")
        p(f"- anchors: {sel['anchors']}")
        p(f"- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): "
          f"{sel['oracle_detail']}")
        p(f"- permutation: {sel['permutation_detail']} · coverage(80) {sel['coverage']}"
          + (" ⚠️ T1's coverage clause is STRUCTURALLY NEAR-INACTIVE (two-point band) — "
             "recorded, never credited (NF-D20)." if t == "played" else ""))
        if sel.get("exclusions_total"):
            p(f"- T2 population (⛔ no fillna(0) — NF-W0b): {sel['exclusions_total']} — "
              f"played-but-unmeasured rows are EXCLUDED AND COUNTED, never imputed.")
        if sel.get("class_cell_fallbacks"):
            p(f"- ⚠️ foil designation-lookup cells thinner than {AV.MIN_CELL} fell back to "
              f"climatology (counted, loud — NF1.7 (a)): {sel['class_cell_fallbacks']}")
        p(f"- MAE (report-only, never selects): {sel['mean_mae_report_only']}")
        p(f"- gate: {gate['checks']}")
        nsa = out["null_states"].get(f"layer_a::{t}", {})
        if nsa.get("field_shrink_flag"):
            f = nsa["field_shrink_flag"]
            p(f"- ⚠️ **field-shrink remedy is {f['status']}** — {f['note']}")
        p("")
    p("## ⭐ Layer B — the gate: does projected availability move the PLAYER projection?")
    p("")
    p(f"Availability forms carried into Layer B (the Layer-A winners): `{out['avail_forms']}` · "
      f"matched-foil forms: `{AV.FOIL_FORMS}` · incumbent per position: "
      f"`{AV.INCUMBENT_OF_POSITION}` (pinned to the committed NF-W2d artifact).")
    p("")
    if not lb:
        p("**NOT RUN** in this invocation (`--skip-layer-b`).")
        p("")
    for pos in (WP.POSITIONS if lb else ()):
        sel, gate = out["layer_b"][pos], out["gates_b"][pos]
        p(f"### {pos} — **{out['verdict']['layer_b'][pos]}** (incumbent `{sel['incumbent_form']}`)")
        p("")
        p(AV.verdict_sentence("champion_avail", "champion_inj", sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps": v} for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        oc = sel["oracle_ceiling"]
        p(f"- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): "
          + AV.verdict_sentence("champion_avail_oracle", "champion_inj", oc["mean_delta"],
                                oc["ci95"][0], oc["ci95"][1])
          + f", {oc['fold_wins']}/{out['n_folds']} folds. This bounds what the availability "
            f"chain can buy at the player level over the injury-aware champion.")
        fe = sel["foil_avail_anchor"]
        p(f"- matched foil-availability anchor (block from the climatology+designation foil — "
          f"attributes any lift to the LEARNED component): "
          + AV.verdict_sentence("champion_avail_foil", "champion_inj", fe["mean_delta"],
                                fe["ci95"][0], fe["ci95"][1]))
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} ({sel['pbo_state'][:24]}…) · "
          f"DSR {sel['dsr']} · p {sel['p_one_sided']} · BH own-family "
          f"{out['fdr']['own_family'].get(pos)} / pooled {out['fdr']['pooled'].get(pos)} "
          f"(binding {out['fdr']['binding'].get(pos)})")
        p(f"- anchors {sel['anchors']} · shuffle {sel['shuffle_detail']} · "
          f"coverage(80) {sel['coverage']}")
        p(f"- 📅 era note (lift sizing — NF-W2d/W2e): {sel['era_note']}")
        p(f"- gate: {gate['checks']}")
        ns = out["null_states"].get(f"layer_b::{pos}", {})
        if ns.get("hand_corrected"):
            p(f"- 🩹 **hand-corrected classification** (the classify_null field-size gap, third "
              f"instance in this vertical): instrument said `{ns['instrument_verdict']['state']}`; "
              f"corrected state **{ns['state']}** — {ns['reason']} Re-test trigger: "
              f"{ns['retest_trigger']}")
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


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W4 availability-mixture bake-off + product gate")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--skip-layer-b", action="store_true",
                    help="Layer A only (development aid — a run without Layer B is NOT a verdict)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w4_availability_bakeoff{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: {p: (before.get(k, {}).get(p), v) for p, v in out["verdict"][k].items()
                     if before.get(k, {}).get(p) != v} for k in out["verdict"]}
        moved = {k: v for k, v in moved.items() if v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored selections without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w4_availability_bakeoff{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    assert_incumbents_match_the_w2d_artifact()
    feat, pit_audit, _store_raw = build_matrix_w2d(SEASONS, rebuild_cache=args.rebuild_cache)
    feat = AV.attach_availability_targets(feat)
    AV.assert_feature_provenance_w4(AV.AVAIL_FEATURES)
    folds = W2.build_folds_w2(feat, AV.TEST_BLOCKS)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-W4: %d folds over %d player-weeks (matrix = the NF-W2d two-era build)",
             n_folds, len(feat))

    layer_a: dict[str, dict] = {}
    a_folds: dict[str, list] = {}
    runners = {"played": run_layer_a_fold_t1, "snap_share": run_layer_a_fold_t2}
    for target in AV.TARGETS:
        frs = [runners[target](f, feat) for f in folds]
        a_folds[target] = [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")}
                           for fr in frs]
        layer_a[target] = select_layer_a(target, frs, n_folds)

    avail_forms = {t: layer_a[t]["winner"] for t in AV.TARGETS}
    log.info("Layer-A winners → availability forms for Layer B: %s", avail_forms)

    layer_b: dict[str, dict] = {}
    b_folds: list[dict] = []
    if not args.skip_layer_b:
        frs = [run_layer_b_fold(f, feat, avail_forms) for f in folds]
        b_folds = [{"label": fr["label"], "scores": fr["scores"],
                    "oracle_ceiling_by_pos": fr["oracle_ceiling_by_pos"]} for fr in frs]
        for pos in WP.POSITIONS:
            layer_b[pos] = select_layer_b(pos, frs, n_folds)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": AV.STORY, "smoke": bool(args.smoke), "skip_layer_b": bool(args.skip_layer_b),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": AV.SELECTION_METRIC,
        "t1_selection_metric": AV.T1_SELECTION_METRIC,
        "targets": list(AV.TARGETS), "n_folds": n_folds,
        "fold_labels": [f.label for f in folds],
        "n_rows": int(len(feat)),
        "pit_audit": pit_audit, "avail_forms": avail_forms,
        "preregistration": {
            "real_arms": {t: list(v) for t, v in AV.REAL_ARMS.items()},
            "foils": list(AV.FOILS),
            "anchors": {t: list(AV.anchors_for(t)) for t in AV.TARGETS},
            "eligible": {t: AV.eligible_labels(t) for t in AV.TARGETS},
            "layer_b_eligible": list(AV.LAYER_B_ELIGIBLE),
            "layer_b_anchors": list(AV.LAYER_B_ANCHORS),
            "incumbent_of_position": dict(AV.INCUMBENT_OF_POSITION),
            "foil_forms": dict(AV.FOIL_FORMS),
            "test_blocks": [list(t) for t in AV.TEST_BLOCKS], "purge_weeks": AV.PURGE_WEEKS,
            "pbo_max": AV.PBO_MAX, "dsr_min": AV.DSR_MIN, "fdr_q": AV.FDR_Q,
            "fdr_families": {k: list(v) for k, v in AV.FDR_FAMILIES.items()},
            "coverage_floor": AV.COVERAGE_FLOOR,
            "eb_kappa_avail": AV.EB_KAPPA_AVAIL, "min_cell": AV.MIN_CELL,
            "inj_gate_classes_t1": list(AV.INJ_GATE_CLASSES_T1),
            "inj_mult_classes_t2": list(AV.INJ_MULT_CLASSES_T2),
            "share_mult_clip": list(AV.SHARE_MULT_CLIP),
            "avail_features": list(AV.AVAIL_FEATURES),
            "avail_proj_features": list(AV.AVAIL_PROJ_FEATURES),
            "oracle_substituted": list(AV.ORACLE_SUBSTITUTED),
            "banned_feature_tokens": list(AV.BANNED_FEATURE_TOKENS),
            "target_leak_tokens": list(AV.TARGET_LEAK_TOKENS) + list(AV.TARGET_LEAK_EXACT),
            "capture_era_folds": list(CAPTURE_ERA_FOLDS),
        },
        "layer_a": layer_a, "layer_b": layer_b,
        "fold_results_a": a_folds, "fold_results_b": b_folds,
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w4_availability_bakeoff{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

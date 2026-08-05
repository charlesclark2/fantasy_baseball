"""run_nf_d16_point_recalibration.py — NF-D16 §0.5 bake-off: a per-position LEVEL recalibration of the
rookie POINT projection (RB/TE/WR; QB excluded), pre-registered as its OWN hypothesis.

THE STORY IN ONE PARAGRAPH. NF1.4 DOCUMENTED a cold rookie-point bias and never corrected it. NF-D14
corroborated that there is something cold to correct but explained its own lift with the wrong
mechanism. NF-D15's matched foil refuted that mechanism — the availability lift is PER-PLAYER — and
separately observed that a per-position CONSTANT recalibration beat the incumbent at all three scaled
positions. That observation was the best of 33 arms chosen AFTER seeing the field, undeflated, and
never registered as its own hypothesis. NF-D16 asks the same question CLEANLY: ≥3 pre-registered
correction FORMS plus a direct-learned foil plus the incumbent NULL, one PRE-REGISTERED framing chosen
before the run, two-sided anchors, and deflation.

🚨 **THE MOTIVATION IS NOT THE RESULT.** NF-D15's observed numbers are cited ONCE — in
`rookie_point_recalibration`'s module docstring, labelled as prior motivation — and never again. If
the clean pre-registration makes the effect shrink, **the shrinkage IS the answer** (E2.1-r).

────────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS PRE-REGISTERED, AND WHERE IT IS WRITTEN DOWN
────────────────────────────────────────────────────────────────────────────────────────────────────
Everything that could otherwise be chosen after seeing a result lives as a CONSTANT in
`rookie_point_recalibration.py`, and this runner READS it rather than restating it:
  · `PREREGISTERED_FRAMING = "pooled"` + `FRAMING_REASON` — one hypothesis, one test, no BH penalty,
    because a LEVEL effect is a-priori common across positions and the ship unit is the whole
    per-position constant vector. The per-position reading is computed as a DISCLOSURE (§3d).
  · `PREREGISTERED_DSR_READING = "whole_field"` — named in advance so the deflation statistic cannot
    be chosen after seeing which reading is kinder (NF-D14/NF-D15 were both bitten by this).
  · `DSR_MIN = 0.95` — the STRICTER of the two available bars, because this hypothesis was surfaced by
    re-reading NF-D15's field. The sensitivity at NF1.4's 0.0 and with the DSR dropped is reported.
  · The four FORMS, the shrink grid, the physical clips, and the anchor set.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. No `best_alpha`, no CLV/ROI claim.
🔒 The rookie INTERVAL's WIDTH model is untouched — NF-D14 settled that question. ⚠️ A shipped LEVEL
   change does move the band's CENTRE (the band is pasted around the point), so a ship requires
   `run_interval_revalidation` to be re-run and every coverage floor re-confirmed.
⛔ QB is excluded by pre-registration and PROVEN untouched on emitted projections, not asserted.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached NF1.4 rookie pool):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d16_point_recalibration
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    rookie_point_recalibration as RC,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_d16_point_recalibration")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_REAL = "rookie_fp_ppr"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-fold fits — computed ONCE per held-out class and shared by every arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cols(frame: pd.DataFrame) -> tuple:
    pos = frame["position_group"].astype(str).str.upper().to_numpy()
    tiers = RC.slot_tier(frame["draft_overall"])
    return pos, tiers


def fold_fits(fold: NF17.Fold, *, seed: int = 20260802) -> dict:
    """Every fitted correction for ONE held-out class, computed once and shared by every arm.

    §0.5 cost hygiene, but more importantly the guarantee that two arms differing only in λ really do
    differ only in λ: the fit is done once and the shrink is applied afterwards.

    ⭐ EVERY FIT IS STRICTLY IN-FOLD — on the prior draft classes' rows and their served point
    projections. The one exception is `_peek`, which is the ORACLE anchor and is fitted on the HELD-OUT
    class on purpose: it is the CEILING of the constant family, and a ceiling has to peek to be one.

    ⚠️ The permutation anchors are fitted at the canonical prescribed form (`mult_const`) and BOTH
    directions are computed:
      · `_perm_across` shuffles realized outcomes ACROSS positions, destroying the per-position level
        structure while preserving the family, the n and the grand mean. This is the anchor that must
        LOSE.
      · `_perm_within` shuffles WITHIN each position, which preserves that position's MARGINAL
        distribution — and a level IS a marginal statistic, so this anchor is EXPECTED to tie. Saying
        so in advance and then measuring it is the point: a permutation test is near-vacuous against a
        level hypothesis, which is a property of the hypothesis rather than a defect in the anchor
        (NF1.9: a mechanism that cannot act is a finding, not an omission)."""
    tr_pos, tr_tiers = _cols(fold.train)
    te_pos, te_tiers = _cols(fold.test)
    p_tr = np.asarray(fold.train_pred, dtype=float)
    y_tr = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)

    rng = np.random.default_rng(seed + int(fold.year))
    y_across = rng.permutation(np.nan_to_num(y_tr, nan=0.0))
    y_within = np.nan_to_num(y_tr, nan=0.0).copy()
    for q in RC.RECALIBRATED_POSITIONS:
        sel = np.flatnonzero(tr_pos == q)
        if len(sel) > 1:
            y_within[sel] = rng.permutation(y_within[sel])

    return {
        "mult_const": RC.fit_mult_const(p_tr, y_tr, tr_pos),
        "add_offset": RC.fit_add_offset(p_tr, y_tr, tr_pos),
        "mult_tier": RC.fit_mult_tier(p_tr, y_tr, tr_pos, tr_tiers),
        "ols_slope": RC.fit_ols(p_tr, y_tr, tr_pos),
        # anchors — ⭐ A PEEKING CEILING PER FORM, fitted on the HELD-OUT class with that form's OWN
        #            estimator. One ceiling for the whole field would be mis-specified: `mult_tier`
        #            and `ols_slope` each CONTAIN the per-position constant as a special case, so
        #            either could legitimately beat the best constant (NF1.7 (b) / NF1.9 (f)).
        "_peek": RC.fit_mult_const(fold.test_pred, fold.test_real, te_pos),
        "_peek_add": RC.fit_add_offset(fold.test_pred, fold.test_real, te_pos),
        "_peek_tier": RC.fit_mult_tier(fold.test_pred, fold.test_real, te_pos, te_tiers,
                                       min_cell=3),
        "_peek_ols": RC.fit_ols(fold.test_pred, fold.test_real, te_pos, min_n=5),
        "_perm_across": RC.fit_mult_const(p_tr, y_across, tr_pos),
        "_perm_within": RC.fit_mult_const(p_tr, y_within, tr_pos),
        # the EXACT-invariance proof for the additive form (see `permutation_invariance_proof`)
        "_perm_within_add": RC.fit_add_offset(p_tr, y_within, tr_pos),
        "_te_pos": te_pos, "_te_tiers": te_tiers,
    }


def arm_prediction(cfg: dict, fits: dict, fold: NF17.Fold) -> np.ndarray:
    """One arm's emitted projection for one held-out class: FIT → λ blend → the QB gate. Three separate
    steps on purpose, so no form owns its own copy of the shrink or of the exclusion."""
    pos, tiers = fits["_te_pos"], fits["_te_tiers"]
    if cfg["form"] == "incumbent":
        return RC.apply_position_adjustment(fold.test_pred, pos, fold.test_pred)
    adj = RC.predict_form(cfg["form"], fits[cfg["form"]], fold.test_pred, pos, tiers)
    blended = RC.blend_toward_incumbent(fold.test_pred, adj, cfg["lam"])
    return RC.apply_position_adjustment(fold.test_pred, pos, blended)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mean(values, nd: int = 4) -> float | None:
    v = np.array([x for x in values if x is not None], dtype=float)
    v = v[np.isfinite(v)]
    return round(float(v.mean()), nd) if len(v) else None


def _score(folds: list[NF17.Fold], fits: dict[int, dict], pos_scale: dict[int, dict],
           predict, label: str, extra: dict | None = None) -> dict:
    """Score ANY arm — candidate or anchor — through the IDENTICAL reducer, so the anchors and the
    candidates are demonstrably answering the same question rather than merely being described that
    way. `predict(fold, fits)` returns the emitted projection for that held-out class."""
    per_cohort, per_cohort_scaled, rows = {}, {}, []
    for f in folds:
        pos = fits[f.year]["_te_pos"]
        pred = predict(f, fits[f.year])
        d = pd.DataFrame({"position_group": pos, _REAL: f.test_real,
                          "_inc": f.test_pred, "_pred": pred})
        per_cohort[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year])
        per_cohort_scaled[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year],
                                                       tier_k=RC.SCALED_TIER_K)
        rows.append(d.assign(year=f.year))
    allrows = pd.concat(rows, ignore_index=True)
    scaled = RC.scaled_positions_only(allrows)
    pooled = _mean([v.get("tier_mae") for v in per_cohort_scaled.values()], 4)
    out = {
        "label": label, "per_cohort": per_cohort,
        "per_cohort_pooled": {y: v.get("tier_mae") for y, v in per_cohort_scaled.items()},
        "pooled_tier_mae": pooled, RC.SELECTION_METRIC: pooled,
        "universe_mae": round(float((scaled["_pred"] - scaled[_REAL]).abs().mean()), 3),
        "universe_bias": round(float((scaled["_pred"] - scaled[_REAL]).mean()), 3),
        **(extra or {}),
    }
    for p in ("QB",) + RC.RECALIBRATED_POSITIONS:
        g = allrows[allrows["position_group"] == p]
        if g.empty:
            continue
        out[f"universe_mae_{p}"] = round(float((g["_pred"] - g[_REAL]).abs().mean()), 2)
        out[f"tier_mae_{p}"] = _mean([v.get("tier_mae_by_pos", {}).get(p)
                                      for v in per_cohort.values()], 3)
        out[f"tier_bias_{p}"] = _mean([v.get("tier_bias_by_pos", {}).get(p)
                                       for v in per_cohort.values()], 3)
        out[f"rho_{p}"] = _mean([v.get("rho_by_pos", {}).get(p) for v in per_cohort.values()], 4)
    return out


def score_arms(folds, fits, pos_scale, cfgs: list[dict]) -> list[dict]:
    return [_score(folds, fits, pos_scale,
                   lambda f, fi, c=c: arm_prediction(c, fi, f), c["label"],
                   extra={"key": RC.config_key(c),
                          **{k: c[k] for k in ("form", "lam", "recalibrates", "shippable")},
                          "monotone": bool(c.get("monotone")), "learned": bool(c.get("learned"))})
            for c in cfgs]


# The peeking ceiling for each FORM: (form, the fold-fits key holding its held-out-class parameters).
# Keyed by the anchor names `RC.FAMILY_CEILING` maps each form to, so the anchor set and the check
# cannot drift apart.
_CEILING_ANCHORS = {"oracle_posconst": ("mult_const", "_peek"),
                    "oracle_addoffset": ("add_offset", "_peek_add"),
                    "oracle_tierconst": ("mult_tier", "_peek_tier"),
                    "oracle_ols": ("ols_slope", "_peek_ols")}
assert set(_CEILING_ANCHORS) == set(RC.FAMILY_CEILING.values()), \
    "the peeking-ceiling anchors and RC.FAMILY_CEILING have drifted apart"


def _anchor_prediction(tag: str, fold: NF17.Fold, fits: dict) -> np.ndarray:
    pos, tiers = fits["_te_pos"], fits["_te_tiers"]
    point = np.asarray(fold.test_pred, dtype=float)
    real = np.asarray(fold.test_real, dtype=float)
    if tag == "oracle_perplayer":
        # PEEKS at full resolution. Scores ~0 on an MAE-type metric; nothing may beat it. A DIRECTION
        # check for an accidentally-inverted metric (E2.1-r's oracle floor in its weak form for a
        # metric that is monotone in accuracy).
        return RC.apply_position_adjustment(point, pos, real)
    if tag in _CEILING_ANCHORS:
        # ⭐ ONE PEEKING CEILING PER FORM — each fitted on the HELD-OUT class with that form's OWN
        #    estimator, so every arm is floored at MATCHED family AND matched resolution. An in-fold
        #    arm beating its own form's peeking fit IS a metric inversion; beating a DIFFERENT,
        #    COARSER form's is merely a capacity effect, and conflating the two is the NF1.7 (b) error
        #    this story's first cut made.
        form, key = _CEILING_ANCHORS[tag]
        return RC.apply_position_adjustment(
            point, pos, RC.predict_form(form, fits[key], point, pos, tiers))
    if tag in ("permuted_across", "permuted_within"):
        key = "_perm_across" if tag == "permuted_across" else "_perm_within"
        return RC.apply_position_adjustment(
            point, pos, RC.predict_form("mult_const", fits[key], point, pos))
    if tag == "zero_scale":
        return RC.apply_position_adjustment(point, pos, np.zeros(len(pos)))
    if tag == "pos_median":
        # NF1.4's MAE-COLLAPSE TELL: the in-fold position median for everyone. MAE is minimised at the
        # conditional median, so this is the arm that WINS an inverted metric — and it is the right
        # degenerate for a LEVEL story specifically, being the extreme of "throw away every per-player
        # distinction", which is exactly what a level correction must NOT do.
        tr_pos = fold.train["position_group"].astype(str).str.upper().to_numpy()
        tr_real = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)
        adj = np.full(len(pos), np.nan)
        for q in RC.RECALIBRATED_POSITIONS:
            v = tr_real[(tr_pos == q) & np.isfinite(tr_real)]
            if len(v):
                adj[pos == q] = float(np.median(v))
        return RC.apply_position_adjustment(point, pos, adj)
    raise ValueError(f"unknown anchor {tag!r}")


def score_anchors(folds, fits, pos_scale) -> dict:
    """The REQUIRED anchor set, scored through the SAME reducer the candidates use, both DIRECTIONS,
    and every one of them READ rather than reasoned about."""
    return {t: _score(folds, fits, pos_scale,
                      lambda f, fi, t=t: _anchor_prediction(t, f, fi), t)
            for t in (("oracle_perplayer",) + tuple(_CEILING_ANCHORS)
                      + ("permuted_across", "permuted_within", "zero_scale", "pos_median"))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE PRE-REGISTERED POOLED SELECTION
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pooled_row(rec: dict, cohorts: list[int]) -> np.ndarray:
    return np.array([rec.get("per_cohort_pooled", {}).get(y, np.nan) for y in cohorts], dtype=float)


def select_pooled(arms: list[dict], inc: dict, cohorts: list[int]) -> dict:
    """Pick + deflate under the PRE-REGISTERED pooled framing: ONE hypothesis ("the rookie point is
    systematically cold at RB/TE/WR"), ONE test, no multiplicity correction.

    Eligibility = shippable AND do-no-ordering-harm at EVERY scaled position. `winner = None` with
    candidates present is a REAL result, not a bug — it means no arm stayed within
    `ORDERING_DO_NO_HARM` of the incumbent's within-position rank correlation everywhere.

    ⚠️ PBO is computed over the ELIGIBLE set — the search the selection ACTUALLY ran — per NF1.8, not
    over every config scored. Both the whole-field and the contender-set DSR are reported; the
    **WHOLE-FIELD reading is the PRE-REGISTERED gate** (`PREREGISTERED_DSR_READING`) and the contender
    reading exists so the two are distinguishable, never to re-open the gate after seeing it."""
    inc_row = _pooled_row(inc, cohorts)
    inc_metric = _mean(inc_row, 4)
    inc_rho = {p: inc.get(f"rho_{p}") for p in RC.RECALIBRATED_POSITIONS}

    cands = []
    for r in arms:
        row = _pooled_row(r, cohorts)
        metric = _mean(row, 4)
        if metric is None:
            continue
        rho = {p: r.get(f"rho_{p}") for p in RC.RECALIBRATED_POSITIONS}
        ordering = RC.ordering_check(rho, inc_rho)
        cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                      "eligible": bool(r["shippable"] and ordering["ok"])})

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["metric"]) if eligible else None
    best_any = min(cands, key=lambda c: c["metric"]) if cands else None

    mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"])) for c in cands}).sort_index()
    defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)

    means = mat.mean(axis=0).sort_values()
    ctr_labels = set(means.index[:max(4, len(means) // 4)])
    trial, ctr = [], []
    for c in cands:
        d = inc_row - c["row"]
        d = d[np.isfinite(d)]
        sr = (float(d.mean() / d.std(ddof=1))
              if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        trial.append(sr)
        if c["rec"]["label"] in ctr_labels:
            ctr.append(sr)

    dsr = dsr_ctr = pval = None
    deltas: list[float] = []
    if best is not None:
        raw = inc_row - best["row"]
        deltas = [float(x) for x in raw[np.isfinite(raw)]]
        dsr = M14.deflated_sharpe(np.array(deltas), np.array(trial, dtype=float))
        dsr_ctr = M14.deflated_sharpe(np.array(deltas), np.array(ctr, dtype=float))
        pval = M14.onesided_paired_pvalue(np.array(deltas))

    return {
        "framing": RC.PREREGISTERED_FRAMING, "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_metric": inc_metric, "incumbent_rho": inc_rho,
        "winner": None if best is None else {
            **{k: best["rec"].get(k) for k in ("label", "key", "form", "lam", "recalibrates",
                                               "shippable", "monotone", "learned")},
            "metric": best["metric"],
            "rho": {p: best["rec"].get(f"rho_{p}") for p in RC.RECALIBRATED_POSITIONS}},
        "best_any": None if best_any is None else {
            "label": best_any["rec"]["label"], "metric": best_any["metric"],
            "eligible": best_any["eligible"]},
        "ordering": None if best is None else best["ordering"],
        "deflation": {**defl, "dsr": dsr, "dsr_contenders": dsr_ctr},
        "pvalue": pval, "per_cohort_delta": [round(x, 3) for x in deltas],
        "eligible_labels": [c["rec"]["label"] for c in eligible],
        "ineligible_labels": [c["rec"]["label"] for c in cands if not c["eligible"]],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The DISCLOSED per-position reading (computed, reported, NEVER the gate)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pos_row(rec: dict, cohorts: list[int], pos: str, key: str = "tier_mae_by_pos") -> np.ndarray:
    return np.array([rec["per_cohort"].get(y, {}).get(key, {}).get(pos, np.nan) for y in cohorts],
                    dtype=float)


def per_position_disclosure(arms: list[dict], inc: dict, cohorts: list[int]) -> dict:
    """⭐ THE FRAMING THIS STORY DID **NOT** PRE-REGISTER, COMPUTED RATHER THAN SPECULATED ABOUT — the
    exact mirror of NF-D15, which pre-registered per-position and disclosed pooled.

    NF-D15's whole lesson is that it was blocked by its FRAMING and not by its effect size, and that it
    could only say so honestly because it computed BOTH readings. NF-D16 owes the same duty in the
    other direction: having chosen the pooled framing in advance and given the reason, it must show
    what the per-position framing would have said — including its 3-test BH-FDR — so a reader can see
    whether the framing decided the answer.

    ⚠️ **REPORTED, NEVER SELECTED ON.** The pre-registered pooled framing governs. If the two readings
    disagree, that is a disclosure, not a licence to take the other one (E2.1-r)."""
    out: dict = {"per_position": [], "fdr": {}, "bh_cutoff_unconditional": round(RC.FDR_Q / 3, 4)}
    inc_rho_all = {p: inc.get(f"rho_{p}") for p in RC.RECALIBRATED_POSITIONS}
    pvals: dict[str, float | None] = {}
    for pos in RC.RECALIBRATED_POSITIONS:
        inc_row = _pos_row(inc, cohorts, pos)
        inc_metric = _mean(inc_row, 4)
        cands = []
        for r in arms:
            row = _pos_row(r, cohorts, pos)
            metric = _mean(row, 4)
            if metric is None:
                continue
            ordering = RC.ordering_check({pos: r.get(f"rho_{pos}")},
                                         {pos: inc_rho_all.get(pos)}, positions=(pos,))
            cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                          "eligible": bool(r["shippable"] and ordering["ok"])})
        eligible = [c for c in cands if c["eligible"]]
        best = min(eligible, key=lambda c: c["metric"]) if eligible else None
        mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"]))
                            for c in cands}).sort_index()
        defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)
        trial = []
        for c in cands:
            d = inc_row - c["row"]
            d = d[np.isfinite(d)]
            trial.append(float(d.mean() / d.std(ddof=1))
                         if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        dsr = pval = None
        if best is not None:
            raw = inc_row - best["row"]
            dd = raw[np.isfinite(raw)]
            dsr = M14.deflated_sharpe(dd, np.array(trial, dtype=float))
            pval = M14.onesided_paired_pvalue(dd)
        pvals[pos] = pval
        out["per_position"].append({
            "position": pos, "incumbent_metric": inc_metric,
            "winner": None if best is None else best["rec"]["label"],
            "metric": None if best is None else best["metric"],
            "delta": (None if best is None or inc_metric is None
                      else round(best["metric"] - inc_metric, 3)),
            "pbo": defl.get("pbo"), "dsr": dsr, "pvalue": pval,
        })
    out["fdr"] = M14.bh_fdr(pvals, q=RC.FDR_Q)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE CEILING GAP — is a better-estimated constant available, or is the truth class-variable?
# ══════════════════════════════════════════════════════════════════════════════════════════════
def constant_stability(folds: list[NF17.Fold], fits: dict[int, dict]) -> dict:
    """⭐ THE DECISIVE DIAGNOSTIC FOR THIS STORY'S SCOPING QUESTION.

    The peeking per-position constant is the CEILING of the whole family, and a candidate that
    captures only a fraction of the headroom to it has two possible explanations that imply OPPOSITE
    next steps: either the estimator is leaving room on the table (⇒ keep estimating better), or the
    correct constant swings so hard from draft class to draft class that no in-fold estimator can
    follow it (⇒ a null nothing would overturn).

    This measures which. For each held-out class and position it compares:
      · `k_infold` — what the in-fold estimator says (what a candidate actually uses), against
      · `k_peek`   — that class's OWN realized constant (what the ceiling uses),
    and asks whether `k_infold` predicts `k_peek` better than the incumbent's implicit constant of 1.0
    does. `skill_vs_null` is the share of the "predict 1.0" error the in-fold estimate removes: ≤ 0
    means the estimator carries NO information about next year's level, which is the class-variable
    reading, measured rather than argued.

    ⚠️ It also reports the IN-SAMPLE OPTIMISM of the training points, which is a THIRD explanation the
    story's framing did not name: the in-fold constant is estimated against point projections that the
    fold's own slot curve was FITTED on, so those points are better calibrated than the held-out ones
    the constant is then applied to. That biases the estimated correction toward 1 — i.e. it
    UNDER-states the correction — which is conservative in direction but not zero in size, and it is
    part of the ceiling gap that is neither "a better estimator" nor "the truth moves"."""
    rows = []
    for f in folds:
        for q in RC.RECALIBRATED_POSITIONS:
            k_in = fits[f.year]["mult_const"].get(q)
            k_pk = fits[f.year]["_peek"].get(q)
            if k_in is None or k_pk is None:
                continue
            rows.append({"class": f.year, "position": q, "k_infold": round(float(k_in), 4),
                         "k_peek": round(float(k_pk), 4),
                         "err_infold": abs(float(k_in) - float(k_pk)),
                         "err_null": abs(1.0 - float(k_pk))})
    if not rows:
        return {"rows": [], "skill_vs_null": None}
    d = pd.DataFrame(rows)
    e_in, e_null = float(d["err_infold"].mean()), float(d["err_null"].mean())
    per_pos = {
        q: {"sd_of_peek_constant": round(float(g["k_peek"].std(ddof=1)), 4) if len(g) > 1 else None,
            "mean_peek_constant": round(float(g["k_peek"].mean()), 4),
            "mean_infold_constant": round(float(g["k_infold"].mean()), 4),
            "skill_vs_null": (round(1.0 - float(g["err_infold"].mean())
                                    / float(g["err_null"].mean()), 4)
                              if float(g["err_null"].mean()) > 1e-9 else None)}
        for q, g in d.groupby("position")}

    # ── the IN-SAMPLE OPTIMISM of the training points, measured on the last fold's training set ──
    optimism = None
    last = folds[-1]
    tr_pos = last.train["position_group"].astype(str).str.upper().to_numpy()
    tr_year = pd.to_numeric(last.train["draft_year"], errors="coerce").to_numpy(dtype=float)
    p_tr, y_tr = np.asarray(last.train_pred, dtype=float), pd.to_numeric(
        last.train[_REAL], errors="coerce").to_numpy(dtype=float)
    pairs = []
    for f in folds[:-1]:
        sel = tr_year == float(f.year)
        if sel.sum() < 5:
            continue
        k_is = RC.fit_mult_const(p_tr[sel], y_tr[sel], tr_pos[sel])
        for q, v in k_is.items():
            pk = fits[f.year]["_peek"].get(q)
            if pk is not None:
                pairs.append({"class": f.year, "position": q,
                              "k_in_sample_point": round(float(v), 4),
                              "k_out_of_sample_point": round(float(pk), 4),
                              "optimism": round(float(v) - float(pk), 4)})
    if pairs:
        optimism = {"rows": pairs,
                    "mean_optimism": round(float(np.mean([r["optimism"] for r in pairs])), 4)}

    return {"rows": rows, "per_position": per_pos,
            "skill_vs_null": round(1.0 - e_in / e_null, 4) if e_null > 1e-9 else None,
            "mean_abs_err_infold": round(e_in, 4), "mean_abs_err_null": round(e_null, 4),
            "in_sample_optimism": optimism}


def face_validity_pre_ship(folds: list[NF17.Fold], fits: dict[int, dict], sel: dict) -> dict:
    """⭐ THE PRE-SHIP CHECK THIS STORY'S FRAMING DID NOT ANTICIPATE — and the one a LEVEL correction
    most needs.

    The story's risk argument is "a level shift moves no ranks, so it is the low-risk half". That is
    true WITHIN a position and FALSE across the board: rookies and veterans are merged onto ONE draft
    board, so lifting every rookie by ~30–40% necessarily moves rookies UP against veterans. NF1.4
    already owns the gate for exactly that failure (`face_validity` / `rookie_board_face_validity`),
    and it exists because MVP-3 dogfooding surfaced a rookie floating to #1 overall.

    ⭐⭐ AND THE GATE IS TWO-SIDED, WHICH IS WHAT MAKES IT USABLE HERE. NF1.4 measured that the COLD
    incumbent breaches the level cap in **0 of 28** cohort-positions while the REALIZED outcomes
    breach it in **9 of 28** — a projection that never projects above what a strong class's best
    rookie actually does is not passing the gate, it is displaying the coldness NF1.4 documented. So
    "breaches 0" is the SYMPTOM, not the target, and REALITY'S OWN BREACH RATE is the reference:
      · breaches ≈ 0        ⇒ still cold (the incumbent's position);
      · breaches ≈ reality  ⇒ correctly levelled;
      · breaches > reality  ⇒ OVER-corrected, i.e. now hot — a ship blocker.
    Scoring reality alongside is the same two-sided-anchor discipline the rest of this harness uses,
    applied to a gate that would otherwise read as "fewer breaches is better".

    ⚠️ **DISCLOSED HONESTLY: this check was added AFTER the run showed the arm clearing its
    pre-registered gate.** That is admissible in exactly one direction — it can only VETO a ship,
    never enable one, and it cannot change which arm the pre-registered metric selected. A constraint
    that can only make the story more conservative is not metric-shopping; one that could have
    manufactured the win would be.

    Only the LEVEL half is computable here — the "no rookie in an overall top-10 slot" half needs
    veterans on the same board and is evaluated by `season_projection.rookie_board_face_validity` at
    export time, which is why it is named as an operator step rather than claimed as passed."""
    w = sel.get("winner")
    per_cohort, tallies = {}, {"incumbent": 0, "candidate": 0, "reality": 0}
    for f in folds:
        board = f.test.assign(is_rookie=True, position=f.test["position_group"],
                              _inc=f.test_pred, _real=f.test_real,
                              _new=(f.test_pred if w is None
                                    else arm_prediction({"form": w["form"], "lam": w["lam"]},
                                                        fits[f.year], f)))
        rec = {k: M14.face_validity(board, f.train, fp_col=col)["positions_over_cap"]
               for k, col in (("incumbent", "_inc"), ("candidate", "_new"), ("reality", "_real"))}
        for k in tallies:
            tallies[k] += len(rec[k])
        per_cohort[str(f.year)] = {k: [f"{v['position']} {v['max_projected']}>{v['top_of_class_cap']}"
                                       for v in rec[k]] for k in rec}
    n_cells = len(folds) * 4                       # cohort × ROOKIE_POSITIONS
    over = tallies["candidate"] > tallies["reality"]
    return {
        "per_cohort": per_cohort, "cells": n_cells,
        "breaches_incumbent": tallies["incumbent"], "breaches_candidate": tallies["candidate"],
        "breaches_reality": tallies["reality"],
        "over_corrected": bool(over), "ok": not over,
        "note": "LEVEL half only; the top-10-overall half needs the merged veteran board and is "
                "checked by season_projection.rookie_board_face_validity at export time.",
    }


def fitted_parameters(folds: list[NF17.Fold], fits: dict[int, dict]) -> dict:
    """The fitted parameters themselves, per class and position — the correction the arms actually
    apply, exposed rather than left implicit inside a metric.

    ⭐ `all_slopes_positive` is load-bearing for the learned foil's ordering claim. An affine
    `a + b·point` moves NO rank when `b > 0` and INVERTS a whole position's board when `b < 0`, so
    "the learned foil does no ordering harm" is TRUE OF THIS RUN'S FITTED SLOPES and NOT of the form.
    Recording the signs is what keeps that distinction visible — a future class that produced a
    negative slope would flip the claim, and the ordering constraint (not the form's description) is
    what would catch it."""
    rows, slopes = [], []
    for f in folds:
        for q in RC.RECALIBRATED_POSITIONS:
            rec = {"class": f.year, "position": q,
                   "mult_const k": fits[f.year]["mult_const"].get(q),
                   "add_offset c (PPR)": fits[f.year]["add_offset"].get(q)}
            ab = fits[f.year]["ols_slope"].get(q)
            if ab:
                rec["ols intercept"], rec["ols slope"] = round(ab[0], 3), round(ab[1], 4)
                slopes.append(float(ab[1]))
            rows.append({k: (round(v, 4) if isinstance(v, float) else v)
                         for k, v in rec.items()})
    return {"rows": rows, "n_slopes": len(slopes),
            "all_slopes_positive": bool(slopes) and all(s > 0 for s in slopes),
            "min_slope": round(min(slopes), 4) if slopes else None,
            "max_slope": round(max(slopes), 4) if slopes else None}


def permutation_invariance_proof(folds: list[NF17.Fold], fits: dict[int, dict]) -> dict:
    """⭐ THE MEASURED VERSION OF "a permutation test cannot bite a LEVEL hypothesis".

    `add_offset`'s statistic is `mean(y) − mean(point)`, which is EXACTLY invariant under a
    within-position permutation of `y`. So the within-permuted additive offset must equal the real one
    to machine precision, at every position and every held-out class. Measuring it turns a claim about
    the algebra into a number in the report — and it is the honest way to disclose that this story's
    permutation anchor is weak against its own hypothesis, rather than presenting a near-tie as if it
    were a passed test."""
    worst = 0.0
    for f in folds:
        real = fits[f.year]["add_offset"]
        perm = fits[f.year]["_perm_within_add"]
        for q in set(real) | set(perm):
            if q in real and q in perm:
                worst = max(worst, abs(float(real[q]) - float(perm[q])))
    return {"max_abs_difference": worst, "exactly_invariant": worst < 1e-9}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:                                     # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:          # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    an, sel, inc = out["anchors"], out["selection"], out["incumbent"]
    p("# NF-D16 — a per-position LEVEL recalibration of the rookie POINT (RB/TE/WR) — §0.5 bake-off")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **arms:** "
      f"{len(out['arms'])} · **held-out rookie-seasons (RB/TE/WR):** {out['n_scaled_rows']} · "
      f"**framing:** PRE-REGISTERED `{out['preregistration']['framing']}` · **DSR reading:** "
      f"PRE-REGISTERED `{out['preregistration']['dsr_reading']}`")
    p("")
    p(f"## ⭐ VERDICT — {out['headline']}")
    p("")
    p(out["verdict"])
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      f"⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and "
      f"every held-out QB: **{out['qb_max_drift']:.9f}** PPR). 🔒 The rookie INTERVAL's WIDTH model is "
      "untouched — NF-D14 settled that question.")
    p("")

    p("## 0. What was pre-registered, and when")
    p("")
    p("Everything that could otherwise have been chosen after seeing a result is a CONSTANT in "
      "`rookie_point_recalibration.py`; this report READS those constants rather than restating them, "
      "so 'what was pre-registered' has exactly one owner.")
    p("")
    pr = out["preregistration"]
    p(_md(pd.DataFrame([
        {"decision": "framing", "value": pr["framing"],
         "why (written BEFORE the run)": pr["framing_reason"]},
        {"decision": "DSR reading that BINDS", "value": pr["dsr_reading"],
         "why (written BEFORE the run)":
             "NF-D14 and NF-D15 were both bitten by a deflation statistic computed over a field "
             "containing its own weak arms. Naming which reading binds in advance is what stops that "
             "from becoming a choice made after seeing the answer."},
        {"decision": "DSR level", "value": pr["dsr_min"],
         "why (written BEFORE the run)":
             "The STRICTER of the two available bars (NF-D14/NF-D15's rather than NF1.4's 0.0), "
             "because this hypothesis was surfaced by re-reading NF-D15's field — a story born that "
             "way must not also be granted a looser bar than the field it was born in."},
        {"decision": "α (single hypothesis)", "value": pr["alpha"],
         "why (written BEFORE the run)":
             "One test under the pooled framing, so NF1.4's q is used directly as α with NO "
             "multiplicity correction. The per-position reading's 3-test BH-FDR is computed as a "
             "DISCLOSURE in §3d and does not gate."},
        {"decision": "selection metric", "value": pr["metric"],
         "why (written BEFORE the run)":
             "NF1.4's draftable-tier MAE, INHERITED. The incumbent rookie point was selected on it; "
             "grading a change to that same product on a different metric is metric-shopping."},
        {"decision": "forms", "value": ", ".join(pr["forms"]),
         "why (written BEFORE the run)":
             "≥3 correction classes + a direct-learned foil + the incumbent NULL. Two are monotone "
             "(zero ordering movement by construction) and two can reorder — which is what gives the "
             "ordering constraint something to refuse instead of passing vacuously."},
    ])))
    p("")
    p("🚨 **THE MOTIVATION IS NOT THE RESULT.** NF-D15 observed a per-position constant beating the "
      "incumbent at all three scaled positions. That observation was the best of 33 arms chosen AFTER "
      "seeing the field, undeflated, and never registered as its own hypothesis — it is the REASON "
      "this story exists and it is cited exactly once, in `rookie_point_recalibration`'s module "
      "docstring, labelled as prior motivation. It appears nowhere in this report as evidence. If the "
      "clean pre-registration shrinks the effect, **the shrinkage is the answer** (E2.1-r).")
    p("")

    p("## 1. The metric, the constraint, and the anchor set")
    p("")
    p("**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The draftable-tier MAE "
      "on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy "
      "a friendlier subset), pooled scale-free over RB/TE/WR for the pre-registered pooled test and "
      "reported per position in raw PPR beside it.")
    p("")
    p(f"**The constraint — DO NO ORDERING HARM**, `ORDERING_DO_NO_HARM = {RC.ORDERING_DO_NO_HARM}`, "
      "NF1.4's own constant inherited verbatim, checked PER POSITION and never as a pooled mean. ⚠️ "
      "**It is NON-BINDING for the two monotone forms BY CONSTRUCTION and BINDING for the other two** "
      "— which is precisely why both kinds are in the field. A field of only constants would leave the "
      "constraint passing having examined nothing.")
    p("")
    p("### The anchors, scored on THIS run")
    p("")
    rows = [{"anchor": t, "what it is": w, "pooled tier MAE": an[t]["pooled_tier_mae"],
             "tier MAE RB": an[t].get("tier_mae_RB"), "tier MAE TE": an[t].get("tier_mae_TE"),
             "tier MAE WR": an[t].get("tier_mae_WR"), "universe MAE": an[t]["universe_mae"]}
            for t, w in [
                ("oracle_perplayer", "ORACLE FLOOR, full resolution (peeks per player). Nothing may "
                                     "beat it."),
                ("oracle_posconst", "CEILING of the `mult_const` family — the held-out class's OWN "
                                    "per-position constant."),
                ("oracle_addoffset", "CEILING of the `add_offset` family."),
                ("oracle_tierconst", "CEILING of the `mult_tier` family (RICHER than a constant)."),
                ("oracle_ols", "CEILING of the `ols_slope` family (RICHER than a constant)."),
                ("permuted_across", "constants from outcomes shuffled ACROSS positions — the level "
                                    "structure destroyed. Must LOSE."),
                ("permuted_within", "constants from outcomes shuffled WITHIN position — the marginal "
                                    "PRESERVED. ⭐ EXPECTED TO TIE (see §4b)."),
                ("zero_scale", "DEGENERATE — project nothing. Must LOSE."),
                ("pos_median", "DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must "
                               "LOSE this one."),
            ] if t in an]
    rows.append({"anchor": "→ INCUMBENT (NULL)", "what it is": "the shipped rookie point, unchanged",
                 "pooled tier MAE": inc["pooled_tier_mae"], "tier MAE RB": inc.get("tier_mae_RB"),
                 "tier MAE TE": inc.get("tier_mae_TE"), "tier MAE WR": inc.get("tier_mae_WR"),
                 "universe MAE": inc["universe_mae"]})
    if out["best_recal"]:
        b = out["best_recal"]
        rows.append({"anchor": "→ BEST RECALIBRATION ARM", "what it is": b["label"],
                     "pooled tier MAE": b["pooled_tier_mae"], "tier MAE RB": b.get("tier_mae_RB"),
                     "tier MAE TE": b.get("tier_mae_TE"), "tier MAE WR": b.get("tier_mae_WR"),
                     "universe MAE": b["universe_mae"]})
    p(_md(pd.DataFrame(rows)))
    p("")
    for ok, good, bad in (
        (out["checks"]["degenerates_lose"],
         "✅ both degenerates lose the primary metric — it is not paying for pessimism",
         "🚨 A DEGENERATE WINS THE PRIMARY METRIC — it is INVERTED; nothing in this run may be "
         "shipped (CLAUDE.md NF-D11/NF-D14)"),
        (out["checks"]["permutation_across_beaten"],
         "✅ the truth beats the ACROSS-position permutation — the per-position level structure is "
         "real information",
         "🚨 THE ACROSS-POSITION PERMUTATION IS NOT BEATEN — the per-position constants carry nothing "
         "a shuffled outcome vector would not give"),
        (out["checks"]["oracle_respected"],
         "✅ the full-resolution oracle floor holds",
         "🚨 THE ORACLE IS BEATEN AT FULL RESOLUTION — mathematically impossible ⇒ the metric is "
         "inverted"),
        (out["checks"]["family_ceiling_respected"],
         f"✅ every arm respects **its own form's** peeking ceiling "
         f"({out['family_ceiling_check']['n_checked']} arms checked at MATCHED family and MATCHED "
         f"resolution)",
         f"🚨 AN ARM BEAT ITS OWN FORM'S PEEKING CEILING — a metric inversion: "
         f"`{out['family_ceiling_check']['violations']}`"),
        (out["checks"]["qb_untouched"],
         "✅ QB is untouched on real emitted projections, not merely by assertion",
         "🚨 A RECALIBRATION REACHED QB — the pre-registered exclusion is broken"),
    ):
        p("- " + (good if ok else bad))
    p("")
    p(out["degenerate_reading"])
    p("")
    p("⭐ **ONE CEILING PER FORM, NOT ONE FOR THE FIELD — and the first cut of this story had it "
      "wrong.** A peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION (NF1.7 "
      "(b) / NF1.9 (f)). `mult_tier` and `ols_slope` each CONTAIN the per-position constant as a "
      "special case, so either can legitimately score better than the best possible constant — a "
      "capacity effect, not an inversion. Flooring the whole field on `oracle_posconst` would have "
      "vetoed a real result for the wrong reason; each arm is therefore checked against the peeking "
      "version of its OWN form, where 'peeking can only help' genuinely holds:")
    p("")
    p(_md(pd.DataFrame(out["family_ceiling_check"]["per_arm"])))
    p("")

    p("## 2. The full field (pooled over RB/TE/WR)")
    p("")
    p(_md(pd.DataFrame([{
        "arm": r["label"], "recal?": "yes" if r["recalibrates"] else "—",
        "monotone?": "yes (0 rank movement)" if r.get("monotone") else ("—" if r["recalibrates"]
                                                                        else ""),
        "pooled tier MAE": r["pooled_tier_mae"],
        "tier MAE RB": r.get("tier_mae_RB"), "tier MAE TE": r.get("tier_mae_TE"),
        "tier MAE WR": r.get("tier_mae_WR"),
        "universe MAE": r["universe_mae"], "universe bias": r["universe_bias"]}
        for r in sorted(out["arms"], key=lambda r: (r["pooled_tier_mae"] is None,
                                                    r["pooled_tier_mae"]))])))
    p("")

    p("## 3. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test")
    p("")
    d = sel["deflation"]
    w = sel["winner"]
    p(f"The ship UNIT is the WHOLE per-position constant vector: a level recalibration is ONE change "
      f"to `project_rookies` that applies at RB/TE/WR together or not at all. Eligible arms "
      f"({sel['n_eligible']} of {sel['n_candidates']}) are those that are shippable AND do no ordering "
      f"harm at EVERY scaled position.")
    p("")
    if w is None:
        p(f"**No arm was eligible.** {sel['n_candidates']} arms scored; none stayed within the "
          f"ordering constraint at every position. The unconstrained best was "
          f"`{(sel['best_any'] or {}).get('label')}` at {(sel['best_any'] or {}).get('metric')} — a "
          f"point-MAE win that scrambles the draft order, which is the trade the constraint exists to "
          f"refuse.")
        p("")
    else:
        p(_md(pd.DataFrame([{
            "incumbent pooled tier MAE": sel["incumbent_metric"],
            "selected arm": w["label"], "pooled tier MAE": w["metric"],
            "Δ vs incumbent": round(w["metric"] - sel["incumbent_metric"], 4),
            "PBO": d.get("pbo"), "Bailey degradation %": d.get("os_gap_pct"),
            "contender spread %": d.get("contender_spread_pct"),
            "DSR (whole-field, THE GATE)": d.get("dsr"),
            "DSR (contender, reported)": d.get("dsr_contenders"),
            "one-sided paired p (1 test)": sel["pvalue"],
            f"α (pre-registered)": RC.ALPHA,
        }])))
        p("")
        p(f"Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): "
          f"`{sel['per_cohort_delta']}` over classes `{out['cohorts']}`.")
        p("")
        if d.get("flips"):
            # NF1.8's `deflate` is shared with an INTERVAL story, so it names its full-sample column
            # `IS80`. Rendering that label here would put an interval score's name on a tier MAE.
            p("**The flip distribution** (NF1.8: a rank statistic alone cannot tell a TIE from an "
              "unstable pick — mass on two arms a fraction of a percent apart IS a tie; mass spread "
              "thinly over a dozen unrelated arms is a search that learnt nothing):")
            p("")
            p(_md(pd.DataFrame(d["flips"]).head(6)
                  .rename(columns={"full-sample IS80": "full-sample pooled tier MAE"})))
            p("")
    p(f"**Ship decision under the pre-registered framing:** `{out['ship_gate']}`")
    p("")

    p("### 3b. Is the answer resting on a gate level I chose? — the sensitivity, computed")
    p("")
    gs = out["gate_sensitivity"]
    p(_md(pd.DataFrame([gs["table"]])))
    p("")
    p(gs["reading"])
    p("")

    p("### 3c. The margin in DRAFT CLASSES — what kind of answer this is")
    p("")
    p(_md(pd.DataFrame([out["power_in_classes"]])))
    p("")
    p("NF1.8's 'state the margin in ROWS' convention, one unit over. A p-value decimal cannot "
      "distinguish **underpowered** from **absent**: an effect that needs a plausible number of "
      "further draft classes is a story to re-run when they exist; one that needs dozens is a null at "
      "any n this program will ever have.")
    p("")

    p("### 3d. ⭐ THE DISCLOSED PER-POSITION READING — the framing this story did NOT pre-register")
    p("")
    p("NF-D15 pre-registered per-position and disclosed pooled; NF-D16 does the exact opposite, and "
      "owes the same duty. **Reported, never selected on** — the pre-registered pooled framing "
      "governs (E2.1-r). This table exists so 'the framing did not decide the answer' is a number "
      "rather than a shrug.")
    p("")
    pp = out["per_position_disclosure"]
    p(_md(pd.DataFrame([{**r, "BH-FDR (3 tests)": "survives" if pp["fdr"].get(r["position"])
                         else "no"} for r in pp["per_position"]])))
    p("")
    p(f"BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: "
      f"**{pp['bh_cutoff_unconditional']}** — against the pooled framing's α of **{RC.ALPHA}**. "
      + out["framing_reading"])
    p("")

    p("## 4. ⭐ THE CEILING GAP, READ — is a better constant available, or is the truth class-variable?")
    p("")
    cg = out["ceiling_gap"]
    p(_md(pd.DataFrame([{
        "incumbent (pooled tier MAE)": cg["incumbent"],
        "best candidate": cg["best_candidate"],
        "CEILING (peeking per-position constant)": cg["ceiling"],
        "headroom (inc − ceiling)": cg["headroom"],
        "captured (inc − candidate)": cg["captured"],
        "share of headroom captured": cg["captured_share"],
        "in-fold skill vs 'predict 1.0'": cg["skill_vs_null"],
    }])))
    p("")
    p(out["ceiling_reading"])
    p("")
    p("**The per-class constants themselves** — the raw material of that reading:")
    p("")
    p(_md(pd.DataFrame([{"position": q, **v}
                        for q, v in out["constant_stability"]["per_position"].items()])))
    p("")
    p(_md(pd.DataFrame(out["constant_stability"]["rows"])))
    p("")
    opt = out["constant_stability"].get("in_sample_optimism")
    if opt:
        p(f"⚠️ **A THIRD EXPLANATION THE STORY'S FRAMING DID NOT NAME — IN-SAMPLE OPTIMISM, measured "
          f"at {opt['mean_optimism']}.** The in-fold constant is estimated against point projections "
          f"the fold's OWN slot curve was fitted on, so those points are better calibrated than the "
          f"held-out ones the constant is then applied to. The same draft class yields a different "
          f"constant depending on whether its points came from a curve that had seen it "
          f"(`k_in_sample_point`) or not (`k_out_of_sample_point`), and the gap between them is a part "
          f"of the ceiling gap that is neither 'a better estimator' nor 'the truth moves'. The "
          f"direction is CONSERVATIVE — it biases the estimated correction toward 1, i.e. it "
          f"UNDER-states it — so it cannot manufacture a lift, but it is not zero.")
        p("")
        p(_md(pd.DataFrame(opt["rows"])))
        p("")

    p("### 4b. ⭐ THE PERMUTATION ANCHOR IS NEAR-VACUOUS AGAINST A LEVEL HYPOTHESIS — measured, "
      "not glossed")
    p("")
    piv = out["permutation_invariance"]
    p(f"`add_offset`'s statistic is `mean(y) − mean(point)`, which is EXACTLY invariant under a "
      f"within-position permutation of `y`. Measured over every position and every held-out class, "
      f"the maximum absolute difference between the real offset and the within-permuted one is "
      f"**{piv['max_abs_difference']:.12f}** — "
      + ("exactly invariant, as the algebra requires." if piv["exactly_invariant"]
         else "🚨 NOT invariant, which means the permutation is not doing what this section claims.")
      + " That is why BOTH permutations are in the anchor set: the WITHIN-position one is expected to "
        "tie and is reported as a property of the hypothesis (a level IS a marginal statistic), while "
        "the ACROSS-position one is the anchor that actually has to be beaten. Presenting a near-tie "
        "as a passed permutation test would be a check that examined nothing.")
    p("")

    p("## 5. Ordering — the structural claim, MEASURED on emitted projections")
    p("")
    p(_md(pd.DataFrame(out["ordering_structural"])))
    p("")
    p("⭐ The two **monotone-by-construction** forms must show max rank movement exactly 0 at every "
      "position — a strictly monotone transform of a position's projections moves no rank. Two things "
      "could break that in practice and neither is visible in the algebra (a multiplicative constant "
      "clipping to different values in different cells; the physical floor at 0 creating TIES among "
      "rookies an additive offset pushed below zero), so the claim is checked on the numbers the arms "
      "actually emit rather than asserted from their definitions.")
    p("")
    fp = out["fitted_parameters"]
    p(f"⚠️ **`ols_slope` IS ONLY *CONDITIONALLY* MONOTONE, AND THIS RUN'S ZERO IS A MEASUREMENT RATHER "
      f"THAN A PROPERTY OF THE FORM.** An affine `a + b·point` moves no rank when `b > 0` and INVERTS "
      f"a whole position's board when `b < 0`. Every fitted slope in this run is positive "
      f"(`all_slopes_positive` = {fp['all_slopes_positive']}, range "
      f"{fp['min_slope']}–{fp['max_slope']} over {fp['n_slopes']} position × class fits), which is WHY "
      f"its measured rank movement is 0 — not because the form guarantees it. A future draft class "
      f"that produced a negative slope would flip that, and the ordering CONSTRAINT (not the form's "
      f"description) is what would catch it. **`mult_tier` is the only form that genuinely reorders** "
      f"— and it is ineligible at every λ for exactly that reason, which is what makes the constraint "
      f"non-vacuous in this field.")
    p("")
    p("**The fitted corrections themselves** — what the arms actually apply, per class and position:")
    p("")
    p(_md(pd.DataFrame(fp["rows"])))
    p("")
    p("### ⭐ 5b. THE CHECK THIS STORY'S FRAMING DID NOT ANTICIPATE — rookies move against VETERANS")
    p("")
    fv = out["face_validity"]
    p("The story's risk argument is 'a level shift moves no ranks, so it is the low-risk half.' That "
      "is true WITHIN a position and **false across the board**: rookies and veterans share ONE draft "
      "board, so lifting every rookie necessarily moves rookies UP against veterans — and NF1.4 "
      "already owns the gate for that failure, because MVP-3 dogfooding surfaced a rookie floating to "
      "#1 overall.")
    p("")
    p("⭐⭐ **AND THE GATE IS TWO-SIDED, WHICH IS THE ONLY REASON IT IS USABLE HERE.** NF1.4 measured "
      "that the COLD incumbent breaches the level cap in **0 of 28** cohort-positions while the "
      "REALIZED outcomes breach it in **9 of 28**. A projection that never projects above what a "
      "strong class's best rookie actually does is not passing this gate — it is displaying exactly "
      "the coldness NF1.4 documented. So 'zero breaches' is the SYMPTOM, not the target, and "
      "**reality's own breach rate is the reference**:")
    p("")
    p(_md(pd.DataFrame([{
        "cohort-positions": fv["cells"],
        "incumbent breaches (cold)": fv["breaches_incumbent"],
        "→ CANDIDATE breaches": fv["breaches_candidate"],
        "REALITY breaches (the reference)": fv["breaches_reality"],
        "over-corrected?": "🚨 YES — now HOT" if fv["over_corrected"] else "no",
    }])))
    p("")
    p("⚠️ **DISCLOSED: this check was added AFTER the run showed the arm clearing its pre-registered "
      "gate.** That is admissible in exactly one direction — it can only VETO a ship, never enable "
      "one, and it cannot change which arm the pre-registered metric selected. A constraint that can "
      "only make the story more conservative is not metric-shopping; one that could have manufactured "
      "the win would be. ⏭️ Only the LEVEL half is computable in this harness — the "
      "'no rookie in an overall top-10 slot' half needs veterans on the same board and is checked by "
      "`season_projection.rookie_board_face_validity` at export time, so it is named as an OPERATOR "
      "step rather than claimed as passed here.")
    p("")
    p(_md(pd.DataFrame([{"class": k, **{kk: ", ".join(vv) or "—" for kk, vv in v.items()}}
                        for k, v in fv["per_cohort"].items()])))
    p("")

    p("### What a shipped recalibration would do to the board")
    p("")
    p(_md(pd.DataFrame(out["board_movement"])))
    p("")
    p("Reported whether or not anything ships — if nothing ships this is the size of what was "
      "declined, which is the number a reader needs to judge whether the null is expensive.")
    p("")

    p("## 6. Honest limitations")
    p("")
    for line in out["limitations"]:
        p(f"- {line}")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Prose
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _degenerate_reading(an: dict, ref: dict) -> str:
    z, m = an["zero_scale"], an["pos_median"]
    if min(z["pooled_tier_mae"], m["pooled_tier_mae"]) <= ref["pooled_tier_mae"]:
        return ("🚨 **A DEGENERATE WON THE PRIMARY METRIC — it is INVERTED and nothing in this run may "
                f"be shipped.** `zero_scale` {z['pooled_tier_mae']} / `pos_median` "
                f"{m['pooled_tier_mae']} against the reference arm's {ref['pooled_tier_mae']}.")
    return (f"⭐ **The degenerate check comes back NEGATIVE, and it is reported because it was SCORED, "
            f"not because it was expected.** `zero_scale` ({z['pooled_tier_mae']}) and NF1.4's "
            f"`pos_median` MAE-collapse tell ({m['pooled_tier_mae']}) both lose decisively to the "
            f"reference arm ({ref['pooled_tier_mae']}). NF-D14's refinement of the NF-D11 landmine is "
            f"why this is a measurement rather than an argument: **MAE inverts when the conditional "
            f"MEDIAN sits at the floor, not merely when the zero atom is fat** — and on the RB/TE/WR "
            f"DRAFTABLE TIER the median is nowhere near zero. The right response to that rule is to "
            f"keep the degenerate in the field and READ it every run, which is what this line is.")


def _ceiling_reading(cg: dict, cs: dict) -> str:
    share = cg.get("captured_share")
    skill = cg.get("skill_vs_null")
    head = (f"The peeking per-position constant is the CEILING of this entire family: pooled tier MAE "
            f"**{cg['ceiling']}** against the incumbent's **{cg['incumbent']}**, i.e. **"
            f"{cg['headroom']}** of headroom exists IN PRINCIPLE for a per-position level correction. "
            f"The best candidate captured **{cg['captured']}** of it "
            f"({'—' if share is None else f'{100 * share:.1f}%'}).")
    if cg["reading"] == "A_estimable":
        return (head + " ⇒ **READING (A) — ESTIMABLE.** The in-fold estimator carries real information "
                f"about the next class's constant (`skill_vs_null` {skill} > 0, i.e. it removes that "
                f"share of the error a naive 'predict 1.0' makes), and the candidate captured a "
                "material share of the available headroom. The level effect is learnable in-fold and "
                "the gap to the ceiling is estimator quality, not an unreachable target.")
    if cg["reading"] == "B_class_variable":
        return (head + " ⇒ **READING (B) — CLASS-VARIABLE, i.e. THE CEILING IS UNREACHABLE IN "
                f"PRINCIPLE.** The in-fold estimate does **not** predict the held-out class's own "
                f"constant better than the incumbent's implicit 1.0 does (`skill_vs_null` {skill}; "
                f"mean |error| {cs.get('mean_abs_err_infold')} in-fold vs "
                f"{cs.get('mean_abs_err_null')} for 'predict 1.0'). The correct constant swings from "
                "draft class to draft class faster than any in-fold estimator can follow, so the "
                "headroom the peeking oracle shows is **not available to a real estimator at any "
                "level of estimator effort**. ⭐ That distinction is the whole reason the ceiling was "
                "computed: a large gap to a peeking oracle looks like an invitation to keep trying, "
                "and here it is a measurement that further trying would not pay. This is the reading "
                "the run supports.")
    return head + " ⇒ the diagnostic is INDETERMINATE on this run."


def _verdict_prose(out: dict) -> str:
    a: list[str] = []
    sel, inc, gate = out["selection"], out["incumbent"], out["ship_gate"]
    w = sel["winner"]
    if w is None:
        a.append("**No arm was eligible under the pre-registered pooled framing** — none stayed "
                 "within the ordering constraint at every scaled position.")
    else:
        failed = [k for k, v in gate.items() if k not in ("ship", "framing") and not v]
        a.append(
            f"**The pre-registered pooled test selects `{w['label']}`**, moving the pooled draftable-"
            f"tier MAE **{sel['incumbent_metric']} → {w['metric']}** "
            f"(Δ {round(w['metric'] - sel['incumbent_metric'], 4)}) over "
            f"{len(out['cohorts'])} held-out draft classes, with PBO {sel['deflation'].get('pbo')}, "
            f"whole-field DSR {sel['deflation'].get('dsr')} (the pre-registered gate, ≥ {RC.DSR_MIN}) "
            f"and a one-sided paired p of {sel['pvalue']} against α = {RC.ALPHA}."
            + (f" **Failing gate(s): `{failed}`.**" if failed else ""))
    a.append("")
    ceil = out["ceiling_gap"]
    if ceil.get("reading") == "B_class_variable":
        a.append(
            "⭐ **AND THE RUN ANSWERS ITS OWN SCOPING QUESTION, WHICH IS THE MOST DURABLE THING IN "
            "IT.** The gap between the incumbent and the PEEKING per-position constant is real and "
            f"large ({ceil['headroom']} pooled tier MAE), and the story pre-registered two readings of "
            "it: either a better-estimated constant closes more of it, or the correct constant is "
            "strongly class-to-class variable and therefore not learnable in-fold at all. **The run "
            "supports the second.** The in-fold estimate does not predict the held-out class's own "
            f"constant better than 'predict 1.0' does (`skill_vs_null` {ceil['skill_vs_null']}), so "
            "the headroom the oracle displays is not available to any real estimator — which converts "
            "'there is room here, keep trying' into a measured 'there is not', and closes the lead "
            "rather than deferring it.")
        a.append("")
    elif ceil.get("reading") == "A_estimable":
        a.append(
            f"⭐ **THE CEILING GAP READS (A) — ESTIMABLE.** The in-fold estimate carries real "
            f"information about the next class's constant (`skill_vs_null` {ceil['skill_vs_null']}) "
            f"and the candidate captured {ceil['captured']} of the {ceil['headroom']} available "
            f"headroom, so the remaining gap is estimator quality rather than an unreachable target.")
        a.append("")
    if gate.get("ship"):
        a.append(
            "⇒ **SHIP.** The recalibration improves the metric the incumbent rookie point was itself "
            "selected on, does no ordering harm at any scaled position, and clears the pre-registered "
            "deflation and significance gates under the framing chosen before the run. ⚠️ It moves the "
            "rookie band's CENTRE, so `run_interval_revalidation` must be re-run and every coverage "
            "floor re-confirmed before this reaches the board. QB stays exactly where NF-D14 left it.")
    else:
        a.append(
            "⇒ **RECORDED NULL — and NF-D15's second lead is now CLOSED rather than left dangling.** "
            "The clean pre-registration is the whole point: the effect that motivated this story was "
            "the best of 33 arms chosen after seeing them, and asked as its own hypothesis under a "
            "framing fixed in advance it does not clear its gate. The shipped rookie point STANDS, "
            "the interval is untouched, and the QB exclusion was never re-opened.")
    return "\n".join(a)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:            # noqa: C901 — orchestration
    ap = argparse.ArgumentParser(
        description="NF-D16 rookie-point LEVEL recalibration bake-off (RB/TE/WR; QB excluded)")
    ap.add_argument("--pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--recalibrated-incumbent", action="store_true",
                    help="build folds with NF-D16's SHIPPED recalibration already applied, i.e. ask "
                         "'is there anything LEFT after shipping?'. The bake-off of record runs "
                         "WITHOUT it — a study of whether to add the correction cannot use the "
                         "corrected point as its own null.")
    ap.add_argument("--smoke", action="store_true",
                    help="one λ and three forms; writes *_smoke artifacts so it can never be "
                         "mistaken for the real search")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    suffix = "_smoke" if args.smoke else ""

    pool = NF17.load_pool(Path(args.pool))
    # ⚠️ `recal_lambda=1.0` is PINNED, not inherited from the served policy (NF-D21 made the
    #    `build_folds` default track serving). `--recalibrated-incumbent` is NF-D16's post-ship
    #    headroom re-read: it asks "how much level effect is left once the FULL correction is
    #    applied", and re-running it at the served λ=0.5 would answer a different question while
    #    reproducing this story's published table. A historical result is scored at ITS OWN λ.
    folds = NF17.build_folds(pool, list(range(args.from_year, args.to_year + 1)),
                             recalibrate=bool(args.recalibrated_incumbent), recal_lambda=1.0)
    suffix += "_post_ship" if args.recalibrated_incumbent else ""
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    log.info("%d held-out draft classes: %s", len(folds), cohorts)

    fits = {f.year: fold_fits(f) for f in folds}
    pos_scale = {f.year: M14.position_scale(f.train) for f in folds}

    cfgs = RC.candidate_configs(smoke=args.smoke)
    log.info("%d arms × %d classes", len(cfgs), len(folds))
    arms = score_arms(folds, fits, pos_scale, cfgs)
    incumbent = next(r for r in arms if r["form"] == "incumbent")

    anchors = score_anchors(folds, fits, pos_scale)
    RC.require_anchors(anchors)

    recal = [r for r in arms if r["recalibrates"] and r["pooled_tier_mae"] is not None]
    best_recal = min(recal, key=lambda r: r["pooled_tier_mae"]) if recal else None
    ref = best_recal or incumbent

    # ⭐ EVERY arm against ITS OWN form's peeking ceiling, not one ceiling for the field.
    ceiling_check = RC.family_ceiling_check(arms, anchors, metric="pooled_tier_mae")

    checks = {
        "degenerates_lose": all(ref["pooled_tier_mae"] < anchors[t]["pooled_tier_mae"]
                                for t in ("zero_scale", "pos_median")),
        "permutation_across_beaten": (ref["pooled_tier_mae"]
                                      < anchors["permuted_across"]["pooled_tier_mae"]),
        "oracle_respected": (anchors["oracle_perplayer"]["pooled_tier_mae"]
                             <= ref["pooled_tier_mae"] + 1e-9),
        "family_ceiling_respected": bool(ceiling_check["ok"]),
        "qb_untouched": True,
    }

    # ⛔ THE SCOPE ASSERTION, MEASURED — every arm, every class, every held-out QB.
    qb_drift = 0.0
    for f in folds:
        pos = fits[f.year]["_te_pos"]
        qb = pos == "QB"
        if not qb.any():
            continue
        for c in cfgs:
            got = arm_prediction(c, fits[f.year], f)
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - f.test_pred[qb]))))
    checks["qb_untouched"] = qb_drift < 1e-12

    sel = select_pooled(arms, incumbent, cohorts)
    ship_gate = RC.pooled_ship(
        winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
        ordering=sel["ordering"] or {"per_position": {}},
        pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"), pvalue=sel["pvalue"])
    # ⭐ A VETO-ONLY PRE-SHIP CHECK, added after the run cleared its pre-registered gate and disclosed
    #    as such: a level correction moves rookies against VETERANS even though it moves no rank
    #    within a position, and NF1.4's face-validity gate is the program's owner of that risk. It can
    #    only block a ship, never enable one, and it cannot change which arm was selected.
    face = face_validity_pre_ship(folds, fits, sel)
    verdict_gate = RC.recalibration_verdict(
        pooled_ships=bool(ship_gate["ship"] and face["ok"]), **checks)
    verdict_gate["face_validity_not_over_corrected"] = bool(face["ok"])

    cs = constant_stability(folds, fits)
    # ⭐ The headroom is measured against the WINNER'S OWN family ceiling — using a different family's
    #    would be the matched-family error one statistic over. The CONSTANT family's is reported
    #    beside it because the story's scoping question was posed on the constant.
    win_form = (sel["winner"] or best_recal or {}).get("form")
    ceil_tag = RC.FAMILY_CEILING.get(win_form, "oracle_posconst")
    ceiling_gap = RC.read_the_ceiling_gap(
        incumbent=incumbent["pooled_tier_mae"],
        best_candidate=(sel["winner"] or {}).get("metric",
                                                 None if best_recal is None
                                                 else best_recal["pooled_tier_mae"]),
        ceiling=anchors[ceil_tag]["pooled_tier_mae"], ceiling_anchor=ceil_tag,
        constant_ceiling=anchors["oracle_posconst"]["pooled_tier_mae"], constant_stability=cs)

    n_scaled = int(sum(len(RC.scaled_positions_only(f.test)) for f in folds))
    out = {
        "story": "NF-D16", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts": cohorts, "n_scaled_rows": n_scaled,
        "preregistration": {
            "framing": RC.PREREGISTERED_FRAMING, "framing_reason": RC.FRAMING_REASON,
            "dsr_reading": RC.PREREGISTERED_DSR_READING, "dsr_min": RC.DSR_MIN,
            "alpha": RC.ALPHA, "pbo_max": RC.PBO_MAX, "metric": RC.SELECTION_METRIC,
            "forms": list(RC.FORMS), "shrink_grid": list(RC.SHRINK_GRID),
            "monotone_forms": list(RC.MONOTONE_FORMS),
            "ordering_binding_forms": list(RC.ORDERING_BINDING_FORMS),
        },
        "arms": arms, "incumbent": incumbent, "best_recal": best_recal, "anchors": anchors,
        "checks": checks, "qb_max_drift": qb_drift,
        "selection": sel, "ship_gate": ship_gate, "verdict_gate": verdict_gate,
        "ship": verdict_gate["ship"],
        "per_position_disclosure": per_position_disclosure(arms, incumbent, cohorts),
        "constant_stability": cs, "ceiling_gap": ceiling_gap,
        "family_ceiling_check": ceiling_check, "face_validity": face,
        "fitted_parameters": fitted_parameters(folds, fits),
        "permutation_invariance": permutation_invariance_proof(folds, fits),
        "ordering_structural": _ordering_structural(folds, fits, cfgs),
        "board_movement": _board_movement(folds, fits, sel, ship_gate),
        "gate_sensitivity": _gate_sensitivity(sel, ship_gate),
        "power_in_classes": _power_in_classes(sel),
        "degenerate_reading": _degenerate_reading(anchors, ref),
        "limitations": _LIMITATIONS,
    }
    out["ceiling_reading"] = _ceiling_reading(ceiling_gap, cs)
    out["framing_reading"] = _framing_reading(out)
    out["headline"] = (
        "✅ SHIP — a per-position LEVEL recalibration of the rookie point at RB/TE/WR"
        if verdict_gate["ship"] else
        "🟡 RECORDED NULL — no pre-registered level recalibration clears its own gate; the shipped "
        "rookie point STANDS")
    out["verdict"] = _verdict_prose(out)

    print("\n=== NF-D16 — rookie-point LEVEL recalibration (RB/TE/WR; QB excluded) ===")
    for r in sorted(arms, key=lambda r: (r["pooled_tier_mae"] is None, r["pooled_tier_mae"]))[:12]:
        print(f"{r['label']:26s} pooled {r['pooled_tier_mae']:7.4f}  "
              f"RB {r.get('tier_mae_RB', float('nan')):7.2f}  "
              f"TE {r.get('tier_mae_TE', float('nan')):7.2f}  "
              f"WR {r.get('tier_mae_WR', float('nan')):7.2f}  univMAE {r['universe_mae']:6.2f}")
    print("\nanchors: " + " · ".join(f"{t} {anchors[t]['pooled_tier_mae']}" for t in anchors))
    print(f"QB max drift {qb_drift:.9f} · global checks: {checks}")
    print(f"pooled: inc {sel['incumbent_metric']} → {(sel['winner'] or {}).get('label')} "
          f"{(sel['winner'] or {}).get('metric')} · PBO {sel['deflation'].get('pbo')} "
          f"DSR {sel['deflation'].get('dsr')} p {sel['pvalue']}")
    print(f"ship gate: {ship_gate}")
    print(f"face-validity (LEVEL half): incumbent {face['breaches_incumbent']} / candidate "
          f"{face['breaches_candidate']} / REALITY {face['breaches_reality']} of {face['cells']} "
          f"cohort-positions over cap → over_corrected={face['over_corrected']}")
    print(f"ceiling gap: {ceiling_gap}")
    print(f"verdict: {verdict_gate}")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_d16_rookie_point_recalibration{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_d16_rookie_point_recalibration{suffix}.md")
    print(f"\n{out['headline']}")
    return 0


def _ordering_structural(folds, fits, cfgs) -> list[dict]:
    """MEASURE the "zero ordering movement by construction" claim on real emitted projections, for
    every form at λ = 1 (the strongest version of each correction)."""
    out = []
    seen = set()
    for c in cfgs:
        if c["form"] == "incumbent" or c["form"] in seen or float(c["lam"]) != 1.0:
            continue
        seen.add(c["form"])
        worst, per = 0.0, {}
        for f in folds:
            got = arm_prediction(c, fits[f.year], f)
            rec = RC.ordering_is_structural(c["form"], f.test_pred, fits[f.year]["_te_pos"], got)
            worst = max(worst, rec["worst_rank_move"])
            for q, v in rec["max_rank_move_by_pos"].items():
                per[q] = max(per.get(q, 0.0), v)
        out.append({"form": c["form"],
                    "expected monotone (0 rank movement)": c["form"] in RC.MONOTONE_FORMS,
                    "max rank movement RB": per.get("RB"), "max rank movement TE": per.get("TE"),
                    "max rank movement WR": per.get("WR"),
                    "worst": round(worst, 3),
                    "structural claim holds": (c["form"] not in RC.MONOTONE_FORMS) or worst == 0.0})
    return out


def _board_movement(folds, fits, sel, ship_gate) -> list[dict]:
    """How much the SELECTED recalibration would actually move the board, per position: the mean |Δ|
    in PPR, within-position rank churn, and how many of the incumbent's draftable tier get displaced.

    Reported whether or not anything ships — if nothing ships this is the size of what was declined."""
    w = sel["winner"]
    if w is None:
        return [{"position": q, "arm": "— none eligible —", "mean abs Δ (PPR)": None,
                 "max abs Δ (PPR)": None, "mean abs rank Δ": None, "tier displacements": None,
                 "would ship": "no"} for q in RC.RECALIBRATED_POSITIONS]
    cfg = {"form": w["form"], "lam": w["lam"]}
    out = []
    for pos_name in RC.RECALIBRATED_POSITIONS:
        d_abs, rank_moves, displaced, tier_n = [], [], 0, 0
        k_tier = RC.TIER_K.get(pos_name, 5)
        for f in folds:
            pos = fits[f.year]["_te_pos"]
            sel_p = pos == pos_name
            if sel_p.sum() < 3:
                continue
            new = arm_prediction(cfg, fits[f.year], f)
            base, cand = f.test_pred[sel_p], new[sel_p]
            d_abs.append(np.abs(cand - base))
            rank_moves.append(np.abs(pd.Series(base).rank(ascending=False).to_numpy()
                                     - pd.Series(cand).rank(ascending=False).to_numpy()))
            displaced += len(set(np.argsort(-base)[:k_tier].tolist())
                             - set(np.argsort(-cand)[:k_tier].tolist()))
            tier_n += min(k_tier, int(sel_p.sum()))
        out.append({
            "position": pos_name, "arm": w["label"],
            "mean abs Δ (PPR)": round(float(np.mean(np.concatenate(d_abs))), 2) if d_abs else None,
            "max abs Δ (PPR)": round(float(np.max(np.concatenate(d_abs))), 2) if d_abs else None,
            "mean abs rank Δ": round(float(np.mean(np.concatenate(rank_moves))), 3)
            if rank_moves else None,
            "tier displacements": f"{displaced} of {tier_n}" if tier_n else None,
            "would ship": "yes" if ship_gate["ship"] else "no"})
    return out


def _gate_sensitivity(sel: dict, ship_gate: dict) -> dict:
    """⭐ IS THE ANSWER RESTING ON A GATE LEVEL I CHOSE? — computed, because a pre-registered bar that
    happens to be the ONLY thing standing between a story and a ship is a bar the reader is entitled to
    see tested.

    ⚠️ A SENSITIVITY, never a re-opened gate (E2.1-r: a gate that only binds when it is inconvenient is
    not a gate). If the readings disagree the pre-registered one still governs — the disclosure is that
    the answer would have been different, not a licence to take the other one."""
    at_nf14 = RC.pooled_ship(winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
                             ordering=sel["ordering"] or {"per_position": {}},
                             pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"),
                             pvalue=sel["pvalue"], dsr_min=0.0)
    no_dsr = {k: v for k, v in ship_gate.items() if k not in ("ship", "framing", "dsr_ok")}
    at_contender = RC.pooled_ship(winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
                                  ordering=sel["ordering"] or {"per_position": {}},
                                  pbo=sel["deflation"].get("pbo"),
                                  dsr=sel["deflation"].get("dsr_contenders"),
                                  pvalue=sel["pvalue"])
    table = {
        "DSR whole-field (THE GATE)": sel["deflation"].get("dsr"),
        "DSR contender-set (reported)": sel["deflation"].get("dsr_contenders"),
        f"ships at pre-registered DSR ≥ {RC.DSR_MIN}": ship_gate["ship"],
        "ships at NF1.4's DSR ≥ 0.0": at_nf14["ship"],
        "ships with the DSR dropped entirely": all(no_dsr.values()),
        "ships on the CONTENDER DSR reading": at_contender["ship"],
    }
    generous = all(no_dsr.values())
    if not generous:
        blocking = [k for k, v in no_dsr.items() if not v]
        reading = (
            "⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING "
            f"IT.** Nothing ships even with the DSR removed ENTIRELY and even on the kinder "
            f"contender-set reading, because `{blocking}` blocks independently. So the verdict is not "
            "an artefact of pre-registering the stricter of the two DSR bars, nor of naming the "
            "whole-field reading as the binding one — a reader who disagrees with either choice "
            "reaches the same verdict.")
    else:
        reading = (
            "⚠️ **THE GATE LEVEL IS LOAD-BEARING.** The pre-registered DSR is the only thing standing "
            "between this story and a ship. **The pre-registered gate GOVERNS** — a bar moved after "
            "seeing the answer is not a bar (E2.1-r) — but a reader is entitled to know it, and the "
            "honest next step is a story that earns more held-out draft classes, not a re-read of "
            "this one.")
    return {"table": table, "reading": reading}


def _power_in_classes(sel: dict, alpha: float = RC.ALPHA, max_n: int = 60) -> dict:
    """⭐ THE MARGIN STATED IN DRAFT CLASSES, not in p-value decimals (NF1.8's 'state the margin in
    ROWS' convention, one unit over) — what separates **underpowered** from **absent**."""
    d = np.asarray(sel.get("per_cohort_delta") or [], dtype=float)
    rec = {"classes now": int(len(d)), "mean Δ (pooled tier MAE)": None, "sd Δ": None,
           "one-sided p": sel.get("pvalue"), "α (single hypothesis)": alpha, "classes needed": None}
    if len(d) >= 3 and float(d.std(ddof=1)) > 1e-12:
        mu, sd = float(d.mean()), float(d.std(ddof=1))
        rec["mean Δ (pooled tier MAE)"] = round(mu, 4)
        rec["sd Δ"] = round(sd, 4)
        if mu > 0:
            from scipy.stats import t as student_t
            for n in range(len(d), max_n + 1):
                if float(student_t.sf(mu / (sd / np.sqrt(n)), n - 1)) <= alpha:
                    rec["classes needed"] = n
                    break
            else:
                rec["classes needed"] = f">{max_n}"
        else:
            rec["classes needed"] = "n/a (the effect is negative)"
    return rec


def _framing_reading(out: dict) -> str:
    pp = out["per_position_disclosure"]
    survivors = [k for k, v in pp["fdr"].items() if v]
    pooled_ok = out["ship_gate"].get("significant")
    if pooled_ok and not survivors:
        return ("⚠️ **THE FRAMING IS LOAD-BEARING, AND THAT IS WORTH SAYING PLAINLY.** The pooled "
                "single-hypothesis test clears α while NO position survives the 3-test BH-FDR. The "
                "pre-registered framing GOVERNS and it was chosen in advance for a stated reason (a "
                "level effect is a-priori common across positions; the ship unit is the whole "
                "constant vector) — but a reader should know that a story framed the other way would "
                "have reached the opposite verdict, which is exactly the disclosure NF-D15 owed in "
                "the other direction.")
    if pooled_ok and survivors:
        return (f"✅ **The two framings AGREE**: the pooled test clears α and `{survivors}` also "
                "survive the 3-test BH-FDR, so the pre-registered choice of framing did not decide "
                "the answer.")
    if not pooled_ok and survivors:
        return (f"⚠️ **The framings DISAGREE in the other direction**: `{survivors}` survive the "
                "per-position BH-FDR while the POOLED test does not clear α. The pre-registered "
                "pooled framing GOVERNS (E2.1-r) — a per-position survivor read as a result here "
                "would be re-framing the hypothesis after seeing which framing passes, which is the "
                "inversion this program keeps closing. It is recorded as a disclosure.")
    return ("✅ **The two framings AGREE**: neither the pooled single-hypothesis test nor any "
            "per-position BH-FDR survivor clears its bar, so the pre-registered choice of framing did "
            "not decide the answer.")


_LIMITATIONS = [
    "⭐ **NO DEPTH-CHART PROVENANCE CAVEAT APPLIES HERE, and that is a deliberate design property "
    "rather than luck.** NF-D14/NF-D15's measured lift carries a hard upper-bound qualifier because "
    "their availability signal reads a WEEK-1 depth chart historically and an AUGUST snapshot live. "
    "NF-D16's forms are estimated from exactly two quantities the board already owns — the served "
    "point projection and the realized rookie fantasy points — so there is no train/serve provenance "
    "asymmetry to bound. This is why `mult_const` was registered as the clean in-fold mean of "
    "`realized / point` rather than inherited from NF-D15's `mean_ratio` foil, which was a mean of a "
    "DEPTH-derived ratio and would have dragged the caveat into a story that touches no depth "
    "feature.",
    "**The in-fold constants are estimated against IN-SAMPLE point projections.** The training rows' "
    "points come from the fold's own slot curve, which was fitted on them, so they are better "
    "calibrated than the held-out points the constant is then applied to. §4 measures the resulting "
    "optimism directly. The direction is CONSERVATIVE — it biases the estimated correction toward 1, "
    "i.e. UNDER-states it, so it cannot manufacture a lift — but it is not zero, and a revival should "
    "estimate the correction against out-of-fold training predictions.",
    "⛔ **QB is out of scope by pre-registration, not by result.** NF-D14 MEASURED the rookie-QB "
    "double-pricing and NF-D15 enforced the exclusion at max drift 0.0; NF-D16 inherits the scope by "
    "IMPORT (`RECALIBRATED_POSITIONS` is `rookie_point_scaling.SCALED_POSITIONS`) so the two stories "
    "cannot drift apart. Whether the rookie-QB point is cold is a separate question this story does "
    "not answer.",
    "**`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is a claim "
    "about a few dozen rookie-seasons across seven draft classes; the paired per-class deltas are "
    "reported so a reader sees the spread rather than only the mean.",
    "**The permutation anchor is WEAK against this hypothesis by construction**, and §4b measures "
    "rather than glosses it: a level is a MARGINAL statistic, so a within-position permutation "
    "preserves it exactly for the additive form. The ACROSS-position permutation is the one that has "
    "to be beaten, and the anchors that do the real work here are the family CEILING and the two "
    "degenerates.",
    "**Do-no-ordering-harm is a rank-correlation constraint, not a promise the board will not move** — "
    "though for the two monotone forms it is a promise the ORDER will not move, which §5 measures at "
    "exactly 0. The PPR magnitudes still change, and §5 reports that churn.",
    "**No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.",
]


if __name__ == "__main__":
    raise SystemExit(main())

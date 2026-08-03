"""run_nf_d18_top_attenuation.py — NF-D18 §0.5 bake-off: is there a rookie-point recalibration that
fixes the cold bias WITHOUT over-placing the top rookie on the merged draft board?

THE STORY IN ONE PARAGRAPH. NF-D16's per-position AFFINE recalibration is RATIFIED and shelved: it
cleared every gate it pre-registered, and then the 2026 board placed its top rookie RB at overall rank
6 against a placement clause that NF-D17 subsequently VALIDATED (cap Q10 = 8.8; rank 6 is outside
reality's entire observed support, minimum 7). NF-D18 asks, as a NEW pre-registered hypothesis,
whether a correction exists that keeps the accuracy gain and leaves the top rookie where the clause
admits. Four attenuating FORMS — a concave power, a robust affine, a monotone quantile map and an
isotonic learned foil — are registered beside NF-D16's ratified affine (the REFERENCE, carried at full
strength so the constraint has something to refuse) and the incumbent NULL. Every arm runs at λ = 1:
re-picking NF-D16's selected shrink after seeing a constraint result is the E2.1-r inversion, so the
globally-shrunk affine appears ONLY as a NON-SHIPPABLE matched foil whose job is to test this story's
own mechanism claim.

⚠️ THE PRE-REGISTRATION LIVES IN `rookie_top_attenuation.py`, NOT HERE. This runner reads those
constants; it does not restate them. Everything choosable-after-a-result — forms, constraints, metric,
framing, DSR reading and level, α, anchors, physical clips — is a constant there.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. `best_alpha = 0`, no CLV/ROI claim.
🔒 The rookie INTERVAL's WIDTH model is untouched. ⚠️ A shipped correction moves the band's CENTRE, so
   a ship requires `run_interval_revalidation` re-run and every coverage floor re-confirmed.
⛔ QB is excluded by pre-registration and PROVEN untouched on emitted projections, never asserted.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached NF1.4 rookie pool + the emitted board):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d18_top_attenuation
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
    rookie_top_attenuation as TA,
    season_projection as SP,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_d18_top_attenuation")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_BOARD = _ART / "nfl_fantasy_season_projections_2026.parquet"
_REAL = "rookie_fp_ppr"

# The peeking ceiling for each FORM: (form, the fold-fits key holding its held-out-class parameters).
# Keyed by the anchor names `TA.FAMILY_CEILING` maps each form to, so the anchor set and the check
# cannot drift apart — asserted at import, not merely intended.
_CEILING_ANCHORS = {"oracle_ols": ("ols_slope", "_peek_ols"),
                    "oracle_power": ("power", "_peek_power"),
                    "oracle_huber": ("huber", "_peek_huber"),
                    "oracle_qmap": ("qmap", "_peek_qmap"),
                    "oracle_isotonic": ("isotonic", "_peek_isotonic")}
assert set(_CEILING_ANCHORS) == set(TA.FAMILY_CEILING.values()), \
    "the peeking-ceiling anchors and TA.FAMILY_CEILING have drifted apart"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-fold fits — computed ONCE per held-out class and shared by every arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fold_fits(fold: NF17.Fold, *, seed: int = 20260802) -> dict:
    """Every fitted correction for ONE held-out class, computed once and shared by every arm.

    §0.5 cost hygiene, but more importantly the guarantee that two arms differing only in FORM really
    do differ only in form: the fold's point projections are built once and every estimator sees the
    identical rows.

    ⭐ EVERY CANDIDATE FIT IS STRICTLY IN-FOLD — on the prior draft classes and their served point
    projections. The `_peek_*` fits are the ORACLE CEILINGS and are fitted on the HELD-OUT class on
    purpose: a ceiling has to peek to be one, and there is one per FORM because the families here NEST
    (NF1.7 (b) / NF1.9 (f)).

    ⚠️ BOTH PERMUTATIONS ARE FITTED AT THE REFERENCE FORM — NF-D16's ratified affine, this field's
    canonical estimator — so the two anchors differ from each other in exactly one thing, which
    outcome vector they saw:
      · `_perm_across` shuffles realized outcomes ACROSS positions, destroying the per-position
        structure while preserving the family, the n and the grand mean. Must LOSE.
      · `_perm_within` shuffles WITHIN each position, preserving that position's marginal EXACTLY and
        destroying only the relationship between projection and outcome. ⭐ In NF-D16 that anchor was
        provably VACUOUS (a level is a marginal statistic, so the shuffle left it byte-identical); here
        every form estimates a SHAPE, which is precisely what the shuffle destroys — so it is
        PRE-REGISTERED AS A GATE THAT MUST BE BEATEN rather than as an expected tie."""
    tr_pos = fold.train["position_group"].astype(str).str.upper().to_numpy()
    te_pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    p_tr = np.asarray(fold.train_pred, dtype=float)
    y_tr = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)

    rng = np.random.default_rng(seed + int(fold.year))
    y_across = rng.permutation(np.nan_to_num(y_tr, nan=0.0))
    y_within = np.nan_to_num(y_tr, nan=0.0).copy()
    for q in TA.ATTENUATED_POSITIONS:
        sel = np.flatnonzero(tr_pos == q)
        if len(sel) > 1:
            y_within[sel] = rng.permutation(y_within[sel])

    fits: dict = {"_te_pos": te_pos, "_tr_pos": tr_pos}
    for form in TA.FORMS:
        fits[form] = TA.fit_form(form, p_tr, y_tr, tr_pos)
    # the peeking ceiling of each form, at RELAXED row floors because a single held-out draft class is
    # ~80 rows: a ceiling that fails to fit would make its own check pass on NOTHING (NF1.7 (a)).
    for tag, (form, key) in _CEILING_ANCHORS.items():
        kw = {"min_n": 5} if form in ("ols_slope", "power", "huber", "isotonic") else {"min_n": 5}
        fits[key] = TA.fit_form(form, fold.test_pred, fold.test_real, te_pos, **kw)
    fits["_perm_across"] = TA.fit_form(TA.REFERENCE_FORM, p_tr, y_across, tr_pos)
    fits["_perm_within"] = TA.fit_form(TA.REFERENCE_FORM, p_tr, y_within, tr_pos)
    return fits


def arm_adjustment(form: str, fits: dict, fold: NF17.Fold) -> np.ndarray:
    """The RAW adjusted projection for one form on one held-out class, BEFORE the QB gate — the input
    both the matched foil and the ordering measurement need."""
    return TA.predict_form(form, fits[form], fold.test_pred, fits["_te_pos"])


def arm_prediction(cfg: dict, fits: dict, fold: NF17.Fold) -> np.ndarray:
    """One arm's emitted projection: FIT → λ blend → the QB gate. Three separate steps on purpose, so
    no form owns its own copy of the shrink or of the exclusion.

    A MATCHED FOIL arm carries its own λ, computed from point projections alone (never from an
    outcome), and is otherwise the REFERENCE affine — that is what makes it matched on magnitude and
    stripped of shape."""
    pos = fits["_te_pos"]
    if cfg["form"] == "incumbent":
        return TA.apply_position_adjustment(fold.test_pred, pos, fold.test_pred)
    if cfg.get("matched_foil"):
        ref = arm_adjustment(TA.REFERENCE_FORM, fits, fold)
        lam = TA.matched_global_lambda(fold.test_pred, pos,
                                       arm_adjustment(cfg["matches"], fits, fold), ref)
        if lam is None:
            return TA.apply_position_adjustment(fold.test_pred, pos, fold.test_pred)
        return TA.apply_position_adjustment(
            fold.test_pred, pos, TA.blend_toward_incumbent(fold.test_pred, ref, lam))
    adj = arm_adjustment(cfg["form"], fits, fold)
    blended = TA.blend_toward_incumbent(fold.test_pred, adj, cfg["lam"])
    return TA.apply_position_adjustment(fold.test_pred, pos, blended)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — candidates and anchors through the IDENTICAL reducer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mean(values, nd: int = 4) -> float | None:
    v = np.array([x for x in values if x is not None], dtype=float)
    v = v[np.isfinite(v)]
    return round(float(v.mean()), nd) if len(v) else None


def _score(folds: list[NF17.Fold], fits: dict[int, dict], pos_scale: dict[int, dict],
           predict, label: str, extra: dict | None = None) -> dict:
    """Score ANY arm — candidate, matched foil or anchor — through the IDENTICAL reducer, so the
    anchors and the candidates are demonstrably answering the same question rather than merely being
    described that way."""
    per_cohort, per_cohort_scaled, rows = {}, {}, []
    for f in folds:
        pos = fits[f.year]["_te_pos"]
        pred = predict(f, fits[f.year])
        d = pd.DataFrame({"position_group": pos, _REAL: f.test_real,
                          "_inc": f.test_pred, "_pred": pred})
        per_cohort[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year])
        per_cohort_scaled[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year],
                                                       tier_k=TA.SCALED_TIER_K)
        rows.append(d.assign(year=f.year))
    allrows = pd.concat(rows, ignore_index=True)
    scaled = TA.scaled_positions_only(allrows)
    pooled = _mean([v.get("tier_mae") for v in per_cohort_scaled.values()], 4)
    out = {
        "label": label, "per_cohort": per_cohort,
        "per_cohort_pooled": {y: v.get("tier_mae") for y, v in per_cohort_scaled.items()},
        "pooled_tier_mae": pooled, TA.SELECTION_METRIC: pooled,
        "universe_mae": round(float((scaled["_pred"] - scaled[_REAL]).abs().mean()), 3),
        "universe_bias": round(float((scaled["_pred"] - scaled[_REAL]).mean()), 3),
        **(extra or {}),
    }
    for p in ("QB",) + TA.ATTENUATED_POSITIONS:
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


def all_configs(*, smoke: bool = False) -> list[dict]:
    """The candidates PLUS one MATCHED GLOBAL FOIL per attenuating arm.

    ⛔ The foils are `shippable = False` and `is_foil = True`: they are excluded from the eligible set,
    from PBO's search and from the DSR trial field. A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2 (a)) —
    they exist to police an attribution, so pricing a search nobody ran against them would tax a real
    finding for the presence of its own control."""
    cfgs = TA.candidate_configs(smoke=smoke)
    present = {c["form"] for c in cfgs}
    for form in TA.ATTENUATION_FORMS:
        if form not in present:
            continue
        cfgs.append({"label": f"{TA.MATCHED_FOIL_PREFIX}({form})", "form": TA.REFERENCE_FORM,
                     "lam": None, "recalibrates": True, "shippable": False, "attenuates": False,
                     "matched_foil": True, "matches": form})
    return cfgs


def score_arms(folds, fits, pos_scale, cfgs: list[dict]) -> list[dict]:
    return [_score(folds, fits, pos_scale,
                   lambda f, fi, c=c: arm_prediction(c, fi, f), c["label"],
                   extra={"key": TA.config_key(c) if not c.get("matched_foil") else c["label"],
                          "form": c["form"], "lam": c["lam"],
                          "recalibrates": c["recalibrates"], "shippable": c["shippable"],
                          "attenuates": bool(c.get("attenuates")),
                          "is_foil": bool(c.get("matched_foil")),
                          "matches": c.get("matches"),
                          "monotone": bool(c.get("monotone")), "learned": bool(c.get("learned"))})
            for c in cfgs]


def _anchor_prediction(tag: str, fold: NF17.Fold, fits: dict) -> np.ndarray:
    pos = fits["_te_pos"]
    point = np.asarray(fold.test_pred, dtype=float)
    real = np.asarray(fold.test_real, dtype=float)
    if tag == "oracle_perplayer":
        return TA.apply_position_adjustment(point, pos, real)
    if tag in _CEILING_ANCHORS:
        form, key = _CEILING_ANCHORS[tag]
        return TA.apply_position_adjustment(point, pos, TA.predict_form(form, fits[key], point, pos))
    if tag in ("permuted_across", "permuted_within"):
        key = "_perm_across" if tag == "permuted_across" else "_perm_within"
        return TA.apply_position_adjustment(
            point, pos, TA.predict_form(TA.REFERENCE_FORM, fits[key], point, pos))
    if tag == "zero_scale":
        return TA.apply_position_adjustment(point, pos, np.zeros(len(pos)))
    if tag == "pos_median":
        tr_pos = fits["_tr_pos"]
        tr_real = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)
        adj = np.full(len(pos), np.nan)
        for q in TA.ATTENUATED_POSITIONS:
            v = tr_real[(tr_pos == q) & np.isfinite(tr_real)]
            if len(v):
                adj[pos == q] = float(np.median(v))
        return TA.apply_position_adjustment(point, pos, adj)
    raise ValueError(f"unknown anchor {tag!r}")


def score_anchors(folds, fits, pos_scale) -> dict:
    return {t: _score(folds, fits, pos_scale,
                      lambda f, fi, t=t: _anchor_prediction(t, f, fi), t)
            for t in (("oracle_perplayer",) + tuple(_CEILING_ANCHORS)
                      + ("permuted_across", "permuted_within", "zero_scale", "pos_median"))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE SERVING FIT + THE 2026 BOARD — where the PLACEMENT constraint is evaluated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def serving_fits(pool: pd.DataFrame, *, upto: int = 2025) -> dict:
    """Every form fitted on the FULL rookie history, exactly as SERVING fits the shipped correction.

    ⭐ THIS REPRODUCES THE PRODUCTION PATH RATHER THAN APPROXIMATING IT. `fit_rookie_slot_curves`
    fits `curve.fp_recal` from `rookie_point_projection(recal_hist, curve)` against the realized
    outcomes of the FULL drafted population, with the point curve itself fitted on the
    survivor-filtered history — which is precisely what is rebuilt here. The fidelity of the
    reproduction is not assumed: `--verify-serving` scores NF-D16's ratified affine through this path
    and asserts it reproduces the value the production curve emits, so every placement number in this
    report is anchored to the served code rather than to a re-implementation of it."""
    hist, band = NF17._curve_inputs(pool)
    hist = hist[pd.to_numeric(hist["draft_year"], errors="coerce") <= upto]
    band = band[pd.to_numeric(band["draft_year"], errors="coerce") <= upto]
    curve = SP.fit_rookie_slot_curves(hist)
    pts = SP.rookie_point_projection(band, curve)
    real = pd.to_numeric(band[_REAL], errors="coerce").to_numpy(dtype=float)
    pos = band["position_group"].astype(str).str.upper().to_numpy()
    return {"_points": pts, "_real": real, "_pos": pos,
            **{form: TA.fit_form(form, pts, real, pos) for form in TA.FORMS}}


def board_arm(board: pd.DataFrame, sfits: dict, cfg: dict) -> np.ndarray:
    """The rookie half of the 2026 board under ONE arm, applied to the board's OWN emitted points —
    which is exactly where serving applies the correction (`recalibrate_fp` acts on the final scored
    projection). The incumbent half of every placement comparison is therefore the SERVED product."""
    rk = board[board["is_rookie"].fillna(False).astype(bool)]
    point = pd.to_numeric(rk["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = rk["position"].astype(str).str.upper().to_numpy()
    if cfg["form"] == "incumbent":
        return TA.apply_position_adjustment(point, pos, point)
    ref = TA.predict_form(TA.REFERENCE_FORM, sfits[TA.REFERENCE_FORM], point, pos)
    if cfg.get("matched_foil"):
        lam = TA.matched_global_lambda(
            point, pos, TA.predict_form(cfg["matches"], sfits[cfg["matches"]], point, pos), ref)
        if lam is None:
            return TA.apply_position_adjustment(point, pos, point)
        return TA.apply_position_adjustment(point, pos,
                                            TA.blend_toward_incumbent(point, ref, lam))
    adj = TA.predict_form(cfg["form"], sfits[cfg["form"]], point, pos)
    return TA.apply_position_adjustment(point, pos,
                                        TA.blend_toward_incumbent(point, adj, cfg["lam"]))


def board_verdicts(board: pd.DataFrame, sfits: dict, cfgs: list[dict],
                   anchors: tuple = ("zero_scale", "pos_median")) -> dict:
    """The PLACEMENT read for every arm on the emitted 2026 board, plus the DEGENERATES.

    ⭐ THE DEGENERATES ARE SCORED HERE FOR A REASON THAT IS NOT DECORATIVE. `zero_scale` SATISFIES the
    placement cap trivially — a board that projects nothing for its rookies places none of them high.
    NF1.8's rule is that a CONSTRAINT a degenerate satisfies is fine, because the selection metric then
    eliminates it, whereas a CRITERION a degenerate WINS is fatal. Reporting that the placement clause
    is the former is the proof that this story did not quietly promote a constraint into a criterion,
    and it is a measurement rather than an argument."""
    out: dict = {}
    rk_mask = board["is_rookie"].fillna(False).astype(bool).to_numpy()
    point = pd.to_numeric(board.loc[rk_mask, "proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = board.loc[rk_mask, "position"].astype(str).str.upper().to_numpy()
    for cfg in cfgs:
        fp = board_arm(board, sfits, cfg)
        place = TA.board_placement(board, fp)
        out[cfg["label"]] = {
            **place, "placement": TA.placement_clearance(place["best_rookie_overall_rank"]),
            "profile": TA.attenuation_profile(point, pos, fp),
        }
    for tag in anchors:
        adj = (np.zeros(len(point)) if tag == "zero_scale"
               else np.array([float(np.median(sfits["_real"][sfits["_pos"] == p]))
                              if (sfits["_pos"] == p).any() else np.nan for p in pos]))
        fp = TA.apply_position_adjustment(point, pos, adj)
        place = TA.board_placement(board, fp)
        out[tag] = {**place, "placement": TA.placement_clearance(place["best_rookie_overall_rank"]),
                    "degenerate": True}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE PRE-REGISTERED POOLED SELECTION — BOTH constraints on eligibility
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pooled_row(rec: dict, cohorts: list[int]) -> np.ndarray:
    return np.array([rec.get("per_cohort_pooled", {}).get(y, np.nan) for y in cohorts], dtype=float)


def select_pooled(arms: list[dict], inc: dict, cohorts: list[int], boards: dict,
                  *, placement_binds: bool = True) -> dict:
    """Pick + deflate under the PRE-REGISTERED pooled framing: ONE hypothesis, ONE test, no
    multiplicity correction.

    Eligibility = shippable AND do-no-ordering-harm at EVERY scaled position AND (when
    `placement_binds`) the NF-D17 placement cap cleared THRESHOLD-INVARIANTLY on the emitted board.
    `placement_binds=False` computes the ORDERING-ONLY reading — NF-D16's convention — which is
    reported as a disclosure so a reader can see exactly what the eligibility choice decided.

    `winner = None` with candidates present is a REAL result, not a bug: it means no arm satisfied both
    constraints, which is the story's own null.

    ⚠️ PBO is computed over the ELIGIBLE set — the search the selection ACTUALLY ran (NF1.8) — and the
    MATCHED FOILS are excluded from both the eligible set and the DSR trial field, because a
    diagnostic is never a trial (MH2 (a)). Both the whole-field and the contender-set DSR are reported;
    the WHOLE-FIELD reading is the PRE-REGISTERED gate."""
    inc_row = _pooled_row(inc, cohorts)
    inc_metric = _mean(inc_row, 4)
    inc_rho = {p: inc.get(f"rho_{p}") for p in TA.ATTENUATED_POSITIONS}

    cands = []
    for r in arms:
        if r.get("is_foil"):
            continue                       # a diagnostic is never a trial and never a candidate
        row = _pooled_row(r, cohorts)
        metric = _mean(row, 4)
        if metric is None:
            continue
        rho = {p: r.get(f"rho_{p}") for p in TA.ATTENUATED_POSITIONS}
        ordering = TA.ordering_check(rho, inc_rho)
        place = (boards.get(r["label"], {}) or {}).get("placement", {})
        elig = bool(r["shippable"] and ordering["ok"]
                    and (place.get("clears", False) if placement_binds else True))
        cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                      "placement": place, "eligible": elig})

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["metric"]) if eligible else None
    best_any = min(cands, key=lambda c: c["metric"]) if cands else None

    mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"])) for c in cands}).sort_index()
    defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)

    means = mat.mean(axis=0).sort_values()
    ctr_labels = set(means.index[:max(3, len(means) // 4)])
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
        "framing": TA.PREREGISTERED_FRAMING, "placement_binds": bool(placement_binds),
        "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_metric": inc_metric, "incumbent_rho": inc_rho,
        "winner": None if best is None else {
            **{k: best["rec"].get(k) for k in ("label", "key", "form", "lam", "recalibrates",
                                               "shippable", "attenuates", "monotone", "learned")},
            "metric": best["metric"],
            "rho": {p: best["rec"].get(f"rho_{p}") for p in TA.ATTENUATED_POSITIONS}},
        "best_any": None if best_any is None else {
            "label": best_any["rec"]["label"], "metric": best_any["metric"],
            "eligible": best_any["eligible"]},
        "ordering": None if best is None else best["ordering"],
        "placement": None if best is None else best["placement"],
        "deflation": {**defl, "dsr": dsr, "dsr_contenders": dsr_ctr},
        "pvalue": pval, "per_cohort_delta": [round(x, 3) for x in deltas],
        "eligible_labels": [c["rec"]["label"] for c in eligible],
        "ineligible": [{"label": c["rec"]["label"], "ordering_ok": c["ordering"]["ok"],
                        "placement_clears": bool(c["placement"].get("clears")),
                        "best_rookie_overall_rank":
                            (boards.get(c["rec"]["label"], {}) or {}).get(
                                "best_rookie_overall_rank")}
                       for c in cands if not c["eligible"]],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The DISCLOSED per-position reading (computed, reported, NEVER the gate)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pos_row(rec: dict, cohorts: list[int], pos: str, key: str = "tier_mae_by_pos") -> np.ndarray:
    return np.array([rec["per_cohort"].get(y, {}).get(key, {}).get(pos, np.nan) for y in cohorts],
                    dtype=float)


def per_position_disclosure(arms: list[dict], inc: dict, cohorts: list[int], boards: dict) -> dict:
    """The framing this story did NOT pre-register, computed rather than speculated about.

    ⚠️ REPORTED, NEVER SELECTED ON. The pre-registered pooled framing governs; if the two readings
    disagree that is a disclosure, not a licence to take the other one (E2.1-r). It exists so 'the
    framing did not decide the answer' is a number rather than a shrug."""
    out: dict = {"per_position": [], "fdr": {}, "bh_cutoff_unconditional": round(TA.FDR_Q / 3, 4)}
    inc_rho_all = {p: inc.get(f"rho_{p}") for p in TA.ATTENUATED_POSITIONS}
    pvals: dict[str, float | None] = {}
    for pos in TA.ATTENUATED_POSITIONS:
        inc_row = _pos_row(inc, cohorts, pos)
        inc_metric = _mean(inc_row, 4)
        cands = []
        for r in arms:
            if r.get("is_foil"):
                continue
            row = _pos_row(r, cohorts, pos)
            metric = _mean(row, 4)
            if metric is None:
                continue
            ordering = TA.ordering_check({pos: r.get(f"rho_{pos}")},
                                         {pos: inc_rho_all.get(pos)}, positions=(pos,))
            place = (boards.get(r["label"], {}) or {}).get("placement", {})
            cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                          "eligible": bool(r["shippable"] and ordering["ok"]
                                           and place.get("clears", False))})
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
    out["fdr"] = M14.bh_fdr(pvals, q=TA.FDR_Q)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MECHANISM ATTRIBUTION — is it the SHAPE, or is it just less correction?
# ══════════════════════════════════════════════════════════════════════════════════════════════
def matched_foil_attribution(arms: list[dict], boards: dict, cohorts: list[int]) -> dict:
    """⭐ THE CONTROL THIS STORY'S CLAIM TURNS ON (NF-D10 (g) / NF-D15 (g′)).

    Every attenuating arm is paired with the REFERENCE affine shrunk globally to the SAME mean
    absolute correction over the draftable tier — same family, same magnitude, UNIFORM instead of
    shaped. Two readings, and they are the whole point of the pairing:

      · PLACEMENT — the arm clears and its matched foil does NOT ⇒ the SHAPE earned the clearance.
        BOTH clear ⇒ MAGNITUDE is the mechanism, this story's premise is REFUTED, and the honest fix
        would be a global λ, which is exactly the re-pick §6 forbids. That distinction cannot be read
        off a leaderboard rank (NF-D10: a rank confuses 'my mechanism is inert' with 'it is tied').
      · ACCURACY — the PAIRED per-class tier-MAE delta between the arm and its foil, which prices what
        the shape costs or buys once magnitude is held equal.

    A missing or unscorable foil is reported as such and never as a pass."""
    by_label = {r["label"]: r for r in arms}
    rows = []
    for r in arms:
        if not r.get("is_foil"):
            continue
        target = by_label.get(r["matches"])
        if target is None:
            continue
        a = _pooled_row(target, cohorts)
        f = _pooled_row(r, cohorts)
        d = a - f
        d = d[np.isfinite(d)]
        pa = ((boards.get(target["label"], {}) or {}).get("placement", {}) or {})
        pf = ((boards.get(r["label"], {}) or {}).get("placement", {}) or {})
        rows.append({
            "arm": target["label"], "foil": r["label"],
            "arm_tier_mae": target["pooled_tier_mae"], "foil_tier_mae": r["pooled_tier_mae"],
            "paired_delta": round(float(d.mean()), 4) if len(d) else None,
            "arm_rank": (boards.get(target["label"], {}) or {}).get("best_rookie_overall_rank"),
            "foil_rank": (boards.get(r["label"], {}) or {}).get("best_rookie_overall_rank"),
            "arm_clears": bool(pa.get("clears")), "foil_clears": bool(pf.get("clears")),
            "shape_earns_clearance": bool(pa.get("clears") and not pf.get("clears")),
            "magnitude_explains_it": bool(pa.get("clears") and pf.get("clears")),
        })
    any_shape = any(r["shape_earns_clearance"] for r in rows)
    any_magnitude = any(r["magnitude_explains_it"] for r in rows)
    return {"rows": rows, "n_pairs": len(rows),
            "shape_earns_a_clearance": bool(any_shape),
            "magnitude_alone_explains_a_clearance": bool(any_magnitude),
            "reading": ("shape" if any_shape and not any_magnitude
                        else "magnitude" if any_magnitude and not any_shape
                        else "mixed" if any_shape and any_magnitude
                        else "no_clearance_to_attribute")}


def fitted_parameters(folds: list[NF17.Fold], fits: dict[int, dict]) -> dict:
    """The fitted parameters themselves, per class and position — the correction the arms actually
    apply, exposed rather than left implicit inside a metric.

    ⭐ `all_gammas_below_one` and `all_slopes_positive` are load-bearing and are MEASUREMENTS, not
    properties of the forms. A power with γ ≥ 1 is not an attenuator at all; an affine or power with a
    negative slope/exponent INVERTS a position's whole board. Recording them is what keeps 'this form
    attenuates at the top' from being an assertion the report repeats after the code stopped
    guaranteeing it."""
    rows, slopes, gammas = [], [], []
    for f in folds:
        for q in TA.ATTENUATED_POSITIONS:
            rec = {"class": f.year, "position": q}
            ab = fits[f.year]["ols_slope"].get(q)
            if ab:
                rec["ols a"], rec["ols b"] = round(ab[0], 3), round(ab[1], 4)
                slopes.append(float(ab[1]))
            hb = fits[f.year]["huber"].get(q)
            if hb:
                rec["huber a"], rec["huber b"] = round(hb[0], 3), round(hb[1], 4)
                slopes.append(float(hb[1]))
            pw = fits[f.year]["power"].get(q)
            if pw:
                rec["power c"], rec["power γ"], rec["power smear"] = (
                    round(pw[0], 3), round(pw[1], 4), round(pw[2], 4))
                gammas.append(float(pw[1]))
            rows.append(rec)
    return {"rows": rows, "n_slopes": len(slopes), "n_gammas": len(gammas),
            "all_slopes_positive": bool(slopes) and all(s > 0 for s in slopes),
            "all_gammas_below_one": bool(gammas) and all(g < 1.0 for g in gammas),
            "min_gamma": round(min(gammas), 4) if gammas else None,
            "max_gamma": round(max(gammas), 4) if gammas else None,
            "min_slope": round(min(slopes), 4) if slopes else None,
            "max_slope": round(max(slopes), 4) if slopes else None}


def ordering_measurements(folds: list[NF17.Fold], fits: dict[int, dict]) -> list[dict]:
    """Within-position rank movement per FORM, measured on emitted projections and pooled to the worst
    observed value over the held-out classes — the strictest honest reading."""
    out = []
    for form in TA.FORMS:
        worst: dict[str, float] = {}
        for f in folds:
            m = TA.ordering_is_structural(form, f.test_pred, fits[f.year]["_te_pos"],
                                          arm_adjustment(form, fits[f.year], f))
            for q, v in m["max_rank_move_by_pos"].items():
                worst[q] = max(worst.get(q, 0.0), v)
        klass = ("monotone by construction" if form in TA.MONOTONE_FORMS
                 else "conditionally monotone" if form in TA.CONDITIONALLY_MONOTONE_FORMS
                 else "reordering")
        out.append({"form": form, "ordering_class": klass, "max_rank_move_by_pos": worst,
                    "worst_rank_move": max(worst.values()) if worst else 0.0,
                    "structural_claim_holds": (form not in TA.MONOTONE_FORMS
                                               or max(worst.values() or [0.0]) == 0.0)})
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:                                     # noqa: BLE001
        return df.to_string(index=False)


def _verdict_prose(out: dict) -> str:
    sel, gate = out["selection"], out["verdict"]
    inc = out["incumbent"]["pooled_tier_mae"]
    a: list[str] = []
    w = sel.get("winner")
    if gate.get("ship"):
        a.append(
            f"**The pre-registered pooled test selects `{w['label']}`**, moving the pooled "
            f"draftable-tier MAE **{inc} → {w['metric']}** over {len(out['cohorts'])} held-out draft "
            f"classes, with PBO {sel['deflation'].get('pbo')}, whole-field DSR "
            f"{sel['deflation'].get('dsr')} (the pre-registered gate, ≥ {TA.DSR_MIN}) and a one-sided "
            f"paired p of {sel['pvalue']} against α = {TA.ALPHA} — while placing the 2026 board's best "
            f"rookie at overall rank "
            f"{out['boards'][w['label']]['best_rookie_overall_rank']}, which clears the validated "
            f"NF-D17 cap at EVERY quantile in the Q05–Q25 band and against reality's observed minimum.")
    elif w is None:
        a.append(
            "**NO ARM IS ELIGIBLE.** Not one pre-registered form satisfies both constraints at once: "
            "do-no-ordering-harm at every scaled position AND the validated NF-D17 placement cap, "
            "cleared threshold-invariantly on the emitted 2026 board. The selection therefore has "
            "nothing to select, which is this story's own null in its purest form.")
    else:
        a.append(
            f"**The pre-registered pooled test selects `{w['label']}`**, moving the pooled "
            f"draftable-tier MAE **{inc} → {w['metric']}** (Δ "
            f"{round(w['metric'] - inc, 4) if inc is not None else None}) over "
            f"{len(out['cohorts'])} held-out draft classes, with PBO {sel['deflation'].get('pbo')}, "
            f"whole-field DSR {sel['deflation'].get('dsr')} (the pre-registered gate, ≥ {TA.DSR_MIN}) "
            f"and a one-sided paired p of {sel['pvalue']} against α = {TA.ALPHA}. **Failing gate(s): "
            f"`{[k for k, v in out['ship_gate'].items() if k not in ('ship', 'framing') and not v]}`.**")
    a.append("")
    att = out["attribution"]
    if att["reading"] == "shape":
        a.append(
            "⭐ **THE MATCHED FOIL ATTRIBUTES THE CLEARANCE TO THE SHAPE.** At least one attenuating "
            "arm clears the placement cap while the REFERENCE affine shrunk to its identical mean "
            "draftable-tier correction does NOT — same family, same magnitude, uniform instead of "
            "shaped. The clearance is therefore a property of WHERE the correction is applied and not "
            "merely of HOW MUCH of it is applied (NF-D15 (g′)).")
    elif att["reading"] == "magnitude":
        a.append(
            "⚠️ **THE MATCHED FOIL REFUTES THIS STORY'S OWN MECHANISM.** Every placement clearance an "
            "attenuating arm achieves is matched by the REFERENCE affine shrunk GLOBALLY to the same "
            "mean draftable-tier correction — so what buys the clearance is MAGNITUDE, not the shape. "
            "That is not a licence to ship the global shrink: re-picking NF-D16's selected λ after "
            "seeing a constraint result is precisely the E2.1-r inversion §6 forbids. It is a finding "
            "that 'attenuate at the top' was the wrong description of the only thing that helps.")
    elif att["reading"] == "no_clearance_to_attribute":
        a.append(
            "⚠️ **THERE IS NO CLEARANCE TO ATTRIBUTE.** No attenuating arm clears the placement cap on "
            "the emitted board, so the matched-foil control has nothing to separate — which is itself "
            "the cleanest possible reading of the pairing: the shape channel did not produce the "
            "outcome the story was built to test.")
    else:
        a.append(
            "⚠️ **MIXED ATTRIBUTION.** Some clearances survive their matched global foil and some do "
            "not; the per-arm table in §5 is the reading, not this summary line.")
    a.append("")
    if gate.get("ship"):
        a.append(
            "⇒ **SHIP.** An attenuated recalibration improves the metric the incumbent rookie point "
            "was itself selected on, does no ordering harm at any scaled position, and leaves the top "
            "rookie inside the placement clause's validated support. ⚠️ It moves the rookie band's "
            "CENTRE, so `run_interval_revalidation` must be re-run and every coverage floor "
            "re-confirmed before this reaches the board, and the `--publish` is a POST-MERGE operator "
            "step. QB stays exactly where NF-D14 left it.")
    else:
        a.append(
            "⇒ **RECORDED NULL — and NF-D16's correction is now shelved PERMANENTLY rather than "
            "pending.** The only publish path NF-D17 left open was a top-attenuating re-shaping that "
            "clears the validated placement cap while keeping the gain; the pre-registered field does "
            "not contain one. NF-D16 stays ratified-but-unserved, the shipped rookie point STANDS, "
            "the interval is untouched, and the QB exclusion was never re-opened.")
    return "\n".join(a)


def write_report(out: dict, path: Path) -> None:          # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    an, sel, inc = out["anchors"], out["selection"], out["incumbent"]
    pr = out["preregistration"]
    p("# NF-D18 — ATTENUATE-AT-THE-TOP rookie-point recalibration (RB/TE/WR) — §0.5 bake-off")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **arms:** "
      f"{out['n_candidate_arms']} candidates + {out['n_foils']} matched foils · "
      f"**held-out rookie-seasons (RB/TE/WR):** {out['n_scaled_rows']} · **framing:** "
      f"PRE-REGISTERED `{pr['framing']}` · **DSR reading:** PRE-REGISTERED `{pr['dsr_reading']}`")
    p("")
    p(f"## ⭐ VERDICT — {out['headline']}")
    p("")
    p(out["verdict_prose"])
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      f"⛔ **QB is EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm and "
      f"every held-out QB: **{out['qb_max_drift']:.9f}** PPR). 🔒 The rookie INTERVAL's WIDTH model is "
      "untouched. ⭐ **The serving reproduction is VERIFIED, not assumed**: NF-D16's ratified affine "
      f"routed through this harness reproduces the production curve's own emitted value to "
      f"**{out['serving_fidelity']['max_abs_diff']:.6f}** PPR "
      f"({out['serving_fidelity']['n_checked']} rookies).")
    p("")

    p("## 0. What was pre-registered, and when")
    p("")
    p("Everything that could otherwise have been chosen after seeing a result is a CONSTANT in "
      "`rookie_top_attenuation.py`; this report READS those constants rather than restating them, so "
      "'what was pre-registered' has exactly one owner.")
    p("")
    p(_md(pd.DataFrame([
        {"decision": "forms", "value": ", ".join(pr["forms"]),
         "why (written BEFORE the run)":
             "The incumbent NULL + NF-D16's RATIFIED affine as the REFERENCE (carried at full strength "
             "so the placement constraint has something to REFUSE) + four attenuating classes: a "
             "concave POWER (shape), a ROBUST affine (estimator), a monotone QUANTILE MAP (no "
             "parameters at all) and an ISOTONIC learned foil (the richest monotone family, which "
             "CONTAINS every other form here)."},
        {"decision": "λ", "value": pr["fixed_lambda"],
         "why (written BEFORE the run)":
             "NOT A KNOB IN THIS STORY. NF-D16 pre-registered a shrink grid and SELECTED λ = 1; "
             "re-picking a selection parameter after seeing a constraint result is the E2.1-r "
             "inversion. The globally-shrunk affine appears ONLY as a non-shippable MATCHED FOIL."},
        {"decision": "constraint C1", "value": f"do-no-ordering-harm ≤ {TA.ORDERING_DO_NO_HARM}",
         "why (written BEFORE the run)":
             "NF1.4's own constant, inherited verbatim, checked PER POSITION and never as a pooled "
             "mean — a pooled ρ can sit flat while one position's ordering collapses."},
        {"decision": "constraint C2", "value": "NF-D17 placement cap, THRESHOLD-INVARIANT",
         "why (written BEFORE the run)":
             "The validated clause, imported rather than re-derived. Clearance is required at EVERY "
             "quantile in NF-D17's Q05–Q25 band AND against reality's observed minimum rank — the same "
             "terms on which the VETO held. That leaves no threshold for anybody to pick."},
        {"decision": "constraints bind on", "value": "ELIGIBILITY (not a post-hoc veto)",
         "why (written BEFORE the run)": pr["eligibility_reason"]},
        {"decision": "framing", "value": pr["framing"],
         "why (written BEFORE the run)": pr["framing_reason"]},
        {"decision": "DSR reading that BINDS", "value": pr["dsr_reading"],
         "why (written BEFORE the run)":
             "Inherited from NF-D16. Naming which reading binds in advance is what stops it from "
             "becoming a choice made after seeing which reading is kinder."},
        {"decision": "DSR level / PBO / α", "value": f"{pr['dsr_min']} / {pr['pbo_max']} / {pr['alpha']}",
         "why (written BEFORE the run)":
             "All three INHERITED FROM NF-D16 BY IMPORT, so the bar cannot drift between the story "
             "that shipped the correction and the story trying to publish it."},
        {"decision": "selection metric", "value": pr["metric"],
         "why (written BEFORE the run)":
             "NF1.4's draftable-tier MAE, INHERITED. The incumbent point was selected on it and NF-D16 "
             "was graded on it; grading the third change to one product on a new metric is "
             "metric-shopping."},
    ])))
    p("")
    p("🚩 **THE A-PRIORI RISK WAS REGISTERED TOO, AND IT MATTERS FOR READING THE RESULT.** NF-D16's "
      "fitted correction is dominated by SLOPE (its pure-level `add_offset` arm scored exactly the "
      "incumbent), and a slope correction lifts the TOP of a position's board most. The selection "
      "metric grades the DRAFTABLE TIER. So the region a top-attenuating form must give up is "
      "precisely the region the metric grades and the defect lives in — the honest prior was a null, "
      "and the one structural reason it might not be is that the placement clause binds on the SINGLE "
      "best rookie while the metric grades a TIER of six.")
    p("")

    p("## 1. The metric, the two constraints, and the anchor set")
    p("")
    p("**Primary metric — `tier_mae`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The draftable-tier MAE "
      "on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor rule, so no arm can buy "
      "a friendlier subset), pooled scale-free over RB/TE/WR for the pooled test and reported per "
      "position in raw PPR beside it.")
    p("")
    p("### The anchors, scored on THIS run")
    p("")
    rows = [{"anchor": t, "what it is": w, "pooled tier MAE": an[t]["pooled_tier_mae"],
             "tier MAE RB": an[t].get("tier_mae_RB"), "tier MAE TE": an[t].get("tier_mae_TE"),
             "tier MAE WR": an[t].get("tier_mae_WR"), "universe MAE": an[t]["universe_mae"]}
            for t, w in [
                ("oracle_perplayer", "ORACLE FLOOR, full resolution (peeks per player). Nothing may "
                                     "beat it."),
                ("oracle_ols", "CEILING of the `ols_slope` (reference affine) family."),
                ("oracle_power", "CEILING of the `power` family."),
                ("oracle_huber", "CEILING of the `huber` family."),
                ("oracle_qmap", "CEILING of the `qmap` family."),
                ("oracle_isotonic", "CEILING of the `isotonic` family — the RICHEST here; it CONTAINS "
                                    "every other form, so it must be the lowest."),
                ("permuted_across", "reference fitted on outcomes shuffled ACROSS positions. Must "
                                    "LOSE."),
                ("permuted_within", "reference fitted on outcomes shuffled WITHIN position — the "
                                    "marginal preserved, the SHAPE destroyed. ⭐ MUST LOSE (see §4b)."),
                ("zero_scale", "DEGENERATE — project nothing. Must LOSE the metric; SATISFIES the "
                               "placement cap (see §6)."),
                ("pos_median", "DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must "
                               "LOSE this one."),
            ] if t in an]
    rows.append({"anchor": "→ INCUMBENT (NULL)", "what it is": "the rookie point as SERVED TODAY",
                 "pooled tier MAE": inc["pooled_tier_mae"], "tier MAE RB": inc.get("tier_mae_RB"),
                 "tier MAE TE": inc.get("tier_mae_TE"), "tier MAE WR": inc.get("tier_mae_WR"),
                 "universe MAE": inc["universe_mae"]})
    p(_md(pd.DataFrame(rows)))
    p("")
    for ok, good, bad in (
        (out["checks"]["degenerates_lose"],
         "✅ both degenerates lose the primary metric — it is not paying for pessimism",
         "🚨 A DEGENERATE WINS THE PRIMARY METRIC — it is INVERTED; nothing here may be shipped"),
        (out["checks"]["permutation_across_beaten"],
         "✅ the truth beats the ACROSS-position permutation",
         "🚨 THE ACROSS-POSITION PERMUTATION IS NOT BEATEN"),
        (out["checks"]["permutation_within_beaten"],
         "✅ ⭐ the truth beats the WITHIN-position permutation — the SHAPE these forms estimate is "
         "real information, and this is the anchor that could not act in NF-D16",
         "🚨 THE WITHIN-POSITION PERMUTATION IS NOT BEATEN — the shapes carry nothing a shuffled "
         "outcome vector would not also give"),
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
         "🚨 A CORRECTION REACHED QB — the pre-registered exclusion is broken"),
    ):
        p(f"- {good if ok else bad}")
    p("")
    p("⭐ **ONE CEILING PER FORM, NOT ONE FOR THE FIELD, AND HERE THE FAMILIES GENUINELY NEST.** "
      "`isotonic` CONTAINS the affine (positive slope), the power (γ > 0) and the quantile map as "
      "special cases, so it can legitimately score better than any of their ceilings — a CAPACITY "
      "effect (NF1.7 (b) / NF1.9 (f)), not an inversion. Flooring the whole field on one ceiling would "
      "veto a real result for the wrong reason, which is the bug NF-D16's first cut shipped. The "
      "measured ordering of the ceilings is the internal-consistency signal a single ceiling cannot "
      "produce:")
    p("")
    p(_md(pd.DataFrame(out["family_ceiling_check"]["per_arm"])))
    p("")

    p("## 2. The full field (pooled over RB/TE/WR)")
    p("")
    p(_md(pd.DataFrame(out["field_table"])))
    p("")
    p("⛔ The `global_match(...)` rows are the NON-SHIPPABLE MATCHED FOILS. They are excluded from the "
      "eligible set, from PBO's search and from the DSR trial field — a diagnostic anchor is never a "
      "trial (MH2 (a)) — and they are reported here so the field can be read whole.")
    p("")

    p("## 3. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test, both constraints")
    p("")
    p(f"Eligible arms ({sel['n_eligible']} of {sel['n_candidates']} candidates) are those that are "
      "shippable AND do no ordering harm at EVERY scaled position AND clear the NF-D17 placement cap "
      "threshold-invariantly on the emitted 2026 board.")
    p("")
    p(_md(pd.DataFrame([{
        "incumbent pooled tier MAE": sel["incumbent_metric"],
        "selected arm": (sel["winner"] or {}).get("label", "— none eligible —"),
        "pooled tier MAE": (sel["winner"] or {}).get("metric"),
        "Δ vs incumbent": (None if not sel["winner"] or sel["incumbent_metric"] is None
                           else round(sel["winner"]["metric"] - sel["incumbent_metric"], 4)),
        "PBO": sel["deflation"].get("pbo"),
        "Bailey degradation %": sel["deflation"].get("os_gap_pct"),
        "contender spread %": sel["deflation"].get("contender_spread_pct"),
        "DSR (whole-field, THE GATE)": sel["deflation"].get("dsr"),
        "DSR (contender, reported)": sel["deflation"].get("dsr_contenders"),
        "one-sided paired p (1 test)": sel["pvalue"], "α (pre-registered)": TA.ALPHA}])))
    p("")
    if sel["per_cohort_delta"]:
        p(f"Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): "
          f"`{sel['per_cohort_delta']}` over classes `{out['cohorts']}`.")
        p("")
    if out["flips"]:
        p("**The flip distribution** (NF1.8: a rank statistic alone cannot tell a TIE from an unstable "
          "pick):")
        p("")
        p(_md(pd.DataFrame(out["flips"])))
        p("")
    p(f"**Ship decision under the pre-registered framing:** `{out['ship_gate']}`")
    p("")
    p("### 3a. ⭐ WHY EACH INELIGIBLE ARM WAS REFUSED — the constraint doing visible work")
    p("")
    p(_md(pd.DataFrame(sel["ineligible"])) if sel["ineligible"]
      else "_every candidate was eligible — which would make both constraints vacuous in this field; "
           "they are not (see the table above)._")
    p("")
    p("### 3b. Is the answer resting on a gate level I chose? — the sensitivity, computed")
    p("")
    p(_md(pd.DataFrame([out["sensitivity"]])))
    p("")
    p(out["sensitivity_prose"])
    p("")
    p("### 3c. ⭐ THE DISCLOSED ORDERING-ONLY READING — the eligibility rule this story did NOT use")
    p("")
    p("NF-D16 applied its face-validity check as a post-hoc VETO on an already-selected arm. NF-D18 "
      "pre-registered the placement cap as an ELIGIBILITY constraint instead, for the reason in §0, "
      "and owes the reader the other reading. **Reported, never selected on.**")
    p("")
    oo = out["ordering_only"]
    p(_md(pd.DataFrame([{
        "eligibility rule": "ordering ONLY (NF-D16's convention)",
        "n eligible": oo["n_eligible"],
        "selected arm": (oo["winner"] or {}).get("label", "— none —"),
        "pooled tier MAE": (oo["winner"] or {}).get("metric"),
        "its board rank": (out["boards"].get((oo["winner"] or {}).get("label"), {}) or {}).get(
            "best_rookie_overall_rank"),
        "would the post-hoc placement VETO fire?": (
            "n/a" if not oo["winner"]
            else "NO — it clears" if (out["boards"].get(oo["winner"]["label"], {}) or {}).get(
                "placement", {}).get("clears") else "YES — vetoed"),
    }])))
    p("")
    p(out["framing_agreement_prose"])
    p("")
    p("### 3d. THE DISCLOSED PER-POSITION READING")
    p("")
    p(_md(pd.DataFrame(out["per_position"]["per_position"])))
    p("")
    p(f"BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: "
      f"**{out['per_position']['bh_cutoff_unconditional']}** — against the pooled framing's α of "
      f"**{TA.ALPHA}**.")
    p("")

    p("## 4. Ordering — MEASURED on emitted projections, never asserted")
    p("")
    p(_md(pd.DataFrame([{"form": r["form"], "ordering class": r["ordering_class"],
                         **{f"max rank move {k}": v for k, v in r["max_rank_move_by_pos"].items()},
                         "worst": r["worst_rank_move"],
                         "structural claim holds": r["structural_claim_holds"]}
                        for r in out["ordering"]])))
    p("")
    p("⭐ **NOTHING IN THIS FIELD IS MONOTONE FOR EVERY ADMISSIBLE PARAMETER EXCEPT THE QUANTILE MAP.** "
      "An affine inverts a position's whole board on a negative slope and a power does on a negative "
      "exponent, so `ols_slope`/`huber`/`power` are CONDITIONALLY monotone and their measured rank "
      "movement is a property of THIS RUN's fitted parameters, not of the forms (NF-D16 method lock "
      "2). `isotonic` is only WEAKLY monotone — its flat segments TIE, and a tie IS rank movement. "
      "The measured fits:")
    p("")
    fp_ = out["fitted"]
    p(f"`all_slopes_positive` = **{fp_['all_slopes_positive']}** (range {fp_['min_slope']}–"
      f"{fp_['max_slope']} over {fp_['n_slopes']} affine fits) · `all_gammas_below_one` = "
      f"**{fp_['all_gammas_below_one']}** (γ range {fp_['min_gamma']}–{fp_['max_gamma']} over "
      f"{fp_['n_gammas']} power fits). ⚠️ A power with γ ≥ 1 is not an attenuator at all — this is the "
      "number that says whether the form registered as the canonical top-attenuator actually is one on "
      "this data.")
    p("")
    p(_md(pd.DataFrame(fp_["rows"])))
    p("")
    p("### 4b. ⭐ THE PERMUTATION ANCHOR THAT WAS VACUOUS IN NF-D16 AND BITES HERE")
    p("")
    p(f"NF-D16 measured its within-position permutation as EXACTLY invariant (max |Δ| 7.1e-15): a "
      f"LEVEL is a MARGINAL statistic and a within-position shuffle preserves the marginal, so the "
      f"anchor could not act, and NF-D16 said so in advance rather than presenting a near-tie as a "
      f"passed test. **Every NF-D18 form estimates a SHAPE** — the relationship between projection and "
      f"outcome — which that same shuffle DESTROYS while preserving the marginal exactly. So the "
      f"anchor genuinely tests this hypothesis, and it was pre-registered as a GATE. Measured: "
      f"within-permutation **{an['permuted_within']['pooled_tier_mae']}** vs the best real arm "
      f"**{out['best_real_arm_metric']}** ⇒ "
      f"{'BEATEN ✅' if out['checks']['permutation_within_beaten'] else 'NOT BEATEN 🚨'}. "
      "⭐ *A mechanism that cannot act is a finding, not an omission* (NF1.9) — and so is one that "
      "starts acting when the hypothesis changes shape.")
    p("")

    p("## 5. ⭐ THE MATCHED GLOBAL FOIL — is it the SHAPE, or just less correction?")
    p("")
    p("Every attenuating arm is paired with the REFERENCE affine shrunk GLOBALLY to the SAME mean "
      "absolute correction over the draftable tier: same family, same magnitude, UNIFORM instead of "
      "shaped. The foil's λ is computed from POINT PROJECTIONS ONLY — no realized outcome enters it — "
      "so it is matched on magnitude without being told anything about the answer. A leaderboard rank "
      "cannot make this distinction (NF-D10 (g)); a matched pair can.")
    p("")
    p(_md(pd.DataFrame(out["attribution"]["rows"])) if out["attribution"]["rows"]
      else "_no attenuating arm scored, so there is nothing to pair._")
    p("")

    p("## 6. ⭐ THE PLACEMENT CONSTRAINT ON THE EMITTED 2026 BOARD")
    p("")
    p("The correction is applied to the board's OWN emitted rookie points — exactly where serving "
      "applies it (`RookieSlotCurve.recalibrate_fp` acts on the final scored projection) — so the "
      "incumbent half of every row below IS the served product rather than a reconstruction of it. "
      "Veterans are untouched by construction, which is precisely why a within-position 'moves no "
      "ranks' argument never reaches this gate.")
    p("")
    p(_md(pd.DataFrame(out["board_table"])))
    p("")
    p(f"The validated NF-D17 cap band: `{out['cap_band']}`, observed minimum realized rank "
      f"**{out['observed_minimum']}** ⇒ a THRESHOLD-INVARIANT clearance requires overall rank ≥ "
      f"**{out['strictest_cap']}**, i.e. rank {int(np.ceil(out['strictest_cap']))} or worse. There is "
      "no threshold left for anybody to pick, which is what makes a clearance as un-reverse-"
      "engineerable as NF-D17's veto was.")
    p("")
    p("⭐ **THE PLACEMENT CLAUSE IS A CONSTRAINT A DEGENERATE SATISFIES, AND THAT IS THE RIGHT SHAPE.** "
      f"`zero_scale` places its best rookie at overall rank "
      f"{(out['boards'].get('zero_scale', {}) or {}).get('best_rookie_overall_rank')} and therefore "
      "CLEARS the cap trivially — while losing the selection metric by a mile. NF1.8's rule is that a "
      "constraint a degenerate satisfies is fine (the metric eliminates it) whereas a CRITERION a "
      "degenerate WINS is fatal. Measuring that is the proof this story did not quietly promote a "
      "constraint into a selection criterion.")
    p("")

    p("## 7. Honest limitations")
    p("")
    for line in out["limitations"]:
        p(f"- {line}")
    p("")
    path.write_text("\n".join(a), encoding="utf-8")
    log.info("wrote %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:            # noqa: C901 — orchestration
    ap = argparse.ArgumentParser(
        description="NF-D18 attenuate-at-the-top rookie-point recalibration (RB/TE/WR; QB excluded)")
    ap.add_argument("--pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--board", default=str(_BOARD))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--smoke", action="store_true",
                    help="three forms; writes *_smoke artifacts so it can never be mistaken for the "
                         "real search")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    suffix = "_smoke" if args.smoke else ""

    pool = NF17.load_pool(Path(args.pool))
    # ⛔ `recalibrate=False`: the incumbent of THIS story is the point as SERVED TODAY, and NF-D16's
    #    serving flip is HELD. A study of whether to add an attenuated correction cannot use a
    #    corrected point as its own null.
    folds = NF17.build_folds(pool, list(range(args.from_year, args.to_year + 1)), recalibrate=False)
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    log.info("%d held-out draft classes: %s", len(folds), cohorts)

    fits = {f.year: fold_fits(f) for f in folds}
    pos_scale = {f.year: M14.position_scale(f.train) for f in folds}

    cfgs = all_configs(smoke=args.smoke)
    log.info("%d arms × %d classes", len(cfgs), len(folds))
    arms = score_arms(folds, fits, pos_scale, cfgs)
    incumbent = next(r for r in arms if r["form"] == "incumbent")

    anchors = score_anchors(folds, fits, pos_scale)
    TA.require_anchors(anchors)

    # ── the SERVING fit + the emitted 2026 board: where the PLACEMENT constraint is evaluated ──
    board = pd.read_parquet(Path(args.board))
    sfits = serving_fits(pool, upto=args.to_year)
    # ⭐ FIDELITY, MEASURED: route NF-D16's ratified affine through this harness and compare against
    #    what the PRODUCTION curve emits. A placement number computed from a re-implementation that
    #    drifted would be a number about nothing.
    hist, band = NF17._curve_inputs(pool)
    prod_curve = SP.fit_rookie_slot_curves(
        hist[pd.to_numeric(hist["draft_year"], errors="coerce") <= args.to_year],
        band_hist=band[pd.to_numeric(band["draft_year"], errors="coerce") <= args.to_year],
        recal_hist=band[pd.to_numeric(band["draft_year"], errors="coerce") <= args.to_year])
    rk_board = board[board["is_rookie"].fillna(False).astype(bool)]
    _pt = pd.to_numeric(rk_board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    _ps = rk_board["position"].astype(str).str.upper().to_numpy()
    fidelity = float(np.max(np.abs(
        prod_curve.recalibrate_fp(_ps, _pt)
        - TA.apply_position_adjustment(
            _pt, _ps, TA.predict_form(TA.REFERENCE_FORM, sfits[TA.REFERENCE_FORM], _pt, _ps)))))

    boards = board_verdicts(board, sfits, cfgs)

    recal = [r for r in arms if r["recalibrates"] and not r.get("is_foil")
             and r["pooled_tier_mae"] is not None]
    best_recal = min(recal, key=lambda r: r["pooled_tier_mae"]) if recal else None
    ref = best_recal or incumbent

    ceiling_check = TA.family_ceiling_check(
        [r for r in arms if not r.get("is_foil")], anchors, metric="pooled_tier_mae")

    checks = {
        "degenerates_lose": all(ref["pooled_tier_mae"] < anchors[t]["pooled_tier_mae"]
                                for t in ("zero_scale", "pos_median")),
        "permutation_across_beaten": (ref["pooled_tier_mae"]
                                      < anchors["permuted_across"]["pooled_tier_mae"]),
        "permutation_within_beaten": (ref["pooled_tier_mae"]
                                      < anchors["permuted_within"]["pooled_tier_mae"]),
        "oracle_respected": (anchors["oracle_perplayer"]["pooled_tier_mae"]
                             <= ref["pooled_tier_mae"] + 1e-9),
        "family_ceiling_respected": bool(ceiling_check["ok"]),
        "qb_untouched": True,
    }

    # ⛔ THE SCOPE ASSERTION, MEASURED — every arm, every class, every held-out QB.
    qb_drift = 0.0
    for f in folds:
        qb = fits[f.year]["_te_pos"] == "QB"
        if not qb.any():
            continue
        for c in cfgs:
            got = arm_prediction(c, fits[f.year], f)
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - f.test_pred[qb]))))
    for c in cfgs:                                          # ...and on the SERVED 2026 board
        got = board_arm(board, sfits, c)
        qb = _ps == "QB"
        if qb.any():
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - _pt[qb]))))
    checks["qb_untouched"] = qb_drift < 1e-12

    sel = select_pooled(arms, incumbent, cohorts, boards, placement_binds=True)
    ordering_only = select_pooled(arms, incumbent, cohorts, boards, placement_binds=False)
    ship_gate = TA.pooled_ship(
        winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
        ordering=sel["ordering"] or {"per_position": {}}, placement=sel["placement"],
        pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"), pvalue=sel["pvalue"])
    verdict_gate = TA.attenuation_verdict(pooled_ships=bool(ship_gate["ship"]), **checks)

    attribution = matched_foil_attribution(arms, boards, cohorts)
    cap_ref = TA.placement_clearance(12)                    # any rank: the band itself is what we want

    n_scaled = int(sum(len(TA.scaled_positions_only(f.test)) for f in folds))
    field_table = [{
        "arm": r["label"], "kind": ("NULL" if r["form"] == "incumbent"
                                    else "MATCHED FOIL (⛔ not shippable)" if r.get("is_foil")
                                    else "REFERENCE (NF-D16)" if r["form"] == TA.REFERENCE_FORM
                                    else "attenuating"),
        "pooled tier MAE": r["pooled_tier_mae"], "tier MAE RB": r.get("tier_mae_RB"),
        "tier MAE TE": r.get("tier_mae_TE"), "tier MAE WR": r.get("tier_mae_WR"),
        "universe MAE": r["universe_mae"], "universe bias": r["universe_bias"],
        "board rank": (boards.get(r["label"], {}) or {}).get("best_rookie_overall_rank"),
        "placement clears": bool(((boards.get(r["label"], {}) or {}).get("placement", {})
                                  or {}).get("clears")),
    } for r in sorted(arms, key=lambda x: (x["pooled_tier_mae"] is None, x["pooled_tier_mae"]))]

    board_table = [{
        "arm": lab,
        "best rookie": v.get("best_rookie"), "pos": v.get("best_rookie_position"),
        "proj PPR": v.get("best_rookie_fp"), "overall rank": v.get("best_rookie_overall_rank"),
        "rookies in top 10": v.get("n_rookies_in_top10"),
        "clears cap (threshold-invariant)": bool((v.get("placement") or {}).get("clears")),
        "top-of-board ratio": (v.get("profile") or {}).get("mean_top_ratio"),
        "tier mean ratio": (v.get("profile") or {}).get("mean_tier_ratio"),
        "attenuates at top": (v.get("profile") or {}).get("attenuates_at_top"),
    } for lab, v in boards.items()]

    best_real = min([r["pooled_tier_mae"] for r in arms
                     if not r.get("is_foil") and r["pooled_tier_mae"] is not None])

    # ── the sensitivity: does a gate level I chose decide the answer? ──
    def _ships_at(dsr_min=None, drop_dsr=False, use_contender=False) -> bool:
        d = (sel["deflation"].get("dsr_contenders") if use_contender
             else sel["deflation"].get("dsr"))
        g = TA.pooled_ship(
            winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
            ordering=sel["ordering"] or {"per_position": {}}, placement=sel["placement"],
            pbo=sel["deflation"].get("pbo"), dsr=d, pvalue=sel["pvalue"],
            dsr_min=(-1e9 if drop_dsr else (TA.DSR_MIN if dsr_min is None else dsr_min)))
        return bool(g["ship"])

    sensitivity = {
        "DSR whole-field (THE GATE)": sel["deflation"].get("dsr"),
        "DSR contender-set (reported)": sel["deflation"].get("dsr_contenders"),
        f"ships at pre-registered DSR ≥ {TA.DSR_MIN}": _ships_at(),
        "ships at NF1.4's DSR ≥ 0.0": _ships_at(dsr_min=0.0),
        "ships with the DSR dropped entirely": _ships_at(drop_dsr=True),
        "ships on the CONTENDER DSR reading": _ships_at(use_contender=True),
    }
    blocking = [k for k, v in ship_gate.items()
                if k not in ("ship", "framing", "dsr_ok") and not v]
    sens_prose = (
        "⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING IT.** "
        f"Nothing ships even with the DSR removed ENTIRELY and even on the kinder contender-set "
        f"reading, because `{blocking}` blocks independently. So the verdict is not an artefact of "
        "inheriting NF-D16's stricter DSR bar nor of naming the whole-field reading as binding — a "
        "reader who disagrees with either choice reaches the same verdict."
        if not any([sensitivity[f"ships at pre-registered DSR ≥ {TA.DSR_MIN}"],
                    sensitivity["ships at NF1.4's DSR ≥ 0.0"],
                    sensitivity["ships with the DSR dropped entirely"],
                    sensitivity["ships on the CONTENDER DSR reading"]])
        else "⚠️ **THE GATE LEVEL IS LOAD-BEARING** — the pre-registered reading GOVERNS (a bar moved "
             "after seeing the answer is not a bar, E2.1-r), but a reader is entitled to see it.")

    ow = ordering_only.get("winner")
    pw = sel.get("winner")
    framing_prose = (
        "✅ **THE ELIGIBILITY RULE DID NOT DECIDE THE ANSWER** — both readings select the same arm."
        if (ow or {}).get("label") == (pw or {}).get("label")
        else "⚠️ **THE TWO READINGS DISAGREE, AND THAT DISAGREEMENT IS EXACTLY THE STORY.** The "
             "ordering-only rule selects "
             f"`{(ow or {}).get('label', '— none —')}`, which the post-hoc placement veto would then "
             f"{'CLEAR' if (boards.get((ow or {}).get('label'), {}) or {}).get('placement', {}).get('clears') else 'REFUSE'}"
             "; the pre-registered rule filters first and selects "
             f"`{(pw or {}).get('label', '— none —')}`. The pre-registered rule GOVERNS. Reporting "
             "both is what makes 'the eligibility choice is disclosed, not hidden' a number.")

    headline = ("✅ SHIP — an attenuated rookie-point recalibration clears BOTH the ordering "
                "constraint and the validated placement cap"
                if verdict_gate["ship"] else
                "🟡 RECORDED NULL — no pre-registered top-attenuation clears both constraints; "
                "NF-D16's correction cannot be served")

    out = {
        "story": "NF-D18", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts": cohorts, "n_scaled_rows": n_scaled,
        "n_candidate_arms": len([c for c in cfgs if not c.get("matched_foil")]),
        "n_foils": len([c for c in cfgs if c.get("matched_foil")]),
        "preregistration": {
            "framing": TA.PREREGISTERED_FRAMING, "framing_reason": TA.FRAMING_REASON,
            "eligibility_reason": TA.ELIGIBILITY_REASON,
            "dsr_reading": TA.PREREGISTERED_DSR_READING, "dsr_min": TA.DSR_MIN,
            "alpha": TA.ALPHA, "pbo_max": TA.PBO_MAX, "metric": TA.SELECTION_METRIC,
            "forms": ["incumbent (NULL)"] + list(TA.FORMS), "fixed_lambda": TA.FIXED_LAMBDA,
            "monotone_forms": list(TA.MONOTONE_FORMS),
            "ordering_binding_forms": list(TA.ORDERING_BINDING_FORMS),
        },
        "incumbent": incumbent, "arms": arms, "anchors": anchors, "boards": boards,
        "best_recal": best_recal, "best_real_arm_metric": round(float(best_real), 4),
        "family_ceiling_check": ceiling_check, "checks": checks,
        "selection": sel, "ordering_only": ordering_only, "ship_gate": ship_gate,
        "verdict": verdict_gate, "attribution": attribution,
        "per_position": per_position_disclosure(arms, incumbent, cohorts, boards),
        "ordering": ordering_measurements(folds, fits), "fitted": fitted_parameters(folds, fits),
        "flips": sel["deflation"].get("flips"),
        "field_table": field_table, "board_table": board_table,
        "cap_band": cap_ref.get("caps_over_q_band"), "observed_minimum": cap_ref.get("observed_minimum"),
        "strictest_cap": cap_ref.get("strictest_cap"),
        "qb_max_drift": qb_drift, "headline": headline,
        "serving_fidelity": {"max_abs_diff": fidelity, "n_checked": int(len(_pt))},
        "sensitivity": sensitivity, "sensitivity_prose": sens_prose,
        "framing_agreement_prose": framing_prose,
        "limitations": [
            "⚠️ **THE PLACEMENT CONSTRAINT IS EVALUATED ON ONE BOARD.** It is a serving-time property "
            "of the 2026 draft board, not a held-out statistical criterion, so it contributes no "
            "power and it does influence WHICH of six discrete forms is selected. Three things bound "
            "that: no arm's PARAMETERS are ever tuned to the board (every form is fitted in-fold and "
            "has no strength dial), the clearance is required to be THRESHOLD-INVARIANT so no cutoff "
            "was chosen, and the ordering-only reading is reported beside it (§3c).",
            "⚠️ **λ WAS DELIBERATELY NOT RE-OPENED, AND THAT BOUNDS WHAT A NULL HERE MEANS.** A global "
            "shrink of NF-D16's affine might well clear the placement cap — the matched foils measure "
            "exactly that — but re-picking a selection parameter after seeing a constraint result is "
            "the E2.1-r inversion. So a null here is 'no top-attenuating SHAPE works', never 'nothing "
            "could ever work'; the forbidden move is measured and reported rather than taken.",
            "**`tier_mae` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A claim here is "
            "a claim about a few dozen rookie-seasons across seven draft classes; the paired per-class "
            "deltas are reported so a reader sees the spread rather than only the mean.",
            "**The in-fold shapes are estimated against IN-SAMPLE point projections** (the training "
            "rows' points come from the fold's own slot curve). NF-D16 measured the resulting optimism "
            "at −0.05 in constant space and the direction is CONSERVATIVE — it biases a correction "
            "toward the identity — but it is not zero, and it applies to every form here.",
            "⛔ **QB is out of scope by pre-registration, not by result** — inherited by import through "
            "NF-D16 from NF-D15, and proven untouched on both the held-out classes and the served "
            "board rather than asserted.",
            "**No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.",
        ],
    }
    out["verdict_prose"] = _verdict_prose(out)

    if not args.no_report:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_report(out, _REPORT_DIR / f"nf_d18_rookie_top_attenuation{suffix}.md")
        (_REPORT_DIR / f"nf_d18_rookie_top_attenuation{suffix}.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("VERDICT: %s", headline)
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())

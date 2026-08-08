"""run_nf_recal1_level.py — NF-RECAL1 §0.5 bake-off: can the fastpath's VETERAN point LEVEL be
recalibrated in-fold, under the product's own ordering, placement and interval-coverage constraints?

THE STORY IN ONE PARAGRAPH. The served point levels were reported to sit systematically BELOW realized
(pooled −37.7 PPR; our/actual QB 0.923 · RB 0.693 · WR 0.778 · TE 0.816), with the availability
discount named as the main carrier and a ~15% RB residual attributed to NF-D11/NF-D15 median-optimal
pessimism. NF-RECAL1 asks whether a LEVEL recalibration of the VETERAN leg can be SELECTED IN-FOLD and
survive the three constraints the product already owns. It grades on CRPS (⛔ never MAE — that is the
statistic that CAUSED the residual), fits and selects strictly in-fold, and treats the SEASON-TOTAL
parameterisation as a matched foil so the per-game hypothesis is attributable rather than asserted.

⚠️ THE PRE-REGISTRATION LIVES IN `level_recalibration.py`, NOT HERE, and was committed before this
file existed. This runner READS those constants; it does not restate them.

⭐ AND IT BEGINS WITH A PREMISE CHECK, WHICH IS NOT A FORMALITY. A recalibration is a correction
fitted to a measured defect, so §0 re-measures the defect in the population this story actually fits
on — with the tier fixed by the INCUMBENT's own projection — and reports the outcome-conditioned
readings beside it. If the two disagree, which reading you take decides the size and even the SIGN of
the correction, and that has to be a number rather than an argument.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. `best_alpha = 0`, no CLV/ROI claim.
⛔ THE ROOKIE LEG IS OUT OF SCOPE — CLOSED by NF-D21 (PM, 2026-08-05). `assert_rookie_leg_untouched`
   is the gate; the disposition is imported, never restated.
⛔ NF1.5's ORDERING layer is untouched. This story changes LEVELS only.
🔒 CODE-READY, NOT DEPLOYED. A serving flip is a POST-LAUNCH operator step with its own soak.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached veteran band panel + merged boards):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_recal1_level
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

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_recal1_level")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_PANEL = _ART / "nf1_9_veteran_band_panel"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STEM = "nf_recal1_level_recalibration"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Data — the walk-forward veteran panel and the per-season merged boards
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_panel(seasons: tuple) -> pd.DataFrame:
    """The veteran walk-forward panel: the SERVED point and band for target season Y, built off
    `base_season = Y − 1`, LEFT-joined so zero-game seasons score as real 0s.

    ⭐ THE LEFT JOIN IS LOAD-BEARING AND IT IS INHERITED, NOT CHOSEN. NF1.9 built this panel that way
    precisely because a rank backtest correctly DROPS zero-game seasons while every level or interval
    backtest must KEEP them — dropping them is the outcome-conditioning §0 exists to keep out, and it
    is 31–35% of this population.

    ⚠️ Provenance is ASSERTED rather than assumed (`base_season == Y − 1`): this story reads artifacts
    it did not build, and a panel rebuilt with later data would make every number here a number about
    a different product while nothing downstream noticed."""
    frames = []
    for y in seasons:
        p = _PANEL / f"panel_target{y}.parquet"
        if not p.exists():
            raise SystemExit(
                f"no veteran band panel for {y} at {p} — rebuild it first:\n"
                "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
                "run_veteran_interval_ablation --build-panel")
        d = pd.read_parquet(p)
        base = int(pd.to_numeric(d["base_season"], errors="coerce").dropna().iloc[0])
        if base != int(y) - 1:
            raise SystemExit(
                f"panel_target{y}.parquet is NOT walk-forward (base_season={base}, expected {y - 1}). "
                "Every level number computed from it would be a number about a different product.")
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["position"] = d["position"].astype(str).str.upper()
    d = d[d["position"].isin(LR.RECALIBRATED_POSITIONS)].copy()
    # ⛔ The scope gate. The panel is a VETERAN panel by construction, but the assertion is what makes
    #    "the closed rookie leg stays closed" a property of the code rather than of this comment.
    d["is_rookie"] = False
    LR.assert_rookie_leg_untouched(d)
    for c in ("point", "served_p10", "served_p90", "proj_games", "real_fp_ppr", "real_games"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["point", "real_fp_ppr"]).reset_index(drop=True)


def board_path(season: int) -> Path:
    return _ART / f"nfl_fantasy_season_projections_{season}.parquet"


def load_boards(seasons: tuple) -> dict:
    """The merged veteran+rookie boards C2 is evaluated on, with their walk-forward provenance
    asserted the same way the panel's is."""
    out = {}
    for s in seasons:
        p = board_path(s)
        if not p.exists():
            raise SystemExit(
                f"no merged board for {s} at {p} — rebuild the per-season boards first:\n"
                "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
                "run_season_projection --backtest-from 2019")
        b = pd.read_parquet(p)
        base = int(pd.to_numeric(b["base_season"], errors="coerce").dropna().iloc[0])
        n_rk = int(b["is_rookie"].fillna(False).astype(bool).sum())
        if base != int(s) - 1 or n_rk == 0:
            raise SystemExit(f"board {s} is not walk-forward (base={base}) or has no rookie leg "
                             f"(n_rookies={n_rk}) — C2 would be evaluated on a different product.")
        b["position"] = b["position"].astype(str).str.upper()
        out[s] = b
    return out


def tier_mask(d: pd.DataFrame, n: int) -> np.ndarray:
    """⭐ THE DRAFTABLE TIER, FIXED BY THE INCUMBENT'S OWN PROJECTION (`LR.TIER_ANCHOR`).

    The top `n` by the INCUMBENT's point, per season, computed ONCE and applied identically to every
    arm — candidate, matched foil, degenerate and oracle alike. That is NF1.1's fixed-anchor rule, and
    it is the single mechanism that stops a candidate from buying a friendlier subset.

    ⛔ It is never re-derived from a candidate's own projection, and never from the realized outcome
    (see `LR.FORBIDDEN_TIER_ANCHORS` and the §0 premise check for what that would manufacture)."""
    keep = np.zeros(len(d), dtype=bool)
    for _, idx in d.groupby("target_season").groups.items():
        sub = d.loc[idx, "point"].nlargest(min(n, len(idx)))
        keep[d.index.get_indexer(sub.index)] = True
    return keep


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ §0 — THE PREMISE CHECK
# ══════════════════════════════════════════════════════════════════════════════════════════════
def premise_check(d: pd.DataFrame, tier_n: int) -> dict:
    """Re-measure the motivating LEVEL defect in the population this story fits on, and beside it the
    outcome-conditioned readings the motivating figure may have used.

    ⭐ WHY EVERY READING IS COMPUTED RATHER THAN THE ONE THIS STORY USES. The motivating table states
    its figures are unconditional, but it covers 1,165 player-seasons out of a ~4,600-row veteran
    universe — so it is conditioned on SOMETHING, and which something decides the answer. NF-D17
    measured a one-sided truncation manufacturing an arbitrary gap; this product's own documentation
    forbids citing its outcome-bucketed decile table for the identical reason. Printing all four
    readings turns "which population" from an argument into a table.

    `premise_confirmed` is deliberately a WEAK, DIRECTIONAL test on the PRE-REGISTERED population: is
    the incumbent-anchored draftable tier biased LOW at all? A recalibration fitted to a defect that
    does not reproduce in its own population is a correction to nothing, and this is the story-level
    veto that says so."""
    rows, out = [], {}

    def read(sel: np.ndarray, tag: str) -> dict:
        s = d.loc[sel]
        if s.empty:
            return {"reading": tag, "n": 0}
        bias = s["point"] - s["real_fp_ppr"]
        per = {q: {"n": int(len(g)),
                   "mean_bias": round(float((g["point"] - g["real_fp_ppr"]).mean()), 2),
                   "ours_over_actual": (round(float(g["point"].mean() / g["real_fp_ppr"].mean()), 3)
                                        if g["real_fp_ppr"].mean() > 0 else None)}
               for q, g in s.groupby("position")}
        return {"reading": tag, "n": int(len(s)),
                "mean_bias": round(float(bias.mean()), 2),
                "median_bias": round(float(bias.median()), 2),
                "ours_over_actual": (round(float(s["point"].mean() / s["real_fp_ppr"].mean()), 3)
                                     if s["real_fp_ppr"].mean() > 0 else None),
                "pct_zero_outcome": round(float((s["real_fp_ppr"] <= 0).mean()), 3),
                "per_position": per}

    inc_tier = tier_mask(d, tier_n)
    real_tier = np.zeros(len(d), dtype=bool)
    for _, idx in d.groupby("target_season").groups.items():
        sub = d.loc[idx, "real_fp_ppr"].nlargest(min(tier_n, len(idx)))
        real_tier[d.index.get_indexer(sub.index)] = True

    out["universe"] = read(np.ones(len(d), dtype=bool), "universe (unconditional)")
    out["draftable_tier_incumbent_anchor"] = read(
        inc_tier, f"draftable tier, INCUMBENT anchor (top {tier_n}/season) ⭐ PRE-REGISTERED")
    out["draftable_tier_realized_anchor"] = read(
        real_tier, f"draftable tier, REALIZED anchor (top {tier_n}/season) ⛔ forbidden")
    out["played_at_least_6_games"] = read(
        (d["real_games"] >= 6).to_numpy(), "played ≥6 games ⛔ outcome-conditioned")

    pre = out["draftable_tier_incumbent_anchor"]
    out["motivating_figures"] = {
        "source": "production_model_state/nfl_season_fantasy.md — MEASURED LEVEL BIAS (NF-TR1)",
        "n": 1165, "mean_bias": -37.7, "median_bias": -34.5,
        "ours_over_actual": {"QB": 0.923, "RB": 0.693, "WR": 0.778, "TE": 0.816},
        "population_note": "stated as unconditional; not reproducible on this panel — see verdict",
    }
    out["premise_confirmed"] = bool(pre.get("mean_bias") is not None and pre["mean_bias"] < 0)
    out["reproduces_motivating_magnitude"] = bool(
        pre.get("mean_bias") is not None and pre["mean_bias"] <= -30.0)
    out["per_position_sign_agrees_with_motivating"] = {
        q: (None if (pre["per_position"].get(q, {}).get("ours_over_actual") is None) else
            bool((pre["per_position"][q]["ours_over_actual"] < 1.0)
                 == (out["motivating_figures"]["ours_over_actual"][q] < 1.0)))
        for q in LR.RECALIBRATED_POSITIONS}
    for k in LR.POPULATION_READINGS:
        rows.append({k2: v for k2, v in out[k].items() if k2 != "per_position"})
    out["table"] = rows
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Folds + per-fold fits
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_folds(d: pd.DataFrame, tier: np.ndarray, seasons: tuple) -> list[dict]:
    """Walk-forward by target season: fit on every panel season STRICTLY BEFORE Y, score on Y.

    ⭐ BOTH SIDES ARE RESTRICTED TO THE INCUMBENT-ANCHORED TIER. Fitting on the tier the metric is
    computed on is NF1.1's own rule ("select on the tier the product is actually used on") and is what
    NF1.4/NF-D16 do. The UNIVERSE reading is computed for every arm as a mandatory disclosure, because
    a tier-fitted correction is applied board-wide at serving time and a reader is entitled to see
    what it does to the rest of the board."""
    d = d.assign(_tier=tier)
    folds = []
    for y in seasons:
        tr = d[(d["target_season"] < y) & d["_tier"]]
        te_all = d[d["target_season"] == y]
        te = te_all[te_all["_tier"]]
        if len(tr) < 200 or te.empty:
            raise SystemExit(f"fold {y}: {len(tr)} train / {len(te)} test rows — too thin to fit.")
        folds.append({"year": int(y), "train": tr.reset_index(drop=True),
                      "test": te.reset_index(drop=True),
                      "test_universe": te_all.reset_index(drop=True)})
    return folds


def fold_fits(fold: dict, *, seed: int = 20260808) -> dict:
    """Every fitted correction for ONE held-out season, computed once and shared by every arm.

    ⭐ THE CANDIDATE FITS ARE STRICTLY IN-FOLD (train = seasons < Y). `_peek_*` are the ORACLE CEILINGS
    and are fitted on the HELD-OUT season on purpose — a ceiling has to peek to be one — and there is
    ONE PER FORM, because the forms NEST and a single shared ceiling would veto a legitimately-better
    richer family as a metric inversion (NF-D16 (g‴)).

    ⚠️ BOTH PERMUTATIONS ARE FITTED AT THE SAME FORM so the anchors differ from the candidates in
    exactly one thing — which outcome vector they saw:
      · `_perm_across` shuffles realized outcomes ACROSS positions (per-position structure destroyed,
        family/n/grand mean preserved). Must LOSE.
      · `_perm_within` shuffles WITHIN each position, preserving that position's MARGINAL exactly.
        ⭐ PRE-REGISTERED TO TIE for the pure level forms — a level IS a marginal statistic, so the
        shuffle cannot act on them — and to BE BEATEN for the slope-carrying `pos_affine`. Saying
        which in advance is the point (NF1.9: a mechanism that cannot act is a finding)."""
    tr, te = fold["train"], fold["test"]
    rng = np.random.default_rng(seed + int(fold["year"]))
    y_tr = tr["real_fp_ppr"].to_numpy(dtype=float)
    pos_tr = tr["position"].to_numpy()

    y_across = rng.permutation(y_tr)
    y_within = y_tr.copy()
    for q in LR.RECALIBRATED_POSITIONS:
        sel = np.flatnonzero(pos_tr == q)
        if len(sel) > 1:
            y_within[sel] = rng.permutation(y_within[sel])

    args_tr = (tr["point"].to_numpy(dtype=float), y_tr, pos_tr,
               tr["proj_games"].to_numpy(dtype=float))
    args_te = (te["point"].to_numpy(dtype=float), te["real_fp_ppr"].to_numpy(dtype=float),
               te["position"].to_numpy(), te["proj_games"].to_numpy(dtype=float))

    band_te = (te["point"].to_numpy(dtype=float), te["served_p10"].to_numpy(dtype=float),
               te["served_p90"].to_numpy(dtype=float), te["real_fp_ppr"].to_numpy(dtype=float),
               te["position"].to_numpy(), te["proj_games"].to_numpy(dtype=float))

    fits: dict = {}
    for form in LR.FORMS:
        for space in LR.SPACES:
            fits[(form, space)] = LR.fit_form(form, space, *args_tr)
        # ⭐ THE CEILING IS FITTED ON THE SELECTION METRIC, NOT BY LEAST SQUARES. See
        #   `LR.fit_form_peeking_on_metric` — an LS-fitted ceiling scored on CRPS is not a bound on a
        #   CRPS-scored arm, and this run MEASURED that (the ceilings did not order by capacity).
        #   The LS fit is kept as the initialisation AND reported, because it is the disclosure that
        #   produced the finding.
        fits[("_peek_ls", form)] = LR.fit_form(form, LR.PRIMARY_SPACE, *args_te)
        fits[("_peek", form, LR.PRIMARY_SPACE)] = LR.fit_form_peeking_on_metric(
            form, LR.PRIMARY_SPACE, *band_te, init=fits[("_peek_ls", form)])
        # ⚠️ BOTH PERMUTATIONS ARE FITTED AT **BOTH** A PURE-LEVEL FORM AND THE SLOPE-CARRYING ONE.
        #   The first cut scored `permuted_across` at `pos_const` and `permuted_within` at
        #   `pos_affine`, so the two anchors differed in TWO things — which shuffle AND which form —
        #   and neither could be read against the other. Matching the forms is what makes the
        #   pre-registered "within TIES on a level, BITES on a slope" a measurement rather than a
        #   comparison of two different experiments.
        for tag, yy in (("_perm_across", y_across), ("_perm_within", y_within)):
            fits[(tag, form)] = LR.fit_form(form, LR.PRIMARY_SPACE, args_tr[0], yy, pos_tr,
                                            args_tr[3])
    fits["_pos_median"] = {q: float(np.median(y_tr[pos_tr == q]))
                           for q in LR.RECALIBRATED_POSITIONS if (pos_tr == q).any()}
    # The incumbent's OWN per-position coverage on this fold's tier — the second term C3 is built on.
    fits["_inc_coverage"] = LR.per_position_coverage(band_te[3], band_te[1], band_te[2], band_te[4])
    return fits


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — candidates and anchors through the IDENTICAL reducer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _triples(fold: dict, key: str = "test") -> tuple:
    d = fold[key]
    return (d["point"].to_numpy(dtype=float), d["served_p10"].to_numpy(dtype=float),
            d["served_p90"].to_numpy(dtype=float), d["position"].to_numpy(),
            d["proj_games"].to_numpy(dtype=float), d["real_fp_ppr"].to_numpy(dtype=float))


def score_fold(fold: dict, adjust, inc_coverage: dict | None = None) -> dict:
    """Score ANY arm on ONE fold through the IDENTICAL reducer, so the anchors and the candidates are
    demonstrably answering the same question rather than merely being described that way.

    `adjust` maps (point, p10, p90, positions, games, realized) → the adjusted triple. It is called on
    the TIER (the pre-registered metric population) and again on the UNIVERSE (the mandatory
    disclosure).

    ⚠️ THE REALIZED VECTOR IS A PARAMETER RATHER THAN A CLOSURE, AND THAT IS A CORRECTNESS PROPERTY.
    The peeking anchors have to see the outcomes OF THE ROWS THEY ARE SCORED ON; a captured tier-sized
    vector would either crash on the universe pass (it did, first run) or — worse, had the two
    populations happened to match in length — silently score an oracle against somebody else's
    outcomes and report it as a clean anchor."""
    p, lo, hi, pos, g, y = _triples(fold)
    ap, alo, ahi = adjust(p, lo, hi, pos, g, y)
    m = LR.band_metrics(ap, alo, ahi, y)
    m["ordering"] = LR.ordering_movement(p, ap, pos)
    m["coverage"] = LR.coverage_floor_check(y, alo, ahi, pos,
                                            incumbent_coverage=inc_coverage)
    m["per_position"] = {q: LR.band_metrics(ap[pos == q], alo[pos == q], ahi[pos == q], y[pos == q])
                         for q in LR.RECALIBRATED_POSITIONS if (pos == q).any()}
    pu, lou, hiu, posu, gu, yu = _triples(fold, "test_universe")
    apu, alou, ahiu = adjust(pu, lou, hiu, posu, gu, yu)
    um = LR.band_metrics(apu, alou, ahiu, yu)
    m["universe"] = {"crps": um[LR.SELECTION_METRIC], "mae": um["mae"], "bias": um["bias"],
                     "coverage80": um["coverage80"], "n": um["n"]}
    return m


def score_arm(folds: list[dict], fits: dict, adjust_for, label: str, extra: dict | None = None
              ) -> dict:
    """Aggregate one arm over every fold. `adjust_for(fold, fits_for_that_fold)` returns the fold's
    `adjust` callable, so an arm whose λ VARIES BY FOLD (every in-fold rule does) and an arm with a
    constant λ go through exactly the same path."""
    per = {f["year"]: score_fold(f, adjust_for(f, fits[f["year"]]),
                                 fits[f["year"]]["_inc_coverage"]) for f in folds}
    def _m(key, nd=4):
        v = [per[y].get(key) for y in per if per[y].get(key) is not None]
        return round(float(np.mean(v)), nd) if v else None
    out = {"label": label, "per_fold": per,
           "per_fold_metric": {y: per[y].get(LR.SELECTION_METRIC) for y in per},
           LR.SELECTION_METRIC: _m(LR.SELECTION_METRIC),
           **{k: _m(k) for k in LR.DISCLOSED_METRICS},
           "universe_crps": round(float(np.mean([per[y]["universe"]["crps"] for y in per])), 4),
           "universe_bias": round(float(np.mean([per[y]["universe"]["bias"] for y in per])), 4),
           "universe_coverage80": round(
               float(np.mean([per[y]["universe"]["coverage80"] for y in per])), 4),
           **(extra or {})}
    for q in LR.RECALIBRATED_POSITIONS:
        vals = [per[y]["per_position"].get(q, {}) for y in per]
        for k in (LR.SELECTION_METRIC, "mae", "bias", "coverage80"):
            v = [x.get(k) for x in vals if x.get(k) is not None]
            out[f"{k}_{q}"] = round(float(np.mean(v)), 3) if v else None
        rho = [per[y]["ordering"]["within_position_rho"].get(q) for y in per]
        rho = [x for x in rho if x is not None and np.isfinite(x)]
        out[f"rho_{q}"] = round(float(np.mean(rho)), 4) if rho else None
    # Constraint state, POOLED OVER ROWS across folds (NF1.8: never a mean of per-fold means).
    yy = np.concatenate([f["test"]["real_fp_ppr"].to_numpy(dtype=float) for f in folds])
    pos = np.concatenate([f["test"]["position"].to_numpy() for f in folds])
    los, his = [], []
    for f in folds:
        p, lo, hi, po, g, real = _triples(f)
        _, alo, ahi = adjust_for(f, fits[f["year"]])(p, lo, hi, po, g, real)
        los.append(alo); his.append(ahi)
    inc_pooled = LR.per_position_coverage(
        yy, np.concatenate([f["test"]["served_p10"].to_numpy(dtype=float) for f in folds]),
        np.concatenate([f["test"]["served_p90"].to_numpy(dtype=float) for f in folds]), pos)
    out["coverage_pooled"] = LR.coverage_floor_check(yy, np.concatenate(los), np.concatenate(his),
                                                     pos, incumbent_coverage=inc_pooled)
    out["worst_rank_move"] = max(per[y]["ordering"]["worst_rank_move"] for y in per)
    return out


def form_adjuster(form: str, space: str, params_key, lam_for):
    """Build an `adjust_for` for a fitted FORM: look up this fold's params and λ, then apply the
    correction to the point AND both band edges with the same map (`LR.apply_to_band`)."""
    def _outer(fold, fits):
        params = fits[params_key] if not callable(params_key) else params_key(fits)
        lam = float(lam_for(fold))
        def _adjust(p, lo, hi, pos, g, y=None):
            # ⛔ `y` is accepted and IGNORED. A candidate must be structurally unable to read the
            #    outcome even though the shared signature offers it — the anchors need it, the
            #    candidates must not have it, and refusing it here is cheaper than trusting each arm.
            return LR.apply_to_band(form, space, params, p, lo, hi, pos, g, lam)
        return _adjust
    return _outer


# ── the anchors ────────────────────────────────────────────────────────────────────────────────
def anchor_adjuster(tag: str, folds: list[dict]):
    """Every two-sided anchor (§8), each built to differ from the candidates in exactly one respect.

    ⚠️ The peeking anchors read the realized vector PASSED IN, never one captured from the fold: they
    are scored on both the tier and the universe, and an oracle graded against a different
    population's outcomes is not an oracle."""
    def _outer(fold, fits):
        def _adjust(p, lo, hi, pos, g, y=None):
            if tag == "oracle_perplayer":
                # Peeks at FULL resolution. Nothing may beat it; the band collapses onto the truth,
                # which is the correct limit for an oracle and gives CRPS ≈ 0.
                return np.clip(y, 0, None), np.clip(y, 0, None), np.clip(y, 0, None)
            if tag == "zero_project":
                z = np.zeros_like(p)
                return z, z, z
            if tag == "wide_band":
                # SHARPNESS degenerate: centre unchanged, band ×3. It SATISFIES every coverage floor
                # and must LOSE CRPS — the proof C3 is a constraint and not a criterion (NF1.8).
                w = LR.WIDE_BAND_FACTOR
                return p, np.clip(p - w * (p - lo), 0, None), p + w * (hi - p)
            if tag == "pos_median":
                adj = np.array([fits["_pos_median"].get(q, np.nan) for q in pos], dtype=float)
                adj = np.where(np.isfinite(adj), adj, p)
                return adj, adj, adj
            if tag == "over_scale":
                return LR.apply_to_band(LR.LEARNED_FOIL, LR.PRIMARY_SPACE,
                                        fits[(LR.LEARNED_FOIL, LR.PRIMARY_SPACE)],
                                        p, lo, hi, pos, g, LR.OVER_SCALE_LAMBDA)
            if tag.startswith("oracle_"):
                form = tag[len("oracle_"):]
                return LR.apply_to_band(form, LR.PRIMARY_SPACE,
                                        fits[("_peek", form, LR.PRIMARY_SPACE)],
                                        p, lo, hi, pos, g, 1.0)
            if tag.startswith("permuted_"):
                # tag form: "permuted_{across|within}@{form}" — the form is EXPLICIT so the two
                # shuffles are always compared at the SAME family (see fold_fits).
                which, form = tag.split("@")
                key = "_perm_across" if which == "permuted_across" else "_perm_within"
                return LR.apply_to_band(form, LR.PRIMARY_SPACE, fits[(key, form)],
                                        p, lo, hi, pos, g, 1.0)
            raise ValueError(f"unknown anchor {tag!r}")
        return _adjust
    return _outer


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ C2 — the per-fold whole-board placement constraint, evaluated OUT-OF-SAMPLE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_rank_by_lambda(board: pd.DataFrame, form: str, space: str, params: dict,
                         grid: tuple = LR.LAMBDA_GRID) -> dict:
    """The best rookie's OVERALL rank on ONE merged board at every λ, with the VETERAN half corrected.

    ⭐ THE DIRECTION IS INVERTED RELATIVE TO NF-D16/D18/D20 AND THAT IS THE WHOLE POINT OF MEASURING
    ITS ACTIVITY. Those stories lifted ROOKIES through a fixed veteran field, so the cap was the
    binding veto. Here the ROOKIE half is fixed and the VETERAN half moves, so a LIFT pushes the best
    rookie DOWN the board — away from the cap — and a recorded "C2 held" can mean the constraint could
    not act. `constraint_activity` counts the folds on which any λ moves the rank at all, and an
    inactive fold is reported UNINFORMATIVE rather than as a pass (NF-D20 (g⁗))."""
    vet = ~board["is_rookie"].fillna(False).astype(bool).to_numpy()
    p = pd.to_numeric(board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = board["position"].astype(str).str.upper().to_numpy()
    g = pd.to_numeric(board.get("proj_games", pd.Series(np.full(len(board), 17.0))),
                      errors="coerce").to_numpy(dtype=float)
    out, detail = {}, {}
    for lam in grid:
        adj = p.copy()
        a, _, _ = LR.apply_to_band(form, space, params, p[vet], p[vet], p[vet],
                                   pos[vet], g[vet], float(lam))
        adj[vet] = a
        b2 = board.assign(proj_fp_ppr=adj)
        place = LR.board_placement(b2)
        out[float(lam)] = place.get("best_rookie_overall_rank")
        detail[float(lam)] = place
    return {"rank_by_lambda": out, "placement_by_lambda": detail}


def board_admits(rank_lambda, rank_incumbent) -> dict:
    """C2 in one inequality: `rank_λ ≥ min(cap, rank_incumbent)`.

    The cap is NF-D17's threshold-invariant one, DELEGATED to `placement_clearance` — this story
    introduces no new threshold and no new reference. The second term governs the CHANGE rather than
    the level: on a board the SHIPPED product already breaches, the clause forbids making the breach
    worse instead of refusing every λ including λ = 0 (a constraint that refuses everything has
    examined nothing — NF1.7 (a)). An unevaluable rank is a REFUSAL, never a pass."""
    br = LR.placement_clearance(999)
    cap = float(max([float(c) for c in br["caps_over_q_band"].values()] + [br["observed_minimum"]]))
    if rank_lambda is None or rank_incumbent is None:
        return {"admits": False, "evaluable": False, "cap": cap,
                "note": "no rookie on the board — C2 could not be evaluated, which is not passing it"}
    r, ri = float(rank_lambda), float(rank_incumbent)
    return {"admits": bool(r >= min(cap, ri)), "admits_strict": bool(r >= cap), "evaluable": True,
            "cap": cap, "rank": r, "incumbent_rank": ri,
            "incumbent_itself_breaches": bool(ri < cap)}


def build_fold_evidence(folds, fits, boards, forms=LR.FORMS, space=LR.PRIMARY_SPACE) -> dict:
    """Per (form, fold): the λ → admissibility map under C1 ∧ C2 ∧ C3, all three evaluated on THAT
    fold's own held-out data and board.

    An arm's rule may then read only the folds strictly BEFORE the one it is scored on, which is what
    makes the constraint an OUT-OF-SAMPLE question ("does an in-fold-selected correction still clear
    on the NEXT board?") rather than a description of the set it was optimised against."""
    ev: dict = {}
    for form in forms:
        ev[form] = {}
        for f in folds:
            y = f["year"]
            params = fits[y][(form, space)]
            ranks = board_rank_by_lambda(boards[y], form, space, params)
            inc_rank = ranks["rank_by_lambda"][0.0]
            p, lo, hi, pos, g, real = _triples(f)
            per_lam = {}
            for lam in LR.LAMBDA_GRID:
                ap, alo, ahi = LR.apply_to_band(form, space, params, p, lo, hi, pos, g, float(lam))
                c1 = LR.ordering_movement(p, ap, pos)
                inc_rho = {q: 1.0 for q in c1["within_position_rho"]}
                c1_ok = all(v >= inc_rho[q] - LR.ORDERING_DO_NO_HARM
                            for q, v in c1["within_position_rho"].items())
                c2 = board_admits(ranks["rank_by_lambda"].get(float(lam)), inc_rank)
                c3 = LR.coverage_floor_check(real, alo, ahi, pos,
                                             incumbent_coverage=fits[y]["_inc_coverage"])
                per_lam[float(lam)] = {
                    "c1_ordering_ok": bool(c1_ok), "c2_placement_ok": bool(c2["admits"]),
                    "c3_coverage_ok": bool(c3["ok"]),
                    "admissible": bool(c1_ok and c2["admits"] and c3["ok"]),
                    "rank": c2.get("rank"), "worst_rank_move": c1["worst_rank_move"],
                    "coverage_breaches": c3["breaches"]}
            ev[form][y] = {
                "per_lambda": per_lam,
                "admissible": tuple(sorted(l for l, v in per_lam.items() if v["admissible"])),
                "incumbent_rank": inc_rank,
                "rank_by_lambda": ranks["rank_by_lambda"],
                "constraint_can_act": bool(len(set(
                    v for v in ranks["rank_by_lambda"].values() if v is not None)) > 1),
                "top_rookie": ranks["placement_by_lambda"][0.0].get("best_rookie"),
                "top_rookie_pos": ranks["placement_by_lambda"][0.0].get("best_rookie_position")}
    return ev


def _anchor_role(tag: str) -> str:
    """Which SIDE of the two-sided anchor set an anchor is on — a ceiling must WIN, a degenerate or a
    permutation must LOSE. Naming the role is what makes the anchor table readable in one pass."""
    if tag == "oracle_perplayer" or tag.startswith("oracle_"):
        return "ceiling"
    if tag.startswith("permuted_"):
        return "permutation"
    return "degenerate"


def anchor_constraint_state(folds, fits, boards, anchor_adjust, tag: str) -> dict:
    """⭐ THE CONSTRAINTS' TEETH, READ IN BOTH DIRECTIONS (NF1.8, and NF-D20's extension of it).

    A constraint is only shown to be a CONSTRAINT rather than a smuggled selection CRITERION when
    both halves are measured:
      · a DO-NOTHING degenerate (`zero_project`) must SATISFY it — the metric is what eliminates that
        arm, not the gate. A gate a do-nothing arm FAILS is doing the metric's job;
      · an OVER-CORRECTING degenerate (`over_scale`) must BREACH it — a gate nothing is ever measured
        failing has examined nothing (NF1.7 (a) in an eligibility rule's clothing).

    Reporting them is the proof this story did not quietly promote C2 or C3 into a criterion."""
    per = {}
    for f in folds:
        y = f["year"]
        p, lo, hi, pos, g, real = _triples(f)
        ap, alo, ahi = anchor_adjust(f, fits[y])(p, lo, hi, pos, g, real)
        c1 = LR.ordering_movement(p, ap, pos)
        c3 = LR.coverage_floor_check(real, alo, ahi, pos,
                                     incumbent_coverage=fits[y]["_inc_coverage"])
        board = boards[y]
        vet = ~board["is_rookie"].fillna(False).astype(bool).to_numpy()
        bp = pd.to_numeric(board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
        bpos = board["position"].astype(str).str.upper().to_numpy()
        bg = pd.to_numeric(board.get("proj_games", pd.Series(np.full(len(board), 17.0))),
                           errors="coerce").to_numpy(dtype=float)
        adj = bp.copy()
        a2, _, _ = anchor_adjust(f, fits[y])(bp[vet], bp[vet], bp[vet], bpos[vet], bg[vet],
                                             np.full(int(vet.sum()), np.nan))
        adj[vet] = a2
        inc_rank = LR.board_placement(board).get("best_rookie_overall_rank")
        new_rank = LR.board_placement(board.assign(proj_fp_ppr=adj)).get("best_rookie_overall_rank")
        c2 = board_admits(new_rank, inc_rank)
        per[y] = {"c2_placement_ok": bool(c2["admits"]), "c3_coverage_ok": bool(c3["ok"]),
                  "rank": c2.get("rank"), "incumbent_rank": inc_rank,
                  "worst_rank_move": c1["worst_rank_move"]}
    return {"anchor": tag,
            "satisfies C2 on every fold": all(v["c2_placement_ok"] for v in per.values()),
            "satisfies C3 on every fold": all(v["c3_coverage_ok"] for v in per.values()),
            "breaches C2 somewhere": any(not v["c2_placement_ok"] for v in per.values()),
            "breaches C3 somewhere": any(not v["c3_coverage_ok"] for v in per.values()),
            "per_fold": per}


def constraint_activity(evidence: dict) -> list[dict]:
    """⭐ ON HOW MANY FOLDS CAN C2 EVEN ACT? — counted, because "C2 held on 7 of 7" means something
    entirely different if the correction could not move the constrained rank on most of them
    (NF-D20 (g⁗)). An inactive fold is UNINFORMATIVE, never a pass."""
    rows = []
    for form, per in evidence.items():
        act = [y for y, v in per.items() if v["constraint_can_act"]]
        rows.append({"form": form, "n_folds": len(per), "folds_c2_can_act": len(act),
                     "active_folds": act,
                     "c2_inactive_everywhere": bool(not act),
                     "why_inactive": ("a leg-monotone correction moves no rank WITHIN the recalibrated "
                                      "leg (it can still move the board — see cross-position)"
                                      if form in LR.LEG_MONOTONE_FORMS and not act else
                                      "no λ moves the best rookie's overall rank on these boards"
                                      if not act else None)})
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE IN-FOLD λ SELECTION — from folds strictly BEFORE the one being scored
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rule_lambdas(form: str, cfg: dict, folds, lam_scored: dict, evidence: dict) -> dict:
    """The λ a RULE selects for every held-out season.

    For season Y the rule may read the admissibility of folds `< Y` and the held-out scores of folds
    `< Y`, and NOTHING else. It intersects the per-fold admissible sets per its pre-registered
    aggregation, then takes the in-fold-metric argmin over that set. With no prior fold it falls back
    to `EMPTY_EVIDENCE_LAMBDA`: a check that did not run is not a check that passed."""
    years = [f["year"] for f in folds]
    out = {}
    for y in years:
        prior = [p for p in years if p < y]
        per_fold = {p: evidence[form][p]["admissible"] for p in prior}
        allowed = LR.aggregate_admissible(per_fold, bool(cfg["constrained"]))
        inner = ({float(lam): float(np.mean([lam_scored[form][float(lam)]["per_fold_metric"][p]
                                             for p in prior]))
                  for lam in LR.LAMBDA_GRID} if prior else {})
        pick = LR.select_lambda(allowed, inner)
        out[y] = {**pick, "folds_seen": prior}
    return out


def holds_out(form: str, lam_by_fold: dict, evidence: dict) -> dict:
    """⭐ THE CONSTRAINTS EVALUATED OUT-OF-SAMPLE — the question that decides a publish.

    For each held-out season, does the λ the rule chose from PRIOR folds satisfy C1 ∧ C2 ∧ C3 on THAT
    season's own data and board — which the rule never saw? An arm that satisfies them only in-sample
    has demonstrated nothing: the in-sample set is what the rule optimised against."""
    per = {}
    for y, lam in lam_by_fold.items():
        rec = evidence[form][y]["per_lambda"].get(float(lam))
        per[y] = {"lam": float(lam), **(rec or {"admissible": False, "note": "λ not on the grid"})}
    return {"holds_out": bool(per) and all(v.get("admissible") for v in per.values()),
            "per_fold": per,
            "c2_only": bool(per) and all(v.get("c2_placement_ok") for v in per.values()),
            "c3_only": bool(per) and all(v.get("c3_coverage_ok") for v in per.values()),
            "failing_folds": [y for y, v in per.items() if not v.get("admissible")]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Selection + deflation under the PRE-REGISTERED pooled framing
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _row(rec: dict, years: list[int]) -> np.ndarray:
    return np.array([rec["per_fold_metric"].get(y, np.nan) for y in years], dtype=float)


def select_pooled(arms: list[dict], inc: dict, years: list[int], placements: dict) -> dict:
    """Pick + deflate under the PRE-REGISTERED pooled framing: ONE hypothesis, ONE test, no
    multiplicity correction.

    Eligibility = shippable AND all three constraints satisfied OUT-OF-SAMPLE on every fold.
    `winner = None` with candidates present is a REAL result, not a bug: it means no arm satisfied the
    constraints, which is this story's own null.

    ⚠️ PBO is computed over the ELIGIBLE set — the search the selection ACTUALLY ran (NF1.8) — and the
    MATCHED FOILS are excluded from both the eligible set and the DSR trial field, because a
    diagnostic is never a trial (MH2 (a)). Both the whole-field and the contender-set DSR are
    reported; the WHOLE-FIELD reading is the pre-registered gate."""
    inc_row = _row(inc, years)
    inc_metric = round(float(np.nanmean(inc_row)), 4)

    cands = []
    for r in arms:
        if r.get("is_foil"):
            continue
        row = _row(r, years)
        place = placements.get(r["label"], {}) or {}
        cands.append({"rec": r, "row": row, "metric": round(float(np.nanmean(row)), 4),
                      "placement": place,
                      "eligible": bool(r.get("shippable") and place.get("holds_out", False))})

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["metric"]) if eligible else None
    best_any = min(cands, key=lambda c: c["metric"]) if cands else None

    mat = pd.DataFrame({c["rec"]["label"]: dict(zip(years, c["row"])) for c in cands}).sort_index()
    defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)
    # ⭐ THE DISCLOSURE THAT KEEPS A CONSTRAINT-REFUSED RECORD READABLE. PBO is computed over the
    #   ELIGIBLE set — the search the selection ACTUALLY ran (NF1.8) — and when a constraint refuses
    #   every recalibrating arm that set collapses to the NULL alone, leaving PBO/DSR UNDEFINED. That
    #   is correct and it is also uninformative, so the UNRESTRICTED reading is reported beside it:
    #   the overfitting state of the search that WOULD have run had the constraint not bound.
    #   ⛔ It gates nothing — reading it as the story's PBO would be exactly the post-hoc field
    #   widening MH2 (a) forbids in the other direction.
    defl_unrestricted = NF18.deflate(mat, subset=None)

    means = mat.mean(axis=0).sort_values()
    ctr_labels = set(means.index[:max(3, len(means) // 4)])
    trial, ctr = [], []
    for c in cands:
        d = inc_row - c["row"]
        d = d[np.isfinite(d)]
        sr = float(d.mean() / d.std(ddof=1)) if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan
        trial.append(sr)
        if c["rec"]["label"] in ctr_labels:
            ctr.append(sr)

    dsr = dsr_ctr = pval = None
    deltas: list[float] = []
    if best is not None:
        raw = inc_row - best["row"]
        deltas = [float(x) for x in raw[np.isfinite(raw)]]
        dsr = M11.deflated_sharpe(np.array(deltas), np.array(trial, dtype=float))
        dsr_ctr = M11.deflated_sharpe(np.array(deltas), np.array(ctr, dtype=float))
        pval = M11.onesided_paired_pvalue(np.array(deltas))

    return {
        "framing": LR.PREREGISTERED_FRAMING, "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_metric": inc_metric,
        "winner": None if best is None else {
            **{k: best["rec"].get(k) for k in ("label", "key", "form", "space", "rule",
                                               "recalibrates", "shippable", "lam_by_fold")},
            "metric": best["metric"], "bias": best["rec"].get("bias"),
            "mae": best["rec"].get("mae"), "coverage80": best["rec"].get("coverage80"),
            "universe_bias": best["rec"].get("universe_bias"),
            "rho": {q: best["rec"].get(f"rho_{q}") for q in LR.RECALIBRATED_POSITIONS}},
        "best_any": None if best_any is None else {
            "label": best_any["rec"]["label"], "metric": best_any["metric"],
            "eligible": best_any["eligible"]},
        "ordering": None if best is None else {
            "per_position": {q: {"rho": best["rec"].get(f"rho_{q}"),
                                 "ok": bool((best["rec"].get(f"rho_{q}") or 0)
                                            >= 1.0 - LR.ORDERING_DO_NO_HARM)}
                             for q in LR.RECALIBRATED_POSITIONS}},
        "coverage": None if best is None else best["rec"].get("coverage_pooled"),
        "placement": None if best is None else best["placement"],
        "deflation": {**defl, "dsr": dsr, "dsr_contenders": dsr_ctr},
        "deflation_unrestricted_disclosure": {
            **defl_unrestricted,
            "note": ("the search that WOULD have run had the constraints not bound — a DISCLOSURE "
                     "only, gating nothing; the pre-registered PBO is over the ELIGIBLE set")},
        "pvalue": pval, "per_fold_delta": [round(x, 4) for x in deltas],
        "eligible_labels": [c["rec"]["label"] for c in eligible],
        "ineligible": [{"label": c["rec"]["label"], "metric": c["metric"],
                        "holds_out": bool(c["placement"].get("holds_out")),
                        "failing_folds": c["placement"].get("failing_folds"),
                        "c2_ok": bool(c["placement"].get("c2_only")),
                        "c3_ok": bool(c["placement"].get("c3_only"))}
                       for c in cands if not c["eligible"]],
    }


def per_position_disclosure(arms: list[dict], inc: dict, years: list[int],
                            placements: dict) -> dict:
    """The framing this story did NOT pre-register, computed rather than speculated about.

    ⚠️ REPORTED, NEVER SELECTED ON. The pre-registered pooled framing governs; if the two readings
    disagree that is a disclosure, not a licence to take the other one (E2.1-r)."""
    out = {"per_position": [], "bh_cutoff_unconditional": round(LR.ALPHA / 4, 4)}
    pvals: dict[str, float | None] = {}
    for q in LR.RECALIBRATED_POSITIONS:
        inc_row = np.array([inc["per_fold"][y]["per_position"].get(q, {}).get(LR.SELECTION_METRIC,
                                                                              np.nan)
                            for y in years], dtype=float)
        cands = []
        for r in arms:
            if r.get("is_foil"):
                continue
            row = np.array([r["per_fold"][y]["per_position"].get(q, {}).get(LR.SELECTION_METRIC,
                                                                            np.nan)
                            for y in years], dtype=float)
            place = placements.get(r["label"], {}) or {}
            cands.append({"rec": r, "row": row, "metric": float(np.nanmean(row)),
                          "eligible": bool(r.get("shippable") and place.get("holds_out", False))})
        elig = [c for c in cands if c["eligible"]]
        best = min(elig, key=lambda c: c["metric"]) if elig else None
        mat = pd.DataFrame({c["rec"]["label"]: dict(zip(years, c["row"]))
                            for c in cands}).sort_index()
        defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in elig] or None)
        trial = []
        for c in cands:
            d = inc_row - c["row"]
            d = d[np.isfinite(d)]
            trial.append(float(d.mean() / d.std(ddof=1))
                         if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        dsr = pval = None
        if best is not None:
            dd = (inc_row - best["row"])[np.isfinite(inc_row - best["row"])]
            dsr = M11.deflated_sharpe(dd, np.array(trial, dtype=float))
            pval = M11.onesided_paired_pvalue(dd)
        pvals[q] = pval
        out["per_position"].append({
            "position": q, "incumbent_metric": round(float(np.nanmean(inc_row)), 4),
            "winner": None if best is None else best["rec"]["label"],
            "metric": None if best is None else round(best["metric"], 4),
            "delta": (None if best is None
                      else round(best["metric"] - float(np.nanmean(inc_row)), 4)),
            "pbo": defl.get("pbo"), "dsr": dsr, "pvalue": pval})
    out["fdr"] = M11.bh_fdr(pvals, q=LR.ALPHA)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MATCHED FOIL — did the PER-GAME channel earn the result? (NF-D15 (g′))
# ══════════════════════════════════════════════════════════════════════════════════════════════
def foil_attribution(arms: list[dict], foils: list[dict], years: list[int]) -> dict:
    """Pair every per-game arm with its SEASON-TOTAL twin — identical in family, fit population, λ
    machinery and metric, differing ONLY in whether the correction's intercept scales with expected
    games — and read the PAIRED per-fold delta.

    NF-D15's lesson is why this is not optional: a lift can be real and its stated mechanism still be
    refuted. "The per-game arm won" is not "it won because the correction scales with availability".

    ⭐ AND THE SPACE-INVARIANT FORMS ARE REPORTED AS AN EXPECTED TIE, PRE-REGISTERED IN
    `LR.SPACE_INVARIANT_FORMS`. A purely multiplicative correction satisfies `k·(p/g)·g ≡ k·p`, so the
    channel CANNOT ACT on them and their paired delta must be exactly 0. Presenting that as a passed
    test would be claiming a mechanism acted where it structurally cannot (NF-D16 (2)); measuring it
    is what turns "the foil would not bite here" from an assertion into a number."""
    by_form = {(r.get("form"), r.get("rule")): r for r in foils}
    rows = []
    for r in arms:
        if r.get("is_foil") or not r.get("recalibrates"):
            continue
        twin = by_form.get((r.get("form"), r.get("rule")))
        if twin is None:
            continue
        d = _row(r, years) - _row(twin, years)
        d = d[np.isfinite(d)]
        invariant = r.get("form") in LR.SPACE_INVARIANT_FORMS
        rows.append({
            "arm": r["label"], "foil": twin["label"], "form": r.get("form"),
            "per_game_crps": r[LR.SELECTION_METRIC], "season_total_crps": twin[LR.SELECTION_METRIC],
            "paired_delta": round(float(d.mean()), 6) if len(d) else None,
            "max_abs_fold_delta": round(float(np.max(np.abs(d))), 9) if len(d) else None,
            "per_game_wins": bool(len(d) and d.mean() < 0),
            "space_invariant_by_construction": invariant,
            "expected_tie_holds": (bool(len(d) and np.max(np.abs(d)) < 1e-6) if invariant else None),
        })
    acting = [r for r in rows if not r["space_invariant_by_construction"]]
    invariant = [r for r in rows if r["space_invariant_by_construction"]]
    return {
        "rows": rows, "n_pairs": len(rows),
        "n_space_acting_pairs": len(acting),
        "space_invariance_proven": bool(invariant) and all(r["expected_tie_holds"]
                                                           for r in invariant),
        "per_game_wins_where_the_channel_can_act": (
            sum(1 for r in acting if r["per_game_wins"]), len(acting)),
        "reading": ("per_game_earns_it"
                    if acting and all(r["per_game_wins"] for r in acting)
                    else "season_total_earns_it"
                    if acting and not any(r["per_game_wins"] for r in acting)
                    else "mixed" if acting else "channel_cannot_act_anywhere"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The null taxonomy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def classify_this_null(arms: list[dict], inc: dict, years: list[int], placements: dict,
                       premise: dict) -> dict:
    """⭐ WHICH KIND OF NULL IS THIS? — run the taxonomy, and say plainly where it does not fit.

    MH2's rule is that a recorded null must NAME its state, because a null read as the wrong kind
    emits the wrong next step. `cv_power.classify_null` classifies STATISTICAL nulls; NF-D18 added
    `CONSTRAINT_REFUSED` for a null produced by a DETERMINISTIC constraint, where no sampling error
    accumulates and more data can never change the answer.

    ⭐ THIS STORY CAN ALSO PRODUCE A THIRD KIND THE TAXONOMY DOES NOT CONTAIN, AND NAMING IT IS PART
    OF THE RESULT: if the PREMISE does not reproduce in the pre-registered population, the null is not
    about power or about a constraint at all — there was no defect of the claimed size to correct, and
    the remedy is to re-scope the CLAIM, never to run more folds or loosen a gate."""
    from betting_ml.utils import cv_power as CP

    inc_row = _row(inc, years)
    recal = [r for r in arms if r.get("recalibrates") and not r.get("is_foil")
             and r.get(LR.SELECTION_METRIC) is not None]
    if not recal:
        return {"state": "UNDEFINED", "reason": "no recalibrating arm scored"}
    best = min(recal, key=lambda r: r[LR.SELECTION_METRIC])
    d = inc_row - _row(best, years)
    d = d[np.isfinite(d)]
    sr = float(d.mean() / d.std(ddof=1)) if len(d) >= 3 and d.std(ddof=1) > 1e-12 else None
    v = CP.classify_null(metric=LR.SELECTION_METRIC, n_folds=len(years),
                         n_arms=len([r for r in arms if not r.get("is_foil")]),
                         beats_foil=bool(d.mean() > 0), observed_sr=sr,
                         fold_wins=int((d > 0).sum()))
    beat_inc = [r["label"] for r in recal
                if r[LR.SELECTION_METRIC] < (inc.get(LR.SELECTION_METRIC) or np.inf)]
    refused = [r["label"] for r in recal
               if not (placements.get(r["label"], {}) or {}).get("holds_out")]
    all_refused = bool(recal) and len(refused) == len(recal)
    constraint_refused = bool(all_refused and beat_inc)
    premise_failed = not premise.get("premise_confirmed", False)

    state = ("PREMISE_NOT_REPRODUCED" if premise_failed else
             "CONSTRAINT_REFUSED" if constraint_refused else v.state)
    return {
        "state": state, "taxonomy_would_say": v.state,
        "taxonomy_fits": not (constraint_refused or premise_failed),
        "why": ("the pre-registered population does not reproduce the motivating defect, so there was "
                "no level shift of the claimed size to correct — a statistical state would emit a "
                "re-test trigger for an effect whose SCOPE, not whose power, is the finding"
                if premise_failed else
                "every recalibrating arm BEAT the incumbent on the metric and was removed by a "
                "DETERMINISTIC constraint with no sampling error to accumulate, so a statistical "
                "state would emit a re-test trigger more folds cannot satisfy"
                if constraint_refused else
                "at least one recalibrating arm survived the constraints, so whatever refused this "
                "story was the METRIC or the deflation gates — the taxonomy applies as written"),
        "best_recalibrating_arm": best["label"],
        "best_recalibrating_metric": best[LR.SELECTION_METRIC],
        "incumbent_metric": inc.get(LR.SELECTION_METRIC),
        "beats_incumbent_on_accuracy": bool(d.mean() > 0),
        "fold_wins": int((d > 0).sum()), "n_folds": len(d),
        "observed_sr": None if sr is None else round(sr, 4),
        "dsr_ceiling_at_this_fold_count": (round(float(CP.dsr_ceiling(len(years))), 4)
                                           if hasattr(CP, "dsr_ceiling") else None),
        "arms_that_beat_the_incumbent": beat_inc,
        "arms_refused_by_the_constraints": refused,
        "remedy": ("re-scope the CLAIM to the population the defect is actually in — ⛔ never more "
                   "folds and never a looser gate" if premise_failed else
                   "a different MECHANISM or a PM decision — never more folds, which cannot move a "
                   "deterministic constraint" if constraint_refused else
                   getattr(v, "remedy", None)),
        "wider_window_is_reachable_now": True,
        "wider_window_note": (
            f"the veteran panel reaches target season {min(LR.WIDE_WINDOW_SEASONS)}, so the METRIC is "
            f"recomputable on {len(LR.WIDE_WINDOW_SEASONS)} folds today; ⛔ C2 is NOT, because the "
            "merged boards begin at 2019 and an unevaluable constraint is never a pass. Widening the "
            "constraint window requires an operator rebuild of the boards "
            "(`run_season_projection --backtest-from 2013`)."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "_(none)_\n"
    cols = cols or list(rows[0].keys())
    head = "| " + " | ".join(cols) + " |\n|" + "|".join(["---"] * len(cols)) + "|\n"
    body = "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)
    return head + body


def write_report(res: dict) -> tuple[Path, Path]:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = _REPORT_DIR / f"{_STEM}.json"
    mp = _REPORT_DIR / f"{_STEM}.md"
    jp.write_text(json.dumps(res, indent=2, default=str))

    pre = res["premise"]
    sel = res["selection"]
    ver = res["verdict"]
    L = []
    A = L.append
    A(f"# NF-RECAL1 — recalibrating the fastpath VETERAN point LEVEL\n")
    A(f"_generated {res['generated_at']}_ · `best_alpha = 0` · "
      f"model `{LR.MODEL_VERSION}` · recalibrates `{LR.RECALIBRATES}`\n")
    A(f"## Verdict: **{res['headline']}**\n")
    A(res["verdict_prose"] + "\n")

    A("## 0. PREMISE CHECK — does the motivating defect reproduce in this population?\n")
    A("⭐ A recalibration is a correction fitted to a measured defect, so the defect is re-measured "
      "in the population this story fits on **before** anything is fitted. The tier is fixed by the "
      "INCUMBENT's own projection (`TIER_ANCHOR`), identically for every arm.\n")
    A(_md_table(pre["table"], ["reading", "n", "mean_bias", "median_bias", "ours_over_actual",
                               "pct_zero_outcome"]))
    A(f"\nMotivating figure (NF-TR1): n **1165**, mean **−37.7**, median **−34.5**, "
      f"our/actual QB 0.923 · RB 0.693 · WR 0.778 · TE 0.816.\n")
    A(_md_table([{"position": q,
                  "n": pre["draftable_tier_incumbent_anchor"]["per_position"].get(q, {}).get("n"),
                  "mean_bias (measured)":
                      pre["draftable_tier_incumbent_anchor"]["per_position"].get(q, {})
                      .get("mean_bias"),
                  "our/actual (measured)":
                      pre["draftable_tier_incumbent_anchor"]["per_position"].get(q, {})
                      .get("ours_over_actual"),
                  "our/actual (motivating)": pre["motivating_figures"]["ours_over_actual"][q],
                  "sign agrees": pre["per_position_sign_agrees_with_motivating"].get(q)}
                 for q in LR.RECALIBRATED_POSITIONS]))
    A(f"\n`premise_confirmed` = **{pre['premise_confirmed']}** · "
      f"`reproduces_motivating_magnitude` = **{pre['reproduces_motivating_magnitude']}**\n")

    A("## 1. The field, and where each arm landed\n")
    A(_md_table(res["leaderboard"]))
    A("\n### Anchors (two-sided, scored every run) — each with its REQUIRED direction\n")
    A(_md_table(res["anchor_table"], ["anchor", "role", "expected", "CRPS", "MAE", "bias", "cov80",
                                      "behaves as expected"]))
    A("\n### Do the constraints have TEETH? — the degenerates read in both directions (NF1.8)\n")
    A("A CONSTRAINT a do-nothing arm satisfies is fine (the metric eliminates it); a CRITERION a "
      "do-nothing arm WINS is fatal. And a gate nothing is ever measured FAILING has examined "
      "nothing. Both halves are measured here rather than asserted.\n")
    A(_md_table([{k: v for k, v in r.items() if k != "per_fold"}
                 for r in res["anchor_constraint_state"]]))
    A("\n### Per-form peeking ceilings — must ORDER BY CAPACITY (NF-D16 (g‴))\n")
    A(_md_table(res["ceiling_table"]))
    A(f"\n`ceilings_order_by_capacity` = **{res['ceilings_order_by_capacity']}** (CRPS-fitted) vs "
      f"**{res['ceilings_order_by_capacity_least_squares_fit']}** (least-squares-fitted).\n\n"
      "⭐ **A THIRD REQUIREMENT ON A PEEKING CEILING, MEASURED HERE: MATCHED OBJECTIVE.** NF1.7 (b) / "
      "NF1.9 (f) / NF-D16 (g‴) require matched FAMILY and matched SAMPLE. This run's first cut fitted "
      "each ceiling by least squares — the candidates' own estimator — and scored it on CRPS, and the "
      "ceilings did not order by capacity even though the families strictly nest. \"Peeking can only "
      "help\" holds only when the peeking fit minimises the objective the arm is SCORED on; an "
      "LS-fitted ceiling is not a bound on a CRPS-scored arm, it is just another arm. Fitting each "
      "ceiling on CRPS restores the ordering and makes `family_ceiling_check` a real inversion "
      "detector rather than a coin flip. One shared ceiling would separately have vetoed a "
      "legitimately-better nested form as an inversion.\n")

    A("## 2. Matched foil — did the PER-GAME channel earn it? (NF-D15 (g′))\n")
    A(_md_table(res["attribution"]["rows"],
                ["arm", "form", "per_game_crps", "season_total_crps", "paired_delta",
                 "space_invariant_by_construction", "expected_tie_holds"]))
    A(f"\nreading = **{res['attribution']['reading']}** · "
      f"`space_invariance_proven` = **{res['attribution']['space_invariance_proven']}** "
      "(a purely multiplicative correction satisfies `k·(p/g)·g ≡ k·p`, so the per-game channel "
      "CANNOT act on three of the five forms — pre-registered as an expected tie and proven, not "
      "discovered).\n")
    A("\n### Permutation vacuity — pre-registered as a TIE, and the SPACE is what decides it\n")
    A("A within-position shuffle preserves that position's MARGINAL exactly, so it cannot move a "
      "SEASON-TOTAL additive level (`c = mean(y − p)`). It DOES move the per-game one "
      "(`c = Σg(y − p)/Σg²`), which re-pairs each outcome with a different expected-games value. ⇒ "
      "the per-game parameterisation makes a level correction stop being a pure marginal statistic — "
      "which is also why the per-game hypothesis is testable at all. Measured, not asserted.\n")
    A(_md_table(res["permutation_vacuity"]))
    A(f"\n### Attribution signature (a level fix moves bias TOWARD zero while accuracy improves)\n")
    A(_md_table([res["signature"]]))

    A("## 3. Constraints\n")
    A("### C2 activity — how many folds can the placement clause even act on? (NF-D20 (g⁗))\n")
    A(_md_table(res["constraint_activity"]))
    A("\n### Out-of-sample constraint state per arm\n")
    A(_md_table(res["constraint_table"]))
    A("\n### Whole-board CROSS-POSITION movement — MEASURED, gated on by NOTHING\n")
    A("⛔ NF-D17 validated a placement clause for the ROOKIE leg; this programme owns **no validated "
      "bar** for whole-board veteran churn, and inventing one on the population whose answer is "
      "already in view is the E2.1-r move. The number is handed to the PM instead.\n")
    A(_md_table(res["cross_position_table"]))

    A("## 4. Deflation + the pre-registered gate\n")
    A(_md_table([res["gate_table"]]))
    A(f"\nPBO over the ELIGIBLE set = `{sel['deflation'].get('pbo')}` · "
      f"whole-field DSR = `{sel['deflation'].get('dsr')}` (**the pre-registered gate**) · "
      f"contender-set DSR = `{sel['deflation'].get('dsr_contenders')}` · "
      f"p = `{sel['pvalue']}`\n")
    A(f"\nPBO over the ELIGIBLE set is `{sel['deflation'].get('pbo')}` — when a constraint refuses "
      "every recalibrating arm the eligible set collapses to the NULL alone and the deflation "
      "statistics are **UNDEFINED, not failed** (MH2: a stat that was not COMPUTABLE must never be "
      "absorbed into a verdict about a mechanism). The unrestricted reading — the search that WOULD "
      f"have run had the constraints not bound — is PBO "
      f"`{res['selection']['deflation_unrestricted_disclosure'].get('pbo')}`, "
      f"OS-degradation `{res['selection']['deflation_unrestricted_disclosure'].get('os_gap_pct')}`. "
      "⛔ It gates nothing.\n")
    A(f"\nSensitivities: {json.dumps(res['sensitivities'])}\n")
    A("\n### Per-position disclosure — computed, NEVER selected on\n")
    A(_md_table(res["per_position"]["per_position"]))

    A("## 5. Null state\n")
    A(_md_table([{k: v for k, v in res["null"].items()
                  if k in ("state", "taxonomy_would_say", "taxonomy_fits",
                           "beats_incumbent_on_accuracy", "fold_wins", "n_folds", "observed_sr")}]))
    A(f"\n**why** — {res['null']['why']}\n")
    A(f"\n**remedy** — {res['null']['remedy']}\n")
    A(f"\n{res['null']['wider_window_note']}\n")

    A("## 6. Story-level verdict\n")
    A(_md_table([ver]))
    A("\n## 7. Scope + serving\n")
    A(f"- ⛔ **Rookie leg out of scope.** {LR.ROOKIE_EXCLUSION_REASON}\n")
    A(f"- **QB in scope.** {LR.QB_INCLUSION_REASON}\n")
    A("- ⛔ **NF1.5's ORDERING layer is untouched.** This story changes LEVELS only.\n")
    A("- 🔒 **CODE-READY, NOT DEPLOYED.** Any serving flip is a POST-LAUNCH operator step with its "
      "own soak, and a level shift moves the band centre ⇒ `run_interval_revalidation` is REQUIRED "
      "before publish (this is the gate that refused NF-D21).\n")
    mp.write_text("".join(L))
    return jp, mp


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true", help="reduced form set; proves the path only")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    seasons = LR.PANEL_SEASONS
    tier_n = LR.draftable_tier_size()
    log.info("NF-RECAL1 — veteran LEVEL recalibration · folds %s · draftable tier %d/season "
             "(DERIVED from the '%s' preset × %d teams)",
             list(seasons), tier_n, LR.TIER_PRESET, LR.DRAFT_TEAMS)

    # Panel over the WIDE window so every fold has a deep in-fold history; folds are the PANEL_SEASONS.
    d = load_panel(tuple(sorted(set(LR.WIDE_WINDOW_SEASONS) | set(seasons))))
    boards = load_boards(seasons)
    tier = tier_mask(d, tier_n)

    premise = premise_check(d, tier_n)
    log.info("§0 premise — pre-registered tier reading: mean bias %.2f (n %d); "
             "universe %.2f; realized-anchored tier %.2f",
             premise["draftable_tier_incumbent_anchor"]["mean_bias"],
             premise["draftable_tier_incumbent_anchor"]["n"],
             premise["universe"]["mean_bias"],
             premise["draftable_tier_realized_anchor"]["mean_bias"])

    folds = build_folds(d, tier, seasons)
    years = [f["year"] for f in folds]
    fits = {f["year"]: fold_fits(f) for f in folds}
    forms = (LR.FORMS[:2] + (LR.LEARNED_FOIL,)) if args.smoke else LR.FORMS

    # ── the constant-λ grid, scored once per (form, space, λ): the substrate every rule reads ──
    lam_scored: dict = {}
    for space in LR.SPACES:
        for form in forms:
            lam_scored.setdefault((space, form), {})
            for lam in LR.LAMBDA_GRID:
                lam_scored[(space, form)][float(lam)] = score_arm(
                    folds, fits,
                    form_adjuster(form, space, (form, space), lambda f, L=lam: L),
                    f"{form}·{space}·λ={lam:g}")
    primary_lam = {form: lam_scored[(LR.PRIMARY_SPACE, form)] for form in forms}

    evidence = build_fold_evidence(folds, fits, boards, forms=forms)
    activity = constraint_activity(evidence)

    # ── the candidate arms + their matched season-total foils ──
    incumbent = score_arm(folds, fits,
                          form_adjuster("pos_const", LR.PRIMARY_SPACE, ("pos_const",
                                                                        LR.PRIMARY_SPACE),
                                        lambda f: 0.0),
                          "incumbent (NULL)",
                          extra={"form": "incumbent", "space": LR.PRIMARY_SPACE, "rule": None,
                                 "recalibrates": False, "shippable": True, "is_foil": False})
    arms, foils, placements = [incumbent], [], {}
    placements["incumbent (NULL)"] = {"holds_out": True, "per_fold": {}, "c2_only": True,
                                      "c3_only": True, "failing_folds": []}

    for space, bucket, is_foil in ((LR.PRIMARY_SPACE, arms, False), (LR.FOIL_SPACE, foils, True)):
        for cfg in [c for c in LR.candidate_configs(space=space, smoke=args.smoke)
                    if c["form"] != "incumbent"]:
            form = cfg["form"]
            lam_by_fold = rule_lambdas(form, cfg, folds,
                                       {form: lam_scored[(space, form)]}, evidence)
            lam_map = {y: v["lam"] for y, v in lam_by_fold.items()}
            label = (f"{form} · {cfg['rule']}" if not is_foil
                     else f"{form} · {cfg['rule']} [season_total FOIL]")
            rec = score_arm(folds, fits,
                            form_adjuster(form, space, (form, space),
                                          lambda f, M=lam_map: M[f["year"]]),
                            label,
                            extra={"key": LR.config_key(cfg), "form": form, "space": space,
                                   "rule": cfg["rule"], "recalibrates": True,
                                   "shippable": not is_foil, "is_foil": is_foil,
                                   "lam_by_fold": lam_map,
                                   "lam_detail": {y: v for y, v in lam_by_fold.items()}})
            bucket.append(rec)
            if not is_foil:
                placements[label] = holds_out(form, lam_map, evidence)

    # ── the anchors ──
    # ⭐ BOTH shuffles at BOTH a pure-LEVEL form and the SLOPE-carrying one, so "within TIES on a
    #   level and BITES on a slope" is a matched measurement rather than two different experiments.
    #   `pos_offset` is included because the invariance is EXACT there and only there: a
    #   within-position shuffle preserves mean(y), so `mean(y − p)` is unchanged to machine
    #   precision. For the MULTIPLICATIVE `pos_const` the estimator is mean(y/p), which re-pairs
    #   under the shuffle and therefore moves a little — so "the permutation is vacuous against a
    #   level" is TRUE FOR AN ADDITIVE LEVEL and only APPROXIMATE for a multiplicative one. Scoring
    #   all three is what turns that distinction into a measurement (NF-D16 measured the additive
    #   case at max |Δ| 7e-15 and this run reproduces the same algebra on a different population).
    perm_forms = ("pos_offset", "pos_const", LR.LEARNED_FOIL)
    anchor_tags = (("oracle_perplayer",)
                   + tuple(f"{w}@{f}" for w in ("permuted_across", "permuted_within")
                           for f in perm_forms)
                   + ("zero_project", "pos_median", "over_scale", "wide_band")
                   + tuple(LR.FAMILY_CEILING[f] for f in forms))
    anchors = {t: score_arm(folds, fits, anchor_adjuster(t, folds), t) for t in anchor_tags}
    LR.require_anchors(anchors, required=anchor_tags)
    # The two-sided constraint reading (NF1.8): a do-nothing degenerate must SATISFY the gates, an
    # over-correcting one must BREACH them. Both are measured, neither is argued.
    anchor_constraints = [anchor_constraint_state(folds, fits, boards, anchor_adjuster(t, folds), t)
                          for t in ("zero_project", "over_scale", "wide_band")]

    # ── selection under the pre-registered pooled framing ──
    sel = select_pooled(arms, incumbent, years, placements)
    per_pos = per_position_disclosure(arms, incumbent, years, placements)
    attribution = foil_attribution(arms, foils, years)

    # ── anchor readings ──
    inc_m = incumbent[LR.SELECTION_METRIC]
    # ⭐ THE SANITY DEGENERATES AND THE MAGNITUDE ANCHOR ARE READ SEPARATELY (NF-D20). `over_scale`
    #   winning is NOT a metric inversion — the do-nothing arms still lose by a mile — it is a
    #   REFUTED MAGNITUDE hypothesis, and bundling the two into one flag would make a future reader
    #   distrust a measurement that is fine.
    sanity_degen = {t: anchors[t][LR.SELECTION_METRIC]
                    for t in ("zero_project", "pos_median", "wide_band")}
    degen = {**sanity_degen, "over_scale": anchors["over_scale"][LR.SELECTION_METRIC]}
    best_real = min((r[LR.SELECTION_METRIC] for r in arms if r.get("recalibrates")),
                    default=inc_m)
    # ⭐ THE DISCLOSURE THAT PRODUCED THE MATCHED-OBJECTIVE FINDING: each form's peeking ceiling
    #   fitted BY LEAST SQUARES beside the same ceiling fitted ON CRPS. The LS column is what failed
    #   to order by capacity, and reporting both is what turns "we changed the estimator" into a
    #   measurement a reader can check.
    ls_ceilings = {f: score_arm(folds, fits,
                                form_adjuster(f, LR.PRIMARY_SPACE, ("_peek_ls", f), lambda _f: 1.0),
                                f"oracle_{f} [least-squares fit]")[LR.SELECTION_METRIC]
                   for f in forms}
    ceilings = {f: anchors[LR.FAMILY_CEILING[f]][LR.SELECTION_METRIC] for f in forms}
    ls_order_ok = all(ls_ceilings.get(b) is None or ls_ceilings.get(a) is None
                      or ls_ceilings[b] <= ls_ceilings[a] + 1e-9
                      for a, b in LR.FORM_NESTING if a in ls_ceilings and b in ls_ceilings)
    ceil_rows = [{"form": f, "anchor": LR.FAMILY_CEILING[f],
                  "ceiling fitted on CRPS ⭐": ceilings[f],
                  "ceiling fitted by least squares": ls_ceilings[f],
                  "LS is not a bound (worse than the CRPS fit)":
                      bool(ls_ceilings[f] is not None and ceilings[f] is not None
                           and ls_ceilings[f] > ceilings[f] + 1e-9)}
                 for f in forms]
    order_ok = all(ceilings.get(b) is None or ceilings.get(a) is None
                   or ceilings[b] <= ceilings[a] + 1e-9
                   for a, b in LR.FORM_NESTING if a in ceilings and b in ceilings)
    fc = LR.family_ceiling_check(
        [{**r, "form": r.get("form"), "recalibrates": r.get("recalibrates"),
          LR.SELECTION_METRIC: r.get(LR.SELECTION_METRIC), "label": r["label"]} for r in arms],
        anchors, metric=LR.SELECTION_METRIC,
        family_ceiling={f: LR.FAMILY_CEILING[f] for f in forms})

    signature = LR.attribution_signature(
        incumbent_bias=incumbent["bias"],
        winner_bias=(sel["winner"] or {}).get("bias"),
        incumbent_metric=inc_m, winner_metric=(sel["winner"] or {}).get("metric"))

    gate = LR.pooled_ship(winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
                          ordering=sel["ordering"] or {"per_position": {}},
                          placement=sel["placement"], coverage=sel["coverage"],
                          pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"),
                          pvalue=sel["pvalue"])
    verdict = LR.level_verdict(
        pooled_ships=gate["ship"], premise_confirmed=premise["premise_confirmed"],
        sanity_degenerates_lose=all(v is not None and v > best_real
                                    for v in sanity_degen.values()),
        permutation_across_beaten=all(
            anchors[f"permuted_across@{f}"][LR.SELECTION_METRIC] > best_real
            for f in perm_forms),
        oracle_respected=(anchors["oracle_perplayer"][LR.SELECTION_METRIC] <= best_real + 1e-9),
        family_ceiling_respected=fc["ok"], ceilings_order_by_capacity=order_ok,
        over_scale_loses=(anchors["over_scale"][LR.SELECTION_METRIC] > best_real),
        wide_band_loses=(anchors["wide_band"][LR.SELECTION_METRIC] > best_real),
        rookie_leg_untouched=True,
        space_invariance_proven=attribution["space_invariance_proven"])
    null = classify_this_null(arms, incumbent, years, placements, premise)

    # ── whole-board cross-position movement, on the SERVING board, at each arm's final λ ──
    serving_board = boards[max(seasons)]
    cross_rows = []
    for r in arms:
        if not r.get("recalibrates"):
            continue
        lam = float(r["lam_by_fold"][max(years)])
        vet = ~serving_board["is_rookie"].fillna(False).astype(bool).to_numpy()
        p = pd.to_numeric(serving_board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
        pos = serving_board["position"].astype(str).str.upper().to_numpy()
        g = pd.to_numeric(serving_board.get("proj_games",
                                            pd.Series(np.full(len(serving_board), 17.0))),
                          errors="coerce").to_numpy(dtype=float)
        adj = p.copy()
        a, _, _ = LR.apply_to_band(r["form"], r["space"], fits[max(years)][(r["form"], r["space"])],
                                   p[vet], p[vet], p[vet], pos[vet], g[vet], lam)
        adj[vet] = a
        mv = LR.cross_position_movement(p, adj, pos, serving_board["player_name"].to_numpy())
        cross_rows.append({"arm": r["label"], "λ": lam, **{k: v for k, v in mv.items()
                                                           if not k.startswith("top10_b")
                                                           and not k.startswith("top10_a")}})

    # ⭐ THE FITTED MAP ITSELF — a deliverable even when the correction is REFUSED. NF-D18's frontier
    #   diagnostic is the precedent: "a null that names where the answer lives is the strongest kind".
    #   ⛔ It is a RECORD, not a recommendation: nothing here may be pre-registered forward by a
    #   successor (that is the E2.1-r laundering NF-D20 forbade).
    fitted = []
    for form in forms:
        for y in years:
            prm = fits[y][(form, LR.PRIMARY_SPACE)]
            for k, v in prm.items():
                fitted.append({"form": form, "fold": y, "cell": str(k),
                               "params": (round(v, 4) if isinstance(v, float)
                                          else [round(float(x), 4) for x in v])})
    fitted_summary = []
    for form in forms:
        for cell in sorted({r["cell"] for r in fitted if r["form"] == form}):
            vals = [r["params"] for r in fitted if r["form"] == form and r["cell"] == cell]
            if isinstance(vals[0], list):
                fitted_summary.append({"form": form, "cell": cell,
                                       "mean intercept": round(float(np.mean([v[0] for v in vals])), 3),
                                       "mean slope": round(float(np.mean([v[1] for v in vals])), 4),
                                       "folds": len(vals)})
            else:
                fitted_summary.append({"form": form, "cell": cell,
                                       "mean param": round(float(np.mean(vals)), 4),
                                       "min": round(float(np.min(vals)), 4),
                                       "max": round(float(np.max(vals)), 4), "folds": len(vals)})

    # ⭐ THE PERMUTATION-VACUITY MEASUREMENT (§8). Pre-registered as an expected TIE for a level
    #   form; measured here PER SPACE, because the tie turns out to be a property of the SPACE.
    vac = []
    for f in folds:
        tr = f["train"]
        yv = tr["real_fp_ppr"].to_numpy(dtype=float)
        pv = tr["point"].to_numpy(dtype=float)
        qv = tr["position"].to_numpy()
        gv = tr["proj_games"].to_numpy(dtype=float)
        rng = np.random.default_rng(11 + f["year"])
        ysh = yv.copy()
        for q in LR.RECALIBRATED_POSITIONS:
            idx = np.flatnonzero(qv == q)
            if len(idx) > 1:
                ysh[idx] = rng.permutation(ysh[idx])
        for space in LR.SPACES:
            a = LR.fit_form("pos_offset", space, pv, yv, qv, gv)
            b = LR.fit_form("pos_offset", space, pv, ysh, qv, gv)
            vac.append({"fold": f["year"], "space": space,
                        "max |Δ param| under a within-position shuffle":
                            max(abs(a[q] - b[q]) for q in a) if a and b else None})
    vacuity = [{"space": sp,
                "max |Δ param| across folds": max(r["max |Δ param| under a within-position shuffle"]
                                                  for r in vac if r["space"] == sp),
                "verdict": ("VACUOUS — a pure marginal statistic the shuffle cannot move"
                            if max(r["max |Δ param| under a within-position shuffle"]
                                   for r in vac if r["space"] == sp) < 1e-9
                            else "ACTS — the fit re-pairs each outcome with a different "
                                 "expected-games value, so the correction is NOT purely marginal")}
               for sp in LR.SPACES]

    headline, prose = build_headline(premise, sel, verdict, null, attribution, activity)
    res = {
        "story": "NF-RECAL1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": LR.MODEL_VERSION, "recalibrates": LR.RECALIBRATES, "best_alpha": 0,
        "preregistration": {
            "framing": LR.PREREGISTERED_FRAMING, "framing_reason": LR.FRAMING_REASON,
            "dsr_reading": LR.PREREGISTERED_DSR_READING, "field_reason": LR.FIELD_REASON,
            "metric": LR.SELECTION_METRIC, "metric_reason": LR.METRIC_REASON,
            "tier_anchor": LR.TIER_ANCHOR, "tier_anchor_reason": LR.TIER_ANCHOR_REASON,
            "tier_n": tier_n, "lambda_provenance": LR.LAMBDA_PROVENANCE,
            "rookie_exclusion": LR.ROOKIE_EXCLUSION_REASON, "qb_inclusion": LR.QB_INCLUSION_REASON,
            "forms": list(forms), "spaces": list(LR.SPACES),
            "space_invariant_forms": list(LR.SPACE_INVARIANT_FORMS),
            "lambda_grid": list(LR.LAMBDA_GRID), "rules": list(LR.SELECTION_RULES),
            "declared_trial_field_size": len(arms),
            "gates": {"pbo_max": LR.PBO_MAX, "dsr_min": LR.DSR_MIN, "alpha": LR.ALPHA,
                      "coverage_floor": LR.COVERAGE_FLOOR,
                      "ordering_do_no_harm": LR.ORDERING_DO_NO_HARM},
        },
        "folds": years, "premise": premise, "selection": sel, "per_position": per_pos,
        "attribution": attribution, "signature": signature, "verdict": verdict, "null": null,
        "constraint_activity": activity,
        "ceilings_order_by_capacity": order_ok,
        "ceilings_order_by_capacity_least_squares_fit": ls_order_ok,
        "matched_objective_finding": (
            "a peeking ceiling is a bound only at matched FAMILY, matched SAMPLE and — measured here — matched OBJECTIVE. Fitted by least squares the ceilings do NOT order by capacity; fitted on the CRPS the arms are scored on, they do."),
        "family_ceiling_check": fc,
        "leaderboard": sorted(
            [{"arm": r["label"], "form": r.get("form"), "rule": r.get("rule"),
              "λ (final fold)": (r["lam_by_fold"][max(years)] if r.get("lam_by_fold") else 0.0),
              "CRPS": r[LR.SELECTION_METRIC], "MAE": r["mae"], "bias": r["bias"],
              "cov80": r["coverage80"], "universe CRPS": r["universe_crps"],
              "universe bias": r["universe_bias"],
              "eligible": r["label"] in sel["eligible_labels"]}
             for r in arms], key=lambda x: x["CRPS"]),
        # ⚠️ THE `expected` COLUMN IS NOT DECORATION. A two-sided anchor set is only readable if each
        #    anchor's REQUIRED DIRECTION is stated: an ORACLE must WIN (it peeks) and a DEGENERATE
        #    must LOSE. A single "did it lose?" column reads a correctly-behaving oracle as a failure
        #    and would train a reader to ignore the one table that polices the metric.
        "anchor_table": [{"anchor": t, "role": _anchor_role(t),
                          "expected": ("beats every real arm" if _anchor_role(t) == "ceiling"
                                       else "loses to every real arm"),
                          "CRPS": anchors[t][LR.SELECTION_METRIC],
                          "MAE": anchors[t]["mae"], "bias": anchors[t]["bias"],
                          "cov80": anchors[t]["coverage80"],
                          "behaves as expected": (
                              bool(anchors[t][LR.SELECTION_METRIC] <= best_real + 1e-9)
                              if _anchor_role(t) == "ceiling"
                              else bool(anchors[t][LR.SELECTION_METRIC] > best_real))}
                         for t in anchor_tags],
        "anchor_constraint_state": anchor_constraints,
        "ceiling_table": ceil_rows,
        "constraint_table": [{"arm": lab, "holds out (C1∧C2∧C3)": v.get("holds_out"),
                              "C2 only": v.get("c2_only"), "C3 only": v.get("c3_only"),
                              "failing folds": v.get("failing_folds")}
                             for lab, v in placements.items()],
        "cross_position_table": cross_rows,
        "gate_table": gate,
        "sensitivities": {
            "dsr_at_0.0": bool((sel["deflation"].get("dsr") or -1) >= 0.0),
            "dsr_removed_would_ship": bool(
                all(v for k, v in gate.items() if k not in ("ship", "framing", "dsr_ok"))),
            "expanded_field_trials": len(arms) + len(forms) * len(LR.LAMBDA_GRID),
            "note": ("the EXPANDED reading counts every constant-λ point as its own trial; the "
                     "pre-registered field is the RULES (MH2 (a): a family gets its own declared "
                     "field, and ⛔ trimming one after the fact under-taxes it)"),
        },
        "permutation_vacuity": vacuity, "permutation_vacuity_per_fold": vac,
        "fitted_map": fitted, "fitted_map_summary": fitted_summary,
        "registry_action": {
            "registry": "betting_ml/models/model_family_registry.yaml (NF-G0)",
            "action": "NONE — nothing was promoted",
            "reason": ("the promotion state machine has states pending/challenger/champion/"
                       "deprecated and NO state for a recorded null; a `challenger` entry means "
                       "'artifact built + STAGED', which would misrepresent a refused arm as being "
                       "on a publish path. NF-D18 and NF-D20 — both CONSTRAINT_REFUSED — likewise "
                       "created no entry. The record of this story is its ablation memo."),
        },
        "headline": headline, "verdict_prose": prose,
    }
    if not args.no_report:
        jp, mp = write_report(res)
        log.info("wrote %s and %s", jp, mp)
    log.info("VERDICT: %s", headline)
    return 0


def build_headline(premise, sel, verdict, null, attribution, activity) -> tuple[str, str]:
    """The one-line verdict and its prose, DERIVED from the run rather than written by hand — so the
    report cannot say something the numbers do not."""
    if not premise["premise_confirmed"]:
        h = "NO CORRECTION — the motivating defect does not reproduce in the pre-registered population"
    elif verdict["ship"]:
        h = f"SHIP-READY (code-ready, not deployed) — {sel['winner']['label']}"
    elif null["state"] == "CONSTRAINT_REFUSED":
        h = "RECORDED NULL — CONSTRAINT_REFUSED"
    else:
        h = f"RECORDED NULL — {null['state']}"

    pre = premise["draftable_tier_incumbent_anchor"]
    prose = (
        f"On the pre-registered population — the veteran leg's draftable tier, fixed by the "
        f"INCUMBENT's own projection — the measured level bias is **{pre['mean_bias']} PPR** over "
        f"n = {pre['n']}, against the motivating **−37.7** over n = 1165. The unconditional universe "
        f"reading is **{premise['universe']['mean_bias']}** and the same tier anchored on the "
        f"REALIZED outcome is **{premise['draftable_tier_realized_anchor']['mean_bias']}** — the "
        f"spread across those three readings is the whole methodological point, and it is why the "
        f"anchor is pre-registered rather than chosen.\n\n"
        f"Best recalibrating arm: `{null['best_recalibrating_arm']}` at CRPS "
        f"{null['best_recalibrating_metric']} vs the incumbent's {null['incumbent_metric']} "
        f"({null['fold_wins']}/{null['n_folds']} folds). "
        f"Matched-foil reading: **{attribution['reading']}**. "
        f"Null state: **{null['state']}**.")
    return h, prose


if __name__ == "__main__":
    raise SystemExit(main())

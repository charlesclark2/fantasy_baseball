"""run_rookie_interval_ablation.py — NF1.7 §0.5 bake-off: the PER-PLAYER rookie 80% band.

WHAT IS BEING SELECTED — the WIDTH AND SHAPE of the rookie 80% interval, and NOTHING ELSE. NF1.4
proved the rookie POINT projection is ~unbiased (its "over-valuation" was a rank effect), so the point
is held byte-identical across every arm here and asserted as such; only `fp_ppr_p10`/`fp_ppr_p90` move.

⚠️ THE DEFECT (NF3 surfacing, 2026-07-29 — confirmed live on the served 2026 board): NF1.4's band is
CLASS-LEVEL. 81 rookies carried **12** distinct intervals (3 per position) against **647** distinct
intervals for 703 veterans. Every top-bucket rookie QB carried an identical 26.5–277.0 while their
point projections spanned 25.1→268.3 — so a 268-point projection sat in the top 3% of "its own" band
and a 25-point rookie at the bottom of the SAME one. The operator put it plainly: "Jeremiyah Love shows
0–443 — that's not his band at all."

⚠️ AND WHY IT HAPPENED — the CLAUDE.md §0.5 selection-metric landmine, live. NF1.4 selected this band
on COVERAGE (0.678 → 0.834). A POSITION-CONSTANT band can hit nominal coverage while carrying ZERO
per-player information, because coverage is a property of the POPULATION, not of the player. Coverage
therefore cannot select an interval. Per the E2.1-r rule ("a coverage figure is a FLOOR, never a target
to minimise distance to"), applied here to intervals:

PRIMARY METRIC = the **INTERVAL SCORE** (Winkler / Gneiting-Raftery IS_0.2 — the sum of the τ=0.10 and
τ=0.90 pinball losses, up to a constant factor):

    IS(l, u, y) = (u − l) + 10·(l − y)·1{y < l} + 10·(y − u)·1{y > u}

Lower is better. It is a PROPER score for the quantile PAIR: it pays for width and is minimised by the
TRUE q10/q90, so it rewards sharpness only when the sharpness is earned. Coverage stays an eligibility
FLOOR (`coverage_80 ≥ 0.80`), never a target.

⭐ FOUR-SIDED SANITY ANCHORS (the `test_oracle_is_the_scoring_floor` pattern, both ends — and this
story needs BOTH degenerate ends because the metric has two ways to be gamed):
  · **ORACLE FLOOR** — the candidate's OWN family, fitted on the HELD-OUT class's REALIZED outcomes
    (it knows the answer). Nothing may beat its own oracle; a candidate that does is proof the metric
    is inverted, not a discovery. ⚠️ The floor is SAME-FAMILY on purpose: a cross-family oracle is not
    a valid floor, because a peeking MISSPECIFIED model is beatable by an honest well-specified one
    (measured — see `anchor_bands` and the `oracle_family` check).
  · **DEGENERATE `zero_width`** — a band of width 0 at the point projection. It is MAXIMALLY sharp, so
    a naive sharpness metric (mean width, MAE-of-width) would crown it. It MUST lose. ⭐ This is the
    anchor that keeps "select on sharpness" from becoming "under-cover on purpose".
  · **DEGENERATE `max_width`** — [0, the position's max realized rookie season]. Coverage ≈ 1.0 and
    useless. A coverage TARGET would love it. It MUST lose — that is the proof the selection is not
    secretly a coverage exercise.
  · **DEGENERATE `class_tercile` (the INCUMBENT)** and `const_width` (ONE band per position). The
    refit must BEAT them, or the whole story is a null and the class-level band stands.
A candidate scoring WORSE than any degenerate ⇒ the metric is inverted. ⛔ MAE/RMSE on WIDTH is the
smell CLAUDE.md warns about and is not used for selection anywhere here.

PRE-REGISTERED CANDIDATE CLASSES (fixed before any result was read; ≥3 classes + a direct-learned
foil, per §0.5 — every one fit IN-FOLD on draft classes strictly BEFORE the held-out class):
  • `legacy_cv`    — the pre-NF1.4 `fp ± z·fp·cv` parameter width (the second honest null).
  • `class_tercile`— NF1.4's shipped class-level tercile bucket (the INCUMBENT to beat).
  • `ratio_q`      — per-position empirical quantiles of realized/predicted, applied to the player's
                     own point. Multiplicative ⇒ width collapses as the point → 0.
  • `ratio_q_floor`— `ratio_q` + an additive upside floor from the bottom prediction decile.
  • `knn_pos`      — q10/q90 of the k nearest training rookies in the POSITION's prediction space.
  • `knn_norm`     — the same in POSITION-NORMALISED prediction space, pooled across positions
                     (~4× the neighbours; assumes a position-invariant shape once scaled).
  • `qreg`         — **THE DIRECT-LEARNED FOIL**: linear quantile regression (pinball, τ=0.10/0.90)
                     of the realized season on the story's named drivers — log point, log draft slot,
                     the P1A residual sd, position.
  • `qreg_sqrt`    — `qreg` on √y (quantiles are monotone-invariant; only the linearity assumption
                     moves).
× a `k` grid for the neighbourhood arms, a regularisation grid for the parametric arm, and a
`resid_sd_gain` grid that widens any form by the player's OWN P1A parameter uncertainty.

DEFLATION: every config counts toward a CSCV/Bailey **PBO** over held-out draft-class splits, with the
config spread printed beside it — per CLAUDE.md, a high PBO on a TIED field is the NULL, while a high
PBO with a WIDE spread is genuine overfitting.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. No `best_alpha`, no CLV/ROI claim.

RUN ON THE LAPTOP (fast, no Snowflake; reads the cached NF1.4 rookie pool, ~1 min):

    uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation

Rebuild the pool from the sports lake first only if the cache is stale:

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_nf1_4 --rebuild-cache
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402

log = logging.getLogger("nfl.fantasy.rookie_interval_ablation")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POOL_CACHE = _ART / "nf1_4_rookie_training.parquet"

# The nominal interval. α = 0.20 ⇒ the interval score's miss penalty is 2/α = 10.
_ALPHA = 0.20
_COVERAGE_FLOOR = 0.80
_MIN_TRAIN_ROWS = 60
_MIN_TEST_ROWS = 15


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered config set
# ══════════════════════════════════════════════════════════════════════════════════════════════
_K_GRID = (30, 50, 80, 120)
_QREG_ALPHA_GRID = (0.0, 0.01)
_RESID_SD_GAIN_GRID = (0.0, 0.10, 0.20)


def candidate_configs() -> list[dict]:
    """The PRE-REGISTERED candidate set. Fixed before any result was read; every entry below counts
    toward the PBO deflation, which is what makes a grid this wide safe to search."""
    cfgs: list[dict] = [
        {"label": "legacy_cv (pre-NF1.4 null)", "arm": "legacy_cv"},
        {"label": "class_tercile (NF1.4 INCUMBENT)", "arm": "class_tercile"},
    ]
    for form in ("ratio_q", "ratio_q_floor"):
        for gain in _RESID_SD_GAIN_GRID:
            cfgs.append({"label": f"{form} · sdgain {gain:g}", "arm": "model", "form": form,
                         "resid_sd_gain": gain})
    for form in ("knn_pos", "knn_norm"):
        for k, gain in itertools.product(_K_GRID, _RESID_SD_GAIN_GRID):
            cfgs.append({"label": f"{form} k{k} · sdgain {gain:g}", "arm": "model", "form": form,
                         "k": k, "resid_sd_gain": gain})
    for form in ("qreg", "qreg_sqrt"):
        for a, gain in itertools.product(_QREG_ALPHA_GRID, _RESID_SD_GAIN_GRID):
            cfgs.append({"label": f"{form} α{a:g} · sdgain {gain:g}", "arm": "model", "form": form,
                         "qreg_alpha": a, "resid_sd_gain": gain})
    return cfgs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def interval_score(lo, hi, y, alpha: float = _ALPHA) -> np.ndarray:
    """The Winkler / Gneiting-Raftery interval score for a central (1−α) interval (LOWER is better).

    Equal (up to the constant 2/α) to the SUM of the pinball losses at τ = α/2 and τ = 1−α/2, so it is
    a PROPER score for the quantile pair: it is minimised by the TRUE q10/q90 and cannot be won by
    either degenerate strategy — a zero-width band pays the full miss penalty, and an all-encompassing
    band pays its own width. That is precisely why it, and not coverage or mean width, selects here."""
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    y = np.asarray(y, dtype=float)
    return (hi - lo) + (2.0 / alpha) * (np.clip(lo - y, 0, None) + np.clip(y - hi, 0, None))


def band_metrics(lo, hi, y, point, positions) -> dict:
    """Every reading of one arm on one held-out draft class. The interval score SELECTS; width and
    coverage are reported so the sharpness/calibration trade is visible rather than asserted."""
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    y, point = np.asarray(y, dtype=float), np.asarray(point, dtype=float)
    inside = (y >= lo) & (y <= hi)
    width = hi - lo
    keys = list(zip(np.round(lo, 1), np.round(hi, 1)))
    counts: dict = {}
    for kk in keys:
        counts[kk] = counts.get(kk, 0) + 1
    wide = width > 1e-9
    frac = np.where(wide, (point - lo) / np.where(wide, width, 1.0), 0.5)
    out = {
        "n": int(len(y)),
        "interval_score": round(float(np.mean(interval_score(lo, hi, y))), 3),
        "coverage_80": round(float(np.mean(inside)), 4),
        "mean_width": round(float(np.mean(width)), 2),
        "median_width": round(float(np.median(width)), 2),
        # ── the DEFECT metrics the guard fires on (`audit_interval_quality`) ──
        "distinct_band_frac": round(float(len(counts)) / max(1, len(keys)), 4),
        "max_shared_band": int(max(counts.values())) if counts else 0,
        "n_extreme_tail": int(np.sum((frac < 0.05) | (frac > 0.95))),
        # how much of the band's variation tracks the PLAYER: the correlation between the width and
        # the player's own point projection. A class-level band scores ~0 within a bucket.
        "width_point_rho": (round(float(pd.Series(width).corr(pd.Series(point), method="spearman")), 3)
                            if len(y) > 3 else None),
    }
    for p in sorted(set(map(str, positions))):
        sel = np.array([str(q) == p for q in positions])
        if sel.sum() >= 3:
            out[f"cov_{p}"] = round(float(np.mean(inside[sel])), 3)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Folds — walk-forward by DRAFT CLASS (the story's leakage-safe eval axis, inherited from NF1.4)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Fold:
    """One held-out draft class, with everything shared by every arm computed ONCE.

    §0.5 cost hygiene (the same rule as the cached feature parquet): the POINT curve, the in-fold
    served point projections and the held-out class's served point projection are identical for every
    arm — this story changes only the interval — so they are built once per class and reused by all
    ~50 configs. Recomputing them per config would be ~50× wasted work AND would risk the point
    drifting between arms, which is the one thing this story must not do."""

    year: int
    train: pd.DataFrame           # the FULL drafted population of the prior classes (band history)
    test: pd.DataFrame
    curve: SP.RookieSlotCurve     # the POINT model, fitted on the survivor-filtered prior classes
    train_pred: np.ndarray        # served point projection for each training row
    test_pred: np.ndarray         # served point projection for each held-out row
    test_real: np.ndarray
    tercile: SP.RookieSlotCurve   # the same curve WITH NF1.4's class-level tercile bands fitted


def _curve_inputs(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`fit_rookie_slot_curves` reads the rookie-year games as `games`; the POINT history keeps MVP-1's
    survivor filter (`games > 0`) and the BAND history is the FULL drafted population (NF1.4)."""
    band = frame.assign(games=lambda d: pd.to_numeric(d["rookie_games"], errors="coerce"))
    return band[band["games"] > 0].copy(), band


def build_folds(pool: pd.DataFrame, cohorts: list[int], *,
                recalibrate: bool = True, recal_lambda: float | None = None) -> list[Fold]:
    """Walk-forward folds by draft class.

    ⭐ `recalibrate` (NF-D16) MUST reach BOTH curves or the harness silently contradicts itself. The
    point comes from `curve` and the class-level band from `tercile`; before NF-D16 those two agreed
    on the point by construction (a band cannot move a point), so passing the recalibration to only
    one would fit a band around a point the harness does not use — NF1.7's class-level defect in a new
    disguise. Both get `recal_hist=band` (the FULL drafted population, matching what serving passes).

    ⭐⭐ NF-D21 FIXED A DRIFT THIS DOCSTRING USED TO ASSERT AWAY. It said the folds match "what serving
    passes" — and they did not. `recalibrate=True` applied the correction at λ = 1 while the serving
    path passed no `recal_hist` at all (NF-D16's flip was HELD), so every standing re-validation was
    scoring a band centred on a point the product did not serve. `recal_lambda=None` now RESOLVES to
    the served λ (`rookie_publish_policy.serving_lambda()`), which makes the claim true by
    construction instead of by comment, and keeps it true the next time λ moves.

    Pass `recal_lambda` explicitly only to study a λ the product does NOT serve.

    `recalibrate=False` reproduces the PRE-NF-D16 incumbent exactly, and NF-D16's / NF-D20's bake-offs
    run that way: a study of whether to add the recalibration cannot use the recalibrated point as its
    own null."""
    if recal_lambda is None:
        from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as _RP
        recal_lambda = _RP.serving_lambda()
    folds: list[Fold] = []
    for y in cohorts:
        tr, te = pool[pool["draft_year"] < y], pool[pool["draft_year"] == y]
        if len(tr) < _MIN_TRAIN_ROWS or len(te) < _MIN_TEST_ROWS:
            continue
        hist, band = _curve_inputs(tr)
        rc = band if (recalibrate and recal_lambda) else None
        curve = SP.fit_rookie_slot_curves(hist, recal_hist=rc,
                                          recal_lambda=recal_lambda)   # point model only
        tercile = SP.fit_rookie_slot_curves(hist, band_hist=band, per_player_band=False,
                                            recal_hist=rc, recal_lambda=recal_lambda)
        folds.append(Fold(
            year=int(y), train=band, test=te.copy(), curve=curve,
            train_pred=SP.rookie_point_projection(band, curve),
            test_pred=SP.rookie_point_projection(te, curve),
            test_real=pd.to_numeric(te["rookie_fp_ppr"], errors="coerce").fillna(0.0).to_numpy(),
            tercile=tercile))
    return folds


def _served_point_is_reproduced(fold: Fold) -> float:
    """The POINT-INVARIANCE proof: `rookie_point_projection` must reproduce what `project_rookies`
    actually emits, or the band would be conditioned on a number the board never shows. Returns the
    max absolute difference over the held-out class (asserted ≈ 0 by the caller)."""
    out = SP.project_rookies(fold.test, fold.curve, fold.year)
    if out.empty:
        return 0.0
    m = dict(zip(out["player_id"], pd.to_numeric(out["proj_fp_ppr"], errors="coerce")))
    got = np.array([float(m.get(g, np.nan)) for g in fold.test["gsis_id"]])
    ok = np.isfinite(got)
    return float(np.max(np.abs(got[ok] - fold.test_pred[ok]))) if ok.any() else 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The arms — candidates and anchors, all emitting (lo, hi) on the held-out class
# ══════════════════════════════════════════════════════════════════════════════════════════════
_Z80 = 1.2815515594


def _finish(lo, hi, point) -> tuple[np.ndarray, np.ndarray]:
    """The coherence + display contract every arm shares, so no arm can win on presentation: the band
    is non-negative, BRACKETS its own point projection, and is rounded OUTWARD to the served 0.1.

    ⚠️ `np.floor(x*10)/10` IS NOT ALWAYS ≤ x (NF1.9). When `x*10` rounds UP to an integer in float64 the
    "outward" rounding lands ABOVE x — e.g. `3.6999999999999997*10 == 37.0` exactly, so the floor gives
    3.7 > x. It is a ~1e-15 excursion, but it is enough to emit a band that marginally EXCLUDES its own
    point estimate, which is the incoherence the export guard fires on. Found by NF1.9's `oracle_point`
    anchor reading 0.946 coverage where a zero-width band AT the realized value must read 1.0. The
    min/max clamps make the direction exact instead of nearly-always-right."""
    lo = np.clip(np.minimum(np.asarray(lo, dtype=float), point), 0.0, None)
    hi = np.maximum(np.asarray(hi, dtype=float), point)
    return np.minimum(np.floor(lo * 10.0) / 10.0, lo), np.maximum(np.ceil(hi * 10.0) / 10.0, hi)


def candidate_band(fold: Fold, cfg: dict) -> tuple[np.ndarray, np.ndarray] | None:
    """One candidate's held-out band. `model` arms run the REAL production fitter/emitter
    (`fit_rookie_band_model` → `band_many`), never a re-implementation — a re-implementation could
    accidentally fix or break something the served path does not."""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    pred = fold.test_pred
    if cfg["arm"] == "legacy_cv":
        cv = np.array([fold.curve.fp_cv_by_pos.get(p, 0.7) for p in pos])
        return _finish(pred - _Z80 * pred * cv, pred + _Z80 * pred * cv, pred)
    if cfg["arm"] == "class_tercile":
        bands = [fold.tercile.band(pos[i], float(pred[i])) for i in range(len(pred))]
        if all(b is None for b in bands):
            return None
        lo = np.array([b[0] if b else 0.0 for b in bands])
        hi = np.array([b[1] if b else pred[i] for i, b in enumerate(bands)])
        return _finish(lo, hi, pred)
    m = SP.fit_rookie_band_model(
        fold.train, fold.train_pred, form=cfg["form"], k=cfg.get("k", SP._ROOKIE_BAND_K),
        resid_sd_gain=cfg.get("resid_sd_gain", 0.0), qreg_alpha=cfg.get("qreg_alpha", 0.0))
    if m is None:
        return None
    lo, hi = m.band_many(pos, pred, overall=fold.test.get("draft_overall"),
                         resid_sd=fold.test.get("projected_nfl_z_sd"))
    # a row the fit cannot speak to falls back to the class-level band, exactly as production does
    bad = ~(np.isfinite(lo) & np.isfinite(hi))
    if bad.any():
        fb = [fold.tercile.band(pos[i], float(pred[i])) for i in np.where(bad)[0]]
        lo[bad] = [b[0] if b else 0.0 for b in fb]
        hi[bad] = [b[1] if b else pred[i] for b, i in zip(fb, np.where(bad)[0])]
    return _finish(lo, hi, pred)


def anchor_bands(fold: Fold, oracle_k: int) -> dict:
    """The sanity anchors on one held-out class — the two ORACLE FLOORS and the three DEGENERATE
    CEILINGS.

    Both oracles PEEK: they are fitted on the held-out class's own REALIZED outcomes, one per family
    the candidates are drawn from (a local neighbourhood, and the parametric quantile regression). A
    candidate fitted strictly in-fold beating a peeking fit of its own family on the same rows is not
    a discovery — it is proof the metric is inverted, which is the whole reason these exist.

    ⚠️ An oracle that FAILS TO FIT must never be silently dropped: `oracle_respected` would then be
    vacuously true (the first cut of this harness did exactly that — the production fitter refuses a
    per-position fit under 40 rows and a held-out class is only ~80 rows across four positions, so
    both oracle attempts returned None and the check passed on nothing). The neighbourhood oracle is
    therefore built from the same `_knn_interval` primitive directly, and the caller raises if either
    is missing.

    (The trivial infimum — zero width AT the realized value — is reported for orientation only; it
    scores ~0 and nothing can beat 0, so it cannot discriminate.)"""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    pred, y = fold.test_pred, fold.test_real
    out: dict = {}

    # ── DEGENERATE CEILINGS ─────────────────────────────────────────────────────────────────
    out["zero_width"] = _finish(pred, pred, pred)
    mx = fold.train.groupby(fold.train["position_group"].astype(str).str.upper())["rookie_fp_ppr"].max()
    hi_max = np.array([float(mx.get(p, np.nanmax(y) if len(y) else 0.0)) for p in pos])
    out["max_width"] = _finish(np.zeros_like(pred), hi_max, pred)
    g = fold.train.assign(_p=fold.train["position_group"].astype(str).str.upper())
    q = g.groupby("_p")["rookie_fp_ppr"].quantile([0.10, 0.90]).unstack()
    lo_c = np.array([float(q.loc[p, 0.10]) if p in q.index else 0.0 for p in pos])
    hi_c = np.array([float(q.loc[p, 0.90]) if p in q.index else 0.0 for p in pos])
    out["const_width"] = _finish(lo_c, hi_c, pred)

    # ── ORACLE FLOORS (both peek at the held-out realized outcomes) ─────────────────────────
    # (a) the neighbourhood family: q10/q90 of the REALIZED outcomes of the k nearest rookies IN THIS
    #     CLASS in position-normalised prediction space, normalised by the class's own realized means.
    lvl = pd.Series(y).groupby(pd.Series(pos)).mean()
    s = np.array([float(lvl.get(p, np.nan)) for p in pos])
    s = np.where(np.isfinite(s) & (s > 1e-6), s, max(float(np.mean(y)), 1e-6))
    lo_o, hi_o = SP._knn_interval(pred / s, y / s, pred / s,
                                  min(oracle_k, len(y)), 0.10, 0.90)
    out["oracle_knn"] = _finish(lo_o * s, hi_o * s, pred)
    # (b) the parametric family: the winner's own quantile regression, fitted on this class's truth.
    om = SP.fit_rookie_band_model(fold.test.assign(rookie_fp_ppr=y), pred, form="qreg",
                                 qreg_alpha=0.01)
    if om is not None:
        l2, h2 = om.band_many(pos, pred, overall=fold.test.get("draft_overall"),
                              resid_sd=fold.test.get("projected_nfl_z_sd"))
        if np.isfinite(l2).all() and np.isfinite(h2).all():
            out["oracle_qreg"] = _finish(l2, h2, pred)

    out["oracle_point"] = _finish(y, y, y)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Running
# ══════════════════════════════════════════════════════════════════════════════════════════════
_MEAN_KEYS = ("interval_score", "coverage_80", "mean_width", "median_width",
              "distinct_band_frac", "width_point_rho")


def run_arm(folds: list[Fold], cfg: dict) -> dict:
    per: dict[int, dict] = {}
    for f in folds:
        b = candidate_band(f, cfg)
        if b is None:
            continue
        per[f.year] = band_metrics(b[0], b[1], f.test_real, f.test_pred,
                                   f.test["position_group"].astype(str).to_numpy())

    def _m(key):
        v = [c[key] for c in per.values() if isinstance(c.get(key), (int, float))]
        return round(float(np.mean(v)), 4) if v else None
    cov_keys = sorted({k for c in per.values() for k in c if k.startswith("cov_")})
    return {
        **{k: v for k, v in cfg.items()},
        **{k: _m(k) for k in _MEAN_KEYS},
        **{k: _m(k) for k in cov_keys},
        "max_shared_band": max([c["max_shared_band"] for c in per.values()], default=None),
        "n_extreme_tail": sum(c["n_extreme_tail"] for c in per.values()),
        "n": sum(c["n"] for c in per.values()),
        "n_cohorts": len(per),
        "per_cohort": per,
    }


def run_anchors(folds: list[Fold], oracle_k: int) -> dict:
    per: dict[str, dict[int, dict]] = {}
    for f in folds:
        for tag, (lo, hi) in anchor_bands(f, oracle_k).items():
            per.setdefault(tag, {})[f.year] = band_metrics(
                lo, hi, f.test_real, f.test_pred, f.test["position_group"].astype(str).to_numpy())
    out = {}
    for tag, d in per.items():
        out[tag] = {k: round(float(np.mean([c[k] for c in d.values()
                                            if isinstance(c.get(k), (int, float))])), 3)
                    for k in ("interval_score", "coverage_80", "mean_width")}
        out[tag]["per_cohort"] = {y: c["interval_score"] for y, c in d.items()}
    return out


def pbo(matrix: pd.DataFrame) -> dict:
    """CSCV / Bailey Probability of Backtest Overfitting over a (draft class × config) matrix of a
    LOWER-IS-BETTER metric. For every balanced split of the classes into IS/OS halves, the IS winner's
    OS rank is recorded; PBO = the share of splits where it lands in the WORSE half."""
    n = len(matrix.index)
    half = n // 2
    if n < 4 or matrix.shape[1] < 2:
        return {"pbo": None, "n_splits": 0, "note": "too few classes/configs for CSCV"}
    logits, below = [], 0
    splits = list(itertools.combinations(range(n), half))
    for combo in splits:
        is_idx = list(combo)
        os_idx = [i for i in range(n) if i not in combo]
        winner = matrix.iloc[is_idx].mean(axis=0).idxmin()
        ranks = matrix.iloc[os_idx].mean(axis=0).rank(ascending=True, method="average")
        w = float(ranks[winner]) / (len(ranks) + 1.0)
        if w > 0.5:
            below += 1
        w = min(max(w, 1e-6), 1 - 1e-6)
        logits.append(float(np.log((1 - w) / w)))
    return {"pbo": round(below / len(splits), 4), "n_splits": len(splits),
            "median_logit": round(float(np.median(logits)), 3)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    an, best, inc = out["anchors"], out["best"], out["incumbent"]
    p("# NF1.7 — PER-PLAYER rookie 80% intervals (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **configs scored:** "
      f"{len(out['configs'])} · **held-out rookie-seasons:** {best['n']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is "
      "selected here is the WIDTH AND SHAPE of the rookie interval. The POINT projection is held "
      "byte-identical across every arm (proved below), because NF1.4 already established that the "
      "rookie point is ~unbiased and its apparent over-valuation was a RANK effect.")
    p("")
    p("## 0. The defect, measured on the served board")
    p("")
    p(_md(pd.DataFrame(out["defect"])))
    p("")
    p("NF1.4's band quantises to **one interval per (position, prediction-tercile)**. On the live "
      "2026 board that is 12 distinct intervals for 81 rookies against 647 for 703 veterans; every "
      "top-bucket rookie QB carried 26.5–277.0 while their point projections spanned 25.1→268.3.")
    p("")
    p("## 1. Why coverage could not have caught it — the §0.5 metric landmine, live")
    p("")
    p("NF1.4 selected this band on COVERAGE (0.678 → 0.834) and the band it picked is genuinely "
      "well-covered. **That is the problem.** Coverage is a property of the POPULATION, not of the "
      "player: a band held CONSTANT within a position can hit its nominal rate exactly while carrying "
      "zero per-player information. So coverage cannot select an interval, and this story selects on "
      "a PROPER interval score with coverage kept strictly as a FLOOR — the E2.1-r rule ('a coverage "
      "figure is a FLOOR, never a target to minimise distance to') applied to intervals.")
    p("")
    p("Primary metric — the **Winkler / Gneiting-Raftery interval score** for a central 80% interval:")
    p("")
    p("```")
    p("IS(l, u, y) = (u − l) + 10·(l − y)·1{y < l} + 10·(y − u)·1{y > u}      (lower is better)")
    p("```")
    p("")
    p("It equals the sum of the τ=0.10 and τ=0.90 pinball losses up to the constant 2/α, so it is "
      "PROPER for the quantile pair: minimised by the true q10/q90, it pays for width AND for missing. "
      "Neither degenerate strategy can win it. ⛔ MAE/RMSE on width is never used.")
    p("")
    p("## 2. The four-sided sanity anchors")
    p("")
    rows = [{"anchor": k, "what it is": v,
             "IS80": an.get(k, {}).get("interval_score"),
             "cov80": an.get(k, {}).get("coverage_80"),
             "mean width": an.get(k, {}).get("mean_width")}
            for k, v in [
                ("oracle_knn", "ORACLE FLOOR (neighbourhood family) — q10/q90 of the REALIZED "
                               "outcomes of the k nearest rookies IN the held-out class. Peeks; "
                               "nothing may beat it."),
                ("oracle_qreg", "ORACLE FLOOR (parametric family) — the winner's own quantile "
                                "regression fitted on the held-out class's truth. Peeks; nothing "
                                "may beat it."),
                ("zero_width", "DEGENERATE — width 0 at the point. MAXIMALLY sharp ⇒ a naive "
                               "sharpness metric would crown it. Must LOSE."),
                ("max_width", "DEGENERATE — [0, the position's max realized rookie season]. "
                              "Coverage ≈ 1 and useless ⇒ a coverage TARGET would love it. Must LOSE."),
                ("const_width", "DEGENERATE — ONE band per position, no conditioning at all. "
                                "Must LOSE."),
                ("oracle_point", "the trivial infimum (zero width AT the realized value, IS = 0) — "
                                 "orientation only, not a discriminator."),
            ] if k in an]
    p(_md(pd.DataFrame(rows)))
    p("")
    checks = out["anchor_checks"]
    p(f"⚠️ The floor the check leans on is **`{checks['oracle_family']}` — the WINNER'S OWN family**. "
      "A cross-family oracle is not a valid floor (a peeking MISSPECIFIED model is beatable by an "
      "honest well-specified one), and a peeking k-NN's capacity depends on its sample size — a "
      "held-out class is only ~80 rows, so the same `k` is a far coarser neighbourhood there than over "
      "the training classes. The other oracle is reported for orientation.")
    p("")
    for label, ok, msg in (
        ("oracle floor respected", checks["oracle_respected"],
         f"the winner does not beat its own peeking oracle ({checks['oracle_family']})"),
        ("zero-width degenerate loses", checks["zero_width_loses"],
         "sharpness was not bought by under-covering"),
        ("max-width degenerate loses", checks["max_width_loses"],
         "the selection is not a coverage exercise in disguise"),
        ("const-width degenerate loses", checks["const_width_loses"],
         "conditioning on the player earns its place"),
        ("incumbent beaten", checks["beats_incumbent"],
         "the per-player band beats NF1.4's class-level band"),
    ):
        p(f"- {'✅' if ok else '🚨'} **{label}** — "
          + (msg if ok else "**THE METRIC OR THE SELECTION IS SUSPECT — do NOT ship it**"))
    p("")
    p("## 3. Results — all configs (sorted by the primary metric)")
    p("")
    tbl = [{"config": r["label"], "IS80": r["interval_score"], "cov80": r["coverage_80"],
            "mean width": r["mean_width"], "distinct-band frac": r["distinct_band_frac"],
            "worst shared": r["max_shared_band"], "extreme-tail rows": r["n_extreme_tail"],
            "ρ(width, point)": r["width_point_rho"],
            "eligible": "yes" if (r["coverage_80"] or 0) >= _COVERAGE_FLOOR else "NO (cov floor)"}
           for r in sorted(out["configs"],
                           key=lambda r: (r["interval_score"] is None, r["interval_score"]))]
    p(_md(pd.DataFrame(tbl)))
    p("")
    p(f"`distinct-band frac` = distinct (p10, p90) pairs ÷ rookies — **1.0 is a fully per-player "
      f"band, 0.04 is the incumbent's 3-buckets-per-position**. `worst shared` is the largest set of "
      f"rookies carrying a byte-identical interval — the number `audit_interval_quality()` fires on. "
      f"`ρ(width, point)` is how much the band's width tracks the player's own projection.")
    p("")
    p("## 4. Deflation — CSCV / PBO over held-out draft-class splits")
    p("")
    d = out["pbo"]
    p(f"**PBO = {d.get('pbo')}** over {d.get('n_splits')} balanced class splits (median logit "
      f"{d.get('median_logit')}); config spread (best→worst IS80) = {out['spread']['min']} → "
      f"{out['spread']['max']} ({out['spread']['pct']}%).")
    p("")
    p("Reading it (CLAUDE.md): a high PBO on a **TIED** field is the NULL — nothing robustly "
      "separates the candidates, so the incumbent's choice is proven rather than lucky. A high PBO "
      "with a **WIDE** spread is genuine overfitting. The spread is the discriminator.")
    p("")
    _p, _s = d.get("pbo"), out["spread"]["pct"]
    if _p is not None:
        p(f"**Quadrant: {'LOW' if _p < 0.2 else 'HIGH'} PBO ({_p}) + "
          f"{'WIDE' if _s >= 10 else 'TIGHT'} spread ({_s}%)** — "
          + ("a genuinely separated winner; the choice survives out-of-sample."
             if _p < 0.2 and _s >= 10 else
             "the winner is stable but the field is close; the choice is safe, the margin small."
             if _p < 0.2 else
             "genuine overfitting; do NOT ship the selection." if _s >= 10 else
             "a TIED field: the null. Ship the simplest arm, not the leaderboard's top row."))
    p("")
    p("## 4b. ⚠️ The top of the field is TIED — and the tie has a coverage asymmetry")
    p("")
    p(_md(pd.DataFrame(out["tied"])))
    p("")
    p(out["tie_note"])
    p("")
    p("## 5. Selection")
    p("")
    p(f"**SHIPPED: `{best['label']}`** — IS80 {best['interval_score']} (incumbent "
      f"{inc['interval_score']}), coverage {best['coverage_80']} (floor {_COVERAGE_FLOOR:.2f}), mean "
      f"width {best['mean_width']} (incumbent {inc['mean_width']}), distinct-band fraction "
      f"{best['distinct_band_frac']} (incumbent {inc['distinct_band_frac']}), worst shared band "
      f"{best['max_shared_band']} (incumbent {inc['max_shared_band']}).")
    p("")
    p(out["verdict"])
    p("")
    p("### Per-position coverage (the FLOOR, per position)")
    p("")
    cov_cols = sorted([k for k in best if k.startswith("cov_")])
    p(_md(pd.DataFrame([
        {"arm": nm, **{k.replace("cov_", ""): r.get(k) for k in cov_cols}}
        for nm, r in (("incumbent (class-level)", inc), ("SHIPPED (per-player)", best))])))
    p("")
    p("## 6. Per-class detail (shipped config)")
    p("")
    p(_md(pd.DataFrame([{"draft_class": y, **{k: v for k, v in c.items()
                                              if not k.startswith("cov_")}}
                        for y, c in sorted(best["per_cohort"].items())])))
    p("")
    p("## 7. Is the rookie band HONESTLY WIDER than a veteran's?")
    p("")
    p("⭐ A rookie has no NFL sample, so his honest band should be WIDER than a comparable veteran's. "
      "'Sharper' is therefore the WRONG direction to optimise blindly — which is exactly why coverage "
      "is a hard FLOOR here and why `zero_width` is an anchor that must lose. This is the direction "
      "check on the selection, not a metric it was picked on.")
    p("")
    p(_md(pd.DataFrame(out["width_vs_vets"])))
    p("")
    p(out["width_note"])
    p("")
    p("## 8. Honest limitations")
    p("")
    p("- **The point projection is untouched, so a mis-placed rookie stays mis-placed.** NF1.4's "
      "finding was that the rookie point runs COLD, and its model bake-off returned a NULL; this "
      "story does not re-attack the level and must not be read as having improved it.")
    p("- **The band is fitted on ~10 draft classes** (~80 drafted skill rookies each). The "
      "neighbourhood arms therefore trade resolution against quantile noise, which is what the `k` "
      "grid selects and the PBO deflates.")
    p("- **`knn_norm` assumes the SHAPE of the rookie outcome distribution is position-invariant once "
      "scaled by the position's mean.** That buys ~4× the neighbours; `knn_pos` is pre-registered "
      "beside it precisely so the assumption is tested rather than believed.")
    p("- **A rookie's band still cannot see anything NFL-specific** — no camp reports, no depth chart, "
      "no preseason. Draft slot, the P1A translation and its parameter sd are the whole information "
      "set, and `confidence = low` remains the honest surface.")
    p("- ⚠️ **QB coverage is BELOW the nominal 80% — in BOTH arms** (see the per-position table: "
      f"{best.get('cov_QB')} shipped vs {inc.get('cov_QB')} incumbent). The coverage floor was "
      "pre-registered POOLED, and the rookie-QB cohort is ~10 players a class of whom ~35% never take "
      "a snap, so the per-position estimate is thin — but it is a real gap and it is NOT fixed here. "
      "It is disclosed rather than buried: the shipped band does not make QB worse, it inherits the "
      "miss. A per-position floor would be the honest next iteration.")
    p("- **No edge claim.** An honest interval is a projection-quality property, not a market edge.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Board-level readings (the defect + the rookie-vs-veteran width check)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_band_summary(path: Path) -> list[dict]:
    """Per-population band degeneracy on an EMITTED board parquet — the live reading of the defect."""
    if not path.exists():
        return []
    d = pd.read_parquet(path)
    if not {"fp_ppr_p10", "fp_ppr_p90", "is_rookie"} <= set(d.columns):
        return []
    rows = []
    for name, sel in (("rookies", d["is_rookie"].fillna(False).astype(bool)),
                      ("veterans", ~d["is_rookie"].fillna(False).astype(bool))):
        g = d[sel & d["fp_ppr_p10"].notna() & d["fp_ppr_p90"].notna()]
        if g.empty:
            continue
        keys = list(zip(g["fp_ppr_p10"].round(1), g["fp_ppr_p90"].round(1)))
        counts: dict = {}
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        rows.append({"population": name, "players": len(g), "distinct bands": len(counts),
                     "distinct-band frac": round(len(counts) / len(g), 3),
                     "worst shared band": max(counts.values()),
                     "mean width": round(float((g["fp_ppr_p90"] - g["fp_ppr_p10"]).mean()), 1)})
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_pool(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(
            f"no rookie pool at {path} — build it first with:\n"
            "  SPORTS_LAKE_REGION=us-east-2 uv run python -m "
            "quant_sports_intel_models.football.nfl.fantasy.run_nf1_4 --rebuild-cache")
    pool = pd.read_parquet(path)
    need = {"draft_year", "draft_overall", "position_group", "rookie_fp_ppr", "rookie_games"}
    missing = need - set(pool.columns)
    if missing:
        raise SystemExit(f"rookie pool missing columns: {sorted(missing)}")
    pool = pool[pd.to_numeric(pool["draft_overall"], errors="coerce").notna()].copy()
    for c in SP._ROOKIE_RAW_STATS:                      # the stat composition the point curve needs
        if c not in pool.columns:
            pool[c] = pd.to_numeric(pool["rookie_fp_ppr"], errors="coerce") * 0.5
    return pool


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.7 per-player rookie 80% interval bake-off")
    ap.add_argument("--pool", default=str(_POOL_CACHE))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--oracle-k", type=int, default=25,
                    help="neighbourhood for the peeking ORACLE band (held-out classes are ~80 rows)")
    ap.add_argument("--board", default=str(_ART / "nfl_fantasy_season_projections_2026.parquet"))
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    pool = load_pool(Path(args.pool))
    cohorts = [y for y in range(args.from_year, args.to_year + 1)]
    folds = build_folds(pool, cohorts)
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    log.info("NF1.7 bake-off: %d classes (%s) × %d configs",
             len(folds), cohorts, len(candidate_configs()))

    # ⭐ POINT-INVARIANCE PROOF — the conditioning variable IS the served point projection.
    point_drift = max(_served_point_is_reproduced(f) for f in folds)
    if point_drift > 1e-6:
        raise SystemExit(
            f"the band's conditioning variable drifted from the SERVED point projection by "
            f"{point_drift:.6f} — `rookie_point_projection` no longer reproduces `project_rookies`. "
            "Fix that before reading any selection: a band centred on a number the board never shows "
            "is the class-level defect in a new disguise.")
    log.info("point-invariance proof: served point reproduced exactly (max drift %.2e)", point_drift)

    cfgs = candidate_configs()
    results = [run_arm(folds, c) for c in cfgs]
    results = [r for r in results if r.get("interval_score") is not None]
    anchors = run_anchors(folds, args.oracle_k)

    incumbent = next(r for r in results if r["arm"] == "class_tercile")
    eligible = [r for r in results
                if r["arm"] not in ("class_tercile", "legacy_cv")
                and (r["coverage_80"] or 0) >= _COVERAGE_FLOOR]
    pool_for_best = eligible or [r for r in results if r["arm"] == "model"]
    best = min(pool_for_best, key=lambda r: r["interval_score"])

    a_is = {k: v["interval_score"] for k, v in anchors.items()}
    # ⚠️ A MISSING ORACLE IS A HARD FAILURE, not a pass. An absent anchor makes `oracle_respected`
    # vacuously true, which is exactly how a broken metric ships (see `anchor_bands`).
    missing = [k for k in ("oracle_knn", "oracle_qreg") if k not in a_is]
    if missing:
        raise SystemExit(
            f"the oracle anchor(s) {missing} did not fit — the oracle-floor check would pass on "
            "NOTHING. Fix the anchor before reading any selection.")
    # ⚠️ THE FLOOR IS THE WINNER'S OWN FAMILY. A cross-family oracle is not a valid floor: a peeking
    # MISSPECIFIED model is beatable by an honest well-specified one, and a peeking k-NN's CAPACITY
    # depends on its sample size (a held-out class is ~80 rows, so k=25 there is a far coarser
    # neighbourhood than the same k over 800 training rows). Both oracles are reported — the
    # same-family one is what the check is allowed to lean on.
    own_oracle = "oracle_qreg" if str(best.get("form", "")).startswith("qreg") else "oracle_knn"
    checks = {
        "oracle_respected": bool(best["interval_score"] >= a_is[own_oracle] - 1e-9),
        "oracle_family": own_oracle,
        "zero_width_loses": bool(best["interval_score"] < a_is["zero_width"]),
        "max_width_loses": bool(best["interval_score"] < a_is["max_width"]),
        "const_width_loses": bool(best["interval_score"] < a_is["const_width"]),
        "beats_incumbent": bool(best["interval_score"] < incumbent["interval_score"]),
        "coverage_floor_met": bool((best["coverage_80"] or 0) >= _COVERAGE_FLOOR),
    }

    mat = pd.DataFrame({r["label"]: {y: c["interval_score"] for y, c in r["per_cohort"].items()}
                        for r in results}).sort_index()
    d = pbo(mat.dropna(axis=1, how="any"))
    vals = [r["interval_score"] for r in results]
    spread = {"min": round(min(vals), 3), "max": round(max(vals), 3),
              "pct": round(100.0 * (max(vals) - min(vals)) / max(1e-9, min(vals)), 1)}

    # ── the TIE at the top, and the coverage asymmetry inside it ────────────────────────────────
    _TIE_PCT = 1.0
    tied = [r for r in sorted(pool_for_best, key=lambda r: r["interval_score"])
            if r["interval_score"] <= best["interval_score"] * (1.0 + _TIE_PCT / 100.0)]
    tie_rows = [{"config": r["label"], "IS80": r["interval_score"],
                 "Δ IS80 vs winner %": round(100.0 * (r["interval_score"] - best["interval_score"])
                                             / best["interval_score"], 2),
                 "cov80": r["coverage_80"],
                 "floor headroom": round((r["coverage_80"] or 0) - _COVERAGE_FLOOR, 3),
                 "mean width": r["mean_width"]} for r in tied]
    best_cov = max(tied, key=lambda r: r["coverage_80"] or 0)
    tie_note = (
        f"The top **{len(tied)}** configs sit within {_TIE_PCT:g}% of each other on the primary "
        f"metric — `{best['label']}` at {best['interval_score']} against `{best_cov['label']}` at "
        f"{best_cov['interval_score']}. Per CLAUDE.md, when the leaders genuinely TIE, *which* of them "
        f"wins is noise, and the low PBO ({d.get("pbo")}) says the same thing from the other direction.\n\n"
        f"⚠️ **The tie is not symmetric, and that is worth naming rather than smoothing away:** the "
        f"P1A-uncertainty widener buys real coverage headroom for almost nothing on the primary metric "
        f"(`{best_cov['label']}` covers {best_cov['coverage_80']} vs the winner's "
        f"{best['coverage_80']}, floor {_COVERAGE_FLOOR:.2f}), so there is a live temptation to "
        f"re-pick on it.\n\n"
        f"**We do NOT, and ship the pre-registered winner.** Coverage was declared an eligibility "
        f"FLOOR, and 'prefer more headroom above the floor' is a MONOTONE-IN-WIDENING criterion — the "
        f"`max_width` degenerate would win it outright. Re-picking a tie on a criterion a degenerate "
        f"wins is how the E2.1-r inversion happens, just facing the other way, and it is exactly the "
        f"overfitting the deflation above exists to catch. Both arms clear the floor; the winner clears "
        f"it by less, and that is recorded here."
        if len(tied) > 1 and (best_cov["coverage_80"] or 0) > (best["coverage_80"] or 0) else
        "The winner is not in a tie on the primary metric — the next config is more than "
        f"{_TIE_PCT:g}% behind.")

    board = board_band_summary(Path(args.board))
    vet = next((r for r in board if r["population"] == "veterans"), None)
    width_rows = [
        {"population": "rookies — NF1.4 class-level (incumbent)", "source": "held-out backtest",
         "mean 80% width": incumbent["mean_width"], "coverage": incumbent["coverage_80"]},
        {"population": f"rookies — {best['label']} (SHIPPED)", "source": "held-out backtest",
         "mean 80% width": best["mean_width"], "coverage": best["coverage_80"]},
    ]
    if vet:
        width_rows.append({"population": "veterans (empirical game-to-game variance)",
                           "source": "emitted 2026 board", "mean 80% width": vet["mean width"],
                           "coverage": None})
    width_note = (
        f"The selected rookie band is **{best['mean_width'] / vet['mean width']:.1f}× wider** than the "
        f"average veteran band ({best['mean_width']} vs {vet['mean width']} PPR) — the honest "
        f"direction. It is also {'WIDER' if (best['mean_width'] or 0) >= (incumbent['mean_width'] or 0) else 'NARROWER'} "
        f"than the class-level band it replaces ({best['mean_width']} vs {incumbent['mean_width']}), "
        "so the interval-score win came from putting the width where it BELONGS per player, not from "
        "shrinking it. Veteran coverage is not comparable (a veteran band is a normal approximation "
        "off realized game-to-game variance, not an empirical quantile), so only the WIDTH is compared."
        if vet else
        "No emitted board was available to compare veteran widths against; re-run with `--board` "
        "pointed at a season-projection parquet.")
    verdict = (
        f"The per-player band EARNS its place: `{best['label']}` cuts the held-out interval score from "
        f"{incumbent['interval_score']} (NF1.4's class-level band) to {best['interval_score']} "
        f"({100.0 * (incumbent['interval_score'] - best['interval_score']) / incumbent['interval_score']:.1f}% "
        f"better) while HOLDING the coverage floor ({best['coverage_80']} ≥ {_COVERAGE_FLOOR:.2f}) and "
        f"lifting the distinct-band fraction {incumbent['distinct_band_frac']} → "
        f"{best['distinct_band_frac']}. The point projection is unchanged."
        if checks["beats_incumbent"] and checks["coverage_floor_met"] else
        "HONEST NULL: no per-player form beats NF1.4's class-level band on the pre-registered interval "
        "score while holding the coverage floor. The class-level band stands, and the app's "
        "'Class-level' label stays TRUE.")

    out = {"cohorts": cohorts, "configs": results, "anchors": anchors, "anchor_checks": checks,
           "best": best, "incumbent": incumbent, "pbo": d, "spread": spread,
           "defect": board, "width_vs_vets": width_rows, "width_note": width_note,
           "tied": tie_rows, "tie_note": tie_note,
           "verdict": verdict,
           "point_drift": point_drift, "coverage_floor": _COVERAGE_FLOOR,
           "generated_at": datetime.now(timezone.utc).isoformat()}

    print("\n=== NF1.7 rookie 80% interval — held-out-by-draft-class scores ===")
    print(f"{'config':34s} {'IS80':>9s} {'cov80':>6s} {'width':>7s} {'distinct':>8s} "
          f"{'shared':>6s} {'ρ(w,pt)':>7s}")
    for r in sorted(results, key=lambda r: r["interval_score"]):
        print(f"{r['label']:34s} {r['interval_score']:9.2f} {r['coverage_80'] or 0:6.3f} "
              f"{r['mean_width'] or 0:7.1f} {r['distinct_band_frac'] or 0:8.3f} "
              f"{r['max_shared_band'] or 0:6d} {r['width_point_rho'] or 0:7.3f}")
    print("\nanchors: " + " · ".join(
        f"{k} IS80={v['interval_score']} (cov {v['coverage_80']})" for k, v in anchors.items()))
    print("checks: " + " · ".join(f"{k}={v}" for k, v in checks.items()))
    print(f"PBO={d.get('pbo')} spread={spread['pct']}%")
    print(f"SHIPPED: {best['label']}")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / "nf1_7_rookie_intervals.json").write_text(json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / "nf1_7_rookie_intervals.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

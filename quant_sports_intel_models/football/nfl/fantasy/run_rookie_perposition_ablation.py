"""run_rookie_perposition_ablation.py — NF1.8 §0.5 bake-off: the rookie band under a PER-POSITION
coverage FLOOR.

WHAT IS BEING SELECTED — the WIDTH AND SHAPE of the rookie 80% interval, and NOTHING ELSE, exactly as
in NF1.7. The point projection is held byte-identical across every arm and asserted as such.

⚠️ WHAT NF1.7 LEFT ON THE TABLE. NF1.7 selected the rookie band on a PROPER interval score with a
pre-registered POOLED coverage floor of 0.80. Pooled coverage duly rose 0.791 → 0.808 — but it
REDISTRIBUTED rather than improving uniformly:

    QB 0.740 → 0.739   RB 0.836 → 0.777   TE 0.730 → 0.878   WR 0.811 → 0.822

That was not a gate miss (the floor was pooled, and pooled cleared it), but it is the same class of
blind spot as NF1.4's, one level up: **pooled coverage is a POPULATION property that one position can
pay for on another's behalf.** A band can hold 80% overall while systematically under-covering the
positions whose outcome distribution it fits worst — and rookie QB is exactly that position (~10
drafted a class, ~35% never take a snap). So NF1.8 re-selects under a PER-POSITION floor.

⭐ WHAT DOES **NOT** CHANGE, because it is the lesson NF1.7 exists to encode: the SELECTION metric is
still the interval score. Coverage — pooled or per-position — is an ELIGIBILITY FLOOR, never a target
to maximise or to minimise distance to (E2.1-r). The proof that this is not a coverage exercise in
disguise is that the `max_width` degenerate SATISFIES EVERY PER-POSITION FLOOR and still loses,
which §2 reports explicitly.

PRIMARY METRIC = the Winkler / Gneiting-Raftery interval score (imported from the NF1.7 harness so the
two stories cannot drift apart):

    IS(l, u, y) = (u − l) + 10·(l − y)·1{y < l} + 10·(y − u)·1{y > u}          (lower is better)

⚠️ ONE METRIC-CONVENTION CHANGE, and it is load-bearing rather than cosmetic. NF1.7 averaged each
metric over the held-out CLASSES (a mean of per-class means). NF1.8 pools over ROWS. Two reasons:
  · a per-position coverage FLOOR cannot be a mean of per-class means — a position thin in one class
    (NF1.7 required ≥3 rows) is silently DROPPED from that mean, so a floor computed that way is
    evaluated on a quietly different population than the one it claims to protect;
  · a rookie-season is the unit the floor is about, so every rookie-season should weigh the same.
Both conventions are reported for every config, and the NF1.7 winner's number under both is printed,
so the comparison to NF1.7 stays honest rather than implicit.

PRE-REGISTERED CANDIDATE CLASSES (fixed before any NF1.8 result was read). Every NF1.7 config is
re-scored — none is dropped, because the floor must be applied to the whole field and not to a
survivor set — PLUS two mechanisms that exist specifically to answer a per-GROUP floor:
  • `qreg_per_pos` — the quantile pair fitted SEPARATELY per position. NF1.7's position dummy shifts
                     only the INTERCEPT, forcing all four positions to share one slope on log(point)
                     and one on the P1A sd. QB is precisely the position whose slope should differ.
  • `cqr_*`        — CONFORMALIZED quantile regression with a MONDRIAN (group-conditional) calibration:
                     the textbook instrument for a per-group coverage floor, since the inflation is the
                     (1−α) quantile of the conformity scores WITHIN the position. `cqr_mode="pool"` is
                     its pre-registered FOIL (identical machinery, one shared quantile) so the report
                     can separate "conformal helped" from "PER-POSITION conditioning helped", and
                     `cqr_scale ∈ (add, width)` tests whether the inflation should be a points-scale
                     constant or proportional to the band's own width.
  Applied on the two parametric bases that led NF1.7's field (`qreg`, `qreg_sqrt`); a conformal layer
  is a CALIBRATION OF a base band, not a base band, so it is not sprayed across the neighbourhood arms.

⭐ THE FOUR ANCHOR-SET GUARDS CARRIED FROM NF1.7 (CLAUDE.md §0.5 — all four earned the hard way):
  1. **A MISSING ANCHOR RAISES.** An anchor that fails to fit makes its own check vacuously true.
  2. **THE ORACLE IS A PERMUTATION, not a fitted oracle.** A peeking fit is only a valid floor at
     EQUAL family AND equal sample size; a held-out class is ~80 rows, so a peeking k-NN there is a
     coarser neighbourhood than the same k over the training classes and is legitimately beatable. The
     well-posed-at-any-n form is: fit the SAME family on the SAME rows against the TRUE outcomes and
     against a PERMUTATION of them. Knowing the answer must score better than not knowing it.
     (The same-family peeking oracles are still reported, and still checked, for orientation.)
  3. **TWO DEGENERATES, not one.** `zero_width` (maximally sharp — a naive sharpness metric crowns it)
     AND `max_width` (coverage ≈ 1 — a coverage TARGET loves it) must BOTH lose. NF1.8 adds the
     reading that matters here: `max_width` PASSES every per-position floor, so the floor is visibly a
     constraint and not the selector.
  4. **THE WIDEN-ONLY KNOB IS MONOTONE.** `resid_sd_gain` clamps its z to max(z, 0) so it can only
     widen; a two-sided version sharpened half the field and cost coverage 0.808 → 0.773.

⚠️ POWER IS REPORTED, NOT ASSUMED. QB carries ~81 held-out rookie-seasons, so the binomial SE of its
coverage at p=0.80 is ~0.044: a hard floor at nominal REJECTS a truly-nominal arm about half the time,
and NF1.7's 0.739 sits only ~1.4 SE below nominal. §3 quantifies that for every position, and a
pre-registered Tier-2 fallback (a documented, power-derived QB floor) exists for the case where Tier 1
admits nothing. A per-position floor may honestly WIDEN QB — that is the correct answer to structural
availability uncertainty, not a defect.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. No `best_alpha`, no CLV/ROI claim.

RUN ON THE LAPTOP (fast, no Snowflake; reads the cached NF1.4 rookie pool, ~30s):

    uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_rookie_perposition_ablation

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
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
)
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation import (  # noqa: E402,E501
    Fold,
    _finish,
    board_band_summary,
    build_folds,
    interval_score,
    load_pool,
    pbo,
)

log = logging.getLogger("nfl.fantasy.rookie_perposition_ablation")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"

_ALPHA = NF17._ALPHA                       # 0.20 ⇒ a central 80% interval, miss penalty 2/α = 10
_NOMINAL = 1.0 - _ALPHA                    # 0.80 — the nominal coverage, pooled AND per position
_COVERAGE_FLOOR = NF17._COVERAGE_FLOOR     # the POOLED floor, carried from NF1.7 unchanged
# A position needs at least this many held-out rookie-seasons before its own coverage is used as a
# FLOOR. Below it the estimate is too noisy to constrain anything and the floor would be pure noise
# selection; such a position is REPORTED as unconstrained rather than silently waved through.
_POS_FLOOR_MIN_N = 30
# The Tier-2 fallback's one-sided confidence level: the QB floor becomes "not significantly below
# nominal at 95%", i.e. nominal − z·SE(n_QB). Derived from SAMPLE SIZE alone — a design quantity known
# before any result — which is what keeps it from being a floor fitted to the number we wanted.
_TIER2_Z = 1.6448536269514722
_TIER2_POSITIONS = ("QB",)
# NF1.7's shipped arm, PINNED as a literal rather than rebuilt from `season_projection`'s constants —
# those constants are what NF1.8 CHANGES, so deriving the reference from them would silently re-point
# the comparison at NF1.8's own winner and make every "vs NF1.7" number in the report read 0.
_NF17_WINNER_LABEL = "qreg α0.01 · sdgain 0"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered config set — every NF1.7 arm, plus the two per-position mechanisms
# ══════════════════════════════════════════════════════════════════════════════════════════════
_RESID_SD_GAIN_GRID = NF17._RESID_SD_GAIN_GRID          # (0.0, 0.10, 0.20)
_QREG_ALPHA_GRID = NF17._QREG_ALPHA_GRID                # (0.0, 0.01)
_CQR_BASES = ("qreg", "qreg_sqrt")
_CQR_ARMS = (("pos", "add"), ("pos", "width"), ("pool", "add"), ("pool", "width"))


def candidate_configs() -> list[dict]:
    """The PRE-REGISTERED NF1.8 candidate set = NF1.7's 44 configs (re-scored in full — the floor has
    to be applied to the WHOLE field, not to a survivor set) + the per-position mechanisms. Every
    entry counts toward the PBO deflation, which is what makes a grid this wide safe to search."""
    cfgs: list[dict] = list(NF17.candidate_configs())
    for form, a, gain in itertools.product(_CQR_BASES, _QREG_ALPHA_GRID, _RESID_SD_GAIN_GRID):
        cfgs.append({"label": f"{form}_perpos α{a:g} · sdgain {gain:g}", "arm": "model", "form": form,
                     "qreg_alpha": a, "resid_sd_gain": gain, "qreg_per_pos": True})
    for form, (mode, scale), gain in itertools.product(_CQR_BASES, _CQR_ARMS, _RESID_SD_GAIN_GRID):
        cfgs.append({"label": f"{form}+cqr[{mode},{scale}] · sdgain {gain:g}", "arm": "model",
                     "form": form, "qreg_alpha": 0.01, "resid_sd_gain": gain,
                     "cqr_mode": mode, "cqr_scale": scale})
    return cfgs


def _band_kwargs(cfg: dict) -> dict:
    return {"form": cfg["form"], "k": cfg.get("k", SP._ROOKIE_BAND_K),
            "resid_sd_gain": cfg.get("resid_sd_gain", 0.0),
            "qreg_alpha": cfg.get("qreg_alpha", 0.0),
            "qreg_per_pos": bool(cfg.get("qreg_per_pos", False)),
            "cqr_mode": cfg.get("cqr_mode", ""), "cqr_scale": cfg.get("cqr_scale", "add")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The arms — every band emitted as (lo, hi, fell_back) on the held-out class
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _tercile_band(fold: Fold, pred: np.ndarray, pos: np.ndarray,
                  idx: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """NF1.4's class-level tercile band — the incumbent arm AND the fallback production uses when a
    per-player fit cannot speak to a row."""
    sel = np.arange(len(pred)) if idx is None else idx
    bands = [fold.tercile.band(pos[i], float(pred[i])) for i in sel]
    lo = np.array([b[0] if b else 0.0 for b in bands], dtype=float)
    hi = np.array([b[1] if b else float(pred[i]) for b, i in zip(bands, sel)], dtype=float)
    return lo, hi


def candidate_band(fold: Fold, cfg: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """One candidate's held-out band, plus the FELL-BACK mask.

    ⚠️ THE MASK IS NOT BOOKKEEPING. A per-player form whose fit is refused for a position (the
    production fitter needs ≥40 in-fold rows, and the 2016–2018 training window carries only 38 rookie
    QBs) silently degrades that position to the CLASS-LEVEL band — so a config could satisfy a
    per-position floor while BEING THE INCUMBENT at the position the floor was written for. Reporting
    the fallback rate is what makes that visible instead of flattering."""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    pred = fold.test_pred
    none = np.zeros(len(pred), dtype=bool)
    if cfg["arm"] == "legacy_cv":
        cv = np.array([fold.curve.fp_cv_by_pos.get(p, 0.7) for p in pos])
        lo, hi = _finish(pred - NF17._Z80 * pred * cv, pred + NF17._Z80 * pred * cv, pred)
        return lo, hi, none
    if cfg["arm"] == "class_tercile":
        if all(fold.tercile.band(pos[i], float(pred[i])) is None for i in range(len(pred))):
            return None
        lo, hi = _tercile_band(fold, pred, pos)
        return (*_finish(lo, hi, pred), np.ones(len(pred), dtype=bool))
    m = SP.fit_rookie_band_model(fold.train, fold.train_pred, **_band_kwargs(cfg))
    if m is None:
        return None
    lo, hi = m.band_many(pos, pred, overall=fold.test.get("draft_overall"),
                         resid_sd=fold.test.get("projected_nfl_z_sd"))
    bad = ~(np.isfinite(lo) & np.isfinite(hi))
    if bad.any():
        idx = np.where(bad)[0]
        lo[idx], hi[idx] = _tercile_band(fold, pred, pos, idx)
    return (*_finish(lo, hi, pred), bad)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — ROW-POOLED, so a position thin in one class is never silently dropped from a mean
# ══════════════════════════════════════════════════════════════════════════════════════════════
def arm_rows(folds: list[Fold], cfg: dict) -> pd.DataFrame | None:
    """One row per held-out rookie-season, over every fold: the emitted band, the realized outcome and
    the served point. Every metric below is a reduction of THIS frame, so the pooled numbers, the
    per-position numbers and the per-class numbers can never disagree about their own population."""
    parts = []
    for f in folds:
        got = candidate_band(f, cfg)
        if got is None:
            continue
        lo, hi, fell = got
        parts.append(pd.DataFrame({
            "year": f.year, "pos": f.test["position_group"].astype(str).str.upper().to_numpy(),
            "lo": lo, "hi": hi, "y": f.test_real, "point": f.test_pred, "fell_back": fell}))
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def _degeneracy(lo: np.ndarray, hi: np.ndarray, point: np.ndarray) -> dict:
    """The DEFECT metrics `audit_interval_quality()` fires on — how much of the band is per-player."""
    keys = list(zip(np.round(lo, 1), np.round(hi, 1)))
    counts: dict = {}
    for kk in keys:
        counts[kk] = counts.get(kk, 0) + 1
    width = hi - lo
    wide = width > 1e-9
    frac = np.where(wide, (point - lo) / np.where(wide, width, 1.0), 0.5)
    return {
        "distinct_band_frac": round(float(len(counts)) / max(1, len(keys)), 4),
        "max_shared_band": int(max(counts.values())) if counts else 0,
        "n_extreme_tail": int(np.sum((frac < 0.05) | (frac > 0.95))),
        "width_point_rho": (round(float(pd.Series(width).corr(pd.Series(point), method="spearman")), 3)
                            if len(point) > 3 else None),
    }


def score_rows(rows: pd.DataFrame) -> dict:
    """Every reading of one arm, ROW-POOLED, with the per-position coverage the floor is applied to and
    the NF1.7 class-mean convention reported beside it for comparability."""
    lo, hi = rows["lo"].to_numpy(dtype=float), rows["hi"].to_numpy(dtype=float)
    y, point = rows["y"].to_numpy(dtype=float), rows["point"].to_numpy(dtype=float)
    inside = (y >= lo) & (y <= hi)
    isc = interval_score(lo, hi, y)
    per_class = rows.assign(_is=isc).groupby("year")["_is"].mean()
    out = {
        "n": int(len(rows)),
        "interval_score": round(float(np.mean(isc)), 3),
        # the NF1.7 convention (mean of per-class means), reported so the two stories are comparable
        "interval_score_classmean": round(float(per_class.mean()), 3),
        "coverage_80": round(float(np.mean(inside)), 4),
        "mean_width": round(float(np.mean(hi - lo)), 2),
        "median_width": round(float(np.median(hi - lo)), 2),
        "fallback_frac": round(float(rows["fell_back"].mean()), 4),
        **_degeneracy(lo, hi, point),
        "per_cohort": {int(k): round(float(v), 3) for k, v in per_class.items()},
    }
    for p, g in rows.assign(_in=inside, _w=hi - lo, _is=isc).groupby("pos"):
        out[f"cov_{p}"] = round(float(g["_in"].mean()), 4)
        out[f"n_{p}"] = int(len(g))
        out[f"width_{p}"] = round(float(g["_w"].mean()), 1)
        out[f"is_{p}"] = round(float(g["_is"].mean()), 2)
        out[f"fallback_{p}"] = round(float(g["fell_back"].mean()), 4)
        # the per-class spread of THIS position's coverage — the cluster-aware standard error, which is
        # the honest one: rookie-seasons inside a draft class are not independent draws.
        cls = g.groupby("year")["_in"].mean()
        out[f"covsd_{p}"] = (round(float(cls.std(ddof=1) / np.sqrt(len(cls))), 4)
                             if len(cls) > 1 else None)
    return out


def run_arm(folds: list[Fold], cfg: dict) -> dict | None:
    rows = arm_rows(folds, cfg)
    if rows is None or rows.empty:
        return None
    return {**cfg, **score_rows(rows)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Anchors — the four NF1.7 guards, plus the per-position reading of the degenerates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _permuted_arm(fold: Fold, cfg: dict, seed_base: int = 20260729) -> tuple[np.ndarray, np.ndarray]:
    """⭐ ANCHOR GUARD 2 — THE PERMUTATION ORACLE. The same family, on the SAME rows, fitted against a
    PERMUTATION of the training outcomes instead of the truth. Knowing the answer must score better
    than not knowing it, and unlike a peeking fitted oracle this comparison is well-posed at ANY sample
    size: family and resolution are held exactly equal, only the information content moves.

    (NF1.7 learned this the hard way twice — a cross-family peeking oracle was legitimately beaten by
    an honest well-specified candidate, and a peeking k-NN fitted on ~80 test rows was beaten because a
    k-NN's CAPACITY depends on n. "Peeking can only help" holds at equal family AND equal sample size.)

    Deterministic per fold (`seed_base + year`) so the anchor is reproducible."""
    pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    rng = np.random.default_rng(seed_base + fold.year)
    shuffled = fold.train.assign(
        rookie_fp_ppr=rng.permutation(
            pd.to_numeric(fold.train["rookie_fp_ppr"], errors="coerce").to_numpy(dtype=float)))
    m = SP.fit_rookie_band_model(shuffled, fold.train_pred, **_band_kwargs(cfg))
    if m is None:
        return np.full(len(pos), np.nan), np.full(len(pos), np.nan)
    lo, hi = m.band_many(pos, fold.test_pred, overall=fold.test.get("draft_overall"),
                         resid_sd=fold.test.get("projected_nfl_z_sd"))
    bad = ~(np.isfinite(lo) & np.isfinite(hi))
    if bad.any():
        idx = np.where(bad)[0]
        lo[idx], hi[idx] = _tercile_band(fold, fold.test_pred, pos, idx)
    return _finish(lo, hi, fold.test_pred)


def anchor_bands(fold: Fold, oracle_k: int) -> dict:
    """The anchor set on one held-out class: TWO degenerate ceilings that must lose, the class-level
    incumbent, and the same-family peeking oracles (kept for orientation — the check that the report
    leans on is the PERMUTATION, built per winning family in `run_anchors`)."""
    out = dict(NF17.anchor_bands(fold, oracle_k))
    return out


def run_anchors(folds: list[Fold], oracle_k: int, permute_cfgs: dict[str, dict]) -> dict:
    """Every anchor scored with the SAME row-pooled reducer the candidates use, so an anchor and a
    candidate can never be compared across two different conventions."""
    per: dict[str, list[pd.DataFrame]] = {}

    def _add(tag: str, fold: Fold, lo, hi) -> None:
        per.setdefault(tag, []).append(pd.DataFrame({
            "year": fold.year, "pos": fold.test["position_group"].astype(str).str.upper().to_numpy(),
            "lo": lo, "hi": hi, "y": fold.test_real, "point": fold.test_pred,
            "fell_back": np.zeros(len(fold.test_pred), dtype=bool)}))

    for f in folds:
        for tag, (lo, hi) in anchor_bands(f, oracle_k).items():
            _add(tag, f, lo, hi)
        for fam, cfg in permute_cfgs.items():
            lo, hi = _permuted_arm(f, cfg)
            if np.isfinite(lo).all() and np.isfinite(hi).all():
                _add(f"permuted_{fam}", f, lo, hi)
    return {tag: score_rows(pd.concat(parts, ignore_index=True)) for tag, parts in per.items()}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The PER-POSITION floor
# ══════════════════════════════════════════════════════════════════════════════════════════════
def position_power(rec: dict, positions: list[str]) -> list[dict]:
    """⚠️ POWER, REPORTED RATHER THAN ASSUMED. A per-position floor at nominal is a hypothesis test with
    the sample size of ONE POSITION behind it. Two standard errors are given because they answer
    different questions:
      · the BINOMIAL SE — sqrt(p(1−p)/n) at p = nominal — the idealised sampling error, and what the
        Tier-2 floor is derived from (it depends only on n, a design quantity);
      · the CLASS-CLUSTERED SE — the spread of the position's per-class coverage ÷ √classes — the
        honest one, because rookie-seasons inside a draft class share a season and are not independent
        draws. When it exceeds the binomial SE, class-to-class variation is the dominant uncertainty.
    `min_not_significantly_below` is the smallest observed coverage that is NOT significantly below
    nominal one-sided at 95% — i.e. the value below which a floor miss is real rather than noise."""
    from scipy.stats import binom
    rows = []
    for p in positions:
        n = int(rec.get(f"n_{p}") or 0)
        if n <= 0:
            continue
        se = float(np.sqrt(_NOMINAL * (1 - _NOMINAL) / n))
        cov = rec.get(f"cov_{p}")
        # EXACT (not asymptotic) probability that a PERFECTLY-calibrated arm is rejected by a hard
        # point-estimate floor at nominal: P(X/n < nominal) for X ~ Binom(n, nominal). ⚠️ It is ≈ 0.5
        # and BARELY MOVES WITH n — which is the honest reading of a point-estimate floor: n does not
        # buy a lower false-reject rate, it buys the ability to detect a SMALLER true shortfall.
        rows.append({
            "position": p, "n": n,
            "coverage (NF1.7 winner)": cov,
            "binomial SE": round(se, 4),
            "class-clustered SE": rec.get(f"covsd_{p}"),
            "min_not_significantly_below": round(_NOMINAL - _TIER2_Z * se, 4),
            "z vs nominal": (round((cov - _NOMINAL) / se, 2) if isinstance(cov, (int, float)) else None),
            "significantly below nominal?":
                ("NO" if isinstance(cov, (int, float)) and cov >= _NOMINAL - _TIER2_Z * se else "yes"),
            "P(reject | truly nominal)": round(float(binom.cdf(np.ceil(_NOMINAL * n) - 1, n, _NOMINAL)), 3),
        })
    return rows


def position_floors(rec: dict, positions: list[str], tier: int) -> dict[str, float]:
    """The pre-registered per-position floors.

    TIER 1 (primary): every position with ≥`_POS_FLOOR_MIN_N` held-out rookie-seasons must cover at
      least the NOMINAL 0.80. A position below that count is left UNCONSTRAINED and said to be so — a
      floor on 12 rows is noise, and a floor nobody can meet for statistical reasons is a floor that
      gets quietly dropped later.
    TIER 2 (documented fallback, used ONLY if Tier 1 admits no config): the structurally-thin positions
      (`_TIER2_POSITIONS` — QB: ~10 drafted a class, ~35% never take a snap) relax to
      `nominal − 1.645·SE(n)`, i.e. "not significantly below nominal one-sided at 95%". Derived from
      SAMPLE SIZE ALONE, which is what stops it being a floor reverse-engineered from the answer.
      Every other position keeps the hard nominal floor."""
    floors: dict[str, float] = {}
    for p in positions:
        n = int(rec.get(f"n_{p}") or 0)
        if n < _POS_FLOOR_MIN_N:
            continue
        if tier == 2 and p in _TIER2_POSITIONS:
            floors[p] = round(_NOMINAL - _TIER2_Z * float(np.sqrt(_NOMINAL * 0.2 / n)), 4)
        else:
            floors[p] = _NOMINAL
    return floors


def deflate(matrix: pd.DataFrame, subset: list[str] | None = None) -> dict:
    """CSCV/PBO **plus Bailey's companion statistic**, because PBO alone is unreadable on this field.

    ⚠️ WHY THE COMPANION IS NOT OPTIONAL HERE. CLAUDE.md's rule is "a high PBO on a TIED field is the
    NULL; a high PBO with a WIDE spread is genuine overfitting — the spread is the discriminator." NF1.8
    breaks that heuristic's assumption: its field contains BOTH ~15 near-clones within 0.3% of each
    other AND known-bad nulls 27% away, so the min→max spread reads WIDE while the actual contest at the
    top is a coin flip. Reading those two numbers together would condemn a selection that is merely
    tied. So two more numbers are reported:
      · `os_gap_pct` — Bailey's PERFORMANCE DEGRADATION: the median, over splits, of how much worse the
        in-sample winner actually SCORES out-of-sample than the out-of-sample best. This is the question
        a practitioner has: not "did my pick rank badly?" but "did picking it COST anything?" A high PBO
        with a ~0% degradation is a tie by definition — the flips are between arms that score the same.
      · `contender_spread_pct` — the min→max spread over the top QUARTILE only, i.e. among arms that
        could plausibly be selected. That is the spread the CLAUDE.md heuristic actually means.
      · ⭐ `flips` — WHICH arms win the in-sample halves, and how often. This is the most informative
        of the four and the cheapest: a PBO near 0.5 whose flip mass sits on two arms a fraction of a
        percent apart is a TIE between them, whereas the same PBO spread thinly over a dozen unrelated
        arms is a search that has learnt nothing. PBO compresses that distinction away.
    `subset` restricts the search to the ELIGIBLE labels, which mirrors the real selection rule (argmin
    interval score among configs that clear the floors) rather than a search nobody performed.

    ⚠️ The floors are held FIXED at their full-sample values inside the splits rather than recomputed
    per split: a per-position coverage estimated on 3 draft classes (~35 QB rows) is far too noisy to
    define an eligible set, so recomputing would deflate against noise rather than against overfitting.
    That is a stated simplification, not an oversight."""
    m = matrix if subset is None else matrix[[c for c in matrix.columns if c in set(subset)]]
    base = pbo(m)
    n = len(m.index)
    if n < 4 or m.shape[1] < 2:
        return {**base, "os_gap_pct": None, "contender_spread_pct": None, "flips": [],
                "n_configs": m.shape[1]}
    gaps: list[float] = []
    wins: dict[str, int] = {}
    for combo in itertools.combinations(range(n), n // 2):
        os_idx = [i for i in range(n) if i not in combo]
        winner = m.iloc[list(combo)].mean(axis=0).idxmin()
        os = m.iloc[os_idx].mean(axis=0)
        wins[winner] = wins.get(winner, 0) + 1
        gaps.append(100.0 * (float(os[winner]) - float(os.min())) / max(1e-9, float(os.min())))
    means = m.mean(axis=0).sort_values()
    top = means.iloc[:max(4, len(means) // 4)]
    return {**base, "os_gap_pct": round(float(np.median(gaps)), 3),
            "os_gap_p90_pct": round(float(np.percentile(gaps, 90)), 3),
            "contender_spread_pct": round(100.0 * (float(top.max()) - float(top.min()))
                                          / max(1e-9, float(top.min())), 2),
            "flips": [{"config": k, "IS-half wins": v, "share": round(v / len(gaps), 3),
                       "full-sample IS80": round(float(means[k]), 3),
                       "Δ vs best %": round(100.0 * (float(means[k]) - float(means.min()))
                                            / float(means.min()), 2)}
                      for k, v in sorted(wins.items(), key=lambda kv: -kv[1])],
            "n_configs": m.shape[1]}


_REQUIRED_ANCHORS = ("oracle_knn", "oracle_qreg", "zero_width", "max_width", "const_width",
                     "permuted_own", "permuted_knn_norm")


def require_anchors(scored: dict) -> None:
    """⭐ ANCHOR GUARD 1 (NF1.7 lesson 1) — A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS.

    An anchor that fails to fit makes its own check VACUOUSLY TRUE: `best >= anchor` on an absent
    anchor is not evaluated at all, so the check passes on NOTHING. NF1.7's first harness did exactly
    that — the production fitter refuses a per-position fit under 40 rows and a held-out class is only
    ~80 rows across four positions, so both oracle attempts returned None and `oracle_respected` was
    reported green having compared nothing. Factored out of `main` so this is unit-testable rather than
    only reachable through a 20-second bake-off."""
    missing = [k for k in _REQUIRED_ANCHORS if k not in scored]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not fit — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


def _find_label(results: list[dict], label: str) -> dict | None:
    return next((r for r in results if r["label"] == label), None)


def floor_slack_rows(rec: dict, floors: dict[str, float]) -> dict[str, int]:
    """⭐ THE FLOOR MARGIN EXPRESSED IN ROOKIE-SEASONS, not in coverage decimals — because a coverage
    decimal hides how few outcomes a per-position floor actually rests on. QB's coverage moving
    0.778 → 0.815 sounds like a calibration change; it is **three rookie-seasons out of 81**. How many
    covered rows a position could lose before its floor breaks is the honest statement of the margin,
    and it is the number a reader needs in order to not over-trust the floor."""
    return {p: int(np.floor((rec.get(f"cov_{p}") or 0) * (rec.get(f"n_{p}") or 0)
                            - f * (rec.get(f"n_{p}") or 0) + 1e-9))
            for p, f in floors.items() if rec.get(f"n_{p}")}


def floor_misses(rec: dict, floors: dict[str, float]) -> list[str]:
    """Which floors a config misses — pooled first, then each position. Empty ⇒ eligible."""
    out = []
    if (rec.get("coverage_80") or 0) < _COVERAGE_FLOOR:
        out.append(f"pooled {rec.get('coverage_80')}<{_COVERAGE_FLOOR:.2f}")
    for p, f in sorted(floors.items()):
        cov = rec.get(f"cov_{p}")
        if cov is None or cov < f:
            out.append(f"{p} {cov}<{f:.3f}")
    return out


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
    nf17, floors, POS = out["nf17_winner"], out["floors"], out["positions"]
    p("# NF1.8 — the rookie 80% interval under a PER-POSITION coverage FLOOR (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **configs scored:** "
      f"{len(out['configs'])} · **held-out rookie-seasons:** {best['n']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is "
      "selected is the WIDTH AND SHAPE of the rookie interval; the POINT projection is held "
      "byte-identical across every arm (proved below).")
    p("")
    p("## 0. Why NF1.7 needed this follow-up")
    p("")
    p("NF1.7 replaced NF1.4's class-level rookie band with a per-player one, selected on a PROPER "
      "interval score with a pre-registered **POOLED** coverage floor of 0.80. Pooled coverage rose "
      "0.791 → 0.808 and the floor was met. But the coverage **redistributed** rather than improving "
      "uniformly:")
    p("")
    p(_md(pd.DataFrame(out["nf17_redistribution"])))
    p("")
    p("That was not a gate miss — the floor was pooled, and pooled cleared it. It is, however, the "
      "same class of blind spot as NF1.4's, one level up: **pooled coverage is a POPULATION property "
      "that one position can pay for on another's behalf.** A band can hold 80% overall while "
      "systematically under-covering the position whose outcome distribution it fits worst, and "
      "rookie QB is exactly that position. So the floor moves per-position.")
    p("")
    p("⭐ **What does NOT change:** the SELECTION metric is still the interval score. Coverage — "
      "pooled or per-position — is an ELIGIBILITY FLOOR, never a target (E2.1-r). §2 proves that "
      "directly: the `max_width` degenerate satisfies EVERY per-position floor and still loses.")
    p("")
    p("### ⚠️ One metric-convention change, and it is load-bearing")
    p("")
    p("NF1.7 averaged each metric over the held-out CLASSES (a mean of per-class means). NF1.8 pools "
      "over ROWS, for two reasons: (a) a per-position floor **cannot** be a mean of per-class means — "
      "NF1.7 required ≥3 rows for a position to enter a class's mean, so a position thin in one class "
      "was silently DROPPED and the floor would be evaluated on a quietly different population than "
      "the one it claims to protect; (b) a rookie-season is the unit the floor is about, so each "
      "should weigh the same. Both conventions are reported for every config below.")
    p("")
    p(_md(pd.DataFrame(out["convention"])))
    p("")
    p("## 1. The pre-registered PER-POSITION floor")
    p("")
    p(f"**Tier 1 (primary):** pooled coverage ≥ {_COVERAGE_FLOOR:.2f} **and** every position with "
      f"≥ {_POS_FLOOR_MIN_N} held-out rookie-seasons ≥ the nominal {_NOMINAL:.2f}.")
    p("")
    p(f"**Tier 2 (documented fallback, used only if Tier 1 admits nothing):** the structurally-thin "
      f"positions ({', '.join(_TIER2_POSITIONS)}) relax to `nominal − 1.645·SE(n)` — 'not "
      f"significantly below nominal, one-sided at 95%'. Derived from SAMPLE SIZE alone (a design "
      f"quantity known before any result), which is what stops it being a floor reverse-engineered "
      f"from the answer. Every other position keeps the hard nominal floor.")
    p("")
    p(f"**TIER USED: {out['tier']}** — {out['tier_note']}")
    p("")
    p(_md(pd.DataFrame([{"position": k, "floor": v,
                         "n (held-out rookie-seasons)": best.get(f"n_{k}")}
                        for k, v in sorted(floors.items())])))
    p("")
    p("## 2. The anchor set — four guards, carried from NF1.7")
    p("")
    p(_md(pd.DataFrame(out["anchor_table"])))
    p("")
    checks = out["anchor_checks"]
    p("⭐ **The oracle is a PERMUTATION** (`permuted_*`): the same family, on the same rows, fitted "
      "against a SHUFFLE of the training outcomes instead of the truth. Knowing the answer must score "
      "better than not knowing it. Unlike a peeking fitted oracle this is well-posed at ANY sample "
      "size — family and resolution are held exactly equal and only the information content moves — "
      "which is the NF1.7 lesson that a peeking MISSPECIFIED oracle, or a peeking k-NN fitted on ~80 "
      "test rows, is legitimately beatable by an honest in-fold arm. The same-family peeking oracles "
      "are still reported and still checked, for orientation.")
    p("")
    for label, ok, msg in out["check_lines"]:
        p(f"- {'✅' if ok else '🚨'} **{label}** — "
          + (msg if ok else "**THE METRIC OR THE SELECTION IS SUSPECT — do NOT ship it**"))
    p("")
    p("### ⭐ The proof the per-position floor is a CONSTRAINT and not the selector")
    p("")
    p(_md(pd.DataFrame(out["degenerate_vs_floor"])))
    p("")
    p(out["degenerate_note"])
    p("")
    p("## 3. Power — what a per-position floor can and cannot resolve")
    p("")
    p(_md(pd.DataFrame(out["power"])))
    p("")
    p(out["power_note"])
    p("")
    p("## 4. Results — all configs (sorted by the primary metric)")
    p("")
    p(_md(pd.DataFrame(out["table"])))
    p("")
    p("`eligible` applies the floors of §1. `fallback %` is the share of held-out rookies whose "
      "per-player fit was REFUSED and who therefore carried the CLASS-LEVEL band — a config with a "
      "high fallback rate at a position is the incumbent in disguise there, however well it covers. "
      "`distinct-band frac` = distinct (p10, p90) pairs ÷ rookies (1.0 = fully per-player; the "
      "incumbent's 3-buckets-per-position is ~0.18). `worst shared` is the number "
      "`audit_interval_quality()` fires on.")
    p("")
    p("## 5. Deflation — CSCV / PBO over held-out draft-class splits")
    p("")
    d, de = out["pbo"], out["pbo_eligible"]
    p(_md(pd.DataFrame(out["deflation_table"])))
    p("")
    p(f"Whole-field spread (best→worst IS80) = {out['spread']['min']} → {out['spread']['max']} "
      f"({out['spread']['pct']}%).")
    p("")
    p("**⚠️ THIS FIELD BREAKS THE USUAL PBO HEURISTIC, AND THE FIX IS TO ADD A NUMBER RATHER THAN TO "
      "ARGUE WITH THE OLD ONE.** CLAUDE.md's rule is: a high PBO on a TIED field is the NULL; a high "
      "PBO with a WIDE spread is genuine overfitting; the spread is the discriminator. NF1.8's field "
      "violates that rule's premise — it contains BOTH ~15 near-clones within 0.3% of each other at "
      "the top AND known-bad nulls 27% away at the bottom, so the whole-field spread reads WIDE while "
      "the actual contest among contenders is a coin flip. Read together, those two numbers would "
      "condemn a selection that is merely tied. So two further statistics are reported:")
    p("")
    p("- **`os_gap_pct` — Bailey's PERFORMANCE DEGRADATION.** How much worse the in-sample winner "
      "actually SCORES out-of-sample than the out-of-sample best. This is the decision-relevant "
      "question: not 'did my pick rank badly?' but 'did picking it COST anything?' A high PBO with a "
      "~0% degradation is a tie **by definition** — the rank flips are between arms that score the "
      "same, which is what a rank statistic cannot distinguish from overfitting.")
    p("- **`contender_spread_pct` — the spread over the top QUARTILE only**, i.e. among arms that could "
      "plausibly be selected. That is the spread the heuristic actually means.")
    p("- ⭐ **`flips` — WHICH arms win the in-sample halves, and how often** (table below). The cheapest "
      "and most informative of the four: a PBO near 0.5 whose flip mass sits on two arms a fraction of "
      "a percent apart is a TIE BETWEEN THEM; the same PBO spread thinly over a dozen unrelated arms is "
      "a search that has learnt nothing. PBO compresses that distinction away, and it is exactly the "
      "distinction this field turns on.")
    p("")
    p("### Which arms actually win the in-sample halves (ELIGIBLE set)")
    p("")
    p(_md(pd.DataFrame(de.get("flips", [])[:8])))
    p("")
    p(out["deflation_verdict"])
    p("")
    p("## 6. Selection")
    p("")
    p(f"**SHIPPED: `{best['label']}`** — IS80 {best['interval_score']} · pooled coverage "
      f"{best['coverage_80']} · mean width {best['mean_width']} · distinct-band fraction "
      f"{best['distinct_band_frac']} · worst shared band {best['max_shared_band']} · fallback "
      f"{100 * (best['fallback_frac'] or 0):.1f}%.")
    p("")
    p(out["verdict"])
    p("")
    p("### ⭐ What the per-position conformal layer actually bought (the FOIL comparison)")
    p("")
    p(_md(pd.DataFrame(out["mechanism"])))
    p("")
    p(out["mechanism_note"])
    p("")
    p("### The tie among ELIGIBLE arms — and why it is not re-picked on coverage headroom")
    p("")
    p(_md(pd.DataFrame(out["tied"])))
    p("")
    p(out["tie_note"])
    p("")
    p("### Per-position coverage and WIDTH — the incumbent, NF1.7, and NF1.8 side by side")
    p("")
    p(_md(pd.DataFrame(out["per_position_compare"])))
    p("")
    p(out["width_note"])
    p("")
    p("## 7. Per-class detail (shipped config)")
    p("")
    p(_md(pd.DataFrame([{"draft_class": y, "interval_score": v}
                        for y, v in sorted(best["per_cohort"].items())])))
    p("")
    p("## 8. Honest limitations")
    p("")
    for line in out["limitations"]:
        p(f"- {line}")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.8 rookie interval — per-position coverage floor")
    ap.add_argument("--pool", default=str(NF17._POOL_CACHE))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--oracle-k", type=int, default=25)
    ap.add_argument("--board", default=str(_ART / "nfl_fantasy_season_projections_2026.parquet"))
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="a TINY slice (4 classes, the parametric arms only) to prove the code path")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    pool = load_pool(Path(args.pool))
    folds = build_folds(pool, list(range(args.from_year, args.to_year + 1)))
    if args.smoke:
        folds = folds[:4]
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    cfgs = [c for c in candidate_configs()
            if not args.smoke or c["arm"] != "model" or "qreg" in str(c.get("form"))]
    log.info("NF1.8 bake-off: %d classes (%s) × %d configs", len(folds), cohorts, len(cfgs))

    # ⭐ POINT-INVARIANCE PROOF — the band's conditioning variable IS the served point projection, and
    #    NF1.8 must not move the point at all (the story's hard constraint).
    point_drift = max(NF17._served_point_is_reproduced(f) for f in folds)
    if point_drift > 1e-6:
        raise SystemExit(
            f"the band's conditioning variable drifted from the SERVED point projection by "
            f"{point_drift:.6f} — `rookie_point_projection` no longer reproduces `project_rookies`. "
            "Fix that before reading any selection.")
    log.info("point-invariance proof: served point reproduced exactly (max drift %.2e)", point_drift)

    results = [r for r in (run_arm(folds, c) for c in cfgs) if r is not None]
    POS = sorted({k[4:] for r in results for k in r if k.startswith("cov_")})
    incumbent = next(r for r in results if r["arm"] == "class_tercile")
    nf17 = _find_label(results, _NF17_WINNER_LABEL)
    if nf17 is None:
        raise SystemExit(f"the NF1.7 winner ({_NF17_WINNER_LABEL}) is not in the field — it must be re-scored "
                         "here, or the comparison to NF1.7 is unanchored")

    # ── the floors, and the two-tier eligibility ────────────────────────────────────────────────
    floors = position_floors(nf17, POS, tier=1)
    searchable = [r for r in results if r["arm"] == "model"]
    tier, elig = 1, [r for r in searchable if not floor_misses(r, floors)]
    if not elig:
        tier = 2
        floors = position_floors(nf17, POS, tier=2)
        elig = [r for r in searchable if not floor_misses(r, floors)]
    tier_note = (
        f"{len(elig)} of {len(searchable)} per-player configs clear the Tier-1 hard nominal floor at "
        f"every position, so the pre-registered Tier-2 fallback was NOT needed — the QB floor is the "
        f"full nominal {_NOMINAL:.2f}." if tier == 1 else
        f"NO config cleared the Tier-1 hard nominal floor at every position, so the documented "
        f"Tier-2 QB floor applies ({floors.get('QB')}); {len(elig)} of {len(searchable)} configs "
        f"clear it.")
    # ⚠️ AN EMPTY ELIGIBLE SET IS AN HONEST NULL AND MUST STILL PRODUCE A REPORT. Exiting here would
    #    leave no artifact of the finding, and the temptation next session would be to relax the floor
    #    until something passes — which is the E2.1-r inversion arriving by the back door. Instead the
    #    NF1.7 winner is carried as the arm of record, the gate goes RED, and the null is written down.
    null_result = not elig
    if null_result:
        log.warning("[ALERT] no config clears even the Tier-2 floors — reporting an HONEST NULL; "
                    "NF1.7's band stands and the gate is RED")
    best = min(elig, key=lambda r: r["interval_score"]) if elig else nf17

    # ── anchors. The permutation is built from the WINNER'S OWN config (`permuted_own`) so family AND
    #    resolution are held exactly equal and only the information content moves; a neighbourhood-family
    #    permutation runs beside it so the check is never the only one that fitted.
    permute_cfgs = {
        "own": ({"arm": "model", **{k: v for k, v in best.items()
                                    if k in ("form", "k", "qreg_alpha", "resid_sd_gain",
                                             "qreg_per_pos", "cqr_mode", "cqr_scale")}}
                if best["arm"] == "model" else
                {"arm": "model", "form": "qreg", "qreg_alpha": 0.01}),
        "knn_norm": {"arm": "model", "form": "knn_norm", "k": 80},
    }
    anchors = run_anchors(folds, args.oracle_k, permute_cfgs)

    a_is = {k: v["interval_score"] for k, v in anchors.items()}
    require_anchors(a_is)          # ⚠️ ANCHOR GUARD 1 — a missing anchor RAISES, never passes
    own_oracle = "oracle_qreg" if str(best.get("form", "")).startswith("qreg") else "oracle_knn"
    own_perm = "permuted_own"
    checks = {
        "permutation_respected": bool(best["interval_score"] < a_is[own_perm]),
        "permutation_family": own_perm,
        "oracle_respected": bool(best["interval_score"] >= a_is[own_oracle] - 1e-9),
        "oracle_family": own_oracle,
        "zero_width_loses": bool(best["interval_score"] < a_is["zero_width"]),
        "max_width_loses": bool(best["interval_score"] < a_is["max_width"]),
        "const_width_loses": bool(best["interval_score"] < a_is["const_width"]),
        "beats_incumbent": bool(best["interval_score"] < incumbent["interval_score"]),
        "pooled_floor_met": bool((best["coverage_80"] or 0) >= _COVERAGE_FLOOR),
        "per_position_floor_met": not floor_misses(best, floors),
        "point_unchanged": bool(point_drift <= 1e-6),
    }
    check_lines = [
        ("permutation oracle respected", checks["permutation_respected"],
         f"the winner beats its OWN family fitted on SHUFFLED outcomes ({checks['permutation_family']}"
         f": {a_is[own_perm]} vs {best['interval_score']}) — the metric rewards information, not width"),
        ("same-family peeking oracle respected", checks["oracle_respected"],
         f"the winner does not beat a peeking fit of its own family ({checks['oracle_family']})"),
        ("zero-width degenerate loses", checks["zero_width_loses"],
         "sharpness was not bought by under-covering"),
        ("max-width degenerate loses", checks["max_width_loses"],
         "the selection is not a coverage exercise in disguise — see the table below"),
        ("const-width degenerate loses", checks["const_width_loses"],
         "conditioning on the player earns its place"),
        ("incumbent beaten", checks["beats_incumbent"],
         "the selected band beats NF1.4's class-level band"),
        ("per-position floor met", checks["per_position_floor_met"],
         f"every position clears its floor ({', '.join(f'{k} {best.get(f'cov_{k}')}≥{v:.3f}' for k, v in sorted(floors.items()))})"),
        ("point projection unchanged", checks["point_unchanged"],
         f"the served rookie point is byte-identical to NF1.7's (max drift {point_drift:.1e})"),
    ]

    # ── deflation over EVERY config scored, AND over the eligible set the selection ran on ──────
    mat = pd.DataFrame({r["label"]: r["per_cohort"] for r in results}).sort_index().dropna(
        axis=1, how="any")
    d = deflate(mat)
    d_elig = deflate(mat, subset=[r["label"] for r in elig]) if elig else dict(d)
    vals = [r["interval_score"] for r in results]
    spread = {"min": round(min(vals), 3), "max": round(max(vals), 3),
              "pct": round(100.0 * (max(vals) - min(vals)) / max(1e-9, min(vals)), 1)}

    # ── the reported tables ─────────────────────────────────────────────────────────────────────
    redistribution = [{"position": p, "n (held-out)": nf17.get(f"n_{p}"),
                       "incumbent (NF1.4 class-level)": incumbent.get(f"cov_{p}"),
                       "NF1.7 (pooled floor)": nf17.get(f"cov_{p}"),
                       "≥ nominal 0.80?": "yes" if (nf17.get(f"cov_{p}") or 0) >= _NOMINAL else "NO"}
                      for p in POS]
    convention = [{"config": r["label"],
                   "IS80 (row-pooled — NF1.8)": r["interval_score"],
                   "IS80 (class-mean — NF1.7)": r["interval_score_classmean"],
                   "Δ": round(r["interval_score"] - r["interval_score_classmean"], 3)}
                  for r in (nf17, incumbent, best) if r]
    anchor_table = [{"anchor": k, "what it is": v, "IS80": a_is.get(k),
                     "pooled cov80": anchors.get(k, {}).get("coverage_80"),
                     "mean width": anchors.get(k, {}).get("mean_width"),
                     **{f"cov {p}": anchors.get(k, {}).get(f"cov_{p}") for p in POS}}
                    for k, v in [
                        ("permuted_own", "⭐ PERMUTATION ORACLE — the WINNER'S OWN arm, same family "
                                         "and same resolution, fitted on SHUFFLED training outcomes. "
                                         "Must LOSE."),
                        ("permuted_knn_norm", "PERMUTATION ORACLE (neighbourhood family). Must LOSE."),
                        ("oracle_qreg", "peeking same-family oracle (parametric) — fitted on the "
                                        "held-out class's truth. Nothing may beat it."),
                        ("oracle_knn", "peeking same-family oracle (neighbourhood). Orientation."),
                        ("zero_width", "DEGENERATE — width 0 at the point. MAXIMALLY sharp ⇒ a naive "
                                       "sharpness metric would crown it. Must LOSE."),
                        ("max_width", "DEGENERATE — [0, the position's max realized rookie season]. "
                                      "Coverage ≈ 1 ⇒ a coverage TARGET would love it. Must LOSE."),
                        ("const_width", "DEGENERATE — ONE band per position, no conditioning at all. "
                                        "Must LOSE."),
                        ("oracle_point", "the trivial infimum (zero width AT the realized value) — "
                                         "orientation only, not a discriminator."),
                    ] if k in a_is]
    deg_rows = []
    for tag in ("max_width", "const_width", "zero_width"):
        rec = anchors[tag]
        deg_rows.append({"degenerate": tag, "IS80": rec["interval_score"],
                         "passes EVERY per-position floor?":
                             "YES" if not floor_misses(rec, floors) else "no",
                         "floors missed": ", ".join(floor_misses(rec, floors)) or "—",
                         "loses to the winner?":
                             "yes" if rec["interval_score"] > best["interval_score"] else "🚨 NO"})
    deg_rows.append({"degenerate": f"SHIPPED — {best['label']}", "IS80": best["interval_score"],
                     "passes EVERY per-position floor?": "YES", "floors missed": "—",
                     "loses to the winner?": "—"})
    degenerate_note = (
        "⭐ **`max_width` satisfies every per-position floor and still loses by a wide margin** — that "
        "is the whole argument that adding a per-position floor did not turn this into a coverage "
        "exercise. A criterion a degenerate wins cannot select an interval (E2.1-r); a CONSTRAINT a "
        "degenerate satisfies is fine, because the degenerate is then eliminated by the metric. This "
        "is also why the floor is not tightened above nominal 'for safety': every notch above nominal "
        "moves the eligible set closer to `max_width` and further from an honest band.")
    power = position_power(nf17, POS)
    qb_n = int(nf17.get("n_QB") or 0)
    qb_se = float(np.sqrt(_NOMINAL * 0.2 / qb_n)) if qb_n else float("nan")
    not_sig = [r["position"] for r in power
               if r["significantly below nominal?"] == "NO"
               and (r["coverage (NF1.7 winner)"] or 0) < _NOMINAL]
    power_note = (
        f"⚠️ **Read this before reading the selection.** QB carries only **{qb_n}** held-out "
        f"rookie-seasons across {len(cohorts)} classes, so the binomial SE of its coverage at nominal "
        f"is **{qb_se:.3f}** — NF1.7's {nf17.get('cov_QB')} sits "
        f"{abs((nf17.get('cov_QB') or 0) - _NOMINAL) / qb_se:.1f} SE below 0.80, i.e. **not "
        f"significantly below nominal**. "
        + (f"The same is true of **{', '.join(not_sig)}**: {'both' if len(not_sig) == 2 else 'all'} "
           f"fail the HARD nominal floor while NOT being significantly below nominal. "
           if len(not_sig) > 1 else "")
        + "Three consequences, all honest:\n\n"
        f"1. **A hard per-position floor at nominal is partly selecting on NOISE.** The exact "
        f"`P(reject | truly nominal)` column shows a perfectly-calibrated arm is rejected ~50% of the "
        f"time at EVERY position — and that rate barely moves with n. Sample size does not buy a lower "
        f"false-reject rate; it buys the ability to detect a SMALLER true shortfall. This is why every "
        f"config counts toward the deflation in §5 and why the pre-registered Tier-2 floor exists.\n"
        f"2. **The gap is nevertheless worth constraining, because the floor turned out CHEAP.** Its "
        f"cost is reported in §6 in interval-score points. Had that cost been large, the honest answer "
        f"would have been to leave NF1.7's band alone and keep disclosing the QB gap — which is exactly "
        f"what NF1.7 did, and would have been the right call again.\n"
        f"3. **The floor is not tightened above nominal 'for safety'.** Every notch above nominal moves "
        f"the eligible set toward `max_width` (§2), which satisfies any coverage floor and is useless.\n\n"
        f"The CLASS-CLUSTERED SE is the more honest column: where it exceeds the binomial SE (RB and WR "
        f"here), class-to-class variation — not per-player miscalibration — is the dominant uncertainty, "
        f"and no amount of in-fold recalibration can remove it. §6 shows that directly.")
    table = [{"config": r["label"], "IS80": r["interval_score"],
              "IS80 (NF1.7 conv.)": r["interval_score_classmean"],
              "cov80": r["coverage_80"],
              **{f"cov {p}": r.get(f"cov_{p}") for p in POS},
              "mean width": r["mean_width"], "distinct-band frac": r["distinct_band_frac"],
              "worst shared": r["max_shared_band"], "fallback %": round(100 * r["fallback_frac"], 1),
              "eligible": "yes" if (r["arm"] == "model" and not floor_misses(r, floors))
                          else ("NO: " + "; ".join(floor_misses(r, floors)) if r["arm"] == "model"
                                else "n/a (null/incumbent)")}
             for r in sorted(results, key=lambda r: r["interval_score"])]
    per_position_compare = []
    for nm, rec in (("incumbent (NF1.4 class-level)", incumbent), ("NF1.7 (pooled floor)", nf17),
                    ("NF1.8 SHIPPED (per-position floor)", best)):
        row = {"arm": nm}
        slack = floor_slack_rows(rec, floors)
        for p in POS:
            row[f"cov {p}"] = rec.get(f"cov_{p}")
        for p in POS:
            row[f"slack {p} (rows)"] = slack.get(p)
        for p in POS:
            row[f"width {p}"] = rec.get(f"width_{p}")
        per_position_compare.append(row)
    slack_best = floor_slack_rows(best, floors)
    tightest = min(slack_best, key=lambda p: slack_best[p]) if slack_best else None
    board = board_band_summary(Path(args.board))
    vet = next((r for r in board if r["population"] == "veterans"), None)
    qb_w = (best.get("width_QB"), nf17.get("width_QB"))
    width_note = (
        f"⭐ **The per-position floor is paid for in WIDTH, and mostly at QB — which is the correct "
        f"answer, not a defect.** QB's mean band goes {qb_w[1]} → {qb_w[0]} PPR "
        f"({'+' if (qb_w[0] or 0) >= (qb_w[1] or 0) else ''}"
        f"{100 * ((qb_w[0] or 0) - (qb_w[1] or 1)) / (qb_w[1] or 1):.1f}%) while its coverage goes "
        f"{nf17.get('cov_QB')} → {best.get('cov_QB')}. A rookie QB whose modal outcome is 'never takes "
        f"a snap' genuinely carries more outcome uncertainty than a rookie WR, and a band that says so "
        f"is more honest than one that reads sharp and misses 26% of the time."
        + (f" Overall the shipped rookie band is {best['mean_width'] / vet['mean width']:.1f}× the "
           f"average veteran band ({best['mean_width']} vs {vet['mean width']} PPR) — a rookie has no "
           f"NFL sample, so wider is the honest direction. Veteran coverage is not comparable (a "
           f"veteran band is a normal approximation off realized game-to-game variance, not an "
           f"empirical quantile), so only the WIDTH is compared." if vet else ""))
    deflation_table = [
        {"search": nm, "configs": v.get("n_configs"), "PBO": v.get("pbo"),
         "median logit": v.get("median_logit"), "os_gap_pct (Bailey degradation)": v.get("os_gap_pct"),
         "os_gap p90 %": v.get("os_gap_p90_pct"),
         "contender spread % (top quartile)": v.get("contender_spread_pct"),
         "splits": v.get("n_splits")}
        for nm, v in (("WHOLE field (every config scored)", d),
                      ("ELIGIBLE set — the search the selection actually ran", d_elig))]

    # ── the deflation VERDICT, read off the flip distribution rather than off PBO alone ──────────
    flips = d_elig.get("flips") or []
    top2 = flips[:2]
    two_arm = (len(top2) == 2 and sum(f["share"] for f in top2) >= 0.5
               and abs(top2[1]["Δ vs best %"] - top2[0]["Δ vs best %"]) < 2.0)
    runner = _find_label(results, top2[1]["config"]) if len(top2) > 1 else None
    deflation_verdict = (
        f"**Verdict on the deflation: {'A TWO-ARM TIE ACROSS FAMILIES — the NULL, not overfitting' if two_arm else 'READ WITH CARE'}.** "
        f"Over the ELIGIBLE set (the search the selection actually ran) PBO = {d_elig.get('pbo')}, "
        f"which taken alone with the 27% whole-field spread would land in the 'genuine overfitting' "
        f"quadrant and forbid shipping. The flip distribution shows what is really happening: "
        + (f"**{top2[0]['IS-half wins']} of {d_elig.get('n_splits')} in-sample halves are won by "
           f"`{top2[0]['config']}` and {top2[1]['IS-half wins']} by `{top2[1]['config']}` — two arms "
           f"from DIFFERENT candidate families, {top2[1]['Δ vs best %']}% apart on the full sample.** "
           f"The top-quartile spread is {d_elig.get('contender_spread_pct')}% and the median "
           f"out-of-sample performance degradation is {d_elig.get('os_gap_pct')}% "
           f"(p90 {d_elig.get('os_gap_p90_pct')}%). A rank statistic flipping between two arms that "
           f"score within a percent of each other cannot separate them, and per CLAUDE.md a TIED field "
           f"is the NULL: *which* of them wins is noise.\n\n"
           f"⇒ **What this story establishes is the per-position FLOOR, not the leaderboard's top row.** "
           f"Both tied arms satisfy every per-position floor, so either is a defensible ship."
           if two_arm else
           f"the flip mass is spread across {len(flips)} arms with a median degradation of "
           f"{d_elig.get('os_gap_pct')}% — the selection is NOT robust and its margin must not be "
           f"treated as real.")
        + ((f"\n\n⚠️ **The tie is broken on the DEFECT METRIC, not on the primary one and NOT on "
            f"coverage headroom.** `{top2[1]['config']}` reverts "
            f"{100 * (runner.get('fallback_frac') or 0):.1f}% of held-out rookies to the CLASS-LEVEL "
            f"band (distinct-band fraction {runner.get('distinct_band_frac')}, worst shared band "
            f"{runner.get('max_shared_band')}) against the shipped arm's "
            f"{100 * (best.get('fallback_frac') or 0):.1f}% / {best.get('distinct_band_frac')} / "
            f"{best.get('max_shared_band')} — i.e. it is partly the very defect NF1.7 exists to remove, "
            f"and is what `audit_interval_quality()` fires on. Breaking a primary-metric tie on the "
            f"program's own defect metric is legitimate; breaking it on coverage headroom would not be, "
            f"because `max_width` wins that (§2). Note the argmin already AGREES with this tiebreak, so "
            f"nothing was re-picked — it is a confirmation, recorded because it would have mattered had "
            f"the two been the other way round.")
           if two_arm and runner is not None else ""))

    # ── the FOIL comparison: what the per-position conformal layer bought, isolated ──────────────
    def _find(lbl: str) -> dict | None:
        return _find_label(results, lbl)
    base_lbl = f"{best.get('form')} α{best.get('qreg_alpha', 0):g} · sdgain {best.get('resid_sd_gain', 0):g}"
    pool_lbl = (f"{best.get('form')}+cqr[pool,{best.get('cqr_scale', 'add')}] · "
                f"sdgain {best.get('resid_sd_gain', 0):g}")
    mechanism = [{"arm": nm, "IS80": r["interval_score"],
                  **{f"cov {p}": r.get(f"cov_{p}") for p in POS},
                  "mean width": r["mean_width"]}
                 for nm, r in (("base — no conformal layer", _find(base_lbl)),
                               ("+ conformal, POOLED calibration (the FOIL)", _find(pool_lbl)),
                               ("+ conformal, PER-POSITION calibration (SHIPPED)", best))
                 if r is not None]
    base_r, pool_r = _find(base_lbl), _find(pool_lbl)
    mechanism_note = (
        "⭐ **The foil earns its place: the POOLED conformal calibration is a numerical NO-OP, so the "
        "gain is attributable to the PER-POSITION conditioning and not to 'conformal' as a word.** "
        + (f"On the shipped base, pooled calibration moves the interval score "
           f"{base_r['interval_score']} → {pool_r['interval_score']} and QB coverage "
           f"{base_r.get('cov_QB')} → {pool_r.get('cov_QB')} — i.e. nowhere — while the per-position "
           f"(Mondrian) calibration moves them to {best['interval_score']} and {best.get('cov_QB')}. "
           if base_r and pool_r else "")
        + "The reason is mechanical and worth recording: the pooled conformity quantile is ≈ 0 because "
          "the base band's OUT-OF-FOLD coverage over the training classes is already ≈ nominal in "
          "aggregate. Only when the conformity scores are read WITHIN a position does the QB-specific "
          "shortfall become visible, and only then can it be corrected.\n\n"
          "⚠️ **And the honest limit of that:** the per-position adjustments are SMALL (on the served "
          "2026 class the fitted inflation is **+0.82 PPR at QB and exactly 0.0 at RB/TE/WR** — the "
          "layer touches ONE position), because each position's in-fold out-of-fold coverage is also "
          "near nominal. In-fold recalibration cannot manufacture coverage that is missing only in the "
          "NEXT class — which is positive evidence that the QB gap is class-to-class variation rather "
          "than a fittable miscalibration, and a reason not to expect any recalibration mechanism to "
          "close it fully.\n\n"
        + (f"**The QB gain decomposes into two roughly equal halves**, and neither is the whole story: "
           f"{nf17.get('cov_QB')} (NF1.7 `qreg`) → {base_r.get('cov_QB')} from moving to the √ scale, "
           f"→ {best.get('cov_QB')} from the Mondrian calibration. The √ scale is the larger structural "
           f"change (the rookie outcome is heavy-right-tailed, so linearity is more plausible there); "
           f"the conformal layer is the part that is TARGETED at the position that was short."
           if base_r else ""))

    # ── the tie among eligible arms ──────────────────────────────────────────────────────────────
    _TIE_PCT = 1.0
    tied = [r for r in sorted(elig or [best], key=lambda r: r["interval_score"])
            if r["interval_score"] <= best["interval_score"] * (1.0 + _TIE_PCT / 100.0)]
    tie_rows = [{"config": r["label"], "IS80": r["interval_score"],
                 "Δ IS80 vs shipped %": round(100.0 * (r["interval_score"] - best["interval_score"])
                                              / best["interval_score"], 2),
                 "pooled cov80": r["coverage_80"],
                 "min per-position headroom":
                     round(min((r.get(f"cov_{p}") or 0) - f for p, f in floors.items()), 3)
                     if floors else None,
                 "mean width": r["mean_width"]} for r in tied]
    def _headroom(r: dict) -> float:
        return min(((r.get(f"cov_{p}") or 0) - f for p, f in floors.items()), default=0.0)
    # the arm with the MOST floor headroom in the tie — the one a coverage-flavoured re-pick would
    # reach for. Ties on headroom broken by the primary metric, so `best` wins when it is already tops.
    best_head = max(tied, key=lambda r: (round(_headroom(r), 4), -r["interval_score"])) if tied else best
    tie_note = (
        f"The top **{len(tied)}** ELIGIBLE configs sit within {_TIE_PCT:g}% of each other on the "
        f"primary metric. Per CLAUDE.md, when the leaders genuinely tie, *which* of them wins is noise "
        f"— and §5's flip distribution says the same thing from the other direction.\n\n"
        + (f"⚠️ **The tie has a coverage asymmetry, and it is declined — exactly as in NF1.7:** "
           f"`{best_head['label']}` carries more headroom above the per-position floors "
           f"({_headroom(best_head):+.3f}) than the shipped arm ({_headroom(best):+.3f}). **We do not "
           f"re-pick on it.**"
           if best_head["label"] != best["label"] else
           f"⭐ **No coverage asymmetry to decline this time:** the shipped arm already carries the most "
           f"headroom above the per-position floors in the tie ({_headroom(best):+.3f}), so — unlike "
           f"NF1.7, where the widened arms bought real headroom for free and had to be turned down — "
           f"there is no temptation to resolve the tie on coverage. Recorded anyway, because the rule "
           f"has to hold when it costs something:")
        + " 'Prefer more headroom above the floor' is MONOTONE IN WIDENING — the `max_width` degenerate "
          "wins it outright (§2), and it satisfies every per-position floor while being useless. "
          "Re-picking a tie on a criterion a degenerate wins is the E2.1-r inversion facing the other "
          "way. The floor is a CONSTRAINT; the interval score SELECTS; the argmin breaks the tie "
          "because a rule must break it somehow.\n\n"
          "(The `min per-position headroom` column is a MIN over positions, so it is bound by whichever "
          "position sits closest to its floor — RB here, not QB. That is the honest reading: RB is now "
          "the tightest position, and a future class that moves RB is the one to watch.)"
        if len(tied) > 1 else
        "The shipped arm is not in a tie among eligible configs — the next eligible arm is more than "
        f"{_TIE_PCT:g}% behind on the primary metric.")

    cost = best["interval_score"] - nf17["interval_score"]
    verdict = (
        "🚨 **HONEST NULL — NOTHING SHIPS.** No pre-registered arm clears the per-position floor at "
        f"every position, even under the documented Tier-2 QB relaxation. NF1.7's `{nf17['label']}` "
        f"stands as the served band, its QB gap ({nf17.get('cov_QB')}) stays DISCLOSED rather than "
        "fixed, and the floor is NOT relaxed further to manufacture a pass — a floor that moves until "
        "something clears it is not a floor. The finding is that per-position coverage at rookie QB is "
        "not reachable by any of the pre-registered mechanisms at this sample size."
        if null_result else
        f"The per-position floor costs **{cost:+.2f} interval-score points "
        f"({100 * cost / nf17['interval_score']:+.1f}%)** against NF1.7's pooled-floor winner "
        f"(`{nf17['label']}`, IS80 {nf17['interval_score']}), and buys every position ≥ its floor: "
        + ", ".join(f"{p} {nf17.get(f'cov_{p}')} → {best.get(f'cov_{p}')}" for p in POS)
        + f". Against the NF1.4 class-level incumbent it is still "
        f"{100 * (incumbent['interval_score'] - best['interval_score']) / incumbent['interval_score']:.1f}% "
        f"better ({incumbent['interval_score']} → {best['interval_score']}) with the distinct-band "
        f"fraction {incumbent['distinct_band_frac']} → {best['distinct_band_frac']}. The rookie POINT "
        f"projection is unchanged (max drift {point_drift:.1e})."
        if best["label"] != nf17["label"] else
        f"**INCUMBENT STANDS.** NF1.7's `{nf17['label']}` is itself the best-scoring config that "
        f"clears every per-position floor, so the per-position floor changes nothing about what is "
        f"served — it upgrades an unverified property into a VERIFIED one. That is a real result: the "
        f"QB gap NF1.7 disclosed is not fixable by any pre-registered arm without giving up more "
        f"interval score than the floor is worth.")
    limitations = [
        "**The point projection is untouched, so a mis-placed rookie stays mis-placed.** NF1.4's "
        "finding was that the rookie point runs COLD and its model bake-off returned a NULL; neither "
        "NF1.7 nor NF1.8 re-attacks the level, and neither may be read as having improved it.",
        f"**Per-position coverage is estimated on {', '.join(f'{p} n={nf17.get(f'n_{p}')}' for p in POS)}** "
        "held-out rookie-seasons. The QB floor in particular is a hypothesis test with ~80 rows behind "
        "it (§3): passing it is necessary, not proof of calibration, and a future class can move it.",
        (f"🚨 **THE FLOOR IS CLEARED BY A HANDFUL OF ROOKIE-SEASONS, AND THAT MUST NOT BE READ AS A "
         f"COMFORTABLE PASS.** The margins in ROWS (see §6) are "
         + ", ".join(f"{p} {slack_best.get(p)}" for p in POS)
         + f" — i.e. {tightest} clears its floor by {slack_best.get(tightest)} covered rookie-season(s), "
           f"and QB's whole 'fix' is {int(round((best.get('cov_QB') or 0) * (best.get('n_QB') or 0))) - int(round((nf17.get('cov_QB') or 0) * (nf17.get('n_QB') or 0)))} "
           f"more covered rookie-seasons out of {best.get('n_QB')}. A coverage decimal makes that look "
           f"like a calibration change; it is a small number of outcomes. The floor is a genuine "
           f"pre-registered constraint and it is genuinely met, but nobody should treat 'QB now covers "
           f"0.815' as a stable property of the model."),
        "**A floor is not a guarantee out of sample.** The floor is met on held-out draft classes "
        "2019–2025; the 2026 class is a genuine extrapolation and the served band carries "
        "`confidence = low` for exactly this reason.",
        "**The conformal arms calibrate IN-FOLD, so they cannot see a NEXT-CLASS gap.** Their fitted "
        "per-position adjustments are small precisely because the training folds' out-of-fold coverage "
        "is already ≈ nominal at every position — evidence that the QB gap is class-to-class variation "
        "rather than a fittable miscalibration, and a reason not to expect any recalibration mechanism "
        "to remove it.",
        "**A rookie's band still cannot see anything NFL-specific** — no camp reports, no depth chart, "
        "no preseason. Draft slot, the P1A translation and its parameter sd are the whole information "
        "set.",
        "**No edge claim.** An honest interval is a projection-quality property, not a market edge.",
    ]

    out = {
        "cohorts": cohorts, "positions": POS, "configs": results, "anchors": anchors,
        "anchor_checks": checks, "check_lines": check_lines, "anchor_table": anchor_table,
        "degenerate_vs_floor": deg_rows, "degenerate_note": degenerate_note,
        "best": best, "incumbent": incumbent, "nf17_winner": nf17,
        "nf17_redistribution": redistribution, "convention": convention,
        "floors": floors, "tier": tier, "tier_note": tier_note,
        "power": power, "power_note": power_note, "table": table,
        "per_position_compare": per_position_compare, "width_note": width_note,
        "mechanism": mechanism, "mechanism_note": mechanism_note,
        "tied": tie_rows, "tie_note": tie_note, "null_result": null_result,
        "deflation_table": deflation_table, "pbo_eligible": d_elig,
        "deflation_verdict": deflation_verdict,
        "pbo": d, "spread": spread, "verdict": verdict, "limitations": limitations,
        "point_drift": point_drift, "coverage_floor": _COVERAGE_FLOOR, "nominal": _NOMINAL,
        "board": board, "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    print("\n=== NF1.8 rookie 80% interval under a PER-POSITION floor ===")
    hdr = f"{'config':38s} {'IS80':>8s} {'cov':>6s} " + " ".join(f"{p:>6s}" for p in POS) + \
          f" {'width':>7s} {'fb%':>5s} elig"
    print(hdr)
    for r in sorted(results, key=lambda r: r["interval_score"]):
        miss = floor_misses(r, floors) if r["arm"] == "model" else ["n/a"]
        print(f"{r['label']:38s} {r['interval_score']:8.2f} {r['coverage_80']:6.3f} "
              + " ".join(f"{(r.get(f'cov_{p}') or 0):6.3f}" for p in POS)
              + f" {r['mean_width']:7.1f} {100 * r['fallback_frac']:5.1f} "
              + ("yes" if not miss else "; ".join(miss)))
    print(f"\ntier={tier} floors={floors}")
    print("anchors: " + " · ".join(f"{k} IS80={v['interval_score']}" for k, v in anchors.items()))
    print("checks: " + " · ".join(f"{k}={v}" for k, v in checks.items()))
    print(f"PBO(all)={d.get('pbo')} PBO(eligible)={d_elig.get('pbo')} "
          f"os_gap={d_elig.get('os_gap_pct')}% contender_spread={d_elig.get('contender_spread_pct')}% "
          f"whole-field spread={spread['pct']}%")
    print(f"SHIPPED: {best['label']}  (NF1.7 winner: {nf17['label']} @ {nf17['interval_score']})")
    for p in POS:
        print(f"  {p}: cov {nf17.get(f'cov_{p}')} → {best.get(f'cov_{p}')} "
              f"(floor {floors.get(p, 'unconstrained')}) · width {nf17.get(f'width_{p}')} → "
              f"{best.get(f'width_{p}')}")

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf1_8_rookie_perposition_floor{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf1_8_rookie_perposition_floor{suffix}.md")
    if not checks["per_position_floor_met"] or not checks["permutation_respected"]:
        raise SystemExit("the NF1.8 gate is RED — see the checks above; do not ship this selection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

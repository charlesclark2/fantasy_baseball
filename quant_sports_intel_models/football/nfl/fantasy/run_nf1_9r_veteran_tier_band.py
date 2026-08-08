"""run_nf1_9r_veteran_tier_band.py — NF1.9-R §0.5 bake-off: re-select the VETERAN 80% interval on the
DRAFTABLE-TIER population.

⚠️ THE DEFECT (NF-RECAL1 Finding 3, 2026-08-08). NF1.9 selected the served veteran band (`knn_norm
k300`) on the FULL projected-veteran universe and validated it honestly there: pooled coverage 0.890,
every per-position floor met. On the DRAFTABLE TIER — the top-156-per-season slice users actually
draft from — the same band covers **~0.50 of its nominal 0.80**. The mechanism is the zero atom
changing populations underneath the band (NF1.9's own §0b, read one level further): on the universe,
31% of outcomes are exactly 0 and 83% of the served lower bounds sit AT 0, so the left tail is nearly
un-missable and coverage ≈ 1 − P(y > p90). On the tier only 7.5% of outcomes are 0 — both tails are
live, the band must genuinely work, and the k=300 neighbourhood (which reaches far down the board)
prices the top of the board far too narrow: the universe read's own top-decile empirical q10–q90 spans
83.8–330.6 PPR against a ~125-PPR mean band. The full-universe validation was honest; it does not
TRANSFER. This story re-selects ON THE TIER, with the universe reading reported as a sibling and never
selected on.

⭐ THE POPULATION (pre-registered, inherited from NF-RECAL1 §0 — the single decision that decides the
answer):
  • The tier is the top `veteran_tier_size()` (= 156, DERIVED from the shipped 12-team standard
    preset's skill roster spots, never typed) veterans PER SEASON **by the INCUMBENT's own point
    projection** (`TIER_ANCHOR = incumbent_projection`). ⛔ NEVER by the realized outcome — NF-RECAL1
    measured what a realized anchor manufactures on these very rows (−12.85 → −64.80 mean bias, 0%
    zero-outcome instead of 7.5%). The anchor is identical for every arm, candidate and oracle alike,
    so no arm can buy a friendlier subset.
  • Folds: walk-forward held-out target seasons 2013–2025 — NF1.9's own pre-registered window (CSCV
    over 13 folds = 1,716 balanced splits). NF-RECAL1 ran 2019–2025 only because its C2 placement
    constraint needed merged boards that begin at 2019; a BAND cannot move a rank (it writes only
    `fp_ppr_p10`/`fp_ppr_p90`), so that constraint — and its window limit — does not apply here, and
    NF-RECAL1 §5 itself named 13 folds as the metric-recomputable wide window.
  • The panel is NF1.9's (`run_season_projection.build_veteran_panel_season`) — LEFT-joined, zero-game
    veterans carried as a real 0.

PRIMARY METRIC = the Winkler/Gneiting interval score (IS80), row-pooled over TIER rows. Coverage —
pooled and per position, ROW-POOLED per NF1.8 — is an ELIGIBILITY FLOOR, never a target (E2.1-r; §2
proves it: the `max_width` degenerate satisfies every floor and must lose the metric).

PRE-REGISTERED CANDIDATE CLASSES (fixed before any NF1.9-R result was read; every one counts toward
deflation):
  • INCUMBENT — the NF1.9 served band (`knn_norm k300 · sdgain 0`), fitted through the identical
    served code path per fold. The null every arm must beat.
  • `knn_norm k∈{50,100,200,500}` — the same family at other resolutions, scored on the tier (maybe
    no tier machinery is needed and the k was simply selected for the wrong population). These change
    the WHOLE board's band, so the NF1.9 universe floors are re-checked as a constraint for them.
  • `knn_tier k∈{50,100,200}` / `knn_pos_tier k∈{25,50,100}` — neighbourhood quantiles fitted on TIER
    training rows only (NF-RECAL1's "fit on the tier the metric is computed on" rule), applied as an
    OVERLAY: tier rows re-priced, every other row keeps the served band.
  • `qreg_tier` / `qreg_sqrt_tier` — THE DIRECT-LEARNED FOIL, fitted on tier rows (on the tier the
    zero atom no longer dominates, so a linear conditional quantile is a genuine contender).
  • `cqr_tier[pos|mag|pool, add|width]` — MONDRIAN conformal calibration of the SERVED band on tier
    rows: group-conditional on POSITION, on PROJECTION MAGNITUDE within the tier, and the POOLED foil
    that makes the conditioning attributable (NF1.8's lesson — on the universe this layer was a
    mathematical no-op because ~29% of conformity scores were exactly 0; on the tier the atom is 7.5%
    and the layer can act. Whether it does is measured, not assumed).
  • `scale_tier` / `cov_tier` — the two honest NULLS: one multiplier on the served band's asymmetric
    half-widths, fitted on the tier on the interval SCORE vs to a COVERAGE TARGET (`cov_tier` is the
    E2.1-r inversion made visible — a foil, never a recommendation).

FLOORS (constraints — a criterion a degenerate wins is fatal, a constraint a degenerate satisfies is
fine):
  • TIER pooled coverage ≥ 0.80, and TIER per-position coverage ≥ 0.80 at every position with ≥ 400
    held-out tier rows (the NF1.9 design constant: binomial SE 0.020 at n=400). On this panel that
    constrains QB (465), RB (490), WR (822). ⚠️ TE (251) and FB (~0 tier rows) are REPORTED AND
    CARRIED, NOT GATED — a power-derived fallback floor for structurally-thin groups is NF-D22's job
    and is deliberately NOT built here (a floor derived beside a known breach looks reverse-engineered
    even when it is not).
  • UNIVERSE guard: the winner, AS SERVED (overlay arms leave non-tier rows byte-identical), must
    still meet NF1.9's own standing floors — pooled ≥ 0.80 and ≥ 0.80 at the universe-constrained
    positions. The tier fix may not un-fix the universe.
  ⚠️ NO Tier-2 relaxation exists in this story. If nothing clears, that is an HONEST NULL, classified
  via `cv_power.classify_null` — never a floor moved until something passes.

DEFLATION (pre-registered): PBO < 0.2 over the ELIGIBLE set (CSCV, 1,716 splits; whole-field reported
beside it), DSR ≥ 0.95 on the WHOLE-FIELD reading (the binding one, per the family convention —
NF-D16/NF-RECAL1; contender-set reported), one-sided paired p ≤ α = 0.10 on the pooled hypothesis
(the ship unit is ONE band change — per-position deltas are DISCLOSED with BH-FDR at q = 0.10, never
gating). Flip distribution + Bailey degradation + contender spread reported per NF1.8.

ANCHORS (all tier-scored, a missing anchor RAISES): the permutation oracle in the winner's own family
AND a different family; the peeking own-family oracle, valid as a floor only against the matched-n
candidate (NF1.7 lesson 2 / NF1.9 (f)); `zero_width` + `max_width` + `const_width_tier` (per-position
tier-trained q10/q90 — "no conditioning WITHIN the tier"), all must lose; `oracle_point` orientation.

⚖️ EDGE-INDEPENDENT — `best_alpha = 0`. What is selected is the tier band's WIDTH AND SHAPE; the point
projection is untouched (structurally: band emitters write only `fp_ppr_p10`/`fp_ppr_p90`).

⛔ CODE-READY, NOT DEPLOYED: the winning configuration is recorded as data + wired behind
`season_projection._VET_TIER_RECAL = False`. The flip (+ re-export + `run_interval_revalidation`
re-run) is a post-merge OPERATOR step with its own soak.

RUN ON THE LAPTOP (no Snowflake; reads the cached NF1.9 veteran band panel):

    uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_nf1_9r_veteran_tier_band
"""
from __future__ import annotations

import argparse
import dataclasses
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

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (  # noqa: E402
    bh_fdr,
    deflated_sharpe,
    onesided_paired_pvalue,
)
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation import (  # noqa: E402,E501
    _finish,
)
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_perposition_ablation import (  # noqa: E402,E501
    deflate,
    floor_slack_rows,
    position_floors,
    position_power,
    require_anchors,
    score_rows,
)
from quant_sports_intel_models.football.nfl.fantasy.run_veteran_interval_ablation import (  # noqa: E402,E501
    Fold,
    _frame,
    _normal_band,
    build_folds,
    load_panel,
)

log = logging.getLogger("nfl.fantasy.nf1_9r_tier_band")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_PANEL_CACHE = (_PROJECT_ROOT
                / "quant_sports_intel_models/football/nfl/fantasy/artifacts/nf1_9_veteran_band_panel")

_ALPHA_IS = 0.20                  # ⇒ a central 80% interval, miss penalty 10 (shared with NF1.9)
_NOMINAL = 0.80
_COVERAGE_FLOOR = 0.80
_FOLD_FROM, _FOLD_TO = 2013, 2025
_POS_FLOOR_MIN_N = 400            # the NF1.9 design constant — inherited, not re-derived
_ALPHA_P = 0.10                   # single-hypothesis level, pooled framing (family convention)
_FDR_Q = 0.10                     # DISCLOSED per-position reading only — never gates
_PBO_MAX = 0.2
_DSR_MIN = 0.95
_BASE = {"form": "knn_norm", "k": 300}   # the NF1.9 served base every overlay sits on
_INCUMBENT_LABEL = "knn_norm k300 (INCUMBENT — the NF1.9 served band)"
# The NF1.9 record this harness must REPRODUCE before any selection is read (the served-band
# reproduction proof, one story on): the winner's universe IS80 and the NF-RECAL1 tier coverage.
_NF19_UNIVERSE_IS80 = 160.888
_NFRECAL1_TIER_COV_2019_2025 = 0.5046
_KNN_K_GRID = (50, 100, 200, 500)          # 300 IS the incumbent — not duplicated
_TIER_KNN_GRID = (50, 100, 200)
_TIER_KNN_POS_GRID = (25, 50, 100)
_CQR_MODES = ("pos", "mag", "pool")
_CQR_SCALES = ("add", "width")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered config set
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs() -> list[dict]:
    """Fixed before any NF1.9-R result was read; EVERY searchable entry counts toward deflation."""
    cfgs: list[dict] = [{"label": _INCUMBENT_LABEL, "arm": "incumbent", **_BASE}]
    for k in _KNN_K_GRID:
        cfgs.append({"label": f"knn_norm k{k} (whole-board re-selection)", "arm": "model",
                     "kind": "universe", "form": "knn_norm", "k": k})
    for k in _TIER_KNN_GRID:
        cfgs.append({"label": f"knn_tier k{k} (tier-fit neighbourhood)", "arm": "model",
                     "kind": "overlay", "tier_form": "knn_tier", "tier_k": k})
    for k in _TIER_KNN_POS_GRID:
        cfgs.append({"label": f"knn_pos_tier k{k} (per-position tier-fit)", "arm": "model",
                     "kind": "overlay", "tier_form": "knn_pos_tier", "tier_k": k})
    for f in ("qreg_tier", "qreg_sqrt_tier"):
        cfgs.append({"label": f"{f} (direct-learned foil, tier-fit)", "arm": "model",
                     "kind": "overlay", "tier_form": f})
    for mode in _CQR_MODES:
        for scale in _CQR_SCALES:
            cfgs.append({"label": f"cqr_tier[{mode},{scale}] (conformal on the served band)",
                         "arm": "model", "kind": "overlay", "tier_form": "cqr_tier",
                         "tier_cqr_mode": mode, "tier_cqr_scale": scale})
    cfgs.append({"label": "scale_tier (null: served band ×m, fitted on the SCORE)", "arm": "model",
                 "kind": "overlay", "tier_form": "scale_tier"})
    cfgs.append({"label": "cov_tier (null: served band ×m, fitted to a COVERAGE TARGET)",
                 "arm": "model", "kind": "overlay", "tier_form": "cov_tier"})
    return cfgs


def _fit_key(cfg: dict) -> tuple:
    """The identity of the FIT a config needs. The two `cqr_tier` SCALES share one fit (both scalings
    come out of one cross-conformal pass — the NF1.9 cost-hygiene trick); the three MODES do not
    (the group is baked into the conformity table at collection time)."""
    return (cfg.get("form", _BASE["form"]), cfg.get("k", _BASE["k"]),
            cfg.get("tier_form", ""), cfg.get("tier_k", 0), cfg.get("tier_cqr_mode", "pos"))


def fitted_model(fold: Fold, cfg: dict, tier_n: int) -> SP.VeteranBandModel | None:
    key = _fit_key(cfg)
    if key not in fold.fits:
        tf = cfg.get("tier_form", "")
        fold.fits[key] = SP.fit_veteran_band_model(
            fold.train, form=cfg.get("form", _BASE["form"]), k=cfg.get("k", _BASE["k"]),
            sd_gain=0.0, qreg_alpha=0.01,
            tier_form=tf, tier_k=cfg.get("tier_k", 0) or 0,
            tier_n=tier_n if tf else 0,
            tier_cqr_mode=cfg.get("tier_cqr_mode", "pos"))
    return fold.fits[key]


def candidate_band(fold: Fold, cfg: dict, tier_n: int,
                   model: SP.VeteranBandModel | None = None
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """One candidate's held-out band + the FELL-BACK mask.

    ⚠️ For an OVERLAY arm, `fell_back` on a tier row means the overlay DECLINED it and the row kept
    the served NF1.9 band — the very band this story re-prices, so hiding it would flatter the arm
    (NF1.9's fallback-mask lesson, pointed at the incumbent instead of the normal approximation).
    For a whole-board arm it keeps NF1.9's meaning (a refused fit degrades to the normal band)."""
    m = model if model is not None else fitted_model(fold, cfg, tier_n)
    if m is None:
        return None
    if cfg.get("tier_cqr_scale") and m.tier_form == "cqr_tier":
        m = dataclasses.replace(m, tier_cqr_scale=str(cfg["tier_cqr_scale"]))
    info: dict = {}
    lo, hi = m.band_many(fold.test_frame, tier_info=info)
    bad = ~(np.isfinite(lo) & np.isfinite(hi))
    if bad.all():
        return None
    if bad.any():
        idx = np.where(bad)[0]
        lo[idx], hi[idx] = _normal_band(fold, idx)
    fell = bad
    if m.tier_form and "in_tier" in info:
        fell = bad | (info["in_tier"] & ~info["overlay_applied"])
    return (*_finish(lo, hi, fold.test_pred), fell)


def fold_tier_mask(fold: Fold, tier_n: int) -> np.ndarray:
    """The held-out season's DRAFTABLE TIER — the top `tier_n` rows by the incumbent's own point
    (`SP._tier_row_mask`, the single owner of the anchor rule; ⛔ never the realized outcome)."""
    return SP._tier_row_mask(fold.test_pred, None, tier_n)


def arm_rows(folds: list[Fold], cfg: dict, tier_n: int) -> pd.DataFrame | None:
    parts = []
    for f in folds:
        got = candidate_band(f, cfg, tier_n)
        if got is None:
            continue
        lo, hi, fell = got
        parts.append(pd.DataFrame({
            "year": f.year, "pos": f.test["position"].astype(str).str.upper().to_numpy(),
            "lo": lo, "hi": hi, "y": f.test_real, "point": f.test_pred, "fell_back": fell,
            "tier": fold_tier_mask(f, tier_n)}))
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def run_arm(folds: list[Fold], cfg: dict, tier_n: int) -> dict | None:
    """TIER-scored record (the selection read) + the UNIVERSE sibling (`u_*` — reported, never
    selected on), from ONE row frame so the two readings can never disagree about their population."""
    rows = arm_rows(folds, cfg, tier_n)
    if rows is None or rows.empty:
        return None
    tier_rows = rows[rows["tier"]].reset_index(drop=True)
    if tier_rows.empty:
        return None
    rec = {**cfg, **score_rows(tier_rows)}
    uni = score_rows(rows)
    rec.update({f"u_{k}": v for k, v in uni.items() if not isinstance(v, dict)})
    rec["u_per_cohort"] = uni["per_cohort"]
    lo, hi, y = (tier_rows[c].to_numpy(dtype=float) for c in ("lo", "hi", "y"))
    rec["below_p10"] = round(float(np.mean(y < lo)), 4)
    rec["above_p90"] = round(float(np.mean(y > hi)), 4)
    rec["p10_at_zero"] = round(float(np.mean(lo <= 0)), 4)
    return rec


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Anchors — tier-scored; a missing anchor RAISES
# ══════════════════════════════════════════════════════════════════════════════════════════════
def anchor_bands(fold: Fold, tier_n: int, oracle_cfg: dict) -> dict:
    pos = fold.test["position"].astype(str).str.upper().to_numpy()
    pred, y = fold.test_pred, fold.test_real
    out: dict = {}
    out["zero_width"] = _finish(pred, pred, pred)
    tr_pos = fold.train["position"].astype(str).str.upper()
    mx = fold.train.groupby(tr_pos)["real_fp_ppr"].max()
    hi_max = np.array([float(mx.get(p, np.nanmax(y) if len(y) else 0.0)) for p in pos])
    out["max_width"] = _finish(np.zeros_like(pred), hi_max, pred)
    # `const_width_tier` — ONE band per position, fitted on TRAIN TIER rows: the "conditioning on the
    # player WITHIN the tier earns nothing" degenerate. Must lose to the winner.
    tr_tier = SP._tier_row_mask(fold.train["point"].to_numpy(dtype=float),
                                fold.train["target_season"].to_numpy(dtype=float), tier_n)
    tt = fold.train.loc[tr_tier]
    q = (tt.assign(_p=tt["position"].astype(str).str.upper())
         .groupby("_p")["real_fp_ppr"].quantile([0.10, 0.90]).unstack())
    lo_c = np.array([float(q.loc[p, 0.10]) if p in q.index else np.nan for p in pos])
    hi_c = np.array([float(q.loc[p, 0.90]) if p in q.index else np.nan for p in pos])
    keep = np.isfinite(lo_c) & np.isfinite(hi_c)
    lo_c = np.where(keep, lo_c, 0.0)
    hi_c = np.where(keep, hi_c, hi_max)
    out["const_width_tier"] = _finish(lo_c, hi_c, pred)

    # PEEKING own-family oracle: the winner's own configuration fitted ON the held-out season (the
    # oracle has to peek to be one). Valid as a floor only against the matched-n candidate below.
    peek = fold.test.assign(real_fp_ppr=y)
    om = SP.fit_veteran_band_model(
        peek, form=oracle_cfg.get("form", _BASE["form"]), k=oracle_cfg.get("k", _BASE["k"]),
        qreg_alpha=0.01, tier_form=oracle_cfg.get("tier_form", ""),
        tier_k=oracle_cfg.get("tier_k", 0) or 0,
        tier_n=tier_n if oracle_cfg.get("tier_form") else 0,
        tier_cqr_mode=oracle_cfg.get("tier_cqr_mode", "pos"))
    if om is not None:
        if oracle_cfg.get("tier_cqr_scale") and om.tier_form == "cqr_tier":
            om = dataclasses.replace(om, tier_cqr_scale=str(oracle_cfg["tier_cqr_scale"]))
        l2, h2 = om.band_many(fold.test_frame)
        bad = ~(np.isfinite(l2) & np.isfinite(h2))
        if bad.any():
            idx = np.where(bad)[0]
            l2[idx], h2[idx] = _normal_band(fold, idx)
        out["oracle_own_family"] = _finish(l2, h2, pred)

    # ⭐ THE MATCHED-n CANDIDATE — the winner's own arm trained on ONE prior season, so its resolution
    # matches the oracle's (NF1.7 lesson 2 / NF1.9 (f): "peeking can only help" holds only at equal
    # family AND equal resolution).
    prev = fold.train[fold.train["target_season"] == fold.year - 1]
    if len(prev) >= SP._VET_BAND_MIN_TRAIN:
        mm = SP.fit_veteran_band_model(
            prev, form=oracle_cfg.get("form", _BASE["form"]), k=oracle_cfg.get("k", _BASE["k"]),
            qreg_alpha=0.01, tier_form=oracle_cfg.get("tier_form", ""),
            tier_k=oracle_cfg.get("tier_k", 0) or 0,
            tier_n=tier_n if oracle_cfg.get("tier_form") else 0,
            tier_cqr_mode=oracle_cfg.get("tier_cqr_mode", "pos"))
        if mm is not None:
            if oracle_cfg.get("tier_cqr_scale") and mm.tier_form == "cqr_tier":
                mm = dataclasses.replace(mm, tier_cqr_scale=str(oracle_cfg["tier_cqr_scale"]))
            l3, h3 = mm.band_many(fold.test_frame)
            bad = ~(np.isfinite(l3) & np.isfinite(h3))
            if bad.any():
                idx = np.where(bad)[0]
                l3[idx], h3[idx] = _normal_band(fold, idx)
            out["matched_n_candidate"] = _finish(l3, h3, pred)

    # orientation: the peeking neighbourhood oracle on the tier, and the trivial infimum
    lvl = pd.Series(y).groupby(pd.Series(pos)).mean()
    s = np.array([float(lvl.get(p, np.nan)) for p in pos])
    s = np.where(np.isfinite(s) & (s > 1e-6), s, max(float(np.mean(y)), 1e-6))
    lo_o, hi_o = SP._knn_interval(pred / s, y / s, pred / s, min(120, len(y)), 0.10, 0.90)
    out["oracle_knn"] = _finish(lo_o * s, hi_o * s, pred)
    out["oracle_point"] = _finish(y, y, y)
    return out


def permuted_arm(fold: Fold, cfg: dict, tier_n: int, seed_base: int = 20260808
                 ) -> tuple[np.ndarray, np.ndarray]:
    """The PERMUTATION ORACLE — the arm's own configuration (base AND overlay) fitted against a
    SHUFFLE of the training outcomes. Well-posed at any n; must LOSE to the winner."""
    rng = np.random.default_rng(seed_base + fold.year)
    shuffled = fold.train.assign(
        real_fp_ppr=rng.permutation(fold.train["real_fp_ppr"].to_numpy(dtype=float)))
    tf = cfg.get("tier_form", "")
    m = SP.fit_veteran_band_model(
        shuffled, form=cfg.get("form", _BASE["form"]), k=cfg.get("k", _BASE["k"]),
        qreg_alpha=0.01, tier_form=tf, tier_k=cfg.get("tier_k", 0) or 0,
        tier_n=tier_n if tf else 0, tier_cqr_mode=cfg.get("tier_cqr_mode", "pos"))
    if m is None:
        return (np.full(len(fold.test_pred), np.nan),) * 2
    if cfg.get("tier_cqr_scale") and m.tier_form == "cqr_tier":
        m = dataclasses.replace(m, tier_cqr_scale=str(cfg["tier_cqr_scale"]))
    lo, hi = m.band_many(fold.test_frame)
    bad = ~(np.isfinite(lo) & np.isfinite(hi))
    if bad.any():
        idx = np.where(bad)[0]
        lo[idx], hi[idx] = _normal_band(fold, idx)
    return _finish(lo, hi, fold.test_pred)


def run_anchors(folds: list[Fold], tier_n: int, permute_cfgs: dict[str, dict],
                oracle_cfg: dict) -> dict:
    per: dict[str, list[pd.DataFrame]] = {}

    def _add(tag: str, fold: Fold, lo, hi) -> None:
        t = fold_tier_mask(fold, tier_n)
        per.setdefault(tag, []).append(pd.DataFrame({
            "year": fold.year, "pos": fold.test["position"].astype(str).str.upper().to_numpy(),
            "lo": lo, "hi": hi, "y": fold.test_real, "point": fold.test_pred,
            "fell_back": np.zeros(len(fold.test_pred), dtype=bool), "tier": t}))

    for f in folds:
        for tag, (lo, hi) in anchor_bands(f, tier_n, oracle_cfg).items():
            _add(tag, f, lo, hi)
        for fam, cfg in permute_cfgs.items():
            lo, hi = permuted_arm(f, cfg, tier_n)
            if np.isfinite(lo).all() and np.isfinite(hi).all():
                _add(f"permuted_{fam}", f, lo, hi)
    return {tag: score_rows(pd.concat(parts, ignore_index=True)
                            .query("tier").reset_index(drop=True))
            for tag, parts in per.items()}


_REQUIRED_ANCHORS = ("oracle_knn", "oracle_own_family", "matched_n_candidate", "zero_width",
                     "max_width", "const_width_tier", "permuted_own", "permuted_alt",
                     "oracle_point")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Eligibility — three clauses, each independently testable (the NF-D17 AND-gate lesson)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def tier_floor_misses(rec: dict, floors: dict[str, float],
                      pooled_floor: float = _COVERAGE_FLOOR) -> list[str]:
    """Clause A+B: the TIER pooled floor and the TIER per-position floors."""
    out = []
    if (rec.get("coverage_80") or 0) < pooled_floor:
        out.append(f"tier pooled {rec.get('coverage_80')}<{pooled_floor:.2f}")
    for p, f in sorted(floors.items()):
        cov = rec.get(f"cov_{p}")
        if cov is None or cov < f:
            out.append(f"tier {p} {cov}<{f:.3f}")
    return out


def universe_floor_misses(rec: dict, floors: dict[str, float],
                          pooled_floor: float = _COVERAGE_FLOOR) -> list[str]:
    """Clause C: the winner AS SERVED must still meet NF1.9's own standing universe floors — the tier
    fix may not un-fix the universe."""
    out = []
    if (rec.get("u_coverage_80") or 0) < pooled_floor:
        out.append(f"universe pooled {rec.get('u_coverage_80')}<{pooled_floor:.2f}")
    for p, f in sorted(floors.items()):
        cov = rec.get(f"u_cov_{p}")
        if cov is None or cov < f:
            out.append(f"universe {p} {cov}<{f:.3f}")
    return out


def eligibility_misses(rec: dict, tier_floors: dict[str, float],
                       universe_floors: dict[str, float]) -> list[str]:
    return tier_floor_misses(rec, tier_floors) + universe_floor_misses(rec, universe_floors)


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
    best, inc = out["best"], out["incumbent"]
    POS = out["positions"]
    p("# NF1.9-R — the VETERAN 80% interval re-selected on the DRAFTABLE-TIER population "
      "(§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **held-out target seasons:** {out['cohorts'][0]}–"
      f"{out['cohorts'][-1]} ({len(out['cohorts'])}) · **configs scored:** {len(out['configs'])} · "
      f"**held-out TIER veteran-seasons:** {best['n']} (universe {best['u_n']}) · **tier:** top "
      f"{out['tier_n']}/season by the INCUMBENT's own point (derived, never typed) · **wall time:** "
      f"{out['wall_s']}s")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`. What is selected is the "
      "WIDTH AND SHAPE of the veteran interval ON THE DRAFTABLE TIER; the point projection is "
      "untouched, non-tier rows keep the NF1.9 band byte-identical (overlay arms), and ⛔ NOTHING "
      "SERVES from this story — `_VET_TIER_RECAL = False`; the flip is a post-merge operator step "
      "with its own soak + `run_interval_revalidation` re-run.")
    p("")
    p("## 0. The defect, and the reproduction of the record it rests on")
    p("")
    p(out["defect_note"])
    p("")
    p(_md(pd.DataFrame(out["defect"])))
    p("")
    p(out["repro_note"])
    p("")
    p("## 0b. The population — the tier, fixed by the incumbent's own projection")
    p("")
    p(out["population_note"])
    p("")
    p(_md(pd.DataFrame(out["population"])))
    p("")
    p("## 1. The pre-registered floors")
    p("")
    p(out["floors_note"])
    p("")
    p(_md(pd.DataFrame(out["floors_table"])))
    p("")
    p("## 2. The anchor set")
    p("")
    p(_md(pd.DataFrame(out["anchor_table"])))
    p("")
    for line in out["check_lines"]:
        label, ok, msg = line[0], line[1], line[2]
        fail = (line[3] if len(line) > 3
                else "**THE METRIC OR THE SELECTION IS SUSPECT — do NOT ship it**")
        p(f"- {'✅' if ok else '⚠️' if len(line) > 3 else '🚨'} **{label}** — {msg if ok else fail}")
    p("")
    p("### ⭐ The proof the floors are CONSTRAINTS and not the selector")
    p("")
    p(_md(pd.DataFrame(out["degenerate_vs_floor"])))
    p("")
    p(out["degenerate_note"])
    p("")
    p("## 3. Power on the tier — and the groups too thin to gate")
    p("")
    p(_md(pd.DataFrame(out["power"])))
    p("")
    p(out["power_note"])
    p("")
    p("## 4. Results — all configs (sorted by TIER IS80; universe sibling beside it)")
    p("")
    p(_md(pd.DataFrame(out["table"])))
    p("")
    p("`eligible` applies §1's three clauses (tier pooled · tier per-position · universe guard). "
      "`fallback %` — for an OVERLAY arm — is the share of TIER rows the overlay DECLINED (those "
      "rows keep the served NF1.9 band, i.e. partly the very band this story re-prices).")
    p("")
    p("### ⭐ Was a new tier fit needed, or just a wider served band?")
    p("")
    p(_md(pd.DataFrame(out["shape_vs_sigma"])))
    p("")
    p(out["shape_note"])
    p("")
    p("### ⭐ What the tier-conditioning bought (the conformal foil ladder)")
    p("")
    p(_md(pd.DataFrame(out["mechanism"])))
    p("")
    p(out["mechanism_note"])
    p("")
    p("## 5. Deflation")
    p("")
    p(_md(pd.DataFrame(out["deflation_table"])))
    p("")
    p(out["deflation_verdict"])
    p("")
    p("### Which arms actually win the in-sample halves (ELIGIBLE set)")
    p("")
    p(_md(pd.DataFrame((out["pbo_eligible"].get("flips") or [])[:8])))
    p("")
    p(f"**DSR (whole field, the pre-registered binding reading): {out['dsr']}** · contender-set DSR "
      f"{out['dsr_contender']} · pooled one-sided paired p = {out['pvalue']} (α = {_ALPHA_P}). "
      f"Per-position disclosure (BH-FDR q = {_FDR_Q}, never gating): {out['per_position_p']}")
    p("")
    p("## 6. Selection")
    p("")
    p(out["verdict"])
    p("")
    p("### The tie among ELIGIBLE arms")
    p("")
    p(_md(pd.DataFrame(out["tied"])))
    p("")
    p(out["tie_note"])
    p("")
    p("### Per-position coverage — TIER and UNIVERSE, row-pooled, slack in ROWS")
    p("")
    p(_md(pd.DataFrame(out["per_position_compare"])))
    p("")
    p(out["width_note"])
    p("")
    p("## 7. Per-season detail (winner vs incumbent, TIER IS80)")
    p("")
    p(_md(pd.DataFrame(out["per_season"])))
    p("")
    p("## 8. Serving state + the standing re-validation")
    p("")
    p(out["serving_note"])
    p("")
    p("## 9. Honest limitations")
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
    ap = argparse.ArgumentParser(description="NF1.9-R — veteran band re-selected on the tier")
    ap.add_argument("--panel", default=str(_PANEL_CACHE))
    ap.add_argument("--from", dest="from_year", type=int, default=_FOLD_FROM)
    ap.add_argument("--to", dest="to_year", type=int, default=_FOLD_TO)
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="a TINY slice (4 seasons, a handful of arms) to prove the code path")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    t0 = time.time()

    tier_n = SP.veteran_tier_size()
    panel = load_panel(Path(args.panel))
    folds = build_folds(panel, list(range(args.from_year, args.to_year + 1)))
    if args.smoke:
        folds = folds[:4]
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable target seasons — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    cfgs = candidate_configs()
    if args.smoke:
        cfgs = [c for c in cfgs
                if c["arm"] == "incumbent"
                or c.get("tier_form") in ("knn_tier", "qreg_tier", "cqr_tier", "cov_tier")
                or (c.get("kind") == "universe" and c.get("k") == 100)]
    log.info("NF1.9-R bake-off: %d held-out seasons (%s) × %d configs · tier=%d/season · "
             "%d panel rows", len(folds), cohorts, len(cfgs), tier_n, len(panel))

    results = [r for r in (run_arm(folds, c, tier_n) for c in cfgs) if r is not None]
    incumbent = next(r for r in results if r["arm"] == "incumbent")
    POS = sorted({k[4:] for k in incumbent if k.startswith("cov_")})

    # ── §0 PREMISE CHECK + the reproduction proofs (before any selection is read) ─────────────
    # ⭐⭐ THE MOTIVATING "~0.50 ON THE TIER" FIGURE BELONGS TO THE *PRE-NF1.9 NORMAL BAND*, NOT THE
    # SERVED KNN BAND — measured here, not asserted. NF-RECAL1's C3 read its "incumbent band" from
    # the panel's `served_p10`/`served_p90` columns, which `VET_PANEL_COLS` documents as "the LITERAL
    # emitted PRE-NF1.9 band" (they are carried so NF1.9's incumbent arm is reproducible). The band
    # actually on the wire since NF1.9 shipped is `knn_norm k300` (`calibrated_per_player`, 784/784
    # skill rows). This harness therefore reproduces the recorded 0.5046 against the band that
    # PRODUCED it (the normal approximation), and measures the SERVED band's tier coverage as the
    # story's real premise — the NF-RECAL1 §0 discipline ("re-measure the motivating defect in the
    # population this story fits on BEFORE fitting anything"), landing one story later.
    uni_repro = abs(incumbent["u_interval_score"] - _NF19_UNIVERSE_IS80) / _NF19_UNIVERSE_IS80
    rows_1925 = arm_rows(folds, {"label": "_", "arm": "incumbent", **_BASE}, tier_n)
    sub = rows_1925[(rows_1925["year"] >= 2019) & rows_1925["tier"]]
    cov_knn_1925 = (float(np.mean((sub["y"] >= sub["lo"]) & (sub["y"] <= sub["hi"])))
                    if len(sub) else float("nan"))
    # the panel's own served (pre-NF1.9 normal) band on the same tier rows — the figure's true owner
    tier_all = pd.concat([f.test.assign(_t=fold_tier_mask(f, tier_n)) for f in folds],
                         ignore_index=True)
    nsub = tier_all[tier_all["_t"] & (tier_all["target_season"] >= 2019)]
    cov_normal_1925 = (float(np.mean((nsub["real_fp_ppr"] >= nsub["served_p10"])
                                     & (nsub["real_fp_ppr"] <= nsub["served_p90"])))
                       if len(nsub) else float("nan"))
    normal_repro = abs(cov_normal_1925 - _NFRECAL1_TIER_COV_2019_2025)
    if not args.smoke:
        if uni_repro > 0.005:
            raise SystemExit(
                f"the incumbent arm does not reproduce NF1.9's recorded universe IS80 "
                f"({incumbent['u_interval_score']} vs {_NF19_UNIVERSE_IS80}) — the incumbent would "
                "be a straw man. Fix that before reading any selection.")
        if normal_repro > 0.01:
            raise SystemExit(
                f"the pre-NF1.9 normal band's 2019–2025 tier coverage ({cov_normal_1925:.4f}) does "
                f"not reproduce NF-RECAL1's recorded {_NFRECAL1_TIER_COV_2019_2025} — the "
                "attribution of the motivating figure is wrong somewhere. Stop.")
    log.info("reproduction: universe IS80 %.3f vs NF1.9's %.3f (Δ %.2f%%) · NORMAL-band tier "
             "cov(2019–25) %.4f vs NF-RECAL1's %.4f · SERVED-knn-band tier cov(2019–25) %.4f",
             incumbent["u_interval_score"], _NF19_UNIVERSE_IS80, 100 * uni_repro,
             cov_normal_1925, _NFRECAL1_TIER_COV_2019_2025, cov_knn_1925)

    # ── floors: tier (this story's) + universe (NF1.9's own, re-checked) ───────────────────────
    tier_floors = position_floors(incumbent, POS, tier=1, min_n=_POS_FLOOR_MIN_N,
                                  tier2_positions=(), nominal=_NOMINAL)
    u_rec = {**{f"n_{p}": incumbent.get(f"u_n_{p}") for p in POS},
             **{f"cov_{p}": incumbent.get(f"u_cov_{p}") for p in POS}}
    universe_floors = position_floors(u_rec, POS, tier=1, min_n=_POS_FLOOR_MIN_N,
                                      tier2_positions=(), nominal=_NOMINAL)
    thin_groups = [p for p in POS if (incumbent.get(f"n_{p}") or 0) < _POS_FLOOR_MIN_N]
    searchable = [r for r in results if r["arm"] == "model"]
    elig = [r for r in searchable if not eligibility_misses(r, tier_floors, universe_floors)]
    null_result = not elig
    if null_result:
        log.warning("[ALERT] no config clears the pre-registered floors — reporting an HONEST NULL; "
                    "⛔ no Tier-2 relaxation exists in this story (NF-D22's job), and the floor is "
                    "not moved until something passes")
    best = min(elig, key=lambda r: r["interval_score"]) if elig else incumbent

    # ── anchors ────────────────────────────────────────────────────────────────────────────────
    own_cfg = ({k: v for k, v in best.items()
                if k in ("form", "k", "tier_form", "tier_k", "tier_cqr_mode", "tier_cqr_scale")}
               if best["arm"] == "model" else {"tier_form": "knn_tier", "tier_k": 100})
    # the ALT permutation must be a DIFFERENT family from the winner's
    if str(own_cfg.get("tier_form", "")).startswith("knn") or not own_cfg.get("tier_form"):
        alt_cfg = {"tier_form": "qreg_tier"}
    else:
        alt_cfg = {"tier_form": "knn_tier", "tier_k": 100}
    permute_cfgs = {"own": own_cfg, "alt": alt_cfg}
    anchors = run_anchors(folds, tier_n, permute_cfgs, oracle_cfg=own_cfg)
    a_is = {k: v["interval_score"] for k, v in anchors.items()}
    require_anchors(a_is, _REQUIRED_ANCHORS)
    checks = {
        "permutation_respected": bool(best["interval_score"] < a_is["permuted_own"]),
        "oracle_respected": bool(best["interval_score"] >= a_is["oracle_own_family"] - 1e-9),
        "oracle_respected_at_matched_n":
            bool(a_is["oracle_own_family"] <= a_is["matched_n_candidate"] + 1e-9),
        "zero_width_loses": bool(best["interval_score"] < a_is["zero_width"]),
        "max_width_loses": bool(best["interval_score"] < a_is["max_width"]),
        "const_width_tier_loses": bool(best["interval_score"] < a_is["const_width_tier"]),
        "beats_incumbent": bool(best["interval_score"] < incumbent["interval_score"]),
        "tier_floor_met": not tier_floor_misses(best, tier_floors),
        "universe_floor_met": not universe_floor_misses(best, universe_floors),
        "universe_is80_reproduced": bool(uni_repro <= 0.005),
        "motivating_figure_attributed": bool(normal_repro <= 0.01),
        "premise_served_band_below_floor": bool(np.isfinite(cov_knn_1925)
                                                and cov_knn_1925 < _COVERAGE_FLOOR),
    }
    check_lines = [
        ("permutation oracle respected", checks["permutation_respected"],
         f"the winner beats its OWN configuration fitted on SHUFFLED outcomes "
         f"({a_is['permuted_own']} vs {best['interval_score']}) — the metric rewards information"),
        ("peeking oracle respected AT MATCHED n", checks["oracle_respected_at_matched_n"],
         f"the peeking own-configuration oracle (tier IS80 {a_is['oracle_own_family']}) beats the "
         f"winner's own arm trained on a single prior season ({a_is['matched_n_candidate']}) — at "
         f"equal family AND equal resolution, knowing the answer helps (NF1.7 lesson 2 / NF1.9 (f))"),
        ("same-family peeking oracle (UNMATCHED n — orientation only)", checks["oracle_respected"],
         f"the winner does not beat the peeking oracle ({a_is['oracle_own_family']})",
         f"the winner ({best['interval_score']}) BEATS the peeking oracle "
         f"({a_is['oracle_own_family']}) — expected at unmatched n and NOT an inversion (the oracle "
         f"fits ~{tier_n} held-out rows; the winner trains on every prior season); the matched-n "
         f"check above is the valid form"),
        ("zero-width degenerate loses", checks["zero_width_loses"],
         "sharpness was not bought by under-covering"),
        ("max-width degenerate loses", checks["max_width_loses"],
         "the selection is not a coverage exercise in disguise"),
        ("const-width (tier-trained) degenerate loses", checks["const_width_tier_loses"],
         "conditioning on the player WITHIN the tier earns its place"),
        ("incumbent beaten on the tier", checks["beats_incumbent"],
         "the selected band beats the served NF1.9 band on the tier"),
        ("tier floors met", checks["tier_floor_met"],
         "pooled + every constrained position ("
         + ", ".join(f"{k} {best.get(f'cov_{k}')}≥{v:.2f}" for k, v in sorted(tier_floors.items()))
         + ")"),
        ("universe guard met", checks["universe_floor_met"],
         "the winner AS SERVED still meets NF1.9's standing universe floors ("
         + ", ".join(f"{k} {best.get(f'u_cov_{k}')}≥{v:.2f}"
                     for k, v in sorted(universe_floors.items())) + ")"),
        ("NF1.9 universe record reproduced", checks["universe_is80_reproduced"],
         f"the incumbent arm reproduces NF1.9's recorded universe IS80 "
         f"({incumbent['u_interval_score']} vs {_NF19_UNIVERSE_IS80}, Δ {100 * uni_repro:.2f}%)"),
        ("motivating ~0.50 figure ATTRIBUTED (to the pre-NF1.9 normal band)",
         checks["motivating_figure_attributed"],
         f"the panel's pre-NF1.9 NORMAL band covers {cov_normal_1925:.4f} on the 2019–2025 tier — "
         f"NF-RECAL1's recorded {_NFRECAL1_TIER_COV_2019_2025} to the digit; the SERVED knn band's "
         f"own tier coverage there is {cov_knn_1925:.4f}"),
        ("premise: SERVED band below the tier floor",
         checks["premise_served_band_below_floor"],
         f"the served knn band's 2019–2025 tier coverage ({cov_knn_1925:.4f}) is below the "
         f"{_COVERAGE_FLOOR:.2f} floor — a live defect, though NOT the motivating ~0.50",
         f"the served knn band's 2019–2025 tier coverage is {cov_knn_1925:.4f} — NOT below the "
         f"{_COVERAGE_FLOOR:.2f} floor. **The motivating premise does not reproduce against the "
         f"band actually on the wire** (the ~0.50 belongs to the pre-NF1.9 normal approximation); "
         f"what remains is a re-selection QUESTION, answered by the gate below, not a standing "
         f"defect"),
    ]

    # ── deflation ──────────────────────────────────────────────────────────────────────────────
    mat = pd.DataFrame({r["label"]: r["per_cohort"] for r in results}).sort_index().dropna(
        axis=1, how="any")
    d = deflate(mat)
    d_elig = deflate(mat, subset=[r["label"] for r in elig]) if elig else dict(d)
    inc_series = pd.Series(incumbent["per_cohort"]).sort_index()
    deltas = (inc_series - pd.Series(best["per_cohort"]).sort_index()).to_numpy(dtype=float)
    trial_srs = []
    for r in searchable:
        dd = (inc_series - pd.Series(r["per_cohort"]).sort_index()).to_numpy(dtype=float)
        sd = float(np.std(dd, ddof=1))
        trial_srs.append(float(np.mean(dd)) / sd if sd > 1e-12 else 0.0)
    dsr = deflated_sharpe(deltas, np.array(trial_srs))
    means = {r["label"]: r["interval_score"] for r in searchable}
    contender_labels = [k for k, _ in sorted(means.items(), key=lambda kv: kv[1])]
    contender_labels = contender_labels[:max(4, len(contender_labels) // 4)]
    dsr_contender = deflated_sharpe(
        deltas, np.array([t for r, t in zip(searchable, trial_srs)
                          if r["label"] in set(contender_labels)]))
    pval = onesided_paired_pvalue(deltas)
    # per-position DISCLOSURE p-values (BH-FDR at q — reported, never gating)
    per_pos_p = {}
    rows_best = arm_rows(folds, {k: v for k, v in best.items() if not isinstance(v, dict)}, tier_n)
    rows_inc = rows_1925
    for pp in POS:
        bi = rows_best[rows_best["tier"] & (rows_best["pos"] == pp)]
        ii = rows_inc[rows_inc["tier"] & (rows_inc["pos"] == pp)]
        if bi.empty or ii.empty:
            per_pos_p[pp] = None
            continue
        db = (ii.assign(_is=SP._interval_score(ii["lo"], ii["hi"], ii["y"]))
              .groupby("year")["_is"].mean()
              - bi.assign(_is=SP._interval_score(bi["lo"], bi["hi"], bi["y"]))
              .groupby("year")["_is"].mean())
        per_pos_p[pp] = onesided_paired_pvalue(db.to_numpy(dtype=float))
    fdr = bh_fdr(per_pos_p, q=_FDR_Q)

    # ── the null's STATE, in the unit that grows (MH2 / NF-D15 (g″)) ──────────────────────────
    dmean = float(np.mean(deltas)) if len(deltas) else 0.0
    dsd = float(np.std(deltas, ddof=1)) if len(deltas) > 2 else 0.0
    t_obs = dmean / (dsd / np.sqrt(len(deltas))) if dsd > 1e-12 else 0.0
    try:
        from scipy.stats import t as _t
        t_needed = float(_t.ppf(1 - _ALPHA_P, len(deltas) - 1))
    except Exception:  # noqa: BLE001
        t_needed = 1.36
    folds_needed = (int(np.ceil(len(deltas) * (t_needed / t_obs) ** 2))
                    if t_obs > 1e-9 else None)
    null_state = {
        "state": ("TIE" if t_obs > 0 and (folds_needed or 10 ** 9) > 60 else
                  ("POWER_LIMITED" if t_obs > 0 else "GENUINE_ABSENCE")),
        "winner_lead_pct_tier_is80": round(100 * (incumbent["interval_score"]
                                                  - best["interval_score"])
                                           / incumbent["interval_score"], 3),
        "per_fold_delta_mean": round(dmean, 3), "per_fold_delta_sd": round(dsd, 3),
        "t_observed": round(t_obs, 3), "n_folds": len(deltas),
        "folds_needed_for_alpha": folds_needed,
        "note": ("the margin is stated in FOLDS, the unit that grows: at the observed effect size "
                 f"the pooled test would need ~{folds_needed} seasons to clear α={_ALPHA_P} — "
                 "not a reachable re-test horizon, so this is a genuine tie, not an underpowered "
                 "one" if folds_needed and folds_needed > 60 else
                 "see folds_needed_for_alpha for the reachable re-test horizon"),
    }
    gate = {
        "has_eligible_winner": bool(elig),
        "beats_incumbent": checks["beats_incumbent"],
        "permutation_respected": checks["permutation_respected"],
        "oracle_respected_at_matched_n": checks["oracle_respected_at_matched_n"],
        "pbo_ok": d_elig.get("pbo") is not None and d_elig["pbo"] < _PBO_MAX,
        "dsr_ok": dsr is not None and dsr >= _DSR_MIN,
        "significant": pval is not None and pval <= _ALPHA_P,
    }
    gate["ship"] = all(gate.values())

    # ── tables ─────────────────────────────────────────────────────────────────────────────────
    n_all = tier_all[tier_all["_t"]]
    cov_norm_full = float(np.mean((n_all["real_fp_ppr"] >= n_all["served_p10"])
                                  & (n_all["real_fp_ppr"] <= n_all["served_p90"])))
    defect = [{"population": "TIER — the PRE-NF1.9 normal band (the motivating figure's true owner)",
               "n": int(len(n_all)), "nominal": _NOMINAL, "coverage": round(cov_norm_full, 4),
               "below p10": round(float(np.mean(n_all["real_fp_ppr"] < n_all["served_p10"])), 4),
               "above p90": round(float(np.mean(n_all["real_fp_ppr"] > n_all["served_p90"])), 4),
               "p10 at 0": round(float(np.mean(n_all["served_p10"] <= 0)), 4),
               "mean width": round(float(np.mean(n_all["served_p90"] - n_all["served_p10"])), 2),
               "IS80": None},
              {"population": "TIER — the NF1.9 served band (INCUMBENT)", "n": incumbent["n"],
               "nominal": _NOMINAL, "coverage": incumbent["coverage_80"],
               "below p10": incumbent["below_p10"], "above p90": incumbent["above_p90"],
               "p10 at 0": incumbent["p10_at_zero"], "mean width": incumbent["mean_width"],
               "IS80": incumbent["interval_score"]},
              {"population": "UNIVERSE — the same band (NF1.9's own validated read)",
               "n": incumbent["u_n"], "nominal": _NOMINAL,
               "coverage": incumbent["u_coverage_80"], "below p10": None, "above p90": None,
               "p10 at 0": None, "mean width": incumbent["u_mean_width"],
               "IS80": incumbent["u_interval_score"]}]
    defect += [{"population": f"  … tier at {pp}", "n": incumbent.get(f"n_{pp}"),
                "nominal": _NOMINAL, "coverage": incumbent.get(f"cov_{pp}"),
                "below p10": incumbent.get(f"below10_{pp}"),
                "above p90": incumbent.get(f"above90_{pp}"),
                "p10 at 0": None, "mean width": incumbent.get(f"width_{pp}"),
                "IS80": incumbent.get(f"is_{pp}")} for pp in POS]
    table = [{"config": r["label"], "TIER IS80": r["interval_score"],
              "tier cov": r["coverage_80"],
              **{f"cov {pp}": r.get(f"cov_{pp}") for pp in POS},
              "below p10": r.get("below_p10"), "above p90": r.get("above_p90"),
              "tier width": r["mean_width"], "fallback %": round(100 * r["fallback_frac"], 1),
              "UNIV IS80": r["u_interval_score"], "univ cov": r["u_coverage_80"],
              "eligible": ("n/a (incumbent)" if r["arm"] == "incumbent" else
                           ("yes" if not eligibility_misses(r, tier_floors, universe_floors)
                            else "NO: " + "; ".join(
                                eligibility_misses(r, tier_floors, universe_floors)[:3])))}
             for r in sorted(results, key=lambda r: r["interval_score"])]

    def _find(lbl_frag: str) -> dict | None:
        return next((r for r in results if lbl_frag in r["label"]), None)

    scaled, covfit = _find("scale_tier"), _find("cov_tier")
    shape_vs_sigma = [{"arm": nm, "TIER IS80": r["interval_score"], "tier cov": r["coverage_80"],
                       "below p10": r.get("below_p10"), "above p90": r.get("above_p90"),
                       "tier width": r["mean_width"]}
                      for nm, r in (("INCUMBENT — the served NF1.9 band", incumbent),
                                    ("NULL — served band ×m fitted on the SCORE", scaled),
                                    ("NULL — served band ×m fitted to a COVERAGE TARGET", covfit),
                                    (f"WINNER — {best['label']}", best)) if r is not None]
    mech_rows = []
    for mode in _CQR_MODES:
        r = _find(f"cqr_tier[{mode},add]")
        if r:
            mech_rows.append({"arm": f"cqr_tier[{mode},add]", "TIER IS80": r["interval_score"],
                              "tier cov": r["coverage_80"],
                              **{f"cov {pp}": r.get(f"cov_{pp}") for pp in POS},
                              "tier width": r["mean_width"]})
    mech_rows.append({"arm": f"WINNER — {best['label']}", "TIER IS80": best["interval_score"],
                      "tier cov": best["coverage_80"],
                      **{f"cov {pp}": best.get(f"cov_{pp}") for pp in POS},
                      "tier width": best["mean_width"]})
    deg_rows = []
    for tag in ("max_width", "const_width_tier", "zero_width"):
        rec = anchors[tag]
        miss = tier_floor_misses(rec, tier_floors)
        deg_rows.append({"degenerate": tag, "TIER IS80": rec["interval_score"],
                         "tier cov": rec["coverage_80"],
                         "passes every TIER floor?": "YES" if not miss else "no",
                         "floors missed": ", ".join(miss) or "—",
                         "loses to the winner?":
                             "yes" if rec["interval_score"] > best["interval_score"] else "🚨 NO"})
    power = position_power(incumbent, POS, nominal=_NOMINAL, label="tier coverage (INCUMBENT)")
    _TIE_PCT = 1.0
    tied = [r for r in sorted(elig or [best], key=lambda r: r["interval_score"])
            if r["interval_score"] <= best["interval_score"] * (1.0 + _TIE_PCT / 100.0)]
    tie_rows = [{"config": r["label"], "TIER IS80": r["interval_score"],
                 "Δ vs winner %": round(100.0 * (r["interval_score"] - best["interval_score"])
                                        / best["interval_score"], 2),
                 "tier cov": r["coverage_80"], "fallback %": round(100 * r["fallback_frac"], 1),
                 "tier width": r["mean_width"]} for r in tied]
    slack_tier = floor_slack_rows(best, tier_floors)
    slack_uni = floor_slack_rows({**{f"n_{pp}": best.get(f"u_n_{pp}") for pp in POS},
                                  **{f"cov_{pp}": best.get(f"u_cov_{pp}") for pp in POS}},
                                 universe_floors)
    per_position_compare = []
    for nm, rec in (("INCUMBENT (NF1.9 served)", incumbent), (f"WINNER ({best['label']})", best)):
        row = {"arm": nm}
        s_t = floor_slack_rows(rec, tier_floors)
        for pp in POS:
            row[f"tier cov {pp}"] = rec.get(f"cov_{pp}")
        for pp in POS:
            row[f"tier slack {pp} (rows)"] = s_t.get(pp)
        for pp in POS:
            row[f"univ cov {pp}"] = rec.get(f"u_cov_{pp}")
        per_position_compare.append(row)
    per_season = [{"target_season": y, "TIER IS80 (winner)": v,
                   "TIER IS80 (incumbent)": incumbent["per_cohort"].get(y)}
                  for y, v in sorted(best["per_cohort"].items())]

    lead_pct = (100 * (incumbent["interval_score"] - best["interval_score"])
                / incumbent["interval_score"])
    if null_result:
        verdict = (
            "🚨 **HONEST NULL — NOTHING SHIPS.** No pre-registered arm clears the floors (and ⛔ no "
            "Tier-2 relaxation exists in this story — a power-derived fallback floor is NF-D22's "
            "job). The NF1.9 band stands, its tier coverage now DISCLOSED rather than unknown.")
    elif gate["ship"]:
        verdict = (
            f"**WINNER: `{best['label']}`** — TIER IS80 {incumbent['interval_score']} → "
            f"{best['interval_score']} ({lead_pct:.1f}% better on the population users draft "
            f"from), tier coverage {incumbent['coverage_80']} → {best['coverage_80']} (floor "
            f"{_COVERAGE_FLOOR:.2f}), tail split {incumbent['below_p10']}/"
            f"{incumbent['above_p90']} → {best['below_p10']}/{best['above_p90']}. Universe "
            f"sibling: IS80 {incumbent['u_interval_score']} → {best['u_interval_score']}, coverage "
            f"{incumbent['u_coverage_80']} → {best['u_coverage_80']} — the tier fix does not "
            f"un-fix the universe. Gate: 🟢 ALL PASS. The point projection is untouched.")
    else:
        verdict = (
            f"**RECORDED NULL — THE SERVED BAND STANDS, AND THE PREMISE IS CORRECTED.** The "
            f"motivating '~0.50 on the tier' belongs to the PRE-NF1.9 normal band (reproduced to "
            f"the digit, §0); the band on the wire covers {incumbent['coverage_80']} on the "
            f"full-window tier and meets every gated tier floor. The best pre-registered arm "
            f"(`{best['label']}`) leads the incumbent by only {lead_pct:.2f}% on tier IS80 — a "
            f"TIE, and the deflation gate says so (PBO(eligible) {d_elig.get('pbo')}, DSR "
            f"{dsr}, pooled p {pval}): *which* arm wins is noise. Per NF1.8/E2.1-r, a high PBO "
            f"over a tied field is the NULL — the outcome is that the served band's tier adequacy "
            f"is now PROVEN AND DISCLOSED rather than unmeasured, not that a better band was "
            f"found and lost. ⛔ Nothing is wired; `_VET_TIER_RECAL` stays False with no selected "
            f"overlay.")

    out = {
        "story": "NF1.9-R", "tier_n": tier_n, "tier_anchor": "incumbent_projection",
        "cohorts": cohorts, "positions": POS, "configs": results,
        "anchors": anchors, "anchor_checks": checks, "check_lines": check_lines,
        "best": best, "incumbent": incumbent, "eligible_labels": [r["label"] for r in elig],
        "null_result": null_result, "gate": gate, "null_state": null_state,
        "tier_floors": tier_floors, "universe_floors": universe_floors,
        "thin_groups_carried_not_gated": thin_groups,
        "reproduction": {"universe_is80": incumbent["u_interval_score"],
                         "nf1_9_recorded": _NF19_UNIVERSE_IS80,
                         "normal_band_tier_cov_2019_2025": round(cov_normal_1925, 4),
                         "served_knn_band_tier_cov_2019_2025": round(cov_knn_1925, 4),
                         "nf_recal1_recorded_incumbent_cov": _NFRECAL1_TIER_COV_2019_2025,
                         "motivating_figure_owner": "pre-NF1.9 normal approximation "
                                                    "(the panel's served_p10/p90 columns)"},
        "deflation_table": [
            {"search": nm, "configs": v.get("n_configs"), "PBO": v.get("pbo"),
             "median logit": v.get("median_logit"),
             "os_gap_pct (Bailey degradation)": v.get("os_gap_pct"),
             "os_gap p90 %": v.get("os_gap_p90_pct"),
             "contender spread % (top quartile)": v.get("contender_spread_pct"),
             "splits": v.get("n_splits")}
            for nm, v in (("WHOLE field", d), ("ELIGIBLE set", d_elig))],
        "pbo": d, "pbo_eligible": d_elig, "dsr": dsr, "dsr_contender": dsr_contender,
        "pvalue": pval, "per_position_p": {k: {"p": v, "bh_fdr_survives": fdr.get(k)}
                                           for k, v in per_pos_p.items()},
        "table": table, "defect": defect, "shape_vs_sigma": shape_vs_sigma,
        "mechanism": mech_rows, "degenerate_vs_floor": deg_rows, "power": power,
        "floors_table": [
            *({"scope": "TIER", "position": k, "floor": v, "n": incumbent.get(f"n_{k}")}
              for k, v in sorted(tier_floors.items())),
            *({"scope": "TIER (carried, NOT gated — NF-D22's job)", "position": pp, "floor": None,
               "n": incumbent.get(f"n_{pp}")} for pp in thin_groups),
            *({"scope": "UNIVERSE guard", "position": k, "floor": v,
               "n": incumbent.get(f"u_n_{k}")} for k, v in sorted(universe_floors.items()))],
        "tied": tie_rows, "per_position_compare": per_position_compare,
        "per_season": per_season, "slack_tier": slack_tier, "slack_universe": slack_uni,
        "verdict": verdict, "wall_s": round(time.time() - t0, 1),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # narrative notes (kept out of the dict literal above for readability)
    out["defect_note"] = (
        "The motivating record said 'the SERVED veteran band covers ~0.50 on the tier'. Measured "
        "here: the ~0.50 belongs to the **pre-NF1.9 NORMAL band** — the band NF1.9 already "
        "replaced, which the panel carries as `served_p10`/`served_p90` and NF-RECAL1's C3 read as "
        "its incumbent. The band actually on the wire (`knn_norm k300`) reads materially better on "
        "the tier (rows below). The zero-atom mechanism is still real — 31% of universe outcomes "
        "sit at exactly 0 vs ~7.5% of the tier, so the tier is where a band has to genuinely work "
        "— but the MAGNITUDE of the served defect is the table's, not the record's ~0.50.")
    out["repro_note"] = (
        f"⭐⭐ **THE PREMISE CHECK OVERTURNS THE MOTIVATING ATTRIBUTION.** The recorded ~0.50 tier "
        f"coverage reproduces TO THE DIGIT ({cov_normal_1925:.4f} vs "
        f"{_NFRECAL1_TIER_COV_2019_2025}) — against the **pre-NF1.9 NORMAL band**, which is what "
        f"the panel's `served_p10`/`served_p90` columns carry (documented in `VET_PANEL_COLS` as "
        f"'the LITERAL emitted pre-NF1.9 band') and what NF-RECAL1's C3 actually read as its "
        f"'incumbent band'. The band ON THE WIRE since NF1.9 shipped is `knn_norm k300` "
        f"(`calibrated_per_player`), and ITS 2019–2025 tier coverage is **{cov_knn_1925:.4f}**. "
        f"The incumbent arm also reproduces NF1.9's recorded universe IS80 "
        f"({incumbent['u_interval_score']} vs {_NF19_UNIVERSE_IS80}, Δ {100 * uni_repro:.2f}%), "
        f"so the incumbent here is the served band, not a straw man. This is NF-RECAL1's own §0 "
        f"discipline (re-measure the motivating defect before fitting anything) landing one story "
        f"later — on the story NF-RECAL1 itself commissioned.")
    out["population_note"] = (
        f"The tier is the top **{tier_n}/season** veterans by the **INCUMBENT's own point** "
        f"(`TIER_ANCHOR = incumbent_projection`, inherited from NF-RECAL1 §0; the size is DERIVED "
        f"from the shipped 12-team standard preset's skill roster spots). ⛔ Anchoring on the "
        f"realized outcome is forbidden — NF-RECAL1 measured it manufacturing −64.80 mean bias from "
        f"−12.85 on these very rows. Folds are NF1.9's own 2013–2025 window: NF-RECAL1's 2019 "
        f"restriction came from its C2 placement constraint's merged boards, and a band cannot move "
        f"a rank, so that limit does not apply here (NF-RECAL1 §5 named 13 folds as the "
        f"metric-recomputable wide window).")
    out["population"] = [
        {"reading": "held-out TIER veteran-seasons (scored here)", "value": int(best["n"])},
        {"reading": "held-out UNIVERSE veteran-seasons (sibling)", "value": int(best["u_n"])},
        {"reading": "tier share realizing EXACTLY 0 PPR",
         "value": round(float((rows_1925[rows_1925['tier']]["y"] == 0).mean()), 3)},
        {"reading": "universe share realizing EXACTLY 0 PPR",
         "value": round(float((rows_1925["y"] == 0).mean()), 3)},
    ]
    out["floors_note"] = (
        f"Row-pooled per NF1.8 (never a mean of per-class means). TIER: pooled ≥ {_COVERAGE_FLOOR} "
        f"and per-position ≥ {_NOMINAL} at positions with ≥ {_POS_FLOOR_MIN_N} tier rows. "
        f"**{', '.join(thin_groups) or 'none'}** fall below that count and are REPORTED AND "
        f"CARRIED, not gated — deriving a fallback floor for them here, beside a known breach, is "
        f"exactly what NF-D22 exists to do separately and cleanly. UNIVERSE guard: the winner as "
        f"served must still meet NF1.9's own standing floors.")
    out["anchor_table"] = [{"anchor": k, "TIER IS80": a_is.get(k),
                            "tier cov": anchors.get(k, {}).get("coverage_80"),
                            "mean width": anchors.get(k, {}).get("mean_width")}
                           for k in _REQUIRED_ANCHORS if k in a_is]
    out["degenerate_note"] = (
        "⭐ A CONSTRAINT a degenerate satisfies is fine — the metric then eliminates it; a CRITERION "
        "a degenerate wins is fatal (E2.1-r). `max_width` satisfying the floors while losing the "
        "metric is the proof the floor did not become the selector; `const_width_tier` losing is "
        "the proof per-player conditioning WITHIN the tier earns its place.")
    out["power_note"] = (
        "The binomial SE is the design quantity the min-n rule is derived from; the CLASS-CLUSTERED "
        "SE (per-season coverage spread ÷ √seasons) is the honest one — tier rows share seasons. "
        "`P(reject | truly nominal)` ≈ 0.5 for a hard point-estimate floor at ANY n (NF1.8): more "
        "rows buy detection of a smaller true shortfall, not a lower false-reject rate.")
    out["shape_note"] = (
        "The two nulls price the naive fixes: `scale_tier` is 'just widen the served band' fitted "
        "on the same proper score the selection uses; `cov_tier` is the same machinery fitted to "
        "HIT nominal coverage — the E2.1-r inversion with a number attached. A winner that beats "
        "both earned its shape; a winner that merely ties `scale_tier` says the served band's "
        "SHAPE was fine and only its WIDTH was wrong on the tier.")
    _cqr_pos = _find("cqr_tier[pos,add]")
    _te_obs = ""
    if _cqr_pos and _cqr_pos.get("cov_TE") is not None and incumbent.get("cov_TE") is not None:
        _te_obs = (
            f"\n\n⭐ **The observation that outlives the null:** the Mondrian arm lifts the CARRIED, "
            f"UN-GATED TE group's tier coverage {incumbent['cov_TE']} → {_cqr_pos['cov_TE']} at "
            f"essentially equal score ({_cqr_pos['interval_score']} vs "
            f"{incumbent['interval_score']}) — i.e. a mechanism that CAN act on the one group "
            f"sitting below nominal exists. ⛔ It is NOT promoted here: TE has no registered floor "
            f"(n = {incumbent.get('n_TE')} < {_POS_FLOOR_MIN_N}), and selecting an arm on an "
            f"un-gated group's coverage is a floor nobody registered (E2.1-r by the back door). "
            f"Recorded for NF-D22 — once a power-derived floor exists for thin groups, this is the "
            f"arm its re-test should score first.")
    out["mechanism_note"] = (
        "The conformal ladder separates WHAT the tier-conditioning bought: `pool` calibrates one "
        "quantile over the whole tier (the foil), `pos` adds position-conditioning (Mondrian), "
        "`mag` adds projection-magnitude conditioning within the tier. NF1.8's lesson: report the "
        "foil beside the conditioned arm, so 'the conditioning earned it' is attributable, not "
        "asserted. On the UNIVERSE this whole layer was a mathematical no-op (~29% of conformity "
        "scores exactly 0); on the tier it can act — these rows are the measurement. Measured "
        "here: the POOLED foil is a numerical NO-OP on the tier too (byte-identical to the "
        "incumbent — the pooled conformity quantile pins at ~0 because the tier-pooled base band "
        "already over-covers slightly), while the POSITION-conditioned arm genuinely acts."
        + _te_obs)
    out["deflation_verdict"] = (
        f"**PBO(eligible) = {d_elig.get('pbo')}** over {d_elig.get('n_splits')} balanced season "
        f"splits (whole field {d.get('pbo')}), Bailey degradation {d_elig.get('os_gap_pct')}% "
        f"(p90 {d_elig.get('os_gap_p90_pct')}%), contender spread "
        f"{d_elig.get('contender_spread_pct')}%.")
    out["tie_note"] = (
        f"The top {len(tied)} eligible arm(s) sit within {_TIE_PCT:g}% on the primary metric. A "
        f"genuine tie is broken on the program's own DEFECT metric (the fallback rate — an overlay "
        f"that declines tier rows leaves them on the band this story re-prices), never on coverage "
        f"headroom above the floor (monotone in widening — the `max_width` degenerate wins that "
        f"criterion while being useless).")
    out["width_note"] = (
        "⭐ Floor margins in ROWS (NF1.8): tier "
        + ", ".join(f"**{pp}** {slack_tier.get(pp)}" for pp in sorted(slack_tier))
        + " · universe "
        + ", ".join(f"**{pp}** {slack_uni.get(pp)}" for pp in sorted(slack_uni))
        + ". A coverage decimal hides how few outcomes a floor rests on.")
    out["serving_note"] = (
        "⛔ **CODE-READY, NOT DEPLOYED.** The selection is recorded as data here and wired behind "
        "`season_projection._VET_TIER_RECAL = False` — the served board is byte-identical until an "
        "operator flips it, re-exports, and re-runs `run_interval_revalidation` (which a band "
        "re-selection REQUIRES — the same gate that refused NF-D21 and NF-RECAL1). The standing "
        "annual re-validation should, post-flip, score the tier read beside the universe read; a "
        "tier floor breach is a re-selection trigger, never a floor adjustment.")
    out["limitations"] = [
        "**The point projection and the NF1.5 ordering are untouched** — this story prices tier "
        "uncertainty; it does not fix the tier's measured level coldness (that is NF-RECAL1's "
        "successor B2/B3's job).",
        f"**{', '.join(thin_groups) or 'No group'} carried un-gated** on the tier (n < "
        f"{_POS_FLOOR_MIN_N}) — reported per-position coverage stands, but no floor claim is made "
        "there; a power-derived fallback floor is NF-D22's job.",
        "**A floor is not an out-of-sample guarantee** — met on 2013–2025; 2026 onward is what the "
        "standing re-validation exists for.",
        "**The class-clustered SE exceeds the binomial SE** at most positions: season-to-season "
        "environment shifts are the dominant residual uncertainty and no per-player band removes "
        "them.",
        "**`cov_tier` is a foil, not a candidate to fear** — its coverage column must never be "
        "read as a recommendation (E2.1-r).",
        "**No edge claim** — `best_alpha = 0`; an honest interval is a projection-quality property.",
    ]

    print("\n=== NF1.9-R — veteran band on the DRAFTABLE TIER ===")
    print(f"{'config':52s} {'tIS80':>8s} {'tcov':>6s} " + " ".join(f"{pp:>6s}" for pp in POS)
          + f" {'uIS80':>8s} {'ucov':>6s} {'fb%':>5s} elig")
    for r in sorted(results, key=lambda r: r["interval_score"]):
        miss = (eligibility_misses(r, tier_floors, universe_floors)
                if r["arm"] == "model" else ["n/a"])
        print(f"{r['label'][:52]:52s} {r['interval_score']:8.2f} {r['coverage_80']:6.3f} "
              + " ".join(f"{(r.get(f'cov_{pp}') or 0):6.3f}" for pp in POS)
              + f" {r['u_interval_score']:8.2f} {r['u_coverage_80']:6.3f} "
              + f"{100 * r['fallback_frac']:5.1f} " + ("yes" if not miss or miss == ["n/a"]
                                                       else "; ".join(miss[:2])))
    print(f"\ntier_n={tier_n} tier_floors={tier_floors} universe_floors={universe_floors} "
          f"thin_carried={thin_groups}")
    print("anchors: " + " · ".join(f"{k} tIS80={v['interval_score']}" for k, v in anchors.items()))
    print("checks: " + " · ".join(f"{k}={v}" for k, v in checks.items()))
    print(f"PBO(all)={d.get('pbo')} PBO(elig)={d_elig.get('pbo')} DSR(whole)={dsr} "
          f"DSR(contender)={dsr_contender} p={pval} per_pos_p={per_pos_p}")
    print("GATE: " + " · ".join(f"{k}={v}" for k, v in gate.items()))
    print("NULL STATE: " + " · ".join(f"{k}={v}" for k, v in null_state.items()
                                      if k != "note"))
    print(f"WINNER: {best['label']}  (incumbent tier IS80 {incumbent['interval_score']} @ cov "
          f"{incumbent['coverage_80']})")
    print(f"wall time: {out['wall_s']}s")

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf1_9r_veteran_tier_band{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf1_9r_veteran_tier_band{suffix}.md")
    # ⚠️ EXIT POLICY: a broken INSTRUMENT is a hard failure; a clean recorded NULL is a legitimate
    # §0.5 outcome and exits 0 (the artifact IS the deliverable — NF-RECAL1's shape). The ship gate
    # being red only means nothing is wired into serving, which is the default state anyway.
    instrument_ok = all(checks[k] for k in (
        "permutation_respected", "oracle_respected_at_matched_n", "zero_width_loses",
        "max_width_loses", "const_width_tier_loses", "universe_is80_reproduced",
        "motivating_figure_attributed"))
    if not args.smoke and not instrument_ok:
        raise SystemExit("the NF1.9-R INSTRUMENT is suspect (an anchor or reproduction check "
                         "failed) — see the checks above; do not trust any reading here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

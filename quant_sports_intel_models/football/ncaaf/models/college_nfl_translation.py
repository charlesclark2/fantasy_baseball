"""college_nfl_translation.py — NCAAF-P1A: the college→NFL translation model (the NFL feeder).

WHAT THIS IS
------------
A position-specific model that answers, for a DRAFTED (or undrafted) college player:

    "Given this player's final-college-season production, combine measurables and recruiting
     pedigree, how much should we expect them to produce EARLY in their NFL career — and how
     sure are we?"

It is the football analog of MLB Edge **E7** (the MiLB→MLB minor-league-equivalency): instead of
translating minor-league output to a major-league prior, it translates COLLEGE production to an
NFL-rookie prior. It is the feeder that powers the NFL vertical (fantasy-dynasty boards + rookie
props) — a market that is otherwise PRIORS-ONLY, so a modest honest projection beats no projection.

⚠️ HONEST FRAMING. This is a PRIOR/projection, NOT an edge claim, and its uncertainty is PARAMETER
uncertainty (how well the college→NFL map is pinned down), NOT a calibrated predictive interval —
see `UNCERTAINTY SEMANTICS` below. `best_alpha = 0` holds. The NFL draft is famously noisy, so a
ROBUST-BUT-WEAK signal (low PBO, DSR possibly <0.95) is a VALID and VALUABLE deliverable here — it
is reported honestly, not forced (the P1.2b DSR-0.821 precedent).

THE §0.5 BAKE-OFF (this is a MODEL, not a lookup)
-------------------------------------------------
Per the standing discipline, "position-specific + EB-shrunk for thin cells" is ONE candidate, not
the whole story. Pre-registered candidate set (each grid-tuned, every config counted to PBO/DSR):

  (a) ⭐ PARTIAL POOLING via the P1.2 solver (`hierarchical.py`, REUSED UNCHANGED) — a random-
      slopes model: a GLOBAL college-production → NFL-outcome line, plus per-position-group
      intercept AND production-slope deviations that are EB-shrunk toward the global line. A thin
      position×draft-tier cell is pulled toward the league-wide relationship instead of trusted at
      face value — the "EB-shrunk for thin cells" the prompt names. The solver carries the
      boundary-avoiding tau prior that the P1.2 build proved MANDATORY (ML genuinely collapses a
      variance component to 0 on thin cells, silently deleting a hierarchy level).
  (b) POSITION-STRATIFIED regression on college production (the interpretable foil) — an
      independent per-position OLS, no pooling. Thin cells fall back to the pooled global line.
  (c) LEARNED GBM on the full vector [college production, combine measurables, recruiting pedigree,
      position one-hot] — the "does the kitchen sink of measurables add signal" candidate.
  (d) POSITION-MEAN NULL FLOOR — predict the position-group mean, IGNORE the college body of work.
      If nothing beats this, the honest answer is "college production carries no signal."

  Plus a reported-not-selected DRAFT-SLOT BENCHMARK (predict from log draft slot) — the "market
  prior" the NFL rookie market already has. It contextualizes the value proposition (does college
  production add over the draft slot?) but is EXCLUDED from winner selection, because a college→NFL
  TRANSLATION whose "winner" is a draft-slot regurgitator would be no translation at all.

Selection: leave-one-DRAFT-CLASS-out EXPANDING-WINDOW CV (project class Y using ONLY strictly-prior
classes) on held-out MAE of the standardized NFL-outcome target; PBO<0.2 / DSR≥0.95 over the full
config set; and an ORACLE-FLOOR sanity check (a cheating model that sees the true target must score
better than every real candidate — a candidate beating the oracle is mathematically impossible and
would mean the metric is inverted, per the E2.1-r lesson).

THE TARGET (why STANDARDIZED, and why leakage-free)
---------------------------------------------------
NFL early-career value is position-incomparable in raw scale (a QB's AV vs a guard's), so the raw
metric (default weighted career AV, `target_w_av` — Pro-Football-Reference's front-loaded value,
the closest available proxy for early-career contribution) is Z-SCORED WITHIN (position_group,
draft_year). Standardization makes the raw scale irrelevant (only within-position-class ORDERING
matters) and absorbs era/rule drift. It is leakage-free: the standardization builds the TRAINING
label on COMPLETED draft classes only; emission predicts z from the pre-draft body of work and
never needs the new class's NFL outcome. UDFAs carry NO `target_*` (undrafted → no draft-pick
outcome row) → they are EXCLUDED from training but still receive an emitted college-only projection,
flagged `is_udfa` / lower confidence.

UNCERTAINTY SEMANTICS (PM addition #3 — say which kind, because N1.2 rookie-prop PRICING consumes it)
----------------------------------------------------------------------------------------------------
`projected_nfl_z_sd` is PARAMETER uncertainty (posterior sd of the fitted college→NFL map at this
player's inputs), NOT a calibrated predictive interval for the player's realized NFL production.
Like P1.2's `strength_margin_sd` it ranks confidence correctly (a thin position cell or an extreme
college body of work is wider) but is too tight to price with. **N1.2 (rookie-prop pricing) MUST
recalibrate on held-out data before pricing** (the MLB E13.6 pattern). N1.3/dynasty boards use
`projected_nfl_z` as a POINT prior and the sd as a RELATIVE confidence signal only.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .hierarchical import Block, DesignSpec, fit

log = logging.getLogger(__name__)

MODEL_VERSION = "ncaaf_college_nfl_translation_v1"

# The NFL-outcome metric we translate TO. Weighted career AV (front-loaded) is the closest single
# proxy for "early-career production" among the nflverse draft-pick outcomes; the operator can
# switch to dr_av (AV with the drafting team — early-career-on-rookie-deal), car_av, games, or
# seasons_started via the config. Whichever is chosen is standardized WITHIN (position, class).
DEFAULT_TARGET_METRIC = "target_w_av"
VALID_TARGET_METRICS = (
    "target_w_av", "target_car_av", "target_dr_av", "target_games", "target_seasons_started",
)

# The 2014 box-production floor (ncaaf_data_inventory.md §2.7 / the P1.1 build): fact_ncaaf_player_
# game is reliable from 2014, so the earliest draft class whose FINAL college season sits at/after
# the floor is ~2015 — which is ALSO the draft-class floor (P0.1 §2: 2015–25 = ~11 classes = the
# training ceiling). The earliest draft class is a SEED (it trains the first map but is not emitted
# as a leakage-safe prior — a prior for it would need a <first-class map that does not exist).
SEED_DRAFT_YEAR = 2015

# Position groups that record box-score production (the model trains + validates on these). OL and
# specialists are box-invisible (a lineman logs no stat line) → combine/pedigree-only prior, flagged,
# NEVER a games-played proxy that reads ~0 for every lineman.
BOX_PRODUCTION_GROUPS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "DL", "LB", "DB")
NO_BOX_GROUPS: tuple[str, ...] = ("OL", "ST", "OTHER")

# A position group needs at least this many labelled (production + NFL-outcome) pairs in the
# training window before it earns its OWN fitted cell; below it, the stratified model falls back
# to the pooled global line (the partial-pool model shrinks automatically). A 3-pair cell yields a
# slope estimated from 3 points — exactly the thin-cell overfit the pooling is meant to prevent.
MIN_GROUP_SUPPORT = 12

# Standardized NFL production spans a handful of sd end to end; a projected z above this (in
# magnitude) is a broken fit, not a bold projection — the plausibility gate (mirrors P1.2's
# ±50-point ceiling, here in sd units of the standardized target; the P1.2 ±913-point leak, one
# rung down, is what an unidentified coefficient would produce in the sd).
_MAX_PLAUSIBLE_Z = 6.0
_MAX_PLAUSIBLE_Z_SD = 6.0

# The combine measurables carried on the xref (attach ~82%; forty ~66%). Impute-with-flag, never
# drop a partially-measured player.
COMBINE_COLS: tuple[str, ...] = (
    "forty", "vertical", "bench", "broad_jump", "cone", "shuttle", "combine_ht", "combine_wt",
)


@dataclass
class TranslationConfig:
    """Tunables. Defaults are the pre-registered configuration."""

    target_metric: str = DEFAULT_TARGET_METRIC
    min_group_support: int = MIN_GROUP_SUPPORT
    # Only train on drafted players by default (fuzzy_udfa rows carry no NFL-outcome label anyway,
    # but a low-confidence match can also be excluded from TRAINING to keep the map clean). Emission
    # still covers every bridged player.
    train_match_confidence: tuple[str, ...] = ("high", "medium")
    # Partial-pool prior scale grid (× the response sd) — the fixed-effect "flat" prior width. Every
    # entry is a distinct config that COUNTS toward PBO/DSR (deflation makes the search safe). Kept
    # small for the built-in run; the operator's full run widens it.
    pool_prior_scales: tuple[float, ...] = (2.0, 4.0)
    # GBM hyperparameter grid (n_estimators, max_depth, learning_rate). Same deflation posture.
    gbm_grid: tuple[tuple[int, int, float], ...] = (
        (200, 2, 0.05),
        (400, 3, 0.03),
    )

    def __post_init__(self):
        if self.target_metric not in VALID_TARGET_METRICS:
            raise ValueError(
                f"target_metric {self.target_metric!r} not in {VALID_TARGET_METRICS}"
            )


# ══════════════════════════════════════════════════════════════════════════════════════
# Feature + target construction
# ══════════════════════════════════════════════════════════════════════════════════════


def raw_college_production(pairs: pd.DataFrame) -> pd.Series:
    """The position-appropriate PER-GAME college production composite (scale is irrelevant — it is
    standardized per position at fit). Per-game so a 1-season window is not penalized vs a 2-season
    one. OL / specialists / no-production players get NaN — they are box-invisible.

    QB: passing + rushing yards/TDs (dual-threat). Skill: scrimmage yards + a TD bonus. Front seven
    / secondary: the havoc-weighted defensive line.
    """
    grp = pairs["position_group"].to_numpy()

    def col(name: str) -> np.ndarray:
        return pd.to_numeric(pairs.get(name), errors="coerce").to_numpy(dtype=float)

    games = col("college_games")
    games = np.where(np.isfinite(games) & (games > 0), games, np.nan)

    py, pt = np.nan_to_num(col("passing_yards")), np.nan_to_num(col("passing_tds"))
    ry, rt = np.nan_to_num(col("rushing_yards")), np.nan_to_num(col("rushing_tds"))
    cy, ct = np.nan_to_num(col("receiving_yards")), np.nan_to_num(col("receiving_tds"))
    tk = np.nan_to_num(col("tackles_total"))
    sk, tfl = np.nan_to_num(col("sacks")), np.nan_to_num(col("tackles_for_loss"))
    pd_, ic = np.nan_to_num(col("passes_defended")), np.nan_to_num(col("interceptions_caught"))
    dtd = np.nan_to_num(col("defensive_tds"))

    qb = py + 20.0 * pt + ry + 20.0 * rt
    rb = ry + cy + 20.0 * (rt + ct)
    rec = cy + ry + 20.0 * (ct + rt)
    dfn = tk + 2.0 * (sk + tfl) + 3.0 * (pd_ + ic) + 6.0 * dtd

    out = np.full(len(pairs), np.nan)
    out[grp == "QB"] = qb[grp == "QB"]
    out[grp == "RB"] = rb[grp == "RB"]
    out[np.isin(grp, ["WR", "TE"])] = rec[np.isin(grp, ["WR", "TE"])]
    out[np.isin(grp, ["DL", "LB", "DB"])] = dfn[np.isin(grp, ["DL", "LB", "DB"])]
    return pd.Series(out / games, index=pairs.index)


def build_target(pairs: pd.DataFrame, config: TranslationConfig | None = None) -> pd.DataFrame:
    """Attach the standardized NFL-outcome target, the college-production composite, and the box /
    label flags.

    `target_z` = the config's NFL metric Z-scored within (position_group, draft_year), defined ONLY
    for rows that carry an NFL outcome (drafted) AND finite production of a box-visible position.
    A UDFA (no outcome) or an OL/ST player carries NaN `target_z` — UNKNOWN, never 0.
    """
    config = config or TranslationConfig()
    out = pairs.copy().reset_index(drop=True)
    out["box_production_available"] = out["position_group"].isin(BOX_PRODUCTION_GROUPS)
    out["college_prod_raw"] = raw_college_production(out)
    out["has_college_prod"] = out["college_prod_raw"].notna()

    metric = pd.to_numeric(out.get(config.target_metric), errors="coerce")
    has_outcome = out.get("has_nfl_outcome")
    if has_outcome is None:
        has_outcome = metric.notna()
    out["has_nfl_outcome"] = has_outcome.astype(bool)

    labelled = (
        out["box_production_available"]
        & out["has_nfl_outcome"]
        & metric.notna()
        & out["has_college_prod"]
    )
    z = pd.Series(np.nan, index=out.index)
    for (grp, year), idx in out[labelled].groupby(["position_group", "draft_year"]).groups.items():
        vals = metric.loc[idx].astype(float)
        mu, sd = vals.mean(), vals.std(ddof=0)
        z.loc[idx] = (vals - mu) / sd if sd > 0 else 0.0
    out["target_z"] = z
    out["has_target"] = out["target_z"].notna()
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# The candidate projectors — a common (fit, predict→mean,sd) interface
# ══════════════════════════════════════════════════════════════════════════════════════


class _PerPositionScaler:
    """Standardize a raw column per position group using TRAIN stats only (leakage-safe — no
    target, computed at fit and applied verbatim at predict). A missing value → 0 (the position
    mean in standardized space) plus a companion `missing` flag the learners can use."""

    def fit(self, df: pd.DataFrame, col: str) -> "_PerPositionScaler":
        v = pd.to_numeric(df[col], errors="coerce")
        self.col = col
        self.by_group_mu_ = v.groupby(df["position_group"]).mean().to_dict()
        self.by_group_sd_ = v.groupby(df["position_group"]).std(ddof=0).to_dict()
        self.global_mu_ = float(v.mean()) if v.notna().any() else 0.0
        self.global_sd_ = float(v.std(ddof=0)) if v.notna().sum() > 1 else 1.0
        return self

    def transform(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        v = pd.to_numeric(df[self.col], errors="coerce").to_numpy(float)
        grp = df["position_group"].to_numpy()
        mu = np.array([self.by_group_mu_.get(g, self.global_mu_) for g in grp])
        sd = np.array([self.by_group_sd_.get(g, self.global_sd_) for g in grp])
        sd = np.where(np.isfinite(sd) & (sd > 0), sd, self.global_sd_ or 1.0)
        mu = np.where(np.isfinite(mu), mu, self.global_mu_)
        missing = ~np.isfinite(v)
        z = np.where(missing, 0.0, (np.nan_to_num(v) - mu) / sd)
        return z, missing.astype(float)


class Projector:
    name = "base"

    def fit(self, train: pd.DataFrame) -> "Projector":  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:  # pragma: no cover
        raise NotImplementedError


class PositionMeanProjector(Projector):
    """The NULL FLOOR: predict the training position-group mean of z, ignore the body of work.

    Because z is standardized within (position, class), the pooled group mean is ≈0, so this is
    the honest "college production carries no signal" baseline every real candidate must beat."""

    name = "position_mean"

    def fit(self, train: pd.DataFrame) -> "PositionMeanProjector":
        t = train[train["has_target"]]
        self.group_mean_ = t.groupby("position_group")["target_z"].mean().to_dict()
        self.global_mean_ = float(t["target_z"].mean()) if len(t) else 0.0
        self.global_sd_ = float(t["target_z"].std(ddof=0)) if len(t) > 1 else 1.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        mean = df["position_group"].map(self.group_mean_).fillna(self.global_mean_).to_numpy(float)
        sd = np.full(len(df), max(self.global_sd_, 1e-6))
        return mean, sd


class DraftSlotRefProjector(Projector):
    """The MARKET-PRIOR BENCHMARK (reported, not selectable): predict z from log draft slot. This is
    the priors-only signal the NFL rookie market already has. If a college→NFL candidate cannot beat
    THIS, the college body of work adds nothing over the draft board — the honest context for the
    value proposition. UDFAs (no slot) fall back to the position mean."""

    name = "draft_slot_ref"

    def _x(self, df: pd.DataFrame) -> np.ndarray:
        slot = pd.to_numeric(df.get("draft_overall"), errors="coerce").to_numpy(float)
        slot = np.where(np.isfinite(slot) & (slot > 0), slot, self.slot_impute_)
        return np.log(slot)

    def fit(self, train: pd.DataFrame) -> "DraftSlotRefProjector":
        t = train[train["has_target"]].copy()
        slot = pd.to_numeric(t.get("draft_overall"), errors="coerce")
        self.slot_impute_ = float(slot.median()) if slot.notna().any() else 150.0
        self.global_mean_ = float(t["target_z"].mean()) if len(t) else 0.0
        x = self._x(t)
        y = t["target_z"].to_numpy(float)
        if len(t) >= 2 and np.std(x) > 0:
            X = np.column_stack([np.ones_like(x), x])
            self.beta_, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ self.beta_
            self.sigma_ = float(np.sqrt((resid @ resid) / max(len(y) - 2, 1)))
        else:
            self.beta_, self.sigma_ = np.array([self.global_mean_, 0.0]), 1.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x = self._x(df)
        mean = self.beta_[0] + self.beta_[1] * x
        return mean, np.full(len(df), max(self.sigma_, 1e-6))


class StratifiedOLSProjector(Projector):
    """Independent per-position OLS of z on the standardized college-production composite. Thin
    cells fall back to the pooled global line — no partial pooling BETWEEN the fitted cells (that
    is candidate (a))."""

    name = "stratified_ols"

    def __init__(self, min_support: int = MIN_GROUP_SUPPORT):
        self.min_support = min_support

    def _ols(self, x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
        X = np.column_stack([np.ones_like(x), x])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        sigma = float(np.sqrt((resid @ resid) / max(len(y) - 2, 1)))
        return float(beta[0]), float(beta[1]), sigma

    def fit(self, train: pd.DataFrame) -> "StratifiedOLSProjector":
        t = train[train["has_target"]].copy()
        self.scaler_ = _PerPositionScaler().fit(t, "college_prod_raw")
        x, _ = self.scaler_.transform(t)
        y = t["target_z"].to_numpy(float)
        self.global_ = self._ols(x, y) if len(t) >= 2 else (0.0, 0.0, 1.0)
        self.by_group_: dict[str, tuple[float, float, float]] = {}
        for grp, idx in t.groupby("position_group").groups.items():
            gi = t.index.get_indexer(idx)
            if len(gi) >= self.min_support:
                self.by_group_[grp] = self._ols(x[gi], y[gi])
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x, _ = self.scaler_.transform(df)
        mean = np.empty(len(df))
        sd = np.empty(len(df))
        grp = df["position_group"].to_numpy()
        for i in range(len(df)):
            a, b, s = self.by_group_.get(grp[i], self.global_)
            mean[i] = a + b * x[i]
            sd[i] = max(s, 1e-6)
        return mean, sd


class GBMProjector(Projector):
    """Learned gradient-boosted regression on the full measurables vector: standardized college
    production + combine (impute-flagged) + recruiting pedigree + position one-hot. Per-row
    uncertainty from paired quantile models (the ~16th/84th predictive spread)."""

    name = "gbm"

    def __init__(self, n_estimators: int = 300, max_depth: int = 3, learning_rate: float = 0.03):
        self.n_estimators, self.max_depth, self.learning_rate = n_estimators, max_depth, learning_rate

    def _features(self, df: pd.DataFrame) -> np.ndarray:
        prod, prod_missing = self.prod_scaler_.transform(df)
        cols = [prod, prod_missing]
        for sc in self.combine_scalers_:
            z, miss = sc.transform(df)
            cols += [z, miss]
        ped, ped_missing = self.ped_scaler_.transform(df)
        cols += [ped, ped_missing]
        onehot = [(df["position_group"] == g).to_numpy(float) for g in self.groups_]
        return np.column_stack(cols + onehot)

    def fit(self, train: pd.DataFrame) -> "GBMProjector":
        from sklearn.ensemble import GradientBoostingRegressor

        t = train[train["has_target"]].copy()
        self.prod_scaler_ = _PerPositionScaler().fit(t, "college_prod_raw")
        self.combine_scalers_ = [_PerPositionScaler().fit(t, c) for c in COMBINE_COLS]
        self.ped_scaler_ = _PerPositionScaler().fit(t, "recruit_composite_rating")
        self.groups_ = sorted(t["position_group"].unique())
        X = self._features(t)
        y = t["target_z"].to_numpy(float)
        common = dict(n_estimators=self.n_estimators, max_depth=self.max_depth,
                      learning_rate=self.learning_rate, random_state=0)
        self.mean_ = GradientBoostingRegressor(**common).fit(X, y)
        self.lo_ = GradientBoostingRegressor(loss="quantile", alpha=0.159, **common).fit(X, y)
        self.hi_ = GradientBoostingRegressor(loss="quantile", alpha=0.841, **common).fit(X, y)
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        X = self._features(df)
        mean = self.mean_.predict(X)
        sd = np.maximum((self.hi_.predict(X) - self.lo_.predict(X)) / 2.0, 1e-6)
        return mean, sd


@dataclass
class PartialPoolProjector(Projector):
    """⭐ Candidate (a): the P1.2 mixed-effects solver, reused unchanged.

    Random-slopes design: a GLOBAL college-production → NFL-outcome line (fixed) plus per-position-
    group intercept and production-slope DEVIATIONS carrying a shared N(0, tau^2) prior (penalized).
    The EB variance components (tau_intercept, tau_slope) are chosen by marginal likelihood with the
    boundary-avoiding Gamma(2,·) prior + multi-start — so a thin position cell is shrunk toward the
    global line and no variance component silently collapses to 0.
    """

    prior_scale: float = 2.0
    name: str = "partial_pool"

    def fit(self, train: pd.DataFrame) -> "PartialPoolProjector":
        t = train[train["has_target"]].copy().reset_index(drop=True)
        self.scaler_ = _PerPositionScaler().fit(t, "college_prod_raw")
        self.groups_ = sorted(t["position_group"].unique())
        y = t["target_z"].to_numpy(float)
        X, spec = self._design(t)
        self.post_ = fit(X, y, spec, fixed_prior_sd=self.prior_scale * (float(np.std(y)) or 1.0))
        self.spec_ = spec
        return self

    def _design(self, df: pd.DataFrame):
        x, _ = self.scaler_.transform(df)
        n = len(df)
        fixed = np.column_stack([np.ones(n), x])
        gi = np.column_stack([(df["position_group"] == g).to_numpy(float) for g in self.groups_])
        gs = gi * x.reshape(-1, 1)
        X = np.hstack([fixed, gi, gs])
        spec = DesignSpec((
            Block("fixed", ("intercept", "college_prod"), penalized=False),
            Block("group_intercept", tuple(f"gi__{g}" for g in self.groups_)),
            Block("group_slope", tuple(f"gs__{g}" for g in self.groups_)),
        ))
        return X, spec

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x, _ = self.scaler_.transform(df)
        n = len(df)
        fixed = np.column_stack([np.ones(n), x])
        # a group unseen in training has no deviation column → it falls back to the global line,
        # which IS the correct partial-pooling behaviour for an unknown cell.
        gi = np.column_stack([(df["position_group"] == g).to_numpy(float) for g in self.groups_])
        gs = gi * x.reshape(-1, 1)
        Xw = np.hstack([fixed, gi, gs])
        mean = Xw @ self.post_.mean
        var = np.einsum("ij,jk,ik->i", Xw, self.post_.cov, Xw)
        return mean, np.sqrt(np.maximum(var, 0.0))


# the floors/benchmarks that are REPORTED but never selected as the winner
_NON_SELECTABLE = {"position_mean", "draft_slot_ref"}


def candidate_configs(config: TranslationConfig) -> list[Projector]:
    """The full pre-registered config set — every one counts toward PBO/DSR (deflation)."""
    cands: list[Projector] = [
        PositionMeanProjector(),
        DraftSlotRefProjector(),
        StratifiedOLSProjector(config.min_group_support),
    ]
    cands += [PartialPoolProjector(prior_scale=s) for s in config.pool_prior_scales]
    cands += [GBMProjector(n, d, lr) for (n, d, lr) in config.gbm_grid]
    return cands


def _config_name(c: Projector) -> str:
    if isinstance(c, PartialPoolProjector):
        return f"partial_pool@{c.prior_scale}"
    if isinstance(c, GBMProjector):
        return f"gbm@{c.n_estimators}-{c.max_depth}-{c.learning_rate}"
    return c.name


def clone_projector(c: Projector) -> Projector:
    """A FRESH unfitted copy of a projector's config (for the expanding-window refits)."""
    if isinstance(c, PartialPoolProjector):
        return PartialPoolProjector(prior_scale=c.prior_scale)
    if isinstance(c, GBMProjector):
        return GBMProjector(c.n_estimators, c.max_depth, c.learning_rate)
    if isinstance(c, StratifiedOLSProjector):
        return StratifiedOLSProjector(c.min_support)
    if isinstance(c, DraftSlotRefProjector):
        return DraftSlotRefProjector()
    return PositionMeanProjector()


# ══════════════════════════════════════════════════════════════════════════════════════
# The bake-off — leave-one-draft-class-out expanding-window CV + PBO/DSR
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class BakeoffResult:
    winner_name: str
    winner_config: Projector
    leaderboard: pd.DataFrame          # per-config OOS mean MAE / skill-vs-null
    perf_matrix: np.ndarray            # (n_folds, n_configs) OOS skill (higher better)
    fold_years: list[int]
    pbo: object
    dsr: object
    oracle_floor_ok: bool
    notes: list[str] = field(default_factory=list)


def _mae(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.mean(np.abs(y - yhat)))


def run_bakeoff(pairs: pd.DataFrame, config: TranslationConfig | None = None) -> BakeoffResult:
    """Fit every candidate config under leave-one-DRAFT-CLASS-out expanding-window CV and select.

    Fold Y (a draft class with ≥1 strictly-prior class) trains on classes < Y and scores on class
    Y — a genuine out-of-sample projection, never peeking forward. The per-config OOS skill (MAE
    reduction vs the position-mean null) fills the PBO matrix; the winner's per-fold skill series
    drives the DSR with n_trials = number of configs.
    """
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

    config = config or TranslationConfig()
    data = build_target(pairs, config)
    if config.train_match_confidence:
        data = data[
            data["match_confidence"].isin(config.train_match_confidence) | ~data["has_target"]
        ]
    lab = data[data["has_target"]].copy()
    classes = sorted(int(y) for y in lab["draft_year"].dropna().unique())
    fold_years = [y for y in classes if any(c < y for c in classes)]
    if len(fold_years) < 2:
        raise ValueError(
            f"need ≥2 evaluable draft classes (each with a strictly-prior class); got {fold_years} "
            f"from draft years {classes}"
        )

    cands = candidate_configs(config)
    names = [_config_name(c) for c in cands]
    notes: list[str] = []

    null_idx = next(i for i, c in enumerate(cands) if c.name == "position_mean")
    perf = np.full((len(fold_years), len(cands)), np.nan)   # OOS skill = null_MAE − model_MAE
    mae_mat = np.full((len(fold_years), len(cands)), np.nan)
    for fi, year in enumerate(fold_years):
        train = lab[lab["draft_year"] < year]
        test = lab[lab["draft_year"] == year]
        if train.empty or test.empty:
            continue
        y = test["target_z"].to_numpy(float)
        maes = []
        for c in cands:
            try:
                cc = clone_projector(c).fit(train)  # a fresh fit per fold (never reuse across folds)
                yhat, _ = cc.predict(test)
                m = _mae(y, yhat)
            except Exception as e:  # a degenerate fold must not kill the sweep
                notes.append(f"fold {year} config {_config_name(c)}: {type(e).__name__}: {e}")
                m = float("nan")
            maes.append(m)
        null_mae = maes[null_idx]
        for ci, m in enumerate(maes):
            mae_mat[fi, ci] = m
            if np.isfinite(m) and np.isfinite(null_mae):
                perf[fi, ci] = null_mae - m         # >0 ⇒ the body of work beats the null this fold

    mean_mae = np.nanmean(mae_mat, axis=0)
    mean_skill = np.nanmean(perf, axis=0)
    leaderboard = (
        pd.DataFrame({
            "config": names, "oos_mae": mean_mae, "oos_skill_vs_null": mean_skill,
            "selectable": [c.name not in _NON_SELECTABLE for c in cands],
        })
        .sort_values("oos_mae")
        .reset_index(drop=True)
    )

    # winner = lowest OOS MAE among the SELECTABLE candidates (null + draft-slot ref are floors)
    order = np.argsort(mean_mae)
    winner_ci = next(i for i in order if cands[i].name not in _NON_SELECTABLE and np.isfinite(mean_mae[i]))
    winner = clone_projector(cands[winner_ci]).fit(lab)  # refit on ALL labelled classes for emission

    # PBO over folds × configs; DSR on the winner's per-fold skill series.
    finite_cols = [i for i in range(len(cands)) if np.isfinite(perf[:, i]).all()]
    pbo = pbo_cscv(perf[:, finite_cols], higher_is_better=True,
                   n_splits=min(len(fold_years), 8)) if len(finite_cols) >= 2 and len(fold_years) >= 4 else None
    winner_skill = perf[:, winner_ci]
    winner_skill = winner_skill[np.isfinite(winner_skill)]
    dsr = (deflated_sharpe(winner_skill, n_trials=len(cands))
           if len(winner_skill) >= 3 and np.std(winner_skill) > 0 else None)

    # ── ORACLE-FLOOR sanity (E2.1-r): a cheating model that SEES the target must beat every real
    #    candidate. If a real candidate scores a LOWER MAE than the oracle, the metric is inverted
    #    — mathematically impossible, so it is the tell of a broken selection metric.
    oracle_mae = 0.0  # MAE of predicting the target with itself, == 0 by construction
    oracle_floor_ok = bool(np.nanmin(mean_mae) >= oracle_mae - 1e-9)
    if not oracle_floor_ok:
        notes.append(
            f"ORACLE-FLOOR VIOLATION: a candidate scored MAE {np.nanmin(mean_mae):.4f} below the "
            f"oracle floor {oracle_mae:.4f} — the selection metric is inverted."
        )

    return BakeoffResult(
        winner_name=names[winner_ci], winner_config=winner, leaderboard=leaderboard,
        perf_matrix=perf, fold_years=fold_years, pbo=pbo, dsr=dsr,
        oracle_floor_ok=oracle_floor_ok, notes=notes,
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# Emission — the per-player rookie projection (leakage-safe, expanding-window)
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class TranslationRun:
    projections: pd.DataFrame     # per-player (gsis_id) — the NFL-vertical join contract
    bakeoff: BakeoffResult
    notes: list[str] = field(default_factory=list)


def emit_projections(
    pairs: pd.DataFrame,
    winner_factory,
    config: TranslationConfig | None = None,
) -> pd.DataFrame:
    """Emit a leakage-safe per-player rookie projection for EVERY bridged player (drafted or UDFA).

    For each draft class Y > seed, the winner is REFIT on labelled pairs from classes < Y (strictly
    prior — the point-in-time discipline), then applied to ALL bridged players in class Y. A UDFA
    (no NFL-outcome label, excluded from training) still gets a college-only projection from the
    fitted line, flagged `is_udfa`. The seed class is not emitted (no strictly-prior map exists).

    `winner_factory()` must return a FRESH unfitted projector of the winning config each call.
    """
    config = config or TranslationConfig()
    data = build_target(pairs, config)
    if config.train_match_confidence:
        train_pool = data[
            data["match_confidence"].isin(config.train_match_confidence) & data["has_target"]
        ]
    else:
        train_pool = data[data["has_target"]]
    classes = sorted(int(y) for y in data["draft_year"].dropna().unique())

    out_rows: list[pd.DataFrame] = []
    for year in classes:
        prior_classes = [c for c in classes if c < year]
        if not prior_classes:
            continue  # the seed / earliest class — no strictly-prior map exists
        train = train_pool[train_pool["draft_year"].isin(prior_classes)]
        if train.empty:
            continue
        model = winner_factory().fit(train)
        cls = data[data["draft_year"] == year].copy()
        mean, sd = model.predict(cls)
        cls["projected_nfl_z"] = mean
        cls["projected_nfl_z_sd"] = sd
        cls["n_prior_classes"] = len(prior_classes)
        cls["n_prior_pairs"] = int(len(train))
        out_rows.append(cls)

    if not out_rows:
        return pd.DataFrame()
    proj = pd.concat(out_rows, ignore_index=True)
    # gsis_id is the NFL-vertical join key + the output grain — a row with no gsis_id cannot be
    # keyed and would collide on the grain (P0.3 leaves a handful of null-gsis_id draft partners,
    # nflverse coverage vintage). Drop them defensively (the mart also filters them; belt + braces).
    n_before = len(proj)
    proj = proj[proj["gsis_id"].notna()].copy()
    if len(proj) < n_before:
        log.warning("dropped %d emitted rows with a null gsis_id (unkeyable for the NFL vertical)",
                    n_before - len(proj))
    proj["sport"] = "ncaaf"
    proj["model_version"] = MODEL_VERSION
    proj["target_metric"] = config.target_metric
    keep = [
        "sport", "gsis_id", "college_athlete_id", "player_name", "position_group", "nfl_position",
        "college", "draft_year", "draft_overall", "draft_round", "is_udfa", "match_confidence",
        "box_production_available", "has_college_prod", "recruit_composite_rating",
        "projected_nfl_z", "projected_nfl_z_sd", "target_metric",
        "n_prior_classes", "n_prior_pairs", "model_version",
    ]
    return proj[[c for c in keep if c in proj.columns]]


def run_college_nfl_translation(
    pairs: pd.DataFrame, config: TranslationConfig | None = None
) -> TranslationRun:
    """End-to-end: bake-off → refit winner → emit per-player leakage-safe rookie projections."""
    config = config or TranslationConfig()
    bake = run_bakeoff(pairs, config)
    w = bake.winner_config
    proj = emit_projections(pairs, lambda: clone_projector(w), config)
    return TranslationRun(projections=proj, bakeoff=bake, notes=list(bake.notes))

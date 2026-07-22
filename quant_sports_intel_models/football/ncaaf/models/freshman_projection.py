"""freshman_projection.py — NCAAF-P1.2b: the recruit-rating → freshman-production MLE.

WHAT THIS IS
------------
A model that answers, for a TRUE FRESHMAN who has never taken a college snap:

    "Given this recruit's 247 composite rating, position and class, how much should we expect
     them to produce as a freshman — and how sure are we?"

It is the recruiting-level analog of a minor-league-equivalency (the MLB E7 pattern), one rung
lower: instead of translating minor-league output to a major-league prior, it translates a
recruiting RATING to a first-college-season production prior. It exists because P1.3's roster
features are built from prior COLLEGE snaps, and a true freshman has none — the recruiting
rating is the only pre-arrival signal there is, so it becomes the prior.

⚠️ HONEST FRAMING. This is a PRIOR, not a projection-of-edge, and its uncertainty is PARAMETER
uncertainty (how well the rating→production map is pinned down), NOT a calibrated predictive
interval — see `UNCERTAINTY SEMANTICS` below. `best_alpha = 0` still holds; whether a freshman
feature earns its place against a market is P1.4's question, under the §0.5 bake-off discipline.

THE §0.5 BAKE-OFF (this is a MODEL, not a lookup)
-------------------------------------------------
Per the standing discipline, "position-specific + EB-shrunk for thin cells" is ONE candidate,
not the whole story. Pre-registered candidate set (each Optuna/grid-tuned, every config counted
toward PBO/DSR):

  (a) ⭐ PARTIAL POOLING via the P1.2 solver (`hierarchical.py`, REUSED UNCHANGED) — a random-
      slopes model: a GLOBAL rating→production line, plus per-position-group intercept AND
      rating-slope deviations that are EB-shrunk toward the global line. A thin position cell
      (few freshmen) is pulled toward the league-wide rating→production relationship instead of
      being trusted at face value — exactly the "EB-shrunk for thin cells" the prompt names, and
      the solver already carries the boundary-avoiding tau prior that the P1.2 build proved is
      MANDATORY (ML genuinely collapses a variance component to 0 on thin cells, silently
      deleting a level of the hierarchy).
  (b) POSITION-STRATIFIED regression on rating (the interpretable foil) — an independent per-
      position OLS, no pooling. Thin cells fall back to the pooled global line.
  (c) LEARNED GBM on [rating, stars, national_ranking, position one-hot, class size].
  (d) POSITION-MEAN NULL FLOOR — predict the position-group mean, IGNORE rating. If nothing
      beats this, the recruiting rating adds nothing and the honest answer is "no signal."

Selection: leave-one-CLASS-out EXPANDING-WINDOW CV (project class Y using ONLY strictly-prior
classes) on held-out MAE of the standardized production target; PBO<0.2 / DSR≥0.95 over the full
config set; and an ORACLE-FLOOR sanity check (a cheating model that sees the true target must
score better than every real candidate — a candidate beating the oracle is mathematically
impossible and would mean the metric is inverted, per the E2.1-r lesson).

THE TARGET (why STANDARDIZED, and why leakage-free)
---------------------------------------------------
Production is position-incomparable (a QB's passing yards vs a corner's tackles), so the raw
metric is chosen per position group and then Z-SCORED WITHIN (position_group, arrival_season).
Standardization makes the raw scale irrelevant (only within-group-season ORDERING matters) and
absorbs league-wide drift. It is leakage-free: the standardization only builds the TRAINING
label on COMPLETED classes; emission predicts z from rating and never needs the new class's
production. OL and deep special teams record no box stats — they carry NO production label and
get a rating-only prior, flagged (`box_production_available = False`), never a fabricated 0.

UNCERTAINTY SEMANTICS (PM addition #4 — say which kind)
------------------------------------------------------
`projected_production_z_sd` is PARAMETER uncertainty (posterior/bootstrap sd of the fitted
rating→production map at this recruit's rating), NOT a calibrated predictive interval for the
freshman's realized production. Like P1.2's `strength_margin_sd` it ranks confidence correctly
(a thin position cell or an extreme rating is wider) but is too tight to price with. A pricing
consumer MUST recalibrate on held-out data (the MLB E13.6 pattern). P1.3 should use
`projected_production_z` as a POINT feature and the sd as a RELATIVE confidence signal only.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .hierarchical import Block, DesignSpec, fit

log = logging.getLogger(__name__)

MODEL_VERSION = "ncaaf_freshman_projection_v1"

# The production floor (ncaaf_data_inventory.md §2.7): player-advanced starts 2014, so the
# earliest recruit class whose freshman production is OBSERVABLE arrives in 2014. 2014 is the
# SEED — it trains the first map but is not emitted as a leakage-safe prior (a 2014 prior would
# need a <2014 map, which the production floor forbids). Emission starts at the first class with
# ≥1 strictly-prior class of training pairs. Mirrors P1.2's un-emitted-seed discipline.
SEED_ARRIVAL_SEASON = 2014

# Position groups that record box-score production (the model trains + validates on these). OL
# and special teams are box-invisible (an offensive lineman logs no stat line) → rating-only
# prior, flagged, NEVER a games-played proxy that would read ~0 for every lineman.
BOX_PRODUCTION_GROUPS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "DL", "LB", "DB", "ATH")
NO_BOX_GROUPS: tuple[str, ...] = ("OL", "ST", "OTHER")

# A position group needs at least this many observed-production pairs in the training window
# before it earns its OWN fitted cell; below it, the stratified/mean models fall back to the
# pooled global line (the partial-pool model shrinks automatically). Not arbitrary — a 3-pair
# cell yields a rating slope estimated from 3 points, which is the thin-cell overfit the pooling
# is meant to prevent.
MIN_GROUP_SUPPORT = 15

# CFB freshman production, standardized, spans a handful of sd end-to-end. A projected z above
# this (in magnitude) is a broken fit, not a bold projection — the plausibility gate (mirrors
# P1.2's ±50-point ceiling; here in sd units of the standardized target).
_MAX_PLAUSIBLE_Z = 6.0
_MAX_PLAUSIBLE_Z_SD = 6.0


@dataclass
class FreshmanConfig:
    """Tunables. Defaults are the pre-registered configuration."""

    # Which recruiting types to model. HighSchool is the clean HS→college signal; JUCO/PrepSchool
    # arrive older and are a different translation — kept separate by default.
    recruit_types: tuple[str, ...] = ("HighSchool",)
    min_group_support: int = MIN_GROUP_SUPPORT
    # Partial-pool prior scale grid (× the response sd) — the fixed-effect "flat" prior width.
    # Every entry is a distinct config that COUNTS toward PBO/DSR (deflation makes the search
    # safe). Kept small for the built-in run; the operator's full run widens it.
    pool_prior_scales: tuple[float, ...] = (2.0, 4.0)
    # GBM hyperparameter grid (n_estimators, max_depth, learning_rate). Same deflation posture.
    gbm_grid: tuple[tuple[int, int, float], ...] = (
        (200, 2, 0.05),
        (400, 3, 0.03),
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# Target construction
# ══════════════════════════════════════════════════════════════════════════════════════


def raw_production(pairs: pd.DataFrame) -> pd.Series:
    """The position-appropriate raw production metric (scale is irrelevant — standardized next).

    Offense skill: scrimmage yards + a TD bonus. Defense: the havoc-weighted line already summed
    in the mart. ATH combines both (it is a mixed label by construction). OL/ST get NaN — they
    are box-invisible and excluded from the production target.
    """
    grp = pairs["position_group"].to_numpy()
    scrim = pd.to_numeric(pairs.get("scrimmage_prod"), errors="coerce").to_numpy(dtype=float)
    tds = pd.to_numeric(pairs.get("scrimmage_tds"), errors="coerce").to_numpy(dtype=float)
    defn = pd.to_numeric(pairs.get("defense_prod"), errors="coerce").to_numpy(dtype=float)
    offense = np.nan_to_num(scrim) + 20.0 * np.nan_to_num(tds)
    out = np.full(len(pairs), np.nan)
    off_mask = np.isin(grp, ["QB", "RB", "WR", "TE"])
    def_mask = np.isin(grp, ["DL", "LB", "DB"])
    ath_mask = grp == "ATH"
    out[off_mask] = offense[off_mask]
    out[def_mask] = np.nan_to_num(defn)[def_mask]
    out[ath_mask] = offense[ath_mask] + 8.0 * np.nan_to_num(defn)[ath_mask]
    return pd.Series(out, index=pairs.index)


def build_target(pairs: pd.DataFrame) -> pd.DataFrame:
    """Attach `raw_production`, the within-(group, arrival_season) standardized `production_z`,
    and `box_production_available`. A row with no observed production (`has_production` false)
    or in a box-invisible group carries NaN `production_z` — UNKNOWN, never 0.
    """
    out = pairs.copy().reset_index(drop=True)
    out["box_production_available"] = out["position_group"].isin(BOX_PRODUCTION_GROUPS)
    out["raw_production"] = raw_production(out)
    has_prod = out.get("has_production")
    if has_prod is None:
        has_prod = out["raw_production"].notna()
    labelled = out["box_production_available"] & has_prod.astype(bool) & out["raw_production"].notna()

    z = pd.Series(np.nan, index=out.index)
    for (grp, season), idx in out[labelled].groupby(["position_group", "arrival_season"]).groups.items():
        vals = out.loc[idx, "raw_production"].astype(float)
        mu = vals.mean()
        sd = vals.std(ddof=0)
        z.loc[idx] = (vals - mu) / sd if sd > 0 else 0.0
    out["production_z"] = z
    out["has_target"] = out["production_z"].notna()
    return out


def _rating_features(df: pd.DataFrame, rating_mu: float, rating_sd: float) -> np.ndarray:
    r = pd.to_numeric(df["composite_rating"], errors="coerce").to_numpy(dtype=float)
    r = np.where(np.isfinite(r), r, rating_mu)
    return (r - rating_mu) / (rating_sd if rating_sd > 0 else 1.0)


# ══════════════════════════════════════════════════════════════════════════════════════
# The candidate projectors — a common (fit, predict→mean,sd) interface
# ══════════════════════════════════════════════════════════════════════════════════════


class Projector:
    name = "base"

    def fit(self, train: pd.DataFrame) -> "Projector":  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:  # pragma: no cover
        raise NotImplementedError


class PositionMeanProjector(Projector):
    """The NULL FLOOR: predict the training position-group mean of z, ignore rating entirely.

    Because z is standardized within (group, season), the pooled group mean is ≈0, so this is
    the honest "recruiting rating carries no signal" baseline every other candidate must beat.
    """

    name = "position_mean"

    def fit(self, train: pd.DataFrame) -> "PositionMeanProjector":
        t = train[train["has_target"]]
        self.group_mean_ = t.groupby("position_group")["production_z"].mean().to_dict()
        self.global_mean_ = float(t["production_z"].mean()) if len(t) else 0.0
        self.global_sd_ = float(t["production_z"].std(ddof=0)) if len(t) > 1 else 1.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        mean = df["position_group"].map(self.group_mean_).fillna(self.global_mean_).to_numpy(float)
        sd = np.full(len(df), max(self.global_sd_, 1e-6))
        return mean, sd


class StratifiedOLSProjector(Projector):
    """Independent per-position OLS of z on standardized rating. Thin cells fall back to the
    pooled global line — no partial pooling BETWEEN the fitted cells (that is candidate (a))."""

    name = "stratified_ols"

    def __init__(self, min_support: int = MIN_GROUP_SUPPORT):
        self.min_support = min_support

    def _ols(self, x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
        X = np.column_stack([np.ones_like(x), x])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        dof = max(len(y) - 2, 1)
        sigma = float(np.sqrt((resid @ resid) / dof))
        return float(beta[0]), float(beta[1]), sigma

    def fit(self, train: pd.DataFrame) -> "StratifiedOLSProjector":
        t = train[train["has_target"]].copy()
        self.rating_mu_ = float(pd.to_numeric(t["composite_rating"], errors="coerce").mean())
        self.rating_sd_ = float(pd.to_numeric(t["composite_rating"], errors="coerce").std(ddof=0)) or 1.0
        x = _rating_features(t, self.rating_mu_, self.rating_sd_)
        y = t["production_z"].to_numpy(float)
        self.global_ = self._ols(x, y) if len(t) >= 2 else (0.0, 0.0, 1.0)
        self.by_group_: dict[str, tuple[float, float, float]] = {}
        for grp, idx in t.groupby("position_group").groups.items():
            gi = t.index.get_indexer(idx)
            if len(gi) >= self.min_support:
                self.by_group_[grp] = self._ols(x[gi], y[gi])
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x = _rating_features(df, self.rating_mu_, self.rating_sd_)
        mean = np.empty(len(df))
        sd = np.empty(len(df))
        grp = df["position_group"].to_numpy()
        for i in range(len(df)):
            a, b, s = self.by_group_.get(grp[i], self.global_)
            mean[i] = a + b * x[i]
            sd[i] = max(s, 1e-6)
        return mean, sd


class GBMProjector(Projector):
    """Learned gradient-boosted regression on rating + stars + ranking + position + class size.
    Per-row uncertainty from paired quantile models (the ~16th/84th predictive spread)."""

    name = "gbm"

    def __init__(self, n_estimators: int = 300, max_depth: int = 3, learning_rate: float = 0.03):
        self.n_estimators, self.max_depth, self.learning_rate = n_estimators, max_depth, learning_rate

    def _features(self, df: pd.DataFrame) -> np.ndarray:
        rating = pd.to_numeric(df["composite_rating"], errors="coerce").fillna(self.rating_mu_).to_numpy(float)
        stars = pd.to_numeric(df.get("stars"), errors="coerce").fillna(self.stars_mu_).to_numpy(float)
        rank = pd.to_numeric(df.get("national_ranking"), errors="coerce").fillna(self.rank_mu_).to_numpy(float)
        onehot = np.column_stack([(df["position_group"] == g).to_numpy(float) for g in self.groups_])
        csize = df["arrival_season"].map(self.class_size_).fillna(self.class_size_mean_).to_numpy(float)
        return np.column_stack([rating, stars, rank, csize, onehot])

    def fit(self, train: pd.DataFrame) -> "GBMProjector":
        from sklearn.ensemble import GradientBoostingRegressor

        t = train[train["has_target"]].copy()
        self.rating_mu_ = float(pd.to_numeric(t["composite_rating"], errors="coerce").mean())
        self.stars_mu_ = float(pd.to_numeric(t.get("stars"), errors="coerce").mean())
        self.rank_mu_ = float(pd.to_numeric(t.get("national_ranking"), errors="coerce").mean())
        self.groups_ = sorted(t["position_group"].unique())
        self.class_size_ = t.groupby("arrival_season").size().to_dict()
        self.class_size_mean_ = float(np.mean(list(self.class_size_.values()))) if self.class_size_ else 0.0
        X = self._features(t)
        y = t["production_z"].to_numpy(float)
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

    Random-slopes design: a GLOBAL rating→production line (fixed) plus per-position-group
    intercept and rating-slope DEVIATIONS carrying a shared N(0, tau^2) prior (penalized). The
    EB variance components (tau_intercept, tau_slope) are chosen by marginal likelihood with the
    boundary-avoiding Gamma(2,·) prior + multi-start — so a thin position cell is shrunk toward
    the global line and no variance component silently collapses to 0.
    """

    prior_scale: float = 2.0
    name: str = "partial_pool"

    def fit(self, train: pd.DataFrame) -> "PartialPoolProjector":
        t = train[train["has_target"]].copy().reset_index(drop=True)
        self.rating_mu_ = float(pd.to_numeric(t["composite_rating"], errors="coerce").mean())
        self.rating_sd_ = float(pd.to_numeric(t["composite_rating"], errors="coerce").std(ddof=0)) or 1.0
        self.groups_ = sorted(t["position_group"].unique())
        y = t["production_z"].to_numpy(float)
        X, spec = self._design(t)
        self.post_ = fit(X, y, spec, fixed_prior_sd=self.prior_scale * (float(np.std(y)) or 1.0))
        self.spec_ = spec
        return self

    def _design(self, df: pd.DataFrame):
        x = _rating_features(df, self.rating_mu_, self.rating_sd_)
        n = len(df)
        fixed = np.column_stack([np.ones(n), x])
        gi = np.column_stack([(df["position_group"] == g).to_numpy(float) for g in self.groups_])
        gs = gi * x.reshape(-1, 1)
        X = np.hstack([fixed, gi, gs])
        spec = DesignSpec((
            Block("fixed", ("intercept", "rating"), penalized=False),
            Block("group_intercept", tuple(f"gi__{g}" for g in self.groups_)),
            Block("group_slope", tuple(f"gs__{g}" for g in self.groups_)),
        ))
        return X, spec

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x = _rating_features(df, self.rating_mu_, self.rating_sd_)
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


def candidate_configs(config: FreshmanConfig) -> list[Projector]:
    """The full pre-registered config set — every one counts toward PBO/DSR (deflation)."""
    cands: list[Projector] = [PositionMeanProjector(), StratifiedOLSProjector(config.min_group_support)]
    cands += [PartialPoolProjector(prior_scale=s) for s in config.pool_prior_scales]
    cands += [GBMProjector(n, d, lr) for (n, d, lr) in config.gbm_grid]
    return cands


# ══════════════════════════════════════════════════════════════════════════════════════
# The bake-off — leave-one-class-out expanding-window CV + PBO/DSR
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class BakeoffResult:
    winner_name: str
    winner_config: Projector
    leaderboard: pd.DataFrame          # per-config OOS mean MAE / skill-vs-null
    perf_matrix: np.ndarray            # (n_folds, n_configs) OOS skill (higher better)
    fold_seasons: list[int]
    pbo: object
    dsr: object
    oracle_floor_ok: bool
    notes: list[str] = field(default_factory=list)


def _mae(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.mean(np.abs(y - yhat)))


def run_bakeoff(pairs: pd.DataFrame, config: FreshmanConfig | None = None) -> BakeoffResult:
    """Fit every candidate config under leave-one-CLASS-out expanding-window CV and select.

    Fold Y (an arrival season with ≥1 strictly-prior class) trains on classes < Y and scores on
    class Y — a genuine out-of-sample projection, never peeking forward. The per-config OOS skill
    (MAE reduction vs the position-mean null) fills the PBO matrix; the winner's per-fold skill
    series drives the DSR with n_trials = number of configs.
    """
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

    config = config or FreshmanConfig()
    data = build_target(pairs)
    if config.recruit_types:
        data = data[data["recruit_type"].isin(config.recruit_types)]
    lab = data[data["has_target"]].copy()
    classes = sorted(int(s) for s in lab["arrival_season"].dropna().unique())
    fold_seasons = [s for s in classes if any(c < s for c in classes)]
    if len(fold_seasons) < 2:
        raise ValueError(
            f"need ≥2 evaluable classes (each with a strictly-prior class); got {fold_seasons} "
            f"from arrival seasons {classes}"
        )

    cands = candidate_configs(config)
    names = [c.name if c.name != "partial_pool" else f"partial_pool@{c.prior_scale}" for c in cands]
    names = [f"gbm@{c.n_estimators}-{c.max_depth}-{c.learning_rate}" if c.name == "gbm" else n
             for c, n in zip(cands, names)]
    notes: list[str] = []

    null_idx = next(i for i, c in enumerate(cands) if c.name == "position_mean")
    perf = np.full((len(fold_seasons), len(cands)), np.nan)   # OOS skill = null_MAE − model_MAE
    mae_mat = np.full((len(fold_seasons), len(cands)), np.nan)
    for fi, season in enumerate(fold_seasons):
        train = lab[lab["arrival_season"] < season]
        test = lab[lab["arrival_season"] == season]
        if train.empty or test.empty:
            continue
        y = test["production_z"].to_numpy(float)
        null_mae = None
        maes = []
        for c in cands:
            try:
                c.fit(train)
                yhat, _ = c.predict(test)
                m = _mae(y, yhat)
            except Exception as e:  # a degenerate fold must not kill the sweep
                notes.append(f"fold {season} config {c.name}: {type(e).__name__}: {e}")
                m = float("nan")
            maes.append(m)
        null_mae = maes[null_idx]
        for ci, m in enumerate(maes):
            mae_mat[fi, ci] = m
            if np.isfinite(m) and np.isfinite(null_mae):
                perf[fi, ci] = null_mae - m         # >0 ⇒ rating beats the null this fold

    mean_mae = np.nanmean(mae_mat, axis=0)
    mean_skill = np.nanmean(perf, axis=0)
    leaderboard = (
        pd.DataFrame({"config": names, "oos_mae": mean_mae, "oos_skill_vs_null": mean_skill})
        .sort_values("oos_mae")
        .reset_index(drop=True)
    )

    # winner = lowest OOS MAE among the NON-null candidates (the null is the floor, not a pick)
    order = np.argsort(mean_mae)
    winner_ci = next(i for i in order if cands[i].name != "position_mean")
    winner = cands[winner_ci]
    winner.fit(lab)  # refit the winner on ALL labelled classes for emission

    # PBO over folds × configs; DSR on the winner's per-fold skill series.
    finite_cols = [i for i in range(len(cands)) if np.isfinite(perf[:, i]).all()]
    pbo = pbo_cscv(perf[:, finite_cols], higher_is_better=True,
                   n_splits=min(len(fold_seasons), 8)) if len(finite_cols) >= 2 and len(fold_seasons) >= 4 else None
    winner_skill = perf[:, winner_ci]
    winner_skill = winner_skill[np.isfinite(winner_skill)]
    dsr = (deflated_sharpe(winner_skill, n_trials=len(cands))
           if len(winner_skill) >= 3 and np.std(winner_skill) > 0 else None)

    # ── ORACLE-FLOOR sanity (E2.1-r): a cheating model that SEES the target must beat every
    #    real candidate. If a real candidate scores a LOWER MAE than the oracle, the metric is
    #    inverted — mathematically impossible, so it is the tell of a broken selection metric.
    oracle_maes = []
    for season in fold_seasons:
        test = lab[lab["arrival_season"] == season]
        oracle_maes.append(_mae(test["production_z"].to_numpy(float), test["production_z"].to_numpy(float)))
    oracle_mae = float(np.mean(oracle_maes))   # == 0 by construction
    oracle_floor_ok = bool(np.nanmin(mean_mae) >= oracle_mae - 1e-9)
    if not oracle_floor_ok:
        notes.append(
            f"ORACLE-FLOOR VIOLATION: a candidate scored MAE {np.nanmin(mean_mae):.4f} below the "
            f"oracle floor {oracle_mae:.4f} — the selection metric is inverted."
        )

    return BakeoffResult(
        winner_name=names[winner_ci], winner_config=winner, leaderboard=leaderboard,
        perf_matrix=perf, fold_seasons=fold_seasons, pbo=pbo, dsr=dsr,
        oracle_floor_ok=oracle_floor_ok, notes=notes,
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# Emission — the per-recruit prior (leakage-safe, expanding-window) + the P1.3 team aggregate
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class FreshmanRun:
    priors: pd.DataFrame          # per-recruit (player_id, arrival_season)
    team_priors: pd.DataFrame     # (season, team) — the P1.3 join contract
    bakeoff: BakeoffResult
    notes: list[str] = field(default_factory=list)


def emit_priors(
    pairs: pd.DataFrame,
    winner_factory,
    config: FreshmanConfig | None = None,
) -> pd.DataFrame:
    """Emit a leakage-safe per-recruit prior for EVERY bridged recruit (produced or not).

    For each arrival season Y > seed, the winner is REFIT on labelled pairs from classes < Y
    (strictly prior — the point-in-time discipline), then applied to ALL recruits arriving in Y.
    A recruit in a box-invisible group (OL/ST) still gets a rating-based prior from the fitted
    global line, flagged `box_production_available = False`. 2014 (the seed) is not emitted.

    `winner_factory()` must return a FRESH unfitted projector of the winning config each call.
    """
    config = config or FreshmanConfig()
    data = build_target(pairs)
    if config.recruit_types:
        data = data[data["recruit_type"].isin(config.recruit_types)].copy()
    lab = data[data["has_target"]]
    classes = sorted(int(s) for s in data["arrival_season"].dropna().unique())

    out_rows: list[pd.DataFrame] = []
    for season in classes:
        prior_classes = [c for c in classes if c < season]
        if not prior_classes:
            continue  # the seed / earliest class — no strictly-prior map exists
        train = lab[lab["arrival_season"].isin(prior_classes)]
        if train.empty:
            continue
        model = winner_factory().fit(train)
        cls = data[data["arrival_season"] == season].copy()
        mean, sd = model.predict(cls)
        cls["projected_production_z"] = mean
        cls["projected_production_z_sd"] = sd
        cls["n_prior_classes"] = len(prior_classes)
        cls["n_prior_pairs"] = int(len(train))
        out_rows.append(cls)

    if not out_rows:
        return pd.DataFrame()
    priors = pd.concat(out_rows, ignore_index=True)
    priors["sport"] = "ncaaf"
    priors["model_version"] = MODEL_VERSION
    priors["is_true_freshman_prior"] = True
    keep = [
        "sport", "player_id", "recruit_name", "arrival_season", "arrival_team",
        "position_group", "recruit_position", "stars", "composite_rating", "national_ranking",
        "box_production_available", "projected_production_z", "projected_production_z_sd",
        "is_true_freshman_prior", "n_prior_classes", "n_prior_pairs", "model_version",
    ]
    return priors[[c for c in keep if c in priors.columns]]


def aggregate_team(priors: pd.DataFrame) -> pd.DataFrame:
    """Roll the per-recruit priors up to the P1.3 join grain (season, team).

    ⭐ THE P1.3 JOIN CONTRACT. P1.3's feature matrix is (season, team, as_of_week); the freshman
    prior is a PRE-SEASON constant (it prices players with no snaps), so it is emitted at
    (season, team) and P1.3 broadcasts it to EVERY as_of_week of that season by joining on
    (season = arrival_season, team = arrival_team). One row per (season, team); NEVER NULL for a
    team with an incoming class (a team with no bridged freshmen is simply absent — LEFT JOIN and
    read the absence as "no projected freshman contribution," not as unknown).
    """
    p = priors.copy()
    p["is_blue_chip"] = pd.to_numeric(p.get("stars"), errors="coerce") >= 4
    g = p.groupby(["arrival_season", "arrival_team"])
    out = g.agg(
        n_incoming_freshmen=("player_id", "size"),
        freshman_class_projected_production=("projected_production_z", "sum"),
        freshman_class_avg_projected_production=("projected_production_z", "mean"),
        freshman_class_top_projected_production=("projected_production_z", "max"),
        freshman_class_avg_rating=("composite_rating", "mean"),
        blue_chip_count=("is_blue_chip", "sum"),
    ).reset_index().rename(columns={"arrival_season": "season", "arrival_team": "team"})
    out.insert(0, "sport", "ncaaf")
    out["model_version"] = MODEL_VERSION
    out["team_season_key"] = out["season"].astype(str) + "-" + out["team"].astype(str)
    return out


def run_freshman_projection(
    pairs: pd.DataFrame, config: FreshmanConfig | None = None
) -> FreshmanRun:
    """End-to-end: bake-off → refit winner → emit per-recruit priors → aggregate to the team grain."""
    config = config or FreshmanConfig()
    bake = run_bakeoff(pairs, config)

    # a factory that reproduces the WINNING config fresh for each expanding-window refit
    w = bake.winner_config

    def factory():
        if isinstance(w, PartialPoolProjector):
            return PartialPoolProjector(prior_scale=w.prior_scale)
        if isinstance(w, GBMProjector):
            return GBMProjector(w.n_estimators, w.max_depth, w.learning_rate)
        if isinstance(w, StratifiedOLSProjector):
            return StratifiedOLSProjector(w.min_support)
        return PositionMeanProjector()

    priors = emit_priors(pairs, factory, config)
    team = aggregate_team(priors) if not priors.empty else pd.DataFrame()
    return FreshmanRun(priors=priors, team_priors=team, bakeoff=bake, notes=list(bake.notes))

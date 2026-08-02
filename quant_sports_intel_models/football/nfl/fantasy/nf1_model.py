"""nf1_model.py — NF1 pure model logic: the JOINT LEARNED re-weighting + the matchup-aware weekly leg.

NF1 is the CONSOLIDATION HOME for the NF-D feature set (operator 2026-07-26). Where MVP-1
(`season_projection.py`) layers each NF-D signal as a fixed HEURISTIC scalar (snap-usage → expected
games, mover rescale, env tilt, injury cap — each a hand-tuned blend constant applied in sequence),
NF1 does the JOINT LEARNED re-weighting of that same signal set and adds a genuine per-player-week
matchup-aware projection. Every function here is PURE (numpy/pandas/sklearn in, DataFrame/array out,
NO IO) so the whole model is unit-tested offline against the fast gate; the DuckDB reads, the
walk-forward bake-off orchestration, the S3 landing, and the NF-D3 grade live in `run_nf1.py`.

⚖️ MARKET-BLIND (operator decision 2026-07-26). NF1 consumes ONLY the orthogonal, information-bearing
signals (box-score line, snap/target/carry usage, team-change opportunity, forward-Vegas team
environment, availability, age) — NOT ADP/ECR. The NF-D3 scorecard established that the QB/RB
within-tier gap vs consensus IS the market signal we lack; a market-blind NF1 therefore CANNOT close
that gap by following the market, and does not pretend to — its job is to extract MORE ordering signal
from the orthogonal set than MVP-1's fixed heuristic product does, and to keep the honest-analytics
identity (the edge is the disagreements with the market, per NF-D3). ADP/ECR stay the BENCHMARK only.

⚖️ EDGE-INDEPENDENT (roadmap §0): a PROJECTION product — no PBO/DSR/CLV betting gate. The §0.5 model-
selection DISCIPLINE still applies (≥3 candidate learner classes, walk-forward CV, feature ablation,
pick on the held-out metric, report the search honestly), but the SHIP GATE is: (a) beat the MVP-1
incumbent on held-out within-position ρ, (b) honest CALIBRATION of the posterior-predictive interval,
(c) FACE-VALIDITY, (d) close the NF-D3 gap vs consensus (as far as a market-blind model can).

⚠️ E2.1-r DISCRETE-COUNT METRIC HYGIENE (CLAUDE.md §0.5). Fantasy points are a sum of discrete-count
props (receptions, TDs) → coverage targets are biased for a correctly-specified count predictive. So:
  • gate the predictive on RANDOMIZED-PIT FLATNESS (`pit_max_decile_deviation`), keep `calib_80` a
    FLOOR (≥0.80) never a TARGET to minimize distance to;
  • SANITY-CHECK the SELECTION metric against an ORACLE FLOOR (`oracle_ordering_is_the_ceiling`) —
    the realized-outcome oracle must score ≥ every candidate on the ordering metric; a candidate that
    "beats" the oracle is the tell that the metric is inverted.

THE OUTPUT CONTRACT is preserved: NF1 emits the SAME raw-stat-line schema MVP-1 does (MVP-2/NF-C1
rescore the raw line per league). The learned season re-weighting sets the LEVEL (a clamped rescale of
MVP-1's line to the learned prediction — one scalar per player, so the line stays internally
consistent and rescores in any league); MVP-1's line is the SHAPE. Rookies keep the slot-curve model
(they carry no base-season feature row to re-weight).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MODEL_VERSION = "nfl_fantasy_nf1_v1"

# The positions NF1 learns a re-weighting for (FB is folded through the heuristic — too few to fit).
LEARN_POSITIONS = ("QB", "RB", "WR", "TE")

# ── The MARKET-BLIND feature contract (the JOINT re-weighting input set). Every column is a realized
#    BASE-season quantity or a leakage-safe FORWARD designation known at projection time — NO ADP/ECR,
#    NO realized-target information. `mvp1_fp` is the strong MVP-1 heuristic prior the learner
#    RE-WEIGHTS against (not a target); the rest are the orthogonal NF-D signals it jointly weights.
# ────────────────────────────────────────────────────────────────────────────────────────────────
FEATURES = (
    "mvp1_fp",         # MVP-1 heuristic season projection (PPR) — the incumbent prior
    "pergame_fp",      # recency-weighted per-game line scored (PPR/g), pre-expected-games
    "base_games",      # base-season games played (durability)
    "expected_games",  # MVP-1 role/usage expected-games estimate
    "snap_share",      # base-season offensive snap share (RB/WR volume-earner signal)
    "target_share",    # base-season target share (receiving role)
    "carry_share",     # base-season carry share (rushing role)
    "depth_rank",      # forward depth-chart rank (role)
    "mover_scale",     # NF-D2 slice-3 team-change opportunity multiplier (1.0 = stayer)
    "team_env",        # NF-D4 forward-Vegas team environment (win-total × Week-1 z-blend)
    "injury_cap_ratio",  # NF-D2 slice-5 availability games ratio (1.0 = no cap; <1 = shelved)
    "age",             # player age at the projection season (the aging-curve term MVP-1 lacked)
    "fp_sd",           # base-season game-to-game PPR sd
)

# NF3.4 — plain-language labels for the transparency panel. One short phrase per feature, written for
# a drafter with no modelling background. Keys must cover every entry in FEATURES (pinned by a test).
FEATURE_LABELS: dict[str, str] = {
    "mvp1_fp": "Our baseline heuristic projection",
    "pergame_fp": "Recent per-game scoring pace",
    "base_games": "Games played last season",
    "expected_games": "Expected games this season (health/role)",
    "snap_share": "Snap share (playing time)",
    "target_share": "Target share (receiving role)",
    "carry_share": "Carry share (rushing role)",
    "depth_rank": "Depth-chart standing",
    "mover_scale": "Team-change opportunity",
    "team_env": "Team offensive environment (Vegas win total)",
    "injury_cap_ratio": "Injury / availability risk",
    "age": "Player age",
    "fp_sd": "Week-to-week scoring volatility",
}

# NF3.4 — one-sentence plain-language definitions, surfaced on hover/tap next to each driver in the
# transparency panel (the same job GLOSSARY does for the boards' VOR/ADP/tier terms). Keys must cover
# every entry in FEATURES (pinned by the same test as FEATURE_LABELS).
FEATURE_DESCRIPTIONS: dict[str, str] = {
    "mvp1_fp": "Our own baseline heuristic projection — NF1's starting point before weighing anything "
               "else below.",
    "pergame_fp": "Points per game over his most recent games, weighted toward the latest ones — how "
                  "well he's scoring right now, before accounting for how many games he's expected to "
                  "play.",
    "base_games": "How many games he actually played last season — more games played is a stronger "
                  "signal than a small sample.",
    "expected_games": "Our own estimate of how many games he's projected to play this season, based "
                      "on his role and recent availability.",
    "snap_share": "The share of his team's offensive snaps he played — how big a role he holds on the "
                  "field.",
    "target_share": "The share of his team's pass targets thrown his way — his role in the passing "
                    "game.",
    "carry_share": "The share of his team's rushing attempts he gets — his role in the running game.",
    "depth_rank": "Where he sits on his team's depth chart at his position — starter vs. backup.",
    "mover_scale": "An adjustment for players who changed teams — a new opportunity, or a lost one, "
                   "with a different roster around him.",
    "team_env": "How good his team's offense is expected to be this season, from Vegas win totals — a "
               "rising tide that lifts every skill player on that offense.",
    "injury_cap_ratio": "How much his availability is capped by injury risk — 1.0 means no cap; lower "
                        "means games are expected to be missed.",
    "age": "The player's age — older players carry more decline risk, younger players carry more "
          "unproven-role uncertainty.",
    "fp_sd": "How much his fantasy scoring bounces around week to week — a volatile player vs. a "
             "consistent one.",
}

# A learned rescale of the MVP-1 line is clamped so a single feature-driven prediction can never
# produce a physically implausible line — the same discipline as the mover/env scalar clamps.
_RESCALE_LO, _RESCALE_HI = 0.55, 1.75


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Candidate learners — each predicts realized next-season PPR from the market-blind feature set.
# The §0.5 bake-off runs ≥3 classes (+ the heuristic null) through walk-forward CV and picks on the
# held-out ordering metric. Every learner exposes fit(X, y, pos) / predict(X, pos); predictions are
# a per-player projected PPR LEVEL (the ordering = the prediction).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _prep_matrix(X: pd.DataFrame, feats: tuple[str, ...]) -> np.ndarray:
    """Feature columns → a float matrix (missing columns become all-NaN so a caller can pass a subset
    for a feature-ablation arm). Imputation/standardisation happen inside each learner's fit."""
    cols = []
    for f in feats:
        s = pd.to_numeric(X[f], errors="coerce") if f in X.columns else pd.Series(np.nan, index=X.index)
        cols.append(s.to_numpy(dtype=float))
    return np.column_stack(cols) if cols else np.empty((len(X), 0))


def _col_median(M: np.ndarray) -> np.ndarray:
    """Per-column median over FINITE entries only (0.0 for an all-NaN column). Avoids the
    `np.nanmedian` 'All-NaN slice' RuntimeWarning — an all-NaN feature column is legitimate here (e.g.
    `team_env` before the 2020 game-line floor, in an early training fold), handled by imputing to 0
    so a standardised zero column has no effect on the fit."""
    n_cols = M.shape[1] if M.ndim == 2 else 0
    med = np.zeros(n_cols)
    for j in range(n_cols):
        col = M[:, j]
        finite = col[np.isfinite(col)]
        if finite.size:
            med[j] = float(np.median(finite))
    return med


class _StandardImputer:
    """Median-impute (fit on train) then z-standardise. Kept tiny + dependency-light so the learners
    stay unit-testable without a sklearn Pipeline. A zero-variance / all-NaN column standardises to
    zeros (no effect on the fit)."""

    def fit(self, M: np.ndarray) -> "_StandardImputer":
        self.med_ = _col_median(M) if M.size else np.zeros(M.shape[1])
        F = self._impute(M)
        self.mu_ = F.mean(axis=0) if F.size else np.zeros(M.shape[1])
        self.sd_ = F.std(axis=0) if F.size else np.ones(M.shape[1])
        self.sd_ = np.where(self.sd_ > 1e-9, self.sd_, 1.0)
        return self

    def _impute(self, M: np.ndarray) -> np.ndarray:
        out = M.copy()
        idx = np.where(~np.isfinite(out))
        if idx[0].size:
            out[idx] = np.take(self.med_, idx[1])
        return out

    def transform(self, M: np.ndarray) -> np.ndarray:
        return (self._impute(M) - self.mu_) / self.sd_


@dataclass
class HeuristicNull:
    """C1 (the incumbent / null): predict = the MVP-1 heuristic projection, unchanged. The bake-off
    baseline every learned candidate's held-out ordering must BEAT to earn a ship. No fit."""

    feats: tuple[str, ...] = FEATURES

    def fit(self, X: pd.DataFrame, y: np.ndarray, pos: np.ndarray) -> "HeuristicNull":
        return self

    def predict(self, X: pd.DataFrame, pos: np.ndarray) -> np.ndarray:
        return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)


@dataclass
class PerPositionRidge:
    """C2: a per-position ridge on the standardised market-blind features → realized PPR. Interpretable
    (the per-position coefficients ARE the joint re-weighting), and the small-data-safe direct-learned
    foil. Position-conditional by construction (a separate fit per position → QB can weight `team_env`
    while WR weights `target_share`)."""

    alpha: float = 10.0
    feats: tuple[str, ...] = FEATURES
    _models: dict = field(default_factory=dict)

    def fit(self, X: pd.DataFrame, y: np.ndarray, pos: np.ndarray) -> "PerPositionRidge":
        from sklearn.linear_model import Ridge

        self._models = {}
        for p in LEARN_POSITIONS:
            m = pos == p
            if m.sum() < 20:
                continue
            imp = _StandardImputer().fit(_prep_matrix(X[m], self.feats))
            F = imp.transform(_prep_matrix(X[m], self.feats))
            reg = Ridge(alpha=self.alpha).fit(F, y[m])
            self._models[p] = (imp, reg)
        return self

    def predict(self, X: pd.DataFrame, pos: np.ndarray) -> np.ndarray:
        out = pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)  # fallback = incumbent
        for p, (imp, reg) in self._models.items():
            m = pos == p
            if m.any():
                out[m] = reg.predict(imp.transform(_prep_matrix(X[m], self.feats)))
        return np.clip(out, 0.0, None)


@dataclass
class PerPositionElasticNet:
    """C3: a per-position elastic-net — the same interpretable per-position blend as C2 but with L1
    sparsity, so a collinear/weak signal (the NF-D2 slice-2 lesson — advanced efficiency re-encodes
    production) is zeroed rather than given spurious weight. alpha + l1_ratio are Optuna-tuned."""

    alpha: float = 0.5
    l1_ratio: float = 0.3
    feats: tuple[str, ...] = FEATURES
    _models: dict = field(default_factory=dict)

    def fit(self, X: pd.DataFrame, y: np.ndarray, pos: np.ndarray) -> "PerPositionElasticNet":
        from sklearn.linear_model import ElasticNet

        self._models = {}
        for p in LEARN_POSITIONS:
            m = pos == p
            if m.sum() < 20:
                continue
            imp = _StandardImputer().fit(_prep_matrix(X[m], self.feats))
            F = imp.transform(_prep_matrix(X[m], self.feats))
            reg = ElasticNet(alpha=self.alpha, l1_ratio=self.l1_ratio, max_iter=5000).fit(F, y[m])
            self._models[p] = (imp, reg)
        return self

    def predict(self, X: pd.DataFrame, pos: np.ndarray) -> np.ndarray:
        out = pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
        for p, (imp, reg) in self._models.items():
            m = pos == p
            if m.any():
                out[m] = reg.predict(imp.transform(_prep_matrix(X[m], self.feats)))
        return np.clip(out, 0.0, None)


@dataclass
class PooledGBM:
    """C4: a pooled gradient-boosted-tree regressor (LightGBM) with position as a categorical feature
    → realized PPR. The flexible non-linear foil that can find interactions the linear blends can't
    (e.g. team_env × QB, snap_share × depth_rank). Deliberately shallow/regularised — the data is
    small (~350 players × a handful of held-out training seasons), so the honest expectation is that
    it does NOT robustly beat the linear blends; the bake-off decides. Deterministic (fixed seed)."""

    n_estimators: int = 300
    num_leaves: int = 15
    learning_rate: float = 0.03
    min_child_samples: int = 30
    subsample: float = 0.8
    feats: tuple[str, ...] = FEATURES
    _model: object = None
    _feat_cols: tuple = ()

    def _frame(self, X: pd.DataFrame, pos: np.ndarray) -> pd.DataFrame:
        M = _prep_matrix(X, self._feat_cols)
        pos_code = pd.Categorical(pos, categories=list(LEARN_POSITIONS)).codes.astype("int64")
        F = pd.DataFrame(M, columns=list(self._feat_cols))
        F["_pos"] = pos_code
        return F

    def fit(self, X: pd.DataFrame, y: np.ndarray, pos: np.ndarray) -> "PooledGBM":
        import lightgbm as lgb

        self._feat_cols = self.feats
        F = self._frame(X, pos)
        F["_pos"] = F["_pos"].astype("category")   # named categorical → consistent fit/predict schema
        self._model = lgb.LGBMRegressor(
            n_estimators=self.n_estimators, num_leaves=self.num_leaves,
            learning_rate=self.learning_rate, min_child_samples=self.min_child_samples,
            subsample=self.subsample, subsample_freq=1, colsample_bytree=0.9,
            reg_lambda=1.0, random_state=13, n_jobs=1, verbosity=-1,
        )
        self._model.fit(F, y, categorical_feature=["_pos"])
        return self

    def predict(self, X: pd.DataFrame, pos: np.ndarray) -> np.ndarray:
        F = self._frame(X, pos)
        F["_pos"] = F["_pos"].astype("category")
        return np.clip(self._model.predict(F), 0.0, None)


# Registry: the pre-registered candidate set for the §0.5 bake-off. `make_learner(name, **hp)` builds
# a fresh instance so the walk-forward loop re-fits per fold. HeuristicNull is the baseline (index 0).
LEARNER_REGISTRY = {
    "heuristic_null": HeuristicNull,
    "ridge": PerPositionRidge,
    "elasticnet": PerPositionElasticNet,
    "gbm": PooledGBM,
}


def make_learner(name: str, feats: tuple[str, ...] = FEATURES, **hp):
    cls = LEARNER_REGISTRY[name]
    return cls(feats=feats, **hp)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF3.4 — feature-importance transparency (the model's own drivers, MODEL-level not per-player)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: excluded from the displayed "top drivers" list — `mvp1_fp` is NF1's incumbent-prior FEATURE (the
#: served MVP-1 heuristic's own output, fed back in as one of NF1's 13 inputs), and it dominates every
#: position's importance (62-80%, measured) precisely because NF1 is a re-weighting OF that prior, not
#: an independent signal a drafter can act on. Reporting "our own baseline projection" as the #1
#: "driver" of a signal-weighting panel is circular, not informative — the story's own example
#: ("snap share, age, prior-year efficiency") is about the REFINEMENT signals, not the restated prior.
#: `baseline_pct` on the report carries its true share so nothing is hidden, just not top-ranked.
_TAUTOLOGICAL_FEATURES = ("mvp1_fp",)


def _normalize_top(raw: dict[str, float], top_n: int, exclude: tuple[str, ...] = ()) -> list[dict]:
    """`{feature -> raw importance}` → the top-N as `[{feature, label, pct}]`, percentages of the
    FULL set's total INCLUDING any excluded features (so truncating/excluding never inflates what's
    shown — a dropped feature's share just isn't displayed, rather than being redistributed onto the
    ones that are)."""
    total = sum(v for v in raw.values() if v > 0)
    ranked = sorted(
        ((f, v) for f, v in raw.items() if f not in exclude), key=lambda kv: kv[1], reverse=True
    )[:top_n]
    return [
        {"feature": f, "label": FEATURE_LABELS.get(f, f),
         "pct": round(100.0 * v / total, 1) if total > 0 else 0.0}
        for f, v in ranked if v > 0
    ]


def feature_importance_report(
    pool: pd.DataFrame,
    hp: dict,
    feats: tuple[str, ...] = FEATURES,
    positions: tuple[str, ...] = LEARN_POSITIONS,
    top_n: int = 6,
    n_repeats: int = 20,
    seed: int = 13,
) -> dict:
    """Fit the NF1 GBM (the §0.5 bake-off winner — see `nf1_season_bakeoff.json`) on `pool` and report
    which signals it leans on: GLOBALLY (LightGBM's own gain-based split importance, across every
    position pooled) and PER POSITION (permutation importance — how much shuffling one feature within
    a position's own rows degrades the FITTED model's accuracy for that position specifically).

    🚨 MODEL-LEVEL, NOT PER-PLAYER: every number here describes the FITTED MODEL's aggregate
    sensitivity to a signal for a position as a whole — never an attribution of any individual
    player's own projection (that would need a per-player method, e.g. SHAP, which this is not).
    Callers must label it accordingly (NF3.4's honest-labelling crux).

    NF1 is the validated, market-blind re-weighting of the SAME signal set MVP-1's
    served heuristic pipeline is built from (see the module docstring) — it is the one model in this
    package that is actually fitted with a genuine `.feature_importances_`, so it is what this panel
    describes. It is NOT necessarily the exact mechanism behind the specific number MVP-1 serves for
    any one player today; the panel is a description of what the underlying signals are worth to a
    validated model over the same feature set, not a live attribution of the served projection."""
    learner = PooledGBM(feats=feats, **hp)
    y = pd.to_numeric(pool["real_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = np.array([str(p) for p in pool["position"]], dtype=object)
    learner.fit(pool, y, pos)
    model = learner._model
    F = learner._frame(pool, pos)
    F["_pos"] = F["_pos"].astype("category")

    booster = model.booster_
    gains = dict(zip(booster.feature_name(), booster.feature_importance(importance_type="gain")))
    global_raw = {f: float(gains.get(f, 0.0)) for f in feats}
    global_total = sum(v for v in global_raw.values() if v > 0)
    global_importance = _normalize_top(global_raw, top_n, exclude=_TAUTOLOGICAL_FEATURES)
    global_baseline_pct = (round(100.0 * global_raw.get("mvp1_fp", 0.0) / global_total, 1)
                           if global_total > 0 else 0.0)

    from sklearn.inspection import permutation_importance

    per_position: dict[str, list[dict]] = {}
    baseline_pct: dict[str, float] = {}
    for p in positions:
        m = pos == p
        if int(m.sum()) < 20:
            continue
        result = permutation_importance(
            model, F[m], y[m], scoring="neg_mean_squared_error",
            n_repeats=n_repeats, random_state=seed,
        )
        raw = {f: max(float(result.importances_mean[i]), 0.0)
               for i, f in enumerate(F.columns) if f in feats}
        raw_total = sum(v for v in raw.values() if v > 0)
        per_position[p] = _normalize_top(raw, top_n, exclude=_TAUTOLOGICAL_FEATURES)
        baseline_pct[p] = (round(100.0 * raw.get("mvp1_fp", 0.0) / raw_total, 1)
                           if raw_total > 0 else 0.0)

    return {
        "model_version": MODEL_VERSION,
        "method": "LightGBM gain importance (global, pooled across positions); permutation importance "
                  "vs held-in-sample squared error (per position, evaluated on the fitted model)",
        "n_pool": int(len(pool)),
        # the share of importance NF1 keeps on its own incumbent-prior feature (mvp1_fp) — not shown
        # in `global`/`positions` (see _TAUTOLOGICAL_FEATURES) but disclosed here so nothing is hidden.
        "baseline_pct": global_baseline_pct,
        "global": global_importance,
        "positions": per_position,
        "positions_baseline_pct": baseline_pct,
    }


def player_feature_contributions(
    fitted_model,
    F: pd.DataFrame,
    player_ids,
    feats: tuple[str, ...] = FEATURES,
    top_n: int = 6,
    min_pts: float = 0.05,
) -> dict[str, dict]:
    """Per-PLAYER contributions — how many fantasy points each signal is estimated to add or subtract
    for THIS player specifically, via LightGBM's exact TreeSHAP (`pred_contrib=True`; no external `shap`
    dependency — it's built into the booster). This is the genuine per-player method the story's own
    honest-labelling note calls out as the alternative to a model-level description; unlike
    `feature_importance_report` (a position-level aggregate), a player's contributions here sum
    EXACTLY to his own NF1 prediction — verified: `contrib.sum(axis=1) == fitted_model.predict(F)` to
    floating-point precision.

    `fitted_model` must be the already-`.fit()`-ted `PooledGBM._model` (an `lgb.LGBMRegressor`); `F`
    must be the matching `PooledGBM._frame(X, pos)` output (features + `_pos` categorical, in the
    SAME column order the model was fit on — mismatched columns would silently mislabel contributions,
    which is why this takes the frame directly rather than rebuilding it, so the caller's `_frame` call
    is the single source of truth for both fit and predict).

    🚨 STILL NF1, NOT THE SERVED NUMBER: `total_pts` is NF1's OWN prediction for this player — a
    validated research-model estimate, not necessarily equal to the served MVP-1 projection shown
    elsewhere on the page (NF1 sets the served ORDERING, not the served LEVEL — see
    `apply_learned_ordering`). Callers must show `total_pts` as our research model's separate estimate,
    never silently relabel it as "his projection." `mvp1_fp`'s own contribution is folded into
    `baseline_pts` (with the model's bias/expected-value term) rather than listed as a "driver" — it's
    the model's OWN starting estimate for him, not an independent signal a drafter can act on (same
    reasoning as `_TAUTOLOGICAL_FEATURES` in `feature_importance_report`)."""
    booster = fitted_model.booster_
    contrib = booster.predict(F, pred_contrib=True)
    names = list(F.columns)                              # matches contrib's column order + a bias col
    bias = contrib[:, -1]
    vals = contrib[:, :-1]
    out: dict[str, dict] = {}
    for i, pid in enumerate(player_ids):
        row = dict(zip(names, vals[i]))
        baseline = float(row.get("mvp1_fp", 0.0)) + float(bias[i])
        total = float(vals[i].sum() + bias[i])
        others = {f: float(row.get(f, 0.0)) for f in feats if f not in _TAUTOLOGICAL_FEATURES}
        ranked = sorted(others.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
        out[str(pid)] = {
            "baseline_pts": round(baseline, 1),
            "total_pts": round(total, 1),
            "drivers": [{"feature": f, "pts": round(v, 1)} for f, v in ranked if abs(v) >= min_pts],
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Rescale the MVP-1 raw line to the learned level (preserves the raw-line contract)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_RAW_SCALE_COLS = (
    "proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td",
)


def apply_learned_ordering(mvp1: pd.DataFrame, learned_score: np.ndarray,
                           positions: tuple = LEARN_POSITIONS,
                           lo: float = 0.30, hi: float = 3.5) -> pd.DataFrame:
    """Apply the learned model as an ORDERING within each position, PRESERVING MVP-1's calibrated
    point-level distribution (a within-position quantile remap — the `blend_adp_prior` mechanism).

    ⭐ WHY (the E2.1-r discrimination-vs-pricing lesson): the §0.5 bake-off validated the learner's
    ORDERING (held-out within-position ρ), NOT its absolute LEVEL. The learner trains on `real_fp_ppr`
    of players who actually played ≥6 games — a SURVIVORSHIP-selected level systematically ABOVE
    MVP-1's risk-adjusted projection (which discounts for expected-games/injury). Using that inflated
    level to rescale the line saturates the clamp and SCRAMBLES the very ordering the bake-off picked.
    So NF1 trusts the learner for RANK and keeps MVP-1's calibrated LEVEL: within each position the
    players are reordered by the learned score and handed that position's own MVP-1 projected-points
    MULTISET in descending order (a monotone remap → the within-position rank == the learned rank
    EXACTLY, so the shipped ordering IS the validated bake-off ordering; the point scale + the
    calibrated season interval stay MVP-1's). Then each raw line is rescaled to its assigned level so
    the raw-line contract holds (NF-C1 rescores it in any league). The clamp is wide (a legitimate
    within-multiset promotion can be large) but bounded to guard a degenerate line.

    Rows outside `positions` (FB / rookies handled elsewhere) keep their MVP-1 line. A position with
    <2 players is a no-op."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as _SP
    out = mvp1.copy()
    base = _SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)
    remapped = base.copy()
    pos = np.array([(p or "").upper() for p in out["position"]], dtype=object)
    score = np.asarray(learned_score, dtype=float)
    for p in positions:
        idx = np.where(pos == p)[0]
        if len(idx) < 2:
            continue
        s = score[idx]
        s = np.where(np.isfinite(s), s, -np.inf)          # unscored players sink to the bottom
        order = idx[np.argsort(-s, kind="stable")]        # best learned score first
        remapped[order] = np.sort(base[idx])[::-1]        # this position's own point multiset, desc
    return apply_learned_level(out, remapped, lo=lo, hi=hi)


def apply_learned_level(mvp1: pd.DataFrame, learned_fp: np.ndarray, fp_col: str = "proj_fp_ppr",
                        lo: float = _RESCALE_LO, hi: float = _RESCALE_HI) -> pd.DataFrame:
    """Rescale each MVP-1 raw stat line so its scored PPR equals the LEARNED projection (clamped).

    Scoring is linear in the stats, so one scalar per player = `clamp(learned_fp / scored_line, lo, hi)`
    keeps the line internally consistent (it rescores to the learned level in ANY league) and physically
    plausible (the clamp guards the tail exactly as the mover/env scalars do). The BASE is the line's
    OWN scored PPR (via `season_projection.score_line`, the rookie rescale-to-target pattern) so the
    output rescores EXACTLY to target, independent of any stale `proj_fp_ppr` on the row. The `_fp_*`
    convenience columns are recomputed by the caller via `score_line`. Rows whose line scores to ~0 are
    left unchanged (no basis to rescale). Returns a copy with `_RAW_SCALE_COLS` rescaled + `nf1_scale`."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as _SP
    out = mvp1.copy()
    if any(c in out.columns for c in _RAW_SCALE_COLS):
        base = _SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)
    else:
        base = pd.to_numeric(out.get(fp_col, np.nan), errors="coerce").to_numpy(dtype=float)
    learned = np.asarray(learned_fp, dtype=float)
    scale = np.where(base > 1e-6, np.clip(learned / np.where(base > 1e-6, base, 1.0), lo, hi), 1.0)
    scale = np.where(np.isfinite(scale), scale, 1.0)
    for c in _RAW_SCALE_COLS:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").to_numpy(dtype=float) * scale
    # re-clamp the internal consistency invariants the line must satisfy
    if {"proj_pass_cmp", "proj_pass_att"} <= set(out.columns):
        out["proj_pass_cmp"] = np.minimum(out["proj_pass_cmp"], out["proj_pass_att"])
    if {"proj_rec", "proj_targets"} <= set(out.columns):
        out["proj_rec"] = np.minimum(out["proj_rec"], out["proj_targets"])
    if {"proj_rush_att", "proj_rec"} <= set(out.columns):
        out["proj_fumbles_lost"] = np.round(
            (pd.to_numeric(out["proj_rush_att"], errors="coerce").to_numpy()
             + pd.to_numeric(out["proj_rec"], errors="coerce").to_numpy()) * 0.006, 2)
    out["nf1_scale"] = np.round(scale, 4)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ordering metrics + E2.1-r hygiene
# ══════════════════════════════════════════════════════════════════════════════════════════════
def within_position_rho(df: pd.DataFrame, score_col: str, real_col: str = "real_fp_ppr",
                        positions: tuple = LEARN_POSITIONS, min_n: int = 10) -> tuple[dict, float | None]:
    """Per-position Spearman(score, realized) + the position-pooled mean — the within-tier ORDERING
    metric that wins drafts (the NF-D3 gap). Returns ({pos: rho}, pooled_mean)."""
    per = {}
    for p in positions:
        d = df[df["position"] == p]
        if len(d) < min_n:
            continue
        a, b = pd.to_numeric(d[score_col], errors="coerce"), pd.to_numeric(d[real_col], errors="coerce")
        if a.std() == 0 or b.std() == 0:
            continue
        per[p] = round(float(a.corr(b, method="spearman")), 4)
    pooled = round(float(np.mean(list(per.values()))), 4) if per else None
    return per, pooled


def oracle_ordering_is_the_ceiling(df: pd.DataFrame, candidate_cols: list[str],
                                   real_col: str = "real_fp_ppr") -> bool:
    """E2.1-r ORACLE FLOOR guard — the realized-outcome oracle (score == realized) must order at ρ=1
    within every position, so NO candidate's pooled within-position ρ may exceed it. A candidate that
    "beats" the oracle is mathematically impossible ⇒ the tell that the ordering metric is inverted.
    Returns True when every candidate scores ≤ the oracle (the metric is sane)."""
    _, oracle = within_position_rho(df.assign(_oracle=df[real_col]), "_oracle", real_col)
    if oracle is None:
        return True
    for c in candidate_cols:
        _, pooled = within_position_rho(df, c, real_col)
        if pooled is not None and pooled > oracle + 1e-9:
            return False
    return True


def randomized_pit(y: np.ndarray, cdf_at_y: np.ndarray, cdf_below_y: np.ndarray,
                   rng: np.random.Generator | None = None) -> np.ndarray:
    """Randomized PIT for a (semi-)discrete predictive: u ~ Uniform(F(y⁻), F(y)) per observation. A
    correctly-specified predictive yields u ~ Uniform(0,1). For a continuous predictive pass
    cdf_below_y == cdf_at_y (→ u == F(y), the ordinary PIT). Deterministic when `rng` is seeded."""
    rng = rng or np.random.default_rng(7)
    lo = np.clip(np.asarray(cdf_below_y, dtype=float), 0.0, 1.0)
    hi = np.clip(np.asarray(cdf_at_y, dtype=float), 0.0, 1.0)
    hi = np.maximum(hi, lo)
    return lo + (hi - lo) * rng.random(len(y))


def pit_max_decile_deviation(pit: np.ndarray) -> float:
    """FLATNESS of the PIT histogram = max |observed_decile_frac − 0.10| over 10 equal bins. 0 = a
    perfectly uniform (well-calibrated) predictive; the E2.1-r flatness gate for a discrete count
    predictive (a coverage number alone is biased). Lower = flatter = better."""
    pit = np.asarray(pit, dtype=float)
    pit = pit[np.isfinite(pit)]
    if len(pit) < 10:
        return float("nan")
    counts, _ = np.histogram(np.clip(pit, 0, 1), bins=10, range=(0, 1))
    return float(np.max(np.abs(counts / len(pit) - 0.10)))


def calib_coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Empirical coverage = fraction of realized y inside [lo, hi]. Kept as a FLOOR (≥ nominal), never
    a target to minimise distance to (E2.1-r: inclusive interval bounds inflate a correct count model's
    coverage → distance-to-nominal rewards under-dispersion)."""
    y, lo, hi = np.asarray(y, float), np.asarray(lo, float), np.asarray(hi, float)
    m = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return float(np.mean((y[m] >= lo[m]) & (y[m] <= hi[m]))) if m.any() else float("nan")


def calibrate_dispersion(resid: np.ndarray, base_sd: np.ndarray, target_cov: float = 0.80,
                         z: float = 1.2815515594) -> float:
    """Find the multiplier κ on `base_sd` so the central `target_cov` interval [μ ± z·κ·sd] achieves AT
    LEAST `target_cov` empirical coverage on the holdout residuals — a FLOOR search (the smallest κ
    whose coverage ≥ target), not a distance-minimiser. `resid` = realized − predicted; `base_sd` = the
    model's raw predictive sd. Returns κ (clamped to [0.5, 4.0]); 1.0 when inputs are too thin."""
    resid, base_sd = np.asarray(resid, float), np.asarray(base_sd, float)
    m = np.isfinite(resid) & np.isfinite(base_sd) & (base_sd > 1e-9)
    if m.sum() < 20:
        return 1.0
    r, s = resid[m], base_sd[m]
    grid = np.linspace(0.5, 4.0, 141)
    for k in grid:
        cov = np.mean(np.abs(r) <= z * k * s)
        if cov >= target_cov:
            return float(round(k, 3))
    return 4.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Matchup-aware WEEKLY leg — defense-vs-position × game environment × home, posterior-predictive
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Empirical-Bayes shrink strength for the as-of defense-vs-position factor: a defense with few games
# this season is pulled toward the neutral 1.0 (a small early-season sample is mostly prior).
_DVP_SHRINK_GAMES = 4.0
# Clamp the multiplicative adjustments to keep a weekly line face-valid (a matchup is a tilt, not a
# regime change). DVP is the widest (a genuinely elite/awful defense-vs-position matters).
_DVP_CLAMP = (0.72, 1.35)
_ENV_CLAMP = (0.80, 1.25)
_HOME_BOOST = 1.02   # a small, well-documented home-field production nudge


def defense_vs_position_factor(allowed: pd.DataFrame, league_mean: pd.DataFrame,
                               shrink_games: float = _DVP_SHRINK_GAMES) -> pd.DataFrame:
    """The as-of DEFENSE-VS-POSITION multiplier: how much a defense inflates/suppresses fantasy points
    to a position vs the league-average defense, EB-shrunk by the defense's sample size.

    PURE over supplied AS-OF aggregates (the caller assembles them leakage-safely — only weeks strictly
    BEFORE the target week, plus a prior-season prior):
      `allowed`      : one row per (defense_team, position) — `fp_allowed_pg` (mean PPR allowed per
                       game to that position) + `def_games` (games in the as-of window).
      `league_mean`  : one row per position — `lg_fp_allowed_pg` (league-average PPR allowed/g).
    factor = 1 + w·(fp_allowed_pg / lg − 1), w = def_games / (def_games + shrink_games), clamped.
    Returns [defense_team, position, dvp_factor]. A defense/position with no as-of data → 1.0 (neutral).
    """
    m = allowed.merge(league_mean, on="position", how="left")
    lg = pd.to_numeric(m["lg_fp_allowed_pg"], errors="coerce").to_numpy(dtype=float)
    ap = pd.to_numeric(m["fp_allowed_pg"], errors="coerce").to_numpy(dtype=float)
    g = pd.to_numeric(m["def_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ratio = np.where(lg > 1e-6, ap / np.where(lg > 1e-6, lg, 1.0), 1.0)
    w = g / (g + shrink_games)
    factor = 1.0 + w * (ratio - 1.0)
    factor = np.where(np.isfinite(factor), factor, 1.0)
    out = m[["defense_team", "position"]].copy()
    out["dvp_factor"] = np.clip(factor, *_DVP_CLAMP)
    return out


def environment_factor(implied_team_points: np.ndarray, league_avg_points: float,
                       clamp: tuple = _ENV_CLAMP) -> np.ndarray:
    """The game-environment multiplier from the week's implied TEAM points (total/2 ± spread/2, a
    leakage-safe pre-game read): factor = clamp(implied / league_avg). A team favoured to score more
    lifts every skill player's expected weekly production; the clamp keeps it a tilt. league_avg ≈ 22.5
    (half a ~45-point NFL total). Neutral (1.0) where the implied points are unknown."""
    ip = np.asarray(implied_team_points, dtype=float)
    lg = league_avg_points if league_avg_points and league_avg_points > 1e-6 else 22.5
    factor = np.where(np.isfinite(ip), ip / lg, 1.0)
    return np.clip(factor, *clamp)


@dataclass
class WeeklyConfig:
    """Which matchup adjustments the weekly leg applies (the §0.5 weekly ablation toggles these). All
    ON = the full matchup-aware model; all OFF = the flat season-per-game baseline (the null arm)."""

    use_dvp: bool = True
    use_env: bool = True
    use_home: bool = True


def project_week(per_game_fp: np.ndarray, per_game_sd: np.ndarray, *, dvp: np.ndarray | None = None,
                 env: np.ndarray | None = None, is_home: np.ndarray | None = None,
                 cfg: WeeklyConfig = WeeklyConfig(), z: float = 1.2815515594) -> pd.DataFrame:
    """The matchup-aware weekly posterior-predictive point projection for one player-week set.

    μ_week = season per-game mean × DVP(opponent, position) × ENV(implied team pts) × home — each a
    leakage-safe multiplicative tilt (toggled by `cfg`). The predictive is a truncated-Normal on a
    non-negative fantasy total: mean μ_week, sd = per-game game-to-game sd (the realized week-to-week
    scoring dispersion), floored at 0. Returns [week_fp, week_sd, week_p10, week_p90] — an honest 80%
    weekly interval (the E2.1-r calibration is applied by the caller via `calibrate_dispersion`).

    Uncertainty type = EMPIRICAL (from the player's realized game-to-game variance), stated by the
    caller. A missing adjustment array or a cfg toggle OFF ⇒ that factor is 1.0 (no-op)."""
    mu = np.asarray(per_game_fp, dtype=float).copy()
    n = len(mu)
    one = np.ones(n)
    fd = (np.asarray(dvp, float) if (cfg.use_dvp and dvp is not None) else one)
    fe = (np.asarray(env, float) if (cfg.use_env and env is not None) else one)
    fh = (np.where(np.asarray(is_home, float) > 0, _HOME_BOOST, 1.0)
          if (cfg.use_home and is_home is not None) else one)
    mu = mu * np.where(np.isfinite(fd), fd, 1.0) * np.where(np.isfinite(fe), fe, 1.0) * fh
    mu = np.clip(mu, 0.0, None)
    sd = np.clip(np.asarray(per_game_sd, dtype=float), 0.0, None)
    return pd.DataFrame({
        "week_fp": np.round(mu, 2),
        "week_sd": np.round(sd, 2),
        "week_p10": np.round(np.clip(mu - z * sd, 0.0, None), 2),
        "week_p90": np.round(mu + z * sd, 2),
    })


def _gamma_shape_scale(mu: np.ndarray, sd: np.ndarray):
    """Method-of-moments Gamma(k, θ) from a target mean μ + sd σ: k = (μ/σ)², θ = σ²/μ. Weekly fantasy
    points are non-negative + RIGHT-SKEWED, which a Gamma fits far better than a symmetric Normal (the
    E2.1-r point: calibrate the shape the data actually has). Guarded for μ,σ→0."""
    mu = np.clip(np.asarray(mu, float), 1e-3, None)
    sd = np.clip(np.asarray(sd, float), 1e-3, None)
    k = np.clip((mu / sd) ** 2, 0.15, 500.0)
    theta = mu / k
    return k, theta


def gamma_weekly_cdf(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """CDF of the Gamma weekly predictive (mean μ, sd σ via MoM) at y — for the PIT calibration check.
    Realized weekly points below 0 (rare: net-negative QB games) are floored at 0 before evaluation."""
    from scipy.stats import gamma

    k, theta = _gamma_shape_scale(mu, sd)
    return np.clip(gamma.cdf(np.clip(np.asarray(y, float), 0.0, None), a=k, scale=theta), 0.0, 1.0)


def gamma_weekly_interval(mu: np.ndarray, sd: np.ndarray, q_lo: float = 0.10,
                          q_hi: float = 0.90) -> tuple[np.ndarray, np.ndarray]:
    """The (q_lo, q_hi) Gamma weekly credible interval → (p10, p90). Right-skewed + non-negative by
    construction (no cl-at-0 Normal artefact), the honest weekly interval shape."""
    from scipy.stats import gamma

    k, theta = _gamma_shape_scale(mu, sd)
    return gamma.ppf(q_lo, a=k, scale=theta), gamma.ppf(q_hi, a=k, scale=theta)


def truncnorm_cdf(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """CDF of a Normal(mu, sd) truncated at 0 (the weekly fantasy-point predictive), evaluated at y —
    for the PIT calibration check. Vectorised, NaN-safe (a zero sd → a step at mu)."""
    from scipy.stats import norm

    y, mu, sd = np.asarray(y, float), np.asarray(mu, float), np.asarray(sd, float)
    sd = np.where(sd > 1e-9, sd, 1e-9)
    a = (0.0 - mu) / sd            # lower truncation point
    denom = 1.0 - norm.cdf(a)
    denom = np.where(denom > 1e-9, denom, 1e-9)
    cdf = (norm.cdf((y - mu) / sd) - norm.cdf(a)) / denom
    return np.clip(cdf, 0.0, 1.0)

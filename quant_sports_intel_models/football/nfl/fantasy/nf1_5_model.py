"""nf1_5_model.py — NF1.5 pure model logic: the CAPSTONE feature-combination bake-off.

NF1.5 is the LAST season-level story of the NF1 arc (operator 2026-07-27). It has TWO objectives,
prioritised in this order:

  (b) ⭐ PRIMARY — the MARKET-AWARE REFINEMENTS NF1.3 left on the table, the only credible
      remaining season-level lift after the market-blind space was exhausted 4× (NF1 / NF1.1 /
      NF1.2 / NF1.4):
        * BLEND-VS-LEARNED  — NF1.3's `PosMarketBlend` blends the market against the raw MVP-1
          heuristic; the refinement blends it against the LEARNED market-blind score (the NF1.1
          per-position winner, fit in-fold) — if our learned signal is better than MVP-1, the
          blend should anchor on it.
        * DISPERSION-WEIGHTED MARKET — a flat blend weight leans on consensus equally everywhere;
          the refinement makes the per-player weight a function of `market_dispersion` (lean on
          the market only where the experts AGREE, preserve our independent view — the fades —
          where the consensus is soft).
      Both are expressed by ONE candidate class, `PosRefinedBlend` (anchor ∈ {mvp1, learned},
      per-row weight w_i = clip(w − slope·z(dispersion), 0, 1); slope=0 nests NF1.3's flat blend,
      anchor=mvp1+slope=0 IS the NF1.3 incumbent form — the refinements are strict supersets, so
      they can only earn a repoint by using the new structure).

  (a) CEILING-PROOF — the market-BLIND combination sweep over the accumulated feature library
      (NF-D7 xFP, NF-D6 SOS, NF1.2's system/qbcorr/oline/contract/opp/spill), asking the one
      question the piecewise passes could not: does any pre-registered BUNDLE × model-class
      COMBINATION unlock an interaction win? EXPECTED NULL — its value is PROVING the incumbent
      is the library ceiling, not assuming it (the E2.1-r tied-field reading).

🚨 GUARDRAILS (this is the highest multiple-comparisons-risk story in the program):
  * ⛔ NO feature powerset — `BLIND_BUNDLES` is a BOUNDED, hypothesis-driven set of 7 bundles
    (base / +xFP / +environment / +contract / +opportunity / all-skill / kitchen-sink), each
    justified by a specific NF1.2 finding (TE env near-miss, RB contract positive, …).
  * EVERY config (class × bundle × position × Optuna trial × foil arm) counts toward the
    deflation — CSCV-PBO / config-spread / deflated-Sharpe / BH-FDR, NF1.1's kit verbatim.
  * PLACEBO — `placebo_shuffle` permutes realized outcomes within (position, target_season);
    the same search machinery run on the placebo pool must NOT pass the gates (a mirage clears
    the naive gate but not the placebo).
  * Selection on the TOP-TIER metric, incumbent-anchored + oracle-checked (`top_tier_rho`), with
    `safe_spearman` (the NF1.1 small-data NaN landmine); per-position independent; the learned
    score is ORDERING-only downstream (`apply_learned_ordering` — never the level).

🧠 MODEL CLASSES: the NF1.1 winners (ridge / GBM / kNN-similarity) + `PosMLP` (128-64-32-class
small MLP — the operator's DL scan candidate, included to TEST the honest prior that DL overfits
at our sample sizes, one deflated candidate among equals, no exemption) + the incumbent foils.
The GBM auto-discovers interactions — no hand-engineered interaction terms.

🔒 HONEST FRAME: the incumbents to beat are the CURRENT best boards — market-blind MVP-1 (the
fade baseline) for the blind sweep, and the NF1.3 market-aware winner per position for the
refinement pass. A NULL keeps the incumbent and PROVES the ceiling. `best_alpha = 0`.

Every function here is PURE (numpy/pandas/sklearn in, arrays/dicts out, NO IO) so the fast gate
covers the machinery offline; DuckDB/S3 reads, walk-forward orchestration, Optuna, and the
report live in `run_nf1_5.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Reuse the accumulated pure kit VERBATIM: NF1.1 metric/deflation/learners, NF1.2 families,
# NF1.3 market features + blend/market-only classes.
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11
from quant_sports_intel_models.football.nfl.fantasy import nf1_2_model as M12
from quant_sports_intel_models.football.nfl.fantasy import nf1_3_model as M13
from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (  # noqa: F401 — re-export
    FDR_Q,
    PBO_MAX,
    DSR_MIN,
    POSITIONS,
    TOP_N,
    XFP_FEATURES,
    PosGBM,
    PosNull,
    PosRidge,
    PosSimilarity,
    bh_fdr,
    combined_ordering_score,
    config_spread,
    cscv_pbo,
    deflated_sharpe,
    onesided_paired_pvalue,
    oracle_top_tier_is_ceiling,
    position_verdict,
    safe_spearman,
    top_tier_rho,
)
from quant_sports_intel_models.football.nfl.fantasy.nf1_3_model import (  # noqa: F401 — re-export
    MARKET_FEATURES,
    PosMarketBlend,
    PosMarketOnly,
    build_market_features,
    market_coverage,
)
from quant_sports_intel_models.football.nfl.fantasy.nf1_model import (
    _StandardImputer,
    _prep_matrix,
)

MODEL_VERSION = "nfl_fantasy_nf1_5_v1"

_MIN_FIT_ROWS = M11._MIN_FIT_ROWS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 (ceiling-proof) — the pre-registered BLIND BUNDLES (bounded, hypothesis-driven; ⛔ no
# powerset). Each bundle = the NF1 core + a named cluster of the accumulated library.
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Hypotheses: `base` (the NF1 core alone — the pre-xFP floor) · `base_xfp` (the NF1.1 settled
# sets: xFP where it survived — QB/RB/TE) · `base_env` (the ENVIRONMENT cluster — NF1.2's TE
# near-miss: sos+system+qbcorr+spill were ALL positive add-one at TE) · `base_contract` (the
# NF-D8 revealed-belief cluster — RB-positive in NF1.2) · `base_opp` (the air-yards opportunity
# axes) · `all_skill` (skill+environment interactions, no contract) · `kitchen_sink` (everything
# — the GBM interaction-discovery ceiling).
#
# ⭐ NF-D10 (2026-07-31) adds the COACHING-REGIME family and, with it, exactly TWO bundles — the
# pre-registered H-SYSTEM test and its environment-cluster companion — plus `coach` inside
# `kitchen_sink` (which means "everything" by definition):
#   `base_system_coach` — the DIRECT test of the story's hypothesis: the team-rate proxy H-SYSTEM
#                         already had, PLUS the regime change that proxy is definitionally blind
#                         to. Its foil is `base_xfp` (same set minus system+coach) and, for
#                         attribution, NF1.2's `system`-only add-one — so a win here is
#                         attributable to the new data, not to the bundle being bigger.
#   `env_coach`         — `base_env` + coach: does the regime variable add on top of the whole
#                         environment cluster, or is it already priced by pass rate/pace/SOS?
# ⛔ still NOT a powerset — the coach family enters in 3 places, each with a stated hypothesis,
# and every added config counts toward the same PBO/DSR/FDR deflation as the rest of the sweep.
BLIND_BUNDLES: dict[str, tuple[str, ...]] = {
    "base": (),
    "base_xfp": ("xfp",),
    "base_env": ("xfp", "sos", "system", "qbcorr", "spill"),
    "base_contract": ("xfp", "contract", "oline"),
    "base_opp": ("xfp", "opp"),
    "base_system_coach": ("xfp", "system", "coach"),
    "env_coach": ("xfp", "sos", "system", "qbcorr", "spill", "coach"),
    "all_skill": ("xfp", "opp", "sos", "system", "qbcorr", "spill"),
    "kitchen_sink": ("xfp", "opp", "sos", "system", "qbcorr", "spill", "contract", "oline",
                     "coach"),
}


def _core_features(pos: str) -> tuple[str, ...]:
    """The NF1 core per position — NF1.1's settled set MINUS the xFP columns (the `base` floor)."""
    return tuple(f for f in M12.BASE_POSITION_FEATURES[pos] if f not in XFP_FEATURES)


def _xfp_cols(pos: str) -> tuple[str, ...]:
    """The xFP columns as NF1.1 SETTLED them per position (QB gets the rush/luck legs only, WR
    none — that verdict is inherited, not re-litigated)."""
    return tuple(f for f in M12.BASE_POSITION_FEATURES[pos] if f in XFP_FEATURES)


def bundle_features(bundle: str, pos: str) -> tuple[str, ...]:
    """The feature set for one (bundle, position) cell. Families apply per NF1.2's pre-registered
    position map (`_family_cols` — e.g. qbcorr is WR/TE-only, oline QB/RB-only)."""
    feats = list(_core_features(pos))
    for fam in BLIND_BUNDLES[bundle]:
        cols = _xfp_cols(pos) if fam == "xfp" else M12._family_cols(fam, pos)
        feats.extend(c for c in cols if c not in feats)
    return tuple(feats)


def effective_bundles(pos: str) -> dict[str, tuple[str, ...]]:
    """The DEDUPED bundle map for one position: a bundle whose feature set collapses to an
    already-registered one (e.g. WR `base_xfp` == `base`, since NF1.1 nulled xFP at WR) is
    dropped — no duplicate configs padding the search."""
    out: dict[str, tuple[str, ...]] = {}
    seen: set[frozenset] = set()
    for b in BLIND_BUNDLES:
        feats = bundle_features(b, pos)
        key = frozenset(feats)
        if key in seen:
            continue
        seen.add(key)
        out[b] = feats
    return out


# The blind-sweep candidate classes: the NF1.1 three + the DL candidate + the two STRUCTURAL
# candidates added by the 2026-07-27 scope extension (operator): a two-part availability×rate
# decomposition and a rank-objective learner. Different model STRUCTURE, same feature library —
# the axis the feature sweeps could not test.
BLIND_CANDIDATES = ("pos_ridge", "pos_gbm", "pos_similarity", "pos_mlp", "pos_twopart", "pos_rank")


@dataclass
class PosMLP:
    """The small-MLP DL candidate (the operator's 2026-07-27 scan; e.g. 128-64-32). Included as
    ONE deflated candidate to test the honest prior — at dozens-to-hundreds of player-seasons per
    position DL is expected to overfit and LOSE to the tree/ridge incumbents. Standardised inputs,
    fixed seed, early stopping; an unfit/too-thin learner predicts the MVP-1 incumbent."""

    hidden: str = "128-64-32"
    alpha: float = 1.0
    learning_rate_init: float = 1e-3
    feats: tuple[str, ...] = ()
    _fit: tuple | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosMLP":
        import warnings

        from sklearn.exceptions import ConvergenceWarning
        from sklearn.neural_network import MLPRegressor

        if len(X) < _MIN_FIT_ROWS:
            return self
        imp = _StandardImputer().fit(_prep_matrix(X, self.feats))
        F = imp.transform(_prep_matrix(X, self.feats))
        layers = tuple(int(h) for h in self.hidden.split("-"))
        mlp = MLPRegressor(hidden_layer_sizes=layers, alpha=self.alpha,
                           learning_rate_init=self.learning_rate_init,
                           max_iter=500, early_stopping=True, validation_fraction=0.15,
                           n_iter_no_change=20, random_state=13)
        # hitting max_iter with early stopping is an expected, benign outcome for a bounded-budget
        # trial candidate — the warning is pure log spam across a 1000+-fit sweep, not an error
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            mlp.fit(F, np.asarray(y, dtype=float))
        self._fit = (imp, mlp)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
        imp, mlp = self._fit
        return np.clip(mlp.predict(imp.transform(_prep_matrix(X, self.feats))), 0.0, None)


@dataclass
class PosTwoPart:
    """The TWO-PART structural candidate (2026-07-27 scope extension): project the PER-GAME rate
    and GAMES PLAYED as separate models, predict rate × games. The season-total target conflates
    rate skill with availability noise; NF-D2 slice 1 established availability as the channel
    where orthogonal information enters — this class lets each part have its own model. Rate =
    a shallow LightGBM on `real_fp_ppr / real_games`; games = a ridge on the same feature set
    (clipped to [0, 18]). Requires `real_games` on the TRAIN frame (the pool carries it); an
    unfit/too-thin learner predicts the MVP-1 incumbent. Deterministic."""

    n_estimators: int = 200
    num_leaves: int = 7
    learning_rate: float = 0.03
    min_child_samples: int = 15
    reg_lambda: float = 1.0
    games_alpha: float = 10.0
    feats: tuple[str, ...] = ()
    _fit: tuple | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosTwoPart":
        import lightgbm as lgb
        from sklearn.linear_model import Ridge

        if len(X) < _MIN_FIT_ROWS or "real_games" not in X.columns:
            return self
        g = pd.to_numeric(X["real_games"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(g) & (g > 0)
        if ok.sum() < _MIN_FIT_ROWS:
            return self
        rate = np.asarray(y, dtype=float)[ok] / g[ok]
        imp = _StandardImputer().fit(_prep_matrix(X, self.feats))
        F = imp.transform(_prep_matrix(X, self.feats))
        rate_model = lgb.LGBMRegressor(
            n_estimators=self.n_estimators, num_leaves=self.num_leaves,
            learning_rate=self.learning_rate, min_child_samples=self.min_child_samples,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
            reg_lambda=self.reg_lambda, random_state=13, n_jobs=1, verbosity=-1)
        rate_model.fit(pd.DataFrame(F[ok], columns=list(self.feats)), rate)
        games_model = Ridge(alpha=self.games_alpha).fit(F[ok], g[ok])
        self._fit = (imp, rate_model, games_model)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
        imp, rate_model, games_model = self._fit
        F = imp.transform(_prep_matrix(X, self.feats))
        rate = np.clip(rate_model.predict(pd.DataFrame(F, columns=list(self.feats))), 0.0, None)
        games = np.clip(games_model.predict(F), 0.0, 18.0)
        return rate * games


@dataclass
class PosRank:
    """The RANK-OBJECTIVE candidate (2026-07-27 scope extension): LightGBM lambdarank trained
    directly on the within-season ORDERING — the selection metric is top-tier Spearman, but every
    other candidate optimises squared error; this class aligns the training objective with the
    metric. Relevance labels = within-(target_season) quantile grades of realized PPR (16 grades);
    groups = target seasons (falls back to one group when the frame has no `target_season`).
    Deterministic; unfit/too-thin predicts the MVP-1 incumbent."""

    n_estimators: int = 200
    num_leaves: int = 7
    learning_rate: float = 0.05
    min_child_samples: int = 15
    reg_lambda: float = 1.0
    feats: tuple[str, ...] = ()
    _fit: tuple | None = None

    _GRADES = 16

    @staticmethod
    def _grade(y: np.ndarray) -> np.ndarray:
        """Quantile grades 0..15 within one group (ties share by average-rank binning)."""
        y = np.asarray(y, dtype=float)
        order = pd.Series(y).rank(method="average", pct=True).to_numpy()
        return np.clip((order * PosRank._GRADES).astype(int), 0, PosRank._GRADES - 1)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosRank":
        import lightgbm as lgb

        if len(X) < _MIN_FIT_ROWS:
            return self
        imp = _StandardImputer().fit(_prep_matrix(X, self.feats))
        F = pd.DataFrame(imp.transform(_prep_matrix(X, self.feats)), columns=list(self.feats))
        if "target_season" in X.columns:
            seasons = pd.to_numeric(X["target_season"], errors="coerce").fillna(-1).to_numpy()
        else:
            seasons = np.zeros(len(X))
        # lambdarank needs contiguous groups: stable-sort by season, remember the inverse order
        order = np.argsort(seasons, kind="stable")
        y_arr = np.asarray(y, dtype=float)[order]
        s_sorted = seasons[order]
        groups = [int(c) for c in pd.Series(s_sorted).groupby(s_sorted, sort=False).size()]
        labels = np.concatenate([self._grade(y_arr[np.where(s_sorted == s)[0]])
                                 for s in pd.unique(s_sorted)])
        model = lgb.LGBMRanker(
            objective="lambdarank", n_estimators=self.n_estimators, num_leaves=self.num_leaves,
            learning_rate=self.learning_rate, min_child_samples=self.min_child_samples,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
            reg_lambda=self.reg_lambda, random_state=13, n_jobs=1, verbosity=-1)
        model.fit(F.iloc[order], labels, group=groups)
        self._fit = (imp, model)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
        imp, model = self._fit
        F = pd.DataFrame(imp.transform(_prep_matrix(X, self.feats)), columns=list(self.feats))
        return model.predict(F)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 (primary) — the market-aware refinements: PosRefinedBlend
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class AnchorSpec:
    """The pre-registered LEARNED anchor for the blend-vs-learned refinement: the NF1.1 stored
    per-position winner (class + hp + its market-blind feature set), fit IN-FOLD by the blend —
    a fixed incumbent component, not a new search axis."""

    learner: str = "pos_ridge"
    hp: dict = field(default_factory=dict)
    feats: tuple[str, ...] = ()


class _AxisZ:
    """Train-fit median-impute + z-standardise for ONE axis (NaN-safe, degenerate-safe)."""

    def fit(self, v: np.ndarray) -> "_AxisZ":
        v = np.asarray(v, dtype=float)
        fin = v[np.isfinite(v)]
        self.med = float(np.median(fin)) if len(fin) else 0.0
        self.mu = float(fin.mean()) if len(fin) else 0.0
        sd = float(fin.std()) if len(fin) > 1 else 0.0
        self.sd = sd if sd > 1e-12 else 1.0
        return self

    def transform(self, v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        v = np.where(np.isfinite(v), v, self.med)
        return (v - self.mu) / self.sd


@dataclass
class PosRefinedBlend:
    """⭐ The NF1.5 refinement candidate — the two NF1.3 leftovers as ONE nested family:

        w_i   = clip(blend_w − disp_slope · z(market_dispersion_i), 0, 1)
        score = (1 − w_i) · z(anchor_i) + w_i · z(market_score_i)

    * `anchor` = "mvp1" (the NF1.3 posture) or "learned" (the blend-vs-learned refinement — the
      NF1.1 per-position winner fit in-fold on the market-blind base set via `inner`).
    * `disp_slope` = the dispersion-weighted-market refinement: slope > 0 leans MORE on the
      consensus where the experts AGREE (low dispersion → z_disp < 0 → w_i above blend_w) and
      LESS where the consensus is soft (preserving the independent view / the fades).
      slope = 0 recovers the flat blend — NF1.3's incumbent form is a strict special case.
    Standardisation is train-fit (leakage-safe); a player with no market slot median-imputes to
    z ≈ 0 on the market axes → falls back toward the anchor (the NF1.3 posture). Deterministic.
    """

    blend_w: float = 0.5
    disp_slope: float = 0.0
    anchor: str = "mvp1"
    inner: AnchorSpec | None = None
    feats: tuple[str, ...] = ()          # unused (axes are explicit) — registry interface parity
    _fit: dict | None = None

    def _anchor_values(self, X: pd.DataFrame, inner_model) -> np.ndarray:
        if self.anchor == "learned" and inner_model is not None:
            return np.asarray(inner_model.predict(X), dtype=float)
        return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosRefinedBlend":
        if len(X) < _MIN_FIT_ROWS:
            return self
        inner_model = None
        if self.anchor == "learned":
            spec = self.inner or AnchorSpec()
            inner_model = M11.make_pos_learner(spec.learner, feats=spec.feats, **spec.hp)
            inner_model.fit(X, np.asarray(y, dtype=float))
        a = self._anchor_values(X, inner_model)
        ms = pd.to_numeric(X.get("market_score"), errors="coerce").to_numpy(dtype=float) \
            if "market_score" in X.columns else np.full(len(X), np.nan)
        md = pd.to_numeric(X.get("market_dispersion"), errors="coerce").to_numpy(dtype=float) \
            if "market_dispersion" in X.columns else np.full(len(X), np.nan)
        self._fit = {"inner": inner_model, "za": _AxisZ().fit(a), "zm": _AxisZ().fit(ms),
                     "zd": _AxisZ().fit(md)}
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
        f = self._fit
        za = f["za"].transform(self._anchor_values(X, f["inner"]))
        ms = pd.to_numeric(X.get("market_score"), errors="coerce").to_numpy(dtype=float) \
            if "market_score" in X.columns else np.full(len(X), np.nan)
        md = pd.to_numeric(X.get("market_dispersion"), errors="coerce").to_numpy(dtype=float) \
            if "market_dispersion" in X.columns else np.full(len(X), np.nan)
        zm = f["zm"].transform(ms)
        zd = f["zd"].transform(md)
        w = np.clip(float(self.blend_w) - float(self.disp_slope) * zd, 0.0, 1.0)
        # a player the market does not rank at all keeps the pure anchor (never a median-imputed
        # market opinion driving his slot)
        w = np.where(np.isfinite(ms), w, 0.0)
        return (1.0 - w) * za + w * zm


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Registries + Optuna spaces
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Stage-1 tuned candidates (the refinement family + the NF1.3 flat blend re-tuned in the SAME
# search, so the refinements' lift over flat is measured within one deflated population).
STAGE1_CANDIDATES = ("pos_learned_adaptive_blend", "pos_learned_blend", "pos_adaptive_blend",
                     "pos_blend_flat")

_STAGE1_VARIANTS = {
    "pos_blend_flat": {"anchor": "mvp1", "tune_slope": False},
    "pos_adaptive_blend": {"anchor": "mvp1", "tune_slope": True},
    "pos_learned_blend": {"anchor": "learned", "tune_slope": False},
    "pos_learned_adaptive_blend": {"anchor": "learned", "tune_slope": True},
}

BLIND_REGISTRY = {
    "pos_null": PosNull,
    "pos_ridge": PosRidge,
    "pos_gbm": PosGBM,
    "pos_similarity": PosSimilarity,
    "pos_mlp": PosMLP,
    "pos_twopart": PosTwoPart,
    "pos_rank": PosRank,
}


def make_blind_learner(name: str, feats: tuple[str, ...], **hp):
    return BLIND_REGISTRY[name](feats=feats, **hp)


def make_stage1_learner(name: str, inner: AnchorSpec | None = None,
                        feats: tuple[str, ...] = (), **hp):
    """Stage-1 factory: refinement variants map onto `PosRefinedBlend`; the foils and any
    incumbent class (NF1.3's WR pos_gbm) route to the NF1.3 registry."""
    if name in _STAGE1_VARIANTS:
        v = _STAGE1_VARIANTS[name]
        return PosRefinedBlend(anchor=v["anchor"], inner=inner, feats=feats, **hp)
    return M13.make_pos_learner(name, feats=feats, **hp)


def suggest_hp(trial, name: str) -> dict:
    """Optuna search spaces — NF1.1/NF1.3's verbatim for the shared classes; the refinement
    family tunes (blend_w[, disp_slope]); the MLP tunes a SMALL bounded space."""
    if name in _STAGE1_VARIANTS:
        hp = {"blend_w": trial.suggest_float("blend_w", 0.0, 1.0)}
        if _STAGE1_VARIANTS[name]["tune_slope"]:
            hp["disp_slope"] = trial.suggest_float("disp_slope", 0.0, 1.5)
        return hp
    if name == "pos_mlp":
        return {"hidden": trial.suggest_categorical("hidden", ["128-64-32", "64-32", "32-16"]),
                "alpha": trial.suggest_float("alpha", 1e-3, 10.0, log=True),
                "learning_rate_init": trial.suggest_float("learning_rate_init", 1e-4, 1e-2, log=True)}
    if name == "pos_twopart":
        return {"n_estimators": trial.suggest_int("n_estimators", 100, 400, step=50),
                "num_leaves": trial.suggest_int("num_leaves", 4, 16),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 40),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 20.0, log=True),
                "games_alpha": trial.suggest_float("games_alpha", 0.5, 100.0, log=True)}
    if name == "pos_rank":
        return {"n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
                "num_leaves": trial.suggest_int("num_leaves", 4, 20),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 40),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 20.0, log=True)}
    return M13.suggest_hp(trial, name)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Incumbent extraction + the placebo control + the serving recommendation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def extract_winners(bakeoff: dict) -> dict[str, dict]:
    """Pull {pos: {learner, hp, mean_top}} from a stored NF1.1/NF1.3 bake-off json — the fixed
    incumbent foils (never re-tuned here)."""
    out = {}
    for pos, r in (bakeoff or {}).get("positions", {}).items():
        w = r.get("winner")
        if w and w.get("learner"):
            out[pos] = {"learner": w["learner"], "hp": w.get("hp", {}),
                        "mean_top": w.get("mean_top")}
    return out


def placebo_shuffle(pool: pd.DataFrame, seed: int = 20260727,
                    real_col: str = "real_fp_ppr") -> pd.DataFrame:
    """The PLACEBO pool: permute the realized outcome WITHIN each (position, target_season) group
    (deterministic). Every feature/anchor column is untouched, so any 'lift' the search finds on
    this pool is pure selection luck — the placebo winner must NOT pass the deflated gates."""
    rng = np.random.default_rng(seed)
    out = pool.copy()
    vals = out[real_col].to_numpy().copy()
    for _, idx in out.groupby(["position", "target_season"], sort=True).indices.items():
        idx = np.asarray(idx)
        vals[idx] = vals[idx[rng.permutation(len(idx))]]
    out[real_col] = vals
    return out


def serving_recommendation(refined_beats_incumbent: dict[str, bool],
                           refined_gates: dict[str, dict],
                           product_delta_vs_nf1_3: float | None,
                           calib_80: float | None,
                           nf1_3_product_beats_blind: bool = True) -> dict:
    """The NF1.5-owned serving decision (pure decision rule; the runner feeds it the measured
    numbers). Options: 'refined-dual-board' (serve the NF1.5 refined market-aware board + keep
    the market-blind MVP-1 fade baseline), 'nf1_3-dual-board' (serve NF1.3's board + MVP-1
    baseline), 'mvp1-blind' (no market-aware board earns serving).

    The fantasy vertical's serving gate = the PRODUCT metric + CALIBRATION (roadmap §0 — not the
    betting PBO/DSR deflation, which is still REPORTED for honesty): the refined board serves
    only if it beats the NF1.3 incumbent on the product metric AND its interval calibration
    verifies (calib_80 ≥ 0.78 — the NF1.3 refinement-#5 verify)."""
    cal_ok = calib_80 is not None and calib_80 >= 0.78
    any_refined_win = any(refined_beats_incumbent.values()) if refined_beats_incumbent else False
    product_win = product_delta_vs_nf1_3 is not None and product_delta_vs_nf1_3 > 0
    if any_refined_win and product_win and cal_ok:
        board = "refined-dual-board"
        why = ("the refined market-aware board beats the NF1.3 incumbent on the product metric "
               "with a verified calibrated interval; the market-blind MVP-1 board stays the "
               "fade-claim baseline (dual-board)")
    elif nf1_3_product_beats_blind and cal_ok:
        board = "nf1_3-dual-board"
        why = ("no refinement improved on NF1.3, whose product win over consensus stands "
               "(first board to beat ADP pooled) and whose calibration verifies; serve the "
               "NF1.3 board with honest market-lean labels + keep MVP-1 as the fade baseline")
    elif nf1_3_product_beats_blind:
        board = "nf1_3-dual-board-pending-calibration"
        why = ("NF1.3's product win stands but the interval-calibration verify has not passed "
               "on a full run — re-run the calibration before flipping the served board")
    else:
        board = "mvp1-blind"
        why = "no market-aware board earned serving; the market-blind MVP-1 board stays"
    return {"serve": board, "why": why,
            "refined_beats_incumbent": refined_beats_incumbent,
            "refined_gates": {p: g.get("repoint") for p, g in (refined_gates or {}).items()},
            "product_delta_vs_nf1_3": product_delta_vs_nf1_3,
            "calib_80": calib_80}

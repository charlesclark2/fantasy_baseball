"""nf1_3_model.py — NF1.3 pure model logic: MARKET-AWARE, POSITION-CONDITIONAL per-position learners.

NF1.3 is the operator-sanctioned (2026-07-27) MARKET-AWARE variant of NF1.1. Two structurally
different market-blind passes (NF1 pooled + NF1.1 per-position) established the MARKET-BLIND CEILING:
both beat MVP-1 on the internal holdout but LOST on the consensus-covered universe, and the QB/RB
top-tier gap IS the market signal a strictly market-blind model cannot close. NF1.3 tests whether
folding ADP/ECR consensus into the per-position board POSITION-CONDITIONALLY — leaning on the market
where it out-orders us (QB/RB), staying independent where WE win (WR/TE) — beats the incumbent on
the PRODUCT metric at QB/RB WITHOUT eroding the WR/TE fade edge.

🔒 HONEST FRAME (non-negotiable — carried into every report + the served provenance):
  * This is a PRODUCT variant, NOT a replacement of the honest differentiator. The market-blind NF1
    (MVP-1 incumbent) stays the baseline for the "we out-predict the market on our fades" claim.
  * ⛔ We NEVER claim to beat the market at the positions where we USE it. At QB/RB the honest frame
    is "we incorporate market consensus" (so our ordering TRACKS ADP/ECR there, by design — a Δρ→0
    vs ADP/ECR is the DESIGN, not an edge); at WR/TE we keep our independent view + the fade edge.
  * `best_alpha = 0` — projection product, no edge/win-rate claim.

REUSE: this module reuses NF1.1's per-position machinery VERBATIM — the metric (`top_tier_rho`,
incumbent-anchored + oracle-checked), the deflation kit (CSCV-PBO / config-spread / deflated-Sharpe /
BH-FDR), and the three market-blind learner classes (`PosRidge` / `PosGBM` / `PosSimilarity`). The
ONLY additions are (a) the ADP/ECR market columns folded into each position's feature set
POSITION-CONDITIONALLY (each position fits separately, so the QB fit can lean hard on the market
while the WR fit ignores it), and (b) two market-native candidate classes:

  * `PosMarketBlend` — ⭐ the headline candidate: the explicit POSITION-CONDITIONAL BLEND WEIGHT the
    story names. score = (1−w)·z(mvp1_fp) + w·z(market_score), w∈[0,1] tuned per position on the
    top-tier metric. w is directly interpretable ("how much market this position leans on"): w→0 is
    the market-blind incumbent, w→1 is pure consensus. This is what "select the per-position blend
    weight" means.
  * `PosMarketOnly` — the pure-consensus reference foil (order by the market rank alone), reported
    beside `PosNull` (the MVP-1 market-blind foil) so the grade can answer the two honesty questions:
    does blending BEAT pure market (else just show consensus), and does it beat market-blind MVP-1.

⚖️ LEAKAGE-SAFE: ADP (FFC, drafted the week before Week 1) and ECR (FantasyPros preseason consensus,
frozen early-September) are both snapshots for the PROJECTION season set BEFORE any of its games are
played — forward signals, not outcomes. The market join (per projection season) lives in the runner.

🧷 ORDERING-NOT-LEVEL (the NF1 survivorship-inflation lesson, unchanged): the learned/blended model
is used for RANK only — the runner hands each position its own MVP-1 calibrated point multiset via
`nf1_model.apply_learned_ordering`. Never the learned/market absolute level.

Every function here is PURE (numpy/pandas/sklearn/scipy in, arrays/dicts out, NO IO) so the fast
gate covers the whole selection machinery offline; the DuckDB reads, the ADP/ECR join, the
walk-forward orchestration, Optuna, the S3 landing, and the NF-D3 grade live in `run_nf1_3.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Reuse NF1.1's pure kit VERBATIM — the metric, the deflation harness, the market-blind learners, the
# per-position feature sets, and the standardiser. NF1.3 only ADDS market to the picture.
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11
from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (  # re-export for consumers/tests
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
from quant_sports_intel_models.football.nfl.fantasy.nf1_model import (
    _StandardImputer,
    _prep_matrix,
)

MODEL_VERSION = "nfl_fantasy_nf1_3_v1"

_MIN_FIT_ROWS = M11._MIN_FIT_ROWS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Market feature engineering (PURE — given a frame carrying the raw ADP/ECR columns the runner joins)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The two market feature axes folded into every position's learner set. ONE consensus-rank axis + ONE
# market-uncertainty axis — deliberately minimal so a distance/kNN candidate does not triple-count the
# highly-collinear raw sources (adp / ecr_rank / market_rank). The raw sources stay on the frame for
# the report + the blend/market-only learners; only these two enter the ridge/gbm/similarity sets.
MARKET_FEATURES: tuple[str, ...] = ("market_rank", "market_dispersion")

# Position-conditional market-aware feature sets = NF1.1's per-position sets + the market axes. Each
# position still fits SEPARATELY (that is the "position-conditional" — QB's fit can weight the market
# heavily while WR's fit ignores it). xFP stays in for QB/RB/TE exactly as NF1.1 settled.
POSITION_FEATURES: dict[str, tuple[str, ...]] = {
    pos: feats + MARKET_FEATURES for pos, feats in M11.POSITION_FEATURES.items()
}

# The pre-registered feature GROUPS for the drop-one ablation, + the new `market` group under test.
FEATURE_GROUPS = {**M11.FEATURE_GROUPS, "market": MARKET_FEATURES}


def build_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive the model-facing market columns from the raw ADP/ECR columns the runner joins on.

    Inputs (any missing → treated as NaN): `adp`, `adp_stdev` (FFC), `ecr_rank`, `ecr_std` (ECR).
    Outputs added to a COPY:
      * `market_rank`        — the unified consensus overall rank (lower = better). ECR-primary
                               (widest coverage incl. 2025), ADP as the fallback; NaN when the player
                               is in NEITHER (deep / undrafted — the learners median-impute, which
                               only touches the sub-draftable tail, never the top-tier metric).
      * `market_dispersion`  — the consensus uncertainty (ECR expert rank_std, ADP stdev fallback);
                               the "how sure is the market" axis the fade panel cares about.
      * `market_score`       — `−market_rank` so higher = better, aligned with the fp direction (the
                               ordering signal the blend / market-only learners consume; RANK-only, so
                               no cross-season normalisation is needed — order is scale-free).
    Pure: no IO, no season grouping needed (rank/score are used only for WITHIN-position ordering)."""
    out = df.copy()
    adp = pd.to_numeric(out.get("adp"), errors="coerce") if "adp" in out.columns else pd.Series(np.nan, index=out.index)
    ecr = pd.to_numeric(out.get("ecr_rank"), errors="coerce") if "ecr_rank" in out.columns else pd.Series(np.nan, index=out.index)
    adp_sd = pd.to_numeric(out.get("adp_stdev"), errors="coerce") if "adp_stdev" in out.columns else pd.Series(np.nan, index=out.index)
    ecr_sd = pd.to_numeric(out.get("ecr_std"), errors="coerce") if "ecr_std" in out.columns else pd.Series(np.nan, index=out.index)

    out["market_rank"] = ecr.where(ecr.notna(), adp)
    out["market_dispersion"] = ecr_sd.where(ecr_sd.notna(), adp_sd)
    out["market_score"] = -pd.to_numeric(out["market_rank"], errors="coerce")
    return out


def market_coverage(df: pd.DataFrame, top_n: dict[str, int] = TOP_N,
                    anchor_col: str = "mvp1_fp") -> dict:
    """Diagnostic: the fraction of each position's DRAFTABLE tier (top-N by the MVP-1 incumbent) that
    the consensus actually covers — the honest read on where the market signal is even present. A
    position whose top tier is thinly covered cannot be a market-aware win."""
    cov = {}
    if "market_rank" not in df.columns:
        return cov
    for p, n in top_n.items():
        d = df[df["position"] == p]
        if d.empty or anchor_col not in d.columns:
            continue
        tier = d.nlargest(int(n), anchor_col)
        if tier.empty:
            continue
        covered = pd.to_numeric(tier["market_rank"], errors="coerce").notna().mean()
        cov[p] = round(float(covered), 3)
    return cov


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The market-native candidate learners (interface identical to NF1.1's: fit(X, y) / predict(X)).
# An unfit / too-thin learner predicts the MVP-1 incumbent (`_mvp1_fallback`) so a caller can never
# receive garbage. Where the market is MISSING (deep players), a market signal falls back to mvp1.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mvp1_fallback(X: pd.DataFrame) -> np.ndarray:
    return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)


@dataclass
class PosMarketOnly:
    """The PURE-CONSENSUS reference foil: order by the market rank alone (`market_score = −rank`).
    Reported beside `PosNull` (the MVP-1 market-blind foil). A player the market does not rank keeps
    the MVP-1 order (so a thin-coverage tier degrades gracefully to the incumbent, never to garbage).
    No hyperparameters — this is a reference ordering, not a tuned candidate.

    Why it matters for honesty: if pure market already wins a position's top tier, the market-aware
    product there is simply "show the consensus" — the blend only earns its keep if it BEATS this."""

    feats: tuple[str, ...] = ()

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosMarketOnly":
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        mvp1 = _mvp1_fallback(X)
        if "market_score" not in X.columns:
            return mvp1
        ms = pd.to_numeric(X["market_score"], errors="coerce").to_numpy(dtype=float)
        # a market rank is a cross-position slot; put it on the mvp1 scale via a rank-preserving map so
        # players WITH a market slot order by the market and players WITHOUT keep their mvp1 position
        # below them — but since the ordering is strictly within-position + rank-only downstream, the
        # raw market_score already orders the covered players correctly; fall back to mvp1 where NaN.
        return np.where(np.isfinite(ms), ms, -1e12 + mvp1)


@dataclass
class PosMarketBlend:
    """⭐ The explicit POSITION-CONDITIONAL BLEND — the story's "per-position blend weight" as a
    first-class tuned parameter.

        score = (1 − w) · z(mvp1_fp) + w · z(market_score)

    where z(·) is the train-fit standardisation (median-imputed so a deep player with no market slot
    contributes ~0 on the market axis — i.e. falls back toward the mvp1 term) and `w ∈ [0, 1]` is
    tuned per position on the held-out top-tier metric. w is directly interpretable: w≈0 ⇒ the
    market-blind incumbent (the WR/TE expectation), w≈1 ⇒ pure consensus (the QB/RB expectation). The
    two signals are standardised on the TRAIN fold only (leakage-safe). Deterministic (pure arithmetic).

    Fitting stores the train medians + (μ, σ) for both axes. Predict blends the standardised axes;
    unfit ⇒ the MVP-1 incumbent."""

    blend_w: float = 0.5
    feats: tuple[str, ...] = ("mvp1_fp", "market_score")
    _fit: tuple | None = None

    _AXES = ("mvp1_fp", "market_score")

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosMarketBlend":
        if len(X) < _MIN_FIT_ROWS:
            return self
        imp = _StandardImputer().fit(_prep_matrix(X, self._AXES))
        self._fit = imp
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return _mvp1_fallback(X)
        z = self._fit.transform(_prep_matrix(X, self._AXES))   # (n, 2): [z_mvp1, z_market]
        w = float(min(max(self.blend_w, 0.0), 1.0))
        return (1.0 - w) * z[:, 0] + w * z[:, 1]


# The NF1.3 candidate registry: the three market-blind classes (now carrying the market feature axes
# via POSITION_FEATURES) + the two market-native classes + the MVP-1 null foil. `PosMarketOnly` is a
# reference foil (reported, not selected among the tuned winners).
POS_LEARNER_REGISTRY = {
    "pos_null": PosNull,
    "pos_market_only": PosMarketOnly,
    "pos_ridge": PosRidge,
    "pos_gbm": PosGBM,
    "pos_similarity": PosSimilarity,
    "pos_market_blend": PosMarketBlend,
}

# The tuned candidate classes the bake-off selects a winner FROM (each has a hyperparameter search).
# pos_market_blend is FIRST — the headline market-aware candidate.
LEARNED_CANDIDATES = ("pos_market_blend", "pos_ridge", "pos_gbm", "pos_similarity")


def make_pos_learner(name: str, feats: tuple[str, ...], **hp):
    return POS_LEARNER_REGISTRY[name](feats=feats, **hp)


def suggest_hp(trial, name: str) -> dict:
    """The Optuna search space per learner class — NF1.1's spaces verbatim for the shared classes, plus
    the market-blend weight. Kept here (in the pure module) so the runner's tuner stays generic."""
    if name == "pos_market_blend":
        return {"blend_w": trial.suggest_float("blend_w", 0.0, 1.0)}
    if name == "pos_ridge":
        return {"alpha": trial.suggest_float("alpha", 0.5, 300.0, log=True)}
    if name == "pos_gbm":
        return {"n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
                "num_leaves": trial.suggest_int("num_leaves", 4, 20),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 40),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 20.0, log=True)}
    if name == "pos_similarity":
        return {"k": trial.suggest_int("k", 5, 75),
                "weight_power": trial.suggest_float("weight_power", 0.0, 3.0),
                "mvp1_emphasis": trial.suggest_float("mvp1_emphasis", 0.5, 4.0, log=True)}
    return {}

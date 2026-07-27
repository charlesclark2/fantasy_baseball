"""nf1_1_model.py — NF1.1 pure model logic: PER-POSITION INDEPENDENT learners + TOP-TIER selection.

NF1.1 attacks the draftable-tier QB/RB gap NF1 v1 left open, with two coupled fixes (operator
2026-07-27, from NF1's own verdict):

  1. PER-POSITION INDEPENDENT MODELS. NF1 v1's winner was a POOLED GBM (position as a categorical) —
     pooling regresses the studs toward the cross-position mean, exactly the tier the draft board
     cares about. Here QB / RB / WR / TE are fit as SEPARATE models with position-specific
     pre-registered feature sets and position-specific tuning. The candidate set per position
     (§0.5, ≥3 learner classes + the null foil): per-position ridge, per-position GBM, and a
     SIMILARITY/COMPARABLES learner (project a player from his N most-similar historical
     player-seasons — the heavily-weighted industry paradigm we had never tried), against the
     MVP-1 per-position heuristic null.

  2. RE-SELECT ON A TOP-TIER-WEIGHTED METRIC. NF1 v1 was selected on full-universe within-position ρ
     and won it while LOSING the product metric (the NF-D3 draftable tier) — the E2.1-r
     selection-metric lesson, round two. NF1.1's selection metric is `top_tier_rho`: within-position
     Spearman restricted to the DRAFTABLE tier (top-N per position, the NF-D7 tier definition).
     ⭐ METRIC HYGIENE: the tier is anchored on the INCUMBENT (MVP-1) projection, NOT on each
     candidate's own score — every candidate is graded on the SAME player subset (apples-to-apples;
     a candidate cannot game the metric by promoting easy-to-predict players into its own tier), and
     the realized-outcome oracle stays a hard ceiling (ρ=1 inside a fixed tier).

  Deflation (the story gate): every evaluated config — every Optuna trial of every learner class —
  counts toward the search. `cscv_pbo` (combinatorial symmetric CV over seasons), `deflated_sharpe`
  (DSR of the winner's per-season lift vs the null, deflated by the whole trial population), and
  `bh_fdr` (Benjamini–Hochberg across the four position searches) gate a repoint: PBO<0.2, DSR≥0.95,
  FDR-surviving. A position that fails keeps MVP-1 (a null is a valid outcome). NOTE the CLAUDE.md
  §0.5 PBO reading: a high PBO over a TIED field is the null (no candidate robustly wins), only a
  high PBO with a WIDE spread is overfitting — report the spread with the number.

⚖️ MARKET-BLIND (unchanged from NF1): no ADP/ECR features — the market-aware variant is a separate
operator decision. NF1.1 tests the MARKET-BLIND CEILING at the top tier; if it cannot close QB/RB,
that IS the evidence for the market-aware decision. `best_alpha = 0` (projection product, no edge
claim).

🧷 ORDERING-NOT-LEVEL (the NF1 survivorship-inflation lesson, kept verbatim): the learned model is
used for RANK only — `nf1_model.apply_learned_ordering` hands each position its own MVP-1 calibrated
point multiset. Never the learned absolute level.

⚠️ NF-D7 SCOPE: the xFP features (`xfp_pg`, `td_luck_ratio`, `xrush_td_pg`, `xrec_td_pg`, `xrec_pg`,
`xrec_yds_pg`) join each position's matrix as CANDIDATE FEATURES for the learned models. NF-D7
already settled that the heuristic TD-regression blend into MVP-1 is a NULL — that question is NOT
re-litigated here; the open question NF1.1 owns is whether a LEARNED per-position model extracts
signal from these features that the pooled/heuristic path couldn't.

Every function here is PURE (numpy/pandas/sklearn/scipy in, arrays/dicts out, NO IO) so the fast
gate covers the whole selection machinery offline; DuckDB reads, the walk-forward orchestration,
Optuna, the S3 landing, and the NF-D3 grade live in `run_nf1_1.py`.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_model import (
    FEATURES as NF1_FEATURES,
    LEARN_POSITIONS,
    _StandardImputer,
    _prep_matrix,
)

MODEL_VERSION = "nfl_fantasy_nf1_1_v1"

POSITIONS = LEARN_POSITIONS  # ("QB", "RB", "WR", "TE")

# The DRAFTABLE tier per position — the NF-D7/NF1.1 top-tier universe (the tier that wins drafts).
TOP_N = {"QB": 24, "RB": 36, "WR": 48, "TE": 24}

# The NF-D7 xFP candidate features (leakage-safe, opportunity-based; xfp_source.load_xfp_features).
XFP_FEATURES = ("xfp_pg", "td_luck_ratio", "xrush_td_pg", "xrec_td_pg", "xrec_pg", "xrec_yds_pg")

# ── PRE-REGISTERED per-position feature sets (hypothesis-driven, not open subset search — §0.5).
#    Rationale: a QB is never a target (drop `target_share`; keep `carry_share` — rushing QBs are the
#    top-tier separator) and his receiving-xFP legs are noise (keep only `xrush_td_pg` +
#    `td_luck_ratio`); an RB carries AND receives (everything); WR/TE never carry meaningfully (drop
#    `carry_share`; receiving xFP legs only). The drop-one-GROUP ablation on each winner reports what
#    each group actually carries.
# ────────────────────────────────────────────────────────────────────────────────────────────────
POSITION_FEATURES: dict[str, tuple[str, ...]] = {
    "QB": tuple(f for f in NF1_FEATURES if f != "target_share") + ("xrush_td_pg", "td_luck_ratio"),
    "RB": NF1_FEATURES + XFP_FEATURES,
    "WR": tuple(f for f in NF1_FEATURES if f != "carry_share")
    + ("xrec_pg", "xrec_yds_pg", "xrec_td_pg", "xfp_pg", "td_luck_ratio"),
    "TE": tuple(f for f in NF1_FEATURES if f != "carry_share")
    + ("xrec_pg", "xrec_yds_pg", "xrec_td_pg", "xfp_pg", "td_luck_ratio"),
}

# Pre-registered feature GROUPS for the drop-one ablation on each position winner (applied as the
# intersection with that position's set). `xfp` is the NF1.1 addition under test.
FEATURE_GROUPS = {
    "usage": ("snap_share", "target_share", "carry_share"),
    "mover": ("mover_scale",),
    "env": ("team_env",),
    "injury": ("injury_cap_ratio",),
    "age": ("age",),
    "role": ("depth_rank", "expected_games", "base_games"),
    "xfp": XFP_FEATURES,
}

# The story's deflation gates for a served-board repoint.
PBO_MAX = 0.2
DSR_MIN = 0.95
FDR_Q = 0.10


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-position candidate learners — each instance fits ONE position's rows.
# Interface: fit(X: DataFrame, y: ndarray) / predict(X: DataFrame) -> ndarray. An unfit (or
# too-thin-to-fit) learner predicts the MVP-1 incumbent (`mvp1_fp`) so a caller can never receive
# garbage for a position the learner couldn't model.
# ══════════════════════════════════════════════════════════════════════════════════════════════
_MIN_FIT_ROWS = 20


def _mvp1_fallback(X: pd.DataFrame) -> np.ndarray:
    return pd.to_numeric(X["mvp1_fp"], errors="coerce").to_numpy(dtype=float)


@dataclass
class PosNull:
    """The per-position MVP-1 null foil: predict = the incumbent heuristic projection, unchanged.
    Every learned candidate's held-out TOP-TIER ordering must beat this to earn a repoint."""

    feats: tuple[str, ...] = ()

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosNull":
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return _mvp1_fallback(X)


@dataclass
class PosRidge:
    """Per-position ridge on the standardised position feature set — the interpretable, small-data-
    safe linear candidate (NF1 v1 showed the linears LOSE top-tier QB; they stay in the set as the
    honest foil the trees must beat)."""

    alpha: float = 10.0
    feats: tuple[str, ...] = ()
    _fit: tuple | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosRidge":
        from sklearn.linear_model import Ridge

        if len(X) < _MIN_FIT_ROWS:
            return self
        imp = _StandardImputer().fit(_prep_matrix(X, self.feats))
        F = imp.transform(_prep_matrix(X, self.feats))
        self._fit = (imp, Ridge(alpha=self.alpha).fit(F, np.asarray(y, dtype=float)))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return _mvp1_fallback(X)
        imp, reg = self._fit
        return np.clip(reg.predict(imp.transform(_prep_matrix(X, self.feats))), 0.0, None)


@dataclass
class PosGBM:
    """Per-position LightGBM — the non-linear candidate, fit on ONE position's rows only (no pooled
    stud-compression). Deliberately shallow/regularised: a single position's pool is a few hundred
    rows. Deterministic (fixed seed)."""

    n_estimators: int = 200
    num_leaves: int = 7
    learning_rate: float = 0.03
    min_child_samples: int = 15
    reg_lambda: float = 1.0
    feats: tuple[str, ...] = ()
    _fit: object = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosGBM":
        import lightgbm as lgb

        if len(X) < _MIN_FIT_ROWS:
            return self
        F = pd.DataFrame(_prep_matrix(X, self.feats), columns=list(self.feats))
        model = lgb.LGBMRegressor(
            n_estimators=self.n_estimators, num_leaves=self.num_leaves,
            learning_rate=self.learning_rate, min_child_samples=self.min_child_samples,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
            reg_lambda=self.reg_lambda, random_state=13, n_jobs=1, verbosity=-1,
        )
        model.fit(F, np.asarray(y, dtype=float))
        self._fit = model
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return _mvp1_fallback(X)
        F = pd.DataFrame(_prep_matrix(X, self.feats), columns=list(self.feats))
        return np.clip(self._fit.predict(F), 0.0, None)


@dataclass
class PosSimilarity:
    """⭐ The SIMILARITY / COMPARABLES (analog) learner — the industry "Similar Player Model"
    paradigm, as a §0.5 candidate class: project a player from the realized next-season outcomes of
    his k most-similar HISTORICAL player-seasons.

    Similarity space = the position's standardised feature matrix (median-imputed, z-scaled on
    train), with the `mvp1_fp` axis optionally EMPHASISED (`mvp1_emphasis` multiplies that z-column)
    so the tuner can decide how much the comp neighbourhood should respect the incumbent's overall
    level vs the orthogonal shape features. Prediction = the inverse-distance-power-weighted mean of
    the k nearest train rows' realized PPR (`weight_power=0` → an unweighted comp average).
    Deterministic (pure distance arithmetic, stable argpartition)."""

    k: int = 20
    weight_power: float = 1.0
    mvp1_emphasis: float = 1.0
    feats: tuple[str, ...] = ()
    _fit: tuple | None = None

    def _axis_scale(self) -> np.ndarray:
        s = np.ones(len(self.feats))
        for j, f in enumerate(self.feats):
            if f == "mvp1_fp":
                s[j] = self.mvp1_emphasis
        return s

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "PosSimilarity":
        if len(X) < _MIN_FIT_ROWS:
            return self
        imp = _StandardImputer().fit(_prep_matrix(X, self.feats))
        F = imp.transform(_prep_matrix(X, self.feats)) * self._axis_scale()
        self._fit = (imp, F, np.asarray(y, dtype=float))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._fit is None:
            return _mvp1_fallback(X)
        from scipy.spatial.distance import cdist

        imp, F_tr, y_tr = self._fit
        F_te = imp.transform(_prep_matrix(X, self.feats)) * self._axis_scale()
        d = cdist(F_te, F_tr)
        k = int(min(max(self.k, 1), F_tr.shape[0]))
        idx = np.argpartition(d, k - 1, axis=1)[:, :k]
        dd = np.take_along_axis(d, idx, axis=1)
        w = 1.0 / np.power(dd + 1e-6, self.weight_power)
        pred = (w * y_tr[idx]).sum(axis=1) / w.sum(axis=1)
        return np.clip(pred, 0.0, None)


# The pre-registered candidate registry (§0.5: 3 learner classes + the null foil, per position).
POS_LEARNER_REGISTRY = {
    "pos_null": PosNull,
    "pos_ridge": PosRidge,
    "pos_gbm": PosGBM,
    "pos_similarity": PosSimilarity,
}


def make_pos_learner(name: str, feats: tuple[str, ...], **hp):
    return POS_LEARNER_REGISTRY[name](feats=feats, **hp)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The TOP-TIER selection metric (+ oracle-ceiling hygiene, E2.1-r)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def safe_spearman(a: pd.Series, b: pd.Series) -> float | None:
    """Degeneracy-safe Spearman: pairwise-dropna, require ≥2 DISTINCT values on each side (a
    near-constant float array can carry ~1e-14 noise, so a `std == 0` check is NOT sufficient — the
    QB pos_gbm NaN bug), and return None for any non-finite result instead of NaN."""
    d = pd.concat([pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")],
                  axis=1, keys=["a", "b"]).dropna()
    if len(d) < 2 or d["a"].nunique() < 2 or d["b"].nunique() < 2:
        return None
    v = float(d["a"].corr(d["b"], method="spearman"))
    return v if np.isfinite(v) else None


def top_tier_rho(df: pd.DataFrame, score_col: str, real_col: str = "real_fp_ppr",
                 anchor_col: str = "mvp1_fp", top_n: dict[str, int] = TOP_N,
                 min_n: int = 8, degenerate_zero: bool = False) -> tuple[dict, float | None]:
    """Per-position Spearman(score, realized) restricted to the DRAFTABLE tier — the NF1.1 selection
    metric. The tier is the top-N players per position by `anchor_col` (the INCUMBENT board), fixed
    across candidates so every candidate grades on the identical subset; pass `anchor_col=None` to
    anchor on the candidate's own score (reporting only, never selection). Returns ({pos: ρ},
    pooled mean over the positions in `top_n`).

    `degenerate_zero=True` (the SELECTION setting): a candidate whose predictions are CONSTANT over
    an otherwise-scoreable tier (realized varies) scores ρ = 0.0 — a constant projection has zero
    ordering skill. Without it (default) the position is skipped, which would let a degenerate
    config be graded on a friendlier season subset than the null."""
    per = {}
    for p, n in top_n.items():
        d = df[df["position"] == p]
        if d.empty:
            continue
        d = d.nlargest(int(n), anchor_col if anchor_col is not None else score_col)
        if len(d) < min_n:
            continue
        a = pd.to_numeric(d[score_col], errors="coerce")
        b = pd.to_numeric(d[real_col], errors="coerce")
        v = safe_spearman(a, b)
        if v is not None:
            per[p] = round(v, 4)
        elif degenerate_zero and b.nunique() > 1:
            per[p] = 0.0
    pooled = round(float(np.mean(list(per.values()))), 4) if per else None
    return per, pooled


def oracle_top_tier_is_ceiling(df: pd.DataFrame, candidate_cols: list[str],
                               real_col: str = "real_fp_ppr", anchor_col: str = "mvp1_fp",
                               top_n: dict[str, int] = TOP_N) -> bool:
    """E2.1-r ORACLE-FLOOR guard on the SELECTION metric: within the fixed anchored tier the
    realized-outcome oracle orders at ρ=1, so no candidate's pooled top-tier ρ may exceed it. A
    candidate that "beats" the oracle is the tell the metric is inverted."""
    _, oracle = top_tier_rho(df.assign(_oracle=df[real_col]), "_oracle", real_col,
                             anchor_col=anchor_col, top_n=top_n)
    if oracle is None:
        return True
    for c in candidate_cols:
        _, pooled = top_tier_rho(df, c, real_col, anchor_col=anchor_col, top_n=top_n)
        if pooled is not None and pooled > oracle + 1e-9:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Deflation — CSCV PBO, deflated Sharpe, BH-FDR (every evaluated config counts)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def cscv_pbo(scores: np.ndarray, max_splits: int = 256) -> float | None:
    """Probability of Backtest Overfitting via Combinatorial Symmetric Cross-Validation (Bailey et
    al.) over SEASON columns. `scores` = (n_configs, n_seasons) of the selection metric (top-tier ρ)
    for EVERY evaluated config. For each balanced split of the seasons into an IS/OOS half: pick the
    IS-mean-best config, find its RELATIVE RANK among all configs on the OOS mean; PBO = the
    fraction of splits where the IS winner lands in the BELOW-MEDIAN half OOS. NaN-safe (a config
    unscored in a season contributes its remaining seasons). Returns None when the matrix is too
    thin to split (needs ≥2 configs and ≥4 seasons)."""
    S = np.asarray(scores, dtype=float)
    if S.ndim != 2 or S.shape[0] < 2 or S.shape[1] < 4:
        return None
    n_cfg, n_s = S.shape
    half = n_s // 2
    splits = list(itertools.combinations(range(n_s), half))
    if len(splits) > max_splits:  # deterministic thinning for a wide season axis
        step = len(splits) / max_splits
        splits = [splits[int(i * step)] for i in range(max_splits)]
    below, total = 0, 0
    for is_cols in splits:
        oos_cols = [c for c in range(n_s) if c not in is_cols]
        with np.errstate(invalid="ignore"):
            is_mean = np.nanmean(S[:, list(is_cols)], axis=1)
            oos_mean = np.nanmean(S[:, oos_cols], axis=1)
        if not np.isfinite(is_mean).any():
            continue
        best = int(np.nanargmax(is_mean))
        if not np.isfinite(oos_mean[best]):
            continue
        finite = np.isfinite(oos_mean)
        rank = float((oos_mean[finite] < oos_mean[best]).sum())
        omega = rank / max(finite.sum() - 1, 1)      # relative OOS rank of the IS winner in [0, 1]
        below += int(omega < 0.5)
        total += 1
    return round(below / total, 4) if total else None


def config_spread(scores: np.ndarray) -> float | None:
    """The across-config SPREAD of mean selection scores — the §0.5 PBO discriminator: a high PBO
    over a TIGHT spread (tied field) is the null; a high PBO over a WIDE spread is overfitting."""
    S = np.asarray(scores, dtype=float)
    if S.ndim != 2 or S.shape[0] < 2:
        return None
    with np.errstate(invalid="ignore"):
        means = np.nanmean(S, axis=1)
    means = means[np.isfinite(means)]
    if len(means) < 2:
        return None
    return round(float(means.max() - means.min()), 4)


def deflated_sharpe(deltas: np.ndarray, trial_srs: np.ndarray) -> float | None:
    """Deflated Sharpe Ratio (Bailey & López de Prado) of the winner's per-season LIFT vs the null.
    `deltas` = per-season (winner − null) selection-metric values; `trial_srs` = the Sharpe of every
    evaluated config's per-season lift (the trial population that deflates the winner — the expected
    max-SR under that many unskilled trials is subtracted). Returns P(true SR > 0 | the search), in
    [0, 1]; gate at ≥ DSR_MIN. None when too thin to estimate (<3 seasons / zero variance)."""
    from scipy.stats import kurtosis, norm, skew

    d = np.asarray(deltas, dtype=float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 3:
        return None
    sd = float(d.std(ddof=1))
    if sd < 1e-12:
        return None
    sr = float(d.mean()) / sd
    srs = np.asarray(trial_srs, dtype=float)
    srs = srs[np.isfinite(srs)]
    em = 0.5772156649015329  # Euler–Mascheroni
    if len(srs) >= 2 and srs.std(ddof=1) > 0:
        n = len(srs)
        sr0 = float(srs.std(ddof=1)) * ((1 - em) * norm.ppf(1 - 1 / n)
                                        + em * norm.ppf(1 - 1 / (n * np.e)))
    else:
        sr0 = 0.0
    g3 = float(skew(d))
    g4 = float(kurtosis(d, fisher=False))
    denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
    if denom <= 0:
        return None
    return round(float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(denom))), 4)


def onesided_paired_pvalue(deltas: np.ndarray) -> float | None:
    """One-sided paired t-test p-value for H1: mean(delta) > 0 — the per-position evidence fed to
    BH-FDR across the four position searches. None when too thin (<3) or degenerate."""
    from scipy.stats import t as student_t

    d = np.asarray(deltas, dtype=float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 3:
        return None
    sd = float(d.std(ddof=1))
    if sd < 1e-12:
        return 0.0 if d.mean() > 0 else 1.0
    tstat = float(d.mean()) / (sd / np.sqrt(T))
    return round(float(1.0 - student_t.cdf(tstat, T - 1)), 4)


def bh_fdr(pvals: dict[str, float | None], q: float = FDR_Q) -> dict[str, bool]:
    """Benjamini–Hochberg at level `q` over the position searches. A None p-value (unscorable) can
    never pass. Returns {key: survives}."""
    items = [(k, p) for k, p in pvals.items() if p is not None]
    out = {k: False for k in pvals}
    if not items:
        return out
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    cutoff_rank = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= q * i / m:
            cutoff_rank = i
    for i, (k, _) in enumerate(items, start=1):
        out[k] = i <= cutoff_rank
    return out


def position_verdict(winner_beats_null: bool, pbo: float | None, dsr: float | None,
                     fdr_pass: bool, pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN) -> dict:
    """The per-position repoint decision: the served board repoints to the learned model ONLY when
    the winner beats the MVP-1 null on the held-out top-tier metric AND the deflation gates all pass
    (PBO < pbo_max, DSR ≥ dsr_min, FDR-surviving). Anything else keeps MVP-1 — a null is a valid,
    recorded outcome, not a failure."""
    checks = {
        "beats_null": bool(winner_beats_null),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "fdr_ok": bool(fdr_pass),
    }
    return {"repoint": all(checks.values()), **checks}


def combined_ordering_score(feats: pd.DataFrame, position_scores: dict[str, np.ndarray]) -> np.ndarray:
    """Assemble the single score array `apply_learned_ordering` consumes from per-position model
    outputs: positions WITH a learned score use it; every other row keeps `mvp1_fp` (→ the remap is
    an identity there — MVP-1 unchanged). Cross-position scale never matters: the remap is strictly
    within-position. `position_scores[p]` must align with `feats[feats.position == p]` row order."""
    score = pd.to_numeric(feats["mvp1_fp"], errors="coerce").to_numpy(dtype=float)
    pos = feats["position"].to_numpy()
    for p, s in position_scores.items():
        m = pos == p
        s = np.asarray(s, dtype=float)
        if m.sum() != len(s):
            raise ValueError(f"position_scores[{p!r}] has {len(s)} rows; frame has {int(m.sum())}")
        score[m] = s
    return score

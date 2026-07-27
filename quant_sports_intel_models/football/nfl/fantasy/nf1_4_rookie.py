"""nf1_4_rookie.py — NF1.4 pure model logic: the rookie-prior bake-off (verdict: NULL).

WHY THIS STORY EXISTS — MVP-3 dogfooding + NF1 both flagged ROOKIE OVER-VALUATION: on the live 2026
board the #1-overall pick (a QB) projects **QB11 / #12 overall at 268 PPR**, a rookie priced as a
fringe-QB1 before taking an NFL snap. The story's hypothesis was that MVP-1's draft-slot →
rookie-year fantasy-point POWER LAW (`season_projection.fit_rookie_slot_curves` +
`project_rookies`) "runs too hot" and needed its LEVEL recalibrated.

🔎 WHAT THE MEASUREMENT ACTUALLY FOUND (walk-forward by draft class 2019–2025 — full numbers in
`ablation_results/nf1_4_rookie.md`). Two things, and neither is the hypothesis:

  1. **The incumbent rookie prior is COLD, not hot.** It under-projects nearly every drafted rookie,
     and it stays cold on the DRAFTABLE tier at every position (`tier_bias` QB −32 / RB −58 /
     WR −49 / TE −44 PPR). Its point projection for the very player that was flagged — the
     #1-overall rookie QB — is close to UNBIASED over seven classes: **+8.9 PPR against a realized
     mean of ~201**. Shifting the level DOWN would make the board worse, not better.

  2. **The flagged symptom is a RANK effect produced by VARIANCE.** On the emitted 2019–25 boards
     the #1-overall QB is projected QB11–QB15 and finishes QB8–QB25 (mean ≈ QB19.5) — about six
     slots high. Rookie QB outcomes are enormously dispersed (Kyler Murray beat his projection by
     85 PPR; Trevor Lawrence missed his by 62) and veteran QB projections pack densely at that
     level, so a few points of projection buy many ranks. A rank error around an unbiased point
     estimate is an UNCERTAINTY problem, not a level one — which is why NF1.4's one shipped change
     is the rookie INTERVAL (`season_projection._fit_rookie_bands`), not the point projection.

⚠️ SURVIVORSHIP — real, and tested, and NOT the cure. `load_rookie_training` fits the curve under
`... where games > 0`, dropping every drafted rookie who never played a snap: over 2016–2025 that is
15% of drafted skill rookies and **35% of QBs**, inflating the survivor-only QB mean from 67 to 104
PPR (+55%). An arm re-fitting the incumbent's EXACT functional form (same power law, same shrink,
same clip — zero new degrees of freedom) on the full drafted population made held-out accuracy
WORSE at every position, because the board was already too cold. It is a genuine flaw in how the
curve is estimated; it is not the flaw that produces the flagged board. It DOES matter for the
interval, where the never-played rookies are exactly the outcomes an honest p10 has to price.

🔬 WHAT THIS MODULE PROVIDES — a pre-registered §0.5 candidate set for the rookie prior, every form
built on the FULL drafted population (a never-played rookie is a REAL zero, not a missing row) and
every non-null form SHRUNK toward the position mean:

  * `incumbent`   — the served MVP-1 slot curve, refit per cohort through the ACTUAL production code
                    path (`fit_rookie_slot_curves` + `project_rookies`, survivor-filtered) = the null
                    to beat. Not a re-implementation: a re-implementation could accidentally fix the
                    survivorship bug and make the null look worse than what is actually served.
  * `pos_mean`    — constant position mean over ALL drafted rookies (the level floor).
  * `pos_median`  — constant position median. ⚠️ THE METRIC-INVERSION TELL (see below), reported and
                    deliberately NOT eligible to win.
  * `slot_eb`     — draft-slot BIN with an empirical-Bayes shrink toward the position mean (the
                    field's "draft capital dominates, then shrink" form, done honestly).
  * `slot_ridge`  — ridge on log1p(rookie fp) over the pre-registered feature blocks.
  * `slot_gbm`    — gradient boosting over the same blocks (the direct-learned foil).

  FEATURE BLOCKS (hypothesis-driven, bounded — §0.5 feature-selection discipline): `slot` (always
  on — P1A's own verdict is that draft capital beats college production 0.64 vs 0.79 MAE), `p1a`
  (NCAAF-P1A `projected_nfl_z` + its residual on slot — the college-production read as a RESIDUAL,
  never standalone), `athletic` (combine measurables, position-standardized + a composite),
  `breakout` (breakout class-year / early-declare — the age-adjusted-production lever), `recruit`
  (247 composite pedigree).

📏 SELECTION-METRIC HYGIENE (CLAUDE.md §0.5 — a pre-registered metric can be SILENTLY INVERTED).
The story's metric is rookie CALIBRATION/accuracy = **MAE**. Rookie fantasy points are heavily
right-skewed with a mass of zeros, so raw MAE is minimized by the conditional MEDIAN — a metric that
would happily crown "predict ~the position median for everyone," destroying the board. Two guards,
both mechanical:
  1. **The degenerate constant is IN THE FIELD and scored** (`pos_median`). If it wins outright,
     that is reported as the metric telling us to collapse — not as a shippable model. Restricting
     the metric to the DRAFTABLE tier is the other half of this guard (`TIER_K`).
  2. **A do-no-ordering-harm ELIGIBILITY constraint**: a candidate may only be SELECTED if its
     held-out within-position ρ is within `ORDERING_DO_NO_HARM` of the incumbent's. A median
     collapse fails this by construction.
  3. **Oracle floor** (`test_oracle_is_the_scoring_floor`): the realized-outcome oracle scores
     MAE = 0; no candidate may score below it. ⚠️ For an MAE-type metric the oracle sits trivially
     at 0, so this is a DIRECTION check rather than the strong guard it is for E2.1-r's
     coverage-distance metric — the substantive check is that the metric is MONOTONE in accuracy
     (`test_the_selection_metric_is_MONOTONE_in_accuracy`).

⚠️ SMALL-N. The per-position rookie sample is TINY (QB ≈ 12/class). Every rank read goes through
`safe_spearman` (the NF1.1 NaN guard, inherited), the walk-forward has only a handful of cohorts, and
the deflation is therefore NOISY — "cannot distinguish from luck" is the EXPECTED verdict for the
ordering leg — and it is what happened: 134 configs × 4 positions repointed NOTHING. That null is
recorded, not forced into a winner. A measured held-out BIAS or a mis-stated INTERVAL is a different
kind of claim: a correctness defect, not a search result, and no deflation gate applies to it.

Everything here is PURE (numpy/pandas in, arrays/dicts out, NO IO) so the whole model is fast-gate
testable; the DuckDB assembly + walk-forward orchestration + reports live in `run_nf1_4.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (
    bh_fdr,
    config_spread,
    cscv_pbo,
    deflated_sharpe,
    onesided_paired_pvalue,
    safe_spearman,
)

MODEL_VERSION = "nfl_fantasy_nf1_4_rookie_v1"

ROOKIE_POSITIONS = ("QB", "RB", "WR", "TE")

# Deflation gates — inherited verbatim from NF1.1 so the rookie search is held to the same bar.
PBO_MAX = 0.2
DSR_MIN = 0.0
FDR_Q = 0.10

# A candidate may only be SELECTED if its held-out within-position ρ stays within this much of the
# incumbent's. The mechanical guard against an MAE-driven collapse to the position median.
ORDERING_DO_NO_HARM = 0.02

# The pre-registered selection metric (lower is better) — see `cohort_metrics`.
SELECTION_METRIC = "tier_mae"

# The forms that exist to CHARACTERISE the metric, never to ship. `pos_median` is the MAE-collapse
# tell; `oracle` is the scoring floor.
NON_SHIPPABLE = ("pos_median", "oracle")

__all__ = [
    "MODEL_VERSION", "ROOKIE_POSITIONS", "PBO_MAX", "DSR_MIN", "FDR_Q", "ORDERING_DO_NO_HARM",
    "FEATURE_BLOCKS", "ROOKIE_LEARNER_REGISTRY", "make_rookie_learner", "candidate_grid",
    "TIER_K", "position_scale", "draftable_tier", "SELECTION_METRIC",
    "cohort_metrics", "pooled_position_rho", "oracle_is_the_scoring_floor", "face_validity",
    "rookie_verdict", "athletic_features", "p1a_slot_residual",
    "bh_fdr", "config_spread", "cscv_pbo", "deflated_sharpe", "onesided_paired_pvalue",
    "safe_spearman",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pre-registered feature blocks (bounded, hypothesis-driven — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#   slot     — DRAFT CAPITAL. Always on: it is the dominant lever in every published rookie model
#              and in P1A's own head-to-head (0.64 vs 0.79 MAE vs college production).
#   p1a      — the NCAAF-P1A college→NFL translation, entered as `projected_nfl_z` AND as its
#              RESIDUAL on slot (the disagreement the draft board did not price). Never standalone.
#   athletic — combine measurables, position-standardized (a 4.4 forty means something different at
#              WR than at TE) + a simple equal-weight composite over the explosion/agility drills.
#   breakout — BREAKOUT AGE, proxied by the college CLASS YEAR in which the player first cleared a
#              positional production threshold (younger breakout = stronger prospect), plus the
#              early-declare signal (final class year / seasons played).
#   recruit  — 247 composite pedigree (a weak prior the field still uses; cheap to carry).
FEATURE_BLOCKS: dict[str, tuple[str, ...]] = {
    "slot": ("log_overall", "draft_round", "is_top10", "is_day1"),
    "p1a": ("projected_nfl_z", "p1a_slot_residual"),
    "athletic": ("forty_z", "vertical_z", "broad_z", "cone_z", "shuttle_z", "bmi_z",
                 "athletic_composite", "has_combine"),
    "breakout": ("breakout_season_index", "breakout_class_year", "career_index_at_draft",
                 "n_college_seasons", "early_breakout", "has_breakout"),
    "recruit": ("recruit_composite_rating", "recruit_stars_f"),
}
ALWAYS_ON_BLOCK = "slot"
OPTIONAL_BLOCKS = ("p1a", "athletic", "breakout", "recruit")


def block_features(blocks: tuple[str, ...]) -> tuple[str, ...]:
    """The flat feature list for a block selection. `slot` is always included (draft capital is the
    backbone; a rookie form without it is not a candidate we pre-registered)."""
    out: list[str] = list(FEATURE_BLOCKS[ALWAYS_ON_BLOCK])
    for b in blocks:
        if b == ALWAYS_ON_BLOCK:
            continue
        out.extend(FEATURE_BLOCKS[b])
    return tuple(dict.fromkeys(out))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Leakage-safe derived features (pure — computed WITHIN a draft class, pre-debut only)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_COMBINE_DRILLS = {
    # column        (z-sign: +1 = higher is better, -1 = lower is better)
    "forty": -1.0,
    "vertical": +1.0,
    "broad_jump": +1.0,
    "cone": -1.0,
    "shuttle": -1.0,
}


def athletic_features(df: pd.DataFrame, *, ref: pd.DataFrame | None = None) -> pd.DataFrame:
    """Position-standardized combine z-scores + an equal-weight athletic composite.

    Standardized against `ref` (the TRAINING classes) when given, else against `df` itself — the
    leakage-safe form when scoring a held-out cohort is to pass the training frame as `ref`, so a
    test class never contributes to its own normalization. A drill the player did not run stays NaN
    (the learners impute; `has_combine` carries the missingness signal explicitly).

    `bmi_z` is the position-standardized size read (weight / height², the frame proxy), NOT a drill.
    """
    base = df if ref is None else ref
    out = pd.DataFrame(index=df.index)
    pos = df["position_group"].astype(str)
    ref_pos = base["position_group"].astype(str)

    def _z(value: pd.Series, reference: pd.Series, sign: float, name: str) -> None:
        z = pd.Series(np.nan, index=df.index, dtype=float)
        for p in pos.unique():
            rp = reference[ref_pos == p].dropna()
            m = pos == p
            if len(rp) < 5 or float(rp.std(ddof=0)) < 1e-9:
                continue
            z.loc[m] = sign * (value[m] - float(rp.mean())) / float(rp.std(ddof=0))
        out[name] = z.clip(-3.5, 3.5)

    for col, sign in _COMBINE_DRILLS.items():
        name = "broad_z" if col == "broad_jump" else col.split("_")[0] + "_z"
        _z(pd.to_numeric(df.get(col), errors="coerce"),
           pd.to_numeric(base.get(col), errors="coerce"), sign, name)

    def _bmi(frame: pd.DataFrame) -> pd.Series:
        ht = pd.to_numeric(frame.get("combine_ht_in"), errors="coerce")
        wt = pd.to_numeric(frame.get("combine_wt"), errors="coerce")
        return (wt * 703.0) / (ht ** 2)

    _z(_bmi(df), _bmi(base), +1.0, "bmi_z")

    drill_cols = [c for c in ("forty_z", "vertical_z", "broad_z", "cone_z", "shuttle_z") if c in out]
    out["athletic_composite"] = out[drill_cols].mean(axis=1, skipna=True) if drill_cols else np.nan
    out["has_combine"] = (
        pd.to_numeric(df.get("forty"), errors="coerce").notna()
        | pd.to_numeric(df.get("vertical"), errors="coerce").notna()
    ).astype(float)
    return out


def p1a_slot_residual(df: pd.DataFrame, *, class_col: str = "draft_year") -> pd.Series:
    """The NCAAF-P1A residual: within (draft class × position), how far `projected_nfl_z` sits above
    the SLOT-EXPECTED z (a within-class regression of z on log draft slot). This is the "where our
    college-production read DISAGREES with the draft board" signal — P1A's verdict is that it is
    valuable as a RESIDUAL and worse than the slot standalone. Leakage-safe: every input is
    pre-debut and the regression is computed inside the class.

    Standardized (÷ residual sd) inside each group so the scale is comparable across classes; a
    group too thin (<6) or degenerate returns 0 (no disagreement information, not a guess).
    """
    z = pd.to_numeric(df.get("projected_nfl_z"), errors="coerce")
    logo = np.log(pd.to_numeric(df.get("draft_overall"), errors="coerce").clip(lower=1))
    out = pd.Series(0.0, index=df.index, dtype=float)
    keys = df[class_col].astype("string").fillna("?") + "|" + df["position_group"].astype(str)
    for _, idx in keys.groupby(keys).groups.items():
        zi, li = z.loc[idx], logo.loc[idx]
        m = np.isfinite(zi) & np.isfinite(li)
        if m.sum() < 6:
            continue
        if float(np.ptp(li[m])) == 0:
            resid = zi - float(zi[m].mean())
        else:
            slope, intercept = np.polyfit(li[m].to_numpy(), zi[m].to_numpy(), 1)
            resid = zi - (intercept + slope * li)
        sd = float(np.nanstd(resid[np.isfinite(resid)]))
        if sd > 1e-9:
            out.loc[idx] = np.clip(np.nan_to_num(resid / sd), -3.0, 3.0)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Candidate learners — every one fits on the FULL drafted population (zeros included) and shrinks
# toward the training position mean. `fit(train, y)` / `predict(test) -> np.ndarray` in fp units.
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class _RookieBase:
    """Shared plumbing: the position-mean anchor + the shrink that every shippable form applies.

    `shrink` = the weight on the position mean (λ). λ=1 collapses to `pos_mean`; λ=0 is the raw
    form. A rookie is a PRIORS-ONLY object — some shrink is the honest posture, and how much is a
    tuned hyperparameter that counts toward the deflation like any other."""
    feats: tuple[str, ...] = ()
    shrink: float = 0.25
    pos_mean_: dict = field(default_factory=dict)
    global_mean_: float = 0.0

    def _fit_anchor(self, train: pd.DataFrame, y: np.ndarray) -> None:
        d = pd.DataFrame({"p": train["position_group"].astype(str).to_numpy(), "y": np.asarray(y, float)})
        self.pos_mean_ = {p: float(g["y"].mean()) for p, g in d.groupby("p") if len(g) >= 3}
        self.global_mean_ = float(np.nanmean(d["y"])) if len(d) else 0.0

    def _anchor(self, test: pd.DataFrame) -> np.ndarray:
        return np.array([self.pos_mean_.get(str(p), self.global_mean_)
                         for p in test["position_group"]], dtype=float)

    def _blend(self, raw: np.ndarray, test: pd.DataFrame) -> np.ndarray:
        lam = float(np.clip(self.shrink, 0.0, 1.0))
        raw = np.nan_to_num(np.asarray(raw, dtype=float), nan=0.0)
        return np.clip((1.0 - lam) * raw + lam * self._anchor(test), 0.0, None)

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        X = frame.reindex(columns=list(self.feats))
        return X.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)


@dataclass
class RookiePosMean(_RookieBase):
    """The LEVEL FLOOR — the training-class position mean over ALL drafted rookies (zeros included).
    Constant within a position, so it has zero ordering skill by construction; it exists to bound the
    calibration question ("how much of the accuracy is just knowing the right level?")."""

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> "RookiePosMean":
        self._fit_anchor(train, y)
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.clip(self._anchor(test), 0.0, None)


@dataclass
class RookiePosMedian(_RookieBase):
    """⚠️ THE METRIC-INVERSION TELL, not a shippable model. MAE is minimized by the conditional
    median, so on a zero-inflated right-skewed target this constant can top the MAE table while
    carrying zero information. Scored and reported precisely so that outcome is legible; barred from
    selection via `NON_SHIPPABLE` + the do-no-ordering-harm constraint."""
    pos_median_: dict = field(default_factory=dict)
    global_median_: float = 0.0

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> "RookiePosMedian":
        d = pd.DataFrame({"p": train["position_group"].astype(str).to_numpy(), "y": np.asarray(y, float)})
        self.pos_median_ = {p: float(g["y"].median()) for p, g in d.groupby("p") if len(g) >= 3}
        self.global_median_ = float(np.nanmedian(d["y"])) if len(d) else 0.0
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.clip(np.array([self.pos_median_.get(str(p), self.global_median_)
                                 for p in test["position_group"]], dtype=float), 0.0, None)


# Draft-slot bins for the EB form. Coarse on purpose — the whole point is that a rookie carries very
# little individuating information, so a fine grid would just re-fit noise.
SLOT_BINS = (0, 10, 20, 32, 50, 75, 105, 150, 1000)


def slot_bin(overall: float) -> int:
    o = float(overall) if np.isfinite(overall) else 1e9
    for i in range(len(SLOT_BINS) - 1):
        if SLOT_BINS[i] < o <= SLOT_BINS[i + 1]:
            return i
    return len(SLOT_BINS) - 2


@dataclass
class RookieSlotEB(_RookieBase):
    """DRAFT CAPITAL, done honestly — a (position, slot-bin) empirical-Bayes mean.

    The published-field form: draft capital dominates, so bin on it; each bin's mean is EB-shrunk
    toward the position mean by `eb_k` (the pseudo-count at which the bin's own evidence equals the
    prior), and the result is shrunk again toward the position mean by λ. This replaces the MVP-1
    power law — a log-log fit EXTRAPOLATES, which is exactly how pick #1 acquires a fringe-QB1
    projection off a curve fit on survivors; a bin mean cannot exceed what its bin actually did."""
    eb_k: float = 12.0
    bin_mean_: dict = field(default_factory=dict)

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> "RookieSlotEB":
        self._fit_anchor(train, y)
        d = pd.DataFrame({
            "p": train["position_group"].astype(str).to_numpy(),
            "b": [slot_bin(o) for o in pd.to_numeric(train["draft_overall"], errors="coerce")],
            "y": np.asarray(y, dtype=float),
        })
        k = max(float(self.eb_k), 0.0)
        for (p, b), g in d.groupby(["p", "b"]):
            n = len(g)
            prior = self.pos_mean_.get(p, self.global_mean_)
            self.bin_mean_[(p, int(b))] = float((n * g["y"].mean() + k * prior) / (n + k))
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        raw = np.array([
            self.bin_mean_.get((str(p), slot_bin(o)), self.pos_mean_.get(str(p), self.global_mean_))
            for p, o in zip(test["position_group"], pd.to_numeric(test["draft_overall"], errors="coerce"))
        ], dtype=float)
        return self._blend(raw, test)


@dataclass
class RookieRidge(_RookieBase):
    """Ridge on log1p(rookie fp) over the selected blocks + position dummies. The linear foil: it
    can express "slot + a bit of athletic/breakout/P1A" and nothing more, so a win here is evidence
    the added blocks carry LINEAR information the slot curve was missing."""
    alpha: float = 3.0
    _model = None
    _cols: tuple[str, ...] = ()
    _med: np.ndarray | None = None

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> "RookieRidge":
        from sklearn.linear_model import Ridge

        self._fit_anchor(train, y)
        X, cols = _design(train, self.feats)
        self._cols = cols
        self._med = _column_medians(X)
        X = _impute(X, self._med)
        self._model = Ridge(alpha=float(self.alpha)).fit(X, np.log1p(np.clip(np.asarray(y, float), 0, None)))
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        X, _ = _design(test, self.feats, cols=self._cols)
        raw = np.expm1(self._model.predict(_impute(X, self._med)))
        return self._blend(raw, test)


@dataclass
class RookieGBM(_RookieBase):
    """The DIRECT-LEARNED foil (§0.5 requires one) — gradient boosting on log1p(rookie fp). Free to
    find any non-linearity/interaction in the blocks (e.g. athleticism mattering only for early
    picks). Deliberately shallow + heavily regularized: ~700 training rows across four positions is
    nowhere near enough for a deep tree, and an over-fit foil makes for a dishonest bake-off."""
    n_estimators: int = 220
    learning_rate: float = 0.04
    max_depth: int = 2
    min_samples_leaf: int = 25
    subsample: float = 0.8
    _model = None
    _cols: tuple[str, ...] = ()
    _med: np.ndarray | None = None

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> "RookieGBM":
        from sklearn.ensemble import GradientBoostingRegressor

        self._fit_anchor(train, y)
        X, cols = _design(train, self.feats)
        self._cols = cols
        self._med = _column_medians(X)
        self._model = GradientBoostingRegressor(
            n_estimators=int(self.n_estimators), learning_rate=float(self.learning_rate),
            max_depth=int(self.max_depth), min_samples_leaf=int(self.min_samples_leaf),
            subsample=float(self.subsample), random_state=17,
        ).fit(_impute(X, self._med), np.log1p(np.clip(np.asarray(y, float), 0, None)))
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        X, _ = _design(test, self.feats, cols=self._cols)
        raw = np.expm1(self._model.predict(_impute(X, self._med)))
        return self._blend(raw, test)


def _design(frame: pd.DataFrame, feats: tuple[str, ...],
            cols: tuple[str, ...] | None = None) -> tuple[np.ndarray, tuple[str, ...]]:
    """Numeric design matrix = the selected features + one-hot position (fixed column order so a
    test frame missing a position still aligns with the fitted model)."""
    d = frame.reindex(columns=list(feats)).apply(pd.to_numeric, errors="coerce")
    for p in ROOKIE_POSITIONS:
        d[f"_pos_{p}"] = (frame["position_group"].astype(str) == p).astype(float)
    if cols:
        d = d.reindex(columns=list(cols))
    return d.to_numpy(dtype=float), tuple(d.columns)


def _column_medians(X: np.ndarray) -> np.ndarray:
    """Per-column median ignoring NaN, with a column that is ENTIRELY NaN mapped to 0.0.

    That case is expected, not exceptional: the `breakout` block is genuinely unavailable for the
    earliest draft classes (the CFBD class-year feed only becomes usable around 2018, see
    `run_nf1_4._breakout_features`), so an early walk-forward fold really does train on a fully
    absent column. `np.nanmedian` handles it correctly but emits an `All-NaN slice` RuntimeWarning
    per fold per config — ~40 lines of noise in a 134-config run that reads like a defect. Handled
    explicitly here so the intent is legible and a REAL numerical warning would still stand out.
    """
    X = np.asarray(X, dtype=float)
    if X.size == 0:
        return np.zeros(X.shape[1] if X.ndim == 2 else 0)
    present = np.isfinite(X).any(axis=0)
    med = np.zeros(X.shape[1], dtype=float)
    if present.any():
        med[present] = np.nanmedian(X[:, present], axis=0)
    return med


def _impute(X: np.ndarray, med: np.ndarray | None) -> np.ndarray:
    X = np.asarray(X, dtype=float).copy()
    if med is None:
        med = np.zeros(X.shape[1])
    med = np.nan_to_num(np.asarray(med, dtype=float), nan=0.0)
    idx = np.where(~np.isfinite(X))
    if len(idx[0]):
        X[idx] = med[idx[1]]
    return X


ROOKIE_LEARNER_REGISTRY = {
    "pos_mean": RookiePosMean,
    "pos_median": RookiePosMedian,
    "slot_eb": RookieSlotEB,
    "slot_ridge": RookieRidge,
    "slot_gbm": RookieGBM,
}


def make_rookie_learner(name: str, feats: tuple[str, ...] = (), **hp):
    return ROOKIE_LEARNER_REGISTRY[name](feats=feats, **hp)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered search grid (EVERY config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_SHRINK_GRID = (0.0, 0.15, 0.30, 0.50)
_EB_K_GRID = (6.0, 12.0, 25.0)
_ALPHA_GRID = (1.0, 3.0, 10.0)
_LR_GRID = (0.03, 0.06)

# Block selections: the always-on slot backbone, then the pre-registered ADDS (single blocks and the
# full stack). NOT an open subset search — five hypotheses, stated up front.
_BLOCK_SETS: tuple[tuple[str, ...], ...] = (
    ("slot",),
    ("slot", "p1a"),
    ("slot", "athletic"),
    ("slot", "breakout"),
    ("slot", "recruit"),
    ("slot", "p1a", "athletic", "breakout", "recruit"),
)


def candidate_grid(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list: (learner, feature blocks, hyper-parameters).

    Every entry is EVALUATED and every entry counts toward the deflation — that is what makes the
    block ablation safe (§0.5). `smoke=True` keeps one config per learner so a wiring run stays
    seconds, and writes to `*_smoke` artifacts so it can never be mistaken for the real search."""
    grid: list[dict] = [
        {"learner": "pos_mean", "blocks": ("slot",), "hp": {}},
        {"learner": "pos_median", "blocks": ("slot",), "hp": {}},
    ]
    shrinks = (0.15,) if smoke else _SHRINK_GRID
    blocksets = _BLOCK_SETS[:2] if smoke else _BLOCK_SETS
    for lam in shrinks:
        for k in ((12.0,) if smoke else _EB_K_GRID):
            grid.append({"learner": "slot_eb", "blocks": ("slot",), "hp": {"shrink": lam, "eb_k": k}})
        for blocks in blocksets:
            for a in ((3.0,) if smoke else _ALPHA_GRID):
                grid.append({"learner": "slot_ridge", "blocks": blocks,
                             "hp": {"shrink": lam, "alpha": a}})
            for lr in ((0.06,) if smoke else _LR_GRID):
                grid.append({"learner": "slot_gbm", "blocks": blocks,
                             "hp": {"shrink": lam, "learning_rate": lr}})
    return grid


def config_key(cfg: dict) -> str:
    hp = "|".join(f"{k}={v}" for k, v in sorted(cfg["hp"].items()))
    return f"{cfg['learner']}[{'+'.join(cfg['blocks'])}]{{{hp}}}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Metrics — calibration (the story's win condition) + ordering (the do-no-harm constraint)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The DRAFTABLE rookie tier per position — roughly how many rookies at each position are actually
# taken in a redraft league. The selection metric is anchored here (NF1.1's lesson: select on the
# tier the product is used on, not the full universe), because the flagged defect lives at the TOP
# of the rookie board and a pooled read over ~75 rookies/class is dominated by late-round noise.
TIER_K = {"QB": 3, "RB": 6, "WR": 8, "TE": 3}


def position_scale(train: pd.DataFrame, real_col: str = "rookie_fp_ppr") -> dict:
    """Per-position sd of realized rookie fp over the TRAINING classes — the scale-free divisor for
    pooling tier MAE across positions. Without it a QB point error (fp in the hundreds) would swamp
    a TE one and the metric would silently become "the QB metric." In-fold and leakage-safe."""
    out = {}
    for p, g in train.groupby(train["position_group"].astype(str)):
        v = pd.to_numeric(g[real_col], errors="coerce").dropna()
        if len(v) >= 10 and float(v.std(ddof=0)) > 1e-6:
            out[p] = float(v.std(ddof=0))
    return out


def draftable_tier(df: pd.DataFrame, anchor_col: str, tier_k: dict = TIER_K) -> pd.DataFrame:
    """The top-`tier_k[pos]` rookies per position by `anchor_col` — the INCUMBENT's projection, so
    the tier is FIXED across candidates and every candidate grades on the identical subset (NF1.1's
    fixed-anchor discipline). A candidate cannot buy a friendlier tier by re-ranking it."""
    parts = []
    for p, k in tier_k.items():
        d = df[df["position_group"].astype(str) == p]
        if d.empty:
            continue
        parts.append(d.nlargest(int(k), anchor_col) if anchor_col in d.columns else d.head(int(k)))
    return pd.concat(parts, ignore_index=False) if parts else df.iloc[:0]


def pooled_position_rho(df: pd.DataFrame, pred_col: str, real_col: str = "rookie_fp_ppr",
                        min_n: int = 8) -> tuple[dict, float | None]:
    """Within-position Spearman(pred, realized) over a rookie cohort, pooled as the mean across the
    positions that scored. `safe_spearman` (NF1.1) handles the small-N degeneracies — a constant
    prediction over a scoreable position returns ρ = 0.0 (zero ordering skill), NOT a skip, so a
    degenerate form can never buy a friendlier cohort subset than the incumbent."""
    per: dict[str, float] = {}
    for p in ROOKIE_POSITIONS:
        d = df[df["position_group"].astype(str) == p]
        if len(d) < min_n:
            continue
        a = pd.to_numeric(d[pred_col], errors="coerce")
        b = pd.to_numeric(d[real_col], errors="coerce")
        v = safe_spearman(a, b)
        if v is not None:
            per[p] = round(v, 4)
        elif b.nunique() > 1:
            per[p] = 0.0
    pooled = round(float(np.mean(list(per.values()))), 4) if per else None
    return per, pooled


def cohort_metrics(df: pd.DataFrame, pred_col: str, real_col: str = "rookie_fp_ppr",
                   anchor_col: str = "_inc", scale: dict | None = None,
                   tier_k: dict = TIER_K) -> dict:
    """The full held-out read for ONE rookie cohort.

    ⭐ `tier_mae` is the PRE-REGISTERED SELECTION METRIC: within each position's DRAFTABLE tier
    (fixed by the incumbent anchor), the MAE divided by that position's training-class rookie-fp sd,
    averaged across positions. Two reasons it is the tier and not the universe:
      • the flagged defect lives at the TOP of the rookie board (see `tier_bias_by_pos`), and a
        pooled read over ~75 rookies per class is dominated by late-round picks nobody drafts;
      • it is NF1.1's own lesson — select on the tier the product is actually used on.
    The scale-free divisor stops QB (fp in the hundreds) from silently becoming the whole metric.

      mae   — MAE over ALL drafted rookies (the universe accuracy read; reported, not selected on).
      rmse  — proper for the conditional MEAN, so a hot form is punished quadratically. MAE and
              RMSE disagreeing is itself diagnostic.
      bias  — mean(pred − real). ⚠️ Over the FULL drafted universe this runs NEGATIVE for the
              incumbent (it is cold on late-round picks); the defect is in `tier_bias`, which is the
              read that matters. Both are reported precisely so the distinction cannot be lost.
      slope — OLS slope of realized on predicted. 1.0 = calibrated in level.
      rho   — pooled within-position rank correlation (the do-no-harm constraint's input).
    """
    cols = [c for c in {pred_col, real_col, "position_group", anchor_col} if c in df.columns]
    d = df[cols].copy()
    for c in (pred_col, real_col):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=[pred_col, real_col])
    if d.empty:
        return {"n": 0}
    err = d[pred_col] - d[real_col]
    per, pooled = pooled_position_rho(d, pred_col, real_col)
    slope = np.nan
    if float(d[pred_col].std(ddof=0)) > 1e-9:
        slope = float(np.polyfit(d[pred_col].to_numpy(), d[real_col].to_numpy(), 1)[0])

    tier = draftable_tier(d, anchor_col, tier_k)
    tier_mae, tier_bias, tier_mae_pos, tier_bias_pos = {}, {}, {}, {}
    for p, g in tier.groupby(tier["position_group"].astype(str)):
        e = g[pred_col] - g[real_col]
        s = (scale or {}).get(p)
        tier_mae_pos[p] = round(float(e.abs().mean()), 2)
        tier_bias_pos[p] = round(float(e.mean()), 2)
        if s and s > 1e-6:
            tier_mae[p] = float(e.abs().mean()) / s
            tier_bias[p] = float(e.mean()) / s
    return {
        "n": int(len(d)),
        "tier_mae": round(float(np.mean(list(tier_mae.values()))), 4) if tier_mae else None,
        "tier_bias": round(float(np.mean(list(tier_bias.values()))), 4) if tier_bias else None,
        "tier_mae_by_pos": tier_mae_pos,
        "tier_bias_by_pos": tier_bias_pos,
        "mae": round(float(err.abs().mean()), 3),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 3),
        "bias": round(float(err.mean()), 3),
        "slope": None if not np.isfinite(slope) else round(slope, 3),
        "rho": pooled,
        "rho_by_pos": per,
        "bias_by_pos": {p: round(float((g[pred_col] - g[real_col]).mean()), 2)
                        for p, g in d.groupby(d["position_group"].astype(str)) if len(g) >= 5},
    }


def oracle_is_the_scoring_floor(df: pd.DataFrame, candidate_cols: list[str],
                                real_col: str = "rookie_fp_ppr", metric: str = "tier_mae",
                                **kw) -> bool:
    """E2.1-r ORACLE-FLOOR guard. The realized-outcome oracle scores MAE = 0; a candidate that
    scores BELOW that is mathematically impossible ⇒ the tell that the selection metric is inverted.

    ⚠️ Scope, stated honestly: for an MAE-type metric the oracle sits trivially at 0, so this is a
    DIRECTION/sign check (it catches a metric accidentally flipped to higher-is-better), not the
    strong guard it is for a coverage-distance metric like E2.1-r's. The substantive hygiene for
    THIS metric is carried by three other things: the metric is monotone in accuracy, the degenerate
    `pos_median` is scored in the field so a collapse is visible, and the do-no-ordering-harm
    constraint makes a collapse ineligible to win. See `test_nf1_4_rookie.py`."""
    oracle = cohort_metrics(df.assign(_oracle=df[real_col]), "_oracle", real_col, **kw).get(metric)
    if oracle is None:
        return True
    for c in candidate_cols:
        m = cohort_metrics(df, c, real_col, **kw).get(metric)
        if m is not None and m < oracle - 1e-9:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Face validity — the hot-curve gate, measured against what rookies ACTUALLY do
# ══════════════════════════════════════════════════════════════════════════════════════════════
def face_validity(board: pd.DataFrame, hist: pd.DataFrame, *, fp_col: str = "proj_fp_ppr",
                  quantile: float = 0.90, top_overall: int = 10, min_classes: int = 3) -> dict:
    """The FACE-VALIDITY gate on an emitted board — the harness-side twin of
    `season_projection.rookie_board_face_validity` (read that docstring for why the LEVEL reference
    class is the whole game: an all-drafted-population Q90 makes the check fire on 7/7 cohorts and
    is therefore uninformative; the per-class-BEST reference is the real tripwire).

      1. `placement` — no rookie in an overall top-`top_overall` slot, and the #1 overall slot is a
         veteran. The story's stated symptom ("a rookie QB floated to #1 overall").
      2. `level` — per position, the MAX projected rookie vs the Q`quantile` of the per-class BEST
         realized rookie over the prior classes in `hist`.

    `hist` needs `position_group`, `rookie_fp_ppr` and `draft_year`. Returns every measurement plus
    `pass`.
    """
    rk = board[board.get("is_rookie", False).fillna(False).astype(bool)] if "is_rookie" in board else board
    checks: dict = {"n_rookies": int(len(rk))}
    if board.empty:
        return {"pass": True, **checks, "note": "empty board"}

    ranked = board.sort_values(fp_col, ascending=False).reset_index(drop=True)
    is_rk = ranked.get("is_rookie", pd.Series(False, index=ranked.index)).fillna(False).astype(bool)
    checks["top1_is_rookie"] = bool(is_rk.iloc[0]) if len(ranked) else False
    checks["n_rookies_in_top10"] = int(is_rk.head(top_overall).sum())
    top_rk = ranked[is_rk].head(1)
    checks["best_rookie_overall_rank"] = int(ranked[is_rk].index[0]) + 1 if len(top_rk) else None
    checks["best_rookie_name"] = str(top_rk.iloc[0].get("player_name")) if len(top_rk) else None

    caps, over = {}, []
    pos_col = "position" if "position" in rk.columns else "position_group"
    if "draft_year" in hist.columns:
        for p in ROOKIE_POSITIONS:
            h = hist[hist["position_group"].astype(str) == p]
            per_class_best = (h.assign(_fp=pd.to_numeric(h["rookie_fp_ppr"], errors="coerce"))
                              .groupby("draft_year")["_fp"].max().dropna())
            if len(per_class_best) < min_classes:
                continue
            cap = float(np.quantile(per_class_best.to_numpy(), quantile))
            caps[p] = round(cap, 1)
            v = pd.to_numeric(rk[rk[pos_col].astype(str) == p][fp_col], errors="coerce")
            if len(v) and float(v.max()) > cap:
                over.append({"position": p, "max_projected": round(float(v.max()), 1),
                             "top_of_class_cap": round(cap, 1)})
    checks["top_of_class_caps"] = caps
    checks["positions_over_cap"] = over
    checks["pass"] = (not checks["top1_is_rookie"]) and checks["n_rookies_in_top10"] == 0 and not over
    return checks


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Rookie uncertainty — NOTE: the SHIPPED implementation lives in `season_projection.py`
# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF1.4's one shippable change is the calibrated rookie 80% band, and it is implemented ONCE, in
# `season_projection._fit_rookie_bands` / `RookieSlotCurve.band` — on the production curve object,
# so the served projection and this harness cannot drift apart. An earlier `IntervalCalibrator`
# prototype lived here; it was deleted rather than kept alongside, because two implementations of
# the same band would be free to disagree and only one of them would be the one users see.

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rookie_verdict(*, beats_incumbent: bool, ordering_ok: bool, pbo: float | None,
                   dsr: float | None, fdr_pass: bool, shippable: bool,
                   pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN) -> dict:
    """The repoint decision for the ORDERING/accuracy claim.

    The served rookie leg repoints to a learned form ONLY when it beats the incumbent slot curve on
    the held-out selection metric, does no ordering harm, passes the deflation (PBO < max, DSR ≥
    min, FDR-surviving), and is a shippable form (not the `pos_median` collapse tell). Anything else
    keeps the incumbent's ORDERING — a null is a recorded outcome, not a failure.

    ⚠️ This verdict governs the SELECTED-FORM claim only. A measured, persistent held-out LEVEL bias
    is a correctness defect and is reported separately (`bias`, `slope`) — it is not something the
    deflation gate can veto, because it is not a search result.
    """
    checks = {
        "beats_incumbent": bool(beats_incumbent),
        "ordering_ok": bool(ordering_ok),
        "shippable": bool(shippable),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "fdr_ok": bool(fdr_pass),
    }
    return {"repoint": all(checks.values()), **checks}

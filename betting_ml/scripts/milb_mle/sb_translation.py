"""sb_translation.py — E8.3: the MiLB→MLB STOLEN-BASE translation mechanism.

PURE MECHANISM — no IO, no S3, no Snowflake. The runner (`run_e8_3_sb.py`) owns the cohort read, the
CV loop and the gates; everything here is deterministic given a DataFrame, so the whole field is unit
-testable and the selection statistics are reproducible.

WHY THIS IS NOT JUST `BATTER_METRICS + ("sb_rate",)`
----------------------------------------------------
E7.3's `run_bakeoff` selects on **MAE**, and MAE is the one selection metric the repo has repeatedly
caught INVERTING on a zero-heavy target (NF-D11: an all-zero nihilist beat every real candidate at
MAE 15.47 vs 18.96). Adding SB to `BATTER_METRICS` would have inherited that selector silently. So
E8.3 keeps the same CV DESIGN (leave-one-debut-cohort-out, expanding window) and replaces the
SELECTOR with a proper score:

  * **CRPS is primary.** It grades the point AND the spread jointly, so pessimism cannot win it.
  * **MAE is reported beside it**, never selected on.
  * ⭐ **The degenerate all-zero arm is scored EVERY run and READ** — per NF-D14 the test for
    MAE-inversion is the CONDITIONAL MEDIAN, not whether the cohort "looks" zero-heavy, and the
    discipline is to measure it rather than reason about it. (Measured here: 13.3% of labelled rows
    are exactly 0 but the conditional median is 0.0435, well off the floor — so the inversion is NOT
    expected to fire. That prediction is recorded in advance and checked against the run, which is
    what makes a passing anchor informative rather than decorative.)

THE ANCHOR SET (NF1.7 (a)-(d) — four ways an anchor set lies, all four guarded)
------------------------------------------------------------------------------
  (a) An anchor that FAILS TO FIT must RAISE, never silently return None → `AnchorFitError`.
  (b) The ORACLE FLOOR is same-FAMILY and same-SAMPLE: it is the winner's OWN arm refit on the
      held-out fold. Nothing may beat it. Beside it sits a PERMUTATION anchor (the same arm fit on
      SHUFFLED labels), which is well-posed at any n and is the one that survives thin folds.
  (c) SHARPNESS NEEDS TWO DEGENERATES: `degenerate_zero` (maximally pessimistic) AND
      `degenerate_mean` (maximally hedged). Both must lose. Reporting one leaves the metric gameable
      from the other side.
  (d) The era correction is a MATCHED FOIL (NF-D10): each era-corrected arm is registered beside the
      byte-identical arm minus the era term, so the family's contribution is a PAIRED delta, not a
      leaderboard rank — a rank cannot tell "the era term is inert" from "the era term is in a tie".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger("e8_3.sb")

MODEL_VERSION = "sb_translation_v1"

# ── Target forms (pre-registered; the story's "PICK THE TARGET DELIBERATELY") ──────────────────────
#
# `label` is the realized MLB column, `feature` the pre-debut MiLB twin. Every form is a RATE — the
# board ranks players, not playing time, and a count would be incommensurable with the per-PA metrics
# it sits beside in MLE_METRIC_WEIGHTS.
#
#   sb_rate    SB / SBO      the primary ABILITY read. Standard roto 5×5 scores GROSS SB, so this is
#                            the category-relevant quantity: a 30/10 and a 30/2 runner are identical
#                            in that format.
#   att_rate   (SB+CS)/SBO   attempt PROPENSITY — "does he go?", the half that a green light controls.
#   succ_rate  SB/(SB+CS)    efficiency — "does he make it?". Priced by net-SB and points leagues.
#   sb_per_pa  SB / PA       the COARSER opportunity proxy, carried so "does the SBO denominator earn
#                            its keep?" is measured rather than assumed.
TARGET_FORMS: dict[str, dict[str, str]] = {
    "sb_rate":   {"feature": "minor_sb_rate",   "label": "mlb_sb_rate",   "denom": "mlb_sbo"},
    "att_rate":  {"feature": "minor_att_rate",  "label": "mlb_att_rate",  "denom": "mlb_sbo"},
    "succ_rate": {"feature": "minor_succ_rate", "label": "mlb_succ_rate", "denom": "mlb_sb"},
    "sb_per_pa": {"feature": "minor_sb_per_pa", "label": "mlb_sb_per_pa", "denom": "mlb_pa"},
}
PRIMARY_TARGET = "sb_rate"

# Physically-plausible MLB-rate range — a projection outside this is a broken map, not a bold call
# (mirrors `milb_mle.PLAUSIBLE_RANGE`). A rate is a proportion of opportunities; >0.75 has never
# happened over a 150-PA-plus label window.
PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "sb_rate": (0.0, 0.75), "att_rate": (0.0, 0.90),
    "succ_rate": (0.0, 1.0), "sb_per_pa": (0.0, 0.30),
}


class AnchorFitError(RuntimeError):
    """An anchor could not be fitted. RAISED, never swallowed.

    ⭐ NF1.7 (a): an anchor that fails to fit makes its check VACUOUSLY TRUE. NF1.7's per-position
    oracle silently returned `None` under 40 rows and `oracle_respected` passed on NOTHING. A missing
    or failed anchor is a hard failure here, so a thin fold can never be mistaken for a clean run.
    """


# ══════════════════════════════════════════════════════════════════════════════════════
# Scoring — CRPS primary, MAE reported
# ══════════════════════════════════════════════════════════════════════════════════════

def crps_gaussian(mu: np.ndarray, sigma: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Closed-form CRPS of a Gaussian predictive against observations (lower is better).

        CRPS(N(mu,sigma), y) = sigma * [ z(2*Phi(z) - 1) + 2*phi(z) - 1/sqrt(pi) ],  z = (y-mu)/sigma

    Analytic rather than sampled on purpose: a stochastic selection metric would make PBO/DSR
    meaningless (the same reason `comp_validation.crps_sample` computes both terms exactly).

    ⚠️ `sigma` is floored at a small positive value. A zero-sigma predictive is a point forecast, for
    which CRPS degenerates to |y-mu| — which is the correct limit, and the floor reaches it smoothly
    instead of dividing by zero.
    """
    from scipy.stats import norm

    mu = np.asarray(mu, dtype=float)
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-9)
    y = np.asarray(y, dtype=float)
    z = (y - mu) / sigma
    return sigma * (z * (2.0 * norm.cdf(z) - 1.0) + 2.0 * norm.pdf(z) - 1.0 / np.sqrt(np.pi))


def score_predictions(mu: np.ndarray, sigma: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """The scoring panel for one arm on one fold. CRPS is the SELECTOR; the rest are reported.

    MAE is carried deliberately even though it is never selected on — the whole point of the NF-D14
    discipline is to SHOW the degenerate's MAE beside its CRPS so a reader can see whether the
    inversion fired on this cohort, rather than take the choice of selector on faith.
    """
    mu, sigma, y = np.asarray(mu, float), np.asarray(sigma, float), np.asarray(y, float)
    ok = np.isfinite(mu) & np.isfinite(y)
    if not ok.any():
        return {"crps": float("nan"), "mae": float("nan"), "rmse": float("nan"),
                "bias": float("nan"), "n": 0}
    mu, sigma, y = mu[ok], np.where(np.isfinite(sigma[ok]), sigma[ok], 1e-9), y[ok]
    return {
        "crps": float(np.mean(crps_gaussian(mu, sigma, y))),
        "mae": float(np.mean(np.abs(y - mu))),
        "rmse": float(np.sqrt(np.mean((y - mu) ** 2))),
        "bias": float(np.mean(mu - y)),
        "n": int(len(y)),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# The candidate arms — a common (fit, predict → mean, sd) interface
# ══════════════════════════════════════════════════════════════════════════════════════

class SbProjector:
    """Common interface. `predict` returns (mean, sd) — an arm with no honest spread returns the
    train-residual sd, so CRPS can grade it rather than silently rewarding a point forecast."""

    name = "base"
    #: does this arm read the era baseline? Used to build the matched-foil pairs (NF-D10).
    uses_era = False

    def fit(self, train: pd.DataFrame) -> "SbProjector":  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:  # pragma: no cover
        raise NotImplementedError

    def clone(self) -> "SbProjector":  # pragma: no cover - interface
        raise NotImplementedError


def _feat(df: pd.DataFrame, col: str) -> np.ndarray:
    return pd.to_numeric(df.get(col), errors="coerce").to_numpy(float)


def _resid_sd(y: np.ndarray, yhat: np.ndarray) -> float:
    r = y - yhat
    r = r[np.isfinite(r)]
    return float(np.std(r, ddof=1)) if r.size > 2 and np.std(r, ddof=1) > 0 else 1e-3


# ── Degenerate ceilings — BOTH must lose (NF1.7 (c)) ──────────────────────────────────────────────

class DegenerateZeroProjector(SbProjector):
    """Project ZERO for everyone. The NF-D11 nihilist.

    ⭐ THIS ARM WINNING MAE ON A ZERO-HEAVY TARGET IS NOT A BUG IN THE ARM — IT IS THE TELL THAT THE
    SELECTOR IS INVERTED. It is scored every run and reported on BOTH metrics precisely so the
    inversion is measured rather than reasoned about.
    """

    name = "degenerate_zero"

    def fit(self, train: pd.DataFrame) -> "DegenerateZeroProjector":
        self.sd_ = _resid_sd(train["target"].to_numpy(float), np.zeros(len(train)))
        return self

    def predict(self, df: pd.DataFrame):
        return np.zeros(len(df)), np.full(len(df), self.sd_)

    def clone(self):
        return DegenerateZeroProjector()


class DegenerateMeanProjector(SbProjector):
    """Project the TRAIN mean for everyone — maximally hedged, the other side of NF1.7 (c).

    Also the honest NULL the translation must beat: "we know his level and era and nothing else".
    """

    name = "degenerate_mean"

    def fit(self, train: pd.DataFrame) -> "DegenerateMeanProjector":
        y = train["target"].to_numpy(float)
        self.mu_ = float(np.nanmean(y))
        self.sd_ = _resid_sd(y, np.full(len(y), self.mu_))
        return self

    def predict(self, df: pd.DataFrame):
        return np.full(len(df), self.mu_), np.full(len(df), self.sd_)

    def clone(self):
        return DegenerateMeanProjector()


class LevelMeanProjector(SbProjector):
    """The FOIL: the train mean of the target WITHIN the row's level. This is the incumbent —
    it is exactly what the board knows today about a prospect's running (his level, and nothing
    player-specific). Every arm must beat this to be worth a weight."""

    name = "L0_foil"

    def fit(self, train: pd.DataFrame) -> "LevelMeanProjector":
        y = train["target"].to_numpy(float)
        self.global_ = float(np.nanmean(y))
        self.by_level_ = train.groupby("level")["target"].mean().to_dict()
        yhat = train["level"].map(self.by_level_).fillna(self.global_).to_numpy(float)
        self.sd_ = _resid_sd(y, yhat)
        return self

    def predict(self, df: pd.DataFrame):
        mu = df["level"].map(self.by_level_).fillna(self.global_).to_numpy(float)
        return mu, np.full(len(df), self.sd_)

    def clone(self):
        return LevelMeanProjector()


class IdentityProjector(SbProjector):
    """Use the MiLB rate UNCHANGED — no translation at all. A reference, not selectable: if this
    won, the honest finding would be "the minor rate needs no map", not "we built a model"."""

    name = "identity_no_translation"

    def fit(self, train: pd.DataFrame) -> "IdentityProjector":
        yhat = _feat(train, "feat")
        self.fallback_ = float(np.nanmean(train["target"].to_numpy(float)))
        self.sd_ = _resid_sd(train["target"].to_numpy(float), np.nan_to_num(yhat, nan=self.fallback_))
        return self

    def predict(self, df: pd.DataFrame):
        mu = np.nan_to_num(_feat(df, "feat"), nan=self.fallback_)
        return mu, np.full(len(df), self.sd_)

    def clone(self):
        return IdentityProjector()


# ── Real candidates ───────────────────────────────────────────────────────────────────────────────

class LevelFactorProjector(SbProjector):
    """A per-LEVEL multiplicative translation factor: MLB_rate ≈ factor[level] × minor_rate.

    The classic MLE form (E7.3's `MultiplicativeFactorProjector` shape). `min_support` guards a level
    whose train cell is too thin to estimate a factor from — it falls back to the pooled factor
    rather than fitting noise.
    """

    name = "level_factor"

    def __init__(self, min_support: int = 20, use_era: bool = False):
        self.min_support = int(min_support)
        self.uses_era = bool(use_era)

    def _x(self, df: pd.DataFrame) -> np.ndarray:
        """The feature, era-corrected when this arm carries the era term.

        The correction expresses the minor rate as a MULTIPLE of the environment he ran in, so a 2019
        line and a 2024 line at the same raw rate are not treated as the same ability.
        """
        x = _feat(df, "feat")
        if not self.uses_era:
            return x
        env = _feat(df, "feat_env")
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.where(np.isfinite(env) & (env > 0), x / env, np.nan)
        return np.where(np.isfinite(rel), rel, x)

    def fit(self, train: pd.DataFrame) -> "LevelFactorProjector":
        x, y = self._x(train), train["target"].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y) & (x > 0)
        self.pooled_ = float(np.sum(y[ok]) / np.sum(x[ok])) if ok.any() and np.sum(x[ok]) > 0 else 1.0
        self.by_level_: dict[str, float] = {}
        lv = train["level"].to_numpy(object)
        for level in pd.unique(lv):
            m = ok & (lv == level)
            if int(m.sum()) >= self.min_support and np.sum(x[m]) > 0:
                self.by_level_[level] = float(np.sum(y[m]) / np.sum(x[m]))
        self.global_mean_ = float(np.nanmean(y))
        self.sd_ = _resid_sd(y, self._mu(train))
        return self

    def _mu(self, df: pd.DataFrame) -> np.ndarray:
        x = self._x(df)
        f = df["level"].map(self.by_level_).fillna(self.pooled_).to_numpy(float)
        mu = x * f
        return np.where(np.isfinite(mu), mu, self.global_mean_)

    def predict(self, df: pd.DataFrame):
        return self._mu(df), np.full(len(df), self.sd_)

    def clone(self):
        return LevelFactorProjector(self.min_support, self.uses_era)


class RidgeProjector(SbProjector):
    """Regularized linear map on the minor rate + level + age (+ era). The direct-learned foil §0.5
    requires beside any prescribed structure.

    `alpha` is the ridge penalty; both grid points are pre-registered configs and both count toward
    PBO/DSR (deflation is what makes the small search safe).
    """

    name = "ridge"

    def __init__(self, alpha: float = 1.0, use_era: bool = False, use_age: bool = True):
        self.alpha = float(alpha)
        self.uses_era = bool(use_era)
        self.use_age = bool(use_age)

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.nan_to_num(_feat(df, "feat"), nan=self.feat_mu_)]
        if self.uses_era:
            env = _feat(df, "feat_env")
            cols.append(np.nan_to_num(env, nan=self.env_mu_))
            # the interaction is where an era term actually acts on a RATE: the same raw rate means
            # a different ability in a different running environment
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = np.where(np.isfinite(env) & (env > 0),
                               np.nan_to_num(_feat(df, "feat"), nan=self.feat_mu_) / env, np.nan)
            cols.append(np.nan_to_num(rel, nan=self.rel_mu_))
        if self.use_age:
            cols.append(np.nan_to_num(_feat(df, "age"), nan=self.age_mu_))
        for level in self.levels_:
            cols.append((df["level"].to_numpy(object) == level).astype(float))
        return np.column_stack(cols)

    def fit(self, train: pd.DataFrame) -> "RidgeProjector":
        from sklearn.linear_model import Ridge

        self.feat_mu_ = float(np.nanmean(_feat(train, "feat")))
        self.age_mu_ = float(np.nanmean(_feat(train, "age")))
        env = _feat(train, "feat_env")
        self.env_mu_ = float(np.nanmean(env)) if np.isfinite(env).any() else 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            rel0 = np.where(np.isfinite(env) & (env > 0),
                            np.nan_to_num(_feat(train, "feat"), nan=self.feat_mu_) / env, np.nan)
        self.rel_mu_ = float(np.nanmean(rel0)) if np.isfinite(rel0).any() else 0.0
        self.levels_ = sorted(pd.unique(train["level"].dropna()))
        X, y = self._design(train), train["target"].to_numpy(float)
        self.model_ = Ridge(alpha=self.alpha).fit(X, y)
        self.global_mean_ = float(np.nanmean(y))
        self.sd_ = _resid_sd(y, self.model_.predict(X))
        return self

    def predict(self, df: pd.DataFrame):
        mu = self.model_.predict(self._design(df))
        return np.where(np.isfinite(mu), mu, self.global_mean_), np.full(len(df), self.sd_)

    def clone(self):
        return RidgeProjector(self.alpha, self.uses_era, self.use_age)


class GBMProjector(SbProjector):
    """Gradient-boosted nonlinear map with a QUANTILE-derived spread — the only arm whose sd is
    genuinely per-player rather than a pooled residual, which CRPS can reward."""

    name = "gbm"

    def __init__(self, n_estimators: int = 300, max_depth: int = 2, learning_rate: float = 0.03,
                 use_era: bool = False):
        self.n_estimators, self.max_depth, self.learning_rate = n_estimators, max_depth, learning_rate
        self.uses_era = bool(use_era)

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.nan_to_num(_feat(df, "feat"), nan=self.feat_mu_),
                np.nan_to_num(_feat(df, "age"), nan=self.age_mu_)]
        if self.uses_era:
            cols.append(np.nan_to_num(_feat(df, "feat_env"), nan=self.env_mu_))
        for level in self.levels_:
            cols.append((df["level"].to_numpy(object) == level).astype(float))
        return np.column_stack(cols)

    def fit(self, train: pd.DataFrame) -> "GBMProjector":
        from sklearn.ensemble import GradientBoostingRegressor

        self.feat_mu_ = float(np.nanmean(_feat(train, "feat")))
        self.age_mu_ = float(np.nanmean(_feat(train, "age")))
        env = _feat(train, "feat_env")
        self.env_mu_ = float(np.nanmean(env)) if np.isfinite(env).any() else 0.0
        self.levels_ = sorted(pd.unique(train["level"].dropna()))
        X, y = self._design(train), train["target"].to_numpy(float)
        common = dict(n_estimators=self.n_estimators, max_depth=self.max_depth,
                      learning_rate=self.learning_rate, random_state=0)
        self.mean_ = GradientBoostingRegressor(**common).fit(X, y)
        self.lo_ = GradientBoostingRegressor(loss="quantile", alpha=0.159, **common).fit(X, y)
        self.hi_ = GradientBoostingRegressor(loss="quantile", alpha=0.841, **common).fit(X, y)
        self.global_mean_ = float(np.nanmean(y))
        return self

    def predict(self, df: pd.DataFrame):
        X = self._design(df)
        mu = self.mean_.predict(X)
        sd = np.maximum((self.hi_.predict(X) - self.lo_.predict(X)) / 2.0, 1e-6)
        return np.where(np.isfinite(mu), mu, self.global_mean_), sd

    def clone(self):
        return GBMProjector(self.n_estimators, self.max_depth, self.learning_rate, self.uses_era)


class BetaBinomShrinkProjector(SbProjector):
    """Empirical-Bayes shrunk rate: the player's minor SB/SBO shrunk toward his level's mean by a
    fitted prior strength, then mapped to MLB by the pooled level factor.

    The form that takes the ZERO-HEAVINESS seriously: a player with 2 steals in 30 opportunities and
    one with 20 in 300 have the same raw rate and very different evidence, and a Beta-Binomial says
    so. `k_prior` (in opportunity units) is fitted on TRAIN by direct CRPS minimisation over a small
    pre-registered grid — the same deflation posture as the other grids.
    """

    name = "beta_binom"

    def __init__(self, k_grid: tuple[float, ...] = (25.0, 75.0, 200.0), use_era: bool = False):
        self.k_grid = k_grid
        self.uses_era = bool(use_era)

    def _shrunk(self, df: pd.DataFrame, k: float) -> np.ndarray:
        sb = pd.to_numeric(df.get("feat_num"), errors="coerce").to_numpy(float)
        opp = pd.to_numeric(df.get("feat_den"), errors="coerce").to_numpy(float)
        prior = df["level"].map(self.prior_by_level_).fillna(self.prior_).to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = (np.nan_to_num(sb) + k * prior) / (np.nan_to_num(opp) + k)
        return np.where(np.isfinite(out), out, prior)

    def fit(self, train: pd.DataFrame) -> "BetaBinomShrinkProjector":
        y = train["target"].to_numpy(float)
        sb = pd.to_numeric(train.get("feat_num"), errors="coerce").to_numpy(float)
        opp = pd.to_numeric(train.get("feat_den"), errors="coerce").to_numpy(float)
        tot_opp = float(np.nansum(opp))
        self.prior_ = float(np.nansum(sb) / tot_opp) if tot_opp > 0 else float(np.nanmean(y))
        self.prior_by_level_ = {}
        lv = train["level"].to_numpy(object)
        for level in pd.unique(lv):
            m = lv == level
            d = float(np.nansum(opp[m]))
            if d > 0:
                self.prior_by_level_[level] = float(np.nansum(sb[m]) / d)
        # pick k on TRAIN by CRPS (never peeking at the eval fold), then the pooled minor→major factor
        best = (float("inf"), self.k_grid[0], 1.0, 1e-3)
        for k in self.k_grid:
            x = self._shrunk(train, k)
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0)
            factor = float(np.sum(y[ok]) / np.sum(x[ok])) if ok.any() and np.sum(x[ok]) > 0 else 1.0
            mu = x * factor
            sd = _resid_sd(y, mu)
            c = float(np.mean(crps_gaussian(mu, np.full(len(y), sd), y)))
            if np.isfinite(c) and c < best[0]:
                best = (c, k, factor, sd)
        _, self.k_, self.factor_, self.sd_ = best
        self.global_mean_ = float(np.nanmean(y))
        return self

    def predict(self, df: pd.DataFrame):
        mu = self._shrunk(df, self.k_) * self.factor_
        return np.where(np.isfinite(mu), mu, self.global_mean_), np.full(len(df), self.sd_)

    def clone(self):
        return BetaBinomShrinkProjector(self.k_grid, self.uses_era)


# ══════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field
# ══════════════════════════════════════════════════════════════════════════════════════

#: arms that are REPORTED but never selected — floors, foils and degenerates
NON_SELECTABLE = {"L0_foil", "identity_no_translation", "degenerate_zero", "degenerate_mean"}

#: the ANCHOR arms, excluded from the DSR trial field entirely.
#: ⭐ MH2.1 (a): A DIAGNOSTIC ANCHOR IS NEVER A TRIAL. The E2.1-r oracle leaked into MH2.1's DSR
#: field, drove cross-trial dispersion to V≈220 and made DSR unclearable for a purely ARITHMETIC
#: reason — the anchor that exists to POLICE the metric was setting the gate's own bar.
ANCHOR_ARMS = {"oracle_peek", "permutation"}


@dataclass
class ArmSpec:
    """One pre-registered arm. `pair_with` names its MATCHED FOIL — the byte-identical arm minus the
    era term — so the era family is read as a PAIRED delta (NF-D10), never as a leaderboard rank."""

    label: str
    factory: object
    selectable: bool = True
    pair_with: str | None = None
    note: str = ""


def build_field(min_support: int = 20) -> list[ArmSpec]:
    """The full pre-registered arm field for the PRIMARY target.

    ⭐ ONE COHERENT, DECLARED FAMILY (MH2 (a)). The field is exactly: the foil, two degenerate
    ceilings, the no-translation reference, and four learner classes each in a raw and an
    era-corrected variant. It is NOT trimmed after the fact — "you get to pre-register a family; you
    do not get to discover one" — and the era variants are matched pairs so the era term's
    contribution is attributable rather than ranked.
    """
    return [
        ArmSpec("L0_foil", lambda: LevelMeanProjector(), selectable=False,
                note="the incumbent: level mean, i.e. what the board knows today"),
        ArmSpec("degenerate_zero", lambda: DegenerateZeroProjector(), selectable=False,
                note="NF-D11 nihilist — MUST LOSE"),
        ArmSpec("degenerate_mean", lambda: DegenerateMeanProjector(), selectable=False,
                note="NF1.7 (c) other side — MUST LOSE"),
        ArmSpec("identity_no_translation", lambda: IdentityProjector(), selectable=False,
                note="the raw minor rate, unmapped"),
        ArmSpec("level_factor", lambda: LevelFactorProjector(min_support, use_era=False)),
        ArmSpec("level_factor_era", lambda: LevelFactorProjector(min_support, use_era=True),
                pair_with="level_factor"),
        ArmSpec("ridge_a1", lambda: RidgeProjector(1.0, use_era=False)),
        ArmSpec("ridge_a1_era", lambda: RidgeProjector(1.0, use_era=True), pair_with="ridge_a1"),
        ArmSpec("ridge_a10", lambda: RidgeProjector(10.0, use_era=False)),
        ArmSpec("gbm", lambda: GBMProjector(300, 2, 0.03, use_era=False)),
        ArmSpec("gbm_era", lambda: GBMProjector(300, 2, 0.03, use_era=True), pair_with="gbm"),
        ArmSpec("beta_binom", lambda: BetaBinomShrinkProjector(use_era=False)),
    ]


# the current-prospect cohort is a synthetic "future" debut cohort so it trains on EVERY graduated
# cohort (a prospect has not debuted, so all graduated players are strictly-prior). Mirrors
# `milb_mle._PROSPECT_COHORT_SENTINEL` exactly.
PROSPECT_COHORT_SENTINEL = 9999


def emit_projections(data: pd.DataFrame, winner_factory,
                     target_form: str = PRIMARY_TARGET) -> pd.DataFrame:
    """Emit a leakage-safe MLB-equivalent SB line for EVERY usable minor line.

    Byte-for-byte the same expanding-window discipline as `milb_mle.emit_projections`: for each
    debut cohort Y, the winner is REFIT on labelled rows from STRICTLY-PRIOR cohorts, then applied to
    cohort Y. Active prospects get the synthetic future cohort so they are fit on ALL graduated
    players. The earliest graduated cohort is a SEED and is not emitted (its map would need a prior
    cohort that does not exist).

    ⚠️ Sharing the discipline is the point: an SB line emitted under a DIFFERENT leakage rule than
    the k_pct/bb_pct/iso lines could not honestly be blended with them in one score.
    """
    if "has_minor_line" not in data.columns:
        raise ValueError("emit_projections needs an eligibility-flagged frame (build_sb_pairs)")
    emit_pool = data[data["has_minor_line"].astype(bool)].copy()
    train_pool = data[data["has_target"].astype(bool)].copy()
    graduated = sorted(int(y) for y in train_pool["debut_cohort"].dropna().unique())
    if not graduated or emit_pool.empty:
        return pd.DataFrame()

    emit_pool["emit_cohort"] = emit_pool["debut_cohort"]
    emit_pool.loc[emit_pool["is_prospect"].astype(bool), "emit_cohort"] = PROSPECT_COHORT_SENTINEL

    lo, hi = PLAUSIBLE_RANGE[target_form]
    out_rows: list[pd.DataFrame] = []
    for year in sorted(int(y) for y in emit_pool["emit_cohort"].dropna().unique()):
        prior = [c for c in graduated if c < year]
        if not prior:
            continue
        train = train_pool[train_pool["debut_cohort"].isin(prior)]
        if train.empty:
            continue
        model = winner_factory().fit(train)
        rows = emit_pool[emit_pool["emit_cohort"] == year].copy()
        mean, sd = model.predict(rows)
        rows[f"mle_{target_form}"] = np.clip(mean, lo, hi)
        rows[f"mle_{target_form}_sd"] = sd
        rows["n_prior_cohorts"] = len(prior)
        rows["n_prior_pairs"] = int(len(train))
        out_rows.append(rows)

    if not out_rows:
        return pd.DataFrame()
    proj = pd.concat(out_rows, ignore_index=True)
    proj["sport"] = "mlb"
    proj["player_type"] = "batter"
    proj["metric"] = target_form
    proj["model_version"] = MODEL_VERSION
    keep = ["sport", "player_type", "metric", "player_id", "player_name", "level", "league",
            "debut_cohort", "is_prospect", "age", "minor_pa", "minor_sbo", "minor_sb", "minor_cs",
            f"minor_{target_form}", f"mlb_{target_form}",
            f"mle_{target_form}", f"mle_{target_form}_sd",
            "n_prior_cohorts", "n_prior_pairs", "model_version"]
    return proj[[c for c in keep if c in proj.columns]]


# ══════════════════════════════════════════════════════════════════════════════════════
# Target construction
# ══════════════════════════════════════════════════════════════════════════════════════

def build_target(pairs: pd.DataFrame, target_form: str = PRIMARY_TARGET) -> pd.DataFrame:
    """Attach the modelling columns for one target form: `feat`, `target`, `feat_env`, and the
    Beta-Binomial's numerator/denominator counts.

    Only rows with `has_target` are usable for fitting; the caller filters. Nothing here imputes a
    missing rate to 0 — an unknown rate stays NaN so it can be excluded, never silently counted as
    "cannot run" (the direction that would flatter the zero degenerate).
    """
    if target_form not in TARGET_FORMS:
        raise ValueError(f"target_form {target_form!r} not in {tuple(TARGET_FORMS)}")
    spec = TARGET_FORMS[target_form]
    out = pairs.copy().reset_index(drop=True)
    out["feat"] = pd.to_numeric(out.get(spec["feature"]), errors="coerce")
    out["target"] = pd.to_numeric(out.get(spec["label"]), errors="coerce")
    # the era baseline for THIS form's feature (attempt-based forms use the attempt environment)
    env_col = "minor_env_att_rate" if target_form == "att_rate" else "minor_env_sb_rate"
    out["feat_env"] = pd.to_numeric(out.get(env_col), errors="coerce")
    # Beta-Binomial counts: successes / opportunities on the MINOR side
    num_col = {"sb_rate": "minor_sb", "att_rate": "minor_sb", "succ_rate": "minor_sb",
               "sb_per_pa": "minor_sb"}[target_form]
    den_col = {"sb_rate": "minor_sbo", "att_rate": "minor_sbo", "succ_rate": "minor_sbo",
               "sb_per_pa": "minor_pa"}[target_form]
    out["feat_num"] = pd.to_numeric(out.get(num_col), errors="coerce")
    out["feat_den"] = pd.to_numeric(out.get(den_col), errors="coerce")
    out["usable"] = (out.get("has_target", False).astype(bool)
                     & out["feat"].notna() & out["target"].notna())
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# The anchors (fitted per fold, RAISE on failure)
# ══════════════════════════════════════════════════════════════════════════════════════

def fit_oracle(arm_factory, train: pd.DataFrame, test: pd.DataFrame,
               rng_seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """The PEEKING oracle: the winner's OWN arm family, refit ON THE HELD-OUT FOLD ITSELF.

    ⭐ NF1.7 (b) / NF1.9 (f): "peeking can only help" holds ONLY at equal FAMILY and equal RESOLUTION.
    Same family is enforced by taking the same `arm_factory`. Sample size is NOT matched — the oracle
    fits the ~n_test held-out rows while the real arm trains on the whole prior history — so a real
    arm BEATING this oracle is admissible (NF-D14 measured exactly that at unmatched n) and is
    reported as a capacity effect rather than treated as an inversion. The MATCHED-n companion is
    `fit_matched_n_candidate`.

    RAISES `AnchorFitError` rather than returning None (NF1.7 (a)).
    """
    if len(test) < 3:
        raise AnchorFitError(
            f"oracle cannot fit: held-out fold has {len(test)} rows (<3). An anchor that cannot fit "
            f"makes its check vacuously true — refusing to report a pass (NF1.7 (a)).")
    try:
        arm = arm_factory().fit(test)
        return arm.predict(test)
    except Exception as e:  # noqa: BLE001 - surfaced, never swallowed
        raise AnchorFitError(f"oracle fit failed: {type(e).__name__}: {e}") from e


def fit_matched_n_candidate(arm_factory, train: pd.DataFrame, test: pd.DataFrame,
                            rng_seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """The winner's own arm trained on a RANDOM TRAIN SUBSAMPLE THE SIZE OF THE ORACLE'S FIT.

    NF1.9 (f) shipped as runnable code: the oracle is a legitimate floor only at matched n, so the
    gate is "the oracle beats THIS", not "the oracle beats the full-history arm".
    """
    n = min(len(test), len(train))
    if n < 3:
        raise AnchorFitError(
            f"matched-n candidate cannot fit: n={n} (<3) — refusing a vacuous pass (NF1.7 (a)).")
    sub = train.sample(n=n, random_state=rng_seed)
    try:
        arm = arm_factory().fit(sub)
        return arm.predict(test)
    except Exception as e:  # noqa: BLE001
        raise AnchorFitError(f"matched-n fit failed: {type(e).__name__}: {e}") from e


def fit_permutation(arm_factory, train: pd.DataFrame, test: pd.DataFrame,
                    rng_seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """The winner's own arm fit on SHUFFLED labels. Well-posed at ANY n (NF1.7 (b)).

    ⭐ **WHAT THIS ANCHOR ACTUALLY ASKS — AND THE MIS-SPECIFICATION IT COST US (E8.3, first run).**
    The permutation arm must SYSTEMATICALLY LOSE TO THE BEST ARM: shuffling destroys the
    feature→label relation, so an arm that still competed would mean the winner's margin came from
    somewhere other than the feature. That is the coherent question, and it is the one now gated on.

    ⚠️ It must NOT be registered as "beats the FOIL ⇒ leak". Shuffling the label destroys the
    feature relation but PRESERVES the label's marginal and, in expectation, its level structure —
    which is exactly what the level-mean foil encodes. So **permutation ≈ foil is the PREDICTED
    outcome**, and the first cut of this story registered it as a violation and duly "caught" a
    0.0006 CRPS gap (1.4%) that the paired test scores at p=0.87 on 5 of 11 folds — a numerical TIE
    read as fatal, which is the E2.1-r / NF1.8 error `paired_anchor`'s own docstring was written
    about. Per NF-D16 (2), an anchor whose mechanism cannot act on the comparison is registered as an
    expected TIE **in advance** and proven, never presented as a passed test.
    """
    if len(train) < 3:
        raise AnchorFitError(
            f"permutation cannot fit: train has {len(train)} rows (<3) — refusing a vacuous pass.")
    shuffled = train.copy()
    rng = np.random.default_rng(rng_seed)
    shuffled["target"] = rng.permutation(shuffled["target"].to_numpy(float))
    try:
        arm = arm_factory().fit(shuffled)
        return arm.predict(test)
    except Exception as e:  # noqa: BLE001
        raise AnchorFitError(f"permutation fit failed: {type(e).__name__}: {e}") from e

"""milb_mle.py — MLB Edge-E7.3: the minor→major translation factors (MLEs), the modeling crux.

WHAT THIS IS
------------
For a player with a minor-league body of work, translate a raw MiLB rate line (wOBA, K%, BB%,
ISO — plus AAA Statcast summaries where they exist) into an **MLB-equivalent rate line with honest
uncertainty**. It is the baseball analog of the NCAAF-P1.2b (recruit→freshman) and P1A (college→NFL)
feeder MLEs — one rung of the same pattern — and it reuses the SAME sport-agnostic partial-pooling
solver (`betting_ml/utils/hierarchical.py`, promoted here from the football tree).

WHY IT MATTERS. The EB posteriors today shrink a low-MLB-PA player toward a GENERIC archetype prior
(`k≈200 PA` — see `eb_batter_posteriors_raw`). A rookie's actual AAA line is far more informative than
that generic prior, but a raw AAA .350 wOBA is NOT a .350 MLB wOBA — the level/league run environment
differs. The MLE closes that gap: a performance-based, level-aware MLB prior for players the market
prices priors-only. It is the Dynasty (E8) moat and the rookie prior for the betting sub-models (E7.5).

⚠️ HONEST FRAMING. This is a PRIOR/projection, NOT an edge claim, and `best_alpha = 0` applies (it is a
projection + a betting prior, never a market bet). Its uncertainty is PARAMETER uncertainty (how well
the minor→major map is pinned down at this player's inputs), NOT a calibrated predictive interval for
the player's realized MLB line — see `UNCERTAINTY SEMANTICS`. The MiLB→MLB signal is genuine but
MODEST (a graduated-player population is small and self-selected); a ROBUST-BUT-WEAK result (low PBO,
DSR possibly <0.95) is a VALID and VALUABLE deliverable here — reported honestly, not forced (the
P1.2b DSR-0.821 precedent).

THE §0.5 BAKE-OFF (this is a MODEL, not a lookup-table)
-------------------------------------------------------
Per the standing discipline, "level×league factors, EB-shrunk for thin cells" is ONE candidate, not
the whole story. Pre-registered candidate set (each grid-tuned, every config counts to PBO/DSR):

  (a) ⭐ PARTIAL POOLING via the shared solver (`hierarchical.py`, REUSED UNCHANGED) — a random-slopes
      model: a GLOBAL minor→MLB line (fixed intercept + minor-rate slope + age), PLUS per-LEVEL
      intercept AND minor-rate-slope deviations and per-LEAGUE intercept deviations that carry a shared
      N(0, tau^2) prior and are EB-shrunk toward the global line. A thin level×league cell is pulled to
      the league-wide relationship, not trusted at face value. The solver's boundary-avoiding Gamma(2,·)
      tau prior + multi-start are MANDATORY here (thin cells make ML collapse a variance component to 0,
      silently deleting a hierarchy level — the P1.2 bug). Ties the program's Bayesian selling point.
  (b) MULTIPLICATIVE run-environment factors (the interpretable, classic-MLE foil) — MLB_hat =
      f_(level,league) · minor_rate, with f an EB-shrunk ratio-of-means per (level,league) toward the
      global ratio. This is the Davenport/James minor-league-equivalency in its traditional form.
  (c) LEARNED GBM on [minor rate, level one-hot, league one-hot, age, log(PA), + AAA Statcast where
      present (impute-with-flag)] → MLB rate. The "does the kitchen sink of features add signal"
      candidate; the ONLY one that reads the E7.2 AAA-Statcast add (a coverage-conditioned feature —
      honest-null a player/season without it).
  (d) LEVEL-MEAN NULL FLOOR — predict the training level-cohort mean of the MLB metric, IGNORE the
      player's own minor line. If nothing beats this, the honest answer is "the minor line carries no
      translatable signal beyond which level the player was at."

  Plus two reported-not-selected BENCHMARKS that contextualize the value proposition:
    * `identity_no_translation` — MLB_hat = the raw minor rate, NO adjustment. Does translating the
      number beat just using it as-is?
    * `archetype_prior` — predict the population MLB mean of the metric (what the incumbent generic
      `k≈200` EB shrinkage collapses to at low PA). This is the prior E7.3 must BEAT to earn its place.
  Both are EXCLUDED from winner selection — a "translation" whose winner is a no-op or the population
  mean would not be a translation at all — but reported, because whether the MLE beats them is the
  whole point.

Selection: leave-one-MLB-DEBUT-COHORT-out EXPANDING-WINDOW CV (project debut cohort Y using ONLY
players who debuted in strictly-prior seasons, whose realized MLB line we already know) on held-out MAE
of the raw MLB metric; PBO<0.2 / DSR≥0.95 over the full config set (reported honestly, per E2.1-r); and
an ORACLE-FLOOR sanity check (a cheating model that sees the true MLB metric must score better than
every real candidate — a candidate beating MAE 0 is mathematically impossible and is the tell of an
inverted metric).

THE TARGET / THE LABEL (why RAW, and why leakage-free)
------------------------------------------------------
The metric is the RAW realized MLB rate — the MLE literally outputs an MLB-EQUIVALENT rate, so it is
NOT standardized (unlike P1A, whose cross-position AV is incomparable; MLB wOBA is directly comparable).
`mlb_<metric>` is the player's realized early-career MLB line (PA-weighted over the first `label_window`
MLB seasons, requiring `mlb_pa ≥ min_mlb_pa`), read from `mart_batter_rolling_stats` season-to-date
`_std` columns. `minor_<metric>` is the player's pre-debut MiLB line at a given LEVEL, aggregated over
MiLB games strictly BEFORE the MLB debut date (the as-of guard). Grain is one row per (player, level):
a player's AAA and AA lines are two translation observations sharing the player's realized MLB label
(a correlated-observation limit stated in the report; per-level rows are what let the model estimate
LEVEL factors at all). A player who never reaches `min_mlb_pa` carries NO label (UNKNOWN, never 0) —
excluded from training, like a P1A UDFA. An ACTIVE PROSPECT (a MiLB line, no MLB debut yet) is the real
deliverable: it carries no label, is excluded from training, but still receives an emitted MLB-equivalent
projection from the latest fitted map, flagged `is_prospect`.

UNCERTAINTY SEMANTICS (say which kind — E7.5 rookie-prior PRICING consumes it)
-----------------------------------------------------------------------------
`mle_<metric>_sd` is PARAMETER uncertainty (posterior sd of the fitted minor→major map at this player's
inputs; the ~16/84 quantile spread for the GBM), NOT a calibrated predictive interval for the player's
realized MLB rate. Like P1.2's `strength_margin_sd` it ranks confidence correctly (a thin level×league
cell or an extreme minor line is wider) but is too tight to price with. **E7.5 (wiring MiLB priors into
`eb_batter_posteriors`) MUST recalibrate on held-out data before pricing** (the E13.6 pattern). An E8
Dynasty display uses `mle_<metric>` as a POINT prior and the sd as a RELATIVE confidence signal only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from betting_ml.utils.hierarchical import Block, DesignSpec, fit

log = logging.getLogger(__name__)

MODEL_VERSION = "milb_mle_v1"

# The four rate metrics the MLE translates (batter side). Each is run as its OWN bake-off (a separate
# minor→major map), analogous to P1A's --target-metric switch — a K% translation is a different
# relationship from a wOBA translation. `minor_<m>` is the feature, `mlb_<m>` is the label.
BATTER_METRICS = ("woba", "k_pct", "bb_pct", "iso")
VALID_METRICS = BATTER_METRICS

# Physically-plausible MLB-rate range per metric — a projected MLB rate outside this is a broken map,
# not a bold projection (mirrors P1.2's ±50-point ceiling / P1A's ±6 sd). Gate in the runner.
PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "woba": (0.150, 0.550),
    "k_pct": (0.0, 0.60),
    "bb_pct": (0.0, 0.35),
    "iso": (0.0, 0.50),
}
# An uncertainty this wide (in the metric's own units) means an unidentified coefficient (P1.2's leak,
# one rung down) — the projection has no information. Gate it.
MAX_PLAUSIBLE_SD: dict[str, float] = {"woba": 0.20, "k_pct": 0.30, "bb_pct": 0.20, "iso": 0.25}

# A (level, league) cell needs at least this many labelled players before it earns its OWN multiplicative
# factor / stratified fit; below it, fall back to the global factor (the partial-pool shrinks
# automatically). A 3-player cell is exactly the thin-cell overfit the pooling exists to prevent.
MIN_CELL_SUPPORT = 12

# The AAA-Statcast add columns (E7.2, AAA-only 2022+). Impute-with-flag, never drop a player who lacks
# them (pre-2022, or a non-AAA line) — a coverage-conditioned feature only the GBM candidate reads.
STATCAST_COLS: tuple[str, ...] = (
    "sc_xwoba", "sc_barrels_per_pa_percent", "sc_hardhit_percent",
    "sc_avg_exit_velocity_mph", "sc_avg_bat_speed_mph",
)

# Levels, ordered nearest-to-MLB first (used for cosmetics / the "highest level" convenience only —
# the model treats level as a categorical factor, not an ordinal).
LEVEL_ORDER = ("Triple-A", "Double-A", "High-A", "Single-A")


# ══════════════════════════════════════════════════════════════════════════════════════
# Metric math (kept in Python so the fast-gate tests exercise it directly; the substrate SQL in
# build_graduated_pairs.py mirrors these exact formulas)
# ══════════════════════════════════════════════════════════════════════════════════════

# FanGraphs-style wOBA linear weights (era-generic constants; the level RUN ENVIRONMENT is exactly what
# the MLE learns on top, so a single weight set is correct — we are not chasing per-season wOBA scale).
_WOBA_W = {"ubb": 0.69, "hbp": 0.72, "b1": 0.89, "b2": 1.27, "b3": 1.62, "hr": 2.10}


def compute_woba_from_counts(df: pd.DataFrame) -> pd.Series:
    """wOBA from box counting stats (the E7.1 `bat_*` columns aggregated over a window).

    wOBA = (0.69·uBB + 0.72·HBP + 0.89·1B + 1.27·2B + 1.62·3B + 2.10·HR)
           / (AB + BB − IBB + SF + HBP).  1B = H − 2B − 3B − HR;  uBB = BB − IBB.
    """
    def c(name: str) -> np.ndarray:
        return pd.to_numeric(df.get(name), errors="coerce").fillna(0.0).to_numpy(float)

    ab, h = c("bat_at_bats"), c("bat_hits")
    dbl, tpl, hr = c("bat_doubles"), c("bat_triples"), c("bat_home_runs")
    bb, ibb, hbp, sf = c("bat_walks"), c("bat_intentional_walks"), c("bat_hit_by_pitch"), c("bat_sac_flies")
    b1 = np.maximum(h - dbl - tpl - hr, 0.0)
    ubb = np.maximum(bb - ibb, 0.0)
    num = (_WOBA_W["ubb"] * ubb + _WOBA_W["hbp"] * hbp + _WOBA_W["b1"] * b1
           + _WOBA_W["b2"] * dbl + _WOBA_W["b3"] * tpl + _WOBA_W["hr"] * hr)
    den = ab + (bb - ibb) + sf + hbp
    out = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
    return pd.Series(out, index=df.index)


def compute_rate_metrics_from_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Attach `minor_woba/k_pct/bb_pct/iso` + `minor_pa` from the aggregated `bat_*` counting stats.

    K% = SO / PA;  BB% = BB / PA;  ISO = (TB − H) / AB = SLG − AVG.  PA = plate appearances.
    """
    def c(name: str) -> np.ndarray:
        return pd.to_numeric(df.get(name), errors="coerce").fillna(0.0).to_numpy(float)

    pa, ab, h, tb = c("bat_plate_appearances"), c("bat_at_bats"), c("bat_hits"), c("bat_total_bases")
    so, bb = c("bat_strike_outs"), c("bat_walks")
    out = df.copy()
    out["minor_pa"] = pa
    out["minor_woba"] = compute_woba_from_counts(df)
    out["minor_k_pct"] = np.divide(so, pa, out=np.full_like(so, np.nan), where=pa > 0)
    out["minor_bb_pct"] = np.divide(bb, pa, out=np.full_like(bb, np.nan), where=pa > 0)
    out["minor_iso"] = np.divide(tb - h, ab, out=np.full_like(ab, np.nan), where=ab > 0)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# Config + target construction
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class MleConfig:
    """Tunables. Defaults are the pre-registered configuration."""

    metric: str = "woba"
    min_cell_support: int = MIN_CELL_SUPPORT
    min_minor_pa: int = 150          # a level line thinner than this is too noisy to translate from
    use_statcast: bool = True        # the GBM reads the AAA-Statcast add where present
    # Partial-pool prior scale grid (× the response sd) — the fixed-effect "flat" prior width. Every
    # entry is a distinct config that COUNTS toward PBO/DSR (deflation makes the search safe).
    pool_prior_scales: tuple[float, ...] = (2.0, 4.0)
    # GBM (n_estimators, max_depth, learning_rate). Same deflation posture.
    gbm_grid: tuple[tuple[int, int, float], ...] = ((300, 2, 0.03), (500, 3, 0.02))

    def __post_init__(self):
        if self.metric not in VALID_METRICS:
            raise ValueError(f"metric {self.metric!r} not in {VALID_METRICS}")

    @property
    def minor_col(self) -> str:
        return f"minor_{self.metric}"

    @property
    def mlb_col(self) -> str:
        return f"mlb_{self.metric}"


def build_target(pairs: pd.DataFrame, config: MleConfig | None = None) -> pd.DataFrame:
    """Attach `feat` (the minor rate for the active metric), `target` (the realized MLB rate), and the
    `has_target` label flag. A row is LABELLED iff it carries a finite minor rate on a thick-enough
    level line AND a realized MLB line meeting the PA floor. An active prospect (no MLB line) or a thin
    level line carries `has_target = False` — UNKNOWN, never 0."""
    config = config or MleConfig()
    out = pairs.copy().reset_index(drop=True)

    feat = pd.to_numeric(out.get(config.minor_col), errors="coerce")
    minor_pa = pd.to_numeric(out.get("minor_pa"), errors="coerce").fillna(0.0)
    out["feat"] = feat
    out["has_minor_line"] = feat.notna() & (minor_pa >= config.min_minor_pa)

    tgt = pd.to_numeric(out.get(config.mlb_col), errors="coerce")
    has_mlb = out.get("has_mlb_label")
    if has_mlb is None:
        mlb_pa = pd.to_numeric(out.get("mlb_pa"), errors="coerce").fillna(0.0)
        has_mlb = tgt.notna() & (mlb_pa > 0)
    out["target"] = tgt
    out["has_mlb_label"] = has_mlb.astype(bool)
    out["has_target"] = out["has_minor_line"] & out["has_mlb_label"] & tgt.notna()
    # A prospect = a usable minor line but no realized MLB label (the emission-only cohort).
    out["is_prospect"] = out["has_minor_line"] & ~out["has_mlb_label"]
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# The candidate projectors — a common (fit, predict → mean, sd) interface
# ══════════════════════════════════════════════════════════════════════════════════════


class _Scaler:
    """Standardize a raw column on TRAIN stats only (leakage-safe — no target, computed at fit, applied
    verbatim at predict). A missing value → 0 (the mean in standardized space) + a `missing` flag."""

    def fit(self, df: pd.DataFrame, col: str) -> "_Scaler":
        v = pd.to_numeric(df.get(col), errors="coerce")
        self.col = col
        self.mu_ = float(v.mean()) if v.notna().any() else 0.0
        self.sd_ = float(v.std(ddof=0)) if v.notna().sum() > 1 and v.std(ddof=0) > 0 else 1.0
        return self

    def transform(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        v = pd.to_numeric(df.get(self.col), errors="coerce").to_numpy(float)
        missing = ~np.isfinite(v)
        z = np.where(missing, 0.0, (np.nan_to_num(v) - self.mu_) / self.sd_)
        return z, missing.astype(float)


class Projector:
    name = "base"
    reads_statcast = False

    def fit(self, train: pd.DataFrame) -> "Projector":  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:  # pragma: no cover
        raise NotImplementedError


class LevelMeanProjector(Projector):
    """NULL FLOOR: predict the training LEVEL-cohort mean of the MLB metric, ignore the minor line.

    This is the honest "the minor line carries no signal beyond which level the player reached" baseline
    every real candidate must beat."""

    name = "level_mean"

    def fit(self, train: pd.DataFrame) -> "LevelMeanProjector":
        t = train[train["has_target"]]
        self.by_level_ = t.groupby("level")["target"].mean().to_dict()
        self.global_ = float(t["target"].mean()) if len(t) else 0.0
        self.sd_ = float(t["target"].std(ddof=0)) if len(t) > 1 else 1.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        mean = df["level"].map(self.by_level_).fillna(self.global_).to_numpy(float)
        return mean, np.full(len(df), max(self.sd_, 1e-9))


class IdentityRefProjector(Projector):
    """REPORTED benchmark (not selectable): MLB_hat = the raw minor rate, NO translation. Does adjusting
    the number beat using it as-is? If identity wins, translation adds nothing."""

    name = "identity_no_translation"

    def fit(self, train: pd.DataFrame) -> "IdentityRefProjector":
        t = train[train["has_target"]]
        resid = (t["target"] - t["feat"]).to_numpy(float)
        self.sd_ = float(np.std(resid)) if len(resid) > 1 else 1.0
        self.global_ = float(t["target"].mean()) if len(t) else 0.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        mean = pd.to_numeric(df["feat"], errors="coerce").fillna(self.global_).to_numpy(float)
        return mean, np.full(len(df), max(self.sd_, 1e-9))


class ArchetypePriorRefProjector(Projector):
    """REPORTED benchmark (not selectable): predict the POPULATION MLB mean of the metric — what the
    incumbent generic `k≈200` EB archetype shrinkage collapses to at low PA. The prior E7.3 must beat to
    justify replacing it."""

    name = "archetype_prior"

    def fit(self, train: pd.DataFrame) -> "ArchetypePriorRefProjector":
        t = train[train["has_target"]]
        self.global_ = float(t["target"].mean()) if len(t) else 0.0
        self.sd_ = float(t["target"].std(ddof=0)) if len(t) > 1 else 1.0
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return np.full(len(df), self.global_), np.full(len(df), max(self.sd_, 1e-9))


class MultiplicativeFactorProjector(Projector):
    """INTERPRETABLE FOIL (the classic Davenport/James minor-league-equivalency): MLB_hat =
    f_(level,league) · minor_rate, with f an EB-shrunk ratio-of-means per (level, league) toward the
    GLOBAL ratio. A thin cell falls back to the global factor. sd from the in-cell residual."""

    name = "multiplicative"

    def __init__(self, min_support: int = MIN_CELL_SUPPORT):
        self.min_support = min_support

    @staticmethod
    def _ratio(t: pd.DataFrame) -> float:
        feat = t["feat"].to_numpy(float)
        tgt = t["target"].to_numpy(float)
        num, den = float(np.nansum(tgt)), float(np.nansum(feat))
        return num / den if den > 0 else 1.0

    def fit(self, train: pd.DataFrame) -> "MultiplicativeFactorProjector":
        t = train[train["has_target"] & np.isfinite(train["feat"])].copy()
        self.global_factor_ = self._ratio(t) if len(t) else 1.0
        self.global_mean_ = float(t["target"].mean()) if len(t) else 0.0
        # EB shrink each cell factor toward the global with a pseudo-count = min_support (Krige-style):
        #   f_cell = (n·f_raw + k·f_global) / (n + k)
        self.by_cell_: dict[tuple, float] = {}
        for cell, idx in t.groupby(["level", "league"]).groups.items():
            g = t.loc[idx]
            n = len(g)
            f_raw = self._ratio(g)
            k = float(self.min_support)
            self.by_cell_[cell] = (n * f_raw + k * self.global_factor_) / (n + k)
        # residual sd of the fitted multiplicative model on train (a single global spread)
        yhat = self._apply(t)
        resid = (t["target"].to_numpy(float) - yhat)
        self.sd_ = float(np.std(resid)) if len(resid) > 1 else 1.0
        return self

    def _apply(self, df: pd.DataFrame) -> np.ndarray:
        feat = pd.to_numeric(df["feat"], errors="coerce").to_numpy(float)
        cells = list(zip(df["level"], df["league"]))
        f = np.array([self.by_cell_.get(c, self.global_factor_) for c in cells])
        out = f * feat
        # a missing minor rate → the global mean (no basis to translate)
        return np.where(np.isfinite(out), out, self.global_mean_)

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return self._apply(df), np.full(len(df), max(self.sd_, 1e-9))


@dataclass
class PartialPoolProjector(Projector):
    """⭐ Candidate (a): the shared mixed-effects solver, reused unchanged.

    Random-slopes design: a GLOBAL minor→MLB line (fixed intercept + minor-rate slope + standardized
    age) PLUS per-LEVEL intercept & minor-rate-slope deviations and per-LEAGUE intercept deviations,
    each a penalized block carrying a shared N(0, tau^2) prior. The EB variance components are chosen by
    marginal likelihood with the boundary-avoiding Gamma(2,·) prior + multi-start, so a thin level×league
    cell is shrunk toward the global line and no variance component silently collapses to 0.
    """

    prior_scale: float = 2.0
    name: str = "partial_pool"

    def fit(self, train: pd.DataFrame) -> "PartialPoolProjector":
        t = train[train["has_target"]].copy().reset_index(drop=True)
        self.feat_scaler_ = _Scaler().fit(t, "feat")
        self.age_scaler_ = _Scaler().fit(t, "age")
        self.levels_ = sorted(t["level"].dropna().unique())
        self.leagues_ = sorted(t["league"].dropna().unique())
        y = t["target"].to_numpy(float)
        X, spec = self._design(t)
        self.post_ = fit(X, y, spec, fixed_prior_sd=self.prior_scale * (float(np.std(y)) or 1.0))
        self.spec_ = spec
        self.global_mean_ = float(np.mean(y)) if len(y) else 0.0
        return self

    def _design(self, df: pd.DataFrame):
        x, _ = self.feat_scaler_.transform(df)
        age, _ = self.age_scaler_.transform(df)
        n = len(df)
        fixed = np.column_stack([np.ones(n), x, age])
        li = np.column_stack([(df["level"] == g).to_numpy(float) for g in self.levels_]) \
            if self.levels_ else np.zeros((n, 0))
        ls = li * x.reshape(-1, 1)
        gi = np.column_stack([(df["league"] == g).to_numpy(float) for g in self.leagues_]) \
            if self.leagues_ else np.zeros((n, 0))
        X = np.hstack([fixed, li, ls, gi])
        blocks = [Block("fixed", ("intercept", "minor", "age"), penalized=False)]
        if self.levels_:
            blocks.append(Block("level_intercept", tuple(f"li__{g}" for g in self.levels_)))
            blocks.append(Block("level_slope", tuple(f"ls__{g}" for g in self.levels_)))
        if self.leagues_:
            blocks.append(Block("league_intercept", tuple(f"gi__{g}" for g in self.leagues_)))
        return X, DesignSpec(tuple(blocks))

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        # rebuild the SAME design against these rows (an unseen level/league has no deviation column →
        # it falls back to the global line, which IS the correct partial-pooling behaviour for a new cell)
        x, _ = self.feat_scaler_.transform(df)
        age, _ = self.age_scaler_.transform(df)
        n = len(df)
        fixed = np.column_stack([np.ones(n), x, age])
        li = np.column_stack([(df["level"] == g).to_numpy(float) for g in self.levels_]) \
            if self.levels_ else np.zeros((n, 0))
        ls = li * x.reshape(-1, 1)
        gi = np.column_stack([(df["league"] == g).to_numpy(float) for g in self.leagues_]) \
            if self.leagues_ else np.zeros((n, 0))
        Xw = np.hstack([fixed, li, ls, gi])
        mean = Xw @ self.post_.mean
        var = np.einsum("ij,jk,ik->i", Xw, self.post_.cov, Xw)
        return mean, np.sqrt(np.maximum(var, 0.0))


class GBMProjector(Projector):
    """Learned gradient-boosted regression on the full feature vector: standardized minor rate + level
    one-hot + league one-hot + standardized age + log(PA) + (AAA-Statcast add, impute-flagged, when
    `use_statcast`). Per-row uncertainty from paired quantile models (the ~16/84 predictive spread)."""

    name = "gbm"
    reads_statcast = True

    def __init__(self, n_estimators: int = 300, max_depth: int = 2, learning_rate: float = 0.03,
                 use_statcast: bool = True):
        self.n_estimators, self.max_depth, self.learning_rate = n_estimators, max_depth, learning_rate
        self.use_statcast = use_statcast

    def _features(self, df: pd.DataFrame) -> np.ndarray:
        z, _ = self.feat_scaler_.transform(df)
        age, _ = self.age_scaler_.transform(df)
        logpa = np.log1p(pd.to_numeric(df.get("minor_pa"), errors="coerce").fillna(0.0).to_numpy(float))
        cols = [z, age, logpa]
        cols += [(df["level"] == g).to_numpy(float) for g in self.levels_]
        cols += [(df["league"] == g).to_numpy(float) for g in self.leagues_]
        if self.use_statcast:
            for sc in self.statcast_scalers_:
                zz, miss = sc.transform(df)
                cols += [zz, miss]
        return np.column_stack(cols)

    def fit(self, train: pd.DataFrame) -> "GBMProjector":
        from sklearn.ensemble import GradientBoostingRegressor

        t = train[train["has_target"]].copy()
        self.feat_scaler_ = _Scaler().fit(t, "feat")
        self.age_scaler_ = _Scaler().fit(t, "age")
        self.levels_ = sorted(t["level"].dropna().unique())
        # keep only leagues with real support as one-hots (avoid a column per rare league)
        vc = t["league"].value_counts()
        self.leagues_ = sorted(vc[vc >= 5].index.tolist())
        self.statcast_scalers_ = [_Scaler().fit(t, c) for c in STATCAST_COLS] if self.use_statcast else []
        X = self._features(t)
        y = t["target"].to_numpy(float)
        common = dict(n_estimators=self.n_estimators, max_depth=self.max_depth,
                      learning_rate=self.learning_rate, random_state=0)
        self.mean_ = GradientBoostingRegressor(**common).fit(X, y)
        self.lo_ = GradientBoostingRegressor(loss="quantile", alpha=0.159, **common).fit(X, y)
        self.hi_ = GradientBoostingRegressor(loss="quantile", alpha=0.841, **common).fit(X, y)
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        X = self._features(df)
        mean = self.mean_.predict(X)
        sd = np.maximum((self.hi_.predict(X) - self.lo_.predict(X)) / 2.0, 1e-9)
        return mean, sd


# the floors/benchmarks that are REPORTED but never selected as the winner
_NON_SELECTABLE = {"level_mean", "identity_no_translation", "archetype_prior"}


def candidate_configs(config: MleConfig) -> list[Projector]:
    """The full pre-registered config set — every one counts toward PBO/DSR (deflation)."""
    cands: list[Projector] = [
        LevelMeanProjector(),
        IdentityRefProjector(),
        ArchetypePriorRefProjector(),
        MultiplicativeFactorProjector(config.min_cell_support),
    ]
    cands += [PartialPoolProjector(prior_scale=s) for s in config.pool_prior_scales]
    cands += [GBMProjector(n, d, lr, use_statcast=config.use_statcast) for (n, d, lr) in config.gbm_grid]
    return cands


def _config_name(c: Projector) -> str:
    if isinstance(c, PartialPoolProjector):
        return f"partial_pool@{c.prior_scale}"
    if isinstance(c, GBMProjector):
        sc = "+sc" if c.use_statcast else ""
        return f"gbm@{c.n_estimators}-{c.max_depth}-{c.learning_rate}{sc}"
    return c.name


def clone_projector(c: Projector) -> Projector:
    """A FRESH unfitted copy of a projector's config (for the expanding-window refits)."""
    if isinstance(c, PartialPoolProjector):
        return PartialPoolProjector(prior_scale=c.prior_scale)
    if isinstance(c, GBMProjector):
        return GBMProjector(c.n_estimators, c.max_depth, c.learning_rate, use_statcast=c.use_statcast)
    if isinstance(c, MultiplicativeFactorProjector):
        return MultiplicativeFactorProjector(c.min_support)
    if isinstance(c, IdentityRefProjector):
        return IdentityRefProjector()
    if isinstance(c, ArchetypePriorRefProjector):
        return ArchetypePriorRefProjector()
    return LevelMeanProjector()


# ══════════════════════════════════════════════════════════════════════════════════════
# The bake-off — leave-one-MLB-debut-cohort-out expanding-window CV + PBO/DSR
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class BakeoffResult:
    metric: str
    winner_name: str
    winner_config: Projector
    leaderboard: pd.DataFrame          # per-config OOS MAE / skill-vs-null
    perf_matrix: np.ndarray            # (n_folds, n_configs) OOS skill (higher better)
    fold_cohorts: list[int]
    pbo: object
    dsr: object
    oracle_floor_ok: bool
    notes: list[str] = field(default_factory=list)


def _mae(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.mean(np.abs(y - yhat)))


def run_bakeoff(pairs: pd.DataFrame, config: MleConfig | None = None) -> BakeoffResult:
    """Fit every candidate under leave-one-DEBUT-COHORT-out expanding-window CV and select.

    Fold Y (an MLB debut cohort with ≥1 strictly-prior cohort) trains on players who debuted BEFORE Y
    and scores on cohort Y — a genuine out-of-sample projection, never peeking at a player's own
    realized MLB line. The per-config OOS skill (MAE reduction vs the level-mean null) fills the PBO
    matrix; the winner's per-fold skill series drives the DSR with n_trials = number of configs.
    """
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

    config = config or MleConfig()
    data = build_target(pairs, config)
    lab = data[data["has_target"]].copy()
    cohorts = sorted(int(y) for y in lab["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(
            f"need ≥2 evaluable debut cohorts (each with a strictly-prior cohort); got {fold_cohorts} "
            f"from cohorts {cohorts}"
        )

    cands = candidate_configs(config)
    names = [_config_name(c) for c in cands]
    notes: list[str] = []

    null_idx = next(i for i, c in enumerate(cands) if c.name == "level_mean")
    perf = np.full((len(fold_cohorts), len(cands)), np.nan)   # OOS skill = null_MAE − model_MAE
    mae_mat = np.full((len(fold_cohorts), len(cands)), np.nan)
    for fi, year in enumerate(fold_cohorts):
        train = lab[lab["debut_cohort"] < year]
        test = lab[lab["debut_cohort"] == year]
        if train.empty or test.empty:
            continue
        y = test["target"].to_numpy(float)
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
                perf[fi, ci] = null_mae - m         # >0 ⇒ the minor line beats the null this fold

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

    # winner = lowest OOS MAE among the SELECTABLE candidates (the floors/benchmarks are context)
    order = np.argsort(mean_mae)
    winner_ci = next(
        i for i in order if cands[i].name not in _NON_SELECTABLE and np.isfinite(mean_mae[i])
    )
    winner = clone_projector(cands[winner_ci]).fit(lab)  # refit on ALL labelled cohorts for emission

    finite_cols = [i for i in range(len(cands)) if np.isfinite(perf[:, i]).all()]
    pbo = (pbo_cscv(perf[:, finite_cols], higher_is_better=True, n_splits=min(len(fold_cohorts), 8))
           if len(finite_cols) >= 2 and len(fold_cohorts) >= 4 else None)
    winner_skill = perf[:, winner_ci]
    winner_skill = winner_skill[np.isfinite(winner_skill)]
    dsr = (deflated_sharpe(winner_skill, n_trials=len(cands))
           if len(winner_skill) >= 3 and np.std(winner_skill) > 0 else None)

    # ── ORACLE-FLOOR sanity (E2.1-r): a model that SEES the target scores MAE 0; no real candidate can
    #    do better. A candidate with a NEGATIVE MAE would mean the metric is inverted.
    oracle_floor_ok = bool(np.nanmin(mean_mae) >= -1e-9)
    if not oracle_floor_ok:
        notes.append(
            f"ORACLE-FLOOR VIOLATION: a candidate scored MAE {np.nanmin(mean_mae):.4f} < 0 — the "
            f"selection metric is inverted."
        )

    return BakeoffResult(
        metric=config.metric, winner_name=names[winner_ci], winner_config=winner,
        leaderboard=leaderboard, perf_matrix=perf, fold_cohorts=fold_cohorts, pbo=pbo, dsr=dsr,
        oracle_floor_ok=oracle_floor_ok, notes=notes,
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# Emission — the per-player MLB-equivalent line (leakage-safe, expanding-window)
# ══════════════════════════════════════════════════════════════════════════════════════

# The current-prospect cohort is a synthetic "future" debut cohort so it trains on EVERY graduated
# cohort (a prospect has not debuted, so all graduated players are strictly-prior). Mirrors P1A's
# UDFA-derived-class trick.
_PROSPECT_COHORT_SENTINEL = 9999


@dataclass
class MleRun:
    metric: str
    projections: pd.DataFrame     # per (player_id, level) MLB-equivalent line + uncertainty
    bakeoff: BakeoffResult
    notes: list[str] = field(default_factory=list)


def emit_projections(pairs: pd.DataFrame, winner_factory, config: MleConfig | None = None) -> pd.DataFrame:
    """Emit a leakage-safe MLB-equivalent line for EVERY usable minor line (graduated player OR active
    prospect). For each debut cohort Y > the earliest, the winner is REFIT on labelled rows from
    STRICTLY-PRIOR cohorts, then applied to cohort Y. Active prospects (no debut) are assigned a synthetic
    future cohort so they are fit on ALL graduated players and emitted flagged `is_prospect`. The earliest
    debut cohort is a SEED (its map would need a <earliest cohort that does not exist) and is not emitted.
    """
    config = config or MleConfig()
    data = build_target(pairs, config)
    # rows we can EMIT for: a usable minor line (labelled graduate OR prospect)
    emit_pool = data[data["has_minor_line"]].copy()
    train_pool = data[data["has_target"]].copy()
    graduated_cohorts = sorted(int(y) for y in train_pool["debut_cohort"].dropna().unique())
    if not graduated_cohorts:
        return pd.DataFrame()

    # assign prospects to the synthetic future cohort
    emit_pool["emit_cohort"] = emit_pool["debut_cohort"]
    emit_pool.loc[emit_pool["is_prospect"], "emit_cohort"] = _PROSPECT_COHORT_SENTINEL
    emit_cohorts = sorted(int(y) for y in emit_pool["emit_cohort"].dropna().unique())

    m = config.metric
    out_rows: list[pd.DataFrame] = []
    for year in emit_cohorts:
        prior = [c for c in graduated_cohorts if c < year]
        if not prior:
            continue  # the seed / earliest graduated cohort — no strictly-prior map exists
        train = train_pool[train_pool["debut_cohort"].isin(prior)]
        if train.empty:
            continue
        model = winner_factory().fit(train)
        cohort_rows = emit_pool[emit_pool["emit_cohort"] == year].copy()
        mean, sd = model.predict(cohort_rows)
        lo, hi = PLAUSIBLE_RANGE[m]
        cohort_rows[f"mle_{m}"] = np.clip(mean, lo, hi)
        cohort_rows[f"mle_{m}_sd"] = sd
        cohort_rows["n_prior_cohorts"] = len(prior)
        cohort_rows["n_prior_pairs"] = int(len(train))
        out_rows.append(cohort_rows)

    if not out_rows:
        return pd.DataFrame()
    proj = pd.concat(out_rows, ignore_index=True)
    proj["sport"] = "mlb"
    proj["player_type"] = "batter"
    proj["metric"] = m
    proj["model_version"] = MODEL_VERSION
    keep = [
        "sport", "player_type", "metric", "player_id", "player_name", "level", "league",
        "debut_cohort", "is_prospect", "age", "minor_pa", f"minor_{m}", f"mlb_{m}",
        f"mle_{m}", f"mle_{m}_sd", "n_prior_cohorts", "n_prior_pairs", "model_version",
    ]
    return proj[[c for c in keep if c in proj.columns]]


def run_milb_mle(pairs: pd.DataFrame, config: MleConfig | None = None) -> MleRun:
    """End-to-end for ONE metric: bake-off → refit winner → emit per-(player, level) MLB-equivalent line."""
    config = config or MleConfig()
    bake = run_bakeoff(pairs, config)
    w = bake.winner_config
    proj = emit_projections(pairs, lambda: clone_projector(w), config)
    return MleRun(metric=config.metric, projections=proj, bakeoff=bake, notes=list(bake.notes))

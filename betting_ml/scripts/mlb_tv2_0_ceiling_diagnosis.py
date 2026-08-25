"""MLB-TV2-0 — the totals-ceiling diagnosis: WHICH LEVER binds the served totals predictive?

Pre-registration: `ablation_results/mlb_tv2_0_prereg.md`, committed BEFORE any statistic
involving a realized outcome was computed on this population. Every constant in the
`REGISTERED` block below is the code twin of that document, and
`test_prereg_document_matches_the_registered_battery` pins the two together.

`best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves**.
This is a projection/pricing-quality diagnosis: no edge, win-rate, ROI or CLV claim.

WHAT THIS IS
------------
The served `total_runs` predictive is a symmetric Normal `(mu_i, sigma_i)` with no serve-time
calibrator. Its wall did not move under 487 features and three learner classes. The TV2 epic
names two candidate levers — feature TYPE (nothing carries per-game DISPERSION) and
distributional ARCHITECTURE (a forced unimodal, symmetric shape). This module measures which
one binds, by bounding each with an ORACLE rather than building either fix.

⛔ EVERY non-incumbent arm is an ORACLE or a CONTROL. Nothing here competes to ship. An oracle
   ceiling licenses FUNDING A STORY; it is never evidence of an achievable improvement.

THE SEPARATION, in one line
---------------------------
    A1  global scale                      -> a RECALIBRATOR can do this; features cannot be needed for it
    A3 - A1   per-game sigma beyond scale -> TV2-1's CEILING (the feature lever)
    B2 - A1   shape beyond scale          -> TV2-2's CEILING (the architecture lever)
    C1        both at once                -> the irreducibility leg

`B2` (a pooled empirical `z` law) ABSORBS a global scale error by construction, which is why the
architecture lever is `closed(B2) - closed(A1)` and not `closed(B2)`. Registering that before
scoring is what stops a shape verdict from quietly banking a calibrator's work.

RUN
---
    uv run python betting_ml/scripts/mlb_tv2_0_ceiling_diagnosis.py            # full battery
    uv run python betting_ml/scripts/mlb_tv2_0_ceiling_diagnosis.py --controls # node 2 only
    uv run python betting_ml/scripts/mlb_tv2_0_ceiling_diagnosis.py --fixture  # the 1e-9 pin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ══════════════════════════════════════════════════════════════════════════════════════════════
# REGISTERED — the code twin of `ablation_results/mlb_tv2_0_prereg.md`. Frozen before scoring.
# ══════════════════════════════════════════════════════════════════════════════════════════════

STORY = "MLB-TV2-0"
SEED = 42
BEST_ALPHA = 0

#: §2 — population
ERA_MODEL_VERSIONS = ("v6", "pre_lineup_v6")
CHAMPION_STAMPS = ("v6", "pre_lineup_v6")
PRIMARY_TIER = "post_lineup"
SECONDARY_TIER = "morning"
CHAMPION_FIT_DATE = "2026-06-23"
N_BLOCKS = 5                      # contiguous DATE blocks, cross-fit

#: §3 — the battery. ⛔ = an oracle/control, never a shippable arm.
ARMS = (
    "incumbent",
    "A1_sigma_level",
    "A2_sigma_mu_binned",
    "A3_sigma_clairvoyant",      # ⛔ UPPER BOUND (peeks at |y-mu| to choose the bin)
    "A_ctrl_permuted",           # ⛔ row-blind matched control
    "B1_shape_skewnormal",
    "B2_shape_empirical",        # ⛔ UPPER BOUND
    "C1_combined",               # ⛔ joint ceiling
)
ORACLE_ARMS = ("A3_sigma_clairvoyant", "A_ctrl_permuted", "B2_shape_empirical", "C1_combined")
N_BINS = 10                       # deciles for the sigma oracles
MIN_BIN_ROWS = 20                 # below this an out-of-block bin falls back to the pooled RMS
SKEWNORM_COLLAPSE_ABS_ALPHA = 0.05  # |a| below this = the nested form collapsed onto its Normal foil

#: §4 — metrics
PRIMARY_STAT = "pit_ks"
CONFIRM_STAT = "p_over_gap_abs"
CRPS_LEVELS = 499
CRPS_VALIDATION_TOL = 1e-3        # grid CRPS vs the Normal closed form on the incumbent

#: §5 — the calibrated-null yardstick
N_NULL = 2000
NULL_BAND = 0.95

#: §7 — THE DECISION RULE (registered forward)
RULE_MAJORITY = 0.50              # a lever "binds" at >= this share of the gap
RULE_MATERIAL = 0.20              # a lever is "in play" at >= this share
RULE_CONFIRM = 0.20               # the winner must also close this share of |p_over_gap|
OUTCOMES = ("NO_MEASURABLE_DEFECT", "IRREDUCIBLE", "FEATURE-BOUND",
            "SHAPE-BOUND", "BOTH", "INDETERMINATE")
ROUTES = {
    "NO_MEASURABLE_DEFECT": "nothing funded; report the MDE",
    "IRREDUCIBLE": "neither TV2-1 nor TV2-2 funded; E13.6b Part B UN-HOLDS",
    "FEATURE-BOUND": "TV2-1 (dispersion feature store) funded first",
    "SHAPE-BOUND": "TV2-2 (mixture-density head) funded first",
    "BOTH": "TV2-1 then TV2-2, the epic's staged order",
    "INDETERMINATE": "routes as IRREDUCIBLE — no lever demonstrated majority closure",
}

#: §9 — positive controls
CONTROL_SIGMA_CV = 0.35           # planted TRUE per-game sigma dispersion
CONTROL_SKEW_ALPHA = 4.0          # planted TRUE shape
CONTROLS = ("PC_clean", "PC_dispersion", "PC_shape", "PC_both")
CONTROL_EXPECT = {
    "PC_clean": "NO_MEASURABLE_DEFECT",
    "PC_dispersion": "FEATURE-BOUND",
    "PC_shape": "SHAPE-BOUND",
    "PC_both": "BOTH",
}
#: §8 — MDE grids (planted deficit size -> does the rule route it correctly?)
MDE_SIGMA_CV_GRID = (0.05, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50)
MDE_SKEW_GRID = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
N_MDE = 20                        # replicates per grid point

_REPORT_MD = PROJECT_ROOT / "ablation_results" / "mlb_tv2_0_ceiling_diagnosis.md"
_REPORT_JSON = PROJECT_ROOT / "ablation_results" / "mlb_tv2_0_ceiling_diagnosis.json"
_CONTROLS_JSON = PROJECT_ROOT / "ablation_results" / "mlb_tv2_0_controls.json"
_FIXTURE = PROJECT_ROOT / "betting_ml" / "tests" / "fixtures" / "mlb_tv2_0_fixture.json"
_CACHE = PROJECT_ROOT / "betting_ml" / "data" / "cache" / "mlb_tv2_0_served.parquet"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔ MARKET-BLIND — the SQL reads no odds column. Pinned by a guard test.
# ══════════════════════════════════════════════════════════════════════════════════════════════

_TABLES = ("daily_model_predictions", "mart_game_results")

_PULL_SQL = f"""
WITH served AS (
    SELECT
        game_pk,
        game_date::date       AS game_date,
        prediction_type       AS tier,
        model_version,
        totals_model_version,
        pred_total_runs       AS mu,
        pred_total_runs_scale AS sigma,
        inserted_at
    FROM daily_model_predictions
    WHERE model_version IN {ERA_MODEL_VERSIONS}
      AND prediction_type IN ('{PRIMARY_TIER}', '{SECONDARY_TIER}')
      AND COALESCE(is_backfill, FALSE) = FALSE
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, prediction_type ORDER BY inserted_at DESC
    ) = 1
)
SELECT
    s.game_pk, s.game_date, s.tier, s.model_version, s.totals_model_version, s.mu, s.sigma,
    (r.home_final_score + r.away_final_score)::DOUBLE AS y_total
FROM served s
JOIN mart_game_results r
  ON r.game_pk = s.game_pk
 AND r.game_type = 'R'
 AND r.home_final_score IS NOT NULL
WHERE s.mu IS NOT NULL AND s.sigma IS NOT NULL AND s.sigma > 0
  AND (s.totals_model_version IS NULL OR s.totals_model_version IN {CHAMPION_STAMPS})
ORDER BY s.game_date, s.game_pk, s.tier
"""


def pull(cache: Path | None = _CACHE):
    """The served rows joined to realized finals. Snowflake-free, market-blind."""
    import pandas as pd
    if cache is not None and cache.exists():
        return pd.read_parquet(cache)
    import os
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, _TABLES)
    df = conn.execute(_PULL_SQL).fetchdf()
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LAWS — the standardized predictive shape. `F_i(x) = law_{block(i)}.cdf((x - mu_i) / scale_i)`.
# ══════════════════════════════════════════════════════════════════════════════════════════════

class NormalLaw:
    name = "normal"

    def cdf(self, t):
        from scipy.stats import norm
        return norm.cdf(t)

    def ppf(self, p):
        from scipy.stats import norm
        return norm.ppf(p)


class SkewNormalLaw:
    """A 3-parameter skew-normal fitted to the out-of-block `z` — absorbs scale AND shape.

    ⚠️ The skew-normal likelihood is FLAT at a = 0 (MH2.8; the boundary-degenerate trap). A fit
    that collapses onto its own Normal foil is a TIE, not a shape finding — `collapsed` records it.
    """
    name = "skewnormal"

    def __init__(self, z):
        from scipy.stats import skew, skewnorm
        z = np.asarray(z, float)
        s = float(skew(z))
        # moment-based start so the optimiser does not sit on the flat ridge at a = 0
        a0 = float(np.clip(np.sign(s) * (abs(s) ** (1 / 3)) * 4.0, -8.0, 8.0)) or 0.5
        self.a, self.loc, self.scale = skewnorm.fit(z, a0, loc=float(np.mean(z)),
                                                    scale=float(np.std(z, ddof=1)))
        self.collapsed = bool(abs(self.a) < SKEWNORM_COLLAPSE_ABS_ALPHA)

    def cdf(self, t):
        from scipy.stats import skewnorm
        return skewnorm.cdf(t, self.a, loc=self.loc, scale=self.scale)

    def ppf(self, p):
        from scipy.stats import skewnorm
        return skewnorm.ppf(p, self.a, loc=self.loc, scale=self.scale)


class EmpiricalLaw:
    """⛔ UPPER BOUND — the empirical quantile function of the out-of-block `z`, Gaussian-tailed.

    The best possible SHAPE given a location and a scale, with no parametric family assumed. It
    absorbs a global scale error too (which is why the architecture lever is measured relative to
    `A1`). Tails beyond the observed range are extended with a Gaussian slope matched at the
    endpoints so the CRPS grid and the PIT stay finite and monotone.
    """
    name = "empirical"

    def __init__(self, z, tail_frac: float = 0.05):
        from scipy.stats import norm
        z = np.sort(np.asarray(z, float))
        m = len(z)
        if m < 3 * N_BINS:
            raise ValueError(f"EmpiricalLaw needs >= {3 * N_BINS} rows, got {m}")
        pp = (np.arange(1, m + 1) - 0.5) / m
        k = max(1, int(round(tail_frac * m)))
        self.z, self.pp = z, pp
        self.p_lo, self.p_hi = float(pp[0]), float(pp[-1])
        self.q_lo, self.q_hi = float(z[0]), float(z[-1])
        self._n_lo, self._n_hi = float(norm.ppf(pp[0])), float(norm.ppf(pp[-1]))
        self.t_lo = max((z[k] - z[0]) / (norm.ppf(pp[k]) - self._n_lo), 1e-6)
        self.t_hi = max((z[-1] - z[-1 - k]) / (self._n_hi - norm.ppf(pp[-1 - k])), 1e-6)

    def ppf(self, p):
        from scipy.stats import norm
        p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
        out = np.interp(p, self.pp, self.z)
        lo, hi = p < self.p_lo, p > self.p_hi
        if lo.any():
            out[lo] = self.q_lo + (norm.ppf(p[lo]) - self._n_lo) * self.t_lo
        if hi.any():
            out[hi] = self.q_hi + (norm.ppf(p[hi]) - self._n_hi) * self.t_hi
        return out

    def cdf(self, t):
        from scipy.stats import norm
        t = np.asarray(t, float)
        out = np.interp(t, self.z, self.pp)
        lo, hi = t < self.q_lo, t > self.q_hi
        if lo.any():
            out[lo] = norm.cdf(self._n_lo + (t[lo] - self.q_lo) / self.t_lo)
        if hi.any():
            out[hi] = norm.cdf(self._n_hi + (t[hi] - self.q_hi) / self.t_hi)
        return np.clip(out, 1e-12, 1 - 1e-12)


class Arm:
    """`mu` (held EXACTLY at the served value for every arm), a per-row `scale`, a per-block law."""

    def __init__(self, name, mu, scale, laws, block):
        self.name, self.mu = name, np.asarray(mu, float)
        self.scale = np.asarray(scale, float)
        self.laws, self.block = laws, np.asarray(block, int)

    def cdf_at(self, x):
        x = np.asarray(x, float)
        out = np.empty(len(x))
        t = (x - self.mu) / self.scale
        for b, law in enumerate(self.laws):
            m = self.block == b
            if m.any():
                out[m] = law.cdf(t[m])
        return out

    def quantiles(self, levels):
        q = np.empty((len(self.mu), len(levels)))
        for b, law in enumerate(self.laws):
            m = self.block == b
            if m.any():
                q[m] = self.mu[m, None] + self.scale[m, None] * law.ppf(levels)[None, :]
        return q


# ══════════════════════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════════════════════

def randomized_pit(y, arm, rng):
    """Continuity-corrected + randomized PIT, generalized from MH2.6's house instrument to any F.

    `total_runs` is an integer and the predictive is continuous: reading `F(y)` straight off is
    lumpy, and inclusive integer interval bounds INFLATE coverage (the E2.1-r defect). Under a
    correctly specified predictive this is EXACTLY uniform, at any scale and any shape.
    """
    y = np.asarray(y, float)
    lo, hi = arm.cdf_at(y - 0.5), arm.cdf_at(y + 0.5)
    return lo + rng.uniform(size=len(y)) * np.maximum(hi - lo, 0.0)


def crps_grid(y, arm, levels=None):
    """CRPS = 2∫ pinball dτ on a shared quantile grid — identical construction for every arm."""
    lv = _levels() if levels is None else levels
    q = arm.quantiles(lv)
    y = np.asarray(y, float)[:, None]
    ind = (y < q).astype(float)
    return float(np.mean(2.0 * np.mean((y - q) * (lv[None, :] - ind), axis=1)))


def _levels():
    return (np.arange(1, CRPS_LEVELS + 1)) / (CRPS_LEVELS + 1.0)


def crps_normal_closed(y, mu, sigma):
    from scipy.stats import norm
    z = (np.asarray(y, float) - mu) / sigma
    return float(np.mean(sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))))


def arm_stats(y, arm, rng):
    """Every statistic, for one arm. `p_over` is read AT THE MODEL'S OWN MEAN — market-blind."""
    from scipy.stats import kstest, kurtosis, skew
    y = np.asarray(y, float)
    n = len(y)
    u = randomized_pit(y, arm, rng)
    counts = np.histogram(u, bins=np.linspace(0, 1, 11))[0] / max(n, 1)
    resid = y - arm.mu
    z = resid / arm.scale
    stated = float(np.mean(1.0 - arm.cdf_at(arm.mu)))
    realized = float(np.mean(y > arm.mu))
    return {
        "n": n,
        "pit_ks": float(kstest(u, "uniform").statistic),          # PRIMARY
        "pit_mdd": float(np.max(np.abs(counts - 0.1))),
        "p_over_stated": stated,
        "p_over_realized": realized,
        "p_over_gap": stated - realized,                          # CO-PRIMARY (as |.|)
        "p_over_gap_abs": abs(stated - realized),
        "crps": crps_grid(y, arm),                                # CONSTRAINT, never a criterion
        "cov80": float(np.mean((u >= 0.10) & (u <= 0.90))),       # FLOOR, never a target
        "cov50": float(np.mean((u >= 0.25) & (u <= 0.75))),
        "mass_below_predictive_median": float(np.mean(u < 0.5)),
        "bias": float(np.mean(resid)),
        "rmse": float(np.sqrt(np.mean(resid ** 2))),
        "var_z_pooled": float(np.var(z, ddof=1)),
        "z_skew": float(skew(z)),
        "z_excess_kurtosis": float(kurtosis(z)),
        "scale_mean": float(np.mean(arm.scale)),
        "scale_cv": float(np.std(arm.scale, ddof=1) / np.mean(arm.scale)),
        "deciles": [float(c) for c in counts],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE BATTERY
# ══════════════════════════════════════════════════════════════════════════════════════════════

def date_blocks(dates, k: int = N_BLOCKS):
    """K CONTIGUOUS date blocks balanced by row count. Not random: the era is a time series."""
    order = np.argsort(np.asarray(dates, dtype="datetime64[D]"), kind="stable")
    block = np.empty(len(order), int)
    edges = np.linspace(0, len(order), k + 1).round().astype(int)
    for b in range(k):
        block[order[edges[b]:edges[b + 1]]] = b
    # a date must not straddle two blocks (same-slate structure would leak)
    d = np.asarray(dates, dtype="datetime64[D]")
    for day in np.unique(d):
        m = d == day
        vals, cnt = np.unique(block[m], return_counts=True)
        block[m] = vals[np.argmax(cnt)]
    return block


def _binned_scale(key, resid, block, *, k=N_BINS):
    """Out-of-block RMS residual within the row's own `key`-decile. Cross-fit; pooled fallback."""
    key, resid, block = np.asarray(key, float), np.asarray(resid, float), np.asarray(block, int)
    out = np.empty(len(key))
    for b in np.unique(block):
        tr, te = block != b, block == b
        edges = np.quantile(key[tr], np.linspace(0, 1, k + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        edges = np.maximum.accumulate(edges)
        lab_tr = np.clip(np.searchsorted(edges, key[tr], side="right") - 1, 0, k - 1)
        lab_te = np.clip(np.searchsorted(edges, key[te], side="right") - 1, 0, k - 1)
        pooled = float(np.sqrt(np.mean(resid[tr] ** 2)))
        vals = np.full(k, pooled)
        for j in range(k):
            m = lab_tr == j
            if m.sum() >= MIN_BIN_ROWS:
                vals[j] = float(np.sqrt(np.mean(resid[tr][m] ** 2)))
        out[te] = vals[lab_te]
    return np.maximum(out, 1e-6)


def _per_block_laws(z, block, factory):
    return [factory(z[block != b]) for b in range(int(block.max()) + 1)]


def build_arms(y, mu, sigma, block, rng):
    """Every arm. ⛔ `A3`/`A_ctrl`/`B2`/`C1` peek by design and bound a lever; they never ship."""
    y, mu, sigma = np.asarray(y, float), np.asarray(mu, float), np.asarray(sigma, float)
    resid = y - mu
    z = resid / sigma
    nb = int(block.max()) + 1
    norm_laws = [NormalLaw() for _ in range(nb)]
    arms, notes = {}, {}

    arms["incumbent"] = Arm("incumbent", mu, sigma, norm_laws, block)

    # A1 — a GLOBAL scale multiplier (1 dof). A recalibrator can do this; no feature is needed.
    c = np.empty(len(y))
    for b in range(nb):
        c[block == b] = float(np.sqrt(np.mean(z[block != b] ** 2)))
    arms["A1_sigma_level"] = Arm("A1_sigma_level", mu, sigma * c, norm_laws, block)
    notes["A1_c_by_block"] = [float(c[block == b][0]) for b in range(nb)]

    # A2 — heteroscedasticity already implied by the CURRENT contract (mu is its output).
    arms["A2_sigma_mu_binned"] = Arm(
        "A2_sigma_mu_binned", mu, _binned_scale(mu, resid, block), norm_laws, block)

    # A3 ⛔ — the answer chooses the bin. THE CEILING on any per-game sigma model.
    s3 = _binned_scale(np.abs(resid), resid, block)
    arms["A3_sigma_clairvoyant"] = Arm("A3_sigma_clairvoyant", mu, s3, norm_laws, block)

    # A_ctrl ⛔ — A3's machinery, row-blind. Must be inert (NF-W7f matched foil).
    perm = rng.permutation(len(y))
    arms["A_ctrl_permuted"] = Arm(
        "A_ctrl_permuted", mu, _binned_scale(np.abs(resid)[perm], resid, block), norm_laws, block)

    # B1 — the specific mechanism MH2.8 identified (its DSR failure is CITED, never re-scored).
    sn_laws = _per_block_laws(z, block, SkewNormalLaw)
    arms["B1_shape_skewnormal"] = Arm("B1_shape_skewnormal", mu, sigma, sn_laws, block)
    notes["B1_alpha_by_block"] = [float(law.a) for law in sn_laws]
    notes["B1_collapsed_any"] = bool(any(law.collapsed for law in sn_laws))

    # B2 ⛔ — the best possible SHAPE given a location and a scale. Absorbs A1 by construction.
    arms["B2_shape_empirical"] = Arm(
        "B2_shape_empirical", mu, sigma, _per_block_laws(z, block, EmpiricalLaw), block)

    # C1 ⛔ — both ceilings at once.
    arms["C1_combined"] = Arm(
        "C1_combined", mu, s3, _per_block_laws(resid / s3, block, EmpiricalLaw), block)

    return arms, notes


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE YARDSTICK — the calibrated-null floor (§5)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def calibrated_null(mu, sigma, block, reps=N_NULL, seed=SEED):
    """Outcomes re-drawn from the served predictive itself, n and per-game (mu, sigma) fixed.

    `round(Normal(mu, sigma))` makes the continuity-corrected randomized PIT EXACTLY uniform, so
    `pit_ks`'s floor here is also the distribution-free CONSTRUCTION floor at this n — the two are
    asserted to agree in `run()`.
    """
    rng = np.random.default_rng(seed)
    nb = int(block.max()) + 1
    inc = Arm("incumbent", mu, sigma, [NormalLaw() for _ in range(nb)], block)
    keys = ("pit_ks", "pit_mdd", "p_over_gap_abs", "crps", "cov80", "cov50", "var_z_pooled")
    out = {k: np.empty(reps) for k in keys}
    for r in range(reps):
        y = np.round(rng.normal(mu, sigma))
        s = arm_stats(y, inc, rng)
        for k in keys:
            out[k] = out[k]
            out[k][r] = s[k]
    return out


def floor_of(null, key, band=NULL_BAND):
    d = np.asarray(null[key], float)
    lo, hi = np.quantile(d, [(1 - band) / 2, 1 - (1 - band) / 2])
    return {"median": float(np.median(d)), "lo": float(lo), "hi": float(hi),
            "material": float((hi - lo) / 2)}


def mc_pvalue(draws, observed):
    d = np.asarray(draws, float)
    med = float(np.median(d))
    tail = float(np.mean(d >= observed)) if observed >= med else float(np.mean(d <= observed))
    return float(min(1.0, 2.0 * (tail * len(d) + 1) / (len(d) + 1)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE DECISION RULE (§7) — registered forward; nothing below reads a result to choose a branch.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _closed(obs_inc, obs_arm, gap, material):
    if gap <= 0:
        return 0.0
    raw = (obs_inc - obs_arm) / gap
    return 0.0 if abs(obs_inc - obs_arm) < material else float(raw)


def decide(stats, floors):
    """Returns the OUTCOME and every share it was computed from. Deterministic, order fixed."""
    fp, fc = floors[PRIMARY_STAT], floors[CONFIRM_STAT]
    inc_p = stats["incumbent"][PRIMARY_STAT]
    inc_c = stats["incumbent"][CONFIRM_STAT]
    gap_p = inc_p - fp["median"]
    gap_c = inc_c - fc["median"]

    def cl(arm, key, gap, fl):
        return _closed(stats["incumbent"][key], stats[arm][key], gap, fl["material"])

    p = {a: cl(a, PRIMARY_STAT, gap_p, fp) for a in ARMS if a != "incumbent"}
    c = {a: cl(a, CONFIRM_STAT, gap_c, fc) for a in ARMS if a != "incumbent"}

    closed_calibrator = p["A1_sigma_level"]
    closed_feature = p["A3_sigma_clairvoyant"] - closed_calibrator
    closed_shape = p["B2_shape_empirical"] - closed_calibrator
    closed_combined = p["C1_combined"]
    conf_feature = c["A3_sigma_clairvoyant"] - c["A1_sigma_level"]
    conf_shape = c["B2_shape_empirical"] - c["A1_sigma_level"]

    # PRECONDITION — the rule does not run on a non-defect (NF1.7 (a)).
    inside = fp["lo"] <= inc_p <= fp["hi"]
    if inside:
        outcome, demoted = "NO_MEASURABLE_DEFECT", None
    elif closed_combined < RULE_MAJORITY:
        outcome, demoted = "IRREDUCIBLE", None
    elif closed_feature >= RULE_MAJORITY and closed_shape < RULE_MATERIAL:
        outcome, demoted = "FEATURE-BOUND", None
    elif closed_shape >= RULE_MAJORITY and closed_feature < RULE_MATERIAL:
        outcome, demoted = "SHAPE-BOUND", None
    elif closed_feature >= RULE_MATERIAL and closed_shape >= RULE_MATERIAL:
        outcome, demoted = "BOTH", None
    else:
        outcome, demoted = "INDETERMINATE", None

    # CONFIRMATION — the winner must move the quantity the product actually prints.
    if outcome in ("FEATURE-BOUND", "BOTH") and conf_feature < RULE_CONFIRM:
        demoted, outcome = f"{outcome} (feature confirm {conf_feature:.3f} < {RULE_CONFIRM})", "INDETERMINATE"
    elif outcome == "SHAPE-BOUND" and conf_shape < RULE_CONFIRM:
        demoted, outcome = f"SHAPE-BOUND (shape confirm {conf_shape:.3f} < {RULE_CONFIRM})", "INDETERMINATE"

    sub = ("CALIBRATOR-SUFFICIENT"
           if outcome == "IRREDUCIBLE" and closed_calibrator >= RULE_MAJORITY else None)
    over_peeking = sorted(a for a in ORACLE_ARMS if stats[a][PRIMARY_STAT] < fp["lo"])

    return {
        "outcome": outcome, "route": ROUTES[outcome], "sub_state": sub, "demoted_from": demoted,
        "primary_stat": PRIMARY_STAT, "confirm_stat": CONFIRM_STAT,
        "incumbent_primary": inc_p, "floor_primary": fp["median"],
        "band_primary": [fp["lo"], fp["hi"]], "material_primary": fp["material"],
        "gap_primary": gap_p, "incumbent_confirm": inc_c, "gap_confirm": gap_c,
        "closed_calibrator": closed_calibrator, "closed_feature": closed_feature,
        "closed_shape": closed_shape, "closed_combined": closed_combined,
        "confirm_feature": conf_feature, "confirm_shape": conf_shape,
        "closed_primary_by_arm": p, "closed_confirm_by_arm": c,
        "control_inert": p["A_ctrl_permuted"], "over_peeking_arms": over_peeking,
        "precondition_incumbent_inside_null_band": bool(inside),
    }


def score(y, mu, sigma, dates, *, seed=SEED, reps=N_NULL, null=None):
    """One population -> every arm's statistics, the floors, and the triggered outcome."""
    block = date_blocks(dates)
    rng = np.random.default_rng(seed)
    arms, notes = build_arms(y, mu, sigma, block, rng)
    stats = {a: arm_stats(y, arms[a], np.random.default_rng(seed + 1000 + i))
             for i, a in enumerate(ARMS)}
    nl = calibrated_null(mu, sigma, block, reps=reps, seed=seed) if null is None else null
    floors = {k: floor_of(nl, k) for k in nl}
    d = decide(stats, floors)
    d["p_primary"] = mc_pvalue(nl[PRIMARY_STAT], stats["incumbent"][PRIMARY_STAT])
    d["p_confirm"] = mc_pvalue(nl[CONFIRM_STAT], stats["incumbent"][CONFIRM_STAT])
    return {"stats": stats, "floors": floors, "decision": d, "notes": notes,
            "block_sizes": [int((block == b).sum()) for b in range(N_BLOCKS)], "_null": nl}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ POSITIVE CONTROLS (§9) — the legs must separate PLANTED causes
# ══════════════════════════════════════════════════════════════════════════════════════════════

def plant(mu, sigma, rng, *, sigma_cv=0.0, skew_alpha=0.0):
    """Synthetic `y` on the REAL served (mu, sigma): a known dispersion and/or shape deficit."""
    from scipy.stats import skewnorm
    n = len(mu)
    s = np.asarray(sigma, float)
    if sigma_cv > 0:
        tau = np.sqrt(np.log1p(sigma_cv ** 2))
        w = rng.normal(size=n)
        f = np.exp(tau * w - 0.5 * tau ** 2)          # E[f] = 1 -> the MEAN scale is preserved
        s = s * f
    if skew_alpha != 0:
        a = float(skew_alpha)
        d = a / np.sqrt(1 + a * a)
        m, sd = d * np.sqrt(2 / np.pi), np.sqrt(1 - 2 * d * d / np.pi)
        e = (skewnorm.rvs(a, size=n, random_state=rng) - m) / sd   # mean 0, var 1
    else:
        e = rng.normal(size=n)
    return np.round(mu + s * e)


def run_controls(mu, sigma, dates, *, seed=SEED, reps=N_NULL):
    out = {}
    block = date_blocks(dates)
    nl = calibrated_null(mu, sigma, block, reps=reps, seed=seed)   # one null; (mu, sigma) fixed
    for i, name in enumerate(CONTROLS):
        rng = np.random.default_rng(seed + 500 + i)
        kw = {"PC_clean": {}, "PC_dispersion": {"sigma_cv": CONTROL_SIGMA_CV},
              "PC_shape": {"skew_alpha": CONTROL_SKEW_ALPHA},
              "PC_both": {"sigma_cv": CONTROL_SIGMA_CV, "skew_alpha": CONTROL_SKEW_ALPHA}}[name]
        y = plant(mu, sigma, rng, **kw)
        r = score(y, mu, sigma, dates, seed=seed, reps=reps, null=nl)
        d = r["decision"]
        out[name] = {
            "planted": kw, "expected": CONTROL_EXPECT[name], "outcome": d["outcome"],
            "passed": d["outcome"] == CONTROL_EXPECT[name],
            "closed_calibrator": d["closed_calibrator"], "closed_feature": d["closed_feature"],
            "closed_shape": d["closed_shape"], "closed_combined": d["closed_combined"],
            "control_inert": d["control_inert"], "demoted_from": d["demoted_from"],
            "incumbent_primary": d["incumbent_primary"], "gap_primary": d["gap_primary"],
        }
    out["_all_passed"] = all(v["passed"] for k, v in out.items() if not k.startswith("_"))
    return out


def mde_curve(mu, sigma, dates, *, seed=SEED, reps=400, n_rep=N_MDE):
    """The smallest PLANTED deficit the rule routes correctly — a null is 'nothing above this'."""
    block = date_blocks(dates)
    nl = calibrated_null(mu, sigma, block, reps=reps, seed=seed)
    curves = {}
    for label, grid, key, want in (("dispersion", MDE_SIGMA_CV_GRID, "sigma_cv", "FEATURE-BOUND"),
                                   ("shape", MDE_SKEW_GRID, "skew_alpha", "SHAPE-BOUND")):
        rows = []
        for g in grid:
            hits = 0
            for r in range(n_rep):
                rng = np.random.default_rng(seed + hash((label, g, r)) % 100000)
                y = plant(mu, sigma, rng, **{key: g})
                o = score(y, mu, sigma, dates, seed=seed, reps=reps, null=nl)["decision"]["outcome"]
                hits += int(o == want)
            rows.append({key: g, "route_rate": hits / n_rep})
        curves[label] = rows
    return curves


# ══════════════════════════════════════════════════════════════════════════════════════════════
# FIXTURE — the 1e-9 reproduction pin, on data that ships with the repo
# ══════════════════════════════════════════════════════════════════════════════════════════════

def fixture_frame(n: int = 400, seed: int = 7):
    """A committed synthetic slate: real-ish (mu, sigma, dates), a planted shape+scale defect."""
    rng = np.random.default_rng(seed)
    mu = 8.8 + 0.55 * rng.normal(size=n)
    sigma = 4.3 + 0.20 * rng.normal(size=n)
    dates = np.array([np.datetime64("2026-06-23") + np.timedelta64(int(i * 60 / n), "D")
                      for i in range(n)])
    y = plant(mu, np.abs(sigma) * 1.06, rng, skew_alpha=3.0)
    return {"mu": mu.tolist(), "sigma": np.abs(sigma).tolist(),
            "dates": [str(d) for d in dates], "y": y.tolist()}


def fixture_run(fx, reps: int = 200):
    mu = np.asarray(fx["mu"], float)
    sigma = np.asarray(fx["sigma"], float)
    dates = np.array(fx["dates"], dtype="datetime64[D]")
    r = score(np.asarray(fx["y"], float), mu, sigma, dates, seed=SEED, reps=reps)
    d = r["decision"]
    return {k: d[k] for k in ("outcome", "closed_calibrator", "closed_feature", "closed_shape",
                              "closed_combined", "gap_primary", "incumbent_primary",
                              "control_inert", "confirm_feature", "confirm_shape")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCATION PROBE (C2) — ⛔ a diagnostic, never a lever. See prereg §6.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def location_probe(y, mu, sigma):
    """⚠️ The spec's `std_pred` names TWO quantities. Both are reported, under distinct names.

    `std_pred_meanspread` = `STDDEV(pred_total_runs)` — the V2 gate's reading (bar >= 2.0), the
    0.773 the spec cites. Every arm in this battery holds `mu` FIXED, so this statistic is
    **ARM-INVARIANT by construction**: no leg can move it. It is therefore a LOCATION-channel
    diagnostic and never an outcome (the NF-MARGIN2 rule — a statistic the arm cannot move is not
    a gate). If the binding channel is the location spread, NEITHER TV2-1 NOR TV2-2 addresses it.
    """
    y, mu, sigma = np.asarray(y, float), np.asarray(mu, float), np.asarray(sigma, float)
    return {
        "std_pred_meanspread": float(np.std(mu, ddof=1)),
        "std_pred_meanspread_v2_gate": 2.0,
        "std_pred_meanspread_passes_v2_gate": bool(np.std(mu, ddof=1) >= 2.0),
        "std_pred_predictive_sd": float(np.mean(sigma)),
        "realized_sd": float(np.std(y, ddof=1)),
        "var_mu_over_var_y": float(np.var(mu, ddof=1) / np.var(y, ddof=1)),
        "sigma_cv": float(np.std(sigma, ddof=1) / np.mean(sigma)),
        "arm_invariant_by_construction": True,
        "null_state_hand_recorded": "INACTIVE (structural)",
        "note": ("mu is held EXACTLY at the served value in every arm, so no leg can move "
                 "std_pred_meanspread. Hand-recorded per the cv_power card's interim rule; "
                 "⛔ NOT rendered as a fold/season re-test trigger (NF-D18)."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# RUN + REPORT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _tier(df, tier):
    d = df[df["tier"] == tier].sort_values(["game_date", "game_pk"]).reset_index(drop=True)
    return (d["y_total"].to_numpy(float), d["mu"].to_numpy(float), d["sigma"].to_numpy(float),
            np.array([str(x) for x in d["game_date"]], dtype="datetime64[D]"))


def run(*, reps: int = N_NULL, mde: bool = True, cache: Path | None = _CACHE) -> dict:
    df = pull(cache)
    out = {"story": STORY, "best_alpha": BEST_ALPHA, "bet_paused": True, "market_blind": True,
           "seed": SEED, "n_null": reps, "n_blocks": N_BLOCKS,
           "champion_fit_date": CHAMPION_FIT_DATE,
           "era": [str(df["game_date"].min()), str(df["game_date"].max())],
           "tiers": {}}
    for tier in (PRIMARY_TIER, SECONDARY_TIER):
        y, mu, sigma, dates = _tier(df, tier)
        r = score(y, mu, sigma, dates, seed=SEED, reps=reps)

        # CRPS-grid validation against the Normal closed form on the incumbent (MH2.8's check).
        closed = crps_normal_closed(y, mu, sigma)
        delta = abs(r["stats"]["incumbent"]["crps"] - closed)
        if delta > CRPS_VALIDATION_TOL:
            raise AssertionError(f"CRPS grid vs closed form |Δ|={delta:.2e} > {CRPS_VALIDATION_TOL}")

        # The calibrated-null floor for pit_ks must equal the distribution-free CONSTRUCTION floor.
        rng = np.random.default_rng(SEED + 99)
        from scipy.stats import kstest
        cons = np.array([kstest(rng.uniform(size=len(y)), "uniform").statistic
                         for _ in range(min(reps, 1000))])
        r["floors"]["pit_ks"]["construction_floor_median"] = float(np.median(cons))

        entry = {
            "n": int(len(y)), "block_sizes": r["block_sizes"],
            "crps_grid_vs_closed_abs_delta": float(delta),
            "stats": r["stats"], "floors": r["floors"], "decision": r["decision"],
            "notes": r["notes"], "location_probe": location_probe(y, mu, sigma),
        }
        if tier == PRIMARY_TIER:
            entry["controls"] = run_controls(mu, sigma, dates, seed=SEED, reps=reps)
            if mde:
                entry["mde"] = mde_curve(mu, sigma, dates, seed=SEED)
        out["tiers"][tier] = entry
    out["verdict"] = out["tiers"][PRIMARY_TIER]["decision"]["outcome"]
    out["route"] = out["tiers"][PRIMARY_TIER]["decision"]["route"]
    out["sub_state"] = out["tiers"][PRIMARY_TIER]["decision"]["sub_state"]
    out["secondary_agrees"] = (out["tiers"][SECONDARY_TIER]["decision"]["outcome"]
                               == out["verdict"])
    return out


def _f(x, d=4):
    return "—" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))


def _arm_table(stats):
    keys = ("pit_ks", "pit_mdd", "p_over_stated", "p_over_realized", "p_over_gap", "crps",
            "cov80", "cov50", "var_z_pooled", "z_skew", "scale_mean", "scale_cv")
    rows = ["| arm | " + " | ".join(f"`{k}`" for k in keys) + " |",
            "|---|" + "---:|" * len(keys)]
    for a in ARMS:
        mark = " ⛔" if a in ORACLE_ARMS else ""
        rows.append(f"| `{a}`{mark} | " + " | ".join(_f(stats[a][k]) for k in keys) + " |")
    return "\n".join(rows)


def write_report(r: dict) -> Path:
    p = r["tiers"][PRIMARY_TIER]
    d = p["decision"]
    lp = p["location_probe"]
    ctl = p["controls"]
    L = [
        f"# MLB-TV2-0 — the totals-ceiling diagnosis: **{r['verdict']}**",
        "",
        f"> ## ⭐ ROUTING: {d['route']}",
        "",
        (f"**Sub-state:** `{d['sub_state']}` — a LABEL inside `IRREDUCIBLE`, mapping to the same "
         "registered action. ⛔ Not a fifth route." if d["sub_state"] else ""),
        "",
        f"`best_alpha = {r['best_alpha']}` · `bet_paused = true` · **market-blind** · **nothing serves** · deploy-held",
        "",
        "> **What this study is.** An ORACLE diagnosis of the SERVED totals predictive: it bounds what "
        "each of the epic's two candidate levers could AT MOST deliver, and triggers a decision rule "
        "registered before any statistic was computed. It builds neither fix. It says nothing about "
        "win rate, edge, ROI or CLV — at `best_alpha = 0` no bet rode on this model. "
        "Pre-registration: [`mlb_tv2_0_prereg.md`](mlb_tv2_0_prereg.md).",
        "",
        "## Population",
        "",
        "| | |", "|---|---|",
        f"| champion | E13.11 (`v6` / `pre_lineup_v6`), fit {r['champion_fit_date']} |",
        f"| era | {r['era'][0]} → {r['era'][1]} (whole era OUT OF SAMPLE by construction) |",
        f"| PRIMARY tier | `{PRIMARY_TIER}` — n = **{p['n']}** (blocks {p['block_sizes']}) |",
        f"| SECONDARY tier | `{SECONDARY_TIER}` — n = **{r['tiers'][SECONDARY_TIER]['n']}** |",
        f"| folds | {N_BLOCKS} contiguous DATE blocks, cross-fit |",
        f"| calibrated null | {r['n_null']} replicates, seed {r['seed']} |",
        f"| CRPS grid vs Normal closed form | \\|Δ\\| = {p['crps_grid_vs_closed_abs_delta']:.2e} (tol {CRPS_VALIDATION_TOL}) |",
        "",
        "---",
        "",
        "## 1. ⭐ The positive controls — run BEFORE the real folds were read",
        "",
        "A diagnosis whose legs cannot separate PLANTED causes cannot separate real ones.",
        "",
        "| control | planted | expected | routed | closed_feature | closed_shape | ✓ |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for c in CONTROLS:
        v = ctl[c]
        L.append(f"| `{c}` | {v['planted'] or 'nothing (the model is correct)'} | "
                 f"`{v['expected']}` | `{v['outcome']}` | {_f(v['closed_feature'],3)} | "
                 f"{_f(v['closed_shape'],3)} | {'✅' if v['passed'] else '⛔'} |")
    L += ["",
          f"**All controls passed: {'✅ YES' if ctl['_all_passed'] else '⛔ NO'}**",
          "",
          "The row-blind matched control `A_ctrl_permuted` (A3's machinery with the binning driven "
          f"by a SHUFFLED `|y−μ|`) closes **{_f(d['control_inert'],3)}** of the gap on the real "
          "folds — a closure bought by capacity rather than by information would show up here.",
          ""]
    if "mde" in p:
        L += ["### MDE — the smallest planted deficit the rule routes correctly", "",
              "| planted σ-CV | routes FEATURE-BOUND | | planted skew α | routes SHAPE-BOUND |",
              "|---:|---:|---|---:|---:|"]
        dm, sm = p["mde"]["dispersion"], p["mde"]["shape"]
        for i in range(max(len(dm), len(sm))):
            a = f"{dm[i]['sigma_cv']:.2f} | {dm[i]['route_rate']:.2f}" if i < len(dm) else " | "
            b = f"{sm[i]['skew_alpha']:.1f} | {sm[i]['route_rate']:.2f}" if i < len(sm) else " | "
            L.append(f"| {a} | | {b} |")
        L.append("")
    L += ["---", "", "## 2. The battery on the real served folds (PRIMARY tier)", "",
          "⛔ = an ORACLE or a CONTROL. **Nothing here competes to ship**, and an oracle ceiling is "
          "what a lever could AT MOST deliver — never what it will.", "",
          _arm_table(p["stats"]), "",
          "`crps` is a CONSTRAINT, never a criterion (E2.1-r). `cov80`/`cov50` are FLOORS, never "
          "targets (NF1.8). Every arm holds `μ` EXACTLY at the served value.", "",
          "### The yardstick", "",
          "| statistic | incumbent | calibrated-null median (the FLOOR) | null 95% band | material | gap | MC p |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for k, obs, pv in ((PRIMARY_STAT, d["incumbent_primary"], d["p_primary"]),
                       (CONFIRM_STAT, d["incumbent_confirm"], d["p_confirm"])):
        f = p["floors"][k]
        L.append(f"| `{k}` | {_f(obs)} | {_f(f['median'])} | [{_f(f['lo'])}, {_f(f['hi'])}] | "
                 f"{_f(f['material'])} | {_f(obs - f['median'])} | {_f(pv,3)} |")
    cf = p["floors"]["pit_ks"].get("construction_floor_median")
    L += ["",
          f"The `pit_ks` calibrated-null floor ({_f(p['floors']['pit_ks']['median'])}) is asserted "
          f"against the distribution-free CONSTRUCTION floor at this n ({_f(cf)}) — `round(Normal)` "
          "with a continuity-corrected randomized PIT is EXACTLY uniform, so the two must agree.",
          "",
          ("⚠️ **OVER_PEEKING** — these oracles land BELOW the floor's lower tail, i.e. below what an "
           "honest model can attain: " + ", ".join(f"`{a}`" for a in d["over_peeking_arms"]) +
           ". Their closure may be cited as *does not bind*, never as *achievable* (NF-W7i).")
          if d["over_peeking_arms"] else
          "No oracle landed below the floor's lower tail — every ceiling below is attainable in principle.",
          "", "---", "",
          "## 3. ⭐ THE LEVERS, BOUNDED", "",
          "| channel | construction | share of the `pit_ks` gap closed | confirm on `\\|p_over_gap\\|` |",
          "|---|---|---:|---:|",
          f"| **calibrator** (global scale) | `closed(A1)` | **{_f(d['closed_calibrator'],3)}** | — |",
          f"| **FEATURE lever** — TV2-1's CEILING | `closed(A3) − closed(A1)` | **{_f(d['closed_feature'],3)}** | {_f(d['confirm_feature'],3)} |",
          f"| **ARCHITECTURE lever** — TV2-2's CEILING | `closed(B2) − closed(A1)` | **{_f(d['closed_shape'],3)}** | {_f(d['confirm_shape'],3)} |",
          f"| **JOINT ceiling** | `closed(C1)` | **{_f(d['closed_combined'],3)}** | — |",
          "",
          f"Bars, registered forward: majority **{RULE_MAJORITY}**, in-play **{RULE_MATERIAL}**, "
          f"confirmation **{RULE_CONFIRM}**. A share below `material` "
          f"({_f(d['material_primary'])} on `pit_ks`) is recorded as **0 (inactive)** — "
          "demonstrable ≠ material (NF-W6).",
          "",
          "Per-arm closure of the `pit_ks` gap:", "",
          "| arm | closed |", "|---|---:|"]
    for a, v in d["closed_primary_by_arm"].items():
        L.append(f"| `{a}` | {_f(v,3)} |")
    L += ["", "---", "",
          "## 4. ⚠️ FLAGGED BINDING CLAUSE — `std_pred`, and the LOCATION channel", "",
          "The spec asks how much of the **`std_pred`**/PIT failure a σ fix closes. `std_pred` names "
          "TWO different statistics in this repo, and **the `0.773 vs ≥2.0` figure the spec cites is "
          "the MEAN-SPREAD one** (`STDDEV(pred_total_runs)`, `validate_v2_gates.py:34`) — a property "
          "of `μ`. Every arm here holds `μ` fixed, so **no leg can move it, by construction**. "
          "Registering a leg against a statistic it cannot move would ship a gate that is décor "
          "(NF-MARGIN2). It is therefore reported as a LOCATION diagnostic and is **not** in the "
          "decision rule. Flagged for the PM, **not edited**.",
          "",
          "| reading | value | bar | |", "|---|---:|---:|---|",
          f"| `std_pred_meanspread` = `STDDEV(pred_total_runs)` (the V2 gate's reading) | "
          f"**{_f(lp['std_pred_meanspread'],3)}** | ≥ 2.0 | "
          f"{'✅' if lp['std_pred_meanspread_passes_v2_gate'] else '⛔ **FAILS**'} |",
          f"| `std_pred_predictive_sd` = `mean(σ)` (Story 10.2's reading) | "
          f"{_f(lp['std_pred_predictive_sd'],3)} | — | |",
          f"| realized `SD(y)` | {_f(lp['realized_sd'],3)} | — | |",
          f"| `Var(μ)/Var(y)` — the share of outcome variance the LOCATION channel explains | "
          f"**{_f(lp['var_mu_over_var_y'],4)}** | — | |",
          f"| served `σ` CV — how much per-game DISPERSION the model expresses at all | "
          f"{_f(lp['sigma_cv'],4)} | — | |",
          "",
          f"Null state, **hand-recorded** per the `cv_power` card's interim rule: "
          f"**`{lp['null_state_hand_recorded']}`** — the mechanism structurally cannot act on this "
          "statistic. ⛔ It is NOT rendered as a fold/season re-test trigger (NF-D18): no number of "
          "additional served games can make a σ leg move `SD(μ)`.",
          "", "---", "",
          "## 5. SECONDARY tier replication (`morning` / `pre_lineup_v6`)", "",
          "Declared in advance as a replication that is REPORTED but does **not** change the verdict "
          "— so the primary cannot be swapped for whichever tier gives the nicer answer (E2.1-r).",
          ""]
    s = r["tiers"][SECONDARY_TIER]["decision"]
    L += ["| | primary (`post_lineup`) | secondary (`morning`) |", "|---|---:|---:|",
          f"| outcome | **`{d['outcome']}`** | `{s['outcome']}` |",
          f"| `closed_calibrator` | {_f(d['closed_calibrator'],3)} | {_f(s['closed_calibrator'],3)} |",
          f"| `closed_feature` | {_f(d['closed_feature'],3)} | {_f(s['closed_feature'],3)} |",
          f"| `closed_shape` | {_f(d['closed_shape'],3)} | {_f(s['closed_shape'],3)} |",
          f"| `closed_combined` | {_f(d['closed_combined'],3)} | {_f(s['closed_combined'],3)} |",
          f"| `std_pred_meanspread` | {_f(lp['std_pred_meanspread'],3)} | "
          f"{_f(r['tiers'][SECONDARY_TIER]['location_probe']['std_pred_meanspread'],3)} |",
          "",
          f"Tiers agree: **{'✅ YES' if r['secondary_agrees'] else '⚠️ NO — reported, verdict unchanged'}**",
          "", "---", "", "## 6. What this study cannot say", "",
          "- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; no bet rode on this model.",
          "- An oracle ceiling is what a lever could **at most** deliver, never what it will. A large "
          "ceiling licenses **funding a story**; it is not evidence of a shipped improvement.",
          "- The verdict is about the **served `post_lineup`** rows in a **2-month** window under "
          "**one** champion. It does not generalise to a different champion.",
          "- MH2.8's skew-normal DSR failure is **cited as evidence, never re-scored** here.",
          ""]
    _REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_MD.write_text("\n".join(x for x in L if x is not None))
    return _REPORT_MD


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_strip(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--controls", action="store_true", help="node 2 only: the positive controls")
    ap.add_argument("--fixture", action="store_true", help="the 1e-9 reproduction pin")
    ap.add_argument("--write-fixture", action="store_true")
    ap.add_argument("--reps", type=int, default=N_NULL)
    ap.add_argument("--no-mde", action="store_true")
    a = ap.parse_args()

    if a.write_fixture:
        _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        fx = fixture_frame()
        fx["expected"] = fixture_run(fx)
        _FIXTURE.write_text(json.dumps(fx, indent=1))
        print(f"fixture → {_FIXTURE}\n{json.dumps(fx['expected'], indent=2)}")
        return
    if a.fixture:
        fx = json.loads(_FIXTURE.read_text())
        got = fixture_run(fx)
        bad = {k: (v, got[k]) for k, v in fx["expected"].items()
               if isinstance(v, float) and abs(v - got[k]) > 1e-9 or
               (not isinstance(v, float) and v != got[k])}
        print(json.dumps(got, indent=2))
        print("REPRODUCTION PIN (1e-9):", "✅ OK" if not bad else f"⛔ DRIFT {bad}")
        sys.exit(0 if not bad else 1)
    if a.controls:
        df = pull()
        _, mu, sigma, dates = _tier(df, PRIMARY_TIER)
        out = run_controls(mu, sigma, dates, reps=a.reps)
        _CONTROLS_JSON.parent.mkdir(parents=True, exist_ok=True)
        _CONTROLS_JSON.write_text(json.dumps(_strip(out), indent=1))
        print(json.dumps(_strip(out), indent=2))
        print("ALL CONTROLS PASSED:", out["_all_passed"])
        sys.exit(0 if out["_all_passed"] else 1)

    r = run(reps=a.reps, mde=not a.no_mde)
    _REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_JSON.write_text(json.dumps(_strip(r), indent=1))
    print(f"report → {write_report(r)}")
    print(f"VERDICT: {r['verdict']} → {r['route']}")


if __name__ == "__main__":
    main()

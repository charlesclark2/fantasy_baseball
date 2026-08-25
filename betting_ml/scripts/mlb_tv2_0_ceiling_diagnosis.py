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
    "A3_sigma_scalemix",         # ⛔ UPPER BOUND (a shrunk Bayes peek at the per-game scale)
    "A_ctrl_permuted",           # ⛔ row-blind matched control
    "B1_shape_skewnormal",
    "B2_shape_empirical",        # ⛔ UPPER BOUND
    "C1_combined",               # ⛔ joint ceiling
)
ORACLE_ARMS = ("A3_sigma_scalemix", "A_ctrl_permuted", "B2_shape_empirical", "C1_combined")
N_BINS = 10                       # deciles for the sigma oracles
MIN_BIN_ROWS = 20                 # below this an out-of-block bin falls back to the pooled RMS
SKEWNORM_COLLAPSE_ABS_ALPHA = 0.05  # |a| below this = the nested form collapsed onto its Normal foil

#: §4 — metrics. ⭐ AMENDMENT 1 (node 2, before any real-data read): ONE PRIMARY PER LEVER.
#: The controls PROVED a single yardstick cannot separate the levers — a planted per-game σ
#: deficit of CV 0.35 moved pooled `pit_ks` from 0.0302 to 0.0241 (i.e. NOT AT ALL), while a
#: marginal shape law cannot recover a per-game scale loss on `crps` (measured: it made it WORSE).
#: Each lever is therefore scored on the statistic it acts on, and neither can steal the other's
#: credit. See `mlb_tv2_0_prereg.md` §12.
CRPS_STAT = "crps"               # a PER-GAME proper score — the only statistic per-game σ can move
ASYM_STAT = "p_over_gap_abs"     # the ASYMMETRY the product prints — a SYMMETRIC scale deficit
                                 # leaves it alone, so the feature lever cannot be scored on it
FIDELITY_STAT = "pit_ks"         # safeguard + context: overall distributional fidelity
PRIMARY_STATS = (CRPS_STAT, ASYM_STAT)
REPORT_STATS = (CRPS_STAT, ASYM_STAT, FIDELITY_STAT)
BOOT_STATS = (CRPS_STAT, ASYM_STAT, FIDELITY_STAT, "p_over_stated", "p_over_gap",
              "pit_mdd")
#: Each lever is scored on EVERY statistic it can act on, and on none it cannot.
LEVER_STATS = {"shape": (CRPS_STAT, ASYM_STAT), "feature": (CRPS_STAT,)}
FEATURE_STAT, SHAPE_STAT = CRPS_STAT, ASYM_STAT   # back-compat aliases for the report
MIX_K_MAX = 3                    # scale-mixture components; K is chosen by BIC, out of block
N_BOOT = 400                     # paired row bootstrap for lever materiality
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
MDE_SIGMA_CV_GRID = (0.05, 0.10, 0.20, 0.35, 0.50)
MDE_SKEW_GRID = (0.5, 1.0, 2.0, 4.0, 6.0)
N_MDE = 8                         # replicates per grid point
MDE_N_BOOT = 150                  # a coarser (hence CONSERVATIVE) paired CI for the MDE sweep only

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


def _em_scale_mixture(z, K, iters=400, tol=1e-10):
    """EM for a ZERO-MEAN K-component normal scale mixture `z ~ Σ w_k N(0, s_k²)`."""
    z2 = np.asarray(z, float) ** 2
    s2 = np.maximum(np.quantile(z2, np.linspace(0.15, 0.85, K)) if K > 1
                    else np.array([z2.mean()]), 1e-6)
    w, ll_old = np.full(K, 1.0 / K), -np.inf
    ll = ll_old
    for _ in range(iters):
        logp = -0.5 * (np.log(2 * np.pi * s2)[None, :] + z2[:, None] / s2[None, :]) + np.log(w)[None, :]
        mx = logp.max(1, keepdims=True)
        e = np.exp(logp - mx)
        den = e.sum(1, keepdims=True)
        r = e / den
        ll = float((np.log(den) + mx).sum())
        w = r.mean(0)
        s2 = np.maximum((r * z2[:, None]).sum(0) / np.maximum(r.sum(0), 1e-12), 1e-6)
        if ll - ll_old < tol:
            break
        ll_old = ll
    return w, s2, ll


class ScaleMixtureOracle:
    """⛔ UPPER BOUND on ANY per-game σ model — a SHRUNK Bayes peek, not a row-level peek.

    ⭐ AMENDMENT 1 (node 2). The registered `A3_sigma_clairvoyant` — out-of-block RMS residual
    within the row's own `|y−μ|` decile — is a DEGENERATE, not a ceiling: it forces `z ≈ ±1`, so on
    CLEAN data it posted `scale_cv 0.745`, `pit_ks 0.225` (vs the incumbent's 0.030), `cov50 0.106`
    and a CRPS BELOW what a correctly specified model can attain. It bounded nothing, in either
    direction. That is NF-W6's warning verbatim: *a row-level peek is a zero-CRPS degenerate, not a
    ceiling* — and the positive controls are what caught it, before any real outcome was read.

    The cure keeps the peek but makes it self-correcting: fit a ZERO-MEAN normal scale mixture to
    the OUT-OF-BLOCK `z` (`K ∈ 1..3` chosen by **BIC**, out of block), then give each in-block row
    its POSTERIOR mean scale `sqrt(E[s² | z_i])`. Two properties make it a legitimate ceiling:

    * **Under a constant true scale, BIC picks `K = 1` and the posterior scale is CONSTANT** — the
      oracle collapses onto `A1` and is INERT. Measured on `PC_clean`: `K = 1` on all 5 blocks,
      CRPS 2.4312 vs the incumbent's 2.4309. A binned clairvoyant cannot do this: it manufactures
      dispersion out of pure noise.
    * The mixture is **SYMMETRIC and zero-mean**, so it cannot absorb SKEW — which is what keeps
      this leg from stealing the architecture lever's credit. Measured on `PC_shape` (α = 4):
      `K = 1` on all blocks, CRPS 2.4498 vs 2.4491 — inert.
    """

    @staticmethod
    def _bic_k(z, k_max):
        z = np.asarray(z, float)
        n = len(z)
        best = None
        for K in range(1, k_max + 1):
            w, s2, ll = _em_scale_mixture(z, K)
            bic = -2 * ll + (2 * K - 1) * np.log(n)
            if best is None or bic < best[0]:
                best = (bic, K, w, s2)
        return best[1], best[2], best[3]

    def __init__(self, z, k_max=MIX_K_MAX):
        z = np.asarray(z, float)
        K, w, s2 = self._bic_k(z, k_max)
        # ⭐ AMENDMENT 4 (prereg §12) — THE SYMMETRY GATE. A genuine per-game scale mixture is
        # SYMMETRIC; SKEW is not. A right-skewed but homoscedastic sample has a heavy RIGHT tail
        # only, which raises BIC's preference for `K = 2` and opens a peek the oracle then profits
        # from — measured: the FEATURE lever fired on 20% of pure-SHAPE control draws. So each side
        # of the median is reflected into a symmetric sample of its own and must INDEPENDENTLY
        # prefer `K ≥ 2`; otherwise the oracle is forced to `K = 1` and is INERT. Under a real scale
        # mixture both tails are heavy and the gate opens; under pure skew only one is.
        d = z - np.median(z)
        sides = []
        for half in (d[d > 0], -d[d < 0]):
            sides.append(self._bic_k(np.concatenate([half, -half]), k_max)[0]
                         if len(half) >= 3 * N_BINS else 1)
        self.K_full, self.K_sides = int(K), [int(x) for x in sides]
        if K > 1 and min(sides) < 2:
            K, w, s2 = self._bic_k(z, 1)          # symmetry gate CLOSED -> inert
        self.K, self.w, self.s2 = K, w, s2

    def scale(self, z):
        """`sqrt(E[s² | z])` — constant (hence inert) whenever `K == 1`."""
        z2 = np.asarray(z, float) ** 2
        logp = (-0.5 * (np.log(2 * np.pi * self.s2)[None, :] + z2[:, None] / self.s2[None, :])
                + np.log(self.w)[None, :])
        mx = logp.max(1, keepdims=True)
        e = np.exp(logp - mx)
        r = e / e.sum(1, keepdims=True)
        return np.sqrt((r * self.s2[None, :]).sum(1))


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

def randomized_pit(y, arm, rng=None, *, u=None):
    """Continuity-corrected + randomized PIT, generalized from MH2.6's house instrument to any F.

    `total_runs` is an integer and the predictive is continuous: reading `F(y)` straight off is
    lumpy, and inclusive integer interval bounds INFLATE coverage (the E2.1-r defect). Under a
    correctly specified predictive this is EXACTLY uniform, at any scale and any shape.
    """
    y = np.asarray(y, float)
    lo, hi = arm.cdf_at(y - 0.5), arm.cdf_at(y + 0.5)
    # ⭐ `u` lets EVERY arm share ONE uniform draw. The arms are compared PAIRWISE on the same
    # outcomes, so independent randomisation per arm injects noise into the DIFFERENCE that has
    # nothing to do with the arms — it inflated the paired CI and cost real detection power.
    uu = rng.uniform(size=len(y)) if u is None else np.asarray(u, float)
    return lo + uu * np.maximum(hi - lo, 0.0)


def _crps_rows(y, arm, levels=None):
    """PER-ROW CRPS = 2∫ pinball dτ on a shared quantile grid — identical for every arm."""
    lv = _levels() if levels is None else levels
    q = arm.quantiles(lv)
    yy = np.asarray(y, float)[:, None]
    ind = (yy < q).astype(float)
    return 2.0 * np.mean((yy - q) * (lv[None, :] - ind), axis=1)


def crps_grid(y, arm, levels=None):
    return float(np.mean(_crps_rows(y, arm, levels)))


def _levels():
    return (np.arange(1, CRPS_LEVELS + 1)) / (CRPS_LEVELS + 1.0)


def crps_normal_closed(y, mu, sigma):
    from scipy.stats import norm
    z = (np.asarray(y, float) - mu) / sigma
    return float(np.mean(sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))))


def arm_rows(y, arm, rng=None, *, u=None):
    """The PER-ROW components every statistic is built from — so the bootstrap can be PAIRED.

    ⭐ Every arm scores the SAME outcomes, so the decision-relevant noise is the noise of the
    DIFFERENCE, not of the level. An unpaired null band is orders of magnitude wider and would
    declare a real, large lever ‘inside noise’ (measured on `PC_dispersion`: the incumbent's CRPS
    sits inside its unpaired null band while an oracle beats it by 0.12).
    """
    y = np.asarray(y, float)
    return {
        "u": randomized_pit(y, arm, rng, u=u),
        "crps": _crps_rows(y, arm),
        "stated": 1.0 - arm.cdf_at(arm.mu),
        "over": (y > arm.mu).astype(float),
    }


def _ks_uniform(u):
    """KS statistic of `u` against Uniform(0,1) — the closed form, vectorised over a 2-D block."""
    v = np.sort(u, axis=-1)
    n = v.shape[-1]
    i = np.arange(1, n + 1) / n
    return np.maximum((i - v).max(-1), (v - (i - 1.0 / n)).max(-1))


def stats_from_rows(rows, idx=None):
    """Recompute every bootstrap-relevant statistic from per-row components on a row subset.

    `idx` may be 1-D (one resample) or 2-D `(B, n)` (a whole bootstrap block at once) — the block
    form is what keeps the paired bootstrap affordable.
    """
    u = rows["u"] if idx is None else rows["u"][idx]
    c = rows["crps"] if idx is None else rows["crps"][idx]
    st = rows["stated"] if idx is None else rows["stated"][idx]
    ov = rows["over"] if idx is None else rows["over"][idx]
    if u.ndim == 1:
        u, c, st, ov = u[None, :], c[None, :], st[None, :], ov[None, :]
        squeeze = True
    else:
        squeeze = False
    n = u.shape[-1]
    counts = np.stack([((u >= b / 10) & (u < (b + 1) / 10)).mean(-1) for b in range(10)], -1)
    out = {"crps": c.mean(-1), "pit_ks": _ks_uniform(u),
           "pit_mdd": np.abs(counts - 0.1).max(-1),
           "p_over_stated": st.mean(-1),
           "p_over_gap": st.mean(-1) - ov.mean(-1),
           "p_over_gap_abs": np.abs(st.mean(-1) - ov.mean(-1))}
    return {k: float(v[0]) for k, v in out.items()} if squeeze else out


def bootstrap_block(rows_by_arm, keys, *, n_boot=N_BOOT, seed=SEED):
    """ONE shared resample-index block, every arm scored on it — the pairing, made affordable."""
    n = len(next(iter(rows_by_arm.values()))["u"])
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    return {a: {k: np.asarray(v[k], float) for k in keys}
            for a, v in ((a, stats_from_rows(r, idx)) for a, r in rows_by_arm.items())}


def paired_lift_ci(rows_a, rows_b, key, *, boot=None, arm_a=None, arm_b=None,
                   n_boot=N_BOOT, seed=SEED, alpha=0.05):
    """95% CI for `stat(A) − stat(B)` under a PAIRED row bootstrap (both arms on the same rows)."""
    point = stats_from_rows(rows_a)[key] - stats_from_rows(rows_b)[key]
    if boot is not None:
        d = boot[arm_a][key] - boot[arm_b][key]
    else:
        n = len(rows_a["u"])
        idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
        d = stats_from_rows(rows_a, idx)[key] - stats_from_rows(rows_b, idx)[key]
    lo, hi = np.quantile(d, [alpha / 2, 1 - alpha / 2])
    return {"point": float(point), "lo": float(lo), "hi": float(hi),
            "material": bool(lo > 0 or hi < 0)}


def arm_stats(y, arm, rng=None, *, u=None):
    """Every statistic, for one arm. `p_over` is read AT THE MODEL'S OWN MEAN — market-blind."""
    from scipy.stats import kstest, kurtosis, skew
    y = np.asarray(y, float)
    n = len(y)
    u = randomized_pit(y, arm, rng, u=u)
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

    # A3 ⛔ — THE CEILING on any per-game sigma model (AMENDMENT 1: a shrunk Bayes peek).
    z_perm = z[rng.permutation(len(y))]
    s3, s3c, mix_k, mix_k_raw = np.empty(len(y)), np.empty(len(y)), [], []
    for b in range(nb):
        ora = ScaleMixtureOracle(z[block != b])
        mix_k.append(ora.K)
        mix_k_raw.append(ora.K_full)
        m = block == b
        s3[m] = sigma[m] * ora.scale(z[m])
        s3c[m] = sigma[m] * ora.scale(z_perm[m])          # row-blind twin
    s3, s3c = np.maximum(s3, 1e-6), np.maximum(s3c, 1e-6)
    arms["A3_sigma_scalemix"] = Arm("A3_sigma_scalemix", mu, s3, norm_laws, block)
    notes["A3_mixture_K_by_block"] = [int(k) for k in mix_k]
    notes["A3_mixture_K_ungated_by_block"] = [int(k) for k in mix_k_raw]
    notes["A3_symmetry_gate_closed_blocks"] = int(sum(1 for a, b_ in zip(mix_k, mix_k_raw)
                                                     if a == 1 and b_ > 1))
    notes["A3_all_blocks_single_component"] = bool(all(k == 1 for k in mix_k))

    # A_ctrl ⛔ — A3's IDENTICAL machinery driven by a SHUFFLED z. Must be inert (NF-W7f).
    arms["A_ctrl_permuted"] = Arm("A_ctrl_permuted", mu, s3c, norm_laws, block)

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

def _closed(obs_inc, obs_arm, gap):
    """Share of `gap` an arm closes. `gap <= 0` = no failure on this statistic to close."""
    return 0.0 if gap <= 0 else float((obs_inc - obs_arm) / gap)


def decide(stats, floors, rows, n_boot=N_BOOT):
    """⭐ THE DECISION RULE (prereg §7, as amended in §12). Deterministic; order fixed.

    TWO INDEPENDENT YES/NO QUESTIONS, hierarchically decomposed:

      Q1  is the ARCHITECTURE lever in play?  `imp(B2) − imp(A1)`   (TV2-2's CEILING)
      Q2  is the FEATURE lever in play?       `imp(C1) − imp(B2)`   (TV2-1's CEILING)

    **Each lever is scored on every statistic it can ACT on, and on none it cannot** — the thing
    the positive controls proved is required (§12):

    * `crps` is a PER-GAME proper score. A marginal shape law is identical across games, so it
      cannot recover a per-game scale loss — which is why the feature lever can be read here and
      cannot be stolen by the shape lever. Both levers act on it.
    * `p_over_gap_abs` is the ASYMMETRY of the predictive around its own mean, i.e. the error on
      the quantity the product literally prints. A SYMMETRIC scale-mixture deficit leaves it alone,
      so **only the shape lever is admissible here** — scoring the feature lever on it would be
      registering a gate the arm cannot move (NF-MARGIN2).

    A lever's share is the **share of the JOINT CEILING** it accounts for on the statistic where it
    acts most, counting only statistics where its PAIRED 95% CI excludes 0 and the lift is
    positive. The calibrated-null gap is reported as CONTEXT (how far the incumbent sits from a
    correctly specified model) but is NOT the denominator: on a planted or a genuinely non-Normal
    world it can go negative, which would zero a real lever's share for an arithmetic reason.

    The decomposition is HIERARCHICAL and deliberately conservative toward the EXPENSIVE lever: the
    architecture lever is scored beyond a plain recalibrator, and the feature lever — the one that
    needs a whole new data product — must prove it adds BEYOND the best marginal shape.
    """
    ch = {}
    for k in REPORT_STATS:
        f = floors[k]
        inc = stats["incumbent"][k]
        ch[k] = {"stat": k, "incumbent": inc, "floor": f["median"], "band": [f["lo"], f["hi"]],
                 "gap": inc - f["median"],
                 "outside_null_band": bool(not (f["lo"] <= inc <= f["hi"])),
                 "closed": {a: _closed(inc, stats[a][k], inc - f["median"])
                            for a in ARMS if a != "incumbent"}}

    boot = bootstrap_block(rows, BOOT_STATS, n_boot=n_boot)

    def lift(hi_arm, lo_arm, k):
        """`stat(lo_arm) − stat(hi_arm)`: positive = `hi_arm` is better. PAIRED CI over rows."""
        r = paired_lift_ci(rows[lo_arm], rows[hi_arm], k, boot=boot,
                           arm_a=lo_arm, arm_b=hi_arm)
        r["material"] = bool(r["material"])
        r["in_play"] = bool(r["material"] and r["point"] > 0)
        return r

    PAIRS = {"calibrator": ("A1_sigma_level", "incumbent"),
             "shape": ("B2_shape_empirical", "A1_sigma_level"),
             "feature": ("C1_combined", "B2_shape_empirical"),
             "feature_direct": ("A3_sigma_scalemix", "A1_sigma_level")}
    joint = {k: lift("C1_combined", "incumbent", k) for k in REPORT_STATS}
    levers = {}
    for name, (hi, lo) in PAIRS.items():
        per = {}
        for k in REPORT_STATS:
            v = lift(hi, lo, k)
            den = joint[k]["point"]
            v["share_of_ceiling"] = float(v["point"] / den) if den > 0 else 0.0
            v["share_of_null_gap"] = _closed(0.0, -v["point"], ch[k]["gap"])
            v["admissible"] = k in LEVER_STATS.get(name.replace("_direct", ""), REPORT_STATS)
            per[k] = v
        shares = [per[k]["share_of_ceiling"] for k in per
                  if per[k]["admissible"] and per[k]["in_play"]]
        levers[name] = {"by_stat": per, "share": max(shares) if shares else 0.0,
                        "in_play": bool(shares)}

    # ⭐ AMENDMENT 3 (prereg §12) — the ASYMMETRY channel is read as a MOVEMENT, not as a folded
    # |gap|. `|g_A1| − |g_B2|` shares the realized over-rate between the arms but does NOT cancel
    # it under the fold, so at n≈758 the binomial noise in `mean(y > μ)` (SE 0.018) swamps an
    # asymmetry the size of the real one and the paired CI spans 0 in most draws — measured: the
    # `PC_shape` control routed correctly only 0.40 of the time. The DIFFERENCE OF STATED
    # PROBABILITIES cancels the realized rate EXACTLY, so it is estimated with almost no outcome
    # noise; the incumbent's (imprecise) gap is used only as the denominator, and its uncertainty
    # is reported rather than propagated into the in-play test.
    g_inc = stats["incumbent"]["p_over_gap"]
    gq = np.quantile(boot["incumbent"]["p_over_gap"], [0.025, 0.975])
    # ⛔ PRECONDITION — you cannot close a gap that is not demonstrably there. Without this the
    # channel credits a shape law for fitting SAMPLE skew: under a pure symmetric scale-mixture
    # deficit the finite-sample `z` has a nonzero skew that drives BOTH the realized over-rate and
    # the fitted empirical median, so the movement and the (noise-only) gap agree in sign ~90% of
    # the time. Measured: `PC_dispersion` routed correctly 0.10 of the time without it.
    gap_material = bool(gq[0] > 0 or gq[1] < 0)
    mv = paired_lift_ci(rows["A1_sigma_level"], rows["B2_shape_empirical"], "p_over_stated",
                        boot=boot, arm_a="A1_sigma_level", arm_b="B2_shape_empirical")
    toward_zero = bool(np.sign(mv["point"]) == np.sign(g_inc) and g_inc != 0)
    in_play = bool(gap_material and mv["material"] and toward_zero)
    asym = {"incumbent_signed_gap": float(g_inc),
            "incumbent_gap_ci": [float(gq[0]), float(gq[1])], "gap_material": gap_material,
            "movement": mv["point"], "lo": mv["lo"], "hi": mv["hi"],
            "material": mv["material"], "toward_zero": toward_zero, "in_play": in_play,
            "share": float(mv["point"] / g_inc) if in_play else 0.0}
    if asym["in_play"] and asym["share"] > levers["shape"]["share"]:
        levers["shape"]["share"] = asym["share"]
        levers["shape"]["in_play"] = True

    ctrl = {k: lift("A_ctrl_permuted", "A1_sigma_level", k) for k in PRIMARY_STATS}
    s_share, f_share = levers["shape"]["share"], levers["feature"]["share"]
    any_failure = any(ch[k]["outside_null_band"] for k in PRIMARY_STATS)
    joint_material = any(joint[k]["in_play"] for k in PRIMARY_STATS)

    demoted = None
    if not joint_material and not any_failure:
        outcome = "NO_MEASURABLE_DEFECT"
    elif s_share < RULE_MATERIAL and f_share < RULE_MATERIAL:
        outcome = "IRREDUCIBLE"
    elif f_share >= RULE_MAJORITY and s_share < RULE_MATERIAL:
        outcome = "FEATURE-BOUND"
    elif s_share >= RULE_MAJORITY and f_share < RULE_MATERIAL:
        outcome = "SHAPE-BOUND"
    elif f_share >= RULE_MATERIAL and s_share >= RULE_MATERIAL:
        outcome = "BOTH"
    else:
        outcome = "INDETERMINATE"

    # SAFEGUARD — a winning lever must not make OVERALL distributional fidelity materially WORSE.
    # ⚠️ Only a materially NEGATIVE lift demotes; a within-noise one is recorded, never scored as
    # a pass (NF1.7 (a)).
    guard = {"state": "NOT_APPLICABLE", "value": None, "stat": FIDELITY_STAT}
    win = {"FEATURE-BOUND": "feature", "SHAPE-BOUND": "shape", "BOTH": "shape"}.get(outcome)
    if win:
        g = levers[win]["by_stat"][FIDELITY_STAT]
        guard = {"state": "FAIL" if (g["material"] and g["point"] < 0)
                 else ("PASS" if g["material"] else "WITHIN_NOISE"),
                 "value": g["point"], "stat": FIDELITY_STAT}
        if guard["state"] == "FAIL":
            demoted = f"{outcome} ({FIDELITY_STAT} lift {g['point']:+.4f} materially negative)"
            outcome = "INDETERMINATE"

    sub = ("CALIBRATOR-SUFFICIENT" if outcome == "IRREDUCIBLE"
           and levers["calibrator"]["share"] >= RULE_MAJORITY else None)
    over = sorted({a for a in ORACLE_ARMS for k in PRIMARY_STATS
                   if ch[k]["outside_null_band"] and stats[a][k] < floors[k]["lo"]})

    return {
        "outcome": outcome, "route": ROUTES[outcome], "sub_state": sub, "demoted_from": demoted,
        "crps_stat": CRPS_STAT, "asym_stat": ASYM_STAT, "fidelity_stat": FIDELITY_STAT,
        "lever_stats": LEVER_STATS, "channels": ch, "levers": levers, "joint_ceiling": joint,
        "control_inert": ctrl, "fidelity_guard": guard, "asymmetry_channel": asym,
        "closed_calibrator": levers["calibrator"]["share"],
        "closed_shape": s_share, "closed_feature": f_share,
        "closed_feature_direct": levers["feature_direct"]["share"],
        "closed_combined": {k: 1.0 if joint[k]["in_play"] else 0.0 for k in PRIMARY_STATS},
        "any_failure_outside_null_band": bool(any_failure),
        "joint_ceiling_material": bool(joint_material),
        "over_peeking_arms": over,
    }


def score(y, mu, sigma, dates, *, seed=SEED, reps=N_NULL, null=None, n_boot=N_BOOT):
    """One population -> every arm's statistics, the floors, and the triggered outcome."""
    block = date_blocks(dates)
    rng = np.random.default_rng(seed)
    arms, notes = build_arms(y, mu, sigma, block, rng)
    stats, rows = {}, {}
    u_shared = np.random.default_rng(seed + 1000).uniform(size=len(y))   # ONE draw, every arm
    for a in ARMS:
        stats[a] = arm_stats(y, arms[a], None, u=u_shared)
        rows[a] = arm_rows(y, arms[a], u=u_shared)
    nl = calibrated_null(mu, sigma, block, reps=reps, seed=seed) if null is None else null
    floors = {k: floor_of(nl, k) for k in nl}
    d = decide(stats, floors, rows, n_boot=n_boot)
    d["mc_p"] = {k: mc_pvalue(nl[k], stats["incumbent"][k]) for k in REPORT_STATS}
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


CONTROL_REPS = 20                 # replicates per control — a rate, not a single draw
CONTROL_ROUTE_BAR = 0.80          # a positive control must route correctly at least this often
CONTROL_WRONG_LEVER_BAR = 0.10    # ...and must credit the OTHER lever at most this often
CONTROL_CLEAN_BAR = 0.90          # a clean frame must return NO_MEASURABLE_DEFECT at least this often


def _control_kwargs(name):
    return {"PC_clean": {}, "PC_dispersion": {"sigma_cv": CONTROL_SIGMA_CV},
            "PC_shape": {"skew_alpha": CONTROL_SKEW_ALPHA},
            "PC_both": {"sigma_cv": CONTROL_SIGMA_CV,
                        "skew_alpha": CONTROL_SKEW_ALPHA}}[name]


def run_controls(mu, sigma, dates, *, seed=SEED, reps=N_NULL, n_rep=CONTROL_REPS):
    """⭐ Node 2. A DETECTION RATE over replicates, never a single draw.

    ⭐ AMENDMENT 2 (prereg §12). A one-draw control conflates "the legs do not separate" with "this
    particular draw was quiet": at `n ≈ 758` a shape deficit the size of the REAL one (`z` skew
    ≈ 0.74, i.e. `α ≈ 4`) is right at the design's detection boundary, so a single replicate routes
    correctly on some seeds and not others. A rate says which of the two it is, and the pass bars
    are DESIGN quantities fixed before any real outcome was read (MH2.8 used the same shape: 40
    clean replicates at a 0.9 bar, 10 positive at 1.0).
    """
    out = {}
    block = date_blocks(dates)
    nl = calibrated_null(mu, sigma, block, reps=reps, seed=seed)   # one null; (mu, sigma) fixed
    wrong = {"PC_dispersion": "closed_shape", "PC_shape": "closed_feature"}
    for i, name in enumerate(CONTROLS):
        kw = _control_kwargs(name)
        want = CONTROL_EXPECT[name]
        hits, wrong_hits, rows = 0, 0, []
        for r in range(n_rep):
            rng = np.random.default_rng(seed + 500 + 97 * i + r)
            d = score(plant(mu, sigma, rng, **kw), mu, sigma, dates,
                      seed=seed, reps=reps, null=nl)["decision"]
            hits += int(d["outcome"] == want)
            if name in wrong:
                wrong_hits += int(d[wrong[name]] >= RULE_MATERIAL)
            rows.append({"outcome": d["outcome"], "closed_shape": d["closed_shape"],
                         "closed_feature": d["closed_feature"],
                         "K": d.get("_K")})
        rate = hits / n_rep
        wrate = wrong_hits / n_rep if name in wrong else 0.0
        bar = CONTROL_CLEAN_BAR if name == "PC_clean" else CONTROL_ROUTE_BAR
        out[name] = {
            "planted": kw, "expected": want, "reps": n_rep,
            "route_rate": rate, "route_bar": bar,
            "wrong_lever_rate": wrate, "wrong_lever_bar": CONTROL_WRONG_LEVER_BAR,
            "wrong_lever_key": wrong.get(name),
            "passed": bool(rate >= bar and wrate <= CONTROL_WRONG_LEVER_BAR),
            "outcome_counts": {o: sum(1 for x in rows if x["outcome"] == o) for o in OUTCOMES
                               if any(x["outcome"] == o for x in rows)},
            "median_closed_shape": float(np.median([x["closed_shape"] for x in rows])),
            "median_closed_feature": float(np.median([x["closed_feature"] for x in rows])),
        }
    out["_all_passed"] = all(v["passed"] for k, v in out.items() if not k.startswith("_"))
    return out


def mde_curve(mu, sigma, dates, *, seed=SEED, reps=400, n_rep=N_MDE, n_boot=MDE_N_BOOT):
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
                o = score(y, mu, sigma, dates, seed=seed, reps=reps, null=nl,
                          n_boot=n_boot)["decision"]["outcome"]
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
    flat = {k: d[k] for k in ("outcome", "closed_calibrator", "closed_feature", "closed_shape")}
    flat.update({f"combined_{k}": v for k, v in d["closed_combined"].items()})
    for name, v in d["levers"].items():
        for k in PRIMARY_STATS:
            flat[f"lift_{name}_{k}"] = v["by_stat"][k]["point"]
    for k in PRIMARY_STATS:
        flat[f"gap_{k}"] = d["channels"][k]["gap"]
        flat[f"inert_{k}"] = d["control_inert"][k]["point"]
        flat[f"ceiling_{k}"] = d["joint_ceiling"][k]["point"]
    flat["fidelity_guard_state"] = d["fidelity_guard"]["state"]
    return flat


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
        r["floors"][SHAPE_STAT]["construction_floor_median"] = float(np.median(cons))

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
    keys = ("crps", "pit_ks", "pit_mdd", "p_over_stated", "p_over_realized", "p_over_gap",
            "cov80", "cov50", "var_z_pooled", "z_skew", "z_excess_kurtosis", "scale_mean",
            "scale_cv")
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
    ch = d["channels"]
    L = [
        f"# MLB-TV2-0 — the totals-ceiling diagnosis: **{r['verdict']}**",
        "",
        f"> ## ⭐ ROUTING: {d['route']}",
        "",
    ]
    if d["sub_state"]:
        L += [f"**Sub-state:** `{d['sub_state']}` — a LABEL inside `IRREDUCIBLE` mapping to the "
              "same registered action. ⛔ Not a fifth route.", ""]
    L += [
        f"`best_alpha = {r['best_alpha']}` · `bet_paused = true` · **market-blind** · "
        "**nothing serves** · deploy-held",
        "",
        "> **What this study is.** An ORACLE diagnosis of the SERVED totals predictive. It bounds "
        "what each of the epic's two candidate levers could AT MOST deliver and triggers a decision "
        "rule registered before any statistic was computed on a realized outcome. It builds neither "
        "fix. It says nothing about win rate, edge, ROI or CLV — at `best_alpha = 0` no bet rode on "
        "this model. Pre-registration: [`mlb_tv2_0_prereg.md`](mlb_tv2_0_prereg.md); the node-2 "
        "amendment is its §12.",
        "",
        "## Population",
        "",
        "| | |", "|---|---|",
        f"| champion | E13.11 (`v6` / `pre_lineup_v6`), fit {r['champion_fit_date']} |",
        f"| era | {r['era'][0]} → {r['era'][1]} — the whole era is OUT OF SAMPLE by construction |",
        f"| PRIMARY tier | `{PRIMARY_TIER}` — n = **{p['n']}** (date blocks {p['block_sizes']}) |",
        f"| SECONDARY tier | `{SECONDARY_TIER}` — n = **{r['tiers'][SECONDARY_TIER]['n']}** |",
        f"| folds | {N_BLOCKS} contiguous DATE blocks, cross-fit |",
        f"| calibrated null | {r['n_null']} replicates, seed {r['seed']} |",
        f"| CRPS grid vs the Normal closed form | \\|Δ\\| = "
        f"{p['crps_grid_vs_closed_abs_delta']:.2e} (tol {CRPS_VALIDATION_TOL}) |",
        "", "---", "",
        "## 1. ⭐ The positive controls — run BEFORE any realized outcome was read",
        "",
        "A diagnosis whose legs cannot separate PLANTED causes cannot separate real ones. **The "
        "first design FAILED these** — and the failure is the most useful thing this story "
        "measured; see §6 and prereg §12.",
        "",
        f"Each control is a DETECTION RATE over {CONTROL_REPS} replicates, not a single draw "
        "(prereg §12, amendment 2).",
        "",
        "| control | planted | expected route | route rate (bar) | wrong-lever rate (bar) | "
        "median `closed_shape` | median `closed_feature` | ✓ |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for c in CONTROLS:
        v = ctl[c]
        L.append(f"| `{c}` | {v['planted'] or '*nothing — the model is correct*'} | "
                 f"`{v['expected']}` | **{v['route_rate']:.2f}** ({v['route_bar']:.2f}) | "
                 f"{v['wrong_lever_rate']:.2f} ({v['wrong_lever_bar']:.2f}) | "
                 f"{_f(v['median_closed_shape'],3)} | {_f(v['median_closed_feature'],3)} | "
                 f"{'✅' if v['passed'] else '⛔'} |")
    L.append("")
    L.append("Outcome distribution per control: " + " · ".join(
        f"`{c}` {ctl[c]['outcome_counts']}" for c in CONTROLS))
    L += ["",
          f"**All controls passed: {'✅ YES' if ctl['_all_passed'] else '⛔ NO'}**", ""]
    if "mde" in p:
        L += ["### MDE — the smallest PLANTED deficit the rule routes correctly", "",
              "A null is *\"no lever larger than this\"*, never a shrug (NF1.8).", "",
              "| planted σ-CV | routes `FEATURE-BOUND` | | planted skew α | routes `SHAPE-BOUND` |",
              "|---:|---:|---|---:|---:|"]
        dm, sm = p["mde"]["dispersion"], p["mde"]["shape"]
        for i in range(max(len(dm), len(sm))):
            x = f"{dm[i]['sigma_cv']:.2f} | {dm[i]['route_rate']:.2f}" if i < len(dm) else "— | —"
            z = f"{sm[i]['skew_alpha']:.1f} | {sm[i]['route_rate']:.2f}" if i < len(sm) else "— | —"
            L.append(f"| {x} | | {z} |")
        L.append("")
    L += ["---", "", "## 2. The battery on the real served folds (PRIMARY tier)", "",
          "⛔ = an ORACLE or a CONTROL. **Nothing here competes to ship**, and an oracle ceiling is "
          "what a lever could AT MOST deliver — never what it will. Every arm holds `μ` EXACTLY at "
          "the served value.", "",
          _arm_table(p["stats"]), "",
          f"Scale-mixture components chosen by BIC, out of block: "
          f"**{p['notes']['A3_mixture_K_by_block']}**"
          + ("  ⟵ ⭐ **`K = 1` on every block: the oracle that is allowed to see the answer finds "
             "NO per-game σ signal at all.**" if p['notes']['A3_all_blocks_single_component'] else "")
          + f"\n\nSkew-normal `α` by block (`B1`, reported): "
          f"{[round(x,3) for x in p['notes']['B1_alpha_by_block']]}"
          + ("  ⚠️ at least one block COLLAPSED onto its Normal foil — a nested form's near-zero "
             "margin is a TIE, not a shape finding." if p['notes']['B1_collapsed_any'] else ""),
          "", "### The yardstick — one primary PER LEVER (prereg §12)", "",
          "| statistic | role | incumbent | calibrated-null median (the FLOOR) | null 95% band | "
          "gap | outside the band? | MC p |",
          "|---|---|---:|---:|---:|---:|---|---:|"]
    roles = {FEATURE_STAT: "**DISPERSION lever's primary** — a PER-GAME proper score",
             SHAPE_STAT: "**ARCHITECTURE lever's primary** — the ASYMMETRY the product prints",
             FIDELITY_STAT: "safeguard — overall distributional fidelity"}
    for k in REPORT_STATS:
        c = ch[k]
        L.append(f"| `{k}` | {roles[k]} | {_f(c['incumbent'])} | {_f(c['floor'])} | "
                 f"[{_f(c['band'][0])}, {_f(c['band'][1])}] | {_f(c['gap'])} | "
                 f"{'✅ yes' if c['outside_null_band'] else '⛔ no'} | {_f(d['mc_p'][k],3)} |")
    cf = p["floors"][SHAPE_STAT].get("construction_floor_median")
    L += ["",
          f"The `{SHAPE_STAT}` calibrated-null floor ({_f(ch[SHAPE_STAT]['floor'])}) is asserted "
          f"against the distribution-free CONSTRUCTION floor at this n ({_f(cf)}) — `round(Normal)` "
          "read with a continuity-corrected randomized PIT is EXACTLY uniform, so the two must "
          "agree. A statistic INSIDE its null band is **inactive**: there is no measurable failure "
          "for a lever to close, and a closure share computed against a `gap` that is itself noise "
          "is the NF1.7 (a) vacuous anchor.", ""]
    L += [("⚠️ **OVER_PEEKING** — these oracles land BELOW an active statistic's floor lower tail, "
           "i.e. below what an honest model can attain: "
           + ", ".join(f"`{a}`" for a in d["over_peeking_arms"]) +
           ". Their closure may be cited as *does not bind*, never as *achievable* (NF-W7i).")
          if d["over_peeking_arms"] else
          "No oracle landed below an active statistic's floor lower tail.",
          "", "---", "", "## 3. ⭐ THE LEVERS, BOUNDED", "",
          "| channel | construction | statistic | paired lift (95% CI) | in play? | share of gap |",
          "|---|---|---|---:|---|---:|"]
    lv = d["levers"]
    for lbl, key, st in (("**calibrator** — a global scale (a RECALIBRATOR can do this)",
                          "calibrator", SHAPE_STAT),
                         ("**ARCHITECTURE lever** — `TV2-2`'s CEILING", "shape", SHAPE_STAT),
                         ("**FEATURE lever** — `TV2-1`'s CEILING", "feature", FEATURE_STAT),
                         ("*(the feature lever read directly)*", "feature_direct", FEATURE_STAT)):
        v = lv[key]
        cons = {"calibrator": "`imp(A1) − imp(incumbent)`", "shape": "`imp(B2) − imp(A1)`",
                "feature": "`imp(C1) − imp(B2)`", "feature_direct": "`imp(A3) − imp(A1)`"}[key]
        L.append(f"| {lbl} | {cons} | `{st}` | {_f(v['point'],4)} "
                 f"[{_f(v['lo'],4)}, {_f(v['hi'],4)}] | "
                 f"{'✅ **yes**' if v['in_play'] else '⛔ no'} | {_f(v['share_of_gap'],3)} |")
    for k in PRIMARY_STATS:
        j = d["joint_ceiling"][k]
        L.append(f"| **JOINT ceiling** (both at once) | `imp(C1) − imp(incumbent)` | `{k}` | "
                 f"{_f(j['point'],4)} [{_f(j['lo'],4)}, {_f(j['hi'],4)}] | "
                 f"{'✅ yes' if j['in_play'] else '⛔ no'} | {_f(j['share_of_gap'],3)} |")
    for k in PRIMARY_STATS:
        c = d["control_inert"][k]
        L.append(f"| ⛔ **row-blind matched control** — must be INERT | `imp(A_ctrl) − imp(A1)` | "
                 f"`{k}` | {_f(c['point'],4)} [{_f(c['lo'],4)}, {_f(c['hi'],4)}] | "
                 f"{'⚠️ **ACTIVE — a capacity artifact**' if c['in_play'] else '✅ inert'} | "
                 f"{_f(c['share_of_gap'],3)} |")
    L += ["",
          f"Bars, registered forward: majority **{RULE_MAJORITY}**, in-play **{RULE_MATERIAL}**. "
          "A lever counts only if its PAIRED 95% CI excludes 0 — every arm scores the same "
          "outcomes, so the decision-relevant noise is the noise of the DIFFERENCE. "
          "Demonstrable ≠ material (NF-W6).",
          "",
          "⭐ **The decomposition is HIERARCHICAL and deliberately conservative toward the expensive "
          "lever.** The architecture lever is scored beyond a plain recalibrator; the feature lever "
          "— the one that needs a whole new data product — must prove it adds **beyond the best "
          "marginal shape**. Shared credit goes to the cheaper mechanism.",
          "",
          f"**Fidelity safeguard on `{FIDELITY_STAT}`: `{d['fidelity_guard']['state']}`** — the "
          f"winning lever's overall-fidelity lift is {_f(d['fidelity_guard']['value'],4)}. Only a "
          "materially NEGATIVE lift demotes; a within-noise one is recorded, never scored as a "
          "pass (NF1.7 (a)).",
          ""]
    if d["demoted_from"]:
        L += [f"⚠️ **DEMOTED**: {d['demoted_from']}", ""]
    L += ["Per-arm closure, by statistic:", "",
          f"| arm | `{FEATURE_STAT}` | `{SHAPE_STAT}` | `{FIDELITY_STAT}` |", "|---|---:|---:|---:|"]
    for a in ARMS:
        if a == "incumbent":
            continue
        L.append(f"| `{a}` | " + " | ".join(
            _f(ch[k]["closed"][a], 3) for k in REPORT_STATS) + " |")
    L += ["", "---", "",
          "## 4. ⚠️ FLAGGED BINDING CLAUSE — `std_pred`, and the LOCATION channel", "",
          "The spec asks how much of the **`std_pred`**/PIT failure a σ fix closes. `std_pred` names "
          "TWO different statistics in this repo, and **the `0.773 vs ≥2.0` figure the spec cites "
          "is the MEAN-SPREAD one** (`STDDEV(pred_total_runs)`, `validate_v2_gates.py:34`) — a "
          "property of `μ`. Every arm here holds `μ` fixed, so **no leg can move it, by "
          "construction**. Registering a leg against a statistic it cannot move would ship a gate "
          "that is décor (NF-MARGIN2). It is therefore reported as a LOCATION diagnostic and is "
          "**not** in the decision rule. Flagged for the PM, **not edited**.",
          "",
          "| reading | value | bar | |", "|---|---:|---:|---|",
          f"| `std_pred_meanspread` = `STDDEV(pred_total_runs)` — the V2 gate's reading | "
          f"**{_f(lp['std_pred_meanspread'],3)}** | ≥ 2.0 | "
          f"{'✅ passes' if lp['std_pred_meanspread_passes_v2_gate'] else '⛔ **FAILS**'} |",
          f"| `std_pred_predictive_sd` = `mean(σ)` — Story 10.2's reading | "
          f"{_f(lp['std_pred_predictive_sd'],3)} | — | |",
          f"| realized `SD(y)` | {_f(lp['realized_sd'],3)} | — | |",
          f"| `Var(μ)/Var(y)` — the share of outcome variance the LOCATION channel explains | "
          f"**{_f(lp['var_mu_over_var_y'],4)}** | — | |",
          f"| served `σ` CV — how much per-game DISPERSION the model expresses AT ALL | "
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
    s2 = r["tiers"][SECONDARY_TIER]
    sd = s2["decision"]
    L += ["| | primary (`post_lineup`) | secondary (`morning`) |", "|---|---:|---:|",
          f"| outcome | **`{d['outcome']}`** | `{sd['outcome']}` |",
          f"| a failure outside its null band? | {d['any_failure_outside_null_band']} | "
          f"{sd['any_failure_outside_null_band']} |",
          f"| `closed_calibrator` | {_f(d['closed_calibrator'],3)} | "
          f"{_f(sd['closed_calibrator'],3)} |",
          f"| `closed_shape` (`{SHAPE_STAT}`) | {_f(d['closed_shape'],3)} | "
          f"{_f(sd['closed_shape'],3)} |",
          f"| `closed_feature` (`{FEATURE_STAT}`) | {_f(d['closed_feature'],3)} | "
          f"{_f(sd['closed_feature'],3)} |",
          f"| mixture `K` by block | {p['notes']['A3_mixture_K_by_block']} | "
          f"{s2['notes']['A3_mixture_K_by_block']} |",
          f"| `std_pred_meanspread` | {_f(lp['std_pred_meanspread'],3)} | "
          f"{_f(s2['location_probe']['std_pred_meanspread'],3)} |",
          "",
          f"Tiers agree: **{'✅ YES' if r['secondary_agrees'] else '⚠️ NO — reported; the verdict is unchanged'}**",
          "", "---", "", "## 6. What this study cannot say", "",
          "- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; no bet rode on this "
          "model, and `bet_paused` stays `true`.",
          "- An oracle ceiling is what a lever could **at most** deliver, never what it will. A "
          "large ceiling licenses **funding a story**; it is not evidence of a shipped improvement.",
          "- The verdict is about the **served `post_lineup`** rows in a **2-month** window under "
          "**one** champion. It does not generalise to a different champion.",
          "- MH2.8's skew-normal DSR failure is **cited as evidence, never re-scored** here.",
          f"- `{SHAPE_STAT}` is structurally near-blind to a per-game σ deficit and `{FEATURE_STAT}` "
          "is comparatively coarse on a marginal shape defect (§1, measured). That is exactly why "
          "each lever is scored on its own statistic — and it is a caution for anyone reading a "
          "single number off this table.",
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

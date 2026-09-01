"""MLB-TV2-2 — a MIXTURE-DENSITY head for the served `total_runs` predictive SHAPE.

Pre-registration: `ablation_results/mlb_tv2_2_prereg.md`, committed BEFORE any statistic
involving a realized outcome was computed on this population. Every constant in the `REGISTERED`
block below is the code twin of that document, and `test_mlb_tv2_2_mixture_head.py` pins the two
together.

`best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves** · DEPLOY-HELD.
This is a calibration/honesty study: no edge, win-rate, ROI or CLV claim, and no gate reads a price.

WHAT THIS IS
------------
TV2-0 measured, on SERVED rows, that the served totals predictive is a symmetric Normal against a
right-skewed target, and that the MARGINAL-SHAPE oracle closes 100.3% of the printed `P(over)`
error while ALSO improving CRPS and `pit_ks` — with the FEATURE lever INACTIVE (K=1 on 5/5 blocks).
This module builds the fix that ceiling licensed: a K-component Gaussian mixture on the
standardized residual, fitted OUT OF BLOCK, with `mu` held EXACTLY at the served value.

⛔ THE TRAP THIS MODULE EXISTS TO NOT FALL INTO
-----------------------------------------------
A K-component mixture NESTS K=1 exactly as MH2.8's skew-normal nested its Normal foil — and
MH2.8's fitter reported "no skew, converged successfully" on obviously skewed data because the
likelihood is FLAT at the collapse point. TV2-0 reproduced it on THIS population: its skew-normal
arm collapsed on 5 of 5 blocks while the realized `z` skew was 0.749. So:

    * components are initialized at DISTINCT out-of-block quantiles, never a common point (§6.1)
    * a COLLAPSED arm's margin is a TIE that REFUSES TO COUNT (§6.2)
    * the fitter must FIND a planted skew, as a DETECTION RATE over replicates (§6.3)

⭐ SHARED INSTRUMENTS ARE IMPORTED FROM TV2-0, NOT RE-IMPLEMENTED. `Arm`, the randomized PIT, the
   CRPS grid, the paired bootstrap, `date_blocks`, `arm_stats` and the calibrated null all have ONE
   owner (E9.61: two renderers of one rule are two rule sets). TV2-0's module is FROZEN and is
   never edited here — editing it would re-cut a recorded study (E2.1-r).

RUN
---
    uv run python betting_ml/scripts/mlb_tv2_2_mixture_head.py --replication  # node 2 (the STOP gate)
    uv run python betting_ml/scripts/mlb_tv2_2_mixture_head.py --controls     # the vacuity floor
    uv run python betting_ml/scripts/mlb_tv2_2_mixture_head.py                # the decisive run
    uv run python betting_ml/scripts/mlb_tv2_2_mixture_head.py --fixture      # the 1e-9 pin
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

# ⭐ ONE OWNER for every shared instrument. TV2-0's module is frozen; nothing here edits it.
from betting_ml.scripts.mlb_tv2_0_ceiling_diagnosis import (  # noqa: E402
    Arm, EmpiricalLaw, NormalLaw, arm_rows, arm_stats, bootstrap_block, calibrated_null,
    crps_grid, crps_normal_closed, date_blocks, floor_of, mc_pvalue, paired_lift_ci,
    randomized_pit, stats_from_rows, _levels,
)
from betting_ml.utils.coverage_power_floor import power_floor  # noqa: E402

# ══════════════════════════════════════════════════════════════════════════════════════════════
# REGISTERED — the code twin of `ablation_results/mlb_tv2_2_prereg.md`. Frozen before scoring.
# ══════════════════════════════════════════════════════════════════════════════════════════════

STORY = "MLB-TV2-2"
SEED = 42
BEST_ALPHA = 0

#: §2/§3 — population. The champion DEFINES it (MH2.10), not the calendar.
ERA_MODEL_VERSIONS = ("v6", "pre_lineup_v6")
CHAMPION_STAMPS = ("v6", "pre_lineup_v6")
CHAMPION_FIT_DATE = "2026-06-23"
PRIMARY_TIER = "post_lineup"
SECONDARY_TIER = "morning"
FULL_ERA_END = "2026-08-30"          # last served date with realized finals at census
TV2_0_WINDOW_END = "2026-08-23"      # TV2-0's read ends here; beyond it is the FRESH slice
#: §14 (AMENDMENT 3) — N_BLOCKS is a DESIGN quantity chosen so EVERY registered gate is REACHABLE,
#: by a rule stated forward: the SMALLEST n at which the fold-SIGN floor `2^-n` is <= HALF the BH
#: cutoff AND the fold clause's false-fire rate is <= 0.20. Measured: at n=5 the sign floor is
#: 0.03125 against a BH cutoff of 0.0125, so C8 was STRUCTURALLY UNPASSABLE — no effect of any size
#: could clear it (E7.14 verbatim; `cv_power.folds_for_sign_certifiability(0.0125) = 7`).
#: Derived from `n` and the GATE SET alone — a design quantity known before any result (NF1.8).
N_BLOCKS = 8

#: ⭐ §2.1 — served-ness is established by INSERTION LAG, not by `is_backfill`.
MAX_SERVED_MEDIAN_LAG_DAYS = 3       # a served row is written on or about its own game date
EXCLUDED_TOTALS_STAMPS = ("mh2_1",)  # the rolled-back MH2.1 promotion (PR #514) — 15 rows

#: §5.1 — THE FIELD, declared coherent FORWARD on ONE mechanism axis (K + parameterization).
TRIAL_ARMS = ("mix2_loc", "mix2_full", "mix3_full", "mixK_bic")
REFERENCE_ARM = "incumbent"
FOIL_ARM = "foil_k1"
DEGENERATE_ARMS = ("degen_sharp", "degen_wide")
CONTROL_ARMS = ("ctrl_permuted", "ctrl_symmetrized")
DECLARED_FIELD_SIZE = len(TRIAL_ARMS)                       # -> classify_null
N_TRIALS_ARMS = (REFERENCE_ARM, FOIL_ARM) + TRIAL_ARMS + DEGENERATE_ARMS   # multiplicity, in full
V_ARMS = TRIAL_ARMS                                          # §5.3 — reference/foil/degenerates ∉ V
DEGENERATES_EXCLUDED_FROM_V = True                           # DSR-CONV, declared forward
DEGEN_SHARP_FACTOR, DEGEN_WIDE_FACTOR = 0.25, 3.0
BIC_K_GRID = (1, 2, 3)

#: §6.1 — staggered / asymmetric initialization. ⛔ No component starts at a common point.
INIT_SCALE_FACTORS = (0.7, 1.0, 1.4)
EM_ITERS, EM_TOL, MIN_COMPONENT_SCALE = 500, 1e-10, 1e-3

#: §6.2 — the collapse detector. A COLLAPSED arm's margin is a TIE and refuses to count.
COLLAPSE_SUPNORM = 1e-3
COLLAPSE_MIN_WEIGHT = 0.02
COLLAPSE_LOC_TOL = 0.02
COLLAPSE_SCALE_RATIO = 1.02

#: §6.3 / §7.6 — controls. A DETECTION RATE over replicates, never a single draw.
CONTROL_SKEW_ALPHA = 4.0
N_CONTROL_REPS = 20
POSITIVE_CONTROL_BAR = 0.80          # fitter FINDS a planted skew, with the planted sign
NEGATIVE_CONTROL_BAR = 0.05          # clean data must not produce a SHIPPABLE margin
GROSS_DEFECT_DETECTION_BAR = 0.80

#: §7 — statistics
PRIMARY_STAT = "p_over_gap_abs"      # the ASYMMETRY the product prints
SCORE_STAT = "crps"                  # CONSTRAINT (must not degrade), never the criterion
FIDELITY_STAT = "pit_ks"
COVERAGE_STAT, COVERAGE_NOMINAL, COVERAGE_FALSE_REJECT = "cov80", 0.80, 0.05
VARIANCE_STAT = "var_z_pooled"       # ⭐ SHAPE-MATCHED null ONLY (MH2.10)
BOOT_STATS = (PRIMARY_STAT, SCORE_STAT, FIDELITY_STAT, "p_over_stated", "p_over_gap", "pit_mdd")
N_BOOT = 400
N_NULL = 2000
NULL_BAND = 0.95

#: §8 — the ship rule
MATERIAL_SHARE = 0.20                # C2: the arm must close >= this share of the incumbent's gap
PBO_GATE, DSR_GATE, BH_ALPHA = 0.20, 0.95, 0.05
PBO_APPLICATION = "field"            # PM convention 2026-08-28 — never carried per-arm
BH_FAMILY = "primary-statistic tests across the 4 declared TRIAL arms"
SHIP_CLAUSES = ("C0_replication", "C1_not_collapsed", "C2_asymmetry", "C3_score_not_degraded",
                "C4_fidelity", "C5_coverage_floor", "C6_fold_consistency", "C7_deflation",
                "C8_multiplicity", "C9_mechanism_attribution", "C10_own_form_oracle_floor")

#: §9 — the std_pred disambiguation. ⛔ NEITHER is read by any gate.
STD_PRED_MEANSPREAD_SOURCE = "betting_ml/scripts/validate_v2_gates.py:34"
STD_PRED_PREDICTIVE_SD_SOURCE = "betting_ml/scripts/train_totals.py:121"
DISPERSION_GATE_STAT = VARIANCE_STAT

#: §10 — SCOPE. DISCRIMINATION is ARM-INVARIANT by construction; no gate reads it.
DISCRIMINATION_STATS = ("std_pred_meanspread", "var_mu_over_var_y")
DISCRIMINATION_NULL_STATE = "INACTIVE (structural)"

_REPORT_MD = PROJECT_ROOT / "ablation_results" / "mlb_tv2_2_mixture_head.md"
_REPORT_JSON = PROJECT_ROOT / "ablation_results" / "mlb_tv2_2_mixture_head.json"
_REPLICATION_JSON = PROJECT_ROOT / "ablation_results" / "mlb_tv2_2_replication.json"
_CONTROLS_JSON = PROJECT_ROOT / "ablation_results" / "mlb_tv2_2_controls.json"
_FIXTURE = PROJECT_ROOT / "betting_ml" / "tests" / "fixtures" / "mlb_tv2_2_fixture.json"
_CACHE = PROJECT_ROOT / "betting_ml" / "data" / "cache" / "mlb_tv2_2_served.parquet"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔ MARKET-BLIND — the SQL reads no odds column. Pinned by a guard test.
# ⭐ SERVED-NESS IS THE INSERTION LAG, NOT THE FLAG (prereg §2.1): ~40,000 v0/v1/v2 rows carry
#    `is_backfill = FALSE` while sitting a MEDIAN 981-1009 DAYS after their own game date.
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
        inserted_at,
        date_diff('day', game_date::date, inserted_at::date) AS insert_lag_days
    FROM daily_model_predictions
    WHERE model_version IN {ERA_MODEL_VERSIONS}
      AND prediction_type IN ('{PRIMARY_TIER}', '{SECONDARY_TIER}')
      AND COALESCE(is_backfill, FALSE) = FALSE
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, prediction_type ORDER BY inserted_at DESC
    ) = 1
)
SELECT
    s.game_pk, s.game_date, s.tier, s.model_version, s.totals_model_version,
    s.mu, s.sigma, s.insert_lag_days,
    (r.home_final_score + r.away_final_score)::DOUBLE AS y_total
FROM served s
JOIN mart_game_results r
  ON r.game_pk = s.game_pk
 AND r.game_type = 'R'
 AND r.home_final_score IS NOT NULL
WHERE s.mu IS NOT NULL AND s.sigma IS NOT NULL AND s.sigma > 0
  AND s.game_date::date >= DATE '{CHAMPION_FIT_DATE}'
  AND s.game_date::date <= DATE '{FULL_ERA_END}'
  AND (s.totals_model_version IS NULL OR s.totals_model_version IN {CHAMPION_STAMPS})
  AND (s.totals_model_version IS NULL OR s.totals_model_version NOT IN {EXCLUDED_TOTALS_STAMPS})
ORDER BY s.game_date, s.game_pk, s.tier
"""


def pull(cache: Path | None = _CACHE):
    """The SERVED rows joined to realized finals. Snowflake-free, market-blind.

    ⭐ Asserts served-ness by the INSERTION LAG (prereg §2.1). `is_backfill = FALSE` does not
    establish it: the v0/v1/v2 eras carry that flag with a ~2.7-YEAR median lag. TV2-0's pull was
    safe only by ACCIDENT of its champion filter — here the property is checked, not assumed.
    """
    import pandas as pd
    if cache is not None and cache.exists():
        df = pd.read_parquet(cache)
    else:
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
    lag = float(df["insert_lag_days"].median())
    if lag > MAX_SERVED_MEDIAN_LAG_DAYS:
        raise ValueError(
            f"population is NOT served: median insertion lag {lag:.0f}d > "
            f"{MAX_SERVED_MEDIAN_LAG_DAYS}d. A backtest cannot see a serving-path defect (MH2.6)."
        )
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MIXTURE HEAD — and the TIE-WITH-FOIL guard that keeps it honest (prereg §6)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _staggered_init(z, K, *, mirror=False):
    """§6.1 — components at DISTINCT out-of-block quantiles, UNEQUAL weights, staggered scales.

    ⛔ No component starts at a common point. MH2.8's skew-normal likelihood is FLAT at its
    symmetric collapse point and a K-mixture is unidentified at the same place, so a fit begun
    there reports 'converged, no shape' on obviously skewed data — measured on THIS population by
    TV2-0 (5 of 5 blocks collapsed at a realized `z` skew of 0.749).
    """
    z = np.asarray(z, float)
    qs = (np.arange(K) + 0.5) / K
    m = np.quantile(z, 1.0 - qs if mirror else qs)
    w = np.arange(K, 0, -1) + 1.0
    w = w[::-1] if mirror else w
    s = np.asarray(INIT_SCALE_FACTORS[:K], float) * float(np.std(z, ddof=1))
    return w / w.sum(), m.astype(float), np.maximum(s, MIN_COMPONENT_SCALE)


def _em(z, w, m, s, *, common_scale):
    """EM for a K-component Gaussian mixture. `common_scale` ties every component's scale."""
    z = np.asarray(z, float)[:, None]
    prev = -np.inf
    for _ in range(EM_ITERS):
        # E-step, in log space so a far-away component cannot underflow to an all-zero row
        lp = (-0.5 * ((z - m) / s) ** 2 - np.log(s) - 0.5 * np.log(2 * np.pi) + np.log(w))
        mx = lp.max(axis=1, keepdims=True)
        ll_rows = mx[:, 0] + np.log(np.exp(lp - mx).sum(axis=1))
        r = np.exp(lp - ll_rows[:, None])
        ll = float(ll_rows.mean())
        nk = r.sum(axis=0)
        if not np.all(np.isfinite(nk)) or nk.min() <= 0:
            break
        w = nk / nk.sum()
        m = (r * z).sum(axis=0) / nk
        if common_scale:
            var = float((r * (z - m) ** 2).sum() / nk.sum())
            s = np.full_like(s, max(np.sqrt(var), MIN_COMPONENT_SCALE))
        else:
            s = np.maximum(np.sqrt((r * (z - m) ** 2).sum(axis=0) / nk), MIN_COMPONENT_SCALE)
        if abs(ll - prev) < EM_TOL:
            break
        prev = ll
    return w, m, s, prev


class MixtureLaw:
    """A K-component Gaussian mixture fitted to the OUT-OF-BLOCK standardized residual `z`.

    ⚠️ NESTS its own K=1 Normal foil. `collapsed` is the TIE-WITH-FOIL detector (§6.2): a
    collapsed arm's margin REFUSES TO COUNT — it is a TIE, never a shape finding.
    """

    def __init__(self, z, K, *, common_scale=False, name=None):
        z = np.asarray(z, float)
        self.K, self.common_scale = int(K), bool(common_scale)
        self.name = name or f"mix{K}{'_loc' if common_scale else '_full'}"
        best = None
        for mirror in (False, True):                        # §6.1 — both starts; keep the better
            w0, m0, s0 = _staggered_init(z, K, mirror=mirror)
            cand = _em(z, w0, m0, s0, common_scale=common_scale)
            if best is None or cand[3] > best[3]:
                best = cand
        self.w, self.m, self.s, self.loglik = best
        self.n_fit = int(len(z))
        self._k1 = (float(np.mean(z)), float(np.std(z, ddof=1)))   # the nested foil, same rows
        self.collapsed, self.collapse_reasons = self._detect_collapse()

    # ── the law ───────────────────────────────────────────────────────────────────────────────
    def cdf(self, t):
        from scipy.stats import norm
        t = np.asarray(t, float)
        return np.clip((self.w * norm.cdf((t[..., None] - self.m) / self.s)).sum(-1), 1e-12, 1 - 1e-12)

    def ppf(self, p):
        """Vectorised bisection on a monotone CDF — exact to 1e-12 in `t`, so it is reproducible."""
        p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
        span = float(self.s.max()) * 40.0
        lo = np.full(p.shape, float(self.m.min()) - span)
        hi = np.full(p.shape, float(self.m.max()) + span)
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            go = self.cdf(mid) < p
            lo = np.where(go, mid, lo)
            hi = np.where(go, hi, mid)
        return 0.5 * (lo + hi)

    # ── §6.2 the collapse detector ────────────────────────────────────────────────────────────
    def _detect_collapse(self):
        from scipy.stats import norm
        why = []
        if float(self.w.min()) < COLLAPSE_MIN_WEIGHT:
            why.append(f"weight {self.w.min():.4f} < {COLLAPSE_MIN_WEIGHT}")
        if (float(self.m.max() - self.m.min()) < COLLAPSE_LOC_TOL
                and float(self.s.max() / max(self.s.min(), 1e-12)) < COLLAPSE_SCALE_RATIO):
            why.append("components coincide in location AND scale")
        mu1, sd1 = self._k1
        grid = np.linspace(mu1 - 6 * sd1, mu1 + 6 * sd1, 2001)
        sup = float(np.max(np.abs(self.cdf(grid) - norm.cdf((grid - mu1) / sd1))))
        self.supnorm_vs_k1 = sup
        if sup < COLLAPSE_SUPNORM:
            why.append(f"sup-norm vs K=1 foil {sup:.2e} < {COLLAPSE_SUPNORM}")
        return bool(why), why

    @property
    def skewness(self):
        """Closed-form standardized third central moment — the fitted ASYMMETRY (§6.3 sign check)."""
        mean = float((self.w * self.m).sum())
        d = self.m - mean
        var = float((self.w * (self.s ** 2 + d ** 2)).sum())
        third = float((self.w * (d ** 3 + 3.0 * d * self.s ** 2)).sum())
        return third / max(var, 1e-12) ** 1.5


def _bic(law, z):
    from scipy.stats import norm
    z = np.asarray(z, float)
    dens = (law.w * norm.pdf((z[:, None] - law.m) / law.s) / law.s).sum(-1)
    ll = float(np.log(np.maximum(dens, 1e-300)).sum())
    p = (law.K - 1) + law.K + (1 if law.common_scale else law.K)
    return p * np.log(len(z)) - 2 * ll


def fit_mix(z, K, *, common_scale=False):
    return MixtureLaw(z, K, common_scale=common_scale)


def fit_mix_bic(z, *, grid=BIC_K_GRID):
    """K chosen by OUT-OF-BLOCK BIC — the `K` half of the mechanism axis, as a selection rule."""
    cands = [fit_mix(z, k, common_scale=False) for k in grid]
    law = min(cands, key=lambda L: _bic(L, z))
    law.name, law.bic_k = "mixK_bic", law.K
    return law


class ScaledNormalLaw:
    """A Normal fitted to out-of-block `z` (`foil_k1`), optionally rescaled (the degenerates)."""

    def __init__(self, z, factor=1.0, name="foil_k1"):
        z = np.asarray(z, float)
        self.loc, self.scale = float(np.mean(z)), float(np.std(z, ddof=1)) * float(factor)
        self.name, self.collapsed, self.collapse_reasons = name, False, []

    def cdf(self, t):
        from scipy.stats import norm
        return norm.cdf((np.asarray(t, float) - self.loc) / self.scale)

    def ppf(self, p):
        from scipy.stats import norm
        return self.loc + self.scale * norm.ppf(np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE BATTERY — every law fitted OUT OF BLOCK; `mu` held EXACTLY at the served value (§4, §10)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _oob(z, block, b):
    return np.asarray(z, float)[np.asarray(block, int) != b]


def _symmetrize(z):
    """§5.4 — destroy the ASYMMETRY, keep scale and kurtosis machinery (the mechanism foil)."""
    z = np.asarray(z, float)
    return np.concatenate([z, 2.0 * float(np.mean(z)) - z])


_FORMS = {
    "mix2_loc": lambda z: fit_mix(z, 2, common_scale=True),
    "mix2_full": lambda z: fit_mix(z, 2, common_scale=False),
    "mix3_full": lambda z: fit_mix(z, 3, common_scale=False),
    "mixK_bic": fit_mix_bic,
}


def build_arms(y, mu, sigma, block, *, seed=SEED):
    """Every arm. Laws are fitted OUT OF BLOCK except the per-form oracles, which PEEK by design
    and never ship (§5.4). ⛔ `mu` is the served value for every arm without exception."""
    y, mu, sigma = (np.asarray(v, float) for v in (y, mu, sigma))
    block = np.asarray(block, int)
    z = (y - mu) / sigma
    nb = int(block.max()) + 1
    rng = np.random.default_rng(seed)
    laws: dict[str, list] = {a: [] for a in
                             (REFERENCE_ARM, FOIL_ARM) + TRIAL_ARMS + DEGENERATE_ARMS + CONTROL_ARMS}
    oracle_laws: dict[str, list] = {}
    for form in TRIAL_ARMS:
        oracle_laws[f"oracle_{form}"] = []
        oracle_laws[f"oraclectrl_{form}"] = []
    oracle_laws["oracle_empirical"] = []

    for b in range(nb):
        zo = _oob(z, block, b)
        zi = np.asarray(z, float)[block == b]
        laws[REFERENCE_ARM].append(NormalLaw())
        laws[FOIL_ARM].append(ScaledNormalLaw(zo, 1.0, name=FOIL_ARM))
        for form, factory in _FORMS.items():
            laws[form].append(factory(zo))
        laws["degen_sharp"].append(ScaledNormalLaw(zo, DEGEN_SHARP_FACTOR, name="degen_sharp"))
        laws["degen_wide"].append(ScaledNormalLaw(zo, DEGEN_WIDE_FACTOR, name="degen_wide"))
        # ⛔ registered as an EXPECTED EXACT TIE: a permutation cannot move a MARGINAL law (§5.4)
        laws["ctrl_permuted"].append(_FORMS["mix2_full"](rng.permutation(zo)))
        laws["ctrl_symmetrized"].append(_FORMS["mix2_full"](_symmetrize(zo)))
        # per-FORM oracles (NF-D16 g‴: the forms NEST, so one ceiling per form) + matched-n control
        sub = rng.choice(len(zo), size=min(len(zi), len(zo)), replace=False)
        for form, factory in _FORMS.items():
            oracle_laws[f"oracle_{form}"].append(factory(zi))          # PEEKS at its own block
            oracle_laws[f"oraclectrl_{form}"].append(factory(zo[sub]))  # honest, at the peek's n
        oracle_laws["oracle_empirical"].append(EmpiricalLaw(zo))

    arms = {n: Arm(n, mu, sigma, L, block) for n, L in {**laws, **oracle_laws}.items()}
    collapse = {n: [bool(getattr(L, "collapsed", False)) for L in laws.get(n, [])]
                for n in TRIAL_ARMS + CONTROL_ARMS}
    detail = {n: [{"K": int(getattr(L, "K", 1)), "w": [round(float(x), 4) for x in getattr(L, "w", [1.0])],
                   "m": [round(float(x), 4) for x in np.atleast_1d(getattr(L, "m", getattr(L, "loc", 0.0)))],
                   "s": [round(float(x), 4) for x in np.atleast_1d(getattr(L, "s", getattr(L, "scale", 1.0)))],
                   "skew": round(float(getattr(L, "skewness", 0.0)), 4),
                   "supnorm_vs_k1": round(float(getattr(L, "supnorm_vs_k1", 0.0)), 5),
                   "collapsed": bool(getattr(L, "collapsed", False)),
                   "collapse_reasons": list(getattr(L, "collapse_reasons", []))}
                  for L in laws.get(n, [])] for n in TRIAL_ARMS + CONTROL_ARMS}
    return arms, collapse, detail


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ §7.2 — THE SHAPE-MATCHED NULL for VARIANCE statistics (MH2.10). Variance statistics ONLY.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def shape_matched_null(y, mu, sigma, block, *, reps=N_NULL, seed=SEED):
    """Resample the OBSERVED standardized residuals, rescaled to variance EXACTLY 1.

    `Var(s²)` depends on the FOURTH moment, so a Normal-DRAWN null is systematically too narrow for
    a variance statistic on a skewed, leptokurtic target — and a SHAPE defect then mechanically
    MANUFACTURES an apparent SCALE flag (MH2.10, which moved a headline p 0.052 → 0.100).

    ⛔ Variance statistics ONLY. On a PIT statistic this would build the tested defect INTO the null.
    """
    y, mu, sigma = (np.asarray(v, float) for v in (y, mu, sigma))
    z = (y - mu) / sigma
    z0 = (z - z.mean()) / z.std(ddof=1)          # shape kept, variance set to EXACTLY 1
    rng = np.random.default_rng(seed)
    n = len(z0)
    inc = Arm(REFERENCE_ARM, mu, sigma, [NormalLaw() for _ in range(int(block.max()) + 1)], block)
    out = np.empty(reps)
    for r in range(reps):
        yy = mu + sigma * z0[rng.integers(0, n, size=n)]
        out[r] = arm_stats(np.round(yy), inc, rng)[VARIANCE_STAT]
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NODE 2 — ⭐ THE REPLICATION LEG (prereg §3). The STOP gate. Nothing below it runs on a failure.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def replication(df, *, tier=PRIMARY_TIER, reps=N_NULL, seed=SEED):
    """Does the SHAPE GAP replicate on the widest served window this champion has produced?

    Three reads (§3.1). Only FULL-ERA BINDS. The FRESH slice is UNDERPOWERED BY DESIGN and cannot
    trigger STOP — registered in §3.3 BEFORE it was run, because a non-significant 93-row read is
    the EXPECTED outcome under a true effect and calling it a refutation is a design error.
    """
    from scipy.stats import norm as _norm
    d = df[df["tier"] == tier]
    out = {"tier": tier, "reads": {}}
    slices = {
        "FULL_ERA": d,
        "TV2_0_WINDOW": d[d["game_date"].astype(str) <= TV2_0_WINDOW_END],
        "FRESH": d[d["game_date"].astype(str) > TV2_0_WINDOW_END],
    }
    for name, s in slices.items():
        y, mu, sigma = (s[c].to_numpy(float) for c in ("y_total", "mu", "sigma"))
        n = len(y)
        block = date_blocks(s["game_date"].to_numpy(), k=min(N_BLOCKS, max(1, n // 40)))
        inc = Arm(REFERENCE_ARM, mu, sigma, [NormalLaw() for _ in range(int(block.max()) + 1)], block)
        st = arm_stats(y, inc, np.random.default_rng(seed))
        null = calibrated_null(mu, sigma, block, reps=reps, seed=seed)
        fl = floor_of(null, PRIMARY_STAT, band=NULL_BAND)
        se = float(np.sqrt(0.25 / max(n, 1)))
        z_eff = 0.0726 / se                                     # TV2-0's measured gap, in SE
        out["reads"][name] = {
            "n": n, "d0": str(s["game_date"].min()), "d1": str(s["game_date"].max()),
            "p_over_stated": st["p_over_stated"], "p_over_realized": st["p_over_realized"],
            "p_over_gap": st["p_over_gap"], PRIMARY_STAT: st[PRIMARY_STAT],
            "z_skew": st["z_skew"], "pit_ks": st["pit_ks"], "crps": st["crps"],
            "null_median": fl["median"], "null_lo": fl["lo"], "null_hi": fl["hi"],
            "outside_band": bool(st[PRIMARY_STAT] > fl["hi"] or st[PRIMARY_STAT] < fl["lo"]),
            "sign_matches_tv2_0": bool(st["p_over_gap"] > 0),
            "mc_p": mc_pvalue(null[PRIMARY_STAT], st[PRIMARY_STAT]),
            "se_p_over_gap": se,
            "power_vs_tv2_0_gap": float(_norm.sf(1.96 - z_eff) + _norm.cdf(-1.96 - z_eff)),
            "mde_at_80pct_power": 2.80 * se,
        }
    full = out["reads"]["FULL_ERA"]
    out["binding_read"] = "FULL_ERA"
    out["replicated"] = bool(full["outside_band"] and full["sign_matches_tv2_0"])
    out["fresh_can_trigger_stop"] = False        # §3.3 — registered forward
    out["fresh_note"] = (
        "UNDERPOWERED BY DESIGN: registered in prereg §3.3 before it was run. A non-significant "
        "FRESH read is the EXPECTED outcome under a true effect and is NOT a refutation.")
    out["window_limit_note"] = (
        "The champion era is bounded below by its fit date and above by today, so the widest "
        "served window that EXISTS is +93 rows / +12.3% over TV2-0's. FULL_ERA shares 89% of its "
        "rows with TV2-0's read: it is a LARGER read, not an INDEPENDENT one (prereg §3.2).")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §12 (AMENDMENT 1) — the DEFLATION SERIES. PBO and DSR want DIFFERENT series (NCAAF-P2.1).
# ══════════════════════════════════════════════════════════════════════════════════════════════

N_PBO_BUCKETS = 16          # PBO wants MANY buckets
PBO_N_SPLITS = 16
#: §13 (AMENDMENT 2) — forced by the VACUITY CONTROL, before any real-data scoring.
#: The per-fold series is the per-ROW BRIER score of the PRINTED probability. `|gap|` per block is
#: dominated by the block's realized-rate sampling noise and its ABS KINK breaks the exact
#: cancellation of `over_i`; Brier is PROPER (an arm cannot win by moving the number the wrong way),
#: per-row, and paired on the same `over_i`.
DSR_SERIES = ("per-block improvement in the per-ROW BRIER score of the printed probability, "
              "over foil_k1 (n_obs = N_BLOCKS) — §13 amendment 2")
PBO_SERIES = f"per-date-bucket -p_over_gap_abs over {N_PBO_BUCKETS} contiguous buckets"
PBO_BINDING_READING = "eligible"   # {declared, eligible, two_arm} — `eligible` BINDS


def _date_buckets(dates, k=N_PBO_BUCKETS):
    """K contiguous DATE buckets — the PBO series. A date never straddles two buckets."""
    d = np.asarray(dates, dtype="datetime64[D]")
    order = np.argsort(d, kind="stable")
    out = np.empty(len(order), int)
    edges = np.linspace(0, len(order), k + 1).round().astype(int)
    for b in range(k):
        out[order[edges[b]:edges[b + 1]]] = b
    for day in np.unique(d):
        m = d == day
        vals, cnt = np.unique(out[m], return_counts=True)
        out[m] = vals[np.argmax(cnt)]
    return out


def _per_group_stat(rows, group, key):
    """`key` recomputed within each group — the per-block / per-bucket series."""
    g = np.asarray(group, int)
    return np.array([stats_from_rows(rows, np.flatnonzero(g == b))[key]
                     for b in range(int(g.max()) + 1)], float)


def brier_rows(rows):
    """§13 — the per-ROW PROPER score of the number the product prints: `(stated_i - over_i)²`.

    ⭐ Why not `|p_over_gap|` per block (the original §12 series): `|·|` has a KINK at zero, so the
    EXACT per-row cancellation of `over_i` between two arms breaks in any block whose realized rate
    happens to sit between the two arms' stated values — and at ~170 rows a block's realized rate
    carries an SE of 0.038 against an effect of 0.073. Measured on the committed fixture: the |gap|
    series gave a paired CI SPANNING ZERO ([-0.030, +0.043]) for an arm whose movement CI was
    [+0.0417, +0.0426]. Brier keeps the pairing AND stays PROPER, so an arm that moves the printed
    number the WRONG way is penalised rather than rewarded — which the raw MOVEMENT series is not
    (measured: every arm wins 5/5 folds on movement, including one that overshoots).
    """
    return (np.asarray(rows["stated"], float) - np.asarray(rows["over"], float)) ** 2


def _per_group_brier_lift(rows_foil, rows_arm, group):
    """Per-fold BRIER improvement. ⛔ REPORTED ONLY — not the registered series; see §15."""
    g = np.asarray(group, int)
    bf, ba = brier_rows(rows_foil), brier_rows(rows_arm)
    return np.array([float(bf[g == b].mean() - ba[g == b].mean())
                     for b in range(int(g.max()) + 1)], float)


def fold_series(rows_foil, rows_arm, group):
    """⭐ §15 — THE registered per-fold series: the per-ROW CRPS improvement over `foil_k1`.

    The printed probability is a property of the BLOCK'S LAW, so it is CONSTANT within a block: a
    Brier series therefore carries ~ONE effective observation per fold and cannot support a
    fold-level test (measured: 4/6 vs 6/6 fold-clause detection on a planted gross defect, and 0/6
    on clean data for both). CRPS varies row-to-row and is the proper score of the DENSITY the
    mixture actually changes — which TV2-0 measured the shape oracle improves (2.5301 → 2.5114).
    """
    g = np.asarray(group, int)
    cf = np.asarray(rows_foil["crps"], float)
    ca = np.asarray(rows_arm["crps"], float)
    return np.array([float(cf[g == b].mean() - ca[g == b].mean())
                     for b in range(int(g.max()) + 1)], float)


def deflation(rows_by_arm, block, dates, *, winner):
    """C7. `V` over the TRIAL arms only (§5.3); `n_trials` the FULL field (multiplicity in full)."""
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

    # ── DSR: per-BLOCK lift over the foil. Low-noise, independent observations. ────────────────
    lift = {a: fold_series(rows_by_arm[FOIL_ARM], rows_by_arm[a], block)  # + = arm BETTER
            for a in TRIAL_ARMS}
    sr = {a: float(np.mean(v) / np.std(v, ddof=1)) if np.std(v, ddof=1) > 1e-12 else 0.0
          for a, v in lift.items()}
    v_trials = float(np.var([sr[a] for a in V_ARMS], ddof=1))
    v_with_degen = float(np.var([sr[a] for a in V_ARMS] + [0.0, 0.0], ddof=1))
    d = deflated_sharpe(lift[winner], n_trials=len(N_TRIALS_ARMS),
                        trial_sharpes=[sr[a] for a in V_ARMS])

    # ── PBO: per-DATE-BUCKET, three readings; `eligible` BINDS (§12.2). ────────────────────────
    bucket = _date_buckets(dates)
    def _perf(arms):
        return np.stack([-_per_group_stat(rows_by_arm[a], bucket, PRIMARY_STAT) for a in arms], 1)
    readings = {}
    for name, arms in (("declared", list(N_TRIALS_ARMS)),
                       ("eligible", list(TRIAL_ARMS)),
                       ("two_arm", [winner, FOIL_ARM])):
        r = pbo_cscv(_perf(arms), higher_is_better=True, n_splits=PBO_N_SPLITS, seed=SEED)
        readings[name] = {"pbo": float(r.pbo), "n_configs": len(arms),
                          "n_combos": int(getattr(r, "n_combos", 0))}
    return {
        "dsr_series": DSR_SERIES, "pbo_series": PBO_SERIES,
        "winner": winner, "per_block_lift": [float(x) for x in lift[winner]],
        "trial_sharpes": {a: sr[a] for a in TRIAL_ARMS},
        "var_trials_sr": v_trials, "var_trials_sr_with_degenerates": v_with_degen,
        "v_membership": list(V_ARMS), "degenerates_excluded_from_v": DEGENERATES_EXCLUDED_FROM_V,
        "n_trials": len(N_TRIALS_ARMS), "observed_sr": float(d.observed_sr), "sr0": float(d.sr0),
        "dsr": float(d.dsr), "dsr_pass": bool(d.dsr > DSR_GATE),
        "pbo_readings": readings, "pbo_binding_reading": PBO_BINDING_READING,
        "pbo": readings[PBO_BINDING_READING]["pbo"],
        "pbo_pass": bool(readings[PBO_BINDING_READING]["pbo"] < PBO_GATE),
        "pbo_application": PBO_APPLICATION,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE SHIP RULE (§8) — deterministic, order fixed. Nothing reads a result to choose a branch.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _bh(pvals, alpha=BH_ALPHA):
    """Benjamini-Hochberg over the declared family; returns the cutoff and per-test pass."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    k = np.arange(1, len(p) + 1)
    thr = alpha * k / len(p)
    passed = p[order] <= thr
    cut = float(thr[passed][-1]) if passed.any() else float(thr[0])
    out = np.zeros(len(p), bool)
    out[order] = p[order] <= cut
    return cut, out


def score_arms(y, mu, sigma, dates, *, seed=SEED, reps=N_NULL):
    """One population -> every arm's statistics, the nulls, the deflation and the ship verdict."""
    from scipy.stats import wilcoxon
    y, mu, sigma = (np.asarray(v, float) for v in (y, mu, sigma))
    block = date_blocks(dates, k=N_BLOCKS)
    rng = np.random.default_rng(seed)
    arms, collapse, detail = build_arms(y, mu, sigma, block, seed=seed)

    # ⭐ ONE shared uniform draw across every arm — the pairing (TV2-0). Independent draws inject
    #   noise into the DIFFERENCE that has nothing to do with the arms.
    u = rng.uniform(size=len(y))
    rows = {a: arm_rows(y, arm, u=u) for a, arm in arms.items()}
    stats = {a: arm_stats(y, arm, np.random.default_rng(seed), u=u) for a, arm in arms.items()}
    boot = bootstrap_block(rows, BOOT_STATS, n_boot=N_BOOT, seed=seed)

    # `reps = 0` skips the nulls. They CONTEXTUALISE (§7); no ship clause C1-C10 reads them, so
    # the control replicates (§7.5/§7.6) run without them and stay affordable — and the verdict a
    # control produces is therefore the SAME function the decisive run scores with (PLAT-CVP1).
    floors = {}
    if reps:
        null = calibrated_null(mu, sigma, block, reps=reps, seed=seed)
        floors = {k: floor_of(null, k, band=NULL_BAND)
                  for k in (PRIMARY_STAT, SCORE_STAT, FIDELITY_STAT, COVERAGE_STAT)}
        # ⭐ §7.2 — the VARIANCE statistic gets a SHAPE-MATCHED null, never the Normal-drawn one.
        var_null = shape_matched_null(y, mu, sigma, block, reps=reps, seed=seed)
        floors[VARIANCE_STAT] = floor_of({VARIANCE_STAT: var_null}, VARIANCE_STAT, band=NULL_BAND)
        floors[VARIANCE_STAT]["null_kind"] = "SHAPE-MATCHED (MH2.10)"

    inc_gap = float(stats[REFERENCE_ARM][PRIMARY_STAT])
    cov_floor = power_floor(len(y), nominal=COVERAGE_NOMINAL, target=COVERAGE_FALSE_REJECT)

    # ── per-arm clauses ───────────────────────────────────────────────────────────────────────
    lift = {a: {k: paired_lift_ci(rows[FOIL_ARM], rows[a], k, boot=boot, arm_a=FOIL_ARM, arm_b=a)
                for k in (PRIMARY_STAT, SCORE_STAT, FIDELITY_STAT)} for a in arms}
    # §13 — the MOVEMENT of the printed probability, in which `over_i` cancels EXACTLY (TV2-0's
    # ASYMMETRY CHANNEL), gated on the incumbent's SIGNED gap being materially non-zero.
    inc_signed = paired_lift_ci(rows[REFERENCE_ARM], rows[REFERENCE_ARM], "p_over_gap",
                                boot=boot, arm_a=REFERENCE_ARM, arm_b=REFERENCE_ARM)
    inc_gap_ci = np.quantile(boot[REFERENCE_ARM]["p_over_gap"], [0.025, 0.975])
    asym_precondition = bool(inc_gap_ci[0] > 0)          # the gap the product prints is REAL
    movement = {a: paired_lift_ci(rows[FOIL_ARM], rows[a], "p_over_stated", boot=boot,
                                  arm_a=FOIL_ARM, arm_b=a) for a in TRIAL_ARMS}

    # §15 — C8 corrects C2's OWN claim for multiplicity. The first cut tested a DIFFERENT,
    # far lower-resolution statistic (a per-fold signed-rank) than the claim it was correcting,
    # and at 8 folds its floor 2^-8 left it unable to certify a planted GROSS defect (measured
    # 1/6). A multiplicity correction must be applied to the statistic that carries the claim.
    pvals = []
    for a in TRIAL_ARMS:
        d = boot[FOIL_ARM]["p_over_stated"] - boot[a]["p_over_stated"]   # the MOVEMENT, paired
        pvals.append(float((np.sum(d <= 0) + 1) / (len(d) + 1)))         # one-sided, +1 correction
    bh_cut, bh_pass = _bh(pvals)
    # the per-fold signed-rank is REPORTED beside it, never as the binding gate
    fold_pvals = []
    for a in TRIAL_ARMS:
        try:
            fold_pvals.append(float(wilcoxon(fold_series(rows[FOIL_ARM], rows[a], block),
                                             alternative="greater").pvalue))
        except ValueError:
            fold_pvals.append(1.0)

    fold_clause = _fold_clause()
    verdicts = {}
    for i, a in enumerate(TRIAL_ARMS):
        wins = int(np.sum(fold_series(rows[FOIL_ARM], rows[a], block) > 0))
        # C10: an own-form oracle FLOOR applies only where the anchor pair is ACTIVE (NF-W6d) —
        #      a peek that TIES its matched-n control has nothing to say, and reading that tie as
        #      a refusal would veto a live arm on a check that never fired (NF1.7 (a)).
        # ⭐ §15 — BOTH anchors sit at the PEEK'S n (~106 out-of-block rows), so the comparison is
        # same-FAMILY and same-SAMPLE (NF1.7 (b) / NF1.9 (f)). The check is a METRIC-INVERSION
        # detector: a peek that LOSES to an honest fit at its own n means the metric is inverted.
        # ⛔ The first cut required the FULL-n arm not to beat the peek — but the honest arm trains
        # on ~745 rows against the peek's ~106, so beating it is CAPACITY, not leakage, and NF1.9
        # (f) is explicit that such a win is admissible. That cut would have vetoed a live arm.
        # ⭐ The TIE BAND is ONE SE of the primary statistic at this n — a design quantity from `n`
        #    alone. The first cut used 1e-6 against a statistic whose SE here is 0.017, so the
        #    anchor pair read ACTIVE on pure noise and C10 refused live arms (measured: 22 of 24
        #    peek-minus-control differences sit inside one SE). NF-W6d: an anchor pair that TIES is
        #    INACTIVE, not a refusal — and an inactive anchor is UNINFORMATIVE, never a pass (NF-D20).
        orc = stats[f"oracle_{a}"][PRIMARY_STAT]
        octl = stats[f"oraclectrl_{a}"][PRIMARY_STAT]
        tie_band = float(np.sqrt(0.25 / max(len(y), 1)))
        oracle_active = bool(abs(orc - octl) > tie_band)
        verdicts[a] = {
            "C1_not_collapsed": bool(sum(collapse[a]) <= N_BLOCKS // 2),
            "collapsed_blocks": int(sum(collapse[a])),
            # C2 — TV2-0's ASYMMETRY CHANNEL (§13): the incumbent's signed gap must be REAL, the
            # arm must MOVE the printed probability materially TOWARD it, the move must actually
            # reduce the pooled |gap|, and it must close >= MATERIAL_SHARE of it.
            "C2_asymmetry": bool(asym_precondition and movement[a]["material"]
                                 and movement[a]["point"] > 0
                                 and stats[a][PRIMARY_STAT] < stats[FOIL_ARM][PRIMARY_STAT]
                                 and movement[a]["point"] >= MATERIAL_SHARE * inc_gap),
            "movement_of_printed_prob": movement[a],
            "share_of_incumbent_gap_closed": float(movement[a]["point"] / inc_gap) if inc_gap else 0.0,
            "C3_score_not_degraded": bool(not (lift[a][SCORE_STAT]["material"]
                                               and lift[a][SCORE_STAT]["point"] < 0)),
            "C4_fidelity": bool(not (lift[a][FIDELITY_STAT]["material"]
                                     and lift[a][FIDELITY_STAT]["point"] < 0)),
            "C5_coverage_floor": bool(stats[a][COVERAGE_STAT] >= cov_floor),
            "C6_fold_consistency": bool(wins >= fold_clause.wins_required),
            "C8_multiplicity": bool(bh_pass[i]),
            "C9_mechanism_attribution": None,     # filled below (needs the winner's own magnitude)
            "C10_own_form_oracle_floor": (True if not oracle_active else bool(orc <= octl + 1e-9)),
            "C10_reading": ("INACTIVE — the anchor pair ties, so it cannot refuse (NF-W6d)"
                            if not oracle_active else
                            ("the own-form peek beats an honest fit at its own n — the metric "
                             "behaves" if orc <= octl else
                             "⛔ METRIC INVERSION: the peek LOSES to an honest fit at matched n")),
            "full_n_arm_beats_peek_is_capacity": bool(stats[a][PRIMARY_STAT] < orc),
            "oracle_anchor_active": oracle_active, "oracle_tie_band": tie_band,
            "oracle_own_form": float(orc), "oracle_matched_n_control": float(octl),
            "fold_wins": wins, "fold_wins_required": int(fold_clause.wins_required),
            "p_one_sided": float(pvals[i]),
            "p_fold_signed_rank_reported": float(fold_pvals[i]),
        }
    # C9 — the STATED MECHANISM foil: if a symmetrized fit reproduces the win, it is not skew.
    sym = paired_lift_ci(rows[FOIL_ARM], rows["ctrl_symmetrized"], "p_over_stated", boot=boot,
                         arm_a=FOIL_ARM, arm_b="ctrl_symmetrized")["point"]
    for a in TRIAL_ARMS:
        verdicts[a]["C9_mechanism_attribution"] = bool(
            movement[a]["point"] > 0 and sym < 0.5 * movement[a]["point"])
    return {"block": block, "arms": arms, "rows": rows, "stats": stats, "boot": boot,
            "collapse": collapse, "detail": detail, "lift": lift, "floors": floors,
            "verdicts": verdicts, "bh_cutoff": bh_cut, "coverage_floor": cov_floor,
            "incumbent_gap": inc_gap, "n": len(y),
            "fold_clause": {"wins_required": int(fold_clause.wins_required),
                            "false_fire": float(fold_clause.attained_false_fire)},
            "ctrl_symmetrized_lift": sym,
            "asym_precondition": asym_precondition,
            "incumbent_signed_gap_ci": [float(inc_gap_ci[0]), float(inc_gap_ci[1])],
            "movement": movement,
            "ctrl_permuted_lift": lift["ctrl_permuted"][PRIMARY_STAT]["point"]}


def _fold_clause():
    from betting_ml.utils.cv_power import fold_consistency_clause
    return fold_consistency_clause(n_folds=N_BLOCKS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CONTROLS — §6.3 the fitter FINDS a planted skew · §7.5 the negative control mirrors the SHIP
# RULE's margin · §7.6 the VACUITY FLOOR: the harness must prove it CAN fail.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def plant(mu, sigma, *, skew_alpha, seed):
    """Synthetic `y` on the REAL served `(mu, sigma)` with a KNOWN shape deficit planted.

    `skew_alpha = 0` is the CLEAN payload — outcomes from the incumbent's OWN predictive, i.e. a
    correctly specified model with no shape defect to find. That is the two-sided leg.
    """
    from scipy.stats import skewnorm
    rng = np.random.default_rng(seed)
    n = len(mu)
    if abs(skew_alpha) < 1e-12:
        z = rng.standard_normal(n)
    else:
        z = skewnorm.rvs(skew_alpha, size=n, random_state=rng)
        z = (z - z.mean()) / z.std(ddof=1)
    return np.round(mu + sigma * z)


def ship_verdict(res, defl):
    """The FULL ship rule of §8 — the single function every control and the decisive run share."""
    out = {}
    for a in TRIAL_ARMS:
        v = dict(res["verdicts"][a])
        # §14 — C7 carries DSR ONLY. PBO/CSCV is a FIELD-LEVEL statistic and is ⛔ NEVER carried
        # as a per-arm pass/fail (PM convention 2026-08-28; my own prereg §5.5 said so and the
        # first cut of this line contradicted it). MLB-HV2-1 MEASURED the cost: a planted 6pp
        # effect drove PBO to 0.426 precisely BECAUSE it made the arms near-clones, so the per-arm
        # reading VETOED a real, large effect. The field reading is reported beside the verdict.
        v["C7_deflation"] = bool(defl["dsr_pass"]) if defl else False
        v["SHIPS"] = all(bool(v[c]) for c in SHIP_CLAUSES if c in v)
        out[a] = v
    return out


def _run_full_rule(y, mu, sigma, dates, *, seed):
    """Score + deflate + apply the ship rule. Used by the decisive run AND by every control."""
    res = score_arms(y, mu, sigma, dates, seed=seed, reps=0)
    winner = max(TRIAL_ARMS, key=lambda a: res["lift"][a][PRIMARY_STAT]["point"])
    defl = deflation(res["rows"], res["block"], dates, winner=winner)
    return res, defl, ship_verdict(res, defl), winner


def run_controls(mu, sigma, dates, *, reps=N_CONTROL_REPS, seed=SEED):
    """§6.3 + §7.5 + §7.6. Every leg is a DETECTION RATE over replicates, never a single draw."""
    out = {"n_reps": reps, "n_rows": int(len(mu))}

    # ── §6.3 the MH2.8 positive control: the fitter must FIND a planted skew ───────────────────
    found, coll = 0, 0
    for r in range(reps):
        y = plant(mu, sigma, skew_alpha=CONTROL_SKEW_ALPHA, seed=seed + 1000 + r)
        block = date_blocks(dates, k=N_BLOCKS)
        _, collapse, detail = build_arms(y, mu, sigma, block, seed=seed)
        sk = [d["skew"] for d in detail["mix2_full"]]
        ok = (sum(collapse["mix2_full"]) <= N_BLOCKS // 2
              and float(np.median(sk)) > 0)          # the PLANTED sign
        found += bool(ok)
        coll += sum(collapse["mix2_full"])
    out["positive_control_fitter_finds_skew"] = {
        "planted_skew_alpha": CONTROL_SKEW_ALPHA, "detection_rate": found / reps,
        "bar": POSITIVE_CONTROL_BAR, "pass": bool(found / reps >= POSITIVE_CONTROL_BAR),
        "collapsed_block_fits": coll, "total_block_fits": reps * N_BLOCKS,
        "note": ("MH2.8's skew-normal reported 'no skew, converged successfully' on obviously "
                 "skewed data; TV2-0 reproduced it on THIS population (5/5 blocks). A fitter that "
                 "cannot find a skew it was handed cannot be trusted to report its absence."),
    }

    # ── §7.5 the NEGATIVE control — mirrors the SHIP RULE's margin, not 'the closest arm' ──────
    # ── §7.6 the VACUITY FLOOR — the same rule, on a planted GROSS defect ──────────────────────
    # ⭐ §16 — the floor is read on the PLAT-CVP1 taxonomy the spec directs this story to consume.
    #    `VACUOUS` means an arm survives the NO-EFFECT payload — the family certifies noise. A
    #    family whose METRIC gates all fire on a planted effect while its DEFLATION half blocks is
    #    `DEFLATION_BLOCKED`: a reachable, reportable state the spec names in advance, NOT a broken
    #    harness. So the two legs ask the two different questions, rather than one ship-rate asking
    #    neither cleanly.
    metric_clauses = [c for c in SHIP_CLAUSES if c != "C7_deflation"]
    for leg, alpha, bar, cmp, mode in (
            ("negative_control_clean_data", 0.0, NEGATIVE_CONTROL_BAR, "le", "ship"),
            ("gross_defect_detection", CONTROL_SKEW_ALPHA, GROSS_DEFECT_DETECTION_BAR, "ge",
             "metric")):
        hits, ship_hits, clause_hits = 0, 0, {c: 0 for c in SHIP_CLAUSES}
        for r in range(reps):
            y = plant(mu, sigma, skew_alpha=alpha, seed=seed + 2000 + r)
            _, _, verd, _ = _run_full_rule(y, mu, sigma, dates, seed=seed)
            ships = any(v["SHIPS"] for v in verd.values())
            metric_ok = any(all(v[c] for c in metric_clauses if c in v) for v in verd.values())
            ship_hits += ships
            hits += ships if mode == "ship" else metric_ok
            for c in SHIP_CLAUSES:
                clause_hits[c] += any(v.get(c) for v in verd.values())
        rate = hits / reps
        out[leg] = {"planted_skew_alpha": alpha, "rate": rate, "rate_is": mode, "bar": bar,
                    "full_ship_rate": ship_hits / reps,
                    "per_clause_detection": {c: v / reps for c, v in clause_hits.items()},
                    "pass": bool(rate <= bar if cmp == "le" else rate >= bar)}
    out["floor_note"] = (
        "The gross leg reports the METRIC-gate detection rate: a family whose metric gates all "
        "fire on a planted effect while its DEFLATION half blocks is DEFLATION_BLOCKED (a state "
        "the spec names in advance), not a vacuous harness. VACUOUS means an arm survives the "
        "NO-EFFECT payload — which is what the negative leg measures, on the FULL ship rule.")
    out["negative_control_note"] = (
        "⛔ NOT 'which arm is closest' (MH2.8's second defect): this is the fraction of clean-data "
        "replicates in which the FULL ship rule of §8 produces a SHIPPABLE margin.")
    out["_all_passed"] = bool(all(out[k]["pass"] for k in
                                  ("positive_control_fitter_finds_skew",
                                   "negative_control_clean_data", "gross_defect_detection")))
    return out


def cvp1_control(mu, sigma, dates, *, seed=SEED):
    """PLAT-CVP1 — EXECUTED, not narrated. Which of OUR registered gates pass a planted effect?"""
    from betting_ml.utils.cv_power import injected_effect_positive_control

    state = {}

    def inject(effect):
        return plant(mu, sigma, skew_alpha=float(effect), seed=seed + 31337)

    def run_gates(payload):
        _, defl, verd, _ = _run_full_rule(payload, mu, sigma, dates, seed=seed)
        state.setdefault("pbo", []).append(defl["pbo"])
        return {a: {c: bool(v[c]) for c in SHIP_CLAUSES if c in v} for a, v in verd.items()}

    rep = injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=CONTROL_SKEW_ALPHA, null_effect=0.0,
        check_null_control=True)
    pbos = state.get("pbo", [])
    # ⚠️ NF-INJ2b — a field-level statistic the injection cannot MOVE is INERT, never a passed leg.
    moved = bool(len(pbos) >= 2 and abs(pbos[0] - pbos[-1]) > 1e-12)
    import dataclasses
    return {"verdict": rep.verdict,
            "detail": _strip({k: v for k, v in dataclasses.asdict(rep).items()
                              if k != "verdict"}),
            "pbo_under_null_and_injected": [float(x) for x in pbos],
            "field_statistic_moved": moved,
            "field_statistic_reading": "ACTIVE" if moved else "INERT",
            "inert_caveat": ("NF-INJ2b: a uniform injection cannot re-order treated arms among "
                             "themselves, so a rank-based FIELD-LEVEL statistic can be invariant "
                             "BY CONSTRUCTION. An unmoved statistic is reported INERT, never as a "
                             "passed leg.")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SENSITIVITY · SCOPE · CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════════════════════

def leave_one_block_out(y, mu, sigma, dates, *, winner, seed=SEED):
    """§7.4 — does ONE anomalous chunk carry the result?

    ⭐ The spec's leave-one-COVID-season-out is INAPPLICABLE-BY-CONSTRUCTION on the decisive
    population: the served champion era is 2026-06-23 → 2026-08-30 and contains no 2020 season,
    indeed no season boundary at all. Running it here would be a vacuous anchor reported as a
    passed test (NF1.7 (a)). This is the applicable analogue and asks the identical question.
    """
    y, mu, sigma = (np.asarray(v, float) for v in (y, mu, sigma))
    d = np.asarray(dates)
    block = date_blocks(d, k=N_BLOCKS)
    out = []
    for b in range(N_BLOCKS):
        m = block != b
        res = score_arms(y[m], mu[m], sigma[m], d[m], seed=seed, reps=0)
        out.append({"held_out_block": b, "n": int(m.sum()),
                    "lift_over_foil": res["lift"][winner][PRIMARY_STAT]["point"],
                    "material": res["lift"][winner][PRIMARY_STAT]["material"],
                    "incumbent_gap": res["incumbent_gap"]})
    pts = np.array([o["lift_over_foil"] for o in out], float)
    return {"applicable_analogue": "leave-one-DATE-BLOCK-out",
            "covid_season_leg": "INAPPLICABLE-BY-CONSTRUCTION — the served era contains no season "
                                "boundary; running it would be a vacuous anchor (NF1.7 (a))",
            "per_block": out, "min": float(pts.min()), "max": float(pts.max()),
            "sign_stable": bool(np.all(pts > 0) or np.all(pts < 0)),
            "spread_over_mean": float((pts.max() - pts.min()) / max(abs(pts.mean()), 1e-12))}


def location_probe(y, mu, sigma):
    """§10 — DISCRIMINATION, REPORTED and never gated. ARM-INVARIANT by construction."""
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    return {
        "std_pred_meanspread": float(np.std(mu, ddof=1)),
        "std_pred_meanspread_source": STD_PRED_MEANSPREAD_SOURCE,
        "std_pred_meanspread_v2_gate": 2.0,
        "std_pred_predictive_sd": float(np.mean(np.asarray(sigma, float))),
        "std_pred_predictive_sd_source": STD_PRED_PREDICTIVE_SD_SOURCE,
        "sd_y_realized": float(np.std(y, ddof=1)),
        "var_mu_over_var_y": float(np.var(mu, ddof=1) / np.var(y, ddof=1)),
        "read_by_any_gate": False,
        "null_state": DISCRIMINATION_NULL_STATE,
        "retest_trigger": None,
        "note": ("Every arm holds mu EXACTLY at the served value, so no arm can move either "
                 "statistic. Registering a gate against a statistic no arm can move would ship "
                 "decor (NF-MARGIN2). INACTIVE gets NO fold/season re-test trigger (NF-D18)."),
    }


def classify(res, defl, verd, winner):
    """`cv_power.classify_null` with the DECLARED field size — read from the MACHINE FLAGS."""
    from betting_ml.utils.cv_power import classify_null
    v = verd[winner]
    hard = [c for c in ("C1_not_collapsed", "C9_mechanism_attribution",
                        "C10_own_form_oracle_floor") if not v[c]]
    nv = classify_null(
        metric=PRIMARY_STAT, n_folds=N_BLOCKS, n_arms=len(TRIAL_ARMS),
        beats_foil=bool(res["lift"][winner][PRIMARY_STAT]["point"] > 0),
        observed_sr=defl["observed_sr"], var_trials_sr=defl["var_trials_sr"],
        var_trials_sr_with_degenerates=defl["var_trials_sr_with_degenerates"],
        degenerates_excluded_from_v=DEGENERATES_EXCLUDED_FROM_V,
        fold_wins=v["fold_wins"], p_one_sided=v["p_one_sided"], bh_cutoff=res["bh_cutoff"],
        pbo=defl["pbo"], pbo_gate=PBO_GATE, pbo_application=PBO_APPLICATION,
        declared_field_size=DECLARED_FIELD_SIZE)
    import dataclasses
    out = _strip(dataclasses.asdict(nv))
    # ⭐ A HARD CONSTRAINT BINDS over any statistical shortfall, and publishes NO data trigger
    #    (NF-D18): no number of served games can move a collapse, a mechanism foil or an oracle.
    if hard:
        out["state_as_recorded"] = out.get("state")
        out["state"] = "CONSTRAINT_REFUSED"
        out["binding_half"] = "hard constraint"
        out["binding_clauses"] = hard
        out["retest_trigger"] = None
        out["constraint_note"] = (
            "A deterministic constraint refused this arm. The remedy is a DIFFERENT MECHANISM or a "
            "PM decision, NEVER more data — and no fold/season re-test trigger is published "
            "(NF-D18). The statistical reading is reported beside it, not hidden.")
    return out


def lockstep(defl):
    """NF-W8-0d — is a shared-variance lever even capable of clearing `dsr_ok`? Computed, not felt."""
    from betting_ml.utils.cv_power import lockstep_variance_lever
    r = lockstep_variance_lever(observed_sr=defl["observed_sr"], n_trials=defl["n_trials"],
                                var_trials_sr=defl["var_trials_sr"], n_obs=N_BLOCKS)
    import dataclasses
    return _strip(dataclasses.asdict(r))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE RUN
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _tier(df, tier):
    d = df[df["tier"] == tier]
    return (d["y_total"].to_numpy(float), d["mu"].to_numpy(float),
            d["sigma"].to_numpy(float), d["game_date"].to_numpy())


def run(*, reps=N_NULL, tier=PRIMARY_TIER, controls=True, seed=SEED):
    df = pull()
    out = {"story": STORY, "seed": seed, "best_alpha": BEST_ALPHA, "bet_paused": True,
           "deploy_held": True, "market_blind": True, "tier": tier,
           "champion": {"model_versions": list(ERA_MODEL_VERSIONS), "fit_date": CHAMPION_FIT_DATE},
           "served_median_insert_lag_days": float(df["insert_lag_days"].median()),
           "prereg": "ablation_results/mlb_tv2_2_prereg.md"}

    # ── NODE 2 — the REPLICATION leg. The STOP gate. ───────────────────────────────────────────
    out["replication"] = replication(df, tier=tier, reps=reps, seed=seed)
    out["replication_secondary"] = replication(df, tier=SECONDARY_TIER, reps=reps, seed=seed)
    if not out["replication"]["replicated"]:
        out["verdict"] = "STOP_PREMISE_FAILED"
        out["route"] = ("The shape gap does not replicate on the widest served window this "
                        "champion has produced. Nothing is fitted; no ship clause is evaluated. "
                        "The funding premise fails and the verdict returns to the PM.")
        return out

    y, mu, sigma, dates = _tier(df, tier)
    out["n"] = int(len(y))

    # ── the vacuity floor + the positive controls, BEFORE the real-data verdict is read ────────
    if controls:
        out["controls"] = run_controls(mu, sigma, dates, seed=seed)
        out["cvp1"] = cvp1_control(mu, sigma, dates, seed=seed)
        if not out["controls"]["_all_passed"]:
            out["verdict"] = "HARNESS_NOT_TRUSTWORTHY"
            out["route"] = ("A control failed. A harness that cannot separate a PLANTED cause "
                            "cannot separate a real one, and its real-data reading is not read "
                            "(MH2.6's vacuity floor).")
            return out

    # ── the decisive run ──────────────────────────────────────────────────────────────────────
    res = score_arms(y, mu, sigma, dates, seed=seed, reps=reps)
    winner = max(TRIAL_ARMS, key=lambda a: res["lift"][a][PRIMARY_STAT]["point"])
    defl = deflation(res["rows"], res["block"], dates, winner=winner)
    verd = ship_verdict(res, defl)
    verd[winner]["C0_replication"] = True
    out.update({
        "winner": winner,
        "stats": {a: res["stats"][a] for a in res["stats"]},
        "lift_over_foil": {a: res["lift"][a] for a in res["lift"]},
        "collapse": res["collapse"], "mixture_detail": res["detail"],
        "floors": res["floors"], "coverage_floor": res["coverage_floor"],
        "incumbent_gap": res["incumbent_gap"], "bh_cutoff": res["bh_cutoff"],
        "bh_family": BH_FAMILY, "fold_clause": res["fold_clause"],
        "deflation": defl, "ship": verd,
        "ctrl_permuted_lift": res["ctrl_permuted_lift"],
        "ctrl_symmetrized_lift": res["ctrl_symmetrized_lift"],
        "classification": classify(res, defl, verd, winner),
        "lockstep": lockstep(defl),
        "sensitivity": leave_one_block_out(y, mu, sigma, dates, winner=winner, seed=seed),
        "location_probe": location_probe(y, mu, sigma),
        "std_pred_disambiguation": {
            "meanspread": STD_PRED_MEANSPREAD_SOURCE,
            "predictive_sd": STD_PRED_PREDICTIVE_SD_SOURCE,
            "read_by_gates": DISPERSION_GATE_STAT,
            "note": "NEITHER std_pred is read by any gate; dispersion gates read var_z_pooled "
                    "in a SHAPE-MATCHED null (§7.2, §9)."},
    })
    shipping = [a for a, v in verd.items() if v.get("SHIPS")]
    out["shipping_arms"] = shipping
    out["verdict"] = "SHIP_CANDIDATE" if winner in shipping else out["classification"]["state"]
    out["route"] = ("DEPLOY-HELD. A model-registry merge to main IS the deploy and no promotion "
                    "gate exists (MH2.1) — the operator packet carries the merge decision."
                    if winner in shipping else
                    "Nothing ships. The verdict is recorded with its null STATE and its MDE.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE 1e-9 REPRODUCTION PIN
# ══════════════════════════════════════════════════════════════════════════════════════════════

def fixture_frame(n=600, seed=7):
    """A committed synthetic slate: real-ish `(mu, sigma, dates)` and a PLANTED shape defect."""
    from scipy.stats import skewnorm
    rng = np.random.default_rng(seed)
    mu = 8.6 + 0.55 * rng.standard_normal(n)
    sigma = 4.35 + 0.21 * np.abs(rng.standard_normal(n))
    dates = (np.datetime64("2026-06-23") +
             (np.arange(n) // 12).astype("timedelta64[D]")).astype(str).tolist()
    z = skewnorm.rvs(4.0, size=n, random_state=rng)
    z = (z - z.mean()) / z.std(ddof=1)
    return {"mu": mu.tolist(), "sigma": sigma.tolist(), "dates": dates,
            "y": np.round(mu + sigma * z).tolist()}


def fixture_run(fx):
    y = np.asarray(fx["y"], float)
    mu, sigma = np.asarray(fx["mu"], float), np.asarray(fx["sigma"], float)
    dates = np.asarray(fx["dates"], dtype="datetime64[D]")
    res, defl, verd, winner = _run_full_rule(y, mu, sigma, dates, seed=SEED)
    return {"winner": winner,
            "incumbent_gap": res["incumbent_gap"],
            "winner_lift": res["lift"][winner][PRIMARY_STAT]["point"],
            "winner_crps_lift": res["lift"][winner][SCORE_STAT]["point"],
            "ctrl_permuted_lift": res["ctrl_permuted_lift"],
            "ctrl_symmetrized_lift": res["ctrl_symmetrized_lift"],
            "collapsed_blocks_mix2_full": int(sum(res["collapse"]["mix2_full"])),
            "mix2_full_skew_block0": res["detail"]["mix2_full"][0]["skew"],
            "dsr": defl["dsr"], "pbo": defl["pbo"], "observed_sr": defl["observed_sr"],
            "sr0": defl["sr0"], "var_trials_sr": defl["var_trials_sr"],
            "ships": sorted(a for a, v in verd.items() if v["SHIPS"])}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _f(x, d=4):
    return "—" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float, np.floating)) else str(x))


def _tick(b):
    return "✅" if b else "⛔"


def write_report(r, path=_REPORT_MD):
    L = [f"# {STORY} — a mixture-density head for the served `total_runs` SHAPE\n",
         f"> **VERDICT: `{r['verdict']}`**\n",
         f"`best_alpha = 0` · `bet_paused` stays `true` · **market-blind** · **nothing serves** · "
         f"**DEPLOY-HELD**\n",
         "**This is a calibration/honesty study.** No edge, win-rate, ROI or CLV claim is made and "
         "no gate reads a market price. Pre-registration: "
         "[`mlb_tv2_2_prereg.md`](mlb_tv2_2_prereg.md) (amendment 1 = its §12).\n",
         f"{r['route']}\n", "---\n", "## 1. Population\n", "| | |", "|---|---|",
         f"| champion | `{'` / `'.join(ERA_MODEL_VERSIONS)}`, fit {CHAMPION_FIT_DATE} |",
         f"| served window | {CHAMPION_FIT_DATE} → {FULL_ERA_END} |",
         f"| PRIMARY tier | `{r['tier']}` — n = **{r.get('n', '—')}** |",
         f"| ⭐ median insertion lag | **{_f(r['served_median_insert_lag_days'], 1)} d** — "
         f"served-ness is the LAG, not the `is_backfill` flag (prereg §2.1) |",
         f"| blocks | {N_BLOCKS} contiguous DATE blocks, cross-fit |\n"]

    # ── replication ───────────────────────────────────────────────────────────────────────────
    rep = r["replication"]
    L += ["## 2. ⭐ The REPLICATION leg (prereg §3) — the STOP gate\n",
          "| read | n | window | stated | realized | gap | null 95% band | outside? | power vs "
          "TV2-0's gap | BINDS |", "|---|---:|---|---:|---:|---:|---|---|---:|---|"]
    for name, d in rep["reads"].items():
        L.append(f"| `{name}` | {d['n']} | {d['d0']} → {d['d1']} | {_f(d['p_over_stated'])} | "
                 f"{_f(d['p_over_realized'])} | **{_f(d['p_over_gap'])}** | "
                 f"[{_f(d['null_lo'])}, {_f(d['null_hi'])}] | {_tick(d['outside_band'])} | "
                 f"{_f(d['power_vs_tv2_0_gap'], 3)} | "
                 f"{'⭐ **yes**' if name == rep['binding_read'] else 'no'} |")
    L += [f"\n**Replicated: {_tick(rep['replicated'])}** — on the BINDING `{rep['binding_read']}` "
          f"read.\n",
          f"⚠️ {rep['fresh_note']}\n", f"⚠️ {rep['window_limit_note']}\n",
          f"Secondary tier (`{SECONDARY_TIER}`, reported, never swaps the primary — E2.1-r): "
          f"replicated = {_tick(r['replication_secondary']['replicated'])}, "
          f"gap {_f(r['replication_secondary']['reads']['FULL_ERA']['p_over_gap'])}\n"]
    if r["verdict"] == "STOP_PREMISE_FAILED":
        path.write_text("\n".join(L) + "\n")
        return path

    # ── controls ──────────────────────────────────────────────────────────────────────────────
    if "controls" in r:
        c = r["controls"]
        L += ["---\n", "## 3. ⭐ The controls — run BEFORE any real-data verdict was read\n",
              "A harness that cannot separate a PLANTED cause cannot separate a real one, and a "
              "harness that cannot FAIL is worse than none (MH2.6's vacuity floor).\n",
              "| leg | what it plants | rate | bar | ✓ |", "|---|---|---:|---:|---|"]
        pc = c["positive_control_fitter_finds_skew"]
        L += [f"| §6.3 the fitter FINDS a planted skew | skew-normal α = {pc['planted_skew_alpha']} "
              f"| **{_f(pc['detection_rate'], 2)}** | ≥ {pc['bar']} | {_tick(pc['pass'])} |",
              f"| §7.5 NEGATIVE control (mirrors the SHIP RULE's margin) | *nothing — a correct "
              f"model* | **{_f(c['negative_control_clean_data']['ship_rate'], 2)}** | "
              f"≤ {NEGATIVE_CONTROL_BAR} | {_tick(c['negative_control_clean_data']['pass'])} |",
              f"| §7.6 detection on a planted GROSS defect | skew-normal α = "
              f"{CONTROL_SKEW_ALPHA} | **{_f(c['gross_defect_detection']['ship_rate'], 2)}** | "
              f"≥ {GROSS_DEFECT_DETECTION_BAR} | {_tick(c['gross_defect_detection']['pass'])} |",
              f"\nCollapsed block fits under the positive control: "
              f"**{pc['collapsed_block_fits']} of {pc['total_block_fits']}** — the staggered "
              f"initialization (§6.1) keeping the fit off the flat ridge MH2.8 died on.\n",
              f"⛔ {c['negative_control_note']}\n"]
        if "cvp1" in r:
            v = r["cvp1"]
            L += [f"**PLAT-CVP1 injected-effect positive control (EXECUTED, not narrated): "
                  f"`{v['verdict']}`.** Field-level statistic: **{v['field_statistic_reading']}** "
                  f"(PBO under null / injected: "
                  f"{', '.join(_f(x) for x in v['pbo_under_null_and_injected'])}).\n",
                  f"⚠️ {v['inert_caveat']}\n"]

    # ── the battery ───────────────────────────────────────────────────────────────────────────
    L += ["---\n", f"## 4. The battery (PRIMARY tier, n = {r['n']})\n",
          "⛔ = an ORACLE or a CONTROL — never a shippable arm. Every arm holds `μ` EXACTLY at the "
          "served value.\n",
          f"| arm | `{PRIMARY_STAT}` | `{SCORE_STAT}` | `{FIDELITY_STAT}` | `p_over_stated` | "
          f"`{COVERAGE_STAT}` | `{VARIANCE_STAT}` | `z_skew` |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    order = [REFERENCE_ARM, FOIL_ARM, *TRIAL_ARMS, *DEGENERATE_ARMS, *CONTROL_ARMS,
             *[f"oracle_{a}" for a in TRIAL_ARMS], "oracle_empirical"]
    for a in order:
        s = r["stats"].get(a)
        if not s:
            continue
        mark = " ⛔" if (a.startswith("oracle") or a.startswith("ctrl") or a in DEGENERATE_ARMS) else ""
        L.append(f"| `{a}`{mark} | {_f(s[PRIMARY_STAT])} | {_f(s[SCORE_STAT])} | "
                 f"{_f(s[FIDELITY_STAT])} | {_f(s['p_over_stated'])} | {_f(s[COVERAGE_STAT])} | "
                 f"{_f(s[VARIANCE_STAT])} | {_f(s['z_skew'])} |")

    L += [f"\n### The fitted mixtures — and the TIE-WITH-FOIL guard (§6.2)\n",
          "| arm | K by block | fitted skew by block | sup-norm vs the K=1 foil | COLLAPSED blocks |",
          "|---|---|---|---|---:|"]
    for a in TRIAL_ARMS:
        d = r["mixture_detail"][a]
        L.append(f"| `{a}` | {[x['K'] for x in d]} | {[x['skew'] for x in d]} | "
                 f"{[x['supnorm_vs_k1'] for x in d]} | **{sum(x['collapsed'] for x in d)}** |")
    L += ["\n⭐ A COLLAPSED arm's margin is a **TIE that refuses to count** — never a shape "
          "finding. TV2-0's skew-normal collapsed on 5 of 5 blocks on this same population at a "
          "realized `z` skew of 0.749; that is the failure this guard exists to make visible.\n"]

    # ── the lift table ────────────────────────────────────────────────────────────────────────
    L += ["---\n", f"## 5. The shape channel — every claim measured over `{FOIL_ARM}`\n",
          f"`{FOIL_ARM}` is a location+scale recalibration with NO shape channel: it keeps the "
          "machinery, the cross-fit and the scale correction and removes only what this story "
          "claims. Scoring against the incumbent instead would let the mixture bank a plain "
          "recalibrator's work (§5.2).\n",
          f"| arm | Δ`{PRIMARY_STAT}` (95% CI) | material | Δ`{SCORE_STAT}` | "
          f"Δ`{FIDELITY_STAT}` | share of the incumbent's gap |",
          "|---|---:|---|---:|---:|---:|"]
    ig = r["incumbent_gap"]
    for a in [*TRIAL_ARMS, *CONTROL_ARMS]:
        l = r["lift_over_foil"][a]
        p = l[PRIMARY_STAT]
        L.append(f"| `{a}` | {_f(p['point'])} [{_f(p['lo'])}, {_f(p['hi'])}] | "
                 f"{_tick(p['material'])} | {_f(l[SCORE_STAT]['point'])} | "
                 f"{_f(l[FIDELITY_STAT]['point'])} | {_f(p['point'] / ig if ig else 0)} |")
    L += [f"\n⛔ `ctrl_permuted` was **registered as an EXPECTED EXACT TIE** (§5.4): a row "
          f"permutation cannot move a MARGINAL law. Measured lift **{_f(r['ctrl_permuted_lift'], 6)}** "
          f"— reported as a proven tie and a machinery check (no row-level leakage), never as a "
          f"passed test (NF1.9).\n",
          f"⛔ `ctrl_symmetrized` is the matched foil for the STATED MECHANISM (§5.4): same form, "
          f"ASYMMETRY destroyed. Measured lift **{_f(r['ctrl_symmetrized_lift'])}**. If the win "
          f"survives symmetrization it is NOT about skew (NF-D15 (g′)).\n"]

    # ── the ship rule ─────────────────────────────────────────────────────────────────────────
    d = r["deflation"]
    L += ["---\n", f"## 6. THE SHIP RULE (§8) — winner `{r['winner']}`\n",
          "| clause | " + " | ".join(f"`{a}`" for a in TRIAL_ARMS) + " |",
          "|---|" + "---|" * len(TRIAL_ARMS)]
    for c in SHIP_CLAUSES:
        vals = [r["ship"][a].get(c) for a in TRIAL_ARMS]
        if all(v is None for v in vals):
            continue
        L.append(f"| `{c}` | " + " | ".join("—" if v is None else _tick(v) for v in vals) + " |")
    L.append("| **SHIPS** | " + " | ".join(_tick(r["ship"][a]["SHIPS"]) for a in TRIAL_ARMS) + " |")

    L += [f"\n### Deflation (§12 amendment 1 — PBO and DSR read SEPARATE series)\n", "| | |",
          "|---|---|",
          f"| DSR series | {d['dsr_series']} |", f"| PBO series | {d['pbo_series']} |",
          f"| `V` membership | `{'`, `'.join(d['v_membership'])}` — reference, foil and "
          f"degenerates ∉ `V` (MH2.1 (a) / DSR-CONV) |",
          f"| `n_trials` | {d['n_trials']} — the FULL field; multiplicity paid in full |",
          f"| `var_trials_sr` | {_f(d['var_trials_sr'])} (with degenerates: "
          f"{_f(d['var_trials_sr_with_degenerates'])}) |",
          f"| observed SR / `SR0` | {_f(d['observed_sr'])} / {_f(d['sr0'])} |",
          f"| **DSR** | **{_f(d['dsr'])}** vs {DSR_GATE} → {_tick(d['dsr_pass'])} |",
          f"| **PBO** (binding: `{d['pbo_binding_reading']}`) | **{_f(d['pbo'])}** vs "
          f"{PBO_GATE} → {_tick(d['pbo_pass'])} |",
          f"| `pbo_application` | `{d['pbo_application']}` — a FIELD-LEVEL statistic, ⛔ never "
          f"carried per-arm (PM convention 2026-08-28) |",
          f"| BH family | {r['bh_family']}; cutoff {_f(r['bh_cutoff'])} |",
          f"| fold clause | ≥ {r['fold_clause']['wins_required']} of {N_BLOCKS} "
          f"(false-fire {_f(r['fold_clause']['false_fire'], 3)}) |",
          f"| coverage floor | {_f(r['coverage_floor'])} — POWER-DERIVED from n at a false-reject "
          f"target of {COVERAGE_FALSE_REJECT} (NF-D22), ⛔ never a flat nominal point-floor |",
          "\nPBO under all three registered readings:\n", "| reading | n configs | PBO |",
          "|---|---:|---:|"]
    for k, v in d["pbo_readings"].items():
        L.append(f"| `{k}`{' ⭐ **binds**' if k == d['pbo_binding_reading'] else ''} | "
                 f"{v['n_configs']} | {_f(v['pbo'])} |")

    # ── classification ────────────────────────────────────────────────────────────────────────
    cl = r["classification"]
    L += ["\n---\n", "## 7. Classification, sensitivity and scope\n",
          f"**`classify_null` state: `{cl.get('state')}`** "
          f"(`declared_field_size = {DECLARED_FIELD_SIZE}`; read from the MACHINE FLAGS, never "
          f"the prose — MH2.7).\n"]
    if cl.get("binding_clauses"):
        L.append(f"⛔ **A HARD CONSTRAINT BINDS**: `{'`, `'.join(cl['binding_clauses'])}`. "
                 f"{cl['constraint_note']} The statistical reading was "
                 f"`{cl.get('state_as_recorded')}` and is reported here rather than hidden.\n")
    if cl.get("retest_trigger"):
        L.append(f"Re-test trigger: {cl['retest_trigger']}\n")
    ls = r["lockstep"]
    L.append(f"**Lockstep check (NF-W8-0d)** — is a shared-variance lever even capable of clearing "
             f"`dsr_ok`? `{ls.get('verdict', ls)}`. ⛔ Computed, never felt: a design change that "
             f"scales every arm's dispersion by a common factor scales `SR` and `SR0` in lockstep, "
             f"so its SIGN is invariant and 'get a lower-variance design' is deterministically "
             f"void.\n")
    sn = r["sensitivity"]
    L += [f"\n### Sensitivity (§7.4)\n",
          f"⭐ The spec's leave-one-COVID-season-out is **{sn['covid_season_leg']}**. The "
          f"applicable analogue — `{sn['applicable_analogue']}` — asks the identical question and "
          f"is what is run.\n",
          f"| held-out block | n | winner's lift over the foil | material |",
          "|---:|---:|---:|---|"]
    for b in sn["per_block"]:
        L.append(f"| {b['held_out_block']} | {b['n']} | {_f(b['lift_over_foil'])} | "
                 f"{_tick(b['material'])} |")
    L.append(f"\nSign stable across all {N_BLOCKS} leave-one-out fits: "
             f"**{_tick(sn['sign_stable'])}** (range {_f(sn['min'])} … {_f(sn['max'])}).\n")

    lp = r["location_probe"]
    L += ["### ⭐ SCOPE — DISCRIMINATION is untouched (prereg §10)\n",
          "| reading | value | bar | |", "|---|---:|---:|---|",
          f"| `std_pred_meanspread` = `STDDEV(pred_total_runs)` — `{lp['std_pred_meanspread_source']}` "
          f"| **{_f(lp['std_pred_meanspread'], 3)}** | ≥ 2.0 | ⛔ FAILS |",
          f"| `std_pred_predictive_sd` = `mean(σ)` — `{lp['std_pred_predictive_sd_source']}` | "
          f"{_f(lp['std_pred_predictive_sd'], 3)} | — | |",
          f"| realized `SD(y)` | {_f(lp['sd_y_realized'], 3)} | — | |",
          f"| `Var(μ)/Var(y)` | **{_f(lp['var_mu_over_var_y'])}** | — | |",
          f"\n**Read by any gate here: {_tick(lp['read_by_any_gate'])} — no.** {lp['note']}\n",
          f"Null state: **`{lp['null_state']}`**; re-test trigger: **none** — ⛔ no number of "
          f"served games can move a statistic no arm can move.\n",
          "**This study fixes the probability the product PRINTS. It does not make the model "
          "better at telling a high-scoring game from a low-scoring one.** Whether 2.0 is even "
          "attainable for a totals model is not something this market-blind study can measure, and "
          "it stays a named OPEN question on the epic.\n",
          "---\n", "## 8. What this study cannot say\n",
          "- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; `bet_paused` stays "
          "`true`; no gate reads a market price.\n"
          "- Nothing about a **different champion** — the population is "
          f"`{'`/`'.join(ERA_MODEL_VERSIONS)}` (fit {CHAMPION_FIT_DATE}); MH2.6's boundary is "
          "respected, not stretched.\n"
          "- Nothing about **DISCRIMINATION** (§7 above).\n"
          "- MH2.8's `INCUMBENT_STANDS`, TV2-0's INACTIVE feature lever and MH2.10's "
          "anti-informative σ-partition all **STAND AS RECORDED**. This study registered a NEW "
          "coherent family forward; it did not re-cut, re-read or relax any recorded gate.\n"
          "- The `FULL_ERA` read shares 89% of its rows with TV2-0's. It is a LARGER read, not an "
          "INDEPENDENT one (§2).\n"
          "- **DEPLOY-HELD.** Per MH2.1 a model-registry merge to `main` IS the deploy and no "
          "promotion gate exists — nothing merged, no registry entry changed, `deploy.sh` not run."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n")
    return path


def _strip(o):
    """The ONE serializer. It must survive every object the run can produce.

    ⚠️ `cv_power`'s `NullVerdict` carries a NESTED `LockstepReport` dataclass, so a `vars()`-based
    conversion leaves an unserializable object one level down — caught by exercising the FULL run
    on planted data before handing the operator an 8-minute job, which would otherwise have
    completed every computation and then died writing its own output.
    """
    import dataclasses
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return _strip(dataclasses.asdict(o))
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in ("arms", "rows", "boot")}
    if isinstance(o, (list, tuple)):
        return [_strip(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _strip(o.tolist())
    return o


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replication", action="store_true", help="node 2 only: the STOP gate")
    ap.add_argument("--controls", action="store_true", help="the vacuity floor only")
    ap.add_argument("--fixture", action="store_true", help="the 1e-9 reproduction pin")
    ap.add_argument("--write-fixture", action="store_true")
    ap.add_argument("--reps", type=int, default=N_NULL)
    ap.add_argument("--control-reps", type=int, default=N_CONTROL_REPS)
    ap.add_argument("--no-controls", action="store_true")
    a = ap.parse_args()

    if a.write_fixture:
        _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        fx = fixture_frame()
        fx["expected"] = fixture_run(fx)
        _FIXTURE.write_text(json.dumps(_strip(fx), indent=1))
        print(f"fixture → {_FIXTURE}\n{json.dumps(_strip(fx['expected']), indent=2)}")
        return
    if a.fixture:
        fx = json.loads(_FIXTURE.read_text())
        got = fixture_run(fx)
        bad = {k: (v, got[k]) for k, v in fx["expected"].items()
               if (isinstance(v, float) and abs(v - got[k]) > 1e-9) or
               (not isinstance(v, float) and v != got[k])}
        print(json.dumps(_strip(got), indent=2))
        print("REPRODUCTION PIN (1e-9):", "✅ OK" if not bad else f"⛔ DRIFT {bad}")
        sys.exit(0 if not bad else 1)
    if a.replication:
        out = replication(pull(), reps=a.reps)
        _REPLICATION_JSON.parent.mkdir(parents=True, exist_ok=True)
        _REPLICATION_JSON.write_text(json.dumps(_strip(out), indent=1))
        print(json.dumps(_strip(out), indent=2))
        print("REPLICATED:", out["replicated"])
        sys.exit(0 if out["replicated"] else 1)
    if a.controls:
        df = pull()
        _, mu, sigma, dates = _tier(df, PRIMARY_TIER)
        out = run_controls(mu, sigma, dates, reps=a.control_reps)
        out["cvp1"] = cvp1_control(mu, sigma, dates)
        _CONTROLS_JSON.parent.mkdir(parents=True, exist_ok=True)
        _CONTROLS_JSON.write_text(json.dumps(_strip(out), indent=1))
        print(json.dumps(_strip(out), indent=2))
        print("ALL CONTROLS PASSED:", out["_all_passed"])
        sys.exit(0 if out["_all_passed"] else 1)

    r = run(reps=a.reps, controls=not a.no_controls)
    _REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_JSON.write_text(json.dumps(_strip(r), indent=1))
    print(f"report → {write_report(r)}")
    print(f"VERDICT: {r['verdict']}")


if __name__ == "__main__":
    main()

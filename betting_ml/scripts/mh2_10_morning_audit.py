"""mh2_10_morning_audit.py — MH2.10: is the MORNING tier's served σ genuinely too small?

WHY THIS EXISTS
===================================================================================================
MH2.6 audited the **post_lineup** served tier and found it clean on level and variance — only a
distributional SHAPE defect, which MH2.8 then could not ship. MH2.6 also carried `morning`
(`pre_lineup_v6`) as a DECLARED-SECONDARY tier: it computed the statistics and never put them
through its own decision rule. In that unread record the morning tier's VARIANCE statistics sit
outside their calibrated nulls (`var_z_pooled` 1.1199, p = 0.043; `rms_var_z_sigma` 0.3267,
p = 0.003) where post_lineup's sit inside.

That matters because the morning tier carries the WHOLE SLATE before lineups post — it is the
most-viewed set of predictions the product ships each day — and "σ is too small" is, unlike a shape
defect, one of the scoped and genuinely fixable branches.

⛔ **A RETRAIN IS NOT ON THE TABLE IN PHASE 1.** The default verdict is NO ACTION.

THE QUESTION, STATED AS THE DELIVERABLE
---------------------------------------------------------------------------------------------------
Is the morning σ genuinely too small (outside its null), **by how much**, and is it a **SCALE**
defect (fixable by widening) or a **SHAPE** defect (the MH2.8 class, already closed)?

⭐ THE INSTRUMENT THIS STUDY ADDS — A NORMAL NULL IS THE WRONG YARDSTICK FOR A VARIANCE STATISTIC
---------------------------------------------------------------------------------------------------
MH2.6's calibrated null redraws outcomes from the served predictive, which is a symmetric NORMAL.
But MH2.6 and MH2.8 both measured that realized `total_runs` is RIGHT-SKEWED and LEPTOKURTIC against
that Normal (z skew ≈ 0.74, excess kurtosis ≈ 0.59). The sampling variance of a VARIANCE statistic
depends on the FOURTH moment — `Var(s²) = σ⁴·(2/(n−1) + κ/n)` — so a Normal-drawn null is
systematically TOO NARROW for `var_z_pooled` whenever the truth is leptokurtic.

⇒ **A SHAPE DEFECT MECHANICALLY MANUFACTURES APPARENT SCALE FLAGS.** Both tiers share the same
right-skewed target, so this is a live alternative explanation for the premise, and the study is
worthless if it cannot rule it in or out. The SHAPE-MATCHED NULL (LOCK 4c) redraws
`y* = μ + σ·ε*` with `ε*` resampled from the observed standardized residuals RE-SCALED TO VARIANCE
EXACTLY 1 — so its null hypothesis is precisely "the σ SCALE is correct", with the SHAPE carried
over as a nuisance.

⛔ It is applied ONLY to the variance statistics. Applying it to the PIT statistics would build the
very shape defect being tested INTO the null and make the shape untestable by construction.

THE METHOD LOCKS THIS STUDY INHERITS (imported, never re-implemented)
---------------------------------------------------------------------------------------------------
1. ⭐ A CONDITIONAL-CALIBRATION RESULT IS A PROPERTY OF ITS STRATIFIER (`mh2_1_rollback.md` §3).
   Every partition publishes its realized-SD-per-bin table and must clear MH2.5's bar FIRST; a
   partition that fails is DISQUALIFIED and LEAVES THE VERDICT FAMILY. ⚠️ Stated in the
   pre-registration in advance: the morning σ-partition failed MH2.6's bar with a NEGATIVE rank
   correlation, so the premise's strongest-looking flag (`rms_var_z_sigma`, p = 0.003) is expected
   to be INADMISSIBLE — and this study says so before re-measuring it.
2. ⭐ MULTIPLICITY (MH2.6 LOCK 5b). A declared 6-statistic family, BH at q = 0.05, plus the
   vacuity floor below which no input could ever be flagged. The premise's "OUTSIDE" marks are
   UNCORRECTED α = 0.05 marks, and an uncorrected family flags a healthy model ~50% of the time.
3. ⭐ THE NEGATIVE CONTROL MIRRORS THE DECISION RULE, NOT A BARE "did anything look odd" (MH2.8).
   It runs the whole harness on clean frames and reads the VERDICT LABEL Phase 2 keys on.
4. ⭐ MATERIALITY (MH2.5). `|Var(z) − 1| ≥ 0.05` — one coverage point — is required IN ADDITION to
   statistical survival.

🔒 `best_alpha = 0`. A pricing/calibration study. It says NOTHING about win rate, edge or ROI.
💸 SNOWFLAKE-FREE. DuckDB over the S3 lakehouse only.

Usage:
    uv run python betting_ml/scripts/mh2_10_morning_audit.py --smoke       # harness check, no S3
    uv run python betting_ml/scripts/mh2_10_morning_audit.py               # the audit
    uv run python betting_ml/scripts/mh2_10_morning_audit.py --acceptance  # ⏱ operator-scale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

STORY = "MH2.10"
BEST_ALPHA = 0

# ══════════════════════════════════════════════════════════════════════════════════════════════
# PRE-REGISTRATION — every constant below is fixed in SOURCE. The prose version is
# `ablation_results/mh2_10_preregistration.md`, committed BEFORE this file computed anything.
# ══════════════════════════════════════════════════════════════════════════════════════════════

# LOCK 1 — POPULATION. The morning tier only; `post_lineup` is a DIFFERENT model with a different
# contract and is not judged here (it appears only in the verdict-inert descriptive block §6).
TIER = "morning"
CONTRAST_TIER = "post_lineup"          # ⛔ descriptive only — never an anchor (MH2.1 (b))
MORNING_CHAMPION = "pre_lineup_v6"     # E13.11, morning tier, served from 2026-06-24
CONTRAST_CHAMPION = "v6"
# ⛔ The MH2.1 challenger priced post_lineup rows only, so this is a NO-OP on this tier. It is kept
#    so a future stamp cannot slip through unfiltered, and the dropped count is REPORTED.
ROLLED_BACK_TOTALS_STAMP = "mh2_1"
#: ⚠️ Declared deviation from MH2.6, whose rule admitted `v6` on the morning tier too (4 rows on
#: 2026-08-01). The probe showed none survives de-dup with a final; the harness asserts it.
EXPECTED_FOREIGN_STAMP_ROWS = 0

# LOCK 2 — WINDOWS. FULL is PRIMARY: the question is a STANDING property, and MH2.6 already measured
# that nothing on this tier moved between windows. A power decision made from the question's shape.
PRIMARY_WINDOW = "FULL"
RECENT_DAYS = 30

# LOCK 4e — MATERIALITY, imported from MH2.5 rather than invented. A Var(z) of `v` turns a nominal
# central-80% interval into realized coverage 2Φ(1.2816/√v) − 1, so one coverage point is
# |v − 1| ≈ 0.045 and MH2.5 fixed 0.05 as the smallest pricing-relevant movement.
MATERIAL_VAR_Z_GAP = 0.05

# LOCK 7 — CONTROLS.
N_BOOT = 2000
N_NULL = 2000
N_POWER = 400
N_CLEAN_CONTROL = 40          # negative-control replicates (operator-scale)
N_SHAPE_CONTROL = 40          # ⭐ the scale/shape discriminator control
CLEAN_FP_BAR = 0.15           # non-WITHIN_NOISE rate on clean frames must not exceed this
SIGMA_DEFECT_FP_BAR = 0.05    # ⭐ the label Phase 2 keys on must be ≈0 on clean AND on skewed-clean
#: MH2.8's fitted skew-normal shape, imported — the real-world shape for the discriminator control.
SKEW_CONTROL_ALPHA = 3.2
#: `games_needed` grid — the unit that GROWS (NF1.8 / MH2).
GAMES_GRID = (655, 900, 1200, 1600, 2200, 3000, 4000)
TARGET_POWER = 0.80
SEED = 42

# ── Everything below is IMPORTED, never re-implemented: one implementation of each method lock ──
from betting_ml.scripts.mh2_5_sigma_recalibration import (  # noqa: E402
    STRATIFIER_MIN_ENDPOINT_SE,
    STRATIFIER_MIN_RHO,
    _bin_labels,
    metric_noise_floor,
    realized_dispersion_table,
    rms_var_z,
)
from betting_ml.scripts.mh2_6_calibration_audit import (  # noqa: E402
    ALPHA,
    FDR_Q,
    VERDICT_STATS_H2H,
    VERDICT_STATS_TOTALS,
    _boot_ci,
    _f,
    _null_table,
    _strat_table,
    bh_reject,
    bootstrap,
    calibrated_null,
    draw_totals,
    h2h_stats,
    min_null_reps,
    n_strata,
    null_verdict,
    pit_shape_diagnosis,
    power_curve_h2h,
    power_curve_totals,
    randomized_pit,
    stratifier_games_needed,
    totals_stats,
)
from betting_ml.scripts.mh2_6_calibration_audit import (  # noqa: E402
    _p_shift as _shift_p,
)

PRIMARY_STRATIFIER = "incumbent_sigma"
SECONDARY_STRATIFIER = "incumbent_mean"
#: The variance statistics — the ONLY ones the shape-matched null may judge (LOCK 4c).
VARIANCE_STATS = ("var_z_pooled", "rms_var_z_sigma", "rms_var_z_mean")

_TABLES = ("daily_model_predictions", "mart_game_results")

#: Both tiers, so the verdict-inert descriptive contrast of §6 can be read on the SAME games.
#: The morning tier is filtered to its OWN champion; the contrast tier to its own.
_PULL_SQL = f"""
WITH served AS (
    SELECT
        game_pk,
        game_date::date              AS game_date,
        prediction_type              AS tier,
        model_version,
        totals_model_version,
        pred_total_runs              AS mu,
        pred_total_runs_scale        AS sigma,
        calibrated_win_prob          AS p_home,
        data_source,
        inserted_at
    FROM daily_model_predictions
    WHERE COALESCE(is_backfill, FALSE) = FALSE
      AND (   (prediction_type = '{TIER}'          AND model_version = '{MORNING_CHAMPION}')
           OR (prediction_type = '{CONTRAST_TIER}' AND model_version = '{CONTRAST_CHAMPION}'))
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, prediction_type ORDER BY inserted_at DESC
    ) = 1
)
SELECT
    s.game_pk, s.game_date, s.tier, s.model_version, s.totals_model_version,
    s.mu, s.sigma, s.p_home, s.data_source,
    (r.home_final_score + r.away_final_score)::DOUBLE AS y_total,
    CASE WHEN r.home_team_won THEN 1.0 ELSE 0.0 END   AS y_home_win
FROM served s
JOIN mart_game_results r
  ON r.game_pk = s.game_pk
 AND r.game_type = 'R'
 AND r.home_final_score IS NOT NULL
ORDER BY s.game_date, s.game_pk, s.tier
"""


def pull(cache: Path | None = None) -> pd.DataFrame:
    """The served rows joined to realized outcomes. Snowflake-free (DuckDB over S3)."""
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
# ⭐ LOCK 4c — THE SHAPE-MATCHED NULL: the discriminator between a SCALE defect and a SHAPE defect
# ══════════════════════════════════════════════════════════════════════════════════════════════

def variance_stats(y, mu, sigma, k: int) -> dict:
    """ONLY the variance statistics — the ONLY family the shape-matched null may judge.

    Deliberately a lean function rather than `totals_stats`: the shape-matched null draws a
    CONTINUOUS `y*` (no integer rounding, because the resampled residual pool already carries the
    real data's rounding signature), so the PIT statistics are not even defined the same way on it.
    Keeping the surface to three statistics makes the LOCK 4c restriction structural rather than a
    matter of remembering to ignore the others.

    A guard test asserts these agree EXACTLY with `totals_stats`' values on the observed rows, so
    the lean path can never silently drift from the imported one.
    """
    y, mu, sigma = np.asarray(y, float), np.asarray(mu, float), np.asarray(sigma, float)
    z = (y - mu) / sigma
    out = {"n": len(y), "var_z_pooled": float(np.var(z, ddof=1))}
    rms_s, rows_s = rms_var_z(z, _bin_labels(sigma, k))
    rms_m, rows_m = rms_var_z(z, _bin_labels(mu, k))
    out["rms_var_z_sigma"] = rms_s
    out["rms_var_z_mean"] = rms_m
    out["rms_var_z_sigma_floor"] = metric_noise_floor([r["n"] for r in rows_s])
    return out


def standardized_shape_pool(y, mu, sigma) -> np.ndarray:
    """The observed standardized residuals, re-centred to mean 0 and re-scaled to POPULATION
    variance exactly 1.

    ⭐ `ddof=0` is load-bearing and is NOT a typo. A with-replacement resample of size `n` from a
    pool has `E[s²(ddof=1)] =` the pool's **population** variance, so standardising with `ddof=0` is
    what makes the shape-matched null centre on `Var(z*) = 1` — i.e. what makes its null hypothesis
    actually be "the σ scale is correct". Standardising with `ddof=1` would put the null's centre at
    `(n−1)/n`, biasing every scale test in the direction of finding a defect.
    """
    z = (np.asarray(y, float) - mu) / sigma
    return (z - np.mean(z)) / np.std(z, ddof=0)


def draw_shape_matched(mu, sigma, pool, rng) -> np.ndarray:
    """`y* = μ + σ·ε*`, `ε*` resampled from a variance-1 shape pool.

    ⛔ NOT rounded to an integer. The pool is built from residuals of INTEGER outcomes, so it
    already carries the rounding's contribution to the fourth moment; re-rounding would count it
    twice. This is also why this draw may only be used for the variance statistics — a continuous
    `y*` makes the E2.1-r continuity-corrected PIT ill-posed, which is a second, structural reason
    for the LOCK 4c restriction.
    """
    eps = rng.choice(pool, size=len(mu), replace=True)
    return np.asarray(mu, float) + np.asarray(sigma, float) * eps


def _standardized_skewnorm(a: float, n: int, rng) -> np.ndarray:
    """Draws from a skew-normal with shape `a`, standardised to mean 0 / variance 1."""
    from scipy.stats import skewnorm
    d = a / np.sqrt(1.0 + a * a)
    m = d * np.sqrt(2.0 / np.pi)
    s = np.sqrt(1.0 - m * m)
    return (skewnorm.rvs(a, size=n, random_state=rng) - m) / s


def shape_matched_verdict(y, mu, sigma, k: int, reps: int, seed: int) -> dict:
    """Place the VARIANCE statistics inside the shape-matched null (LOCK 4c).

    Also reports the skew-normal-fitted variant as the pre-registered SENSITIVITY, and the ratio of
    the two nulls' widths — the number that says HOW MUCH of the Normal null's verdict was an
    artefact of assuming the wrong shape.
    """
    obs = variance_stats(y, mu, sigma, k)
    pool = standardized_shape_pool(y, mu, sigma)
    nd = calibrated_null(
        lambda r: variance_stats(draw_shape_matched(mu, sigma, pool, r), mu, sigma, k), reps, seed)
    out = {"null": null_verdict(obs, nd, list(VARIANCE_STATS)), "observed": obs,
           "pool_excess_kurtosis": float(_excess_kurtosis(pool)),
           "pool_skew": float(_skew(pool))}
    # declared sensitivity — a PARAMETRIC shape instead of the resampled one
    nd_sn = calibrated_null(
        lambda r: variance_stats(
            np.asarray(mu, float) + np.asarray(sigma, float)
            * _standardized_skewnorm(SKEW_CONTROL_ALPHA, len(mu), r), mu, sigma, k), reps, seed)
    out["sensitivity_skewnorm"] = null_verdict(obs, nd_sn, list(VARIANCE_STATS))
    out["null_width"] = {
        kk: float(np.quantile(nd[kk], 1 - ALPHA / 2) - np.quantile(nd[kk], ALPHA / 2))
        for kk in VARIANCE_STATS if kk in nd}
    return out


def _skew(x):
    from scipy.stats import skew
    return skew(np.asarray(x, float))


def _excess_kurtosis(x):
    from scipy.stats import kurtosis
    return kurtosis(np.asarray(x, float))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ LOCK 4a/4d — THE σ-SCALE ESTIMAND, in the actionable unit
# ══════════════════════════════════════════════════════════════════════════════════════════════

def sigma_scale(y, mu, sigma, reps: int, seed: int) -> dict:
    """`ĉ = sqrt(Var(z))` — the multiplier that would make the pooled predictive variance correct.

    "The morning σ is X% too small" is `ĉ − 1`. The CI is a ROW-RESAMPLING bootstrap, which makes no
    distributional assumption at all — deliberately, because the whole scale-vs-shape question is
    about whether a distributional assumption is doing the work.
    """
    y, mu, sigma = np.asarray(y, float), np.asarray(mu, float), np.asarray(sigma, float)
    z = (y - mu) / sigma
    rng = np.random.default_rng(seed)
    n = len(z)
    draws = [float(np.sqrt(np.var(z[rng.integers(0, n, n)], ddof=1))) for _ in range(reps)]
    lo, hi = _boot_ci(draws)
    c = float(np.sqrt(np.var(z, ddof=1)))
    return {"c_hat": c, "pct_too_small": 100.0 * (c - 1.0), "ci_lo": lo, "ci_hi": hi,
            "ci_excludes_one": bool(lo > 1.0 or hi < 1.0), "n": n,
            "var_z": float(np.var(z, ddof=1)),
            "material": bool(abs(np.var(z, ddof=1) - 1.0) >= MATERIAL_VAR_Z_GAP),
            "material_bar": MATERIAL_VAR_Z_GAP}


def out_of_sample_scale(fit: pd.DataFrame, apply_to: pd.DataFrame, reps: int, seed: int) -> dict:
    """⭐ `ĉ` fitted on EARLIER and applied to RECENT.

    An in-sample `ĉ` is BY CONSTRUCTION the value that zeroes its own target — a CEILING, never a
    shippable estimate (the MH2.8 oracle discipline). This is the honest read: does the multiplier
    estimated on one window actually fix the next one?
    """
    if len(fit) < 30 or len(apply_to) < 30:
        return {"evaluable": False, "n_fit": len(fit), "n_apply": len(apply_to)}
    c = sigma_scale(fit["y_total"].values, fit["mu"].values, fit["sigma"].values, reps, seed)
    y, mu, sg = apply_to["y_total"].values, apply_to["mu"].values, apply_to["sigma"].values
    before = float(np.var((y - mu) / sg, ddof=1))
    after = float(np.var((y - mu) / (sg * c["c_hat"]), ddof=1))
    return {"evaluable": True, "n_fit": len(fit), "n_apply": len(apply_to),
            "c_hat_fit": c["c_hat"], "var_z_before": before, "var_z_after": after,
            "gap_before": abs(before - 1.0), "gap_after": abs(after - 1.0),
            "closed": bool(abs(after - 1.0) < abs(before - 1.0))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ LOCK 7 — `games_needed`: the margin stated in the unit that GROWS
# ══════════════════════════════════════════════════════════════════════════════════════════════

def games_needed_for_sigma(mu, sigma, c_true: float, *, reps: int, seed: int,
                           grid=GAMES_GRID, family_size: int = 5) -> dict:
    """At what served `n` does the pooled σ test reach 80% power AT THE BH THRESHOLD it must clear?

    ⭐ The bar is `q/m`, BH's threshold for the SMALLEST p in the family — the only threshold a
    single surviving statistic can be judged against without knowing the others. Reporting power
    against an UNCORRECTED α = 0.05 would be reporting power for a test this study does not run,
    which is exactly the premise's error.

    Larger `n` is synthesised by resampling the observed (μ, σ) pairs — a statement about the
    INSTRUMENT at the observed magnitude, not a test of the model.
    """
    mu, sigma = np.asarray(mu, float), np.asarray(sigma, float)
    rng = np.random.default_rng(seed)
    bar = FDR_Q / max(family_size, 1)
    curve = {}
    for n in grid:
        idx = rng.integers(0, len(mu), n)
        m2, s2 = mu[idx], sigma[idx]
        k = n_strata(n)
        nd = calibrated_null(
            lambda r: {"v": float(np.var((draw_totals(m2, s2, r) - m2) / s2, ddof=1))}, reps, seed)
        d = nd["v"]
        hits = 0
        for _ in range(reps):
            y = draw_totals(m2, s2, rng, sigma_scale=c_true)
            v = float(np.var((y - m2) / s2, ddof=1))
            lo = (1.0 + float(np.sum(d <= v))) / (len(d) + 1.0)
            hi = (1.0 + float(np.sum(d >= v))) / (len(d) + 1.0)
            hits += int(min(1.0, 2.0 * min(lo, hi)) <= bar)
        curve[int(n)] = hits / reps
    hit = [n for n, r in sorted(curve.items()) if r >= TARGET_POWER]
    return {"curve": curve, "c_true": c_true, "bh_threshold": bar, "family_size": family_size,
            "games_needed": (min(hit) if hit else None), "target_power": TARGET_POWER}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE AUDIT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _totals_window(df: pd.DataFrame, seed: int, *, reps: int, boot: bool = True) -> dict:
    y, mu, sg = df["y_total"].values, df["mu"].values, df["sigma"].values
    rng = np.random.default_rng(seed)
    k = n_strata(len(y))
    obs = totals_stats(y, mu, sg, rng, k)
    res = {"obs": obs}
    if boot:
        res["ci"] = bootstrap(
            lambda idx, r: totals_stats(y[idx], mu[idx], sg[idx], r, k), len(y), reps, seed)
    nd = calibrated_null(
        lambda r: totals_stats(draw_totals(mu, sg, r), mu, sg, r, k), reps, seed)
    res["null"] = null_verdict(obs, nd, [
        "pit_mdd", "pit_ks", "cov80", "cov50", "bias", "rmse", "crps",
        "var_z_pooled", "rms_var_z_sigma", "rms_var_z_mean"])
    # ⭐ POSITIVE CONTROLS — the test must FIRE on a known defect at this exact n.
    res["controls"] = {}
    for nm, kw in (("sigma_x1.25", {"sigma_scale": 1.25}), ("mu_plus_0.75", {"mu_shift": 0.75})):
        rc = np.random.default_rng(seed + 7)
        bad = totals_stats(draw_totals(mu, sg, rc, **kw), mu, sg, rc, k)
        res["controls"][nm] = null_verdict(bad, nd, ["pit_mdd", "cov80", "bias",
                                                     "var_z_pooled", "rms_var_z_sigma"])
    # ⭐ THE METHOD LOCK — publish the stratifier validation BEFORE any Var(z) is read.
    resid = y - mu
    res["stratifiers"] = {
        PRIMARY_STRATIFIER: realized_dispersion_table(sg, resid, k),
        SECONDARY_STRATIFIER: realized_dispersion_table(mu, resid, k),
    }
    res["stratifier_power"] = stratifier_games_needed(sg, k)
    # ⭐ LOCK 4c — the shape-matched null, variance statistics ONLY.
    res["shape_matched"] = shape_matched_verdict(y, mu, sg, k, reps, seed)
    # ⭐ the positive control must ALSO fire in the shape-matched null, or that null is not
    #    conservative — it is broken (NF1.7 (a)).
    rc = np.random.default_rng(seed + 7)
    pool = standardized_shape_pool(y, mu, sg)
    nd_sm = calibrated_null(
        lambda r: variance_stats(draw_shape_matched(mu, sg, pool, r), mu, sg, k), reps, seed)
    res["shape_matched"]["controls"] = {
        nm: null_verdict(variance_stats(draw_shape_matched(mu, sg * f, pool, rc), mu, sg, k),
                         nd_sm, list(VARIANCE_STATS))
        for nm, f in (("sigma_x1.25", 1.25), ("sigma_x1.15", 1.15))}
    # ⭐ LOCK 4a — the estimand, in the actionable unit.
    res["sigma_scale"] = sigma_scale(y, mu, sg, reps, seed)
    # ⚠️ POST-HOC diagnosis of the pre-registered PIT flag — excluded from the verdict family.
    res["pit_shape"] = pit_shape_diagnosis(randomized_pit(y, mu, sg, np.random.default_rng(seed)),
                                           (y - mu) / sg)
    return res


def _h2h_window(df: pd.DataFrame, seed: int, *, reps: int, boot: bool = True) -> dict:
    y, p = df["y_home_win"].values, df["p_home"].values
    k = n_strata(len(y))
    obs = h2h_stats(y, p, k)
    res = {"obs": obs}
    if boot:
        res["ci"] = bootstrap(lambda idx, r: h2h_stats(y[idx], p[idx], k), len(y), reps, seed)
    nd = calibrated_null(lambda r: h2h_stats(r.binomial(1, p).astype(float), p, k), reps, seed)
    res["null"] = null_verdict(obs, nd, ["cil", "brier", "reliability", "ece", "log_loss"])
    rc = np.random.default_rng(seed + 7)
    bad = h2h_stats(rc.binomial(1, _shift_p(p, 0.05)).astype(float), p, k)
    res["controls"] = {"p_plus_0.05": null_verdict(bad, nd, ["cil", "brier", "ece"])}
    return res


def _verdict_family(t: dict, win: str) -> tuple[tuple[str, ...], str | None]:
    """The totals verdict family, minus any statistic the method lock DISQUALIFIES (MH2.6)."""
    strat = (t["totals"][win].get("stratifiers") or {}).get(PRIMARY_STRATIFIER) or {}
    if strat.get("valid"):
        return VERDICT_STATS_TOTALS, None
    return (tuple(s for s in VERDICT_STATS_TOTALS if s != "rms_var_z_sigma"),
            f"`rms_var_z_sigma` DROPPED from the {win} verdict family — the primary stratifier "
            f"failed its validation (ρ = {_f(strat.get('spearman_rho'), 3)}), so no Var(z) may be "
            f"read off it")


def _bh_survivors(t: dict, win: str) -> tuple[dict, tuple[str, ...], str | None]:
    fam_t, note = _verdict_family(t, win)
    pv, origin = {}, {}
    for leg, fam in (("totals", fam_t), ("h2h", VERDICT_STATS_H2H)):
        for k in fam:
            v = (t[leg][win].get("null") or {}).get(k)
            if v and v.get("evaluable"):
                pv[f"{leg}::{k}"] = v["p_two_sided"]
                origin[f"{leg}::{k}"] = (leg, k)
    out = {"totals": [], "h2h": []}
    for key in bh_reject(pv):
        leg, k = origin[key]
        out[leg].append(k)
    return ({m: sorted(v) for m, v in out.items()}, fam_t, note)


def _decide(t: dict, sigma_mde: float | None = None) -> dict:
    """LOCK 8 — the decision rule, fixed before any statistic on this population.

    ⭐ `SHAPE_ARTIFACT` is a DISTINCT, NON-FIRING verdict rather than a caveat attached to a firing
    one. MH2.6's own closing sentence is that firing a scoped σ branch at an unscoped shape defect
    is "fitting noise with extra steps"; making that its own label is what stops the study from
    shipping a σ fix for a defect that is not σ's.

    ⚠️ ⭐ `POWER_LIMITED` IS LOAD-BEARING AND THE FIRST CUT LEFT IT UNREACHABLE. The
    pre-registration's decision table has always carried the row "the MDE cannot resolve the effect
    → POWER_LIMITED — say so in games AND days-to-reach; do not dress it as a clean null", but the
    first implementation of this function had no branch that could assign it, so every
    underpowered window would have been reported as a clean `WITHIN_NOISE`. A pre-registered
    verdict with no reachable branch is the NF1.7 (a) vacuous-check class INSIDE the very study
    written to guard against it. It is implemented here as the committed rule reads: if nothing
    survives the correction AND the observed |ĉ − 1| is smaller than the smallest σ deviation
    detectable at 80% power, the honest label is "this window could not have found an effect of
    the size it measured", not "there is no effect".

    `sigma_mde` is the σ-MDE at this population's n. It depends ONLY on (n, μ, σ) — never on the
    outcomes — so the controls can be handed the same value and judge the SAME rule the real run
    judged (MH2.8: a control that does not mirror the decision rule answers a question the rule
    never asked).
    """
    win = PRIMARY_WINDOW
    survivors, fam, note = _bh_survivors(t, win)
    notes = [note] if note else []
    tw = t["totals"][win]
    sc = tw["sigma_scale"]
    sm = (tw["shape_matched"].get("null") or {}).get("var_z_pooled") or {}

    var_z_survives_normal = "var_z_pooled" in survivors["totals"]
    var_z_outside_shape = bool(sm.get("outside_null"))
    any_survivor = bool(survivors["totals"] or survivors["h2h"])
    # ⭐ the observed effect sits BELOW the smallest effect the window could have detected
    underpowered = bool(sigma_mde is not None
                        and abs(sc["c_hat"] - 1.0) < (float(sigma_mde) - 1.0))
    pit_only = bool(survivors["totals"]) and set(survivors["totals"]) <= {"pit_mdd"} \
        and not survivors["h2h"]

    if var_z_survives_normal and var_z_outside_shape and sc["ci_excludes_one"] and sc["material"]:
        v = "SIGMA_SCALE_DEFECT"
        why = ("the pooled σ scale is outside BOTH the Normal and the shape-matched null, its "
               "bootstrap CI excludes 1, and the gap clears the MH2.5 materiality bar")
    elif var_z_survives_normal and not var_z_outside_shape:
        v = "SHAPE_ARTIFACT"
        why = ("`var_z_pooled` survives the Normal null but NOT the shape-matched null — the flag "
               "is the MH2.8-class SHAPE defect leaking into a variance statistic, not a σ-scale "
               "defect")
    elif var_z_survives_normal and not sc["material"]:
        v, why = "IMMATERIAL", ("the σ gap survives but is smaller than one coverage point "
                               "(the MH2.5 bar)")
    elif pit_only:
        v = "SHAPE_DEFECT"
        why = ("only the PIT flatness statistic survives — the MH2.8 class, on the morning tier; "
               "MH2.8 already ran that study and it did not ship")
    elif any_survivor:
        v, why = "OTHER_MISCALIBRATION", "a statistic survives BH that is neither σ-scale nor shape"
    elif underpowered:
        v = "POWER_LIMITED"
        why = (f"nothing survives the correction, but the observed σ gap (ĉ = {sc['c_hat']:.4f}) "
               f"is SMALLER than the smallest σ deviation this window could detect at 80% power "
               f"(MDE σ × {sigma_mde:.2f}) — the instrument could not have found an effect of the "
               f"size it measured, so this is NOT a clean null")
    else:
        v = "WITHIN_NOISE"
        why = ("no statistic in the declared family survives the multiplicity correction in the "
               "primary window, and the observed σ gap is LARGER than the MDE — so the window "
               "could have found it and did not")
    return {"verdict": v, "reason": why, "window": win,
            "sigma_mde": sigma_mde, "underpowered_for_observed_effect": underpowered,
            "bh_survivors": survivors, "verdict_family": {"totals": list(fam),
                                                          "h2h": list(VERDICT_STATS_H2H)},
            "var_z_survives_normal_null": var_z_survives_normal,
            "var_z_outside_shape_matched_null": var_z_outside_shape,
            "sigma_scale": sc, "fdr_q": FDR_Q, "notes": notes,
            "phase_2_fires": v == "SIGMA_SCALE_DEFECT"}


def _windows(dates: np.ndarray) -> dict:
    uniq = np.array(sorted(set(dates)))
    anchor = uniq[-1]
    return {"anchor": anchor, "era_start": uniq[0],
            "recent_start": anchor - pd.Timedelta(days=RECENT_DAYS - 1).to_pytimedelta()}


def run(*, seed: int = SEED, smoke: bool = False, cache: Path | None = None,
        frame: pd.DataFrame | None = None, reps: int | None = None,
        power_reps: int | None = None, with_power: bool = True,
        with_games_needed: bool = True, sigma_mde: float | None = None,
        windows: tuple[str, ...] = ("FULL", "RECENT", "EARLIER")) -> dict:
    """`frame` injects a served frame directly — used by the controls and the guards to prove this
    machine can return something OTHER than its default verdict (a verdict machine with one
    reachable verdict is the NF1.7 (a) vacuous-check class wearing a study's clothes)."""
    n_null = int(reps) if reps is not None else (max(min_null_reps() + 1, 300) if smoke else N_NULL)
    n_pow = int(power_reps) if power_reps is not None else (60 if smoke else N_POWER)
    if n_null < min_null_reps():
        raise RuntimeError(
            f"{STORY}: reps={n_null} is below the vacuity floor {min_null_reps()}. Below it a "
            f"Monte-Carlo p cannot resolve past BH's strictest threshold, so NO input could ever "
            f"be flagged and the verdict would be WITHIN_NOISE by construction — refusing to "
            f"report a null the instrument could not have contradicted.")

    df = frame if frame is not None else (_smoke_frame(seed) if smoke else pull(cache))
    d = df[df["tier"] == TIER].copy()
    if d.empty:
        raise RuntimeError(f"{STORY}: the served-row pull returned ZERO morning rows — refusing to "
                           f"report a calibration verdict on an empty population.")
    foreign = int((d["model_version"] != MORNING_CHAMPION).sum())
    if foreign != EXPECTED_FOREIGN_STAMP_ROWS:
        raise RuntimeError(
            f"{STORY}: {foreign} morning rows carry a model_version other than "
            f"'{MORNING_CHAMPION}' (pre-registered expectation: {EXPECTED_FOREIGN_STAMP_ROWS}). "
            f"The declared population deviation from MH2.6 has grown — refusing to run silently.")

    w = _windows(d["game_date"].values)
    d["window"] = np.where(d["game_date"] >= w["recent_start"], "RECENT", "EARLIER")
    tot = d[d["totals_model_version"].fillna("") != ROLLED_BACK_TOTALS_STAMP]

    t = {
        "n_served_rows": int(len(d)), "n_totals_rows": int(len(tot)),
        "n_dropped_rolled_back": int(len(d) - len(tot)),
        "era_start": str(w["era_start"]), "anchor": str(w["anchor"]),
        "recent_start": str(w["recent_start"]),
        "n_recent": int((d["window"] == "RECENT").sum()),
        "n_earlier": int((d["window"] == "EARLIER").sum()),
        "n_dates": int(d["game_date"].nunique()),
        "totals": {}, "h2h": {},
    }
    # ⚠️ `windows` exists ONLY so the control sweep can skip the two windows the decision rule never
    #    reads (`_decide` reads the PRIMARY window alone). It is a COST knob, never a scope knob:
    #    a guard test asserts the verdict is byte-identical with and without the extra windows, so
    #    the controls cannot silently judge a cheaper rule than the real run (MH2.8).
    for win, sel in (("FULL", tot), ("RECENT", tot[tot["window"] == "RECENT"]),
                     ("EARLIER", tot[tot["window"] == "EARLIER"])):
        if win in windows and len(sel) >= 30:
            t["totals"][win] = _totals_window(sel, seed, reps=n_null)
    for win, sel in (("FULL", d), ("RECENT", d[d["window"] == "RECENT"]),
                     ("EARLIER", d[d["window"] == "EARLIER"])):
        if win in windows and len(sel) >= 30:
            t["h2h"][win] = _h2h_window(sel, seed, reps=n_null)

    # LOCK 4d — the honest out-of-sample read of the multiplier.
    if {"RECENT", "EARLIER"} <= set(windows):
        t["out_of_sample_scale"] = out_of_sample_scale(
            tot[tot["window"] == "EARLIER"], tot[tot["window"] == "RECENT"], n_null, seed)

    if with_power:
        f = tot
        t["power"] = {
            "n": int(len(f)),
            "sigma_scale": power_curve_totals(f["mu"].values, f["sigma"].values, "var_z_pooled",
                                              (1.02, 1.05, 1.08, 1.10, 1.15, 1.20, 1.25, 1.30),
                                              mode="sigma", seed=seed, reps=n_pow),
            "mu_shift": power_curve_totals(f["mu"].values, f["sigma"].values, "bias",
                                           (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00),
                                           mode="mu", seed=seed, reps=n_pow),
            "p_shift": power_curve_h2h(d["p_home"].values, "cil",
                                       (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10),
                                       seed=seed, reps=n_pow),
        }
    if with_games_needed and "FULL" in t["totals"]:
        c = t["totals"]["FULL"]["sigma_scale"]["c_hat"]
        fam = len(_verdict_family(t, "FULL")[0]) + len(VERDICT_STATS_H2H)
        t["games_needed"] = games_needed_for_sigma(tot["mu"].values, tot["sigma"].values, c,
                                                   reps=n_pow, seed=seed, family_size=fam)

    if sigma_mde is None and with_power:
        sigma_mde = (t.get("power") or {}).get("sigma_scale", {}).get("mde")

    result = {"story": STORY, "best_alpha": BEST_ALPHA, "seed": seed, "smoke": smoke,
              "n_null": n_null, "n_power": n_pow, "tier": TIER, "morning": t}
    # §6 — the verdict-INERT descriptive contrast on the SAME games.
    result["contrast"] = _contrast_block(df)
    result["verdict"] = _decide(t, sigma_mde)
    return result


def sigma_mde_for(mu, sigma, *, reps: int, seed: int) -> float | None:
    """The σ-MDE at this population's n. Depends ONLY on (n, μ, σ) — never on the outcomes.

    Factored out so the CONTROLS can be handed the same number the real run used and therefore
    judge the IDENTICAL decision rule, `POWER_LIMITED` branch included (MH2.8).
    """
    return power_curve_totals(mu, sigma, "var_z_pooled",
                              (1.02, 1.05, 1.08, 1.10, 1.15, 1.20, 1.25, 1.30),
                              mode="sigma", seed=seed, reps=reps).get("mde")


def _contrast_block(df: pd.DataFrame) -> dict:
    """§6 — morning vs post_lineup on the SAME games. VERDICT-INERT BY CONSTRUCTION.

    ⛔ NOT an anchor: post_lineup is not a known-correct reference, merely a model MH2.6 measured
    inside its null, and MH2.1 (b) forbids an incumbent-relative anchor — the absolute σ claim is
    anchored on the analytic truth `Var(z) = 1` and on nothing else.
    ⛔ NOT an information-monotonicity claim: the two served contracts DO NOT NEST (16 vs 15 served
    columns, 7 shared), so the law-of-total-variance argument that would license one does not apply.
    It is reported because `σ_morning − σ_post` is DETERMINISTIC — it involves no outcome at all —
    and so it names a mechanism at zero inferential cost.
    """
    m = df[df["tier"] == TIER][["game_pk", "mu", "sigma", "y_total"]]
    p = df[df["tier"] == CONTRAST_TIER][["game_pk", "mu", "sigma"]]
    j = m.merge(p, on="game_pk", suffixes=("_m", "_p"))
    if j.empty:
        return {"evaluable": False, "n_shared": 0}
    zm = (j["y_total"] - j["mu_m"]) / j["sigma_m"]
    zp = (j["y_total"] - j["mu_p"]) / j["sigma_p"]
    return {
        "evaluable": True, "n_shared": int(len(j)),
        "sigma_mean_morning": float(j["sigma_m"].mean()),
        "sigma_mean_post": float(j["sigma_p"].mean()),
        "mean_sigma_sq_morning": float((j["sigma_m"] ** 2).mean()),
        "mean_sigma_sq_post": float((j["sigma_p"] ** 2).mean()),
        "sigma_cv_morning": float(j["sigma_m"].std(ddof=1) / j["sigma_m"].mean()),
        "sigma_cv_post": float(j["sigma_p"].std(ddof=1) / j["sigma_p"].mean()),
        "pct_games_morning_sigma_narrower": float((j["sigma_m"] < j["sigma_p"]).mean()),
        "var_z_morning": float(np.var(zm, ddof=1)), "var_z_post": float(np.var(zp, ddof=1)),
        "realized_sd": float(np.std(j["y_total"], ddof=1)),
        "contracts_nest": False,
        "note": ("verdict-inert: descriptive mechanism read only — not an anchor, not an "
                 "information-monotonicity claim (the served contracts do not nest)"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ LOCK 7 — CONTROLS. The negative control mirrors the DECISION RULE (MH2.8), not a bare
# "did anything look odd", and the discriminator control is what licenses any scale/shape claim.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def clean_frame(n: int, rng, *, mu_ref=None, sigma_ref=None, sigma_scale: float = 1.0,
                shape_alpha: float | None = None, n_dates: int = 53) -> pd.DataFrame:
    """A synthetic SERVED frame whose predictive is exactly as stated.

    `sigma_scale` corrupts the TRUTH (outcomes drawn wider/narrower than the stated σ) — a known
    defect the instrument must find. `shape_alpha` draws a correctly-SCALED but SKEWED truth — the
    real-world shape, which the instrument must NOT report as a σ-scale defect.
    """
    if mu_ref is None:
        mu = rng.normal(8.9, 0.65, n)
        sg = np.clip(rng.normal(4.29, 0.28, n), 3.2, 6.5)
    else:
        idx = rng.integers(0, len(mu_ref), n)
        mu, sg = np.asarray(mu_ref, float)[idx], np.asarray(sigma_ref, float)[idx]
    if shape_alpha is None:
        eps = rng.normal(0.0, 1.0, n)
    else:
        eps = _standardized_skewnorm(shape_alpha, n, rng)
    p = np.clip(rng.normal(0.505, 0.036, n), 0.02, 0.98)
    days = pd.date_range("2026-06-24", periods=n_dates).date
    return pd.DataFrame({
        "game_pk": np.arange(n), "game_date": np.sort(rng.choice(days, n)), "tier": TIER,
        "model_version": MORNING_CHAMPION, "totals_model_version": MORNING_CHAMPION,
        "mu": mu, "sigma": sg, "p_home": p, "data_source": "feature_store",
        "y_total": np.round(mu + sg * sigma_scale * eps),
        "y_home_win": rng.binomial(1, p).astype(float),
    })


def control_sweep(*, n: int, mu_ref, sigma_ref, reps: int, seed: int,
                  n_clean: int = N_CLEAN_CONTROL, n_shape: int = N_SHAPE_CONTROL,
                  n_detect: int = 8) -> dict:
    """⭐ The instrument's OWN operating characteristics, read through the VERDICT LABEL.

    MH2.8's lesson, applied: a negative control must apply the SHIP RULE's threshold, not a bare
    "who looks closest". So every replicate here runs the WHOLE harness and reads the label Phase 2
    keys on — `SIGMA_SCALE_DEFECT` — rather than asking whether some statistic looked odd.
    """
    # ⭐ the MDE is a function of (n, μ, σ) ONLY, so computing it once and injecting it makes every
    #    control replicate judge the SAME rule the real run judged — `POWER_LIMITED` branch and all.
    #    A control that silently skipped that branch would be measuring a different decision rule
    #    from the one Phase 2 keys on, which is precisely MH2.8's negative-control defect.
    mde = sigma_mde_for(mu_ref, sigma_ref, reps=min(reps, N_POWER), seed=seed)

    def label(fr):
        return run(frame=fr, reps=reps, with_power=False, with_games_needed=False,
                   sigma_mde=mde, windows=("FULL",))["verdict"]["verdict"]

    rng = np.random.default_rng(seed)
    clean = [label(clean_frame(n, rng, mu_ref=mu_ref, sigma_ref=sigma_ref))
             for _ in range(n_clean)]
    # ⭐ THE DISCRIMINATOR CONTROL — correctly scaled, but SKEWED like the real world.
    skewed = [label(clean_frame(n, rng, mu_ref=mu_ref, sigma_ref=sigma_ref,
                                shape_alpha=SKEW_CONTROL_ALPHA))
              for _ in range(n_shape)]
    detect = {}
    for nm, f in (("sigma_x1.25", 1.25), ("sigma_x1.15", 1.15), ("sigma_x0.85", 0.85)):
        detect[nm] = [label(clean_frame(n, rng, mu_ref=mu_ref, sigma_ref=sigma_ref, sigma_scale=f))
                      for _ in range(n_detect)]

    # ⛔ NON-FIRING labels, plural. `POWER_LIMITED` is as non-firing as `WITHIN_NOISE`, so counting
    #    it as a "false positive" would penalise the instrument for correctly declaring that a
    #    small effect is undetectable at this n — the opposite of the honesty the label exists for.
    non_firing = ("WITHIN_NOISE", "POWER_LIMITED")

    def rate(labs, want=None):
        if want is None:
            return float(np.mean([x not in non_firing for x in labs]))
        return float(np.mean([x == want for x in labs]))

    return {
        "n_rows_per_frame": n, "reps": reps, "sigma_mde_injected": mde,
        "negative_control": {
            "n": len(clean), "labels": {x: clean.count(x) for x in sorted(set(clean))},
            "any_defect_label_rate": rate(clean), "bar": CLEAN_FP_BAR,
            "sigma_defect_rate": rate(clean, "SIGMA_SCALE_DEFECT"),
            "sigma_defect_bar": SIGMA_DEFECT_FP_BAR,
            "passed": bool(rate(clean) <= CLEAN_FP_BAR
                           and rate(clean, "SIGMA_SCALE_DEFECT") <= SIGMA_DEFECT_FP_BAR),
        },
        "discriminator_control_skewed_but_correctly_scaled": {
            "n": len(skewed), "shape_alpha": SKEW_CONTROL_ALPHA,
            "labels": {x: skewed.count(x) for x in sorted(set(skewed))},
            "sigma_defect_rate": rate(skewed, "SIGMA_SCALE_DEFECT"),
            "bar": SIGMA_DEFECT_FP_BAR,
            "passed": bool(rate(skewed, "SIGMA_SCALE_DEFECT") <= SIGMA_DEFECT_FP_BAR),
        },
        "detection": {nm: {"labels": {x: v.count(x) for x in sorted(set(v))},
                           "sigma_defect_rate": rate(v, "SIGMA_SCALE_DEFECT"),
                           "any_flag_rate": rate(v)}
                      for nm, v in detect.items()},
        "seed": seed,
    }


def shape_artifact_reachability(*, n: int, mu_ref, sigma_ref, reps: int, seed: int,
                                n_rep: int = 8, t_df: float = 5.0,
                                scales=(1.06, 1.08)) -> dict:
    """⭐ Is the SCALE-vs-SHAPE boundary in the right PLACE, or only in the source?

    The clause-isolation guard proves `SHAPE_ARTIFACT` binds alone at the decision-rule level. That
    is necessary but not sufficient: a discriminator could be reachable in principle and still sit
    at a useless threshold. This probe drives the harness end to end on a world that is BOTH
    heavy-tailed AND genuinely mis-scaled, and sweeps the true scale error across the boundary.

    What it must show is a MONOTONE hand-over: at a scale error small enough that the heavy tail
    can account for it, the verdict should be `SHAPE_ARTIFACT`; as the true error grows past what
    the shape can explain, it must flip to `SIGMA_SCALE_DEFECT`. A discriminator that answered
    `SHAPE_ARTIFACT` at every scale error would be a machine that can never blame σ — the mirror
    image of the premise's error, and just as wrong.
    """
    from scipy.stats import t as tdist

    def frame(rng, scale):
        fr = clean_frame(n, rng, mu_ref=mu_ref, sigma_ref=sigma_ref)
        e = tdist.rvs(t_df, size=n, random_state=rng)
        e = e / np.std(e, ddof=0)
        fr["y_total"] = np.round(fr["mu"].values + fr["sigma"].values * scale * e)
        return fr

    out = {}
    for sc in scales:
        labs = [run(frame=frame(np.random.default_rng(900 + i), sc), reps=reps,
                    with_power=False, with_games_needed=False,
                    windows=("FULL",))["verdict"]["verdict"] for i in range(n_rep)]
        out[f"sigma_x{sc}"] = {"labels": {x: labs.count(x) for x in sorted(set(labs))},
                               "shape_artifact_rate": float(np.mean(
                                   [x == "SHAPE_ARTIFACT" for x in labs])),
                               "sigma_defect_rate": float(np.mean(
                                   [x == "SIGMA_SCALE_DEFECT" for x in labs]))}
    rates = [out[f"sigma_x{sc}"]["sigma_defect_rate"] for sc in scales]
    return {"t_df": t_df, "n_rows_per_frame": n, "reps": reps, "by_scale": out,
            # the hand-over must be monotone in the TRUE scale error, or the boundary is arbitrary
            "hands_over_monotonically": bool(all(a <= b for a, b in zip(rates, rates[1:]))),
            "both_branches_reached": bool(
                any(v["shape_artifact_rate"] > 0 for v in out.values())
                and any(v["sigma_defect_rate"] > 0 for v in out.values()))}


def _smoke_frame(seed: int) -> pd.DataFrame:
    """A tiny synthetic served frame — proves the harness end to end without touching S3."""
    rng = np.random.default_rng(seed)
    m = clean_frame(300, rng)
    p = m.copy()
    p["tier"] = CONTRAST_TIER
    p["model_version"] = CONTRAST_CHAMPION
    p["sigma"] = p["sigma"] * 1.02
    return pd.concat([m, p], ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _power_table(p: dict, unit: str) -> str:
    if not p.get("evaluable"):
        return "_(not evaluable)_\n"
    L = [f"| {unit} | detection rate |", "|---:|---:|"]
    for g, v in p["curve"].items():
        L.append(f"| {g:g} | {v:.2f} |")
    mde = p.get("mde")
    L.append("")
    L.append(f"**MDE at {int(p['target_power'] * 100)}% power: "
             f"{'%g' % mde if mde is not None else '**NOT REACHED on the grid**'}**")
    return "\n".join(L) + "\n"


def write_report(r: dict, controls: dict | None = None) -> Path:
    v, t = r["verdict"], r["morning"]
    full = t["totals"]["FULL"]
    L: list[str] = []
    A = L.append
    A("# MH2.10 — morning-tier (`pre_lineup_v6`) served-calibration audit")
    A("")
    if r.get("smoke"):
        A("> ⛔⛔ **SYNTHETIC SMOKE OUTPUT — NOT THE AUDIT.** Every number below is drawn from a "
          "generated frame and says nothing about the served model. Kept only to prove the report "
          "path runs.")
        A("")
    A(f"**Verdict: `{v['verdict']}`** — {v['reason']}.")
    A("")
    A(f"`best_alpha = 0` · deploy-held · Phase 2 fires: "
      f"**{'YES' if v['phase_2_fires'] else 'NO'}**")
    A("")
    A("> **What this study is.** A calibration audit of the MORNING rows the app ACTUALLY SERVED — "
      "the whole slate, before lineups post — against realized outcomes. It says nothing about win "
      "rate, edge or ROI; at `best_alpha = 0` no bet rode on this model. Pre-registration: "
      "[`mh2_10_preregistration.md`](mh2_10_preregistration.md), committed before any statistic was "
      "computed on this population.")
    A("")
    A("## Population")
    A("")
    A("| | |")
    A("|---|---|")
    A(f"| champion | `{MORNING_CHAMPION}` (E13.11 morning tier) |")
    A(f"| era | {t['era_start']} → {t['anchor']} ({t['n_dates']} dates) |")
    A(f"| served rows | **{t['n_served_rows']}** (RECENT {t['n_recent']} / "
      f"EARLIER {t['n_earlier']}) |")
    A(f"| totals rows | {t['n_totals_rows']} (dropped rolled-back stamp: "
      f"{t['n_dropped_rolled_back']}) |")
    A(f"| primary window | **{PRIMARY_WINDOW}** — the question is a STANDING property |")
    A("")
    A("Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole era is "
      "out of sample** — MH2.1's \"split at the incumbent's fit date\" rule holds by construction.")
    A("")
    A("---")
    A("")
    A("## 1. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read")
    A("")
    A("The exact step whose absence caused the MH2.1 rollback: *a conditional-calibration result is "
      "a property of its stratifier*. Bars are MH2.5's, imported not re-declared.")
    A("")
    for win in ("FULL", "RECENT"):
        if win not in t["totals"]:
            continue
        for nm in (PRIMARY_STRATIFIER, SECONDARY_STRATIFIER):
            role = "PRIMARY" if nm == PRIMARY_STRATIFIER else "SECONDARY"
            A(f"### {win} · `{nm}` ({role})")
            A("")
            A(_strat_table(t["totals"][win]["stratifiers"][nm]))
    sp = full.get("stratifier_power") or {}
    if sp.get("evaluable"):
        A("### Is the partition WRONG, or merely UNDER-POWERED? — stated in games")
        A("")
        A(f"The served morning σ barely varies: **CV {sp['sigma_cv']:.4f}**, extreme-decile ratio "
          f"{sp['sigma_extreme_ratio']:.3f} ⇒ clearing the pre-registered {sp['bar']} SE bar needs "
          f"**≈{sp['games_needed']:,} served games** at `k = {sp['k']}`.")
        A("")
        A("⚠️ ⭐ **But under-power is not this partition's problem.** A merely under-powered "
          "partition has the RIGHT SIGN and too little of it. Read the rank correlation above: it "
          "is **negative**, i.e. in this sample the morning model's σ orders realized dispersion "
          "slightly BACKWARDS. ⇒ the morning σ carries **no usable dynamic-range information**, "
          "and the premise's strongest-looking flag — `rms_var_z_sigma`, p = 0.003 — is "
          "**INADMISSIBLE**, exactly as the pre-registration said it expected to be.")
        A("")
    A("---")
    A("")
    A("## 2. `total_runs` — the calibrated-null placement (the PRIMARY, Normal null)")
    A("")
    for win in ("FULL", "RECENT", "EARLIER"):
        if win not in t["totals"]:
            continue
        A(f"### {win} (n = {t['totals'][win]['obs']['n']})")
        A("")
        A(_null_table(t["totals"][win]["null"]))
    A("⚠️ **These are UNCORRECTED α = 0.05 marks.** The verdict reads them through BH at "
      f"q = {FDR_Q} over the declared family — see §5.")
    A("")
    A("### ⭐ Positive controls — the test is proven able to FIRE at this n")
    A("")
    for nm, cc in (full.get("controls") or {}).items():
        fired = [k for k, x in cc.items() if x.get("outside_null")]
        A(f"- **{nm}** → fires on: {fired or '**nothing**'}")
    A("")
    A("---")
    A("")
    A("## 3. ⭐ SCALE vs SHAPE — the discriminator this study exists to run")
    A("")
    A("### 3a. The σ-scale estimand, in the actionable unit")
    A("")
    sc = full["sigma_scale"]
    A("| | |")
    A("|---|---|")
    A(f"| `ĉ = √Var(z)` | **{sc['c_hat']:.4f}** |")
    A(f"| the morning σ is too small by | **{sc['pct_too_small']:.2f}%** |")
    A(f"| bootstrap 95% CI on `ĉ` | [{sc['ci_lo']:.4f}, {sc['ci_hi']:.4f}] |")
    A(f"| CI excludes 1.0 | {'✅ yes' if sc['ci_excludes_one'] else '⛔ **no**'} |")
    A(f"| `\\|Var(z) − 1\\|` | {abs(sc['var_z'] - 1.0):.4f} vs the MH2.5 materiality bar "
      f"{sc['material_bar']} → {'MATERIAL' if sc['material'] else 'immaterial'} |")
    A("")
    A("The CI is a **row-resampling bootstrap**, which makes no distributional assumption at all — "
      "deliberately, because the whole scale-vs-shape question is about whether a distributional "
      "assumption is doing the work.")
    A("")
    A("### 3b. ⭐ The shape-matched null — why a Normal null is the wrong yardstick here")
    A("")
    sm = full["shape_matched"]
    A(f"Realized standardized residuals on this population: **skew {sm['pool_skew']:.3f}**, "
      f"**excess kurtosis {sm['pool_excess_kurtosis']:.3f}**. The sampling variance of a *variance* "
      "statistic depends on the FOURTH moment (`Var(s²) = σ⁴·(2/(n−1) + κ/n)`), so a null drawn "
      "from a symmetric **Normal** is systematically **too narrow** for `var_z_pooled` whenever the "
      "truth is leptokurtic — i.e. **a SHAPE defect mechanically manufactures apparent SCALE "
      "flags**.")
    A("")
    A("The shape-matched null redraws `y* = μ + σ·ε*` with `ε*` resampled from the observed "
      "standardized residuals **re-scaled to variance exactly 1**, so its null hypothesis is "
      "precisely *\"the σ scale is correct\"*, with the SHAPE carried over as a nuisance. ⛔ It is "
      "applied to the VARIANCE statistics only — using it on the PIT statistics would build the "
      "very shape defect being tested into the null.")
    A("")
    A(_null_table(sm["null"]))
    A("**Declared sensitivity — a parametric (skew-normal) shape instead of the resampled one:**")
    A("")
    A(_null_table(sm["sensitivity_skewnorm"]))
    A("**Null-band width, Normal vs shape-matched** — how much of the Normal null's verdict was an "
      "artefact of assuming the wrong shape:")
    A("")
    A("| statistic | Normal null width | shape-matched width | ratio |")
    A("|---|---:|---:|---:|")
    for kk in VARIANCE_STATS:
        nv = (full["null"] or {}).get(kk) or {}
        w_n = (nv.get("null_hi", float("nan")) - nv.get("null_lo", float("nan"))
               if nv.get("evaluable") else float("nan"))
        w_s = sm["null_width"].get(kk, float("nan"))
        A(f"| `{kk}` | {_f(w_n)} | {_f(w_s)} | "
          f"{_f(w_s / w_n if np.isfinite(w_n) and w_n else float('nan'), 2)}× |")
    A("")
    A("### ⭐ The shape-matched null is proven able to FIRE (it is conservative, not broken)")
    A("")
    for nm, cc in (sm.get("controls") or {}).items():
        fired = [k for k, x in cc.items() if x.get("outside_null")]
        A(f"- **{nm}** → fires on: {fired or '**nothing**'}")
    A("")
    A("### 3c. The honest out-of-sample read of the multiplier")
    A("")
    oos = t.get("out_of_sample_scale") or {}
    if oos.get("evaluable"):
        A("An in-sample `ĉ` is BY CONSTRUCTION the value that zeroes its own target — a CEILING, "
          "never a shippable estimate (the MH2.8 oracle discipline). Fitted on EARLIER, applied "
          "to RECENT:")
        A("")
        A("| | |")
        A("|---|---|")
        A(f"| `ĉ` fitted on EARLIER (n = {oos['n_fit']}) | {oos['c_hat_fit']:.4f} |")
        A(f"| `Var(z)` on RECENT (n = {oos['n_apply']}) before | {oos['var_z_before']:.4f} |")
        A(f"| `Var(z)` on RECENT after applying `ĉ` | {oos['var_z_after']:.4f} |")
        A(f"| gap to 1.0 closed? | {'✅ yes' if oos['closed'] else '⛔ no'} "
          f"({oos['gap_before']:.4f} → {oos['gap_after']:.4f}) |")
    else:
        A("_(not evaluable at this window size)_")
    A("")
    A("---")
    A("")
    A("## 4. `home_win` — the calibrated-null placement")
    A("")
    A("⚠️ **Stated in the pre-registration so it cannot be mistaken for a finding:** the registry "
      "records v6 `home_win` as a confirmed THIN-SIGNAL target (served spread ≈ 0.035), so a flat "
      "reliability curve is the EXPECTED shape, not a defect.")
    A("")
    for win in ("FULL", "RECENT"):
        if win not in t["h2h"]:
            continue
        o = t["h2h"][win]["obs"]
        A(f"### {win} (n = {o['n']})")
        A("")
        A(f"served `p̂` SD **{o['p_sd']:.4f}** · mean `p̂` {o['p_mean']:.4f} vs realized home rate "
          f"{o['y_rate']:.4f} · Brier {o['brier']:.4f} = reliability {o['reliability']:.4f} − "
          f"resolution {o['resolution']:.4f} + uncertainty {o['uncertainty']:.4f}")
        A("")
        A(_null_table(t["h2h"][win]["null"]))
    A("---")
    A("")
    A("## 5. ⭐ The multiplicity correction — what actually survives")
    A("")
    A(f"The declared verdict family, BH-corrected at q = {FDR_Q} across the union, in the primary "
      f"window **{PRIMARY_WINDOW}**:")
    A("")
    A(f"- totals family: {v['verdict_family']['totals']}")
    A(f"- h2h family: {v['verdict_family']['h2h']}")
    A("")
    for n_ in v.get("notes") or []:
        A(f"- ⛔ {n_}")
    A("")
    A(f"**Survivors: totals {v['bh_survivors']['totals'] or 'none'}, "
      f"h2h {v['bh_survivors']['h2h'] or 'none'}.**")
    A("")
    A("| clause | value |")
    A("|---|---|")
    A(f"| `var_z_pooled` survives BH in the Normal null | "
      f"{'✅ yes' if v['var_z_survives_normal_null'] else '⛔ no'} |")
    A(f"| `var_z_pooled` outside the SHAPE-MATCHED null | "
      f"{'✅ yes' if v['var_z_outside_shape_matched_null'] else '⛔ no'} |")
    A(f"| `ĉ` CI excludes 1.0 | {'✅ yes' if sc['ci_excludes_one'] else '⛔ no'} |")
    A(f"| gap clears the MH2.5 materiality bar | {'✅ yes' if sc['material'] else '⛔ no'} |")
    if v.get("sigma_mde") is not None:
        A(f"| ⭐ observed gap vs the MDE | `\\|ĉ − 1\\|` = {abs(sc['c_hat'] - 1):.4f} vs MDE − 1 = "
          f"{v['sigma_mde'] - 1:.4f} → "
          f"{'**BELOW the MDE — undetectable here**' if v['underpowered_for_observed_effect'] else 'above the MDE'} |")
    A("")
    A("---")
    A("")
    A("## 6. Descriptive — morning vs post_lineup on the SAME games (⛔ VERDICT-INERT)")
    A("")
    c = r["contrast"]
    if c.get("evaluable"):
        A("⛔ **Not an anchor** — post_lineup is not a known-correct reference, merely a model MH2.6 "
          "measured inside its null, and MH2.1 (b) forbids an incumbent-relative anchor. ⛔ **Not "
          "an information-monotonicity claim** — the two served contracts **do not nest** (16 vs 15 "
          "served columns, 7 shared), so the law-of-total-variance argument that would license one "
          "does not apply. It is reported because `σ_morning − σ_post` involves **no outcome at "
          "all**, so it names a mechanism at zero inferential cost.")
        A("")
        A("| | morning | post_lineup |")
        A("|---|---:|---:|")
        A(f"| mean σ | {c['sigma_mean_morning']:.4f} | {c['sigma_mean_post']:.4f} |")
        A(f"| mean σ² | {c['mean_sigma_sq_morning']:.4f} | {c['mean_sigma_sq_post']:.4f} |")
        A(f"| σ CV | {c['sigma_cv_morning']:.4f} | {c['sigma_cv_post']:.4f} |")
        A(f"| `Var(z)` | {c['var_z_morning']:.4f} | {c['var_z_post']:.4f} |")
        A("")
        A(f"On the **{c['n_shared']}** games both tiers priced (realized SD "
          f"{c['realized_sd']:.4f}), the morning model — which does not see the posted lineup — "
          f"emits a **narrower** σ than the post-lineup model on "
          f"**{100 * c['pct_games_morning_sigma_narrower']:.1f}%** of them.")
    else:
        A("_(no shared games)_")
    A("")
    A("---")
    A("")
    A("## 7. ⭐ Power — what this window could and could not have detected")
    A("")
    A("A null verdict means \"no defect **larger than the MDE**\". MH2.6 never computed power for "
      "this tier.")
    A("")
    pw = t.get("power") or {}
    if pw:
        A(f"### At the served morning n = {pw['n']}")
        A("")
        A("**σ mis-scale** (detected via pooled `Var(z)`):")
        A("")
        A(_power_table(pw["sigma_scale"], "σ × factor"))
        A("**μ level shift** (detected via `bias`):")
        A("")
        A(_power_table(pw["mu_shift"], "runs"))
        A("**`p̂` shift** (detected via calibration-in-the-large):")
        A("")
        A(_power_table(pw["p_shift"], "probability"))
    gn = t.get("games_needed")
    if gn:
        A("### ⭐ `games_needed` — the margin in the unit that GROWS")
        A("")
        A(f"At the OBSERVED magnitude (`ĉ = {gn['c_true']:.4f}`), the rate at which the pooled σ "
          f"test clears **the BH threshold it must actually clear** "
          f"(`q/m = {gn['bh_threshold']:.4f}` at a family of {gn['family_size']}) — not an "
          f"uncorrected α = 0.05, which is the premise's error:")
        A("")
        A("| served games | detection rate |")
        A("|---:|---:|")
        for g, val in gn["curve"].items():
            A(f"| {g:,} | {val:.2f} |")
        A("")
        need = gn["games_needed"]
        if need:
            days = int(np.ceil(need / max(t["n_served_rows"] / max(t["n_dates"], 1), 1)))
            have_days = int(np.ceil((need - t["n_served_rows"])
                                    / max(t["n_served_rows"] / max(t["n_dates"], 1), 1)))
            A(f"**Games needed at {int(gn['target_power'] * 100)}% power: ≈{need:,}** — against "
              f"{t['n_served_rows']:,} served today. At this era's rate of "
              f"{t['n_served_rows'] / max(t['n_dates'], 1):.1f} morning games/day that is ≈{days:,} "
              f"days of serving in total, i.e. **≈{max(have_days, 0):,} more days**.")
        else:
            A(f"**NOT REACHED on the grid (max {max(gn['curve']):,} games)** at "
              f"{int(gn['target_power'] * 100)}% power.")
        A("")
    if controls:
        A("---")
        A("")
        A("## 8. ⭐ The instrument's OWN measured operating characteristics")
        A("")
        A("A verdict label means nothing until you know how often it appears on a **healthy** "
          "model. Every replicate below runs the WHOLE harness and reads the **verdict label Phase "
          "2 keys on** — MH2.8's lesson that a negative control must apply the ship rule's "
          "threshold, not a bare \"who looks closest\".")
        A("")
        nc = controls["negative_control"]
        A(f"### Negative control — {nc['n']} clean frames at n = "
          f"{controls['n_rows_per_frame']}, σ exactly right")
        A("")
        A("| label | count | rate |")
        A("|---|---:|---:|")
        for lab, cnt in nc["labels"].items():
            A(f"| `{lab}` | {cnt} | {cnt / nc['n']:.3f} |")
        A("")
        A(f"any defect label {nc['any_defect_label_rate']:.3f} (bar {nc['bar']}) · "
          f"⭐ `SIGMA_SCALE_DEFECT` {nc['sigma_defect_rate']:.3f} (bar {nc['sigma_defect_bar']}) "
          f"→ {'✅ PASSED' if nc['passed'] else '⛔ **FAILED**'}")
        A("")
        dc = controls["discriminator_control_skewed_but_correctly_scaled"]
        A(f"### ⭐ The scale/shape discriminator control — {dc['n']} frames, σ **exactly right** "
          f"but the truth SKEWED (α = {dc['shape_alpha']})")
        A("")
        A("This is the control that licenses any scale-vs-shape attribution at all: a correctly "
          "scaled but skewed world must **not** be reported as a σ-scale defect.")
        A("")
        A("| label | count | rate |")
        A("|---|---:|---:|")
        for lab, cnt in dc["labels"].items():
            A(f"| `{lab}` | {cnt} | {cnt / dc['n']:.3f} |")
        A("")
        A(f"`SIGMA_SCALE_DEFECT` {dc['sigma_defect_rate']:.3f} (bar {dc['bar']}) → "
          f"{'✅ PASSED' if dc['passed'] else '⛔ **FAILED**'}")
        A("")
        A("### Detection on KNOWN σ defects at the same settings")
        A("")
        A("| corruption | `SIGMA_SCALE_DEFECT` rate | any-flag rate |")
        A("|---|---:|---:|")
        for nm, dd in controls["detection"].items():
            A(f"| {nm} | {dd['sigma_defect_rate']:.2f} | {dd['any_flag_rate']:.2f} |")
        A("")
    A("---")
    A("")
    A("## 9. Verdict")
    A("")
    A(f"**`{v['verdict']}`** — {v['reason']}.")
    A("")
    A(f"**Phase 2 fires: {'YES' if v['phase_2_fires'] else 'NO'}.** "
      + ("A pre-registered σ-widening on the `pre_lineup` model only is required."
         if v["phase_2_fires"] else
         "⛔ No retrain, no recalibration, no registry edit, no deploy."))
    A("")
    if v["verdict"] == "POWER_LIMITED":
        A("### ⚠️ This is NOT a clean null, and the difference is the whole result")
        A("")
        A("Read the two facts together:")
        A("")
        A(f"1. The measured σ gap is **{sc['pct_too_small']:.2f}%** and it is **MATERIAL** by "
          f"MH2.5's bar — bigger than one coverage point.")
        A(f"2. The smallest σ error this window could have DECLARED at 80% power is "
          f"**{100 * (v['sigma_mde'] - 1):.0f}%**. The effect is smaller than the instrument's "
          f"resolution, so a non-detection here carries **no information against it**.")
        A("")
        A("⭐ **And that MDE is the OPTIMISTIC one, so this label is the conservative call.** The "
          "MDE curve is measured against the UNCORRECTED two-sided null band, while the verdict "
          "requires clearing **BH** over the declared family — a strictly higher bar. The true "
          "BH-corrected MDE is therefore LARGER than the figure quoted, which puts the observed "
          "effect even further below resolution. Using the optimistic MDE makes `POWER_LIMITED` "
          "*harder* to declare, not easier.")
        A("")
        A("⛔ Reporting that as \"the morning σ is fine\" would be false. ⛔ Reporting it as \"the "
          "morning σ is too small\" would be equally false — the pre-registered test does not "
          "support it. The honest statement is the third one: **the effect is real-looking, "
          "consistent, material in size, and NOT DECLARABLE at 655 served games.**")
        A("")
        A("**What \"real-looking\" rests on — three readings that are not the pre-registered test, "
          "and do not substitute for it:**")
        A("")
        vz = {w: t["totals"][w]["obs"]["var_z_pooled"] for w in ("FULL", "RECENT", "EARLIER")
              if w in t["totals"]}
        A(f"1. **Same sign and near-identical size in two INDEPENDENT out-of-sample windows** — "
          f"`Var(z)` = "
          + ", ".join(f"{w} {x:.4f}" for w, x in vz.items())
          + ". A noise artefact has no reason to reproduce to the third decimal across a "
            "disjoint split.")
        if oos.get("evaluable"):
            A(f"2. **The multiplier GENERALISES.** Fitted on EARLIER alone "
              f"(`ĉ` = {oos['c_hat_fit']:.4f}) and applied to RECENT, it moves `Var(z)` "
              f"{oos['var_z_before']:.4f} → {oos['var_z_after']:.4f}. That is an out-of-sample "
              f"read, not the in-sample ceiling.")
        A(f"3. **A coherent mechanism** — §6: on the games both tiers priced, the morning model "
          "emits a NARROWER σ than the post-lineup model, which MH2.6 measured inside its null.")
        A("")
        A("⚠️ ⭐ **None of the three is a pre-registered test, and they are recorded as context, "
          "not as evidence that survived a gate.** Reading them as a finding would be the exact "
          "post-hoc promotion this lineage keeps punishing (E2.1-r); the pre-registered answer is "
          "the one above it, and it is `POWER_LIMITED`.")
        A("")
        gn2 = t.get("games_needed") or {}
        if gn2.get("games_needed"):
            A(f"⭐ **The trigger is REACHABLE BY WAITING, which makes it a live re-test rather than "
              f"a future note (MH2).** ≈{gn2['games_needed']:,} served morning games at the "
              f"observed magnitude — ≈{max(int(np.ceil((gn2['games_needed'] - t['n_served_rows']) / max(t['n_served_rows'] / max(t['n_dates'], 1), 1))), 0):,} "
              f"more days of serving. ⛔ No new modelling, no wider field, no different statistic "
              f"is needed — only games.")
            A("")
    A("### What a Phase 2 would have to be, if the re-test ever declares it")
    A("")
    A("⛔ **Not fired by this study.** Recorded so a successor does not have to re-derive it:")
    A("")
    A("- a σ-widening on the **`pre_lineup` model only** — it is a DIFFERENT model from "
      "post_lineup with a DIFFERENT, non-nesting contract, and MH2.6 measured post_lineup's "
      "variance inside its null. ⛔ post_lineup is not touched.")
    A("- ⚠️ **a per-game σ fix is NOT available on this tier and that is a measured fact, not an "
      "oversight** — §1 shows the served morning σ orders realized dispersion with a NEGATIVE rank "
      "correlation, so there is no validated partition to condition a dynamic-range fix on. The "
      "only admissible shape of fix today is a **global scale multiplier**.")
    A("- the fix must beat **flat-σ as a null-to-beat** (MH2.1's rollback demoted flat-σ from a "
      "proven improvement to a null), carry a matched heteroscedastic foil, and be scored on CRPS "
      "plus the conditional instrument — on a stratifier that has passed its validation first.")
    A("")
    A("⛔ **Deploy-held regardless.** Any promotion carries the MH2.1 landmines: a one-target swap "
      "breaks bundle-assuming consumers (`daily_model_predictions.model_version` is stamped from "
      "`home_win`; `mart_clv_labeled_games` hardcodes `v6`; the backfill idempotency key is "
      "`(game_pk, model_version, retrain_tag)`); serve the **validated object**, never a "
      "re-derivation; and **a registry change ships with the box image on merge to `main` — "
      "merging IS the deploy, with no gate between merge and serve.** `best_alpha = 0`.")
    A("")
    _ABL.mkdir(parents=True, exist_ok=True)
    # ⚠️ A RUNNER THAT WRITES A FIXED OUTPUT PATH CLOBBERS A PRIOR RUN'S ARTIFACT (NF-W2c-CBS), and
    #    this one bit during MH2.10 itself: a `--smoke` invocation run purely to check that the
    #    report code path still compiled OVERWROTE the real served-population report with synthetic
    #    numbers. Nothing errored, and a `--smoke` report is byte-plausible — it has the same
    #    sections, the same verdict vocabulary and a realistic-looking `ĉ`. Scoping the filename to
    #    the run is the cure; the report also carries its own `smoke` banner so a stray copy cannot
    #    be mistaken for the audit.
    stem = "mh2_10_morning_audit" + ("_SMOKE" if r.get("smoke") else "")
    p = _ABL / f"{stem}.md"
    p.write_text("\n".join(L))
    payload = dict(r)
    if controls:
        payload["controls"] = controls
    (_ABL / f"{stem}.json").write_text(json.dumps(payload, indent=2, default=str))
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="MH2.10 morning-tier served-calibration audit")
    ap.add_argument("--smoke", action="store_true", help="synthetic frame; no S3, no Snowflake")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--cache", type=str, default=None, help="parquet cache for the served pull")
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--acceptance", action="store_true",
                    help="ALSO measure the instrument's own operating characteristics (⏱ slow)")
    ap.add_argument("--control-reps", type=int, default=None)
    ap.add_argument("--controls-from", type=str, default=None,
                    help="reuse a PRIOR run's measured controls (⏱ the sweep is ~30 min, and "
                         "re-running it to re-render prose would be pure waste). Reads the "
                         "`controls` block of a previous result JSON.")
    ap.add_argument("--n-clean", type=int, default=N_CLEAN_CONTROL)
    ap.add_argument("--n-shape", type=int, default=N_SHAPE_CONTROL)
    ap.add_argument("--reachability", action="store_true",
                    help="run the scale-vs-shape BOUNDARY probe only, and print its JSON")
    a = ap.parse_args()

    if a.reachability:
        df = _smoke_frame(a.seed) if a.smoke else pull(Path(a.cache) if a.cache else None)
        m = df[df["tier"] == TIER]
        print(json.dumps(shape_artifact_reachability(
            n=len(m), mu_ref=m["mu"].values, sigma_ref=m["sigma"].values,
            reps=a.control_reps or N_NULL, seed=a.seed), indent=2))
        return

    r = run(seed=a.seed, smoke=a.smoke, cache=Path(a.cache) if a.cache else None, reps=a.reps)
    controls = None
    if a.controls_from:
        controls = json.loads(Path(a.controls_from).read_text()).get("controls")
        if not controls:
            raise SystemExit(f"{STORY}: no `controls` block in {a.controls_from} — refusing to "
                             f"render an operating-characteristics section from nothing.")
    if a.acceptance:
        t = r["morning"]["totals"]["FULL"]["obs"]
        df = _smoke_frame(a.seed) if a.smoke else pull(Path(a.cache) if a.cache else None)
        m = df[df["tier"] == TIER]
        controls = control_sweep(
            n=t["n"], mu_ref=m["mu"].values, sigma_ref=m["sigma"].values,
            reps=a.control_reps or r["n_null"], seed=a.seed,
            n_clean=a.n_clean, n_shape=a.n_shape)
        print(json.dumps(controls, indent=2))
    p = write_report(r, controls)
    print(f"[{STORY}] verdict = {r['verdict']['verdict']} — {r['verdict']['reason']}")
    print(f"[{STORY}] report → {p}")


if __name__ == "__main__":
    main()

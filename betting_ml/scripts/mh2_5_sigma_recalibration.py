"""mh2_5_sigma_recalibration.py — MH2.5: make the served totals model's per-game σ GENERALIZE and
WIDEN its dynamic range.

WHY THIS EXISTS
===================================================================================================
The served `total_runs`/`post_lineup` champion is the **v6 NGBoost Normal**. It predicts a per-game
σ, and MH2.1's rollback measured two things about that σ on a VALIDATED stratifier:

  1. **It generalizes only weakly.** RMS |Var(z) − 1| across σ-deciles was ≈0.12 in-sample and
     ≈0.23 out of sample. Its advantage over a constant σ shrank ~60% once out of sample.
  2. **The heteroscedasticity it is trying to express IS REAL and is UNDER-expressed.** Realized SD
     rises **+35%** across the served σ's own deciles while that σ rises only **+23%**.

⇒ the target is "make per-game σ GENERALIZE, and WIDEN its dynamic range", **NOT** "remove it".

⛔ **THE FLAT-σ CONTROL IS A NULL TO BEAT, NOT A PROVEN IMPROVEMENT.** MH2.1 promoted a
homoscedastic arm and was ROLLED BACK the same day; on a validated stratifier flattening measured
WORSE (0.2519 vs 0.2275). Do not carry that claim forward. See `mh2_1_rollback.md` §6.

⛔ **METHOD LOCK — A CONDITIONAL-CALIBRATION RESULT IS A PROPERTY OF ITS STRATIFIER.**
Every Var(z) number in this study is computed over a stratifier that has been VALIDATED first:
the realized-SD-per-bin table is published with its rank correlation and per-bin SE, and the bins
must demonstrably separate realized dispersion. A σ-CV floor, a matched foil and a permutation null
do NOT substitute — MH2.1 had all three and still landed on strata whose ordering did not survive.
A stratifier that fails validation is DISQUALIFIED and no number is read off it (NF1.7 (a): a check
that cannot fail is not a check; an anchor that fails to fit is not a pass).

WHY CRPS AND PIT-KS CANNOT SELECT HERE (the MH2.1 methodological point that SURVIVES)
-------------------------------------------------------------------------------------------------
CRPS is dominated by the MEAN. PIT-KS is a MARGINAL statistic — a model that over-covers the calm
games by exactly as much as it under-covers the volatile ones has a flat pooled PIT and a clean
PIT-KS while being badly miscalibrated CONDITIONALLY. Both are structurally BLIND to a per-game
variance defect. They are reported here as sanity, NEVER as the selection metric.

THE DESIGN, IN ONE PARAGRAPH
-------------------------------------------------------------------------------------------------
Every arm shares the INCUMBENT'S MEAN and differs ONLY in σ. That is the NF-D15 (g′) matched-foil
discipline applied to the whole field: any difference between two arms is attributable to the
variance model and to nothing else. Per purged/embargoed fold we fit ONE NGBoost on the first 80% of
the training rows, hold out the last 20% as an honest CALIBRATION split on which every recalibrator
is fitted, and score on the fold's eval rows. Because all arms — the incumbent included — inherit
the identical handicap, the COMPARISON is exact even though the absolute level is slightly
pessimistic relative to the served artifact (MH2.1 (c): keep the handicap identical, never
post-hoc-trim it).

🔒 `best_alpha = 0`. A pricing/calibration study. It says nothing about win rate, edge or ROI.
💸 SNOWFLAKE-FREE AND NETWORK-FREE BY CONSTRUCTION — reads only the local training-matrix parquet
   MH2.1's bake-off already cached, and HALTS rather than pulling if it is absent.

Usage:
    uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py --smoke      # harness check
    uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py              # PRIMARY (8 folds)
    uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py --exclude-seasons 2020  # control
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
_JSON_DIR = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"
_CACHE = PROJECT_ROOT / "betting_ml/data/cache/edge_e1_training_from2016.parquet"

STORY = "MH2.5"
BEST_ALPHA = 0
TARGET, TIER = "total_runs", "post_lineup"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PRE-REGISTRATION — every constant below is fixed in SOURCE before any arm is scored.
# A choice made after seeing a score is window-shopping, which is the defect MH2 exists to stop.
# ══════════════════════════════════════════════════════════════════════════════════════════════

# LOCK 1 — THE WINDOW. Identical to MH2.1's, so the two studies are directly comparable.
#   PRIMARY:     min_year = 2016, 2020 KEPT (11 seasons ⇒ 8 purged folds).
#   SENSITIVITY: 2020 dropped from BOTH train and eval (⇒ 7 folds), run as a DECLARED control.
MH25_MIN_YEAR = 2016
MH25_SENSITIVITY_EXCLUDE = (2020,)

# LOCK 2 — THE FIELD. DECLARED, NOT DISCOVERED (MH2 §a: "you get to pre-register a family; you do
# not get to discover one"). No arm may be dropped after a score is seen — trimming a field
# post hoc UNDER-taxes DSR and is a second layer of the selection bias DSR exists to deflate.
#
# All nine arms share the incumbent's MEAN and differ only in σ.
#
#   ── the four real candidates, all aiming to WIDEN the dynamic range ──
#   power_widen         σ' = a·σ̄·(σ/σ̄)^γ, (a,γ) fit in-fold by Gaussian NLL. A ONE-shape-parameter
#                       widener that NESTS the incumbent (γ=1) and the flat null (γ=0), so it can
#                       only beat them by finding a γ that genuinely helps out of fold.
#   iso_widen           nonparametric monotone recalibration: isotonic regression of squared
#                       residual on σ, fitted on the calibration split. Can widen arbitrarily.
#   var_glm             a genuinely LEARNED variance head — ridge on log(resid²) over the contract
#                       features, ignoring the incumbent's σ entirely. The direct-learned foil.
#   var_glm_plus_sigma  the same head WITH log σ_incumbent as an extra feature (the combination).
#
#   ── the five anchors, all in the field and all pre-registered to LOSE ──
#   incumbent           the served v6 σ, verbatim. THE BAR.
#   level_only          ⭐ THE MATCHED FOIL (NF-D15 g′). The incumbent's σ multiplied by ONE constant
#                       fitted on the calibration split. Every candidate is level-corrected the same
#                       way, so WITHOUT this arm a candidate could win purely by fixing the LEVEL
#                       while the story claims it fixed the SHAPE. A win must clear BOTH `incumbent`
#                       and `level_only`, or the mechanism is mis-attributed.
#   flat_sigma          ⚠️ THE NULL TO BEAT — a single constant σ (MH2.1's rolled-back winner shape).
#   over_disperse       `level_only` × 1.5 — the `max_width` degenerate (NF1.8 (3)).
#   under_disperse      `level_only` ÷ 1.5 — its mirror. A criterion a degenerate WINS is fatal, so
#                       the metric is proven two-sided by scoring both.
MH25_CANDIDATES = ("power_widen", "iso_widen", "var_glm", "var_glm_plus_sigma")
MH25_ANCHORS = ("incumbent", "level_only", "flat_sigma", "over_disperse", "under_disperse")
MH25_FIELD = MH25_ANCHORS + MH25_CANDIDATES          # n_trials for PBO/DSR = 9
MH25_INCUMBENT_ARM = "incumbent"
MH25_MATCHED_FOIL = "level_only"
MH25_FLAT_NULL = "flat_sigma"
MH25_DEGENERATES = ("over_disperse", "under_disperse")

# LOCK 3 — DIAGNOSTIC ANCHORS ARE **NEVER TRIALS** (MH2.1 (a): the `oracle_floor` DSR-field leak).
# An arm that SEES the realized target drives the cross-trial Sharpe dispersion `V`, and `SR0 = √V·
# z(N)` — so a diagnostic anchor left in the field silently SETS the bar of the gate it exists to
# police. These are scored and reported, and excluded from `n_trials`, from `V` and from PBO.
#
#   oracle_bin  ⭐⭐ **THE INVERSION GATE, AND THE ONLY ARM NOTHING MAY BEAT.** Each bin's REALIZED
#       SD used as that bin's σ, built on the SAME partition the headline is scored over — so it is
#       conditionally calibrated BY CONSTRUCTION, not by fitting. Its score IS the metric's
#       empirical noise floor at this n and k (the analytic figure is reported beside it). An arm
#       beating a CONSTRUCTION is mathematically impossible and means the metric is inverted, so
#       this — and only this — HALTs the run (E2.1-r's oracle-floor discipline, with the floor
#       available in closed form rather than fitted).
#   oracle_<form>  PER-FORM peeking arms, one per candidate (NF-D16 g‴: the forms NEST, so a single
#       ceiling would veto a legitimately-better nested form). ⚠️ **THESE ARE A HEADROOM DIAGNOSTIC,
#       NOT A GATE, AND BEATING ONE IS NOT AN INVERSION.** A peeking oracle is a floor only at
#       matched FAMILY *and* matched SAMPLE (NF1.7 (b)), and here matched sample is often
#       UNOBTAINABLE — an oracle can only be fitted on eval rows, of which there are fewer than the
#       calibration split in most folds. NF-D14 settles the reading: "a winner can LEGITIMATELY beat
#       a peeking oracle at UNMATCHED n." Measured on this harness's own smoke: `iso_widen` beat
#       `oracle_iso`, which is a capacity effect (a high-variance isotonic fit on 400 peeking rows
#       vs an honest fit on 787), NOT a metric inversion — treating it as one would have HALTed a
#       perfectly sound run. Each oracle is nevertheless fitted at the largest matched n available
#       and its `n_oracle_fit` is reported, so the mismatch is visible rather than assumed away.
#       What they measure: how much of the achievable widening the design could learn IN ADVANCE.
#   perm_sigma  the incumbent's σ randomly PERMUTED across eval games. ⭐ REGISTERED IN ADVANCE to
#       DEGRADE to roughly the flat-σ arm's score: permutation destroys the σ↔dispersion link while
#       preserving σ's marginal distribution, so an arm that "works" only because σ is wide (rather
#       than because it is RIGHT) is exposed here. (NF-D16 sibling (1): register the expected
#       behaviour of an anchor in advance, so a near-tie is not presented as a passed test.)
MH25_PER_FORM_CEILING = {
    "power_widen": "oracle_power",
    "iso_widen": "oracle_iso",
    "var_glm": "oracle_var_glm",
    "var_glm_plus_sigma": "oracle_var_glm_plus_sigma",
}
MH25_DIAGNOSTICS = tuple(MH25_PER_FORM_CEILING.values()) + ("oracle_bin", "perm_sigma")

# LOCK 4 — THE SELECTION METRIC AND ITS PARTITION.
# Primary  : RMS |Var(z) − 1| across deciles of a VALIDATED COMMON stratifier, pooled out-of-fold.
#            `Var(z) = 1` in every stratum is ANALYTIC TRUTH for any conditionally-calibrated
#            predictive — no oracle, no fitting, and (MH2.1 (b)) never anchored on the incumbent,
#            because an incumbent-relative metric inverts whenever the incumbent is the defective one.
# Secondary: the Winkler interval score (a PROPER interval score). Central-80% coverage is reported
#            as a FLOOR, ⛔ never as a target (E2.1-r / NF1.8: a coverage TARGET is monotone in
#            widening and the `max_width` degenerate wins it).
# Sanity   : CRPS and PIT-KS, reported and structurally blind — see the module docstring.
N_STRATA = 10
NOMINAL = 0.80

# LOCK 4b — THE COMMON STRATIFIER. Fixed before the candidates exist and controlled by no candidate:
# the INCUMBENT's per-game σ (the partition MH2.1's rollback validated) and, as an independent
# robustness partition, the incumbent's predicted MEAN (mechanistically grounded — for count-like
# totals the variance grows with the level, and it is not a σ model at all, so a result that holds
# on both cannot be a property of any one σ's ordering).
#   ⚠️ Each arm is ALSO profiled on strata from its OWN σ, reported as a DIAGNOSTIC only. An own-σ
#   partition can NEVER be the criterion: a flat-σ arm has no own-σ partition at all, so it would
#   score ~0 by construction — a criterion the degenerate wins outright, which is fatal (NF1.8).
MH25_COMMON_STRATIFIERS = ("incumbent_sigma", "incumbent_mean")
MH25_PRIMARY_STRATIFIER = "incumbent_sigma"

#: ⚠️ **ADDED POST-HOC, ON THE RECORD, AND IT CANNOT SHIP ANYTHING.** The pre-registered primary
#: partition FAILED its own validation on the first full run (realized SD ×1.03 across a σ range of
#: ×1.54), which the pre-registration did not anticipate and which has an obvious candidate
#: explanation the pre-registration also did not anticipate: **pooled σ deciles over eleven seasons
#: sort largely by ERA**, and the 2016→2026 run environment moved far more than within-season
#: volatility does. So a partition that mixes eras can show a wide σ range against a flat realized-SD
#: range while the WITHIN-era ordering is perfectly informative — which is exactly the population
#: `mh2_1_rollback.md` §3 validated on (2026 alone). This partition ranks σ WITHIN each fold and
#: pools the ranks, removing the era channel.
#:   ⛔ It is a DIAGNOSTIC. It was chosen after seeing that the primary failed, so a win on it would
#:   be window-shopping (MH2 §a). It may inform this record and a successor's PRE-registration; it
#:   may never produce a ship. The harness enforces that: nothing can ship when the pre-registered
#:   primary is disqualified, whatever any other partition says.
MH25_POSTHOC_STRATIFIERS = ("incumbent_sigma_within_fold",)

# LOCK 4c — THE STRATIFIER-VALIDATION BAR, stated before it is measured. A partition is admissible
# only if realized dispersion demonstrably RISES across its bins. MH2.1's rollback measured
# ρ ≈ 0.66 on the served σ; the bar is set well below that so it tests admissibility rather than
# re-asserting the known answer, and the full table (n, mean stratifier, realized SD, per-bin SE)
# is published whether it passes or fails.
STRATIFIER_MIN_RHO = 0.30
#: The endpoint separation must also exceed this many pooled standard errors — a rank correlation
#: alone can be driven by a monotone but negligible trend.
STRATIFIER_MIN_ENDPOINT_SE = 2.0

# LOCK 5 — THE PRACTICALLY-MEANINGFUL EFFECT, derived from a SERVING quantity and fixed in advance
# (the NF1.8 discipline: a threshold reverse-engineered from the answer is not a threshold).
# A Var(z) of `v` turns a nominal central-80% interval into realized coverage 2Φ(1.2816/√v) − 1.
# One percentage point of coverage error corresponds to |v − 1| ≈ 0.045. So an RMS |Var(z) − 1|
# improvement smaller than 0.05 is worth LESS THAN ONE COVERAGE POINT across the volatility range
# and is not a pricing-relevant improvement, however significant it may be.
MH25_MEANINGFUL_RMS_GAIN = 0.05

# LOCK 6 — DEFLATION. Unchanged from the program's standing bars.
PBO_MAX = 0.2
DSR_MIN_CONF = 0.95
BH_Q = 0.05

# LOCK 7 — THE CALIBRATION SPLIT. The last 20% of each fold's TRAINING rows by date, held out from
# the NGBoost fit so every recalibrator is fitted on HONEST out-of-sample residuals. Fitting a σ
# recalibration on in-sample residuals would systematically SHRINK σ — the exact opposite of this
# story's target — so this split is load-bearing, not hygiene.
CAL_FRACTION = 0.20

# LOCK 8 — CANDIDATE HYPERPARAMETERS, fixed in advance (no tuning pass; §0.5's Optuna step is not
# part of this story, and a two-parameter shape family does not warrant one).
GAMMA_BOUNDS = (0.0, 3.0)      # γ=0 is the flat null, γ=1 the incumbent, γ>1 a WIDENER
RIDGE_ALPHA = 1.0
DEGENERATE_K = 1.5             # the over/under-disperser multiplier
#: σ is clamped to this multiple of the calibration split's mean σ, both ways. A learned variance
#: head can otherwise emit a near-zero σ on one row and dominate every score through it.
SIGMA_CLAMP = (0.3, 3.0)

# LOCK 9 — NOT POINT-IN-TIME. Inherited verbatim from MH2.1 Lock 4 and it still binds.
MH25_POINT_IN_TIME_CAVEAT = (
    "⚠️ **NOT POINT-IN-TIME — every number here is a CEILING.** `load_features` reads each game's "
    "row as it exists NOW (post-game backfilled and dense); the live serve only ever saw the sparse "
    "pre-game row. The honest live figure comes from scoring the ACTUALLY-SERVED predictions, never "
    "from this matrix. This binds the LEVELS; the arm-to-arm COMPARISON is unaffected because every "
    "arm reads the identical matrix."
)

_EULER_LOG_CHI2 = 1.2703628454614782   # −E[log χ²₁]; absorbed by the fitted intercept, kept for docs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The metric, its partition, and the validation the partition must pass FIRST
# ══════════════════════════════════════════════════════════════════════════════════════════════

def realized_dispersion_table(strat: np.ndarray, resid: np.ndarray, k: int = N_STRATA) -> dict:
    """⭐ **THE METHOD LOCK, AS CODE — publish this BEFORE reading any Var(z).**

    Bins `strat` into `k` quantiles and reports, per bin: n, the mean stratifier value, the REALIZED
    SD of the residuals, its standard error, and the mean absolute residual. Then the rank
    correlation of realized SD against the bin index and the endpoint separation in pooled SE.

    A stratifier whose bins do not separate realized dispersion measures NOTHING, and a
    Var(z)-by-stratum statistic computed over it can be silently INVERTED — the E2.1-r inversion
    class raised one level, from the metric to the partition the metric is computed over
    (`mh2_1_rollback.md` §3). The SE of an SD estimate at n is ≈ sd/√(2n).
    """
    from scipy.stats import spearmanr

    strat = np.asarray(strat, float)
    resid = np.asarray(resid, float)
    lab = pd.qcut(pd.Series(strat).rank(method="first"), k, labels=False, duplicates="drop")
    lab = np.asarray(lab, float)
    rows = []
    for s in range(int(np.nanmax(lab)) + 1):
        m = lab == s
        n = int(m.sum())
        if n < 3:
            continue
        sd = float(np.std(resid[m], ddof=1))
        rows.append({
            "bin": int(s), "n": n,
            "mean_stratifier": float(np.mean(strat[m])),
            "realized_sd": sd,
            "realized_sd_se": float(sd / np.sqrt(2.0 * n)),
            "mean_abs_resid": float(np.mean(np.abs(resid[m]))),
        })
    if len(rows) < 3:
        return {"valid": False, "reason": "fewer than 3 populated bins — the partition is degenerate",
                "bins": rows}
    sds = np.array([r["realized_sd"] for r in rows], float)
    rho = float(spearmanr(np.arange(len(sds)), sds).statistic)
    pooled_se = float(np.sqrt(rows[0]["realized_sd_se"] ** 2 + rows[-1]["realized_sd_se"] ** 2))
    endpoint_se = float((sds[-1] - sds[0]) / pooled_se) if pooled_se > 0 else float("nan")
    # the DYNAMIC-RANGE comparison this story exists to close: how far the stratifier moves vs how
    # far realized dispersion actually moves across the same bins.
    # ⚠️ A RANK-valued stratifier (used to strip an era channel) has no meaningful range RATIO —
    # its bins run 0→1 by construction, so the ratio would read ×19 and the "dispersion match"
    # derived from it would be nonsense. Suppress both rather than print an uninterpretable number.
    is_rank = bool(rows[0]["mean_stratifier"] >= 0.0 and rows[-1]["mean_stratifier"] <= 1.0
                   and np.all(np.diff([r["mean_stratifier"] for r in rows]) > 0)
                   and rows[-1]["mean_stratifier"] - rows[0]["mean_stratifier"] > 0.5)
    strat_range = (float("nan") if is_rank else
                   (rows[-1]["mean_stratifier"] / rows[0]["mean_stratifier"]
                    if rows[0]["mean_stratifier"] else float("nan")))
    sd_range = float(sds[-1] / sds[0]) if sds[0] else float("nan")
    valid = bool(rho >= STRATIFIER_MIN_RHO and endpoint_se >= STRATIFIER_MIN_ENDPOINT_SE)
    return {
        "valid": valid,
        "reason": ("realized dispersion rises across the bins" if valid else
                   f"FAILS the pre-registered bar (ρ={rho:.3f} vs {STRATIFIER_MIN_RHO}, endpoints "
                   f"{endpoint_se:.2f} SE apart vs {STRATIFIER_MIN_ENDPOINT_SE}) — DISQUALIFIED, no "
                   f"Var(z) may be read off this partition"),
        "spearman_rho": rho,
        "endpoint_separation_se": endpoint_se,
        "stratifier_is_rank_valued": is_rank,
        "stratifier_range_ratio": strat_range,
        "realized_sd_range_ratio": sd_range,
        "dispersion_match": (float(strat_range / sd_range)
                             if np.isfinite(strat_range) and sd_range else float("nan")),
        "bins": rows,
    }


def _bin_labels(strat: np.ndarray, k: int = N_STRATA) -> np.ndarray:
    return np.asarray(pd.qcut(pd.Series(np.asarray(strat, float)).rank(method="first"),
                              k, labels=False, duplicates="drop"), float)


def rms_var_z(z: np.ndarray, lab: np.ndarray) -> tuple[float, list[dict]]:
    """RMS deviation of per-stratum `Var(z)` from **1.0** — the analytic truth.

    ⛔ Anchored on 1.0, never on the incumbent. MH2.1 (b): when a known-correct reference exists
    analytically, anchor on it — an incumbent-relative metric INVERTS whenever the incumbent is the
    defective one, and can only ever say "different", never "better".
    """
    z = np.asarray(z, float)
    rows = []
    for s in range(int(np.nanmax(lab)) + 1):
        m = lab == s
        if m.sum() < 3:
            continue
        rows.append({"bin": int(s), "n": int(m.sum()), "var_z": float(np.var(z[m], ddof=1))})
    if not rows:
        return float("nan"), rows
    d = np.array([r["var_z"] for r in rows], float) - 1.0
    return float(np.sqrt(np.mean(d ** 2))), rows


def metric_noise_floor(bin_sizes) -> float:
    """The RMS this statistic posts for a PERFECTLY calibrated model at these bin sizes.

    `Var̂` over m draws of a standard normal has variance ≈ 2/(m−1), so a perfect model's RMS
    |Var(z)−1| is ≈ √(mean(2/(m−1))) — strictly positive and shrinking only as √n. Reported beside
    every score because a difference smaller than this floor is not a measurement (the same lesson
    that killed the `max − min` statistic in MH2.1: a range over k noisy estimates measures k and n,
    not miscalibration).
    """
    m = np.asarray([b for b in bin_sizes if b > 1], float)
    return float(np.sqrt(np.mean(2.0 / (m - 1.0)))) if len(m) else float("nan")


def winkler_score(y, lo, hi, alpha: float = 1.0 - NOMINAL) -> np.ndarray:
    """Winkler interval score for a central (1−α) interval — a PROPER interval score (lower better).

    Used as the SECONDARY, not as a coverage target: it penalises width and non-coverage jointly, so
    the `max_width` degenerate cannot win it (E2.1-r's floor-not-target rule, NF1.8's operational
    test).
    """
    y, lo, hi = np.asarray(y, float), np.asarray(lo, float), np.asarray(hi, float)
    w = hi - lo
    return w + (2.0 / alpha) * (np.maximum(lo - y, 0.0) + np.maximum(y - hi, 0.0))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The σ models. Every one is fitted on the CALIBRATION SPLIT only and applied to the eval rows.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _level_fix(sigma_cal: np.ndarray, resid_cal: np.ndarray, sigma_apply: np.ndarray) -> np.ndarray:
    """Scale σ by ONE constant so that `mean(resid²/σ²) = 1` on the calibration split.

    Applied identically to every candidate AND to the `level_only` matched foil, which is what makes
    a candidate's win attributable to the SHAPE of its σ rather than to its LEVEL (NF-D15 g′).
    """
    s = np.maximum(np.asarray(sigma_cal, float), 1e-9)
    a2 = float(np.mean((np.asarray(resid_cal, float) / s) ** 2))
    return np.asarray(sigma_apply, float) * float(np.sqrt(max(a2, 1e-12)))


def _clamp(sigma: np.ndarray, ref_mean: float) -> np.ndarray:
    lo, hi = SIGMA_CLAMP[0] * ref_mean, SIGMA_CLAMP[1] * ref_mean
    return np.clip(np.asarray(sigma, float), lo, hi)


def fit_power(sigma_cal, resid_cal) -> dict:
    """σ' = a · σ̄ · (σ/σ̄)^γ — the parametric WIDENER, fitted by Gaussian NLL.

    For any γ the scale `a` has the closed form `a² = mean(r²/u²)` with `u = σ̄(σ/σ̄)^γ`, so only γ
    needs a 1-D search. The family NESTS the incumbent (γ=1, a≈1) and the flat null (γ=0), which is
    what makes "γ̂ > 1 helps out of fold" a real claim rather than a re-parameterisation.
    """
    s = np.maximum(np.asarray(sigma_cal, float), 1e-9)
    r = np.asarray(resid_cal, float)
    sbar = float(np.mean(s))

    def _nll(g: float) -> float:
        u = sbar * (s / sbar) ** g
        a2 = float(np.mean((r / u) ** 2))
        a2 = max(a2, 1e-12)
        return float(np.sum(np.log(np.sqrt(a2) * u) + (r ** 2) / (2.0 * a2 * u ** 2)))

    grid = np.linspace(GAMMA_BOUNDS[0], GAMMA_BOUNDS[1], 61)
    vals = [_nll(g) for g in grid]
    g0 = float(grid[int(np.argmin(vals))])
    try:                                            # local refinement around the grid minimum
        from scipy.optimize import minimize_scalar
        step = float(grid[1] - grid[0])
        res = minimize_scalar(_nll, bounds=(max(GAMMA_BOUNDS[0], g0 - step),
                                            min(GAMMA_BOUNDS[1], g0 + step)), method="bounded")
        if res.success and np.isfinite(res.fun):
            g0 = float(res.x)
    except Exception:                               # pragma: no cover - refinement is optional
        pass
    u = sbar * (s / sbar) ** g0
    a = float(np.sqrt(max(float(np.mean((r / u) ** 2)), 1e-12)))
    return {"gamma": g0, "a": a, "sigma_bar": sbar}


def apply_power(sigma, p: dict) -> np.ndarray:
    s = np.maximum(np.asarray(sigma, float), 1e-9)
    return p["a"] * p["sigma_bar"] * (s / p["sigma_bar"]) ** p["gamma"]


def fit_iso(sigma_cal, resid_cal):
    """Nonparametric monotone recalibration: isotonic regression of resid² on σ.

    Strictly more flexible than `power_widen` (which it contains as a special case), which is
    precisely why each of the two needs its OWN peeking ceiling — NF-D16 (g‴): one ceiling for
    nesting forms VETOES a legitimately-better nested form as a false metric inversion.
    """
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
    iso.fit(np.asarray(sigma_cal, float), np.asarray(resid_cal, float) ** 2)
    return iso


def apply_iso(sigma, iso) -> np.ndarray:
    return np.sqrt(np.maximum(iso.predict(np.asarray(sigma, float)), 1e-9))


def fit_var_glm(X_cal, resid_cal, sigma_cal=None, *, use_sigma: bool, seed: int = 42):
    """A LEARNED variance head: ridge on `log(resid² + δ)` over the contract features.

    `var_glm` ignores the incumbent's σ entirely — it is the direct-learned foil for the variance,
    the §0.5 requirement that a prescribed structure always face a learned one.
    `var_glm_plus_sigma` adds `log σ_incumbent` as one more feature (the combination).

    The fitted intercept absorbs the `−E[log χ²₁]` offset, and `_level_fix` afterwards removes any
    residual level bias — so this arm competes on the SHAPE of its variance surface only.
    """
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    r2 = np.asarray(resid_cal, float) ** 2
    delta = 0.01 * float(np.mean(r2)) or 1e-6
    Z = _var_glm_design(X_cal, sigma_cal, use_sigma=use_sigma)
    model = make_pipeline(StandardScaler(), Ridge(alpha=RIDGE_ALPHA, random_state=seed))
    model.fit(Z, np.log(r2 + delta))
    return model


def _var_glm_design(X, sigma, *, use_sigma: bool) -> np.ndarray:
    Z = np.asarray(X, float)
    if use_sigma:
        Z = np.column_stack([Z, np.log(np.maximum(np.asarray(sigma, float), 1e-9))])
    return Z


def apply_var_glm(X, sigma, model, *, use_sigma: bool) -> np.ndarray:
    Z = _var_glm_design(X, sigma, use_sigma=use_sigma)
    return np.sqrt(np.maximum(np.exp(np.clip(model.predict(Z), -20.0, 20.0)), 1e-9))


def oracle_bin_sigma(strat_eval: np.ndarray, resid_eval: np.ndarray, k: int = N_STRATA) -> np.ndarray:
    """⛔ PEEKS AT THE TARGET — diagnostic only, never a trial. Each bin's realized SD as its σ.

    On the scoring partition this is calibrated by construction, so its score IS the metric's
    empirical noise floor. Nothing can beat it; anything that does means the metric is inverted
    (E2.1-r's oracle-floor discipline, with the floor available analytically).
    """
    lab = _bin_labels(strat_eval, k)
    out = np.full(len(resid_eval), np.nan, float)
    for s in range(int(np.nanmax(lab)) + 1):
        m = lab == s
        if m.sum() >= 3:
            out[m] = float(np.std(np.asarray(resid_eval, float)[m], ddof=1))
    med = float(np.nanmedian(out)) if np.isfinite(np.nanmedian(out)) else 1.0
    return np.where(np.isfinite(out), out, med)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The run
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _fold_sigmas(df, tr, ev, cols, tcol, *, seed: int, smoke: bool) -> dict:
    """Fit one fold and return every arm's σ on the eval rows, plus the shared μ and diagnostics."""
    from betting_ml.scripts.promotion_gate_eval import NGBoostSpec, _impute

    # LOCK 7 — the honest calibration split: the last CAL_FRACTION of TRAINING rows by date, held
    # out of the fit. Every recalibrator sees only out-of-sample residuals.
    tr = np.asarray(tr)
    order = np.argsort(df.loc[tr, "game_date"].to_numpy(), kind="stable")
    tr = tr[order]
    n_cal = max(int(round(CAL_FRACTION * len(tr))), 200)
    inner, cal = tr[:-n_cal], tr[-n_cal:]

    X_inner, X_rest = _impute(df.loc[inner, cols], df.loc[np.concatenate([cal, np.asarray(ev)]), cols])
    X_cal, X_ev = X_rest.iloc[:len(cal)], X_rest.iloc[len(cal):]
    y_inner = df.loc[inner, tcol].to_numpy(float)
    y_cal = df.loc[cal, tcol].to_numpy(float)
    y_ev = df.loc[ev, tcol].to_numpy(float)

    # 🪤 **`NGBRegressor(random_state=...)` DOES NOT SEED ITS BASE LEARNER.** NGBoost's own
    # `random_state` covers its minibatching and line search; the default base learner is a
    # `DecisionTreeRegressor` constructed with `random_state=None`, which falls back to numpy's
    # GLOBAL RNG to break split ties. Measured on this matrix: two fits of the same class on the
    # SAME rows with the SAME `seed=42` produced per-game σ differing by up to **0.39** — ~9% of σ,
    # comparable to σ's entire cross-game spread AT THAT SCALE (it is far smaller at the real 400
    # estimators — see the `sigma_reproducibility` diagnostic, which measures it rather than
    # assuming). Seeding the global RNG immediately before each fit is what makes this study
    # reproducible; without it the recorded four-decimal figures are not re-derivable.
    # ⚠️ This is not local to MH2.5 — every NGBoost bake-off in the repo inherits it.
    np.random.seed(seed)
    spec = NGBoostSpec(60 if smoke else 400, "Normal", name="ngboost_normal", seed=seed)
    fitted = spec.fit(X_inner, y_inner)
    out_cal, out_ev = fitted.output(X_cal), fitted.output(X_ev)
    mu_cal = np.asarray(out_cal.mean, float)
    s_cal = np.maximum(np.asarray(out_cal.scale, float), 1e-9)
    mu_ev = np.asarray(out_ev.mean, float)
    s_ev = np.maximum(np.asarray(out_ev.scale, float), 1e-9)
    r_cal = y_cal - mu_cal
    r_ev = y_ev - mu_ev
    ref = float(np.mean(s_cal))
    rng = np.random.default_rng(seed)

    def _fit_candidates(X_fit, s_fit, r_fit) -> dict:
        """Fit all four candidate forms on ONE (X, σ, resid) set; return the fitted objects.

        Called TWICE with identical code — once on the honest calibration split (the real arms) and
        once on a matched-size random subsample of the eval fold (the peeking per-form ceilings).
        Sharing the code is what guarantees a ceiling differs from its arm in exactly one respect:
        WHICH rows it was fitted on. Anything else — a level fix applied to one and not the other, a
        different clamp — would make the ceiling an unmatched foil and its verdict meaningless.
        """
        return {
            "power": fit_power(s_fit, r_fit),
            "iso": fit_iso(s_fit, r_fit),
            "var_glm": fit_var_glm(X_fit, r_fit, s_fit, use_sigma=False, seed=seed),
            "var_glm_plus_sigma": fit_var_glm(X_fit, r_fit, s_fit, use_sigma=True, seed=seed),
            "_fit": (X_fit, s_fit, r_fit),
        }

    def _apply_candidates(M: dict, X_to, s_to) -> dict[str, np.ndarray]:
        """Emit each fitted form's σ on an arbitrary row set, level-fixed on ITS OWN fit rows."""
        X_fit, s_fit, r_fit = M["_fit"]
        o = {"power_widen": _clamp(apply_power(s_to, M["power"]), ref),
             "iso_widen": _clamp(_level_fix(apply_iso(s_fit, M["iso"]), r_fit,
                                            apply_iso(s_to, M["iso"])), ref)}
        for nm, use_sigma in (("var_glm", False), ("var_glm_plus_sigma", True)):
            o[nm] = _clamp(_level_fix(
                apply_var_glm(X_fit, s_fit, M[nm], use_sigma=use_sigma), r_fit,
                apply_var_glm(X_to, s_to, M[nm], use_sigma=use_sigma)), ref)
        return o

    sig: dict[str, np.ndarray] = {}
    #  ── anchors ────────────────────────────────────────────────────────────────────────────────
    sig["incumbent"] = s_ev
    sig["level_only"] = _level_fix(s_cal, r_cal, s_ev)
    flat_const = float(np.sqrt(np.mean(s_cal ** 2)))
    sig["flat_sigma"] = _level_fix(np.full(len(s_cal), flat_const), r_cal,
                                   np.full(len(s_ev), flat_const))
    sig["over_disperse"] = sig["level_only"] * DEGENERATE_K
    sig["under_disperse"] = sig["level_only"] / DEGENERATE_K
    #  ── candidates, fitted on the HONEST calibration split ─────────────────────────────────────
    honest = _fit_candidates(X_cal, s_cal, r_cal)
    sig.update(_apply_candidates(honest, X_ev, s_ev))
    #  ── diagnostics (⛔ NOT trials — LOCK 3) ───────────────────────────────────────────────────
    # LOCK 3 / NF1.7 (b): the per-form ceilings PEEK (they are fitted on eval rows) but at MATCHED n
    # — a subsample of the eval fold the same size as the calibration split — because "peeking can
    # only help" holds only at equal family AND equal resolution.
    n_or = min(len(cal), len(ev))
    sub = rng.choice(len(ev), size=n_or, replace=False)
    peeking = _fit_candidates(X_ev.iloc[sub], s_ev[sub], r_ev[sub])
    peek = _apply_candidates(peeking, X_ev, s_ev)
    for arm, ceiling in MH25_PER_FORM_CEILING.items():
        sig[ceiling] = peek[arm]
    sig["oracle_bin"] = _clamp(oracle_bin_sigma(s_ev, r_ev), ref)
    sig["perm_sigma"] = sig["level_only"][rng.permutation(len(s_ev))]

    # the in-fold (calibration-split) σ of each arm, for the GENERALIZATION GAP: an arm that looks
    # good on the rows it was calibrated on and poor out of fold has widened without generalizing,
    # which is the defect MH2.5 exists to fix rather than reproduce.
    p = honest["power"]
    cal_sig = {"incumbent": s_cal, "level_only": _level_fix(s_cal, r_cal, s_cal),
               **_apply_candidates(honest, X_cal, s_cal)}
    return {
        "mu": mu_ev, "y": y_ev, "resid": r_ev, "sigma": sig,
        "cal": {"sigma": cal_sig, "resid": r_cal},
        "power_gamma": p["gamma"], "power_a": p["a"],
        "oracle_power_gamma": peeking["power"]["gamma"], "n_oracle_fit": int(n_or),
        "n_inner": int(len(inner)), "n_cal": int(len(cal)), "n_eval": int(len(ev)),
        "eval_year": int(df.loc[ev, "game_year"].astype(int).iloc[0]),
    }


def _sigma_reproducibility(df, fold, cols, tcol, *, seed: int, smoke: bool) -> dict:
    """Refit the incumbent class twice under DIFFERENT global seeds and compare its per-game σ."""
    from betting_ml.scripts.promotion_gate_eval import NGBoostSpec, _impute

    tr, ev = fold
    Xtr, Xev = _impute(df.loc[tr, cols], df.loc[ev, cols])
    ytr = df.loc[tr, tcol].to_numpy(float)
    sigmas = []
    for sd in (seed, seed + 1):
        np.random.seed(sd)
        out = NGBoostSpec(60 if smoke else 400, "Normal", name="ngboost_normal", seed=seed
                          ).fit(Xtr, ytr).output(Xev)
        sigmas.append(np.asarray(out.scale, float))
    a, b = sigmas
    run_sd = float(np.std(a - b) / np.sqrt(2.0))       # per-game SD of ONE fit's σ around the truth
    cross = float(np.std(np.mean(sigmas, axis=0)))
    return {
        "n_eval": int(len(a)), "seeds": [seed, seed + 1],
        "run_to_run_sd": run_sd, "cross_game_sd": cross,
        "noise_to_signal": float(run_sd / cross) if cross else float("nan"),
        "max_abs_difference": float(np.max(np.abs(a - b))),
        "note": ("Both fits use the IDENTICAL class, rows and `NGBoostSpec(seed=...)`; only numpy's "
                 "GLOBAL RNG differs, which is what the default base `DecisionTreeRegressor` "
                 "actually consumes. `run_to_run_sd` is the per-game SD of a single fit's σ implied "
                 "by the paired difference; `cross_game_sd` is how much σ varies BETWEEN games."),
    }


def _score(y, mu, sigma, lab) -> dict:
    from scipy.stats import kstest, norm

    from betting_ml.utils.promotion_gate import crps_normal

    z = (np.asarray(y, float) - mu) / np.maximum(sigma, 1e-12)
    rms, bins = rms_var_z(z, lab)
    zq = float(norm.ppf(0.5 + NOMINAL / 2.0))
    lo, hi = mu - zq * sigma, mu + zq * sigma
    pit = norm.cdf(z)
    return {
        "rms_abs_var_z_minus_1": rms,
        "bins": bins,
        "pooled_var_z": float(np.var(z, ddof=1)),
        "coverage": float(np.mean((y >= lo) & (y <= hi))),
        "winkler": float(np.mean(winkler_score(y, lo, hi))),
        "crps": float(np.mean(crps_normal(y, mu, sigma))),
        "pit_ks": float(kstest(np.clip(pit, 1e-9, 1 - 1e-9), "uniform").statistic),
        "mean_sigma": float(np.mean(sigma)),
        "sigma_cv": float(np.std(sigma) / np.mean(sigma)) if np.mean(sigma) else float("nan"),
        "sigma_p90_over_p10": (float(np.percentile(sigma, 90) / np.percentile(sigma, 10))
                               if np.percentile(sigma, 10) > 0 else float("nan")),
    }


def run(*, exclude_seasons: tuple[int, ...] = (), seed: int = 42, smoke: bool = False) -> dict:
    if not _CACHE.exists():
        try:
            shown = _CACHE.relative_to(PROJECT_ROOT)
        except ValueError:                                          # pragma: no cover
            shown = _CACHE
        raise SystemExit(
            f"❌ {shown} is absent.\n"
            f"   This script deliberately REFUSES to pull it — a pull would wake the Snowflake\n"
            f"   warehouse, and this diagnostic exists to be free. Run MH2.1's bake-off first\n"
            f"   (it writes this cache), or copy it in from a checkout that has it, then re-run."
        )

    from betting_ml.scripts.e7_9_train_serve_consistency import (
        build_arm_contracts, contract_coverage_by_season, design_bar, dsr_gate,
    )
    from betting_ml.scripts.model_bakeoff import _TARGETS, load_clean_matrix
    from betting_ml.scripts.promotion_gate_eval import make_gate_splitter

    tcol = _TARGETS[TARGET]["col"]
    df = load_clean_matrix(refresh_cache=False, smoke=smoke, min_year=MH25_MIN_YEAR)
    if exclude_seasons:
        keep = ~df["game_year"].astype(int).isin([int(y) for y in exclude_seasons])
        print(f"[{STORY}] LOCK-1 sensitivity: dropping season(s) {list(exclude_seasons)} from BOTH "
              f"train and eval — {int((~keep).sum()):,} of {len(df):,} rows")
        df = df.loc[keep].reset_index(drop=True)
    seasons = sorted(int(s) for s in df["game_year"].unique())

    cols = build_arm_contracts(TARGET, TIER, set(df.columns), family="mh2_1")["incumbent"]
    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=3)
    folds = list(splitter(df))
    n_arms = len(MH25_FIELD)
    print(f"[{STORY}] {TARGET}/{TIER}: {seasons[0]}–{seasons[-1]} ({len(seasons)} seasons) → "
          f"{len(folds)} purged folds · {len(df):,} rows · {len(cols)} contract cols · SNOWFLAKE-FREE")
    print(f"[{STORY}] field ({n_arms} trials): {list(MH25_FIELD)}")
    print(f"[{STORY}] diagnostics (NOT trials): {list(MH25_DIAGNOSTICS)}")
    bar = design_bar(len(folds), n_arms)
    print(f"[{STORY}] LOCK-5 design bar BEFORE any fit: {json.dumps(bar['dsr_required_per_fold_sr_asymptotic_V'])} "
          f"per-fold Sharpe at asymptotic V · PBO evaluable={bar['pbo_evaluable']} · "
          f"DSR ceiling at any effect={bar['dsr_ceiling_at_any_effect']}")

    per_fold, fold_meta = [], []
    for i, (tr, ev) in enumerate(folds, 1):
        f = _fold_sigmas(df, tr, ev, cols, tcol, seed=seed, smoke=smoke)
        per_fold.append(f)
        fold_meta.append({k: f[k] for k in ("eval_year", "n_inner", "n_cal", "n_eval",
                                            "n_oracle_fit", "power_gamma", "power_a",
                                            "oracle_power_gamma")})
        print(f"[{STORY}]   fold {i}/{len(folds)} eval={f['eval_year']} "
              f"(inner {f['n_inner']:,} / cal {f['n_cal']:,} / eval {f['n_eval']:,}) "
              f"γ̂={f['power_gamma']:.3f} (oracle γ={f['oracle_power_gamma']:.3f})")

    all_names = list(MH25_FIELD) + list(MH25_DIAGNOSTICS)
    y = np.concatenate([f["y"] for f in per_fold])
    mu = np.concatenate([f["mu"] for f in per_fold])
    resid = np.concatenate([f["resid"] for f in per_fold])
    sig = {n: np.concatenate([f["sigma"][n] for f in per_fold]) for n in all_names}

    # ── STEP 1 (THE METHOD LOCK): VALIDATE EVERY PARTITION BEFORE READING ANY Var(z) ─────────────
    within = np.concatenate([                       # σ ranked WITHIN each fold, then pooled
        (pd.Series(f["sigma"]["incumbent"]).rank(method="first").to_numpy() - 0.5) / f["n_eval"]
        for f in per_fold])
    strat_values = {"incumbent_sigma": sig["incumbent"], "incumbent_mean": mu,
                    "incumbent_sigma_within_fold": within}
    # ⭐ The construction floor is only a floor ON THE PARTITION IT WAS BUILT AGAINST, so it is
    # rebuilt per partition below rather than once. (Measured while building this harness: a single
    # `oracle_bin` built on the σ partition was BEATEN by five arms when the scoring partition
    # turned out to be the MEAN one, firing the inversion HALT on a sound run — a floor evaluated
    # against the wrong partition is not a floor.)
    sig["oracle_bin"] = oracle_bin_sigma(strat_values[MH25_PRIMARY_STRATIFIER], resid)
    stratifiers = {k: realized_dispersion_table(v, resid) for k, v in strat_values.items()}
    for k, v in stratifiers.items():
        tag = " [POST-HOC]" if k in MH25_POSTHOC_STRATIFIERS else ""
        rng_txt = ("stratifier is rank-valued" if v.get("stratifier_is_rank_valued")
                   else f"vs stratifier range ×{v.get('stratifier_range_ratio'):.3f}")
        print(f"[{STORY}] stratifier `{k}`{tag}: valid={v['valid']} ρ={v.get('spearman_rho'):.3f} "
              f"endpoints {v.get('endpoint_separation_se'):.2f} SE apart · realized-SD range "
              f"×{v.get('realized_sd_range_ratio'):.3f} {rng_txt}")
    primary_ok = stratifiers[MH25_PRIMARY_STRATIFIER]["valid"]

    # ⭐ PER-FOLD validation of the pre-registered primary. A pooled partition can fail because the
    # SIGNAL is absent or because the pooling MIXES ERAS; only the per-fold tables tell them apart,
    # and the pre-registration did not ask for them.
    per_fold_validation = []
    for f in per_fold:
        v = realized_dispersion_table(f["sigma"]["incumbent"], f["resid"], k=5)
        per_fold_validation.append({
            "eval_year": f["eval_year"], "n": f["n_eval"], "valid": v.get("valid"),
            "spearman_rho": v.get("spearman_rho"),
            "endpoint_separation_se": v.get("endpoint_separation_se"),
            "sigma_range_ratio": v.get("stratifier_range_ratio"),
            "realized_sd_range_ratio": v.get("realized_sd_range_ratio"),
            "dispersion_match": v.get("dispersion_match")})

    # ── STEP 2: pooled out-of-fold scores on every VALID partition ───────────────────────────────
    pooled: dict[str, dict] = {}
    for skey, sv in stratifiers.items():
        if not sv["valid"]:
            continue                       # DISQUALIFIED — no number is read off a failed partition
        lab = _bin_labels(strat_values[skey])
        sig_k = {**sig, "oracle_bin": oracle_bin_sigma(strat_values[skey], resid)}
        pooled[skey] = {n: _score(y, mu, sig_k[n], lab) for n in all_names}
        pooled[skey]["_noise_floor"] = metric_noise_floor(
            [r["n"] for r in pooled[skey][MH25_INCUMBENT_ARM]["bins"]])

    # own-σ profiles — DIAGNOSTIC ONLY (LOCK 4b). A flat-σ arm has no own-σ partition, so this can
    # never be a criterion; it answers "does each arm's own σ mean what it says?"
    own_sigma = {}
    for n in all_names:
        if float(np.std(sig[n])) / max(float(np.mean(sig[n])), 1e-9) < 1e-6:
            own_sigma[n] = {"degenerate": True,
                            "note": "σ is constant — it induces no partition, so an own-σ reading "
                                    "would be vacuously perfect. Excluded, never scored as a pass."}
            continue
        v = realized_dispersion_table(sig[n], resid)
        r, _ = rms_var_z((y - mu) / np.maximum(sig[n], 1e-12), _bin_labels(sig[n]))
        own_sigma[n] = {"degenerate": False, "stratifier_valid": v["valid"],
                        "spearman_rho": v["spearman_rho"],
                        "realized_sd_range_ratio": v["realized_sd_range_ratio"],
                        "sigma_range_ratio": v["stratifier_range_ratio"],
                        "dispersion_match": v["dispersion_match"],
                        "rms_abs_var_z_minus_1": r}

    # ── STEP 3: the PER-FOLD series the deflation gates run on ───────────────────────────────────
    # ⭐ Note the per-fold labels for `incumbent_sigma` and its within-fold-ranked sibling are
    # IDENTICAL by construction — ranking σ inside a fold IS that fold's σ order — so the DEFLATION
    # series was era-free all along and the two partitions can differ only at the POOLED level.
    # That is a useful fact, not a shortcut: it localises the pooled primary's failure to the
    # cross-era channel rather than to the per-fold measurement.
    fold_label_source = {"incumbent_sigma": lambda f: f["sigma"]["incumbent"],
                         "incumbent_sigma_within_fold": lambda f: f["sigma"]["incumbent"],
                         "incumbent_mean": lambda f: f["mu"]}
    fold_scores_by_strat: dict[str, dict[str, list[float]]] = {}
    fold_winkler_by_strat: dict[str, dict[str, list[float]]] = {}
    for skey, getter in fold_label_source.items():
        if skey not in pooled:
            continue
        fs = {n: [] for n in all_names}
        fw = {n: [] for n in all_names}
        for f in per_fold:
            lab = _bin_labels(getter(f))
            fsig = {**f["sigma"],
                    "oracle_bin": oracle_bin_sigma(getter(f), f["resid"])}
            for n in all_names:
                sc = _score(f["y"], f["mu"], fsig[n], lab)
                fs[n].append(sc["rms_abs_var_z_minus_1"])
                fw[n].append(sc["winkler"])
        fold_scores_by_strat[skey], fold_winkler_by_strat[skey] = fs, fw

    # ── ⭐ HOW MUCH OF σ's SPREAD IS FIT NOISE? (one extra fit, on the last fold) ────────────────
    # If refitting the SAME class on the SAME rows moves a game's σ by an amount comparable to how
    # much σ varies BETWEEN games, then σ's dynamic range is substantially a fitting artifact — and
    # a partition built on it cannot separate realized dispersion however large its range looks.
    # This is measured rather than inferred because it is the most economical explanation for the
    # pre-registered primary partition failing its own validation.
    repro = _sigma_reproducibility(df, folds[-1], cols, tcol, seed=seed, smoke=smoke)
    print(f"[{STORY}] σ reproducibility (same class, same rows, seeds {seed} vs {seed + 1}): "
          f"run-to-run SD {repro['run_to_run_sd']:.4f} vs cross-game SD {repro['cross_game_sd']:.4f} "
          f"⇒ ratio {repro['noise_to_signal']:.3f}")

    # ── ⭐ THE PREMISE TEST — the single most decisive number in this study ──────────────────────
    # `power_widen` is a WIDENER by construction: γ is free over [0, 3], γ=1 reproduces the served
    # σ, γ>1 widens its dynamic range and γ<1 narrows it. MH2.5's premise says the fitted γ̂ should
    # come out ABOVE 1. Counting which side of 1 it lands on, per fold, tests the premise directly
    # and with no interpretation — and the peeking oracle's γ says the same thing with hindsight.
    gam = [f["power_gamma"] for f in per_fold]
    ogam = [f["oracle_power_gamma"] for f in per_fold]
    dmatch = [v["dispersion_match"] for v in per_fold_validation if np.isfinite(v["dispersion_match"])]
    premise = {
        "premise": "MH2.5 (from mh2_1_rollback.md §3): the served per-game σ UNDER-expresses "
                   "heteroscedasticity, so its dynamic range should be WIDENED.",
        "gamma_bounds": list(GAMMA_BOUNDS),
        "gamma_hat_per_fold": [round(g, 4) for g in gam],
        "oracle_gamma_per_fold": [round(g, 4) for g in ogam],
        "folds": len(gam),
        "folds_fitted_gamma_above_1_WIDENING": int(sum(1 for g in gam if g > 1.0)),
        "folds_fitted_gamma_below_1_NARROWING": int(sum(1 for g in gam if g < 1.0)),
        "folds_oracle_gamma_below_1": int(sum(1 for g in ogam if g < 1.0)),
        "dispersion_match_per_fold": [round(d, 4) for d in dmatch],
        "folds_sigma_range_EXCEEDS_realized_sd_range": int(sum(1 for d in dmatch if d > 1.0)),
        "verdict": ("REFUTED — the widener chose to NARROW" if sum(1 for g in gam if g < 1.0) > len(gam) / 2
                    else "SUPPORTED — the widener chose to widen"),
    }

    # ── ⭐ METRIC DIVERGENCE — do the two pre-registered readings even want the same σ? ───────────
    # `RMS |Var(z)−1|` is a SECOND-MOMENT target; central-80% coverage and the Winkler score are
    # BULK/QUANTILE targets. On a fat-tailed residual they do NOT coincide: the variance is inflated
    # by the tails while the 80% interval is set by the middle, so the σ that makes Var(z)=1 is
    # WIDER than the σ that makes coverage 0.80. Which one matters depends on the serving question —
    # and served `P(over)` at a line is a CDF read NEAR THE MIDDLE, i.e. the quantile regime.
    # Quantified here rather than argued, because the two readings disagreed in this run.
    from scipy.stats import kurtosis as _kurt, norm as _norm
    from scipy.optimize import brentq as _brentq
    z_inc = (y - mu) / np.maximum(sig["incumbent"], 1e-12)
    zq = float(_norm.ppf(0.5 + NOMINAL / 2.0))

    def _cov_at(c: float) -> float:
        return float(np.mean(np.abs(z_inc) <= zq * c))
    try:
        c_cov = float(_brentq(lambda c: _cov_at(c) - NOMINAL, 0.5, 2.0))
    except Exception:                                                        # pragma: no cover
        c_cov = float("nan")
    divergence = {
        "excess_kurtosis_of_z_incumbent": float(_kurt(z_inc, fisher=True)),
        "sigma_multiplier_that_sets_var_z_to_1": float(np.sqrt(np.var(z_inc, ddof=1))),
        "sigma_multiplier_that_sets_coverage_to_0.80": c_cov,
        "note": ("A Normal has excess kurtosis 0 and the two multipliers coincide. The gap below "
                 "is how far the second-moment target and the interval target disagree about how "
                 "wide the served σ should be."),
    }

    # the GENERALIZATION GAP (in-fold calibration split vs out-of-fold eval), the story's other half
    ref_fs = fold_scores_by_strat.get(MH25_PRIMARY_STRATIFIER) or next(iter(
        fold_scores_by_strat.values()))
    gen_gap = {}
    for n in per_fold[0]["cal"]["sigma"]:
        infold, oof = [], []
        for f, of in zip(per_fold, ref_fs[n]):
            cs = f["cal"]["sigma"][n]
            lab_c = _bin_labels(f["cal"]["sigma"]["incumbent"])
            r, _ = rms_var_z(f["cal"]["resid"] / np.maximum(cs, 1e-12), lab_c)
            infold.append(r)
            oof.append(of)
        gen_gap[n] = {"in_fold_rms": float(np.mean(infold)), "out_of_fold_rms": float(np.mean(oof)),
                      "gap": float(np.mean(oof) - np.mean(infold))}

    return _decide(dict(
        seasons=seasons, exclude_seasons=exclude_seasons, folds=len(folds), n_rows=len(df),
        n_eval_rows=int(len(y)), contract_cols=cols, fold_meta=fold_meta, design_bar=bar,
        stratifiers=stratifiers, primary_ok=primary_ok, pooled=pooled, own_sigma=own_sigma,
        per_fold_validation=per_fold_validation, premise=premise, divergence=divergence,
        repro=repro,
        fold_scores_by_strat=fold_scores_by_strat,
        fold_winkler_by_strat=fold_winkler_by_strat, gen_gap=gen_gap, seed=seed,
        smoke=smoke, n_arms=n_arms,
        contract_coverage=contract_coverage_by_season(df, cols),
    ), dsr_gate)


def _decide(R: dict, dsr_gate) -> dict:
    """Apply the pre-registered decision rule. The DEFAULT is INCUMBENT_STANDS."""
    from betting_ml.utils.overfitting import pbo_cscv

    from betting_ml.scripts.e7_9_train_serve_consistency import classify_the_null

    inc, foil = MH25_INCUMBENT_ARM, MH25_MATCHED_FOIL
    prim = MH25_PRIMARY_STRATIFIER
    gates: dict = {}
    result: dict = {
        "story": STORY, "best_alpha": BEST_ALPHA, "target": TARGET, "tier": TIER,
        "seasons": R["seasons"], "excluded_seasons": [int(s) for s in R["exclude_seasons"]],
        "n_folds": R["folds"], "n_rows": R["n_rows"], "n_eval_rows": R["n_eval_rows"],
        "n_arms_in_field": R["n_arms"], "field": list(MH25_FIELD),
        "diagnostic_anchors_excluded_from_deflation": list(MH25_DIAGNOSTICS),
        "contract_cols": R["contract_cols"], "seed": R["seed"], "smoke": R["smoke"],
        "snowflake_free": True, "nominal_coverage": NOMINAL,
        "design_bar": R["design_bar"], "fold_meta": R["fold_meta"],
        "stratifier_validation": R["stratifiers"],
        "per_fold_primary_validation": R["per_fold_validation"],
        "premise_test": R["premise"], "metric_divergence": R["divergence"],
        "sigma_reproducibility": R["repro"],
        "primary_stratifier": prim,
        "posthoc_stratifiers": list(MH25_POSTHOC_STRATIFIERS),
        "pooled": R["pooled"], "own_sigma_diagnostic": R["own_sigma"],
        "per_fold_rms_by_stratifier": {
            sk: {k: [round(x, 5) for x in v] for k, v in fs.items()}
            for sk, fs in R["fold_scores_by_strat"].items()},
        "generalization_gap": R["gen_gap"],
        "point_in_time_caveat": MH25_POINT_IN_TIME_CAVEAT,
        "contract_coverage_by_season": {
            str(k): {"rows": v["rows"], "coverage": v["coverage"],
                     "structurally_absent": v["structurally_absent"]}
            for k, v in R["contract_coverage"].items()},
    }

    # ⛔ THE METHOD LOCK IS A HARD GATE, NOT A REPORT LINE. If the PRE-REGISTERED primary partition
    # fails its own validation, this run cannot ship anything — whatever any other partition says.
    # It may still SCORE, on the best partition that did validate, because a disqualified headline
    # is not a reason to withhold the diagnostic a successor needs; but `binding` stays False and
    # the ship rule is short-circuited, so no amount of downstream green can launder it.
    binding = bool(R["primary_ok"])
    scoring = prim if binding else next(
        (k for k in list(MH25_COMMON_STRATIFIERS) + list(MH25_POSTHOC_STRATIFIERS)
         if k in R["pooled"]), None)
    result["binding"] = binding
    result["scoring_stratifier"] = scoring
    if scoring is None:
        result["verdict"] = "STRATIFIER_DISQUALIFIED"
        result["reading"] = (
            "⛔ **NO VERDICT AND NO SCORES — every candidate partition failed its own validation, "
            "so no Var(z) number in this run may be read at all.** "
            + R["stratifiers"][prim]["reason"] + " This is a refusal, not a null: MH2.1 was rolled "
            "back precisely because a conditional-calibration result was read off a partition "
            "nobody had checked (NF1.7 (a) — an anchor that fails is never a pass).")
        return result

    P = R["pooled"][scoring]
    R["fold_scores"] = R["fold_scores_by_strat"][scoring]
    R["fold_winkler"] = R["fold_winkler_by_strat"][scoring]
    rms = {n: P[n]["rms_abs_var_z_minus_1"] for n in list(MH25_FIELD) + list(MH25_DIAGNOSTICS)}
    floor = P["_noise_floor"]
    real = {n: rms[n] for n in MH25_CANDIDATES}
    leader = min(real, key=real.get)

    # ── ANCHOR CHECKS FIRST. A metric that a degenerate wins, or that beats its own oracle, cannot
    #    select anything — so these are read BEFORE the leader's number (NF1.7 (d)).
    # ⭐ THE INVERSION GATE IS `oracle_bin` ALONE — a CONSTRUCTION, so no capacity argument can
    # excuse beating it. The per-form peeking arms are reported as HEADROOM, never as a gate: at
    # unmatched n a winner may legitimately beat one (NF-D14), and this harness's own smoke produced
    # exactly that.
    floor_ok = {a: bool(rms[a] >= rms["oracle_bin"] - 1e-12) for a in MH25_FIELD}
    anchors = {
        "analytic_noise_floor_of_the_metric": round(floor, 5),
        "oracle_bin_construction_floor": round(rms["oracle_bin"], 5),
        "construction_floor_respected_by_every_arm": bool(all(floor_ok.values())),
        "arms_beating_the_construction_floor": [a for a, ok in floor_ok.items() if not ok],
        "per_form_headroom": {
            a: {"arm": round(rms[a], 5), "peeking_same_form": c, "peeking_score": round(rms[c], 5),
                "headroom": round(rms[a] - rms[c], 5)}
            for a, c in MH25_PER_FORM_CEILING.items()},
        "degenerates_lose_to_leader": {d: bool(rms[leader] < rms[d]) for d in MH25_DEGENERATES},
        "flat_null_loses_to_leader": bool(rms[leader] < rms[MH25_FLAT_NULL]),
        "permutation_anchor": {
            "rms": round(rms["perm_sigma"], 5),
            "flat_sigma_rms": round(rms[MH25_FLAT_NULL], 5),
            "registered_expectation": ("permuting σ destroys the σ↔dispersion link while preserving "
                                       "σ's marginal, so `perm_sigma` was registered in advance to "
                                       "degrade to roughly `flat_sigma`"),
            "degraded_to_flat": bool(abs(rms["perm_sigma"] - rms[MH25_FLAT_NULL])
                                     < max(0.5 * rms[MH25_FLAT_NULL], 2 * floor)),
        },
    }
    result["anchors"] = anchors

    if not anchors["construction_floor_respected_by_every_arm"]:
        result["verdict"] = "METRIC_INVERTED_HALT"
        result["reading"] = (
            f"⛔ **HALT — {anchors['arms_beating_the_construction_floor']} beat `oracle_bin`, which "
            f"assigns each bin its OWN REALIZED SD and is therefore conditionally calibrated BY "
            f"CONSTRUCTION on the very partition the metric is computed over.** Nothing can beat a "
            f"construction, so this is a statement about the METRIC, not about the arms (E2.1-r). "
            f"No winner is crowned.")
        return result

    # ── the pre-registered SHIP rule ────────────────────────────────────────────────────────────
    margin_vs_inc = rms[inc] - rms[leader]
    margin_vs_foil = rms[foil] - rms[leader]
    fold_arr = np.array([[-R["fold_scores"][a][t] for a in MH25_FIELD]      # higher = better
                         for t in range(R["folds"])], float)
    try:
        pbo = pbo_cscv(fold_arr, higher_is_better=True, n_splits=min(16, R["folds"] - (R["folds"] % 2)),
                       seed=R["seed"])
        pbo_val, pbo_note = float(pbo.pbo), None
    except Exception as e:                                                   # pragma: no cover
        pbo_val, pbo_note = float("nan"), f"PBO unevaluable: {e}"
    dsr = dsr_gate({a: R["fold_scores"][a] for a in MH25_FIELD}, inc, leader, n_trials=R["n_arms"])

    # BH-FDR over the four real candidates, paired across folds against the incumbent.
    from scipy.stats import ttest_rel
    tests = []
    for a in MH25_CANDIDATES:
        d = np.array(R["fold_scores"][inc], float) - np.array(R["fold_scores"][a], float)
        t = ttest_rel(np.array(R["fold_scores"][inc], float), np.array(R["fold_scores"][a], float),
                      alternative="greater")
        tests.append({"arm": a, "mean_gain": float(np.mean(d)), "p_one_sided": float(t.pvalue)})
    tests.sort(key=lambda r: r["p_one_sided"])
    m = len(tests)
    bh_pass = False
    for i, t in enumerate(tests, 1):
        t["bh_cutoff"] = BH_Q * i / m
        t["passes_bh"] = bool(t["p_one_sided"] <= t["bh_cutoff"])
        if t["arm"] == leader and t["passes_bh"]:
            bh_pass = True

    fold_wins = int(sum(1 for a, b in zip(R["fold_scores"][inc], R["fold_scores"][leader]) if b < a))
    cov_floor_ok = bool(P[leader]["coverage"] >= min(P[inc]["coverage"], NOMINAL) - 0.01)

    gates = {
        "leader": leader,
        "rms_leader": round(rms[leader], 5),
        "rms_incumbent": round(rms[inc], 5),
        "rms_matched_foil_level_only": round(rms[foil], 5),
        "rms_flat_null": round(rms[MH25_FLAT_NULL], 5),
        "margin_vs_incumbent": round(margin_vs_inc, 5),
        "margin_vs_matched_foil": round(margin_vs_foil, 5),
        "meaningful_gain_required": MH25_MEANINGFUL_RMS_GAIN,
        "beats_incumbent_materially": bool(margin_vs_inc > MH25_MEANINGFUL_RMS_GAIN),
        "beats_matched_foil_materially": bool(margin_vs_foil > MH25_MEANINGFUL_RMS_GAIN),
        "beats_flat_null": anchors["flat_null_loses_to_leader"],
        "beats_both_degenerates": bool(all(anchors["degenerates_lose_to_leader"].values())),
        "pbo": pbo_val, "pbo_max": PBO_MAX,
        "pbo_pass": bool(np.isfinite(pbo_val) and pbo_val < PBO_MAX), "pbo_note": pbo_note,
        "dsr_fixed_convention": dsr,
        "dsr_pass": bool(dsr.get("available") and dsr["dsr"] >= DSR_MIN_CONF),
        "bh_tests": tests, "bh_q": BH_Q, "bh_pass": bh_pass,
        "fold_wins_leader_over_incumbent": fold_wins, "n_folds": R["folds"],
        "coverage_floor_respected": cov_floor_ok,
        "winkler_leader": round(float(np.mean(R["fold_winkler"][leader])), 4),
        "winkler_incumbent": round(float(np.mean(R["fold_winkler"][inc])), 4),
    }
    # ⛔ the short-circuit: a disqualified pre-registered primary means nothing ships, full stop.
    # ── ⭐ DEFLATION SENSITIVITY — NON-BINDING, and it is NOT a rescue ───────────────────────────
    # MH2.1 (a) established that a DIAGNOSTIC anchor must never enter the DSR trial field, because
    # `SR0 = √V·z(N)` scales with the cross-trial Sharpe DISPERSION and an anchor therefore SETS the
    # bar of the gate it exists to police. This run surfaces the MIRROR of that: a pre-registered
    # DEGENERATE anchor — which correctly IS a trial for multiplicity — also sets the bar through V,
    # by LOSING hugely and CONSISTENTLY. `dsr_gate`'s existing guard misses it (it flags |Sharpe| >
    # 10; these sit around −3 and −9).
    #
    # The two requirements that collide are each individually right: NF1.8/NF1.7 demand degenerates
    # in the field to prove the metric is two-sided, and MH2 §a demands the full DECLARED field in
    # `n_trials`. Note `dsr_gate` ALREADY resolves exactly this tension for the reference arm — it
    # keeps the incumbent in `n_trials` while excluding it from `V`, because a designed-constant
    # skill series is not evidence about dispersion. The same argument extends verbatim to arms
    # pre-registered to lose by construction.
    #
    # ⛔ IT IS REPORTED, NOT APPLIED. This convention was not pre-registered here, so using it would
    # be laundering a gate against a result already seen (MH2.2). It exists so the record can say
    # whether the null is EVIDENTIAL or ARITHMETIC, and so a successor can pre-register it.
    from betting_ml.utils.overfitting import deflated_sharpe
    sens: dict = {"binding": False,
                  "why": "V measured over the trial arms EXCLUDING the pre-registered "
                         "lose-by-construction degenerates; n_trials unchanged at the full field"}
    if dsr.get("available"):
        keep = [a for a in dsr["trial_arms"] if a not in MH25_DEGENERATES]
        sh = [t for a, t in zip(dsr["trial_arms"], dsr["trial_sharpes"]) if a in keep]
        lead_series = (np.array(R["fold_scores"][inc], float)
                       - np.array(R["fold_scores"][leader], float))
        alt = deflated_sharpe(lead_series, n_trials=R["n_arms"], trial_sharpes=sh)
        sens.update({
            "trial_sharpes_all": dsr["trial_sharpes"],
            "degenerate_sharpes": [t for a, t in zip(dsr["trial_arms"], dsr["trial_sharpes"])
                                   if a in MH25_DEGENERATES],
            "V_as_gated": dsr["var_trials_sr"],
            "V_excluding_designed_losers": float(np.var(np.asarray(sh, float), ddof=1)),
            "sr0_as_gated": dsr["sr0"], "sr0_excluding_designed_losers": float(alt.sr0),
            "observed_sr": dsr["observed_sr"],
            "dsr_as_gated": dsr["dsr"], "dsr_excluding_designed_losers": float(alt.dsr),
        })
    # NF1.8: a PBO computed over a field that CONTAINS its own nulls measures the nulls. So report
    # the contender-only PBO and the per-fold winner distribution beside the binding figure — a rank
    # statistic cannot tell "my pick is unstable" from "my pick is tied".
    contenders = [a for a in MH25_FIELD if a not in MH25_DEGENERATES]
    try:
        cm = np.array([[-R["fold_scores"][a][t] for a in contenders] for t in range(R["folds"])],
                      float)
        sens["pbo_contenders_only"] = float(pbo_cscv(
            cm, higher_is_better=True, n_splits=min(16, R["folds"] - (R["folds"] % 2)),
            seed=R["seed"]).pbo)
        sens["contender_arms"] = contenders
    except Exception as e:                                                   # pragma: no cover
        sens["pbo_contenders_only"] = float("nan")
        sens["pbo_contenders_note"] = str(e)
    winners: dict[str, int] = {}
    for t in range(R["folds"]):
        wname = min(MH25_FIELD, key=lambda a: R["fold_scores"][a][t])
        winners[wname] = winners.get(wname, 0) + 1
    sens["per_fold_winner_counts"] = winners
    all_r = sorted(rms[a] for a in MH25_FIELD)
    q = all_r[:max(len(all_r) // 4, 2)]
    sens["whole_field_spread"] = round(float(all_r[-1] - all_r[0]), 5)
    sens["contender_spread_top_quartile"] = round(float(q[-1] - q[0]), 5)
    gates["deflation_sensitivity"] = sens

    ship = bool(binding
                and gates["beats_incumbent_materially"] and gates["beats_matched_foil_materially"]
                and gates["beats_flat_null"] and gates["beats_both_degenerates"]
                and gates["pbo_pass"] and gates["dsr_pass"] and gates["bh_pass"]
                and gates["coverage_floor_respected"])
    result["gates"] = gates

    if ship:
        result["verdict"] = "SHIP_RECALIBRATION"
        result["reading"] = (
            f"✅ **`{leader}` clears every pre-registered gate.** RMS |Var(z)−1| "
            f"{rms[inc]:.4f} (served σ) → **{rms[leader]:.4f}**, and — the attribution that matters "
            f"— it also clears the LEVEL-ONLY matched foil ({rms[foil]:.4f}) by "
            f"{margin_vs_foil:.4f}, so the gain is in the SHAPE of σ, not its level (NF-D15 g′). "
            f"PBO {pbo_val:.3f} · DSR {dsr.get('dsr', float('nan')):.4f} · {fold_wins}/{R['folds']} "
            f"folds. ⚠️ `best_alpha = 0`: this is a pricing-calibration improvement and licenses no "
            f"edge, win-rate or ROI claim.")
        return result

    result["verdict"] = "INCUMBENT_STANDS"
    failed = [k for k in ("beats_incumbent_materially", "beats_matched_foil_materially",
                          "beats_flat_null", "beats_both_degenerates", "pbo_pass", "dsr_pass",
                          "bh_pass", "coverage_floor_respected") if not gates[k]]
    result["null_classification"] = classify_the_null(
        metric="crps", n_folds=R["folds"], n_arms=R["n_arms"],
        margin=margin_vs_inc, dsr_fixed=dsr)
    # ⚠️ MH2.2: `classify_null` sees only a TRIAL COUNT and cannot tell a DECLARED narrow family from
    # a DISCOVERED one, so a "re-test at a smaller field" trigger below the declared 9 arms is
    # SUSPECT ADVICE, not a remedy — it would re-commit the selection bias DSR exists to deflate.
    mf = result["null_classification"].get("max_field_size")
    result["null_classification"]["smaller_field_trigger_is_safe"] = bool(
        mf is None or int(mf) >= R["n_arms"])
    result["reading"] = (
        f"⚪ **INCUMBENT_STANDS** — `{leader}` is the best candidate at RMS |Var(z)−1| "
        f"{rms[leader]:.4f} against the served σ's {rms[inc]:.4f} (level-only foil {rms[foil]:.4f}, "
        f"flat null {rms[MH25_FLAT_NULL]:.4f}), and the gate(s) {failed} did not clear. "
        f"The null is classified `{result['null_classification']['state']}`.")
    return result


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _stem(r: dict) -> str:
    return ("mh2_5_sigma_recalibration"
            + ("_no2020" if r["excluded_seasons"] else "")
            + ("_smoke" if r.get("smoke") else ""))


def write_report(r: dict) -> Path:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    stem = _stem(r)
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(r, indent=2, default=float))

    a: list[str] = []
    w = a.append
    w("# MH2.5 — make the served totals model's per-game σ generalize and widen its dynamic range")
    w("")
    w(f"> ⚠️ **Not an edge claim.** `best_alpha = {BEST_ALPHA}`, `bet_paused = true`. A "
      "pricing/calibration study; it says nothing about win rate, edge or ROI.")
    w("")
    w("> 💸 **Snowflake-free and network-free** — reads only the local training-matrix parquet "
      "MH2.1's bake-off already cached, and HALTs rather than pulling if it is absent.")
    w("")
    if r.get("smoke"):
        w("> ⚠️ **SMOKE RUN — rows and estimators capped. A HARNESS CHECK, NOT A RESULT.**")
        w("")
    w(f"**VERDICT: `{r['verdict']}`**")
    w("")
    w(r["reading"])
    w("")
    w(f"- `{r['target']}` / `{r['tier']}` · window **{r['seasons'][0]}–{r['seasons'][-1]}** · "
      f"**{r['n_folds']} purged/embargoed folds** · {r['n_rows']:,} rows "
      f"({r['n_eval_rows']:,} out-of-fold eval rows) · {len(r['contract_cols'])}-column served contract"
      + (f" · **seasons excluded: {r['excluded_seasons']}**" if r["excluded_seasons"] else ""))
    w(f"- Field: **{r['n_arms_in_field']} pre-registered arms** (declared, not discovered) — "
      + ", ".join(f"`{x}`" for x in r["field"]))
    w(f"- Diagnostic anchors, ⛔ **excluded from `n_trials`, from DSR's `V` and from PBO** "
      f"(MH2.1 (a) — a diagnostic anchor is never a trial): "
      + ", ".join(f"`{x}`" for x in r["diagnostic_anchors_excluded_from_deflation"]))
    w("")
    w(r["point_in_time_caveat"])
    w("")

    # ── 0. THE PREMISE TEST ─────────────────────────────────────────────────────────────────────
    pt = r.get("premise_test")
    if pt:
        w("## 0. The premise test — does the widener want to widen?")
        w("")
        w(f"> {pt['premise']}")
        w("")
        w(f"`power_widen` is a WIDENER by construction: γ is free over {pt['gamma_bounds']}, **γ = 1 "
          f"reproduces the served σ exactly, γ > 1 widens its dynamic range, γ < 1 narrows it.** So "
          f"which side of 1 the in-fold NLL fit lands on tests the premise directly, with no "
          f"interpretation and nothing to argue about.")
        w("")
        w(f"**Fitted γ̂ landed BELOW 1 — i.e. the widener chose to NARROW — in "
          f"{pt['folds_fitted_gamma_below_1_NARROWING']} of {pt['folds']} folds** "
          f"(γ̂ = {', '.join(f'{g:.2f}' for g in pt['gamma_hat_per_fold'])}). The **peeking** oracle, "
          f"which is allowed to see the answer, chose γ < 1 in "
          f"{pt['folds_oracle_gamma_below_1']} of {pt['folds']} and lands lower still "
          f"({', '.join(f'{g:.2f}' for g in pt['oracle_gamma_per_fold'])}).")
        w("")
        w(f"Independently, the per-fold dispersion match (σ's own range ÷ the realized-SD range "
          f"across the same bins) exceeds 1 — meaning σ's dynamic range is **WIDER** than the "
          f"dispersion it can resolve — in **{pt['folds_sigma_range_EXCEEDS_realized_sd_range']} of "
          f"{len(pt['dispersion_match_per_fold'])} folds** "
          f"({', '.join(f'{d:.2f}' for d in pt['dispersion_match_per_fold'])}).")
        w("")
        w(f"**⇒ PREMISE {pt['verdict']}.**")
        w("")

    rp = r.get("sigma_reproducibility")
    if rp:
        w("### 0b. 🪤 How much of σ's spread is fit noise?")
        w("")
        w("`NGBRegressor(random_state=...)` seeds NGBoost's own minibatching and line search — **it "
          "does NOT seed the base learner.** The default base is a `DecisionTreeRegressor` built "
          "with `random_state=None`, so it breaks split ties off numpy's GLOBAL RNG. Two fits of "
          "the identical class on the identical rows with the identical `seed` therefore disagree.")
        w("")
        w(f"Measured on the last fold ({rp['n_eval']:,} games), seeds {rp['seeds'][0]} vs "
          f"{rp['seeds'][1]}, everything else held fixed:")
        w("")
        w(f"- per-game **run-to-run SD of σ: {rp['run_to_run_sd']:.4f}** (max single-game "
          f"disagreement **{rp['max_abs_difference']:.3f}**)")
        w(f"- **cross-game SD of σ: {rp['cross_game_sd']:.4f}** — i.e. how much σ actually varies "
          f"between games")
        w(f"- ⇒ **noise-to-signal {rp['noise_to_signal']:.3f}**")
        w("")
        if rp["noise_to_signal"] >= 0.25:
            w("⭐ **This is a live explanation for §1's result:** a σ whose game-to-game variation is "
              "substantially refit noise cannot order games by volatility, however wide its range "
              "looks. It also BOUNDS what any σ study on this class can resolve.")
        else:
            w("⭐ **HYPOTHESIS REFUTED BY ITS OWN MEASUREMENT, and recorded as such.** The obvious "
              "explanation for §1 — \"σ's dynamic range is mostly refit noise, so of course it "
              "cannot order games by volatility\" — is WRONG here: refit noise is only "
              f"**{rp['noise_to_signal']:.1%}** of σ's cross-game spread. The served σ genuinely "
              "varies between games; it simply varies in a way that does not track realized "
              "dispersion out of fold. That is a harder and more interesting finding than a noise "
              "story, and it is why this was measured rather than argued.")
            w("")
            w(f"⚠️ **A SMOKE-SCALE PROBE WOULD HAVE SUPPORTED THE WRONG CONCLUSION.** The same check "
              f"at 120 estimators on 4,000 rows (the scale a `--smoke` harness check runs at) put "
              f"the max single-game disagreement at **0.39** — ~9% of σ — which reads as \"σ is "
              f"mostly noise\". At the real 400 estimators on 14,594 rows it is "
              f"**{rp['max_abs_difference']:.3f}**. Refit noise is capacity- and n-dependent, so a "
              f"reproducibility figure must be quoted at the FITTING SCALE THAT SHIPS.")
        w("")
        w("⚠️ **Not local to MH2.5** — every NGBoost bake-off in this repo inherits it, and any "
          "recorded per-game σ figure produced without seeding the global RNG is not re-derivable. "
          "This harness seeds `np.random.seed(seed)` immediately before each fit; the run above is "
          "reproducible, earlier MH2.x/E7.9/E1.9 σ figures are not.")
        w("")

    # ── 1. THE METHOD LOCK ──────────────────────────────────────────────────────────────────────
    w("## 1. The method lock — the stratifier is validated BEFORE any Var(z) is read")
    w("")
    w("MH2.1 was rolled back because a conditional-calibration result was read off a partition "
      "nobody had checked. A σ-CV floor, a matched foil and a permutation null were all present and "
      "none of them asks the load-bearing question: **do these bins actually separate realized "
      "dispersion?** So that table comes first here, and a partition that fails its pre-registered "
      f"bar (ρ ≥ {STRATIFIER_MIN_RHO} and endpoints ≥ {STRATIFIER_MIN_ENDPOINT_SE} SE apart) is "
      "DISQUALIFIED — no number is read off it.")
    w("")
    for key, v in r["stratifier_validation"].items():
        mark = "✅ VALID" if v["valid"] else "⛔ DISQUALIFIED"
        role = ("**PRE-REGISTERED PRIMARY**" if key == r["primary_stratifier"]
                else "⚠️ **POST-HOC — diagnostic only, cannot ship**"
                if key in r.get("posthoc_stratifiers", []) else "pre-registered secondary")
        w(f"### `{key}` — {mark} · {role}")
        w("")
        w(f"{v['reason']}")
        w("")
        w(f"- Spearman ρ(bin, realized SD) = **{v['spearman_rho']:.3f}** · endpoints "
          f"**{v['endpoint_separation_se']:.2f} SE** apart")
        if v.get("stratifier_is_rank_valued"):
            w(f"- ⭐ **Dynamic range:** realized SD moves **×{v['realized_sd_range_ratio']:.3f}** "
              f"across these bins. (This stratifier is RANK-valued, so it has no meaningful range "
              f"ratio of its own and no dispersion-match figure is quoted.)")
        else:
            w(f"- ⭐ **Dynamic range:** the stratifier moves "
              f"**×{v['stratifier_range_ratio']:.3f}** across its bins while realized SD moves "
              f"**×{v['realized_sd_range_ratio']:.3f}** — a match ratio of "
              f"**{v['dispersion_match']:.3f}** (1.000 = the stratifier expresses exactly as much "
              f"dispersion as there is; **< 1 = UNDER-expressed**, **> 1 = OVER-expressed**, i.e. a "
              f"σ whose dynamic range is wider than the dispersion it can actually resolve).")
        w("")
        w("| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |")
        w("|---:|---:|---:|---:|---:|---:|")
        for b in v["bins"]:
            w(f"| {b['bin']} | {b['n']:,} | {b['mean_stratifier']:.3f} | {b['realized_sd']:.3f} | "
              f"{b['realized_sd_se']:.3f} | {b['mean_abs_resid']:.3f} |")
        w("")

    if r.get("per_fold_primary_validation"):
        w("### The same validation, PER FOLD (quintiles) — pooled failure vs per-fold failure")
        w("")
        w("A pooled partition can fail because the SIGNAL is absent or because the POOLING mixes "
          "eras. Only the per-fold tables tell those apart, and the pre-registration did not ask "
          "for them — they are reported here because the pooled primary failed.")
        w("")
        w("| eval year | n | ρ | endpoints (SE) | σ range | realized-SD range | dispersion match |")
        w("|---:|---:|---:|---:|---:|---:|---:|")
        for v in r["per_fold_primary_validation"]:
            w(f"| {v['eval_year']} | {v['n']:,} | {v['spearman_rho']:+.3f} | "
              f"{v['endpoint_separation_se']:+.2f} | ×{v['sigma_range_ratio']:.3f} | "
              f"×{v['realized_sd_range_ratio']:.3f} | {v['dispersion_match']:.3f} |")
        w("")

    if r["verdict"] == "STRATIFIER_DISQUALIFIED":
        (_ABL / f"{stem}.md").write_text("\n".join(a) + "\n")
        return _ABL / f"{stem}.md"

    prim = r.get("scoring_stratifier") or r["primary_stratifier"]
    P = r["pooled"][prim]
    if not r.get("binding", True):
        w("## ⛔ EVERYTHING BELOW IS NON-BINDING")
        w("")
        w(f"The PRE-REGISTERED primary partition (`{r['primary_stratifier']}`) was DISQUALIFIED "
          f"above, so **nothing in this run can ship, whatever the gates say.** The scores below "
          f"are computed on `{prim}` — reported because a disqualified headline is not a reason to "
          f"withhold the diagnostic a successor needs, and short-circuited in code so no amount of "
          f"downstream green can launder it. Read them as *what a successor would pre-register*, "
          f"never as a result.")
        w("")
    names = list(r["field"]) + list(r["diagnostic_anchors_excluded_from_deflation"])
    leader_name = r.get("gates", {}).get("leader")

    # ── 2. the leaderboard ──────────────────────────────────────────────────────────────────────
    w(f"## 2. Pooled out-of-fold scores on the scoring partition (`{prim}`"
      + ("" if r.get("binding", True) else "  — ⛔ NON-BINDING") + ")")
    w("")
    w("**RMS |Var(z) − 1| is the selection metric** and it is anchored on the ANALYTIC truth "
      "`Var(z) = 1`, never on the incumbent — an incumbent-relative metric inverts whenever the "
      "incumbent is the defective one and can only ever say *different*, never *better* (MH2.1 (b)). "
      "CRPS and PIT-KS are reported as sanity and are structurally BLIND here: CRPS is "
      "mean-dominated and every arm shares the identical mean, and PIT-KS is marginal, so a model "
      "that over-covers the calm games exactly as much as it under-covers the volatile ones passes "
      "it while being badly miscalibrated conditionally.")
    w("")
    w(f"⚠️ The metric's own **noise floor at these bin sizes is {P['_noise_floor']:.4f}** — the RMS a "
      "PERFECTLY calibrated model posts here. A difference smaller than that is not a measurement.")
    w("")
    w("| arm | RMS &#124;Var(z)−1&#124; | pooled Var(z) | Winkler | cov@80% | CRPS | PIT-KS | "
      "mean σ | σ CV | σ p90/p10 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    order = sorted(r["field"], key=lambda n: P[n]["rms_abs_var_z_minus_1"])
    for n in order + ["—"] + list(r["diagnostic_anchors_excluded_from_deflation"]):
        if n == "—":
            w("| *— diagnostics below: NOT trials —* | | | | | | | | | |")
            continue
        s = P[n]
        tag = f"**`{n}`**" if n == leader_name else f"`{n}`"
        w(f"| {tag} | {s['rms_abs_var_z_minus_1']:.4f} | {s['pooled_var_z']:.4f} | "
          f"{s['winkler']:.3f} | {s['coverage']:.4f} | {s['crps']:.4f} | {s['pit_ks']:.4f} | "
          f"{s['mean_sigma']:.3f} | {s['sigma_cv']:.4f} | {s['sigma_p90_over_p10']:.3f} |")
    w("")
    if len(r["pooled"]) > 1:
        w("### Robustness — the same metric on the independent second partition")
        w("")
        w("A result that holds on the incumbent's predicted MEAN as well as on its σ cannot be a "
          "property of any one σ model's ordering.")
        w("")
        for key, PP in r["pooled"].items():
            if key == prim:
                continue
            w(f"| arm | RMS &#124;Var(z)−1&#124; on `{key}` |")
            w("|---|---:|")
            for n in sorted(r["field"], key=lambda x: PP[x]["rms_abs_var_z_minus_1"]):
                w(f"| `{n}` | {PP[n]['rms_abs_var_z_minus_1']:.4f} |")
            w("")

    # ── 3. anchors ──────────────────────────────────────────────────────────────────────────────
    an = r["anchors"]
    w("## 3. The anchors — read these BEFORE the leader's number")
    w("")
    w("A metric a degenerate WINS cannot select anything, and an arm that beats a peeking version of "
      "its own form means the metric is inverted, not that the arm is good. Both are checked here "
      "and both are two-sided.")
    w("")
    w(f"- ⭐ **THE INVERSION GATE — `oracle_bin`, the CONSTRUCTION floor.** Each bin is given its own "
      f"REALIZED SD as σ on the very partition the headline is scored over, so it is conditionally "
      f"calibrated by construction rather than by fitting. It scores "
      f"**{an['oracle_bin_construction_floor']:.4f}** against the analytic noise floor "
      f"**{an['analytic_noise_floor_of_the_metric']:.4f}** — i.e. this is how small a difference is "
      f"even MEASURABLE here. Respected by every arm = "
      f"**{an['construction_floor_respected_by_every_arm']}**"
      + (f" (⛔ violated by {an['arms_beating_the_construction_floor']})"
         if not an["construction_floor_respected_by_every_arm"] else "") + ".")
    w("")
    w("- **PER-FORM peeking arms — a HEADROOM diagnostic, ⛔ NOT a gate.** One per candidate, because "
      "the forms NEST and a single ceiling would veto a legitimately-better nested form (NF-D16 g‴). "
      "⚠️ **Beating one is NOT an inversion**: a peeking oracle is a floor only at matched FAMILY "
      "*and* matched SAMPLE (NF1.7 (b)), and matched sample is often unobtainable here — an oracle "
      "can only be fitted on eval rows, of which there are fewer than the calibration split in most "
      "folds. NF-D14: *a winner can legitimately beat a peeking oracle at unmatched n.* Positive "
      "headroom = the design left achievable widening on the table.")
    w("")
    w("| arm | its score | same form, PEEKING | headroom |")
    w("|---|---:|---:|---:|")
    for arm, d in an["per_form_headroom"].items():
        w(f"| `{arm}` | {d['arm']:.4f} | {d['peeking_score']:.4f} | {d['headroom']:+.4f} |")
    w("")
    w(f"- **Degenerates must LOSE** (NF1.8 (3), two-sided): `over_disperse` "
      f"{'✅' if an['degenerates_lose_to_leader']['over_disperse'] else '⛔'} · `under_disperse` "
      f"{'✅' if an['degenerates_lose_to_leader']['under_disperse'] else '⛔'}. A *constraint* a "
      f"degenerate satisfies is fine; a *criterion* a degenerate wins is fatal.")
    w(f"- ⚠️ **The flat-σ NULL TO BEAT** (MH2.1's rolled-back winner shape — ⛔ do NOT carry its "
      f"claim that it beat the incumbent): the leader "
      f"{'beats' if an['flat_null_loses_to_leader'] else '**DOES NOT BEAT**'} it.")
    pa = an["permutation_anchor"]
    w(f"- **Permutation anchor** — {pa['registered_expectation']}. Measured: `perm_sigma` "
      f"{pa['rms']:.4f} vs `flat_sigma` {pa['flat_sigma_rms']:.4f} ⇒ degraded as registered = "
      f"**{pa['degraded_to_flat']}**.")
    w("")

    # ── 3b. metric divergence ───────────────────────────────────────────────────────────────────
    dv = r.get("metric_divergence")
    if dv:
        w("## 3b. ⚠️ The two pre-registered readings do not want the same σ")
        w("")
        w("`RMS |Var(z) − 1|` is a **second-moment** target. Central-80% coverage and the Winkler "
          "score are **bulk/quantile** targets. On a Normal they coincide; on a fat-tailed residual "
          "they do not — the variance is inflated by the tails while the 80% interval is set by the "
          "middle — so the σ that makes `Var(z) = 1` is WIDER than the σ that makes coverage 0.80.")
        w("")
        w(f"- Excess kurtosis of the served model's `z`: **{dv['excess_kurtosis_of_z_incumbent']:+.3f}** "
          f"(a Normal is 0)")
        w(f"- σ multiplier that sets **Var(z) = 1**: **×{dv['sigma_multiplier_that_sets_var_z_to_1']:.4f}**")
        w(f"- σ multiplier that sets **coverage = 0.80**: "
          f"**×{dv['sigma_multiplier_that_sets_coverage_to_0.80']:.4f}**")
        w("")
        w("⭐ **This matters for what a fix would mean operationally.** Served `P(over)` at a line is "
          "a CDF read NEAR THE MIDDLE of the predictive, i.e. it lives in the quantile regime, not "
          "the second-moment regime. A rescale chosen to satisfy the primary metric is therefore not "
          "automatically an improvement to the number the product actually serves, and this study "
          "does not claim it is. Reported because the primary and secondary readings DISAGREED in "
          "this run — the E2.1-r discipline applied to the gap between two metrics rather than to "
          "one of them.")
        w("")

    # ── 4. generalization ───────────────────────────────────────────────────────────────────────
    w("## 4. Does σ GENERALIZE? — in-fold vs out-of-fold")
    w("")
    w("The other half of the target. An arm that widens its σ but only fits the fold it was "
      "calibrated on reproduces the defect instead of fixing it; the gap below is the diagnostic. "
      "In-fold = the held-out calibration split each recalibrator was fitted on; out-of-fold = the "
      "purged eval rows.")
    w("")
    w("| arm | in-fold RMS | out-of-fold RMS | gap |")
    w("|---|---:|---:|---:|")
    for n, g in sorted(r["generalization_gap"].items(), key=lambda kv: kv[1]["out_of_fold_rms"]):
        w(f"| `{n}` | {g['in_fold_rms']:.4f} | {g['out_of_fold_rms']:.4f} | {g['gap']:+.4f} |")
    w("")

    # ── 5. own-σ diagnostic ─────────────────────────────────────────────────────────────────────
    w("## 5. Each arm on ITS OWN σ — a diagnostic, ⛔ never the criterion")
    w("")
    w("\"Does your σ mean what you say it means?\" A flat-σ arm induces **no partition at all**, so "
      "an own-σ reading would be vacuously perfect — which is exactly why this can never be the "
      "selection metric (it is a criterion the degenerate wins outright, NF1.8).")
    w("")
    w("| arm | own-σ partition valid | ρ | σ range | realized-SD range | dispersion match | "
      "RMS on own σ |")
    w("|---|:--:|---:|---:|---:|---:|---:|")
    for n in names:
        d = r["own_sigma_diagnostic"][n]
        if d.get("degenerate"):
            w(f"| `{n}` | — | — | — | — | — | *no partition (constant σ)* |")
            continue
        w(f"| `{n}` | {'✅' if d['stratifier_valid'] else '⛔'} | {d['spearman_rho']:.3f} | "
          f"×{d['sigma_range_ratio']:.3f} | ×{d['realized_sd_range_ratio']:.3f} | "
          f"{d['dispersion_match']:.3f} | {d['rms_abs_var_z_minus_1']:.4f} |")
    w("")

    # ── 6. the gates ────────────────────────────────────────────────────────────────────────────
    if "gates" not in r:
        # a HALT verdict (the metric proved inverted against a per-form ceiling) reaches here. The
        # anchors and diagnostics above are exactly what a reader needs; no gate table is emitted,
        # because there is no admissible winner to gate.
        (_ABL / f"{stem}.md").write_text("\n".join(a) + "\n")
        return _ABL / f"{stem}.md"
    g = r["gates"]
    w("## 6. The pre-registered decision rule")
    w("")
    w(f"Leader = **`{g['leader']}`**. Every clause below was fixed in source before any arm scored.")
    w("")
    w("| gate | requirement | measured | pass |")
    w("|---|---|---:|:--:|")
    w(f"| material gain vs the SERVED σ | > {g['meaningful_gain_required']} RMS | "
      f"{g['margin_vs_incumbent']:+.4f} | {'✅' if g['beats_incumbent_materially'] else '⛔'} |")
    w(f"| ⭐ material gain vs the LEVEL-ONLY matched foil | > {g['meaningful_gain_required']} RMS | "
      f"{g['margin_vs_matched_foil']:+.4f} | {'✅' if g['beats_matched_foil_materially'] else '⛔'} |")
    w(f"| beats the flat-σ NULL | — | {g['rms_flat_null']:.4f} vs {g['rms_leader']:.4f} | "
      f"{'✅' if g['beats_flat_null'] else '⛔'} |")
    w(f"| beats BOTH degenerates | — | — | {'✅' if g['beats_both_degenerates'] else '⛔'} |")
    w(f"| PBO | < {g['pbo_max']} | {g['pbo']:.4f} | {'✅' if g['pbo_pass'] else '⛔'} |")
    d = g["dsr_fixed_convention"]
    w(f"| DSR (fixed convention, measured V) | ≥ {DSR_MIN_CONF} | "
      f"{d.get('dsr', float('nan')):.4f} | {'✅' if g['dsr_pass'] else '⛔'} |")
    w(f"| BH-FDR over the {len(g['bh_tests'])} real candidates | q = {g['bh_q']} | — | "
      f"{'✅' if g['bh_pass'] else '⛔'} |")
    w(f"| central-80% coverage FLOOR (⛔ never a target) | ≥ incumbent − 0.01 | "
      f"{P[g['leader']]['coverage']:.4f} vs {P['incumbent']['coverage']:.4f} | "
      f"{'✅' if g['coverage_floor_respected'] else '⛔'} |")
    w("")
    w(f"- Fold consistency (reported, not a gate here): the leader beats the served σ in "
      f"**{g['fold_wins_leader_over_incumbent']}/{g['n_folds']}** folds.")
    if d.get("available"):
        w(f"- DSR detail — observed per-fold Sharpe **{d['observed_sr']:.3f}** vs bar "
          f"**SR0 = {d['sr0']:.3f}** at {d['n_trials']} trials; measured cross-trial dispersion "
          f"V = {d['var_trials_sr']:.4f}. The incumbent is the REFERENCE and is excluded from V "
          f"(its skill-vs-itself series is identically zero); `n_trials` stays the full field.")
        if d.get("degenerate_trial_arms"):
            w(f"  - ⚠️ numerically degenerate trial arms (|Sharpe| > 10, a near-zero-denominator "
              f"artifact rather than genuine dispersion): {d['degenerate_trial_arms']}")
    else:
        w(f"- DSR: {d.get('note')}")
    w("")
    sv = g.get("deflation_sensitivity") or {}
    if sv.get("trial_sharpes_all"):
        w("### ⭐ Deflation sensitivity — is the DSR failure EVIDENTIAL or ARITHMETIC?")
        w("")
        w("⛔ **NON-BINDING AND NOT A RESCUE.** The gate above stands exactly as pre-registered. "
          "This block exists so the record can say WHY it failed, and so a successor can "
          "pre-register the convention rather than discover it (MH2.2).")
        w("")
        w(f"Measured per-arm trial Sharpes: `{sv['trial_sharpes_all']}`. The two entries at "
          f"`{sv['degenerate_sharpes']}` are the pre-registered DEGENERATES — arms that exist to "
          f"LOSE. Because `SR0 = √V·z(N)` scales with the cross-trial Sharpe **dispersion**, an arm "
          f"that loses hugely and CONSISTENTLY inflates the bar just as effectively as one that "
          f"wins hugely:")
        w("")
        w("| | V | SR0 | observed SR | DSR |")
        w("|---|---:|---:|---:|---:|")
        w(f"| **as gated** (full declared field) | {sv['V_as_gated']:.3f} | {sv['sr0_as_gated']:.3f} "
          f"| {sv['observed_sr']:.3f} | {sv['dsr_as_gated']:.4g} |")
        w(f"| V excluding the designed losers | {sv['V_excluding_designed_losers']:.3f} | "
          f"{sv['sr0_excluding_designed_losers']:.3f} | {sv['observed_sr']:.3f} | "
          f"{sv['dsr_excluding_designed_losers']:.4g} |")
        w("")
        w("⭐ **This is MH2.1 (a) mirrored.** There, a DIAGNOSTIC anchor leaked into the trial field "
          "and set the gate's own bar. Here, a pre-registered degenerate — which correctly IS a "
          "trial for MULTIPLICITY — sets the bar through **V**, by losing consistently. "
          "`dsr_gate`'s existing guard does not catch it (it flags |Sharpe| > 10). The two rules "
          "that collide are each right on their own: NF1.8/NF1.7 require degenerates in the field "
          "to prove the metric is two-sided, and MH2 §a requires the full declared field in "
          "`n_trials`. ⭐ Note the repo ALREADY resolves this same tension for the reference arm — "
          "`dsr_gate` keeps the incumbent in `n_trials` while excluding it from `V`, on the grounds "
          "that a designed-constant skill series is not evidence about dispersion. Extending that "
          "to lose-by-construction anchors is the same argument, not a new one.")
        w("")
        w(f"- PBO as gated (whole declared field): **{g['pbo']:.4f}** · PBO over CONTENDERS only "
          f"(degenerates dropped, NF1.8): **{sv.get('pbo_contenders_only', float('nan')):.4f}**")
        w(f"- Whole-field spread **{sv['whole_field_spread']:.4f}** vs contender (top-quartile) "
          f"spread **{sv['contender_spread_top_quartile']:.4f}** — NF1.8: a spread computed over a "
          f"field that CONTAINS its own nulls measures the nulls.")
        w(f"- Per-fold winner counts (the cheap flip statistic): `{sv['per_fold_winner_counts']}` — "
          f"mass on a single arm is a stable pick; mass spread thinly over unrelated arms is a "
          f"search that learnt nothing.")
        w("")

    w("### BH-FDR, paired across folds against the served σ")
    w("")
    w("| arm | mean per-fold gain | p (one-sided) | BH cutoff | passes |")
    w("|---|---:|---:|---:|:--:|")
    for t in g["bh_tests"]:
        w(f"| `{t['arm']}` | {t['mean_gain']:+.5f} | {t['p_one_sided']:.4f} | "
          f"{t['bh_cutoff']:.4f} | {'✅' if t['passes_bh'] else '⛔'} |")
    w("")

    # ── 7. the null classification ──────────────────────────────────────────────────────────────
    if "null_classification" in r:
        nc = r["null_classification"]
        w("## 7. What KIND of null this is (`cv_power.classify_null`)")
        w("")
        w(f"**`{nc['state']}`** — {nc['reason']}")
        w("")
        if nc.get("retest_trigger"):
            w(f"- Re-test trigger: **{nc['retest_trigger']}**")
        sv2 = r.get("gates", {}).get("deflation_sensitivity") or {}
        if (sv2.get("V_excluding_designed_losers") is not None
                and sv2["V_as_gated"] > 4 * sv2["V_excluding_designed_losers"]):
            w("- ⚠️⚠️ **THIS CLASSIFICATION INHERITS THE SAME `V` ARTIFACT AND MUST NOT BE QUOTED "
              "BARE.** `classify_null` is handed the binding `var_trials_sr`, which the "
              "lose-by-construction degenerates inflate "
              f"({sv2['V_as_gated']:.3f} vs {sv2['V_excluding_designed_losers']:.4f} without them). "
              "Its `DSR_UNREACHABLE` label — and in particular its \"not rescuable by field size, "
              "the only lever left is a lower-variance design\" remedy — is therefore a statement "
              "about the anchor arithmetic, NOT about the evidence. Read it beside §6's sensitivity "
              "table. This is the third member of the MH2.2 family: **the instrument's own remedy "
              "text is only as trustworthy as the quantity it was handed.**")
        if not nc.get("smaller_field_trigger_is_safe", True):
            w("- ⚠️ **THE INSTRUMENT'S OWN REMEDY IS SUSPECT HERE (MH2.2).** `classify_null` sees "
              "only a TRIAL COUNT and cannot tell a DECLARED narrow family from a DISCOVERED one, "
              f"so a \"re-test at a field of ≤{nc.get('max_field_size')}\" trigger would prescribe "
              f"shrinking BELOW this story's pre-registered {r['n_arms_in_field']}-arm family — "
              "which re-commits the very selection bias DSR exists to deflate. ⛔ Do not act on it.")
        w(f"- Detail: `{json.dumps(nc.get('detail', {}), default=float)}`")
        w("")

    # ── 8. per-fold ─────────────────────────────────────────────────────────────────────────────
    w("## 8. Per-fold detail")
    w("")
    w("| eval year | inner-train | cal split | eval | fitted γ̂ (power) | peeking oracle γ |")
    w("|---:|---:|---:|---:|---:|---:|")
    for f in r["fold_meta"]:
        w(f"| {f['eval_year']} | {f['n_inner']:,} | {f['n_cal']:,} | {f['n_eval']:,} | "
          f"{f['power_gamma']:.3f} | {f['oracle_power_gamma']:.3f} |")
    w("")
    w("γ̂ is the fitted exponent of the widener `σ' = a·σ̄·(σ/σ̄)^γ`. **γ = 1 is the incumbent, γ = 0 "
      "is the flat null, γ > 1 WIDENS.** The peeking oracle's γ (fitted on the eval fold itself) is "
      "the value that would have been optimal with hindsight — the gap between the two is how much "
      "of the widening the design could actually learn in advance.")
    w("")
    w("| eval year | " + " | ".join(f"`{n}`" for n in r["field"]) + " |")
    w("|---:|" + "---:|" * len(r["field"]))
    for i, f in enumerate(r["fold_meta"]):
        w(f"| {f['eval_year']} | "
          + " | ".join(f"{r['per_fold_rms_by_stratifier'][prim][n][i]:.4f}"
                        for n in r["field"]) + " |")
    w("")

    # ── 9. LOCK 2 coverage ──────────────────────────────────────────────────────────────────────
    w("## 9. Contract coverage by season (MH2.1 Lock 2 — per COLUMN, not a pooled mean)")
    w("")
    w("MH2.1 (c): report per-column ABSENCE, not a pooled coverage mean — \"missing\" and \"NEVER "
      "EXISTED\" are different findings, and a structurally absent column means the early folds "
      "evaluate a DIFFERENT contract rather than a sparser one. This BOUNDS what a wide window can "
      "certify; it is not a reason to trim folds (the handicap is identical across arms).")
    w("")
    w("| season | rows | mean coverage | structurally absent columns |")
    w("|---:|---:|---:|---|")
    for k, v in sorted(r["contract_coverage_by_season"].items()):
        w(f"| {k} | {v['rows']:,} | {v['coverage']:.3f} | "
          + (", ".join(f"`{c}`" for c in v["structurally_absent"]) or "—") + " |")
    w("")
    w("---")
    w("")
    w("## Reproduction")
    w("")
    w("```bash")
    w("# LAPTOP. Snowflake-free; requires betting_ml/data/cache/edge_e1_training_from2016.parquet")
    w("uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py")
    w("uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py --exclude-seasons 2020")
    w("```")
    path = _ABL / f"{stem}.md"
    path.write_text("\n".join(a) + "\n")
    return path


def rewrite_reports() -> list[str]:
    """Re-emit the markdown for every stored run. **Refits nothing** — zero compute, zero Snowflake.

    The JSON already carries every number, so a prose or presentation change must never cost another
    2-minute fit (and must never be able to change a recorded figure while doing so).
    """
    out = []
    for src in sorted(_JSON_DIR.glob("mh2_5_sigma_recalibration*.json")):
        out.append(str(write_report(json.loads(src.read_text())).relative_to(PROJECT_ROOT)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="MH2.5 per-game σ recalibration bake-off (SF-free)")
    ap.add_argument("--rewrite-reports", action="store_true",
                    help="Re-emit the markdown from stored JSON. Refits nothing.")
    ap.add_argument("--exclude-seasons", type=int, nargs="*", default=[],
                    help="LOCK-1 declared sensitivity, e.g. --exclude-seasons 2020 (the COVID control)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true",
                    help="Cap rows/estimators for a fast harness check. NOT a result.")
    args = ap.parse_args()
    if args.rewrite_reports:
        for pth in rewrite_reports():
            print(f"[{STORY}] report → {pth}")
        return
    r = run(exclude_seasons=tuple(args.exclude_seasons or ()), seed=args.seed, smoke=args.smoke)
    p = write_report(r)
    print(f"\n[{STORY}] VERDICT: {r['verdict']}")
    print(f"[{STORY}] {r['reading']}")
    print(f"[{STORY}] report → {p.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

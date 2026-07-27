"""mle_prior_pitcher.py — MLB Edge-E7.5p: recalibrate the E7.3p PITCHER MiLB→MLB MLE into a PRICEABLE
rookie-STARTER prior, and the calibration ablation vs the incumbent generic prior.

WHAT THIS IS (and how it differs from the batter sibling)
---------------------------------------------------------
E7.5 did this for BATTERS (`mle_prior.py` → `eb_batter_posteriors_raw`). E7.3p landed the PITCHER MLE
(`milb_mle_pitcher_v1`), and this module is its wiring half: it turns those projections into the prior a
debuting / low-BF rookie STARTER gets in `eb_starter_posteriors` instead of the generic experience-band
prior — the same cold-start mispricing E7.5 fixed on the hitting side.

All the prior-strength + recalibration + ablation MATH is shared with the batter module (`mle_prior`);
this file is the pitcher CONFIG on top of it. Three things genuinely differ:

  1. WHICH METRICS ARE WIRED. E7.3p graded the five pitcher translations very differently:
        gb_pct        corr 0.551, PBO 0.000, DSR 1.000  → ✅ STRONG  (the cross-definition GO-share proxy carried)
        bb_pct        corr 0.367, PBO 0.000, DSR 0.947  → 🟡 weak-but-real
        k_pct         corr 0.366, PBO 0.014, DSR 0.786  → 🟡 weak-but-real
        hr_rate       corr 0.094, PBO 0.900             → ❌ TIED-FIELD null (the E2.1-r read) — NOT wired
        xwoba_against corr 0.147, does not beat archetype → ❌ no-signal — NOT wired
     So the wired set is (gb_pct, k_pct, bb_pct). ⚠️ EXPECTATION-SET: pitcher K% translates FAR more
     weakly than batter K% (0.366 vs E7.3's 0.637 — a real asymmetry, same harness), so the rookie-STARTER
     prior's lift is expected to be MORE MODEST than the batter version's, and the biggest single
     contribution should come from GB% (contact management), not K%.

  2. THE EVIDENCE COUNT IS NOT PA. κ is an equivalent number of BINOMIAL TRIALS, so it must be expressed
     in the units of the thing the served build observes: K%/BB% accrue per BATTER FACED (BF); GB% accrues
     per BALL IN PLAY (BIP). `EVIDENCE_COUNT` records that mapping, and the recalibration's label-sampling
     decomposition uses the matching denominator (using TBF for a GB rate would understate the label noise
     ~2x, since BIP ≈ 0.6·TBF).

  3. THE THIN-CAMEO FLOOR IS PER-METRIC. E7.5's landmine (a 1-PA cameo inflating σ_resid 2–3x) recurs
     verbatim here — measured on the real E7.3p artifacts the `mlb_pa ≥ 150` (TBF) floor cuts σ_resid by
     1.7–2.2x on all three metrics. GB% needs a SECOND floor: a pitcher can clear 150 TBF while putting
     very few balls in play, and a ~20-BIP realized GB% is nearly pure noise → `MIN_MLB_BIP`.

⛔ NOT WIRED, deliberately: `hr_rate` and `xwoba_against` (see `PITCHER_NOT_WIRED`). A no-signal metric
stays on the incumbent generic prior — E7.3's wOBA precedent, and the E2.1-r tied-field discipline.

BOUNDED RATES ⇒ PSEUDO-COUNT (κ) BLENDS, NEVER NORMAL-NORMAL
------------------------------------------------------------
All three wired metrics are bounded rates in [0,1], so every MLE-prior update here is the pseudo-count
blend  post = (m·κ + obs·n) / (κ + n)  — identical to E7.5's Beta-Binomial update, and identical to the
served DuckDB SQL. This is the E7.5 ISO lesson applied pre-emptively: a Normal-Normal update with a
measurement-variance floor lets a tiny-sample extreme observation overwhelm the prior, and a variance
floor cannot save it. `kappa_blend_posterior_mean` below IS `mle_prior.beta_posterior_mean` (same algebra
with α = m·κ, β = (1−m)·κ) — aliased, not re-implemented, so there is one formula to keep in sync with SQL.

Pure numpy/pandas — no S3, no DuckDB, no `pipeline` import (the fast-gate rule).
`best_alpha = 0`: a cold-start calibration fix, never a market bet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.mle_prior import (
    KAPPA_CAP,
    KAPPA_FLOOR,
    MetricAblation,
    MetricCalibration,
    ablate_metric,
    beta_posterior_mean,
    highest_level_rows,
    kappa_from_resid_sd,
    recalibrate_metric,
)

__all__ = [
    "PITCHER_PRIOR_METRICS", "PITCHER_NOT_WIRED", "EVIDENCE_COUNT", "MIN_MLB_BIP",
    "KAPPA_FLOOR", "KAPPA_CAP", "kappa_from_resid_sd", "kappa_blend_posterior_mean",
    "recalibrate_pitcher", "ablate_pitcher", "build_calibrated_pitcher_prior_table",
]

# The pitcher metrics E7.5p wires, STRONGEST FIRST (the ordering the report + registry use).
PITCHER_PRIOR_METRICS: tuple[str, ...] = ("gb_pct", "k_pct", "bb_pct")

# Deliberately NOT wired — a no-signal translation must stay on the incumbent generic prior.
PITCHER_NOT_WIRED: dict[str, str] = {
    "hr_rate": "E7.3p TIED FIELD (winner beats the null by 1e-4, PBO 0.900, corr 0.094) — the E2.1-r "
               "reading makes this effectively NO-SIGNAL; HR suppression is BABIP-adjacent.",
    "xwoba_against": "E7.3p no-signal (corr 0.147, DSR 0.030; does NOT beat the generic archetype prior) "
                     "— the batter-wOBA mirror. eb_xwoba_against keeps its experience-band prior.",
}

# κ is an equivalent number of BINOMIAL TRIALS, so it lives in the units the served build observes.
# K%/BB% accrue per batter faced; GB% accrues per ball in play. The served SQL must weight each metric's
# observed line by the MATCHING count (current_bf vs prior-season BIP) or κ means nothing.
EVIDENCE_COUNT: dict[str, str] = {"gb_pct": "bip", "k_pct": "bf", "bb_pct": "bf"}

# The GB-specific thin-sample floor (the E7.5 cameo landmine, second order). `has_mlb_label` gates on
# mlb_pa (TBF) ≥ 150; a pitcher can clear that while putting few balls in play, and a ~20-BIP realized
# GB% is nearly pure sampling noise → it would inflate σ_resid and weaken the prior for everyone.
MIN_MLB_BIP = 50


def kappa_blend_posterior_mean(mean: float, kappa: float, n: float, obs_rate: float | None) -> float:
    """The served κ-blend: (m·κ + obs·n)/(κ + n). n=0 (or no observed rate) → the MLE mean; n→∞ → observed.

    This is `mle_prior.beta_posterior_mean` under its pitcher-side name (α = m·κ, β = (1−m)·κ makes the
    Beta-Binomial posterior mean exactly this) — aliased rather than re-implemented so there is ONE
    formula mirrored by the served `eb_starter_posteriors` DuckDB SQL."""
    return beta_posterior_mean(mean, kappa, n, obs_rate)


def _prep(proj: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Per-metric view of the projections with (a) the right evidence count in `mlb_pa` — which is what
    `recalibrate_metric` decomposes label-sampling noise against — and (b) the metric's thin-sample floor
    folded into `has_mlb_label`.

    GB% swaps in `mlb_bip` (balls in play) and additionally requires MIN_MLB_BIP; K%/BB% keep `mlb_pa`
    (which on the pitcher side IS batters faced — the E7.3p harness keeps the column name shared)."""
    d = proj.copy()
    if "has_mlb_label" not in d:
        return d
    lab = d["has_mlb_label"].fillna(False).astype(bool)
    if EVIDENCE_COUNT.get(metric) == "bip":
        bip = pd.to_numeric(d.get("mlb_bip", pd.Series(np.nan, index=d.index)), errors="coerce")
        d["mlb_pa"] = bip                       # the GB rate's binomial n
        lab = lab & (bip >= MIN_MLB_BIP)
    d["has_mlb_label"] = lab
    return d


def recalibrate_pitcher(proj: pd.DataFrame, metrics: tuple[str, ...] = PITCHER_PRIOR_METRICS,
                        highest_level_only: bool = True) -> dict[str, MetricCalibration]:
    """E13.6 recalibration per wired pitcher metric: parameter sd → held-out predictive spread σ_resid,
    measured on graduated pitchers at their HIGHEST reached level under the metric's thin-sample floor."""
    return {m: recalibrate_metric(_prep(proj, m), m, highest_level_only) for m in metrics}


def ablate_pitcher(proj: pd.DataFrame, metrics: tuple[str, ...] = PITCHER_PRIOR_METRICS,
                   highest_level_only: bool = True) -> dict[str, MetricAblation]:
    """Purged leave-one-debut-cohort-out calibration ablation (MLE prior vs the incumbent generic prior)
    per wired pitcher metric — the AC evidence that the rookie-STARTER prior is better CALIBRATED."""
    return {m: ablate_metric(_prep(proj, m), m, highest_level_only) for m in metrics}


def build_calibrated_pitcher_prior_table(proj: pd.DataFrame,
                                         calib: dict[str, MetricCalibration]) -> pd.DataFrame:
    """One row per pitcher (MLBAM `player_id` → `pitcher_id`) at the HIGHEST reached MiLB level, carrying
    the served prior: each wired metric's MLE mean + its per-pitcher pseudo-count κ.

    A metric NULL for that pitcher (no minor line supporting it at that level) stays NULL — the served
    build then falls back to the incumbent generic prior for THAT METRIC ONLY. `pitcher_id` is emitted as
    a clean integer-valued string (never a float repr) — the INC-17 `'664983.0'` join-poisoning class."""
    df = proj.copy()
    df = highest_level_rows(df)

    out = pd.DataFrame({
        "pitcher_id": _id_string(df["player_id"]),
        "mle_level": df["level"].astype(str),
        "is_prospect": df["is_prospect"].astype(bool) if "is_prospect" in df else False,
    })
    for m in PITCHER_PRIOR_METRICS:
        if m not in calib:
            continue
        mean = pd.to_numeric(df.get(f"mle_{m}"), errors="coerce").to_numpy(float)
        sd = calib[m].resid_sd
        out[f"mle_{m}"] = mean
        out[f"{m}_prior_kappa"] = [kappa_from_resid_sd(x, sd) if np.isfinite(x) else np.nan
                                   for x in mean]
    return out.reset_index(drop=True)


def _id_string(s: pd.Series) -> pd.Series:
    """MLBAM id → canonical string. A float-typed id would render '664983.0' and silently match NOTHING
    on the served VARCHAR join (INC-17); coerce through Int64 when the column is numeric."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().all():
        return num.astype("Int64").astype(str)
    return s.astype(str)

"""mle_prior.py — MLB Edge-E7.5: recalibrate the E7.3 MiLB→MLB MLE into a PRICEABLE rookie prior,
and the calibration ablation vs the incumbent generic prior.

WHAT THIS IS
------------
E7.3 shipped the minor→major translation MLE (`milb_mle_v1`): for a graduated / prospect batter it
emits an MLB-equivalent rate line (K%/BB%/ISO — the metrics that TRANSLATE — plus wOBA, which does NOT
and is NOT wired) with PARAMETER uncertainty. That uncertainty is the posterior sd of the fitted map at
the player's inputs; it is CORRECT for ranking confidence but far too TIGHT to price a realized-rate
interval with (`milb_mle.py::UNCERTAINTY SEMANTICS`). E7.5 does the E13.6 recalibration step: it replaces
the parameter sd with the held-out PREDICTIVE spread of the MLE mean around realized early-career MLB
production, and converts that into a Beta-Binomial prior pseudo-count (K%/BB%) / a Normal prior sd (ISO)
that the served `eb_batter_posteriors_raw` build shrinks a low-MLB-PA rookie's observed line toward.

Everything here is PURE numpy/pandas (no S3, no DuckDB, no `pipeline` import) so the fast gate exercises
the recalibration + ablation math directly (model-quality gates are behavioural — CI mocks all IO).

WHY RECALIBRATE, NOT USE `mle_*_sd` DIRECTLY
--------------------------------------------
The MLE projections are emitted LEAKAGE-SAFE (each graduated player's `mle_<m>` was fit only on
strictly-prior debut cohorts — `milb_mle.emit_projections`), so `(mle_<m>, mlb_<m>)` over graduated
players is an honest out-of-sample pairing. The residual sd `σ_resid[m] = std(mlb_<m> − mle_<m>)` is the
HONEST predictive spread. We use σ_resid (not the tighter parameter `mle_<m>_sd`) as the prior sd. This
is deliberately a SLIGHT over-estimate of the true between-player prior sd — it also carries the finite-PA
sampling noise in the realized label — which makes the prior a touch WEAKER (observed data takes over a
touch faster). That is the SAFE direction for a prior that must never overpower a player's own MLB line.

PRIOR STRENGTH (the pseudo-count)
---------------------------------
A Beta(α, β) prior with mean m and pseudo-count κ = α + β has sd sqrt(m(1−m)/(κ+1)). Matching that to the
recalibrated σ_resid gives κ(m) = m(1−m)/σ_resid² − 1, clipped to [κ_floor, κ_cap]. κ is the equivalent
number of MLB PAs the prior is "worth": the served build's Beta-Binomial update
(α + obs·PA)/(α + β + PA) then shrinks the rookie's observed rate toward the MLE mean, converging to the
observed line as PA accrues — the exact PA-accrual blend E7.5 asks for, extended (not duplicated). For
ISO (Normal-Normal) there is no pseudo-count; the recalibrated σ_resid IS the prior sd.

THE ABLATION (the AC — improved rookie CALIBRATION, not an edge claim)
---------------------------------------------------------------------
Leave-one-debut-cohort-out (purged): for each cohort Y, the GENERIC baseline = the population mean of the
realized MLB metric over STRICTLY-PRIOR cohorts (what the incumbent generic archetype/level prior collapses
to at PA≈0 — E7.3's `archetype_prior` benchmark), the MLE prior = the OOS `mle_<m>`. Each scored on the
cohort-Y rookies by predictive NLL + CRPS (calibration × sharpness) + MAE + interval coverage. `best_alpha
= 0` — this is a prior, never a market bet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# The metrics E7.5 wires. wOBA is DELIBERATELY excluded — E7.3 proved it carries no translatable signal
# beyond level (ties the generic archetype prior, 0.0285 vs 0.0284) so wiring it would only add noise.
PRIOR_METRICS = ("k_pct", "bb_pct", "iso")
# Beta-Binomial metrics (a rate in [0,1] with a pseudo-count prior); ISO is Normal-Normal (no pseudo-count).
_BETA_METRICS = ("k_pct", "bb_pct")

# κ clip. Floor 20 ≈ a quarter-season of PAs — a weak-but-real prior even when σ_resid is wide (a metric
# that translates loosely still beats the generic prior per E7.3, so keep some pull). Cap 400 mirrors the
# sequential chain's prior_neff_cap so an over-tight σ_resid can never freeze the rookie's own MLB line.
KAPPA_FLOOR = 20.0
KAPPA_CAP = 400.0

# Levels ordered nearest-to-MLB first — the served prior uses the player's HIGHEST reached level (the most
# MLB-relevant single translation).
_LEVEL_RANK = {"Triple-A": 0, "Double-A": 1, "High-A": 2, "Single-A": 3}


# ══════════════════════════════════════════════════════════════════════════════════════
# Prior-strength math (mirrors the served eb_batter_posteriors_raw DuckDB SQL EXACTLY so the
# wiring test is meaningful)
# ══════════════════════════════════════════════════════════════════════════════════════


def kappa_from_resid_sd(mean: float, resid_sd: float,
                        floor: float = KAPPA_FLOOR, cap: float = KAPPA_CAP) -> float:
    """Beta pseudo-count κ whose prior sd sqrt(m(1−m)/(κ+1)) matches the recalibrated σ_resid.

    κ = m(1−m)/σ_resid² − 1, clipped to [floor, cap]. A degenerate mean (0/1) or non-positive σ falls
    back to the floor (a weak prior), never NaN/Inf."""
    m = float(mean)
    s = float(resid_sd)
    if not np.isfinite(m) or not np.isfinite(s) or s <= 0 or m <= 0.0 or m >= 1.0:
        return float(floor)
    kappa = m * (1.0 - m) / (s * s) - 1.0
    return float(np.clip(kappa, floor, cap))


def beta_posterior_mean(mean: float, kappa: float, pa: float, obs_rate: float | None) -> float:
    """Beta-Binomial posterior mean with an MLE-derived prior — the served formula.

    prior α = mean·κ, β = (1−mean)·κ; post = (α + obs·PA)/(α + β + PA). At PA=0 (or no observed rate)
    this is exactly the MLE mean; as PA→∞ it converges to the observed rate."""
    alpha = mean * kappa
    beta = (1.0 - mean) * kappa
    if pa <= 0 or obs_rate is None or not np.isfinite(obs_rate):
        return alpha / (alpha + beta)
    return (alpha + obs_rate * pa) / (alpha + beta + pa)


def normal_posterior_mean(mu0: float, sigma0: float, pa: float, obs_iso: float | None) -> float:
    """Normal-Normal posterior mean for ISO — the GENERIC (non-MLE) served formula. NOTE: this is the
    incumbent path and is NOT used for the MLE prior — its measurement-variance floor lets a tiny-sample
    extreme obs_iso (>1 over a few PAs) overwhelm the prior; the MLE path uses the regularized pseudo-count
    below instead (mirroring K%/BB%)."""
    if pa <= 0 or obs_iso is None or not np.isfinite(obs_iso):
        return float(mu0)
    sigma_meas_sq = max(obs_iso * (1.0 - obs_iso), 0.001) / pa
    prec_prior = 1.0 / (sigma0 * sigma0)
    prec_obs = 1.0 / sigma_meas_sq
    return (mu0 * prec_prior + obs_iso * prec_obs) / (prec_prior + prec_obs)


# ISO is unbounded (extra-bases/AB ∈ {0,1,2,3}), so unlike a [0,1] rate the Normal-Normal update blows up
# for a tiny-sample extreme obs_iso. The MLE ISO prior therefore uses a PSEUDO-COUNT blend (like K%/BB%):
# κ_iso = V_ISO_PER_PA / iso_prior_sd², with V_ISO_PER_PA ≈ the per-PA variance of extra-bases-per-AB.
V_ISO_PER_PA = 0.25


def iso_kappa(iso_prior_sd: float, v_iso: float = V_ISO_PER_PA) -> float:
    """κ_iso (equivalent PAs the MLE ISO prior is worth). Mirrors the served DuckDB SQL exactly."""
    s = float(iso_prior_sd)
    if not np.isfinite(s) or s <= 0:
        return float("nan")
    return v_iso / (s * s)


def iso_pseudocount_posterior_mean(mle_iso: float, iso_prior_sd: float, pa: float,
                                   obs_iso: float | None, v_iso: float = V_ISO_PER_PA) -> float:
    """Regularized ISO posterior mean: (mle·κ_iso + obs·PA)/(κ_iso + PA). PA=0 → the MLE mean; a tiny-sample
    extreme obs_iso can only nudge it (κ_iso ≫ pa), so eb_iso stays in range — the served MLE formula."""
    k = iso_kappa(iso_prior_sd, v_iso)
    if pa <= 0 or obs_iso is None or not np.isfinite(obs_iso) or not np.isfinite(k):
        return float(mle_iso)
    return (mle_iso * k + obs_iso * pa) / (k + pa)


# ══════════════════════════════════════════════════════════════════════════════════════
# Recalibration — replace the parameter sd with the held-out predictive spread
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class MetricCalibration:
    metric: str
    resid_sd: float          # the recalibrated predictive sd (REPLACES mle_<m>_sd for pricing)
    param_sd_median: float   # the incumbent (too-tight) parameter sd, for the tightness ratio
    n: int
    coverage_68: float       # frac |mlb − mle| ≤ σ_resid  (honest ≈ 0.68)
    coverage_90: float       # frac |mlb − mle| ≤ 1.645·σ_resid  (honest ≈ 0.90)
    label_sampling_sd: float # mean sqrt(p(1−p)/mlb_pa) — the part of σ_resid that is label noise
    true_sd_est: float       # variance-decomposed between-player prior sd (diagnostic)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "resid_sd": round(self.resid_sd, 6),
            "param_sd_median": round(self.param_sd_median, 6),
            "tightness_ratio": round(self.resid_sd / self.param_sd_median, 3)
            if self.param_sd_median > 0 else None,
            "n": self.n,
            "coverage_68": round(self.coverage_68, 4),
            "coverage_90": round(self.coverage_90, 4),
            "label_sampling_sd": round(self.label_sampling_sd, 6),
            "true_sd_est": round(self.true_sd_est, 6),
            "kappa_floor": KAPPA_FLOOR,
            "kappa_cap": KAPPA_CAP,
        }


def highest_level_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce to one row per player at the HIGHEST reached level — the single translation the served prior
    uses. Aligning the calibration/ablation population with the SERVED population (highest level) is what
    keeps σ_resid honest; the lower-level rows are noisier translations the served build never reads."""
    d = df.copy()
    d["_rank"] = _level_rank(d["level"])
    return d.sort_values(["player_id", "_rank"]).drop_duplicates("player_id", keep="first")


def _labelled(proj: pd.DataFrame, metric: str, highest_level_only: bool = True) -> pd.DataFrame:
    """Graduated (labelled) rows for `metric`: a finite emitted MLE, a realized MLB line, AND — when the
    label columns are present (merged from graduated_pairs) — `has_mlb_label` (mlb_pa ≥ the E7.3 floor).

    Without the `has_mlb_label` filter the emitted `mlb_<m>` includes thin-sample cameos (a 1-PA K% of
    1.0) that blow up σ_resid — so the runner MUST merge the label flag; this mirrors E7.3's training set.
    """
    mcol, tcol = f"mle_{metric}", f"mlb_{metric}"
    if mcol not in proj or tcol not in proj:
        return proj.iloc[0:0]
    out = proj.copy()
    if "has_mlb_label" in out:
        out = out[out["has_mlb_label"].fillna(False).astype(bool)]
    if highest_level_only and "level" in out:
        out = highest_level_rows(out)
    out = out.copy()
    out["_mle"] = pd.to_numeric(out[mcol], errors="coerce")
    out["_mlb"] = pd.to_numeric(out[tcol], errors="coerce")
    return out[out["_mle"].notna() & out["_mlb"].notna()].copy()


def recalibrate_metric(proj: pd.DataFrame, metric: str, highest_level_only: bool = True) -> MetricCalibration:
    """Held-out predictive-spread recalibration for one metric over the graduated (labelled) rows.

    The MLE projections are already leakage-safe (expanding-window by debut cohort), so `mlb − mle` is an
    honest OOS residual; σ_resid is its std. Coverage against σ_resid reports whether that sd is honest."""
    lab = _labelled(proj, metric, highest_level_only)
    if len(lab) < 3:
        raise ValueError(f"[{metric}] need ≥3 labelled graduated rows to recalibrate; got {len(lab)}")
    resid = (lab["_mlb"] - lab["_mle"]).to_numpy(float)
    resid_sd = float(np.std(resid, ddof=1))
    if not np.isfinite(resid_sd) or resid_sd <= 0:
        raise ValueError(f"[{metric}] degenerate residual sd {resid_sd}")

    scol = f"mle_{metric}_sd"
    param_sd_median = (float(np.nanmedian(pd.to_numeric(lab[scol], errors="coerce")))
                       if scol in lab else float("nan"))

    a = np.abs(resid)
    cov68 = float(np.mean(a <= resid_sd))
    cov90 = float(np.mean(a <= 1.645 * resid_sd))

    # variance decomposition: σ_resid² ≈ σ_true² + E[p(1−p)/mlb_pa] (label sampling noise). Report σ_true
    # as a diagnostic; the SERVED prior sd stays σ_resid (the conservative, fully-honest predictive spread).
    p = lab["_mlb"].to_numpy(float)
    if "mlb_pa" in lab:
        pa = pd.to_numeric(lab["mlb_pa"], errors="coerce").to_numpy(float)
    else:
        pa = np.full(len(lab), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        samp_var = np.where(pa > 0, np.clip(p * (1.0 - p), 0.0, None) / pa, np.nan)
    label_sampling_sd = (float(np.sqrt(np.nanmean(samp_var)))
                         if np.any(np.isfinite(samp_var)) else 0.0)
    true_var = max(resid_sd * resid_sd - (label_sampling_sd ** 2), (0.25 * resid_sd) ** 2)
    return MetricCalibration(
        metric=metric, resid_sd=resid_sd, param_sd_median=param_sd_median, n=len(lab),
        coverage_68=cov68, coverage_90=cov90, label_sampling_sd=label_sampling_sd,
        true_sd_est=float(np.sqrt(true_var)),
    )


def recalibrate(proj: pd.DataFrame, metrics=PRIOR_METRICS,
                highest_level_only: bool = True) -> dict[str, MetricCalibration]:
    return {m: recalibrate_metric(proj, m, highest_level_only) for m in metrics}


# ══════════════════════════════════════════════════════════════════════════════════════
# The calibrated per-player prior table (one row per batter at the highest reached level)
# ══════════════════════════════════════════════════════════════════════════════════════


def _level_rank(level: pd.Series) -> pd.Series:
    return level.map(_LEVEL_RANK).fillna(99).astype(int)


def build_calibrated_prior_table(proj: pd.DataFrame, calib: dict[str, MetricCalibration]) -> pd.DataFrame:
    """One row per batter (MLBAM `player_id` → `batter_id`) at the HIGHEST reached level, carrying the
    recalibrated MLE prior the served build reads: mle mean + per-player Beta pseudo-count (K%/BB%) /
    Normal prior sd (ISO). A metric NULL for that player (no minor line at that level) stays NULL — the
    served build then falls back to the generic prior for that metric only."""
    df = proj.copy()
    df["_rank"] = _level_rank(df["level"])
    df = df.sort_values(["player_id", "_rank"]).drop_duplicates("player_id", keep="first")

    out = pd.DataFrame({
        "batter_id": df["player_id"].astype(str),
        "mle_level": df["level"].astype(str),
        "is_prospect": df["is_prospect"].astype(bool) if "is_prospect" in df else False,
    })
    for m in ("k_pct", "bb_pct"):
        mean = pd.to_numeric(df.get(f"mle_{m}"), errors="coerce")
        sd = calib[m].resid_sd
        out[f"mle_{m}"] = mean.to_numpy(float)
        out[f"{m}_prior_kappa"] = [
            kappa_from_resid_sd(x, sd) if np.isfinite(x) else np.nan for x in mean.to_numpy(float)
        ]
    iso = pd.to_numeric(df.get("mle_iso"), errors="coerce")
    out["mle_iso"] = iso.to_numpy(float)
    out["iso_prior_sd"] = np.where(np.isfinite(iso.to_numpy(float)), calib["iso"].resid_sd, np.nan)
    return out.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════
# The calibration ablation — MLE prior vs the incumbent generic prior, purged by debut cohort
# ══════════════════════════════════════════════════════════════════════════════════════


def _norm_nll(y: np.ndarray, mu: np.ndarray, sd: float) -> np.ndarray:
    sd = max(float(sd), 1e-9)
    return 0.5 * np.log(2.0 * np.pi * sd * sd) + (y - mu) ** 2 / (2.0 * sd * sd)


def _norm_crps(y: np.ndarray, mu: np.ndarray, sd: float) -> np.ndarray:
    """Closed-form CRPS for a Normal predictive (Gneiting & Raftery 2007) — a proper score that is far
    less sensitive to sd mis-specification than NLL, so it isolates whether the MEAN is better."""
    from math import pi, sqrt
    sd = max(float(sd), 1e-9)
    z = (y - mu) / sd
    phi = np.exp(-0.5 * z * z) / sqrt(2.0 * pi)
    Phi = 0.5 * (1.0 + _erf(z / sqrt(2.0)))
    return sd * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / sqrt(pi))


def _erf(x: np.ndarray) -> np.ndarray:
    # vectorized erf via the numpy-friendly Abramowitz-Stegun 7.1.26 approximation (max err ~1.5e-7)
    x = np.asarray(x, float)
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
               + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


@dataclass
class MetricAblation:
    metric: str
    n_scored: int
    n_cohorts: int
    mle_nll: float
    generic_nll: float
    mle_crps: float
    generic_crps: float
    mle_mae: float
    generic_mae: float
    mle_cov68: float
    generic_cov68: float
    mle_cov90: float
    generic_cov90: float
    notes: list[str] = field(default_factory=list)

    @property
    def mle_wins(self) -> bool:
        return self.mle_nll < self.generic_nll and self.mle_crps <= self.generic_crps + 1e-9

    def to_dict(self) -> dict:
        return {
            "metric": self.metric, "n_scored": self.n_scored, "n_cohorts": self.n_cohorts,
            "mle_nll": round(self.mle_nll, 5), "generic_nll": round(self.generic_nll, 5),
            "mle_crps": round(self.mle_crps, 6), "generic_crps": round(self.generic_crps, 6),
            "mle_mae": round(self.mle_mae, 6), "generic_mae": round(self.generic_mae, 6),
            "mle_cov68": round(self.mle_cov68, 4), "generic_cov68": round(self.generic_cov68, 4),
            "mle_cov90": round(self.mle_cov90, 4), "generic_cov90": round(self.generic_cov90, 4),
            "mle_wins": self.mle_wins, "notes": self.notes,
        }


def ablate_metric(proj: pd.DataFrame, metric: str, highest_level_only: bool = True) -> MetricAblation:
    """Purged leave-one-debut-cohort-out calibration comparison for one metric.

    For each cohort Y (with ≥1 strictly-prior cohort): the GENERIC baseline mean = population mean of the
    realized MLB metric over PRIOR cohorts (the incumbent generic prior at PA≈0); the MLE mean = the OOS
    `mle_<m>` (already fit on strictly-prior cohorts). Each method's predictive sd = its OWN residual sd on
    the prior cohorts, so both are self-calibrated and the comparison is calibration × SHARPNESS, not a sd
    handicap. Scored on the cohort-Y rookies by NLL / CRPS / MAE / coverage."""
    lab = _labelled(proj, metric, highest_level_only)
    if "debut_cohort" not in lab:
        raise ValueError(f"[{metric}] projections carry no debut_cohort — cannot purge by cohort")
    lab = lab[lab["debut_cohort"].notna()].copy()
    lab["debut_cohort"] = lab["debut_cohort"].astype(int)
    cohorts = sorted(lab["debut_cohort"].unique())
    eval_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(eval_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable cohorts; got {eval_cohorts}")

    ys, mle_mu, gen_mu = [], [], []
    mle_sd_by_row, gen_sd_by_row = [], []
    for y in eval_cohorts:
        prior = lab[lab["debut_cohort"] < y]
        test = lab[lab["debut_cohort"] == y]
        if prior.empty or test.empty:
            continue
        gen_mean = float(prior["_mlb"].mean())
        gen_sd = float(np.std(prior["_mlb"].to_numpy(float), ddof=1)) or 1e-6
        mle_sd = float(np.std((prior["_mlb"] - prior["_mle"]).to_numpy(float), ddof=1)) or 1e-6
        ys.append(test["_mlb"].to_numpy(float))
        mle_mu.append(test["_mle"].to_numpy(float))
        gen_mu.append(np.full(len(test), gen_mean))
        mle_sd_by_row.append(np.full(len(test), mle_sd))
        gen_sd_by_row.append(np.full(len(test), gen_sd))

    y = np.concatenate(ys)
    mmu, gmu = np.concatenate(mle_mu), np.concatenate(gen_mu)
    msd, gsd = np.concatenate(mle_sd_by_row), np.concatenate(gen_sd_by_row)

    def _cov(resid_abs, sd, z):
        return float(np.mean(resid_abs <= z * sd))

    mle_nll = float(np.mean([_norm_nll(np.array([yi]), np.array([mi]), si)[0]
                             for yi, mi, si in zip(y, mmu, msd)]))
    gen_nll = float(np.mean([_norm_nll(np.array([yi]), np.array([gi]), si)[0]
                             for yi, gi, si in zip(y, gmu, gsd)]))
    mle_crps = float(np.mean([_norm_crps(np.array([yi]), np.array([mi]), si)[0]
                              for yi, mi, si in zip(y, mmu, msd)]))
    gen_crps = float(np.mean([_norm_crps(np.array([yi]), np.array([gi]), si)[0]
                              for yi, gi, si in zip(y, gmu, gsd)]))
    return MetricAblation(
        metric=metric, n_scored=int(len(y)), n_cohorts=len(eval_cohorts),
        mle_nll=mle_nll, generic_nll=gen_nll, mle_crps=mle_crps, generic_crps=gen_crps,
        mle_mae=float(np.mean(np.abs(y - mmu))), generic_mae=float(np.mean(np.abs(y - gmu))),
        mle_cov68=_cov(np.abs(y - mmu), msd, 1.0), generic_cov68=_cov(np.abs(y - gmu), gsd, 1.0),
        mle_cov90=_cov(np.abs(y - mmu), msd, 1.645), generic_cov90=_cov(np.abs(y - gmu), gsd, 1.645),
    )


def ablate(proj: pd.DataFrame, metrics=PRIOR_METRICS,
           highest_level_only: bool = True) -> dict[str, MetricAblation]:
    return {m: ablate_metric(proj, m, highest_level_only) for m in metrics}


# ══════════════════════════════════════════════════════════════════════════════════════
# E7.5b — the HEAD-TO-HEAD gate: a re-derived prior vs the CURRENTLY-SERVED one
# ══════════════════════════════════════════════════════════════════════════════════════
#
# WHY THE `ablate()` ABOVE IS NOT THE E7.5b GATE
# ----------------------------------------------
# `ablate()` asks "does an MLE prior beat the GENERIC population prior?" — the E7.5 shipping question,
# already answered ✅ for all three metrics. E7.5b asks a strictly harder one: does a prior re-derived
# from a NEW MLE beat the prior that is ALREADY SERVING on the live run_diff / pre_lineup contract? The
# incumbent already beats generic, so beating generic is not evidence for a swap. This head-to-head is
# the comparison the story turns on.
#
# THE FOUR DISCIPLINES THAT MAKE IT A REAL GATE (repo lessons, applied)
# --------------------------------------------------------------------
# 1. MATCHED POPULATION (NF1.9 (f) / E7.12 `cache_is_current`). The two projection sets do NOT have the
#    same rows — a re-fit can add players. Scoring each on its own labelled rows compares two different
#    populations and calls the difference a model effect. So both arms are scored on the INTERSECTION of
#    their labelled highest-level rows, and `n_challenger_only`/`n_incumbent_only` are reported so a
#    silently-shrunk eval set is visible rather than absorbed.
# 2. SELF-CALIBRATED SD PER ARM. Each arm's predictive sd is the std of ITS OWN residuals on the strictly
#    prior cohorts. Neither arm is handicapped by the other's spread — the contest is calibration ×
#    sharpness, exactly as in `ablate_metric`.
# 3. TWO-SIDED ANCHORS (NF-D11 / NF-D16 (g‴)). A DEGENERATE CEILING that must LOSE (the generic
#    population prior, and a within-cohort PERMUTATION of the challenger's own means — which destroys the
#    per-player pairing while preserving the marginal distribution exactly), and a PEEKING FLOOR that must
#    WIN. The floor is computed PER FORM — each arm is floored by the peeking version of ITSELF (its own
#    means shifted by the held-out cohort's mean residual) — because a single shared ceiling would veto a
#    legitimately-better arm as a false metric inversion.
#    ⚠️ The permutation anchor is deliberately chosen over a fitted oracle: it is well-posed at ANY n
#    (NF1.7 (b)), and a MISSING/undecidable anchor is reported as unavailable, never as a pass (NF1.7 (a)).
# 4. A PAIRED PER-COHORT READ, not a comparison of two pooled means (E7.12 slice 1's own hard-won lesson):
#    the per-cohort NLL deltas give a fold win rate and a one-sided p, which separates "systematically
#    better" from "won the pooled average by a hair".
#
# COVERAGE IS A FLOOR, NEVER A TARGET (E2.1-r / NF1.8). The named failure mode for this story is a prior
# that gets SHARPER without getting better CALIBRATED. NLL already punishes over-sharpness, but the
# explicit instrument is a one-sided coverage FLOOR on the challenger (`cov68 ≥ 0.68 − tol`,
# `cov90 ≥ 0.90 − tol`). The upper side is REPORTED and never gated — gating it would make coverage a
# target, which is the inversion this repo has already paid for twice.

# One-sided slack on the challenger's coverage floors. 0.07 at n≈540 is ~3.5 binomial SE, deliberately
# generous: the floor exists to catch a prior that is sharp AND mis-calibrated, not to referee noise.
COVERAGE_FLOOR_TOL = 0.07
# α for the paired per-cohort NLL test, and the fold-win-rate bar. Both are the E7.12 slice-1 house
# values, transplanted verbatim rather than tuned for this story.
H2H_ALPHA = 0.10
H2H_MIN_FOLD_WIN_RATE = 0.60


@dataclass
class ArmScores:
    """Pooled held-out scores for one arm over the matched eval rows."""
    name: str
    nll: float
    crps: float
    mae: float
    cov68: float
    cov90: float

    def to_dict(self) -> dict:
        return {"arm": self.name, "nll": round(self.nll, 5), "crps": round(self.crps, 6),
                "mae": round(self.mae, 6), "cov68": round(self.cov68, 4), "cov90": round(self.cov90, 4)}


@dataclass
class HeadToHead:
    """Challenger (a prior re-derived from a new MLE) vs the CURRENTLY-SERVED incumbent prior."""
    metric: str
    n_scored: int
    n_cohorts: int
    n_challenger_only: int      # labelled rows the challenger has and the incumbent does not (dropped)
    n_incumbent_only: int       # …and vice-versa (dropped) — a silently-shrunk eval set must be visible
    challenger: ArmScores
    incumbent: ArmScores
    generic: ArmScores                  # degenerate ceiling — must LOSE
    permuted: ArmScores                 # degenerate ceiling — must LOSE
    oracle_challenger: ArmScores        # per-form peeking floor for the challenger — must WIN
    oracle_incumbent: ArmScores         # per-form peeking floor for the incumbent  — must WIN
    cohort_nll_delta: list[float]       # incumbent − challenger per cohort (>0 ⇒ challenger better)
    fold_win_rate: float
    p_one_sided: float | None           # H1: the challenger is systematically better on NLL
    challenger_sigma: float             # final-fold self-calibrated sd (the sd that would be SERVED)
    incumbent_sigma: float
    notes: list[str] = field(default_factory=list)

    # ── the pre-registered per-metric conditions ─────────────────────────────────────────
    @property
    def beats_on_nll(self) -> bool:
        return self.challenger.nll < self.incumbent.nll

    @property
    def beats_on_crps(self) -> bool:
        return self.challenger.crps <= self.incumbent.crps + 1e-9

    @property
    def folds_clear(self) -> bool:
        return self.fold_win_rate >= H2H_MIN_FOLD_WIN_RATE

    @property
    def p_clears(self) -> bool:
        return self.p_one_sided is not None and self.p_one_sided < H2H_ALPHA

    @property
    def coverage_floor_holds(self) -> bool:
        return (self.challenger.cov68 >= 0.68 - COVERAGE_FLOOR_TOL
                and self.challenger.cov90 >= 0.90 - COVERAGE_FLOOR_TOL)

    @property
    def degenerates_lose(self) -> bool:
        """Both degenerate ceilings must lose to the challenger on the primary score."""
        return (self.challenger.nll < self.generic.nll
                and self.challenger.nll < self.permuted.nll)

    @property
    def oracle_floor_holds(self) -> bool:
        """Each arm is floored by the PEEKING version of ITS OWN form (NF-D16 (g‴)). An arm beating its
        own oracle is mathematically impossible ⇒ the tell that the score is inverted, not a win."""
        return (self.challenger.nll >= self.oracle_challenger.nll - 1e-9
                and self.incumbent.nll >= self.oracle_incumbent.nll - 1e-9)

    def gate_detail(self, fdr_survives: bool | None = None) -> dict:
        d = {
            "beats_on_nll": self.beats_on_nll,
            "beats_on_crps": self.beats_on_crps,
            "fold_win_rate>=0.60": self.folds_clear,
            f"p_one_sided<{H2H_ALPHA}": self.p_clears,
            "coverage_floor_holds": self.coverage_floor_holds,
            "degenerate_ceilings_lose": self.degenerates_lose,
            "oracle_floor_holds": self.oracle_floor_holds,
        }
        if fdr_survives is not None:
            d["BH-FDR@0.10"] = bool(fdr_survives)
        return d

    def ships(self, fdr_survives: bool | None = None) -> bool:
        """SHIP iff every pre-registered condition holds. A metric that does not ship keeps the SERVED
        incumbent VERBATIM (per-metric, not all-or-nothing — the E7.12 emission precedent)."""
        return all(self.gate_detail(fdr_survives).values())

    def to_dict(self, fdr_survives: bool | None = None) -> dict:
        return {
            "metric": self.metric, "n_scored": self.n_scored, "n_cohorts": self.n_cohorts,
            "n_challenger_only": self.n_challenger_only, "n_incumbent_only": self.n_incumbent_only,
            "challenger": self.challenger.to_dict(), "incumbent": self.incumbent.to_dict(),
            "generic": self.generic.to_dict(), "permuted": self.permuted.to_dict(),
            "oracle_challenger": self.oracle_challenger.to_dict(),
            "oracle_incumbent": self.oracle_incumbent.to_dict(),
            "cohort_nll_delta": [round(float(x), 6) for x in self.cohort_nll_delta],
            "fold_win_rate": round(self.fold_win_rate, 4),
            "p_one_sided": None if self.p_one_sided is None else round(self.p_one_sided, 6),
            "challenger_sigma": round(self.challenger_sigma, 6),
            "incumbent_sigma": round(self.incumbent_sigma, 6),
            "gate": self.gate_detail(fdr_survives),
            "ships": self.ships(fdr_survives),
            "notes": self.notes,
        }


def _one_sided_paired_p(delta: np.ndarray) -> float | None:
    """One-sided paired t on the per-cohort deltas. H1: delta > 0 (the challenger is better).

    A zero-variance delta is NOT untestable — a constant advantage is the MOST systematic case there is
    (the NF1.7 (a) hole, facing the other way), so it is decided on the sign."""
    d = np.asarray(delta, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return None
    if np.std(d, ddof=1) == 0:
        return 0.0 if float(np.mean(d)) > 0 else 1.0
    from scipy import stats
    t = float(np.mean(d) / (np.std(d, ddof=1) / np.sqrt(len(d))))
    return float(stats.t.sf(t, df=len(d) - 1))


def _score(y: np.ndarray, mu: np.ndarray, sd: np.ndarray, name: str) -> ArmScores:
    nll = float(np.mean([_norm_nll(np.array([a]), np.array([b]), c)[0] for a, b, c in zip(y, mu, sd)]))
    crps = float(np.mean([_norm_crps(np.array([a]), np.array([b]), c)[0] for a, b, c in zip(y, mu, sd)]))
    r = np.abs(y - mu)
    return ArmScores(name=name, nll=nll, crps=crps, mae=float(np.mean(r)),
                     cov68=float(np.mean(r <= sd)), cov90=float(np.mean(r <= 1.645 * sd)))


def head_to_head_metric(challenger_proj: pd.DataFrame, incumbent_proj: pd.DataFrame, metric: str,
                        highest_level_only: bool = True, seed: int = 7) -> HeadToHead:
    """Purged leave-one-debut-cohort-out head-to-head for one metric, on the MATCHED eval rows.

    Both frames are `mle_projections`-shaped (a `mle_<metric>` emission + the realized `mlb_<metric>`
    label + `debut_cohort`, with `has_mlb_label` merged in). The realized label is taken from the
    INCUMBENT frame so the two arms are scored against a byte-identical target."""
    ch = _labelled(challenger_proj, metric, highest_level_only)
    inc = _labelled(incumbent_proj, metric, highest_level_only)
    for d, who in ((ch, "challenger"), (inc, "incumbent")):
        if "debut_cohort" not in d:
            raise ValueError(f"[{metric}] {who} projections carry no debut_cohort — cannot purge by cohort")

    ch = ch[ch["debut_cohort"].notna()].copy()
    inc = inc[inc["debut_cohort"].notna()].copy()
    ch_ids, inc_ids = set(ch["player_id"]), set(inc["player_id"])
    n_ch_only, n_inc_only = len(ch_ids - inc_ids), len(inc_ids - ch_ids)

    # MATCHED population: score both arms on exactly the same rows (NF1.9 (f)).
    merged = inc[["player_id", "level", "debut_cohort", "_mlb", "_mle"]].rename(
        columns={"_mle": "_inc", "level": "_inc_level"}
    ).merge(
        ch[["player_id", "_mle", "level"]].rename(columns={"_mle": "_ch", "level": "_ch_level"}),
        on="player_id", how="inner",
    )
    if merged.empty:
        raise ValueError(f"[{metric}] the challenger and incumbent share no labelled players")
    merged["debut_cohort"] = merged["debut_cohort"].astype(int)

    notes: list[str] = []
    lvl_mismatch = int((merged["_inc_level"].astype(str) != merged["_ch_level"].astype(str)).sum())
    if lvl_mismatch:
        notes.append(f"{lvl_mismatch} matched players resolve to a DIFFERENT highest level across the two "
                     "projection sets — their translations are not like-for-like")
    if n_ch_only or n_inc_only:
        notes.append(f"eval set matched to the intersection: dropped {n_ch_only} challenger-only and "
                     f"{n_inc_only} incumbent-only labelled players")

    cohorts = sorted(merged["debut_cohort"].unique())
    eval_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(eval_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable cohorts; got {eval_cohorts}")

    rng = np.random.default_rng(seed)
    parts: dict[str, list[np.ndarray]] = {k: [] for k in
                                          ("y", "ch_mu", "inc_mu", "gen_mu", "perm_mu",
                                           "orc_ch_mu", "orc_inc_mu", "ch_sd", "inc_sd", "gen_sd")}
    per_cohort_delta: list[float] = []
    ch_sigma = inc_sigma = float("nan")

    for y_ in eval_cohorts:
        prior = merged[merged["debut_cohort"] < y_]
        test = merged[merged["debut_cohort"] == y_]
        if prior.empty or test.empty:
            continue
        # each arm self-calibrated on ITS OWN prior-cohort residuals (no sd handicap)
        ch_sd = float(np.std((prior["_mlb"] - prior["_ch"]).to_numpy(float), ddof=1)) or 1e-6
        inc_sd = float(np.std((prior["_mlb"] - prior["_inc"]).to_numpy(float), ddof=1)) or 1e-6
        gen_sd = float(np.std(prior["_mlb"].to_numpy(float), ddof=1)) or 1e-6
        gen_mean = float(prior["_mlb"].mean())
        ch_sigma, inc_sigma = ch_sd, inc_sd      # the last fold's sd ≈ what would be SERVED

        yv = test["_mlb"].to_numpy(float)
        chv = test["_ch"].to_numpy(float)
        incv = test["_inc"].to_numpy(float)
        # degenerate ceiling #2: the challenger's OWN means permuted within the held-out cohort — the
        # marginal distribution is preserved EXACTLY, only the per-player pairing is destroyed.
        permv = chv.copy()
        rng.shuffle(permv)
        # per-FORM peeking floors: each arm shifted by the held-out cohort's own mean residual
        orc_chv = chv + float(np.mean(yv - chv))
        orc_incv = incv + float(np.mean(yv - incv))

        n = len(test)
        parts["y"].append(yv)
        parts["ch_mu"].append(chv)
        parts["inc_mu"].append(incv)
        parts["gen_mu"].append(np.full(n, gen_mean))
        parts["perm_mu"].append(permv)
        parts["orc_ch_mu"].append(orc_chv)
        parts["orc_inc_mu"].append(orc_incv)
        parts["ch_sd"].append(np.full(n, ch_sd))
        parts["inc_sd"].append(np.full(n, inc_sd))
        parts["gen_sd"].append(np.full(n, gen_sd))

        # paired per-cohort NLL delta (incumbent − challenger; >0 ⇒ the challenger is better)
        ch_nll = float(np.mean(_norm_nll(yv, chv, ch_sd)))
        inc_nll = float(np.mean(_norm_nll(yv, incv, inc_sd)))
        per_cohort_delta.append(inc_nll - ch_nll)

    cat = {k: np.concatenate(v) for k, v in parts.items()}
    d = np.asarray(per_cohort_delta, float)
    return HeadToHead(
        metric=metric, n_scored=int(len(cat["y"])), n_cohorts=len(per_cohort_delta),
        n_challenger_only=n_ch_only, n_incumbent_only=n_inc_only,
        challenger=_score(cat["y"], cat["ch_mu"], cat["ch_sd"], "challenger"),
        incumbent=_score(cat["y"], cat["inc_mu"], cat["inc_sd"], "incumbent"),
        generic=_score(cat["y"], cat["gen_mu"], cat["gen_sd"], "generic_degenerate"),
        permuted=_score(cat["y"], cat["perm_mu"], cat["ch_sd"], "permuted_challenger_degenerate"),
        oracle_challenger=_score(cat["y"], cat["orc_ch_mu"], cat["ch_sd"], "oracle_challenger"),
        oracle_incumbent=_score(cat["y"], cat["orc_inc_mu"], cat["inc_sd"], "oracle_incumbent"),
        cohort_nll_delta=[float(x) for x in d],
        fold_win_rate=float(np.mean(d > 0)) if len(d) else 0.0,
        p_one_sided=_one_sided_paired_p(d),
        challenger_sigma=ch_sigma, incumbent_sigma=inc_sigma, notes=notes,
    )


def head_to_head(challenger_proj: pd.DataFrame, incumbent_proj: pd.DataFrame,
                 metrics=PRIOR_METRICS, highest_level_only: bool = True,
                 seed: int = 7) -> dict[str, HeadToHead]:
    return {m: head_to_head_metric(challenger_proj, incumbent_proj, m, highest_level_only, seed)
            for m in metrics}


def bh_fdr(pvals: dict[str, float | None], alpha: float = H2H_ALPHA) -> dict[str, bool]:
    """Benjamini-Hochberg over the per-metric primary contrasts. Three metrics is a three-test family,
    and shipping off three uncorrected p-values is how a family becomes a fishing expedition (NF-D15).
    A metric with no computable p never survives — an unevaluable test is not a passed one."""
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    survive: dict[str, bool] = {k: False for k in pvals}
    if not items:
        return survive
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    kmax = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax = i
    for i, (k, _) in enumerate(items, start=1):
        survive[k] = i <= kmax
    return survive

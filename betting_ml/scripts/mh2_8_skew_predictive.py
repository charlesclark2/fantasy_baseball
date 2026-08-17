"""MH2.8 — does a SKEW-CAPABLE predictive fix the served `total_runs` shape defect?

⚠️ **Not an edge claim.** `best_alpha = 0`. A pricing/calibration study, deploy-held.

MH2.6 (`STANDING_MISCALIBRATION`) measured, on 634 served rows: the PIT is not uniform
(`pit_mdd` 0.0420 vs a calibrated-null median 0.0215, p = 0.008) in BOTH nested windows, while
`bias` (+0.0085) and `Var(z)` (1.065) sit INSIDE their nulls. Realized `z` carries **skew +0.735**.
The served predictive is a symmetric Normal and realized total runs are right-skewed — a blow-up
inning has no left-hand mirror. It is a **SHAPE** error, and it is **STANDING**, so no retrain of
the same family can reach it.

The serving consequence is the reason this study exists: **57.3% of games land below the predictive
median**, so at a line at the model's own mean the product prints `P(over) = 0.500` against a
realized 0.427 — over-stated by ≈7 points at the middle, which is exactly where a totals line sits.

⛔ **This is a FRESH §0.5 pre-registration, not a continuation of MH2.6.** MH2.6's two pre-scoped
Phase-2 branches (σ dynamic range → MH2.5; level/mean → a wide-window retrain) do NOT apply — its
own §6 records that neither is the right instrument for the defect it found. What carries over is
the FINDING and the METHOD (its served-audit harness, its vacuity-floor discipline), never its
decision rule.

The pre-registration is transcribed in the `LOCK 1 … LOCK 11` block below and in
`ablation_results/mh2_8_preregistration.md`, which was committed BEFORE this file computed anything
(the ordering is visible in the branch's git history). The SOURCE is authoritative; a guard test
(`betting_ml/tests/test_mh2_8_skew_predictive.py`) pins the constants that matter.

⭐ **The one design point worth reading before the numbers.** Both pre-registered PRIMARY metrics
are MARGINAL statistics, and a degenerate wins both BY CONSTRUCTION: a predictive that ignores every
feature and emits the unconditional distribution of `total_runs` has a perfectly flat PIT and a zero
`p_over_gap` while carrying ZERO conditional information. That is NF1.8's "a criterion a degenerate
WINS is fatal" in its most literal form. So `climo` is IN THE FIELD to make the inversion visible,
and CRPS enters as a NON-INFERIORITY CONSTRAINT — an arm may not BUY flatness with sharpness.

Snowflake-free: the training matrix is read via `data_loader.set_s3_mode(True)` (DuckDB over the S3
lakehouse) and the served rows via the same lakehouse views MH2.6 uses.

Usage
-----
    # smoke (seconds — proves the code path, NOT a result)
    uv run python betting_ml/scripts/mh2_8_skew_predictive.py --smoke

    # the real run (LAPTOP, > 2 min — an OPERATOR command)
    uv run python betting_ml/scripts/mh2_8_skew_predictive.py
    uv run python betting_ml/scripts/mh2_8_skew_predictive.py --exclude-seasons 2020
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"
_CACHE = PROJECT_ROOT / "betting_ml/data/cache/edge_e1_training_from2016.parquet"
_SERVED_CACHE = PROJECT_ROOT / "betting_ml/data/cache/mh2_8_served.parquet"

STORY = "MH2.8"
BEST_ALPHA = 0
TARGET, TIER = "total_runs", "post_lineup"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PRE-REGISTRATION — every constant below is fixed in SOURCE before any arm is scored.
# ══════════════════════════════════════════════════════════════════════════════════════════════

# LOCK 1 — THE WINDOW. Identical to MH2.1 Lock 1 and MH2.5 Lock 1 so the studies are comparable
# AT THE CONCLUSION LEVEL. (⚠️ NOT at the level of absolute numbers — see LOCK 1b.)
MH28_MIN_YEAR = 2016
MH28_SENSITIVITY_EXCLUDE = (2020,)

#: LOCK 1b — ⚠️ **DECLARED DEVIATION from MH2.5's matrix, stated before any arm was scored.**
#: MH2.5/MH2.1 read `load_clean_matrix`, which applies two E1 de-leak swaps. This study applies
#: NEITHER, and the reason is a mandate rather than a convenience:
#:   * `_swap_stuff_plus_deleaked` needs a live SNOWFLAKE connection, which this story forbids. It
#:     rewrites nine `*_starter_*` arsenal columns — ⭐ NONE of which is in the 13-column contract —
#:     so skipping it is a PROVABLE NO-OP here, and a guard test pins that mechanically.
#:   * `_swap_bullpen_v3` rewrites `{home,away}_bp_eb_uncertainty`, which ARE 2 of the 13. It needs
#:     per-season `per_reliever_*.parquet` caches that are GITIGNORED and absent from this worktree
#:     (the NF-INFRA1 class), and whose rebuild is a Snowflake-bound backfill.
#: ⇒ absolute LEVELS are NOT comparable to MH2.5's and the row count differs from its 20,055. The
#: ARM-TO-ARM comparison — the only thing this study decides on — is unaffected, because every arm
#: reads the IDENTICAL matrix (MH2.5's own Lock 9 logic on a different perturbation).
MH28_APPLY_DELEAK_SWAPS = False
#: The columns `_swap_stuff_plus_deleaked` would rewrite. Pinned so the "provable no-op" claim is
#: MEASURED against the real contract by the guard test rather than asserted in prose.
MH28_STUFF_SWAP_SUFFIXES = (
    "starter_stuff_plus", "starter_fastball_stuff_plus", "starter_slider_stuff_plus",
    "starter_curveball_stuff_plus", "starter_changeup_stuff_plus", "starter_avg_fastball_velo",
    "starter_fastball_pct", "starter_breaking_pct", "starter_offspeed_pct",
)

# LOCK 2 — THE FIELD: 8 trials, DECLARED NOT DISCOVERED (MH2 §a — you get to PRE-REGISTER a family;
# you do not get to DISCOVER one). No arm may be dropped after a score is seen: trimming post hoc
# UNDER-taxes DSR and is a second layer of the very selection bias DSR exists to deflate (MH2.2).
#
#   ── the four candidates, every one skew-capable ──
#   ngb_lognormal    NGBoost LogNormal — right-skewed BY FAMILY, on positive support.
#   ngb_gamma        NGBoost Gamma — right-skewed, variance ∝ mean², the count-like law totals obey.
#   lgbm_quantile    a DISTRIBUTIONAL-QUANTILE learner (LightGBM pinball at a level grid,
#                    monotonised, exponential tails). Expresses ARBITRARY right skew and inherits
#                    nothing from the incumbent — §0.5's required direct-learned foil.
#   skewnorm_recal   ⭐ a SHAPE RECALIBRATION of the incumbent: keep NGBoost's μ and σ, map the
#                    standardised residual through an Azzalini skew-normal whose (a, b, α) are fitted
#                    in-fold on the honest calibration split, moment-matched so the predictive mean
#                    and SD are preserved exactly. NESTS `normal_recal` at α = 0.
#
#   ── the four anchors, all in n_trials and all pre-registered to LOSE ──
#   incumbent      the NGBoost Normal — the served family. THE BAR.
#   normal_recal   ⭐ THE MATCHED FOIL (NF-D15 g′): the IDENTICAL machinery with α CLAMPED TO 0, i.e.
#                  a pure location/scale refit on the same split. Without it a skew arm could win by
#                  fixing the LEVEL or the SCALE while the story claims it fixed the SHAPE.
#   climo          ⚠️ THE NIHILIST — the unconditional empirical predictive, ignoring every feature.
#                  REGISTERED IN ADVANCE TO WIN BOTH PRIMARIES AND TO LOSE CRPS (LOCK 4).
#   overskew       the magnitude degenerate (NF-D20 `over_scale`): `skewnorm_recal` with α × 3.
#                  Registered to LOSE. If it WINS, that is a REFUTED MAGNITUDE HYPOTHESIS — the fit
#                  under-corrects — not a metric inversion, and it is recorded as such, never
#                  re-labelled (E2.1-r).
MH28_CANDIDATES = ("ngb_lognormal", "ngb_gamma", "lgbm_quantile", "skewnorm_recal")
MH28_ANCHORS = ("incumbent", "normal_recal", "climo", "overskew")
MH28_FIELD = MH28_ANCHORS + MH28_CANDIDATES              # n_trials for PBO/DSR = 8
MH28_INCUMBENT_ARM = "incumbent"
MH28_MATCHED_FOIL = "normal_recal"
MH28_NIHILIST = "climo"
#: DSR-CONV (2026-08-08) — a pre-registered LOSE-BY-CONSTRUCTION arm stays in `n_trials` (we DID try
#: it) and leaves `V` (a skill series whose size is fixed BY DESIGN is not a measurement of how much
#: real configurations disperse). ⚠️ FORWARD-ONLY, and this story OPTS IN here, before the run:
#: the exclusion is NON-MONOTONE, so an arm qualifies BY DESIGN and ⛔ never BY DECLARATION.
MH28_DEGENERATES = ("climo", "overskew")
#: ⭐ Clause 1 (the metric-inversion check) reads the SELECTION clauses ONLY. A metric inversion is a
#: property of the METRIC, not of whether the arm that exposed it happens to be DEPLOYABLE — and the
#: nihilist is `SERVED_UNVALIDATABLE` by construction, so folding clause 10 in would make the check
#: pass for a reason with nothing to do with the metric. That is the vacuous-guard shape (NF1.7 (a))
#: occurring INSIDE the check written to catch a bad metric, and it is why this exclusion is a named
#: constant a guard can break rather than an inline list.
MH28_INVERSION_EXCLUDED_CLAUSES = ("1_nihilist_did_not_clear", "10_served_gate")

# LOCK 2b — DIAGNOSTIC ANCHORS ARE ⛔ NEVER TRIALS (MH2.1 (a): the `oracle_floor` DSR-field leak, in
# which the anchor that exists to POLICE the gate silently SET its bar). Excluded from `n_trials`,
# from DSR's `V`, and from PBO.
#   oracle_skewnorm / oracle_lgbm_quantile
#       PER-FORM peeking ceilings at MATCHED n (NF1.7 (b): "peeking can only help" holds only at
#       equal FAMILY *and* equal RESOLUTION; NF-D16 g‴: the forms NEST, so one field-wide ceiling
#       would falsely veto a legitimately-better nested form). ⚠️ A HEADROOM DIAGNOSTIC, NOT A GATE
#       — beating one is a capacity effect, not an inversion (NF-D14).
#   perm_shape
#       ⚠️ REGISTERED IN ADVANCE AS STRUCTURALLY INACTIVE FOR A GLOBAL-α ARM. Permuting one constant
#       α across games is a MATHEMATICAL NO-OP, so this anchor is expected to tie EXACTLY, and a tie
#       is an INACTIVE anchor — ⛔ NOT a passed test (NF-D20; NF-D16 sibling (1)). It is informative
#       only for `lgbm_quantile`, whose shape genuinely varies row to row, and it is read ONLY there.
MH28_PER_FORM_CEILING = {"skewnorm_recal": "oracle_skewnorm",
                         "lgbm_quantile": "oracle_lgbm_quantile"}
MH28_PERM_ARM = "lgbm_quantile"
MH28_DIAGNOSTICS = tuple(MH28_PER_FORM_CEILING.values()) + ("perm_shape",)

# LOCK 3 — THE METRICS.
# `total_runs` is an INTEGER COUNT and every candidate predictive is continuous, so PIT is taken
# with a CONTINUITY CORRECTION and RANDOMISATION, through EACH ARM'S OWN CDF (E2.1-r: gate a
# discrete target on randomised-PIT flatness, never on raw interval coverage — inclusive integer
# bounds INFLATE it, which is the defect that could REWARD under-dispersion).
#
# PRIMARY (two):
#   pit_mdd      max-decile deviation of the randomised PIT. THE STATISTIC THAT FAILED IN MH2.6.
#   p_over_gap   ⭐ THE SERVING-RELEVANT NUMBER. Reference line = the arm's OWN predictive mean;
#                stated `p = 1 − F(L)` minus realized `1[y > L]`. The incumbent's is ≈ +0.073.
#                ⚠️ At the model's own mean this BOUNDS the SHAPE error; on the SERVED leg it is
#                also measured AT THE ACTUAL POSTED LINE — registered here so the posted-line read
#                cannot be mistaken for a post-hoc addition (it is the gap MH2.6's §2 flagged and
#                could not close).
# CONSTRAINTS (⛔ never selection criteria): CRPS non-inferiority (LOCK 4) and the coverage FLOOR.
# SECONDARY (reported, verdict-inert): CRPS, `rms_var_z` on a VALIDATED stratifier only, realized
# `z` skew/kurtosis, `mass_below_predictive_median`, `pit_ks`.
MH28_PRIMARIES = ("pit_mdd", "p_over_gap")
#: Quantile grid used for the CRPS identity `CRPS = 2∫ pinball_τ dτ` and for the moments of arms
#: without a closed form. ⭐ Computed the SAME way for EVERY arm — a per-arm mixture of closed forms
#: and grid approximations would put a systematic arm-to-arm bias inside a non-inferiority
#: constraint. The Normal closed form is reported beside it purely to validate the estimator.
MH28_CRPS_LEVELS = 499
#: The LightGBM pinball levels actually FITTED. The dense CDF/quantile function is built from these
#: by monotonisation + interpolation + EXPONENTIAL tail extension — a flat tail beyond the fitted
#: grid is a known serving-representation defect (NF-MARGIN1), not a neutral default.
MH28_LGBM_LEVELS = (0.01, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50,
                    0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99)

# LOCK 3b — THE COVERAGE FLOOR. ⛔ A FLOOR, NEVER A TARGET (E2.1-r / NF1.8: a coverage target is
# MONOTONE IN WIDENING and the `max_width` degenerate wins it outright). Derived from a DESIGN
# quantity — MH2.6's calibrated-null 95% band at the SERVED n, whose lower edges were 0.7697
# (`cov80`) and 0.4606 (`cov50`) — rounded DOWN so a correctly-specified predictive clears them with
# margin at this n. ⛔ Never tightened above nominal "for safety" (NF1.8 (a)).
MH28_COV80_FLOOR = 0.75
MH28_COV50_FLOOR = 0.45

# LOCK 5 — THE PRACTICALLY-MEANINGFUL EFFECTS. All three are derived from DESIGN quantities and
# fixed in advance; a threshold reverse-engineered from the answer is not a threshold (NF1.8).
#: The HALF-WIDTH of MH2.6's calibrated-null 95% band for `pit_mdd` at the served n
#: ([0.0117, 0.0356] around a 0.0215 median). An improvement smaller than the null band's own width
#: ON THE POPULATION THAT MATTERS is not distinguishable from sampling noise there, however
#: significant it may be on 14k CV rows.
MH28_MEANINGFUL_PIT_MDD_GAIN = 0.012
#: The product prints `P(over)` as a percentage; two points is the resolution at which the displayed
#: number changes for a user, and it is a quarter of the observed 0.073 defect.
MH28_MEANINGFUL_P_OVER_GAP = 0.020
#: INHERITED VERBATIM from MH2.5's `pre_registered_meaningful_crps_lift = 0.02`, so the
#: non-inferiority band is the program's existing notion of a material CRPS move rather than a new
#: number invented for this study.
MH28_CRPS_TOLERANCE = 0.020

# LOCK 6 — THE STRATIFIER IS VALIDATED FIRST, OR NOTHING IS READ OFF IT. Bars imported from MH2.5
# VERBATIM (`STRATIFIER_MIN_RHO = 0.30`, `STRATIFIER_MIN_ENDPOINT_SE = 2.0`), not re-declared.
# ⚠️ Stated in advance so a failure is not mistaken for a result: MH2.5 found this partition FAILS
# when pooled across 2016–2026 (σ deciles sort largely by ERA) and MH2.6 found it FAILS on the
# RECENT served window (≈1,155 served games needed). A disqualification here is the EXPECTED outcome
# and carries NO information about the skew hypothesis — `Var(z)` is a SCALE instrument and this
# study is about SHAPE.
MH28_STRATIFIERS = ("incumbent_sigma", "incumbent_mean")
MH28_PRIMARY_STRATIFIER = "incumbent_sigma"
MH28_N_STRATA = 10

# LOCK 7 — THE VACUITY FLOOR. Five controls, all run regardless of the result. A verdict is
# worthless if the instrument could not have produced the other one.
#: ⭐ NEGATIVE CONTROL — clean data must NOT flag. Outcomes redrawn from the incumbent's OWN
#: per-fold predictive (n and per-game μ/σ held fixed), the selection re-run, and the winner
#: recorded. A harness that picks a skew arm on NORMAL data has not found skew in the real data —
#: it has found its own preference. Acceptance is pre-stated and two-sided.
MH28_NEG_CONTROL_REPS = 40
MH28_NEG_CONTROL_MIN_CLEAN = 0.90
#: POSITIVE CONTROL — a KNOWN skew must fire and must be SELECTED.
MH28_POS_CONTROL_ALPHA = 3.0
#: MDE grid over the true skew-normal shape α. Reported at 80% power, in the unit that GROWS.
MH28_MDE_ALPHA_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
MH28_MDE_REPS = 120
MH28_TARGET_POWER = 0.80
#: NON-DEGENERATE MC-p FLOOR — enough null reps that the SMALLEST attainable p is below the BH
#: cutoff. A p-value that cannot reach its own threshold is a vacuous test (MH2.6).
MH28_NULL_REPS = 2000
SEED = 42

# LOCK 8 — DEFLATION AND THE CV GATES. Unchanged from the program's standing bars.
PBO_MAX = 0.2
DSR_MIN_CONF = 0.95
BH_Q = 0.05
EMBARGO_DAYS = 3
#: LOCK 8b — the honest calibration split: the last CAL_FRACTION of each fold's TRAINING rows by
#: date, held OUT of the learner fit, so every recalibrator sees only OUT-OF-SAMPLE residuals.
#: Fitting a shape recalibration on IN-SAMPLE residuals would understate the tail the study is
#: about, so this split is load-bearing, not hygiene (MH2.5 Lock 7).
CAL_FRACTION = 0.20
#: Bounds on the fitted skew-normal shape. Wide enough that the fit is never at a bound for a real
#: skew of ~0.75 (α ≈ 2 reproduces it); tight enough that the NLL stays numerically sane.
ALPHA_BOUNDS = (-8.0, 8.0)
#: The magnitude degenerate's multiplier (NF-D20 `over_scale`).
OVERSKEW_K = 3.0

# LOCK 9 — THE SERVED-ROW GATE AND ITS PRE-REGISTERED ASYMMETRY.
# MH2.1 was rolled back PRECISELY because a backtest conclusion did not survive the served
# population, so a CV win is necessary and NOT SUFFICIENT.
# ⚠️ Only an arm that is a FUNCTION OF THE SERVED (μ, σ) can be evaluated on served rows. A
# learned-family arm would have to be re-scored from features, and the offline matrix is NOT
# POINT-IN-TIME (MH2.5 Lock 9) — a re-score would be a CEILING, not the served number, which is the
# exact substitution MH2.1's rollback punished. ⇒ a `SERVED_UNVALIDATABLE` arm ⛔ CANNOT SHIP.
MH28_SERVED_EVALUABLE = ("incumbent", "normal_recal", "skewnorm_recal", "overskew")
#: The served era begins at the E13.11 champion's fit date, so the whole served window is out of
#: sample and MH2.1's "split a same-season backtest at the incumbent's fit date" rule holds BY
#: CONSTRUCTION. The recalibration applied to it is the LAST CV FOLD's, whose calibration split ends
#: before the 2026 season — i.e. strictly BEFORE this date, so the served read is prospective.
MH28_SERVED_ERA_START = "2026-06-23"

# LOCK 10 — THE SHIP RULE lives in `_decide`. Default verdict: INCUMBENT_STANDS.
# LOCK 11 — PROMOTION IS DEPLOY-HELD; the MH2.1 landmines are restated in the report and the
# pre-registration. This harness NEVER writes a registry entry, a pickle or a serving artifact.
MH28_PROMOTION_LANDMINES = (
    "A ONE-TARGET SWAP BREAKS BUNDLE-ASSUMING CONSUMERS — `daily_model_predictions.model_version` "
    "is stamped from `registry['home_win']` only, the backfill idempotency key is "
    "`(game_pk, model_version, retrain_tag)`, and `mart_clv_labeled_games` hardcodes `v6`.",
    "SERVE THE OBJECT THAT WAS VALIDATED, NOT A RE-DERIVATION — a skew layer is a DIFFERENT "
    "distributional family, not a re-parameterisation; `predict_today`/the backfill call NGBoost's "
    "`pred_dist(X).params` verbatim, so whatever ships must persist exactly what was scored here.",
    "A MODEL-REGISTRY CHANGE SHIPS WITH THE BOX IMAGE ON MERGE TO `main` (`orchestration_cd.yml` "
    "`COPY . .`) — MERGING **IS** THE DEPLOY, with no gate between merge and serve.",
    "`best_alpha = 0` — no bet rides on this model, which is what made MH2.1's rollback cost one "
    "registry edit.",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PREDICTIVES — one interface, so every arm is scored by identical code
# ══════════════════════════════════════════════════════════════════════════════════════════════

class Predictive:
    """A per-row continuous predictive distribution over `total_runs`.

    Subclasses supply `cdf` and `ppf`; everything the study scores is derived from those by shared
    code, so no arm can win because it was measured differently from another.
    """

    n: int

    def cdf(self, x: np.ndarray) -> np.ndarray:          # pragma: no cover - interface
        raise NotImplementedError

    def ppf(self, q: np.ndarray | float) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    # ── shared derivations ────────────────────────────────────────────────────────────────────
    def _grid(self) -> tuple[np.ndarray, np.ndarray]:
        """(levels, quantiles[n, L]) on the shared CRPS grid — cached per instance."""
        if getattr(self, "_grid_cache", None) is None:
            lv = (np.arange(1, MH28_CRPS_LEVELS + 1) - 0.5) / MH28_CRPS_LEVELS
            self._grid_cache = (lv, np.column_stack([self.ppf(t) for t in lv]))
        return self._grid_cache

    def mean(self) -> np.ndarray:
        lv, Q = self._grid()
        return Q.mean(axis=1)

    def sd(self) -> np.ndarray:
        lv, Q = self._grid()
        return np.sqrt(np.maximum(Q.var(axis=1), 1e-12))

    def crps(self, y: np.ndarray) -> np.ndarray:
        """`CRPS = 2∫₀¹ pinball_τ(y, q_τ) dτ` — the exact identity, on the shared grid."""
        lv, Q = self._grid()
        y = np.asarray(y, float)[:, None]
        d = y - Q
        return 2.0 * np.mean(np.where(d >= 0, lv[None, :] * d, (lv[None, :] - 1.0) * d), axis=1)


@dataclass
class NormalPred(Predictive):
    mu: np.ndarray
    sigma: np.ndarray

    def __post_init__(self):
        self.mu = np.asarray(self.mu, float)
        self.sigma = np.maximum(np.asarray(self.sigma, float), 1e-9)
        self.n = len(self.mu)
        self._grid_cache = None

    def cdf(self, x):
        from scipy.stats import norm
        return norm.cdf((np.asarray(x, float) - self.mu) / self.sigma)

    def ppf(self, q):
        from scipy.stats import norm
        return self.mu + self.sigma * norm.ppf(q)

    def mean(self):
        return self.mu

    def sd(self):
        return self.sigma

    def crps_closed_form(self, y) -> np.ndarray:
        """Reported BESIDE the grid estimator purely to validate it — never used for a verdict."""
        from scipy.stats import norm
        z = (np.asarray(y, float) - self.mu) / self.sigma
        return self.sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1.0 / np.sqrt(np.pi))


@dataclass
class SkewNormalPred(Predictive):
    """Azzalini skew-normal, MOMENT-MATCHED to a target mean and SD.

    Parameterised by (mean, sd, α) rather than (ξ, ω, α) so that **α is the only thing that changes
    the SHAPE** — the mean and SD are held exactly. That is what makes `skewnorm_recal` vs
    `normal_recal` a MATCHED PAIR differing in one respect (NF-D15 g′): at α = 0 the two are
    byte-identical, so any difference between them is attributable to skew and to nothing else.
    """
    target_mean: np.ndarray
    target_sd: np.ndarray
    alpha: np.ndarray

    def __post_init__(self):
        m = np.asarray(self.target_mean, float)
        s = np.maximum(np.asarray(self.target_sd, float), 1e-9)
        a = np.broadcast_to(np.asarray(self.alpha, float), m.shape).astype(float)
        d = a / np.sqrt(1.0 + a ** 2)
        b = np.sqrt(2.0 / np.pi)
        self.omega = s / np.sqrt(np.maximum(1.0 - (b * d) ** 2, 1e-12))
        self.xi = m - self.omega * b * d
        self.a = a
        self._m, self._s = m, s
        self.n = len(m)
        self._grid_cache = None

    def cdf(self, x):
        from scipy.stats import skewnorm
        return skewnorm.cdf(np.asarray(x, float), self.a, loc=self.xi, scale=self.omega)

    def ppf(self, q):
        from scipy.stats import skewnorm
        return skewnorm.ppf(q, self.a, loc=self.xi, scale=self.omega)

    # ⭐ EXACT by construction — the parameterisation moment-matches, so the mean and SD are the
    # targets themselves. Reading them off the quantile grid instead would be both slower and
    # slightly WRONG (a grid approximation), and it is what made the control sweep intractable.
    def mean(self):
        return self._m

    def sd(self):
        return self._s


@dataclass
class ScipyPred(Predictive):
    """Any frozen scipy continuous distribution with per-row parameters (LogNormal / Gamma)."""
    dist: object
    params: dict

    def __post_init__(self):
        any_p = next(iter(self.params.values()))
        self.n = len(np.asarray(any_p, float))
        self._grid_cache = None

    def cdf(self, x):
        return self.dist.cdf(np.asarray(x, float), **self.params)

    def ppf(self, q):
        return self.dist.ppf(q, **self.params)


@dataclass
class ClimoPred(Predictive):
    """⚠️ THE NIHILIST — the unconditional empirical predictive, identical for every row.

    Built as the empirical CDF of the TRAINING integers, read at the half-integer breakpoints the
    continuity-corrected PIT uses. Under `y_eval ~ y_train` its randomised PIT is EXACTLY uniform,
    which is precisely why it is in the field: it makes the marginal-metric inversion visible
    instead of leaving it to be reasoned about (NF1.8).
    """
    train_y: np.ndarray
    n_rows: int

    def __post_init__(self):
        v = np.asarray(self.train_y, float)
        self.support = np.arange(np.floor(v.min()) - 1, np.ceil(v.max()) + 2)
        counts = np.array([np.mean(v <= s) for s in self.support])
        self.cum = counts
        self._mu, self._sd = float(v.mean()), float(v.std(ddof=1))
        self.n = int(self.n_rows)
        self._grid_cache = None

    def _cdf1(self, x: np.ndarray) -> np.ndarray:
        return np.interp(x, self.support, self.cum, left=0.0, right=1.0)

    def cdf(self, x):
        return self._cdf1(np.asarray(x, float))

    def ppf(self, q):
        qq = np.atleast_1d(np.asarray(q, float))
        v = np.interp(qq, self.cum, self.support)
        return np.full(self.n, float(v[0])) if v.size == 1 else v

    def mean(self):
        return np.full(self.n, self._mu)

    def sd(self):
        return np.full(self.n, self._sd)


@dataclass
class QuantilePred(Predictive):
    """A distributional-quantile learner's output: per-row quantiles at a fitted level grid.

    Monotonised (a crossing is a fitting artifact, not a distribution), then extended beyond the
    fitted grid with EXPONENTIAL tails — a FLAT extension past the outermost fitted knot is a known
    serving-representation defect that leaves the predictive with no tails at all (NF-MARGIN1), and
    it would silently reward this arm on a metric that reads the middle.
    """
    levels: np.ndarray
    q: np.ndarray                     # (n, len(levels))

    def __post_init__(self):
        self.levels = np.asarray(self.levels, float)
        self.q = np.maximum.accumulate(np.asarray(self.q, float), axis=1)
        self.n = self.q.shape[0]
        lo_w = np.maximum(self.q[:, 1] - self.q[:, 0], 1e-3)
        hi_w = np.maximum(self.q[:, -1] - self.q[:, -2], 1e-3)
        self.lo_scale = lo_w / max(np.log(self.levels[1] / self.levels[0]), 1e-6)
        self.hi_scale = hi_w / max(np.log((1 - self.levels[-2]) / (1 - self.levels[-1])), 1e-6)
        self._grid_cache = None

    def cdf(self, x):
        x = np.asarray(x, float)
        out = np.empty(self.n)
        for i in range(self.n):
            out[i] = np.interp(x[i], self.q[i], self.levels)
        below = x < self.q[:, 0]
        above = x > self.q[:, -1]
        # ⚠️ clipped: a CDF evaluated far outside the fitted grid otherwise overflows `exp` and
        # returns a nan, which would silently corrupt this arm's PIT rather than error.
        lo_t = np.clip((x - self.q[:, 0]) / self.lo_scale, -700.0, 0.0)
        hi_t = np.clip((x - self.q[:, -1]) / self.hi_scale, 0.0, 700.0)
        out = np.where(below, self.levels[0] * np.exp(lo_t), out)
        out = np.where(above, 1.0 - (1 - self.levels[-1]) * np.exp(-hi_t), out)
        return np.clip(out, 1e-9, 1 - 1e-9)

    def ppf(self, q):
        t = float(q)
        if t < self.levels[0]:
            return self.q[:, 0] + self.lo_scale * np.log(t / self.levels[0])
        if t > self.levels[-1]:
            return self.q[:, -1] - self.hi_scale * np.log((1 - t) / (1 - self.levels[-1]))
        return np.array([np.interp(t, self.levels, self.q[i]) for i in range(self.n)])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE SHAPE RECALIBRATION — the matched pair, one machinery, one extra parameter
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: ⭐⭐ **THE α = 0 STATIONARY POINT — the defect that would have produced a perfectly clean FALSE
#: NULL, and the reason this study has a positive control.** The Azzalini skew-normal's information
#: matrix is SINGULAR at α = 0 and its profile likelihood is FLAT there, so a gradient optimiser
#: started at α = 0 reports α̂ = 0 with `success=True` and never moves. Measured on this harness's
#: first smoke run: **α̂ = 0.000 in ALL EIGHT folds**, on data whose realized skew is +0.735.
#: Downstream that is invisible and catastrophic — `skewnorm_recal` becomes byte-identical to its
#: own matched foil, the paired delta is exactly zero, and the study reports "no skew arm helps"
#: with every gate green. The cure is a MULTI-START whose seeds straddle zero on both sides;
#: what CAUGHT it is the pre-registered positive control (LOCK 7), which is precisely the vacuity
#: floor's purpose — an instrument that cannot find a KNOWN defect cannot be trusted on an unknown
#: one (NF1.7 (a)).
ALPHA_STARTS = (-4.0, -2.0, -0.5, 0.5, 2.0, 4.0)


def fit_shape_recal(mu_cal, sigma_cal, y_cal, *, allow_skew: bool) -> dict:
    """Fit `(a, b, α)` on the honest calibration split by skew-normal NLL.

    ⭐ **The matched pair is built from ONE function.** `allow_skew=False` clamps α to 0 and gives
    `normal_recal` — a pure location/scale refit; `allow_skew=True` gives `skewnorm_recal`, which
    NESTS it. Sharing the code is what guarantees the two arms differ in EXACTLY one respect. A
    separately-written foil could differ in an optimiser, a bound or a starting point, and then the
    paired delta would no longer isolate skew (NF-D15 g′).

    ⚠️ See `ALPHA_STARTS` — the multi-start is LOAD-BEARING, not hygiene.
    """
    from scipy.optimize import minimize
    from scipy.stats import skewnorm

    mu = np.asarray(mu_cal, float)
    sg = np.maximum(np.asarray(sigma_cal, float), 1e-9)
    y = np.asarray(y_cal, float)

    def nll(p):
        al = float(p[2]) if allow_skew else 0.0
        pred = SkewNormalPred(mu + float(p[0]), float(np.exp(p[1])) * sg, al)
        lp = skewnorm.logpdf(y, pred.a, loc=pred.xi, scale=pred.omega)
        return float(-np.sum(lp)) if np.all(np.isfinite(lp)) else 1e12

    bounds = [(-5.0, 5.0), (np.log(0.4), np.log(2.5)),
              ALPHA_BOUNDS if allow_skew else (0.0, 0.0)]
    starts = [0.0] if not allow_skew else [0.0, *ALPHA_STARTS]
    best = None
    for a0 in starts:
        res = minimize(nll, [0.0, 0.0, a0], method="L-BFGS-B", bounds=bounds)
        if best is None or res.fun < best.fun:
            best = res
    a, b = float(best.x[0]), float(np.exp(best.x[1]))
    al = float(best.x[2]) if allow_skew else 0.0
    return {"a": a, "b": b, "alpha": al, "nll": float(best.fun),
            "converged": bool(best.success), "n_starts": len(starts)}


def apply_shape_recal(mu, sigma, p: dict, *, alpha_scale: float = 1.0) -> SkewNormalPred:
    al = float(np.clip(p["alpha"] * alpha_scale, -30.0, 30.0))
    return SkewNormalPred(np.asarray(mu, float) + p["a"],
                          p["b"] * np.asarray(sigma, float), al)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE STATISTICS
# ══════════════════════════════════════════════════════════════════════════════════════════════

def randomized_pit(y, pred: Predictive, rng) -> np.ndarray:
    """PIT with a CONTINUITY CORRECTION and randomisation, through the arm's OWN CDF.

    `total_runs` is an integer and the predictive is continuous. Reading `F(y)` straight off an
    integer outcome is lumpy, and reading interval coverage off inclusive integer bounds INFLATES it
    — the exact defect E2.1-r found could REWARD under-dispersion. Spreading each integer over the
    probability mass its unit interval carries is uniform under a correctly specified predictive, at
    any scale and any shape.
    """
    y = np.asarray(y, float)
    lo = pred.cdf(y - 0.5)
    hi = pred.cdf(y + 0.5)
    return np.clip(lo + rng.uniform(size=len(lo)) * (hi - lo), 1e-12, 1 - 1e-12)


def pit_mdd(u: np.ndarray) -> float:
    """Max-decile deviation — the PRIMARY flatness statistic (E2.1-r)."""
    dec = np.histogram(u, bins=np.linspace(0, 1, 11))[0] / max(len(u), 1)
    return float(np.max(np.abs(dec - 0.1)))


def p_over_at(y, pred: Predictive, line: np.ndarray) -> dict:
    """⭐ The serving-relevant read: stated `P(over)` minus realized, at a given line."""
    line = np.asarray(line, float)
    stated = 1.0 - pred.cdf(line)
    realized = (np.asarray(y, float) > line).astype(float)
    n = max(len(realized), 1)
    return {
        "p_over_stated": float(np.mean(stated)),
        "p_over_realized": float(np.mean(realized)),
        "p_over_gap": float(np.mean(stated) - np.mean(realized)),
        "p_over_gap_se": float(np.sqrt(np.var(realized) / n)),
        "n": int(n),
    }


def score_arm(y, pred: Predictive, rng, *, strat_labels=None) -> dict:
    """Every scored quantity for one arm, from the shared interface. Identical code for all arms."""
    from scipy.stats import kstest, kurtosis, skew

    y = np.asarray(y, float)
    u = randomized_pit(y, pred, rng)
    m, s = pred.mean(), pred.sd()
    z = (y - m) / np.maximum(s, 1e-12)
    out = {
        "pit_mdd": pit_mdd(u),
        "pit_ks": float(kstest(u, "uniform").statistic),
        "crps": float(np.mean(pred.crps(y))),
        # ⛔ coverage read off the RANDOMISED PIT, never off inclusive integer bounds (E2.1-r).
        "cov80": float(np.mean((u >= 0.10) & (u <= 0.90))),
        "cov50": float(np.mean((u >= 0.25) & (u <= 0.75))),
        "mass_below_predictive_median": float(np.mean(u < 0.5)),
        "bias": float(np.mean(y - m)),
        "var_z_pooled": float(np.var(z, ddof=1)),
        "z_skew": float(skew(z)),
        "z_excess_kurtosis": float(kurtosis(z)),
        "mean_sigma": float(np.mean(s)),
    }
    out.update({k: v for k, v in p_over_at(y, pred, m).items()})
    if strat_labels is not None:
        from betting_ml.scripts.mh2_5_sigma_recalibration import rms_var_z
        rms, _bins = rms_var_z(z, strat_labels)
        out["rms_var_z"] = float(rms)
    return out


def uniform_mdd_null(n: int, reps: int, seed: int) -> dict:
    """⭐ **THE CONSTRUCTION FLOOR — the only thing nothing may beat.**

    Under a correctly specified predictive the randomised PIT is EXACTLY uniform, so the attainable
    `pit_mdd` at `n` rows is the MDD of `n` iid uniforms. That is a CONSTRUCTION, not a fit, so an
    arm scoring below its extreme lower tail is mathematically impossible and means the metric is
    inverted ⇒ HALT (E2.1-r's oracle-floor discipline, available here in closed form rather than
    fitted, which also sidesteps NF1.7 (b)'s matched-n problem entirely).
    """
    rng = np.random.default_rng(seed)
    draws = np.array([pit_mdd(rng.uniform(size=n)) for _ in range(reps)])
    return {
        "n": int(n), "reps": int(reps),
        "median": float(np.median(draws)),
        "p001": float(np.percentile(draws, 0.1)),
        "p025": float(np.percentile(draws, 2.5)),
        "p975": float(np.percentile(draws, 97.5)),
    }


def mc_pvalue(draws: np.ndarray, observed: float) -> float:
    """Two-sided MC p with the (r+1)/(n+1) correction — it can never return a vacuous 0."""
    d = np.asarray(draws, float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return float("nan")
    centre = float(np.median(d))
    r = int(np.sum(np.abs(d - centre) >= abs(observed - centre)))
    return float((r + 1) / (d.size + 1))


def min_null_reps(family_size: int, q: float = BH_Q) -> int:
    """The MC-p floor: enough reps that the SMALLEST attainable p clears the BH cutoff.

    The strictest BH cutoff in a family of `m` is `q/m`, and the smallest attainable MC p is
    `1/(reps+1)`. A test whose p CANNOT reach its own threshold is vacuous (NF1.7 (a)).
    """
    return int(np.ceil(family_size / q))


def bh_reject(pvals: dict[str, float], q: float = BH_Q) -> set[str]:
    """Benjamini–Hochberg at `q` — MH2.6 measured that omitting this drove the family-wise error to
    ≈50% and produced two wrong verdicts on CLEAN synthetic frames. Imported, not re-learnt."""
    items = sorted(((k, v) for k, v in pvals.items() if np.isfinite(v)), key=lambda kv: kv[1])
    m = len(items)
    keep: set[str] = set()
    for i, (k, p) in enumerate(items, 1):
        if p <= q * i / m:
            keep = {kk for kk, _ in items[:i]}
    return keep


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE ARMS — fitted per fold
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _ngboost(dist: str, X_inner, y_inner, *, seed: int, smoke: bool):
    """Fit one NGBoost family and return a callable emitting a `Predictive` on arbitrary rows.

    🪤 **`NGBRegressor(random_state=...)` DOES NOT SEED ITS BASE LEARNER** — the default
    `DecisionTreeRegressor` is built with `random_state=None` and breaks split ties off numpy's
    GLOBAL RNG, so two fits of the identical class on identical rows with the identical `seed`
    disagree (MH2.5 measured per-game σ differing by up to 0.30 at serving scale). Seeding the
    global RNG immediately before each fit is what makes this study reproducible.
    """
    from ngboost import NGBRegressor
    from ngboost.distns import Gamma, LogNormal, Normal
    from scipy import stats

    D = {"Normal": Normal, "LogNormal": LogNormal, "Gamma": Gamma}[dist]
    np.random.seed(seed)
    m = NGBRegressor(n_estimators=60 if smoke else 400, Dist=D, verbose=False,
                     learning_rate=0.01, minibatch_frac=1.0, random_state=seed)
    m.fit(X_inner.values, np.asarray(y_inner, float))

    def emit(X) -> Predictive:
        p = m.pred_dist(X.values).params
        if dist == "Normal":
            return NormalPred(np.asarray(p["loc"], float), np.asarray(p["scale"], float))
        if dist == "LogNormal":
            # ngboost's LogNormal exposes (s, scale) in scipy's own parameterisation.
            return ScipyPred(stats.lognorm, {"s": np.maximum(np.asarray(p["s"], float), 1e-6),
                                             "scale": np.maximum(np.asarray(p["scale"], float),
                                                                 1e-6)})
        return ScipyPred(stats.gamma, {"a": np.maximum(np.asarray(p["alpha"], float), 1e-6),
                                       "scale": 1.0 / np.maximum(np.asarray(p["beta"], float),
                                                                 1e-6)})
    return emit


def _lgbm_quantile(X_inner, y_inner, *, seed: int, smoke: bool):
    """A distributional-quantile learner: one LightGBM pinball fit per level in `MH28_LGBM_LEVELS`.

    §0.5's required DIRECT-LEARNED foil — it inherits nothing from the incumbent's μ or σ, so a win
    here would say the shape is learnable from the features rather than repairable as a transform.
    """
    import lightgbm as lgb

    levels = np.array(MH28_LGBM_LEVELS, float)
    models = []
    for t in levels:
        models.append(lgb.LGBMRegressor(
            objective="quantile", alpha=float(t), n_estimators=60 if smoke else 250,
            learning_rate=0.05, num_leaves=15 if smoke else 31, min_child_samples=40,
            verbose=-1, random_state=seed, n_jobs=-1,
        ).fit(X_inner.values, np.asarray(y_inner, float)))

    def emit(X) -> Predictive:
        return QuantilePred(levels, np.column_stack([m.predict(X.values) for m in models]))
    return emit


def _fold(df, tr, ev, cols, tcol, *, seed: int, smoke: bool) -> dict:
    """Fit one fold and return every arm's `Predictive` on the eval rows, plus the diagnostics."""
    from betting_ml.scripts.promotion_gate_eval import _impute

    # LOCK 8b — the honest calibration split, held OUT of every learner fit.
    tr = np.asarray(tr)
    tr = tr[np.argsort(df.loc[tr, "game_date"].to_numpy(), kind="stable")]
    n_cal = max(int(round(CAL_FRACTION * len(tr))), 200)
    inner, cal = tr[:-n_cal], tr[-n_cal:]

    X_inner, X_rest = _impute(df.loc[inner, cols],
                              df.loc[np.concatenate([cal, np.asarray(ev)]), cols])
    X_cal, X_ev = X_rest.iloc[:len(cal)], X_rest.iloc[len(cal):]
    y_inner = df.loc[inner, tcol].to_numpy(float)
    y_cal = df.loc[cal, tcol].to_numpy(float)
    y_ev = df.loc[ev, tcol].to_numpy(float)
    rng = np.random.default_rng(seed)

    normal = _ngboost("Normal", X_inner, y_inner, seed=seed, smoke=smoke)
    inc_cal, inc_ev = normal(X_cal), normal(X_ev)

    # ── the matched pair, from ONE machinery (LOCK 2 / NF-D15 g′) ─────────────────────────────
    p_norm = fit_shape_recal(inc_cal.mu, inc_cal.sigma, y_cal, allow_skew=False)
    p_skew = fit_shape_recal(inc_cal.mu, inc_cal.sigma, y_cal, allow_skew=True)

    lgbm = _lgbm_quantile(X_inner, y_inner, seed=seed, smoke=smoke)
    preds: dict[str, Predictive] = {
        "incumbent": inc_ev,
        "normal_recal": apply_shape_recal(inc_ev.mu, inc_ev.sigma, p_norm),
        "skewnorm_recal": apply_shape_recal(inc_ev.mu, inc_ev.sigma, p_skew),
        "overskew": apply_shape_recal(inc_ev.mu, inc_ev.sigma, p_skew, alpha_scale=OVERSKEW_K),
        "climo": ClimoPred(y_inner, len(y_ev)),
        "ngb_lognormal": _ngboost("LogNormal", X_inner, y_inner, seed=seed, smoke=smoke)(X_ev),
        "ngb_gamma": _ngboost("Gamma", X_inner, y_inner, seed=seed, smoke=smoke)(X_ev),
        "lgbm_quantile": lgbm(X_ev),
    }

    # ── diagnostics — ⛔ NEVER trials (LOCK 2b) ───────────────────────────────────────────────
    # PER-FORM peeking ceilings at MATCHED n: a subsample of the EVAL fold the same size as the
    # calibration split, because "peeking can only help" holds only at equal FAMILY *and* equal
    # RESOLUTION (NF1.7 (b)), and because the forms NEST (NF-D16 g‴).
    n_or = min(len(cal), len(ev))
    sub = rng.choice(len(ev), size=n_or, replace=False)
    p_peek = fit_shape_recal(inc_ev.mu[sub], inc_ev.sigma[sub], y_ev[sub], allow_skew=True)
    preds["oracle_skewnorm"] = apply_shape_recal(inc_ev.mu, inc_ev.sigma, p_peek)
    preds["oracle_lgbm_quantile"] = _lgbm_quantile(
        X_ev.iloc[sub], y_ev[sub], seed=seed, smoke=smoke)(X_ev)
    # `perm_shape` acts ONLY on the per-game-shape arm — for a global-α arm permutation is a
    # mathematical no-op and the anchor is INACTIVE, not passing (LOCK 2b / NF-D20).
    qp = preds[MH28_PERM_ARM]
    preds["perm_shape"] = QuantilePred(qp.levels, qp.q[rng.permutation(len(y_ev))])

    return {
        "y": y_ev, "preds": preds,
        "recal": {"normal": p_norm, "skewnorm": p_skew, "oracle_skewnorm": p_peek},
        "n_inner": int(len(inner)), "n_cal": int(len(cal)), "n_eval": int(len(ev)),
        "n_oracle_fit": int(n_or),
        "eval_year": int(df.loc[ev, "game_year"].astype(int).iloc[0]),
        "cal": {"mu": inc_cal.mu, "sigma": inc_cal.sigma, "y": y_cal},
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE VACUITY FLOOR (LOCK 7)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def score_primaries_only(y, pred: Predictive, rng) -> dict:
    """`pit_mdd` and `p_over_gap` ONLY — no CRPS grid.

    ⚠️ Used by the CONTROLS, which select on the primaries alone. Building the shared 499-level
    quantile grid for every control replicate is what made the sweep intractable (measured: the
    full-scale MDE sweep would have been ~10^10 `ppf` evaluations). This computes exactly what
    `_select_on_primaries` reads and nothing else — it is a COST decision, not a metric decision,
    and the arms are still compared on identical code.
    """
    u = randomized_pit(y, pred, rng)
    m = pred.mean()
    return {"pit_mdd": pit_mdd(u),
            "p_over_gap": float(np.mean(1.0 - pred.cdf(m)) - np.mean(np.asarray(y, float) > m))}


def _select_on_primaries(scores: dict[str, dict]) -> str:
    """Which arm the PRIMARY metrics pick, among the served-evaluable recal family + the nihilist.

    Used ONLY by the controls. Rank by `pit_mdd`, tie-break on `|p_over_gap|` — the same ordering
    the ship rule's clauses 3–4 encode, reduced to a single winner so a control can report one.
    """
    return min(scores, key=lambda a: (scores[a]["pit_mdd"], abs(scores[a]["p_over_gap"])))


def _control_replicate(mu_cal, sigma_cal, mu_ev, sigma_ev, y_train, rng, *,
                       true_alpha: float) -> str:
    """One control replicate: redraw outcomes from a KNOWN truth and re-run the selection.

    `true_alpha = 0` is the NEGATIVE control (the incumbent Normal is TRUE — no skew arm may win);
    `true_alpha > 0` is the POSITIVE control (a known skew must be found AND selected).

    ⚠️ **SCOPE, recorded rather than quietly folded in.** The replicate re-fits the RECALIBRATION
    family and the nihilist, NOT the learned families — refitting NGBoost/LightGBM per replicate is
    ~40× the cost of the whole study. What it therefore tests is exactly the vacuity question that
    can ship: *does the selection metric plus the recalibration machinery INVENT skew on data with
    none?* A control over the learned families would answer a different question and is out of
    scope for this study, which is stated here rather than left to be inferred.
    """
    truth_cal = SkewNormalPred(mu_cal, sigma_cal, true_alpha)
    truth_ev = SkewNormalPred(mu_ev, sigma_ev, true_alpha)
    y_cal = np.round(truth_cal.ppf(rng.uniform(size=len(mu_cal))))
    y_ev = np.round(truth_ev.ppf(rng.uniform(size=len(mu_ev))))

    p_norm = fit_shape_recal(mu_cal, sigma_cal, y_cal, allow_skew=False)
    p_skew = fit_shape_recal(mu_cal, sigma_cal, y_cal, allow_skew=True)
    arms = {
        "incumbent": NormalPred(mu_ev, sigma_ev),
        "normal_recal": apply_shape_recal(mu_ev, sigma_ev, p_norm),
        "skewnorm_recal": apply_shape_recal(mu_ev, sigma_ev, p_skew),
        "overskew": apply_shape_recal(mu_ev, sigma_ev, p_skew, alpha_scale=OVERSKEW_K),
        "climo": ClimoPred(y_train, len(y_ev)),
    }
    return _select_on_primaries({a: score_primaries_only(y_ev, p, rng) for a, p in arms.items()})


def run_controls(per_fold: list[dict], *, seed: int, reps: int, mde_reps: int) -> dict:
    """LOCK 7 — the negative control, the positive control and the MDE curve."""
    rng = np.random.default_rng(seed)
    mu_cal = np.concatenate([f["cal"]["mu"] for f in per_fold])
    sg_cal = np.concatenate([f["cal"]["sigma"] for f in per_fold])
    mu_ev = np.concatenate([f["preds"]["incumbent"].mu for f in per_fold])
    sg_ev = np.concatenate([f["preds"]["incumbent"].sigma for f in per_fold])
    y_train = np.concatenate([f["cal"]["y"] for f in per_fold])

    def sweep(alpha: float, n: int) -> list[str]:
        return [_control_replicate(mu_cal, sg_cal, mu_ev, sg_ev, y_train, rng, true_alpha=alpha)
                for _ in range(n)]

    neg = sweep(0.0, reps)
    clean = sum(1 for w in neg if w in ("incumbent", "normal_recal"))
    pos = sweep(MH28_POS_CONTROL_ALPHA, max(reps // 4, 8))

    mde = {}
    for a in MH28_MDE_ALPHA_GRID:
        wins = sweep(float(a), mde_reps)
        mde[float(a)] = float(np.mean([w == "skewnorm_recal" for w in wins]))
    hit = [a for a, r in sorted(mde.items()) if r >= MH28_TARGET_POWER]
    return {
        "negative_control": {
            "reps": len(neg), "clean_rate": clean / max(len(neg), 1),
            "bar": MH28_NEG_CONTROL_MIN_CLEAN,
            "passed": bool(clean / max(len(neg), 1) >= MH28_NEG_CONTROL_MIN_CLEAN),
            "winners": {w: neg.count(w) for w in sorted(set(neg))},
        },
        "positive_control": {
            "true_alpha": MH28_POS_CONTROL_ALPHA, "reps": len(pos),
            "selected_skew_rate": float(np.mean([w == "skewnorm_recal" for w in pos])),
            "winners": {w: pos.count(w) for w in sorted(set(pos))},
        },
        "mde_curve": mde,
        "mde_alpha_at_80pct_power": (min(hit) if hit else None),
        "n_rows": int(len(mu_ev)),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE SERVED-ROW GATE (LOCK 9)
# ══════════════════════════════════════════════════════════════════════════════════════════════

_SERVED_TABLES = ("daily_model_predictions", "mart_game_results")

#: MH2.6's served population, EXTENDED with the posted totals line so `p_over_gap` can be read at
#: the line the product actually priced — the read MH2.6's §2 flagged as missing and could not close.
_SERVED_SQL = """
WITH served AS (
    SELECT game_pk, game_date::date AS game_date, prediction_type AS tier,
           model_version, totals_model_version,
           pred_total_runs AS mu, pred_total_runs_scale AS sigma,
           total_line_consensus, bovada_line, inserted_at
    FROM daily_model_predictions
    WHERE model_version IN ('v6', 'pre_lineup_v6')
      AND prediction_type IN ('post_lineup', 'morning')
      AND COALESCE(is_backfill, FALSE) = FALSE
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, prediction_type ORDER BY inserted_at DESC) = 1
)
SELECT s.game_pk, s.game_date, s.tier, s.model_version, s.totals_model_version,
       s.mu, s.sigma, s.total_line_consensus, s.bovada_line,
       (r.home_final_score + r.away_final_score)::DOUBLE AS y_total
FROM served s
JOIN mart_game_results r ON r.game_pk = s.game_pk
 AND r.game_type = 'R' AND r.home_final_score IS NOT NULL
ORDER BY s.game_date, s.game_pk, s.tier
"""


def _served_cache_path() -> Path:
    """⭐ **THE CACHE IS KEYED ON A HASH OF THE QUERY TEXT, not on a fixed name.**

    Measured during this harness's build-out: `pull_served` initially reused MH2.6's cache path, so
    it silently returned MH2.6's COLUMN SET — the posted-line columns this study added were simply
    absent, the `p_over_gap`-at-the-line block rendered EMPTY, and nothing errored. That is exactly
    NF-C0e (c): a cache keyed on the query RANGE rather than the query TEXT serves a stale column
    set. A stale cache must be impossible to READ, not merely noisy.
    """
    import hashlib
    h = hashlib.sha256(_SERVED_SQL.encode()).hexdigest()[:12]
    return _SERVED_CACHE.with_name(f"mh2_8_served_{h}.parquet")


def pull_served(cache: Path | None = None) -> pd.DataFrame:
    """MH2.6's served rows + the posted line. Snowflake-free (DuckDB over S3)."""
    cache = _served_cache_path() if cache is None else cache
    if cache is not None and cache.exists():
        return pd.read_parquet(cache)
    import os
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, _SERVED_TABLES)
    df = conn.execute(_SERVED_SQL).fetchdf()
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    return df


def served_gate(recal: dict, *, seed: int, tier: str = "post_lineup",
                served: pd.DataFrame | None = None) -> dict:
    """⭐ MH2.1's rollback rule, as code: a CV win is NECESSARY AND NOT SUFFICIENT.

    Applies the CV-fitted recalibration to the ACTUALLY-SERVED (μ, σ) and re-scores. The
    recalibration used is the LAST CV FOLD's, whose calibration split ends before the 2026 season
    and therefore strictly BEFORE the served era begins — so this is a PROSPECTIVE read, not an
    in-sample one.

    Three arms are reported and their roles differ:
      * `skewnorm_recal` — the validated object; **this is what the gate binds on**.
      * `skew_only`      — a declared robustness read that applies ONLY α, holding the served μ and
                           σ byte-identical. MH2.6 found level and scale are already INSIDE their
                           nulls, so this variant cannot damage what is already right; it isolates
                           whether the SHAPE term alone carries the served improvement.
      * `in_sample_ceiling` — α refitted ON THE SERVED ROWS. ⛔ **A CEILING, NOT A RESULT** — it
                           sees the answer. Reported only to bound what the mechanism could achieve.
    """
    df = pull_served() if served is None else served
    d = df[(df["tier"] == tier)
           & (df["totals_model_version"].fillna("") != "mh2_1")
           & df["y_total"].notna() & df["mu"].notna() & df["sigma"].notna()].copy()
    y = d["y_total"].to_numpy(float)
    mu = d["mu"].to_numpy(float)
    sg = d["sigma"].to_numpy(float)

    inc = NormalPred(mu, sg)
    arms = {
        "incumbent": inc,
        "skewnorm_recal": apply_shape_recal(mu, sg, recal),
        "skew_only": SkewNormalPred(mu, sg, recal["alpha"]),
        "normal_recal": apply_shape_recal(mu, sg, {**recal, "alpha": 0.0}),
        "overskew": apply_shape_recal(mu, sg, recal, alpha_scale=OVERSKEW_K),
    }
    p_in = fit_shape_recal(mu, sg, y, allow_skew=True)
    arms["in_sample_ceiling"] = apply_shape_recal(mu, sg, p_in)

    scored = {a: score_arm(y, p, np.random.default_rng(seed)) for a, p in arms.items()}

    # ⭐ `p_over_gap` AT THE ACTUAL POSTED LINE — the served error, not merely the shape bound.
    line_cols = {"consensus": "total_line_consensus", "bovada": "bovada_line"}
    at_line: dict[str, dict] = {}
    for tag, col in line_cols.items():
        if col not in d.columns:
            continue
        ok = d[col].notna().to_numpy()
        if ok.sum() < 30:                       # too thin to read — say so, never score it healthy
            at_line[tag] = {"n": int(ok.sum()), "evaluable": False}
            continue
        L = d.loc[ok, col].to_numpy(float)
        at_line[tag] = {"evaluable": True, "coverage": float(ok.mean()), **{
            a: p_over_at(y[ok], _subset(p, ok), L) for a, p in arms.items()}}

    null = uniform_mdd_null(len(y), MH28_NULL_REPS, seed)
    return {
        "tier": tier, "n": int(len(y)),
        "era": [str(d["game_date"].min()), str(d["game_date"].max())],
        "recal_applied": recal, "in_sample_ceiling_recal": p_in,
        "arms": scored, "at_posted_line": at_line,
        "pit_construction_floor": null,
        "mh2_6_null_band_pit_mdd": [0.0117, 0.0356],
        "served_evaluable_arms": list(MH28_SERVED_EVALUABLE),
        "rng_note": "every arm is scored on an IDENTICALLY-SEEDED generator, so the randomised-PIT "
                    "draw is COMMON across arms and no arm can win on its own lucky randomisation.",
    }


def _subset(p: Predictive, mask: np.ndarray) -> Predictive:
    """Restrict a predictive to a row mask — needed for the posted-line read, which drops rows."""
    if isinstance(p, NormalPred):
        return NormalPred(p.mu[mask], p.sigma[mask])
    if isinstance(p, SkewNormalPred):
        out = SkewNormalPred(np.zeros(int(mask.sum())), np.ones(int(mask.sum())), 0.0)
        out.xi, out.omega, out.a = p.xi[mask], p.omega[mask], np.asarray(p.a)[mask]
        out.n = int(mask.sum())
        out._grid_cache = None
        return out
    raise TypeError(f"no row-subset defined for {type(p).__name__}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE RUN
# ══════════════════════════════════════════════════════════════════════════════════════════════

def load_matrix(*, min_year: int, smoke: bool) -> pd.DataFrame:
    """The training matrix, Snowflake-free. ⚠️ LOCK 1b — the two E1 de-leak swaps are NOT applied."""
    import os
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    from betting_ml.utils import data_loader as dl
    from betting_ml.utils.training_cache import get_cached_df

    dl.set_s3_mode(True)
    key = f"edge_e1_training_from{int(min_year)}"
    df = get_cached_df(key, lambda: dl.load_features(min_year=int(min_year)),
                       source_label="the S3 lakehouse").reset_index(drop=True)
    if smoke:
        df = df.groupby("game_year", group_keys=False).head(400).reset_index(drop=True)
    return df


def run(*, exclude_seasons: tuple[int, ...] = (), seed: int = SEED, smoke: bool = False) -> dict:
    from betting_ml.scripts.e7_9_train_serve_consistency import (
        build_arm_contracts, contract_coverage_by_season, design_bar, dsr_gate,
    )
    from betting_ml.scripts.mh2_5_sigma_recalibration import (
        _bin_labels, realized_dispersion_table,
    )
    from betting_ml.scripts.model_bakeoff import _TARGETS
    from betting_ml.scripts.promotion_gate_eval import make_gate_splitter
    from betting_ml.utils.cv_power import fold_consistency_clause
    from betting_ml.utils.overfitting import pbo_cscv

    tcol = _TARGETS[TARGET]["col"]
    df = load_matrix(min_year=MH28_MIN_YEAR, smoke=smoke)
    if exclude_seasons:
        keep = ~df["game_year"].astype(int).isin([int(y) for y in exclude_seasons])
        print(f"[{STORY}] LOCK-1 sensitivity: dropping {list(exclude_seasons)} from BOTH train and "
              f"eval — {int((~keep).sum()):,} of {len(df):,} rows")
        df = df.loc[keep].reset_index(drop=True)
    seasons = sorted(int(s) for s in df["game_year"].unique())

    cols = build_arm_contracts(TARGET, TIER, set(df.columns), family="mh2_1")["incumbent"]
    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=EMBARGO_DAYS)
    folds = list(splitter(df))
    n_arms = len(MH28_FIELD)
    print(f"[{STORY}] {TARGET}/{TIER}: {seasons[0]}–{seasons[-1]} ({len(seasons)} seasons) → "
          f"{len(folds)} purged folds · {len(df):,} rows · {len(cols)} contract cols · SNOWFLAKE-FREE")
    print(f"[{STORY}] field ({n_arms} trials): {list(MH28_FIELD)}")
    print(f"[{STORY}] diagnostics (⛔ NOT trials): {list(MH28_DIAGNOSTICS)}")
    bar = design_bar(len(folds), n_arms)
    print(f"[{STORY}] LOCK-8 design bar BEFORE any fit: "
          f"{bar['dsr_required_per_fold_sr_asymptotic_V']} per-fold Sharpe at asymptotic V · "
          f"PBO evaluable={bar['pbo_evaluable']} · DSR ceiling={bar['dsr_ceiling_at_any_effect']}")

    per_fold = []
    for i, (tr, ev) in enumerate(folds, 1):
        f = _fold(df, tr, ev, cols, tcol, seed=seed, smoke=smoke)
        per_fold.append(f)
        print(f"[{STORY}]   fold {i}/{len(folds)} eval={f['eval_year']} "
              f"(inner {f['n_inner']:,} / cal {f['n_cal']:,} / eval {f['n_eval']:,}) "
              f"α̂={f['recal']['skewnorm']['alpha']:.3f} "
              f"(peeking α={f['recal']['oracle_skewnorm']['alpha']:.3f})")

    all_names = list(MH28_FIELD) + list(MH28_DIAGNOSTICS)
    y = np.concatenate([f["y"] for f in per_fold])
    inc_mu = np.concatenate([f["preds"]["incumbent"].mu for f in per_fold])
    inc_sg = np.concatenate([f["preds"]["incumbent"].sigma for f in per_fold])

    # ── STEP 1 (THE METHOD LOCK): VALIDATE EVERY PARTITION BEFORE READING ANY Var(z) ───────────
    resid = y - inc_mu
    strat_values = {"incumbent_sigma": inc_sg, "incumbent_mean": inc_mu}
    stratifiers = {k: realized_dispersion_table(v, resid, k=MH28_N_STRATA)
                   for k, v in strat_values.items()}
    for k, v in stratifiers.items():
        print(f"[{STORY}] stratifier `{k}`: valid={v['valid']} ρ={v.get('spearman_rho'):.3f} "
              f"endpoints {v.get('endpoint_separation_se'):.2f} SE apart")
    primary_ok = bool(stratifiers[MH28_PRIMARY_STRATIFIER]["valid"])
    lab = _bin_labels(strat_values[MH28_PRIMARY_STRATIFIER], k=MH28_N_STRATA) if primary_ok else None

    # ── STEP 2: score every arm, pooled out-of-fold and per fold ───────────────────────────────
    # ⭐ Every arm is scored with an IDENTICALLY-SEEDED generator, so the randomised-PIT draw is
    # COMMON across arms and no arm can win on its own lucky randomisation.
    pooled: dict[str, dict] = {}
    for a in all_names:
        preds = [f["preds"][a] for f in per_fold]
        u = np.concatenate([randomized_pit(f["y"], f["preds"][a], np.random.default_rng(seed + 7))
                            for f in per_fold])
        m = np.concatenate([p.mean() for p in preds])
        s = np.concatenate([p.sd() for p in preds])
        crps = np.concatenate([p.crps(f["y"]) for p, f in zip(preds, per_fold)])
        # `p_over` is read AT EACH ARM'S OWN PREDICTIVE MEAN, so the stated leg must be evaluated
        # per fold through that fold's CDF and only then pooled.
        stated = np.concatenate([1.0 - p.cdf(p.mean()) for p in preds])
        pooled[a] = _pool(y, u, m, s, crps, stated, lab)
    per_fold_scores = {a: [score_arm(f["y"], f["preds"][a], np.random.default_rng(seed + 7))
                           for f in per_fold] for a in all_names}

    # the Normal closed form beside the shared grid estimator — validates the estimator, never a verdict
    inc_pred = [f["preds"]["incumbent"] for f in per_fold]
    crps_closed = float(np.mean(np.concatenate(
        [p.crps_closed_form(f["y"]) for p, f in zip(inc_pred, per_fold)])))

    # ── STEP 3: the CONSTRUCTION FLOOR and the inversion HALT ──────────────────────────────────
    floor = uniform_mdd_null(len(y), MH28_NULL_REPS, seed)
    inverted = [a for a in MH28_FIELD if pooled[a]["pit_mdd"] < floor["p001"]]

    # ── STEP 4: the gates ──────────────────────────────────────────────────────────────────────
    fold_primary = {a: [s["pit_mdd"] for s in per_fold_scores[a]] for a in MH28_FIELD}
    leader = min((a for a in MH28_CANDIDATES), key=lambda a: pooled[a]["pit_mdd"])
    perf = np.column_stack([-np.array(fold_primary[a]) for a in MH28_FIELD])   # higher = better
    try:
        pbo = pbo_cscv(perf, higher_is_better=True, n_splits=min(len(folds) // 1 * 2, 16),
                       seed=seed)
        pbo_val, pbo_note = float(pbo.pbo), None
    except Exception as exc:                                        # pragma: no cover - guard
        pbo_val, pbo_note = float("nan"), f"PBO not evaluable: {exc}"
    dsr = dsr_gate(fold_primary, MH28_INCUMBENT_ARM, leader,
                   n_trials=n_arms, degenerate_arms=MH28_DEGENERATES)
    clause = fold_consistency_clause(len(folds))
    wins = int(sum(1 for a, b in zip(fold_primary[leader], fold_primary[MH28_INCUMBENT_ARM])
                   if a < b))

    controls = run_controls(per_fold, seed=seed,
                            reps=8 if smoke else MH28_NEG_CONTROL_REPS,
                            mde_reps=6 if smoke else MH28_MDE_REPS)

    # ── STEP 5: the SERVED-ROW gate (LOCK 9) ───────────────────────────────────────────────────
    serving_recal = per_fold[-1]["recal"]["skewnorm"]
    try:
        served = served_gate(serving_recal, seed=seed)
    except Exception as exc:                                        # pragma: no cover - guard
        served = {"error": str(exc), "evaluable": False}

    R = {
        "story": STORY, "best_alpha": BEST_ALPHA, "target": TARGET, "tier": TIER,
        "seed": seed, "smoke": smoke,
        "exclude_seasons": [int(s) for s in exclude_seasons],
        "seasons": seasons, "n_rows": int(len(df)), "n_eval_rows": int(len(y)),
        "n_folds": len(folds), "n_arms": n_arms, "contract_cols": cols,
        "deleak_swaps_applied": MH28_APPLY_DELEAK_SWAPS,
        "design_bar": bar,
        "fold_meta": [{k: f[k] for k in ("eval_year", "n_inner", "n_cal", "n_eval",
                                         "n_oracle_fit")} | {
            "alpha_hat": f["recal"]["skewnorm"]["alpha"],
            "a_hat": f["recal"]["skewnorm"]["a"], "b_hat": f["recal"]["skewnorm"]["b"],
            "oracle_alpha": f["recal"]["oracle_skewnorm"]["alpha"]} for f in per_fold],
        "pooled": pooled, "per_fold_scores": per_fold_scores,
        "fold_primary": fold_primary,
        "crps_grid_vs_closed_form": {"grid": pooled["incumbent"]["crps"], "closed": crps_closed,
                                     "abs_diff": abs(pooled["incumbent"]["crps"] - crps_closed)},
        "stratifiers": stratifiers, "primary_stratifier_valid": primary_ok,
        "pit_construction_floor": floor, "inversion_arms": inverted,
        "leader": leader, "pbo": pbo_val, "pbo_note": pbo_note, "dsr": dsr,
        "fold_consistency": {"required": clause.wins_required, "wins": wins,
                             "n_folds": len(folds), "attainable": clause.attainable,
                             "attained_false_fire": clause.attained_false_fire,
                             "legacy_wins_required": clause.legacy_wins_required,
                             "passed": bool(clause.attainable
                                            and wins >= (clause.wins_required or 10**9))},
        "controls": controls, "served": served,
        "min_null_reps_required": min_null_reps(len(MH28_PRIMARIES) + 2),
        "null_reps_used": MH28_NULL_REPS,
        "coverage_by_season": contract_coverage_by_season(df, cols),
        "promotion_landmines": list(MH28_PROMOTION_LANDMINES),
    }
    R["decision"] = _decide(R)
    return R


def _pool(y, u, m, s, crps, stated, lab) -> dict:
    """Pool one arm's out-of-fold scores. Identical code for every arm, by construction."""
    from scipy.stats import kstest, kurtosis, skew

    z = (y - m) / np.maximum(s, 1e-12)
    realized = (y > m).astype(float)
    out = {
        "pit_mdd": pit_mdd(u), "pit_ks": float(kstest(u, "uniform").statistic),
        "crps": float(np.mean(crps)),
        # ⛔ coverage off the RANDOMISED PIT, never off inclusive integer bounds (E2.1-r).
        "cov80": float(np.mean((u >= 0.10) & (u <= 0.90))),
        "cov50": float(np.mean((u >= 0.25) & (u <= 0.75))),
        "mass_below_predictive_median": float(np.mean(u < 0.5)),
        "bias": float(np.mean(y - m)), "var_z_pooled": float(np.var(z, ddof=1)),
        "z_skew": float(skew(z)), "z_excess_kurtosis": float(kurtosis(z)),
        "mean_sigma": float(np.mean(s)),
        "p_over_stated": float(np.mean(stated)),
        "p_over_realized": float(np.mean(realized)),
        "p_over_gap": float(np.mean(stated) - np.mean(realized)),
        "p_over_gap_se": float(np.sqrt(np.var(realized) / max(len(realized), 1))),
        "deciles": [float(x) for x in
                    np.histogram(u, bins=np.linspace(0, 1, 11))[0] / max(len(u), 1)],
    }
    if lab is not None:
        from betting_ml.scripts.mh2_5_sigma_recalibration import rms_var_z
        rms, _b = rms_var_z(z, lab)
        out["rms_var_z"] = float(rms)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 10 — THE SHIP RULE. Default verdict: INCUMBENT_STANDS.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _clauses(arm: str, R: dict) -> dict:
    """The ten pre-registered clauses, evaluated for ONE arm. Each is independently checkable."""
    P, inc = R["pooled"], R["pooled"][MH28_INCUMBENT_ARM]
    a, foil = P[arm], R["pooled"][MH28_MATCHED_FOIL]
    served = R.get("served") or {}
    sv = (served.get("arms") or {}).get(arm)
    band = served.get("mh2_6_null_band_pit_mdd") or [0.0, 1.0]
    line = (served.get("at_posted_line") or {}).get("consensus") or {}
    served_inc = (served.get("arms") or {}).get(MH28_INCUMBENT_ARM) or {}

    served_ok = None
    if arm not in MH28_SERVED_EVALUABLE:
        served_ok = False                       # SERVED_UNVALIDATABLE ⇒ cannot ship (LOCK 9)
    elif sv:
        gap_ok_mean = abs(sv["p_over_gap"]) <= abs(served_inc.get("p_over_gap", 0.0)) - \
            MH28_MEANINGFUL_P_OVER_GAP
        gap_ok_line = None
        if line.get("evaluable") and arm in line and MH28_INCUMBENT_ARM in line:
            gap_ok_line = abs(line[arm]["p_over_gap"]) <= \
                abs(line[MH28_INCUMBENT_ARM]["p_over_gap"]) - MH28_MEANINGFUL_P_OVER_GAP
        served_ok = bool(
            sv["pit_mdd"] <= band[1]
            and gap_ok_mean and (gap_ok_line is not False)
            and sv["crps"] <= served_inc.get("crps", np.inf) + MH28_CRPS_TOLERANCE
            and sv["cov80"] >= MH28_COV80_FLOOR and sv["cov50"] >= MH28_COV50_FLOOR)

    dsr_val = R["dsr"].get("dsr")
    return {
        "1_nihilist_did_not_clear": None,       # filled by `_decide` (it needs every arm's verdict)
        "2_no_inversion": not R["inversion_arms"],
        "3_beats_incumbent_pit_mdd": bool(inc["pit_mdd"] - a["pit_mdd"]
                                          >= MH28_MEANINGFUL_PIT_MDD_GAIN),
        "4_closes_p_over_gap": bool(abs(inc["p_over_gap"]) - abs(a["p_over_gap"])
                                    >= MH28_MEANINGFUL_P_OVER_GAP),
        "5_beats_matched_foil": bool(a["pit_mdd"] < foil["pit_mdd"]
                                     and abs(a["p_over_gap"]) < abs(foil["p_over_gap"])),
        "6_crps_non_inferior": bool(a["crps"] <= inc["crps"] + MH28_CRPS_TOLERANCE),
        "7_coverage_floor": bool(a["cov80"] >= MH28_COV80_FLOOR
                                 and a["cov50"] >= MH28_COV50_FLOOR),
        "8_pbo_dsr": bool(np.isfinite(R["pbo"]) and R["pbo"] < PBO_MAX
                          and dsr_val is not None and dsr_val >= DSR_MIN_CONF),
        "9_fold_consistency": bool(R["fold_consistency"]["passed"]),
        "10_served_gate": served_ok,
    }


def _decide(R: dict) -> dict:
    """⭐ The ship rule, and the two ways it refuses to ship for a reason other than a losing arm.

    * `METRIC_INVERTED` — the NIHILIST cleared the rule. Both primaries are MARGINAL statistics that
      a feature-blind predictive wins by construction (LOCK 4); if the constraints failed to stop it,
      the metric — not the leaderboard — is what this run measured.
    * `HALT_METRIC_INVERSION` — an arm scored BELOW the construction floor, which is impossible for
      a real predictive.
    """
    from betting_ml.utils.cv_power import classify_null

    per_arm = {a: _clauses(a, R) for a in MH28_FIELD}
    # ⭐ The inversion check reads the SELECTION clauses ONLY — see MH28_INVERSION_EXCLUDED_CLAUSES.
    _selection = [k for k in per_arm[MH28_NIHILIST]
                  if k not in MH28_INVERSION_EXCLUDED_CLAUSES]
    nihilist_clears = all(per_arm[MH28_NIHILIST][k] is True for k in _selection)
    for a in per_arm:
        per_arm[a]["1_nihilist_did_not_clear"] = not nihilist_clears

    def ships(a: str) -> bool:
        return all(v is True for v in per_arm[a].values())

    shippable = [a for a in MH28_CANDIDATES if ships(a)]
    leader = R["leader"]
    inc = R["pooled"][MH28_INCUMBENT_ARM]
    lead = R["pooled"][leader]

    if R["inversion_arms"]:
        verdict = "HALT_METRIC_INVERSION"
    elif nihilist_clears:
        verdict = "METRIC_INVERTED"
    elif shippable:
        verdict = "SHIP_CHALLENGER"
    else:
        verdict = "INCUMBENT_STANDS"

    dsr = R["dsr"]
    null = None
    if verdict == "INCUMBENT_STANDS":
        margin_sd = None
        fs = np.array(R["fold_primary"][leader], float) - \
            np.array(R["fold_primary"][MH28_INCUMBENT_ARM], float)
        if fs.size > 1 and np.std(fs, ddof=1) > 0:
            margin_sd = float(-np.mean(fs) / np.std(fs, ddof=1))
        null = classify_null(
            metric="pit_mdd", n_folds=R["n_folds"], n_arms=R["n_arms"],
            beats_foil=bool(lead["pit_mdd"] < R["pooled"][MH28_MATCHED_FOIL]["pit_mdd"]),
            observed_sr=margin_sd, var_trials_sr=dsr.get("var_trials_sr"),
            fold_wins=R["fold_consistency"]["wins"],
            # ⭐ MH2.7: pass the DECLARED field size and read the MACHINE FLAG, never the prose —
            # 8 IS the declared minimum, so "use a smaller field" is an INADMISSIBLE remedy here.
            declared_field_size=R["n_arms"],
            degenerates_excluded_from_v=True,
            mde_sd_units=None, meaningful_sd_units=None)
        null = {k: getattr(null, k) for k in dir(null)
                if not k.startswith("_") and not callable(getattr(null, k))}

    return {
        "verdict": verdict,
        "leader": leader,
        "shippable_arms": shippable,
        "clauses": per_arm,
        "nihilist_cleared_the_rule": bool(nihilist_clears),
        "margins_vs_incumbent": {
            a: {"pit_mdd_gain": float(inc["pit_mdd"] - R["pooled"][a]["pit_mdd"]),
                "p_over_gap_closed": float(abs(inc["p_over_gap"])
                                           - abs(R["pooled"][a]["p_over_gap"])),
                "crps_delta": float(R["pooled"][a]["crps"] - inc["crps"])}
            for a in MH28_FIELD},
        "null_classification": null,
        "deploy_held": True,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE REPORT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _f(x, d=4):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "✅" if x else "⛔"
    try:
        return f"{float(x):.{d}f}"
    except (TypeError, ValueError):
        return str(x)


def _stem(r: dict) -> str:
    s = "mh2_8_skew_predictive"
    if r.get("exclude_seasons"):
        s += "_no" + "".join(str(x) for x in r["exclude_seasons"])
    return s + ("_smoke" if r.get("smoke") else "")


def write_report(r: dict) -> Path:
    d = r["decision"]
    P = r["pooled"]
    inc = P[MH28_INCUMBENT_ARM]
    L: list[str] = []
    w = L.append

    w(f"# MH2.8 — a SKEW-CAPABLE `total_runs` predictive vs the served symmetric Normal\n")
    if r.get("smoke"):
        # ⚠️ A smoke report is a CODE-PATH proof, not a result. Without a banner in the file itself
        # a stray copy reads exactly like the study — the repo's recurring "a number quoted from the
        # wrong artifact" hazard, and the cheapest possible guard against it.
        w("> # ⛔⛔ SMOKE RUN — **NOT A RESULT. DO NOT QUOTE ANY NUMBER BELOW.**\n"
          "> Fits are tiny (60 NGBoost estimators on 400 rows/season) and the control replicate\n"
          "> counts are a fraction of the pre-registered ones. This file exists to prove the code\n"
          "> path executes. The study is the run WITHOUT `--smoke`.\n")
    w(f"**Verdict: `{d['verdict']}`** · `best_alpha = 0` · **deploy-held**\n")
    w("> **What this study is.** A distributional-SHAPE bake-off against the defect MH2.6 measured "
      "on the SERVED rows. It says nothing about win rate, edge or ROI — at `best_alpha = 0` no bet "
      "rides on this model. Pre-registration: [`mh2_8_preregistration.md`](mh2_8_preregistration.md), "
      "committed BEFORE this harness computed anything.\n")

    w("## Population\n")
    w("| | |")
    w("|---|---|")
    w(f"| window | {r['seasons'][0]}–{r['seasons'][-1]} ({len(r['seasons'])} seasons) |")
    w(f"| folds | {r['n_folds']} purged + embargoed ({EMBARGO_DAYS}d) |")
    w(f"| rows | {r['n_rows']:,} ({r['n_eval_rows']:,} out-of-fold eval rows) |")
    w(f"| contract | {len(r['contract_cols'])}-column served contract |")
    w(f"| field | {r['n_arms']} declared trials + {len(MH28_DIAGNOSTICS)} diagnostics (⛔ not trials) |")
    if r.get("exclude_seasons"):
        w(f"| ⚠️ sensitivity | seasons {r['exclude_seasons']} dropped from BOTH train and eval |")
    w("")
    w("⚠️ **LOCK 1b — declared deviation, stated before any arm was scored.** The two E1 de-leak "
      "swaps are NOT applied: `_swap_stuff_plus_deleaked` needs Snowflake (forbidden here) and "
      "touches **no contract column** — a provable no-op, pinned by a guard test — while "
      "`_swap_bullpen_v3` touches 2 of the 13 and needs gitignored per-reliever caches absent from "
      "this worktree. ⇒ absolute LEVELS are **not** comparable to MH2.5's; the arm-to-arm "
      "comparison is unaffected because every arm reads the identical matrix.\n")

    w("## 1. ⭐ The design bar, stated BEFORE any fit\n")
    b = r["design_bar"]
    w(f"- required per-fold Sharpe at asymptotic `V`: **{b['dsr_required_per_fold_sr_asymptotic_V']}**")
    w(f"- PBO evaluable at {r['n_folds']} folds × {r['n_arms']} arms: **{b['pbo_evaluable']}**")
    w(f"- DSR ceiling at ANY effect size: **{b['dsr_ceiling_at_any_effect']}**")
    w(f"- fold-consistency clause: **{r['fold_consistency']['required']} of "
      f"{r['n_folds']} wins** required (calibrated, not a bare 60% — MH2 H8)\n")
    w("This is a statement about the DESIGN that no result can contaminate.\n")

    w("## 2. ⭐ The construction floor — the only thing nothing may beat\n")
    fl = r["pit_construction_floor"]
    w(f"Under a correctly specified predictive the randomised PIT is EXACTLY uniform, so the "
      f"attainable `pit_mdd` at n = {fl['n']:,} is the MDD of that many iid uniforms: median "
      f"**{_f(fl['median'])}**, 95% band [{_f(fl['p025'])}, {_f(fl['p975'])}], 0.1st percentile "
      f"**{_f(fl['p001'])}**. It is a CONSTRUCTION, not a fit, so an arm below its extreme lower "
      f"tail is mathematically impossible.\n")
    w(f"- arms below the floor: **{r['inversion_arms'] or 'none'}** "
      f"{'⛔ HALT' if r['inversion_arms'] else '✅'}\n")

    w("## 3. The leaderboard (pooled out of fold)\n")
    w("`pit_mdd` and `p_over_gap` are the PRIMARIES; CRPS is a **constraint**, never a criterion; "
      "coverage is a **FLOOR**, never a target.\n")
    w("| arm | role | `pit_mdd` | `p_over_gap` | stated / realized | CRPS | cov80 | cov50 | z skew |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    roles = {"incumbent": "**THE BAR**", "normal_recal": "⭐ matched foil",
             "climo": "⚠️ nihilist", "overskew": "degenerate"}
    for a in list(MH28_FIELD) + list(MH28_DIAGNOSTICS):
        s = P[a]
        role = roles.get(a, "candidate" if a in MH28_CANDIDATES else "⛔ diagnostic")
        w(f"| `{a}` | {role} | {_f(s['pit_mdd'])} | {_f(s['p_over_gap'], 4)} | "
          f"{_f(s['p_over_stated'], 3)} / {_f(s['p_over_realized'], 3)} | {_f(s['crps'])} | "
          f"{_f(s['cov80'], 3)} | {_f(s['cov50'], 3)} | {_f(s['z_skew'], 3)} |")
    w("")
    cf = r["crps_grid_vs_closed_form"]
    w(f"CRPS is computed IDENTICALLY for every arm on the shared {MH28_CRPS_LEVELS}-level quantile "
      f"grid (`CRPS = 2∫pinball`). Validation against the Normal closed form on the incumbent: grid "
      f"{_f(cf['grid'])} vs closed {_f(cf['closed'])} (|Δ| {_f(cf['abs_diff'], 5)}).\n")

    w("### ⭐ Did the nihilist do what it was registered to do?\n")
    cl = P[MH28_NIHILIST]
    w(f"`climo` ignores every feature. Registered IN ADVANCE to WIN both primaries and LOSE CRPS — "
      f"measured: `pit_mdd` {_f(cl['pit_mdd'])} vs the incumbent's {_f(inc['pit_mdd'])}, "
      f"`p_over_gap` {_f(cl['p_over_gap'])} vs {_f(inc['p_over_gap'])}, CRPS {_f(cl['crps'])} vs "
      f"{_f(inc['crps'])}.\n")
    w(f"- nihilist cleared the full ship rule: **{_f(d['nihilist_cleared_the_rule'])}** "
      f"{'⛔ the metric is INVERTED and nothing ships' if d['nihilist_cleared_the_rule'] else '✅ the sharpness constraint held'}\n")

    w("## 4. The fitted skew, per fold\n")
    w("| fold | eval | inner | cal | eval n | α̂ | a | b | peeking α |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for i, f in enumerate(r["fold_meta"], 1):
        w(f"| {i} | {f['eval_year']} | {f['n_inner']:,} | {f['n_cal']:,} | {f['n_eval']:,} | "
          f"{_f(f['alpha_hat'], 3)} | {_f(f['a_hat'], 3)} | {_f(f['b_hat'], 3)} | "
          f"{_f(f['oracle_alpha'], 3)} |")
    w("")

    w("## 5. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read\n")
    w("The exact step whose absence caused the MH2.1 rollback. Bars imported from MH2.5 verbatim.\n")
    for k, v in r["stratifiers"].items():
        tag = "PRIMARY" if k == MH28_PRIMARY_STRATIFIER else "SECONDARY"
        ok = "✅ VALIDATED" if v.get("valid") else "⛔ **DISQUALIFIED**"
        w(f"- `{k}` ({tag}): ρ = {_f(v.get('spearman_rho'), 3)} (bar {STRAT_RHO_BAR}) · endpoints "
          f"{_f(v.get('endpoint_separation_se'), 2)} SE apart (bar {STRAT_SE_BAR}) → {ok}")
    w("")
    if not r["primary_stratifier_valid"]:
        w("> ⛔ No `Var(z)` is read off the primary partition. **This was pre-registered as the "
          "EXPECTED outcome** (MH2.5 found it fails when pooled across eras; MH2.6 found it fails "
          "on the served window) and it carries **no information about the skew hypothesis** — "
          "`Var(z)` is a SCALE instrument and this study is about SHAPE.\n")

    w("## 6. ⭐ The vacuity floor — the instrument is proven able to produce the OTHER answer\n")
    c = r["controls"]
    n = c["negative_control"]
    w(f"### Negative control — clean data must NOT flag\n")
    w(f"Outcomes redrawn from the incumbent's OWN per-fold predictive ({n['reps']} replicates), "
      f"the selection re-run each time. A harness that picks a skew arm on Normal data has not "
      f"found skew in the real data — it has found its own preference.\n")
    w(f"- winner distribution: `{n['winners']}`")
    w(f"- clean rate (`incumbent` or `normal_recal` selected): **{_f(n['clean_rate'], 3)}** "
      f"against a pre-stated bar of {n['bar']} → {_f(n['passed'])}\n")
    p = c["positive_control"]
    w(f"### Positive control — a KNOWN skew must be found AND selected\n")
    w(f"- true α = {p['true_alpha']}, {p['reps']} replicates → `skewnorm_recal` selected "
      f"**{_f(p['selected_skew_rate'], 3)}** of the time; winners `{p['winners']}`\n")
    w(f"### MDE — what this design could and could not have detected\n")
    w("A null verdict means *\"no shape defect larger than the MDE\"*. Stating it is the difference "
      "between a measured null and a shrug (NF1.8).\n")
    w("| true α | detection rate |")
    w("|---:|---:|")
    for a_, rate in sorted(c["mde_curve"].items()):
        w(f"| {a_} | {_f(rate, 2)} |")
    w("")
    mde = c["mde_alpha_at_80pct_power"]
    w(f"**MDE at {int(MH28_TARGET_POWER*100)}% power: α = "
      f"{mde if mde is not None else '**NOT REACHED on the grid**'}**, at n = {c['n_rows']:,} "
      f"out-of-fold games.\n")
    w(f"### Multiplicity and the MC-p floor\n")
    w(f"- BH at q = {BH_Q} across the declared verdict family (MH2.6 measured that omitting this "
      f"drove the family-wise error to ≈50% and produced two wrong verdicts on CLEAN frames).")
    w(f"- MC null reps used **{r['null_reps_used']:,}** against a required minimum of "
      f"**{r['min_null_reps_required']}** — so the smallest attainable p clears its own BH cutoff "
      f"and no test is vacuous.\n")

    w("## 7. The deflation gates\n")
    dsr = r["dsr"]
    w(f"- leader among the candidates: **`{r['leader']}`**")
    w(f"- **PBO** {_f(r['pbo'], 3)} (bar < {PBO_MAX}){' — ' + r['pbo_note'] if r.get('pbo_note') else ''}")
    w(f"- **DSR** {_f(dsr.get('dsr'), 4)} (bar ≥ {DSR_MIN_CONF}) · binds: `{dsr.get('binds')}` · "
      f"whole-field figure {_f(dsr.get('dsr_with_degenerates_in_V'), 4)}")
    w(f"- DSR-CONV: degenerates `{list(MH28_DEGENERATES)}` are in `n_trials` (we DID try them) and "
      f"OUT of `V` — **declared before the run**, because the exclusion is non-monotone and an arm "
      f"qualifies BY DESIGN, never by declaration (MH2.5 / DSR-CONV).")
    w(f"- fold consistency: {r['fold_consistency']['wins']} wins of {r['n_folds']} against a "
      f"required {r['fold_consistency']['required']} → {_f(r['fold_consistency']['passed'])}\n")

    w("## 8. ⭐ The SERVED-ROW gate — MH2.1's rollback rule, as code\n")
    sv = r.get("served") or {}
    if not sv.get("arms"):
        w(f"⛔ **NOT EVALUATED** — {sv.get('error', 'unavailable')}. A missing served read is "
          f"UNVERIFIED, never healthy (NF1.7 (a)): with it absent, nothing may ship.\n")
    else:
        w(f"Served population: **{sv['n']} rows**, {sv['era'][0]} → {sv['era'][1]}, tier "
          f"`{sv['tier']}`. Every row post-dates the champion's fit, so the whole window is out of "
          f"sample — MH2.1's \"split at the incumbent's fit date\" rule holds by construction.\n")
        w(f"The recalibration applied is the **last CV fold's** (`α = "
          f"{_f(sv['recal_applied']['alpha'], 3)}`, `a = {_f(sv['recal_applied']['a'], 3)}`, "
          f"`b = {_f(sv['recal_applied']['b'], 3)}`), whose calibration split ends before the 2026 "
          f"season — i.e. strictly BEFORE the served era. This is a PROSPECTIVE read.\n")
        w("| arm | `pit_mdd` | `p_over_gap` @ own mean | stated / realized | CRPS | cov80 | cov50 |")
        w("|---|---:|---:|---:|---:|---:|---:|")
        for a, s in sv["arms"].items():
            w(f"| `{a}` | {_f(s['pit_mdd'])} | {_f(s['p_over_gap'])} | "
              f"{_f(s['p_over_stated'], 3)} / {_f(s['p_over_realized'], 3)} | {_f(s['crps'])} | "
              f"{_f(s['cov80'], 3)} | {_f(s['cov50'], 3)} |")
        w("")
        w(f"MH2.6's calibrated-null band for `pit_mdd` was {sv['mh2_6_null_band_pit_mdd']}; the "
          f"construction floor at this n is median {_f(sv['pit_construction_floor']['median'])}, "
          f"95% band [{_f(sv['pit_construction_floor']['p025'])}, "
          f"{_f(sv['pit_construction_floor']['p975'])}].\n")
        w("### ⭐ `P(over)` AT THE ACTUAL POSTED LINE — the served error, not the shape bound\n")
        w("MH2.6 could only measure this at the model's own mean and flagged the gap in its own §2. "
          "It is pre-registered here, so it is a planned read and not a post-hoc addition.\n")
        for tag, blk in (sv.get("at_posted_line") or {}).items():
            if not blk.get("evaluable"):
                w(f"- `{tag}`: ⛔ not evaluable — only {blk.get('n', 0)} rows carry a line "
                  f"(reported as UNVERIFIED, never scored healthy).")
                continue
            w(f"\n**`{tag}` line** (line present on {_f(blk['coverage'], 3)} of served rows)\n")
            w("| arm | stated `P(over)` | realized | gap |")
            w("|---|---:|---:|---:|")
            for a in sv["arms"]:
                if a in blk:
                    w(f"| `{a}` | {_f(blk[a]['p_over_stated'], 4)} | "
                      f"{_f(blk[a]['p_over_realized'], 4)} | {_f(blk[a]['p_over_gap'], 4)} |")
        w("")
        w(f"⛔ **`in_sample_ceiling` is a CEILING, not a result** — its α "
          f"({_f(sv['in_sample_ceiling_recal']['alpha'], 3)}) was fitted ON the served rows and "
          f"therefore sees the answer. It bounds what the mechanism could achieve; it may not be "
          f"cited as evidence of what it WILL achieve.\n")
        w(f"⚠️ **PRE-REGISTERED ASYMMETRY.** Only arms that are a function of the served (μ, σ) can "
          f"be read here: `{list(MH28_SERVED_EVALUABLE)}`. The learned families "
          f"(`ngb_lognormal`, `ngb_gamma`, `lgbm_quantile`) would need a re-score from features, "
          f"and the offline matrix is NOT point-in-time (MH2.5 Lock 9) — a re-score would be a "
          f"CEILING, not the served number, which is the exact substitution MH2.1's rollback "
          f"punished. ⇒ they are **`SERVED_UNVALIDATABLE` and cannot ship.**\n")

    w("## 9. The ship rule, clause by clause\n")
    keys = list(next(iter(d["clauses"].values())).keys())
    w("| arm | " + " | ".join(f"`{k.split('_', 1)[0]}`" for k in keys) + " | ships |")
    w("|---" * (len(keys) + 2) + "|")
    for a in MH28_FIELD:
        row = d["clauses"][a]
        w(f"| `{a}` | " + " | ".join(_f(row[k]) for k in keys) + " | "
          + _f(a in d["shippable_arms"]) + " |")
    w("")
    w("Legend — 1 nihilist did not clear · 2 no inversion · 3 beats incumbent on `pit_mdd` by ≥ "
      f"{MH28_MEANINGFUL_PIT_MDD_GAIN} · 4 closes `|p_over_gap|` by ≥ {MH28_MEANINGFUL_P_OVER_GAP} · "
      f"5 beats the MATCHED FOIL on both primaries · 6 CRPS non-inferior within "
      f"{MH28_CRPS_TOLERANCE} · 7 coverage floors ({MH28_COV80_FLOOR}/{MH28_COV50_FLOOR}) · "
      "8 PBO+DSR · 9 fold consistency · 10 the SERVED-ROW gate.\n")
    w("### Margins vs the incumbent\n")
    w("| arm | `pit_mdd` gain | `|p_over_gap|` closed | CRPS Δ (− is better) |")
    w("|---|---:|---:|---:|")
    for a, m in d["margins_vs_incumbent"].items():
        w(f"| `{a}` | {_f(m['pit_mdd_gain'])} | {_f(m['p_over_gap_closed'])} | "
          f"{_f(m['crps_delta'])} |")
    w("")

    w("## 10. Verdict\n")
    w(f"**`{d['verdict']}`**\n")
    if d["null_classification"]:
        nc = d["null_classification"]
        w(f"- null state: **`{nc.get('state')}`**")
        for k in ("reason", "trigger", "detail", "field_remedy_admissible"):
            if nc.get(k) is not None:
                w(f"- {k}: {nc[k]}")
        w("")
        adm = nc.get("field_remedy_admissible")
        w("⭐ **`field_remedy_admissible` is the MACHINE FLAG and it is what is read here, never "
          "the prose** (MH2.7). Its three states are distinct and only one of them is a lever:\n")
        w({
            None: "- **`None` — FIELD SIZE IS NO LEVER AT ALL.** Not even a 2-arm field clears at "
                  "this evidence, so there is nothing for a smaller field to be admissible ABOUT. "
                  "⛔ Do NOT read this as \"re-run with fewer arms\".",
            False: "- **`False` — the arithmetic sits BELOW the declared family.** The ≤N figure "
                   "survives as arithmetic and the IMPERATIVE is REFUSED: this field's "
                   f"{r['n_arms']} arms ARE the declared minimum, and re-cutting a field you have "
                   "already scored is the selection bias DSR exists to deflate (MH2.2).",
            True: "- **`True` — a pre-registered family at least this small exists**, so the "
                  "prescription can be acted on without re-cutting a scored field.",
        }[adm])
        w(f"\n`declared_field_size_source` = `{nc.get('detail', {}).get('declared_field_size_source')}` "
          "— a claim about a DOCUMENT, not about the data. The document is "
          "`mh2_8_preregistration.md` §2, committed before this harness computed anything.\n")

    w("## 11. ⛔ Promotion is DEPLOY-HELD — the MH2.1 landmines, restated\n")
    for ln in r["promotion_landmines"]:
        w(f"- {ln}")
    w("")
    w("This harness never writes a registry entry, a pickle or a serving artifact. If an arm clears "
      "every clause the record hands the operator a DECISION, not a fait accompli.\n")

    w("## Reproduce\n")
    w("```bash")
    w("# LAPTOP. Snowflake-free (DuckDB over S3); requires AWS creds + the .env in this worktree.")
    cmd = "uv run python betting_ml/scripts/mh2_8_skew_predictive.py"
    if r.get("exclude_seasons"):
        cmd += " --exclude-seasons " + " ".join(str(s) for s in r["exclude_seasons"])
    w(cmd)
    w("```")

    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    md = _ABL / f"{_stem(r)}.md"
    md.write_text("\n".join(L) + "\n")
    (_JSON_DIR / f"{_stem(r)}.json").write_text(json.dumps(_jsonable(r), indent=2))
    return md


STRAT_RHO_BAR = 0.30
STRAT_SE_BAR = 2.0


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_jsonable(v) for v in o.tolist()]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny fits on 400 rows/season — proves the code path, NOT a result")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--exclude-seasons", type=int, nargs="*", default=[],
                    help="the declared LOCK-1 sensitivity (use 2020)")
    a = ap.parse_args()
    r = run(exclude_seasons=tuple(a.exclude_seasons), seed=a.seed, smoke=a.smoke)
    path = write_report(r)
    d = r["decision"]
    print(f"\n[{STORY}] VERDICT: {d['verdict']} · leader `{d['leader']}` · "
          f"shippable {d['shippable_arms'] or 'none'} · deploy-held")
    print(f"[{STORY}] report → {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

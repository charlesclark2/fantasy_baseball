"""e7_9_train_serve_consistency.py — MLB Edge-E7.9: close the E7.5 / E7.5p train-serve gap and
decide whether the MiLB-MLE-corrected feature block (+ the newly-joined `eb_gb_pct`) earns a
retrained champion.

WHY THIS EXISTS
---------------
E7.5 wired the BATTER MiLB→MLB MLE into `eb_batter_posteriors_raw` and E7.5p wired the PITCHER MLE
into `eb_starter_posteriors`. Both changed the SERVED feature distribution while the served
champions were still fitted on the OLD generic-prior values — a train/serve mismatch. E7.5p also
landed `eb_gb_pct` (E7.3p's strongest translation, −23% cold-start MAE) as a served column with NO
consumer; E7.9's dbt change joins it through `feature_pregame_starter_features` →
`home_/away_starter_eb_gb_pct`, and THIS script is what decides whether a model should use it.

TWO MODES
---------
`--audit` (fast, S3-native, no fitting)
    Answers "how big is the skew, and which SERVED contracts does it actually touch?" BEFORE
    spending a retrain on it. Reads the served v6 sidecars and intersects them with the columns
    E7.5 / E7.5p can move. ⚠️ Run this FIRST: the answer re-scopes the bake-off.

`--bakeoff --target ... --tier ...` (the §0.5 retrain, minutes → OPERATOR)
    A pre-registered arm grid of CONTRACT VARIANT × LEARNER CLASS under E1.1 purged/embargoed CV,
    scored on the target's honest distributional metric (CRPS), with ONE shared PBO surface over
    the whole grid and a DSR deflated by the grid size.

      contract variants
        incumbent   — the served v6 contract, verbatim. The bar.
        plus_gb     — incumbent + home_/away_starter_eb_gb_pct (the E7.9 join; the question the
                      story exists to answer).
        plus_eb     — incumbent + the E7.5/E7.5p-corrected EB columns the contract does NOT already
                      carry. Pre-registered so "the corrected block does not help" is a MEASURED
                      null rather than an assumption.
        plus_both   — plus_gb ∪ plus_eb.
      learner classes: the model_bakeoff slate (ngboost_normal = the incumbent class, xgboost,
      lightgbm, catboost, glm_elasticnet) — ≥3 classes with a direct-learned foil, per §0.5.

DECISION RULE (pre-registered; the default is INCUMBENT_STANDS)
--------------------------------------------------------------
SHIP a challenger only if ALL hold:
  1. it beats the INCUMBENT arm (incumbent contract × incumbent class) on CRPS by MORE than the
     NOISE_FLOOR for the metric — a within-floor win is a tie, and a tie ships nothing;
  2. PBO < 0.2 over the whole arm grid;
  3. DSR > 0 at 95% on the per-bucket improvement series, deflated by n_arms;
  4. calibration (PIT-KS) does not degrade vs the incumbent arm.
Otherwise: INCUMBENT_STANDS, and the null IS the deliverable.
⚠️ E2.1-r SELECTION-METRIC HYGIENE: an ORACLE arm (sees the realized target) is scored alongside
the candidates and MUST come first. A candidate beating the oracle is mathematically impossible and
means the metric is inverted — the run HALTs rather than reporting a winner.
⚠️ `best_alpha = 0`. This is a calibration / train-serve-consistency exercise, not an edge claim.
Nothing here licenses a win-rate or ROI statement.

LEAKAGE POSTURE (audited, not assumed)
--------------------------------------
The MLE prior itself is leakage-safe by CONSTRUCTION: `milb_mle.emit_projections` refits the
translation map per MLB debut cohort on STRICTLY-PRIOR cohorts, and the minor-league line entering
it is strictly pre-debut (`build_graduated_pairs`). So a 2023 game reads a prior fit on ≤2022
graduates — no as-of rebuild is required for the historical backfill. The one residual full-sample
quantity is the recalibrated κ (ONE scalar per metric, from `mle_prior.recalibrate`); it carries no
player-specific information and is reported in the audit rather than silently ignored.

RUNTIME: the bake-off retrains (arms × folds) — NGBoost/CatBoost dominate. Minutes → HAND TO THE
OPERATOR (>2-min rule). `--smoke` caps rows/estimators/arms for a fast end-to-end harness check.

STORY MH2.1 — THE WIDE-WINDOW RE-RUN (2026-08-02)
-------------------------------------------------
MH2 measured that E7.9's binding caveat ("3 purged folds — can rule out a LARGE effect, not a small
one") is a **WINDOW CHOICE, not a data limit**: the served store holds 2016–2026 at ≥0.827 contract
coverage, i.e. **8 folds available TODAY** against the 3 E7.9 ran. `--mh2-1` re-runs the bake-off on
that window with a PRE-REGISTERED 4-arm family and the FIXED DSR convention. See the `MH21_*` block
below for the locks — all four registered in source BEFORE any arm was scored.

⚠️ The DSR convention fix is NOT optional and is NOT scoped to MH2.1: E7.9's `n_obs` was ~19
year-MONTH buckets (not independent draws) with no `trial_sharpes`, and **both biases inflate DSR**,
so its recorded 0.842 is an OVERSTATEMENT. Every run now scores the FIXED convention and reports the
legacy one beside it. Recorded E7.9 verdicts are untouched — they live in stored JSON and
`--rewrite-reports` recomputes nothing.

Usage:
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py --audit
    # MH2.1 PRIMARY (2020 kept ⇒ 8 folds) and the declared SENSITIVITY (2020 dropped ⇒ 7 folds):
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
        --bakeoff --mh2-1 --target total_runs --tier post_lineup --s3 --refresh-cache
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
        --bakeoff --mh2-1 --exclude-seasons 2020 --target total_runs --tier post_lineup --s3
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py \
        --bakeoff --target run_diff --tier pre_lineup --s3 --refresh-cache
    uv run python betting_ml/scripts/e7_9_train_serve_consistency.py --bakeoff --target total_runs --smoke

⚠️ `--s3 --refresh-cache` is the real-run combination. Without `--refresh-cache` the harness reads a
stale cached matrix; without `--s3` it reads Snowflake, which does not carry `eb_gb_pct` until the
operator recreates the external table — so the `plus_gb` arm would be silently DROPPED and the
story's headline question would go unanswered. The harness reports every dropped variant for
exactly this reason: read that line before trusting a verdict.
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

STORY = "E7.9"
BEST_ALPHA = 0

# ── the columns E7.5 / E7.5p can move, at the GAME grain ──────────────────────────────────────
# E7.5  (batter MLE → eb_batter_posteriors_raw): K% / BB% / ISO, aggregated to avg_eb_* per side.
# E7.5p (pitcher MLE → eb_starter_posteriors):   K% / BB% for a COLD-START starter, plus the NEW
#        eb_gb_pct column. eb_xwoba_against (+ _sequential, _uncertainty) is NOT wired to the MLE —
#        it keeps its experience-band prior verbatim — so it is deliberately absent here.
E75_BATTER_COLS = tuple(
    f"{side}_avg_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct", "iso")
)
E75P_STARTER_COLS = tuple(
    f"{side}_starter_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct")
)
# The E7.9 join itself — a NEW column, in no incumbent contract by construction.
E79_GB_COLS = ("home_starter_eb_gb_pct", "away_starter_eb_gb_pct")

MLE_AFFECTED_COLS = E75_BATTER_COLS + E75P_STARTER_COLS

# served v6 sidecars (registry `feature_columns_path` / `pre_lineup_feature_columns_path`)
SERVED_CONTRACTS = {
    ("total_runs", "post_lineup"): "betting_ml/models/total_runs/feature_columns_v6_total_runs_post_lineup_served.json",
    ("total_runs", "pre_lineup"):  "betting_ml/models/total_runs/feature_columns_v6_total_runs_pre_lineup_served.json",
    ("run_diff", "post_lineup"):   "betting_ml/models/run_differential/feature_columns_v6_run_diff_post_lineup_served.json",
    ("run_diff", "pre_lineup"):    "betting_ml/models/run_differential/feature_columns_v6_run_diff_pre_lineup_served.json",
    ("home_win", "post_lineup"):   "betting_ml/models/home_win/feature_columns_v6_home_win_post_lineup_served.json",
    ("home_win", "pre_lineup"):    "betting_ml/models/home_win/feature_columns_v6_home_win_pre_lineup_served.json",
}

# build_imputation_pipeline() ALWAYS appends these; they are in the served sidecar but are not
# real contract features, so they must be stripped before a contract is re-derived.
IMPUTER_ADDED = ("has_starter_platoon_data", "is_new_venue")

# The incumbent learner class per regression target (E1.9 v6 → E13.11 deploy).
INCUMBENT_CLASS = {"total_runs": "ngboost_normal", "run_diff": "ngboost_normal"}

PBO_MAX = 0.2
DSR_MIN_CONF = 0.95

# ── PRE-REGISTRATION AMENDMENT #1 — calibration tolerance (dated 2026-07-29, PM-adjudicated) ──────
# EFFECTIVE FOR RUNS ON OR AFTER 2026-07-29. It does NOT alter any recorded E7.9 verdict; the three
# 2026-07-28 runs stand exactly as scored under the original 1e-9 tolerance.
#
# WHY: the original `calibration_not_degraded` gate required best.pit_ks <= inc.pit_ks + 1e-9. On
# run_diff/pre_lineup it FIRED at PIT-KS 0.0294 vs 0.0293 — a 1e-4 difference, i.e. it tripped on
# ROUNDING, not on real degradation. A 1e-9 tolerance on a statistic whose own sampling noise is
# orders of magnitude larger is a MISSPECIFIED gate: it is nearly guaranteed to fail whenever the
# leader is not literally the incumbent, which makes it uninformative rather than protective.
#
# WHY THIS IS LEGITIMATE AND NOT PRE-REGISTRATION LAUNDERING: the amendment is written BEFORE the
# next run and cannot change the result that exposed the defect (that verdict was INCUMBENT_STANDS
# on the MARGIN gate, which failed decisively and independently). Loosening a gate to rescue a
# result you have already seen is laundering; fixing a demonstrably misspecified gate forward, on
# the record, with a date, is calibration. If a future run passes ONLY because of this amendment,
# that fact must be stated explicitly in its report.
#
# THE RULE: degradation is material only if it exceeds BOTH an absolute floor and a relative floor —
# whichever is larger — so the gate scales sensibly across targets with very different PIT-KS levels
# (run_diff/post sits near 0.025, total_runs/post near 0.060).
CALIBRATION_TOLERANCE_ABS = 1e-3      # absolute floor
CALIBRATION_TOLERANCE_REL = 0.10      # or 10% of the incumbent's PIT-KS, whichever is larger
CALIBRATION_AMENDMENT_DATE = "2026-07-29"
CALIBRATION_AMENDMENT_LEGACY_TOL = 1e-9   # what the 2026-07-28 E7.9 runs were scored under


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STORY MH2.1 — the WIDE-WINDOW re-run, PRE-REGISTERED (2026-08-02, BEFORE any arm was scored)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# MH2 measured that E7.9's binding caveat — "3 purged folds; this can rule out a LARGE effect, not
# a small one" — is a WINDOW CHOICE and not a data limit. `feature_pregame_game_features` holds
# 2015–2026 / 26,883 rows, and the served 13-column `total_runs/post_lineup` contract is ≥0.827
# non-null from 2016 (0.449 in 2015). So the re-test is available TODAY, with no calendar wait.
#
# Everything below is registered BEFORE the run. A choice made after seeing a score is
# window-shopping, which is precisely the defect MH2 exists to stop.
#
# LOCK 1 — THE WINDOW AND THE 2020 DECISION.
#   PRIMARY:     min_year = 2016, 2020 KEPT (11 seasons ⇒ 8 folds; eval years 2019…2026).
#   SENSITIVITY: 2020 dropped from BOTH train and eval (10 seasons ⇒ 7 folds; eval years 2019,
#                2021…2026), run and reported as a DECLARED sensitivity, not as an alternative
#                headline.
#   WHY 2020 IS IN THE PRIMARY, decided in advance and on design grounds only:
#     (a) it is what MH2 §7 measured and what this story's own 8-fold arithmetic assumes — changing
#         it after the fact would silently move the headline;
#     (b) power is the entire point of this re-run, and dropping 2020 costs a fold (8 → 7);
#     (c) 2020 is ATYPICAL but not unrepresented downstream — the extra-innings ghost runner it
#         introduced is permanent from 2023, so it is not a one-season-only regime in the way the
#         60-game schedule is.
#   AND WHY THE SENSITIVITY IS MANDATORY ANYWAY: 2020 is an 898-game season whose totals-generating
#   process (7-inning doubleheaders, no fans, a 60-game sprint) is structurally different. If the
#   verdict FLIPS between the two, neither reading is trustworthy and that fact is the finding.
MH21_MIN_YEAR = 2016
MH21_SENSITIVITY_EXCLUDE = (2020,)

# LOCK 1b — the field. NOT the 24–28-arm variant×learner grid E7.9 ran. MH2 §2b: DSR's bar rises
# with the FIELD SIZE, the required per-fold Sharpe at 8 folds falls 1.69 → 1.18 going from 28 arms
# to 4, and E7.9 measured that 74% of its own headline margin was the LEARNER SWAP rather than the
# features. So the family is the question E7.9 itself pre-registered as follow-up #2 — `plus_eb` on
# `total_runs` — crossed with the incumbent learner and ONE direct-learned foil.
#   ⚠️ THE FAMILY IS DECLARED, NOT DISCOVERED (MH2 §a): "you get to pre-register a family; you do
#   not get to discover one." No arm may be dropped from this list after a score is seen — trimming
#   a field after the fact under-taxes DSR and is a second layer of the very selection bias DSR
#   exists to deflate.
MH21_VARIANTS = ("incumbent", "plus_eb")
MH21_LEARNERS = ("ngboost_normal", "glm_elasticnet")   # incumbent class + direct-learned foil

# LOCK 2 — coverage is NOT uniform across the window (2016–20 ≈ 0.83 contract coverage vs ≈0.98 for
# 2024+), so the older folds lean harder on imputation. Per-fold coverage is reported BESIDE the
# per-fold score, and a lift living only in the thin folds is an imputation artifact, not a feature
# effect. This is a reporting obligation, not a gate — a coverage-based exclusion decided after the
# fact would be exactly the window-shopping Lock 1 forbids.

# LOCK 3 — THE DSR CONVENTION (MH2 defect 2). See `dsr_gate()` below.

# LOCK 4 — THE MATRIX IS STILL NOT POINT-IN-TIME (E7.9's own caveat; `load_features` reads each
# game's row AS IT EXISTS NOW, post-backfill and dense). Widening the window WIDENS that exposure:
# the 2016–2020 rows have had the longest to be backfilled. Every number this harness produces is a
# CEILING, not an achievable live figure, and the report says so unconditionally.
MH21_POINT_IN_TIME_CAVEAT = (
    "⚠️ **NOT POINT-IN-TIME — every number here is a CEILING.** `load_features` reads each game's "
    "row as it exists NOW (post-game backfilled and dense); the live serve only ever saw the sparse "
    "pre-game row. Widening the window to 2016 WIDENS this exposure rather than shrinking it — the "
    "oldest rows have had the longest to be backfilled — so a wide-window score is if anything a "
    "MORE optimistic ceiling than E7.9's. The honest live figure comes from scoring the ACTUALLY-"
    "SERVED predictions (`honest_live_skill.py`), never from this matrix."
)

# The pre-registered practically-meaningful effect, for the TRUSTWORTHY-DEAD vs POWER-LIMITED call
# (MH2 §0.5.4). It is the program's OWN materiality constant — `NOISE_FLOOR['crps'] = 0.02` — i.e. a
# design quantity fixed long before this story, not a threshold reverse-engineered from the answer
# (the NF1.8 discipline). A null is TRUSTWORTHY_DEAD only if the design could have resolved a lift
# this large and did not.
MH21_MEANINGFUL_CRPS_LIFT = 0.02


def calibration_tolerance(incumbent_pit_ks: float) -> float:
    """The amendment-#1 tolerance: max(absolute floor, 10% of the incumbent's PIT-KS).

    Kept a pure function so the guard test can pin the rule itself rather than a single constant.
    """
    if not np.isfinite(incumbent_pit_ks):
        return CALIBRATION_TOLERANCE_ABS
    return max(CALIBRATION_TOLERANCE_ABS, CALIBRATION_TOLERANCE_REL * abs(float(incumbent_pit_ks)))


# ── Q1 (PM-adjudicated 2026-07-29): margin ATTRIBUTION ────────────────────────────────────────────
# The gate compares leader-arm vs incumbent-arm, where an arm is (contract variant × learner class).
# That is the right PROMOTION question — "is any configuration better?" — and the gate is unchanged.
# But it CONFLATES the feature effect with a learner-class swap, and E7.9's three runs showed 54-77%
# of every leader's margin was the ngboost_normal -> glm_elasticnet swap, NOT the features. A report
# that credits such a margin to a features story is making a claim the study did not test. So every
# report now decomposes the margin before attributing it.


def margin_decomposition(table_rows: list[dict], incumbent_arm: str, leader_arm: str,
                         metric: str) -> dict:
    """Split (incumbent - leader) into the LEARNER-swap part and the CONTRACT part.

    learner_swap = incumbent_arm - (incumbent contract × LEADER's learner)
    contract     = (incumbent contract × leader's learner) - leader_arm
    The two sum to the reported margin by construction. Returns NaNs (never raises) when the
    same-learner reference arm is absent — a report must degrade, not crash.
    """
    key = f"{metric}_mean"
    scores = {r["arm"]: r[key] for r in table_rows}
    leader_learner = leader_arm.partition("::")[2]
    same_learner_ref = f"incumbent::{leader_learner}"
    inc, lead = scores.get(incumbent_arm), scores.get(leader_arm)
    ref = scores.get(same_learner_ref)
    if inc is None or lead is None:
        return {"available": False}
    total = inc - lead
    if ref is None:
        return {"available": False, "total": round(total, 6)}
    learner = inc - ref
    contract = ref - lead
    return {
        "available": True,
        "total": round(total, 6),
        "learner_swap": round(learner, 6),
        "contract": round(contract, 6),
        "learner_share": (round(learner / total, 4) if total not in (0, None) else None),
        "same_learner_reference_arm": same_learner_ref,
    }


def _sharpe(series) -> float:
    """Sharpe of a skill series — mean / SD with `ddof=1`, exactly as `h_harness.dsr_report._sr`.

    Returns 0.0 for a degenerate series (fewer than 3 finite points, or zero variance). The
    incumbent's own skill-vs-itself series is identically zero by construction, so this branch is
    REACHED on every run and must not raise.
    """
    s = np.asarray(series, float)
    s = s[np.isfinite(s)]
    if len(s) < 3:
        return 0.0
    sd = float(np.std(s, ddof=1))
    return float(np.mean(s) / sd) if sd > 0 else 0.0


def dsr_gate(fold_scores: dict[str, list[float]], incumbent_arm: str, leader_arm: str,
             *, n_trials: int) -> dict:
    """⭐ **LOCK 3 — E7.9's DSR CONVENTION, FIXED (MH2 defect 2). Both legacy biases INFLATED DSR.**

    E7.9 computed DSR on ~19 year-MONTH buckets and passed NO `trial_sharpes`. Two independent
    biases, and they push the SAME way:

      1. **`n_obs` was ~19 month-buckets, not 3 folds.** The DSR statistic scales with `√(n_obs−1)`,
         and month-buckets inside one purged fold are NOT independent draws — they share a training
         fit. Counting 19 where the design yields 3 inflates the statistic by ≈ √(18/2) ≈ 3×.
      2. **`trial_sharpes` was omitted**, so `deflated_sharpe` fell back to `V = 1/n_obs` — the
         ASYMPTOTIC null variance of one Sharpe estimate — in place of the MEASURED cross-trial
         Sharpe dispersion. `SR0 = √V·z(N)`, so an understated `V` understates the bar. This is the
         E7.15-H3 defect verbatim: a gate that reports on a quantity it is not measuring.

    ⇒ **E7.9's recorded `DSR 0.842` is an OVERSTATEMENT under this convention**; the true
    narrow-window figure is ≤ that. Which is why a wide-window number scored the LEGACY way would
    not have been comparable to it, and the whole point of the re-run would have been lost.

    THE FIX, matching `h_harness.dsr_report`: observations are the FOLDS, and `trial_sharpes` is
    measured from every arm's own per-fold skill series.

    `fold_scores[arm]` is that arm's per-fold mean of the honest metric (LOWER is better), so the
    skill series is `incumbent − arm` (positive ⇒ the arm is better).

    ⚠️ **THE INCUMBENT IS THE REFERENCE, SO IT IS NOT ONE OF THE TRIALS WHOSE DISPERSION `V`
    MEASURES.** Its skill-vs-itself series is identically zero by construction, and feeding that
    forced 0 into a variance estimated from only a handful of arms materially INFLATES `V` — and
    `SR0 = √V·z(N)` — for a purely structural reason. `h_harness.dsr_report` excludes its `foil`
    from `cols` for exactly this reason, and Lock 3 names that function as the target convention.
    So `V` is measured over the NON-reference arms. `n_trials` nevertheless stays the FULL field
    size, because every arm — the incumbent included — was a configuration that could have won, and
    multiplicity must not be understated. Both choices push the bar UP relative to the alternative,
    which is the right direction for a gate.

    🪤 **AND `V` FROM A SMALL FAMILY IS ITSELF UNSTABLE, so it is disclosed rather than trusted
    silently.** Two arms differing from the incumbent by a nearly CONSTANT amount across folds have
    a near-zero skill SD and hence an enormous Sharpe — a near-zero-denominator artifact, not
    genuine dispersion. Measured on smoke data during this harness's own build-out, one such arm
    drove `V` to 176.9 and `SR0` to ~14, which would make the gate unclearable for a reason that is
    arithmetic rather than evidential. This function therefore ALSO returns the asymptotic-`V`
    figure (the benchmark MH2 §7's design table used) and an explicit list of numerically degenerate
    trial arms. The MEASURED-`V` figure BINDS, as pre-registered; the other two exist so a high bar
    can be told apart from a broken one.

    Both conventions are returned. The FIXED one BINDS; the legacy one is reported beside it so the
    size of the MH2-defect-2 bias is visible on the record rather than asserted.
    """
    from betting_ml.utils.overfitting import deflated_sharpe

    inc = np.asarray(fold_scores[incumbent_arm], float)
    skill = {a: inc - np.asarray(v, float) for a, v in fold_scores.items()}
    lead = skill[leader_arm]
    lead = lead[np.isfinite(lead)]

    out: dict = {
        "convention": "per-FOLD observations + measured trial_sharpes (MH2.1 Lock 3)",
        "n_obs": int(len(lead)),
        "n_trials": int(n_trials),
        "dsr": float("nan"), "observed_sr": float("nan"), "sr0": float("nan"),
        "var_trials_sr": float("nan"), "available": False,
    }
    if len(lead) < 3 or np.std(lead) == 0:
        out["note"] = ("the leader's per-fold skill series is degenerate (fewer than 3 folds, or "
                       "identically zero because the leader IS the incumbent) — DSR is UNDEFINED "
                       "here, not failed")
        return out

    trial_arms = [a for a in fold_scores if a != incumbent_arm]
    trial_sharpes = [_sharpe(skill[a]) for a in trial_arms]
    res = deflated_sharpe(lead, n_trials=int(n_trials), trial_sharpes=trial_sharpes)
    n_obs = int(len(lead))
    asym = deflated_sharpe(lead, n_trials=int(n_trials), var_trials_sr=1.0 / n_obs)
    degenerate = [a for a, s in zip(trial_arms, trial_sharpes) if abs(s) > 10.0]
    out.update({
        "available": True,
        "dsr": float(res.dsr),
        "observed_sr": float(res.observed_sr),
        "sr0": float(res.sr0),
        "var_trials_sr": float(np.var(np.asarray(trial_sharpes, float), ddof=1))
        if len(trial_sharpes) > 1 else float("nan"),
        "skill_mean": float(np.mean(lead)),
        "skill_sd": float(np.std(lead, ddof=1)),
        "trial_arms": trial_arms,
        "trial_sharpes": [round(float(t), 4) for t in trial_sharpes],
        # reported, NEVER binding — the benchmark MH2 §7's design table used
        "dsr_asymptotic_V": float(asym.dsr),
        "sr0_asymptotic_V": float(asym.sr0),
        # a |Sharpe| this large at single-digit folds is a near-zero-denominator artifact
        "degenerate_trial_arms": degenerate,
    })
    return out


def variant_effect_by_learner(table_rows: list[dict], metric: str) -> list[dict]:
    """Per-learner effect of each contract variant vs the incumbent contract (+ = better).

    Holding the learner FIXED is the only way to read a FEATURE effect out of this grid; the
    headline margin cannot do it. Ordered by the learner's incumbent-contract score (best first).
    """
    key = f"{metric}_mean"
    scores = {r["arm"]: r[key] for r in table_rows}
    learners = sorted({r["learner"] for r in table_rows
                       if r.get("learner") and r["learner"] != "-"})
    out = []
    for lrn in learners:
        base = scores.get(f"incumbent::{lrn}")
        if base is None:
            continue
        row = {"learner": lrn, "incumbent": round(base, 4)}
        for v in ("plus_gb", "plus_eb", "plus_both"):
            x = scores.get(f"{v}::{lrn}")
            row[v] = round(base - x, 4) if x is not None else None
        out.append(row)
    return sorted(out, key=lambda r: r["incumbent"])


def design_bar(n_folds: int, n_arms: int) -> dict:
    """⭐ **LOCK 5 — STATE THE BAR BEFORE THE RUN, in the unit the gate actually uses.**

    `DSR ≥ 0.95` reads like a fixed bar and is not one: it is a required per-fold SHARPE that moves
    with BOTH the fold count and the field size. Printed before a single arm is fitted, this is a
    statement about the DESIGN that no result can contaminate — and it is what turns "E7.9 scored
    0.842 against 0.95" from a claim about the features into a claim about the window.

    Reported at the ASYMPTOTIC `V = 1/n_obs`, which is the same convention MH2 §7's design table
    used, so the numbers are directly comparable to it. ⚠️ The MEASURED `V` from the real run will
    differ — a tight, coherent family has a SMALLER cross-trial dispersion than the asymptotic
    fallback and so a LOWER bar — which is why the post-run report states the realised bar beside
    this one instead of quietly substituting it.
    """
    from betting_ml.utils.cv_power import (
        achievable_folds, dsr_ceiling, dsr_required_sr, pbo_evaluable,
    )

    return {
        "n_folds": int(n_folds),
        "n_arms": int(n_arms),
        "pbo_evaluable": bool(pbo_evaluable(n_folds, n_arms)),
        "dsr_ceiling_at_any_effect": round(float(dsr_ceiling(n_folds)), 4),
        "dsr_required_per_fold_sr_asymptotic_V": round(float(dsr_required_sr(
            n_obs=int(n_folds), n_trials=int(n_arms), var_trials_sr=1.0 / max(int(n_folds), 1))), 3),
        "reference_e7_9_design": {
            "n_folds": 3, "n_arms": 28,
            "dsr_ceiling_at_any_effect": round(float(dsr_ceiling(3)), 4),
            "dsr_required_per_fold_sr_asymptotic_V": round(float(dsr_required_sr(
                n_obs=3, n_trials=28, var_trials_sr=1.0 / 3)), 3),
            "pbo_evaluable": bool(pbo_evaluable(3, 28)),
        },
        "achievable_folds_check": int(achievable_folds(int(n_folds) + 3)),
    }


def classify_the_null(*, metric: str, n_folds: int, n_arms: int, margin: float,
                      dsr_fixed: dict) -> dict:
    """Classify an INCUMBENT_STANDS outcome into one of `cv_power.NULL_STATES` (MH2 §0.5.4).

    The whole point of MH2.1 is to move E7.9's null off POWER_LIMITED. That claim has to be
    COMPUTED, not asserted — and it can land on any of the seven states, including ones that are
    worse news than "underpowered".

    The MDE is stated against the gate that actually BINDS here. E7.9's rule is
    `margin > noise floor AND PBO AND DSR AND calibration` — it carries no fold-consistency clause
    and no BH family — so `cv_power.mde_in_sd_units` (which simulates a consistency+BH composite)
    would answer about a rule this harness does not run. Instead the detectable effect is derived
    from the DSR gate itself at the MEASURED dispersion, and compared against the pre-registered
    practically-meaningful lift `NOISE_FLOOR['crps']`.
    """
    from betting_ml.utils.cv_power import classify_null, dsr_required_sr

    beats_foil = bool(margin > 0)
    kw: dict = {"metric": metric, "n_folds": int(n_folds), "n_arms": int(n_arms),
                "beats_foil": beats_foil}
    detail: dict = {}
    if dsr_fixed.get("available"):
        sd = float(dsr_fixed["skill_sd"])
        kw.update({"observed_sr": float(dsr_fixed["observed_sr"]),
                   "var_trials_sr": float(dsr_fixed["var_trials_sr"])})
        req_sr = float(dsr_required_sr(n_obs=int(n_folds), n_trials=int(n_arms),
                                       var_trials_sr=float(dsr_fixed["var_trials_sr"])))
        # the SMALLEST metric lift this design could have certified, in the metric's own units
        detectable_lift = req_sr * sd
        detail = {
            "required_per_fold_sr_at_measured_V": round(req_sr, 3),
            "fold_skill_sd": round(sd, 5),
            "min_detectable_crps_lift": round(detectable_lift, 5),
            "pre_registered_meaningful_crps_lift": MH21_MEANINGFUL_CRPS_LIFT,
        }
        if sd > 0:
            kw.update({"mde_sd_units": req_sr,
                       "meaningful_sd_units": MH21_MEANINGFUL_CRPS_LIFT / sd})
    v = classify_null(**kw)
    return {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
            "folds_have": v.folds_have, "folds_needed": v.folds_needed,
            "max_field_size": v.max_field_size, "detail": {**v.detail, **detail}}


def _read_contract(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    return [c for c in cols if c not in IMPUTER_ADDED]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MODE 1 — the exposure audit (no fitting; run this BEFORE spending a retrain)
# ══════════════════════════════════════════════════════════════════════════════════════════════


def audit_served_contracts() -> dict:
    """Which SERVED contracts actually carry a column E7.5 / E7.5p can move?

    The story's premise is a train/serve mismatch on 'the served totals + run-diff models'. That
    premise is only true where an affected column is IN a served contract — and the v6 post_lineup
    contracts are 13-feature slim sets. Measuring this first is what keeps the retrain honest (and
    scoped): an unaffected contract needs no retrain, only the new-feature question.
    """
    out = {}
    for (target, tier), path in SERVED_CONTRACTS.items():
        p = PROJECT_ROOT / path
        if not p.exists():
            out[f"{target}/{tier}"] = {"error": f"missing sidecar {path}"}
            continue
        cols = _read_contract(path)
        affected = [c for c in cols if c in MLE_AFFECTED_COLS]
        out[f"{target}/{tier}"] = {
            "contract": path,
            "n_features": len(cols),
            "mle_affected_in_contract": affected,
            "n_mle_affected": len(affected),
            "has_gb_already": [c for c in cols if c in E79_GB_COLS],
            "train_serve_skew": bool(affected),
        }
    return out


def audit_prior_exposure(min_season: int = 2021) -> dict:
    """How much of the served starter population does the pitcher MLE actually move, and by how
    much? SF-free — reads the S3 lakehouse parquet directly.

    Reference for the magnitude is the GENERIC experience-band prior mean (`ref_eb_starter_priors`,
    age_band 'u25'). That is EXACT for `prior_only` rows (where the generic posterior IS the band
    mean) and an UPPER BOUND for `full_eb` rows (where the generic path would already have shrunk
    toward the pitcher's own observed line). Reported split by branch so the bound is visible
    rather than buried in a pooled average.
    """
    import duckdb

    conn = duckdb.connect()
    conn.execute("install httpfs; load httpfs; set s3_region='us-east-2';")
    try:
        conn.execute("create secret (type s3, provider credential_chain)")
    except Exception:
        pass  # a secret may already exist in this process
    b = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"
    s = f"read_parquet('{b}/eb_starter_posteriors/**/*.parquet')"
    p = f"read_parquet('{b}/milb_mle_pitcher_prior/data.parquet')"
    r = f"read_parquet('{b}/ref_eb_starter_priors/**/*.parquet')"

    exposure = conn.execute(f"""
        with s as (select * from {s} where season >= {int(min_season)}),
             p as (select try_cast(pitcher_id as bigint) pid from {p})
        select count(*)                                                              as starter_rows,
               sum(case when s.age_band = 'u25' then 1 else 0 end)                   as cold_start_rows,
               sum(case when s.age_band = 'u25' and p.pid is not null then 1 else 0 end) as mle_moved_rows
        from s left join p on p.pid = try_cast(s.pitcher_id as bigint)
    """).fetchone()

    magnitude = conn.execute(f"""
        with s as (select * from {s} where season >= {int(min_season)} and age_band = 'u25'),
             p as (select try_cast(pitcher_id as bigint) pid from {p}),
             ref as (select SEASON season, lower(METRIC) metric, MU mu from {r} where AGE_BAND = 'u25')
        select s.eb_data_source,
               count(*)                                              as n,
               avg(abs(s.eb_k_pct  - rk.mu))                         as mean_abs_k_shift,
               quantile_cont(abs(s.eb_k_pct - rk.mu), 0.9)           as p90_abs_k_shift,
               avg(abs(s.eb_bb_pct - rb.mu))                         as mean_abs_bb_shift
        from s
        join p on p.pid = try_cast(s.pitcher_id as bigint)
        left join ref rk on rk.season = s.season and rk.metric = 'k_pct'
        left join ref rb on rb.season = s.season and rb.metric = 'bb_pct'
        group by 1 order by 2 desc
    """).fetchdf()

    gb = conn.execute(
        f"select count(*) n, count(eb_gb_pct) nonnull, min(eb_gb_pct) lo, max(eb_gb_pct) hi from {s}"
    ).fetchone()
    conn.close()

    rows, cold, moved = exposure
    return {
        "min_season": min_season,
        "starter_rows": int(rows),
        "cold_start_rows": int(cold),
        "mle_moved_rows": int(moved),
        "share_of_starter_rows_moved": round(moved / rows, 4) if rows else None,
        # a game has two starters; P(at least one moved) under independence — a scoping figure,
        # NOT a claim about the joint distribution of the two rotations.
        "approx_share_of_games_touched": round(1 - (1 - moved / rows) ** 2, 4) if rows else None,
        "magnitude_vs_generic_band_prior_mean": magnitude.to_dict(orient="records"),
        "eb_gb_pct": {"rows": int(gb[0]), "non_null": int(gb[1]),
                      "min": float(gb[2]), "max": float(gb[3])},
    }


def run_audit(min_season: int) -> dict:
    contracts = audit_served_contracts()
    exposure = audit_prior_exposure(min_season)
    skewed = [k for k, v in contracts.items() if v.get("train_serve_skew")]
    result = {
        "story": STORY, "mode": "audit", "best_alpha": BEST_ALPHA,
        "served_contracts": contracts,
        "contracts_with_train_serve_skew": skewed,
        "prior_exposure": exposure,
        "leakage_posture": {
            "mle_map": "leakage-safe by construction — emit_projections refits per debut cohort on "
                       "STRICTLY-PRIOR cohorts; the minor line is strictly pre-debut. No as-of "
                       "rebuild is needed for the historical backfill.",
            "residual_full_sample_quantity": "the recalibrated kappa (one scalar per metric, from "
                                             "mle_prior.recalibrate) is fit on all graduates; it "
                                             "carries no player-specific information.",
        },
    }
    _write_audit_report(result)
    return result


def _write_audit_report(result: dict) -> None:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    (_JSON_DIR / "e7_9_audit.json").write_text(json.dumps(result, indent=2, default=float))

    ex = result["prior_exposure"]
    skewed = result["contracts_with_train_serve_skew"]
    lines: list[str] = []
    a = lines.append
    a(f"# MLB Edge-{STORY} — train/serve exposure audit (BATTER + STARTER MiLB-MLE priors)")
    a("")
    a("> ⚠️ **Not an edge result.** This scopes a retrain; `best_alpha = 0`.")
    a("")
    a("## Which SERVED contracts does the MLE actually touch?")
    a("")
    a("| model / tier | features | E7.5/E7.5p columns in contract | train-serve skew |")
    a("|---|---:|---|---|")
    for k, v in result["served_contracts"].items():
        if "error" in v:
            a(f"| {k} | — | `{v['error']}` | ? |")
            continue
        cols = ", ".join(f"`{c}`" for c in v["mle_affected_in_contract"]) or "—"
        a(f"| {k} | {v['n_features']} | {cols} | {'**YES**' if v['train_serve_skew'] else 'no'} |")
    a("")
    if skewed:
        a(f"**Skewed contracts: {', '.join(skewed)}.** Every other served contract is UNAFFECTED — "
          "the MLE-moved columns are simply not in it, so for those models E7.9 is a "
          "new-feature question (`eb_gb_pct`) and not a skew repair.")
    else:
        a("**No served contract carries an MLE-moved column** — the flagged train/serve skew does "
          "not reach any served prediction. E7.9 reduces to the `eb_gb_pct` question.")
    a("")
    a("## How much does the pitcher MLE move the served starter population?")
    a("")
    a(f"- Starter rows (season ≥ {ex['min_season']}): **{ex['starter_rows']:,}**")
    a(f"- Cold-start (`age_band='u25'`): **{ex['cold_start_rows']:,}**")
    a(f"- Cold-start WITH an MLE prior (the rows whose `eb_k_pct`/`eb_bb_pct` actually change): "
      f"**{ex['mle_moved_rows']:,}** = {ex['share_of_starter_rows_moved']:.1%} of starter rows "
      f"(≈{ex['approx_share_of_games_touched']:.1%} of games touch ≥1 moved starter)")
    a("")
    a("Magnitude vs the generic experience-band prior mean — EXACT for `prior_only`, an UPPER "
      "BOUND for `full_eb` (the generic path would already have shrunk toward the observed line):")
    a("")
    a("| eb_data_source | n | mean abs K% shift | p90 | mean abs BB% shift |")
    a("|---|---:|---:|---:|---:|")
    for row in ex["magnitude_vs_generic_band_prior_mean"]:
        a(f"| {row['eb_data_source']} | {int(row['n']):,} | {row['mean_abs_k_shift']:.4f} | "
          f"{row['p90_abs_k_shift']:.4f} | {row['mean_abs_bb_shift']:.4f} |")
    a("")
    g = ex["eb_gb_pct"]
    a(f"`eb_gb_pct` (the E7.5p column E7.9 joins through): {g['non_null']:,}/{g['rows']:,} non-null, "
      f"range {g['min']:.3f}–{g['max']:.3f}.")
    a("")
    a("## Leakage posture")
    a("")
    for k, v in result["leakage_posture"].items():
        a(f"- **{k}** — {v}")
    a("")
    (_ABL / "e7_9_train_serve_audit.md").write_text("\n".join(lines) + "\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MODE 2 — the pre-registered retrain bake-off
# ══════════════════════════════════════════════════════════════════════════════════════════════


def build_arm_contracts(target: str, tier: str, df_cols,
                        family: str = "full") -> dict[str, list[str]]:
    """The PRE-REGISTERED contract variants. Registered before any result is seen; a variant whose
    added columns are entirely absent from the matrix is DROPPED (and reported), never silently
    collapsed onto the incumbent — two identically-columned arms would double-count in the PBO
    surface and understate the multiple-testing burden.

    `family='mh2_1'` restricts to MH2.1's pre-registered `{incumbent, plus_eb}` (see `MH21_VARIANTS`).
    The restriction is DECLARED IN THE SOURCE ahead of the run, not applied to a scored field.
    """
    base = [c for c in _read_contract(SERVED_CONTRACTS[(target, tier)]) if c in df_cols]
    gb = [c for c in E79_GB_COLS if c in df_cols and c not in base]
    eb = [c for c in MLE_AFFECTED_COLS if c in df_cols and c not in base]

    variants = {"incumbent": base}
    if gb:
        variants["plus_gb"] = base + gb
    if eb:
        variants["plus_eb"] = base + eb
    if gb and eb:
        variants["plus_both"] = base + gb + eb
    if family == "mh2_1":
        variants = {k: v for k, v in variants.items() if k in MH21_VARIANTS}
    return variants


#: A contract column at or below this non-null share in a season is treated as STRUCTURALLY ABSENT
#: — the feature did not exist yet, rather than being sporadically missing.
ABSENT_COVERAGE_THRESHOLD = 0.05


def contract_coverage_by_season(df, cols: list[str]) -> dict[int, dict]:
    """⭐ **LOCK 2 — per-season coverage of the incumbent contract, at PER-COLUMN resolution.**

    MH2 measured 2016–20 at ≈0.83 contract coverage against ≈0.98 for 2024+, so the older folds
    lean harder on imputation. Reported BESIDE the per-fold score so a reader can see whether a lift
    lives only in the thin folds — which would make it an imputation artifact, not a feature effect.
    Computed on the ACTUAL training matrix (not the served store), so it describes the rows the arms
    were really fitted and scored on.

    ⚠️ **A PER-SEASON MEAN HIDES THE THING THAT ACTUALLY MATTERS, so this also reports which
    columns are STRUCTURALLY ABSENT.** Measured on the REAL served store (2026-08-02), TWO of the
    13 `total_runs/post_lineup` contract columns are absent for part of the MH2.1 window:

      * `away_lineup_bat_speed_vs_starter_velo` — Statcast BAT-TRACKING, launched mid-2023:
        **0.000 non-null 2016–2022**, 0.431 in 2023, ~0.98 from 2024.
      * `home_starter_proj_fip` — a FanGraphs projection that begins in 2020:
        **0.000 non-null 2016–2019**, ~0.97+ thereafter.

    A mean of "0.83" reads like uniformly noisier data. The truth is that eval fold 2019 evaluates
    **11 of 13** features, 2020–2022 evaluate **12**, 2023 evaluates 12 + a 43%-covered 13th, and
    only **2024–2026 evaluate the contract that is actually served** — a structurally DIFFERENT
    contract, not merely a sparser one. That distinction is the whole point of Lock 2 and a pooled
    mean cannot express it. (2015 has SEVEN of the 13 absent, which is why the window starts at
    2016.)
    """
    present = [c for c in cols if c in df.columns]
    out: dict[int, dict] = {}
    for yr, g in df.groupby(df["game_year"].astype(int)):
        per_col = g[present].notna().mean() if present else None
        out[int(yr)] = {
            "rows": int(len(g)),
            "coverage": (round(float(per_col.mean()), 4) if present else float("nan")),
            "structurally_absent": (sorted(per_col[per_col <= ABSENT_COVERAGE_THRESHOLD].index)
                                    if present else []),
            "per_column": ({c: round(float(v), 4) for c, v in per_col.items()} if present else {}),
        }
    return out


class _OracleSpec:
    """E2.1-r selection-metric sanity: a predictive centred on the REALIZED target with a tiny
    spread. It cannot be beaten on a proper score. If any candidate outscores it, the metric is
    inverted and the run must HALT rather than crown a winner."""

    name = "oracle_floor"

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None):
        from betting_ml.utils.promotion_gate import PredictiveOutput
        y = np.asarray(yev, float)
        return PredictiveOutput.normal(y, np.full(len(y), 1e-3))


def run_retrain_bakeoff(target: str, tier: str, *, seed: int, smoke: bool,
                        refresh_cache: bool, embargo_days: int, s3: bool = False,
                        min_year: int = 2021, exclude_seasons: tuple[int, ...] = (),
                        family: str = "full") -> dict:
    from betting_ml.scripts.model_bakeoff import (
        _TARGETS, _assert_market_blind, _candidates, load_clean_matrix,
    )
    from betting_ml.scripts.promotion_gate_eval import _impute, make_gate_splitter
    from betting_ml.utils.feature_hygiene import is_identifier_name
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
    from betting_ml.utils.promotion_gate import NOISE_FLOOR, calibration_report

    cfg = _TARGETS[target]
    kind, metric, tcol = cfg["kind"], cfg["metric"], cfg["col"]
    if kind != "reg":
        raise SystemExit(f"{STORY} covers the regression champions only; got kind={kind}")

    # SF-FREE READ (repo doctrine): with --s3 the matrix comes from the S3 lakehouse via DuckDB
    # instead of Snowflake. This is not just hygiene — the DuckDB `--w8b` build carries the E7.9
    # `*_starter_eb_gb_pct` join from its FIRST rebuild, whereas the Snowflake table does not until
    # the operator recreates the external table and re-materializes. Reading S3 is what lets the
    # retrain run WITHOUT waiting on that, and it is the same surface the served `--s3` path uses.
    if s3:
        from betting_ml.utils.data_loader import set_s3_mode
        set_s3_mode(True)
        print(f"[{STORY}] reading the training matrix from the S3 lakehouse (Snowflake-free)")
    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke, min_year=min_year)
    # LOCK 1 — the window, applied exactly as pre-registered. The exclusion is a DECLARED
    # sensitivity, never a post-hoc trim; the report always names which arm of it produced it.
    if exclude_seasons:
        keep = ~df["game_year"].astype(int).isin([int(y) for y in exclude_seasons])
        print(f"[{STORY}] LOCK-1 sensitivity: dropping season(s) {list(exclude_seasons)} from BOTH "
              f"train and eval — {int((~keep).sum()):,} of {len(df):,} rows")
        df = df.loc[keep].reset_index(drop=True)
    seasons = sorted(df["game_year"].astype(int).unique())
    variants = build_arm_contracts(target, tier, set(df.columns), family=family)
    # ⚠️ "DROPPED" means the added columns are ABSENT FROM THE MATRIX — a data fact worth reading
    # before trusting a verdict. It must NOT be conflated with a variant the pre-registered family
    # deliberately never included; reporting an intentional exclusion as a drop would make a
    # declared field look like a broken one.
    registered_extra = ([v for v in MH21_VARIANTS if v != "incumbent"] if family == "mh2_1"
                        else ["plus_gb", "plus_eb", "plus_both"])
    dropped = [v for v in registered_extra if v not in variants]
    for cols in variants.values():
        _assert_market_blind(cols)
        bad = [c for c in cols if is_identifier_name(c)]
        if bad:
            raise SystemExit(f"❌ identifier column(s) in a contract variant: {bad}")

    # learner slate: reuse the E1.9 bake-off classes so the comparison is apples-to-apples with the
    # selection that produced the incumbent. Floors are dropped here — E7.9's bar is the INCUMBENT
    # arm, not no-skill; the market floor would also break the market-blind posture of the grid.
    classes = [c for c in _candidates(kind, target, df, seed=seed, smoke=smoke)
               if not c.name.startswith("floor_")]
    if family == "mh2_1":
        classes = [c for c in classes if c.name in MH21_LEARNERS]
        missing = [n for n in MH21_LEARNERS if n not in {c.name for c in classes}]
        if missing:
            # A pre-registered arm that cannot be BUILT must HALT, never silently shrink the field:
            # a field trimmed after registration under-taxes DSR (MH2 §a). `--smoke` legitimately
            # caps the slate, so it is exempt — and is not a result either way.
            raise SystemExit(
                f"❌ MH2.1 pre-registered learner(s) {missing} are not in the candidate slate. The "
                f"field may not be silently narrowed — fix the slate or amend the registration on "
                f"the record before running."
            )
    arms = [(v, c) for v in variants for c in classes]
    arm_names = [f"{v}::{c.name}" for v, c in arms]
    incumbent_arm = f"incumbent::{INCUMBENT_CLASS[target]}"
    if incumbent_arm not in arm_names:
        raise SystemExit(f"❌ the incumbent arm {incumbent_arm} is not in the grid {arm_names}")

    # one splitter over the UNION of every variant's columns, so every arm sees IDENTICAL folds
    # (a per-variant purge band would give the wider contract different eval rows and make the
    # arms incomparable).
    union_cols = sorted({c for cols in variants.values() for c in cols})
    splitter, _ = make_gate_splitter(True, feature_cols=union_cols, embargo_days=embargo_days)
    folds = list(splitter(df))
    print(f"[{STORY}] {target}/{tier}: {len(variants)} contract variants × {len(classes)} classes "
          f"= {len(arms)} arms × {len(folds)} purged folds  (metric={metric})")
    for v, cols in variants.items():
        print(f"   {v:10s} {len(cols):4d} features"
              + (f"  (+{sorted(set(cols) - set(variants['incumbent']))})" if v != "incumbent" else ""))
    if dropped:
        print(f"   [dropped variants — added columns absent from the matrix] {dropped}")

    # ── LOCK 5 — THE BAR, STATED BEFORE A SINGLE ARM IS FITTED ──────────────────────────────────
    bar = design_bar(len(folds), len(arm_names))
    print(f"[{STORY}] window {seasons[0]}–{seasons[-1]} ({len(seasons)} seasons) → {len(folds)} folds"
          + (f"  [2020 EXCLUDED — declared sensitivity]" if 2020 in exclude_seasons else ""))
    print(f"[{STORY}] PRE-REGISTERED BAR (asymptotic V, before any result): required per-fold "
          f"Sharpe {bar['dsr_required_per_fold_sr_asymptotic_V']} at {len(folds)} folds × "
          f"{len(arm_names)} arms · DSR ceiling at ANY effect "
          f"{bar['dsr_ceiling_at_any_effect']} · PBO evaluable={bar['pbo_evaluable']}")
    print(f"[{STORY}]   reference — E7.9 as it ran (3 folds × 28 arms): required per-fold Sharpe "
          f"{bar['reference_e7_9_design']['dsr_required_per_fold_sr_asymptotic_V']}, "
          f"ceiling {bar['reference_e7_9_design']['dsr_ceiling_at_any_effect']}, "
          f"PBO evaluable={bar['reference_e7_9_design']['pbo_evaluable']}")

    coverage = contract_coverage_by_season(df, variants["incumbent"])

    per_arm: dict[str, list] = {n: [] for n in arm_names}
    oracle = _OracleSpec()
    per_arm[oracle.name] = []
    for tr, ev in folds:
        ytr, yev = df.loc[tr, tcol].values, df.loc[ev, tcol].values
        cache: dict[str, tuple] = {}
        for (v, c), name in zip(arms, arm_names):
            if v not in cache:
                cache[v] = _impute(df.loc[tr, variants[v]], df.loc[ev, variants[v]])
            Xtr, Xev = cache[v]
            per_arm[name].append((ev, c.fit_predict(Xtr, ytr, Xev, yev), yev))
        Xtr, Xev = cache["incumbent"]
        per_arm[oracle.name].append((ev, oracle.fit_predict(Xtr, ytr, Xev, yev), yev))

    # the eval SEASON of each fold — the observation unit the FIXED DSR convention uses (Lock 3)
    fold_years = [int(pd.Series(df.loc[ev, "game_year"]).astype(int).iloc[0]) for _, ev in folds]
    fold_rows = [int(len(ev)) for _, ev in folds]

    # pool per-arm scores + a (bucket × arm) matrix for PBO + a (fold × arm) matrix for DSR
    rows, bucket_perf, fold_scores = [], {}, {}
    for name in arm_names + [oracle.name]:
        primary, buckets, pit, per_fold = [], [], [], []
        for ev, out, yev in per_arm[name]:
            s = out.score_to_truth(yev, metric)
            primary.append(s)
            per_fold.append(float(np.nanmean(s)))
            ym = (df.loc[ev, "game_year"].astype(int).astype(str) + "-"
                  + df.loc[ev, "game_date"].astype("datetime64[ns]").dt.month.astype(str).str.zfill(2))
            buckets.append(ym.values)
            if out.kind in ("normal", "lognormal", "samples"):
                pit.append(calibration_report(yev, out)["pit_ks"])
        fold_scores[name] = per_fold
        primary = np.concatenate(primary)
        bvec = np.concatenate(buckets)
        bucket_perf[name] = pd.Series(primary).groupby(pd.Series(bvec)).mean().to_dict()
        variant, _, cls = name.partition("::")
        rows.append({
            "arm": name, "variant": variant, "learner": cls or "-",
            f"{metric}_mean": float(np.nanmean(primary)),
            "pit_ks": float(np.nanmean(pit)) if pit else float("nan"),
            "n": int(len(primary)),
        })
    table = pd.DataFrame(rows).sort_values(f"{metric}_mean").reset_index(drop=True)

    # ── E2.1-r ORACLE-FLOOR SANITY — must fire BEFORE any winner is declared ──
    oracle_score = float(table.loc[table["arm"] == oracle.name, f"{metric}_mean"].iloc[0])
    cand = table[table["arm"] != oracle.name]
    beats_oracle = list(cand.loc[cand[f"{metric}_mean"] < oracle_score - 1e-12, "arm"])
    if beats_oracle:
        raise SystemExit(
            f"❌ ORACLE-FLOOR VIOLATION: {beats_oracle} scored better than an oracle that SEES the "
            f"target ({metric} {oracle_score:.6f}). The selection metric is inverted — fix the "
            f"metric before reading any result (E2.1-r)."
        )

    inc = cand.loc[cand["arm"] == incumbent_arm].iloc[0]
    best = cand.iloc[0]
    nf = NOISE_FLOOR.get(metric, 0.0)
    margin = float(inc[f"{metric}_mean"]) - float(best[f"{metric}_mean"])  # >0 ⇒ challenger better

    # PBO over the WHOLE grid (every variant × class counts toward the multiple-testing surface).
    # Kept on year-MONTH buckets, unchanged and PRE-REGISTERED as the binding surface, so the wide
    # window is comparable to E7.9 on this gate; the coarser fold-level PBO is reported beside it.
    all_b = sorted(set().union(*[set(bucket_perf[n]) for n in arm_names]))
    perf = np.array([[bucket_perf[n].get(b, np.nan) for n in arm_names] for b in all_b])
    keep = ~np.isnan(perf).any(axis=1)
    pbo_val = float("nan")
    if keep.sum() >= 4 and len(arm_names) >= 2:
        pbo_val = float(pbo_cscv(perf[keep], higher_is_better=False,
                                 n_splits=min(16, keep.sum() - (keep.sum() % 2))).pbo)
    fold_perf = np.array([[fold_scores[n][i] for n in arm_names] for i in range(len(folds))])
    pbo_fold = float("nan")
    if len(folds) >= 4 and len(arm_names) >= 2 and np.isfinite(fold_perf).all():
        pbo_fold = float(pbo_cscv(fold_perf, higher_is_better=False,
                                  n_splits=len(folds) - (len(folds) % 2)).pbo)

    # ── LOCK 3 — DSR under the FIXED convention (per-FOLD obs + measured trial_sharpes). BINDING.
    # ⚠️ CANDIDATE ARMS ONLY — the E2.1-r `oracle_floor` is a diagnostic ANCHOR that SEES the
    # target, not a trial. Leaving it in the trial field gave it a per-fold skill Sharpe of ~30 and
    # drove the measured dispersion `V` to 220 (`SR0` ≈ 15.6), i.e. an anchor that exists to police
    # the metric was silently setting the gate's bar. Caught by this harness's own
    # degenerate-trial-arm disclosure during the build-out, on smoke data, before any real arm was
    # scored. `arm_names` excludes the oracle by construction — the same set PBO already uses.
    dsr_fixed = dsr_gate({n: fold_scores[n] for n in arm_names},
                         incumbent_arm, str(best["arm"]), n_trials=len(arm_names))
    dsr_p = float(dsr_fixed["dsr"])

    # the LEGACY convention (per-bucket obs, no trial_sharpes) — reported, NOT binding, so the size
    # of MH2 defect 2 is visible on the record instead of asserted. Both of its biases inflate DSR,
    # so `dsr_legacy > dsr_fixed` is the expected direction and E7.9's recorded 0.842 is an
    # OVERSTATEMENT of what that design supported.
    imp = np.array([bucket_perf[incumbent_arm].get(b, np.nan) - bucket_perf[best["arm"]].get(b, np.nan)
                    for b in all_b], float)
    imp = imp[np.isfinite(imp)]
    dsr_legacy_obj = (deflated_sharpe(imp, n_trials=len(arm_names))
                      if len(imp) >= 3 and np.std(imp) > 0 else None)
    dsr_legacy = {
        "convention": "per-BUCKET (year-month) observations, no trial_sharpes — E7.9 as recorded",
        "n_obs": int(len(imp)),
        "dsr": float(getattr(dsr_legacy_obj, "dsr", float("nan"))) if dsr_legacy_obj else float("nan"),
        "binding": False,
    }

    # AMENDMENT #1 (2026-07-29): tolerance = max(1e-3, 10% of the incumbent's PIT-KS) instead of the
    # original 1e-9, which tripped on rounding. See the amendment block at the top of this module.
    calib_tol = calibration_tolerance(float(inc["pit_ks"]))
    calib_ok = bool(np.isnan(best["pit_ks"]) or np.isnan(inc["pit_ks"])
                    or best["pit_ks"] <= inc["pit_ks"] + calib_tol)
    # Would this run have FAILED under the pre-amendment tolerance? If so the report must say so
    # explicitly, so a pass that depends on the amendment is never silent.
    calib_ok_legacy = bool(np.isnan(best["pit_ks"]) or np.isnan(inc["pit_ks"])
                           or best["pit_ks"] <= inc["pit_ks"] + CALIBRATION_AMENDMENT_LEGACY_TOL)
    gates = {
        "beats_incumbent_by_more_than_noise_floor": bool(best["arm"] != incumbent_arm and margin > nf),
        "pbo_lt_0_2": bool(np.isfinite(pbo_val) and pbo_val < PBO_MAX),
        "dsr_gt_0_at_95": bool(np.isfinite(dsr_p) and dsr_p >= DSR_MIN_CONF),
        "calibration_not_degraded": calib_ok,
    }
    ship = all(gates.values())
    verdict = "SHIP_CHALLENGER" if ship else "INCUMBENT_STANDS"

    # LOCK 2 — per-fold score BESIDE per-fold contract coverage, so "the lift lives only in the thin
    # folds" is readable rather than a thing a reader has to take on trust.
    per_fold_table = [
        {
            "fold": i + 1,
            "eval_season": fold_years[i],
            "eval_rows": fold_rows[i],
            "contract_coverage": coverage.get(fold_years[i], {}).get("coverage"),
            "structurally_absent": coverage.get(fold_years[i], {}).get("structurally_absent") or [],
            "incumbent": round(fold_scores[incumbent_arm][i], 4),
            "leader": round(fold_scores[str(best["arm"])][i], 4),
            "leader_minus_incumbent": round(
                fold_scores[str(best["arm"])][i] - fold_scores[incumbent_arm][i], 4),
        }
        for i in range(len(folds))
    ]

    result = {
        "story": STORY, "mode": "bakeoff", "best_alpha": BEST_ALPHA,
        "target": target, "tier": tier, "metric": metric, "smoke": smoke, "seed": seed,
        # ── MH2.1 provenance: the window and the field, as registered ──
        "window": {
            "min_year": int(min_year),
            "excluded_seasons": [int(y) for y in exclude_seasons],
            "seasons": [int(s) for s in seasons],
            "n_seasons": len(seasons),
            "family": family,
            "is_mh2_1": bool(family == "mh2_1"),
            "arm": ("PRIMARY (2020 kept)" if family == "mh2_1" and not exclude_seasons
                    else "SENSITIVITY (2020 dropped from train AND eval)"
                    if family == "mh2_1" else "n/a — E7.9 default field"),
        },
        "design_bar": bar,
        "contract_coverage_by_season": {str(k): v for k, v in coverage.items()},
        "per_fold": per_fold_table,
        "dsr_fixed": dsr_fixed,
        "dsr_legacy_convention": dsr_legacy,
        "pbo_fold_level": pbo_fold,
        "point_in_time_caveat": MH21_POINT_IN_TIME_CAVEAT,
        "n_arms": len(arm_names), "n_folds": len(folds), "n_rows": int(len(df)),
        "variants": {k: {"n_features": len(v),
                         "added_vs_incumbent": sorted(set(v) - set(variants["incumbent"]))}
                     for k, v in variants.items()},
        "dropped_variants": dropped,
        "incumbent_arm": incumbent_arm,
        "incumbent_metric": float(inc[f"{metric}_mean"]),
        "leader_arm": str(best["arm"]),
        "leader_metric": float(best[f"{metric}_mean"]),
        "margin_vs_incumbent": round(margin, 6),
        "noise_floor": nf,
        "pbo": pbo_val, "dsr": dsr_p,
        "oracle_metric": oracle_score, "oracle_floor_ok": True,
        "gates": gates, "verdict": verdict,
        # Q1: never report a margin without its attribution.
        "margin_decomposition": margin_decomposition(
            table.to_dict(orient="records"), incumbent_arm, str(best["arm"]), metric),
        "variant_effect_by_learner": variant_effect_by_learner(
            table.to_dict(orient="records"), metric),
        # Q2 provenance: which tolerance scored this run, and whether the verdict depends on it.
        "calibration_tolerance": calib_tol,
        "calibration_amendment": CALIBRATION_AMENDMENT_DATE,
        "calibration_would_fail_pre_amendment": bool(calib_ok and not calib_ok_legacy),
        "table": table.to_dict(orient="records"),
    }
    # LOCK 5 — a null must NAME which of the seven states it is in (MH2 §0.5.4). Computed, never
    # asserted: MH2.1's whole claim is that this null moves off POWER_LIMITED, and that claim is
    # only worth anything if the classifier was free to land somewhere worse.
    if verdict == "INCUMBENT_STANDS":
        result["null_classification"] = classify_the_null(
            metric=metric, n_folds=len(folds), n_arms=len(arm_names),
            margin=margin, dsr_fixed=dsr_fixed)
    _write_bakeoff_report(result, table)
    print(f"\n[{STORY}] VERDICT: {verdict}  (leader={result['leader_arm']}, "
          f"margin={margin:+.4f} vs floor {nf}, PBO={pbo_val:.3f}, "
          f"DSR={dsr_p:.3f} [fixed convention; legacy {dsr_legacy['dsr']:.3f}])")
    if result.get("null_classification"):
        print(f"[{STORY}] NULL STATE: {result['null_classification']['state']} — "
              f"{result['null_classification']['reason']}")
    return result


def _report_stem(result: dict) -> str:
    """Where a run's artifacts land.

    ⚠️ **AN MH2.1 RUN MUST NEVER OVERWRITE AN E7.9 RECORD.** They answer the same question on
    different designs, and E7.9's three recorded verdicts are the baseline MH2.1 is measured
    against — clobbering one would destroy the comparison the story exists to make. The window and
    the sensitivity arm are both in the name, so the primary and the 2020-dropped sensitivity are
    separate artifacts too.
    """
    w = result.get("window") or {}
    if not w.get("is_mh2_1"):
        return f"e7_9_retrain_{result['target']}_{result['tier']}" + ("_smoke" if result["smoke"] else "")
    excl = "".join(f"_no{y}" for y in w.get("excluded_seasons") or [])
    return (f"mh2_1_retrain_{result['target']}_{result['tier']}_w{w.get('min_year')}{excl}"
            + ("_smoke" if result["smoke"] else ""))


def _append_mh21_sections(a, result: dict, m: str) -> None:
    """The four MH2.1 lock disclosures, emitted into every wide-window report.

    Each is a REPORTING obligation from the pre-registration, so none of them may be conditional on
    the result being interesting — a disclosure that only appears when it flatters the run is not a
    disclosure.
    """
    w = result["window"]
    bar = result.get("design_bar") or {}
    fixed = result.get("dsr_fixed") or {}
    legacy = result.get("dsr_legacy_convention") or {}

    # ── LOCK 1 + LOCK 5: the design and the bar, both fixed before the run ──
    a("## The design, and the bar it had to clear — both PRE-REGISTERED")
    a("")
    a(f"- **Window** `{w['min_year']}–{w['seasons'][-1]}` — {w['n_seasons']} seasons ⇒ "
      f"**{result['n_folds']} folds** (E7.9 ran 6 seasons ⇒ 3). Arm: **{w['arm']}**."
      + (f" Excluded: {w['excluded_seasons']}." if w.get("excluded_seasons") else ""))
    a(f"- **Field** {result['n_arms']} arms — the pre-registered family "
      f"`{list(result['variants'])}` × `{list(MH21_LEARNERS)}`, NOT E7.9's 28-arm grid. Declared in "
      f"source before the run; no arm was dropped after a score was seen.")
    a("")
    a("| design | folds | arms | required per-fold Sharpe for `DSR ≥ 0.95` | DSR ceiling at ANY effect | PBO evaluable |")
    a("|---|---:|---:|---:|---:|---|")
    ref = bar.get("reference_e7_9_design", {})
    a(f"| E7.9, as it ran | {ref.get('n_folds')} | {ref.get('n_arms')} | "
      f"{ref.get('dsr_required_per_fold_sr_asymptotic_V')} | "
      f"{ref.get('dsr_ceiling_at_any_effect')} | {ref.get('pbo_evaluable')} |")
    a(f"| **this run** | {bar.get('n_folds')} | {bar.get('n_arms')} | "
      f"**{bar.get('dsr_required_per_fold_sr_asymptotic_V')}** | "
      f"{bar.get('dsr_ceiling_at_any_effect')} | {bar.get('pbo_evaluable')} |")
    a("")
    a("(Asymptotic `V = 1/n_obs`, the convention MH2 §7's design table used, so these are directly "
      "comparable to it. The bar at the run's MEASURED dispersion is stated in the DSR section "
      "below — it is not substituted for this one.)")
    a("")

    # ── LOCK 3: the DSR convention fix, and the size of the bias it removes ──
    a("## ⭐ LOCK 3 — the DSR convention, FIXED (MH2 defect 2)")
    a("")
    a("E7.9 computed DSR on ~19 year-MONTH buckets and passed no `trial_sharpes`. **Both biases "
      "inflate DSR**: month-buckets inside one purged fold are not independent draws (the statistic "
      "scales with `√(n_obs−1)`), and omitting `trial_sharpes` substitutes the asymptotic "
      "`V = 1/n_obs` for the MEASURED cross-trial dispersion in `SR0 = √V·z(N)`. So **E7.9's "
      "recorded `DSR 0.842` is an OVERSTATEMENT of what that design supported** — which is exactly "
      "why a wide-window number scored the legacy way would not have been comparable to it.")
    a("")
    a("| convention | observations | `n_obs` | trial dispersion `V` | DSR | binds |")
    a("|---|---|---:|---|---:|---|")
    if fixed.get("available"):
        a(f"| **FIXED** (per-fold + measured `trial_sharpes`) | purged folds | {fixed['n_obs']} | "
          f"measured, {fixed['var_trials_sr']:.5f} | **{fixed['dsr']:.3f}** | ✅ **YES** |")
    else:
        a(f"| **FIXED** (per-fold + measured `trial_sharpes`) | purged folds | "
          f"{fixed.get('n_obs')} | — | UNDEFINED | ✅ **YES** |")
    a(f"| legacy (E7.9 as recorded) | year-month buckets | {legacy.get('n_obs')} | "
      f"asymptotic `1/n_obs` | {legacy.get('dsr', float('nan')):.3f} | no — reported only |")
    a("")
    if fixed.get("available"):
        a(f"Leader's per-fold skill series (incumbent − leader, positive ⇒ leader better): mean "
          f"`{fixed['skill_mean']:+.5f}`, SD `{fixed['skill_sd']:.5f}`, Sharpe "
          f"`{fixed['observed_sr']:.3f}` against a deflated benchmark `SR0 = {fixed['sr0']:.3f}`.")
        a("")
        a(f"Trial Sharpes (non-reference arms — the incumbent IS the reference, so its "
          f"identically-zero skill series is excluded from `V` per `h_harness.dsr_report`): "
          f"`{dict(zip(fixed.get('trial_arms', []), fixed.get('trial_sharpes', [])))}`.")
        a("")
        a(f"**Sensitivity on the benchmark, so a high bar can be told from a broken one:** at the "
          f"asymptotic `V = 1/n_obs` (the benchmark MH2 §7's design table used) the same series "
          f"gives `SR0 = {fixed['sr0_asymptotic_V']:.3f}` and "
          f"**DSR {fixed['dsr_asymptotic_V']:.3f}**, against the measured-`V` "
          f"`SR0 = {fixed['sr0']:.3f}` / DSR {fixed['dsr']:.3f}. The MEASURED figure BINDS, as "
          f"pre-registered — this line is disclosure, not a re-pick.")
        a("")
        if fixed.get("degenerate_trial_arms"):
            a(f"🪤 **`V` IS CONTAMINATED BY A NEAR-ZERO-DENOMINATOR ARM.** "
              f"{fixed['degenerate_trial_arms']} post a per-fold skill Sharpe above 10 — an arm "
              f"differing from the incumbent by a nearly CONSTANT amount across folds, which is an "
              f"arithmetic artifact of a small fold count rather than genuine cross-trial "
              f"dispersion. It inflates `V`, hence `SR0`, hence makes the measured-`V` DSR harder "
              f"than the evidence warrants. **Read the asymptotic-`V` figure above beside it before "
              f"concluding anything about the mechanism from this gate.**")
            a("")
    if not fixed.get("available") and fixed.get("note"):
        a(f"⚠️ {fixed['note']}")
        a("")
    if np.isfinite(result.get("pbo_fold_level", float("nan"))):
        a(f"PBO is reported on BOTH surfaces: **{result['pbo']:.3f}** on year-month buckets "
          f"(pre-registered as binding, so the wide window stays comparable to E7.9 on this gate) "
          f"and {result['pbo_fold_level']:.3f} at the coarser fold level.")
        a("")

    # ── LOCK 2: per-fold coverage beside per-fold score ──
    a("## LOCK 2 — per-fold score BESIDE per-fold contract coverage")
    a("")
    a("Coverage is **not uniform across the window** — the earlier folds lean harder on imputation. "
      "A lift that lives only in the thin folds is an imputation artifact, not a feature effect.")
    a("")
    a(f"| fold | eval season | eval rows | contract coverage | contract cols STRUCTURALLY ABSENT | incumbent {m} | leader {m} | leader − incumbent |")
    a("|---:|---:|---:|---:|---|---:|---:|---:|")
    for r in result.get("per_fold") or []:
        cov = r.get("contract_coverage")
        absent = r.get("structurally_absent") or []
        cov_s = f"{cov:.3f}" if cov is not None else "n/a"
        absent_s = ", ".join(f"`{c}`" for c in absent) if absent else "—"
        a(f"| {r['fold']} | {r['eval_season']} | {r['eval_rows']:,} | {cov_s} | {absent_s} | "
          f"{r['incumbent']:.4f} | {r['leader']:.4f} | {r['leader_minus_incumbent']:+.4f} |")
    a("")
    a("(`leader − incumbent` is NEGATIVE when the leader is better — the metric is lower-is-better.)")
    a("")
    absent_any = sorted({c for r in (result.get("per_fold") or [])
                         for c in (r.get("structurally_absent") or [])})
    if absent_any:
        a(f"🚩 **A CONTRACT COLUMN IS ENTIRELY MISSING IN AT LEAST ONE EVAL FOLD: "
          f"{', '.join(f'`{c}`' for c in absent_any)}.** Those folds do NOT evaluate the served "
          f"contract — the absent column imputes to a constant, so they score a structurally "
          f"SMALLER model. A pooled coverage mean cannot express this, which is why the columns are "
          f"named. ⚠️ Read any cross-fold difference in the light of this before attributing it to "
          f"the `plus_eb` feature block: the early folds differ from the late ones in WHICH "
          f"contract they are testing, not only in how noisy it is.")
        a("")

    # ── LOCK 5: which of the seven null states ──
    nc = result.get("null_classification")
    if nc:
        a("## ⭐ Which of the seven null states is this? (MH2 §0.5.4 — computed, not asserted)")
        a("")
        a(f"**`{nc['state']}`** — {nc['reason']}")
        a("")
        det = nc.get("detail") or {}
        if det.get("min_detectable_crps_lift") is not None:
            a(f"- Smallest {m} lift this design could have CERTIFIED (DSR gate, measured "
              f"dispersion): **{det['min_detectable_crps_lift']:.5f}** — required per-fold Sharpe "
              f"{det['required_per_fold_sr_at_measured_V']} × fold-skill SD {det['fold_skill_sd']}.")
            a(f"- Pre-registered practically-meaningful lift: **"
              f"{det['pre_registered_meaningful_crps_lift']}** (`NOISE_FLOOR['crps']`, a design "
              f"constant fixed long before this story — not reverse-engineered from the answer).")
            a("")
        a(f"- Re-test trigger: {nc.get('retest_trigger') or '**none — do NOT re-test.**'}")
        if nc.get("max_field_size"):
            a(f"- Largest field in which this effect would still clear DSR: "
              f"**{nc['max_field_size']} arms**.")
        a("")
        a("⚠️ The MDE is stated against the gate that actually BINDS here (margin + PBO + DSR + "
          "calibration). This harness carries no fold-consistency clause and no BH family, so a "
          "consistency+BH power figure would describe a rule it does not run.")
        a("")


def _write_bakeoff_report(result: dict, table: pd.DataFrame) -> None:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(result)
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))

    m = result["metric"]
    w = result.get("window") or {}
    mh21 = bool(w.get("is_mh2_1"))
    lines: list[str] = []
    a = lines.append
    if mh21:
        a(f"# MLB MH2.1 — WIDE-WINDOW retrain bake-off: {result['target']} ({result['tier']})")
        a("")
        a(f"> Re-run of E7.9's retrain on the **{w['seasons'][0]}–{w['seasons'][-1]}** window "
          f"({w['n_seasons']} seasons ⇒ **{result['n_folds']} folds**) with a **pre-registered "
          f"{result['n_arms']}-arm family**, under the FIXED DSR convention. "
          f"Arm of the design: **{w['arm']}**.")
    else:
        a(f"# MLB Edge-{STORY} — retrain bake-off: {result['target']} ({result['tier']})")
    a("")
    if result["smoke"]:
        a("> ⚠️ **SMOKE RUN** — rows/estimators/arms capped. A harness check, NOT a result.")
        a("")
    a(f"> ⚠️ **Not an edge claim.** `best_alpha = {BEST_ALPHA}`. This decides whether the "
      "MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; "
      "it says nothing about win rate or ROI. A CRPS improvement on `total_runs` is a "
      "PRICING/CALIBRATION improvement, never an edge, a win rate, or an ROI.")
    a("")
    if mh21:
        a(f"> {result.get('point_in_time_caveat', MH21_POINT_IN_TIME_CAVEAT)}")
        a("")
    a(f"**VERDICT: `{result['verdict']}`**")
    a("")
    a(f"- Honest metric **{m}** (lower = better) · {result['n_arms']} arms × "
      f"{result['n_folds']} purged/embargoed folds · {result['n_rows']:,} rows · seed {result['seed']}")
    a(f"- Incumbent arm `{result['incumbent_arm']}` = {result['incumbent_metric']:.4f}")
    a(f"- Leader `{result['leader_arm']}` = {result['leader_metric']:.4f} "
      f"(margin {result['margin_vs_incumbent']:+.4f}; noise floor {result['noise_floor']})")
    a(f"- PBO {result['pbo']:.3f} (gate < {PBO_MAX}) · DSR {result['dsr']:.3f} "
      f"(gate ≥ {DSR_MIN_CONF})")
    a(f"- Oracle-floor sanity (E2.1-r): oracle {m} = {result['oracle_metric']:.6f}; no candidate "
      "beat it ✅")
    a("")

    if mh21:
        _append_mh21_sections(a, result, m)

    a("## ⚠️ Margin attribution — the margin is NOT purely a feature effect")
    a("")
    md = result.get("margin_decomposition") or {}
    if md.get("available"):
        a(f"The gate compares leader-arm vs incumbent-arm, where an arm is (contract variant × "
          f"learner class). That is the right PROMOTION question, but it CONFLATES the feature "
          f"effect with a learner-class swap. Split against `{md['same_learner_reference_arm']}` "
          f"(the incumbent contract under the LEADER's learner):")
        a("")
        a("| component | Δ {m} | share of margin |".format(m=m))
        a("|---|---:|---:|")
        share = md.get("learner_share")
        a(f"| **learner swap** (incumbent learner → `{result['leader_arm'].partition('::')[2]}`) | "
          f"{md['learner_swap']:+.4f} | {share:.0%} |" if share is not None
          else f"| **learner swap** | {md['learner_swap']:+.4f} | — |")
        a(f"| **contract** (added features) | {md['contract']:+.4f} | "
          + (f"{1 - share:.0%} |" if share is not None else "— |"))
        a(f"| **total reported margin** | {md['total']:+.4f} | 100% |")
        a("")
        if share is not None and share >= 0.5:
            a(f"🚩 **{share:.0%} of this margin is the LEARNER SWAP, not the features.** Do not read "
              f"`{md['total']:+.4f}` as what the added columns bought — that figure is "
              f"`{md['contract']:+.4f}`.")
    else:
        a("_Not available — the leader's learner has no incumbent-contract counterpart in this grid._")
    a("")
    a("### Feature effect holding the LEARNER FIXED (+ = variant better than the incumbent contract)")
    a("")
    ve = result.get("variant_effect_by_learner") or []
    if ve:
        a(f"| learner | incumbent {m} | plus_gb | plus_eb | plus_both |")
        a("|---|---:|---:|---:|---:|")
        for r in ve:
            def _f(x):
                return f"{x:+.4f}" if isinstance(x, (int, float)) else "n/a"
            a(f"| {r['learner']} | {r['incumbent']:.4f} | {_f(r.get('plus_gb'))} | "
              f"{_f(r.get('plus_eb'))} | {_f(r.get('plus_both'))} |")
        a("")
        a("This table — not the headline margin — is where a FEATURE effect can be read.")
    a("")
    a("## Pre-registered gates")
    a("")
    tol = result.get("calibration_tolerance")
    amend = result.get("calibration_amendment")
    a("| gate | result |")
    a("|---|---|")
    for k, v in result["gates"].items():
        a(f"| `{k}` | {'✅ pass' if v else '❌ fail'} |")
    a("")
    if tol is None:
        a(f"⚠️ Scored under the ORIGINAL `calibration_not_degraded` tolerance of "
          f"`{CALIBRATION_AMENDMENT_LEGACY_TOL:g}`, i.e. BEFORE pre-registration amendment #1 "
          f"({CALIBRATION_AMENDMENT_DATE}). That tolerance is tight enough to trip on ROUNDING; where "
          f"this gate failed, check whether the PIT-KS difference is material before reading it as a "
          f"real calibration regression. **This recorded verdict is left exactly as scored** — the "
          f"amendment is forward-dated and does not retro-apply.")
    else:
        a(f"Calibration tolerance in effect: `{tol:.5f}` (pre-registration amendment #1, "
          f"{amend} — max of a {CALIBRATION_TOLERANCE_ABS:g} absolute floor and "
          f"{CALIBRATION_TOLERANCE_REL:.0%} of the incumbent's PIT-KS).")
        if result.get("calibration_would_fail_pre_amendment"):
            a("")
            a("🚩 **This run's `calibration_not_degraded` PASS depends on amendment #1** — it would "
              "have FAILED under the original 1e-9 tolerance. Stated explicitly, per the amendment's "
              "own disclosure requirement.")
    a("")
    if result["verdict"] == "INCUMBENT_STANDS":
        a("**Reading the null honestly.** No arm clears every gate, so the served champion is "
          "unchanged and there is NO prediction backfill to run (E7.9 step 7 is conditional on a "
          "promotion). Per the E2.1-r note: if the top arms are TIED within the noise floor, a high "
          "PBO is the NULL — 'which tied arm wins is noise' — not evidence of overfitting. Check the "
          "spread in the table below before reading PBO as a failure.")
    else:
        a("**A challenger cleared every gate.** Promote per the model-promotion runbook, then run "
          "E7.9 step 7 (the historical prediction backfill) — labelled a BACKTEST, never a "
          "real-time record.")
    a("")
    a("## Contract variants")
    a("")
    a("| variant | features | added vs incumbent |")
    a("|---|---:|---|")
    for k, v in result["variants"].items():
        added = ", ".join(f"`{c}`" for c in v["added_vs_incumbent"]) or "— (the bar)"
        a(f"| `{k}` | {v['n_features']} | {added} |")
    if result["dropped_variants"]:
        a("")
        a(f"Dropped (added columns absent from the matrix): {result['dropped_variants']}. A dropped "
          "variant is NOT silently folded onto the incumbent — that would double-count an arm and "
          "understate the multiple-testing burden.")
    a("")
    a("## Full arm table")
    a("")
    a(f"| arm | variant | learner | {m} | PIT-KS | n |")
    a("|---|---|---|---:|---:|---:|")
    for r in table.to_dict("records"):
        a(f"| `{r['arm']}` | {r['variant']} | {r['learner']} | {r[f'{m}_mean']:.4f} | "
          f"{r['pit_ks']:.4f} | {r['n']:,} |")
    a("")
    (_ABL / f"{stem}.md").write_text("\n".join(lines) + "\n")


def rewrite_reports() -> list[str]:
    """Re-emit every recorded bake-off report from its stored JSON — no re-fitting.

    Q1 (PM-adjudicated 2026-07-29): the recorded reports credit a mostly-learner-swap margin to a
    features study. The stored `table` already holds every arm's score, so the decomposition is
    derivable WITHOUT refitting anything.

    ⚠️ VERDICTS ARE NOT RECOMPUTED. Gates, PBO, DSR and the verdict are re-emitted verbatim from the
    stored result; only the attribution sections are added. In particular the forward-dated
    calibration amendment does NOT retro-apply — a run stored without a `calibration_tolerance` key
    was scored under the original 1e-9 tolerance and the report says so.
    """
    written = []
    for path in sorted(_JSON_DIR.glob("e7_9_retrain_*.json")):
        result = json.loads(path.read_text())
        rows = result.get("table") or []
        if not rows:
            continue
        metric = result["metric"]
        result.setdefault("margin_decomposition", margin_decomposition(
            rows, result["incumbent_arm"], result["leader_arm"], metric))
        result.setdefault("variant_effect_by_learner", variant_effect_by_learner(rows, metric))
        path.write_text(json.dumps(result, indent=2, default=float))
        _write_bakeoff_report(result, pd.DataFrame(rows))
        written.append(f"{result['target']}/{result['tier']}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{STORY} train/serve consistency: audit + retrain bake-off")
    ap.add_argument("--audit", action="store_true", help="Exposure audit only (fast, no fitting).")
    ap.add_argument("--bakeoff", action="store_true", help="Run the pre-registered retrain bake-off.")
    ap.add_argument("--target", choices=["total_runs", "run_diff"], default="total_runs")
    ap.add_argument("--tier", choices=["post_lineup", "pre_lineup"], default="post_lineup")
    ap.add_argument("--min-season", type=int, default=2021, help="Audit: earliest season to scope.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Re-pull the training matrix (REQUIRED after the E7.9 dbt join lands, or "
                         "the cached parquet has no eb_gb_pct columns).")
    ap.add_argument("--s3", action="store_true",
                    help="Read the training matrix from the S3 lakehouse via DuckDB instead of "
                         "Snowflake (repo doctrine; also the only source carrying eb_gb_pct before "
                         "the Snowflake external table is recreated). Pair with --refresh-cache.")
    ap.add_argument("--smoke", action="store_true", help="Cap rows/estimators for a harness check.")
    # ── MH2.1: the pre-registered wide window + family ──
    ap.add_argument("--min-year", type=int, default=2021,
                    help="Earliest season in the training matrix (the WINDOW). E7.9 ran 2021; "
                         f"MH2.1's pre-registered window is {MH21_MIN_YEAR}. A non-2021 value gets "
                         "its own training-matrix cache key.")
    ap.add_argument("--exclude-seasons", type=int, nargs="*", default=[],
                    help="Season(s) dropped from BOTH train and eval. MH2.1's declared Lock-1 "
                         f"sensitivity is `--exclude-seasons {MH21_SENSITIVITY_EXCLUDE[0]}`.")
    ap.add_argument("--family", choices=["full", "mh2_1"], default="full",
                    help="`full` = E7.9's variant×learner grid. `mh2_1` = the pre-registered "
                         f"{len(MH21_VARIANTS) * len(MH21_LEARNERS)}-arm family "
                         f"{list(MH21_VARIANTS)} × {list(MH21_LEARNERS)}.")
    ap.add_argument("--mh2-1", action="store_true",
                    help="Shorthand for MH2.1's PRIMARY design: "
                         f"--min-year {MH21_MIN_YEAR} --family mh2_1. Add "
                         f"`--exclude-seasons {MH21_SENSITIVITY_EXCLUDE[0]}` for the declared "
                         "sensitivity arm.")
    ap.add_argument("--rewrite-reports", action="store_true",
                    help="Re-emit every recorded report from its stored JSON (adds the Q1 margin "
                         "attribution). Recomputes NOTHING — verdicts/gates are re-emitted verbatim.")
    args = ap.parse_args()
    if args.mh2_1:
        args.min_year, args.family = MH21_MIN_YEAR, "mh2_1"

    if args.rewrite_reports:
        done = rewrite_reports()
        print(f"[{STORY}] rewrote {len(done)} report(s): {', '.join(done) or 'none found'}")
        if not (args.audit or args.bakeoff):
            return

    if not (args.audit or args.bakeoff):
        ap.error("pass --audit and/or --bakeoff (or --rewrite-reports)")
    if args.audit:
        res = run_audit(args.min_season)
        skew = res["contracts_with_train_serve_skew"]
        print(f"\n[{STORY}] served contracts WITH train/serve skew: {skew or 'NONE'}")
        print(f"[{STORY}] report → {_ABL / 'e7_9_train_serve_audit.md'}")
    if args.bakeoff:
        run_retrain_bakeoff(args.target, args.tier, seed=args.seed, smoke=args.smoke,
                            refresh_cache=args.refresh_cache, embargo_days=args.embargo_days,
                            s3=args.s3, min_year=args.min_year,
                            exclude_seasons=tuple(args.exclude_seasons or ()),
                            family=args.family)


if __name__ == "__main__":
    main()

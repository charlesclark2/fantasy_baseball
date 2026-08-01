"""E7.12 SLICE 5 — PROSPECT AGING CURVES: the age × minor-line INTERACTION, not an age main effect.

Run (LAPTOP, several minutes per side — hand to the operator, do not run in-session):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice5 \
        --player-type batter
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice5 \
        --player-type pitcher

🛑 READ FIRST: `age` IS ALREADY IN THE INCUMBENT
---------------------------------------------------------------------------------------------------
`PartialPoolProjector._design` has carried `Block("fixed", ("intercept", "minor", "age"))` since E7.3.
**This slice is not "add age."** It asks whether age changes the SLOPE of the translation — whether a
20-year-old and a 25-year-old posting the same Double-A line should have that line read differently —
plus whether the age main effect is mis-specified as LINEAR. A session that adds an age main effect
here would measure nothing and file a null meaning only "I re-added an existing feature."

THE TWO CHANNELS, AND WHY THEY ARE SEPARATE ARMS (NF-D15 g′)
---------------------------------------------------------------------------------------------------
A bucketed age term can enter through two channels and they support DIFFERENT claims:
  • **SLOPE** (`Y1`/`Y2`) — per-bucket deviations on the minor-rate coefficient. This is the only one
    that can express *"youth changes how much the line MEANS"*, the actual aging-curve hypothesis.
  • **INTERCEPT** (`Y3`/`Y3b`) — per-bucket level shifts. This can only say *"the linear age main
    effect is the wrong shape"*, which is a real and useful finding but a different one.
Both are pre-registered as ladder arms, and `Y3b` is simultaneously the **matched foil** for `Y2`:
identical bucketing, identical everything, the claimed channel removed. If the slope arm wins and the
intercept-only arm does not, the interaction is attributable. If both win by the same margin, the
honest report is "age is mis-specified as linear", NOT "the aging curve is real" — a win is not
self-attributing, and the paired delta is what separates the two.

⚠️ CONFOUNDED WITH S2 BY CONSTRUCTION — HANDLED, NOT ASSUMED AWAY
---------------------------------------------------------------------------------------------------
A young player who did NOT develop never gets promoted, so he is never in this training set. **"Young
players' lines translate better" is precisely the claim survivorship bias manufactures out of
nothing.** The story prompt allows either (i) carrying S2's correction or (ii) declaring the estimate
an upper bound. This runner does **BOTH, as a matched pair**: `V_ipw_Y0` / `V_ipw_Y2` re-run the
baseline and the interaction under S2's `T1b_ipw_odds` inverse-odds weights, which re-weight the
graduate sample toward the UN-PROMOTED population the board is actually served on. The
`survivorship_read` compares the age lift with and without that re-weighting:
  • lift SURVIVES re-weighting ⇒ not an artifact of who got promoted;
  • lift COLLAPSES ⇒ the age effect was selection wearing an aging-curve costume, and the unweighted
    number is an upper bound — which is the outcome the prompt warns is most likely.
Either way the headline number stays the UNWEIGHTED one (S2's emission is deferred by PM ruling, so
the shipped configuration is still slice 1's) and the re-weighted pair is a stated sensitivity, never
folded into the margin.

`best_alpha = 0`. This is a projection, not an edge claim.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.age_context import (
    AGE_BUCKET,
    REL_BUCKET,
    REL_COL,
    attach_age_features,
    bucket_coverage,
    level_median_age,
    permute_bucket,
)
from betting_ml.scripts.milb_mle.milb_mle import (
    GBMProjector,
    PartialPoolProjector,
    build_target,
)
from betting_ml.scripts.milb_mle.park_context import apply_context
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
    SIDES,
    SideConfig,
    _paired_p,
    bh_fdr,
    deflation_report,
    paired_anchor,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import (
    S2Arm,
    attach_arm_columns,
    propensity_for_fold,
    shipped_spec,
)

log = logging.getLogger("e7_12_slice5")

_KEYS = ["player_id", "level"]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

_PLACEBO_BUCKET = "_s5_placebo_bucket"
_INTERACT_COL = "_s5_age_x_minor"

# The S2 arm the sensitivity pair borrows. Named rather than reconstructed so that if S2's winner is
# ever re-labelled, this raises on the lookup instead of silently testing a different correction.
_S2_SENSITIVITY_ARM = S2Arm(
    "T1b_ipw_odds", "odds", None, "sensitivity",
    "inverse-odds weights (1-p)/p — re-weights graduates toward the UN-PROMOTED population")


@dataclass(frozen=True)
class S5Arm:
    label: str
    kind: str                      # "ladder" | "anchor" | "reference" | "sensitivity"
    note: str
    bucket_col: str | None = None
    bucket_slope: bool = False
    bucket_intercept: bool = False
    linear_interaction: bool = False   # a single continuous age_z × minor_z fixed column
    permute: bool = False              # permute the BUCKET (never `age` — see age_context)
    ipw: bool = False                  # carry S2's inverse-odds weights
    gbm: bool = False
    gbm_use_age: bool = True

    @property
    def selectable(self) -> bool:
        """Anchors and reference arms are SCORED and counted toward deflation, never selected.

        The GBM arms are references rather than candidates on purpose: E7.9 measured that 54-77% of
        every apparent margin in this program was the LEARNER SWAP, not the mechanism. Letting a GBM
        win here would report a learner change as an aging-curve finding.
        """
        return self.kind in ("ladder", "sensitivity")


S5_LADDER: tuple[S5Arm, ...] = (
    S5Arm("Y0_shipped", "ladder",
          "the SHIPPED slice-1 configuration for this metric — the real incumbent, age main effect "
          "and all"),
    S5Arm("Y1_age_slope", "ladder",
          "⭐ (a) THE INTERACTION on ABSOLUTE age: per-age-bucket deviations on the minor-rate SLOPE, "
          "a penalized block with its own tau^2 (the `level_slope` pattern). Expresses 'youth changes "
          "how much the line means'",
          bucket_col=AGE_BUCKET, bucket_slope=True),
    S5Arm("Y2_rel_slope", "ladder",
          "⭐ (b) THE SAME INTERACTION on AGE-RELATIVE-TO-LEVEL — the honest form, since a 22-year-old "
          "is old for Single-A and young for Triple-A. Better-balanced buckets than absolute age",
          bucket_col=REL_BUCKET, bucket_slope=True),
    S5Arm("Y3_age_growth_prior", "ladder",
          "(c) THE AGE-BUCKETED GROWTH PRIOR on absolute age: per-bucket INTERCEPT deviations. Can "
          "only say the linear age main effect is the wrong shape — it cannot express an interaction",
          bucket_col=AGE_BUCKET, bucket_intercept=True),
    S5Arm("Y3b_rel_growth_prior", "ladder",
          "🎏 THE MATCHED FOIL for Y2 as well as a ladder arm in its own right: identical bucketing, "
          "the INTERCEPT channel only. If this matches Y2, the finding is 'age is mis-specified as "
          "linear', NOT 'the aging curve is real' (NF-D15 g′ — a win is not self-attributing)",
          bucket_col=REL_BUCKET, bucket_intercept=True),
    S5Arm("Y4_rel_slope_prior", "ladder",
          "both channels together on the honest form — registered because a growth prior and a slope "
          "interaction are different mechanisms and one does not subsume the other",
          bucket_col=REL_BUCKET, bucket_slope=True, bucket_intercept=True),
    S5Arm("Y5_linear_interaction", "ladder",
          "the SIMPLEST parametric form: one continuous age_z × minor_z coefficient in the unpenalized "
          "fixed block. The parsimony foil — if the bucketing wins only because it has more "
          "parameters, this arm exposes it",
          linear_interaction=True),
    # ── anchors: must LOSE ──
    S5Arm("A_bucket_placebo", "anchor",
          "DEGENERATE FOIL — Y2's exact structure with the BUCKET ASSIGNMENT permuted within "
          "(level, debut_cohort). The real `age` main effect is left untouched, so this isolates the "
          "interaction channel rather than corrupting the baseline. Must lose",
          bucket_col=_PLACEBO_BUCKET, bucket_slope=True, permute=True),
    # ── reference: the direct-learned ceiling probe (§0.5), scored, never selected ──
    S5Arm("R_gbm_age", "reference",
          "CEILING PROBE — a gradient-boosted learner that sees age and the line and is free to learn "
          "ANY interaction between them, prescribed shape or not",
          gbm=True, gbm_use_age=True),
    S5Arm("R_gbm_noage", "reference",
          "🎏 its MATCHED PAIR with age removed. The PAIRED gap R_gbm_noage − R_gbm_age is an upper "
          "bound on how much age structure is exploitable here AT ALL — a bound that does not depend "
          "on our bucketing being the right shape. A ~zero gap means no learner can find an age "
          "effect, which is a far stronger null than 'our arm missed its gate'",
          gbm=True, gbm_use_age=False),
    # ── sensitivity: the S2 confound pair, counted toward deflation, never the headline ──
    S5Arm("V_ipw_Y0", "sensitivity",
          "the shipped baseline re-weighted by S2's inverse-odds propensity — the matched BASE for the "
          "survivorship read (comparing a weighted arm to an unweighted baseline would confound the "
          "re-weighting with the mechanism)",
          ipw=True),
    S5Arm("V_ipw_Y2", "sensitivity",
          "⚠️ Y2 under the same re-weighting. (V_ipw_Y0 − V_ipw_Y2) vs (Y0 − Y2) is the direct test of "
          "whether the age effect is real or is survivorship in an aging-curve costume",
          bucket_col=REL_BUCKET, bucket_slope=True, ipw=True),
)

# How much of the unweighted age lift must survive S2 re-weighting before the effect is called robust
# to selection. 0.5 = "at least half the lift remains"; below that the unweighted number is reported
# as an UPPER BOUND. Pre-registered here rather than chosen after seeing the ratio.
SURVIVORSHIP_RETENTION_MIN = 0.50

# The fold-win-rate gate, shared with slices 1/2/4. Named here (rather than inlined) because S5 adds
# two conditions ON TOP of it and both need the same threshold.
FOLD_WIN_GATE = 0.60


def placebo_fold_win_rate(leaderboard: pd.DataFrame) -> float:
    """The permuted-bucket placebo's own fold-win rate against the incumbent.

    Returns 0.0 when the placebo did not run, so an ABSENT placebo can never trip the disqualifier —
    a missing anchor must fail open on the anchor and be caught by the `available: False` report,
    not silently DROP every arm (NF1.7 lesson 1, applied in the direction that matters here).
    """
    r = leaderboard.loc[leaderboard["arm"] == "A_bucket_placebo", "fold_win_rate"]
    return float(r.iloc[0]) if len(r) and np.isfinite(r.iloc[0]) else 0.0


def by_label(arms: tuple[S5Arm, ...] = S5_LADDER) -> dict[str, S5Arm]:
    return {a.label: a for a in arms}


@dataclass
class S5Result:
    metric: str
    prior_scale: float
    shipped_rung: str
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    coverage: pd.DataFrame
    deflation: dict
    anchors: dict
    survivorship: dict
    verdict: str
    winner: str
    reasons: list[str] = field(default_factory=list)


def _fold_frame(lab: pd.DataFrame, year: int, rng: np.random.Generator) -> pd.DataFrame:
    """The labelled frame with age features derived from THIS fold's training rows only.

    The level medians are a population aggregate, so deriving them over the whole frame would let the
    held-out cohort's own ages set the origin its `age_vs_level` is measured from. Cheap to recompute,
    so there is no reason to accept even that small a leak.
    """
    train = lab[lab["debut_cohort"] < year]
    out = attach_age_features(lab, level_median_age(train))
    out[_PLACEBO_BUCKET] = permute_bucket(out, REL_BUCKET, rng)
    return out


def _build_arm(frame: pd.DataFrame, arm: S5Arm, scale: float, shipped_weight: str | None,
               prop: pd.DataFrame | None, marginal: float, rng: np.random.Generator
               ) -> tuple[pd.DataFrame, object]:
    """Return `(frame, unfitted_model)` for one arm."""
    out = frame
    weight_col = shipped_weight
    if arm.ipw:
        if prop is None:
            raise ValueError(f"{arm.label} needs a propensity but none was available for this fold")
        out, weight_col, _ = attach_arm_columns(out, _S2_SENSITIVITY_ARM, prop, marginal,
                                                shipped_weight, rng)
    if arm.gbm:
        # the E7.3 GBM grid's middle configuration, held fixed across both reference arms so the pair
        # differs ONLY in whether age is visible
        return out, GBMProjector(300, 2, 0.03, use_statcast=False, use_age=arm.gbm_use_age)

    extra: tuple[str, ...] = ()
    if arm.linear_interaction:
        out = out.copy()
        # standardization happens inside the projector's `_Scaler`; this column is the raw product of
        # the two quantities the interaction is between, formed on the frame so both fit and predict
        # see the identical definition
        age = pd.to_numeric(out["age"], errors="coerce")
        out[_INTERACT_COL] = age * pd.to_numeric(out["feat"], errors="coerce")
        extra = (_INTERACT_COL,)
    return out, PartialPoolProjector(
        prior_scale=scale, weight_col=weight_col, extra_cols=extra,
        bucket_col=arm.bucket_col, bucket_slope=arm.bucket_slope,
        bucket_intercept=arm.bucket_intercept)


def run_s5_ladder(pairs: pd.DataFrame, park_ctx: pd.DataFrame | None, metric: str,
                  side: SideConfig, arms: tuple[S5Arm, ...] = S5_LADDER,
                  seed: int = 5,
                  propensity_cache: dict | None = None) -> S5Result:
    """Score every S5 arm under the E7.3 fold structure, learner held fixed for every selectable arm."""
    base_spec = shipped_spec(side, metric)
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    rng = np.random.default_rng(seed)
    cache = propensity_cache if propensity_cache is not None else {}

    adj = apply_context(pairs, park_ctx, base_spec, metric, tuple(_KEYS))
    lab = build_target(adj, cfg)
    lab = lab[lab["has_target"]].reset_index(drop=True)
    if "age" not in lab.columns:
        raise KeyError("the labelled frame carries no `age` column — S5 cannot run")

    cohorts = sorted(int(y) for y in lab["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"need >=2 evaluable debut cohorts; got {fold_cohorts}")

    labels = [a.label for a in arms]
    mae = pd.DataFrame(index=fold_cohorts, columns=labels, dtype=float)
    notes: list[str] = []
    coverage: pd.DataFrame | None = None

    for year in fold_cohorts:
        frame = _fold_frame(lab, year, rng)
        if coverage is None:
            coverage = bucket_coverage(frame)
        # the propensity depends only on (pairs, cutoff) — NOT on the metric — so it is memoized across
        # every metric in the run. S2 refit it per metric and again per stratum read; that was ~2x the
        # hazard fits this needs.
        if year not in cache:
            try:
                cache[year] = propensity_for_fold(pairs, cutoff_season=year)
            except Exception as e:  # noqa: BLE001 — a thin early fold must not kill the sweep
                cache[year] = None
                notes.append(f"fold {year}: propensity unavailable ({type(e).__name__}: {e})")
        pf = cache[year]

        for arm in arms:
            if arm.ipw and pf is None:
                continue
            try:
                fr, mdl = _build_arm(frame, arm, scale, base_spec.weight_col,
                                     pf.propensity if pf else None,
                                     pf.marginal if pf else 0.5, rng)
                train, test = fr[fr["debut_cohort"] < year], fr[fr["debut_cohort"] == year]
                if train.empty or test.empty:
                    continue
                mdl.fit(train)
                yhat, _ = mdl.predict(test)
                mae.loc[year, arm.label] = float(
                    np.mean(np.abs(test["target"].to_numpy(float) - yhat)))
            except Exception as e:  # noqa: BLE001
                notes.append(f"fold {year} arm {arm.label}: {type(e).__name__}: {e}")

    if mae.notna().to_numpy().sum() == 0:
        raise RuntimeError(f"[{metric}] no fold produced a scored arm — {notes}")

    base = mae["Y0_shipped"]
    board = []
    for arm in arms:
        col = mae[arm.label]
        # a SENSITIVITY arm is scored against its own re-weighted base, not against the unweighted
        # incumbent — otherwise the IPW re-weighting and the age mechanism are confounded in one number
        ref = mae["V_ipw_Y0"] if (arm.kind == "sensitivity" and "V_ipw_Y0" in mae) else base
        d = (ref - col).to_numpy(float)
        dfin = d[np.isfinite(d)]
        board.append({
            "arm": arm.label, "kind": arm.kind, "selectable": arm.selectable,
            "oos_mae": float(col.mean(skipna=True)),
            "reference": "V_ipw_Y0" if arm.kind == "sensitivity" else "Y0_shipped",
            "pct_lift_vs_ref": (100.0 * float(np.mean(dfin)) / float(ref.mean(skipna=True))
                                if len(dfin) and ref.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(dfin > 0)) if len(dfin) else np.nan,
            "p_one_sided": _paired_p(d),
            "note": arm.note,
        })
    leaderboard = pd.DataFrame(board).sort_values("oos_mae").reset_index(drop=True)

    eligible = [a.label for a in arms if a.selectable]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)

    anchors = s5_anchors(mae, leaderboard)
    surv = survivorship_read(mae)
    verdict, winner, reasons = s5_verdict(leaderboard, anchors, surv, notes)
    return S5Result(metric=metric, prior_scale=scale, shipped_rung=base_spec.label,
                    leaderboard=leaderboard, mae_by_fold=mae, fold_cohorts=fold_cohorts,
                    coverage=coverage if coverage is not None else pd.DataFrame(),
                    deflation=defl, anchors=anchors, survivorship=surv,
                    verdict=verdict, winner=winner, reasons=reasons)


def s5_anchors(mae: pd.DataFrame, leaderboard: pd.DataFrame) -> dict:
    def m_of(lbl: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == lbl, "oos_mae"]
        return float(r.iloc[0]) if len(r) else float("nan")

    out = {
        "placebo_vs_rel_slope": paired_anchor(mae, "A_bucket_placebo", "Y2_rel_slope"),
        # 🎏 THE CHANNEL FOIL. Not "does something age-shaped help" but "does the SLOPE channel earn
        # anything the INTERCEPT channel does not" — the paired delta NF-D15 g′ requires before a win
        # may be attributed to the interaction rather than to a mis-specified main effect.
        "intercept_only_vs_rel_slope": paired_anchor(mae, "Y3b_rel_growth_prior", "Y2_rel_slope"),
        "linear_vs_bucketed": paired_anchor(mae, "Y5_linear_interaction", "Y2_rel_slope"),
        "rel_slope_mae": m_of("Y2_rel_slope"),
        "placebo_mae": m_of("A_bucket_placebo"),
        "intercept_only_mae": m_of("Y3b_rel_growth_prior"),
    }
    # ⭐ THE CEILING PROBE, read as a PAIRED gap. A free learner denied age vs the same learner given
    # age: if removing age costs a tree ensemble essentially nothing, then no age structure of ANY
    # shape is exploitable on this substrate, and a pooled-arm null is corroborated rather than merely
    # unfalsified. A LARGE gap the pooled arms failed to capture would be the opposite finding — that
    # our prescribed bucketing is the wrong shape, not that age is inert.
    if {"R_gbm_age", "R_gbm_noage"}.issubset(mae.columns):
        g = (mae["R_gbm_noage"] - mae["R_gbm_age"]).to_numpy(float)
        g = g[np.isfinite(g)]
        base = float(mae["R_gbm_age"].mean(skipna=True))
        out["free_learner_age_value"] = {
            "mean_mae_gap": float(np.mean(g)) if len(g) else None,
            "pct_of_gbm_mae": (round(100.0 * float(np.mean(g)) / base, 4)
                               if len(g) and base else None),
            "folds_age_helps": int((g > 0).sum()), "n_folds": int(len(g)),
            "note": "positive ⇒ removing age HURTS the free learner ⇒ age structure exists to find",
        }
    return out


def survivorship_read(mae: pd.DataFrame) -> dict:
    """⚠️ THE S2 CONFOUND, MEASURED — does the age lift survive re-weighting toward the un-promoted?

    A young player who never developed was never promoted and is therefore absent from every training
    row here. That absence alone can manufacture "young lines translate better". The comparison is
    strictly PAIRED: the unweighted lift (Y0 − Y2) against the re-weighted lift (V_ipw_Y0 − V_ipw_Y2),
    so the IPW re-weighting is present on BOTH sides of the second difference and cannot be mistaken
    for the mechanism.
    """
    need = {"Y0_shipped", "Y2_rel_slope", "V_ipw_Y0", "V_ipw_Y2"}
    if not need.issubset(mae.columns):
        return {"available": False,
                "note": "the IPW sensitivity pair did not run — no survivorship read is possible, "
                        "and the age estimate must be reported as an UPPER BOUND"}
    raw = (mae["Y0_shipped"] - mae["Y2_rel_slope"]).to_numpy(float)
    wgt = (mae["V_ipw_Y0"] - mae["V_ipw_Y2"]).to_numpy(float)
    ok = np.isfinite(raw) & np.isfinite(wgt)
    raw, wgt = raw[ok], wgt[ok]
    if len(raw) < 3:
        return {"available": True, "n_folds": int(len(raw)),
                "note": "too few paired folds to read — reported, not enforced"}
    r_mean, w_mean = float(np.mean(raw)), float(np.mean(wgt))
    # retention is only meaningful when the unweighted lift is positive; a negative baseline lift makes
    # the ratio uninterpretable (dividing two numbers that are both the wrong sign), so say so instead
    retention = (w_mean / r_mean) if r_mean > 1e-12 else None
    return {
        "available": True, "n_folds": int(len(raw)),
        "unweighted_lift": r_mean, "reweighted_lift": w_mean,
        "retention": (round(float(retention), 4) if retention is not None else None),
        "survives_reweighting": (bool(retention is not None
                                      and retention >= SURVIVORSHIP_RETENTION_MIN)),
        "retention_floor": SURVIVORSHIP_RETENTION_MIN,
        "reading": (
            "no positive unweighted lift to retain — the survivorship question does not arise"
            if retention is None else
            "the age lift SURVIVES re-weighting toward the un-promoted population ⇒ it is not merely "
            "an artifact of who got promoted"
            if retention >= SURVIVORSHIP_RETENTION_MIN else
            "the age lift COLLAPSES under re-weighting ⇒ it is substantially selection, and the "
            "unweighted number is an UPPER BOUND, not an estimate"),
    }


def s5_verdict(leaderboard: pd.DataFrame, anchors: dict, surv: dict,
               notes: list[str]) -> tuple[str, str, list[str]]:
    reasons = list(notes)
    sel = leaderboard[leaderboard["selectable"] & (leaderboard["arm"] != "Y0_shipped")]
    # a sensitivity arm is a diagnostic, never a shipping candidate — it is scored against a
    # re-weighted base whose emission path the PM has deferred
    sel = sel[sel["kind"] != "sensitivity"]
    sel = sel[sel["fold_win_rate"] >= FOLD_WIN_GATE]
    # 🪤 **A FOLD-COUNT GATE ALONE ADMITS AN ARM THAT IS WORSE ON AVERAGE** (found on the real run,
    # 2026-08-01: pitcher `k_pct` `Y2_rel_slope` won 7/11 folds while posting a HIGHER mean OOS MAE
    # than the incumbent and a mean lift of −0.20%). `fold_win_rate` counts narrow wins and ignores
    # their size, so an arm that wins seven folds by a hair and loses four by a mile clears it. BH-FDR
    # happens to rescue this case — a negative mean lift forces the one-sided p above 0.5, so the
    # downgrade is certain — but relying on a downstream correction to catch a mis-specified gate is
    # exactly the "detected, nobody notified" shape, and the pre-FDR log line still said ADD. Require
    # BOTH: wins often AND wins on average.
    sel = sel[sel["pct_lift_vs_ref"] > 0]
    if sel.empty:
        reasons.append(f"no age arm both beat the shipped configuration in >={FOLD_WIN_GATE:.0%} of "
                       f"cohorts AND improved mean OOS MAE")
        return "DROP", "Y0_shipped", reasons

    win = sel.sort_values("oos_mae").iloc[0]
    label = str(win["arm"])
    is_slope = label in ("Y1_age_slope", "Y2_rel_slope", "Y4_rel_slope_prior",
                         "Y5_linear_interaction")
    uses_buckets = label in ("Y1_age_slope", "Y2_rel_slope", "Y3_age_growth_prior",
                             "Y3b_rel_growth_prior", "Y4_rel_slope_prior")

    # ⭐ **A PLACEBO MUST BE TESTED AGAINST THE SELECTION RULE, NOT ONLY HEAD-TO-HEAD.** The paired
    # anchor below asks "does the placebo systematically beat the real arm" — a question that can
    # answer NO while the placebo still CLEARS THE VERY GATE the real arm is being selected on. That
    # happened on the real run: pitcher `k_pct`'s permuted-bucket placebo won **9/11** folds against
    # the incumbent (vs the real arm's 7/11) and posted a BETTER mean MAE than both, while the paired
    # test read p=0.33 "not violated". If a RANDOM bucket assignment passes the gate, the gate is not
    # measuring age — it is measuring the effect of adding any penalized 5-column block — and no
    # bucketed arm may be selected through it. Scoped to bucketed arms because that is what this
    # placebo foils; `Y5_linear_interaction` is a single continuous column and is not addressed by it.
    if uses_buckets and float(placebo_fold_win_rate(leaderboard)) >= FOLD_WIN_GATE:
        reasons.append(
            f"⛔ the PERMUTED-BUCKET placebo ITSELF cleared the {FOLD_WIN_GATE:.0%} fold gate "
            f"({placebo_fold_win_rate(leaderboard):.3f}) — a random bucket assignment passes the "
            f"selection rule, so the rule is measuring the addition of a penalized block, not age. "
            f"No bucketed arm can be selected through a gate its own placebo clears.")
        return "DROP", "Y0_shipped", reasons

    if anchors.get("placebo_vs_rel_slope", {}).get("violated"):
        reasons.append("⛔ the PERMUTED-BUCKET placebo matched or beat the real bucketing — the "
                       "movement is bucket dispersion, not age information")
        return "DROP", "Y0_shipped", reasons

    if is_slope and anchors.get("intercept_only_vs_rel_slope", {}).get("violated"):
        # NOT a DROP — something real won. But the CLAIM has to change, and saying so is the point of
        # registering the matched foil in the first place.
        reasons.append(
            "⚠️ ATTRIBUTION CHANGED: the INTERCEPT-only arm (identical bucketing, claimed channel "
            "removed) systematically matched or beat the slope arm. The finding is 'the age main "
            "effect is mis-specified as LINEAR', NOT 'youth changes how much the line means'. The "
            "aging-curve interaction is REFUTED as the mechanism even though an age arm won.")
        return "ADD_LEVEL_ONLY", "Y3b_rel_growth_prior", reasons

    if is_slope and surv.get("available") and surv.get("retention") is not None \
            and not surv.get("survives_reweighting"):
        reasons.append(
            f"⚠️ the age lift retains only {surv['retention']:.0%} of itself under S2 re-weighting "
            f"(floor {SURVIVORSHIP_RETENTION_MIN:.0%}) — substantially SELECTION rather than aging. "
            f"Reported as an UPPER BOUND; not eligible to ship on this evidence.")
        return "UPPER_BOUND_ONLY", label, reasons

    return "ADD", label, reasons


def synthetic_recovery_check(n: int = 2400, seed: int = 5) -> dict:
    """⭐ CAN THIS MACHINERY ACTUALLY FIND WHAT IT CLAIMS TO LOOK FOR — and can it tell the two channels
    apart?

    NF1.7 lesson 1: an anchor that cannot fail passes on nothing. Two of this slice's instruments are
    only worth their reporting space if they are demonstrably discriminating:

      1. **the slope block** — plant a genuine age × line interaction and require `Y2_rel_slope` to
         beat the baseline; plant NOTHING and require it not to. A block that cannot recover a planted
         effect turns every real-data null into "my code does not work", which is not a finding.
      2. **the channel foil** — plant an INTERCEPT-only age effect (per-bucket level shifts, identical
         slopes) and require the intercept arm to win it while the slope arm does not. This is the
         discrimination the whole attribution rests on: without it, `intercept_only_vs_rel_slope` is
         untested machinery and a real-data "the intercept explains it" reading would be unearned.

    Returns the three regimes' lifts. Run by the unit tests; not part of the live ladder.
    """
    rng = np.random.default_rng(seed)

    def _panel(mode: str) -> pd.DataFrame:
        level = rng.choice(["Single-A", "High-A", "Double-A", "Triple-A"], n)
        ref = pd.Series(level).map(
            {"Single-A": 21.0, "High-A": 22.0, "Double-A": 22.8, "Triple-A": 24.0}).to_numpy(float)
        age = ref + rng.normal(0.0, 1.8, n)
        feat = rng.normal(0.10, 0.030, n)
        rel = age - ref
        young = (rel < -0.5).astype(float)
        slope = 0.60 + (0.55 * young if mode == "slope" else 0.0)
        level_shift = 0.020 * young if mode == "intercept" else 0.0
        y = 0.020 + slope * (feat - 0.10) + level_shift + rng.normal(0.0, 0.010, n)
        return pd.DataFrame({
            "player_id": np.arange(n), "level": level, "league": rng.choice(["L1", "L2"], n),
            "age": age, "feat": feat, "minor_pa": rng.integers(150, 600, n), "target": y,
            "has_target": True,
            "debut_cohort": rng.choice([2019, 2020, 2021, 2022], n)})

    out: dict = {}
    for mode in ("slope", "intercept", "none"):
        df = _panel(mode)
        df = attach_age_features(df, level_median_age(df))
        tr, te = df[df["debut_cohort"] < 2022], df[df["debut_cohort"] == 2022]
        scored = {}
        for lbl, kw in (("base", {}),
                        ("slope_arm", dict(bucket_col=REL_BUCKET, bucket_slope=True)),
                        ("intercept_arm", dict(bucket_col=REL_BUCKET, bucket_intercept=True))):
            mdl = PartialPoolProjector(prior_scale=2.0, **kw).fit(tr)
            yhat, _ = mdl.predict(te)
            scored[lbl] = float(np.mean(np.abs(te["target"].to_numpy(float) - yhat)))
        out[mode] = {
            "base_mae": round(scored["base"], 6),
            "slope_arm_pct_lift": round(100.0 * (scored["base"] - scored["slope_arm"])
                                        / scored["base"], 4),
            "intercept_arm_pct_lift": round(100.0 * (scored["base"] - scored["intercept_arm"])
                                            / scored["base"], 4),
        }
    out["reading"] = (
        "a planted SLOPE effect should lift the slope arm well above the intercept arm; a planted "
        "INTERCEPT effect should do the reverse; the null panel should lift neither materially")
    return out


def write_report(results: dict[str, S5Result], fdr: dict, side: SideConfig, dest: Path) -> None:
    L: list[str] = []
    A = L.append
    A(f"# E7.12 slice 5 — prospect aging curves ({side.player_type}s)\n")
    A("> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**\n")
    A("## 🛑 This slice is not \"add age\"\n")
    A("`age` has been an unpenalized fixed main effect in `PartialPoolProjector` since E7.3. The "
      "question here is whether age changes the **slope** of the translation — whether a 20-year-old "
      "and a 25-year-old posting the same Double-A line should have that line read differently — and, "
      "separately, whether the age main effect is mis-specified as **linear**.\n")
    A("\n### The two channels are separate arms on purpose\n")
    A("| channel | arms | the claim it can support |\n|---|---|---|\n"
      "| **slope** | `Y1_age_slope`, `Y2_rel_slope`, `Y4`, `Y5` | *youth changes how much the line "
      "MEANS* — the actual aging-curve hypothesis |\n"
      "| **intercept** | `Y3_age_growth_prior`, `Y3b_rel_growth_prior` | *the linear age main effect "
      "is the wrong shape* — real, but a different finding |\n")
    A("\n`Y3b` is simultaneously a ladder arm and the **matched foil** for `Y2`: identical bucketing, "
      "the claimed channel removed. If both win by the same margin the honest report is the intercept "
      "one — a win is not self-attributing (NF-D15 g′).\n")
    A("\n### ⚠️ Confounded with S2 by construction, and handled as a matched pair\n")
    A("A young player who did NOT develop never gets promoted, so he is in none of these training "
      "rows. **\"Young players' lines translate better\" is exactly what survivorship bias "
      "manufactures out of nothing.** `V_ipw_Y0` / `V_ipw_Y2` re-run the baseline and the interaction "
      "under S2's `T1b_ipw_odds` inverse-odds weights, which tilt the graduate sample toward the "
      "un-promoted population the board actually scores. The second difference — re-weighted lift over "
      "unweighted lift — is the `survivorship` block below. The IPW re-weighting appears on BOTH sides "
      "of that difference, so it cannot be mistaken for the mechanism.\n")
    A(f"Retention floor: **{SURVIVORSHIP_RETENTION_MIN:.0%}** of the unweighted lift must survive, "
      f"pre-registered before the run.\n")
    A("\n### The ceiling probe\n")
    A("`R_gbm_age` / `R_gbm_noage` are a matched pair of gradient-boosted learners differing ONLY in "
      "whether age is visible. A tree ensemble can express any age × line interaction it likes, so "
      "their paired gap bounds how much age structure is exploitable here **at all**, independent of "
      "whether our prescribed bucketing is the right shape. Neither is selectable: E7.9 measured that "
      "54-77% of every apparent margin in this program was the learner swap, and a GBM win here would "
      "report a learner change as an aging-curve finding.\n")

    A("\n## Verdicts\n")
    A(pd.DataFrame([{
        "metric": m, "shipped_baseline": r.shipped_rung, "verdict": r.verdict, "winner": r.winner,
        "folds": len(r.fold_cohorts),
        "age_lift_retention_under_IPW": r.survivorship.get("retention"),
        "BH-FDR@0.10": fdr.get(m),
    } for m, r in results.items()]).to_markdown(index=False))

    for m, r in results.items():
        A(f"\n---\n\n## `{m}` (baseline = `{r.shipped_rung}`, prior_scale = {r.prior_scale})\n")
        A(f"folds {r.fold_cohorts}\n")
        A(r.leaderboard.drop(columns=["note"]).round(6).to_markdown(index=False))
        A("\n⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted "
          "incumbent — comparing a re-weighted arm to an unweighted baseline would fold the "
          "re-weighting into the mechanism's margin.\n")
        A("\n### Survivorship (the S2 confound)\n")
        A("```\n" + json.dumps(r.survivorship, indent=2, default=str) + "\n```")
        A("\n### Anchors\n")
        A("```\n" + json.dumps(r.anchors, indent=2, default=str) + "\n```")
        A("\n### Deflation\n")
        A("```\n" + json.dumps(r.deflation, indent=2, default=str) + "\n```")
        if len(r.coverage):
            A("\n### Bucket support (labelled rows, last fold's bucketing)\n")
            A("An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed "
              "for has to be visible rather than inferred.\n")
            A(r.coverage.to_markdown(index=False))
        if r.reasons:
            A("\n### Notes\n")
            for x in r.reasons:
                A(f"- {x}")
    dest.write_text("\n".join(L))
    log.info("wrote %s", dest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.12 slice 5 — prospect aging curves")
    p.add_argument("--player-type", choices=sorted(SIDES), default="batter")
    p.add_argument("--metrics", nargs="*", default=None)
    p.add_argument("--seed", type=int, default=5)
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[a.player_type]
    suffix = side.reduced.artifact_suffix
    art = _ABLATION / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(art / side.pairs_name)
    pctx_path = _ABLATION / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    park_ctx = pd.read_parquet(pctx_path) if pctx_path.exists() else None
    log.info("pairs %d · park ctx %s", len(pairs), len(park_ctx) if park_ctx is not None else "ABSENT")

    metrics = tuple(a.metrics) if a.metrics else side.metrics
    cache: dict = {}     # fold → PropensityFold, shared across metrics (it does not depend on one)
    results: dict[str, S5Result] = {}
    for m in metrics:
        log.info("── %s ──", m)
        results[m] = run_s5_ladder(pairs, park_ctx, m, side, seed=a.seed, propensity_cache=cache)
        log.info("[%s] verdict=%s winner=%s retention=%s", m, results[m].verdict,
                 results[m].winner, results[m].survivorship.get("retention"))

    pvals = {m: float(r.leaderboard.loc[r.leaderboard["arm"] == r.winner, "p_one_sided"].iloc[0])
             for m, r in results.items()
             if r.verdict == "ADD" and r.winner in set(r.leaderboard["arm"])
             and np.isfinite(r.leaderboard.loc[r.leaderboard["arm"] == r.winner,
                                               "p_one_sided"].iloc[0])}
    fdr = bh_fdr(pvals)
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict, r.winner = "DROP", "Y0_shipped"
            r.reasons.append("⛔ FDR-DOWNGRADED — did not survive Benjamini-Hochberg at alpha=0.10 "
                             "across the metrics tested in this run")

    dest = _ABLATION / f"e7_12_slice5_aging_curves{suffix}.md"
    write_report(results, fdr, side, dest)
    for m, r in results.items():
        log.info("FINAL [%s] %s → %s", m, r.verdict, r.winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

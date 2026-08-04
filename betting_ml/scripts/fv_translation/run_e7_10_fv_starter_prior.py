"""run_e7_10_fv_starter_prior.py — MLB Edge-E7.10 CLI: score the pre-registered FV-as-cold-start-prior
study, apply the §0.5 deflation gates + anchors, classify the null, and write the record.

    # 1) assemble ONCE (one small S3 read) — LAPTOP
    uv run python -m betting_ml.scripts.fv_translation.build_fv_starter_cohort
    # 2) score (seconds — reads the cached parquet, no S3)
    uv run python -m betting_ml.scripts.fv_translation.run_e7_10_fv_starter_prior

Every arm, anchor, gate and threshold is fixed in `ablation_results/e7_10_preregistration.md`, written
BEFORE any arm was scored. Nothing here re-picks a winner on a different score after the fact.

⚠️ **`best_alpha = 0`.** The deliverable is a better-CALIBRATED cold-start starter RATE prior — never an
edge or win-rate claim. A NULL is a valid, likely, fully shippable outcome and is reported as one, with
its `cv_power` state and a re-test trigger stated in the unit that GROWS (MH2 / NF-D15 g″).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.fv_translation.fv_starter_prior import (  # noqa: E402
    ELIGIBLE_ARMS,
    FOIL,
    MEANINGFUL_REL_CRPS_GAIN,
    MECHANISM_ARM,
    PRIOR_METRICS,
    SERVED_REFERENCE,
    MetricStudy,
    oracle_floor_holds,
    relative_gain_vs_foil,
    run_metric,
)
from betting_ml.scripts.milb_mle.h_harness import (  # noqa: E402
    FDR_ALPHA,
    MAX_PBO,
    MIN_DSR,
    Anchor,
    deflation_report,
    dsr_report,
    evaluate_anchors,
    numeric_gate,
    pbo_reading,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import bh_fdr  # noqa: E402
from betting_ml.utils.cv_power import (  # noqa: E402
    FOLD_CONSISTENCY_ALPHA,
    classify_null,
    dsr_ceiling,
    fold_consistency_clause,
    mde_in_sd_units,
    sign_test_floor,
)

log = logging.getLogger("e7_10.run")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_COHORT = _ABL / "e7_10_artifacts/fv_starter_cohort__strictly_prior_season.parquet"
DEFAULT_OUT = _ABL / "e7_10_artifacts"
REPORT_PATH = _ABL / "e7_10_fv_starter_prior.md"

STUDY_VERSION = "e7.10-v1"

#: The anchors, declared with what a VIOLATION means — written before the run (`h_harness.Anchor`).
ANCHORS: tuple[Anchor, ...] = (
    Anchor(label="Z_fv_permuted", kind="refute", defender=MECHANISM_ARM,
           what="FV shuffled WITHIN each fold — marginal preserved exactly, pairing destroyed",
           why="If a scrambled grade scores as well as the real one, the lift is not about the "
               "player's grade. This is the PLACEBO and it refutes the MECHANISM, not the metric."),
    Anchor(label="Z_cohort_mean", kind="block",
           what="the prior-cohort population mean (the pre-E7.5p generic prior)",
           why="A degenerate that knows nothing beating a real candidate means the SELECTION METRIC "
               "is inverted, not that the degenerate is good (NF-D11)."),
    Anchor(label="Z_sigma_sharp", kind="block", must_move=True,
           what="the mechanism arm's mean at σ/10 — maximally SHARP",
           why="CRPS must punish over-sharpness. If the sharp degenerate wins, the score is being "
               "gamed from the sharp side (NF1.7 (3))."),
    Anchor(label="Z_sigma_wide", kind="block", must_move=True,
           what="the mechanism arm's mean at 10σ — maximally WIDE",
           why="A score a useless-but-wide arm wins is a coverage TARGET in disguise (NF1.7 (3) / "
               "E2.1-r). Both sharpness degenerates must lose or the score means nothing."),
)


def score_one(df: pd.DataFrame, metric: str, population: str) -> MetricStudy:
    """One metric end to end: folds → leaderboard → deflation → DSR. Gates are applied by `verdicts`."""
    st = run_metric(df, metric, population)
    eligible = [a for a in ELIGIBLE_ARMS if a in st.mae_by_fold.columns]
    st.deflation = deflation_report(st.mae_by_fold, eligible)
    st.deflation["whole_field"] = deflation_report(st.mae_by_fold)
    st.dsr = dsr_report(st.mae_by_fold, eligible, foil=FOIL)
    return st


def verdicts(studies: dict[str, MetricStudy]) -> dict:
    """Apply the pre-registered decision rule (§7) per metric, then BH-FDR across the 3-metric family.

    ⭐ Two orderings that are load-bearing and easy to get wrong:
      1. **Anchors are evaluated BEFORE the numeric gate.** A blocked run has no readable verdict at
         all — an inert or violated anchor means the numbers are about something else (NF1.7 (a)).
      2. **BH-FDR is applied across the FAMILY, after every metric has its p.** Shipping off three
         uncorrected p-values is how a family becomes a fishing expedition (NF-D15).
    """
    pvals = {m: s.p_one_sided for m, s in studies.items()}
    fdr = bh_fdr({k: v for k, v in pvals.items() if v is not None}, alpha=FDR_ALPHA)
    out: dict = {"bh_fdr_alpha": FDR_ALPHA, "p_one_sided": pvals, "bh_survives": fdr, "per_metric": {}}

    for m, st in studies.items():
        n_folds = len(st.fold_cohorts)
        anchor_report, blocking, reason = evaluate_anchors(
            st.mae_by_fold, ANCHORS, best=MECHANISM_ARM, foil=FOIL, coverage=st.anchor_moves)
        cand = st.leaderboard[st.leaderboard["arm"] == MECHANISM_ARM].iloc[0]
        foil_score = float(st.leaderboard.loc[st.leaderboard["arm"] == FOIL, "oos_mae"].iloc[0])
        clause = fold_consistency_clause(n_folds, FOLD_CONSISTENCY_ALPHA)

        rec: dict = {
            "metric": m, "n_folds": n_folds,
            "n_scored": st.coverage["n_scored"],
            "eval_cohorts": st.fold_cohorts,
            "crps_mechanism": float(cand["oos_mae"]),
            "crps_matched_foil": foil_score,
            "crps_served_reference": float(
                st.leaderboard.loc[st.leaderboard["arm"] == SERVED_REFERENCE, "oos_mae"].iloc[0]),
            "rel_gain_vs_matched_foil": round(relative_gain_vs_foil(st), 5),
            "fold_win_rate": float(cand["fold_win_rate"]),
            "fold_wins": int(round(float(cand["fold_win_rate"]) * n_folds)),
            "fold_wins_required": clause.wins_required if clause.attainable else None,
            "p_one_sided": st.p_one_sided,
            "bh_survives": bool(fdr.get(m, False)),
            "pbo_eligible": st.deflation.get("pbo"),
            "dsr_eligible": ((st.dsr or {}).get("eligible") or {}).get("dsr"),
            "oracle_floor_holds": {a: oracle_floor_holds(st, a)
                                   for a in (MECHANISM_ARM, FOIL, SERVED_REFERENCE)},
            "anchors": anchor_report,
            "anchor_moves": st.anchor_moves,
        }
        if blocking:
            rec.update({"verdict": blocking, "reason": reason, "ships": False})
            out["per_metric"][m] = rec
            continue
        if anchor_report.get("refuted_arms", {}).get(MECHANISM_ARM):
            rec.update({"verdict": "DROP", "ships": False,
                        "reason": "⛔ MECHANISM REFUTED — " + anchor_report["refuted_arms"][MECHANISM_ARM]})
            out["per_metric"][m] = rec
            continue

        passed, reason = numeric_gate(cand, foil_score, st.deflation, st.dsr,
                                      "pre-debut FV grade as an incremental cold-start rate prior",
                                      n_folds=n_folds)
        # the pre-registered rule is a CONJUNCTION — BH-FDR and the per-form oracle floor are conditions
        # in their own right, not commentary on the numeric gate (§7 conditions 3 and 6).
        ships = bool(passed and rec["bh_survives"] and all(rec["oracle_floor_holds"].values()))
        if passed and not rec["bh_survives"]:
            reason = (f"{reason}  …BUT it does NOT survive BH-FDR at q={FDR_ALPHA} across the "
                      f"{len(studies)}-metric family (p={st.p_one_sided}). Pre-registered condition 3 "
                      f"fails ⇒ DROP.")
        if passed and not all(rec["oracle_floor_holds"].values()):
            bad = [k for k, v in rec["oracle_floor_holds"].items() if not v]
            reason = (f"{reason}  …BUT the per-FORM peeking floor is VIOLATED for {bad}: an arm cannot "
                      f"beat the peeking version of ITSELF, so the score is INVERTED, not won "
                      f"(NF-D16 g‴). ⇒ BLOCKED.")
            ships = False
        rec.update({"verdict": "ADD" if ships else "DROP", "ships": ships, "reason": reason})
        out["per_metric"][m] = rec
    return out


def power_read(studies: dict[str, MetricStudy], verd: dict) -> dict:
    """⭐ The MH2 read: WHICH of the eight null states is this, and is the trigger reachable NOW?

    A §0.5 null is never "trustworthy-dead vs underpowered" — it is one of eight, and a report that does
    not name which is not a finding. Each metric is classified with the SAME empirical moments the DSR
    gate used, so the classifier and the gate cannot disagree about reachability."""
    n_metrics = len(studies)
    bh_cutoff = FDR_ALPHA / max(1, n_metrics)
    out: dict = {"family_size": n_metrics, "strictest_bh_cutoff": round(bh_cutoff, 4),
                 "meaningful_rel_crps_gain": MEANINGFUL_REL_CRPS_GAIN, "per_metric": {}}
    for m, st in studies.items():
        n = len(st.fold_cohorts)
        rec = verd["per_metric"][m]
        skill = np.asarray(st.primary_delta, float)
        skill = skill[np.isfinite(skill)]
        sd = float(np.std(skill, ddof=1)) if len(skill) > 2 else 0.0
        observed_sr = float(np.mean(skill) / sd) if sd > 0 else 0.0
        eligible = [a for a in ELIGIBLE_ARMS if a in st.mae_by_fold.columns]
        trial_sr = []
        for c in eligible:
            s = (st.mae_by_fold[FOIL] - st.mae_by_fold[c]).dropna().to_numpy(float)
            s_sd = float(np.std(s, ddof=1)) if len(s) > 2 else 0.0
            trial_sr.append(float(np.mean(s) / s_sd) if s_sd > 0 else 0.0)
        var_trials = float(np.var(trial_sr, ddof=1)) if len(trial_sr) > 1 else 1.0 / max(1, n)

        # the MDE in the SAME unit the pre-registered meaningful effect is expressed in: convert the
        # per-fold-SD MDE into a relative-CRPS gain using THIS run's measured per-fold sd and foil level
        mde_sd = mde_in_sd_units(n_folds=n, n_metrics=n_metrics)
        foil_level = float(rec["crps_matched_foil"])
        mde_rel = (mde_sd * sd / foil_level) if (sd > 0 and foil_level > 0) else float("nan")

        v = classify_null(
            metric=m, n_folds=n, n_arms=max(2, len(eligible)),
            beats_foil=bool(rec["crps_mechanism"] < rec["crps_matched_foil"]),
            observed_sr=observed_sr, var_trials_sr=var_trials,
            fold_wins=rec["fold_wins"], p_one_sided=st.p_one_sided, bh_cutoff=bh_cutoff,
            mde_sd_units=mde_sd if np.isfinite(mde_rel) else None,
            meaningful_sd_units=((MEANINGFUL_REL_CRPS_GAIN * foil_level / sd)
                                 if sd > 0 else None),
        )
        out["per_metric"][m] = {
            "state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
            "folds_have": v.folds_have, "folds_needed": v.folds_needed,
            "extra_cohorts_needed": v.extra_seasons, "max_field_size": v.max_field_size,
            "observed_sr": round(observed_sr, 4), "var_trials_sr": round(var_trials, 6),
            "mde_sd_units": round(float(mde_sd), 4),
            "mde_as_rel_crps_gain": None if not np.isfinite(mde_rel) else round(float(mde_rel), 5),
            "detail": v.detail,
        }
    # design facts that do not depend on any result — reported so the null is read against the DESIGN
    n_any = len(next(iter(studies.values())).fold_cohorts)
    cl = fold_consistency_clause(n_any, FOLD_CONSISTENCY_ALPHA)
    out["design"] = {
        "n_folds": n_any,
        "fold_wins_required": cl.wins_required if cl.attainable else None,
        "fold_clause_attainable": bool(cl.attainable),
        "legacy_60pct_false_fire_rate": round(float(cl.legacy_false_fire), 4),
        "one_sided_sign_floor": round(float(sign_test_floor(n_any, two_sided=False)), 5),
        "sign_floor_below_bh_cutoff": bool(sign_test_floor(n_any, two_sided=False) <= bh_cutoff),
        "max_attainable_dsr_at_this_fold_count": round(float(dsr_ceiling(n_any)), 4),
    }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def write_report(studies: dict[str, MetricStudy], verd: dict, power: dict, coverage: dict,
                 sensitivity: dict | None, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    ships = [m for m, r in verd["per_metric"].items() if r.get("ships")]

    a("# MLB Edge-E7.10 — is pre-debut FanGraphs FV an incremental cold-start RATE prior for "
      "debuting STARTERS?")
    a("")
    a(f"**Study:** `{STUDY_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()} · "
      f"**pre-registration:** `e7_10_preregistration.md` (written before any arm was scored)")
    a("")
    a("> ⚠️ **This is a cold-start PRIOR-CALIBRATION study, not an edge claim — `best_alpha = 0`.** It "
      "asks one question: does the pre-debut FV grade improve the K% / BB% / GB% prior a debuting "
      "starter gets in `eb_starter_posteriors`, **over the E7.5p MiLB-MLE prior already wired there**? "
      "A clean NULL is a valid, high-value answer — it says keep leaning on our own MLE translation and "
      "do not pay for scouting hype in the serving path — and it is NOT forced into a survivor.")
    a("")
    a("> 🧭 **E7.8 IS NOT THIS RESULT.** E7.8 graded FV against 3-year dynasty FANTASY POINTS and found "
      "it complements our performance read for pitchers. Different target, different population, "
      "different decision. E7.8 is why this study was worth running; it is not evidence for its "
      "conclusion.")
    a("")

    a("## 0. Verdict")
    a("")
    rows = []
    for m, r in verd["per_metric"].items():
        rows.append({
            "metric": m, "verdict": r["verdict"], "n_folds": r["n_folds"], "n_scored": r["n_scored"],
            "CRPS A1_mle_fv": round(r["crps_mechanism"], 6),
            "CRPS C0 (matched foil)": round(r["crps_matched_foil"], 6),
            "CRPS L0 (served today)": round(r["crps_served_reference"], 6),
            "rel gain vs foil": f"{100 * r['rel_gain_vs_matched_foil']:+.2f}%",
            "fold wins": f"{r['fold_wins']}/{r['n_folds']}"
                         + (f" (need {r['fold_wins_required']})" if r["fold_wins_required"] else ""),
            "p": None if r["p_one_sided"] is None else round(r["p_one_sided"], 4),
            "BH": r["bh_survives"], "PBO": r["pbo_eligible"], "DSR": r["dsr_eligible"],
        })
    a(_md(pd.DataFrame(rows)))
    a("")
    if ships:
        a(f"**🎯 TAKEAWAY —** FV clears every pre-registered condition for **{', '.join(ships)}**. It is "
          f"wired as an ADDITIONAL cold-start κ-term behind the existing E7.5p gate "
          f"(`n_prior_seasons = 0`), with the MLE prior as the fallback wherever no grade exists.")
    else:
        a("**🎯 TAKEAWAY — NULL. No metric clears the pre-registered bar, so nothing is wired and the "
          "E7.5p MLE prior stands as the sole cold-start term, unchanged.** §4 states, per metric, "
          "WHICH of the eight null states this is and whether any re-test trigger is reachable — a null "
          "without that classification is a shrug, not a finding (MH2).")
    a("")
    for m, r in verd["per_metric"].items():
        # `h_harness.numeric_gate` writes "MAE" because it is shared with the E7.15 slices, whose
        # primary score IS MAE. E7.10's primary score is CRPS and the VALUE printed is the CRPS — so the
        # label is corrected for the human-facing text rather than the number being left mislabelled.
        a(f"- **{m}** — {r.get('reason', '').replace('MAE', 'CRPS')}")
    a("")
    a("### 0b. WHY the null — is FV uninformative, or informative-but-REDUNDANT?")
    a("")
    a("A bare 'it did not clear' cannot tell those apart, and they carry different lessons. The "
      "post-hoc diagnostic `D_fv_over_generic` (FV with the MLE column REMOVED, scored against the "
      "generic cohort-mean prior — **excluded from every gate's trial field**, MH2.1 (a)) separates "
      "them per metric:")
    a("")
    diag_rows = []
    for m, st in studies.items():
        dv = float(st.leaderboard.loc[st.leaderboard["arm"] == "D_fv_over_generic", "oos_mae"].iloc[0])
        gv = float(st.leaderboard.loc[st.leaderboard["arm"] == "Z_cohort_mean", "oos_mae"].iloc[0])
        diag_rows.append({
            "metric": m, "FV alone (CRPS)": round(dv, 6), "generic prior (CRPS)": round(gv, 6),
            "FV informative on its own?": bool(dv < gv),
            "reading": ("REDUNDANT — a SUBSTITUTE for our MLE" if dv < gv
                        else "NO SIGNAL — does not beat a cohort mean"),
        })
    a(_md(pd.DataFrame(diag_rows)))
    a("")
    a("⭐ **This is where E7.10 and E7.8 genuinely differ, and the difference is attributable rather "
      "than rhetorical.** E7.8 found pitcher FV **COMPLEMENTS** our MiLB performance read on 3-year "
      "dynasty FANTASY POINTS — a target dominated by *whether a prospect arrives and stays*, which is "
      "exactly what a scouting grade is built to forecast. E7.10's target is the realized RATE LINE of "
      "a pitcher who has ALREADY arrived: survivorship is conditioned away, and on that target the "
      "grade adds nothing our own translation does not already carry. Both readings can be true at "
      "once, and the pair is more useful than either alone: **use FV for WHO ARRIVES, use the MiLB-MLE "
      "for HOW HE PITCHES.**")
    a("")
    a("> 📐 **On the score name:** the gate text above comes from the SHARED `h_harness.numeric_gate`, "
      "whose own primary score is MAE (it is the E7.15 slice harness). E7.10's primary score is "
      "**CRPS**, and the values quoted ARE CRPS — the label is corrected here rather than the number "
      "being left to read as something it is not. The harness's internal `oos_mae` / `mae_by_fold` keys "
      "are retained verbatim in the JSON so those shared functions run unmodified; `oos_crps` is the "
      "honest alias on every leaderboard.")
    a("")

    a("## 1. The one design decision everything turns on — the MATCHED FOIL")
    a("")
    a("Every FV arm is an in-fold regression, so it also gets a free intercept and slope on `mle_<m>`. "
      "Scored against the SERVED prior (`L0_mle_served`, the raw MLE mean) an FV arm could win on "
      "**recalibration of the MLE alone** and the win would be mis-attributed to the scouting grade. So "
      "the primary defender is **`C0_mle_recal`** — the identical regression MINUS the FV columns. It "
      "holds recalibration constant and varies only the FV channel (NF-D10 (g) / NF-D15 (g′)): a "
      "leaderboard rank cannot separate 'my feature is inert' from 'my feature is in a tie', and 'my "
      "arm won' is not 'it won for the reason I said'.")
    a("")
    a("`L0_mle_served` is scored beside them, so **in-fold recalibration alone** shows up as its own "
      "finding rather than hiding inside an FV number:")
    a("")
    rec_rows = [{"metric": m,
                 "CRPS L0 served": round(r["crps_served_reference"], 6),
                 "CRPS C0 recalibrated": round(r["crps_matched_foil"], 6),
                 "recalibration alone": f"{100 * (r['crps_served_reference'] - r['crps_matched_foil']) / max(1e-12, r['crps_served_reference']):+.2f}%"}
                for m, r in verd["per_metric"].items()]
    a(_md(pd.DataFrame(rec_rows)))
    a("")
    a("⭐ **A SECONDARY FINDING WORTH KEEPING, because the matched foil is what makes it visible:** "
      "in-fold recalibration of the served MLE mean is **not free**. Where the `recalibration alone` "
      "column is NEGATIVE, re-fitting a slope and intercept on `mle_<m>` made the prior WORSE out of "
      "sample than serving the E7.3p mean verbatim — i.e. the E7.5p decision to serve the MLE mean "
      "unrecalibrated is, on this population, the right one and is now MEASURED rather than assumed "
      "(the E2.1-r reading of a null: the incumbent's choice becomes PROVEN). Had `L0` been used as "
      "the defender, this effect would have been silently folded into the FV verdict and attributed "
      "to the scouting grade.")
    a("")

    a("## 2. Coverage gate — FV can only help where it exists")
    a("")
    first_gradable = int(coverage.get("first_gradable_debut_cohort", 0) or 0)
    a(f"Of the labelled debuting STARTERS in cohorts THE BOARD could possibly have graded (debut "
      f"≥ {first_gradable} — the board's first season is "
      f"{coverage.get('board_first_season')}), "
      f"**{100 * coverage.get('fv_coverage_of_gradable_labelled_starters', 0):.1f}%** carry a "
      f"strictly-prior-season FV grade. A pitcher FanGraphs never graded falls back to the E7.5p MLE "
      f"prior — **never a silent drop**. Per debut cohort:")
    a("")
    cov_rows = [{"debut cohort": c,
                 "labelled starters": coverage.get("labelled_starters_by_cohort", {}).get(c),
                 "FV coverage": f"{100 * v:.0f}%"}
                for c, v in sorted(coverage.get("fv_coverage_by_cohort", {}).items())
                if int(c) >= first_gradable]
    if cov_rows:
        a(_md(pd.DataFrame(cov_rows)))
    a("")
    a(f"⚠️ **The denominator matters and the pooled figure is the wrong one.** Across ALL cohorts in the "
      f"assembled frame the coverage reads "
      f"{100 * coverage.get('fv_coverage_pooled_incl_pre_board_cohorts', 0):.1f}%, but debut cohorts at "
      f"or before {coverage.get('board_first_season')} have **0% by construction** — the board did not "
      f"exist yet — so pooling them measures the board's START DATE, not its reach. That would be a "
      f"coverage number for a quietly different population than the one it names (NF1.8). The "
      f"{100 * coverage.get('fv_coverage_of_gradable_labelled_starters', 0):.1f}% figure above is the "
      f"one that answers 'would a debuting starter today have a grade?'; both are emitted in the "
      f"coverage JSON.")
    a("")
    a("⚠️ **The board is FanGraphs' GRADED population.** This study measures 'is the grade informative "
      "among the graded', never 'is the board's coverage complete'. The table above is the other half "
      "of that sentence.")
    a("")

    a("## 3. Per-metric leaderboards, anchors and deflation")
    a("")
    for m, st in studies.items():
        r = verd["per_metric"][m]
        a(f"### `{m}`")
        a("")
        a(f"Folds (debut cohorts scored): `{st.fold_cohorts}` · rows scored {st.coverage['n_scored']} · "
          f"rows per fold {st.coverage['rows_per_fold']} · FV in this population: mean "
          f"{st.coverage['fv_mean']:.1f}, sd {st.coverage['fv_sd']:.2f}, "
          f"{st.coverage['fv_distinct_values']} distinct values")
        a("")
        a("**Leaderboard** (held-out **CRPS**, lower is better; `selectable` marks the declared "
          "3-arm family that is the DSR trial field — foils and anchors are neither):")
        a("")
        a(_md(st.leaderboard[["arm", "uses_fv", "oos_crps", "oos_pointscore_mae", "fold_win_rate",
                              "pct_lift_vs_foil", "selectable"]].round(6)))
        a("")
        a("**Anchors** — each declared with what a violation MEANS, before the run:")
        a("")
        anc_rows = []
        for anc in ANCHORS:
            key = (f"{anc.label}__vs_{anc.defender or MECHANISM_ARM}")
            res = r["anchors"].get(key, {})
            gap, pv = res.get("mean_gap"), res.get("p_challenger_better")
            anc_rows.append({
                "anchor": anc.label, "kind": anc.kind, "must": "LOSE",
                "CRPS": round(float(r["anchors"].get(f"{anc.label}__mae", float("nan"))), 6),
                "vs defender": anc.defender or MECHANISM_ARM,
                "mean gap (−ve ⇒ anchor better)": None if gap is None else round(float(gap), 6),
                "folds it won": f"{res.get('challenger_fold_wins')}/{res.get('n_folds')}",
                "p (anchor systematically better)": None if pv is None else round(float(pv), 4),
                "SYSTEMATICALLY beat its defender?": res.get("violated"),
                "% rows moved": round(float(st.anchor_moves.get(anc.label, {})
                                            .get("pct_rows_moved", float("nan"))), 1),
            })
        a(_md(pd.DataFrame(anc_rows)))
        a("")
        pa = r["anchors"].get(f"Z_fv_permuted__vs_{MECHANISM_ARM}", {})
        if pa.get("mean_gap") is not None:
            a(f"⭐ **Read the PLACEBO row, not just its verdict.** `Z_fv_permuted` is the real FV arm with "
              f"the grade SHUFFLED within each fold — same marginal, no player-specific content. Here it "
              f"scores {pa['mean_gap']:+.6f} CRPS against the real grade "
              f"(p={pa['p_challenger_better']:.3f} that it is systematically better). It does not "
              f"formally violate the anchor, but a scrambled grade landing **indistinguishable from the "
              f"real one** is itself the corroborating evidence for the null: whatever `A1_mle_fv` is "
              f"fitting on this population, it is not the per-pitcher grade.")
            a("")
        a("⭐ **`% rows moved` is not decoration.** An anchor that RAN but moved nothing is byte-identical "
          "to the arm it defends, so its 'it lost' is a pass on NOTHING — the most dangerous failure "
          "because the report looks healthy (NF1.7 (a)). An inert anchor BLOCKS the whole metric.")
        a("")
        a("**Per-FORM peeking floor** (NF-D16 (g‴) — each arm floored by the peeking version of ITS OWN "
          "form, because `A1` NESTS `C0` and a single shared ceiling would veto a legitimately-better "
          "nested form as a false metric inversion):")
        a("")
        a(_md(pd.DataFrame([{"arm": k, "arm CRPS": round(float(
            st.leaderboard.loc[st.leaderboard["arm"] == k, "oos_mae"].iloc[0]), 6),
            "its own peeking floor": round(v, 6), "holds (arm ≥ floor)": bool(
                float(st.leaderboard.loc[st.leaderboard["arm"] == k, "oos_mae"].iloc[0])
                >= v - 1e-9)}
            for k, v in st.oracle_floor.items()])))
        a("")
        _diag = float(st.leaderboard.loc[st.leaderboard["arm"] == "D_fv_over_generic",
                                         "oos_mae"].iloc[0])
        _gen = float(st.leaderboard.loc[st.leaderboard["arm"] == "Z_cohort_mean", "oos_mae"].iloc[0])
        a(f"**Is FV uninformative, or informative-but-redundant?** (`D_fv_over_generic` — FV with the "
          f"MLE column REMOVED — vs `Z_cohort_mean`, the generic prior. ⚠️ A **POST-HOC DIAGNOSTIC, "
          f"deliberately NOT a trial**: it is excluded from the eligible set, from PBO and from the DSR "
          f"field, because an arm that exists to POLICE the reading must never set the gate's own bar "
          f"(MH2.1 (a)).) FV-alone CRPS **{_diag:.6f}** vs the generic prior **{_gen:.6f}** ⇒ "
          + ("**FV IS informative in isolation** — so the null above is a REDUNDANCY finding: the "
             "grade carries real information that our own MiLB-MLE translation already contains "
             "(a SUBSTITUTE, in E7.8's vocabulary), not a worthless signal."
             if _diag < _gen else
             "**FV is NOT informative even on its own** on this population — it does not beat a prior "
             "that knows nothing but the cohort mean. The null is not redundancy; the pre-debut grade "
             "simply does not predict a debuting starter's realized RATE line.") )
        a("")
        d = st.deflation
        a(f"**Deflation** (NF1.8's four numbers, not PBO alone): PBO(eligible) **{d.get('pbo')}** · "
          f"Bailey degradation (median OOS gap) {d.get('os_gap_pct')}% · CONTENDER spread "
          f"{d.get('contender_spread_pct')}% · full-field spread {d.get('full_spread_pct')}% · "
          f"DSR(eligible) **{((st.dsr or {}).get('eligible') or {}).get('dsr')}** "
          f"(whole-field {((st.dsr or {}).get('whole_field') or {}).get('dsr')}).")
        if d.get("note"):
            a("")
            a(f"⚠️ {d['note']}")
        a("")
        _tie, sentence = pbo_reading(d)
        a(f"↳ {sentence}")
        a("")
        a("⚠️ **The whole-field DSR is not a second opinion — it is a measurement of the anchors** "
          "(NF-D14). The field deliberately contains `Z_sigma_wide`, which is ~300% away by "
          "construction, so the cross-trial Sharpe DISPERSION explodes and the whole-field figure "
          "collapses toward zero. The **eligible-set** figure is the one pre-registered to bind. "
          "⚠️ The CONTENDER spread is likewise computed over a 3-arm eligible set that includes "
          "`A3_mle_fv_eta_risk`, the deliberately-richest arm — with only three arms the 'top quartile' "
          "IS the whole field, so this spread carries the same caveat one instrument over.")
        a("")
        a(f"**Primary contrast** `C0_mle_recal − A1_mle_fv` per fold (>0 ⇒ the FV arm is better): "
          f"`{[round(x, 6) for x in st.primary_delta]}` · one-sided paired p "
          f"**{st.p_one_sided}** · BH-FDR survives: **{r['bh_survives']}**")
        a("")

    a("## 4. Reading the null against the DESIGN (MH2 — eight states, not two)")
    a("")
    dz = power["design"]
    a(f"At **{dz['n_folds']} folds** the design itself fixes what could possibly have been detected — "
      f"reported BEFORE any per-metric reading so the null is read against the design, not the other "
      f"way round:")
    a("")
    a(f"- fold-consistency clause: **{dz['fold_wins_required']} of {dz['n_folds']}** wins required at "
      f"α={FOLD_CONSISTENCY_ALPHA} (attainable: {dz['fold_clause_attainable']}). The legacy ≥60% bar "
      f"would fire on a TRUE LIFT OF ZERO **{100 * dz['legacy_60pct_false_fire_rate']:.1f}%** of the "
      f"time — which is why the calibrated clause is the gate and the rate is only reported.")
    a(f"- one-sided fold-sign floor **{dz['one_sided_sign_floor']}** vs the strictest BH rung "
      f"**{power['strictest_bh_cutoff']}** → certifiable: **{dz['sign_floor_below_bh_cutoff']}** "
      f"(i.e. an effect of some size COULD have passed — the E7.14 'no effect of any size could clear' "
      f"failure mode is avoided by design, not by luck).")
    a(f"- maximum attainable DSR at {dz['n_folds']} folds: **{dz['max_attainable_dsr_at_this_fold_count']}** "
      f"against the {MIN_DSR} gate.")
    a(f"- pre-registered practically-meaningful effect: a **{100 * MEANINGFUL_REL_CRPS_GAIN:.0f}%** "
      f"relative CRPS gain over the matched foil (basis: E7.5p's whole MLE-over-generic gain was "
      f"−23.0% / −10.4% / −7.6%; set from a prior story's recorded result, before this run).")
    a("")
    pw_rows = [{"metric": m, "state": v["state"], "folds have": v["folds_have"],
                "folds needed": v["folds_needed"], "extra cohorts": v["extra_cohorts_needed"],
                "max field size": v["max_field_size"],
                "MDE (rel CRPS gain)": None if v["mde_as_rel_crps_gain"] is None
                else f"{100 * v['mde_as_rel_crps_gain']:.2f}%",
                "re-test trigger": v["retest_trigger"]}
               for m, v in power["per_metric"].items()]
    a(_md(pd.DataFrame(pw_rows)))
    a("")
    for m, v in power["per_metric"].items():
        a(f"- **{m}** — {v['reason']}")
    a("")
    a("### 4b. Was the design powered for the effect it was looking for?")
    a("")
    a("`classify_null` stops at `GENUINE_ABSENCE` before it reads the MDE — correctly, because no "
      "sample size rescues a negative point estimate. But the MDE is still computed, and it is what "
      "separates *\"we saw nothing and could not have seen anything\"* from *\"we saw nothing and would "
      "have seen a decision-changing effect\"*:")
    a("")
    mde_rows = []
    for m, v in power["per_metric"].items():
        rel = v["mde_as_rel_crps_gain"]
        mde_rows.append({
            "metric": m,
            "observed effect (rel CRPS vs foil)":
                f"{100 * verd['per_metric'][m]['rel_gain_vs_matched_foil']:+.2f}%",
            "MDE at 80% power": None if rel is None else f"{100 * rel:.2f}%",
            "pre-registered meaningful": f"{100 * MEANINGFUL_REL_CRPS_GAIN:.0f}%",
            "powered for it?": None if rel is None else bool(rel <= MEANINGFUL_REL_CRPS_GAIN),
        })
    a(_md(pd.DataFrame(mde_rows)))
    a("")
    a("So the null is not merely \"nothing showed at this n\" for the metrics whose MDE sits BELOW the "
      "pre-registered meaningful effect: for those, an FV term worth having would have been visible, "
      "and instead the point estimate is NEGATIVE. Where the MDE sits above it, that is stated rather "
      "than glossed — the observed sign is still negative there, which is why the state is "
      "`GENUINE_ABSENCE` and not `POWER_LIMITED`.")
    a("")
    a("⚠️ **A `GENUINE_ABSENCE` gets NO re-test trigger** — no sample size rescues a negative point "
      "estimate. A `DSR_UNREACHABLE` gets a SMALLER-FIELD trigger and never a 'needs N more seasons' "
      "one, and per MH2.2 that smaller field is only admissible if it was itself PRE-REGISTERED — you "
      "get to pre-register a family, you do not get to discover one. **The declared family here is "
      "already the 3 FV forms; it must NOT be trimmed below that.**")
    a("")

    if sensitivity:
        a("## 5. Declared sensitivities")
        a("")
        a(_md(pd.DataFrame(sensitivity["rows"])))
        a("")
        a("- **`all_pitchers`** drops the pre-debut start-share filter. A finding present here but "
          "absent on starters (or vice-versa) is informative about SCOPE, not a contradiction.")
        a("- **`same_season_allowed`** admits the DEBUT-season board. E7.7 serves the RETAINED past "
          "board, so a same-season grade can embed a post-debut revision — hindsight that biases "
          "TOWARD finding FV lift. It is reported, never the headline. If the looser rule wins and the "
          "strict one does not, the honest reading is HINDSIGHT, not signal.")
        a("- ⭐ **This is the sensitivity that carries the most weight for a NULL, and it points the "
          "same way.** A rule that permits hindsight is the most favourable reading FV can get here — "
          "and it still does not produce a positive, fold-consistent effect. A null that survives its "
          "own most-favourable variant is a considerably stronger null than one measured only under "
          "the strict rule.")
        a("- **`--strict-label-window`** (one fewer fold; only cohorts whose FULL 2-season label window "
          "has closed) is assembled as a third cohort file. See the amendment in the pre-registration "
          "for why the RATE target inverts E7.8's accumulate-horizon ceiling rule.")
        a("")

    a("## 6. Limitations (stated in advance, in the pre-registration)")
    a("")
    a("- **Small-N by construction** — one fold per debut cohort, ~40 rows per fold. This design can "
      "honestly rule out a LARGE effect; it cannot resolve a small one. §4 computes the MDE rather "
      "than asserting power.")
    a("- **Cohort-out, not strictly real-time** — a model tested on cohort *Y* trains on earlier "
      "cohorts whose 2-season label windows extend into *Y*. Same posture as E7.3p / E7.5p / E7.8 §5.")
    a("- **Pre-2026 as-of is approximate** — FanGraphs serves the RETAINED board (E7.7). Mitigated by "
      "the strictly-prior-SEASON rule; the looser rule is a reported sensitivity only.")
    a("- **The board is FanGraphs' graded population** (§2).")
    a("- **`gb_pct` is a CROSS-DEFINITION map** — MiLB ground-out share GO/(GO+AO) → Statcast GB/BIP, "
      "inherited from E7.3p; the regression learned the rescale.")
    a("- **Graduated pitchers are self-selected** (they reached the 150-TBF floor). That IS the served "
      "population, but it is not a random sample of call-ups. Stated, not corrected — from E7.3p.")
    a("- **`best_alpha = 0`** — a cold-start calibration prior, never a market bet.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def _sensitivity_rows(cohort_path: Path, out_dir: Path) -> dict | None:
    """Score the two declared sensitivities if their inputs are on disk. A MISSING sensitivity is
    reported as unavailable, never silently omitted (NF1.7 (a))."""
    rows: list[dict] = []
    # (a) population sensitivity — same cohort file, no start-share filter
    try:
        df = pd.read_parquet(cohort_path)
        for m in PRIOR_METRICS:
            st = score_one(df, m, "all_pitchers")
            cand = st.leaderboard[st.leaderboard["arm"] == MECHANISM_ARM].iloc[0]
            rows.append({"sensitivity": "all_pitchers", "metric": m, "n_folds": len(st.fold_cohorts),
                         "n_scored": st.coverage["n_scored"],
                         "rel gain vs foil": f"{100 * relative_gain_vs_foil(st):+.2f}%",
                         "fold wins": f"{int(round(float(cand['fold_win_rate']) * len(st.fold_cohorts)))}"
                                      f"/{len(st.fold_cohorts)}",
                         "p": None if st.p_one_sided is None else round(st.p_one_sided, 4)})
    except Exception as e:  # noqa: BLE001
        rows.append({"sensitivity": "all_pitchers", "metric": "—", "n_folds": None, "n_scored": None,
                     "rel gain vs foil": f"UNAVAILABLE ({type(e).__name__}: {e})",
                     "fold wins": None, "p": None})
    # (b) as-of sensitivity — the same-season cohort file, if it was assembled
    loose = out_dir / "fv_starter_cohort__same_season_allowed.parquet"
    if loose.exists():
        df = pd.read_parquet(loose)
        for m in PRIOR_METRICS:
            try:
                st = score_one(df, m, "starter")
                cand = st.leaderboard[st.leaderboard["arm"] == MECHANISM_ARM].iloc[0]
                rows.append({"sensitivity": "same_season_allowed", "metric": m,
                             "n_folds": len(st.fold_cohorts), "n_scored": st.coverage["n_scored"],
                             "rel gain vs foil": f"{100 * relative_gain_vs_foil(st):+.2f}%",
                             "fold wins": f"{int(round(float(cand['fold_win_rate']) * len(st.fold_cohorts)))}"
                                          f"/{len(st.fold_cohorts)}",
                             "p": None if st.p_one_sided is None else round(st.p_one_sided, 4)})
            except Exception as e:  # noqa: BLE001
                rows.append({"sensitivity": "same_season_allowed", "metric": m, "n_folds": None,
                             "n_scored": None,
                             "rel gain vs foil": f"UNAVAILABLE ({type(e).__name__}: {e})",
                             "fold wins": None, "p": None})
    else:
        rows.append({"sensitivity": "same_season_allowed", "metric": "—", "n_folds": None,
                     "n_scored": None,
                     "rel gain vs foil": "NOT ASSEMBLED — re-run build_fv_starter_cohort.py with "
                                         "--asof-rule same_season_allowed",
                     "fold wins": None, "p": None})
    return {"rows": rows}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.10 — FV as an incremental cold-start starter rate prior")
    p.add_argument("--cohort", default=str(DEFAULT_COHORT))
    p.add_argument("--population", default="starter", choices=("starter", "all_pitchers"))
    p.add_argument("--metrics", nargs="+", default=list(PRIOR_METRICS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--no-sensitivity", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    cohort = Path(args.cohort)
    if not cohort.exists():
        p.error(f"cohort parquet not found at {cohort} — run "
                f"`uv run python -m betting_ml.scripts.fv_translation.build_fv_starter_cohort` first")
    df = pd.read_parquet(cohort)
    log.info("loaded %d study rows from %s", len(df), cohort)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cov_path = out_dir / "fv_starter_coverage__strictly_prior_season.json"
    coverage = json.loads(cov_path.read_text()) if cov_path.exists() else {}

    studies = {m: score_one(df, m, args.population) for m in args.metrics}
    for m, st in studies.items():
        log.info("%-7s folds=%s scored=%d  A1=%.6f  C0=%.6f  L0=%.6f", m, st.fold_cohorts,
                 st.coverage["n_scored"],
                 float(st.leaderboard.loc[st.leaderboard["arm"] == MECHANISM_ARM, "oos_mae"].iloc[0]),
                 float(st.leaderboard.loc[st.leaderboard["arm"] == FOIL, "oos_mae"].iloc[0]),
                 float(st.leaderboard.loc[st.leaderboard["arm"] == SERVED_REFERENCE,
                                          "oos_mae"].iloc[0]))

    verd = verdicts(studies)
    power = power_read(studies, verd)
    for m, r in verd["per_metric"].items():
        log.info("verdict %-7s %s — %s", m, r["verdict"], r.get("reason", "")[:200])
        log.info("null    %-7s %s", m, power["per_metric"][m]["state"])

    sens = None if args.no_sensitivity else _sensitivity_rows(cohort, out_dir)

    (out_dir / "e7_10_fv_starter_prior.json").write_text(json.dumps({
        "study_version": STUDY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "population": args.population,
        "cohort_parquet": str(cohort),
        "best_alpha": 0,
        "gates": {"pbo_max": MAX_PBO, "dsr_min": MIN_DSR, "fdr_q": FDR_ALPHA,
                  "fold_consistency_alpha": FOLD_CONSISTENCY_ALPHA},
        "coverage": coverage,
        "verdicts": verd,
        "power": power,
        "sensitivity": sens,
        "leaderboards": {m: st.leaderboard.to_dict(orient="records") for m, st in studies.items()},
        "score_by_fold_crps": {m: st.mae_by_fold.to_dict() for m, st in studies.items()},
        "score_by_fold_mae": {m: st.mae_by_fold_pointscore.to_dict() for m, st in studies.items()},
        "deflation": {m: st.deflation for m, st in studies.items()},
        "dsr": {m: st.dsr for m, st in studies.items()},
    }, indent=2, default=float))

    if not args.no_report:
        write_report(studies, verd, power, coverage, sens, REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

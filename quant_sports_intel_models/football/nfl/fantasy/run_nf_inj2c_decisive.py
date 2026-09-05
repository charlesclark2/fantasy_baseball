"""run_nf_inj2c_decisive.py — NF-INJ2c node 4: the decisive run, on the STRICT-DOMINANCE route.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_decisive \
        --duckdb /var/lib/credence/sports/sports.duckdb

⭐ READ FIRST, in this order: `ablation_results/nf_inj2c_margin_construction_rule.md` (node 3a —
**BINDING**, committed before the re-measure) and `ablation_results/nf_inj2c_preregistration.md`
(committed before any arm was scored). This module COMPUTES; it decides nothing. A band, a field or
a measure appearing here that is not in one of those documents is a defect in this file.

────────────────────────────────────────────────────────────────────────────────────────────────
THE DISPOSITION, AND WHY IT IS NOT "THE WINNER"
────────────────────────────────────────────────────────────────────────────────────────────────
PM ruling 2: the registered ship route is STRICT DOMINANCE, alone — `stratified` against the SERVED
incumbent, improve-or-tie on every measure, regress nowhere. So the arm under test is FIXED by the
registration (`nf_inj2c_assignment_rule.PRIMARY_ARM`) and is ⛔ never selected as "the best CRPS".
Choosing the arm after seeing the scores is the E2.1-r inversion in the one place a dominance claim
is most exposed to it.

⭐ STRICT DOMINANCE IS THE ONE DISPOSITION SHAPE WITH NO TUNABLE THRESHOLD. The only quantity that
has to exist is the TIE BAND, and node 3a fixed every one of them in advance.

────────────────────────────────────────────────────────────────────────────────────────────────
WHERE EACH MEASURE COMES FROM — and why three of them are READ, not computed
────────────────────────────────────────────────────────────────────────────────────────────────
M1, M5, M6 are FOLD measures and are computed here over the seven registered folds.

M2's BASELINE, M3 and M4 are BOARD measures taken on node 3b's capture-pinned board. They are READ
from `nf_inj2c_dominance_baseline.json`, ⛔ never recomputed: a second computation of a committed
baseline is a second answer to one question, and the two would drift (the E9.61 two-renderers class).
This module REFUSES to run if that report is absent or its pin did not hold — a dominance claim
against a board nobody is served is not a measurement (node 3a §5 branch 3).

⚠️ M2's BAND, unlike its baseline, is a FOLD quantity — the SE of the per-fold PAIRED difference
(3a §2, R1) — so the authoritative M2 verdict is computed HERE. Node 3b's own board-level M2 reading
is carried beside it and labelled as the baseline it is; 3b says so itself.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE DOES NOT DO
────────────────────────────────────────────────────────────────────────────────────────────────
It implements no assignment rule (every arm is NF-INJ2b's kernel, dispatched — NF-W6c), no band
(node 3a), no field (the PM's ruling, transcribed in `nf_inj2c_assignment_rule`), and no serving
policy (`nf_inj2b_rate_ordering.resolve_served_arm()` is the single authority).

🚦 OPERATOR RUN (>2 min). `best_alpha = 0`; nothing serves; DEPLOY-HELD.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ⚠️ `parents[4]` is the REPO ROOT and is the house convention (90 modules use it; 4 use
# `parents[5]`, which resolves ABOVE the repo — three of those four are this story's own lineage,
# so the off-by-one propagated by copy). It is latent there because every box run passes an
# absolute `--duckdb` and the relative fallback never fires. Flagged for the closeout, ⛔ not
# silently fixed in a decided story's module from here.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import coverage_power_floor as CPF  # noqa: E402
from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2c_assignment_rule as C  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2_rate_permutation as R2  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB  # noqa: E402,E501

log = logging.getLogger("nfl.fantasy.nf_inj2c_decisive")

_STEM = "nf_inj2c_decisive"
_REPORT_DIR = RB._REPORT_DIR
_BASELINE_REPORT = _REPORT_DIR / "nf_inj2c_dominance_baseline.json"

#: ⭐ THE BINDING FIELD — the PM's declared five-arm point-space family, as a value object so the
#: SAME deflation arithmetic NF-INJ2b runs is reused rather than forked (MH2.7). ⛔ A field is a
#: PRE-REGISTRATION act; this transcribes one, it does not assemble one.
BINDING_FIELD = RB.FieldSpec(
    arms=tuple(C.ARMS), degenerates=tuple(C.DEGENERATE_ARMS), reference=tuple(C.REFERENCE_ARMS),
    declared_field_size=C.DECLARED_FIELD_SIZE,
    label="NF-INJ2c BINDING five-arm point-space field (PM ruling 2026-09-01)")

#: the inherited NF-INJ2b field, published beside the binding figure and labelled NON-BINDING
#: (§2.4 / NF-D14's two-sided rule). It publishes whichever way it comes out and ⛔ cannot rescue a
#: binding refusal. ⛔ No third field is ever computed.
DIAGNOSTIC_FIELD = RB.NF_INJ2B_FIELD

#: §2.3(b), transcribed. Stated as a CONSTANT so the report and the lever cannot drift apart.
_FIELD_TRIM_STATUS = (
    "STRUCTURALLY UNAVAILABLE — `V` has exactly two members, so the only available drops are the "
    "arm under test (inadmissible outright, NF-W7h) or the sole other contributor (leaving `V` "
    "undefined at one point). Any refusal is stated A FORTIORI on the design, ⛔ never as a trimmed "
    "number (pre-registration §2.3(b))."
)

#: the interval level NF1.9's served band targets; M6's floor is DERIVED from each group's n against
#: this nominal, ⛔ never a flat point-floor at it (NF-D22).
NOMINAL_COVERAGE = 0.80


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The node-3b baseline — READ, and refused rather than reconstructed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_measures(path: Path | None = None) -> dict:
    """M2's baseline, M3 and M4 for every arm, READ from node 3b's capture-pinned report.

    ⛔ REFUSES rather than returning None or recomputing (NF-INJ2b's own lesson: `served if served is
    not None else board` compares an arm to ITSELF and reports a structural zero as a measurement)."""
    p = path or _BASELINE_REPORT
    if not p.exists():
        raise SystemExit(
            f"node 3b's report is not committed at {p} — M2's baseline, M3 and M4 are BOARD measures "
            "taken on its capture-pinned board and are READ from it, never recomputed here. Run:\n"
            "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            "run_nf_inj2c_dominance_baseline --duckdb <path>")
    rep = json.loads(p.read_text())
    pin = ((rep.get("application_2026") or {}).get("reproduction_pin") or {})
    if not pin.get("reproduces", False):
        raise SystemExit(
            f"node 3b's reproduction pin DID NOT HOLD (worst {pin.get('worst_abs_diff')} over "
            f"{pin.get('n')} rows vs {pin.get('tolerance')}) — this run is VOID, not a null (node 3a "
            "§5 branch 3): a dominance claim against a board nobody is served is not a measurement.")
    dom = rep.get("dominance") or {}
    if not dom.get("arms"):
        raise SystemExit(f"node 3b's report at {p} carries no dominance table — refusing to proceed "
                         "on a baseline that was never computed (NF1.7 (a))")
    return {
        "source": str(p),
        "generated_at": rep.get("generated_at"),
        "capture": rep.get("capture"),
        "reproduction_pin": pin,
        "served_incumbent_baseline": dom.get("served_incumbent_baseline"),
        "bands": dom.get("bands"),
        "arms": dom.get("arms"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The FOLD measures — M1, M2's band, M5, M6
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _series(per_fold: dict, arm: str, folds, key: str) -> np.ndarray:
    return np.asarray([per_fold.get(arm, {}).get(y, {}).get(key) for y in folds], dtype=float)


def m1_crps_lift(per_fold: dict, folds: tuple[int, ...], arm: str) -> dict:
    """M1 — the arm's CRPS lift over the incumbent, with the R1 band: the per-fold SE of its OWN
    lift series. A DISPERSION quantity fixed by the design, ⛔ not a threshold chosen to reach a
    verdict (node 3a §1 R1, NF-INJ2b's convention adopted verbatim)."""
    lifts = np.asarray([R2.fold_lift(per_fold, arm, y) for y in folds], dtype=float)
    lifts = lifts[np.isfinite(lifts)]
    if len(lifts) < 2:
        return {"evaluable": False,
                "why": "fewer than two finite per-fold lifts — the R1 band is a per-fold SE and "
                       "cannot be formed; an unevaluable measure is never a pass (NF1.7 (a))"}
    band = float(lifts.std(ddof=1) / np.sqrt(len(lifts)))
    mean = float(lifts.mean())
    return {
        "evaluable": True, "mean_lift_vs_incumbent": round(mean, 4),
        "per_fold_lift": {int(y): round(float(v), 4) for y, v in zip(folds, lifts)},
        "folds_won": int((lifts > 0).sum()), "n_folds": int(len(lifts)),
        "tie_band": round(band, 4), "band_rule": "R1",
        "one_sided_p": M14.onesided_paired_pvalue(lifts),
        "verdict": _r1_verdict(mean, band, better="higher"),
    }


def m2_coherence(per_fold: dict, folds: tuple[int, ...], arm: str, board: dict) -> dict:
    """M2 — coherence violating players per fold, attribution-controlled, with the R1 band: the SE of
    the per-fold PAIRED difference (arm − incumbent).

    ⭐ The BASELINE is node 3b's board figure; the BAND is a FOLD quantity, which is why the
    authoritative verdict is computed here and 3b's board-level reading is carried beside it."""
    a = _series(per_fold, arm, folds, "coherence_violating_players")
    i = _series(per_fold, C.INCUMBENT_ARM, folds, "coherence_violating_players")
    null = _series(per_fold, "mvp1_null", folds, "coherence_violating_players")
    ok = np.isfinite(a) & np.isfinite(i) & np.isfinite(null)
    # ⭐ ATTRIBUTION CONTROL (3a §3(b)): a violation `mvp1_null` also produces is not caused by the
    # ordering step. Declared even though measured INERT on node 1's populations — an inert control
    # must be STATED, not discovered (NF-D20).
    # ⚠️ STATED LIMITATION: node 3b subtracts by KEY (a set difference) because it has the violating
    # players; a fold record carries only a COUNT, so this is a count-level proxy for that set
    # difference and the two coincide only when the control's violations are a subset of the arm's.
    # It is immaterial HERE precisely because the control is measured inert (0 on all seven folds),
    # which `control_inert` reports so a reader can check that rather than take it on trust.
    paired = (np.maximum(a - null, 0.0) - np.maximum(i - null, 0.0))[ok]
    if len(paired) < 2:
        return {"evaluable": False,
                "why": "fewer than two folds carry a paired coherence difference — the R1 band "
                       "cannot be formed (NF1.7 (a))"}
    band = float(paired.std(ddof=1) / np.sqrt(len(paired)))
    mean = float(paired.mean())
    arm_board = (board.get("arms") or {}).get(arm) or {}
    return {
        "evaluable": True,
        "mean_paired_diff_vs_incumbent": round(mean, 4),
        "per_fold_paired_diff": {int(y): round(float(v), 4)
                                 for y, v in zip([f for f, k in zip(folds, ok) if k], paired)},
        "attribution_control": "violations mvp1_null also produces are subtracted (3a §3(b))",
        "control_inert": bool(np.nansum(null) == 0),
        "tie_band": round(band, 4), "band_rule": "R1",
        "verdict": _r1_verdict(-mean, band, better="higher"),   # fewer is better ⇒ negate
        "board_baseline_from_node_3b": {
            "incumbent_attributable": (board.get("served_incumbent_baseline") or {}).get(
                "M2_violations_attributable"),
            "arm_attributable": arm_board.get("M2_violations_attributable"),
            "board_level_reading": arm_board.get("M2_verdict"),
            "note": "the BOARD figure is the BASELINE the pre-registration quotes; the BAND is the "
                    "per-fold paired SE above, so the authoritative M2 verdict is this run's",
        },
    }


def _r1_verdict(signed_gain: float, band: float, *, better: str) -> str:
    """IMPROVES / TIES / REGRESSES against an R1 band. `signed_gain` is already oriented so that
    POSITIVE is better."""
    if not np.isfinite(signed_gain) or not np.isfinite(band):
        return "UNEVALUABLE"
    if signed_gain > band:
        return "IMPROVES"
    if signed_gain < -band:
        return "REGRESSES"
    return "TIES"


def m5_ordering(per_fold: dict, folds: tuple[int, ...], arm: str) -> dict:
    """M5 — draftable-tier Spearman ρ per position, at NF-INJ2's registered bar, VERBATIM (R3):
    a one-sided paired t on the per-fold (incumbent − arm) deltas, BH-corrected across the four
    positions at q = 0.10. ⛔ This story supersedes no gate and relaxes none."""
    by_pos, pvals = {}, {}
    for p_ in R2.POSITIONS:
        w = RB.scored_pos(per_fold, arm, folds, "tier_rho_by_position", p_)
        i = RB.scored_pos(per_fold, C.INCUMBENT_ARM, folds, "tier_rho_by_position", p_)
        if w is not None and i is not None:
            by_pos[p_] = {"arm": w, "incumbent": i, "delta": round(w - i, 4)}
        d = []
        for y in folds:
            wv = per_fold.get(arm, {}).get(y, {}).get("tier_rho_by_position", {}).get(p_)
            iv = per_fold.get(C.INCUMBENT_ARM, {}).get(y, {}).get("tier_rho_by_position", {}).get(p_)
            if wv is not None and iv is not None:
                d.append(iv - wv)               # POSITIVE = the arm is WORSE at this position
        if len(d) >= 3:
            pvals[p_] = M14.onesided_paired_pvalue(np.asarray(d, dtype=float))
    sig = M14.bh_fdr(pvals, q=M14.FDR_Q) if pvals else {}
    regressed = [p_ for p_, v in sig.items() if bool(v)]
    return {
        "evaluable": bool(pvals),
        "metric": "top_tier_rho (the metric NF1.5's own bake-off selected on)",
        "by_position": by_pos, "regression_pvalues": pvals,
        "regression_significant_by_position": sig,
        "band_rule": "R3", "q": M14.FDR_Q,
        "verdict": ("UNEVALUABLE" if not pvals else ("REGRESSES" if regressed else "TIES_OR_BETTER")),
        "regressed_positions": regressed,
        "bh_direction_note": ("⚠️ this BH protects against a false REFUSAL — it is directionally "
                              "GENEROUS to the arm. Declared in the pre-registration §6, so the "
                              "generosity is on the record rather than discovered by a reader."),
        "strict_point_estimate_reading": (all(v["arm"] >= v["incumbent"] - 1e-9
                                              for v in by_pos.values()) if by_pos else None),
    }


def m6_interval_floor(per_fold: dict, folds: tuple[int, ...], arm: str) -> dict:
    """M6 — per-group interval coverage against its NF-D22 POWER FLOOR (R3).

    ⭐ POOLED OVER ROWS, ⛔ never a mean of per-fold rates: a per-group constraint averaged over folds
    silently re-weights a thin fold equal to a fat one, and drops a group thin in one fold entirely
    (NF1.8). ⛔ And the floor is DERIVED from each group's n against the pre-registered false-reject
    target — a flat point-floor at nominal is a ~50% coin flip on a perfectly calibrated band at ANY
    n (NF-D22), which is why it is refused."""
    groups: dict[str, dict] = {}
    for p_ in R2.POSITIONS:
        covered = 0.0
        n = 0
        for y in folds:
            rec = per_fold.get(arm, {}).get(y, {})
            rate = (rec.get("coverage80_by_position") or {}).get(p_)
            k = (rec.get("coverage_n_by_position") or {}).get(p_)
            if rate is None or not k:
                continue
            covered += float(rate) * int(k)
            n += int(k)
        if n <= 0:
            groups[p_] = {"evaluable": False,
                          "why": "no fold contributed a scored interval for this group"}
            continue
        # ⭐ THE VERDICT READS THE VALUES THE REPORT RENDERS. Comparing an unrounded floor while
        # printing a rounded one lets a table and a gate disagree about the same number — the E9.61
        # class this repo has already been burned by. Both are rounded to the SAME precision and
        # the comparison is made on those; a disagreement below 1e-4 in a coverage RATE is not a
        # finding, and a floor DERIVED from n cannot be sensitive at that scale.
        cov = round(covered / n, 4)
        floor = round(float(CPF.power_floor(n, nominal=NOMINAL_COVERAGE)), 4)
        groups[p_] = {"evaluable": True, "n_rows": n, "coverage": cov,
                      "power_floor": floor, "nominal": NOMINAL_COVERAGE,
                      "clears": bool(cov >= floor)}
    evaluable = [g for g in groups.values() if g.get("evaluable")]
    short = [p_ for p_, g in groups.items() if g.get("evaluable") and not g["clears"]]
    return {
        "evaluable": bool(evaluable),
        "pooling": "over ROWS across folds (NF1.8), ⛔ never a mean of per-fold rates",
        "groups": groups, "band_rule": "R3",
        "false_reject_target": CPF.FALSE_REJECT_TARGET,
        "verdict": ("UNEVALUABLE" if not evaluable else ("REGRESSES" if short else "CLEARS")),
        "groups_below_floor": short,
        "reading_note": ("a PASS is 'not shown broken at this n', ⛔ never 'shown right' — each "
                         "group's floor carries the resolution its own n buys (NF-D22)"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Deflation — the BINDING field, and the NON-BINDING DIAGNOSTIC beside it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def deflation_blocks(per_fold: dict, folds: tuple[int, ...], arm: str) -> dict:
    """Both figures the pre-registration §2.4 declares IN ADVANCE, computed with the SAME arithmetic.

    ⭐ The diagnostic publishes whichever way it comes out — including more favourably than the
    binding number (NF-D14's two-sided rule). It ⛔ cannot rescue a binding refusal and no
    disposition reads it. ⛔ No third field is ever computed."""
    binding = RB.deflation(per_fold, folds, arm, field=BINDING_FIELD)
    diagnostic = RB.deflation(per_fold, folds, arm, field=DIAGNOSTIC_FIELD)
    lifts = np.asarray([R2.fold_lift(per_fold, arm, y) for y in folds], dtype=float)
    lifts = lifts[np.isfinite(lifts)]
    return {
        "binding": binding,
        "diagnostic": {**diagnostic, "label": C.DIAGNOSTIC_LABEL,
                       "status": "NON-BINDING — declared in advance, publishes either way, and "
                                 "⛔ cannot rescue a binding refusal"},
        "lockstep_variance_lever": _lockstep(lifts, binding),
        "field_trim_2x2": binding.get("dsr_2x2_diagnostic"),
        "design_quantities": {
            "dsr_ceiling_at_n_folds": cv_power.dsr_ceiling(len(folds)),
            "fold_consistency_required_wins": cv_power.fold_consistency_clause(
                len(folds)).wins_required,     # None ⇒ UNDEFINED at n ≤ 2 (MH2 H8), never a pass
            "pbo_evaluable": cv_power.pbo_evaluable(n_folds=len(folds),
                                                    n_configs=BINDING_FIELD.declared_field_size),
            "note": "computed from the FOLD COUNT alone, before any score — a refusal at seven "
                    "folds is a statement about the evidence, ⛔ not about structural impossibility",
        },
    }


def _lockstep(lifts: np.ndarray, binding: dict) -> dict:
    """⭐ RUN FIRST IF DSR REFUSES, BEFORE ANY REMEDY IS NAMED (pre-registration §6, NF-W8-0d).

    A shared-variance lever (rows/fold, folds, draws, a proportionally sharper estimator) scales
    every trial Sharpe AND the benchmark `SR0` by the same factor, so `SR − SR0` keeps its SIGN: the
    lever is DETERMINISTICALLY VOID whenever `SR ≤ SR0`. Prescribing "more seasons/rows/draws" there
    is the actively misleading NF-D18 direction, so the 2026 trigger is WITHHELD with the reason
    stated rather than published.

    ⛔ Computed from the SAME quantities `dsr_conv` reads — the winner's own per-fold delta series
    and the declared field's V-member trial Sharpes — so the lever answers about the gate that
    actually refused, not a re-derivation of it."""
    v_members = [float(binding["trial_sharpes"][a]) for a in (binding.get("v_members") or [])
                 if a in (binding.get("trial_sharpes") or {})]
    if len(lifts) < 3 or float(lifts.std(ddof=1)) < 1e-12 or len(v_members) < 2:
        return {"evaluable": False,
                "why": "the lever needs the winner's per-fold series and at least two V members — "
                       "an unevaluable check is never a pass (NF1.7 (a))",
                "field_trim_status": _FIELD_TRIM_STATUS}
    from scipy.stats import kurtosis as _kurt, skew as _skew
    rep = cv_power.lockstep_variance_lever(
        observed_sr=float(lifts.mean()) / float(lifts.std(ddof=1)),
        n_trials=BINDING_FIELD.declared_field_size,
        var_trials_sr=float(np.var(v_members, ddof=1)),
        n_obs=int(len(lifts)),
        skew=float(_skew(lifts)), kurt=float(_kurt(lifts, fisher=False)))
    reachable = bool(rep.sr > rep.sr0)
    return {
        "evaluable": True,
        "sr": round(float(rep.sr), 4), "sr0": round(float(rep.sr0), 4),
        "gap": round(float(rep.gap), 4),
        "lever_closed": bool(rep.closed),
        "sign_invariant": bool(rep.sign_invariant),
        "dsr_falls_as_design_sharpens": bool(rep.dsr_falls_as_design_sharpens),
        "ladder": rep.ladder,
        "sr_gt_sr0": reachable,
        "fold_trigger_publishable": reachable,
        "why": ("a fold trigger only means anything when SR > SR0: `n` enters through √(n−1), which "
                "scales a positive gap but can never CREATE one (NF-W8-0d). Under DSR_UNREACHABLE "
                "the calendar-bound 2026 trigger is WITHHELD with this reason stated, ⛔ never "
                "published — that is the NF-D18 misleading direction."),
        "field_trim_status": _FIELD_TRIM_STATUS,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict — strict dominance through node 3a's committed bands
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: what each measure's verdict token must be for DOMINANCE. ⛔ "improve or tie, regress nowhere".
_ACCEPTABLE = {
    "M1": {"IMPROVES", "TIES"}, "M2": {"IMPROVES", "TIES"},
    "M3": {"IMPROVES", "TIES"}, "M4": {"IMPROVES", "TIES"},
    "M5": {"TIES_OR_BETTER"}, "M6": {"CLEARS"},
}


def dominance_verdict(measures: dict[str, dict]) -> dict:
    """`stratified` DOMINATES iff EVERY measure improves or ties. One measure worse than the
    incumbent by more than its own band is a regression, and PM ruling 3 makes that a NULL —
    ⛔ never a band to widen, a measure to drop, or a dimension to re-classify as disclosed-only."""
    tokens = {m: (measures.get(m) or {}).get("verdict") for m in _ACCEPTABLE}
    unevaluable = sorted(m for m, v in tokens.items() if v in (None, "UNEVALUABLE"))
    regressed = sorted(m for m, v in tokens.items()
                       if v is not None and v != "UNEVALUABLE" and v not in _ACCEPTABLE[m])
    if unevaluable:
        state = "UNEVALUABLE"
    elif regressed:
        state = "REGRESSES"
    else:
        state = "DOMINATES"
    return {
        "state": state, "by_measure": tokens,
        "regressed_measures": regressed, "unevaluable_measures": unevaluable,
        "rule": ("improve-or-tie on EVERY measure and regress nowhere (node 3a §2). ⛔ An "
                 "UNEVALUABLE measure is NOT a pass — a dominance claim missing a measure is not a "
                 "dominance claim (NF1.7 (a))."),
    }


def verdict(*, dominance: dict, defl: dict, control: dict, control_binding: dict,
            fold_wins: int, folds: int) -> dict:
    """The pre-committed outcome, selected — ⛔ never composed after the numbers are visible.

    The four branches are node 3a §5 / pre-registration §11, transcribed."""
    binding_dsr = (defl.get("binding") or {}).get("dsr_binding")
    dsr_min = (defl.get("binding") or {}).get("dsr_min", M14.DSR_MIN)
    pbo = (defl.get("binding") or {}).get("pbo")
    pbo_max = (defl.get("binding") or {}).get("pbo_max", M14.PBO_MAX)
    # ⛔ `.wins_required`, ⛔ never the raw 0.60 rate (MH2 H8): the calibrated clause bounds the
    # false-fire rate at EVERY fold count, and at seven it is STRICTER than the legacy one (6 vs 5)
    # — the direction MH2 H8 guarantees, and the reason the legacy figure is reported beside it.
    clause = cv_power.fold_consistency_clause(folds)
    # ⭐ `wins_required` is None when the clause DECLARES ITSELF UNDEFINED — at n ≤ 2 the sign test's
    # smallest attainable false-fire rate `2⁻ⁿ` already exceeds α, so no win count means anything
    # (MH2 H8 (2)). An UNDEFINED clause is ⛔ never a pass and ⛔ never a failure: it propagates as
    # None and the verdict reports UNEVALUABLE. (This fired on the 2-fold code-path smoke, which is
    # what a smoke is for; the registered seven folds require 6.)
    required = (None if clause.wins_required is None else int(clause.wins_required))
    gates = {
        "dsr": (None if binding_dsr is None else bool(binding_dsr >= dsr_min)),
        "pbo_field_level": (None if pbo is None else bool(pbo < pbo_max)),
        "fold_consistency": (None if required is None else bool(fold_wins >= required)),
    }
    failed = sorted(k for k, v in gates.items() if v is False)
    undefined = sorted(k for k, v in gates.items() if v is None)

    # ⭐ AMENDMENT 1 §4 — the control is read BEFORE any gate result, and a control failure blocks
    # the disposition regardless of any badge. A family that cannot certify a planted effect makes
    # every gate reading downstream of it moot, so it is prior. ⛔ Nothing is lost by the ordering:
    # the deflation gates are computed and recorded in FULL either way, so a run that fails both
    # shows both. ⛔ A REGRESSION still reads NULL ahead of it — a measured regression against the
    # incumbent is a direct comparison the control's sensitivity cannot manufacture.
    control_failed = str(control_binding.get("state")) in ("FAILS", "UNEVALUABLE")
    if dominance["state"] == "UNEVALUABLE":
        state = "UNEVALUABLE"
    elif dominance["state"] == "REGRESSES":
        state = "NULL"
    elif control_failed:
        state = "CONTROL_REFUSED"
    elif failed:
        state = "DEFLATION_REFUSED"
    elif undefined:
        state = "UNEVALUABLE"
    else:
        state = "DOMINATES"
    return {
        "state": state, "gates": gates, "gates_failed": failed, "gates_undefined": undefined,
        "fold_consistency_required_wins": required, "fold_wins": fold_wins,
        "fold_consistency_clause": {
            "wins_required": required, "attained_false_fire": clause.attained_false_fire,
            "legacy_wins_required": clause.legacy_wins_required,
            "legacy_false_fire": clause.legacy_false_fire,
            "note": "the CALIBRATED clause (MH2 H8) — the raw 0.60 rate is a different gate at "
                    "every fold count and nearly free at the low end"},
        "branch": {
            "DOMINATES": "M1–M6 dominate and the deflation gates pass → SHIP under the dominance "
                         "disposition, DEPLOY-HELD, with PM ruling 5's disclosure: this HALVES the "
                         "incoherence and the give-back, it does not end them; NF-COH2 is the "
                         "recorded successor.",
            "NULL": "a measure regressed beyond its own band → NULL. PM ruling 3, verbatim: "
                    "'that is a NULL, not a margin to adjust.'",
            "CONTROL_REFUSED": "M1–M6 dominate but the POSITIVE CONTROL's binding substance "
                               "(amendment 1 §4: the INJECTED leg) failed or could not be "
                               "evaluated → the gate family has not been shown able to certify a "
                               "planted effect, so no disposition it reaches is supported. ⛔ NOT "
                               "a statement about the arm.",
            "DEFLATION_REFUSED": "M1–M6 dominate but a binding deflation gate refuses → read "
                                 "against §7's control, with the lockstep check FIRST and §2.3(b)'s "
                                 "structural unavailability stated. The diagnostic field publishes "
                                 "beside it and ⛔ does not rescue it.",
            "UNEVALUABLE": "a measure or gate could not be computed — ⛔ never scored as a pass "
                           "(NF1.7 (a)).",
        }[state],
        # ⛔ the instrument's BADGE, recorded VERBATIM (amendment 1 §5 (c)) — it does NOT bind.
        "positive_control": control.get("verdict"),
        "control_reading": control.get("reading"),
        # ⭐ what BINDS (amendment 1 §4 (b)) — the injected leg's content, as a verdict.
        "control_binding": control_binding,
        "null_leg_declaration_applies": control.get("null_leg_declaration_applies"),
        "best_alpha": 0,
        "served_arm": B.resolve_served_arm(),
        "deploy_held": True,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The injected-effect positive control — over the INJECTION-SENSITIVE half only (§7)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _plat_cvp2_landed() -> bool:
    """Whether the instrument exposes the DECLARED-partition parameters (PLAT-CVP2's durable half).

    ⛔ Not `hasattr(cv_power, "CONSTRAINT_BLOCKED")`: the verdict is a string INSIDE the function,
    not a module attribute, so that check reports False on an instrument that HAS landed — which is
    how the pre-registration's premise came to be stated and how it stayed unnoticed."""
    import inspect
    params = inspect.signature(cv_power.injected_effect_positive_control).parameters
    return "gate_classes" in params and "invariant_gates" in params


def gate_table(payload: dict) -> dict[str, dict[str, bool]]:
    """`{arm -> {gate -> passed}}` over THIS story's six measures — ⛔ not NF-INJ2b's gate set.

    ⭐ WHY THIS EXISTS AT ALL, and it is not a preference. NF-INJ2b's `gate_table` emits
    `coherence_restored`, a gate demanding zero violations — the gate PM ruling 2 REMOVED from this
    story on node 1's §4 bound ("coherence is MEASURED AND REPORTED, never gated at zero"). Driving
    the control with it would re-import a refused gate through the back door and reproduce exactly
    the `BLIND` badge NF-INJ2b's own control earned for that reason. Its keys are also not the ones
    the pre-registration §7 partition names, so `blocking_gates` could never be READ against the
    declared table.

    ⛔ `pbo` IS DELIBERATELY ABSENT. CSCV/PBO has ONE value for the whole field and answers whether
    the SELECTION overfit; carrying it per-arm converts "the search was unstable" into "this arm
    failed", which is not a statement the statistic makes (MLB-HV2-1 MEASURED the cost). It is a
    FIELD-level verdict beside this table, and `pbo_application="field"` says so. A consequence
    worth stating: `field_level_gates_applied_per_arm` should come back EMPTY, and that emptiness is
    the affirmative finding, not an absence of one.

    ⭐ ONE IMPLEMENTATION. This is the function the study scores with AND the one the control
    re-runs on the injected payload — re-implementing the gates inside the control would restate
    this harness's assumptions instead of testing them (the NF-C0e class)."""
    folds = tuple(payload["folds"])
    per_fold = payload["per_fold"]
    board = payload.get("board") or {}
    clause = cv_power.fold_consistency_clause(len(folds))
    required = clause.wins_required
    out: dict[str, dict[str, bool]] = {}
    for arm in C.ARMS:
        m1 = m1_crps_lift(per_fold, folds, arm)
        m2 = m2_coherence(per_fold, folds, arm, board) if board else {"verdict": "UNEVALUABLE"}
        m5 = m5_ordering(per_fold, folds, arm)
        m6 = m6_interval_floor(per_fold, folds, arm)
        m3 = _board_measure(board, arm, "M3") if board else {"verdict": "UNEVALUABLE"}
        m4 = _board_measure(board, arm, "M4") if board else {"verdict": "UNEVALUABLE"}
        wins = int(m1.get("folds_won") or 0)
        defl = RB.deflation(per_fold, folds, arm, field=BINDING_FIELD)
        dsr = defl.get("dsr_binding")
        out[arm] = {
            "m1_crps_lift": m1.get("verdict") == "IMPROVES",
            "m2_coherence": m2.get("verdict") in ("IMPROVES", "TIES"),
            "m3_worst_times_over": m3.get("verdict") in ("IMPROVES", "TIES"),
            "m4_giveback": m4.get("verdict") in ("IMPROVES", "TIES"),
            "m5_tier_rho": m5.get("verdict") == "TIES_OR_BETTER",
            "m6_interval_floor": m6.get("verdict") == "CLEARS",
            # ⛔ a clause that could not be formed is NOT a pass (NF1.7 (a) / MH2 H8): at n ≤ 2 the
            # calibrated clause is UNDEFINED, and False here is the honest rendering for a gate
            # function whose contract is strictly boolean.
            "fold_consistency": bool(required is not None and wins >= required),
            "dsr": bool(dsr is not None and dsr >= defl.get("dsr_min", M14.DSR_MIN)),
        }
    return out


def positive_control(per_fold: dict, folds: tuple[int, ...], scored: dict,
                     coherence: dict[str, int], board: dict | None = None) -> dict:
    """Run NF-INJ2b's registered control, then READ `blocking_gates` against THIS story's declared
    injection partition (§7).

    ⭐ PLAT-CVP2 has not landed, so `cv_power` still exposes no `CONSTRAINT_BLOCKED` verdict. The 2b
    annotation pattern is therefore carried: if `BLIND` fires and every blocker is on the INVARIANT
    side, the honest statement is that the family's statistical half demonstrably fires and the
    verdict was decided by measures no injection can reach — ⛔ neither a rescue nor a condemnation.
    ⛔ The control is NEVER re-run with a constraint removed to obtain a nicer badge (E2.1-r)."""
    payload = dict(RB.build_payload(per_fold, folds, scored, coherence))
    payload["board"] = board or {}
    # ⭐ THIS story's field, ⛔ not NF-INJ2b's. Amendment 1 clause (b) F2/F3 charge a
    # DEGENERATE that survives, which is only sound if the injection never treated it.
    inject = RB.make_injector(payload, field=BINDING_FIELD)

    def _inject(effect: float) -> dict:
        """The injected payload must carry the BOARD block through unchanged — M3/M4 are
        INJECTION-INVARIANT by declaration, so an injector that dropped them would make the control
        report them as unevaluable and blame the injection for it."""
        out = dict(inject(effect))
        out["board"] = payload["board"]
        out.setdefault("folds", list(folds))
        return out

    rep = cv_power.injected_effect_positive_control(
        inject=_inject, run_gates=gate_table, effect=RB.INJECTED_EFFECT,
        check_null_control=True,
        # ⭐ DECLARED, ⛔ not inferred. `cv_power` otherwise partitions the gate set by a NAME
        # HEURISTIC over its own default vocabulary — "a fact about this repo's harness names, not
        # about what your clauses measure", in the instrument's own words. The program convention
        # (CLAUDE.md) is deflation-class = {pbo, cscv, dsr, deflated_sharpe}; `bh_fdr` and
        # `fold_consistency` are MULTIPLICITY/STABILITY gates and are ⛔ NOT deflation-class.
        gate_classes=dict(C.GATE_CLASSES))
    # `injected_effect_positive_control` returns a DATACLASS, not a dict — unpacked explicitly (as
    # NF-INJ2b does) rather than via `asdict`, so a field the instrument adds later cannot silently
    # land in this record unread.
    rep = {
        "verdict": rep.verdict, "reason": rep.reason,
        "effect_injected_crps": rep.effect,
        "survivors": list(rep.survivors), "metric_survivors": list(rep.metric_survivors),
        "deflation_blocked": list(rep.deflation_blocked),
        "deflation_gates": list(rep.deflation_gates), "metric_gates": list(rep.metric_gates),
        "blocking_gates": {k: list(v) for k, v in rep.blocking_gates.items()},
        "field_level_gates_applied_per_arm": list(rep.field_level_gates_applied_per_arm),
        "null_control_checked": rep.null_control_checked,
        "null_control_survivors": (None if rep.null_control_survivors is None
                                   else list(rep.null_control_survivors)),
    }
    # ⚠️ `blocking_gates` is a {arm -> [gate names]} MAPPING, not a flat list. Iterating it directly
    # yields ARM names, which then land in `blockers_unclassified` and make the partition look
    # broken when it is the READING that is (found by the 2-fold code-path smoke).
    bg = rep.get("blocking_gates") or {}
    blockers = (sorted({g for gates in bg.values() for g in (gates or [])})
                if isinstance(bg, dict) else sorted(bg))
    invariant = [g for g in blockers if g in C.INJECTION_INVARIANT_GATES]
    sensitive = [g for g in blockers if g in C.INJECTION_SENSITIVE_GATES]
    unclassified = [g for g in blockers if g not in C.INJECTION_INVARIANT_GATES
                    and g not in C.INJECTION_SENSITIVE_GATES]
    reading = None
    if str(rep.get("verdict")) == "VACUOUS":
        # ⚠️⚠️ RECORDED VERBATIM, THEN READ THROUGH A FORWARD DECLARATION — ⛔ never re-labelled.
        # `inject(0.0)` returns the REAL payload, so "an arm survives the NO-EFFECT payload" is
        # measured on real data, and on real data H1 asserts precisely that `stratified` clears
        # every measure. This study's gate table IS the ship condition, so:
        #     ship ⇒ a non-degenerate arm survives the null leg ⇒ VACUOUS.
        # A verdict ENTAILED by the outcome it exists to inform carries no information about it.
        #
        # ⭐ PRE-REGISTRATION AMENDMENT 1 (PM ruling, decision request #6 D1, 2026-09-05) declares
        # this badge INAPPLICABLE to this family — declared BEFORE the number existed, on the
        # instrument's SOURCE rather than on any score. ⛔ The declaration is SCOPED: it does not
        # reach a DEGENERATE survivor (§3), and it re-scopes the control WITHOUT waiving it — the
        # INJECTED leg binds instead (§4), and can still FAIL the study. ⛔ Re-running the control
        # with the null check disabled to obtain a nicer badge stays forbidden (§7, E2.1-r), so the
        # null leg RUNS every time and its survivor set is recorded — which is what makes §3's
        # carve-out enforceable rather than decorative.
        _surv = list(rep.get("null_control_survivors") or [])
        _degen = [a for a in _surv if a in C.DEGENERATE_ARMS]
        reading = (
            f"VACUOUS fired because arm(s) {_surv} clear every gate on the NO-EFFECT payload — "
            "which IS the real data (`inject(0.0)` returns it unchanged). ⚠️ BOTH READINGS STAY ON "
            "THE RECORD: (a) the instrument's — the family certifies noise, so the injected run "
            "says nothing; (b) the null leg assumes the real payload contains NO effect, which is "
            "the negation of H1, so on a DOMINANCE disposition a TRUE hypothesis produces this "
            "badge BY CONSTRUCTION. ⭐ WHICH ONE BINDS IS DECLARED, ⛔ not chosen here: "
            "pre-registration AMENDMENT 1 (PM ruling #6 D1) declares (b) — the badge is "
            "INAPPLICABLE to this family — and makes the INJECTED leg the control's binding "
            "substance. NF-INJ2b never reached this branch because `coherence_restored` blocked "
            "every arm, the gate PM ruling 2 removed here."
            + (f" ⛔⛔ THE DECLARATION DOES NOT APPLY TO THIS RUN: degenerate(s) {_degen} are among "
               "the null-leg survivors, which §3 carves out explicitly — an arm registered to LOSE "
               "clearing every gate is not entailed by H1 and is a genuine alarm about the family. "
               "The control FAILS (§4 F3)." if _degen else
               " The declaration APPLIES: no declared degenerate is among the survivors."))
    elif str(rep.get("verdict")) == "BLIND" and blockers and not sensitive and not unclassified:
        reading = ("BLIND fired, and EVERY blocker is on the declared INJECTION-INVARIANT side — a "
                   "gate an injected CRPS effect cannot move. The honest statement is: the family's "
                   "statistical half demonstrably fires; the verdict was decided by measures no "
                   "injection can reach. ⛔ Neither a rescue nor a condemnation.")
    elif unclassified:
        reading = (f"blocking gate(s) {unclassified!r} are in NEITHER declared half — the partition "
                   "in `nf_inj2c_assignment_rule` no longer covers this gate set, so the control "
                   "cannot be read against it (NF1.7 (a): an unevaluable reading is not a pass).")
    # ⭐ AMENDMENT 1 §3 — the declaration is SCOPED, ⛔ not a blanket waiver. The §2 entailment
    # (ship ⇒ null-leg survivor ⇒ VACUOUS) covers a survivor set of NON-DEGENERATE arms: those are
    # the arms H1 predicts will clear. A DEGENERATE clearing every gate on the real payload is not
    # entailed by H1 and is a genuine alarm about the family, so the declaration does not reach it.
    null_survivors = list(rep.get("null_control_survivors") or [])
    degenerate_null_survivors = [a for a in null_survivors if a in C.DEGENERATE_ARMS]
    declaration_applies = (str(rep.get("verdict")) == "VACUOUS"
                           and not degenerate_null_survivors)
    return {
        **rep,
        "declared_partition": {"injection_sensitive": list(C.INJECTION_SENSITIVE_GATES),
                               "injection_invariant": list(C.INJECTION_INVARIANT_GATES)},
        "null_leg_declaration_applies": declaration_applies,
        "degenerate_null_survivors": degenerate_null_survivors,
        "blockers_on_invariant_side": invariant,
        "blockers_on_sensitive_side": sensitive,
        "blockers_unclassified": unclassified,
        "reading": reading,
        # ⚠️ MEASURED, ⛔ not asserted — and it REFUTES the pre-registration §7's premise, which is
        # recorded rather than worked around (NF-W7f: a premise a measurement refutes is part of the
        # record). §7's text stays VERBATIM in the pre-registration.
        "plat_cvp2_landed": _plat_cvp2_landed(),
        "preregistration_7_premise": (
            "§7 states PLAT-CVP2 'has not landed ... no CONSTRAINT_BLOCKED verdict and no "
            "injection-invariant-gate parameter'. MEASURED FALSE at this commit: `gate_classes=` "
            "and `invariant_gates=` both exist and `CONSTRAINT_BLOCKED` is a verdict. ⭐ SUPERSEDED "
            "BY MEASUREMENT — §7 is left UNEDITED; the control is driven by the DECLARED partition "
            "(which §7 itself declares), ⛔ not by the instrument's name heuristic. Using the "
            "parameter is not a relaxation: the partition is unchanged and was declared BEFORE the "
            "control ran, which is exactly the anti-laundering condition the instrument names."),
    }


def control_binding_verdict(control: dict) -> dict:
    """PRE-REGISTRATION AMENDMENT 1 §4 (b) — the control's BINDING substance, as a verdict.

    ⭐ THE DECLARATION RE-SCOPES THE CONTROL; IT NEVER WAIVES IT (PM ruling #6 D1, verbatim). The
    null leg's `VACUOUS` is declared inapplicable to this family, and the INJECTED leg becomes what
    binds — which cuts BOTH ways. Four ways the control FAILS, and a failure blocks the disposition
    regardless of any badge:

      F1  no arm clears every injection-MOVABLE gate (`metric_survivors` empty) — the planted effect
          was not detected, so a null from this family would be free.
      F2  a declared DEGENERATE is among the INJECTED leg's survivors — the family passes an arm
          registered to lose.
      F3  a declared DEGENERATE is among the NULL leg's survivors — amendment 1 §3's carve-out; an
          alarm H1 does not entail and the declaration does not reach.
      F4  the control did not run, or its record lacks the keys above — ⛔ never a pass (NF1.7 (a)).

    ⭐ `metric_survivors`, ⛔ not `survivors`, is the F1 reading: charging an arm stopped by an
    INJECTION-INVARIANT gate to the family's SENSITIVITY is PLAT-CVP2 defect 1 — the defect that
    earned NF-INJ2b's `BLIND` badge. An arm blocked only by a gate the injection cannot move has
    still demonstrated the family detected the effect.

    ⛔ This function can only REFUSE. There is no return value that makes a disposition easier to
    reach than the base registration made it, which is the property that makes an amendment written
    after a measurement admissible (amendment 1 §0).
    """
    required = ("metric_survivors", "survivors", "null_control_checked")
    missing = [k for k in required if k not in control]
    if missing:
        return {"state": "UNEVALUABLE", "failures": ["F4"], "why":
                f"the control record is missing {missing!r} — an unevaluable control is never a "
                "pass (NF1.7 (a) / amendment 1 §4 F4)", "checks": {}}
    if not control.get("null_control_checked"):
        return {"state": "UNEVALUABLE", "failures": ["F4"], "why":
                "the null leg did NOT run, so amendment 1 §3's degenerate carve-out could not be "
                "evaluated — and §5 forbids disabling it (E2.1-r). Never a pass (NF1.7 (a)).",
                "checks": {}}

    degen = set(C.DEGENERATE_ARMS)
    metric_survivors = list(control.get("metric_survivors") or [])
    injected_survivors = list(control.get("survivors") or [])
    null_survivors = list(control.get("null_control_survivors") or [])
    f1 = not metric_survivors
    f2 = sorted(a for a in injected_survivors if a in degen)
    f3 = sorted(a for a in null_survivors if a in degen)

    failures = (["F1"] if f1 else []) + (["F2"] if f2 else []) + (["F3"] if f3 else [])
    checks = {
        "F1_effect_detected": not f1,
        "F2_no_degenerate_survived_injection": not f2,
        "F3_no_degenerate_survived_null_leg": not f3,
        "metric_survivors": metric_survivors,
        "degenerate_injected_survivors": f2,
        "degenerate_null_survivors": f3,
    }
    if failures:
        why = "; ".join(filter(None, [
            ("F1 — NO arm cleared every injection-MOVABLE gate at an injected effect of "
             f"{control.get('effect_injected_crps')!r}: the family did not detect a planted effect "
             "of this size, so a null from it would be free (BLIND)." if f1 else ""),
            (f"F2 — degenerate(s) {f2} cleared EVERY gate on the INJECTED payload: the family "
             "passes an arm registered to lose." if f2 else ""),
            (f"F3 — degenerate(s) {f3} cleared EVERY gate on the NULL leg (the real payload). "
             "Amendment 1 §3 carves this out of the declaration explicitly: it is not entailed by "
             "H1 and is a genuine alarm about the gate family." if f3 else ""),
        ]))
        return {"state": "FAILS", "failures": failures, "why": why, "checks": checks}
    return {
        "state": "PASSES", "failures": [], "checks": checks,
        "why": (f"the injected leg detected the planted effect ({metric_survivors} cleared every "
                "injection-MOVABLE gate) and no declared degenerate survived either leg. ⛔ This is "
                "the control's binding substance under amendment 1 §4; the instrument's own badge "
                f"({control.get('verdict')!r}) is recorded verbatim beside it and does not bind."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The run
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, schema: str, folds: tuple[int, ...], selections: dict, *,
        base_from: int = C.BASE_FROM, board: dict | None = None) -> dict:
    """Score every fold, assemble M1–M6, and reach the pre-committed outcome.

    ⭐ ALL TEN NF-INJ2b arms are scored, because §2.4 requires the inherited field's DSR as a
    declared NON-BINDING diagnostic. The BINDING field is the five-arm subset, and every deflation
    statistic that binds is computed over it alone."""
    brd = board if board is not None else board_measures()
    per_fold: dict[str, dict[int, dict]] = {}
    fold_n: dict[int, int] = {}
    for y in folds:
        cap = RB.capture_fold(con, y, schema, selections, base_from=base_from)
        frames = {a: RB.arm_frame(cap, a) for a in B.ARMS}
        # ⭐ the ORACLES are DIAGNOSTIC ANCHORS, not trials — they are scored for the anchor audit
        # and are outside every declared field, so they can never reach `V` (MH2.1 (a): an anchor
        # that leaks into the trial field SETS the gate's own bar).
        frames.update(RB.oracle_arms(cap))
        for a, f in frames.items():
            per_fold.setdefault(a, {})[y] = R2.score_frame(f, cap["realized"], cap["mvp1_point"])
        fold_n[y] = int(per_fold[C.INCUMBENT_ARM][y]["n"] or 0)
        log.info("fold %d scored (n=%d) — %s", y, fold_n[y],
                 " ".join(f"{a}:{per_fold[a][y]['crps']}" for a in C.ARMS))

    keys = ("crps", "mae", "coverage80", "interval_score80", "bias", "rho_pooled",
            "tier_rho_pooled", "coherence_violating_players")
    scored = {a: {k: (round(float(np.mean([per_fold[a][y][k] for y in folds
                                           if per_fold[a][y].get(k) is not None])), 4)
                      if any(per_fold[a][y].get(k) is not None for y in folds) else None)
                  for k in keys}
              for a in per_fold}

    arm = C.PRIMARY_ARM
    measures = {
        "M1": m1_crps_lift(per_fold, folds, arm),
        "M2": m2_coherence(per_fold, folds, arm, brd),
        "M3": _board_measure(brd, arm, "M3"),
        "M4": _board_measure(brd, arm, "M4"),
        "M5": m5_ordering(per_fold, folds, arm),
        "M6": m6_interval_floor(per_fold, folds, arm),
    }
    defl = deflation_blocks(per_fold, folds, arm)
    coherence_counts = {a: int(scored[a]["coherence_violating_players"] or 0) for a in B.ARMS}
    control = positive_control(per_fold, folds, scored, coherence_counts, board=brd)
    control_binding = control_binding_verdict(control)
    dom = dominance_verdict(measures)
    vdt = verdict(dominance=dom, defl=defl, control=control, control_binding=control_binding,
                  fold_wins=int((measures["M1"] or {}).get("folds_won") or 0), folds=len(folds))

    return {
        "story": "NF-INJ2c node 4 — the decisive run on the STRICT-DOMINANCE route",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0, "deploy_held": True,
        "primary_arm": arm,
        "registration": {
            "binding_field": list(C.ARMS), "declared_field_size": C.DECLARED_FIELD_SIZE,
            "degenerates": list(C.DEGENERATE_ARMS), "reference": list(C.REFERENCE_ARMS),
            "excluded_rate_space": list(C.EXCLUDED_RATE_SPACE_ARMS),
            "diagnostic_field": list(C.DIAGNOSTIC_FIELD),
            "folds": list(folds), "base_from": base_from,
            "v_members_declared": [a for a in C.ARMS
                                   if a not in set(C.DEGENERATE_ARMS) | set(C.REFERENCE_ARMS)],
        },
        "node_3b_baseline": {k: brd[k] for k in
                             ("source", "generated_at", "reproduction_pin",
                              "served_incumbent_baseline", "bands")},
        "fold_n": fold_n,
        "scored": scored,
        "measures": measures,
        "dominance": dom,
        "deflation": defl,
        "anchors": RB.anchor_audit(scored, arm),
        "positive_control": control,
        "control_binding": control_binding,
        "verdict": vdt,
    }


def _board_measure(board: dict, arm: str, which: str) -> dict:
    """M3 / M4 — READ from node 3b, ⛔ never recomputed here (see the module docstring)."""
    rec = (board.get("arms") or {}).get(arm) or {}
    base = board.get("served_incumbent_baseline") or {}
    key = {"M3": "M3_worst_times_over", "M4": "M4_giveback_measure"}[which]
    precision = {"M3": C.M3_RECORDED_PRECISION, "M4": C.M4_RECORDED_PRECISION}[which]
    a, i = rec.get(key), base.get(key)
    if a is None or i is None:
        return {"evaluable": False,
                "why": f"node 3b's report carries no {key} for {arm!r} or for the incumbent — an "
                       "unevaluable measure is never a pass (NF1.7 (a))"}
    gain = float(i) - float(a)                       # lower is better ⇒ incumbent − arm
    return {
        "evaluable": True, "arm": a, "incumbent": i, "gain_lower_is_better": round(gain, 4),
        "tie_band": precision, "band_rule": "R2",
        "verdict": _r1_verdict(gain, precision, better="higher"),
        "source": "node 3b (BOARD measure — read, never recomputed)",
        "node_3b_reading": rec.get(f"{which}_verdict"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def write_report_md(rep: dict, path: Path) -> None:
    m, v, d = rep["measures"], rep["verdict"], rep["deflation"]
    L = [f"# NF-INJ2c node 4 — the decisive run ({v['state']})", "",
         "> ⛔ `best_alpha = 0`. Nothing serves; DEPLOY-HELD; `SERVED_ARM` stays "
         f"`{v['served_arm']}`. Bands are READ from `nf_inj2c_margin_construction_rule.md` "
         "(node 3a, BINDING, committed before the re-measure); ⛔ none is defined here.", "",
         f"Generated {rep['generated_at']}. Primary arm **`{rep['primary_arm']}`** — FIXED by the "
         "registration, ⛔ never selected as 'the best CRPS'.", "",
         "## 1. The verdict", "",
         f"**{v['state']}** — {v['branch']}", ""]
    L += ["| measure | what | band rule | verdict |", "|---|---|---|---|"]
    for k in ("M1", "M2", "M3", "M4", "M5", "M6"):
        spec = C.MEASURES[k]
        L.append(f"| {k} | {spec['what']} | {(m[k] or {}).get('band_rule', spec['band'])} "
                 f"| **{(m[k] or {}).get('verdict', 'UNEVALUABLE')}** |")
    L += ["", f"⭐ {rep['dominance']['rule']}", ""]
    L += ["## 2. The deflation gates", "",
          f"- BINDING field ({d['binding'].get('field_label')}): "
          f"DSR **{d['binding'].get('dsr_binding')}** vs {d['binding'].get('dsr_min')} · "
          f"PBO **{d['binding'].get('pbo')}** vs {d['binding'].get('pbo_max')} "
          f"(`pbo_application={d['binding'].get('pbo_application')}`)",
          f"- {C.DIAGNOSTIC_LABEL}: DSR **{d['diagnostic'].get('dsr_binding')}** — "
          "declared in advance, publishes either way, ⛔ cannot rescue a binding refusal",
          f"- fold consistency: {v['fold_wins']} of {len(rep['registration']['folds'])} wins vs "
          f"{v['fold_consistency_required_wins']} required (⛔ never the raw 0.60 rate — MH2 H8)",
          f"- field-trim 2×2: {d['lockstep_variance_lever'].get('field_trim_status')}", ""]
    if v["state"] == "DEFLATION_REFUSED":
        ls = d["lockstep_variance_lever"]
        L += ["### The lockstep variance lever, run BEFORE any remedy is named (NF-W8-0d)", "",
              f"- SR **{ls.get('sr')}** vs SR0 **{ls.get('sr0')}** · lever closed: "
              f"**{ls.get('lever_closed')}** · sign-invariant: **{ls.get('sign_invariant')}**",
              f"- 2026 fold trigger publishable: **{ls.get('fold_trigger_publishable')}** — "
              f"{ls.get('why')}", ""]
    pc = rep["positive_control"]
    cb = rep["control_binding"]
    L += ["## 3. The injected-effect positive control", "",
          "⭐ Read under **pre-registration amendment 1** (PM ruling #6 D1, 2026-09-05): the "
          "instrument's badge is recorded VERBATIM and does ⛔ NOT bind; the **INJECTED leg** is the "
          "control's binding substance, and it can still FAIL the study.", "",
          f"- **BINDING (amendment 1 §4): {cb.get('state')}**"
          + (f" — failures {cb.get('failures')}" if cb.get("failures") else ""),
          f"  - {cb.get('why')}",
          f"- instrument badge (recorded, ⛔ non-binding): **{pc.get('verdict')}**",
          f"- amendment 1 §3 declaration applies to this badge: "
          f"**{pc.get('null_leg_declaration_applies')}**"
          + (f" — degenerate null-leg survivors {pc.get('degenerate_null_survivors')} carve it out"
             if pc.get("degenerate_null_survivors") else ""),
          f"- blockers on the declared INVARIANT side: {pc.get('blockers_on_invariant_side')}; on "
          f"the SENSITIVE side: {pc.get('blockers_on_sensitive_side')}",
          f"- PLAT-CVP2 landed: **{pc.get('plat_cvp2_landed')}** · PLAT-CVP3 (the advantage-removed "
          "null construction) is the CARDED true fix; this study does not wait for it"]
    if pc.get("reading"):
        L += ["", f"⭐ {pc['reading']}"]
    L += ["", "## 4. The node-3b baseline this run reads", "",
          f"- source `{rep['node_3b_baseline']['source']}`, generated "
          f"{rep['node_3b_baseline']['generated_at']}",
          f"- reproduction pin: worst **{rep['node_3b_baseline']['reproduction_pin'].get('worst_abs_diff')}** "
          f"vs {rep['node_3b_baseline']['reproduction_pin'].get('tolerance')} ⇒ "
          f"**{rep['node_3b_baseline']['reproduction_pin'].get('reproduces')}**",
          "", "⛔ M3, M4 and M2's BASELINE are BOARD measures READ from that report, never "
          "recomputed here — a second computation of a committed baseline is a second answer to one "
          "question.", ""]
    path.write_text("\n".join(L))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2c node 4 — the decisive run")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--folds", default=None,
                    help="comma-separated; default = the SEVEN registered folds. ⛔ Re-cutting the "
                         "window is refused (PM ruling 2026-09-01) — this exists for a SMOKE only, "
                         "and a non-default value is stamped in the report as NOT the registration.")
    ap.add_argument("--base-from", type=int, default=C.BASE_FROM)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    import duckdb
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree does not carry the "
                         "gitignored artifact (NF-INFRA1); pass --duckdb with an absolute path.")
    con = duckdb.connect(args.duckdb, read_only=True)

    folds = (tuple(int(x) for x in args.folds.split(",")) if args.folds else C.FOLDS)
    selections = N15.load_selection(json.loads(RB._NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    rep = run(con, args.schema, folds, selections, base_from=args.base_from)
    # ⭐ A SMOKE WRITES ITS OWN STEM. A runner with a fixed output path clobbers a DECIDED story's
    # record on any partial re-run (NF-INJ3b-M D4, and the NF-W2c-CBS incident where a source-scoped
    # re-run silently overwrote the tracked full-source report). The decided stem is reachable ONLY
    # by the registered seven folds, so a code-path proof cannot be mistaken for the decisive run.
    smoke = tuple(folds) != tuple(C.FOLDS)
    stem = f"{_STEM}_smoke" if smoke else _STEM
    if smoke:
        rep["⚠️ SMOKE"] = (f"folds {list(folds)} are NOT the registered seven {list(C.FOLDS)} — this "
                           "run is a CODE-PATH proof, it reaches no verdict the record may quote, "
                           f"and it writes `{stem}` so it cannot clobber the decisive artifact")
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{stem}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_report_md(rep, _REPORT_DIR / f"{stem}.md")
    log.info("node 4 %s — %s", "SMOKE" if smoke else "complete",
             rep["verdict"]["state"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

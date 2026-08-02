"""h_harness.py — the shared §0.5 harness for the E7.15 round-2 slices (H1 ladder, H2 opponent, …).

E7.12 ran six slices and E7.15 runs four hypotheses against the SAME substrate, the SAME fold structure
and the SAME shipped foil. Everything that is genuinely mechanism-agnostic lives here exactly once —
the deflation reading, the anchor evaluation, the numeric gate, the propensity-tercile machinery and the
honest-null analysis — so a lesson learned in one slice cannot be half-applied in the next.

⭐ **WHAT IS SHARED AND WHAT IS NOT, AND WHY THE SEAM IS HERE.** The NUMERIC gate (does it beat the foil,
on enough folds, past PBO/DSR) is identical for every hypothesis and is shared. The ANCHORS are not: H1's
anchors ask "is this a level re-centring?" and "is the within-player link real?", H2's ask "is this the
opponent or any dispersed multiplier?" and "did the player inflate his own opponents?" — different
questions about different mechanisms. So anchors are DECLARED per slice as `Anchor` records and evaluated
by shared code. That keeps a slice from quietly shipping with fewer anchors than its predecessor while
still letting each slice ask its own question.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
    deflation_report,
    paired_anchor,
)
from betting_ml.utils.cv_power import (
    FOLD_CONSISTENCY_ALPHA,
    fold_consistency_clause,
    fold_gate_false_fire,
    folds_to_clear_dsr,
)

log = logging.getLogger("e7_15.harness")

# ── Pre-registered gate thresholds (readiness lock 1 + the §0.5 deflation contract) ────────────────
# ⚠️ **MH2/H8: THIS RATE IS RETAINED ONLY AS A REPORTED REFERENCE — IT IS NO LONGER THE CLAUSE.**
# `fold_win_rate ≥ 0.60` fires on a TRUE lift of ZERO 49.7% of the time at 3 folds and 27.4% at 11,
# i.e. its stringency is a side-effect of `n` rather than a property of the gate. `numeric_gate` now
# additionally requires `cv_power.fold_consistency_clause`, which holds the FALSE-FIRE RATE fixed and
# lets the required win COUNT move with `n`. The calibrated clause is weakly STRICTER at every fold
# count, so adopting it can only prevent a false ADD — verified against the stored record to
# re-decide none of the 8 ADDs on file (E7.12-S1/S2 all sit at 8–10 wins of 11 against a requirement
# of 8). See `ablation_results/mh2_cv_power_characterization.md` §6.
MIN_FOLD_WIN_RATE = 0.60
MAX_PBO = 0.20
MIN_DSR = 0.95
FDR_ALPHA = 0.10
MIN_PCT_ROWS_MOVED = 1.0

# DESCRIPTIVE, NOT DECISIVE. A high PBO means two completely different things and the verdict is DROP for
# both, but the RECORD is not the same: with the contenders inside this spread the field is TIED, and
# E2.1-r's reading applies — "no candidate robustly beats the incumbent ⇒ the incumbent's choice is now
# PROVEN, not assumed". With a WIDE spread the same PBO is genuine instability. The threshold changes no
# gate; it only stops the report from asking its reader to do the classification by hand (NF1.8).
TIE_CONTENDER_SPREAD_PCT = 0.5


# ══════════════════════════════════════════════════════════════════════════════════════
# Anchors — declared per slice, evaluated once
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Anchor:
    """One thing that must hold, or the slice cannot be believed.

    `kind`:
      * `noop`   — this arm must be a BYTE no-op against the foil. It guards the PLUMBING: if the
                   transform's own code path moves the answer when its parameters are neutral, every
                   arm's margin is confounded with the machinery. A violation BLOCKS.
      * `block`  — this arm must LOSE, and its winning invalidates the METRIC (a degenerate ceiling
                   beating a real candidate means the selection metric is inverted — NF-D11). BLOCKS.
      * `refute` — this arm must LOSE, and its winning invalidates the MECHANISM's stated story without
                   condemning the metric (NF-D15 g′). DROPS.

    ⭐ **`defender` SCOPES A REFUTATION TO ONE MECHANISM — and getting this wrong vetoes innocent arms
    (the NF-D16 (g‴) shape, one instrument over).** A `refute` anchor with `defender=None` defends
    whatever arm is currently winning, so its violation is a statement about the slice's SELECTION and
    correctly DROPS the metric. A `refute` anchor with an EXPLICIT `defender` is a matched foil for ONE
    named mechanism (E7.15 H3's shuffled player grouping foils the random intercept, and nothing else) —
    so its violation must disqualify **only that arm**, never a structurally unrelated candidate that
    happens to share the metric. A single field-wide veto would fail exactly as NF-D16's single peeking
    ceiling did: it would reject a legitimately-better arm for another mechanism's sin. Scoped
    refutations are reported in `refuted_arms`; the caller must drop those arms from selection.
    """

    label: str
    kind: str
    what: str                    # short human name, used in the reason text
    why: str                     # what a VIOLATION means — written before the run
    defender: str | None = None  # what it must not beat; None ⇒ the best eligible arm (field-wide veto)
    # ⭐ Does this anchor TRANSFORM the feature? If so it must demonstrably MOVE rows, or it is inert and
    # its "it lost" is a pass on nothing. A degenerate-PROJECTOR anchor legitimately moves no feature, so
    # this is opt-in rather than assumed.
    must_move: bool = True

    def __post_init__(self):
        if self.kind not in ("noop", "block", "refute"):
            raise ValueError(f"kind={self.kind!r} not in ('noop', 'block', 'refute')")


def evaluate_anchors(mae: pd.DataFrame, anchors: tuple[Anchor, ...], best: str, foil: str,
                     coverage: dict | None = None) -> tuple[dict, str | None, str | None]:
    """Evaluate every anchor. Returns `(report, blocking_verdict_or_None, reason_or_None)`.

    🪤 **NF1.7 (a): AN ANCHOR THAT DID NOT RUN IS NOT AN ANCHOR THAT PASSED — IN TWO WAYS.**

    1. **ABSENT.** The arm is missing from the run entirely. Enumerated and treated as a hard failure.
    2. **INERT.** ⭐ **The arm RAN but its transform moved NOTHING**, so it is byte-identical to the foil
       and "it lost" is a pass on nothing. This is the worse case because it looks like a healthy result.
       It is not hypothetical: E7.15 H2's first cut disabled its own SELF-INFLATION anchor this way — a
       column-name mismatch made the non-LOO factor fall back to 1.0, the arm silently became the foil,
       and the check reported `violated=False`. The most load-bearing anchor in the slice was passing on
       nothing while the report said it held. `coverage` supplies `pct_rows_moved` per arm; an anchor
       declared `must_move` that moved ~0% BLOCKS.
    """
    missing = [a.label for a in anchors if a.label not in mae.columns]
    out: dict = {"required_anchors_present": not missing, "missing_anchors": missing,
                 "best_arm": best, "foil": foil}
    for a in anchors:
        if a.kind == "noop":
            gap = (float(np.nanmax(np.abs((mae[a.label] - mae[foil]).to_numpy(float))))
                   if a.label in mae.columns and foil in mae.columns else np.nan)
            out[f"{a.label}__max_abs_gap"] = gap
            out[f"{a.label}__is_a_noop"] = bool(np.isfinite(gap) and gap < 1e-9)
        else:
            out[f"{a.label}__vs_{a.defender or 'best'}"] = paired_anchor(
                mae, a.label, a.defender or best)
        if a.label in mae.columns:
            out[f"{a.label}__mae"] = float(mae[a.label].mean(skipna=True))

    if missing:
        return out, "BLOCKED", (
            f"⛔ BLOCKED — required anchor(s) {missing} are ABSENT from this run. An anchor that did not "
            f"run is not an anchor that passed (NF1.7 (a)); nothing may ship without them.")

    inert = [a.label for a in anchors
             if a.must_move and a.kind != "noop"
             and float(((coverage or {}).get(a.label) or {}).get("pct_rows_moved") or 0.0)
             <= MIN_PCT_ROWS_MOVED]
    out["inert_anchors"] = inert
    if coverage is not None and inert:
        return out, "BLOCKED", (
            f"⛔ BLOCKED — anchor(s) {inert} RAN but moved ≤{MIN_PCT_ROWS_MOVED}% of rows, i.e. they are "
            f"byte-identical to the foil. Their 'it lost' is a pass on NOTHING (NF1.7 (a)) — an inert "
            f"anchor is more dangerous than a missing one because the report looks healthy. Fix the "
            f"anchor before reading any verdict from this run.")

    for a in anchors:
        if a.kind == "noop" and not out[f"{a.label}__is_a_noop"]:
            return out, "BLOCKED", (
                f"⛔ BLOCKED — `{a.label}` ({a.what}) is NOT a byte no-op vs the foil "
                f"(max |Δ| = {out[f'{a.label}__max_abs_gap']:.3e}). {a.why}")
    # SCOPED refutations first — they disqualify their own defender, they do not veto the metric.
    refuted: dict[str, str] = {}
    for a in anchors:
        if a.kind != "refute" or not a.defender:
            continue
        res = out[f"{a.label}__vs_{a.defender}"]
        if res.get("violated"):
            refuted[a.defender] = (
                f"`{a.label}` ({a.what}) systematically beat `{a.defender}` "
                f"({res['challenger_fold_wins']}/{res['n_folds']} folds, "
                f"p={res['p_challenger_better']:.3f}). {a.why}")
    out["refuted_arms"] = refuted

    for a in anchors:
        if a.kind == "noop" or (a.kind == "refute" and a.defender):
            continue
        res = out[f"{a.label}__vs_{a.defender or 'best'}"]
        if not res.get("violated"):
            continue
        head = "⛔ BLOCKED" if a.kind == "block" else "⛔ MECHANISM REFUTED"
        return out, ("BLOCKED" if a.kind == "block" else "DROP"), (
            f"{head} — `{a.label}` ({a.what}) systematically beat "
            f"`{a.defender or best}` ({res['challenger_fold_wins']}/{res['n_folds']} folds, "
            f"p={res['p_challenger_better']:.3f}). {a.why}")
    return out, None, None


# ══════════════════════════════════════════════════════════════════════════════════════
# Deflation
# ══════════════════════════════════════════════════════════════════════════════════════


def dsr_report(mae: pd.DataFrame, eligible: list[str], foil: str = "L0_foil") -> dict:
    """Deflated Sharpe on the winner's per-fold SKILL series, reported over BOTH trial fields.

    ⭐ **NF-D14: A DEFLATION STATISTIC COMPUTED OVER A FIELD CONTAINING ITS OWN NULLS MEASURES THE
    NULLS.** `deflated_sharpe`'s expected-max term scales with the cross-trial Sharpe DISPERSION, and a
    §0.5 field deliberately contains anchors that are far away by construction. So the ELIGIBLE-set
    figure is the one PRE-REGISTERED to bind and the whole-field figure is reported beside it; if both
    clear, nothing turns on the choice, which is the clean shape.
    """
    from betting_ml.utils.overfitting import deflated_sharpe

    if foil not in mae.columns:
        return {"available": False, "note": f"no {foil} column — DSR undefined"}
    skill = pd.DataFrame(mae[[foil]].to_numpy(float) - mae.to_numpy(float),
                         index=mae.index, columns=mae.columns)

    def _sr(s: np.ndarray) -> float:
        s = s[np.isfinite(s)]
        return float(np.mean(s) / np.std(s, ddof=1)) if len(s) > 2 and np.std(s, ddof=1) > 0 else 0.0

    out: dict = {"available": True}
    for tag, cols in (("eligible", [c for c in eligible if c in skill.columns and c != foil]),
                      ("whole_field", [c for c in skill.columns if c != foil])):
        if not cols:
            out[tag] = None
            continue
        best = str(skill[cols].mean(axis=0, skipna=True).idxmax())
        series = skill[best].to_numpy(float)
        series = series[np.isfinite(series)]
        if len(series) < 3 or np.std(series) == 0:
            out[tag] = {"arm": best, "dsr": None, "note": "too few folds / zero variance"}
            continue
        res = deflated_sharpe(series, n_trials=len(cols),
                              trial_sharpes=[_sr(skill[c].to_numpy(float)) for c in cols])
        out[tag] = {"arm": best, "n_trials": len(cols), "dsr": float(res.dsr),
                    "observed_sr": float(res.observed_sr), "sr0": float(res.sr0),
                    "passes": bool(res.dsr >= MIN_DSR)}
    out["binds"] = "eligible"
    return out


def pbo_reading(defl: dict) -> tuple[bool, str]:
    """Classify a high PBO as a TIE or as INSTABILITY, and say which. Returns `(is_tie, sentence)`.

    A rank statistic cannot tell "my pick is unstable" from "my pick is tied" (NF1.8), and the verdict is
    DROP either way — but the RECORD differs, and leaving that classification to the report's reader is
    how the E2.1-r reading gets lost.
    """
    spread = defl.get("contender_spread_pct")
    flips = defl.get("flips") or []
    top = ", ".join(f"{f['config']} {f['share']:.0%} (+{f['pct_vs_best']:.3f}%)" for f in flips[:3])
    tie = spread is not None and float(spread) < TIE_CONTENDER_SPREAD_PCT
    if tie:
        return True, (
            f"⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is {spread}% and the "
            f"in-sample halves split across arms a fraction of a percent apart ({top}). Which tied arm "
            f"wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest "
            f"record is 'no candidate robustly beats the shipped configuration', so the shipped "
            f"configuration is now PROVEN rather than assumed.")
    return False, (
        f"The contender spread is {spread}%, WIDE relative to the margin, and the in-sample winners are "
        f"spread thinly ({top}) — this is genuine instability, a search that learnt nothing, not a tie "
        f"(NF1.8).")


def numeric_gate(cand: pd.Series, foil_mae: float, defl: dict, dsr: dict,
                 mechanism: str, n_folds: int | None = None) -> tuple[bool, str | None]:
    """The gate every slice shares: beats the foil, on enough folds, past PBO and DSR.

    Returns `(passed, failure_reason_or_None)`. Anchors and the tercile read are the CALLER's, because
    they are the parts that genuinely differ per hypothesis.

    ⭐ **MH2/H8 — THE FOLD CLAUSE IS NOW CALIBRATED, NOT A FIXED RATE.** `n_folds` (when supplied)
    activates `cv_power.fold_consistency_clause`: the required WIN COUNT is the smallest `k` whose
    null probability `P(Bin(n,½) ≥ k)` is ≤ 0.20, so the clause's false-fire rate is bounded at every
    fold count instead of drifting from 0.50 (n=3) to 0.27 (n=11). Two consequences worth stating in
    the failure text rather than burying: (1) the clause can be **UNATTAINABLE** at very low fold
    counts, and an unattainable clause is UNDEFINED, not passed — the same honesty `deflation_report`
    already applies to CSCV; (2) it is weakly stricter than the legacy rate everywhere, so it can
    only prevent a false ADD. `n_folds=None` preserves the legacy behaviour exactly, so an existing
    caller that has not been updated cannot silently change its own verdicts.
    """
    beats = bool(cand["oos_mae"] < foil_mae - 1e-12)
    consistent = bool(np.isfinite(cand["fold_win_rate"])
                      and cand["fold_win_rate"] >= MIN_FOLD_WIN_RATE)
    clause_note = ""
    if n_folds:
        cl = fold_consistency_clause(int(n_folds), FOLD_CONSISTENCY_ALPHA)
        wins = int(round(float(cand["fold_win_rate"]) * int(n_folds)))
        if not cl.attainable:
            return False, (
                f"⛔ UNDEFINED — at {n_folds} folds the smallest attainable fold-sign false-fire "
                f"rate is 2^-{n_folds} = {0.5 ** int(n_folds):.4f} > α={FOLD_CONSISTENCY_ALPHA}, so "
                f"NO win count makes the consistency clause meaningful. The legacy "
                f"`≥{MIN_FOLD_WIN_RATE:.0%}` bar would have fired here on a true lift of zero "
                f"{fold_gate_false_fire(int(n_folds)):.1%} of the time. This is a statement about "
                f"the DESIGN, not the mechanism — not a failed gate (MH2/H8).")
        consistent = consistent and wins >= cl.wins_required
        clause_note = (f"; calibrated clause needs {cl.wins_required}/{n_folds} at "
                       f"α={FOLD_CONSISTENCY_ALPHA} (got {wins}; the legacy "
                       f"≥{MIN_FOLD_WIN_RATE:.0%} bar would fire "
                       f"{cl.legacy_false_fire:.1%} of the time on a NULL)")
    if not (beats and consistent):
        return False, (
            f"🟡 no arm clears: best eligible `{cand['arm']}` MAE {cand['oos_mae']:.5f} vs foil "
            f"{foil_mae:.5f} ({cand['pct_lift_vs_foil']:.2f}%, fold win rate "
            f"{cand['fold_win_rate']:.0%}; the pre-registered bar is a strict OOS improvement in "
            f"≥{MIN_FOLD_WIN_RATE:.0%} of folds{clause_note}). DROPPED.")
    pbo = defl.get("pbo")
    if not (pbo is None or float(pbo) < MAX_PBO):
        _tie, sentence = pbo_reading(defl)
        return False, (f"⛔ DEFLATION — PBO over the ELIGIBLE set is {float(pbo):.3f} ≥ {MAX_PBO}. "
                       f"{sentence} Either way it does not ship.")
    d = (dsr or {}).get("eligible") or {}
    if not (d.get("dsr") is None or bool(d.get("passes"))):
        return False, (
            f"⛔ DEFLATION — DSR over the eligible trial set is {d.get('dsr'):.3f} < {MIN_DSR} "
            f"(n_trials={d.get('n_trials')}). State the shortfall in the unit that GROWS — folds and "
            f"seasons, not p-decimals — before recording this as an absence (NF-D15 g″).")
    return True, (
        f"✅ `{cand['arm']}` beats the shipped configuration OOS ({cand['oos_mae']:.5f} vs "
        f"{foil_mae:.5f}, {cand['pct_lift_vs_foil']:.2f}%) in {cand['fold_win_rate']:.0%} of folds, "
        f"PBO(eligible)={pbo}, DSR(eligible)={d.get('dsr')} [{mechanism}].")


# ══════════════════════════════════════════════════════════════════════════════════════
# H5 — the per-propensity-tercile read
# ══════════════════════════════════════════════════════════════════════════════════════


def stratified_lift(rows: pd.DataFrame, reference: str = "L0_foil",
                    moved_only: bool = False) -> pd.DataFrame:
    """Held-out MAE by promotion-propensity TERCILE, per arm (H5). Stratum 0 = LOWEST propensity.

    ⭐ **`moved_only` RESTRICTS TO ROWS THE MECHANISM CAN ACTUALLY ACT ON, AND ON THIS POPULATION THAT
    IS THE DIFFERENCE BETWEEN A READING AND A DILUTION.** A row the transform leaves untouched
    contributes exactly zero lift by construction. Measured on the scored population
    (`propensity_composition`), only ~48% of the LOW-propensity tercile's rows are movable by the H1
    ladder against ~61% of the high tercile — so an all-rows tercile read dilutes the low end HARDEST,
    which is the exact end the H5 gate is about. Same class as the NF1.8 "a per-group constraint
    evaluated on a quietly different population than the one it names" lesson.
    """
    if rows.empty or "stratum" not in rows.columns:
        return pd.DataFrame()
    if moved_only:
        if "moved" not in rows.columns:
            return pd.DataFrame()
        movable = set(map(tuple, rows.loc[rows["moved"], ["fold", "player_id", "level"]]
                          .drop_duplicates().to_numpy()))
        if not movable:
            return pd.DataFrame()
        keys = list(map(tuple, rows[["fold", "player_id", "level"]].to_numpy()))
        rows = rows[[k in movable for k in keys]]
    ref = (rows[rows["arm"] == reference]
           .set_index(["fold", "player_id", "level"])["abs_err"].rename("ref_err"))
    ref = ref[~ref.index.duplicated()]
    out = []
    for arm, d in rows.groupby("arm"):
        j = d.set_index(["fold", "player_id", "level"]).join(ref, how="inner")
        for s, ds in j.dropna(subset=["stratum"]).groupby("stratum"):
            base_mae = float(ds["ref_err"].mean())
            out.append({"arm": arm, "stratum": int(s), "n": int(len(ds)),
                        "mae": float(ds["abs_err"].mean()),
                        "pct_lift_vs_foil": (100.0 * float((ds["ref_err"] - ds["abs_err"]).mean())
                                             / base_mae if base_mae else np.nan)})
    return pd.DataFrame(out)


def propensity_composition(rows: pd.DataFrame, foil: str = "L0_foil") -> pd.DataFrame:
    """⚠️ **WHAT THE PROPENSITY TERCILE ACTUALLY CONTAINS — published so nobody re-reads it as what it
    is not.**

    E7.12 slice 2 introduced these terciles as "the only observable proxy for the un-promoted prospects
    we serve", and E7.15 H1 inherited that reading. On the scored LABELLED cohort it runs the other way:
    the LOW-propensity tercile is the one RICHEST in Triple-A rows (36.4% batter / 40.4% pitcher, vs
    21.0% / 17.0% in the high tercile) and POOREST in Single-A (4.3% / 10.4% vs 25.2% / 24.8%). It
    selects late-arriving graduates, not low-level prospects. The stratification is real and stable; the
    INTERPRETATION attached to it was never checked against the level mix.

    So the level mix is reported beside every tercile table. A per-group read whose group composition is
    unstated is a per-group read of something else.
    """
    if rows.empty or "stratum" not in rows.columns or "level" not in rows.columns:
        return pd.DataFrame()
    d = rows[rows["arm"] == foil].dropna(subset=["stratum"])
    if d.empty:
        return pd.DataFrame()
    ct = pd.crosstab(d["stratum"], d["level"], normalize="index").mul(100.0).round(1)
    ct.insert(0, "n_rows", d.groupby("stratum").size())
    if "moved" in rows.columns:
        mv = (rows[rows["arm"] != foil].dropna(subset=["stratum"])
              .groupby("stratum")["moved"].mean().mul(100.0).round(1))
        ct.insert(1, "pct_rows_the_mechanism_can_move", mv)
    return ct.reset_index()


def low_tercile_read(stratified: pd.DataFrame, stratified_moved: pd.DataFrame,
                     best: str) -> tuple[float, float]:
    """`(gated_low_tercile_lift, all_rows_low_tercile_lift)` for `best`. The GATE reads the moved view;
    the all-rows figure is published beside it, because changing which population a gate reads without
    showing both is how a gate quietly starts measuring something else."""
    def _low(frame: pd.DataFrame) -> float:
        if frame.empty:
            return np.nan
        r = frame[(frame["arm"] == best) & (frame["stratum"] == 0)]
        return float(r["pct_lift_vs_foil"].iloc[0]) if len(r) else np.nan

    low_all, low = _low(stratified), _low(stratified_moved)
    return (low_all if not np.isfinite(low) else low), low_all


# ══════════════════════════════════════════════════════════════════════════════════════
# Reading a null honestly (NF-D15 g″) — computed, not asserted
# ══════════════════════════════════════════════════════════════════════════════════════


def null_analysis(results: dict, pvals: dict, foil: str = "L0_foil") -> dict:
    """⭐ **TWO DISCIPLINES THAT SEPARATE AN HONEST NULL FROM A SHRUG** (NF-D15 g″), both computed here
    rather than argued in prose:

    **(a) PROVE THE NULL DOES NOT REST ON YOUR OWN GATE CHOICE.** Re-decide the whole run with the
    deflation gates REMOVED — no PBO ceiling, no DSR floor — and report who survives. If the answer is
    still "nobody", the binding constraint is elsewhere and the null is a property of the data, not of a
    threshold this session picked. If a metric only dies at DSR, that must be said plainly.

    **(b) STATE THE MARGIN IN THE UNIT THAT GROWS.** For each metric whose best arm is positive but
    undetectable, solve for the number of held-out DEBUT COHORTS at which the observed per-fold effect
    would clear the strictest BH rung and the DSR floor — holding the effect size fixed. Folds here ARE
    seasons (one per MLB debut cohort), so the answer is a calendar date, which is what makes it an
    actionable re-test trigger instead of a p-decimal.

    ⚠️ And the distinction the same lesson insists on: a best arm that does NOT beat the foil on average
    is a **GENUINE ABSENCE** — no sample size rescues a negative point estimate — not an underpowered
    effect. The two must not be recorded as the same kind of null.

    🪤 **THE EXTRAPOLATION MUST BE COMPUTED AGAINST THE GATE IT CLAIMS TO EXTRAPOLATE (E7.15 H3, found
    2026-08-01 while reading a live result).** `folds_needed_DSR` originally called `deflated_sharpe`
    WITHOUT `trial_sharpes`, while the gate (`dsr_report`) passes the real per-arm Sharpe series. Those
    are two different benchmarks: `sr0` scales with the cross-trial Sharpe DISPERSION, so omitting it
    silently substitutes an easier bar. Live consequence — batter `bb_pct` reported "needs 11 folds,
    already has 11, **0 extra seasons**" against a gate reading **DSR 0.607 vs the 0.95 floor**, i.e.
    the null analysis said an arm was on the doorstep when it was not close. A diagnostic that reports
    on a quantity it is not actually measuring is the session's recurring shape, one instrument over.
    **The dispersion is a property of the FIELD, not of n**, so it is held fixed while only the winner's
    series is resized — which is exactly the "holding the effect size fixed" logic already stated above.
    Pinned by `test_null_analysis_extrapolation_matches_its_own_gate`.
    """
    from scipy import stats

    m_family = len([m for m, r in results.items()
                    if not r.leaderboard[r.leaderboard["selectable"]
                                         & r.leaderboard["active"]].empty])
    strictest_bh = FDR_ALPHA / m_family if m_family else FDR_ALPHA
    rows, survivors = [], []
    for m, r in results.items():
        sel = r.leaderboard[r.leaderboard["selectable"] & r.leaderboard["active"]]
        if sel.empty:
            rows.append({"metric": m, "arm": None,
                         "kind": "no active arm — the mechanism cannot act on this metric"})
            continue
        cand = sel.iloc[0]
        mae = r.mae_by_fold
        skill = (mae[foil] - mae[str(cand["arm"])]).dropna().to_numpy(float)
        n = len(skill)
        # ⭐ the SAME trial field the DSR gate used, so the extrapolation extrapolates THAT gate and not
        # an easier one (see the docstring). The dispersion is a property of the field, not of n.
        eligible_arms = [str(a) for a in r.leaderboard.loc[r.leaderboard["selectable"], "arm"]
                         if str(a) in mae.columns and str(a) != foil]
        trial_sharpes = []
        for c in eligible_arms:
            s = (mae[foil] - mae[c]).dropna().to_numpy(float)
            sd = float(np.std(s, ddof=1)) if len(s) > 2 else 0.0
            trial_sharpes.append(float(np.mean(s) / sd) if sd > 0 else 0.0)
        beats = bool(cand["oos_mae"] < float(mae[foil].mean()) - 1e-12)
        consistent = bool(cand["fold_win_rate"] >= MIN_FOLD_WIN_RATE)
        fdr_ok = bool(pvals.get(m) is not None and pvals[m] <= strictest_bh)
        if beats and consistent and fdr_ok:
            survivors.append(m)
        need_fdr = need_dsr = None
        kind = "underpowered"
        if not beats or n < 3 or float(np.std(skill, ddof=1)) == 0 or float(np.mean(skill)) <= 0:
            kind = "genuine absence — the best arm does not beat the foil on average"
        else:
            t_obs = float(np.mean(skill) / (np.std(skill, ddof=1) / np.sqrt(n)))
            need_fdr = next((k for k in range(n, 4001)
                             if float(stats.t.sf(t_obs * np.sqrt(k / n), df=k - 1)) <= strictest_bh),
                            None)
            # 🪤 **THE THIRD DEFECT IN THIS EXTRAPOLATION (MH2, 2026-08-02) — `np.resize` DOES NOT
            # HOLD THE EFFECT SIZE FIXED, though the docstring above says it does.** Resizing TILES
            # the series; tiling preserves the population SD but the Sharpe is computed with
            # `ddof=1`, so the resized Sharpe is inflated by ≈√(n/(n−1)) — 4.9% at n=11 — and the
            # partial final tile makes the inflation NON-MONOTONE in k, so `next(...)` can stop
            # early on a wobble rather than at the true crossing. Measured on the live record:
            # E7.15-H3 `bb_pct` recorded 140 folds where the honest answer is 372, i.e. every
            # re-test trigger this function produced was OPTIMISTIC. `cv_power.folds_to_clear_dsr`
            # is the closed-form solution of the SAME gate — `n` enters the DSR statistic only
            # through √(n−1), so the crossing has an exact expression and no search is needed. It
            # also returns None for the RIGHT reason (`SR ≤ SR0` ⇒ unreachable at any n), which the
            # old search could only discover by exhausting its horizon.
            rc, sd0 = skill - skill.mean(), float(np.std(skill, ddof=0))
            _sk = float((rc ** 3).mean() / sd0 ** 3) if sd0 > 0 else 0.0
            _ku = float((rc ** 4).mean() / sd0 ** 4) if sd0 > 0 else 3.0
            # …and the branch matters: `deflated_sharpe` uses the MEASURED cross-trial dispersion
            # when ≥2 trial Sharpes exist (a field constant, held fixed) and otherwise falls back to
            # the asymptotic `1/n_obs`, which genuinely shrinks as folds accrue. Extrapolate the
            # branch the gate actually took, not the convenient one.
            _measured = len(trial_sharpes) > 1
            need_dsr = folds_to_clear_dsr(
                observed_sr=float(np.mean(skill) / np.std(skill, ddof=1)),
                n_trials=max(2, len(eligible_arms) or len(sel)),
                var_trials_sr=(float(np.var(trial_sharpes, ddof=1)) if _measured else 1.0 / n),
                skew=_sk, kurt=_ku, confidence=MIN_DSR, max_folds=4000,
                n_obs_now=n, var_is_asymptotic_fallback=not _measured)
        rows.append({
            "metric": m, "arm": str(cand["arm"]),
            "pct_lift_vs_foil": round(float(cand["pct_lift_vs_foil"]), 4),
            "fold_win_rate": float(cand["fold_win_rate"]), "p_one_sided": pvals.get(m),
            "beats_foil": beats, "clears_fold_bar": consistent,
            "clears_PBO": bool(r.deflation.get("pbo") is None
                               or float(r.deflation["pbo"]) < MAX_PBO),
            "clears_DSR": bool(((r.dsr or {}).get("eligible") or {}).get("passes")),
            "clears_BH_rank1": fdr_ok, "kind": kind,
            "folds_have": n, "folds_needed_BH": need_fdr, "folds_needed_DSR": need_dsr,
            # 🪤 **AN `or 0` COLLAPSES "UNREACHABLE" INTO "ALREADY SATISFIED" — the SECOND defect in this
            # function, and the direct consumer of the first (E7.15 H3, 2026-08-01).** `max(need_fdr or 0,
            # need_dsr or 0)` treats a None (the gate is NOT reachable within the search horizon) as a
            # requirement of ZERO folds, so the answer silently reports only the OTHER gate. Live: batter
            # `woba` read "+21 seasons" — implying a 2047 re-test would clear — while its DSR requirement
            # was UNREACHABLE at any n, i.e. more seasons will never fix it. It also inverted the ranking:
            # "+21" looked NEARER than `bb_pct`'s honest "+129" when woba is strictly worse. A shortfall
            # is only a re-test trigger if EVERY gate it must clear is reachable, so an unreachable
            # constituent must propagate, and WHICH gate is unreachable must be named.
            "unreachable_gates": [g for g, v in (("BH-FDR", need_fdr), ("DSR", need_dsr))
                                  if kind == "underpowered" and v is None],
            "extra_seasons_needed": (
                None if (kind != "underpowered" or need_fdr is None or need_dsr is None)
                else max(need_fdr, need_dsr) - n),
        })
    return {
        "family_size": m_family, "strictest_bh_cutoff": round(strictest_bh, 4),
        "survivors_with_PBO_and_DSR_gates_REMOVED": survivors,
        "binding_constraint": ("BH-FDR multiplicity — no arm's p clears the strictest rung, so removing "
                               "the deflation gates changes nothing" if not survivors else
                               "the deflation gates — at least one arm would ship without them"),
        "per_metric": rows,
    }


__all__ = [
    "Anchor", "evaluate_anchors", "dsr_report", "pbo_reading", "numeric_gate",
    "fold_consistency_clause", "FOLD_CONSISTENCY_ALPHA",
    "stratified_lift", "propensity_composition", "low_tercile_read", "null_analysis",
    "deflation_report", "MIN_FOLD_WIN_RATE", "MAX_PBO", "MIN_DSR", "FDR_ALPHA",
    "MIN_PCT_ROWS_MOVED", "TIE_CONTENDER_SPREAD_PCT",
]

"""run_mh2_2.py — MH2.2: E7.15-H3's TRAJECTORY family, re-run as its OWN pre-registered field.

⚠️ **OPERATOR-RUN (>2 min).** 7 arms × the side's metrics × 11 leave-one-debut-cohort-out folds. Much
cheaper than H3 (no random-intercept arms, which were the ~600–1,050-column penalized fits), but still
past the 2-minute bar on the full metric set.

    uv run python -m betting_ml.scripts.milb_mle.run_mh2_2
    uv run python -m betting_ml.scripts.milb_mle.run_mh2_2 --player-type pitcher

WHAT IT DECIDES, AND WHAT IT RETIRES
------------------------------------
E7.15-H3 recorded its trajectory arms as "a REAL effect that FAILED DSR at 0.607 over the 7-arm field
and **CLEARS at 0.998** over the 2-arm trajectory family". MH2 reproduced both and found the 2-arm
field to be **POST-HOC**: H3's own pre-registration names THREE trajectory arms (`T1_traj_ladder`,
`T2_traj_raw`, `T3_tenure`) and the 0.998 drops `T3_tenure` — *the arm that lost*.

⛔ **You get to pre-register a family; you do not get to discover one.** Trimming a field after the
fact is the second layer of the very selection bias DSR exists to deflate, and it is not a small
correction here: dropping `T3_tenure` collapses the cross-trial Sharpe DISPERSION by ~20,000× on
`bb_pct`, and that channel — not multiplicity — is what buys the 0.998 (`--report` prints the
`decompose_field_size` split).

So this module scores the **3-arm family as declared**, and its deliverable is a formally
pre-registered verdict closing the E7.15/E7.17 trajectory lineage. **The expected outcome is a
recorded NULL**, written down in `mh2_2_preregistration.md` before anything here was run.

THE FIVE LOCKS, AND WHERE EACH ONE IS ENFORCED IN CODE
------------------------------------------------------
1. **No arm is dropped for losing.** `TRAJECTORY_FAMILY` carries `T3_tenure`; `_assert_declared_field`
   raises if the scored field is not exactly the declared one.
2. **Mechanisms are split.** Only the trajectory arms are scored — the player-structure family
   (`P1`/`P2`/`P3`/`P4`) keeps H3's verdict. The pitcher side's largest H3 lift (`k_pct` +1.713%) is
   `P4_re_dedup`, i.e. PLAYER STRUCTURE, and crediting trajectory with it would mis-attribute the
   result. Batter and pitcher are reported as separate verdicts and never pooled.
3. **The bar is stated in advance**, in per-fold Sharpe (`cv_power.dsr_required_sr`) rather than as
   "DSR ≥ 0.95", and the shortfall in the unit that grows (`folds_to_clear_dsr`).
4. **`xwoba_against` is INACTIVE, declared up front** — a Triple-A-only Statcast feature has zero
   within-player transitions for a trajectory delta to act on. It is excluded from the BH-FDR family:
   a metric no arm can move is not a hypothesis that was tested.
5. **Anchors as H3 declared them**, minus `A_re_shuffled` — see `MH2_2_ANCHORS`.

⭐ **THE REPRODUCTION ANCHOR (`--check-reproduction`, on by default).** A re-scored field is a
legitimate *re-reading of the same evidence* only if the evidence is byte-identical. This asserts the
freshly-fitted per-fold MAE matches E7.15-H3's recorded matrix for every shared arm; if it does not,
the deflation comparison is between two different runs and the whole argument collapses.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.h_harness import (  # noqa: E402
    FDR_ALPHA,
    MIN_DSR,
    Anchor,
    null_analysis,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES, SideConfig, bh_fdr  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_15_h3 import _BY_LABEL, H3Arm, H3Result, run_h3  # noqa: E402
from betting_ml.utils.cv_power import (  # noqa: E402
    classify_null,
    decompose_field_size,
    dsr_ceiling,
    dsr_required_sr,
    fold_consistency_clause,
    folds_to_clear_dsr,
)
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_ladder_results,
    insert_design_block,
)

log = logging.getLogger("mh2_2")

_ART = (_PROJECT_ROOT
        / "quant_sports_intel_models/baseball/edge_program/ablation_results/mh2_2_artifacts")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_H3_ART = (_PROJECT_ROOT
           / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")

FOIL = "L0_foil"

# ── 🔒 LOCK 1: THE FAMILY, DECLARED. `T3_tenure` is HERE BECAUSE IT LOST LAST TIME. ───────────────
# The mechanism is "a player's PATH through the minors, which the aggregated final-level box line
# erases". `T1`/`T2` read the RATE delta between consecutive levels; `T3` reads the TIME and level
# count over the same traversal. Both are properties of the path and neither is readable from the
# final line, so they are one family. The ONLY admissible ground for excluding `T3` would be
# mechanistic ("tenure is not trajectory") and it fails on that argument — so it stays.
#
# ⚠️ A 2-arm "rate-change-only" family is a DIFFERENT, NARROWER hypothesis. It is not forbidden, but it
# must be declared BEFORE a run. This module registers the 3-arm family and reports the 2-arm figure
# only as the RETIRED post-hoc reading (`posthoc_sensitivity`).
TRAJECTORY_FAMILY: tuple[str, ...] = ("T1_traj_ladder", "T2_traj_raw", "T3_tenure")

#: The post-hoc field E7.15-H3 actually reported 0.998 over. Kept ONLY so the report can show what it
#: bought and where the gain came from — never as a selectable field.
RETIRED_POSTHOC_FIELD: tuple[str, ...] = ("T1_traj_ladder", "T2_traj_raw")

_ANCHOR_LABELS: tuple[str, ...] = ("A_traj_shuffled", "A_weight_identity", "A_degenerate_mean")

MH2_2_ARMS: tuple[H3Arm, ...] = tuple(
    _BY_LABEL[lbl] for lbl in (FOIL, *TRAJECTORY_FAMILY, *_ANCHOR_LABELS))

# ── 🔒 LOCK 5: ANCHORS. Three of H3's four, and the fourth is dropped on MECHANISTIC grounds. ─────
# ⛔ `A_re_shuffled` IS DELIBERATELY ABSENT. It is a matched foil for the player RANDOM INTERCEPT
# (`P3_player_re`), permuting the row→player assignment with the group-size multiset preserved.
# Lock 2 removed the player-structure family, so that anchor has NO DEFENDER here. Carrying an anchor
# whose defender is absent gives you something that can neither pass nor fail meaningfully — the
# NF1.7 (a) vacuous-anchor shape — and pointing it at whatever happens to be winning instead would be
# the NF-D16 (g‴) mis-scoping that vetoes an innocent arm for another mechanism's sin. It is dropped
# because its MECHANISM left the field, never because of anything it scored.
MH2_2_ANCHORS: tuple[Anchor, ...] = (
    Anchor("A_degenerate_mean", "block", "the DEGENERATE CEILING — predict the population mean",
           "A metric a 'predict nothing' arm wins cannot select a projection (NF-D11); the selection "
           "metric is inverted for this cohort.",
           must_move=False),   # a degenerate PROJECTOR transforms nothing — legitimately moves 0%
    Anchor("A_weight_identity", "noop", "the BYTE NO-OP — a constant observation weight",
           "The harness changed something it did not declare; no arm's margin can be trusted."),
    Anchor("A_traj_shuffled", "refute", "the SHUFFLED trajectory delta — permuted within level",
           "The trajectory's apparent edge is 'any dispersed extra regressor helps', not the direction "
           "a player was moving.",
           defender="T1_traj_ladder"),
)

# ── 🔒 LOCK 4: declared INACTIVE before the run, not discovered after it ──────────────────────────
#: metric → why the trajectory mechanism structurally CANNOT act on it. An INACTIVE metric is a finding
#: about the POPULATION's scope: there is no defect to hunt and no fold count that fixes it (MH2 §8).
INACTIVE_METRICS: dict[str, dict[str, str]] = {
    "pitcher": {
        "xwoba_against":
            "`xwoba_against`'s minor-league feature is a TRIPLE-A-ONLY Statcast summary, so a player "
            "carries it at one level at most and the trajectory delta has ZERO within-player "
            "transitions to act on. E7.15-H3 recorded `T1_traj_ladder` and `T2_traj_raw` at EXACTLY "
            "0.000% lift here — the signature of an arm byte-identical to the foil. INACTIVE is a "
            "statement about the population's scope, not about the effect; the remedy is a different "
            "population, never more seasons (E7.15/NF1.9/MH2).",
    },
}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Field hygiene — the locks, enforced mechanically rather than asserted in prose
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _assert_declared_field(result: H3Result, metric: str) -> None:
    """🔒 LOCKS 1 + 5 + MH2.1 (a), checked against what was ACTUALLY scored.

    Three separate ways a §0.5 field silently stops being the declared one, all fatal and all cheap to
    rule out:

    1. **An arm went missing** — the scored selectable set is not exactly `TRAJECTORY_FAMILY`. That is
       the post-hoc trimming this whole story exists to retire, so it raises rather than warns.
    2. **An anchor joined the trial field.** ⭐ **A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2.1 (a)).**
       An anchor is far from the winner BY CONSTRUCTION, so letting one into the DSR field inflates
       the cross-trial dispersion `V` and the anchor that exists to POLICE the metric silently SETS
       the gate's own bar. That is not hypothetical — it is exactly how MH2.1's `oracle_floor` made
       DSR unclearable for a purely arithmetic reason.
    3. **The foil counted as a trial.** `dsr_report` excludes it; asserted here so a harness change
       cannot quietly re-include it.
    """
    scored = set(result.leaderboard.loc[result.leaderboard["selectable"], "arm"].astype(str))
    if scored != set(TRAJECTORY_FAMILY):
        raise AssertionError(
            f"[{metric}] the SCORED selectable field {sorted(scored)} is not the DECLARED family "
            f"{sorted(TRAJECTORY_FAMILY)}. A field that drifts from its pre-registration is exactly "
            f"the post-hoc trimming MH2.2 exists to retire — you get to pre-register a family, you "
            f"do not get to discover one.")
    trials = (result.dsr.get("eligible") or {}).get("n_trials")
    if trials is not None and int(trials) != len(TRAJECTORY_FAMILY):
        raise AssertionError(
            f"[{metric}] the DSR trial field has {trials} members against the declared "
            f"{len(TRAJECTORY_FAMILY)}. An anchor or the foil has joined the trial set — a diagnostic "
            f"anchor is NEVER a trial (MH2.1 (a)); it would inflate the cross-trial dispersion and set "
            f"the gate's own bar.")


def _series_moments(series: np.ndarray) -> tuple[float, float, float]:
    """`(sharpe, skew, NON-excess kurtosis)` computed exactly as `overfitting.deflated_sharpe` does.

    ⚠️ **THE EMPIRICAL MOMENTS MUST BE THREADED THROUGH** (`cv_power` says so twice, in
    `decompose_field_size` and in `classify_null`). Defaulting them here would make the classifier
    answer about a normal-moment world while the GATE it is classifying used the real ones — the two
    then disagree about whether a metric is DSR-reachable, which is the entire verdict. Same moments
    everywhere, or nowhere.
    """
    r = np.asarray(series, float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return 0.0, 0.0, 3.0
    sd1 = float(np.std(r, ddof=1))
    sr = float(np.mean(r) / sd1) if sd1 > 0 else 0.0
    rc, sd0 = r - r.mean(), float(np.std(r, ddof=0))
    skew = float((rc ** 3).mean() / sd0 ** 3) if sd0 > 0 else 0.0
    kurt = float((rc ** 4).mean() / sd0 ** 4) if sd0 > 0 else 3.0
    return sr, skew, kurt


def _skill(mae: pd.DataFrame, arm: str) -> np.ndarray:
    s = (mae[FOIL] - mae[arm]).to_numpy(float)
    return s[np.isfinite(s)]


def _field_stats(mae: pd.DataFrame, field: tuple[str, ...]) -> dict:
    """The winner, its per-fold skill series and the field's cross-trial Sharpe dispersion `V`."""
    present = [c for c in field if c in mae.columns]
    sharpes = {c: _series_moments(_skill(mae, c))[0] for c in present}
    best = max(present, key=lambda c: float(np.nanmean(_skill(mae, c))) if len(_skill(mae, c)) else -np.inf)
    ser = _skill(mae, best)
    sr, skew, kurt = _series_moments(ser)
    V = float(np.var(list(sharpes.values()), ddof=1)) if len(sharpes) > 1 else 0.0
    return {"arm": best, "series": ser, "n_obs": len(ser), "observed_sr": sr,
            "skew": skew, "kurt": kurt, "var_trials_sr": V, "n_trials": len(present),
            "trial_sharpes": sharpes}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered bar (🔒 LOCK 3) and the retired post-hoc reading
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def preregistered_bar(mae: pd.DataFrame, n_folds: int) -> dict:
    """🔒 **LOCK 3 — the honest bar, in per-fold Sharpe, beside what the winner actually posted.**

    "DSR ≥ 0.95" is not a readable bar; `dsr_required_sr` turns it into the per-fold Sharpe THIS field
    demands, which is a property of the DESIGN and can be read before a single arm is fitted. The
    shortfall is then stated in the unit that GROWS — folds, which here ARE MLB debut cohorts, i.e.
    one per season (NF-D15 g″).
    """
    f = _field_stats(mae, TRAJECTORY_FAMILY)
    bar = dsr_required_sr(n_obs=f["n_obs"], n_trials=f["n_trials"], var_trials_sr=f["var_trials_sr"],
                          skew=f["skew"], kurt=f["kurt"])
    need = folds_to_clear_dsr(observed_sr=f["observed_sr"], n_trials=f["n_trials"],
                              var_trials_sr=f["var_trials_sr"], skew=f["skew"], kurt=f["kurt"])
    return {
        "arm": f["arm"], "n_folds": int(n_folds), "observed_sr": round(f["observed_sr"], 4),
        "required_sr_for_dsr_gate": round(float(bar), 4),
        "sr_shortfall": round(float(bar) - f["observed_sr"], 4),
        "folds_needed_for_dsr": need,
        "extra_debut_cohorts_needed": (None if need is None else max(0, int(need) - int(n_folds))),
        "dsr_ceiling_at_this_n_obs": round(dsr_ceiling(f["n_obs"], f["kurt"]), 4),
        "var_trials_sr": round(f["var_trials_sr"], 6),
        "trial_sharpes": {k: round(v, 4) for k, v in f["trial_sharpes"].items()},
    }


def posthoc_sensitivity(mae: pd.DataFrame) -> dict:
    """⭐ **WHAT THE POST-HOC 2-ARM FIELD ACTUALLY BOUGHT — and which channel paid for it.**

    Shrinking a field moves TWO things and only one of them is "multiplicity" (`cv_power`): the trial
    COUNT `N`, and the cross-trial Sharpe DISPERSION `V`, because the arm you drop is the one far from
    the winner. On this family the dispersion channel is overwhelmingly dominant — dropping the LOSING
    arm collapses `V` by ~20,000× on `bb_pct` — so the recorded 0.998 was bought almost entirely by
    removing a loser's spread, which is the second layer of selection bias DSR exists to deflate.

    Reported so the retired number is visible and explained, never so it can be selected on.
    """
    wide, narrow = _field_stats(mae, TRAJECTORY_FAMILY), _field_stats(mae, RETIRED_POSTHOC_FIELD)
    d = decompose_field_size(
        observed_sr=wide["observed_sr"], n_obs=wide["n_obs"],
        n_trials_wide=wide["n_trials"], var_wide=wide["var_trials_sr"],
        n_trials_narrow=narrow["n_trials"], var_narrow=narrow["var_trials_sr"],
        skew=wide["skew"], kurt=wide["kurt"])   # ⚠️ same moments as the gate — never defaulted
    d.update({
        "declared_field": list(TRAJECTORY_FAMILY), "retired_posthoc_field": list(RETIRED_POSTHOC_FIELD),
        "dropped_arm": sorted(set(TRAJECTORY_FAMILY) - set(RETIRED_POSTHOC_FIELD)),
        "var_declared": round(wide["var_trials_sr"], 8),
        "var_posthoc": round(narrow["var_trials_sr"], 8),
        "dispersion_collapse_ratio": (round(wide["var_trials_sr"] / narrow["var_trials_sr"], 1)
                                      if narrow["var_trials_sr"] > 0 else None),
    })
    return d


def _classify(metric: str, result: H3Result, side_key: str) -> dict:
    """`cv_power.classify_null` on this metric, with the INACTIVE declaration honoured FIRST."""
    inactive_reason = INACTIVE_METRICS.get(side_key, {}).get(metric)
    mae, n_folds = result.mae_by_fold, len(result.fold_cohorts)
    f = _field_stats(mae, TRAJECTORY_FAMILY)
    lb = result.leaderboard
    sel = lb[lb["selectable"] & lb["active"]]
    beats = bool(not sel.empty
                 and float(sel.iloc[0]["oos_mae"]) < float(mae[FOIL].mean(skipna=True)) - 1e-12)
    wins = (int(round(float(sel.iloc[0]["fold_win_rate"]) * n_folds)) if not sel.empty
            and np.isfinite(sel.iloc[0]["fold_win_rate"]) else None)
    v = classify_null(
        metric=metric, n_folds=n_folds, n_arms=len(TRAJECTORY_FAMILY), beats_foil=beats,
        observed_sr=f["observed_sr"], var_trials_sr=f["var_trials_sr"],
        fold_wins=wins, skew=f["skew"], kurt=f["kurt"],
        active=inactive_reason is None, inactive_reason=inactive_reason)
    return {"metric": metric, "state": v.state, "reason": v.reason,
            "retest_trigger": v.retest_trigger, "folds_have": v.folds_have,
            "folds_needed": v.folds_needed, "extra_cohorts": v.extra_seasons,
            "max_field_size": v.max_field_size, "detail": v.detail}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The reproduction anchor
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def check_reproduction(results: dict[str, H3Result], side: SideConfig, tol: float = 1e-9) -> dict:
    """⭐ **DID THIS RUN REPRODUCE E7.15-H3's RECORDED PER-FOLD MAE, ARM FOR ARM AND FOLD FOR FOLD?**

    MH2.2 re-reads the same evidence over a differently-DECLARED field. That is only legitimate if the
    evidence is identical — otherwise the "0.849 vs 0.998" comparison is between two different runs and
    proves nothing about field definition. Every shared arm is checked; a mismatch is reported loudly
    and marks the run UNVERIFIED rather than being silently tolerated.

    ⚠️ A MISSING H3 ARTIFACT MAKES THIS `UNVERIFIED`, NEVER `OK` — a check that did not run is not a
    check that passed (NF1.7 (a)).
    """
    suffix = side.reduced.artifact_suffix
    path = _H3_ART / f"e7_15_h3{suffix}_summary.json"
    if not path.exists():
        return {"status": "UNVERIFIED", "note": f"H3 artifact absent at {path} — cannot compare. A "
                                                f"check that did not run is not a check that passed."}
    rec = json.loads(path.read_text()).get("per_metric", {})
    rows, worst = [], 0.0
    for m, r in results.items():
        h3 = rec.get(m)
        if not h3:
            rows.append({"metric": m, "status": "UNVERIFIED", "note": "not in the H3 artifact"})
            continue
        # ⚠️ JSON dict keys are STRINGS, so the recorded matrix comes back indexed by "2016" while the
        # freshly-fitted one is indexed by the int 2016. Left un-coerced, `reindex` aligns NOTHING, every
        # gap is NaN, and the check reports MISMATCH for a run that reproduces perfectly — a comparison
        # that cannot succeed is as useless as one that cannot fail (NF1.7 (a), both directions).
        old = pd.DataFrame(h3["mae_by_fold"])
        old.index = pd.Index([int(i) for i in old.index], name=r.mae_by_fold.index.name)
        fresh = r.mae_by_fold.copy()
        fresh.index = pd.Index([int(i) for i in fresh.index], name=fresh.index.name)
        shared = [c for c in fresh.columns if c in old.columns]
        common_folds = [i for i in fresh.index if i in set(old.index)]
        gaps, compared = {}, 0
        for c in shared:
            a = fresh.loc[common_folds, c].astype(float).to_numpy()
            b = old.loc[common_folds, c].astype(float).to_numpy()
            both = np.isfinite(a) & np.isfinite(b)
            compared += int(both.sum())
            gaps[c] = float(np.max(np.abs(a[both] - b[both]))) if both.any() else float("nan")
        finite = [g for g in gaps.values() if np.isfinite(g)]
        mx = float(max(finite)) if finite else float("nan")
        worst = max(worst, 0.0 if not np.isfinite(mx) else mx)
        # ⭐ `n_cells_compared` is the anti-vacuity field: a run that aligned ZERO cells would otherwise
        # post `max_gap = nan` and could be mis-read as "nothing disagreed".
        rows.append({"metric": m, "n_shared_arms": len(shared), "n_cells_compared": compared,
                     "max_abs_mae_gap_vs_h3": mx,
                     "status": ("OK" if compared > 0 and np.isfinite(mx) and mx <= tol
                                else "MISMATCH" if compared > 0 else "UNVERIFIED")})
    bad = [r for r in rows if r.get("status") != "OK"]
    return {"status": "OK" if not bad else "MISMATCH", "tolerance": tol,
            "worst_abs_gap": worst, "per_metric": rows,
            "note": ("every shared arm reproduces E7.15-H3's recorded per-fold MAE — the two runs are "
                     "the SAME evidence, so the field-definition comparison is valid."
                     if not bad else
                     "⛔ at least one arm did NOT reproduce H3's recorded MAE. The declared-vs-post-hoc "
                     "comparison is between two DIFFERENT runs and must not be read as a statement "
                     "about field definition until this is resolved.")}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class SideOutcome:
    side_key: str
    results: dict[str, H3Result]
    fdr: dict
    nulls: dict
    bars: dict
    posthoc: dict
    classifications: dict
    reproduction: dict
    inactive: dict


def write_report(o: SideOutcome, path: Path, side: SideConfig) -> None:
    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if df is not None and not df.empty else "_(empty)_"

    n_folds = max((len(r.fold_cohorts) for r in o.results.values()), default=0)
    clause = fold_consistency_clause(n_folds) if n_folds else None
    L: list[str] = []
    A = L.append
    A(f"# MH2.2 — the trajectory family as its OWN pre-registered field ({side.player_type} side)\n")
    A(f"_generated {datetime.now(timezone.utc).isoformat()} · declared field = "
      f"`{'`, `'.join(TRAJECTORY_FAMILY)}` · foil = the SHIPPED E7.12-slice-1 configuration · "
      f"`best_alpha = 0`_\n")
    A("> Pre-registration (written before any arm was scored): `mh2_2_preregistration.md`.\n")
    A("> ⚠️ **A projection, not an edge claim.** Nothing here is emitted to the served board.\n")

    A("\n## 0. What this run retires\n")
    A("E7.15-H3 recorded the trajectory arms as clearing **DSR 0.998** over a 2-arm field. That field "
      "is **POST-HOC** — H3's own pre-registration names THREE trajectory arms and the 0.998 drops "
      "`T3_tenure`, *the arm that lost*. This run scores the family **as declared**.\n")
    A("⛔ **You get to pre-register a family; you do not get to discover one.**\n")

    A("\n## 1. Reproduction anchor — is this the SAME evidence as E7.15-H3?\n")
    A(f"**{o.reproduction.get('status')}** — {o.reproduction.get('note')}\n")
    A(md(pd.DataFrame(o.reproduction.get("per_metric", []))))

    A("\n## 2. Verdicts (declared 3-arm field)\n")
    A(md(pd.DataFrame([{
        "metric": m, "verdict": r.verdict, "winner": r.winner,
        "best_arm": o.bars.get(m, {}).get("arm"),
        "pct_lift_vs_foil": round(float(r.leaderboard.loc[
            r.leaderboard["arm"] == o.bars.get(m, {}).get("arm"), "pct_lift_vs_foil"].iloc[0]), 3)
        if o.bars.get(m, {}).get("arm") in set(r.leaderboard["arm"]) else np.nan,
        "BH-FDR": o.fdr.get(m),
        "PBO(eligible)": r.deflation.get("pbo"),
        "DSR(declared 3-arm)": round(float((r.dsr.get("eligible") or {}).get("dsr") or np.nan), 4),
        "null_state": o.classifications.get(m, {}).get("state"),
    } for m, r in o.results.items()])))
    for m, why in o.inactive.items():
        A(f"\n- 🕳️ **`{m}` — INACTIVE (declared before the run).** {why}\n")

    A("\n## 3. 🔒 The pre-registered bar — stated in per-fold Sharpe, not as a p-decimal\n")
    A("`required_sr` is `cv_power.dsr_required_sr`: the per-fold skill Sharpe an arm MUST post to reach "
      f"DSR ≥ {MIN_DSR} **in this 3-arm field**. It is a property of the DESIGN and is readable before "
      "any arm is fitted.\n")
    A(md(pd.DataFrame([{"metric": m, **{k: v for k, v in b.items() if k != "trial_sharpes"}}
                       for m, b in o.bars.items()])))
    if clause is not None:
        A(f"\n**Fold-consistency clause (MH2/H8, calibrated):** at {n_folds} folds it requires "
          f"**{clause.wins_required}/{n_folds}** wins at α={clause.alpha} (null false-fire "
          f"{clause.attained_false_fire:.3f}) against the legacy `≥60%` bar's "
          f"{clause.legacy_wins_required} wins (null false-fire {clause.legacy_false_fire:.3f}). It is "
          f"weakly STRICTER, so it can only ever prevent a false ADD — never manufacture one.\n")

    A("\n## 4. ⭐ What the retired post-hoc 2-arm field actually bought\n")
    A("Shrinking a field moves TWO things and only one is 'multiplicity': the trial COUNT `N`, and the "
      "cross-trial Sharpe DISPERSION `V` — because the arm you drop is the one far from the winner "
      "(`cv_power.decompose_field_size`). **The dispersion channel is the dominant one here**, i.e. the "
      "0.998 was bought by deleting a LOSER's spread, not by an honest multiplicity reduction.\n")
    A(md(pd.DataFrame([{"metric": m, "dropped": ",".join(d.get("dropped_arm") or []),
                        "DSR_declared_3arm": d.get("dsr_wide_field"),
                        "DSR_posthoc_2arm": d.get("dsr_narrow_field"),
                        "if_only_N_shrank": d.get("dsr_if_only_trial_count_shrank"),
                        "if_only_V_shrank": d.get("dsr_if_only_dispersion_shrank"),
                        "V_declared": d.get("var_declared"), "V_posthoc": d.get("var_posthoc"),
                        "V_collapse_ratio": d.get("dispersion_collapse_ratio")}
                       for m, d in o.posthoc.items()])))

    A("\n## 5. Null classification (`cv_power.classify_null`) and the re-test trigger\n")
    A(md(pd.DataFrame([{"metric": c["metric"], "state": c["state"],
                        "folds_have": c["folds_have"], "folds_needed": c["folds_needed"],
                        "extra_debut_cohorts": c["extra_cohorts"],
                        "max_field_size": c["max_field_size"],
                        "retest_trigger": c["retest_trigger"]}
                       for c in o.classifications.values()])))
    A("\n⚠️ **Folds here ARE MLB debut cohorts — one per season — and the MLB label substrate "
      "(`mart_batter_rolling_stats`, `stg_batter_pitches`) begins in 2015.** So 11 folds is the MAXIMUM "
      "available today on both sides, and every fold-count trigger above is **CALENDAR-BOUND: +1 fold "
      "per MLB season**, not a window widening that could be done now (MH2 rule (b)). See "
      "`mh2_2_preregistration.md` §8 for the one lever that IS reachable today.\n")

    # ⭐ A FINDING ABOUT THE INSTRUMENT, surfaced by being the first story to run `classify_null`
    # against an ALREADY-pre-registered field — see the reading note of the same name below.
    trapped = [c for c in o.classifications.values()
               if c.get("max_field_size") is not None and isinstance(c.get("max_field_size"), int)
               and 2 <= int(c["max_field_size"]) < len(TRAJECTORY_FAMILY)]
    if trapped:
        names = ", ".join(f"`{c['metric']}` (≤{c['max_field_size']} arms)" for c in trapped)
        A(f"\n🪤 **READ THE `max_field_size` LEG OF THOSE TRIGGERS WITH CARE — FOR {names} IT PRESCRIBES "
          f"EXACTLY THE THING THIS STORY RETIRES.** `cv_power.classify_null` offers 'a field of ≤N arms "
          f"at the CURRENT fold count' as a generic remedy, and it is a correct statement of the "
          f"arithmetic. But the ≤2-arm field on this family **is the post-hoc one** — the arithmetic is "
          f"satisfied by dropping `T3_tenure`, i.e. by dropping the arm that lost. **A smaller field is "
          f"a legitimate remedy ONLY when the smaller family is declared in advance on MECHANISTIC "
          f"grounds; it is never a licence to re-cut a field you have already scored.** Taken literally "
          f"here it would re-commit the selection bias in a badge that reads like a re-test trigger.\n")

    for m, r in o.results.items():
        A(f"\n## {m}\n")
        A(f"_shipped foil: `{r.shipped_spec.label}` · prior_scale {r.prior_scale} · "
          f"{len(r.fold_cohorts)} folds {r.fold_cohorts}_\n")
        A(md(r.leaderboard.drop(columns=["note"], errors="ignore")))
        A("\n**Anchors**\n")
        for a in MH2_2_ANCHORS:
            d = r.anchors.get(a.label)
            if isinstance(d, dict):
                A(f"- `{a.label}` ({a.what}): {d}")
        A(f"\n- `A_weight_identity` byte-no-op: "
          f"{r.anchors.get('A_weight_identity__is_a_noop')} "
          f"(max |Δ| = {r.anchors.get('A_weight_identity__max_abs_gap')})")
        A(f"\n**Per-arm trial Sharpes (the DSR field):** "
          f"{json.dumps(o.bars.get(m, {}).get('trial_sharpes', {}), default=float)}\n")
        A("\n**Reasons**\n")
        for x in r.reasons:
            A(f"- {x}")

    A("\n## 6. Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)\n")
    A(f"**Binding constraint: {o.nulls['binding_constraint']}**\n")
    A(md(pd.DataFrame(o.nulls.get("per_metric", []))))

    A("\n## Reading notes\n")
    A("- **🔒 LOCK 1 — `T3_tenure` is in the field BECAUSE it lost last time.** Dropping an arm for "
      "losing is not a field definition, it is a selection, and it is the second layer of the very "
      "bias DSR exists to deflate.\n")
    A("- **🔒 LOCK 2 — this is the TRAJECTORY family only.** The player-structure arms "
      "(`P1`/`P2`/`P3`/`P4`) keep E7.15-H3's verdict. The pitcher side's largest H3 lift (`k_pct` "
      "+1.713%) is `P4_re_dedup` — PLAYER STRUCTURE — and crediting trajectory with it would "
      "mis-attribute the result. **Batter and pitcher are separate verdicts and are never pooled: the "
      "batter side is where the lead is; the pitcher trajectory arms are NEGATIVE on `k_pct`, `bb_pct` "
      "and `hr_rate`.**\n")
    A("- **🔒 LOCK 5 — `A_re_shuffled` is deliberately ABSENT.** It is a matched foil for the player "
      "random intercept, which lock 2 removed from the field, so it has no defender here. An anchor "
      "without its defender can neither pass nor fail meaningfully (NF1.7 (a)) and re-pointing it at "
      "the current leader would veto an innocent arm for another mechanism's sin (NF-D16 g‴).\n")
    A("- **A diagnostic anchor is NEVER a trial (MH2.1 (a))** — the DSR field is the 3 selectable arms; "
      "the foil and all anchors are excluded from `n_trials` and from the dispersion `V`. Asserted "
      "mechanically by `_assert_declared_field`, not assumed.\n")
    A("- 🪤 **`classify_null`'s `max_field_size` re-test trigger is UNSAFE ADVICE once a field is "
      "already pre-registered — a finding about the INSTRUMENT, surfaced because MH2.2 is the first "
      "story to run it against a declared family.** 'Re-run in a field of ≤N arms' is arithmetically "
      "correct and, on this family, is satisfied by dropping the arm that lost. The remedy is only "
      "legitimate when the smaller family is declared in advance on mechanistic grounds. `classify_null` "
      "cannot tell the two apart, so the CALLER must — which is what §5's callout does.\n")
    A("- **The `folds_needed` figures here supersede `mh2_2_preregistration.md` §4's.** The "
      "pre-registration computed `dsr_required_sr`/`folds_to_clear_dsr` under NORMAL moments while this "
      "run threads the winner's EMPIRICAL skew and kurtosis — the same moments the DSR gate itself "
      "uses. Every DSR value, every verdict and all nine null STATES are unchanged (the pre-registered "
      "DSRs came from `deflated_sharpe`, which was already empirical); only the derived bar and fold "
      "counts move. It is a live instance of `cv_power`'s own 'same moments everywhere, or nowhere' "
      "warning, recorded rather than quietly corrected.\n")
    A("- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.\n")

    body = "\n".join(L) + "\n"
    db = design_block_from_ladder_results(
        o.results, fold_rule="leave-one-MLB-debut-cohort-out (n_cohorts)",
        primary_contrast="the DECLARED 3-arm trajectory family vs the shipped E7.12-S1 foil")
    db.source_artifact = f"mh2_2_trajectory_family{side.reduced.artifact_suffix}.md"
    db.gates = {"MIN_DSR": MIN_DSR, "FDR_ALPHA": FDR_ALPHA,
                "fold_consistency_wins_required": (clause.wins_required if clause else None)}
    for e in db.per_metric or []:
        e["null_state"] = o.classifications.get(e.get("metric"), {}).get("state")
    path.write_text(insert_design_block(body, db))
    log.info("wrote %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MH2.2 — the trajectory family as its own declared field")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--metrics", nargs="+", default=None)
    p.add_argument("--max-folds", type=int, default=None,
                   help="SMOKE ONLY — score just the last N folds to prove the code path cheaply. Not "
                        "a scoreable run: it changes the deflation field and the cohort arithmetic.")
    p.add_argument("--no-check-reproduction", action="store_true",
                   help="skip the E7.15-H3 per-fold MAE reproduction anchor (smoke runs only — a "
                        "truncated fold list cannot reproduce the full recorded matrix)")
    p.add_argument("--out-dir", default=str(_ART))
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[args.player_type]
    suffix = side.reduced.artifact_suffix
    e73 = _REPORT_DIR / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(e73 / side.pairs_name)
    pairs["player_id"] = pairs["player_id"].astype(str)
    park_path = _REPORT_DIR / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    park = pd.read_parquet(park_path) if park_path.exists() else None

    inactive = dict(INACTIVE_METRICS.get(side.player_type, {}))
    requested = list(args.metrics or side.metrics)
    # 🔒 LOCK 4 — an INACTIVE metric is declared, not discovered, and is excluded from the BH family:
    # a metric no arm can move is not a hypothesis that was tested.
    metrics = [m for m in requested if m not in inactive]
    skipped = [m for m in requested if m in inactive]
    for m in skipped:
        log.info("🕳️ [%s] INACTIVE (declared) — %s", m, inactive[m])

    results: dict[str, H3Result] = {}
    cache: dict = {}
    for m in metrics:
        log.info("=== MH2.2 [%s]: %s (declared field: %s) ===",
                 side.player_type, m, ", ".join(TRAJECTORY_FAMILY))
        r = run_h3(pairs, park, m, side, MH2_2_ARMS, propensity_cache=cache,
                   max_folds=args.max_folds, anchors=MH2_2_ANCHORS, calibrated_fold_clause=True)
        _assert_declared_field(r, m)
        results[m] = r
        log.info("[%s] verdict=%s winner=%s", m, r.verdict, r.winner)
        for x in r.reasons:
            log.info("[%s] %s", m, x)

    if not results:
        log.warning("no ACTIVE metrics to score for the %s side", side.player_type)
        return 0

    pvals = {}
    for m, r in results.items():
        cand = r.leaderboard[r.leaderboard["selectable"] & r.leaderboard["active"]]
        pvals[m] = (float(cand.iloc[0]["p_one_sided"])
                    if not cand.empty and pd.notna(cand.iloc[0]["p_one_sided"]) else None)
    fdr = bh_fdr(pvals, alpha=FDR_ALPHA)
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict, r.winner = "DROP", FOIL
            r.reasons.append(
                f"⛔ FDR-DOWNGRADED — cleared the per-metric bar (p={pvals.get(m)}) but does NOT "
                f"survive Benjamini-Hochberg over the {len(pvals)}-metric ACTIVE family at "
                f"α={FDR_ALPHA}.")

    bars = {m: preregistered_bar(r.mae_by_fold, len(r.fold_cohorts)) for m, r in results.items()}
    posthoc = {m: posthoc_sensitivity(r.mae_by_fold) for m, r in results.items()}
    classifications = {m: _classify(m, r, side.player_type) for m, r in results.items()}
    for m, why in inactive.items():
        classifications[m] = {"metric": m, "state": "INACTIVE", "reason": why,
                              "retest_trigger": "a population on which the mechanism can act at all",
                              "folds_have": None, "folds_needed": None, "extra_cohorts": None,
                              "max_field_size": None, "detail": {}}
    repro = ({"status": "SKIPPED", "note": "reproduction anchor skipped by flag / smoke run"}
             if (args.no_check_reproduction or args.max_folds)
             else check_reproduction(results, side))
    if repro.get("status") == "MISMATCH":
        log.error("⛔ REPRODUCTION MISMATCH — %s", repro.get("note"))
    nulls = null_analysis(results, pvals)
    log.info("NULL ANALYSIS — %s", nulls["binding_constraint"])

    o = SideOutcome(side.player_type, results, fdr, nulls, bars, posthoc, classifications,
                    repro, inactive)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"mh2_2_trajectory_family{suffix}_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "declared_field": list(TRAJECTORY_FAMILY),
        "retired_posthoc_field": list(RETIRED_POSTHOC_FIELD),
        "anchors": [a.label for a in MH2_2_ANCHORS],
        "anchor_excluded_on_mechanistic_grounds": {
            "A_re_shuffled": "a matched foil for `P3_player_re`, which lock 2 removed from the field — "
                             "an anchor without its defender is vacuous (NF1.7 (a)) and re-pointing it "
                             "would mis-scope a refutation (NF-D16 g‴)."},
        "inactive_metrics": inactive,
        "reproduction_vs_e7_15_h3": repro,
        "bh_fdr_alpha": FDR_ALPHA, "bh_fdr": fdr,
        "preregistered_bar": bars,
        "retired_posthoc_sensitivity": posthoc,
        "null_classification": classifications,
        "null_analysis": nulls,
        "per_metric": {m: {
            "verdict": r.verdict, "winner": r.winner,
            "leaderboard": r.leaderboard.to_dict(orient="records"),
            "mae_by_fold": r.mae_by_fold.to_dict(), "coverage": r.coverage,
            "deflation": r.deflation, "dsr": r.dsr, "anchors": r.anchors,
            "reasons": r.reasons,
        } for m, r in results.items()},
    }, indent=2, default=float))

    if not args.no_report:
        write_report(o, _REPORT_DIR / f"mh2_2_trajectory_family{suffix}.md", side)
    log.info("MH2.2 VERDICTS (%s): %s", side.player_type, {m: r.verdict for m, r in results.items()})
    log.info("MH2.2 NULL STATES (%s): %s", side.player_type,
             {m: c["state"] for m, c in classifications.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

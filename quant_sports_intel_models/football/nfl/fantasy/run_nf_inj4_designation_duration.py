"""run_nf_inj4_designation_duration.py — NF-INJ4 §0.5 bake-off: the designation → duration model.

⭐ READ `ablation_results/nf_inj4_preregistration.md` FIRST. It was committed before this file
scored anything, and everything decidable in advance lives as a CONSTANT in
`nf_inj4_designation_duration.py` — this runner READS them and restates nothing (the NF-D16
discipline). `ablation_results/nf_inj4_data_census.md` is the census that shaped the registration.

PIPELINE: the census frame (PIT-gated, 1,309 rows / 398 players / 18 weeks, 2025) → grouped 10-fold
by player → 7 declared arms + 3 anchor families through ONE exact discrete-CRPS reducer →
PBO (field-level, declared + eligible sets) + DSR-CONV + BH + `cv_power` fold consistency → the
PLAT-CVP2 injected-effect positive control with an EXPLICIT gate partition → `classify_null` →
ship-or-null.

RUN (LAPTOP — reads local artifacts read-only, writes local artifacts; measured ~2 s):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4_designation_duration
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power as CP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    nf_inj4_designation_duration as DD,
)

log = logging.getLogger("nfl.fantasy.nf_inj4")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
_FRAME = _HERE / "artifacts" / "nf_inj4_designation_frame_2025.parquet"

#: 🔒 The SERVED arm. Deploy-held: the board's weekly-designation discount is EXACTLY ZERO today.
SERVED_ARM = DD.INCUMBENT_ARM


# ══════════════════════════════════════════════════════════════════════════════════════════════
# One fold: every arm + every anchor through ONE reducer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _score(pmf: np.ndarray, test: pd.DataFrame) -> dict:
    p = DD.truncate_to_support(pmf, test["games_remaining"].to_numpy())
    y = test["spell"].to_numpy()
    mu = DD.expected_games_missed(p)
    return {"crps": float(DD.crps_discrete(p, y).mean()),
            # ⛔ DISCLOSED, NEVER SELECTS. Measurably inverted on this cohort (NF-D11): 65.6% zeros
            # with a conditional median of 0, so the all-zero nihilist minimises it.
            "mae": float(np.mean(np.abs(y - mu))),
            "mean_expected_games_missed": float(mu.mean()), "n": int(len(y))}


def score_fold(frame: pd.DataFrame, test_idx: np.ndarray, *, rng: np.random.Generator,
               train_idx: np.ndarray | None = None) -> dict:
    test = frame.iloc[test_idx]
    train = (frame.drop(frame.index[test_idx]) if train_idx is None
             else frame.iloc[train_idx])
    arms = {a: _score(DD.fit_predict(a, train, test), test) for a in DD.ARMS}

    # ── per-FORM peeking oracles (NF-D16 (g‴)): the forms NEST, so one field-wide ceiling would
    #    veto a legitimately better nested form as a false metric inversion.
    oracles = {a: _score(DD.fit_predict(a, test, test), test) for a in DD.ARMS}

    # ── matched-n control (NF1.7 (b) / NF1.9 (f)): the winner's own form at the oracle's RESOLUTION.
    #    A peeking oracle is a floor only at matched family AND matched sample.
    n_peek = len(test)
    matched: dict[str, dict] = {}
    for a in DD.ARMS:
        take = rng.choice(len(train), size=min(n_peek, len(train)), replace=False)
        matched[a] = _score(DD.fit_predict(a, train.iloc[take], test), test)

    # ── permutation anchor: designations SHUFFLED within the training fold, destroying the
    #    designation↔outcome link. Well-posed at any n, which a fitted oracle is not.
    perm_train = train.copy()
    perm_train["designation"] = rng.permutation(perm_train["designation"].to_numpy())
    perm = {a: _score(DD.fit_predict(a, perm_train, test), test) for a in DD.SHIPPABLE_ARMS}

    return {"n_test": int(len(test)), "n_train": int(len(train)),
            "arms": arms, "oracles": oracles, "matched_n": matched, "permutation": perm}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Selection, deflation, anchors
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pooled(per_fold: list[dict]) -> dict:
    out = {}
    for a in DD.ARMS:
        c = np.array([f["arms"][a]["crps"] for f in per_fold], dtype=float)
        base = np.array([f["arms"][DD.INCUMBENT_ARM]["crps"] for f in per_fold], dtype=float)
        out[a] = {"crps": round(float(c.mean()), 6),
                  "mae": round(float(np.mean([f["arms"][a]["mae"] for f in per_fold])), 6),
                  "mean_lift_vs_incumbent": round(float((base - c).mean()), 6),
                  "fold_crps": [round(float(x), 6) for x in c]}
    return out


def select_winner(pool: dict) -> str:
    """The winner is the best SHIPPABLE arm on pooled CRPS. `fixed_penalty`, the foil and the
    degenerates are ineligible BY REGISTRATION, not by outcome (NF-D20)."""
    return min(DD.SHIPPABLE_ARMS, key=lambda a: pool[a]["crps"])


def _srs(lift_by_arm: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for a, v in lift_by_arm.items():
        d = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
        if len(d) >= 2:
            out[a] = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 1e-12 else 0.0
    return out


def dsr_conv(deltas, trial_srs_for_v, n_trials: int) -> float | None:
    """DSR under DSR-CONV: the pre-registered DEGENERATES stay in `n_trials` (full multiplicity) and
    are excluded from the cross-trial dispersion `V`. Reproduced rather than calling the shared
    `M14.deflated_sharpe`, which derives the trial COUNT from `len(trial_srs)` so the two channels
    `SR0 = √V·z(N)` is taxed through cannot be set independently — and editing a SHARED instrument
    other verticals pin is the MH2.7 (ii) hazard. The whole-field figure is reported beside it."""
    from scipy.stats import kurtosis, norm, skew
    d = np.asarray(deltas, dtype=float); d = d[np.isfinite(d)]
    if len(d) < 3 or float(d.std(ddof=1)) < 1e-12:
        return None
    sr = float(d.mean()) / float(d.std(ddof=1))
    v = np.asarray([x for x in trial_srs_for_v if np.isfinite(x)], dtype=float)
    em = 0.5772156649015329
    sr0 = (float(v.std(ddof=1)) * ((1 - em) * norm.ppf(1 - 1 / n_trials)
                                   + em * norm.ppf(1 - 1 / (n_trials * np.e)))
           if len(v) >= 2 and v.std(ddof=1) > 0 and n_trials >= 2 else 0.0)
    g3, g4 = float(skew(d)), float(kurtosis(d, fisher=False))
    den = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
    if den <= 0:
        return None
    return round(float(norm.cdf((sr - sr0) * np.sqrt(len(d) - 1) / np.sqrt(den))), 4)


def deflation(per_fold: list[dict], winner: str) -> dict:
    """PBO (FIELD-level, declared + eligible sets) + the NF1.8 triad + DSR-CONV.

    PBO is computed on NEGATED CRPS because `cscv_pbo` picks the in-sample ARGMAX and CRPS is a
    loss — getting that sign wrong reports the field upside-down."""
    arms = list(DD.ARMS)
    mat = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)
    elig = list(DD.SHIPPABLE_ARMS)
    mat_e = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in elig], dtype=float)

    lifts = {a: [f["arms"][DD.INCUMBENT_ARM]["crps"] - f["arms"][a]["crps"] for f in per_fold]
             for a in arms}
    srs_all = _srs(lifts)
    srs_v = {k: v for k, v in srs_all.items() if k not in DD.DEGENERATE_ARMS}
    d = np.asarray(lifts[winner], dtype=float)

    scores = mat.mean(axis=1)
    order = np.argsort(-scores)
    top = order[:max(2, len(arms) // 4)]
    # NF1.8 triad: the flip distribution is the cheapest and most informative of the three.
    flips: dict[str, int] = {}
    for k in range(len(per_fold)):
        rest = [j for j in range(len(per_fold)) if j != k]
        w = arms[int(np.argmax(mat[:, rest].mean(axis=1)))]
        flips[w] = flips.get(w, 0) + 1
    os_best = arms[int(np.argmax(scores))]
    degradation = round(float(scores[arms.index(os_best)] - scores[arms.index(winner)]), 6)

    return {
        "pbo_declared_field": M14.cscv_pbo(mat),
        "pbo_eligible_set": M14.cscv_pbo(mat_e),
        "pbo_application": DD.PBO_APPLICATION,
        "pbo_binding": "eligible_set (NF1.8: compute PBO over the search the selection ran)",
        "dsr_conv": dsr_conv(d, list(srs_v.values()), DD.DECLARED_FIELD_SIZE),
        "dsr_whole_field": M14.deflated_sharpe(d, np.asarray(list(srs_all.values()))),
        "trial_sharpes": {k: round(v, 4) for k, v in sorted(srs_all.items(), key=lambda kv: -kv[1])},
        "V_declared_excl_degenerates": round(float(np.var(list(srs_v.values()), ddof=1)), 6),
        "V_whole_field": round(float(np.var(list(srs_all.values()), ddof=1)), 6),
        "degenerates_excluded_from_v": DD.DEGENERATES_EXCLUDED_FROM_V,
        "n_trials": DD.DECLARED_FIELD_SIZE,
        "leave_one_fold_out_flip_distribution": flips,
        "bailey_performance_degradation": degradation,
        "whole_field_spread_pct": round(100.0 * (float(-scores.min()) - float(-scores.max()))
                                        / max(1e-9, float(-scores.max())), 2),
        "contender_spread_pct": round(100.0 * (float(-scores[top].min()) - float(-scores[top].max()))
                                      / max(1e-9, float(-scores[top].max())), 2),
        "note": "⚠️ The degenerate exclusion is NON-MONOTONE and is therefore not a lever: dropping "
                "a NEAR-MEAN arm WIDENS the sample variance and RAISES the bar. It applies to the "
                "two arms named degenerate before any score, and to nothing else (DSR-CONV). ⛔ No "
                "post-hoc trim of any kind (MH2.2), and no menu of per-candidate-family DSRs.",
    }


def anchor_audit(per_fold: list[dict], winner: str) -> dict:
    """⭐ A MISSING OR UNFITTABLE ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 (a)).

    ⭐ AND — DECLARED FORWARD (pre-registration §4, the NF-W6d fix) — an own-form oracle that does
    not beat its MATCHED-N control is an INACTIVE anchor pair, not a refusal: the peek had nothing
    to act on at that resolution, and reading a tie as "this form has no headroom" is what cost
    NF-W6d three shippable arms."""
    def mean(get):
        v = [get(f) for f in per_fold]
        return float(np.mean(v)) if all(x is not None and np.isfinite(x) for x in v) else None

    out: dict = {}
    for a in DD.ARMS:
        arm = mean(lambda f, a=a: f["arms"][a]["crps"])
        orc = mean(lambda f, a=a: f["oracles"][a]["crps"] if a in f["oracles"] else None)
        ctl = mean(lambda f, a=a: f["matched_n"][a]["crps"] if a in f["matched_n"] else None)
        if orc is None or ctl is None:
            out[a] = {"evaluable": False,
                      "why": "the own-form oracle or its matched-n control is unfittable — recorded "
                             "as a FAILED check, never a pass (NF1.7 (a))"}
            continue
        active = bool(orc < ctl - 1e-6)
        out[a] = {"evaluable": True, "arm_crps": round(arm, 6),
                  "own_form_oracle_crps": round(orc, 6), "matched_n_control_crps": round(ctl, 6),
                  "anchor_pair_active": active,
                  "respects_oracle": bool(arm >= orc - 1e-9),
                  "reading": ("ACTIVE — the peek is measurably better than an honest fit at the same "
                              "n, so the floor is informative"
                              if active else
                              "INACTIVE — the peek ties its matched-n control, so the pair could not "
                              "act; UNINFORMATIVE, neither a refusal nor a pass (NF-W6d / NF-D20)")}

    perm = mean(lambda f: f["permutation"][winner]["crps"])
    win = mean(lambda f: f["arms"][winner]["crps"])
    out["_permutation"] = ({"evaluable": True, "winner_crps": round(win, 6),
                            "permuted_crps": round(perm, 6),
                            "beats_permutation": bool(win < perm - 1e-9)}
                           if perm is not None else
                           {"evaluable": False,
                            "why": "permutation anchor unfittable — a FAILED check, never a pass"})
    out["_degenerates"] = {
        d: {"crps": round(mean(lambda f, d=d: f["arms"][d]["crps"]), 6),
            "loses_to_winner": bool(mean(lambda f, d=d: f["arms"][d]["crps"]) > win + 1e-9)}
        for d in DD.DEGENERATE_ARMS}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Gates — the ONE function the positive control also drives
# ══════════════════════════════════════════════════════════════════════════════════════════════
def gate_table(per_fold: list[dict]) -> dict[str, dict[str, bool]]:
    """`{arm: {gate: bool}}` for the SHIPPABLE arms, over the study's OWN registered gates.

    ⭐ This is the function `injected_effect_positive_control` drives. Re-implementing the gates
    inside the control would restate this harness's assumptions instead of testing them (the NF-C0e
    "a test that reads a value back under the key the code wrote" class), so there is exactly one
    definition of what a gate means and both callers use it."""
    pool = pooled(per_fold)
    anchors = anchor_audit(per_fold, select_winner(pool))
    defl = deflation(per_fold, select_winner(pool))
    clause = CP.fold_consistency_clause(len(per_fold))

    out: dict[str, dict[str, bool]] = {}
    for a in DD.SHIPPABLE_ARMS:
        lifts_inc = np.array([f["arms"][DD.INCUMBENT_ARM]["crps"] - f["arms"][a]["crps"]
                              for f in per_fold], dtype=float)
        lifts_foil = np.array([f["arms"][DD.MATCHED_FOIL]["crps"] - f["arms"][a]["crps"]
                               for f in per_fold], dtype=float)
        p = M14.onesided_paired_pvalue(lifts_foil)
        perm = np.array([f["permutation"][a]["crps"] - f["arms"][a]["crps"] for f in per_fold])
        d_conv = dsr_conv(lifts_inc,
                          [v for k, v in defl["trial_sharpes"].items()
                           if k not in DD.DEGENERATE_ARMS],
                          DD.DECLARED_FIELD_SIZE)
        oracle_ok = all(v.get("respects_oracle", False)
                        for k, v in anchors.items()
                        if not k.startswith("_") and v.get("evaluable")) and \
            all(v.get("evaluable") for k, v in anchors.items() if not k.startswith("_"))
        out[a] = {
            "beats_incumbent": bool(lifts_inc.mean() > 0),
            "beats_foil": bool(lifts_foil.mean() > 0),
            "fold_consistency": bool(clause.passes(int((lifts_foil > 0).sum()))),
            "bh_ok": bool(p is not None and p <= DD.BH_CUTOFF_BINDING),
            "oracle_respected": bool(oracle_ok),
            "beats_permutation": bool(perm.mean() > 0),
            "dsr_ok": bool(d_conv is not None and d_conv >= DD.MIN_DSR),
            "degenerates_lose": bool(all(
                np.mean([f["arms"][dg]["crps"] for f in per_fold])
                > np.mean([f["arms"][a]["crps"] for f in per_fold]) + 1e-9
                for dg in DD.DEGENERATE_ARMS)),
        }
    return out


def run_folds(frame: pd.DataFrame, *, seed: int = DD.FOLD_SEED) -> list[dict]:
    rng = np.random.default_rng(seed)
    return [score_fold(frame, idx, rng=rng) for idx in DD.grouped_player_folds(frame, seed=seed)]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The PLAT-CVP2 injected-effect positive control
# ══════════════════════════════════════════════════════════════════════════════════════════════
def positive_control(frame: pd.DataFrame) -> dict:
    """"Which gates should pass a planted effect?" — EXECUTED, not narrated.

    `gate_classes` is declared EXPLICITLY (no name heuristic) and `invariant_gates` was named in the
    registration before this ran, so an arm stopped only by `degenerates_lose` reads as
    `CONSTRAINT_BLOCKED` rather than as the `BLIND` inversion earlier callers annotated around."""
    def inject(effect: float) -> pd.DataFrame:
        f = frame.copy()
        hit = f["designation"].isin(DD.INJECTED_DESIGNATIONS).to_numpy()
        f.loc[hit, "spell"] = np.minimum(
            f.loc[hit, "spell"].to_numpy() + float(effect),
            f.loc[hit, "games_remaining"].to_numpy()).astype(int)
        return f

    def run_gates(payload: pd.DataFrame) -> dict[str, dict[str, bool]]:
        return gate_table(run_folds(payload))

    rep = CP.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=DD.INJECTION_EFFECT_GAMES,
        gate_classes=DD.GATE_CLASSES, invariant_gates=DD.INVARIANT_GATES,
        check_null_control=True)
    return {
        "verdict": rep.verdict, "effect_games": DD.INJECTION_EFFECT_GAMES,
        "injected_designations": list(DD.INJECTED_DESIGNATIONS),
        "survivors": list(rep.survivors), "metric_survivors": list(rep.metric_survivors),
        "deflation_blocked": list(rep.deflation_blocked),
        "constraint_blocked": list(rep.constraint_blocked),
        "blocking_gates": rep.blocking_gates,
        "partition_source": rep.partition_source, "partition_verified": rep.partition_verified,
        "gate_classes_resolved": rep.gate_classes_resolved,
        "invariant_gates": list(rep.invariant_gates),
        "field_level_gates_applied_per_arm": list(rep.field_level_gates_applied_per_arm),
        "null_control_checked": rep.null_control_checked,
        "null_control_survivors": (None if rep.null_control_survivors is None
                                   else list(rep.null_control_survivors)),
        "reason": rep.reason,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Declared diagnostics — reported, never gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def secondary_week_design(frame: pd.DataFrame) -> dict:
    """The forward-chained purged week blocks. A SIGN-CONSISTENCY reading only: at 6 folds the sign
    floor (0.0156) REFUSES the conservative BH cutoff, which is why this is not the primary."""
    rng = np.random.default_rng(DD.FOLD_SEED + 1)
    per_fold = [score_fold(frame, te, rng=rng, train_idx=tr)
                for tr, te in DD.purged_week_folds(frame)]
    pool = pooled(per_fold)
    out = {}
    for a in DD.SHIPPABLE_ARMS:
        d = np.array([f["arms"][DD.MATCHED_FOIL]["crps"] - f["arms"][a]["crps"] for f in per_fold])
        out[a] = {"mean_lift_vs_foil": round(float(d.mean()), 6),
                  "folds_positive": int((d > 0).sum()), "n_folds": len(per_fold),
                  "sign_matches_primary": None}
    return {"design": "forward-chained purged week blocks", "blocks": list(DD.SECONDARY_TEST_BLOCKS),
            "per_arm": out, "pooled_crps": {a: pool[a]["crps"] for a in DD.ARMS},
            "why_not_primary": "at 6 folds the one-sided sign floor is 0.0156, which "
                               "`validate_sign_certifiability` REFUSES against the conservative BH "
                               "cutoff 0.00714 — a design no effect of any size could certify",
            "gate": False}


def censoring_sensitivity(frame: pd.DataFrame) -> dict:
    """Declared diagnostic: the same scoring with right-censored rows removed. Never a gate."""
    sub = frame[~frame["censored"].astype(bool)].reset_index(drop=True)
    per_fold = run_folds(sub)
    pool = pooled(per_fold)
    return {"rows": int(len(sub)), "rows_dropped": int(len(frame) - len(sub)),
            "pooled_crps": {a: pool[a]["crps"] for a in DD.ARMS},
            "winner": select_winner(pool), "gate": False}


def resolution_sensitivity_note() -> dict:
    """The pre-registered most-severe-wins sensitivity. ⚠️ The census MEASURED it INACTIVE."""
    return {
        "rule": "most severe designation wins, recency breaks ties",
        "active": False,
        "reading": "INACTIVE — all 18 player-weeks whose captures carry more than one distinct "
                   "designation resolve IDENTICALLY under both rules, because in this population a "
                   "designation only ever escalates (questionable → out) and never de-escalates. "
                   "Its agreement carries NO information and is not scored as a pass (NF-D20). It "
                   "stays registered so the 2026 re-test inherits it.",
        "gate": False,
    }


def gate_effect_sweep(frame: pd.DataFrame) -> dict:
    """⚠️ **POST-HOC DIAGNOSTIC — declared as such, added AFTER the decisive run, gating nothing.**

    The positive control returned `BLIND` blocked by `oracle_respected` alone. `BLIND` reads as "a
    null from this family is free", so before that badge is carried forward the claim behind it is
    MEASURED rather than argued: re-run the study's own gate table at a ladder of injected effects
    and report, per gate, whether it MOVES at all. A gate identical at effect 0 and at a large
    planted effect is injection-INVARIANT IN FACT.

    ⛔ It is NOT invariant BY DECLARATION, and this diagnostic does not make it so — this
    registration declared only `degenerates_lose` invariant, and "a gate cannot be reclassified as
    injection-invariant after seeing that it blocked" is this study's own pre-registration text
    (E2.1-r). The reclassification is a FINDING handed to the successor, never applied here.
    """
    ladder = (0.0, 0.5, 1.0, 2.0, 4.0)
    rows = []
    for eff in ladder:
        f = frame.copy()
        hit = f["designation"].isin(DD.INJECTED_DESIGNATIONS).to_numpy()
        f.loc[hit, "spell"] = np.minimum(
            f.loc[hit, "spell"].to_numpy() + eff,
            f.loc[hit, "games_remaining"].to_numpy()).astype(int)
        tbl = gate_table(run_folds(f))
        rows.append({"effect_games": eff,
                     **{g: bool(tbl[DD.PRIMARY_ARM][g]) for g in DD.GATE_CLASSES}})
    df = pd.DataFrame(rows)
    # ⚠️ A BOOLEAN GATE ALREADY SATISFIED AT EFFECT 0 CANNOT MOVE UPWARD, so "did it change?" is
    #    UNINFORMATIVE for a passing gate — the first cut of this diagnostic reported seven gates
    #    as "invariant in fact", which is nonsense for the ones that pass. The discriminating
    #    statement is narrower and only concerns the gates a blocked arm is actually stuck behind:
    #    which gates are FALSE at every rung, i.e. cannot be made to fire by a planted effect.
    #    (NF-D20's "count what the mechanism could act on" applied to the diagnostic itself.)
    state = {}
    for g in DD.GATE_CLASSES:
        vals = set(bool(x) for x in df[g])
        state[g] = ("always_passes" if vals == {True} else
                    "always_fails" if vals == {False} else "moves_with_the_effect")
    stuck = [g for g, v in state.items()
             if v == "always_fails" and g not in DD.INVARIANT_GATES]
    return {
        "post_hoc": True, "gate": False, "arm": DD.PRIMARY_ARM, "ladder": list(ladder),
        "per_effect": rows,
        "gate_state_across_the_ladder": state,
        "uninformative_because_already_passing_at_effect_zero":
            [g for g, v in state.items() if v == "always_passes"],
        "blocking_and_unmovable_by_a_planted_effect": stuck,
        "reading": "a gate that is FALSE at every rung — including a planted effect four times the "
                   "registered size — cannot be made to fire by the injection, so an arm blocked "
                   "by it ALONE cleared everything the control could move: the SUBSTANCE of "
                   "CONSTRAINT_BLOCKED. ⛔ The BLIND badge STANDS as the instrument returned it, "
                   "because this registration did not declare that gate invariant in advance "
                   "(E2.1-r, and this study's own §6 says so verbatim); the reclassification is a "
                   "FINDING for the successor, never applied here. ⚠️ Gates listed as "
                   "`always_passes` say nothing in this sweep — a satisfied boolean has nowhere to "
                   "move.",
    }


def oracle_floor_decomposition(per_fold: list[dict], anchors: dict) -> dict:
    """⭐ **A PRE-REGISTERED ANCHOR THAT FAILS IS LEFT FAILING AND DECOMPOSED, NEVER RE-LABELLED**
    (NF-D20). `oracle_respected` as registered reads "no arm beats its OWN-FORM oracle", and it
    FAILS on all three shippable arms. The decomposition says which half failed and why.

    · the NAIVE clause `arm_crps >= own_form_oracle_crps` — FAILS;
    · the NF1.9 (f) clause `own_form_oracle_crps <= matched_n_control_crps` — the floor enforced at
      equal family AND equal RESOLUTION — PASSES on every active pair.

    ⇒ the peek is a genuine peek (it beats an honest fit at its own n), but it is fitted at roughly
    a NINTH of the arms' training resolution, and `MIN_CELL_N` cripples it further at that size, so
    the naive clause is measuring the ORACLE'S SAMPLE SIZE rather than any property of an arm — the
    NF-W7i capacity-starved-ceiling shape. ⛔ Reporting this does NOT rescue the gate: the clause
    was registered in its naive form and it stays failed."""
    n_train = float(np.mean([f["n_train"] for f in per_fold]))
    n_test = float(np.mean([f["n_test"] for f in per_fold]))
    rows = []
    for a in DD.SHIPPABLE_ARMS:
        v = anchors[a]
        rows.append({
            "arm": a, "arm_crps": v["arm_crps"],
            "own_form_oracle_crps": v["own_form_oracle_crps"],
            "matched_n_control_crps": v["matched_n_control_crps"],
            "naive_clause_arm_ge_oracle": bool(v["respects_oracle"]),
            "nf1_9f_clause_oracle_le_matched_n": bool(
                v["own_form_oracle_crps"] <= v["matched_n_control_crps"] + 1e-9),
            "anchor_pair_active": bool(v["anchor_pair_active"]),
        })
    return {
        "registered_clause": "no arm beats its OWN-FORM oracle; matched-n control evaluable",
        "registered_clause_result": "FAILED",
        "per_arm": rows,
        "mean_train_rows": round(n_train, 1), "mean_oracle_peek_rows": round(n_test, 1),
        "resolution_ratio_train_over_peek": round(n_train / max(n_test, 1e-9), 2),
        "min_cell_n": DD.MIN_CELL_N,
        "reading": (
            "the naive clause is UNPASSABLE BY CONSTRUCTION in this design: the peek is fitted on a "
            f"test fold of ~{n_test:.0f} rows against arms trained on ~{n_train:.0f}, and a cell "
            f"below MIN_CELL_N={DD.MIN_CELL_N} backs off, so at peek resolution most of the "
            "conditioning collapses to the pooled distribution. An arm beating a label-seeing "
            "oracle here is CAPACITY, never leakage (the arms are fitted strictly on training rows "
            "disjoint by player). ⛔ The gate stays FAILED as registered."),
        "gate": False,
    }


def mechanism_activity(frame: pd.DataFrame, folds: list[np.ndarray]) -> dict:
    """NF-D20 — COUNT the rows the mechanism can act on before crediting any pass. A designation
    level with no eval rows on a fold is UNINFORMATIVE there, never a pass."""
    rows = []
    for k, idx in enumerate(folds):
        ev = frame.iloc[idx]
        mix = ev["designation"].value_counts().to_dict()
        rows.append({"fold": k, "n_eval": int(len(ev)),
                     **{d: int(mix.get(d, 0)) for d in DD.DESIGNATION_LEVELS}})
    tot = {d: int((frame["designation"] == d).sum()) for d in DD.DESIGNATION_LEVELS}
    thin = [d for d, n in tot.items() if n < DD.MIN_CELL_N]
    return {"per_fold": rows, "total_by_designation": tot,
            "levels_below_min_cell_n": thin,
            "note": f"a level below MIN_CELL_N={DD.MIN_CELL_N} can never populate its own in-fold "
                    f"cell and always BACKS OFF — its apparent conditioning is the parent's, which "
                    f"is uninformative about that level, never a pass (NF-D20)."}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════
def verdict(frame: pd.DataFrame, per_fold: list[dict]) -> dict:
    pool = pooled(per_fold)
    winner = select_winner(pool)
    gates = gate_table(per_fold)[winner]
    defl = deflation(per_fold, winner)
    anchors = anchor_audit(per_fold, winner)
    clause = CP.fold_consistency_clause(len(per_fold))

    lifts_foil = np.array([f["arms"][DD.MATCHED_FOIL]["crps"] - f["arms"][winner]["crps"]
                           for f in per_fold], dtype=float)
    p = M14.onesided_paired_pvalue(lifts_foil)
    fold_wins = int((lifts_foil > 0).sum())

    ship = all(v is True for v in gates.values())
    sd = float(np.std(lifts_foil, ddof=1)) if len(lifts_foil) > 1 else float("nan")
    null = CP.classify_null(
        metric="crps_spell", n_folds=len(per_fold), n_arms=DD.DECLARED_FIELD_SIZE,
        beats_foil=bool(lifts_foil.mean() > 0),
        observed_sr=(float(lifts_foil.mean() / sd) if sd > 1e-12 else None),
        var_trials_sr=float(np.var([v for k, v in defl["trial_sharpes"].items()
                                    if k not in DD.DEGENERATE_ARMS], ddof=1)),
        fold_wins=fold_wins, p_one_sided=p, bh_cutoff=DD.BH_CUTOFF_BINDING,
        mde_sd_units=CP.mde_in_sd_units(n_folds=len(per_fold)),
        pbo=defl["pbo_eligible_set"], pbo_gate=DD.MAX_PBO, pbo_application=DD.PBO_APPLICATION,
        degenerates_excluded_from_v=DD.DEGENERATES_EXCLUDED_FROM_V,
        declared_field_size=DD.DECLARED_FIELD_SIZE)

    return {
        "winner": winner, "served_arm": SERVED_ARM, "deploy_held": True, "best_alpha": 0,
        "gates": gates, "ship": ship,
        "gate_classes": DD.GATE_CLASSES, "invariant_gates": list(DD.INVARIANT_GATES),
        "winner_vs_foil": {
            "mean_lift_crps": round(float(lifts_foil.mean()), 6),
            "fold_wins": fold_wins, "n_folds": len(per_fold),
            "fold_consistency_wins_required": clause.wins_required,
            "fold_consistency_false_fire": round(clause.attained_false_fire, 4),
            "p_one_sided": p,
            "bh_cutoff_binding": DD.BH_CUTOFF_BINDING,
            "bh_cutoff_conservative_reported": round(DD.BH_CUTOFF_CONSERVATIVE, 6),
            "clears_conservative_reading": bool(p is not None
                                                and p <= DD.BH_CUTOFF_CONSERVATIVE),
        },
        "winner_vs_incumbent": {
            "mean_lift_crps": pool[winner]["mean_lift_vs_incumbent"],
            "incumbent_crps": pool[DD.INCUMBENT_ARM]["crps"], "winner_crps": pool[winner]["crps"],
        },
        "null_classification": _classify(null, gates, anchors, per_fold),
        "non_shippable_by_registration": {
            a: {"crps": pool[a]["crps"], "beats_every_shippable_arm": bool(
                pool[a]["crps"] < min(pool[s]["crps"] for s in DD.SHIPPABLE_ARMS) - 1e-9)}
            for a in DD.NON_SHIPPABLE_BY_REGISTRATION},
        "pooled": pool, "deflation": defl, "anchors": anchors,
        "mechanism_activity": mechanism_activity(frame, DD.grouped_player_folds(frame)),
    }


def _classify(null, gates: dict, anchors: dict, per_fold: list[dict]) -> dict:
    """The instrument's verdict VERBATIM, plus the null STATE this study is actually in.

    ⭐ **NF-D18's EIGHTH STATE.** `cv_power.classify_null` classifies STATISTICAL nulls — power,
    field size, absence. A null caused by a DETERMINISTIC ANCHOR CLAUSE is a different kind: no
    fold count and no season count moves it, because the quantity that fails it (the ratio of an
    arm's training rows to its oracle's peek) is fixed by the CV design, not by `n`. Reporting such
    a null as POWER_LIMITED would publish the actively-misleading "come back with more seasons"
    direction NF-D18 exists to stop. So the classifier's output is preserved verbatim and the
    binding half is named beside it (the NF-W7 shape: a mixed statistical/anchor null classifies by
    the half that BINDS).

    ⛔ This changes no gate and ships nothing. If every gate passed, the state below would be the
    ship, and it is not."""
    raw = {"state": null.state, "reason": null.reason, "retest_trigger": null.retest_trigger,
           "pbo_application_admissible": getattr(null, "pbo_application_admissible", None),
           "field_remedy_admissible": getattr(null, "field_remedy_admissible", None),
           "detail": null.detail}
    failed = [g for g, v in gates.items() if v is not True]
    anchor_only = bool(failed) and set(failed) <= {"oracle_respected"}
    if not failed:
        return {"state": null.state, "binding_half": None, "instrument_verdict_verbatim": raw,
                "note": "every registered gate passed; the classifier's state describes the "
                        "statistical reading only."}
    if anchor_only:
        return {
            "state": "CONSTRAINT_REFUSED",
            "binding_half": "anchor",
            "why": "every STATISTICAL gate passes decisively and the study is refused by ONE "
                   "pre-registered ANCHOR clause. That clause fails on a ratio fixed by the CV "
                   "design (an arm's training rows to its own-form oracle's peek), so no fold "
                   "count and no season count can move it — the remedy is a DIFFERENT ANCHOR "
                   "DESIGN registered forward, or a PM decision. NEVER more data.",
            "retest_trigger": None,
            "publishes_a_data_trigger": False,
            "instrument_verdict_verbatim": raw,
            "instrument_note": "`classify_null` has no state for a deterministic-constraint "
                               "refusal (NF-D18), so its output above is a statement about the "
                               "STATISTICAL reading and is preserved rather than overwritten.",
        }
    return {"state": null.state, "binding_half": "statistical", "failed_gates": failed,
            "instrument_verdict_verbatim": raw}


def apply_serving_counterfactual(frame: pd.DataFrame, winner: str) -> dict:
    """What the winning arm's E[games missed] would be per designation level, at a full remaining
    schedule — the quantity `season_projection` would consume. Reported for EVERY run: a null still
    needs its counterfactual on the record."""
    ref = pd.DataFrame({
        "designation": list(DD.DESIGNATION_LEVELS) * len(DD.POSITION_GROUPS),
        "position": [p for p in DD.POSITION_GROUPS for _ in DD.DESIGNATION_LEVELS],
        "practice_level": DD.PRACTICE_UNKNOWN,
        "games_remaining": DD.SUPPORT_MAX,
    })
    pmf = DD.truncate_to_support(DD.fit_predict(winner, frame, ref),
                                 ref["games_remaining"].to_numpy())
    ref["expected_games_missed"] = np.round(DD.expected_games_missed(pmf), 4)
    ref["rate_multiplier"] = np.round(
        (DD.SEASON_GAMES - ref["expected_games_missed"]) / DD.SEASON_GAMES, 4)
    return {"arm": winner, "fitted_on": "the FULL frame (a serving read, not a fold)",
            "season_games": DD.SEASON_GAMES,
            "formula": "new_games = min(current, current x (SEASON_GAMES - E[spell]) / SEASON_GAMES)",
            "scope": "REGULAR-SEASON designations only (pre-registration §7)",
            "rows": ref.to_dict("records")}


def run(frame: pd.DataFrame, *, with_control: bool = True) -> dict:
    t0 = time.time()
    per_fold = run_folds(frame)
    v = verdict(frame, per_fold)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-INJ4", "season": DD.SEASON,
        "preregistration": "ablation_results/nf_inj4_preregistration.md",
        "census": "ablation_results/nf_inj4_data_census.md",
        "frame": {"rows": int(len(frame)), "players": int(frame[DD.FOLD_UNIT].nunique()),
                  "weeks": int(frame["week"].nunique()), "seasons": 1},
        "design": {"primary": f"grouped {DD.N_FOLDS}-fold by {DD.FOLD_UNIT}",
                   "seed": DD.FOLD_SEED, "n_folds": len(per_fold)},
        **v,
        "serving_counterfactual": apply_serving_counterfactual(frame, v["winner"]),
        "diagnostics": {
            "secondary_week_design": secondary_week_design(frame),
            "censoring_sensitivity": censoring_sensitivity(frame),
            "resolution_sensitivity": resolution_sensitivity_note(),
            "oracle_floor_decomposition": oracle_floor_decomposition(
                per_fold, anchor_audit(per_fold, v["winner"])),
            "gate_effect_sweep": gate_effect_sweep(frame),
            "mae_is_disclosed_never_selects": {
                a: {"crps": v["pooled"][a]["crps"], "mae": v["pooled"][a]["mae"]}
                for a in DD.ARMS},
        },
    }
    if with_control:
        out["positive_control"] = positive_control(frame)
    out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def render(s: dict) -> str:
    pool = pd.DataFrame(s["pooled"]).T[["crps", "mae", "mean_lift_vs_incumbent"]]
    gates = pd.DataFrame([{"gate": k, "class": DD.GATE_CLASSES[k], "passes": v}
                          for k, v in s["gates"].items()])
    anch = pd.DataFrame({k: v for k, v in s["anchors"].items()
                         if not k.startswith("_")}).T
    return "\n".join([
        "# NF-INJ4 — designation → games-missed duration model (§0.5 bake-off)", "",
        f"Generated {s['generated_at']}. Pre-registration: `{s['preregistration']}` (committed "
        f"before any scoring). Census: `{s['census']}`.", "",
        f"**Verdict: {'SHIP' if s['ship'] else 'NULL'} — "
        f"`{s['null_classification']['state']}`. Winner `{s['winner']}`. "
        f"Served arm `{s['served_arm']}` UNCHANGED; deploy-held; `best_alpha = 0`.**", "",
        f"Frame: {s['frame']['rows']} rows / {s['frame']['players']} players / "
        f"{s['frame']['weeks']} weeks / {s['frame']['seasons']} season. "
        f"Design: {s['design']['primary']}.", "",
        "## Gates", "", gates.to_markdown(index=False), "",
        "## Pooled scores (CRPS selects; MAE is disclosed and selects nothing)", "",
        pool.to_markdown(), "",
        "## Winner vs the matched status-blind foil", "",
        "```json", json.dumps(s["winner_vs_foil"], indent=2), "```", "",
        "## Deflation", "", "```json", json.dumps(s["deflation"], indent=2), "```", "",
        "## Anchors", "", anch.to_markdown(), "",
        "```json", json.dumps({k: v for k, v in s["anchors"].items()
                               if k.startswith("_")}, indent=2), "```", "",
        "## Positive control (PLAT-CVP2)", "",
        "```json", json.dumps(s.get("positive_control", {"skipped": True}), indent=2), "```", "",
        "## Null classification", "",
        "```json", json.dumps(s["null_classification"], indent=2), "```", "",
        "## Serving counterfactual", "",
        pd.DataFrame(s["serving_counterfactual"]["rows"]).to_markdown(index=False), "",
        "## Declared diagnostics (reported, never gates)", "",
        "```json", json.dumps(s["diagnostics"], indent=2), "```", "",
    ])


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-INJ4 designation → duration bake-off")
    ap.add_argument("--no-control", action="store_true",
                    help="skip the injected-effect positive control (smoke only)")
    ap.add_argument("--out", default="nf_inj4_designation_duration",
                    help="report stem under ablation_results/")
    args = ap.parse_args(argv)

    if not _FRAME.exists():
        raise SystemExit(
            f"{_FRAME} is absent — run `run_nf_inj4_census` first. ⛔ Refusing to score an unbuilt "
            f"frame (NF1.7 (a): an empty read must never be recorded as a measured null).")
    frame = pd.read_parquet(_FRAME)
    s = run(frame, with_control=not args.no_control)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(s, indent=2, default=str))
    (_REPORT_DIR / f"{args.out}.md").write_text(render(s))
    print(json.dumps({k: s[k] for k in ("winner", "ship", "gates", "winner_vs_foil",
                                        "null_classification", "elapsed_s")},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

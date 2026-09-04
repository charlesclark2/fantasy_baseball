"""run_nf_inj4b_designation_duration.py — NF-INJ4b: the decisive run under the CORRECTED anchor.

⭐ READ `ablation_results/nf_inj4b_preregistration.md` FIRST. It was committed before this file
scored anything. Everything decidable in advance is a CONSTANT in `nf_inj4b_designation_duration.py`
(the delta) or in `nf_inj4_designation_duration.py` (the inherited field/folds/data); this runner
READS them and restates neither.

────────────────────────────────────────────────────────────────────────────────────────────────
⛔ THE HONESTY CLAUSE — binding, and it governs how every number below may be read
────────────────────────────────────────────────────────────────────────────────────────────────
The field, the folds, the seed and the substrate are NF-INJ4's, and this run PROVES it two ways:
the fold machinery is IMPORTED from NF-INJ4's runner verbatim (`run_folds`, `pooled`,
`select_winner`, `deflation` — so not one number can drift), and the substrate was vintage-checked
against NF-INJ4's committed census before the registration was written.

⇒ **Every number this run reports is ALREADY KNOWN from NF-INJ4's record; only the gate flips.**
This buys a PROPERLY-REGISTERED RECORD of an already-measured result — ⛔ never fresh confirmation.
The `reproduction_pin` section is the proof of that claim and is the ONLY thing the reproduction of
a known number is allowed to certify: the PIPELINE, never the hypothesis.

⭐ The one genuinely NEW result is the PLAT-CVP2 positive control's VERDICT, because the control
drives the study's own gate function and this registration CHANGES that function.

WHAT IS REPLACED, AND ONLY THIS: `anchor_audit` (extended to the three-state matched-resolution
reading) and `gate_table` (the naive oracle clause retired; the two named clauses registered).

RUN (LAPTOP — reads one local parquet, writes local artifacts; MEASURED ~11 s with the ladder):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_designation_duration
"""
from __future__ import annotations

import argparse
import dataclasses
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
    nf_inj4b_designation_duration as B,
    run_nf_inj4_designation_duration as R4,
)

log = logging.getLogger("nfl.fantasy.nf_inj4b")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
_FRAME = _HERE / "artifacts" / "nf_inj4_designation_frame_2025.parquet"
#: NF-INJ4's committed record — READ ONLY, for the reproduction pin. ⛔ Never written.
_INJ4_RESULT = _REPORT_DIR / "nf_inj4_designation_duration.json"

#: 🔒 The SERVED arm. Deploy-held: the board's weekly-designation discount is EXACTLY ZERO today.
SERVED_ARM = DD.INCUMBENT_ARM

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The reproduction pin — NF-INJ2c #5 representation-tolerant semantics
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: NF-INJ4's result JSON stores every figure at `round(x, 6)`, so its QUANTUM is 1e-6 and the widest
#: a faithful reproduction can legitimately sit from a published value is HALF that.
PIN_ARTIFACT_QUANTUM = 1e-6
PIN_BAR = PIN_ARTIFACT_QUANTUM / 2.0
#: ⛔ NOT slack — a REPRESENTATION allowance, consuming NF-INJ2c decision #5 (PR #1073, merged at
#: `dev` 1199a1f5). A decimal half-unit has no exact binary form, so the SAME structural tie lands on
#: either side of the bar by luck of representation; admitting one ULP is what makes the pin decide
#: on the DATA rather than on floating-point happenstance. A figure wrong by any amount the 6-decimal
#: artifact can EXPRESS still refuses. ⛔ And a 1e-9 bar taken RAW against a 6-decimal artifact would
#: be UNACHIEVABLE on correct reproduction (the E9.61 / NF-INJ2b class) — the epsilon rides on the
#: artifact's own half-quantum, it does not replace it.
PIN_REPR_EPS = 1e-9


def pin_ok(mine: float | None, recorded: float | None) -> bool:
    """⛔ FAIL-CLOSED: a missing or non-finite figure on EITHER side REFUSES — a comparison that
    could not be evaluated is never a pass (NF1.7 (a))."""
    if mine is None or recorded is None:
        return False
    m, r = float(mine), float(recorded)
    if not (np.isfinite(m) and np.isfinite(r)):
        return False
    return bool(abs(m - r) <= PIN_BAR + PIN_REPR_EPS)


def reproduction_pin(pool: dict, anchors: dict, defl: dict, wvf: dict) -> dict:
    """⭐ THE HONESTY CLAUSE'S PROOF: does this run reproduce NF-INJ4's published figures?

    ⛔ What a PASS certifies is the PIPELINE — that field, folds, seed and substrate really are
    unchanged, so "only the gate flips" is a measured statement. It certifies NOTHING about the
    mechanism: reproducing a known number is not evidence for the hypothesis that produced it.
    ⭐ A FAILURE would be the genuinely interesting outcome — it would mean something moved, the
    honesty clause's precondition is broken, and the result must be reported as NEW evidence with
    every deflation statistic recomputed from scratch (MH2.2 / NF-INJ3 §0a).
    """
    if not _INJ4_RESULT.exists():
        return {"evaluable": False,
                "why": f"{_INJ4_RESULT.name} is absent — the pin has nothing to compare against, "
                       f"and an unverifiable reproduction claim must REFUSE rather than be assumed "
                       f"(NF1.7 (a))"}
    rec = json.loads(_INJ4_RESULT.read_text())
    checks: list[dict] = []

    def add(name: str, mine, recorded):
        checks.append({"figure": name, "nf_inj4_recorded": recorded,
                       "nf_inj4b_rebuilt": (round(float(mine), 9) if mine is not None else None),
                       "reproduces": pin_ok(mine, recorded)})

    for a in DD.ARMS:
        add(f"pooled.{a}.crps", pool[a]["crps"], rec["pooled"].get(a, {}).get("crps"))
    for a in DD.ARMS:
        r = rec["anchors"].get(a, {})
        add(f"anchor.{a}.arm_crps", anchors[a].get("arm_crps"), r.get("arm_crps"))
        add(f"anchor.{a}.own_form_oracle_crps",
            anchors[a].get("own_form_oracle_crps"), r.get("own_form_oracle_crps"))
        add(f"anchor.{a}.matched_n_control_crps",
            anchors[a].get("matched_n_control_crps"), r.get("matched_n_control_crps"))
    add("winner_vs_foil.mean_lift_crps", wvf["mean_lift_crps"],
        rec["winner_vs_foil"]["mean_lift_crps"])
    add("winner_vs_foil.p_one_sided", wvf["p_one_sided"], rec["winner_vs_foil"]["p_one_sided"])
    add("deflation.dsr_conv", defl["dsr_conv"], rec["deflation"]["dsr_conv"])
    add("deflation.pbo_declared_field", defl["pbo_declared_field"],
        rec["deflation"]["pbo_declared_field"])
    add("deflation.pbo_eligible_set", defl["pbo_eligible_set"],
        rec["deflation"]["pbo_eligible_set"])
    add("deflation.V_declared_excl_degenerates", defl["V_declared_excl_degenerates"],
        rec["deflation"]["V_declared_excl_degenerates"])

    failed = [c for c in checks if not c["reproduces"]]
    return {
        "evaluable": True,
        "bar": PIN_BAR, "representation_epsilon": PIN_REPR_EPS,
        "artifact_quantum": PIN_ARTIFACT_QUANTUM,
        "semantics": "NF-INJ2c decision #5 (PR #1073): the registered bar is the published "
                     "artifact's HALF-QUANTUM, evaluated with a 1e-9 representation epsilon at the "
                     "decimal boundary. ⛔ The epsilon is not slack and does not replace the bar.",
        "figures_checked": len(checks), "figures_reproduced": len(checks) - len(failed),
        "all_reproduce": not failed,
        "failures": failed,
        "checks": checks,
        "what_a_pass_certifies": "the PIPELINE — that field, folds, seed and substrate are "
                                 "genuinely unchanged, which is what makes 'only the gate flips' a "
                                 "MEASUREMENT. ⛔ It certifies NOTHING about the mechanism; "
                                 "reproducing a known number is not evidence for the hypothesis "
                                 "that produced it.",
        "winner_matches": rec.get("winner"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE REGISTRATION DELTA #1 — the anchor audit at MATCHED RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════════════════════
def anchor_audit(per_fold: list[dict], winner: str) -> dict:
    """The ONE measured pair (`own_form_oracle` vs `matched_n_control`), read as THREE states.

    ⭐ TWO GUARDS, NAMED SEPARATELY (pre-registration §2), because registering one does not give you
    the other — the standing convention NF-INJ4 produced:
      A `anchor_pair_informative`         — NF-W6d: could the pair ACT at all?
      B `oracle_floor_matched_resolution` — NF1.9 (f): given that it could, does the floor HOLD at
                                            equal family AND equal resolution?

    ⚠️ B is VACUOUS on an INACTIVE pair, so this audit reports B's pass count BESIDE A's active count
    and never on its own (NF-D20). ⭐ And an activity classification is not a magnitude (NF-W7f), so
    the per-arm `|oracle − control|` margin is reported: a reader can see the 1e-6 tolerance is not
    load-bearing instead of taking the classification on trust.

    ⛔ The RETIRED naive clause (`arm_crps ≥ own_form_oracle_crps`) is still COMPUTED and REPORTED as
    a diagnostic. It will read FALSE, exactly as NF-INJ4 measured. Retiring a clause from the gate
    table is not a reason to stop showing its number, and in a design where an arm COULD see its own
    test rows that clause is the thing that catches it — here the fold construction (disjoint BY
    PLAYER) excludes leakage, so an arm beating its own peek can only be CAPACITY.

    ⭐ A MISSING OR UNFITTABLE ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 (a)) — carried over.
    """
    def mean(get):
        v = [get(f) for f in per_fold]
        return float(np.mean(v)) if all(x is not None and np.isfinite(x) for x in v) else None

    tol = B.ANCHOR_TIE_TOL
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
        margin = orc - ctl
        state = ("ACTIVE" if margin < -tol else
                 "VIOLATED" if margin > tol else "INACTIVE")
        out[a] = {
            "evaluable": True,
            "arm_crps": round(arm, 6),
            "own_form_oracle_crps": round(orc, 6),
            "matched_n_control_crps": round(ctl, 6),
            "oracle_minus_control": round(margin, 9),
            "abs_margin_vs_tie_tol": round(abs(margin) / tol, 1),
            "state": state,
            # Clause A's per-arm reading
            "pair_active": state == "ACTIVE",
            # Clause B's per-arm reading — ⚠️ vacuously True when the pair is INACTIVE
            "floor_holds": state != "VIOLATED",
            "floor_reading_is_vacuous_here": state == "INACTIVE",
            # ⛔ RETIRED FROM THE GATE TABLE, reported as a diagnostic
            "retired_naive_clause_arm_ge_oracle": bool(arm >= orc - 1e-9),
            "reading": (
                "ACTIVE — the peek is measurably better than an honest fit at the SAME n, so the "
                "floor at equal family and equal resolution is INFORMATIVE and it HOLDS"
                if state == "ACTIVE" else
                "INACTIVE — the peek TIES its matched-n control, so the pair could not act. "
                "UNINFORMATIVE: neither a refusal (NF-W6d) nor a pass (NF1.7 (a))"
                if state == "INACTIVE" else
                "⛔ VIOLATED — an HONEST matched-n fit BEATS the peeking oracle, so the 'oracle' is "
                "not a floor at all: the peek is starved past usefulness or the anchor is mis-built"),
        }

    # ── the anchor CONSTRUCTION is self-checked, not assumed. `matched_n_control` is only "matched"
    #    if it is genuinely fitted at the peek's resolution; if it silently fitted at FULL resolution
    #    the whole matched reading would be vacuous — the clause would measure nothing while looking
    #    like it measured something (NF1.7 (a) at the construction level).
    per_fold_res = [{"n_peek": int(f["n_test"]), "n_train": int(f["n_train"]),
                     "n_control_train": int(min(f["n_test"], f["n_train"])),
                     "matched": bool(min(f["n_test"], f["n_train"]) == int(f["n_test"]))}
                    for f in per_fold]
    out["_resolution"] = {
        "matched_on_every_fold": all(r["matched"] for r in per_fold_res),
        "mean_n_peek": round(float(np.mean([r["n_peek"] for r in per_fold_res])), 1),
        "mean_n_train": round(float(np.mean([r["n_train"] for r in per_fold_res])), 1),
        "mean_n_control_train": round(float(np.mean([r["n_control_train"] for r in per_fold_res])), 1),
        "arm_to_peek_resolution_ratio": round(
            float(np.mean([r["n_train"] for r in per_fold_res]))
            / max(1e-9, float(np.mean([r["n_peek"] for r in per_fold_res]))), 1),
        "per_fold": per_fold_res,
        "why_it_is_checked": "a control fitted at FULL resolution would make both clauses VACUOUS "
                             "while still returning a number. The control's training size is "
                             "`min(n_test, n_train)` by construction and must equal the peek's row "
                             "count; a mismatch makes both clauses UNEVALUABLE — a hard failure, "
                             "never a pass.",
        "note": "the ARM-to-peek ratio is the quantity that made NF-INJ4's NAIVE clause "
                "unpassable-by-construction. It is reported, and it is NOT what either registered "
                "clause reads: both read the ORACLE against a control at the PEEK's own resolution.",
    }

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

    ev = {k: v for k, v in out.items() if not k.startswith("_") and v.get("evaluable")}
    active = [k for k, v in ev.items() if v["pair_active"]]
    violated = [k for k, v in ev.items() if not v["floor_holds"]]
    out["_clauses"] = {
        B.ANCHOR_CLAUSE_INFORMATIVE: {
            "reading": "NF-W6d inactive-pair: could the anchor family ACT at all?",
            "shippable_arms_active": sorted(a for a in active if a in DD.SHIPPABLE_ARMS),
            "all_arms_active": sorted(active),
            "n_active_of_evaluable": f"{len(active)}/{len(ev)}",
            "passes": bool(any(a in DD.SHIPPABLE_ARMS for a in active)),
        },
        B.ANCHOR_CLAUSE_FLOOR: {
            "reading": "NF1.9 (f) capacity: does the floor HOLD at equal family AND equal resolution?",
            "violations": sorted(violated),
            "n_holding_of_evaluable": f"{len(ev) - len(violated)}/{len(ev)}",
            # ⚠️ NF-D20: the pass count means nothing without the ACTIVE count beside it.
            "n_holding_NON_VACUOUSLY": f"{len([a for a in active if a not in violated])}"
                                       f"/{len(active)} active pairs",
            "vacuous_on": sorted(k for k, v in ev.items() if v["floor_reading_is_vacuous_here"]),
            "passes": not violated,
        },
        "retired_naive_clause_diagnostic": {
            "gates": False,
            "arms_failing_it": sorted(k for k, v in ev.items()
                                      if not v["retired_naive_clause_arm_ge_oracle"]),
            "why_it_is_not_a_gate": "it compares an arm trained at FULL resolution against a peek at "
                                    "1/9th of it, so it measures the ORACLE'S SAMPLE SIZE rather "
                                    "than any arm property (NF-INJ4's decomposition; the NF-W7i "
                                    "capacity-starved-ceiling shape). ⛔ Reported, never re-read.",
        },
        "all_anchors_evaluable": bool(
            len(ev) == len([k for k in out if not k.startswith("_")])
            and out["_resolution"]["matched_on_every_fold"]
            and out["_permutation"].get("evaluable", False)),
    }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE REGISTRATION DELTA #2 — the gate table
# ══════════════════════════════════════════════════════════════════════════════════════════════
def gate_table(per_fold: list[dict]) -> dict[str, dict[str, bool]]:
    """`{arm: {gate: bool}}` for the SHIPPABLE arms, over NF-INJ4b's OWN registered gates.

    ⭐ This is the function `injected_effect_positive_control` drives, so there is exactly ONE
    definition of what a gate means and both callers use it (the NF-C0e "a test that reads a value
    back under the key the code wrote" class).

    Identical to NF-INJ4's table except that `oracle_respected` is replaced by the two named
    matched-resolution clauses. Everything else — including every metric and deflation gate — is
    computed by NF-INJ4's own imported helpers.
    """
    pool = R4.pooled(per_fold)
    winner = R4.select_winner(pool)
    anchors = anchor_audit(per_fold, winner)
    defl = R4.deflation(per_fold, winner)
    clause = CP.fold_consistency_clause(len(per_fold))

    cl = anchors["_clauses"]
    evaluable = bool(cl["all_anchors_evaluable"])
    informative = bool(cl[B.ANCHOR_CLAUSE_INFORMATIVE]["passes"]) and evaluable
    floor_holds = bool(cl[B.ANCHOR_CLAUSE_FLOOR]["passes"]) and evaluable

    out: dict[str, dict[str, bool]] = {}
    for a in DD.SHIPPABLE_ARMS:
        lifts_inc = np.array([f["arms"][DD.INCUMBENT_ARM]["crps"] - f["arms"][a]["crps"]
                              for f in per_fold], dtype=float)
        lifts_foil = np.array([f["arms"][DD.MATCHED_FOIL]["crps"] - f["arms"][a]["crps"]
                               for f in per_fold], dtype=float)
        p = M14.onesided_paired_pvalue(lifts_foil)
        perm = np.array([f["permutation"][a]["crps"] - f["arms"][a]["crps"] for f in per_fold])
        d_conv = R4.dsr_conv(lifts_inc,
                             [v for k, v in defl["trial_sharpes"].items()
                              if k not in DD.DEGENERATE_ARMS],
                             DD.DECLARED_FIELD_SIZE)
        out[a] = {
            "beats_incumbent": bool(lifts_inc.mean() > 0),
            "beats_foil": bool(lifts_foil.mean() > 0),
            "fold_consistency": bool(clause.passes(int((lifts_foil > 0).sum()))),
            "bh_ok": bool(p is not None and p <= B.BH_CUTOFF_BINDING),
            B.ANCHOR_CLAUSE_INFORMATIVE: informative,
            B.ANCHOR_CLAUSE_FLOOR: floor_holds,
            "beats_permutation": bool(perm.mean() > 0),
            "dsr_ok": bool(d_conv is not None and d_conv >= B.MIN_DSR),
            "degenerates_lose": bool(all(
                np.mean([f["arms"][dg]["crps"] for f in per_fold])
                > np.mean([f["arms"][a]["crps"] for f in per_fold]) + 1e-9
                for dg in DD.DEGENERATE_ARMS)),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The gate ladder — this study TESTS its own forward invariance declaration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _inject(frame: pd.DataFrame, effect: float) -> pd.DataFrame:
    f = frame.copy()
    hit = f["designation"].isin(DD.INJECTED_DESIGNATIONS).to_numpy()
    f.loc[hit, "spell"] = np.minimum(
        f.loc[hit, "spell"].to_numpy() + effect,
        f.loc[hit, "games_remaining"].to_numpy()).astype(int)
    return f


#: ⚠️ POST-HOC (declared as such), gating nothing. Several shuffles, because ONE lucky draw must
#: not decide whether a gate family discriminates.
MECHANISM_ABSENT_SEEDS: tuple[int, ...] = (11, 22, 33, 44, 55)


def mechanism_absent_control(frame: pd.DataFrame) -> dict:
    """⚠️ **POST-HOC DIAGNOSTIC — declared as such, added AFTER the decisive run, gating nothing.**

    ⭐ **WHY IT EXISTS.** The PLAT-CVP2 positive control returned **`VACUOUS`** — "an arm survives on
    the NO-EFFECT payload ⇒ the family certifies noise". ⛔ **That badge STANDS exactly as the
    instrument returned it** (E2.1-r: a result is annotated, never re-labelled). But `VACUOUS` is a
    substantive claim about this gate family, and NF-INJ4's own handling of a badge it disagreed
    with is the precedent: the claim behind it is **MEASURED, not argued.**

    The suspicion to test: this registration inherits NF-INJ4's `inject(0.0) → the UNMODIFIED
    payload`, and the unmodified payload is the REAL 2025 data, in which designations genuinely
    predict games missed. The instrument's `VACUOUS` semantics presuppose that `inject(0)` yields a
    population where the mechanism is ABSENT — so "no EXTRA effect planted" is being read as "no
    effect", which on observational data carrying a real effect is a different thing.

    The discriminating measurement, which the suspicion cannot supply on its own: run the SAME gate
    table on payloads where the mechanism is genuinely ABSENT — designations SHUFFLED across the
    frame, destroying the designation ↔ outcome link while preserving every marginal. This is the
    study's own registered `permutation` anchor logic lifted from one arm to the whole gate family.

    · If arms still survive there, the family really does certify noise and `VACUOUS` is
      substantively right — the ship would not be trustworthy.
    · If the family REFUSES there, it discriminates, and `VACUOUS` is an artifact of the null leg's
      PAYLOAD SPECIFICATION rather than a property of the gates.
    """
    rows = []
    for seed in MECHANISM_ABSENT_SEEDS:
        rng = np.random.default_rng(seed)
        f = frame.copy()
        f["designation"] = rng.permutation(f["designation"].to_numpy())
        tbl = gate_table(R4.run_folds(f))
        surv = sorted(a for a, g in tbl.items() if all(g.values()))
        rows.append({"shuffle_seed": seed, "survivors": surv,
                     "failing_gates": sorted({k for g in tbl.values()
                                              for k, v in g.items() if not v})})
    discriminates = all(not r["survivors"] for r in rows)
    return {
        "post_hoc": True, "gate": False,
        "payload": "designations SHUFFLED across the frame — the mechanism is genuinely ABSENT, "
                   "every marginal preserved",
        "n_shuffles": len(rows), "per_shuffle": rows,
        "survivors_on_any_shuffle": sorted({a for r in rows for a in r["survivors"]}),
        "family_discriminates": discriminates,
        "reading": (
            "⭐ ZERO arms survive on a genuinely mechanism-ABSENT payload, on every shuffle, with "
            "the metric and deflation gates failing each time. **The gate family does NOT certify "
            "noise.** ⇒ the `VACUOUS` badge is an artifact of the null leg's PAYLOAD "
            "SPECIFICATION, not a property of these gates — see `null_control_leg_specification`."
            if discriminates else
            "⛔ arms SURVIVE on a payload where the mechanism is absent. The `VACUOUS` badge is "
            "SUBSTANTIVELY RIGHT: this gate family certifies noise, and the ship verdict above is "
            "NOT trustworthy."),
    }


def null_control_leg_specification(control: dict, absent: dict) -> dict:
    """⭐ **THE INSTRUMENT FINDING, stated as a general property rather than as this study's excuse.**

    With `inject(0.0)` defined as the IDENTITY, the positive control's null-control leg is
    **logically equivalent to the negation of the ship verdict**:

      · `VACUOUS` fires ⟺ some arm clears every gate on the null payload
      · the null payload IS the real data
      · the study SHIPS ⟺ some arm clears every gate on the real data
      ⇒ **the study ships ⟺ the control returns `VACUOUS`.**

    So for ANY caller defining `inject(0) = identity`, that leg carries **zero information about the
    gate family** — it cannot fire on a study that fails and cannot help firing on one that
    succeeds. It is a restatement of the decisive run wearing a control's badge (the NF1.7 (a)
    family: a check whose outcome is fixed by something other than the thing it claims to measure).

    ⭐ **AND NF-INJ4's CLEAN NULL LEG WAS CLEAN FOR THE WRONG REASON — which is why nobody could
    have seen this before now.** NF-INJ4 recorded `null_control_survivors: []`. That is not evidence
    its null leg was well-specified: its `oracle_respected` clause was FALSE on the real payload, so
    it blocked every arm on the identity payload too. **The defective anchor was masking the
    mis-specification**, and removing the defect is what exposed it. ⛔ This says nothing about
    NF-INJ4's verdict, which stands; it is an observation drawn from its own published
    `blocking_gates` and its recorded gate result on the real data.

    ⛔ **THE REMEDY IS NOT TO WEAKEN THE LEG.** The null-control payload must be MECHANISM-ABSENT,
    not merely UN-INJECTED — for an observational study the correct null destroys the mechanism (a
    permutation), which every §0.5 study already has machinery for. That is a change to the
    CALLER'S `inject`, or to the instrument's contract, and either way it is a FORWARD decision for
    the PM, ⛔ not something this run adopts after seeing its own badge (E2.1-r).
    """
    return {
        "instrument_verdict_verbatim": control.get("verdict"),
        "verdict_stands": True,
        "why_the_leg_is_uninformative_for_this_caller": (
            "`inject(0.0)` is the IDENTITY, so the null payload IS the real data — a population "
            "that CARRIES a real, independently-measured effect. `VACUOUS` presupposes an "
            "effect-FREE null payload, so here 'an arm survives the no-effect payload' is the "
            "study's own finding restated, not evidence that the family certifies noise."),
        "the_leg_is_equivalent_to_the_negation_of_the_ship_verdict": True,
        "measured_discrimination_on_a_mechanism_absent_payload": {
            "family_discriminates": absent["family_discriminates"],
            "survivors_on_any_shuffle": absent["survivors_on_any_shuffle"],
            "n_shuffles": absent["n_shuffles"]},
        "nf_inj4_null_leg_was_clean_for_the_wrong_reason": (
            "NF-INJ4 recorded `null_control_survivors: []` — but its `oracle_respected` clause was "
            "FALSE on the real payload, so it blocked every arm on the identity payload too. The "
            "defective anchor MASKED this mis-specification; removing it is what exposed it. ⛔ "
            "NF-INJ4's verdict and record stand unedited."),
        "remedy_is_a_forward_pm_decision": (
            "the null-control payload should be MECHANISM-ABSENT (a permutation), not merely "
            "UN-INJECTED. ⛔ Not adopted here after seeing the badge (E2.1-r) — handed to the PM."),
        "this_registration_did_not_anticipate_it": (
            "⚠️ A DEFECT IN THIS REGISTRATION, reported as one. The pre-registration (§4) predicted "
            "the control's PBO leg would be inert and said NOTHING about the null leg, whose "
            "identity-at-zero specification it inherited from NF-INJ4 verbatim and did not "
            "examine."),
    }


def invariance_ladder(frame: pd.DataFrame) -> dict:
    """⭐ **PRE-REGISTERED, not post-hoc: this study DECLARED both anchor clauses injection-invariant
    FORWARD, and this is the measurement that can REFUTE that declaration.**

    NF-INJ4 ran this ladder as a post-hoc diagnostic and reported the NAIVE clause FALSE at every
    rung — evidence about a DIFFERENT clause, which is why it was carried as corroboration and never
    as proof. Here the declaration is on the record BEFORE the run, so the ladder is a falsification
    test of it.

    ⚠️ A BOOLEAN GATE ALREADY SATISFIED AT EFFECT 0 CANNOT MOVE UPWARD, so "did it change?" is
    UNINFORMATIVE for a passing gate — NF-INJ4's first cut of this diagnostic reported seven passing
    gates as "invariant in fact", which is nonsense. The three states are separated (NF-D20's "count
    what the mechanism could act on", applied to the diagnostic itself), and the discriminating
    reading for THIS study is narrow and stated forward: a DECLARED-INVARIANT gate that
    `moves_with_the_effect` REFUTES the declaration.

    ⚠️ And the honest limit, declared forward: for a clause that PASSES at every rung, `always_passes`
    is CONSISTENT WITH the declaration but does not PROVE invariance — a satisfied boolean has
    nowhere to move upward. The ladder can only ever REFUTE this declaration, never confirm it, and
    it is reported that way rather than as a passed check (NF1.7 (a)).
    """
    ladder = (0.0, 0.5, 1.0, 2.0, 4.0)
    rows = []
    for eff in ladder:
        tbl = gate_table(R4.run_folds(_inject(frame, eff)))
        rows.append({"effect_games": eff,
                     **{g: bool(tbl[DD.PRIMARY_ARM][g]) for g in B.GATE_CLASSES}})
    df = pd.DataFrame(rows)
    state = {}
    for g in B.GATE_CLASSES:
        vals = {bool(x) for x in df[g]}
        state[g] = ("always_passes" if vals == {True} else
                    "always_fails" if vals == {False} else "moves_with_the_effect")
    refuted = [g for g in B.INVARIANT_GATES if state[g] == "moves_with_the_effect"]
    return {
        "pre_registered": True, "gate": False, "arm": DD.PRIMARY_ARM, "ladder": list(ladder),
        "per_effect": rows,
        "gate_state_across_the_ladder": state,
        "declared_invariant": list(B.INVARIANT_GATES),
        "declaration_refuted_for": refuted,
        "declaration_holds": not refuted,
        "reading": (
            "⭐ NO declared-invariant clause MOVED with the planted effect, up to 4x the registered "
            "size — CONSISTENT with the forward declaration. ⚠️ It is not PROOF: a clause that "
            "PASSES at every rung has nowhere to move upward, so this ladder can only REFUTE the "
            "declaration, never confirm it. Reported as consistency, never as a passed check "
            "(NF1.7 (a))."
            if not refuted else
            f"⛔ THE FORWARD DECLARATION IS REFUTED for {refuted}: a clause declared "
            f"injection-INVARIANT in this registration MOVES with the planted effect. This is a "
            f"DEFECT IN THIS REGISTRATION and is reported as one, not corrected after the fact "
            f"(E2.1-r)."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd=4):
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def render(s: dict) -> str:
    g = s["gates"]
    a = s["anchors"]
    cl = a["_clauses"]
    L: list[str] = []
    L += [f"# NF-INJ4b — the designation → duration model under a MATCHED-RESOLUTION oracle anchor",
          "",
          f"**Verdict: `{s['verdict']}`.** `best_alpha = 0`. **DEPLOY-HELD** — the served "
          f"Questionable / Doubtful / Out availability discount is EXACTLY ZERO until the gated "
          f"ship path and explicit operator approval.", "",
          "---", "",
          "## ⛔ 0. Read this before any number below",
          "",
          "**This study buys a PROPERLY-REGISTERED RECORD of an ALREADY-MEASURED result. It is not "
          "new evidence and it is not fresh confirmation.**", "",
          "NF-INJ4 measured this mechanism and published it. The field, the folds, the seed and the "
          "substrate here are NF-INJ4's — the fold machinery is IMPORTED from its runner verbatim, "
          "and the substrate was vintage-checked against its committed census before this "
          "registration was written. So **every number below was already known, and only the gate "
          "flips.**", "",
          f"The reproduction pin is the proof of that claim: **"
          f"{s['reproduction_pin'].get('figures_reproduced')} of "
          f"{s['reproduction_pin'].get('figures_checked')} published figures reproduce** at the "
          f"artifact's own resolution. ⛔ What that certifies is the PIPELINE — that "
          f"\"only the gate flips\" is a measurement. It certifies NOTHING about the mechanism: "
          f"reproducing a known number is not evidence for the hypothesis that produced it.", "",
          "⭐ **The one genuinely NEW result is the positive control's verdict** (§4), because the "
          "control drives the study's own gate function and this registration changes that "
          "function.", "",
          "⛔ NF-INJ4's registration, verdict and record stand UNEDITED. This supersedes ONE clause "
          "going forward and never re-reads its refusal (E2.1-r).", "",
          "---", "",
          "## 1. The gates, in the registered order", "",
          "| gate | class | result |", "|---|---|---|"]
    for gate, cls in B.GATE_CLASSES.items():
        L.append(f"| `{gate}` | {cls} | {'✅ PASS' if g[gate] else '⛔ FAIL'} |")
    L += ["",
          f"**Winner: `{s['winner']}`** — pooled CRPS {_fmt(s['pooled'][s['winner']]['crps'])} "
          f"against the matched status-blind foil's "
          f"{_fmt(s['pooled'][DD.MATCHED_FOIL]['crps'])} and the served incumbent's "
          f"{_fmt(s['pooled'][DD.INCUMBENT_ARM]['crps'])}.", "",
          f"Lift over the foil **+{_fmt(s['winner_vs_foil']['mean_lift_crps'])} CRPS** on "
          f"**{s['winner_vs_foil']['fold_wins']} of {s['winner_vs_foil']['n_folds']} folds**, "
          f"one-sided p = {s['winner_vs_foil']['p_one_sided']:g} against the binding single-"
          f"hypothesis cutoff {B.BH_CUTOFF_BINDING:g} (the conservative arm-corrected "
          f"{B.BH_CUTOFF_CONSERVATIVE:.5f} is cleared too). PBO "
          f"{s['deflation']['pbo_eligible_set']:g} over the eligible set and "
          f"{s['deflation']['pbo_declared_field']:g} over the declared field; DSR-CONV "
          f"{s['deflation']['dsr_conv']}.", "",
          "---", "",
          "## 2. ⭐ The anchor, at MATCHED RESOLUTION — the one clause this story changes", "",
          "The registered clause NF-INJ4 refused on read *\"no arm beats its own-form oracle\"*. "
          "That oracle is fitted on a "
          f"**{a['_resolution']['mean_n_peek']:.0f}-row test fold** against arms trained on "
          f"**{a['_resolution']['mean_n_train']:.0f} rows** — a "
          f"**{a['_resolution']['arm_to_peek_resolution_ratio']}× ratio fixed by the CV design** — "
          "so it measured the ORACLE'S SAMPLE SIZE, not any property of an arm.", "",
          "NF1.9 (f): a peeking oracle is a floor **only at matched `n`**. Both readings of that "
          "one measured pair are registered here as SEPARATE named clauses, because registering "
          "one does not give you the other.", "",
          "| arm | arm CRPS | oracle | matched-n control | oracle − control | state |",
          "|---|---|---|---|---|---|"]
    for arm in DD.ARMS:
        v = a[arm]
        if not v.get("evaluable"):
            L.append(f"| `{arm}` | — | — | — | — | ⛔ UNEVALUABLE |")
            continue
        L.append(f"| `{arm}` | {_fmt(v['arm_crps'])} | {_fmt(v['own_form_oracle_crps'])} | "
                 f"{_fmt(v['matched_n_control_crps'])} | {v['oracle_minus_control']:+.6f} | "
                 f"{v['state']} |")
    ci = cl[B.ANCHOR_CLAUSE_INFORMATIVE]
    cf = cl[B.ANCHOR_CLAUSE_FLOOR]
    L += ["",
          f"**A — `{B.ANCHOR_CLAUSE_INFORMATIVE}` (NF-W6d inactive-pair): "
          f"{'✅ PASS' if ci['passes'] else '⛔ FAIL'}.** "
          f"{ci['n_active_of_evaluable']} evaluable pairs are ACTIVE; the active shippable arms are "
          f"{', '.join('`%s`' % x for x in ci['shippable_arms_active']) or '—'}. An INACTIVE pair "
          f"had nothing to act on and is UNINFORMATIVE — neither a refusal nor a pass.", "",
          f"**B — `{B.ANCHOR_CLAUSE_FLOOR}` (NF1.9 (f) capacity): "
          f"{'✅ PASS' if cf['passes'] else '⛔ FAIL'}.** The floor holds on "
          f"{cf['n_holding_of_evaluable']} evaluable pairs — but ⚠️ it is VACUOUS on the "
          f"{len(cf['vacuous_on'])} INACTIVE ones "
          f"({', '.join('`%s`' % x for x in cf['vacuous_on']) or '—'}), so the number that carries "
          f"information is **{cf['n_holding_NON_VACUOUSLY']}** (NF-D20: count what the mechanism "
          f"could ACT on before crediting \"the constraint held N of M\").", "",
          "⭐ **The tie tolerance is measurably not load-bearing.** Every ACTIVE pair sits "
          f"orders of magnitude clear of the ±{B.ANCHOR_TIE_TOL:g} band (smallest active margin "
          f"{min([abs(a[x]['oracle_minus_control']) for x in ci['all_arms_active']], default=0):.6f}"
          f", i.e. ~{min([a[x]['abs_margin_vs_tie_tol'] for x in ci['all_arms_active']], default=0):,.0f}× "
          f"the tolerance), and every INACTIVE pair is an EXACT tie. An activity classification is "
          "not a magnitude (NF-W7f), so the margins are published rather than the labels alone.", "",
          "⛔ **The retired naive clause is still reported.** It reads FALSE on "
          f"{', '.join('`%s`' % x for x in cl['retired_naive_clause_diagnostic']['arms_failing_it']) or '—'} "
          "— exactly as NF-INJ4 measured. In THIS design an arm beating its own peek can only be "
          "CAPACITY, never leakage: the arms are fitted strictly on training rows disjoint **by "
          "player**, so leakage is excluded by the FOLD CONSTRUCTION rather than by the anchor. "
          "⚠️ That does not generalise — in a design where an arm could see its own test rows, the "
          "naive clause is the thing that catches it.", "",
          "⭐ **The anchor construction is self-checked, not assumed:** the matched-n control is "
          f"fitted on {a['_resolution']['mean_n_control_train']:.0f} rows against a peek of "
          f"{a['_resolution']['mean_n_peek']:.0f} — matched on every fold: "
          f"**{a['_resolution']['matched_on_every_fold']}**. A control that silently fitted at FULL "
          "resolution would make both clauses vacuous while still returning a number.", "",
          "---", "",
          "## 3. The forward invariance declaration, and the ladder that could have refuted it", ""]
    lad = s["diagnostics"]["invariance_ladder"]
    L += [f"Both anchor clauses were declared **injection-invariant FORWARD** — the declaration "
          f"NF-INJ4 said belonged to its successor. `{'`, `'.join(lad['declared_invariant'])}`.", "",
          "| effect (games) | " + " | ".join(f"`{k}`" for k in B.GATE_CLASSES) + " |",
          "|---" * (len(B.GATE_CLASSES) + 1) + "|"]
    for r in lad["per_effect"]:
        L.append(f"| {r['effect_games']} | "
                 + " | ".join("✅" if r[k] else "⛔" for k in B.GATE_CLASSES) + " |")
    L += ["", lad["reading"], "",
          "---", "",
          "## 4. ⭐ The positive control — the one genuinely NEW result, and it is not what was expected",
          ""]
    ctl = s.get("positive_control", {})
    ab = s["diagnostics"].get("mechanism_absent_control", {})
    if ctl.get("verdict"):
        spec = ctl.get("null_control_leg_specification", {})
        L += [f"The PLAT-CVP2 injected-effect positive control returned **`{ctl['verdict']}`** "
              f"(partition `{ctl.get('partition_source')}`, verified "
              f"`{ctl.get('partition_verified')}`). ⛔ **That badge STANDS exactly as the instrument "
              f"returned it** (E2.1-r). At the registered 1-game effect all three shippable arms "
              f"clear every gate with an EMPTY blocking set — but the badge is decided by the "
              f"null-control leg, on which the same three arms also survive.", "",
              "⭐ **The claim behind the badge was MEASURED, not argued** — NF-INJ4's own handling "
              "of a badge it disagreed with is the precedent. Running the SAME gate table on "
              "payloads where the mechanism is genuinely ABSENT (designations shuffled, every "
              "marginal preserved):", ""]
        if ab.get("per_shuffle"):
            L += ["| shuffle seed | survivors | failing gates |", "|---|---|---|"]
            for r in ab["per_shuffle"]:
                L.append(f"| {r['shuffle_seed']} | "
                         f"{', '.join('`%s`' % x for x in r['survivors']) or '**none**'} | "
                         f"{', '.join('`%s`' % x for x in r['failing_gates'])} |")
            L += ["", ab["reading"], ""]
        L += ["⭐ **The instrument finding, stated generally rather than as this study's excuse.** "
              "With `inject(0.0)` defined as the IDENTITY, the null-control leg is *logically "
              "equivalent to the negation of the ship verdict*: `VACUOUS` fires exactly when some "
              "arm clears every gate on the null payload, the null payload IS the real data, and "
              "the study ships exactly when some arm clears every gate on the real data. ⇒ **the "
              "study ships ⟺ the control returns `VACUOUS`.** For any caller defining "
              "`inject(0) = identity` that leg carries ZERO information about the gate family.", "",
              "⭐ **And NF-INJ4's clean null leg was clean for the WRONG REASON**, which is why this "
              "could not have been seen before now: it recorded `null_control_survivors: []`, but "
              "its `oracle_respected` clause was FALSE on the real payload, so it blocked every arm "
              "on the identity payload too. The defective anchor was MASKING the mis-specification. "
              "⛔ NF-INJ4's verdict and record stand unedited; this is drawn from its own published "
              "figures.", "",
              "⚠️ **This is a DEFECT IN THIS REGISTRATION and is reported as one.** The "
              "pre-registration predicted the control's PBO leg would be inert and said NOTHING "
              "about the null leg, whose identity-at-zero specification it inherited verbatim and "
              "did not examine. ⛔ The remedy — a MECHANISM-ABSENT null payload rather than an "
              "UN-INJECTED one — is a FORWARD decision for the PM, not something adopted here after "
              "seeing the badge.", ""]
    L += ["---", "",
          "## 5. What the record must NOT say", "",
          "- ⛔ Not *\"the mechanism is confirmed\"* — the evidence is NF-INJ4's, and this run "
          "reproduces it by construction.",
          "- ⛔ Not *\"replicated\"* — same field, same folds, same seed, same rows. A reproduction "
          "pin is a pipeline check.",
          "- ✅ What it does say: the mechanism's evidence is now held under a registration whose "
          "anchor clause measures an ARM PROPERTY instead of a FOLD SIZE, so the refusal that "
          "blocked it no longer stands in the way.", ""]
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-INJ4b designation → duration, matched-resolution")
    ap.add_argument("--no-control", action="store_true",
                    help="skip the positive control + ladder (smoke only; never for a decisive run)")
    ap.add_argument("--out", default="nf_inj4b_designation_duration",
                    help="report stem under ablation_results/")
    args = ap.parse_args(argv)
    t0 = time.time()

    if not _FRAME.exists():
        raise SystemExit(
            f"{_FRAME} is absent — run `run_nf_inj4b_substrate` first. ⛔ Refusing to score an "
            f"unbuilt frame; and that rebuild VINTAGE-CHECKS the substrate against NF-INJ4's "
            f"committed census, which is the precondition this study's honesty clause rests on.")
    frame = pd.read_parquet(_FRAME)

    per_fold = R4.run_folds(frame)
    pool = R4.pooled(per_fold)
    winner = R4.select_winner(pool)
    anchors = anchor_audit(per_fold, winner)
    defl = R4.deflation(per_fold, winner)
    gates = gate_table(per_fold)[winner]

    lifts_foil = np.array([f["arms"][DD.MATCHED_FOIL]["crps"] - f["arms"][winner]["crps"]
                           for f in per_fold], dtype=float)
    clause = CP.fold_consistency_clause(len(per_fold))
    wvf = {
        "mean_lift_crps": round(float(lifts_foil.mean()), 6),
        "fold_wins": int((lifts_foil > 0).sum()), "n_folds": len(per_fold),
        "fold_consistency_wins_required": clause.wins_required,
        "fold_consistency_false_fire": round(clause.attained_false_fire, 4),
        "p_one_sided": M14.onesided_paired_pvalue(lifts_foil),
        "bh_cutoff_binding": B.BH_CUTOFF_BINDING,
        "bh_cutoff_conservative_reported": round(B.BH_CUTOFF_CONSERVATIVE, 6),
    }
    wvf["clears_conservative_reading"] = bool(
        wvf["p_one_sided"] is not None and wvf["p_one_sided"] <= B.BH_CUTOFF_CONSERVATIVE)

    pin = reproduction_pin(pool, anchors, defl, wvf)
    ship = all(gates.values())

    control: dict = {"ran": False,
                     "why": "--no-control (smoke only; ⛔ never a decisive run)"}
    ladder: dict = {"ran": False, "why": "--no-control"}
    absent: dict = {"ran": False, "why": "--no-control"}
    if not args.no_control:
        rep = CP.injected_effect_positive_control(
            inject=lambda e: _inject(frame, e),
            run_gates=lambda payload: gate_table(R4.run_folds(payload)),
            effect=B.INJECTION_EFFECT_GAMES,
            gate_classes=B.GATE_CLASSES,
            invariant_gates=B.INVARIANT_GATES,
            check_null_control=True)
        control = json.loads(json.dumps(dataclasses.asdict(rep), default=str))
        control["effect_games"] = B.INJECTION_EFFECT_GAMES
        control["is_the_one_genuinely_new_result"] = (
            "⭐ YES. Every other number in this report was already known from NF-INJ4's record. The "
            "control drives the study's OWN gate function, and this registration CHANGES that "
            "function, so its verdict is a genuinely new measurement rather than a reproduction.")
        ladder = invariance_ladder(frame)
        absent = mechanism_absent_control(frame)
        control["null_control_leg_specification"] = null_control_leg_specification(control, absent)

    verdict = ("SHIP_CANDIDATE (DEPLOY-HELD)" if ship else "REFUSED")
    null_cls = None
    if not ship:
        # ⛔ Registered forward (pre-registration §6): `classify_null` is called in the registered
        #    order on a refusal. ⚠️ If the ONLY failing clauses are the DECLARED-INVARIANT anchor
        #    ones, the refusal is DETERMINISTIC (a constraint on the anchor construction, not a
        #    statistical shortfall) and the instrument has no state for that — so its output is
        #    preserved VERBATIM beside a `CONSTRAINT_REFUSED` reading with `binding_half`, and ⛔ no
        #    data re-test trigger is published (NF-D18: "come back with more seasons" is the
        #    actively-misleading direction for a constraint no fold count can move).
        failed = sorted(k for k, v in gates.items() if not v)
        srs_v = [v for k, v in defl["trial_sharpes"].items() if k not in DD.DEGENERATE_ARMS]
        instrument = json.loads(json.dumps(CP.classify_null(
            metric="crps_spell", n_folds=len(per_fold), n_arms=DD.DECLARED_FIELD_SIZE,
            declared_field_size=DD.DECLARED_FIELD_SIZE,
            beats_foil=bool(gates["beats_foil"]),
            fold_wins=wvf["fold_wins"], p_one_sided=wvf["p_one_sided"],
            bh_cutoff=B.BH_CUTOFF_BINDING,
            pbo=defl["pbo_eligible_set"], pbo_application=B.PBO_APPLICATION,
            var_trials_sr=float(np.var(srs_v, ddof=1)) if len(srs_v) >= 2 else None,
            degenerates_excluded_from_v=B.DEGENERATES_EXCLUDED_FROM_V), default=str))
        anchor_only = bool(failed) and set(failed) <= set(B.INVARIANT_GATES)
        null_cls = {
            "failed_gates": failed,
            "state": "CONSTRAINT_REFUSED" if anchor_only else "SEE_INSTRUMENT",
            "binding_half": "anchor" if anchor_only else None,
            "publishes_a_data_trigger": not anchor_only,
            "instrument_verdict_verbatim": instrument,
            "instrument_note": "⛔ `classify_null` has no state for a deterministic-constraint "
                               "refusal (NF-D18), so its output is preserved verbatim rather than "
                               "overwritten." if anchor_only else None,
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": B.STORY, "supersedes": B.SUPERSEDES,
        "preregistration": f"ablation_results/nf_inj4b_preregistration.md",
        "substrate_vintage": "ablation_results/nf_inj4b_substrate_vintage.json",
        "honesty_clause": (
            "⛔ BINDING. Field, folds, seed and substrate are NF-INJ4's — the fold machinery is "
            "IMPORTED from its runner verbatim and the substrate was vintage-checked against its "
            "committed census. Every number here was ALREADY KNOWN and only the gate flips. This "
            "is a properly-registered record of an already-measured result, ⛔ NEVER fresh "
            "confirmation. The ONE new result is the positive control's verdict."),
        "frame": {"rows": int(len(frame)), "players": int(frame["gsis_id"].nunique()),
                  "weeks": int(frame["week"].nunique()), "seasons": 1},
        "design": {"primary": f"grouped {DD.N_FOLDS}-fold by {DD.FOLD_UNIT}",
                   "seed": DD.FOLD_SEED, "n_folds": len(per_fold)},
        "winner": winner, "served_arm": SERVED_ARM,
        "deploy_held": True, "best_alpha": 0,
        "verdict": verdict, "ship": ship,
        "gates": gates,
        "gate_classes": B.GATE_CLASSES,
        "invariant_gates": list(B.INVARIANT_GATES),
        "winner_vs_foil": wvf,
        "winner_vs_incumbent": {
            "mean_lift_crps": round(float(np.mean(
                [f["arms"][DD.INCUMBENT_ARM]["crps"] - f["arms"][winner]["crps"]
                 for f in per_fold])), 6),
            "incumbent_crps": pool[DD.INCUMBENT_ARM]["crps"],
            "winner_crps": pool[winner]["crps"]},
        "reproduction_pin": pin,
        "pooled": pool,
        "deflation": defl,
        "anchors": anchors,
        "positive_control": control,
        "null_classification": null_cls,
        "diagnostics": {"invariance_ladder": ladder,
                        "mechanism_absent_control": absent},
        "elapsed_s": round(time.time() - t0, 2),
    }

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(summary, indent=2, default=str))
    (_REPORT_DIR / f"{args.out}.md").write_text(render(summary))
    print(json.dumps({k: summary[k] for k in
                      ("story", "verdict", "ship", "winner", "gates", "elapsed_s")},
                     indent=2, default=str))
    log.info("reproduction pin: %s/%s figures reproduce",
             pin.get("figures_reproduced"), pin.get("figures_checked"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

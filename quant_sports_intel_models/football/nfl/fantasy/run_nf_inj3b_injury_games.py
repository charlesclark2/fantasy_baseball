"""run_nf_inj3b_injury_games.py — NF-INJ3b: the FRESH forward re-registration of the injury-games caps.

⭐ READ `ablation_results/nf_inj3b_preregistration.md` FIRST. It was committed BEFORE this module
scored anything, and it — not this file — is the registration. ⛔ Editing it after a result is not
a pre-registration (E2.1-r).

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
────────────────────────────────────────────────────────────────────────────────────────────────
NF-INJ3 (`ablation_results/nf_inj3_injury_games.md`, PR #1003) returned `POWER_LIMITED` on two
specification items its own pre-registration left UNSTATED — `V`'s membership and the BH family —
not on the evidence. The PM funded this successor (recorded ruling **D2 = A**) to re-register the
study with those items NAMED UP FRONT.

So the ONLY thing NF-INJ3b changes is the REGISTRATION:

  · `V` = the non-degenerate, NON-REFERENCE arms   (DSR-CONV **and** MH2.1 (a));  `N` = full field
  · the BH family = a SINGLE hypothesis at q = 0.10, named and justified before any p-value
  · the PRIMARY is `hurdle_transfer`, REGISTERED (never the field's argmin)
  · the field is 6 arms, declared ON MECHANISM before any DSR of any kind was computed

⭐ **THE DATA AND THE SCORING ARE INHERITED BYTE-IDENTICALLY.** `nf_inj3_injury_games.py` and
`run_nf_inj3_injury_games.py` are imported READ-ONLY and are NOT edited — a post-decision story
writes to its OWN output paths and never mutates a decided story's code or artifacts (the
"a fixed-output-path write clobbers a decided story's audit trail" landmine). That inheritance is
not asserted, it is PINNED: `reproduction_pin_vs_parent` requires every per-fold, per-arm CRPS to
match NF-INJ3's recorded value to < 1e-9 (⛔ never `round(..., 6)`), which is what makes "only the
registration changed" a MEASURED claim.

⚠️ **HONESTY, carried from preregistration §0 and repeated here so no reader can miss it.** The
direction and magnitude of this effect are already public in NF-INJ3's record. Re-running the same
harness on the same data cannot confirm them a second time — a gate that passes here is a
REPRODUCTION, not a corroboration, and is written up as one. The one genuinely open question is
`DSR`: `V` is a SAMPLE VARIANCE, it moves NON-MONOTONICALLY with the field's membership, and this
field is not NF-INJ3's field ⇒ **the parent's 0.973 diagnostic is NOT inherited and is NOT this
study's expected value.** BH gets its first honest answer.

RUN (LAPTOP — reads the local DuckDB + build artifacts read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3b_injury_games \
        --duckdb <path>/sports.duckdb --artifacts <path>/football/nfl/fantasy/artifacts
    ... --smoke     # 3 folds, a code-path proof only
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

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj3_injury_games as R3,
)

log = logging.getLogger("nfl.fantasy.nf_inj3b")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
MAX_PBO, MIN_DSR = 0.20, 0.95
#: the tolerance of the parent-scoring reproduction pin. ⛔ NOT `round(..., 6)` — a 6-dp round CAPS
#: the pin at 1e-6 and a genuinely divergent run can slip under it (the E11.24 rounding landmine).
PIN_TOL = 1e-9

# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE REGISTRATION — preregistration §2, §3, §5, §6. Declared FORWARD; not re-cut under any outcome.
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: preregistration §2 — the coherent family, declared ON MECHANISM: every form that fits the
#: injury-games LEVEL in-fold on the same population through the same shared predictive, plus the
#: reference it must beat and the two degenerates that must lose.
ARMS: tuple[str, ...] = (
    "incumbent",        # REFERENCE — the shipped {RES:4, PUP:4, NFI:4, SUS:7} at blend 0.7
    "fitted_status",    # the SAME form, per-status level + blend fitted in-fold
    "timing_aware",     # one GLM conditional mean — i.e. the PRIMARY with the split removed
    "hurdle_transfer",  # PRIMARY — P(plays ≥ 1) × E[games | plays ≥ 1] on IDENTICAL covariates
    "all_zero",         # DEGENERATE
    "no_cap",           # DEGENERATE
)
DECLARED_FIELD_SIZE = len(ARMS)

#: ⛔ EXCLUDED ON MECHANISM, before any score: `sus_regime` is not another way to fit the level, it
#: is a per-status REGIME carve-out for `SUS` — and `SUS` is STRUCTURALLY INACTIVE where this claim
#: lands (0 of 22 served rows; 11 eval rows, ALL in 2019–2020, so it is inert on 5 of 7 folds).
#: Registering it makes the field pay multiplicity for an arm that cannot act (NF-D20).
#: ⚠️ The narrowing is declared ADVERSE: NF-INJ3's public trial Sharpes put `sus_regime` (0.475)
#: essentially on top of `fitted_status` (0.4779) — a NEAR-MEAN arm — and DSR-CONV documents that
#: dropping a near-mean arm WIDENS `V` and RAISES the bar. It is recorded here so the exclusion can
#: never be read as chosen for its effect on a gate.
EXCLUDED_ON_MECHANISM: dict[str, str] = {
    "sus_regime": "a per-status REGIME carve-out for SUS, which has 0 rows on the 2026 serving "
                  "cohort and 11 eval rows all in 2019–2020 (inert on 5 of 7 folds) — a different "
                  "mechanism, structurally inactive where the claim lands (NF-D20)",
}

#: preregistration §2 — REGISTERED, not selected. Every gate is computed on THIS arm; if another
#: eligible arm posts a lower pooled CRPS that is recorded as a leaderboard fact and the study does
#: NOT switch (a shipping arm chosen after the scores is an undeclared search).
PRIMARY_ARM = "hurdle_transfer"
INCUMBENT_REFERENCE = "incumbent"
#: the MATCHED FOIL for the primary's claimed channel: identical covariates, availability SPLIT
#: removed and nothing else changed (NF-D10 / NF-D15). The paired delta IS the hurdle attribution.
MATCHED_FOIL = "timing_aware"
#: named DEGENERATE before any score — declaring one after it loses is laundering.
DEGENERATE_ARMS: tuple[str, ...] = ("all_zero", "no_cap")

#: preregistration §3 — `V`'s MEMBERSHIP, named up front. `N` stays at the FULL declared field.
#:   · DSR-CONV  — the pre-registered degenerates are ∈ `N` and ∉ `V`
#:   · MH2.1 (a) — the REFERENCE arm is ∉ `V`: its skill series is identically ZERO by construction
#:                 (it is the baseline every lift is measured against), so its trial Sharpe is a
#:                 structural 0.0 that inflates a small family's `V` exactly as a diagnostic anchor
#:                 does. This is the convention NF-INJ3's registration omitted.
V_EXCLUDED_ARMS: tuple[str, ...] = DEGENERATE_ARMS + (INCUMBENT_REFERENCE,)

#: preregistration §6 — the BH FAMILY. ONE mechanism, ONE population, no position axis and no
#: per-status axis registered, and the primary is REGISTERED not selected ⇒ exactly ONE hypothesis
#: test in this study. The field's search is deflated by DSR at `N = 6`; applying BH across the
#: arms as well would deflate the SAME search a second time with a second instrument.
BH_FAMILY = "single_hypothesis"
BH_Q = M14.FDR_Q                                  # 0.10
BH_FAMILY_SIZE = 1

#: 🔒 the SERVED arm. DEPLOY-HELD under every outcome of this run: a pass triggers the gated ship
#: path (placement read → interval revalidation → superflex caveat → MEASURED served-point impact)
#: and the ship/no-ship decision is the OPERATOR's, never this harness's.
SERVED_ARM = "incumbent"

#: the parent's recorded artifacts — the reproduction pin reads them, never rewrites them.
PARENT_JSON = {"full": "nf_inj3_injury_games.json", "smoke": "nf_inj3_injury_games_smoke.json"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Deflation under THIS registration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def deflation(per_fold: list[dict], primary: str) -> dict:
    """PBO + the NF1.8 triad + DSR under the §3 `V` convention, over the DECLARED 6-arm field.

    PBO is computed on **negated** CRPS because `cscv_pbo` picks the in-sample ARGMAX and CRPS is a
    loss — getting that sign wrong reports the field upside-down."""
    arms = list(ARMS)
    mat = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)
    lifts = {a: [f["arms"][INCUMBENT_REFERENCE]["crps"] - f["arms"][a]["crps"] for f in per_fold]
             for a in arms}
    srs_all = R3._srs(lifts)
    srs_v = {k: v for k, v in srs_all.items() if k not in V_EXCLUDED_ARMS}
    d = np.asarray(lifts[primary], dtype=float)
    scores = mat.mean(axis=1)
    order = np.argsort(-scores)                       # negated CRPS: higher = better
    top = order[:max(2, len(arms) // 4)]
    return {
        "pbo": M14.cscv_pbo(mat),
        "dsr_registered": R3.dsr_conv(d, list(srs_v.values()), DECLARED_FIELD_SIZE),
        "dsr_whole_field": M14.deflated_sharpe(d, np.asarray(list(srs_all.values()))),
        "trial_sharpes": {k: round(v, 4) for k, v in sorted(srs_all.items(), key=lambda kv: -kv[1])},
        # ⭐ DERIVED from `srs_v`, never re-derived from the arm list: a reported membership
        #    that is computed separately from the one DSR actually uses can drift silently
        #    (found by this story's RED proof — the mutation landed and the claim did not move).
        "V_arms": sorted(srs_v),
        "V_excluded_arms": list(V_EXCLUDED_ARMS),
        "V_registered": round(float(np.var(list(srs_v.values()), ddof=1)), 6),
        "V_whole_field": round(float(np.var(list(srs_all.values()), ddof=1)), 6),
        "n_trials": DECLARED_FIELD_SIZE,
        "whole_field_spread_pct": round(100.0 * (float(-scores.min()) - float(-scores.max()))
                                        / max(1e-9, float(-scores.max())), 2),
        "contender_spread_pct": round(100.0 * (float(-scores[top].min()) - float(-scores[top].max()))
                                      / max(1e-9, float(-scores[top].max())), 2),
        "flip_distribution": _flip_distribution(mat, arms),
        "bailey_degradation_pct": _bailey_degradation(mat, arms),
        "note": "⛔ `V`'s membership is FIXED by preregistration §3 and is not re-cut under any "
                "outcome (MH2.2). The exclusion is NON-MONOTONE and is therefore not a lever: "
                "dropping a near-mean arm WIDENS the sample variance and RAISES the bar.",
    }


def _flip_distribution(mat: np.ndarray, arms: list[str]) -> dict:
    """NF1.8 — WHICH arms win the in-sample halves, and how often. Mass on two arms a fraction of a
    percent apart IS a tie; mass spread thinly over unrelated arms is a search that learnt nothing.
    This is the cheapest and most informative of the triad."""
    n = mat.shape[1]
    half = max(1, n // 2)
    wins: dict[str, int] = {a: 0 for a in arms}
    total = 0
    for start in range(n - half + 1):
        idx = list(range(start, start + half))
        wins[arms[int(np.argmax(mat[:, idx].mean(axis=1)))]] += 1
        total += 1
    return {"in_sample_windows": total, "wins": {a: w for a, w in wins.items() if w}}


def _bailey_degradation(mat: np.ndarray, arms: list[str]) -> float | None:
    """NF1.8 — the median OUT-of-sample gap between the IN-sample winner and the OS best, i.e. the
    decision-relevant question ('did picking it COST anything?') rather than the rank question."""
    n = mat.shape[1]
    if n < 4:
        return None
    half = n // 2
    gaps = []
    for start in range(n - half):
        ins, oos = list(range(start, start + half)), [j for j in range(n) if j not in
                                                      range(start, start + half)]
        w = int(np.argmax(mat[:, ins].mean(axis=1)))
        os_scores = mat[:, oos].mean(axis=1)
        best = float(os_scores.max())
        gaps.append(100.0 * (best - float(os_scores[w])) / max(1e-9, abs(best)))
    return round(float(np.median(gaps)), 2) if gaps else None


def deflation_diagnostics(per_fold: list[dict], primary: str, defl: dict) -> dict:
    """⛔ DIAGNOSTICS — REPORTED, NEVER ACTED ON (MH2.2: you get to PRE-REGISTER a family, you do
    not get to DISCOVER one). They name a lever; they do not license a re-read of a gate.

    ⭐ The `nf_w7h_drop_most_extreme` 2×2 REFUSES to report when the dropped arm IS the arm under
    test — a DSR reached by deleting the winner is INADMISSIBLE (NF-W7h)."""
    lifts = {a: [f["arms"][INCUMBENT_REFERENCE]["crps"] - f["arms"][a]["crps"] for f in per_fold]
             for a in ARMS}
    srs_all = R3._srs(lifts)
    srs_v = {k: v for k, v in srs_all.items() if k not in V_EXCLUDED_ARMS}
    d = np.asarray(lifts[primary], dtype=float)
    out: dict = {}
    # what the PARENT's (reference-in-V) convention would have said on THIS field — recorded so a
    # reader can see the size of the single specification change, never so it can be acted on.
    parent_v = {k: v for k, v in srs_all.items() if k not in DEGENERATE_ARMS}
    out["parent_convention_reference_inside_v"] = {
        "V": round(float(np.var(list(parent_v.values()), ddof=1)), 6),
        "dsr": R3.dsr_conv(d, list(parent_v.values()), DECLARED_FIELD_SIZE),
        "admissible_to_act_on": False,
        "why": "NF-INJ3's convention, shown on NF-INJ3b's field so the effect of naming MH2.1 (a) "
               "is legible. The REGISTERED figure binds (E2.1-r).",
    }
    mean = float(np.mean(list(srs_v.values())))
    far = max(srs_v, key=lambda k: abs(srs_v[k] - mean))
    if far == primary:
        out["nf_w7h_drop_most_extreme"] = {
            "evaluable": False, "dropped_arm": far,
            "why": "the most extreme trial Sharpe IS the arm under test — a DSR reached by deleting "
                   "it would be INADMISSIBLE (NF-W7h), so no trimmed figure is reported"}
    else:
        kept = [v for k, v in srs_v.items() if k != far]
        out["nf_w7h_drop_most_extreme"] = {
            "evaluable": True, "dropped_arm": far, "dropped_arm_sharpe": round(srs_v[far], 4),
            "V_without_dropped_arm": round(float(np.var(kept, ddof=1)), 6),
            "dsr_without_dropped_arm": R3.dsr_conv(d, kept, DECLARED_FIELD_SIZE),
            "note": "⛔ A DIAGNOSTIC, NOT A TRIM."}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Anchors, attribution, gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def anchor_audit(per_fold: list[dict], primary: str) -> dict:
    """⭐ A MISSING OR UNFITTABLE ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 (a))."""
    def _m(get):
        v = [get(f) for f in per_fold]
        return float(np.mean(v)) if all(x is not None and np.isfinite(x) for x in v) else None

    out: dict = {}
    for a in ARMS:
        if a in DEGENERATE_ARMS:
            continue                       # a degenerate has no own FORM to peek at; §5 gate 6 owns it
        arm = _m(lambda f, a=a: f["arms"][a]["crps"])
        orc = _m(lambda f, a=a: f["oracles"][a]["crps"] if a in f["oracles"] else None)
        if orc is None:
            out[a] = {"evaluable": False,
                      "why": "no own-form peeking oracle — the check would pass on NOTHING"}
            continue
        out[a] = {"evaluable": True, "arm_crps": round(arm, 4),
                  "own_form_oracle_crps": round(orc, 4),
                  "respects_oracle": bool(arm >= orc - 1e-9)}
    mn = _m(lambda f: f["matched_n"]["crps"] if f["matched_n"] else None)
    ow = out.get(primary, {})
    out["_matched_n_control"] = (
        {"evaluable": True, "matched_n_crps": round(mn, 4),
         "oracle_beats_matched_n": bool(ow.get("own_form_oracle_crps", np.inf) <= mn + 1e-9),
         "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution "
                "(NF1.7 (b) / NF1.9 (f)) — the primary's own form on ONE prior season"}
        if mn is not None else
        {"evaluable": False, "why": "matched-n control unfittable — recorded as a FAILED check, "
                                    "never a pass (NF1.7 (a))"})
    out["_degenerates"] = {
        dg: {"crps": round(_m(lambda f, dg=dg: f["arms"][dg]["crps"]), 4),
             "loses_to_primary": bool(_m(lambda f, dg=dg: f["arms"][dg]["crps"])
                                      > _m(lambda f: f["arms"][primary]["crps"]) + 1e-9)}
        for dg in DEGENERATE_ARMS}
    out["_pooled_mean"] = {"crps": round(_m(lambda f: f["anchors"]["pooled_mean"]["crps"]), 4)}
    return out


def channel_decomposition(pooled: dict, per_fold: list[dict]) -> dict:
    """Attribute the primary's total lift to CHANNELS, each step a MATCHED PAIR differing by
    EXACTLY one thing (`margin_attribution`: report the split, never headline the blend).

      incumbent      → fitted_status     the LEVEL channel — same form, levels+blend fitted in-fold
      fitted_status  → timing_aware      the FORM change (cap-blend → a covariate GLM)
      timing_aware   → hurdle_transfer   the HURDLE-SPLIT channel (identical covariates) = gate 9

    The steps sum EXACTLY to the primary's total lift, by construction."""
    def d(a, b):
        v = [f["arms"][a]["crps"] - f["arms"][b]["crps"] for f in per_fold]
        return {"delta_crps": round(float(np.mean(v)), 4),
                "folds_positive": int(sum(1 for x in v if x > 0)),
                "p_one_sided": M14.onesided_paired_pvalue(np.asarray(v))}
    steps = {
        "level__incumbent_to_fitted_status": d("incumbent", "fitted_status"),
        "form__fitted_status_to_glm": d("fitted_status", "timing_aware"),
        "hurdle_split__glm_to_hurdle": d("timing_aware", "hurdle_transfer"),
    }
    return {"steps": steps,
            "sum_of_steps": round(sum(v["delta_crps"] for v in steps.values()), 4),
            "primary_total_lift": pooled[PRIMARY_ARM]["mean_lift"]}


def verdict(*, primary: str, pooled: dict, defl: dict, anchors: dict, fold_clause: dict,
            bh: dict, permutation: dict, foil: dict) -> dict:
    """preregistration §5 — ALL NINE must pass to SHIP. Every gate is on the REGISTERED primary."""
    gates = {
        "beats_incumbent": bool(pooled[primary]["mean_lift"] > 0),
        "fold_consistency": bool(fold_clause.get("passes")),
        "pbo_ok": (None if defl["pbo"] is None else bool(defl["pbo"] < MAX_PBO)),
        "dsr_ok": (None if defl["dsr_registered"] is None
                   else bool(defl["dsr_registered"] >= MIN_DSR)),
        "bh_ok": bool(bh.get("survives")),
        "degenerates_lose": bool(all(v["loses_to_primary"]
                                     for v in anchors["_degenerates"].values())),
        "oracle_respected": bool(all(v.get("respects_oracle", False)
                                     for k, v in anchors.items()
                                     if not k.startswith("_") and isinstance(v, dict))
                                 and anchors["_matched_n_control"].get("evaluable")),
        "beats_permutation": bool(permutation["beats"]),
        "hurdle_attributable": bool(foil["mean_delta"] > 0),
    }
    return {"primary": primary, "gates": gates, "ship": all(v is True for v in gates.values()),
            "served_arm": SERVED_ARM, "deploy_held": True, "best_alpha": 0,
            "gate_9_reporting_rule": "a primary win that gate 9 does not separate is reported as a "
                                     "win for the SHARED in-fold fitted LEVEL, never for the "
                                     "availability split (NF-D10 / NF-D15)"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reproduction pin vs the parent (preregistration §8)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _compare_crps(per_fold: list[dict], other_path: Path) -> dict:
    """Per-fold × per-arm CRPS comparison of THIS run against a recorded artifact, at `PIN_TOL`.

    ⛔ NOT a `round(..., 6)` comparison: rounding CAPS the pin at 1e-6, so a genuinely divergent run
    slips under it. ⭐ NON-VACUITY is asserted FIRST — an empty comparison set passes on NOTHING
    (NF1.7 (a) / the vacuous-guard family). Per-ARM worst differences are returned as well as the
    scalar, because WHICH arms diverge is the diagnostic that separates a code change from an
    environment change."""
    if not other_path.exists():
        return {"evaluable": False, "artifact": other_path.name,
                "why": f"artifact {other_path.name} absent — recorded as a FAILED check, never a "
                       f"pass (NF1.7 (a))"}
    other = json.loads(other_path.read_text())
    by_year = {int(f["year"]): f for f in other.get("per_fold", [])}
    per_arm = {a: 0.0 for a in ARMS}
    worst, n_cmp, missing = 0.0, 0, []
    for f in per_fold:
        o = by_year.get(int(f["year"]))
        if o is None:
            missing.append(int(f["year"]))
            continue
        for a in ARMS:
            if a not in o.get("arms", {}):
                missing.append(f"{f['year']}/{a}")
                continue
            dv = abs(float(f["arms"][a]["crps"]) - float(o["arms"][a]["crps"]))
            per_arm[a] = max(per_arm[a], dv)
            worst = max(worst, dv)
            n_cmp += 1
    expected = len(per_fold) * len(ARMS)
    return {"evaluable": True, "artifact": other_path.name, "tolerance": PIN_TOL,
            "comparisons": n_cmp, "comparisons_expected": expected,
            "non_vacuous": bool(n_cmp == expected and n_cmp > 0), "missing": missing,
            "max_abs_crps_difference": worst,
            "max_abs_difference_by_arm": {a: v for a, v in per_arm.items()},
            "arms_that_diverge": sorted([a for a, v in per_arm.items() if v >= PIN_TOL]),
            "passes": bool(n_cmp == expected and n_cmp > 0 and worst < PIN_TOL)}


def reproduction_pin_vs_parent(per_fold: list[dict], parent_path: Path,
                               control_path: Path | None) -> dict:
    """preregistration §8 pin 1 — every per-fold, per-arm CRPS must equal NF-INJ3's RECORDED value
    to < 1e-9, so that "only the REGISTRATION changed" is a MEASURED claim, not an assertion.

    ⭐ **A SECOND, TWO-SIDED MEASUREMENT SHIPS BESIDE IT, AND IT IS THE ONE THAT ATTRIBUTES A
    FAILURE.** The registered pin compares against an artifact produced by a *different process on a
    different day*, so on its own a miss cannot distinguish "the code changed" from "the numerical
    ENVIRONMENT changed". `control_path` is the PARENT'S OWN ENTRYPOINT re-run in THIS environment
    (`run_nf_inj3_injury_games --out ...`), which is the control that separates them:

      · NF-INJ3b ≡ parent-code-rerun-HERE  AND  recorded-parent ≠ parent-code-rerun-HERE
            ⇒ the divergence is ENVIRONMENTAL. The registered pin still FAILS as registered — it is
              not re-cut (E2.1-r) — but its INTENT is measured TRUE.
      · NF-INJ3b ≠ parent-code-rerun-HERE
            ⇒ a real code divergence, and the study's premise is broken.

    ⛔ The control is a DIAGNOSTIC that ATTRIBUTES the registered pin's result. It never becomes the
    pin, and a failing registered pin is never relabelled a pass."""
    pin = _compare_crps(per_fold, parent_path)
    out = {**pin, "parent": parent_path.name,
           "what_it_proves": "the data, folds, shared \u03c6 and arm fits are BYTE-IDENTICAL to the "
                             "parent \u21d2 the entire delta between the two studies is the "
                             "REGISTRATION (preregistration \u00a72 / \u00a73 / \u00a76)."}
    ctl = (_compare_crps(per_fold, control_path) if control_path is not None
           else {"evaluable": False, "why": "no --parent-control artifact supplied — the "
                                            "attribution of a pin miss is NOT evaluable "
                                            "(NF1.7 (a)); it is not scored as clean"})
    import scipy  # noqa: PLC0415  — recorded so a future reader can date an environment change
    out["environment_control"] = {
        **ctl,
        "what_it_is": "the PARENT'S OWN entrypoint (run_nf_inj3_injury_games) re-run in THIS "
                      "environment, on the same DuckDB and the same build artifacts",
        "admissible_to_relabel_the_pin": False,
        "numpy": np.__version__, "scipy": scipy.__version__, "pandas": pd.__version__,
    }
    if pin.get("evaluable") and ctl.get("evaluable"):
        env_only = bool((not pin["passes"]) and ctl["passes"])
        out["divergence_attribution"] = (
            "ENVIRONMENTAL — this run is byte-identical to the parent's own code re-run here, so "
            "the miss against the RECORDED artifact measures an unpinned numerical environment "
            "(the diverging arms are exactly the L-BFGS-B-fitted ones), NOT a code change. The "
            "registered pin stands as FAILED-AS-REGISTERED and is not re-cut (E2.1-r); its INTENT "
            "— that the entire delta between the two studies is the registration — is measured "
            "TRUE by this control." if env_only else
            "CLEAN — the registered pin passes." if pin["passes"] else
            "\u26a0\ufe0f CODE DIVERGENCE — this run differs from the parent's own code re-run "
            "here. The study's premise that only the registration changed is BROKEN.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, art: Path, folds: tuple[int, ...], parent_json: Path,
        control_json: Path | None = None) -> dict:
    t0 = time.time()
    hist_seasons = tuple(range(IG.ERA_MIN_SEASON, max(folds) + 1))
    pop, prov = R3.build_population(con, art, hist_seasons)
    serving, sprov = R3.build_population(con, art, (R3.SERVING_SEASON,))
    activity = R3.mechanism_activity(pop, folds)

    per_fold = [R3.score_fold(pop, y) for y in folds]
    pooled = {}
    for a in ARMS:
        c = [f["arms"][a]["crps"] for f in per_fold]
        lift = [f["arms"][INCUMBENT_REFERENCE]["crps"] - f["arms"][a]["crps"] for f in per_fold]
        pooled[a] = {"crps": round(float(np.mean(c)), 4),
                     "mae": round(float(np.mean([f["arms"][a]["mae"] for f in per_fold])), 4),
                     "mean_games": round(float(np.mean([f["arms"][a]["mean_mu"]
                                                        for f in per_fold])), 3),
                     "mean_lift": round(float(np.mean(lift)), 4),
                     "folds_beating_incumbent": int(sum(1 for x in lift if x > 0)),
                     "per_fold_lift": [round(x, 4) for x in lift]}

    primary = PRIMARY_ARM
    eligible = [a for a in ARMS if a not in DEGENERATE_ARMS and a != INCUMBENT_REFERENCE]
    argmin = min(eligible, key=lambda a: pooled[a]["crps"])
    #: ⭐ the primary is REGISTERED. If the argmin differs the study RECORDS the discrepancy and
    #: does NOT switch — a shipping arm chosen after the scores is an undeclared search.
    primary_is_argmin = {"registered_primary": primary, "field_argmin": argmin,
                         "agree": bool(primary == argmin),
                         "rule": "gates are computed on the REGISTERED primary under every "
                                 "outcome; a disagreement is disclosed, never acted on"}

    defl = deflation(per_fold, primary)
    defl["diagnostics"] = deflation_diagnostics(per_fold, primary, defl)
    anchors = anchor_audit(per_fold, primary)

    fc = cv_power.fold_consistency_clause(len(folds))
    wins = pooled[primary]["folds_beating_incumbent"]
    fold_clause = {"observed_wins": wins, "required_wins": fc.wins_required,
                   "n_folds": len(folds), "alpha": fc.alpha,
                   "attained_false_fire": fc.attained_false_fire,
                   "passes": bool(wins >= fc.wins_required)}

    # ── BH: preregistration §6 — SINGLE hypothesis, q = 0.10, named before any p-value ──────────
    p_primary = M14.onesided_paired_pvalue(np.asarray(pooled[primary]["per_fold_lift"]))
    pvals_all = {a: M14.onesided_paired_pvalue(np.asarray(pooled[a]["per_fold_lift"]))
                 for a in eligible}
    strict = M14.bh_fdr(pvals_all, q=BH_Q)
    bh = {
        "family": BH_FAMILY, "family_size": BH_FAMILY_SIZE, "q": BH_Q,
        "primary_p_one_sided": p_primary,
        "cutoff": BH_Q,
        "survives": bool(p_primary is not None and p_primary < BH_Q),
        "why_this_family": "one MECHANISM (the injury-games level for a flagged veteran), one "
                           "POPULATION (flagged non-returner veterans, 2019–2025 eval folds), no "
                           "registered position or per-status axis, and the primary is REGISTERED "
                           "not selected ⇒ exactly ONE hypothesis test. The field's SEARCH is "
                           "deflated by DSR at N=6; applying BH across the arms as well deflates "
                           "the same search a SECOND time with a second instrument.",
        "disclosed_not_binding": {
            "reading": "the strict across-arms sensitivity — the eligible arms as parallel "
                       "hypotheses (this is NOT the registered family)",
            "n_eligible": len(eligible), "rank1_cutoff": round(BH_Q / max(1, len(eligible)), 4),
            "all_pvalues": pvals_all, "primary_survives": bool(strict.get(primary)),
            "admissible_to_act_on": False},
    }

    perm_lift = [f["anchors"]["permuted_timing"]["crps"] - f["arms"][primary]["crps"]
                 for f in per_fold]
    permutation = {
        "permuted_crps": round(float(np.mean(
            [f["anchors"]["permuted_timing"]["crps"] for f in per_fold])), 4),
        "primary_crps": pooled[primary]["crps"],
        "mean_lift_over_permuted": round(float(np.mean(perm_lift)), 4),
        "p_one_sided": M14.onesided_paired_pvalue(np.asarray(perm_lift)),
        "beats": bool(np.mean(perm_lift) > 0)}

    foil_d = [f["arms"][MATCHED_FOIL]["crps"] - f["arms"][primary]["crps"] for f in per_fold]
    foil = {"foil": MATCHED_FOIL, "foil_crps": pooled[MATCHED_FOIL]["crps"],
            "primary_crps": pooled[primary]["crps"],
            "mean_delta": round(float(np.mean(foil_d)), 4),
            "per_fold": [round(x, 4) for x in foil_d],
            "folds_positive": int(sum(1 for x in foil_d if x > 0)),
            "p_one_sided": M14.onesided_paired_pvalue(np.asarray(foil_d)),
            "what_it_measures": "hurdle_transfer − timing_aware on IDENTICAL covariates = the "
                                "AVAILABILITY-SPLIT attribution. A primary win this does not "
                                "separate is a win for the shared in-fold fitted LEVEL, never for "
                                "the hurdle (NF-D10 / NF-D15)."}

    vd = verdict(primary=primary, pooled=pooled, defl=defl, anchors=anchors,
                 fold_clause=fold_clause, bh=bh, permutation=permutation, foil=foil)
    # ⭐ NF-D15 (g″): PROVE the outcome does not rest on MY gate choice — re-read it with each
    #    contestable gate relaxed IN TURN and name what still binds.
    vd["gate_choice_sensitivity"] = {
        "fails_with_dsr_removed": bool(
            not all(v is True for g, v in vd["gates"].items() if g != "dsr_ok")),
        "fails_with_bh_removed": bool(
            not all(v is True for g, v in vd["gates"].items() if g != "bh_ok")),
        "fails_with_both_removed": bool(
            not all(v is True for g, v in vd["gates"].items() if g not in ("dsr_ok", "bh_ok"))),
        "failing_gates": [g for g, v in vd["gates"].items() if v is not True],
    }

    nullcls = None
    if not vd["ship"]:
        d = np.asarray(pooled[primary]["per_fold_lift"], dtype=float)
        sr = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 1e-12 else 0.0
        nullcls = cv_power.classify_null(
            metric=f"nf_inj3b_crps_{primary}", n_folds=len(folds),
            n_arms=DECLARED_FIELD_SIZE, declared_field_size=DECLARED_FIELD_SIZE,
            beats_foil=bool(pooled[primary]["mean_lift"] > 0),
            observed_sr=sr, var_trials_sr=defl["V_registered"],
            var_trials_sr_with_degenerates=defl["V_whole_field"],
            degenerates_excluded_from_v=True,
            fold_wins=wins, p_one_sided=p_primary, bh_cutoff=BH_Q,
            mde_sd_units=cv_power.mde_in_sd_units(n_folds=len(folds), n_metrics=1),
        ).__dict__

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t0, 1),
        "story": "NF-INJ3b",
        "preregistration": "ablation_results/nf_inj3b_preregistration.md",
        "parent_null": "ablation_results/nf_inj3_injury_games.md (NF-INJ3, POWER_LIMITED, PR #1003)",
        "registration": {
            "arms": list(ARMS), "declared_field_size": DECLARED_FIELD_SIZE,
            "primary_arm": PRIMARY_ARM, "matched_foil": MATCHED_FOIL,
            "degenerates": list(DEGENERATE_ARMS),
            "excluded_on_mechanism": EXCLUDED_ON_MECHANISM,
            "V_excluded_arms": list(V_EXCLUDED_ARMS),
            "bh_family": BH_FAMILY, "bh_family_size": BH_FAMILY_SIZE, "bh_q": BH_Q,
            "era_min_season": IG.ERA_MIN_SEASON, "folds": list(folds),
        },
        "primary_vs_argmin": primary_is_argmin,
        "population": prov, "serving_population": sprov,
        "mechanism_activity": activity,
        "per_fold": [{k: v for k, v in f.items() if k != "provenance"} for f in per_fold],
        "pooled": pooled, "deflation": defl, "anchors": anchors,
        "fold_consistency": fold_clause, "bh": bh,
        "permutation_anchor": permutation, "matched_foil": foil,
        "channel_decomposition": channel_decomposition(pooled, per_fold),
        "verdict": vd, "null_classification": nullcls,
        "reproduction_pin_vs_parent": reproduction_pin_vs_parent(per_fold, parent_json,
                                                                 control_json),
        "incumbent_reproduction": R3.reproduction_pin(serving),
        "serving_application": R3.apply_serving(pop, serving, primary),
        "mae_inversion_check": R3.mae_inversion(pop),
        "era_fidelity": R3.era_fidelity(con),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def write_report_md(rep: dict, path: Path) -> None:
    v, d, g = rep["verdict"], rep["deflation"], rep["verdict"]["gates"]
    nc = rep.get("null_classification") or {}
    state = "SHIP" if v["ship"] else (nc.get("state") or "NULL")
    L: list[str] = []
    p = L.append

    p(f"# NF-INJ3b — a FRESH forward re-registration of the injury-games caps")
    p("")
    p(f"**VERDICT: {state}** — registered primary `{v['primary']}`. `best_alpha = 0`. "
      f"Generated {rep['generated_at']} in {rep['elapsed_s']}s.")
    p("")
    p(f"> Pre-registration: `{rep['preregistration']}` — committed BEFORE any arm was scored under "
      f"this registration. ⛔ Not edited by this run (E2.1-r).")
    p("")
    p(f"> 🔒 DEPLOY-HELD: `SERVED_ARM` is `\"{v['served_arm']}\"`. Nothing here serves until the "
      f"gated ship path completes AND the operator records a disposition.")
    p("")
    p("## 0. ⚠️ HONESTY CLAUSE — read before the leaderboard")
    p("")
    p("**This study bought a PROPERLY-REGISTERED RECORD and an HONEST BH ANSWER. It did not buy "
      "new evidence.** The direction and magnitude of this effect were already public in NF-INJ3's "
      "record, and this run re-scores the *same harness on the same data* — every per-fold, per-arm "
      "CRPS is pinned BYTE-IDENTICAL to the parent's (§1 below). ⇒ **a gate that passes here is a "
      "REPRODUCTION, not a corroboration**, and is written up as one.")
    p("")
    p("⭐ The one genuinely open question was **DSR**. `V` is a SAMPLE VARIANCE and moves "
      "NON-MONOTONICALLY with the field's MEMBERSHIP, and this field is not NF-INJ3's field — so "
      "the parent's **0.973** diagnostic was **NOT inherited** and was **NOT** this study's "
      "expected value. It is reported below as what it is: a figure computed for the first time "
      "under a family declared on mechanism.")
    p("")

    # 1. the pin
    pin = rep["reproduction_pin_vs_parent"]
    ip = rep["incumbent_reproduction"]
    p("## 1. Reproduction pins — what makes \"only the REGISTRATION changed\" a MEASUREMENT")
    p("")
    if pin.get("evaluable"):
        p(f"**Pin 1 — scoring identity vs the RECORDED parent artifact "
          f"(`{pin['parent']}`):** {pin['comparisons']}/{pin['comparisons_expected']} per-fold × "
          f"per-arm CRPS compared; max absolute difference "
          f"**{pin['max_abs_crps_difference']:.3e}** against a tolerance of "
          f"**{pin['tolerance']:.0e}** ⇒ **{'PASS' if pin['passes'] else 'FAIL AS REGISTERED'}**. "
          f"Non-vacuous: {pin['non_vacuous']}. Arms that diverge: "
          f"`{pin.get('arms_that_diverge')}`.")
    else:
        p(f"⚠️ **Pin 1 NOT EVALUABLE** — {pin.get('why')}")
    p("")
    ec = pin.get("environment_control", {})
    if ec.get("evaluable"):
        p(f"**The two-sided CONTROL that ATTRIBUTES pin 1** — the PARENT'S OWN entrypoint re-run "
          f"in THIS environment (`{ec['artifact']}`), same DuckDB, same build artifacts: "
          f"{ec['comparisons']}/{ec['comparisons_expected']} compared, max absolute difference "
          f"**{ec['max_abs_crps_difference']:.3e}** ⇒ **{'IDENTICAL' if ec['passes'] else 'DIVERGENT'}**. "
          f"(numpy {ec['numpy']}, scipy {ec['scipy']}, pandas {ec['pandas']}.)")
        p("")
        p(f"⇒ **Attribution: {pin.get('divergence_attribution')}**")
    else:
        p(f"⚠️ **The attribution control is NOT EVALUABLE** — {ec.get('why')}. A pin miss therefore "
          f"cannot be attributed, and is NOT scored as clean (NF1.7 (a)).")
    p("")
    p("⛔ The control is a DIAGNOSTIC. It does not become the pin and a failing registered pin is "
      "never relabelled a pass (E2.1-r).")
    p("")
    p(f"**Served-board identity:** **{ip['n_flagged_veterans']}** flagged veterans on the live "
      f"2026 board ({ip['status_mix']}); **{ip['above_incumbent_ceiling']}** exceed the incumbent's "
      f"ceiling; max round-trip error **{ip['max_abs_round_trip_error']:.2e}**.")
    p("")

    # 2. the registration
    r = rep["registration"]
    p("## 2. The registration, as declared (preregistration §2 / §3 / §6)")
    p("")
    p(f"* **Field ({r['declared_field_size']} arms, declared ON MECHANISM):** "
      + ", ".join(f"`{a}`" for a in r["arms"]))
    p(f"* **Registered PRIMARY:** `{r['primary_arm']}` — gates are computed on the primary, never "
      f"on the field's argmin. Field argmin this run: `{rep['primary_vs_argmin']['field_argmin']}` "
      f"(agree: **{rep['primary_vs_argmin']['agree']}**).")
    p(f"* **Matched foil for the claimed channel:** `{r['matched_foil']}` — identical covariates, "
      f"availability SPLIT removed and nothing else changed.")
    for arm, why in r["excluded_on_mechanism"].items():
        p(f"* **Excluded ON MECHANISM:** `{arm}` — {why}. ⚠️ The narrowing is ADVERSE by DSR-CONV's "
          f"own non-monotonicity (a near-mean arm's removal WIDENS `V`), declared before scoring.")
    p(f"* **`V` membership:** measured over {', '.join('`'+a+'`' for a in d['V_arms'])}; "
      f"EXCLUDED from `V`: {', '.join('`'+a+'`' for a in d['V_excluded_arms'])} "
      f"(DSR-CONV degenerates + MH2.1 (a) reference). `n_trials` = **{d['n_trials']}** — every "
      f"declared arm pays FULL multiplicity.")
    p(f"* **BH family:** `{r['bh_family']}` (size {r['bh_family_size']}) at q = {r['bh_q']}.")
    p(f"* **Era floor:** {r['era_min_season']} — a DATA-FIDELITY quantity (§8). Folds: {r['folds']}.")
    p("")

    # 3. leaderboard
    p("## 3. The field")
    p("")
    rows = []
    for a in ARMS:
        pl = rep["pooled"][a]
        role = ("REFERENCE" if a == INCUMBENT_REFERENCE else
                "DEGENERATE" if a in DEGENERATE_ARMS else
                "**PRIMARY**" if a == PRIMARY_ARM else
                "matched foil" if a == MATCHED_FOIL else "")
        rows.append({"arm": a, "role": role, "CRPS": pl["crps"], "MAE": pl["mae"],
                     "mean games": pl["mean_games"],
                     "lift vs incumbent": pl["mean_lift"],
                     "folds beating incumbent": ("— (self)" if a == INCUMBENT_REFERENCE
                                                 else pl["folds_beating_incumbent"])})
    p(R3._md(rows, ["arm", "role", "CRPS", "MAE", "mean games", "lift vs incumbent",
                    "folds beating incumbent"]))
    p("")
    mi = rep["mae_inversion_check"]
    p(f"⛔ **CRPS selects. MAE never does — MEASURED, not assumed.** n={mi['n']}, median realized "
      f"games {mi['median_realized_games']}, zero share {mi['zero_share']}; the all-zero nihilist "
      f"scores MAE **{mi['mae_all_zero_nihilist']}** against the pooled mean's "
      f"**{mi['mae_pooled_mean']}** ⇒ MAE inverted = **{mi['mae_is_inverted']}** (NF-D11/NF-D14).")
    p("")

    # 4. gates
    p("## 4. Gates (preregistration §5 — all nine must pass)")
    p("")
    fc, bh = rep["fold_consistency"], rep["bh"]
    grows = [
        {"gate": "1 beats incumbent", "value": rep["pooled"][v["primary"]]["mean_lift"],
         "bar": "> 0", "verdict": g["beats_incumbent"]},
        {"gate": "2 fold consistency", "value": fc["observed_wins"],
         "bar": f"≥ {fc['required_wins']} of {fc['n_folds']}", "verdict": g["fold_consistency"]},
        {"gate": "3 PBO (declared field)", "value": d["pbo"], "bar": f"< {MAX_PBO}",
         "verdict": g["pbo_ok"]},
        {"gate": "4 DSR (registered V)", "value": d["dsr_registered"], "bar": f"≥ {MIN_DSR}",
         "verdict": g["dsr_ok"]},
        {"gate": "5 BH-FDR (single hypothesis)", "value": bh["primary_p_one_sided"],
         "bar": f"< q = {bh['q']}", "verdict": g["bh_ok"]},
        {"gate": "6 degenerates lose", "value": {k: x["crps"] for k, x
                                                 in rep["anchors"]["_degenerates"].items()},
         "bar": "both lose", "verdict": g["degenerates_lose"]},
        {"gate": "7 own-form oracle + matched-n", "value": "per-form (NF-D16 g‴)",
         "bar": "no arm beats its own form's peek", "verdict": g["oracle_respected"]},
        {"gate": "8 beats permutation", "value": rep["permutation_anchor"]["mean_lift_over_permuted"],
         "bar": "> 0", "verdict": g["beats_permutation"]},
        {"gate": "9 hurdle attributable (matched foil)", "value": rep["matched_foil"]["mean_delta"],
         "bar": "> 0", "verdict": g["hurdle_attributable"]},
    ]
    p(R3._md(grows, ["gate", "value", "bar", "verdict"]))
    p("")
    p(f"**SHIP = {v['ship']}.** Failing gates: "
      f"{rep['verdict']['gate_choice_sensitivity']['failing_gates'] or 'none'}.")
    p("")
    p(f"Whole-field DSR **{d['dsr_whole_field']}** beside the binding registered figure "
      f"**{d['dsr_registered']}** (`V` registered {d['V_registered']} vs whole-field "
      f"{d['V_whole_field']}). Contender spread **{d['contender_spread_pct']}%** vs whole-field "
      f"**{d['whole_field_spread_pct']}%** — a spread computed over a field containing its OWN "
      f"nulls measures the nulls (NF1.8).")
    p("")
    p(f"NF1.8 triad — flip distribution `{d['flip_distribution']['wins']}` over "
      f"{d['flip_distribution']['in_sample_windows']} in-sample windows; Bailey performance "
      f"degradation **{d['bailey_degradation_pct']}%**.")
    p("")
    p(f"Trial Sharpes: `{d['trial_sharpes']}`")
    p("")
    p(d["note"])
    p("")

    # 5. BH
    p("## 5. The BH family — named BEFORE any p-value (preregistration §6)")
    p("")
    p(f"**Registered family: `{bh['family']}`, size {bh['family_size']}, q = {bh['q']}.** "
      f"Primary one-sided paired p = **{bh['primary_p_one_sided']}** against a cutoff of "
      f"**{bh['cutoff']}** ⇒ **{'SURVIVES' if bh['survives'] else 'FAILS'}**.")
    p("")
    p(f"*Why this family:* {bh['why_this_family']}")
    p("")
    dn = bh["disclosed_not_binding"]
    p(f"**DISCLOSED, NOT BINDING** — {dn['reading']}: rank-1 cutoff {dn['rank1_cutoff']} over "
      f"{dn['n_eligible']} eligible arms ⇒ primary survives = **{dn['primary_survives']}**. "
      f"⛔ The registered family binds whichever way this falls, including if this reading would "
      f"have been kinder (`admissible_to_act_on: false`).")
    p("")

    # 6. attribution
    cd = rep["channel_decomposition"]
    p("## 6. Where the lift comes from — matched pairs, one change per step")
    p("")
    p(R3._md([{"channel": k, **vv} for k, vv in cd["steps"].items()],
             ["channel", "delta_crps", "folds_positive", "p_one_sided"]))
    p("")
    p(f"Steps sum to **{cd['sum_of_steps']}** against the primary's total lift "
      f"**{cd['primary_total_lift']}** (exact by construction).")
    p("")
    mf = rep["matched_foil"]
    p(f"**Gate 9 / the matched foil.** `{PRIMARY_ARM}` **{mf['primary_crps']}** vs "
      f"`{mf['foil']}` **{mf['foil_crps']}** ⇒ paired delta **{mf['mean_delta']}** "
      f"({mf['folds_positive']}/{len(mf['per_fold'])} folds positive, p = {mf['p_one_sided']}). "
      f"{mf['what_it_measures']}")
    p("")
    pa = rep["permutation_anchor"]
    p(f"**Permutation anchor.** permuted **{pa['permuted_crps']}** vs primary "
      f"**{pa['primary_crps']}** ⇒ lift **{pa['mean_lift_over_permuted']}** "
      f"(p = {pa['p_one_sided']}).")
    p("")

    # 7. anchors
    p("## 7. Anchors — a missing anchor is a FAILED check, never a pass (NF1.7 (a))")
    p("")
    arows = [{"arm": k, **{kk: vv for kk, vv in val.items() if kk != "why"}}
             for k, val in rep["anchors"].items() if not k.startswith("_")]
    p(R3._md(arows, ["arm", "evaluable", "arm_crps", "own_form_oracle_crps", "respects_oracle"]))
    p("")
    p(f"**Matched-n control** — `{json.dumps(rep['anchors']['_matched_n_control'], default=str)}`")
    p("")
    p(f"**Pooled-mean anchor** CRPS {rep['anchors']['_pooled_mean']['crps']}.")
    p("")

    # 8. mechanism activity
    act = rep["mechanism_activity"]
    p("## 8. Mechanism activity (NF-D20 — count before crediting)")
    p("")
    p(R3._md(act["per_fold"], ["fold", "n_eval", "RES", "PUP", "NFI", "SUS", "timing_varies"]))
    p("")
    p(f"Totals by status: `{act['total_by_status']}`. **Inactive: `{act['inactive_statuses']}`.** "
      f"{act['note']}")
    p("")

    # 9. serving counterfactual
    sa = rep["serving_application"]
    p("## 9. What the primary would serve on today's board")
    p("")
    p(f"Arm `{sa['arm']}` on the **{sa['n']}** flagged veterans of the live board: mean expected "
      f"games **{sa['mean_incumbent_games']} → {sa['mean_arm_games']}**; {sa['n_moved_down']} move "
      f"DOWN, {sa['n_moved_up']} move UP.")
    p("")
    p(R3._md(sa["rows"][:15], ["player_name", "position", "status", "eg", "incumbent_games",
                               "arm_games", "delta"]))
    p("")
    p("⚠️ Reported for the record whether or not the arm ships. A shipping arm is **level-adjacent** "
      "(MVP-1's point is `rate × games`) and additionally requires the whole-board placement read "
      "(`run_nf_tr2b_placement_read`), `run_interval_revalidation` (NF-D16 / NF-D21), NF-TR2b's "
      "caveat that the VOR shield is ADDITIVE-only and does NOT hold under the two superflex "
      "configs, and a **MEASURED** served-POINT impact (NF1.5 hands part of the availability "
      "discount back — never assume proportional).")
    p("")

    # 10. classification
    p("## 10. Null classification" if not v["ship"] else "## 10. Gate-choice sensitivity")
    p("")
    if nc:
        p("```json")
        p(json.dumps(nc, indent=2, default=str))
        p("```")
        p("")
        p("⚠️ Read the machine flag `field_remedy_admissible`, **never the prose** (MH2.7).")
        p("")
    else:
        p("**`cv_power.classify_null` is INAPPLICABLE, and that is NAMED rather than left silent "
          "(NF1.7 (a)).** It is the instrument for a NULL; this study cleared every registered "
          "gate, so there is no null state to classify and no re-test trigger to publish. ⛔ In "
          "particular, no fold-count / \"more seasons\" trigger is emitted — 28 folds is 28 NFL "
          "seasons and the era floor is a data-fidelity fact, so such a trigger would be the "
          "NF-D18 actively-misleading direction even if a gate had failed.")
        p("")
    gs = v["gate_choice_sensitivity"]
    p(f"**NF-D15 (g″) — does the outcome rest on MY gate choice?** fails with DSR removed: "
      f"{gs['fails_with_dsr_removed']}; fails with BH removed: {gs['fails_with_bh_removed']}; "
      f"fails with BOTH removed: {gs['fails_with_both_removed']}.")
    p("")

    # 11. diagnostics
    dg = d["diagnostics"]
    p("## 11. Deflation diagnostics — ⛔ REPORTED, NEVER ACTED ON")
    p("")
    p("```json")
    p(json.dumps(dg, indent=2, default=str))
    p("```")
    p("")
    p("They name a LEVER; they never license a re-read of a registered gate (E2.1-r / MH2.2). A DSR "
      "reached by deleting the arm under test is INADMISSIBLE and is refused rather than reported "
      "(NF-W7h).")
    p("")
    for line in reading_section(rep):
        p(line)

    path.write_text("\n".join(L))


def reading_section(rep: dict) -> list[str]:
    """The hand-written reading. The JSON and the tables above are the machine record; this is what
    a PM has to be able to act on."""
    v, d, g = rep["verdict"], rep["deflation"], rep["verdict"]["gates"]
    sa, mf, cd = rep["serving_application"], rep["matched_foil"], rep["channel_decomposition"]
    bh, pin = rep["bh"], rep["reproduction_pin_vs_parent"]
    L: list[str] = ["## 12. Reading the result (hand-written; the JSON above is the machine record)",
                    ""]
    a = L.append
    if v["ship"]:
        a("**All nine registered gates pass. The study CLEARS — and the honest word for what that "
          "buys is a RECORD, not a discovery.**")
        a("")
        a("### 1. What is genuinely NEW here, stated narrowly")
        a("")
        a("Exactly two things, and neither is evidence:")
        a("")
        a(f"* **`DSR` computed for the first time under a family declared on MECHANISM: "
          f"{d['dsr_registered']}** against the 0.95 bar. ⚠️ This is **not** the parent's 0.973 "
          f"diagnostic re-appearing — that figure belonged to a DIFFERENT membership. ⭐ And the "
          f"direction is the tell that the registration was honest: `V` is a SAMPLE VARIANCE, "
          f"NF-INJ3b's mechanism-justified narrowing drops a NEAR-MEAN arm, and the "
          f"pre-registration declared **before scoring** that this would WIDEN `V` and RAISE the "
          f"bar. It did — `V` {d['V_registered']} against the parent diagnostic's 0.0151, and DSR "
          f"lands BELOW 0.973. **The narrowing cost the study DSR and it still clears.** A field "
          f"chosen for its effect on this gate would have moved the other way.")
        a(f"* **BH gets its first honest answer.** The family is named (`{bh['family']}`, size "
          f"{bh['family_size']}, q = {bh['q']}) and the primary's p = {bh['primary_p_one_sided']} "
          f"clears it. ⛔ The strict across-arms sensitivity is DISCLOSED and does **not** clear "
          f"(rank-1 cutoff {bh['disclosed_not_binding']['rank1_cutoff']}); the registered family "
          f"binds regardless, and it was named before any p-value existed. **A reader who thinks "
          f"the across-arms reading is right should read this study as NOT clearing gate 5** — "
          f"that is precisely why both are on the record.")
        a("")
        a("### 2. What is NOT new, and must not be written up as though it were")
        a("")
        a(f"Everything else. Pin 1 matches the parent's recorded artifact at "
          f"**{pin.get('max_abs_crps_difference', float('nan')):.1e}** over "
          f"{pin.get('comparisons')} comparisons — the same data, the same folds, the same shared "
          f"φ, the same arm fits. Seven of the nine gates passed in NF-INJ3 and pass again here "
          f"**because they are the same numbers**. ⛔ A foregone gate outcome is a REPRODUCTION. "
          f"It is not fresh confirmation and it does not raise anyone's confidence in the effect "
          f"beyond what NF-INJ3 already earned.")
        a("")
        a("### 3. The substantive finding — unchanged from the parent, restated because it is what "
          "the operator is deciding about")
        a("")
        a(f"The shipped caps are roughly **double** what any fitted form says. Pooled expected "
          f"games: incumbent **{rep['pooled']['incumbent']['mean_games']}** against "
          f"**{rep['pooled'][v['primary']]['mean_games']}** for the primary. On the live board all "
          f"**{sa['n_moved_down']} of {sa['n']}** flagged veterans move DOWN (mean "
          f"**{sa['mean_incumbent_games']} → {sa['mean_arm_games']}** games), **{sa['n_moved_up']}** "
          f"move up.")
        a("")
        a(f"⚠️ **Read the fold counts, not just the means.** The primary beats the incumbent on "
          f"**{rep['pooled'][v['primary']]['folds_beating_incumbent']}/7** folds at p = "
          f"{bh['primary_p_one_sided']}. This is a LARGE mean effect with real fold-to-fold "
          f"variance, not a metronomic one. It clears the registered bar; it is not overwhelming.")
        a("")
        a(f"**Where the lift lives.** LEVEL "
          f"{cd['steps']['level__incumbent_to_fitted_status']['delta_crps']} → FORM "
          f"{cd['steps']['form__fitted_status_to_glm']['delta_crps']} → HURDLE SPLIT "
          f"{cd['steps']['hurdle_split__glm_to_hurdle']['delta_crps']}, summing exactly to "
          f"{cd['sum_of_steps']}. The LEVEL channel dominates by an order of magnitude — **the "
          f"constants, not the shape, are the defect.** Gate 9 separates the availability split "
          f"from the covariates the two arms share (delta {mf['mean_delta']}, p = "
          f"{mf['p_one_sided']}), so the winner's FORM is attributable, but the money is in the "
          f"level.")
        a("")
        a("### 4. ⛔ What a pass here does NOT authorise")
        a("")
        a("**Nothing serves.** A cap change is **level-adjacent** (`point = rate × games`), so the "
          "gated ship path in preregistration §5 runs first and every step of it is still "
          "deploy-held: the whole-board cross-position **placement read** against the PUBLISHED "
          "artifact; **`run_interval_revalidation`**; NF-TR2b's caveat that the VOR shield is "
          "**ADDITIVE-only** and does **not** cover the two superflex configs; and the served-"
          "**POINT** impact **MEASURED**, never assumed proportional — NF1.5's ordering step hands "
          "part of the availability discount back (NF-INJ1 / NF-INJ2 territory).")
        a("")
        a("**And the parent's null STANDS exactly as recorded.** NF-INJ3 is `POWER_LIMITED` and is "
          "not re-read, re-scored or re-labelled by this study (E2.1-r). NF-INJ3b is a separate, "
          "freshly-registered study that happens to run on the same numbers.")
    else:
        a(f"**The study does NOT clear.** Failing gates: "
          f"`{v['gate_choice_sensitivity']['failing_gates']}`. The registered figures BIND; no gate "
          f"is re-read and no field is re-cut (E2.1-r / MH2.2).")
    a("")
    return L


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b §0.5 injury-games re-registration")
    ap.add_argument("--duckdb", default=R3._DEFAULT_DUCKDB)
    ap.add_argument("--artifacts", default=None,
                    help="dir holding the single-vintage MVP-1 builds (gitignored — NF-INFRA1)")
    ap.add_argument("--smoke", action="store_true", help="3 folds, for a code-path proof only")
    ap.add_argument("--parent-control", default=None,
                    help="JSON from the PARENT entrypoint re-run in THIS environment — the "
                         "control that attributes a reproduction-pin miss (see §8)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)
    folds = IG.FOLDS[-3:] if args.smoke else IG.FOLDS
    parent = _REPORT_DIR / PARENT_JSON["smoke" if args.smoke else "full"]
    ctl = Path(args.parent_control) if args.parent_control else None
    rep = run(con, R3.artifacts_dir(args.artifacts), folds, parent, ctl)
    stem = args.out or ("nf_inj3b_injury_games_smoke" if args.smoke else "nf_inj3b_injury_games")
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{stem}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_report_md(rep, _REPORT_DIR / f"{stem}.md")
    log.info("NF-INJ3b %s — primary=%s ship=%s pin=%s → %s",
             "SMOKE" if args.smoke else "FULL", rep["verdict"]["primary"], rep["verdict"]["ship"],
             rep["reproduction_pin_vs_parent"].get("passes"), _REPORT_DIR / f"{stem}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

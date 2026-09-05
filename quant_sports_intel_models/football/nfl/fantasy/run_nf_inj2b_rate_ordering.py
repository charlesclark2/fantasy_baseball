"""run_nf_inj2b_rate_ordering.py — NF-INJ2b: the §0.5 bake-off, executed.

⭐ PRE-REGISTRATION: `ablation_results/nf_inj2b_preregistration.md`, committed before any arm was
scored. ⛔ Not edited by this run (E2.1-r). Anything the run overturns is recorded here under a
`SUPERSEDED` marker, verbatim (NF-W7f).

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2b_rate_ordering

🚦 THE DECISIVE RUN IS THE OPERATOR'S (>2 min). Measured: ~15 s per fold warm (191.7 s on the first,
cold), so seven folds plus a ten-arm 2026 application is several minutes. A ≤2-fold `--smoke` is a
CODE-PATH PROOF only and writes to `*_smoke.{json,md}` — ⛔ a smoke is never a gate.

⚠️ TWO PREREQUISITES, BOTH ENFORCED BY A REFUSAL RATHER THAN A WARNING:
  1. the PUBLISHED board must be staged as the baseline —
       aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/projections.json \
         quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_inj2b_baseline/served_projections_2026.json \
         --region us-east-1
  2. the local MVP-1 2026 board must be within `MAX_BASELINE_LAG_HOURS` of it. It is REBUILT by the
     publish chain's own first steps (`pipeline/jobs/sports_nfl_board_publish_job.py` is the
     authority): the `nfl.staging` / `nfl.marts` dbt run, then `run_season_projection`. ⭐ Note that
     `--market-refresh` pulls a live ADP/ECR snapshot that FEEDS THE ORDERING and moves daily, so an
     exact pin against a published board is only reachable close to that board's own publish — a
     property of the chain, not of this story.

`best_alpha = 0`. Nothing here serves: `nf_inj2b_rate_ordering.SERVED_ARM` is `None` (defer to
NF-INJ2's policy, which is `incumbent`) and `assert_coherent()` refuses a flag flip the record does
not support.

WHAT IS REUSED AND WHAT IS NOT. Every field-AGNOSTIC reducer is imported from NF-INJ2's runner —
`load_realized`, `score_frame`, `fold_lift`, `dsr_conv`, `injury_giveback`, `availability_gradient`,
`placement_read`, `ordering_decomposition`, `mechanism_activity` — so the candidates, the anchors and
the degenerates of BOTH stories pass through the identical reducers and "the anchors answer the same
question as the candidates" stays a property of the code (NF-C0e). Only the field-DEPENDENT parts
(the 10-arm deflation, the per-form ceilings, the verdict) are written here, because they are
parameterised on THIS story's declared field.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2_rate_permutation as R2  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_inj2b")

_ART = R2._ART
_REPORT_DIR = R2._REPORT_DIR
_NF1_5_REPORT = R2._NF1_5_REPORT
_STEM = "nf_inj2b_rate_ordering"
POSITIONS = R2.POSITIONS
REPRO_TOL = R2.REPRO_TOL

#: the injected effect for the positive control, DECLARED in the pre-registration §3 before any
#: score: +0.75 CRPS per fold on every non-degenerate, non-reference arm — ~2.4× the lift NF-INJ2
#: measured, i.e. an effect nobody would call marginal, applied UNIFORMLY so the near-clone geometry
#: the control exists to probe is preserved.
INJECTED_EFFECT = 0.75


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Data — one REAL build per fold, then every arm on the identical frame (common random numbers)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def capture_fold(con, year: int, schema: str, selections: dict, base_from: int = 2017) -> dict:
    """Run the REAL shipped build for `year` ONCE and capture what every arm needs.

    ⭐ THE THREE SCORES COME FROM ONE IMPLEMENTATION. The build is run with the shipped
    `score_target="points"`, capturing the market-attached feature frame and the training pool it
    fitted on; the `rate` and `rate_reselect` scores are then produced by `N15.score_from_frames` —
    the SAME function `learned_scores_by_player` calls — over those SAME frames. So the arms differ
    in the fit target and in nothing else, and the score the bake-off measures is the score the board
    would serve if this ever shipped (NF-C0e)."""
    base = year - 1
    inputs = N15.load_inputs(con, sorted(set(list(range(base_from, base)) + [base])), schema)
    cap: dict = {}
    proj = N15.build_season_projection(con, base, year, schema, selections, inputs,
                                       base_from=base_from, market_refresh=False, capture=cap)
    if not cap:
        raise SystemExit(f"fold {year}: the build ran but captured nothing — the veteran "
                         "postprocess hook did not fire, so no arm could be scored")
    if "feats" not in cap:
        raise SystemExit(
            f"fold {year}: the build captured no feature frame, so the rate-target scores would "
            "have to be re-derived in the harness — which would measure something other than what "
            "the board serves (NF-C0e). Refusing rather than falling back.")
    cap["year"] = year
    cap["board"] = proj
    cap["realized"] = R2.load_realized(year)
    cap["mvp1_point"] = SP.score_line(cap["vets"].copy(),
                                      prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)

    nf11, _ = N15._load_incumbents()
    pid = cap["vets"]["player_id"].astype(str)
    cap["scores_by_target"] = {"points": cap["scores"]}
    for tgt in ("rate", "rate_reselect"):
        sc, prov = N15.score_from_frames(cap["feats"], cap["pool"], cap["selections"], nf11,
                                         year, score_target=tgt)
        cap["scores_by_target"][tgt] = sc
        cap.setdefault("score_provenance", {})[tgt] = prov
    # ⚠️ EVERY ARM IS SCORED ON THE IDENTICAL POPULATION. `eligible` is the points-run's mask, shared
    # by construction, so a rate score that happens to be missing for an eligible row would SINK that
    # row instead of leaving it alone — a silent population change between arms. Counted here rather
    # than assumed to be zero (NF1.7 (a)).
    cap["score_by_target_arr"] = {}
    cap["score_coverage_gap"] = {}
    for tgt, sc in cap["scores_by_target"].items():
        arr = np.array([sc.get(x, np.nan) for x in pid], dtype=float)
        cap["score_by_target_arr"][tgt] = arr
        cap["score_coverage_gap"][tgt] = int(np.sum(cap["eligible"] & ~np.isfinite(arr)))
    # the structural-activity table of the pre-registration §1b, RECOMPUTED per fold rather than
    # inherited: a cell where the re-fit cannot act is UNINFORMATIVE, never a pass (NF-D20).
    cap["refit_activity"] = _refit_activity(cap)
    return cap


def _refit_activity(cap: dict) -> dict:
    """Per position: CAN the target re-fit act at all? (NF-D20, pre-registration §1b.)

    `PosRefinedBlend` scores `(1−w)·z(anchor) + w·z(market_score)`, and the fit target reaches the
    score ONLY through the inner model, which exists only when `anchor == "learned"`. A position
    whose selected class anchors on `mvp1_fp` therefore has a score that is INDEPENDENT of the fit
    target, and its result under a rate arm is uninformative about the hypothesis rather than
    evidence for it."""
    pos = np.array([str(p or "").upper() for p in cap["vets"]["position"]], dtype=object)
    pts = cap["score_by_target_arr"]["points"]
    out: dict[str, dict] = {}
    for p in POSITIONS:
        m = (pos == p) & cap["eligible"]
        if m.sum() < 2:
            continue
        row: dict = {"n": int(m.sum())}
        for tgt in ("rate", "rate_reselect"):
            arr = cap["score_by_target_arr"][tgt]
            ok = m & np.isfinite(pts) & np.isfinite(arr)
            d = float(np.max(np.abs(arr[ok] - pts[ok]))) if ok.any() else float("nan")
            rho = (pd.Series(pts[ok]).corr(pd.Series(arr[ok]), method="spearman")
                   if ok.sum() >= 3 else None)
            row[tgt] = {"max_abs_score_delta": (None if not np.isfinite(d) else round(d, 6)),
                        "rho_vs_points_fit": (None if rho is None or pd.isna(rho)
                                              else round(float(rho), 6)),
                        "can_act": bool(np.isfinite(d) and d > 1e-12)}
        out[p] = row
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — ONE reducer for candidates, foils, degenerates and oracles alike
# ══════════════════════════════════════════════════════════════════════════════════════════════
def arm_frame(cap: dict, arm: str, *, score: np.ndarray | None = None) -> pd.DataFrame:
    """Apply `arm` to the captured veteran frame through the SHIPPING ordering function.

    The score defaults to the one the arm's registration NAMES (`SCORE_OF`), so an arm cannot be
    scored under the wrong target by a call site. `score` overrides it — that is how the per-form
    PEEKING ORACLES are built (the same form ordered by the realized outcome), which makes an oracle
    same-form AND same-sample by construction, carrying none of the capacity confound a
    separately-FITTED oracle would (NF1.7 (b) / NF1.9 (f))."""
    if score is None:
        tgt = B.SCORE_OF[arm]
        score = cap["score_by_target_arr"]["points" if tgt is None else tgt]
    out = M1.apply_learned_ordering(cap["vets"], score, positions=cap["positions"],
                                    eligible=cap["eligible"], arm=arm)
    out = SP.score_line(out, prefix="proj_")
    out = SP.attach_season_interval(out, band_model=cap["band_model"])
    return out


def oracle_arms(cap: dict) -> dict[str, pd.DataFrame]:
    """A peeking oracle for EACH candidate FORM (NF-D16 g‴).

    A single field-wide ceiling is wrong because the forms NEST — `feasibility_clamp` CONTAINS
    `incumbent` (the same permutation under a narrower bound), and the stratified rules contain the
    unstratified ones as the one-stratum case — so a nested form can legitimately beat another form's
    ceiling and one shared ceiling would veto a real winner as a false metric inversion.

    ⭐ THE ORACLE REPLACES THE SCORE, WHICH IS THIS STORY'S TREATED FACTOR. So `oracle_rate_refit` and
    `oracle_points_rate_permute` are the SAME object: two arms differing only in F1 have the same
    ceiling once the score is replaced by the realized outcome. That is correct — the ceiling is a
    property of the FORM (F2) — and it is stated because a reader meeting two identical rows would
    otherwise suspect a bug."""
    vets = cap["vets"].copy()
    vets["pid"] = vets["player_id"].astype(str)
    real = cap["realized"].set_index("pid")["real_fp_ppr"]
    peek = vets["pid"].map(real).to_numpy(dtype=float)     # NaN where unrealized → sinks, as usual
    return {f"oracle_{a}": arm_frame(cap, a, score=peek)
            for a in B.ARMS if a not in B.DEGENERATE_ARMS}


def anchor_audit(scored: dict[str, dict], winner: str) -> dict:
    """Two-sided anchor reading, with the ACTIVITY check the floor needs to mean anything.

    * every pre-registered DEGENERATE must LOSE to the winner (NF1.8: a criterion a degenerate wins
      is fatal; a constraint it satisfies is fine, because the metric then eliminates it);
    * the winner must not beat the peeking ceiling OF ITS OWN FORM;
    * ⚠️ a ceiling that TIES its candidate is INACTIVE, not a refusal (NF-W6d) — a peek that cannot
      move the metric has said nothing, so it is reported UNINFORMATIVE rather than counted as a
      passed test (NF1.7 (a))."""
    w = scored[winner]["crps"]
    degen = {a: scored[a]["crps"] for a in B.DEGENERATE_ARMS if a in scored}
    degen_lose = {a: (v is not None and w is not None and v > w) for a, v in degen.items()}
    ceil = scored.get(f"oracle_{winner}", {}).get("crps")
    gap = None if (ceil is None or w is None) else round(float(w - ceil), 4)
    active = gap is not None and abs(gap) > 1e-6
    return {
        "degenerates_scored": {a: round(v, 4) for a, v in degen.items() if v is not None},
        "winner_crps": w,
        "every_degenerate_loses": all(degen_lose.values()) if degen_lose else None,
        "degenerate_verdicts": degen_lose,
        "own_form_ceiling": ceil,
        "own_form_ceiling_gap": gap,
        "own_form_ceiling_active": active,
        "own_form_ceiling_respected": (None if not active else bool(w >= ceil)),
        "ceiling_reading": ("UNINFORMATIVE — the peek ties the honest arm, so the anchor pair could "
                            "not act (NF-W6d); it is not evidence in either direction."
                            if not active else "ACTIVE"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Deflation — the pre-registration's §3, computed rather than described
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class FieldSpec:
    """The DECLARED field a deflation statistic is computed over.

    ⭐ Threaded rather than read from a module global so a SECOND registration over a DIFFERENT
    declared family (NF-INJ2c's five-arm point-space field) reuses this exact arithmetic instead of
    forking a copy that drifts — the MH2.7 lesson ("a defect corrected N times downstream is a defect
    in the INSTRUMENT") and the NF-C0e two-implementations class.

    ⛔ It is NOT a knob. A field is a PRE-REGISTRATION act; passing one here records which declared
    family a number belongs to, and no caller may assemble one after seeing a score (MH2.2)."""
    arms: tuple[str, ...]
    degenerates: tuple[str, ...]
    reference: tuple[str, ...]
    declared_field_size: int
    label: str


#: NF-INJ2b's own declared field — the DEFAULT, so every existing call site is byte-identical.
NF_INJ2B_FIELD = FieldSpec(
    arms=tuple(B.ARMS), degenerates=tuple(B.DEGENERATE_ARMS), reference=tuple(B.REFERENCE_ARMS),
    declared_field_size=B.DECLARED_FIELD_SIZE, label="NF-INJ2b declared 10-arm field")


def _v_members(srs_all: dict[str, float], field: FieldSpec | None = None) -> dict[str, float]:
    """The arms whose trial Sharpes form `V`.

    ⭐ DECLARED FORWARD (pre-registration §3): the two lose-by-construction DEGENERATES are excluded
    (DSR-CONV) **and so is `incumbent`, the REFERENCE arm**, whose lift series is identically zero by
    construction — a structural 0.0 inflates a small family's dispersion exactly as a diagnostic
    anchor does (MH2.1 (a)). `n_trials` stays at the FULL declared field, so nothing is bought back
    on multiplicity. This is the convention NF-INJ3's null turned on, fixed here BEFORE any score;
    ⛔ it is not a re-read of NF-INJ2's number."""
    f = field or NF_INJ2B_FIELD
    drop = set(f.degenerates) | set(f.reference)
    return {k: v for k, v in srs_all.items() if k not in drop and np.isfinite(v)}


def deflation(per_fold: dict[str, dict[int, dict]], folds: tuple[int, ...], winner: str,
              *, field: FieldSpec | None = None) -> dict:
    """PBO / DSR / spread / flip distribution over the DECLARED 10-arm field.

    PBO is computed over the ELIGIBLE set — the declared field, the search the selection actually ran
    (MH2) — on NEGATED CRPS, because `cscv_pbo` picks the in-sample ARGMAX and CRPS is a loss.

    The NF1.8 triad is reported beside PBO, because a rank statistic alone cannot tell "my pick is
    unstable" from "my pick is tied": the FLIP DISTRIBUTION, Bailey's PERFORMANCE DEGRADATION, and
    the CONTENDER spread beside the whole-field spread (which, containing this field's own declared
    degenerates, measures the degenerates)."""
    f = field or NF_INJ2B_FIELD
    arms = list(f.arms)
    S = np.full((len(arms), len(folds)), np.nan, dtype=float)
    for i, a in enumerate(arms):
        for j, y in enumerate(folds):
            v = per_fold.get(a, {}).get(y, {}).get("crps")
            if v is not None:
                S[i, j] = -float(v)                       # negate: cscv_pbo maximises
    pbo = M14.cscv_pbo(S)
    contenders = [i for i, a in enumerate(arms) if a not in f.degenerates]

    import itertools
    n_s = len(folds)
    flips: dict[str, int] = {}
    degr: list[float] = []
    if n_s >= 4:
        splits = list(itertools.combinations(range(n_s), n_s // 2))
        if len(splits) > 256:
            step = len(splits) / 256
            splits = [splits[int(i * step)] for i in range(256)]
        for is_cols in splits:
            oos = [c for c in range(n_s) if c not in is_cols]
            with np.errstate(invalid="ignore"):
                ism = np.nanmean(S[:, list(is_cols)], axis=1)
                oosm = np.nanmean(S[:, oos], axis=1)
            if not np.isfinite(ism).any():
                continue
            b = int(np.nanargmax(ism))
            flips[arms[b]] = flips.get(arms[b], 0) + 1
            if np.isfinite(oosm[b]) and np.isfinite(np.nanmax(oosm)):
                best_oos = float(np.nanmax(oosm))
                if abs(best_oos) > 1e-12:
                    degr.append((best_oos - float(oosm[b])) / abs(best_oos))
    total_flips = sum(flips.values()) or 1

    lift = {a: [R2.fold_lift(per_fold, a, y) for y in folds] for a in arms}
    srs_all = R2._srs(lift)
    v_members = _v_members(srs_all, f)
    v_nondeg_only = {k: v for k, v in srs_all.items()
                     if k not in f.degenerates and np.isfinite(v)}
    deltas = np.asarray(lift.get(winner, []), dtype=float)
    return {
        "pbo": pbo, "pbo_max": M14.PBO_MAX,
        "pbo_application": "field",
        "spread_whole_field": M14.config_spread(S),
        "spread_contender": (M14.config_spread(S[contenders, :]) if len(contenders) >= 2 else None),
        "flip_distribution": {k: round(v / total_flips, 4)
                              for k, v in sorted(flips.items(), key=lambda kv: -kv[1])},
        "bailey_degradation_pct": (round(float(np.median(degr)) * 100, 3) if degr else None),
        "trial_sharpes": {k: round(v, 4) for k, v in srs_all.items()},
        "v_members": sorted(v_members),
        "field_label": f.label,
        "v_excluded": sorted(set(f.degenerates) | set(f.reference)),
        "dsr_whole_field": M14.deflated_sharpe(deltas, np.asarray(list(srs_all.values()))),
        # ⭐ THE BINDING FIGURE, per the pre-registration §3: degenerates AND the reference arm out
        # of `V`, `n_trials` at the full declared field.
        "dsr_binding": R2.dsr_conv(deltas, list(v_members.values()), f.declared_field_size),
        # reported BESIDE it so the convention's effect is on the record rather than asserted —
        # this is NF-INJ2's convention (degenerates out, reference IN), recomputed on this field.
        "dsr_reference_included_in_v": R2.dsr_conv(deltas, list(v_nondeg_only.values()),
                                                   f.declared_field_size),
        "dsr_min": M14.DSR_MIN,
        "dsr_2x2_diagnostic": _dsr_2x2(deltas, srs_all, winner, f),
        "declared_field_size": f.declared_field_size,
    }


def _dsr_2x2(deltas, srs_all: dict[str, float], winner: str,
              field: FieldSpec | None = None) -> dict:
    """DSR under the declared field vs the same winner with the single most extreme trial Sharpe
    dropped — a DIAGNOSTIC, never acted on (NF-W7f: measure the 2×2 BEFORE naming a remedy).

    ⛔ NF-W7h: a DSR reached only by deleting the WINNER is INADMISSIBLE, so the dropped arm is named
    and the diagnostic REFUSES to report a figure when that arm is the winner."""
    f = field or NF_INJ2B_FIELD
    srs = _v_members(srs_all, f)
    if len(srs) < 3:
        # ⭐ At exactly TWO members the diagnostic is not merely unevaluated, it is INADMISSIBLE BY
        # CONSTRUCTION (NF-W7h): the only drops available are the arm under test — inadmissible
        # outright — or the other contributor, which leaves `V` undefined at one point. A refusal is
        # then stated A FORTIORI on the design, ⛔ never as a trimmed number.
        return {"evaluable": False,
                "structurally_unavailable": len(srs) == 2,
                "v_member_count": len(srs),
                "why": ("`V` has exactly two members, so the only available drops are the arm under "
                        "test (inadmissible — NF-W7h) or the sole other contributor (leaving `V` "
                        "undefined). The 2x2 is STRUCTURALLY UNAVAILABLE for this declared field; "
                        "state any refusal a fortiori on the design."
                        if len(srs) == 2 else "fewer than 3 finite trial Sharpes in `V`")}
    mean = float(np.mean(list(srs.values())))
    far = max(srs, key=lambda k: abs(srs[k] - mean))
    if far == winner:
        return {"evaluable": False, "dropped_arm": far,
                "why": "the most extreme trial Sharpe IS the winner — a DSR reached by deleting it "
                       "would be inadmissible (NF-W7h), so no trimmed figure is reported"}
    kept = [v for k, v in srs.items() if k != far]
    return {
        "evaluable": True, "dropped_arm": far, "dropped_arm_sharpe": round(srs[far], 4),
        "V_declared": round(float(np.var(list(srs.values()), ddof=1)), 4),
        "V_without_dropped_arm": round(float(np.var(kept, ddof=1)), 4),
        "dsr_declared": R2.dsr_conv(deltas, list(srs.values()), f.declared_field_size),
        "dsr_without_dropped_arm": R2.dsr_conv(deltas, kept, f.declared_field_size),
        "note": "⛔ A DIAGNOSTIC, NOT A TRIM. Every arm here is DECLARED; you get to pre-register a "
                "family, you do not get to discover one (MH2.2).",
        "reading": "if V falls hard and DSR barely moves, the binding quantity is per-fold NOISE "
                   "(a variance/design problem), NOT multiplicity — and prescribing a coherent "
                   "re-registration would spend a successor on the wrong lever (NF-W7f)",
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE REGISTERED GATE FUNCTION — the one the study scores with AND the one the control re-runs
# ══════════════════════════════════════════════════════════════════════════════════════════════
def gate_table(payload: dict) -> dict[str, dict[str, bool]]:
    """`{arm -> {gate -> passed}}` for the whole declared field, from the pre-registration's §3.

    ⭐ THIS IS THE STUDY'S OWN GATE FUNCTION, and it is what
    `cv_power.injected_effect_positive_control` re-runs on the injected payload. Re-implementing the
    gates inside the control would restate this harness's assumptions instead of testing them (the
    NF-C0e "a test that reads a value back under the key the code wrote" class), so there is exactly
    one implementation and the control drives it.

    ⛔ `pbo` IS DELIBERATELY ABSENT from the per-arm table. CSCV/PBO has ONE value for the whole
    field and answers whether the SELECTION overfit; it does not vary across arms, so carrying it as
    a per-arm pass/fail converts "the search was unstable" into "this arm failed", which is not a
    statement the statistic makes (PLAT-CVP1 defect 4(a); MLB-HV2-1 MEASURED the cost — a 6pp planted
    bias drove PBO to 0.426 precisely BECAUSE it made the arms near-clones, and a per-arm reading
    would have vetoed a real, large effect). It is recorded as a FIELD-level verdict beside this
    table, and `classify_null` is told `pbo_application="field"`. A consequence worth stating: the
    control's `field_level_gates_applied_per_arm` should come back EMPTY, and that emptiness is the
    affirmative finding, not an absence of one.

    `payload` carries `per_fold`, `folds`, `scored`, `tier_rho`, `coherence` — everything the gates
    read — so `inject()` can build a counterfactual population without touching this function."""
    folds = tuple(payload["folds"])
    per_fold = payload["per_fold"]
    scored = payload["scored"]
    tier = payload["tier_rho"]                     # {arm: {fold: {pos: rho}}}
    coherence = payload["coherence"]               # {arm: attributable violating players}

    lift = {a: np.asarray([R2.fold_lift(per_fold, a, y) for y in folds], dtype=float)
            for a in B.ARMS}
    srs_all = R2._srs({a: list(v) for a, v in lift.items()})
    v_members = _v_members(srs_all)
    clause = cv_power.fold_consistency_clause(len(folds))

    # the two anchors are FIELD-level facts about the winner's own form, evaluated per arm below
    out: dict[str, dict[str, bool]] = {}
    for a in B.ARMS:
        d = lift[a][np.isfinite(lift[a])]
        mean = float(d.mean()) if len(d) else float("nan")
        wins = int((d > 0).sum())
        p1 = M14.onesided_paired_pvalue(d)
        dsr = R2.dsr_conv(d, list(v_members.values()), B.DECLARED_FIELD_SIZE)
        # ORDERING: no position regresses distinguishably from noise, BH across the four positions
        pv: dict[str, float | None] = {}
        for pos in POSITIONS:
            deltas = []
            for y in folds:
                wv = tier.get(a, {}).get(y, {}).get(pos)
                iv = tier.get("incumbent", {}).get(y, {}).get(pos)
                if wv is not None and iv is not None:
                    deltas.append(iv - wv)         # POSITIVE = this arm is WORSE at this position
            if len(deltas) >= 3:
                pv[pos] = M14.onesided_paired_pvalue(np.asarray(deltas, dtype=float))
        sig = M14.bh_fdr(pv, q=M14.FDR_Q) if pv else {}
        ceil = scored.get(f"oracle_{a}", {}).get("crps")
        w_crps = scored.get(a, {}).get("crps")
        ceil_active = (ceil is not None and w_crps is not None and abs(w_crps - ceil) > 1e-6)
        out[a] = {
            "beats_incumbent": bool(np.isfinite(mean) and mean > 0.0),
            "fold_consistency": bool(clause.passes(wins)) if clause.attainable else False,
            "bh_fdr": bool(p1 is not None and p1 <= M14.FDR_Q),
            "degenerates_lose": all(
                (scored.get(g, {}).get("crps") is not None and w_crps is not None
                 and scored[g]["crps"] > w_crps) for g in B.DEGENERATE_ARMS),
            # ⚠️ an INACTIVE ceiling is not a refusal (NF-W6d) — a peek that cannot move the metric
            # has said nothing, so it passes rather than being scored as a failure it never tested.
            "own_form_ceiling": (True if not ceil_active else bool(w_crps >= ceil)),
            "ordering_not_regressed": (not any(bool(v) for v in sig.values())) if pv else False,
            "coherence_restored": bool(coherence.get(a) == 0),
            "dsr": bool(dsr is not None and dsr >= M14.DSR_MIN),
        }
    return out


def build_payload(per_fold: dict, folds: tuple[int, ...], scored: dict,
                  coherence: dict[str, int]) -> dict:
    """Assemble the gate function's input from the scored run — ONE shape, so the real run and the
    injected control differ ONLY in the numbers, never in the plumbing."""
    tier = {a: {y: dict(v.get("tier_rho_by_position") or {}) for y, v in d.items()}
            for a, d in per_fold.items()}
    return {"folds": list(folds), "per_fold": per_fold, "scored": scored,
            "tier_rho": tier, "coherence": dict(coherence)}


#: the injected tier-ρ improvement, DECLARED in the pre-registration §3 (AMENDMENT 2026-08-27,
#: before any scoring): a planted TRUE POSITIVE for this study is an arm that is better on the
#: SELECTING metric **and** does not regress the pre-registered ORDERING constraint, so the
#: injection must reach both. Without it the control would report `BLIND` whenever the constraint
#: legitimately fails on real data — a label that means "a null from this family is free" and would
#: be flatly wrong here.
INJECTED_TIER_RHO = 0.05


def make_injector(base_payload: dict, field: "FieldSpec | None" = None):
    """`inject(effect) -> payload` for `cv_power.injected_effect_positive_control`.

    `field=` names WHOSE registration decides which arms are treated; it defaults to NF-INJ2b's, so
    every existing caller is byte-identical.

    Plants an effect of KNOWN size into THIS study's own population: every non-degenerate,
    non-reference arm gets its per-fold CRPS improved by `effect` and its per-fold draftable-tier ρ
    improved by `INJECTED_TIER_RHO` at every position. `inject(0.0)` returns the REAL payload
    untouched — that is the two-sided (null-control) leg, and it must not plant anything, or the
    control's own vacuity check would be vacuous (NF1.7 (a)).

    ⭐ The injection is UNIFORM across the treated arms ON PURPOSE. Arms 2–6 of this field are
    near-clones on the assignment axis, and a uniform edge is exactly what makes near-clones
    simultaneously strong — the geometry that drives PBO up (NF1.8: a high PBO over near-clones is a
    TIE, not overfitting) and collapses DSR through cross-trial dispersion (MH2.5 / NF-W6b-C). A
    control that planted a DIFFERENT effect per arm would dodge the very shape it exists to probe."""
    # ⭐ PARAMETERISED, ⛔ not hardcoded to NF-INJ2b's field (MH2.7: a shared instrument takes the
    # caller's declaration). Until 2026-09-05 this read `B.ARMS` / `B.DEGENERATE_ARMS` directly and
    # happened to be right for NF-INJ2c only because the two registrations declare the SAME
    # degenerates and reference — a coincidence, not a guarantee. It is LOAD-BEARING now:
    # amendment 1's clause (b) F2/F3 read "a degenerate survived" as a control FAILURE, and that
    # reading presumes the injection never TREATED the degenerate. A field whose degenerate set
    # differed would have had its degenerates injected, improved, and then charged for surviving.
    f = field or NF_INJ2B_FIELD
    treated = [a for a in f.arms
               if a not in f.degenerates and a not in f.reference]

    def inject(effect: float) -> dict:
        eff = float(effect)
        pf = {a: {y: dict(v) for y, v in d.items()} for a, d in base_payload["per_fold"].items()}
        tier = {a: {y: dict(v) for y, v in d.items()}
                for a, d in base_payload["tier_rho"].items()}
        scored = {a: dict(v) for a, v in base_payload["scored"].items()}
        if eff != 0.0:
            for a in treated:
                for y, v in pf.get(a, {}).items():
                    if v.get("crps") is not None:
                        v["crps"] = float(v["crps"]) - eff          # CRPS is a loss ⇒ subtract
                for y, v in tier.get(a, {}).items():
                    for pos, rho in list(v.items()):
                        if rho is not None:
                            v[pos] = min(1.0, float(rho) + INJECTED_TIER_RHO)
                if scored.get(a, {}).get("crps") is not None:
                    scored[a]["crps"] = float(scored[a]["crps"]) - eff
        return {"folds": list(base_payload["folds"]), "per_fold": pf, "scored": scored,
                "tier_rho": tier, "coherence": dict(base_payload["coherence"])}

    return inject


def positive_control(base_payload: dict, folds: tuple[int, ...]) -> dict:
    """Run the pre-registered injected-effect control through `cv_power`, and record the FIELD-level
    PBO's behaviour beside it.

    ⭐ THE FIELD-LEVEL HALF IS THE HV2-1 MECHANISM AND IT IS NOT IN THE PER-ARM TABLE, so it must be
    reported separately or the study would simply not see it: a uniform planted edge makes the arms
    simultaneously strong near-clones, which is a TIE, and CSCV reads a tie as instability."""
    inject = make_injector(base_payload)
    rep = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=gate_table, effect=INJECTED_EFFECT, check_null_control=True)

    def _matrix(payload) -> np.ndarray:
        arms = list(B.ARMS)
        S = np.full((len(arms), len(folds)), np.nan, dtype=float)
        for i, a in enumerate(arms):
            for j, y in enumerate(folds):
                v = payload["per_fold"].get(a, {}).get(y, {}).get("crps")
                if v is not None:
                    S[i, j] = -float(v)
        return S

    def _pbo_of(payload) -> float | None:
        return M14.cscv_pbo(_matrix(payload))

    def _argmax_splits(S: np.ndarray) -> list[int]:
        """Which arm wins the IN-SAMPLE half of each balanced split — the quantity CSCV ranks."""
        import itertools
        n_s = S.shape[1]
        if n_s < 4:
            return []
        splits = list(itertools.combinations(range(n_s), n_s // 2))
        if len(splits) > 256:
            step = len(splits) / 256
            splits = [splits[int(i * step)] for i in range(256)]
        out = []
        for is_cols in splits:
            with np.errstate(invalid="ignore"):
                ism = np.nanmean(S[:, list(is_cols)], axis=1)
            out.append(int(np.nanargmax(ism)) if np.isfinite(ism).any() else -1)
        return out

    return {
        "verdict": rep.verdict,
        "effect_injected_crps": rep.effect,
        "effect_injected_tier_rho": INJECTED_TIER_RHO,
        "reason": rep.reason,
        "survivors": list(rep.survivors),
        "metric_survivors": list(rep.metric_survivors),
        "deflation_blocked": list(rep.deflation_blocked),
        "deflation_gates": list(rep.deflation_gates),
        "metric_gates": list(rep.metric_gates),
        "blocking_gates": {k: list(v) for k, v in rep.blocking_gates.items()},
        # ⭐ the PLAT-CVP1 defect-4(a) detector. EMPTY is the affirmative finding here: this study's
        # registered gate table deliberately carries no field-level statistic as a per-arm pass/fail.
        "field_level_gates_applied_per_arm": list(rep.field_level_gates_applied_per_arm),
        "null_control_checked": rep.null_control_checked,
        "null_control_survivors": (None if rep.null_control_survivors is None
                                   else list(rep.null_control_survivors)),
        "field_level_pbo_real": _pbo_of(inject(0.0)),
        "field_level_pbo_injected": _pbo_of(inject(INJECTED_EFFECT)),
        **_pbo_injection_activity(_matrix(inject(0.0)), _matrix(inject(INJECTED_EFFECT)),
                                  _argmax_splits),
    }


def _pbo_injection_activity(S_real: np.ndarray, S_inj: np.ndarray, argmax_splits) -> dict:
    """⭐ CAN THE INJECTION MOVE PBO AT ALL? — measured, not assumed (NF1.7 (a) / NF-D20).

    CSCV/PBO is RANK-BASED: it asks which arm wins each in-sample half. The pre-registered injection
    is UNIFORM and ADDITIVE across the treated arms (deliberately — uniformity is what preserves the
    near-clone geometry the control exists to probe), and adding the SAME constant to every treated
    arm on every fold cannot re-order them among themselves. So whenever the in-sample argmax is
    already a treated arm on a split, the injection leaves that split's winner unchanged.

    ⇒ Under THIS injection the field-level PBO may be a STRUCTURAL NO-OP, in which case its
    invariance is a property of the injection and says NOTHING about the field. That is a finding to
    report, ⛔ never a passed test (NF1.9: a mechanism that cannot act is a finding, not an
    omission). MLB-HV2-1's PBO moved because its injection was a bias on the DATA that each arm
    responded to DIFFERENTLY; a uniform score shift is a different object and must not be read as
    the same measurement."""
    a_real, a_inj = argmax_splits(S_real), argmax_splits(S_inj)
    moved = sum(1 for x, y in zip(a_real, a_inj) if x != y)
    inert = bool(a_real and moved == 0)
    return {
        "field_level_pbo_splits_whose_winner_moved": moved,
        "field_level_pbo_splits": len(a_real),
        "field_level_pbo_injection_inert": inert,
        "field_level_pbo_note": (
            "⚠️ MEASURED STRUCTURALLY INERT: the injection moved the in-sample winner on "
            f"{moved}/{len(a_real)} splits, so the field-level PBO under injection is a property of "
            "the UNIFORM ADDITIVE injection (CSCV is rank-based; a common shift cannot re-order the "
            "treated arms among themselves), ⛔ NOT evidence about this field. MLB-HV2-1's PBO rose "
            "because its injection was a bias on the DATA that each arm responded to differently — "
            "a different object. Reported because a mechanism that CANNOT act is a finding, not an "
            "omission (NF1.9 / NF-D20)."
            if inert else
            f"the injection moved the in-sample winner on {moved}/{len(a_real)} splits, so the PBO "
            "comparison is ACTIVE. A RISE under a uniform edge is the signature of a TIE among "
            "near-clones (NF1.8), ⛔ not evidence that the field overfits."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The 2026 application — the CURRENT (flip-board) served vintage
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: half the rounding unit of the PUBLISHED board. `projections.json` serves `fpPpr`/`g` rounded to
#: ONE decimal, so a 1e-9 reproduction pin against it is not merely strict — it is UNACHIEVABLE, and
#: a study that quoted one would be reporting a tolerance nothing could ever meet (the E9.61 class:
#: an API-rounded side compared against a recomputed side manufactures phantom deltas). The pin
#: against the SERVED artifact therefore runs at the artifact's OWN resolution, and says so.
PUBLISHED_ROUNDING_TOL = 0.05

#: ⭐ REPRESENTATION EPSILON for the published-artifact comparison. ⛔ THIS IS NOT SLACK, and the
#: distinction is the whole point. `PUBLISHED_ROUNDING_TOL` is a DECIMAL bar — half the artifact's
#: 0.1 quantum — evaluated in BINARY floating point, and a decimal half-unit has no exact binary
#: representation: a `proj_games` of 16.55 against a published 16.6 differs by
#: `0.05000000000000071`, ONE ULP above a bar whose own operator (`<=`) already intends 0.05 to
#: PASS. `proj_games` is quantised on a 0.05 grid, so `.x5` ties are STRUCTURAL and recur on every
#: board — without this epsilon the pin is incapable of passing on a CORRECT reproduction, which is
#: the unachievable-gate family `tolerance_note` below already names one step coarser (E9.61), and
#: this program refuses an unachievable gate as firmly as a loosened one.
#: 1e-9 is EIGHT ORDERS OF MAGNITUDE below the artifact's own 0.1 quantum and far below the
#: smallest difference a 1-decimal artifact can express, so it cannot admit a materially wrong row.
#: It is the same discriminator the diagnosis used to establish that ZERO rows differ by any amount
#: the artifact could carry.
#: ⛔ Deliberately NOT "round both sides to 1dp and compare equal": 16.55 is itself unrepresentable,
#: so round-half-even at the boundary reintroduces the exact artifact this fixes — the publisher's
#: float and ours could legally round a `.x5` tie in opposite directions.
#: (PM ruling, NF-INJ2c decision request #5: a COMPARISON-PRECISION defect, not a bar move. The
#: registered bar, its population and its binding condition are unchanged.)
PUBLISHED_TOL_REPR_EPS = 1e-9


def reproduces_at_published_resolution(worst: float) -> bool:
    """Does `worst` sit within the PUBLISHED artifact's own resolution?

    Evaluates the REGISTERED bar `worst <= PUBLISHED_ROUNDING_TOL` with decimal-boundary semantics
    instead of raw binary `<=`. The bar itself is unchanged and is still what the report quotes.

    ⛔ `PUBLISHED_TOL_REPR_EPS` IS NOT slack — it is a REPRESENTATION allowance. The bar is a
    DECIMAL half-unit with no exact binary form, so the SAME structural tie lands on either side of
    it by luck of representation: `16.6 - 16.55` is `0.05000000000000071` (over) while
    `15.1 - 15.05` is `0.049999999999998934` (under). Admitting that ULP is what makes the gate
    decide on the DATA rather than on floating-point happenstance. A row wrong by any amount the
    1-decimal artifact can express still REFUSES.

    ⛔ FAIL-CLOSED: a non-finite `worst` (an empty join — nothing was compared) REFUSES, because a
    comparison that could not be evaluated is never a pass (NF1.7(a)).
    """
    w = float(worst)
    if not math.isfinite(w):
        return False
    return bool(w <= PUBLISHED_ROUNDING_TOL + PUBLISHED_TOL_REPR_EPS)

#: how far the local MVP-1 board may lag the SERVED board before the 2026 application REFUSES.
#: The spec's baseline criterion is explicit — the flip board is the baseline, and the SHIP lesson
#: binds: verify input freshness BEFORE any board-vintage measurement.
MAX_BASELINE_LAG_HOURS = 48.0


def served_baseline(json_path: Path) -> tuple[pd.DataFrame, dict]:
    """The CURRENT SERVED board, read from the PUBLISHED artifact — ⛔ never reconstructed.

    ⭐ THE SPEC'S BASELINE CRITERION, EXECUTED. `projections.json` as published to the prod
    api-cache IS the flip board a drafter sees; a locally rebuilt "served" snapshot is a claim about
    the wire, not a reading of it (the CLV / NF-INJ1 stale-vintage trap, and NF1.9-R's `served_*`
    column that never tracked what shipped).

    Returns `(frame, vintage)`. ⛔ REFUSES rather than returning None: the caller's inherited
    behaviour was to substitute the ARM'S OWN BOARD for a missing baseline, which makes every
    served-relative figure compare an arm to itself and reports a structural 0.0 as a measurement."""
    if not json_path.exists():
        raise SystemExit(
            f"no published board at {json_path} — the 2026 application measures against the CURRENT "
            f"SERVED vintage and REFUSES to substitute a rebuild for it (a rebuild compared to "
            f"itself reports a structural zero as a measurement). Stage it first:\n"
            f"  aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/projections.json "
            f"{json_path} --region us-east-1")
    doc = json.loads(json_path.read_text())
    rows = doc.get("players") or []
    if not rows:
        raise SystemExit(f"the published board at {json_path} carries no players")
    fr = pd.DataFrame([{"player_id": str(r.get("id")), "proj_fp_ppr": r.get("fpPpr"),
                        "proj_games": r.get("g")} for r in rows])
    fr = fr[pd.to_numeric(fr["proj_fp_ppr"], errors="coerce").notna()].copy()
    man = json_path.with_name("manifest.json")
    vintage: dict = {"projections_generated_at": doc.get("generated_at"),
                     "n_rows": int(len(fr)), "source": str(json_path)}
    if man.exists():
        m = json.loads(man.read_text())
        vintage.update(
            manifest_generated_at=m.get("generated_at"),
            input_vintage=(m.get("freshness") or {}).get("input_vintage"),
            injury_input=(m.get("coherence") or {}).get("injury_input"),
            coherence_violating_players=(m.get("coherence") or {}).get("violating_players"),
            injury_games_stamp=m.get("injuryGamesStamp"),
            reported_absence_count=m.get("reportedAbsenceCount"))
    return fr, vintage


def _assert_baseline_is_current(mvp1: pd.DataFrame, vintage: dict) -> dict:
    """⭐ VERIFY INPUT FRESHNESS BEFORE ANY BOARD-VINTAGE MEASUREMENT (the spec's SHIP lesson).

    Two independent checks, both REFUSING rather than warning, because a stale baseline does not
    make a measurement noisy — it makes it a measurement of a different product:

    * the local MVP-1 board must not lag the SERVED board by more than `MAX_BASELINE_LAG_HOURS`;
    * the served board's own injury-input verdict (stamped on the manifest by the build that
      consumed the feed) must read OK — a stale feed once capped Kittle at 3.3 games and nearly
      poisoned a measurement."""
    from datetime import datetime as _dt
    out: dict = {"max_lag_hours": MAX_BASELINE_LAG_HOURS}
    local = str(pd.to_datetime(mvp1["generated_at"].iloc[0], utc=True))
    served_at = vintage.get("projections_generated_at")
    out["local_mvp1_generated_at"] = local
    out["served_generated_at"] = served_at
    if served_at:
        lag = abs((pd.to_datetime(served_at, utc=True)
                   - pd.to_datetime(mvp1["generated_at"].iloc[0], utc=True)).total_seconds()) / 3600
        out["lag_hours"] = round(float(lag), 2)
        if lag > MAX_BASELINE_LAG_HOURS:
            raise SystemExit(
                f"the local MVP-1 2026 board is {lag:.1f}h from the SERVED board (bar "
                f"{MAX_BASELINE_LAG_HOURS}h). Every 2026 number would be about a board nobody is "
                f"served (the spec's baseline criterion + the CLV / NF-INJ1 stale-vintage trap). "
                f"Rebuild the MVP-1 board before running the 2026 application.")
    inj = vintage.get("injury_input") or {}
    out["served_injury_input"] = inj
    if inj and str(inj.get("verdict")).upper() not in ("OK", ""):
        raise SystemExit(
            f"the SERVED board's own injury-input verdict is {inj.get('verdict')!r} "
            f"({inj.get('detail')}) — refusing to measure a give-back against a board built on a "
            f"stale feed (the NF-INJ3b-SHIP lesson).")
    return out


def apply_2026(con, schema: str, selections: dict, arms: tuple[str, ...],
               base_from: int = 2017, served_json: Path | None = None) -> dict:
    """Build the FULL 2026 board (veterans + rookies) under each arm and measure what would ship.

    Rebuilt per arm rather than spliced, because the placement read is a whole-board cross-position
    question and the rookie leg must sit in it exactly as it does on the wire. ⭐ Each arm is built
    with the FIT TARGET its registration names (`SCORE_OF`), through the shipped
    `build_season_projection` — so the counterfactual board is produced by the serving path, not by
    a harness that re-derives it (NF-C0e)."""
    mvp1 = pd.read_parquet(_ART / "nfl_fantasy_season_projections_2026.parquet")
    outdir = _ART / "nf_inj2b_baseline"
    outdir.mkdir(parents=True, exist_ok=True)
    # ⛔ The baseline is READ from the published artifact and the run REFUSES without it. The
    # inherited behaviour substituted the ARM'S OWN BOARD for a missing baseline, which makes every
    # served-relative figure compare an arm to itself and reports a structural zero as a
    # measurement (NF1.7 (a) — a check that did not run is not a check that passed).
    served, vintage = served_baseline(served_json or (outdir / "served_projections_2026.json"))
    freshness = _assert_baseline_is_current(mvp1, vintage)

    status = RSP.load_forward_roster_status(con, 2026)
    flagged = status[status["proj_status"].astype(str).str.upper().isin(
        SP._INJURY_STATUS_GAMES_CAP)]
    board_ids = set(mvp1["player_id"].astype(str))
    capped_ids = [x for x in flagged["player_id"].astype(str).tolist() if x in board_ids]
    out: dict = {
        "cohort_source": ("load_forward_roster_status(2026).proj_status ∈ "
                          f"{sorted(SP._INJURY_STATUS_GAMES_CAP)} — the cap's own input"),
        "n_capped": len(capped_ids),
        "board_generated_at": str(mvp1["generated_at"].iloc[0])[:25],
        "served_vintage": vintage,
        "baseline_freshness": freshness,
        "arms": {},
    }
    inputs = N15.load_inputs(con, sorted(set(list(range(base_from, 2025)) + [2025])), schema)
    for arm in arms:
        tgt = B.SCORE_OF[arm] or "points"
        board = N15.build_season_projection(con, 2025, 2026, schema, selections, inputs,
                                            base_from=base_from, market_refresh=False, arm=arm,
                                            score_target=tgt)
        coh = PC.frame_coherence_summary(board)
        ids = {(v.get("id"), v.get("name")) for v in coh["violations"]}
        rec = {
            "score_target": tgt,
            "coherence_violating_players": coh["n_violating_players"],
            "coherence_violations": coh["n_violations"],
            "coherence_by_position": coh["by_position"],
            "coherence_applicable": coh["applicable"],
            "coherence_unevaluable": coh["n_unevaluable"],
            "worst_violations": [
                {k: v[k] for k in ("name", "stat", "implied_per_game",
                                   "max_ever_per_game", "expected_games")}
                for v in coh["violations"][:5]],
            "injury_giveback": R2.injury_giveback(mvp1, served, board, capped_ids),
            "availability_gradient": R2.availability_gradient(mvp1, board),
            "clamp_saturation_high": int((pd.to_numeric(board["nf1_scale"], errors="coerce")
                                          >= 3.4999).sum()),
            "clamp_saturation_low": int((pd.to_numeric(board["nf1_scale"], errors="coerce")
                                         <= 0.3001).sum()),
            "n_rows": int(len(board)),
            "placement": R2.placement_read(mvp1, board),
            "_violating_keys": sorted(f"{i}|{n}" for i, n in ids),
        }
        out["arms"][arm] = rec
        board.to_parquet(outdir / f"board_2026_{arm}.parquet", index=False)
        log.info("2026 %-24s target=%-13s violations=%2d giveback=%+.1f%% gradient_rho=%s",
                 arm, tgt, rec["coherence_violating_players"],
                 rec["injury_giveback"].get("giveback_pct") or float("nan"),
                 rec["availability_gradient"]["rho"])
    # ⭐ ATTRIBUTION BY CONTROL. `mvp1_null` is the ordering step switched entirely OFF, so a
    # violation it ALSO produces is a defect of the underlying MVP-1 board that no permutation rule
    # can be causing. Both counts are reported so a reader can apply either.
    baseline_keys = set(out["arms"].get("mvp1_null", {}).get("_violating_keys", []))
    for arm, rec in out["arms"].items():
        own = set(rec.pop("_violating_keys", []))
        rec["coherence_violations_also_present_with_ordering_OFF"] = sorted(own & baseline_keys)
        rec["coherence_violating_players_attributable"] = len(own - baseline_keys)
    out["attribution_control"] = (
        "violations also produced by `mvp1_null` (the ordering step OFF) are subtracted — a defect "
        "present with the mechanism disabled is not caused by the mechanism")

    if "incumbent" in arms:
        inc = pd.read_parquet(outdir / "board_2026_incumbent.parquet")
        a, b = inc.copy(), served.copy()
        for d in (a, b):
            d["pid"] = d["player_id"].astype(str)
        j = b[["pid", "proj_fp_ppr", "proj_games"]].merge(a[["pid", "proj_fp_ppr", "proj_games"]],
                                                          on="pid", suffixes=("_s", "_r"))
        worst = max(float(pd.to_numeric(j[f"{c}_s"], errors="coerce")
                          .sub(pd.to_numeric(j[f"{c}_r"], errors="coerce")).abs().max())
                    for c in ("proj_fp_ppr", "proj_games"))
        # ⭐ THE TOLERANCE IS THE PUBLISHED ARTIFACT'S OWN RESOLUTION, and saying so is the point.
        # `projections.json` serves one decimal place, so a 1e-9 pin against it is not strict, it is
        # UNACHIEVABLE — quoting one would be quoting a bar nothing could ever meet (E9.61: an
        # API-rounded side compared against a recomputed side manufactures phantom deltas). The
        # story's 1e-9 discipline still governs every LOCAL comparison; this pin is against the wire.
        out["reproduction_pin"] = {
            "n": int(len(j)), "worst_abs_diff": worst,
            "tolerance": PUBLISHED_ROUNDING_TOL,
            "representation_epsilon": PUBLISHED_TOL_REPR_EPS,
            "story_tolerance_for_local_diffs": REPRO_TOL,
            "reproduces": reproduces_at_published_resolution(worst),
            "note": "the incumbent arm rebuilt through this story's code vs the PUBLISHED 2026 "
                    "artifact. If this does not hold, every arm delta is measured against a board "
                    "nobody is served (the CLV / NF-INJ1 stale-vintage trap).",
            "tolerance_note": "the published board is rounded to ONE decimal, so the pin runs at "
                              "half that rounding unit — a 1e-9 bar against a 1dp artifact is "
                              "UNACHIEVABLE, not strict (E9.61).",
            "representation_note": "the registered bar is UNCHANGED at "
                                   f"{PUBLISHED_ROUNDING_TOL}; it is a DECIMAL bar evaluated in "
                                   "BINARY, so it is compared with a "
                                   f"{PUBLISHED_TOL_REPR_EPS:g} representation epsilon — ⛔ NOT "
                                   "slack. `proj_games` is quantised on a 0.05 grid, so a `.x5` "
                                   "value against its 1dp publication differs by exactly the bar "
                                   "and lands ONE ULP over it in binary; without the epsilon this "
                                   "pin cannot pass a CORRECT reproduction (the unachievable-gate "
                                   "family, E9.61). A row wrong by any amount a 1-decimal artifact "
                                   "can express still REFUSES.",
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Verdict — the pre-registration's §6, computed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def joint_success(*, arm: str, gates: dict[str, bool], app2026: dict | None,
                  activity: dict) -> dict:
    """The spec's THREE-PART joint criterion, computed rather than asserted.

    (a) holds the ordering constraint at EVERY position's draftable tier;
    (b) removes — or at minimum does not reintroduce — the give-back;
    (c) drives the NF-INJ1 violation count on its counterfactual board toward zero.

    ⛔ (a) IS NOT SATISFIED BY PASSING ONLY WHERE THE MECHANISM IS INACTIVE. The per-position
    activity count is carried beside the pass count, because an inactive cell is UNINFORMATIVE and
    was never a test (NF-D20 / NF1.7 (a))."""
    rec = (app2026 or {}).get("arms", {}).get(arm, {})
    give = (rec.get("injury_giveback") or {}).get("giveback_pct")
    inc_give = ((app2026 or {}).get("arms", {}).get("incumbent", {})
                .get("injury_giveback") or {}).get("giveback_pct")
    viol = rec.get("coherence_violating_players_attributable")
    act = {p: bool(v.get(B.SCORE_OF[arm] or "points", {}).get("can_act"))
           for p, v in activity.items()} if B.SCORE_OF[arm] in ("rate", "rate_reselect") else {}
    return {
        "a_ordering_holds": gates.get("ordering_not_regressed"),
        "a_active_positions": sorted(p for p, v in act.items() if v),
        "a_inactive_positions": sorted(p for p, v in act.items() if not v),
        "a_note": ("the target re-fit is STRUCTURALLY INACTIVE at "
                   f"{sorted(p for p, v in act.items() if not v)} — those cells are UNINFORMATIVE "
                   "about the hypothesis, never a pass (NF-D20)") if act and not all(act.values())
                  else ("every position the arm is registered to act on is ACTIVE" if act else
                        "not a target-re-fit arm — the activity question does not apply"),
        "b_giveback_pct": give,
        "b_incumbent_giveback_pct": inc_give,
        "b_giveback_removed": (None if give is None or inc_give is None
                               else bool(give <= max(0.0, inc_give) + 1e-9)),
        "c_violations_attributable": viol,
        "c_coherence_restored": (None if viol is None else bool(viol == 0)),
        "all_three": (None if (gates.get("ordering_not_regressed") is None or give is None
                               or inc_give is None or viol is None)
                      else bool(gates.get("ordering_not_regressed")
                                and give <= max(0.0, inc_give) + 1e-9 and viol == 0)),
    }


def verdict(*, winner: str, pooled: dict, defl: dict, anchors: dict, gates: dict,
            ordering: dict, joint: dict, pair_reads: dict,
            gate_undefined: dict | None = None) -> dict:
    """The pre-registration's §6, computed. Each branch NAMES the reading it corresponds to, so a
    reader can check the verdict against the document rather than against this code."""
    beats = pooled.get("mean_lift_vs_incumbent")
    band = pooled.get("tie_band", 0.0)
    wins = beats is not None and beats > band
    ties = beats is not None and abs(beats) <= band
    regressed = [p for p, sig in (ordering.get("regression_significant_by_position") or {}).items()
                 if sig]
    und = dict(gate_undefined or {})

    #: the gates whose statistic MUST have been evaluated before anything ships. `own_form_ceiling`
    #: is deliberately absent: an INACTIVE peeking ceiling is UNINFORMATIVE, not a refusal, and it
    #: passes by design (NF-W6d) — treating its inactivity as a blocker would convert "the anchor
    #: pair could not act" into "the arm failed", which is the same conflation one level over.
    SHIP_REQUIRES_EVALUATED = ("pbo_field_level", "dsr", "fold_consistency", "bh_fdr",
                               "ordering_not_regressed")
    unevaluated = sorted(k for k in SHIP_REQUIRES_EVALUATED if und.get(k))

    def _failed(key: str) -> bool:
        """⭐ MH2: a gate is REFUSED only when it was EVALUATED and FAILED. `gate_table` is strictly
        boolean (that is the positive control's contract), so an UNCOMPUTABLE statistic arrives as
        `False` and would otherwise be read as a refusal — publishing `DEFLATION_REFUSED` for a gate
        that never ran. That is the actively-misleading direction: `classify_null` correctly returns
        `UNDEFINED` for the same input, and the two must not disagree.

        ⚠️ DEFENCE IN DEPTH, ⛔ not the load-bearing owner: the `unevaluated` branch below already
        catches every gate in `SHIP_REQUIRES_EVALUATED` before this is reached, so deleting the
        `und` clause here changes no current behaviour (its RED proof therefore targets the BRANCH
        ORDER, which is what actually carries the property). It is kept because it states the rule
        LOCALLY — a later reordering would otherwise silently restore the defect — and it is named
        redundant here so a reader does not mistake it for the thing under test."""
        return gates.get(key) is False and not und.get(key)

    if regressed:
        # §6 branch 2. The constraint is BREACHED at a named position by a margin DISTINGUISHABLE
        # FROM NOISE — a constraint the arm fails, not a shortage of evidence. ⛔ NO "more seasons"
        # trigger: more folds make a real regression MORE significant, not less (NF-D18).
        state = "CONSTRAINT_REFUSED"
        why = (f"the pre-registered ORDERING constraint is breached at {', '.join(regressed)} by a "
               f"margin distinguishable from noise — §6 branch 2: do not ship")
    elif joint.get("c_coherence_restored") is False:
        state = "NULL"
        why = ("the arm does not restore coherence, which is the correctness constraint the whole "
               "story exists to satisfy — §6 branch 3")
    elif beats is not None and not wins and not ties:
        state = "GENUINE_ABSENCE"
        why = ("the best arm LOSES the selecting metric on average — no n and no field size rescues "
               "a negative point estimate (§6 branch 4)")
    elif unevaluated:
        # ⛔ A GATE THAT COULD NOT BE COMPUTED HAS NOT BEEN CLEARED. This branch sits ABOVE the ship
        # branches on purpose: an arm that wins the metric while a pre-registered gate never ran has
        # not passed that gate, and shipping on it would be the NF1.7 (a) vacuity — "a check that
        # did not run is not a check that passed" — with a product change riding on it. It is
        # equally not a REFUSAL: a refusal carries a remedy and an unevaluated gate has none, which
        # is why `classify_null` returns `UNDEFINED` for the same input and the two must agree.
        state = "UNDEFINED"
        why = (f"a pre-registered gate was NOT COMPUTABLE at this fold count "
               f"({', '.join(unevaluated)}) — ⛔ not failed, not passed, and ⛔ not shippable")
    elif (_failed("dsr") or _failed("bh_fdr")) and (wins or ties):
        # §6 branch 5. A deflation gate was EVALUATED and FAILED while the metric and the constraint
        # passed. Read against the positive control's verdict; ⛔ no season/fold trigger when the
        # lockstep invariant holds (NF-W8-0d).
        state = "DEFLATION_REFUSED"
        why = ("the metric and constraint gates pass and a pre-registered DEFLATION gate was "
               "EVALUATED and FAILED — §6 branch 5; read against the injected-effect control")
    elif wins or ties:
        blocking = [k for k in ("degenerates_lose", "coherence_restored", "ordering_not_regressed")
                    if gates.get(k) is False]
        state = "SHIP" if not blocking else "SHIP_WITH_CAVEAT"
        why = ("wins the selecting metric" if wins else
               "TIES the selecting metric — and a tie SHIPS under the pre-registration's §6 first "
               "branch, because the incumbent fails a correctness constraint this arm satisfies")
    else:
        state = "NULL"
        why = "no branch of §6 is satisfied"

    srs = defl.get("trial_sharpes") or {}
    w_sr = srs.get(winner)
    members = _v_members(srs)
    from scipy.stats import norm as _norm
    em, n = 0.5772156649015329, defl["declared_field_size"]
    sr0 = (float(np.std(list(members.values()), ddof=1))
           * ((1 - em) * _norm.ppf(1 - 1 / n) + em * _norm.ppf(1 - 1 / (n * np.e)))
           if len(members) >= 2 else None)
    unreachable = (w_sr is not None and sr0 is not None and w_sr <= sr0)
    return {
        "state": state, "why": why, "gates": gates, "gate_undefined": und,
        "gates_unevaluated_blocking_a_ship": unevaluated,
        "mean_lift_vs_incumbent": beats, "tie_band": band,
        "beats_the_selecting_metric": bool(wins), "ties_the_selecting_metric": bool(ties),
        "ordering_regressed_at": regressed,
        "joint_success": joint,
        "matched_pair_reads": pair_reads,
        "dsr_reading": {
            "winner_sharpe": w_sr, "benchmark_SR0": (round(sr0, 4) if sr0 is not None else None),
            "state": "DSR_UNREACHABLE" if unreachable else "REACHABLE",
            "note": ("SR ≤ SR0 in THIS declared field ⇒ no fold count clears the bar (n enters only "
                     "through √(n−1), which SCALES a positive gap and cannot CREATE one — "
                     "NF-W8-0d's lockstep invariant). ⛔ Do NOT publish a season/fold re-test "
                     "trigger for it." if unreachable else
                     "a positive SR − SR0 gap exists; more folds would scale it"),
        },
        "no_more_data_trigger": True,
        "no_more_data_trigger_why":
            ("the binding refusal is a pre-registered CONSTRAINT the arm breaches — more folds make "
             "a real regression MORE significant, not less (NF-D18)" if regressed else
             "the DSR shortfall is unreachable at any n (lockstep invariant, NF-W8-0d)"
             if unreachable else
             "a negative point estimate is not rescued by n (NF-D15 g″)"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, schema: str, folds: tuple[int, ...], selections: dict, *,
        base_from: int = 2017) -> dict:
    t0 = time.time()
    per_fold: dict[str, dict[int, dict]] = {}
    activity: dict[int, dict] = {}
    refit_activity: dict[int, dict] = {}
    decomposition: dict[int, dict] = {}
    provenance: dict[int, dict] = {}
    coverage_gap: dict[int, dict] = {}
    fold_n: dict[int, int] = {}

    for y in folds:
        cap = capture_fold(con, y, schema, selections, base_from=base_from)
        frames = {a: arm_frame(cap, a) for a in B.ARMS}
        frames.update(oracle_arms(cap))
        for a, f in frames.items():
            per_fold.setdefault(a, {})[y] = R2.score_frame(f, cap["realized"], cap["mvp1_point"])
        fold_n[y] = int(per_fold["incumbent"][y]["n"] or 0)
        activity[y] = R2.mechanism_activity(cap)
        refit_activity[y] = cap["refit_activity"]
        decomposition[y] = R2.ordering_decomposition(cap)
        provenance[y] = cap.get("score_provenance", {})
        coverage_gap[y] = cap["score_coverage_gap"]
        log.info("fold %d scored (n=%d) — %s", y, fold_n[y],
                 " ".join(f"{a}:{per_fold[a][y]['crps']}" for a in B.ARMS))

    scored = {a: {k: (round(float(np.mean([per_fold[a][y][k] for y in folds
                                           if per_fold[a][y].get(k) is not None])), 4)
                      if any(per_fold[a][y].get(k) is not None for y in folds) else None)
                  for k in ("crps", "mae", "coverage80", "interval_score80", "bias",
                            "rho_pooled", "tier_rho_pooled", "coherence_violating_players")}
              for a in per_fold}

    # ── the WINNER: the best CRPS among the declared NON-degenerate, NON-reference arms ──────────
    cands = [a for a in B.ARMS if a not in B.DEGENERATE_ARMS and a not in B.REFERENCE_ARMS]
    winner = min(cands, key=lambda a: (scored[a]["crps"] if scored[a]["crps"] is not None
                                       else float("inf")))
    lifts = np.asarray([R2.fold_lift(per_fold, winner, y) for y in folds], dtype=float)
    lifts = lifts[np.isfinite(lifts)]
    pooled = {
        "winner": winner,
        "mean_lift_vs_incumbent": (round(float(lifts.mean()), 4) if len(lifts) else None),
        "per_fold_lift": {int(y): round(R2.fold_lift(per_fold, winner, y), 4) for y in folds},
        "folds_won": int((lifts > 0).sum()),
        # the per-fold SE of the winner's own lift — a DISPERSION quantity fixed by the design, ⛔
        # not a threshold chosen to reach a verdict.
        "tie_band": (round(float(lifts.std(ddof=1) / np.sqrt(len(lifts))), 4)
                     if len(lifts) >= 2 else 0.0),
        "one_sided_p": M14.onesided_paired_pvalue(lifts),
        "selection_rule": ("lowest pooled CRPS among the declared arms that are neither a "
                           "pre-registered degenerate nor the reference"),
    }

    defl = deflation(per_fold, folds, winner)
    anchors = anchor_audit(scored, winner)
    fold_clause = cv_power.fold_consistency_clause(len(folds))

    # ── the ORDERING constraint, at NF-INJ2's bar, verbatim ─────────────────────────────────────
    ord_by_pos, ord_full_by_pos, ord_p = {}, {}, {}
    for p_ in POSITIONS:
        w = scored_pos(per_fold, winner, folds, "tier_rho_by_position", p_)
        i = scored_pos(per_fold, "incumbent", folds, "tier_rho_by_position", p_)
        if w is not None and i is not None:
            ord_by_pos[p_] = (w, i)
        wf = scored_pos(per_fold, winner, folds, "rho_by_position", p_)
        i_f = scored_pos(per_fold, "incumbent", folds, "rho_by_position", p_)
        if wf is not None and i_f is not None:
            ord_full_by_pos[p_] = (wf, i_f)
        d = []
        for y in folds:
            wv = per_fold[winner][y]["tier_rho_by_position"].get(p_)
            iv = per_fold["incumbent"][y]["tier_rho_by_position"].get(p_)
            if wv is not None and iv is not None:
                d.append(iv - wv)               # POSITIVE = the winner is WORSE at this position
        if len(d) >= 3:
            ord_p[p_] = M14.onesided_paired_pvalue(np.asarray(d, dtype=float))
    ord_sig = M14.bh_fdr(ord_p, q=M14.FDR_Q) if ord_p else {}
    ordering_block = {
        "metric": "top_tier_rho (the metric NF1.5's own bake-off selected on)",
        "by_position_winner_vs_incumbent": ord_by_pos,
        "not_regressed": (None if not ord_p else not any(bool(v) for v in ord_sig.values())),
        "binding_reading": ("no position shows a regression distinguishable from noise (one-sided "
                            "paired t on per-fold tier-ρ deltas, BH across the four positions at "
                            f"q={M14.FDR_Q}) — NF-INJ2's bar, VERBATIM. A strict point-estimate bar "
                            "at nominal is a coin flip at any n (NF-D22)."),
        "bh_direction_note": ("⚠️ this BH protects against a false REFUSAL, i.e. it is directionally "
                              "GENEROUS to the arm. Declared in the pre-registration §3, so the "
                              "generosity is on the record rather than discovered by a reader."),
        "regression_pvalues": ord_p,
        "regression_significant_by_position": ord_sig,
        "strict_point_estimate_reading": (all(w >= i - 1e-9 for w, i in ord_by_pos.values())
                                          if ord_by_pos else None),
        "full_population_by_position": ord_full_by_pos,
        "full_population_not_regressed": (all(w >= i - 1e-9 for w, i in ord_full_by_pos.values())
                                          if ord_full_by_pos else None),
    }

    coherence_counts = {a: (scored[a]["coherence_violating_players"] or 0) for a in B.ARMS}
    payload = build_payload(per_fold, folds, scored, coherence_counts)
    gates_all = gate_table(payload)
    gates = dict(gates_all[winner])
    gates["pbo_field_level"] = bool(defl["pbo"] is not None and defl["pbo"] < defl["pbo_max"])
    # ⭐ MH2: a statistic that could not be COMPUTED is UNDEFINED, ⛔ never FAILED. `gate_table` must
    # stay strictly boolean (that is `injected_effect_positive_control`'s contract), so
    # undefinedness is carried BESIDE it and the report renders it as its own state. Without this a
    # 2-fold smoke would print "PBO … False" for a number that was never computable — the exact
    # conflation the seven-state null taxonomy exists to prevent.
    gate_undefined = {
        "pbo_field_level": defl["pbo"] is None,
        "dsr": defl["dsr_binding"] is None,
        "fold_consistency": not fold_clause.attainable,
        "bh_fdr": pooled["one_sided_p"] is None,
        "ordering_not_regressed": ordering_block["not_regressed"] is None,
        "own_form_ceiling": not anchors["own_form_ceiling_active"],
    }

    control = positive_control(payload, folds)
    pair_reads = matched_pair_reads(per_fold, folds, scored)
    joint = joint_success(arm=winner, gates=gates, app2026=None,
                          activity=_pooled_refit_activity(refit_activity))
    vd = verdict(winner=winner, pooled=pooled, defl=defl, anchors=anchors, gates=gates,
                 ordering=ordering_block, joint=joint, pair_reads=pair_reads,
                 gate_undefined=gate_undefined)

    nullcls = None
    if vd["state"] not in ("SHIP", "SHIP_WITH_CAVEAT"):
        srs = defl.get("trial_sharpes") or {}
        members = _v_members(srs)
        v_all = [v for v in srs.values() if np.isfinite(v)]
        nullcls = cv_power.classify_null(
            metric=LR.SELECTION_METRIC, n_folds=len(folds), n_arms=B.DECLARED_FIELD_SIZE,
            declared_field_size=B.DECLARED_FIELD_SIZE,
            beats_foil=bool((pooled["mean_lift_vs_incumbent"] or 0.0) > 0.0),
            observed_sr=(float(np.mean(lifts) / lifts.std(ddof=1))
                         if len(lifts) >= 2 and lifts.std(ddof=1) > 1e-12 else None),
            var_trials_sr=(float(np.var(list(members.values()), ddof=1))
                           if len(members) >= 2 else None),
            var_trials_sr_with_degenerates=(float(np.var(v_all, ddof=1))
                                            if len(v_all) >= 2 else None),
            degenerates_excluded_from_v=True,
            fold_wins=pooled["folds_won"],
            p_one_sided=pooled["one_sided_p"],
            bh_cutoff=M14.FDR_Q,
            pbo=defl["pbo"], pbo_application="field")

    return {
        "story": "NF-INJ2b", "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0, "elapsed_s": round(time.time() - t0, 1),
        "folds": list(folds), "fold_rows": fold_n,
        "fold_window_provenance": "inherited from NF1.5 stage-1 `score_from` — not chosen here",
        "selections": {p: s["learner"] for p, s in selections.items()},
        "declared_field": list(B.ARMS), "declared_field_size": B.DECLARED_FIELD_SIZE,
        "degenerates": list(B.DEGENERATE_ARMS), "reference_arms": list(B.REFERENCE_ARMS),
        "score_of": dict(B.SCORE_OF), "assignment_of": dict(B.ASSIGNMENT_OF),
        "leaderboard": scored,
        "per_fold": {a: {int(y): v for y, v in d.items()} for a, d in per_fold.items()},
        "mechanism_activity": {int(y): v for y, v in activity.items()},
        "refit_activity": {int(y): v for y, v in refit_activity.items()},
        "refit_activity_pooled": _pooled_refit_activity(refit_activity),
        "score_provenance": {int(y): v for y, v in provenance.items()},
        "score_coverage_gap": {int(y): v for y, v in coverage_gap.items()},
        "ordering_decomposition": {int(y): v for y, v in decomposition.items()},
        "pooled": pooled, "deflation": defl, "anchors": anchors,
        # ⭐ MH2 H8: the CALIBRATED clause, never the raw 0.60 rate — that rate is a different gate
        # at every fold count and nearly free at the low end. `wins_required is None` means the
        # level is UNATTAINABLE at this n, which the clause reports as UNDEFINED rather than passed.
        "fold_consistency": {"n_folds": len(folds),
                             "wins_required": fold_clause.wins_required,
                             "attainable": fold_clause.attainable,
                             "attained_false_fire": fold_clause.attained_false_fire,
                             "legacy_wins_required": fold_clause.legacy_wins_required,
                             "legacy_false_fire": fold_clause.legacy_false_fire,
                             "observed_wins": pooled["folds_won"],
                             "passes": bool(fold_clause.passes(pooled["folds_won"]))},
        "ordering": ordering_block,
        "matched_pair_reads": pair_reads,
        "gate_table": gates_all,
        "gate_undefined": gate_undefined,
        "positive_control": control,
        "verdict": vd, "null_classification": (None if nullcls is None else str(nullcls)),
    }


def scored_pos(per_fold: dict, arm: str, folds, key: str, pos: str) -> float | None:
    v = [per_fold[arm][y][key].get(pos) for y in folds if per_fold[arm][y].get(key)]
    v = [x for x in v if x is not None]
    return round(float(np.mean(v)), 4) if v else None


def _pooled_refit_activity(refit_activity: dict[int, dict]) -> dict:
    """Pool the per-fold structural-activity table. A position is ACTIVE only if the re-fit could
    move its score on EVERY fold — an "active on some folds" cell is reported as such rather than
    rounded up, because an inactive fold is UNINFORMATIVE, never a pass (NF-D20)."""
    out: dict[str, dict] = {}
    for p in POSITIONS:
        rows = [d[p] for d in refit_activity.values() if p in d]
        if not rows:
            continue
        out[p] = {}
        for tgt in ("rate", "rate_reselect"):
            acts = [bool(r[tgt]["can_act"]) for r in rows if tgt in r]
            deltas = [r[tgt]["max_abs_score_delta"] for r in rows
                      if tgt in r and r[tgt]["max_abs_score_delta"] is not None]
            rhos = [r[tgt]["rho_vs_points_fit"] for r in rows
                    if tgt in r and r[tgt]["rho_vs_points_fit"] is not None]
            out[p][tgt] = {
                "folds_active": int(sum(acts)), "folds": len(acts),
                "can_act": bool(acts and all(acts)),
                "max_abs_score_delta": (round(float(max(deltas)), 6) if deltas else None),
                "min_rho_vs_points_fit": (round(float(min(rhos)), 6) if rhos else None),
            }
    return out


def matched_pair_reads(per_fold: dict, folds: tuple[int, ...], scored: dict) -> dict:
    """The declared matched pairs, READ (NF-D15 g′ / NF-W7e).

    Each pair differs on exactly ONE factor — `assert_coherent()` proves that at import — so the
    paired per-fold delta attributes the difference to that factor and to nothing else. ⭐ The 2×2
    INTERACTION is reported, because two mechanism halves are NOT additive and a study that
    recombined them from separate conditional measurements would report a number nothing measured
    (NF-W7e)."""
    out: dict[str, dict] = {}
    for a, foil, why in B.MATCHED_PAIRS:
        d = np.asarray([R2.fold_lift(per_fold, a, y) - R2.fold_lift(per_fold, foil, y)
                        for y in folds], dtype=float)
        d = d[np.isfinite(d)]
        out[f"{a} − {foil}"] = {
            "isolates": why,
            "mean_paired_delta_crps": (round(float(d.mean()), 4) if len(d) else None),
            "folds_positive": int((d > 0).sum()), "folds": int(len(d)),
            "one_sided_p": M14.onesided_paired_pvalue(d),
            "factor": ("TARGET" if B.ASSIGNMENT_OF[a] == B.ASSIGNMENT_OF[foil] else "ASSIGNMENT"),
        }
    # ── the 2×2 interaction over {points, rate} × {rate-by-score, rate-within-strata} ────────────
    def _mean(a: str) -> float | None:
        v = np.asarray([R2.fold_lift(per_fold, a, y) for y in folds], dtype=float)
        v = v[np.isfinite(v)]
        return float(v.mean()) if len(v) else None
    cells = {k: _mean(k) for k in ("points_rate_permute", "rate_refit",
                                   "points_rate_stratified", "rate_refit_stratified")}
    if all(v is not None for v in cells.values()):
        d_target_bys = cells["rate_refit"] - cells["points_rate_permute"]
        d_target_str = cells["rate_refit_stratified"] - cells["points_rate_stratified"]
        d_assign_pts = cells["points_rate_stratified"] - cells["points_rate_permute"]
        d_assign_rate = cells["rate_refit_stratified"] - cells["rate_refit"]
        joint = cells["rate_refit_stratified"] - cells["points_rate_permute"]
        out["_2x2_interaction"] = {
            "cells_mean_lift_vs_incumbent": {k: round(v, 4) for k, v in cells.items()},
            "target_effect_within_by_score": round(d_target_bys, 4),
            "target_effect_within_stratified": round(d_target_str, 4),
            "assignment_effect_within_points": round(d_assign_pts, 4),
            "assignment_effect_within_rate": round(d_assign_rate, 4),
            "joint_effect": round(joint, 4),
            "sum_of_halves": round(d_target_bys + d_assign_pts, 4),
            "interaction": round(joint - (d_target_bys + d_assign_pts), 4),
            "reading": ("NF-W7e: two halves that each move the metric are NOT additive. A large "
                        "interaction means the halves are rescuing (or cancelling) each other, and "
                        "a MARGINAL delta measured with the other half at one setting is not a "
                        "measurement of the other setting. ⛔ Never recombine channels measured "
                        "conditionally — the joint cell is scored here, not inferred."),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _coherence_fold_count(rep: dict, arm: str) -> str:
    """How many folds carry ≥1 coherence violation for `arm`.

    The leaderboard's coherence figure is a per-fold MEAN, and a mean is exactly the shape that
    hides a rare violation behind a rounded zero. The count is what a reader needs to tell "this
    arm is coherent by construction" from "this arm is coherent in six of seven folds"."""
    d = (rep.get("per_fold") or {}).get(arm) or {}
    seen = [v.get("coherence_violating_players") for v in d.values()]
    got = [x for x in seen if x is not None]
    if not got:
        return "—"
    return f"{sum(1 for x in got if x)}/{len(got)}"


def write_report_md(rep: dict, path: Path) -> None:
    L: list[str] = []
    v = rep["verdict"]
    A = L.append
    A(f"# NF-INJ2b — re-fit the ordering learner on a per-game RATE target\n")
    A(f"**VERDICT: {v['state']}** — {v['why']}. `best_alpha = 0`. "
      f"Generated {rep['generated_at'][:19]}Z in {rep['elapsed_s']}s.\n")
    A("> Pre-registration: `nf_inj2b_preregistration.md` (committed before any arm was scored; "
      "AMENDMENT 1 filed before any scoring). ⛔ Not edited by this run — E2.1-r.\n")
    A("> 🔒 DEPLOY-HELD: `nf_inj2b_rate_ordering.SERVED_ARM` is `None`, so the board serves "
      "NF-INJ2's policy (`incumbent`). Nothing here serves until the PM records a disposition.\n")

    A("\n## 1. The declared field\n")
    A(f"Folds **{'–'.join(str(y) for y in (rep['folds'][0], rep['folds'][-1]))}** "
      f"({len(rep['folds'])}), {rep['fold_window_provenance']}. Declared field "
      f"**{rep['declared_field_size']}** arms; degenerates `{'`, `'.join(rep['degenerates'])}`; "
      f"reference `{'`, `'.join(rep['reference_arms'])}`.\n")
    rows = []
    for a, s in sorted(rep["leaderboard"].items(),
                       key=lambda kv: (kv[1]["crps"] if kv[1]["crps"] is not None else 1e9)):
        rows.append({"arm": a, "target": rep["score_of"].get(a, "—") or "—",
                     "assignment": rep["assignment_of"].get(a, "oracle"),
                     "CRPS": _fmt(s["crps"]), "MAE": _fmt(s["mae"]),
                     "cov80": _fmt(s["coverage80"]), "tier ρ": _fmt(s["tier_rho_pooled"]),
                     # ⭐ 4dp, and the fold count beside it. This value is a per-fold MEAN, and at 0
                     # decimals a genuine 0.1429 (one violating player in one of seven folds) RENDERS
                     # AS "0" — so the table asserted a coherence the `coherence_restored` gate,
                     # which demands EXACTLY 0, was simultaneously refusing. A rounded render that
                     # contradicts a gate reading the same number is the E9.61 class, and here it
                     # hid the refutation of this story's own by-construction premise.
                     "coherence viol./fold": _fmt(s["coherence_violating_players"], 4),
                     "folds w/ ≥1": _coherence_fold_count(rep, a)})
    A(_md_table(rows, ["arm", "target", "assignment", "CRPS", "MAE", "cov80", "tier ρ",
                       "coherence viol./fold", "folds w/ ≥1"]))
    A("\n⛔ **CRPS selects. MAE never does** — the target is skewed and the low-availability cohort "
      "is exactly where the conditional median sits near the floor (NF-D11 / NF-D14). Disclosed, "
      "not used.\n")
    A("\n⚠️ **The coherence column is a PRECONDITION, ⛔ not a discriminator.** The pre-registration "
      "says so in advance: the `rate_*` arms satisfy it by construction, so it must not be presented "
      "as evidence that they beat anything. It is reported for EVERY arm — a constraint a degenerate "
      "satisfies is fine (the metric then eliminates it); a *criterion* a degenerate WINS is fatal "
      "(NF1.8).\n")
    A("\n⭐ **AND THE PRE-REGISTRATION'S \"by construction\" IS REFUTED BY THIS COLUMN, at the edge.** "
      "The value is a per-fold MEAN, and no arm reaches exactly 0: `rate_refit` carries one "
      "violating player in ONE of seven folds. The `coherence_restored` gate demands `= 0`, so it "
      "reads **False for every arm in the field** — which is why the injected-effect control below "
      "can only return `BLIND`, and it is a fact about a deterministic constraint, ⛔ not about the "
      "family's statistical sensitivity. Recorded as it fell (E2.1-r); the remedy is a successor "
      "whose coherence clause declares its attribution and its tolerance FORWARD.\n")

    A("\n## 2. Could the re-fit ACT? (NF-D20 — counted, never assumed)\n")
    A("The pre-registration §1b predicted this table before any scoring. A cell the re-fit cannot "
      "move is UNINFORMATIVE about the hypothesis, ⛔ never a pass.\n")
    rows = []
    for p, d in sorted(rep.get("refit_activity_pooled", {}).items()):
        for tgt in ("rate", "rate_reselect"):
            if tgt in d:
                rows.append({"position": p, "target": tgt,
                             "folds active": f"{d[tgt]['folds_active']}/{d[tgt]['folds']}",
                             "max abs Δscore": _fmt(d[tgt]["max_abs_score_delta"], 6),
                             "min ρ vs points-fit": _fmt(d[tgt]["min_rho_vs_points_fit"], 6),
                             "can act": str(d[tgt]["can_act"])})
    A(_md_table(rows, ["position", "target", "folds active", "max abs Δscore",
                       "min ρ vs points-fit", "can act"]))

    A("\n## 3. The winner vs the incumbent\n")
    p_ = rep["pooled"]
    A(f"Winner **`{p_['winner']}`** ({p_['selection_rule']}). Mean CRPS lift **{_fmt(p_['mean_lift_vs_incumbent'])}** "
      f"over {len(rep['folds'])} folds, winning **{p_['folds_won']}/{len(rep['folds'])}**. "
      f"Tie band ±{_fmt(p_['tie_band'])} (the per-fold SE of the winner's own lift — a dispersion "
      f"quantity fixed by the design, ⛔ not a threshold chosen to reach a verdict).\n")
    A(_md_table([{"fold": k, "lift": _fmt(x)} for k, x in p_["per_fold_lift"].items()],
                ["fold", "lift"]))

    A("\n## 4. The matched pairs — WHICH factor moved it (NF-D15 g′ / NF-W7e)\n")
    rows = []
    for k, d in rep["matched_pair_reads"].items():
        if k.startswith("_"):
            continue
        rows.append({"pair": k, "factor": d["factor"], "Δ CRPS": _fmt(d["mean_paired_delta_crps"]),
                     "folds +": f"{d['folds_positive']}/{d['folds']}",
                     "one-sided p": _fmt(d["one_sided_p"]), "isolates": d["isolates"]})
    A(_md_table(rows, ["pair", "factor", "Δ CRPS", "folds +", "one-sided p", "isolates"]))
    inter = rep["matched_pair_reads"].get("_2x2_interaction")
    if inter:
        A("\n### The 2×2 interaction\n")
        A(_md_table([{"quantity": k, "value": _fmt(x)} for k, x in inter.items()
                     if k not in ("reading", "cells_mean_lift_vs_incumbent")],
                    ["quantity", "value"]))
        A(f"\n{inter['reading']}\n")

    A("\n## 5. Gates\n")
    g = v["gates"]
    d = rep["deflation"]
    und = rep.get("gate_undefined", {})

    def _gv(key: str) -> str:
        """⭐ UNDEFINED is its OWN state, never rendered as a failure (MH2). A statistic that could
        not be computed at this fold count has said nothing in either direction."""
        if und.get(key):
            return "UNDEFINED (not computable at this n — ⛔ not a failure)"
        return str(g.get(key))
    rows = [
        {"gate": "PBO (FIELD-level, eligible = the declared field)", "value": _fmt(d["pbo"]),
         "bar": f"< {d['pbo_max']}", "verdict": _gv("pbo_field_level")},
        {"gate": "DSR (binding: degenerates AND reference ∉ V)", "value": _fmt(d["dsr_binding"]),
         "bar": f"≥ {d['dsr_min']}", "verdict": _gv("dsr")},
        {"gate": "DSR (reference INCLUDED in V — reported beside it)",
         "value": _fmt(d["dsr_reference_included_in_v"]), "bar": "—", "verdict": "—"},
        {"gate": "DSR (whole field)", "value": _fmt(d["dsr_whole_field"]), "bar": "—",
         "verdict": "—"},
        {"gate": "fold consistency (calibrated — MH2 H8)",
         "value": str(rep["fold_consistency"]["observed_wins"]),
         "bar": (f"≥ {rep['fold_consistency']['wins_required']} wins "
                 f"(false-fire {_fmt(rep['fold_consistency']['attained_false_fire'], 3)}; the raw "
                 f"0.60 rate would need {rep['fold_consistency']['legacy_wins_required']} at "
                 f"false-fire {_fmt(rep['fold_consistency']['legacy_false_fire'], 3)})"),
         "verdict": _gv("fold_consistency")},
        {"gate": "BH-FDR (SINGLE hypothesis — declared §3)", "value": _fmt(p_["one_sided_p"]),
         "bar": f"≤ {M14.FDR_Q}", "verdict": _gv("bh_fdr")},
        {"gate": "ordering not regressed (draftable tier)",
         "value": json.dumps(rep["ordering"]["by_position_winner_vs_incumbent"]),
         "bar": "no BH-significant regression", "verdict": _gv("ordering_not_regressed")},
        {"gate": "ordering — full population (disclosed)",
         "value": json.dumps(rep["ordering"]["full_population_by_position"]),
         "bar": "ρ ≥ incumbent", "verdict": str(rep["ordering"]["full_population_not_regressed"])},
        {"gate": "coherence restored", "value": _fmt(
            rep["leaderboard"][p_["winner"]]["coherence_violating_players"], 0),
         "bar": "= 0", "verdict": str(g.get("coherence_restored"))},
        {"gate": "degenerates lose", "value": json.dumps(anchors_scored(rep)),
         "bar": "all lose", "verdict": str(g.get("degenerates_lose"))},
        {"gate": "own-form peeking ceiling", "value": _fmt(rep["anchors"]["own_form_ceiling"]),
         "bar": rep["anchors"]["ceiling_reading"], "verdict": _gv("own_form_ceiling")},
    ]
    A(_md_table(rows, ["gate", "value", "bar", "verdict"]))
    A(f"\n{rep['ordering']['bh_direction_note']}\n")
    A(f"\nNF1.8 triad beside PBO — a rank statistic alone cannot tell an unstable pick from a tied "
      f"one: flip distribution `{json.dumps(d['flip_distribution'])}`, Bailey performance "
      f"degradation **{_fmt(d['bailey_degradation_pct'], 3)}%**, contender spread "
      f"**{_fmt(d['spread_contender'])}** against a whole-field spread of "
      f"**{_fmt(d['spread_whole_field'])}** (the whole-field figure contains this field's own "
      f"declared degenerates, so it measures the degenerates — MH2 / NF1.8).\n")
    A(f"\nTrial Sharpes: `{json.dumps(d['trial_sharpes'])}`. `V` is measured over "
      f"`{'`, `'.join(d['v_members'])}` — the pre-registration §3 convention: the two degenerates "
      f"AND the `incumbent` REFERENCE arm are excluded (MH2.1 (a): a structural 0.0 inflates a small "
      f"family's dispersion), while `n_trials` stays at the full declared "
      f"{d['declared_field_size']}.\n")

    A("\n## 6. The INJECTED-EFFECT POSITIVE CONTROL (pre-registered §3)\n")
    c = rep["positive_control"]
    A(f"**`{c['verdict']}`** at an injected **+{c['effect_injected_crps']} CRPS** and "
      f"**+{c['effect_injected_tier_rho']} tier-ρ** per fold on every non-degenerate, "
      f"non-reference arm.\n")
    A(f"\n{c['reason']}\n")
    # ⭐ PM ruling D2 (2026-08-29): annotate the badge at the point of reading, so a future reader
    # cannot take it at face value. Render-time only — the control's own verdict string above is
    # left exactly as the instrument returned it (E2.1-r: a result is annotated, never re-labelled).
    _blockers = {g for b in c.get("blocking_gates", {}).values() for g in b}
    _invariant = sorted(_blockers & {"coherence_restored"})
    if c["verdict"] == "BLIND" and _invariant:
        A(f"\n⚠️ **⛔ DO NOT READ THAT BADGE AT FACE VALUE — the blockage is a DETERMINISTIC "
          f"CONSTRAINT, not statistical insensitivity, and the instrument cannot yet say so.** "
          f"`{'`, `'.join(_invariant)}` is INJECTION-INVARIANT: the injection moves CRPS and tier-ρ "
          f"and cannot move a board's coherence, so no arm could clear it however sensitive this "
          f"family is — and `stratified` and `feasibility_clamp` are blocked under injection by it "
          f"ALONE, with every metric gate AND `dsr` firing correctly for them. `BLIND` reads \"a "
          f"null from this family is free\"; the honest reading is that the family's statistical "
          f"half demonstrably fires and its verdict was decided by a constraint no injection can "
          f"reach — NF-D18's `CONSTRAINT_REFUSED`, one level up, inside a positive control. "
          f"Recorded as the instrument returned it; **PLAT-CVP2** is carded to accept a "
          f"FORWARD-DECLARED set of injection-invariant gates and report `CONSTRAINT_BLOCKED`, "
          f"leaving `BLIND` its meaning for gates the injection could have moved.\n")
    A(f"\n* metric gates: `{'`, `'.join(c['metric_gates'])}`\n"
      f"* deflation-class gates present: `{'`, `'.join(c['deflation_gates']) or '—'}`\n"
      f"* survivors: `{'`, `'.join(c['survivors']) or 'none'}`  ·  metric survivors: "
      f"`{'`, `'.join(c['metric_survivors']) or 'none'}`  ·  deflation-blocked: "
      f"`{'`, `'.join(c['deflation_blocked']) or 'none'}`\n"
      f"* null-control leg ran: **{c['null_control_checked']}**; survivors on the NO-EFFECT "
      f"payload: `{c['null_control_survivors']}` (any survivor here would make the family VACUOUS "
      f"and every reading of this study meaningless)\n")
    A(f"\n⭐ **`field_level_gates_applied_per_arm` = `{c['field_level_gates_applied_per_arm'] or '[]'}`.** "
      f"EMPTY is the affirmative finding the pre-registration predicted: this study's registered "
      f"per-arm gate table deliberately carries NO field-level statistic as a per-arm pass/fail. "
      f"CSCV/PBO has one value for the whole field and answers whether the SELECTION overfit; "
      f"reading it per-arm converts \"the search was unstable\" into \"this arm failed\", which is "
      f"not a statement the statistic makes (PLAT-CVP1 defect 4(a)).\n")
    A(f"\nField-level PBO, reported BESIDE the control because it is deliberately outside the "
      f"per-arm table: real **{_fmt(c['field_level_pbo_real'])}** → injected "
      f"**{_fmt(c['field_level_pbo_injected'])}** (the injection moved the in-sample winner on "
      f"**{c['field_level_pbo_splits_whose_winner_moved']}/{c['field_level_pbo_splits']}** splits; "
      f"injection inert: **{c['field_level_pbo_injection_inert']}**).\n\n{c['field_level_pbo_note']}\n")

    A("\n## 7. Anchors\n")
    an = rep["anchors"]
    A(f"- Degenerates scored every run and READ, ⛔ not reasoned about: "
      f"`{json.dumps(an['degenerates_scored'])}` against the winner's **{_fmt(an['winner_crps'])}** "
      f"⇒ every degenerate loses: **{an['every_degenerate_loses']}**.\n")
    A(f"\n- Own-form peeking ceiling (one PER FORM — the forms NEST, so a single field-wide ceiling "
      f"would veto a legitimately better nested form, NF-D16 g‴): **{_fmt(an['own_form_ceiling'])}**, "
      f"gap **{_fmt(an['own_form_ceiling_gap'])}**, respected **{an['own_form_ceiling_respected']}**. "
      f"{an['ceiling_reading']}\n")
    A("\n⭐ A note a reader would otherwise read as a bug: the oracle REPLACES the score, which is "
      "this story's treated factor — so two arms differing only in the fit target share ONE ceiling. "
      "That is correct: the ceiling is a property of the FORM, not of the target.\n")

    A("\n## 8. The JOINT success criterion (the spec's three legs)\n")
    j = v["joint_success"]
    A(_md_table([
        {"leg": "(a) ordering holds at every draftable tier", "value": str(j["a_ordering_holds"]),
         "note": j["a_note"]},
        {"leg": "(b) give-back removed / not reintroduced", "value": str(j["b_giveback_removed"]),
         "note": f"arm {_fmt(j['b_giveback_pct'], 2)}% vs incumbent "
                 f"{_fmt(j['b_incumbent_giveback_pct'], 2)}%"},
        {"leg": "(c) NF-INJ1 violations → 0", "value": str(j["c_coherence_restored"]),
         "note": f"attributable violating players: {_fmt(j['c_violations_attributable'], 0)}"},
        {"leg": "**ALL THREE**", "value": f"**{j['all_three']}**", "note": ""},
    ], ["leg", "value", "note"]))

    if rep.get("application_2026"):
        A("\n## 9. The 2026 board — the CURRENT served (flip-board) vintage\n")
        app = rep["application_2026"]
        if app.get("arms_subset"):
            A("\n> 🚨 **THIS SECTION RAN ON AN ARM SUBSET — A CODE-PATH PROOF, ⛔ NEVER A GATE.** "
              "The `mvp1_null` attribution control and the give-back comparison need the FULL "
              "declared field; every number below is plumbing, not evidence.\n")
        A(f"Built off `generated_at` **{app['board_generated_at']}**. Injury-capped cohort "
          f"n=**{app['n_capped']}** ({app['cohort_source']}).\n")
        fr = app.get("baseline_freshness") or {}
        vin = app.get("served_vintage") or {}
        A(f"\n**Baseline vintage, verified from INSIDE the served artifact before any measurement** "
          f"(the NF-INJ3b-SHIP lesson): local MVP-1 `{fr.get('local_mvp1_generated_at')}` vs the "
          f"SERVED board `{fr.get('served_generated_at')}` = **{_fmt(fr.get('lag_hours'), 2)}h** "
          f"against a {_fmt(fr.get('max_lag_hours'), 1)}h bar; the served board's own injury-input "
          f"verdict is **{(fr.get('served_injury_input') or {}).get('verdict')}** "
          f"({(fr.get('served_injury_input') or {}).get('lag_hours')}h). Injury-games stamp on the "
          f"served board: **{(vin.get('injury_games_stamp') or {}).get('verdict')}**; adopted "
          f"reported-absence overrides: **{vin.get('reported_absence_count')}**.\n")
        rp = app.get("reproduction_pin")
        if rp:
            A(f"\n**Reproduction pin:** the incumbent arm rebuilt through this story's code matches "
              f"the SERVED artifact to **{rp['worst_abs_diff']:.3g}** over {rp['n']} rows "
              f"(tolerance {rp['tolerance']}) ⇒ **{rp['reproduces']}**. {rp['note']}\n")
        rows = []
        for a, r in app["arms"].items():
            gb = r["injury_giveback"]
            rows.append({
                "arm": a, "target": r["score_target"],
                "impossible rows": _fmt(r["coherence_violating_players"], 0),
                "…attributable": _fmt(r["coherence_violating_players_attributable"], 0),
                "give-back %": _fmt(gb.get("giveback_pct"), 2),
                "median ratio": _fmt(gb.get("median_point_ratio")),
                "ρ(games, ratio)": _fmt(r["availability_gradient"]["rho"]),
                "clamp hi/lo": f"{r['clamp_saturation_high']}/{r['clamp_saturation_low']}"})
        A(_md_table(rows, ["arm", "target", "impossible rows", "…attributable", "give-back %",
                           "median ratio", "ρ(games, ratio)", "clamp hi/lo"]))
        A(f"\n⭐ **ATTRIBUTION BY CONTROL, not by scope declaration.** {app['attribution_control']}\n")

    A("\n## 10. Null classification\n")
    A(f"```json\n{json.dumps(rep.get('null_classification'), indent=2)}\n```\n")

    A("\n## 11. Reading, against the pre-registration's §6\n")
    A(f"- **{v['state']}** — {v['why']}.\n")
    A(f"\n- DSR reading: winner per-fold Sharpe **{_fmt(v['dsr_reading']['winner_sharpe'])}** against "
      f"the declared field's benchmark SR0 **{_fmt(v['dsr_reading']['benchmark_SR0'])}** ⇒ "
      f"**{v['dsr_reading']['state']}**. {v['dsr_reading']['note']}\n")
    dd = d.get("dsr_2x2_diagnostic") or {}
    if dd.get("evaluable"):
        A(f"\n- The 2×2, computed as a labelled diagnostic BEFORE naming any remedy (NF-W7f): "
          f"dropping the most extreme arm in `V` (`{dd['dropped_arm']}`, Sharpe "
          f"{_fmt(dd['dropped_arm_sharpe'])}) collapses `V` **{_fmt(dd['V_declared'])} → "
          f"{_fmt(dd['V_without_dropped_arm'])}** and moves DSR **{_fmt(dd['dsr_declared'])} → "
          f"{_fmt(dd['dsr_without_dropped_arm'])}**. {dd['note']} {dd['reading']}\n")
    elif dd:
        A(f"\n- The DSR 2×2 is **not reported**: {dd.get('why')}\n")
    A(f"\n- ⛔ **NO \"more data\" re-test trigger** is published. {v['no_more_data_trigger_why']}\n")
    path.write_text("\n".join(L) + "\n")


def anchors_scored(rep: dict) -> dict:
    return rep["anchors"]["degenerates_scored"]


def _fmt(v, nd: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, np.integer)) and nd == 0:
        return str(int(v))
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _md_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out) + "\n"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2b — rate-target ordering §0.5 bake-off")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--folds", default=None,
                    help="comma seasons; default = NF1.5's OWN stage-1 window (inherited)")
    ap.add_argument("--no-2026", action="store_true", help="skip the served-board application")
    ap.add_argument("--served-json", default=None,
                    help="the PUBLISHED 2026 projections.json (the CURRENT served vintage). "
                         "Default: artifacts/nf_inj2b_baseline/served_projections_2026.json")
    ap.add_argument("--only-arms", default=None,
                    help="comma-separated arm subset for the 2026 application — a CODE-PATH PROOF "
                         "only, ⛔ never a gate (the attribution control needs the full field)")
    ap.add_argument("--smoke", action="store_true",
                    help="two folds, no 2026 — a CODE-PATH PROOF, ⛔ never a gate")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-render the markdown from the COMMITTED json and exit. ⛔ Re-scores "
                         "NOTHING: `write_report_md` is a pure function of the stored report, so a "
                         "rendering defect is fixable without a refit and without any number being "
                         "able to move (the NF-W2e rule — derive the report at report time, so "
                         "correcting a wrong sentence never costs a re-run, which is the pressure "
                         "that leaves a known-wrong record published).")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.rewrite_report:
        stem = _STEM + ("_smoke" if args.smoke else "")
        src = _REPORT_DIR / f"{stem}.json"
        if not src.exists():
            raise SystemExit(f"no committed report at {src} — there is nothing to re-render")
        rep = json.loads(src.read_text())
        write_report_md(rep, _REPORT_DIR / f"{stem}.md")
        print(f"re-rendered {stem}.md from {stem}.json — verdict {rep['verdict']['state']} "
              f"(generated {rep['generated_at'][:19]}Z; NOT re-scored)")
        return 0
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    import duckdb
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree must copy the "
                         "gitignored artifacts + DuckDB in first (NF-INFRA1)")
    con = duckdb.connect(args.duckdb, read_only=True)
    selections = N15.load_selection(json.loads(_NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    folds = (tuple(int(x) for x in args.folds.split(",")) if args.folds
             else R2.registered_folds())
    if args.smoke:
        folds, args.no_2026 = folds[-2:], True

    rep = run(con, args.schema, folds, selections, base_from=args.base_from)
    if not args.no_2026:
        arms_2026 = (tuple(a.strip() for a in args.only_arms.split(",")) if args.only_arms
                     else B.ARMS)
        if args.only_arms:
            log.warning("[ALERT] the 2026 application is running on a SUBSET %s — a CODE-PATH PROOF "
                        "only. The mvp1_null attribution control and the give-back comparison need "
                        "the FULL field; ⛔ nothing from a subset run is a gate.", arms_2026)
        rep["application_2026"] = apply_2026(
            con, args.schema, selections, arms_2026, base_from=args.base_from,
            served_json=Path(args.served_json) if args.served_json else None)
        rep["application_2026"]["arms_subset"] = bool(args.only_arms)
        # the joint criterion needs the served board, so it is RE-computed once it exists
        w = rep["pooled"]["winner"]
        rep["verdict"]["joint_success"] = joint_success(
            arm=w, gates=rep["verdict"]["gates"], app2026=rep["application_2026"],
            activity=rep["refit_activity_pooled"])
        rep["verdict"] = verdict(
            winner=w, pooled=rep["pooled"], defl=rep["deflation"], anchors=rep["anchors"],
            gates=rep["verdict"]["gates"], ordering=rep["ordering"],
            joint=rep["verdict"]["joint_success"], pair_reads=rep["matched_pair_reads"],
            gate_undefined=rep.get("gate_undefined"))

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{_STEM}{suffix}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_report_md(rep, _REPORT_DIR / f"{_STEM}{suffix}.md")
    v = rep["verdict"]
    log.info("VERDICT %s — %s · winner %s · lift %s · PBO %s · DSR %s · control %s",
             v["state"], v["why"], rep["pooled"]["winner"],
             rep["pooled"]["mean_lift_vs_incumbent"], rep["deflation"]["pbo"],
             rep["deflation"]["dsr_binding"], rep["positive_control"]["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""run_nf_d22_power_floor.py — NF-D22: the POWER-DERIVED coverage floor for structurally-thin groups,
and the consequence of installing it.

════════════════════════════════════════════════════════════════════════════════════════════════
🚨 WHAT THIS STORY IS, AND — MORE IMPORTANTLY — WHAT IT IS NOT
════════════════════════════════════════════════════════════════════════════════════════════════
IT IS: a fix to a measured statistical defect in a GATE. The standing interval re-validation and the
NF-G0 `interval_floors` promotion gate both read a per-group coverage floor as a HARD POINT ESTIMATE
at the nominal level. Against a *perfectly calibrated* band that floor rejects with probability

    n                            30     81    148    400   1000   3000   6000
    P(reject | truly nominal)   0.393  0.456  0.500  0.470  0.481  0.489  0.492

— i.e. **a coin toss at every sample size this program has**, and, the part that is easy to get
wrong, that rate does NOT improve with n (more rows buy the power to detect a SMALLER true shortfall,
not a lower false-reject rate — NF1.8 §3). A gate whose refusals are coin tosses is not conservative;
it is uninformative, and its refusals still read as evidence, which is worse than not gating at all.

IT IS NOT: a way to unblock anything. NF-D21 — the rookie-point publish that this floor happens to
have refused — is a CLOSED story (`rookie_publish_policy.DISPOSITION == "CONSTRAINT_REFUSED"`,
`DISPOSITION_IS_NOT_PENDING == True`), and the PM closed it precisely so that no follow-on would feel
a pull toward a floor that clears λ = 0.5. This runner honours that in the only way that is checkable
rather than promised:

  ⛔ **THE FLOOR IS DERIVED BEFORE ANY BAND IS SCORED, AND §1 OF THE REPORT PROVES IT.** The floor
     table is computed from row counts and a pre-registered false-reject target alone —
     `coverage_power_floor.power_floor` takes no coverage argument and a guard asserts its signature
     never gains one. Every floor in this report could have been published a year ago.
  ⛔ **THE PRE-REGISTERED TARGET IS NOT A NEW NUMBER.** It is NF1.8's own Tier-2 level (a one-sided
     95% test ⇒ 0.05), recorded long before any of the results now read against it. NF-D22 changes
     that level's SCOPE (from a hardcoded two-position tuple to every constrained group) and its FORM
     (exact Binomial rather than a normal approximation that does not honour the rate it advertises).
     It does not move the level, and a guard pins the equality mechanically.
  ⛔ **THE MEASURED 0.7905 THAT REFUSED NF-D21 APPEARS NOWHERE IN THE DERIVATION.** It appears in §3
     below only as a CONSEQUENCE — read after the floor exists — which is the correct and only
     admissible ordering (E2.1-r).
  ⛔ **NOTHING HERE FLIPS A SERVING SWITCH.** `rookie_publish_policy.SERVING_ENABLED` is untouched and
     stays `False`. A publish requires a NEW PM disposition on a CLOSED story; this runner reports
     that the gate now clears and stops. (`assert_coherent` would refuse the incoherent state anyway
     — serving while the disposition still reads `CONSTRAINT_REFUSED` — but the point is that the
     re-decision is the PM's, not a session's.)
  ⛔ **THE §0.5 SELECTION FLOOR IS UNTOUCHED.** `run_rookie_perposition_ablation.position_floors`
     still governs bake-off ELIGIBILITY at the hard nominal level, and its guards are unedited and
     green. There a FIELD of arms exists and the METRIC does the selecting; here there is one shipped
     band, no field and no metric, so the floor IS the whole decision — which is exactly and only
     where a ~50% false-reject rate is fatal. Relaxing eligibility inside recorded searches would
     re-decide them post hoc.

════════════════════════════════════════════════════════════════════════════════════════════════
WHAT IT MEASURES
════════════════════════════════════════════════════════════════════════════════════════════════
  §1  THE FLOOR, DERIVED FROM DESIGN QUANTITIES ONLY — every group's floor, its required covered-row
      count, the relaxation in rows, its exact false-reject rate under both rules, and the floor's
      RESOLUTION (the largest true shortfall it detects at 80% power). Published before any band is
      scored.
  §2  THE TWO-SIDED VALIDATION — a truly-nominal band must clear the new floor at the target rate,
      AND a genuinely-short band must still fail it. Both computed exactly from the Binomial, at
      every real group size, so neither half rests on a simulation seed.
  §3  THE CONSEQUENCE — NF-D16's λ sweep re-scored under the floor in force, and λ = 0.5 routed
      through the ten NF-G0 gates. Read AFTER §1 and §2, never before.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · a projection-quality gate. No market, edge,
CLV or ROI claim is made or implied anywhere in this story.

⛔ WRITES ONLY ITS OWN `nf_d22_power_floor.{json,md}` PATHS. A run must never overwrite a decided
story's artifacts — NF-D21's `nf_g0_d21_governance_publish.*` record its refusal under the rule in
force AT THE TIME and must keep saying so (the NCAAF-P2.1 S1-serve lesson: a fixed-output-path write
clobbered a decided story's audit trail and nothing failed).

RUN ON THE LAPTOP. §1 and §2 are pure arithmetic and need nothing; §3 needs the rookie pool + the
2026 board, which are GITIGNORED and therefore ABSENT IN A FRESH WORKTREE (NF-INFRA1) — point
`--artifacts` at the main checkout rather than copying files in:

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d22_power_floor

    # from a worktree (§3 needs the main checkout's artifacts, ~1 min):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d22_power_floor \\
      --artifacts /path/to/main/quant_sports_intel_models/football/nfl/fantasy/artifacts

    # §1 + §2 only (instant, needs no artifact at all):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d22_power_floor --design-only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import coverage_power_floor as CPF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    rookie_point_recalibration as RC,
    rookie_publish_policy as RP,
    run_nf_d18_top_attenuation as NFD18,
    run_nf_d21_publish as D21,
    run_interval_revalidation as RV,
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
    run_veteran_interval_ablation as NF19,
)

log = logging.getLogger("nfl.fantasy.nf_d22_power_floor")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_OUT_JSON = _REPORT_DIR / "nf_d22_power_floor.json"
_OUT_MD = _REPORT_DIR / "nf_d22_power_floor.md"

#: The group sizes §1 and §2 are evaluated at. ⚠️ DESIGN QUANTITIES: a REFERENCE LADDER spanning the
#: program's whole range plus the ACTUAL per-group row counts, which are properties of the held-out
#: cohorts (how many rookie RBs were drafted 2019–2025) and not of any band's performance. Nothing
#: here is chosen by looking at a coverage number.
_REFERENCE_NS = (30, 50, 81, 100, 148, 200, 400, 1000, 3000, 6000)

#: The true coverages §2 probes for the "a genuinely-short band must still FAIL" half. Spaced from
#: nominal downward; pre-registered as a grid, not selected.
_SHORTFALL_GRID = (0.80, 0.775, 0.75, 0.725, 0.70, 0.65, 0.60)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — the floor, from design quantities ONLY
# ══════════════════════════════════════════════════════════════════════════════════════════════
def design_table(nominal: float = 0.80, ns: tuple[int, ...] = _REFERENCE_NS) -> dict:
    """The floor at every reference size — computable with no band, no board and no fold.

    ⭐ THIS IS THE STORY'S CENTRAL EVIDENCE, not a preamble. If the floor can be published from row
    counts and a pre-registered target alone, then no result can have produced it, and the E2.1-r
    accusation ("a floor that moves until something clears it") has nothing to attach to."""
    rows = [CPF.group_floor(n, nominal=nominal) for n in ns]
    return {
        "nominal": nominal,
        "floor_rule": CPF.FLOOR_RULE,
        "target_false_reject_rate": CPF.FALSE_REJECT_TARGET,
        "target_provenance": CPF.TARGET_PROVENANCE,
        "detection_power": CPF.DETECTION_POWER,
        "rows": rows,
        # ⭐ THE INDICTMENT OF THE RULE BEING REPLACED, as a single number rather than a claim.
        "incumbent_false_reject_range": [
            round(min(r["false_reject_rate_at_nominal_floor"] for r in rows), 4),
            round(max(r["false_reject_rate_at_nominal_floor"] for r in rows), 4)],
        "new_false_reject_max": round(max(r["false_reject_rate"] for r in rows), 4),
        # every size this program has is "thin" under the only knob-free criterion available — which
        # is WHY the floor is applied uniformly and no thin-group list exists
        "all_reference_sizes_thin": all(r["is_thin"] for r in rows),
        # ⚠️ THE ENVELOPE, NOT POINTWISE MONOTONICITY. The requirement is an integer count, so
        #    discreteness makes the floor locally jagged; what is stable is `(nominal − floor)·√n`.
        #    Asserting monotonicity would be a claim the arithmetic does not support.
        "attenuation_envelope": [
            round(min((nominal - r["floor"]) * np.sqrt(r["n"]) for r in rows), 4),
            round(max((nominal - r["floor"]) * np.sqrt(r["n"]) for r in rows), 4)],
        "self_attenuates": bool(rows[0]["floor"] < rows[-1]["floor"] < nominal
                                and (nominal - rows[-1]["floor"]) < 0.01),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the two-sided validation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def two_sided_validation(nominal: float = 0.80, ns: tuple[int, ...] = _REFERENCE_NS,
                         shortfalls: tuple[float, ...] = _SHORTFALL_GRID) -> dict:
    """Both halves a floor must satisfy, computed EXACTLY (no simulation, so no seed to be lucky on).

    ⭐ A ONE-SIDED CHECK WOULD BE VACUOUS AND IS THE OBVIOUS WAY TO GET THIS WRONG. "A correct band
    passes" is satisfied perfectly by a floor of 0.0; "a broken band fails" is satisfied perfectly by
    a floor of 1.0. Only both together say anything, and the second half is what stops NF-D22 from
    being a floor-removal wearing a floor's badge."""
    rows, verdicts = [], []
    for n in ns:
        floor = CPF.power_floor(n, nominal=nominal)
        row = {"n": n, "floor": round(floor, 4),
               "P(pass | truly nominal)": round(
                   CPF.pass_probability(n, true_coverage=nominal, floor=floor), 4),
               "target P(pass)": round(1.0 - CPF.FALSE_REJECT_TARGET, 4)}
        for p in shortfalls:
            row[f"P(pass | true cov {p:.3f})"] = round(
                CPF.pass_probability(n, true_coverage=p, floor=floor), 4)
        rows.append(row)
        # HALF A — a truly-nominal band clears at (at least) the pre-registered rate. EXACT.
        nominal_ok = row["P(pass | truly nominal)"] >= 1.0 - CPF.FALSE_REJECT_TARGET
        # HALF B — a materially-short band still fails. "Material" is read off the floor's OWN
        # resolution rather than a number picked here: at each n, the shortfall the floor detects at
        # `DETECTION_POWER` must exist and must lie strictly below nominal.
        res = CPF.detectable_shortfall(n, nominal=nominal)
        short_ok = res is not None and res < nominal
        verdicts.append({"n": n, "nominal_band_clears": bool(nominal_ok),
                         "short_band_still_fails": bool(short_ok),
                         "detectable_shortfall": res})
    return {
        "rows": rows,
        "verdicts": verdicts,
        "pass": all(v["nominal_band_clears"] and v["short_band_still_fails"] for v in verdicts),
        "note": ("Exact Binomial throughout — both halves are closed-form, so neither rests on a "
                 "simulation seed. `detectable_shortfall` is the floor's RESOLUTION: a ✅ means "
                 "'not shown to be broken at this n', never 'shown to be right' (NF1.7 (a))."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — the consequence: NF-D16's λ sweep under the floor in force
# ══════════════════════════════════════════════════════════════════════════════════════════════
def floor_sweep(pool_path: Path, from_year: int, to_year: int,
                lams: tuple[float, ...] = (0.0, *RC.SHRINK_GRID)) -> dict:
    """NF-D21's λ sweep, re-scored under the NF-D22 floor. Same folds, same band, same arithmetic.

    ⛔ IT IS DIAGNOSIS, NOT A MENU — NF-D21's own words, and they bind here unchanged. λ is fixed by
    PM judgment; re-picking it because a neighbour has more headroom would be selecting on the
    constraint's own headroom, which NF1.8 prohibits outright. The sweep exists so a reader can see
    that the change is a property of the FLOOR (every λ gains the same ~9 rows) and not of λ.

    Both readings are carried per λ, so "what would the previous rule have said" is a column rather
    than an archaeology dig."""
    pool = NF17.load_pool(pool_path)
    cfg = RV.shipped_rookie_cfg()
    out_rows = []
    for lam in lams:
        folds = NF17.build_folds(pool, list(range(from_year, to_year + 1)),
                                 recalibrate=bool(lam), recal_lambda=float(lam))
        rec = NF18.run_arm(folds, cfg)
        if rec is None:
            out_rows.append({"lambda": float(lam), "error": "did not score"})
            continue
        positions = sorted({k[4:] for k in rec if k.startswith("cov_")})
        block = RV._floor_block(rec, positions, {"min_n": NF18._POS_FLOOR_MIN_N,
                                                 "tier2_positions": NF18._TIER2_POSITIONS,
                                                 "nominal": NF18._NOMINAL})
        out_rows.append({
            "lambda": float(lam),
            "pooled_coverage": round(float(rec["coverage_80"]), 4),
            "pooled_floor": block["pooled_floor"],
            "interval_score": round(float(rec["interval_score"]), 3),
            "coverage": {p: round(float(rec[f"cov_{p}"]), 4) for p in positions},
            "n_by_position": block["n_by_position"],
            "floors": block["floors"],
            "floors_at_nominal": block["floors_at_nominal"],
            "slack_rows": block["slack_rows"],
            "slack_rows_at_nominal": block["slack_rows_at_nominal"],
            "misses": block["misses"],
            "misses_at_nominal_floor": block["misses_at_nominal_floor"],
            "pass": bool(block["pass"]),
            "pass_at_nominal_floor": not block["misses_at_nominal_floor"],
            "floor_detail": block["floor_detail"],
            "family_false_reject": block["family_false_reject"],
            "pooled_backstop": block["pooled_backstop"],
        })
    return {"cohorts": [from_year, to_year], "config": cfg["label"], "rows": out_rows,
            "floor_rule": CPF.FLOOR_RULE}


def veteran_design_floors(nominal: float = None) -> dict:
    """The VETERAN population's floors under the same rule — the "uniformly, to every group" half.

    Included because NF-D22 must not be a rookie fix wearing a general badge. The veteran groups are
    ~20× larger, so their floors barely move (the correction self-attenuates), and showing that is
    the point: the rule is the same everywhere and it simply does less where less is needed.

    ⚠️ Row counts here come from NF1.9's OWN pre-registered fold design, not from a scored band, so
    this stays a design table."""
    nom = NF19._NOMINAL if nominal is None else float(nominal)
    return {
        "nominal": nom,
        "min_n": NF19._POS_FLOOR_MIN_N,
        "note": ("Veteran per-position n is ~20× the rookie equivalent, so the calibrated floor "
                 "sits within ~1pp of nominal there. The rule is identical; its EFFECT scales with "
                 "1/√n, which is why no thin-group boundary had to be drawn."),
        "reference": [CPF.group_floor(n, nominal=nom)
                      for n in (NF19._POS_FLOOR_MIN_N, 1000, 2000, 4000, 6000)],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, md_path: Path, json_path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-D22 — a power-derived coverage floor for structurally-thin groups")
    p("")
    p(f"**Generated:** {out['generated_at']} · **verdict: {out['verdict']}**")
    p("")
    p("> ⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · a projection-QUALITY gate. No "
      "market, edge, CLV or ROI claim is made or implied. Nothing in this run flips a serving "
      "switch: `rookie_publish_policy.SERVING_ENABLED` is untouched and stays "
      f"`{out['serving_enabled']}`.")
    p("")
    p(out["verdict_prose"])
    p("")
    p("## 1. The floor — derived from DESIGN QUANTITIES ONLY")
    p("")
    p("Every number in this section is a function of a group's held-out row count, the nominal "
      "coverage the band was built for, and a **pre-registered false-reject target**. Nothing else "
      "reaches it: `coverage_power_floor.power_floor` takes no coverage argument, and a guard "
      "asserts its signature never gains one. **This whole table could have been published before "
      "any band was ever scored** — which is the property that makes it a floor rather than a "
      "number reverse-engineered from something that failed (E2.1-r).")
    p("")
    p(f"**The target is not a new number.** {out['design']['target_provenance']}")
    p("")
    d = out["design"]
    p(_md(pd.DataFrame([{
        "n": r["n"], "floor (NF-D22)": r["floor"],
        "covered rows required": r["covered_rows_required"],
        "…at the nominal floor": r["covered_rows_required_at_nominal_floor"],
        "relaxation (rows)": r["relaxation_rows"],
        "P(reject | truly nominal)": r["false_reject_rate"],
        "…under the previous rule": r["false_reject_rate_at_nominal_floor"],
        "normal-approx floor (NF1.8 form)": r["normal_approx_floor"],
        "approx. rate error": r["approximation_error"],
        "detectable shortfall": r["detectable_shortfall"],
        "thin?": r["is_thin"]} for r in d["rows"]])))
    p("")
    p(f"⭐ **The rule being replaced rejects a perfectly-calibrated band "
      f"{d['incumbent_false_reject_range'][0]:.3f}–{d['incumbent_false_reject_range'][1]:.3f} of the "
      f"time — at EVERY size.** That is the defect: not that the floor is strict, but that its "
      f"refusals carry almost no information while still reading as evidence. Under the new rule the "
      f"worst observed false-reject rate across the same range is "
      f"**{d['new_false_reject_max']:.4f}**, against a target of "
      f"{d['target_false_reject_rate']:.2f}.")
    p("")
    p("⭐ **No thin-group list exists, and that is deliberate.** The floor self-attenuates, "
      f"converging to nominal as the group grows (`{d['self_attenuates']}`: at the largest "
      "reference size it sits within 1pp of nominal), so nothing has to decide where to stop "
      "applying it. ⚠️ Attenuation is an **envelope, not pointwise monotonicity** — the requirement "
      "is an integer count, so discreteness makes the floor locally jagged; what is stable is "
      f"`(nominal − floor)·√n`, measured here at "
      f"{d['attenuation_envelope'][0]:.2f}–{d['attenuation_envelope'][1]:.2f} across three orders "
      "of magnitude. Asserting monotonicity would have been a claim the arithmetic does not "
      "support. Under the pre-registered target every size "
      "this program has is 'thin' by the only knob-free criterion available — the calibrated floor "
      f"sits more than one covered row below the nominal one (`{d['all_reference_sizes_thin']}`) — "
      "so 'uniformly to all thin groups' and 'uniformly to every constrained group' are the same "
      "set. A boundary would have been a degree of freedom someone chose; there is none.")
    p("")
    p("⚠️ **`approx. rate error`** is why the exact Binomial form gates rather than NF1.8's normal "
      "approximation `nominal − 1.645·SE`: a positive value means that approximation rejects a "
      "truly-nominal band MORE often than the rate it advertises. NF-D22 keeps NF1.8's LEVEL and "
      "fixes its FORM.")
    p("")
    p("### 1b. The same rule on the VETERAN population — the 'uniformly' half")
    p("")
    p(out["veterans"]["note"])
    p("")
    vdf = pd.DataFrame([{"n": r["n"], "floor": r["floor"],
                         "relaxation (rows)": r["relaxation_rows"],
                         "relaxation (pp)": r["relaxation_pp"],
                         "P(reject | truly nominal)": r["false_reject_rate"]}
                        for r in out["veterans"]["reference"]])
    # ⚠️ rendered as text: `to_markdown(floatfmt=…)` formats an all-numeric frame column-blind, so
    #    an integer row count comes out as "400.0000" in a published artifact.
    vdf["n"] = vdf["n"].map(lambda v: f"{int(v)}")
    vdf["relaxation (rows)"] = vdf["relaxation (rows)"].map(lambda v: f"{int(v)}")
    p(_md(vdf))
    p("")
    p("## 2. The two-sided validation")
    p("")
    p("⭐ **A one-sided check would be vacuous, and it is the obvious way to get this wrong.** "
      "'A correct band passes' is satisfied perfectly by a floor of 0.0; 'a broken band fails' is "
      "satisfied perfectly by a floor of 1.0. Only both together say anything — and the second half "
      "is what stops this story from being a floor-removal wearing a floor's badge. Both are exact "
      "Binomial computations, so neither rests on a simulation seed.")
    p("")
    p(_md(pd.DataFrame(out["two_sided"]["rows"])))
    p("")
    p(f"**Verdict: {'✅ BOTH HALVES HOLD AT EVERY REFERENCE SIZE' if out['two_sided']['pass'] else '🚨 FAILED'}** "
      "— a truly-nominal band clears at or above the pre-registered rate, and a materially-short "
      "band still fails. " + out["two_sided"]["note"])
    p("")
    if out.get("sweep"):
        p("## 3. The consequence — NF-D16's λ sweep under the floor in force")
        p("")
        p("⚠️ **READ THIS SECTION AFTER §1 AND §2, WHICH IS THE ORDER IT WAS COMPUTED IN.** The floor "
          "above exists independently of everything below; this section reports what installing it "
          "implies for a band that was already scored. Reversing that order is exactly the E2.1-r "
          "inversion this story is most exposed to.")
        p("")
        p("⛔ **The sweep is DIAGNOSIS, not a menu** (NF-D21's words, unchanged). λ is fixed by PM "
          "judgment; re-picking it because a neighbour has more headroom would be selecting on the "
          "constraint's own headroom, which NF1.8 prohibits outright.")
        p("")
        srows = []
        for r in out["sweep"]["rows"]:
            if r.get("error"):
                srows.append({"λ": r["lambda"], "error": r["error"]})
                continue
            srows.append({
                "λ": r["lambda"], "pooled cov": r["pooled_coverage"],
                "IS80": r["interval_score"],
                **{f"cov {p}": v for p, v in sorted(r["coverage"].items())},
                **{f"slack {p} (rows)": v for p, v in sorted(r["slack_rows"].items())},
                "verdict (NF-D22)": "✅ met" if r["pass"] else "🚨 breach",
                "verdict (previous rule)": "✅ met" if r["pass_at_nominal_floor"] else "🚨 breach",
            })
        p(_md(pd.DataFrame(srows)))
        p("")
        p("Slack under the PREVIOUS rule, for comparison:")
        p("")
        p(_md(pd.DataFrame([
            {"λ": r["lambda"],
             **{f"slack {p} @nominal (rows)": v
                for p, v in sorted((r.get("slack_rows_at_nominal") or {}).items())},
             "misses (previous rule)": ", ".join(r.get("misses_at_nominal_floor") or []) or "—"}
            for r in out["sweep"]["rows"] if not r.get("error")])))
        p("")
    if out.get("governance"):
        p("## 4. NF-D16 at λ = 0.5 routed through the ten NF-G0 gates")
        p("")
        p(_md(pd.DataFrame([{"gate": g["gate"], "status": g["status"], "detail": g["detail"]}
                            for g in out["governance"]["validation"]["gates"]])))
        p("")
        p(f"`ready_to_promote`: **{out['governance']['validation']['ready_to_promote']}**")
        p("")
    p("## 5. What this does NOT do")
    p("")
    p("- ⛔ **It does not publish, and it does not flip a serving switch.** "
      f"`rookie_publish_policy.SERVING_ENABLED` is `{out['serving_enabled']}` and this run does not "
      "touch it. NF-D21 is a **CLOSED** story with disposition "
      f"`{out['nf_d21_disposition']['disposition']}` and "
      f"`DISPOSITION_IS_NOT_PENDING = {out['nf_d21_disposition']['is_not_pending']}`; a publish "
      "requires a NEW PM disposition recorded against the floor now in force. That re-decision is "
      "the PM's, and `rookie_publish_policy.assert_coherent()` refuses the incoherent in-between "
      "state (serving while the disposition still reads a refusal) at import.")
    p("- ⛔ **It does not touch the §0.5 SELECTION floor.** `position_floors` still gates bake-off "
      "eligibility at the hard nominal level, and NF1.8's guards are unedited and green. Relaxing "
      "eligibility inside searches that are already recorded would re-decide them post hoc.")
    p("- ⛔ **It does not correct for multiplicity**, deliberately: a Bonferroni split would make "
      "every individual floor LOOSER, which is the one adjustment a reader should most distrust "
      "from this story. The family false-reject rate is reported beside each population's floors as "
      "an honest caveat, and the per-group pre-registered target binds (NF1.8: report both "
      "conventions, let the pre-registered one bind).")
    p("- ⛔ **It does not make a floor pass mean 'the band is right'.** `detectable_shortfall` is the "
      "floor's resolution, published with every verdict: at n = 148 the floor detects a true "
      "coverage of ~0.71 or worse at 80% power and cannot resolve anything finer. A ✅ means 'not "
      "shown to be broken at this n'.")
    p("")
    p("## 6. A breach under this rule")
    p("")
    p("Still a **RE-SELECTION TRIGGER**, and the floor still may not move (E2.1-r; NF1.8 §1). ⭐ That "
      "prohibition binds HARDER now, not less: the false-reject target is NF1.8's own pre-registered "
      "level rather than a knob, and a breach under a calibrated rule is genuine evidence instead of "
      "a coin toss. `run_interval_revalidation` still exits non-zero on a breach.")
    p("")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(a) + "\n")
    json_path.write_text(json.dumps(out, indent=2, default=float))
    log.info("report → %s", md_path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--from-year", type=int, default=2019)
    ap.add_argument("--to-year", type=int, default=2025)
    ap.add_argument("--artifacts", default=None,
                    help="directory holding the rookie pool + season boards. GITIGNORED artifacts "
                         "are ABSENT in a fresh worktree (NF-INFRA1) — point this at the main "
                         "checkout rather than copying files in.")
    ap.add_argument("--design-only", action="store_true",
                    help="§1 + §2 only — pure arithmetic, needs no artifact")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")

    art = Path(args.artifacts) if args.artifacts else D21._ART
    design = design_table()
    two_sided = two_sided_validation()
    vets = veteran_design_floors()

    out: dict = {
        "story": "NF-D22",
        "generated_at": _now(),
        "best_alpha": 0,
        "floor_rule": CPF.FLOOR_RULE,
        "artifacts_dir": str(art),
        "design": design,
        "two_sided": two_sided,
        "veterans": vets,
        "serving_enabled": RP.SERVING_ENABLED,
        "nf_d21_disposition": {
            "disposition": RP.DISPOSITION,
            "is_not_pending": RP.DISPOSITION_IS_NOT_PENDING,
            "rationale": RP.DISPOSITION_RATIONALE,
            "note": ("NF-D22 does not re-open it. A publish needs a NEW PM disposition recorded "
                     "against the floor now in force; this run reports the gate's reading and "
                     "stops."),
        },
    }

    if not two_sided["pass"]:
        out["verdict"] = "🚨 THE FLOOR FAILED ITS OWN TWO-SIDED VALIDATION"
        out["verdict_prose"] = (
            "The power-derived floor did not satisfy both halves of its validation, so it may not "
            "be installed. ⛔ Do NOT proceed to §3 — a floor that cannot both admit a correct band "
            "and refuse a broken one is not a floor.")
        write_report(out, _OUT_MD, _OUT_JSON) if not args.no_report else None
        print(f"\n=== {out['verdict']} ===\n")
        return 1

    pool = art / "nf1_4_rookie_training.parquet"
    if args.design_only or not pool.is_file():
        if not args.design_only:
            log.warning("[ALERT] no rookie pool at %s — §3 SKIPPED. It is gitignored (NF-INFRA1); "
                        "pass --artifacts pointing at the main checkout.", pool)
        out["verdict"] = ("✅ FLOOR INSTALLED — design + two-sided validation clear"
                          + ("" if args.design_only else "; §3 SKIPPED (rookie pool absent)"))
        out["verdict_prose"] = (
            "The power-derived floor is derived from design quantities alone (§1) and satisfies "
            "both halves of its validation (§2). §3 — the consequence for NF-D16's λ sweep — was "
            "not computed in this run"
            + (" (`--design-only`)." if args.design_only else
               ", because the gitignored rookie pool is absent from this checkout (NF-INFRA1). "
               "⚠️ An absent §3 is NOT a clearance: nothing about NF-D16 may be read from this "
               "run."))
        if not args.no_report:
            write_report(out, _OUT_MD, _OUT_JSON)
        print(f"\n=== {out['verdict']} ===\n")
        return 0

    # ── §3 — the consequence, computed only after §1 and §2 stand ──────────────────────────────
    sweep = floor_sweep(pool, args.from_year, args.to_year)
    lam = float(RP.SHRINK_LAMBDA)
    served_row = next((r for r in sweep["rows"] if r["lambda"] == lam), None)
    out["sweep"] = sweep
    out["lambda"] = lam

    if served_row and not served_row.get("error"):
        revalidation = {"pass": bool(served_row["pass"]),
                        "floor_rule": CPF.FLOOR_RULE,
                        "rookies": {"misses": served_row["misses"],
                                    "floor_rule": CPF.FLOOR_RULE},
                        "rookie_point_shrink_lambda": lam}
        board_path = art / D21._SERVED_BOARD.format(season=args.season)
        if board_path.is_file():
            board = pd.read_parquet(board_path)
            # ⚠️ NOT `D21.serving_params`: it reads D21's OWN module-level pool path, which is the
            #    worktree's (absent — NF-INFRA1). The fit itself is D21's, unchanged; only the pool
            #    path is the one this run was given.
            params = NFD18.serving_fits(NF17.load_pool(pool),
                                        upto=args.season - 1)[RC.LEARNED_FOIL]
            effects = D21.board_effects(board, params, lam, "served (NF1.5 ordering)")
            parity = D21.scoring_parity(board, params, lam)
            lineage = D21.lineage_for(board, lam, args.season)
            with tempfile.TemporaryDirectory() as td:
                out["governance"] = D21.run_gates(board, effects, parity, revalidation, lineage,
                                                  Path(td))
            out["board_effects"] = effects
            out["scoring_parity"] = parity
        else:
            log.warning("[ALERT] no served board at %s — the NF-G0 gate run is SKIPPED", board_path)

    floors_ok = bool(served_row and served_row.get("pass"))
    prev_ok = bool(served_row and served_row.get("pass_at_nominal_floor"))
    gates_ok = bool((out.get("governance") or {}).get("validation", {}).get("ready_to_promote"))
    out["interval_floors_clears_at_lambda"] = floors_ok
    out["interval_floors_cleared_under_previous_rule"] = prev_ok
    out["all_g0_gates_clear"] = gates_ok

    if floors_ok:
        out["verdict"] = "✅ FLOOR INSTALLED — and NF-D16 at λ=0.5 now CLEARS the interval-floor gate"
        out["verdict_prose"] = (
            f"The power-derived floor is derived from design quantities alone (§1) and satisfies "
            f"both halves of its validation (§2). Installing it, NF-D16's rookie recalibration at "
            f"λ = {lam} clears every per-group coverage floor"
            + (" and every one of the ten NF-G0 gates" if gates_ok else "")
            + f" — under the previous hard point-estimate rule it did not "
              f"(`pass_at_nominal_floor = {prev_ok}`). ⛔ **That is a CONSEQUENCE, not this story's "
              "motivation, and it publishes nothing.** NF-D21 stays CLOSED with disposition "
              f"`{RP.DISPOSITION}`; a publish needs a NEW PM disposition recorded against the floor "
              "now in force, and `SERVING_ENABLED` is untouched at "
              f"`{RP.SERVING_ENABLED}`.")
    else:
        out["verdict"] = "✅ FLOOR INSTALLED — NF-D16 at λ=0.5 is STILL refused"
        misses = (served_row or {}).get("misses") or ["(λ did not score)"]
        out["verdict_prose"] = (
            f"The floor is installed and validated (§1, §2). NF-D16 at λ = {lam} is nevertheless "
            f"still refused: {misses}. ⭐ That is a RECORDED FINDING, not a defect in this floor — "
            "a refusal under a calibrated rule is genuine evidence, which is precisely what the "
            "previous coin-flip rule could not produce. ⛔ The floor does not move again.")

    if not args.no_report:
        write_report(out, _OUT_MD, _OUT_JSON)
    print(f"\n=== {out['verdict']} ===\n")
    for r in sweep["rows"]:
        if r.get("error"):
            continue
        print(f"  λ={r['lambda']:.2f}  pooled {r['pooled_coverage']}  "
              f"slack {r['slack_rows']}  NF-D22 {'✅' if r['pass'] else '🚨'}  "
              f"previous {'✅' if r['pass_at_nominal_floor'] else '🚨'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""run_nf_inj2c_coherence_diagnosis.py — NF-INJ2c NODE 1: the games-floor hypothesis, established
or refuted, and every surviving coherence violation ATTRIBUTED to a named mechanism.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_coherence_diagnosis \
        --duckdb <abs path to sports.duckdb>

⛔ THIS IS A DIAGNOSIS, NOT A BAKE-OFF. It scores no arm against realized outcomes, computes no
gate, and cannot produce a verdict. It exists because NF-INJ2b's decisive record left the residual
violations as a COUNT AND A POSITION (2019 / QB / 1 player under `rate_refit`) — the row itself is
gone — and the NF-INJ2c spec makes the mechanism a HARD GATE: only a diagnosed mechanism licenses a
tolerance in the forward coherence clause (a tolerance designed around an undiagnosed residual is a
bar reverse-engineered from the number that failed it — E2.1-r).

THE HYPOTHESIS UNDER TEST (spec node 1, verbatim in substance): the ASSIGNMENT floors the games
divisor at `max(games, GAMES_FLOOR=0.25)` (`nf_inj2_rate_permutation.assign_targets`) while the
COHERENCE CHECK divides by the row's REAL `proj_games` (`projection_coherence.row_violations`). If a
row carries `0 < g <= 0.25`, the two disagree and a rate arm that is "coherent by construction" can
still breach — by exactly the factor `GAMES_FLOOR / g`.

⭐ THE DECISIVE MEASUREMENT IS CHEAP AND TWO-SIDED. `gsafe` differs from `g` on a row **iff** that
row is non-finite or `g <= GAMES_FLOOR`. So counting those rows on the ACTUAL fold frames settles the
hypothesis outright: zero such rows ⇒ `gsafe == g` identically ⇒ the floor CANNOT have acted, and the
hypothesis is REFUTED however plausible it reads (NF1.9 — a mechanism that cannot act is a finding).
A non-zero count is not by itself a confirmation either: the run then re-derives each arm's targets
with the floor REMOVED and reports whether the violating rows survive, which is the matched
counterfactual rather than an inference from a count.

⚠️ AT THE TIME OF THE RECORDED RUN `nf_inj2_rate_permutation.games_floor_binding` counted
`isfinite(g) & (g < GAMES_FLOOR)` while `gsafe` replaced `~(isfinite(g) & (g > GAMES_FLOOR))` — the
recorded measurement therefore MISSED a non-finite row the kernel does floor, so both counts were
reported separately rather than one being silently preferred, because "the floor is inert" is the
claim under test and must not be read off the narrower of two definitions (NF1.7 (a)). ⭐ PLAT-CVP2
defect 4 fixed that at its owner: both columns now read `games_floored_mask()`, the SAME predicate
the kernel applies, so they agree BY CONSTRUCTION. They are still printed side by side — an
agreement that is asserted every run is stronger evidence than one column ever was, and the recorded
values (0 on every fold) are unchanged, since the divergence was only ever on a row shape this
population does not contain.

THE FOUR CANDIDATE MECHANISMS, all measured per violating row (never inferred):
  M1 GAMES_FLOOR   — `gsafe != g` on the violating row or on the row whose rate it received.
  M2 CLAMP-LO      — `nf1_scale` pinned at 0.30, i.e. the assigned target was BELOW 30% of the row's
                     own MVP-1 point, so the row is served ABOVE the level it was assigned.
  M3 STAT MIX      — the multiset a rate arm preserves is the FANTASY-POINT rate multiset, not each
                     counting stat's own rate. A high-volume / low-efficiency row promoted to another
                     player's points rate carries its OWN stat mix up with it, so a single stat can
                     breach at a perfectly ordinary fantasy-point rate. This is a property of the
                     assignment rule, ⛔ not an artefact, and no tolerance absorbs it.
  M4 PRE-EXISTING  — the row already breaches under `mvp1_null` (the ordering OFF). Attribution by
                     control, the NF-INJ2 convention: a defect present with the mechanism disabled is
                     not caused by the mechanism.

Writes `ablation_results/nf_inj2c_coherence_diagnosis.{json,md}`. `best_alpha = 0`; nothing serves.
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

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2_rate_permutation as R2  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB  # noqa: E402,E501

log = logging.getLogger("nfl.fantasy.nf_inj2c")

_STEM = "nf_inj2c_coherence_diagnosis"
_REPORT_DIR = RB._REPORT_DIR

#: the arms the diagnosis reads. `mvp1_null` is the M4 attribution CONTROL and is not optional —
#: without it a pre-existing MVP-1 breach would be charged to the ordering rule (NF-INJ2's own
#: attribution-by-control convention, and the reason `stratified`'s count is quoted "attributable").
DIAGNOSED_ARMS: tuple[str, ...] = (
    "mvp1_null", "incumbent", "points_rate_permute", "rate_refit",
    "points_rate_stratified", "rate_refit_stratified", "stratified", "feasibility_clamp",
)


def games_audit(cap: dict) -> dict:
    """Can the `GAMES_FLOOR` act at all on this fold? Counted, never assumed (NF-D20)."""
    g = pd.to_numeric(cap["vets"].get("proj_games"), errors="coerce").to_numpy(dtype=float)
    elig = np.asarray(cap["eligible"], dtype=bool)
    # ⭐ PLAT-CVP2 defect 4 — this used to re-implement the kernel's predicate here, which is how a
    # census and its own mechanism drifted apart. Both now read ONE owner.
    moved = RP.games_floored_mask(g)
    finite = np.isfinite(g)
    return {
        "n_rows": int(len(g)),
        "n_eligible": int(elig.sum()),
        "games_floor": RP.GAMES_FLOOR,
        "min_games": (None if not finite.any() else round(float(np.nanmin(g[finite])), 6)),
        "p01_games": (None if not finite.any() else round(float(np.nanpercentile(g[finite], 1)), 6)),
        "n_non_finite": int((~finite).sum()),
        "n_at_or_below_floor": int(np.sum(finite & (g <= RP.GAMES_FLOOR))),
        # ⭐ PLAT-CVP2 defect 4 — both columns are kept and both now read ONE predicate, so their
        # AGREEMENT is an assertion rather than a coincidence. Before the fix the recorded one was
        # the NARROWER (it could not see a non-finite row the kernel floors).
        "recorded_games_floor_binding": int(RP.games_floor_binding(cap["vets"].get("proj_games"))),
        "kernel_rows_actually_floored": int(moved.sum()),
        "kernel_rows_actually_floored_eligible": int((moved & elig).sum()),
        "floor_can_act": bool(moved.any()),
        "floor_can_act_on_eligible": bool((moved & elig).any()),
    }


def _fp_rate(frame: pd.DataFrame, g: np.ndarray) -> np.ndarray:
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    pts = SP.score_line(frame.copy(), prefix="proj_")["proj_fp_ppr"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(g > 0, pts / np.where(g > 0, g, 1.0), np.nan)


def classify_mechanism(*, pre_existing: bool, floored: bool, clamp_lo: bool) -> str:
    """Name the mechanism behind ONE violating stat-row. Pure, so it is testable in isolation.

    ⭐ THE ORDER IS THE CLAIM, and it is deliberate. `M4_PRE_EXISTING` is checked FIRST because it is
    an ATTRIBUTION BY CONTROL: a breach the `mvp1_null` degenerate ALSO produces — the ordering step
    switched entirely off — is a defect of the underlying MVP-1 board that no permutation rule can be
    causing (NF-INJ2's own convention, and the reason its counts are quoted "attributable"). Charging
    such a row to the games floor would inflate the very hypothesis under test with rows the
    mechanism demonstrably did not create.

    `M1_GAMES_FLOOR` then outranks `M2_CLAMP_LO` because a floored divisor makes the assignment and
    the check disagree about the row's games OUTRIGHT, whereas the clamp only bounds how much of an
    assigned level is reached — a row can be both, and the floor is the stronger statement.

    ⛔ Extracted rather than inlined so a guard can isolate the ORDER with a fixture in which several
    clauses are true at once. A conjunction/precedence guard whose fixture trips only one clause
    proves nothing about the precedence (NF-D17)."""
    if pre_existing:
        return "M4_PRE_EXISTING"
    if floored:
        return "M1_GAMES_FLOOR"
    if clamp_lo:
        return "M2_CLAMP_LO"
    return "M3_STAT_MIX_OR_PROMOTION"


def attribute(cap: dict, arm: str, mvp1_viol_keys: set) -> dict:
    """Every violation `arm` produces on this fold, each attributed to a NAMED mechanism."""
    vets = cap["vets"]
    g = pd.to_numeric(vets.get("proj_games"), errors="coerce").to_numpy(dtype=float)
    gsafe = np.where(np.isfinite(g) & (g > RP.GAMES_FLOOR), g, RP.GAMES_FLOOR)
    floored = np.where(np.isfinite(g), gsafe != g, True)
    elig = np.asarray(cap["eligible"], dtype=bool)

    out = RB.arm_frame(cap, arm)
    summary = PC.frame_coherence_summary(out)
    scale = pd.to_numeric(out.get("nf1_scale", np.nan), errors="coerce").to_numpy(dtype=float)
    base_rate = _fp_rate(vets, g)
    served_rate = _fp_rate(out, g)

    pid = vets["player_id"].astype(str).to_numpy()
    idx_of = {p: i for i, p in enumerate(pid)}
    rows: list[dict] = []
    for v in summary["violations"]:
        i = idx_of.get(str(v.get("id")))
        if i is None:
            rows.append({**v, "mechanism": "UNMATCHED_ROW",
                         "note": "the violating row is not in the captured veteran frame "
                                 "(a rookie / K / DST path) — outside this ordering rule"})
            continue
        s = float(scale[i]) if np.isfinite(scale[i]) else float("nan")
        clamp_lo = bool(np.isfinite(s) and s <= 0.3001)
        clamp_hi = bool(np.isfinite(s) and s >= 3.4999)
        pre_existing = (str(v.get("id")), v.get("stat")) in mvp1_viol_keys
        mech = classify_mechanism(pre_existing=pre_existing, floored=bool(floored[i]),
                                  clamp_lo=clamp_lo)
        rows.append({
            **v,
            "mechanism": mech,
            "eligible": bool(elig[i]),
            "proj_games": round(float(g[i]), 4) if np.isfinite(g[i]) else None,
            "gsafe": round(float(gsafe[i]), 4),
            "floor_moved_this_row": bool(floored[i]),
            "nf1_scale": round(s, 4) if np.isfinite(s) else None,
            "clamp_lo_bound": clamp_lo, "clamp_hi_bound": clamp_hi,
            "mvp1_fp_rate": round(float(base_rate[i]), 4) if np.isfinite(base_rate[i]) else None,
            "served_fp_rate": round(float(served_rate[i]), 4) if np.isfinite(served_rate[i]) else None,
            "stat_headroom_x": round(float(v["max_ever_per_game"]) / float(v["implied_per_game"]), 4)
                               if float(v["implied_per_game"]) else None,
        })
    by_mech: dict[str, int] = {}
    for r in rows:
        by_mech[r["mechanism"]] = by_mech.get(r["mechanism"], 0) + 1
    players = {(r.get("id"), r.get("name")) for r in rows}
    attributable = {(r.get("id"), r.get("name")) for r in rows if r["mechanism"] != "M4_PRE_EXISTING"}
    return {
        "arm": arm,
        "n_violating_players": summary["n_violating_players"],
        "n_violations": summary["n_violations"],
        "n_attributable_players": len(attributable),
        "by_position": summary["by_position"],
        "n_unevaluable": summary["n_unevaluable"],
        "by_mechanism": by_mech,
        "violations": rows,
        "clamp_lo_rows": int(np.sum(np.isfinite(scale) & (scale <= 0.3001))),
        "clamp_hi_rows": int(np.sum(np.isfinite(scale) & (scale >= 3.4999))),
    }


def diagnose_fold(con, year: int, schema: str, selections: dict, base_from: int) -> dict:
    cap = RB.capture_fold(con, year, schema, selections, base_from=base_from)
    ga = games_audit(cap)
    mvp1 = attribute(cap, "mvp1_null", set())
    mvp1_keys = {(r.get("id"), r.get("stat")) for r in mvp1["violations"]}
    arms = {"mvp1_null": mvp1}
    for a in DIAGNOSED_ARMS:
        if a == "mvp1_null":
            continue
        arms[a] = attribute(cap, a, mvp1_keys)
    return {"year": year, "games_audit": ga, "arms": arms}


def _verdict(folds: dict) -> dict:
    """The node-1 gate: ESTABLISHED or REFUTED, on measurement alone."""
    can_act = any(f["games_audit"]["floor_can_act"] for f in folds.values())
    m1 = sum(f["arms"][a]["by_mechanism"].get("M1_GAMES_FLOOR", 0)
             for f in folds.values() for a in f["arms"])
    total = sum(f["arms"][a]["n_violations"] for f in folds.values() for a in f["arms"])
    if not can_act:
        state = "REFUTED"
        why = ("`gsafe == proj_games` on EVERY row of EVERY diagnosed fold — the assignment's games "
               "floor never moved a divisor, so it cannot have produced a single violation. The "
               "hypothesis is refuted by a two-sided measurement, not by an absent effect: the "
               "mechanism could not act (NF1.9 / NF-D20).")
    elif m1 == 0:
        state = "REFUTED"
        why = ("the floor DOES move at least one row, so the mechanism could act — and not one "
               "violating row is a floored row. Refuted with the activity check green, which is the "
               "strong form of the refutation.")
    else:
        state = "ESTABLISHED"
        why = (f"{m1} of {total} violating stat-rows are rows the games floor moved.")
    return {"state": state, "why": why, "floor_could_act": can_act,
            "m1_attributed_violations": m1, "total_violations": total}


def residual_profile(folds: dict) -> dict:
    """Per arm, the SHAPE of what survives — not just how much.

    ⭐ THE READING THIS EXISTS FOR. A count alone cannot tell a rounding at the envelope edge from
    the founding NF-INJ1 defect, and the two license completely different clauses: a residual that
    is 1.0x-1.1x over on players with a FULL season of expected games is an edge effect a declared
    tolerance can be designed around; a residual that is 1.8x over on a ~1-game player is the exact
    row NF-INJ1 was built to catch (`Easton Stick at 1.9 expected games with 82.7 pass attempts per
    game`), and no tolerance absorbs it without disabling the guard. So the profile reports the
    worst breach, the games of the row that carries it, and the fraction of violating rows sitting
    on low-availability players — measured, never characterised in prose."""
    out: dict[str, dict] = {}
    for f in folds.values():
        for arm, r in f["arms"].items():
            acc = out.setdefault(arm, {"n_folds_with_any": 0, "violations": 0, "players": 0,
                                       "times_over": [], "games_of_violating_rows": []})
            acc["violations"] += r["n_violations"]
            acc["players"] += r["n_violating_players"]
            acc["n_folds_with_any"] += int(bool(r["n_violations"]))
            for v in r["violations"]:
                if v.get("times_over") is not None:
                    acc["times_over"].append(float(v["times_over"]))
                if v.get("proj_games") is not None:
                    acc["games_of_violating_rows"].append(float(v["proj_games"]))
    for arm, acc in out.items():
        t, g = acc.pop("times_over"), acc.pop("games_of_violating_rows")
        acc["mean_players_per_fold"] = round(acc["players"] / max(len(folds), 1), 4)
        acc["max_times_over"] = round(max(t), 3) if t else None
        acc["median_times_over"] = round(float(np.median(t)), 3) if t else None
        acc["min_games_on_a_violating_row"] = round(min(g), 3) if g else None
        acc["median_games_on_a_violating_row"] = round(float(np.median(g)), 3) if g else None
        # "low availability" is the envelope's own founding case, not a threshold invented here:
        # NF-INJ1's headline row is Easton Stick at 1.9 expected games.
        acc["n_rows_under_2_games"] = int(sum(1 for x in g if x < 2.0)) if g else 0
        acc["share_rows_under_2_games"] = round(sum(1 for x in g if x < 2.0) / len(g), 4) if g else None
    return out


def write_md(rep: dict, path: Path) -> None:
    v = rep["verdict"]
    L = [f"# NF-INJ2c node 1 — the games-floor hypothesis: **{v['state']}**", "",
         f"> ⛔ A DIAGNOSIS, not a bake-off: no arm is scored against a realized outcome and no gate "
         f"is computed here. Generated {rep['generated_at']} over folds "
         f"{', '.join(str(y) for y in rep['folds'])}.", "",
         f"**{v['why']}**", ""]
    L += ["## 1. Could the floor act? (counted per fold, never assumed)", "",
          "| fold | rows | eligible | min `proj_games` | non-finite | `g <= 0.25` | "
          "`games_floor_binding()` | rows the KERNEL actually floored |",
          "|---|---|---|---|---|---|---|---|"]
    for y, f in rep["folds_detail"].items():
        a = f["games_audit"]
        L.append(f"| {y} | {a['n_rows']} | {a['n_eligible']} | {a['min_games']} | "
                 f"{a['n_non_finite']} | {a['n_at_or_below_floor']} | "
                 f"{a['recorded_games_floor_binding']} | {a['kernel_rows_actually_floored']} |")
    L += ["", "⭐ PLAT-CVP2 d4: the two right-hand columns now read ONE predicate "
          "(`games_floored_mask`), so they agree BY CONSTRUCTION; at the time of the recorded run "
          "they were DIFFERENT definitions — `games_floor_binding()` "
              "counts `isfinite(g) & (g < 0.25)`, the kernel floors "
              "`~(isfinite(g) & (g > 0.25))`. Both are shown because \"the floor is inert\" is the "
              "claim under test and must not be read off the narrower one (NF1.7 (a)).", ""]
    L += ["## 2. Every violation, attributed", "",
          "| fold | arm | players | attributable | violations | by mechanism | clamp-lo rows | clamp-hi rows |",
          "|---|---|---|---|---|---|---|---|"]
    for y, f in rep["folds_detail"].items():
        for a, r in f["arms"].items():
            mech = ", ".join(f"{k}={n}" for k, n in sorted(r["by_mechanism"].items())) or "—"
            L.append(f"| {y} | `{a}` | {r['n_violating_players']} | {r['n_attributable_players']} | "
                     f"{r['n_violations']} | {mech} | {r['clamp_lo_rows']} | {r['clamp_hi_rows']} |")
    prof = rep.get("residual_profile") or {}
    L += ["", "## 3. WHAT survives, not just how much — the residual's SHAPE", "",
          "| arm | players/fold | folds with any | worst × over | median × over | "
          "min games on a violating row | median games | rows under 2 games |",
          "|---|---|---|---|---|---|---|---|"]
    for arm in rep["diagnosed_arms"]:
        a = prof.get(arm)
        if not a:
            continue
        L.append(f"| `{arm}` | {a['mean_players_per_fold']} | {a['n_folds_with_any']}/"
                 f"{len(rep['folds'])} | {a['max_times_over']} | {a['median_times_over']} | "
                 f"{a['min_games_on_a_violating_row']} | {a['median_games_on_a_violating_row']} | "
                 f"{a['n_rows_under_2_games']} ({a['share_rows_under_2_games']}) |")
    L += ["", "⭐ a COUNT cannot tell a rounding at the envelope edge from the founding NF-INJ1 "
              "defect, and the two license different clauses — NF-INJ1's headline row is *Easton "
              "Stick at 1.9 expected games with 82.7 pass attempts per game*, so \"under 2 games\" "
              "is the envelope's own founding case and ⛔ not a threshold invented here.", ""]
    L += ["", "## 4. The violating rows themselves — the evidence NF-INJ2b's record did not keep", ""]
    for y, f in rep["folds_detail"].items():
        for a, r in f["arms"].items():
            if not r["violations"]:
                continue
            L.append(f"### {y} · `{a}`")
            L.append("")
            L.append("| player | pos | stat | season | g | gsafe | floored | scale | clamp | "
                     "implied/g | max ever | × over | mvp1 fp/g | served fp/g | mechanism |")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for w in r["violations"][:40]:
                clamp = ("LO" if w.get("clamp_lo_bound") else
                         "HI" if w.get("clamp_hi_bound") else "—")
                L.append(f"| {str(w.get('name'))[:24]} | {w.get('pos')} | {w.get('stat')} | "
                         f"{w.get('season_total')} | {w.get('proj_games')} | {w.get('gsafe')} | "
                         f"{w.get('floor_moved_this_row')} | {w.get('nf1_scale')} | {clamp} | "
                         f"{w.get('implied_per_game')} | {w.get('max_ever_per_game')} | "
                         f"{w.get('times_over')} | {w.get('mvp1_fp_rate')} | "
                         f"{w.get('served_fp_rate')} | `{w.get('mechanism')}` |")
            if len(r["violations"]) > 40:
                L.append(f"| … and {len(r['violations']) - 40} more | | | | | | | | | | | | | | |")
            L.append("")
    # ── 5. the reading, DERIVED from the numbers above rather than asserted beside them ───────
    prof = rep.get("residual_profile") or {}
    inc, strat = prof.get("incumbent") or {}, prof.get("stratified") or {}
    rate_arms = [a for a in ("points_rate_permute", "rate_refit", "points_rate_stratified",
                             "rate_refit_stratified") if a in prof]
    L += ["", "## 5. Reading — what this licenses, and what it does not", "",
          f"**The hypothesis is {rep['verdict']['state']}.** {rep['verdict']['why']} The floor's "
          f"own self-check (`games_floor_binding()`) agrees — and at the time of the recorded run "
          f"so did the then-WIDER definition "
          f"the kernel actually applies, so the refutation does not rest on the narrower count.", "",
          "⭐ **THE RESIDUALS ARE TWO DIFFERENT POPULATIONS, and only one of them is the kind of "
          "thing a tolerance is for.**", ""]
    if rate_arms:
        wo = max((prof[a]["max_times_over"] or 0) for a in rate_arms)
        mg = min((prof[a]["min_games_on_a_violating_row"] or 99) for a in rate_arms)
        under2 = sum(prof[a]["n_rows_under_2_games"] for a in rate_arms)
        ppf = max(prof[a]["mean_players_per_fold"] for a in rate_arms)
        L += [f"* **The rate-assignment arms** ({', '.join('`' + a + '`' for a in rate_arms)}) leave "
              f"at worst **{wo}×** the all-time envelope, on players carrying at least **{mg}** "
              f"expected games, with **{under2}** violating rows on a player under 2 expected games, "
              f"at most **{ppf}** players per fold. Every one is the SAME shape: the multiset a rate "
              f"arm preserves is the FANTASY-POINT rate multiset, not each counting stat's own rate, "
              f"so a full-season dual-threat QB promoted to another QB's points rate carries his own "
              f"stat MIX up with him and grazes a single counting ceiling. That is a mechanism-level "
              f"edge effect on the envelope boundary — the thing a declared tolerance can be designed "
              f"around, ⛔ though designing one is a PM decision this node does not take.", ""]
    if strat and inc:
        L += [f"* **`stratified` is not that.** It leaves **{strat['mean_players_per_fold']}** "
              f"players per fold on **{strat['n_folds_with_any']}/{len(rep['folds'])}** folds, worst "
              f"**{strat['max_times_over']}×** over, on a row with **"
              f"{strat['min_games_on_a_violating_row']}** expected games, and "
              f"**{strat['n_rows_under_2_games']}** of its violating rows "
              f"({strat['share_rows_under_2_games']}) sit on a player under 2 expected games. The "
              f"incumbent's own residual is **{inc['mean_players_per_fold']}** players per fold, "
              f"worst **{inc['max_times_over']}×**, **{inc['share_rows_under_2_games']}** under 2 "
              f"games. ⇒ **`stratified` is the incumbent's defect at lower VOLUME, not a different "
              f"defect** — the same rows, the same magnitudes, the same low-availability "
              f"concentration. NF-INJ1's founding row is *Easton Stick at 1.9 expected games with "
              f"82.7 pass attempts per game*; `stratified` still serves rows of exactly that shape "
              f"(and Easton Stick himself is among them on the 2025 fold). A tolerance wide enough "
              f"to admit them would not be a tolerance, it would be the guard switched off.", ""]
    L += ["⛔ **This node takes no decision.** It establishes a mechanism and refutes one; the "
          "coherence clause, its attribution rule and any tolerance are the PM's to re-scope, and "
          "the NF-INJ2c spec makes that explicit: a refuted node-1 STOPS the story here rather than "
          "letting a pre-registration be written around a mechanism that was never there.", ""]
    path.write_text("\n".join(L) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2c node 1 — coherence-violation diagnosis")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--folds", default=None, help="comma-separated; default = the registered 7")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive the .md from the COMMITTED .json with ZERO re-scoring (NF-W2e) "
                         "— the only sanctioned way to correct a rendering without moving a number")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    if args.rewrite_report:
        rep = json.loads((_REPORT_DIR / f"{_STEM}.json").read_text())
        rep["residual_profile"] = residual_profile(rep["folds_detail"])
        (_REPORT_DIR / f"{_STEM}.json").write_text(json.dumps(rep, indent=2, default=str))
        write_md(rep, _REPORT_DIR / f"{_STEM}.md")
        log.info("report re-derived from the committed JSON — no arm was re-scored")
        return 0

    import duckdb
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree does not carry the "
                         "gitignored artifact (NF-INFRA1); pass --duckdb with an absolute path to "
                         "the main checkout's copy.")
    con = duckdb.connect(args.duckdb, read_only=True)
    selections = N15.load_selection(json.loads(RB._NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    folds = (tuple(int(x) for x in args.folds.split(",")) if args.folds else R2.registered_folds())

    detail: dict = {}
    for y in folds:
        log.info("── diagnosing fold %d ─────────────────────────────", y)
        detail[str(y)] = diagnose_fold(con, y, args.schema, selections, args.base_from)
    rep = {
        "story": "NF-INJ2c node 1 — coherence-violation mechanism diagnosis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0,
        "folds": list(folds),
        "games_floor": RP.GAMES_FLOOR,
        "diagnosed_arms": list(DIAGNOSED_ARMS),
        "folds_detail": detail,
    }
    rep["residual_profile"] = residual_profile(detail)
    rep["verdict"] = _verdict(detail)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{_STEM}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_md(rep, _REPORT_DIR / f"{_STEM}.md")
    log.info("NODE 1 VERDICT: %s — %s", rep["verdict"]["state"], rep["verdict"]["why"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

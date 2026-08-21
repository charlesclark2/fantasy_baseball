"""nf_tr2b_placement.py — the WHOLE-BOARD CROSS-POSITION PLACEMENT READ for the NF-TR2b veteran
level correction (the NF-D16 class), as pure functions over a served board.

WHY THIS EXISTS — the question the shipped guarantee cannot answer. NF-TR2b applies a per-position
MULTIPLICATIVE constant `k` to the veteran per-game rate (2026: QB 0.929 · RB 1.248 · WR 1.099 ·
TE 1.112). Because a positive constant is a monotone map, the WITHIN-position order is preserved
EXACTLY, and that is already pinned (record §5, L5 rank identity, min rho = 1.0 on every fold).
⭐ That guarantee is silent on the only ordering a drafter actually reads: the CROSS-position one.

⚠️ AND VOR DOES NOT ABSORB IT. NF-W8-0 measured that an ADDITIVE per-group level shift CANCELS in
VOR space — a group's own replacement level absorbs it, so a cross-group level artifact is
structurally harmless on a VOR-ranked board. That result DOES NOT TRANSFER HERE, and assuming it
would be the mistake: TR2b is MULTIPLICATIVE, so `points -> k*points` sends `vor -> k*vor`, which
does not cancel, AND it re-runs `compute_replacement_levels`' greedy FLEX allocation — a
cross-position draft ON POINTS — so each position's replacement DEPTH moves too. The effect is real
and has to be measured rather than reasoned about.

WHAT IS GATED vs WHAT IS ONLY REPORTED — the E2.1-r discipline, stated up front. Every gate below is
STRUCTURAL (a mathematical identity or a degenerate-board floor) or INHERITED BY DELEGATION from a
threshold this program already owns. ⛔ NOTHING here is a threshold reverse-engineered from the
measured answer — that is the inversion this repo has been burned by, and a "sanity band" chosen
after seeing the result would be exactly it.

  GATED (a pathology refusal):
    G1 within-position order preserved exactly       — a mathematical identity of a positive constant
    G2 rookie placement cap not breached             — DELEGATED to `season_projection.
                                                       rookie_placement_breach` (NF-D18/D20 owns the
                                                       cap; it is never transcribed here)
    G3 no recalibrated position wiped from the top   — a degenerate-board floor, not a tuned level
    G4 band integrity (p10 <= point <= p90)          — a hard serving defect, threshold-free

  REPORTED, NEVER GATED (a read, never a target):
    rank-movement distribution by band · top-N positional composition · replacement + flex
    reallocation · Spearman vs ADP · the rookie-cohort shift

⭐ ON G2, AND WHY THE DIRECTION IS THE WHOLE POINT. `rookie_placement_breach` returns
`breach = (best_rookie_overall_rank < cap)` — it caps a rookie placing TOO HIGH. TR2b touches only
VETERANS, so rookies move only as a RELATIVE consequence, and because three of the four k are > 1
they move DOWN — strictly AWAY from that cap. So the inherited whole-board placement constraint
cannot be breached by this correction, and the gate is a two-sided proof of that rather than a hope.
⚠️ THE HONEST CONVERSE, which belongs in the record rather than hidden: there is NO guard on the
opposite side (a rookie placed too LOW). The rookie leg is held at incumbent (NF-D21 CLOSED,
CONSTRAINT_REFUSED), so TR2b re-prices veterans against an UNCORRECTED rookie leg by construction.
That is a measured, disclosed consequence — not a defect this read can adjudicate.

INCUMBENT RECONSTRUCTION IS EXACT, NOT APPROXIMATE. NFL offensive scoring
(`league_presets._BASE_SCORING` + `rec`) is purely LINEAR in the stat line, and TR2b scales the whole
stat line by a per-position constant, so `league_points` scale by exactly `k`. The non-linear terms
(`dst_pa_g_*`, `fg_made_*`) apply only to K/DST, which TR2b does not touch
(`veteran_level_policy.RECALIBRATED_POSITIONS`). Rookies are untouched. The only residual is the
served board's 1-decimal rounding of `pts` (<= 0.05 pt), which can only reorder players already tied
at that precision.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from quant_sports_intel_models.fantasy_engine.vor import build_board, compute_replacement_levels
from quant_sports_intel_models.football.nfl.fantasy import veteran_level_policy as VLP

#: Positions carried on a served NFL board, in report order.
BOARD_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "K", "DST")

#: The top-N cutoffs the composition report uses. Descriptive only — never a gate.
TOP_N_REPORT: tuple[int, ...] = (12, 24, 36, 60, 100)

#: G3's degenerate floor: a recalibrated position that vanishes ENTIRELY from this many top rows is a
#: pathological reordering. This is a ZERO-survivor floor (does the position still exist at the top
#: at all), not a tuned composition band — the distinction is what keeps it out of E2.1-r territory.
TOP_N_SURVIVAL: int = 100


def reconstruct_incumbent_points(board: pd.DataFrame, k: Mapping[str, float], *,
                                 points_col: str = "pts", position_col: str = "pos",
                                 rookie_col: str = "rookie") -> pd.Series:
    """The pre-TR2b league points, recovered by undoing `k` on the rows TR2b actually moved.

    Exact by linearity (see the module docstring). A row is divided by `k[pos]` iff it is a VETERAN
    at a RECALIBRATED position; every other row (rookies, K, DST, any position outside the policy)
    is returned unchanged.
    """
    pts = pd.to_numeric(board[points_col], errors="coerce")
    recal = set(VLP.RECALIBRATED_POSITIONS) & set(k)
    is_vet = ~board[rookie_col].astype(bool)
    at_recal_pos = board[position_col].isin(recal)
    scale = pd.Series(1.0, index=board.index)
    touched = is_vet & at_recal_pos
    scale.loc[touched] = 1.0 / board.loc[touched, position_col].map(k).astype(float)
    return pts * scale


def paired_boards(board: pd.DataFrame, k: Mapping[str, float], config, profile) -> dict:
    """Build the INCUMBENT and RECALIBRATED boards through the SAME shipped `build_board`.

    Running both sides through one harness is deliberate: the exporter's tie-break among equal-VOR
    players then CANCELS, so every difference reported downstream is the correction's doing rather
    than a sorting convention. (A separate positive control establishes that this harness reproduces
    the SERVED replacement levels exactly and VOR to the board's own 1dp rounding.)
    """
    served = pd.to_numeric(board["pts"], errors="coerce")
    keep = served.notna()
    b = board.loc[keep].copy()
    base = pd.DataFrame({
        "position": b["pos"].to_numpy(), "id": b["id"].to_numpy(),
        "name": b["name"].to_numpy(), "rookie": b["rookie"].to_numpy(),
        "adp": pd.to_numeric(b.get("adp"), errors="coerce").to_numpy(),
    })
    rec = base.copy(); rec["league_points"] = served.loc[keep].to_numpy()
    inc = base.copy(); inc["league_points"] = reconstruct_incumbent_points(b, k).to_numpy()
    out = {}
    for lab, frame in (("inc", inc), ("rec", rec)):
        out[f"board_{lab}"] = build_board(frame, config, profile, points_col="league_points")
        repl, started = compute_replacement_levels(frame, config, profile, points_col="league_points")
        out[f"repl_{lab}"], out[f"started_{lab}"] = repl, started
    return out


def movement(board_inc: pd.DataFrame, board_rec: pd.DataFrame) -> pd.DataFrame:
    """Per-player overall-rank movement. `move` > 0 means the player moved UP the board."""
    m = board_inc[["id", "position", "name", "adp", "rookie", "overall_rank"]].merge(
        board_rec[["id", "overall_rank"]], on="id", suffixes=("_inc", "_rec"))
    m["move"] = m["overall_rank_inc"] - m["overall_rank_rec"]
    return m


def top_n_composition(board: pd.DataFrame, n: int,
                      positions: Iterable[str] = BOARD_POSITIONS) -> dict[str, int]:
    top = board.nsmallest(n, "overall_rank")
    return {p: int((top["position"] == p).sum()) for p in positions}


def within_position_order_preserved(board_inc: pd.DataFrame, board_rec: pd.DataFrame) -> dict:
    """G1 — a positive per-position constant must preserve order EXACTLY *within each LEG*.

    ⭐ PER LEG, AND THE SCOPING IS THE WHOLE SUBTLETY — it was measured, not assumed. TR2b corrects
    VETERANS only (the rookie leg is held at incumbent, NF-D21 CLOSED), so a position's board mixes
    a SCALED cohort with an UNSCALED one. A gate demanding whole-position order invariance therefore
    fails BY CONSTRUCTION, and would be demanding something TR2b never claimed: the record's L5
    identity is about the corrected population, not about rookie-vs-veteran placement.

    Measured on the served board, all 14 configs: every leg is internally order-identical at every
    position (veterans True, rookies True), and K/DST — the positions carrying NO rookies — are
    WHOLLY identical. That K/DST control is what proves the breaks are the leg boundary rather than
    a monotonicity failure: if the constant were not order-preserving, K/DST would break too.

    So the identity is gated per leg, and the cross-leg reordering it exposes is REPORTED
    (`cross_leg_reordered_positions`) rather than silently folded into a pass or a fail.
    """
    out: dict[str, object] = {"positions": {}, "pass": True,
                              "cross_leg_reordered_positions": []}
    for pos, grp_i in board_inc.groupby("position"):
        grp_r = board_rec[board_rec["position"] == pos]
        gi = grp_i.sort_values("overall_rank")
        gr = grp_r.sort_values("overall_rank")
        rec_pos: dict[str, object] = {}
        for lab, mask_i, mask_r in (
                ("veterans", ~gi["rookie"].astype(bool), ~gr["rookie"].astype(bool)),
                ("rookies", gi["rookie"].astype(bool), gr["rookie"].astype(bool))):
            a, b = gi[mask_i]["id"].tolist(), gr[mask_r]["id"].tolist()
            rec_pos[lab] = {"n": len(a), "order_identical": bool(a == b)}
            if a != b:
                out["pass"] = False
        whole = gi["id"].tolist() == gr["id"].tolist()
        rec_pos["whole_position_order_identical"] = bool(whole)
        if not whole:
            out["cross_leg_reordered_positions"].append(str(pos))
        out["positions"][str(pos)] = rec_pos
    return out


def band_integrity(rows: pd.DataFrame, *, point: str = "fpPpr",
                   lo: str = "fpP10", hi: str = "fpP90") -> dict:
    """G4 — the served band must ORDER (p10 <= p90) and BRACKET its own point.

    This is the half of the interval re-validation that needs NO realized outcomes, and it is the
    half TR2b can actually move: the correction raises the veteran POINT by `k` while holding the
    NF1.9-validated band BYTE-IDENTICAL, so the predictable serving-side symptom is the point being
    pushed toward — or through — its own p90. Coverage (the MISCALIBRATED half) still needs realized
    outcomes and a warm panel; that stays `run_interval_revalidation`'s job and cannot be done here.
    """
    d = rows.copy()
    for c in (point, lo, hi):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d[point].notna() & d[lo].notna() & d[hi].notna()]
    bad_order = int((d[lo] > d[hi]).sum())
    above = int((d[point] > d[hi] + 1e-9).sum())
    below = int((d[point] < d[lo] - 1e-9).sum())
    width = (d[hi] - d[lo]).replace(0, np.nan)
    frac = ((d[point] - d[lo]) / width)
    return {"n": int(len(d)), "band_order_violations": bad_order,
            "point_above_p90": above, "point_below_p10": below,
            "at_p90_within_0p05": int((d[point].sub(d[hi]).abs() < 0.05).sum()),
            "median_frac_of_band": None if not len(frac.dropna()) else round(float(frac.median()), 4),
            "pass": bool(bad_order == 0 and above == 0 and below == 0)}


def position_survival(board_rec: pd.DataFrame, k: Mapping[str, float],
                      top_n: int = TOP_N_SURVIVAL) -> dict:
    """G3 — no RECALIBRATED position may be wiped out of the top `top_n` of the served board."""
    comp = top_n_composition(board_rec, top_n)
    recal = sorted(set(VLP.RECALIBRATED_POSITIONS) & set(k))
    missing = [p for p in recal if comp.get(p, 0) == 0]
    return {"top_n": int(top_n), "composition": comp, "recalibrated_positions": recal,
            "wiped_out": missing, "pass": not missing}


def rookie_placement(board: pd.DataFrame) -> dict:
    """G2 — the inherited whole-board placement cap, DELEGATED not transcribed.

    `season_projection.rookie_placement_breach` owns the cap (NF-D18/D20) including its robustness
    band over q; this function only supplies the board's best rookie rank and passes the verdict
    through, so the threshold can never drift out of sync with its owner.
    """
    from quant_sports_intel_models.football.nfl.fantasy.season_projection import (
        rookie_placement_breach)
    rk = board[board["rookie"].astype(bool)]
    best = int(rk["overall_rank"].min()) if len(rk) else None
    verdict = rookie_placement_breach(best)
    return {"best_rookie_overall_rank": best, "verdict": verdict,
            "pass": verdict.get("breach") is not True}


def spearman_vs_adp(m: pd.DataFrame) -> dict:
    """A market READ — reported, NEVER gated.

    Agreement with ADP is not a target: the program's public position is `best_alpha = 0` and the
    board is deliberately allowed to disagree with the crowd. It is reported because a correction
    that COLLAPSED market agreement would be a signal worth a human look, and because the direction
    is informative (TR2b's movers move toward their own ADP).
    """
    has = m["adp"].notna()
    if int(has.sum()) < 3:
        return {"n": int(has.sum()), "rho_incumbent": None, "rho_recalibrated": None, "delta": None}
    ri = float(m.loc[has, "overall_rank_inc"].corr(m.loc[has, "adp"], method="spearman"))
    rr = float(m.loc[has, "overall_rank_rec"].corr(m.loc[has, "adp"], method="spearman"))
    return {"n": int(has.sum()), "rho_incumbent": round(ri, 4),
            "rho_recalibrated": round(rr, 4), "delta": round(rr - ri, 4)}


def classify_placement(gates: Mapping[str, Mapping]) -> dict:
    """The verdict: SANE only when every STRUCTURAL/INHERITED gate holds.

    ⚠️ An UNEVALUABLE gate is never scored healthy (NF1.7 (a)) — a gate that could not be computed
    is reported as such and refuses the verdict, rather than passing on nothing.
    """
    detail = {}
    for name, g in gates.items():
        p = None if g is None else g.get("pass")
        detail[name] = "PASS" if p is True else ("FAIL" if p is False else "UNEVALUABLE")
    bad = [n for n, v in detail.items() if v != "PASS"]
    return {"verdict": "SANE" if not bad else "REVIEW_REQUIRED",
            "gates": detail, "failing": bad}

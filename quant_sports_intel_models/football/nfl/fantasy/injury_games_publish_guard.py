"""injury_games_publish_guard.py — 🔒 the D6 PUBLISH-TIME STAMP GUARD (NF-INJ3b-SHIP).

THE FAILURE IT KILLS, NAMED: **a served build that forgot its covariate feed, quietly shipping the
INCUMBENT caps under the fitted arm's `model_version`.** That is not a hypothesis — it is the
residual risk `injury_games_serving` created on purpose. NF-INJ3b-M discovered by RUNNING the build
that `project_veterans` is also called by NF1.5's internal research-frame assembly, which has no
covariate feed, so forcing the policy on process-wide killed the whole build. The cure was an
explicit `feed_supplied=False` on those call sites — and the cost of that cure is that a REAL
serving build which loses its feed now takes the same quiet incumbent path, while the board-wide
policy stamp goes on claiming the fitted arm. `injury_games_serving`'s own comment says where the
answer belongs: *"guard the ARTIFACT at publish (does the board carry the fitted stamp?)"*. Here.

⭐ IT ASKS BOTH HALVES, BECAUSE EITHER ALONE IS SATISFIED BY THE DEFECT. The stamp alone is
identical on a good flip and on a fed-less build. The games column alone is identical too — a
flagged veteran is capped either way, just at a different number. Only the stamp CHECKED AGAINST
what the rows actually did separates them.

⭐ IT READS THE ARTIFACT, NEVER THE POLICY MODULE'S WORD FOR ITSELF. `injury_games_policy` supplies
the NAMES (which version string means "the fitted arm", which columns carry the evidence); every
VALUE comes off the built board. A guard that asked the policy whether serving was enabled would
keep reading correct while the served board drifted — the NF-C0e "declaration outruns its
production" class, inside the guard written to catch it.

⭐ AND IT COUNTS THE ROWS THE MECHANISM COULD ACT ON BEFORE CREDITING A PASS. A board with no
certified (RES/PUP veteran) rows at all — an off-season board — reports `NO_CERTIFIED_ROWS`, which
is a PASS but is NOT the same fact as a clean flip and is never rendered as one (NF-D20: an
inactive gate is uninformative, never a pass).

⛔ MATERIAL TOLERANCE, NEVER BITWISE (NF-INJ3c §6, card QkpAHBYa). Same-commit board rebuilds differ
in the rookie band at 0–21 material cells, so no comparison in this repo may be exact. This one is
scoped to the certified veteran population and compares at `MATERIAL_ATOL`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

#: the board column carrying which cap model this build was CONFIGURED to serve.
STAMP_COL = "injury_games_model_version"
#: the two PER-ROW evidence columns (owned by `season_projection`, read here so they cannot drift).
SERVED_COL, INCUMBENT_COL = SP.INJURY_GAMES_EVIDENCE_COLS

#: ⛔ never `==`. The standing no-bitwise-board-comparison rule; a cap that moved a row by less than
#: this did not move it in any sense a drafter or an operator can see.
MATERIAL_ATOL = 1e-9

#: verdicts that permit a publish. Everything else refuses.
PASSING = ("FLIPPED_AND_MOVED", "INCUMBENT_CLEAN", "NO_CERTIFIED_ROWS", "PRE_STORY_BOARD")


def _one(board: pd.DataFrame, col: str):
    """The board's single value for a stamp column, or None. Two distinct values is a HARD ERROR —
    it means two builds were concatenated, and stamping one of them would publish a claim true of
    half a board (`rookie_policy_stamp`'s rule, restated because this guard must not be softer)."""
    if col not in board.columns:
        return None
    vals = pd.Series(board[col]).dropna().unique()
    if len(vals) > 1:
        raise ValueError(
            f"injury_games_publish_guard: the board carries {len(vals)} distinct values for {col} "
            f"({list(vals)[:4]}) — two builds appear to have been concatenated, and neither the "
            f"stamp nor the row evidence describes the whole artifact.")
    return (vals[0] if len(vals) else None)


def evaluate(board: pd.DataFrame) -> dict:
    """`{verdict, passed, ...evidence}` for one built board. Never raises on a defect — it REPORTS,
    and the caller refuses; a guard that raised its own findings could not be tested two-sided."""
    stamp = _one(board, STAMP_COL)
    stamp = None if stamp is None else str(stamp)
    claims_fitted = (stamp == POLICY.MODEL_VERSION)

    have_rows = SERVED_COL in board.columns and INCUMBENT_COL in board.columns
    if not have_rows:
        # A board built before this story carries neither the stamp nor the evidence: an honest
        # absence. But a board that CLAIMS the fitted arm and carries no evidence is unverifiable,
        # and an unverifiable artifact is a failure, never a pass (NF1.7 (a)).
        verdict = "UNVERIFIABLE" if claims_fitted else "PRE_STORY_BOARD"
        return {"verdict": verdict, "passed": verdict in PASSING, "stamp": stamp,
                "claims_fitted": claims_fitted, "n_certified": None, "n_fitted": None,
                "n_moved": None, "material_atol": MATERIAL_ATOL,
                "detail": (f"the board carries {STAMP_COL}={stamp!r} but not "
                           f"{SERVED_COL}/{INCUMBENT_COL}, so what the cap actually did to each row "
                           f"cannot be read back off the artifact"
                           if claims_fitted else
                           "the board predates NF-INJ3b-SHIP (no injury-games evidence columns) and "
                           "claims no fitted cap model")}

    served = pd.to_numeric(board[SERVED_COL], errors="coerce").to_numpy(dtype=float)
    incumbent = pd.to_numeric(board[INCUMBENT_COL], errors="coerce").to_numpy(dtype=float)
    n_certified = int(np.isfinite(incumbent).sum())
    fit_ok = np.isfinite(served)
    n_fitted = int(fit_ok.sum())
    both = fit_ok & np.isfinite(incumbent)
    moved = both & (np.abs(served - incumbent) > MATERIAL_ATOL)
    n_moved = int(moved.sum())
    max_abs = float(np.abs(served[both] - incumbent[both]).max()) if both.any() else 0.0

    if n_certified == 0 and n_fitted == 0:
        verdict, detail = "NO_CERTIFIED_ROWS", (
            "this board carries NO certified (RES/PUP veteran) rows, so the injury-games cap could "
            "not act on it at all. That is a PASS because there is nothing to publish wrongly — it "
            "is NOT evidence that the flip works, and must not be read as one (NF-D20).")
    elif claims_fitted and n_fitted == 0:
        verdict, detail = "STAMPED_BUT_UNSERVED", (
            f"the board stamps the FITTED cap model ({stamp}) but the fitted arm produced NO row: "
            f"{n_certified} certified row(s) were available and every one kept the incumbent cap. "
            f"This is the signature of a build that lost its covariate feed (`feed_supplied=False`, "
            f"or a feed the leakage gate refused) while the policy stayed ON.")
    elif claims_fitted and n_moved == 0:
        verdict, detail = "STAMPED_BUT_UNMOVED", (
            f"the board stamps the FITTED cap model ({stamp}) and the fitted arm produced "
            f"{n_fitted} row(s), but NOT ONE differs from the incumbent cap by more than "
            f"{MATERIAL_ATOL:g} (largest move {max_abs:.3g}). A flip that changes nothing is a "
            f"claim the artifact does not support.")
    elif claims_fitted:
        verdict, detail = "FLIPPED_AND_MOVED", (
            f"{n_moved} of {n_fitted} fitted row(s) differ materially from the incumbent cap "
            f"(largest move {max_abs:.3g} games) under the fitted stamp {stamp}.")
    elif n_fitted > 0 or n_moved > 0:
        verdict, detail = "MOVED_WITHOUT_STAMP", (
            f"the fitted arm produced {n_fitted} row(s) ({n_moved} materially different from the "
            f"incumbent cap) but the board stamps {stamp!r}, not the fitted "
            f"{POLICY.MODEL_VERSION!r}. The served numbers and the artifact's own account of where "
            f"they came from disagree.")
    else:
        verdict, detail = "INCUMBENT_CLEAN", (
            f"the board stamps {stamp!r} and no row was produced by the fitted arm — the incumbent "
            f"caps, consistently ({n_certified} certified row(s) all on the shipped constants).")

    return {"verdict": verdict, "passed": verdict in PASSING, "stamp": stamp,
            "claims_fitted": claims_fitted, "fitted_model_version": POLICY.MODEL_VERSION,
            "incumbent_model_version": POLICY.INCUMBENT_MODEL_VERSION,
            "n_certified": n_certified, "n_fitted": n_fitted, "n_moved": n_moved,
            "max_abs_move": max_abs, "material_atol": MATERIAL_ATOL, "detail": detail}


def refusal_message(result: dict, season: int) -> str:
    """The operator-facing refusal. Names the diagnosis and the remedy, never just the verdict."""
    return (
        f"🔴 NF-INJ3b-SHIP PUBLISH REFUSED — the staged {season} board's injury-games stamp and its "
        f"own rows disagree.\n\n"
        f"  verdict: {result['verdict']}\n"
        f"  {result['detail']}\n\n"
        f"  stamp={result['stamp']!r}  certified_rows={result['n_certified']}  "
        f"fitted_rows={result['n_fitted']}  materially_moved={result['n_moved']}\n\n"
        "NOTHING WAS PUBLISHED. The board currently serving from S3 is untouched, which is the "
        "right outcome: a board whose provenance stamp is wrong is worse than a stale one, because "
        "every later reconciliation (the NF-G0 registry, the methodology panel, the next "
        "investigation) trusts that stamp.\n\n"
        "MOST LIKELY CAUSE: the build served the INCUMBENT caps while `injury_games_policy."
        "SERVING_ENABLED` was True — i.e. it reached `injury_games_serving.served_injury_games` "
        "with no covariate feed. Check the build log for 'NF-INJ3b: injury covariate feed BUILT' "
        "(present on a good build) and for 'supplied no covariate feed' (present on the defect), "
        "then rebuild.")

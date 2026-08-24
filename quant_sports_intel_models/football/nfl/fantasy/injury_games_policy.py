"""injury_games_policy.py — the ONE place the served INJURY-GAMES model is decided (NF-INJ3b), the
sibling of `veteran_level_policy` (veteran level) and `rookie_publish_policy` (rookie leg).

WHAT IS SERVED (when `SERVING_ENABLED`): NF-INJ3b's certified `hurdle_transfer` arm — an explicit
availability HURDLE, `P(plays ≥ 1) × E[games | plays ≥ 1]`, fitted in-fold over
`onset_carryover, weeks_since_last_game, prior_games, log1p_prior_fp, is_qb` plus status dummies,
replacing the hardcoded `season_projection._INJURY_STATUS_GAMES_CAP` blend for a flagged veteran.
The fitted object is PERSISTED as a coefficient table and loaded at build time — ⛔ never re-fitted
on a serving path (MH2.1: serve the object that was VALIDATED, never a re-derivation).

WHY THIS FORM — the record: `ablation_results/nf_inj3b_injury_games.md` (NF-INJ3b: CLEARS 9/9 on the
registered primary; +0.2845 CRPS over the incumbent, 6/7 folds, PBO 0.0000, DSR 0.9715 under a `V`
naming DSR-CONV **and** MH2.1 (a), BH p 0.0501 as a named single hypothesis, both degenerates lose,
every arm respects its own-form peeking oracle with the matched-n control) and its parent
`nf_inj3_injury_games.md` (NF-INJ3, `POWER_LIMITED` — the same numbers under a registration that
left `V`'s membership and the BH family unstated).

⛔ **`fitted_status` IS REFUSED AND THE REFUSAL LIVES HERE SO IT CANNOT BE RESURRECTED** (PM ruling
D2, 2026-08-23). It is the cheap-to-serve arm — the incumbent's own functional form with the level
and blend re-fitted, carrying 77% of the total lift — and on NF-INJ3b's numbers it wins **4 of 7**
folds at **p = 0.1265**, failing both the fold-consistency clause and BH. Choosing it *now*, because
it is cheaper to serve, is picking an arm after seeing the scores. A future story may register it as
its OWN primary; nothing here may serve it.

⭐ **PM BOUNDARY, recorded verbatim (D2):** *the certified population is RES/PUP; SUS and NFI rows
RETAIN the incumbent constants — zero live rows, exploratory channels — until a live row exists and
a registered read covers them.* `CERTIFIED_STATUSES` / `INCUMBENT_STATUSES` below ARE that boundary,
and `injury_games_serving.served_injury_games` reads them rather than restating it.

⭐ THE FLIP IS ONE READ OF `serving_enabled()`. `SERVING_ENABLED = False` ⇒ the board is
BYTE-IDENTICAL to the incumbent cap path, and the rollback is the same code path.
`assert_coherent()` runs at import and refuses a flip that contradicts the recorded disposition.
"""
from __future__ import annotations

#: The story that selected the served arm, and its recorded parent null.
SOURCE_MODEL = "NF-INJ3b"
PREDECESSOR = "NF-INJ3"
DECISION_STORY = "NF-INJ3b"
MODEL_VERSION = "nfl_fantasy_nf_inj3b_injury_games_v1"
#: what the board stamps when serving is OFF (the incumbent hardcoded caps).
INCUMBENT_MODEL_VERSION = "nfl_fantasy_injury_cap_incumbent_v1"

#: The recorded dispositions of each story's pre-registered gate.
DISPOSITION = "SHIP"                            # NF-INJ3b: 9/9 registered gates
PREDECESSOR_DISPOSITION = "POWER_LIMITED"       # NF-INJ3: same numbers, unstated V + BH family

#: The served form + arm, READ from the pre-registration so they cannot drift.
FORM = "hurdle"
ARM = "hurdle_transfer"
SELECTION_STATUS = "STATISTICALLY_SELECTED"
STATISTICALLY_SELECTED = True

#: ⭐ THE PM BOUNDARY (D2), as data. A status NOT in `CERTIFIED_STATUSES` keeps the incumbent
#: constant even when serving is ON — the study certified RES/PUP and nothing else.
CERTIFIED_STATUSES: tuple[str, ...] = ("RES", "PUP")
INCUMBENT_STATUSES: tuple[str, ...] = ("SUS", "NFI")
PM_BOUNDARY = (
    "the certified population is RES/PUP; SUS and NFI rows RETAIN the incumbent constants — zero "
    "live rows, exploratory channels — until a live row exists and a registered read covers them")

#: ⛔ Arms this study measured and REFUSED to serve, with the reason, so a later session cannot
#: resurrect one by re-reading the leaderboard (PM ruling D2).
REFUSED_ARMS: dict[str, str] = {
    "fitted_status": "wins 4 of 7 folds at p = 0.1265 — fails the fold-consistency clause AND BH on "
                     "NF-INJ3b's own numbers. It carries 77% of the lift and is far cheaper to "
                     "serve, which is exactly why choosing it now would be picking an arm after "
                     "seeing the scores (PM ruling D2). A future story may register it as its own "
                     "primary; nothing here may serve it.",
}

#: 🔒 THE FLIP. DEPLOY-HELD: NF-INJ3b cleared its gates, but its §5 ship path is INCOMPLETE — the
#: served-POINT impact is what NF-INJ3b-M measures, and the ship/no-ship is the OPERATOR's decision
#: taken WITH that measurement. Merging this file does not serve anything.
SERVING_ENABLED: bool = False

#: the persisted coefficient table (committed, NOT gitignored — a serving artifact under a
#: gitignored path is the NF-INFRA1 deploy-ephemeral time bomb).
ARTIFACT_FILENAME = "nfl_fantasy_injury_games_hurdle_v1.json"


def serving_enabled() -> bool:
    """The single read. False ⇒ the incumbent cap path, byte-for-byte."""
    return bool(SERVING_ENABLED)


def is_certified(status: str) -> bool:
    """PM boundary D2 — does the certified arm apply to this status at all?"""
    return str(status) in CERTIFIED_STATUSES


def stamp() -> dict:
    """The board-wide stamp columns, mirroring `veteran_level_policy.stamp()`."""
    on = serving_enabled()
    return {
        "injury_games_status": ("fitted_hurdle" if on else "incumbent"),
        "injury_games_form": (FORM if on else ""),
        "injury_games_arm": (ARM if on else ""),
        "injury_games_source_model": (SOURCE_MODEL if on else ""),
        "injury_games_decision_story": (DECISION_STORY if on else ""),
        "injury_games_certified_statuses": (",".join(CERTIFIED_STATUSES) if on else ""),
        "injury_games_statistically_selected": (bool(STATISTICALLY_SELECTED) if on else False),
        "injury_games_model_version": (MODEL_VERSION if on else INCUMBENT_MODEL_VERSION),
    }


def assert_coherent() -> None:
    """Refuse a flip that contradicts the recorded disposition (the `veteran_level_policy` shape).

    ⭐ A bare flag flip is exactly how a refused study gets served by accident, so the contradiction
    is refused AT IMPORT rather than caught in review."""
    if SERVING_ENABLED and DISPOSITION != "SHIP":
        raise RuntimeError(
            f"injury_games_policy: SERVING_ENABLED is True but {SOURCE_MODEL}'s recorded "
            f"disposition is {DISPOSITION!r}. A flip that contradicts the record is refused "
            f"(E2.1-r). Record a NEW disposition first.")
    if set(CERTIFIED_STATUSES) & set(INCUMBENT_STATUSES):
        raise RuntimeError(
            "injury_games_policy: a status cannot be both certified and incumbent-held — the PM "
            "boundary (D2) is not expressible as written.")
    if ARM in REFUSED_ARMS:
        raise RuntimeError(
            f"injury_games_policy: the served ARM {ARM!r} is in REFUSED_ARMS — a refused arm must "
            f"never become the served one without a fresh registration (PM ruling D2).")


assert_coherent()

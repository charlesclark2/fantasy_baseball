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

🔒 **SERVING IS ON** as of NF-INJ3b-SHIP (operator ruling D5=A, 2026-08-24) — see `SERVING_ENABLED`
for the decision and its measured basis. Two things that flip does NOT do, because both have been
misread before: it does not PUBLISH (a built board reaches users only through
`export_draft_board_json --publish`, an operator step), and it does not make the arm reachable from
any population other than veteran RES/PUP.
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

#: ⚠️⚠️ THE SECOND POPULATION BOUNDARY, AND IT IS A READING RATHER THAN A RULING — FLAGGED FOR THE
#: PM (NF-INJ3b-SHIP). NF-INJ3b's preregistration §3 excluded RETURNERS (`seasons_missed >= 1`)
#: from the scored population, and gave the reason: NF-D11's absence prior runs immediately after
#: this cap, so a returner's served games compose TWO caps and this arm's contribution is not
#: separably recoverable. The arm was therefore never evaluated on them.
#:
#: Operator ruling D5=A authorises "veteran RES/PUP"; it does not mention returners either way, and
#: the live 2026 board carries FOUR flagged veterans who are returners. Two readings were available
#: and neither is free:
#:   • serve them the fitted arm — applies a certified arm to a population the study explicitly
#:     removed from its own evaluation, i.e. uncertified there;
#:   • hold them on the incumbent — the conservative reading, identical in shape to the D2
#:     treatment of SUS/NFI ("until a live row exists and a registered read covers them"), and it
#:     makes the served population EXACTLY the population NF-INJ3b certified.
#: The conservative reading is what ships. ⭐ It is also what makes NF-INJ3b-M's headline figures
#: (-2.61 games / -1.23 PPR on 22 flagged rows) the right sanity anchor: that cohort is the 26
#: flagged veterans MINUS these 4 returners.
#: ⛔ A future story may register returners as its own population; nothing here serves them.
CERTIFIED_EXCLUDES_RETURNERS = True
RETURNER_BOUNDARY = (
    "NF-INJ3b's preregistration §3 excluded returners (seasons_missed >= 1) from the scored "
    "population — their served games compose this cap AND NF-D11's absence prior, so this arm's "
    "contribution is not separably recoverable — so the arm is uncertified on them and they keep "
    "the incumbent constants. A READING of ruling D5=A, flagged for the PM, not a ruling.")

#: ⛔ Arms this study measured and REFUSED to serve, with the reason, so a later session cannot
#: resurrect one by re-reading the leaderboard (PM ruling D2).
REFUSED_ARMS: dict[str, str] = {
    "fitted_status": "wins 4 of 7 folds at p = 0.1265 — fails the fold-consistency clause AND BH on "
                     "NF-INJ3b's own numbers. It carries 77% of the lift and is far cheaper to "
                     "serve, which is exactly why choosing it now would be picking an arm after "
                     "seeing the scores (PM ruling D2). A future story may register it as its own "
                     "primary; nothing here may serve it.",
}

#: 🔒 THE FLIP — **ON** since NF-INJ3b-SHIP (operator ruling D5=A, 2026-08-24).
#:
#: THE DECISION, recorded here because a flag flipped without its reasoning is indistinguishable
#: from one flipped by accident. NF-INJ3b cleared 9/9 registered gates; NF-INJ3b-M then measured
#: what a drafter actually sees, which is what §5(d) blocked on: flagged veterans move **-2.61
#: games / -1.23 PPR** on average, ~90% of the raw point impact is ABSORBED and REDISTRIBUTED by
#: NF1.5's re-order, and the largest single point move on the board (11.46 PPR) lands on an
#: **UNFLAGGED** player, with 517 unflagged rank moves. The operator accepted that trade with eyes
#: open. ⚠️ The redistribution is a known MIS-SPECIFICATION (NF1.5 permutes a POINT multiset while
#: this arm moves GAMES — NF-INJ1/NF-INJ2), owned by NF-INJ2b; ruling D5=A accepted it rather than
#: waiting on it, and nothing here relaxes or re-reads NF-INJ2's CONSTRAINT_REFUSED.
#:
#: ⛔ SCOPE — VETERAN RES/PUP ONLY, and every other boundary is unchanged and enforced elsewhere:
#:    SUS/NFI keep the incumbent constants (`CERTIFIED_STATUSES` below, PM ruling D2);
#:    ROOKIES keep them too, structurally — the rookie frame never reaches `injury_games_serving`
#:    at all (NF-INJ3c's routing; ⛔ do not alter it);
#:    `fitted_status` stays REFUSED and unreachable (`REFUSED_ARMS`, enforced by `assert_coherent`).
#:
#: ⭐ THE ROLLBACK IS THIS ONE LINE, and it is the same code path, not a second one: `False` returns
#: the board to the incumbent caps byte-for-byte (pinned by test). It does NOT, on its own, publish
#: anything — a built board only reaches users through `export_draft_board_json --publish`.
SERVING_ENABLED: bool = True

#: the persisted coefficient table (committed, NOT gitignored — a serving artifact under a
#: gitignored path is the NF-INFRA1 deploy-ephemeral time bomb).
ARTIFACT_FILENAME = "nfl_fantasy_injury_games_hurdle_v1.json"


def serving_enabled() -> bool:
    """The single read. False ⇒ the incumbent cap path, byte-for-byte."""
    return bool(SERVING_ENABLED)


def is_certified(status: str) -> bool:
    """PM boundary D2 — does the certified arm apply to this status at all?"""
    return str(status) in CERTIFIED_STATUSES


def certified_rows(df) -> "np.ndarray":
    """The rows of a board frame the certified arm may serve — BOTH population boundaries, in ONE
    place, so `injury_games_serving` reads them rather than restating either.

    status ∈ `CERTIFIED_STATUSES` **and** not a returner (see `RETURNER_BOUNDARY`). A frame with no
    `seasons_missed` column cannot express the returner condition; that is treated as "no returners"
    rather than raising, because the veteran board always carries it and a research frame that does
    not has no returners to protect."""
    import numpy as np
    import pandas as pd

    ok = pd.Series(df["proj_status"]).astype(str).isin(CERTIFIED_STATUSES).to_numpy()
    if CERTIFIED_EXCLUDES_RETURNERS and "seasons_missed" in getattr(df, "columns", ()):
        sm = pd.to_numeric(df["seasons_missed"], errors="coerce").fillna(0.0).to_numpy()
        ok = ok & (sm < 1)
    return np.asarray(ok, dtype=bool)


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

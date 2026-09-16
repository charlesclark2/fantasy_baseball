"""waiver_pool.py  (NF-WVR1 — the free-agent pool and the positional-need annotation)
====================================================================================================

Two pure functions over data the API already holds:

  * `free_agent_pool` — a league's board MINUS every player on every team's roster.
  * `positional_need` — where the caller's own roster is thin against their league's lineup slots.

⛔ THERE IS NO VALUE COLUMN HERE, AND THAT IS A PM RULING, NOT AN OMISSION (2026-09-16).
The season board publishes a FULL-SEASON projection that never decrements, and — the part that
settles it — has NO IN-SEASON PRODUCTION CHANNEL AT ALL: `run_nf1.assemble_features` is "every
column is a base-season realized quantity or a leakage-safe forward designation" (base_season 2025)
and the daily publish refreshes only depth_charts/rosters/weekly_rosters. So the number moves with
role, health and market, never with what a player has actually DONE in 2026.

The PM refused shipping it as a value column even relabelled, quoted:

    "a value ranking whose top entry hasn't taken a snap is plausible-but-wrong at the feature's
     core question — a waiver decision IS 'what changed since the draft' — and no label rescues a
     ranking built to ignore the answer."

The row that carried the argument: Fernando Mendoza topped the available pool at 268.3 projected
points having taken zero snaps in week 1. A rest-of-season value column arrives with NF-ROS1.

⛔ AND NOTHING HERE RANKS ACROSS POSITIONS (PM ruling 2). Measured through the REAL scorer over the
live 870-row board, 12-team full-PPR, the top 25 AVAILABLE players are 6 QB / 3 TE / 16 K by raw
points and 14 K / 8 DST / 2 TE / 1 QB by VOR — because the FA pool IS the below-replacement
population BY CONSTRUCTION, so draft-VOR is <=0 across it and the lowest-dispersion positions float
up. (NF-C7's "best value on the board late in a draft is structurally a backup TE/QB" and NF-C5's
"a starter-cutoff replacement carried into an auction is the bug", on a third surface.)
⇒ `positional_need` is the cross-position instrument and it SELECTS POSITIONS, NOT PLAYERS.

Evidence for every measurement above: `docs/nf_wvr1_fa_pool_diagnosis.md`.
"""

from __future__ import annotations

from app.backend.services import league_scoring

#: Why a league cannot have an FA pool computed for it at all. Distinct from a per-player absence:
#: these describe the LEAGUE, and each one means the pool would be WRONG rather than thin.
POOL_REFUSAL_REASONS: tuple[str, ...] = (
    # ⭐ THE ONE THAT MATTERS. `bound_league_rosters` drops WHOLE TEAMS at
    # MAX_LEAGUE_ROSTER_PLAYERS = 500, recording it on `league_rosters_truncated`. A pool computed
    # over a truncated roster set CONTAINS THE DROPPED TEAMS' PLAYERS — i.e. it recommends players
    # who are already owned, which the PM named "the worst output this feature can produce". The
    # flag is already on the record, so the refusal costs nothing but taking it.
    "rosters_truncated",
    # The league has no stored rosters at all — every league imported before NF-C6P3 shipped, and
    # every hand-entered one. Distinguishable from "has rosters and they are empty".
    "no_league_rosters",
    # Stored rosters exist but cover fewer teams than the league declares, so some team's roster is
    # missing and its players would read as available.
    "rosters_incomplete",
    # The platform cannot re-fetch rosters, so any pool would be as old as the import. ESPN is
    # PERMANENT (a paste flow; we hold no credential and the adapter forbids acquiring one);
    # Yahoo is PENDING the app-side entitlement grant. The caller distinguishes them.
    "platform_cannot_refresh",
)

#: Why one board row is not shown as available even though nobody rosters it.
PLAYER_ABSENCE_REASONS: tuple[str, ...] = (
    # The board does not publish this position for this league's slots.
    "position_not_projected",
    # ⚠️ NOT a zero and NOT an omission (the spec's requirement, and NF1.7 (a)): a deep-league FA
    # pool reaches past the board's tail. Measured against real 2026 week-1 lines, 2.2% of
    # skill-position performers are past it and none scored 5 PPR — small, but real, and it renders
    # as a STATED absence.
    "no_board_row",
)


def _rostered_keys(league_rosters: list[dict] | None) -> set[str]:
    """Every `league_scoring._join_key` claimed by ANY team in the league.

    ⛔ JOINS ON NAME+POSITION (D/ST BY FRANCHISE), NEVER ON AN ID, and this is load-bearing rather
    than a convenience. Three id vocabularies are in play — Sleeper's own roster ids, our board's
    ids, and nflverse gsis ids — and 113 of 870 published board rows carry SYNTHETIC ids (81 rookies
    + 32 team defences). An id join would silently drop the rookie class, which is precisely the
    population a waiver surface exists to surface (the NF-INFRA1 / NF-C-LDA-0 crosswalk defect).
    Measured clean on the live board: 870 rows -> 870 distinct keys, 0 collisions.

    A roster row with no usable name contributes NOTHING — it cannot be matched, so it cannot
    subtract. That is deliberate: a blank row must not silently remove an arbitrary board player.
    """
    keys: set[str] = set()
    for entry in league_rosters or []:
        if not isinstance(entry, dict):
            continue
        for p in entry.get("players") or []:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            if not name:
                continue
            keys.add(league_scoring._join_key(name, p.get("position"), p.get("team")))
    return keys


def pool_refusals(record: dict, *, platform_can_refresh: bool = True) -> list[str]:
    """Every reason this league's FA pool would be WRONG, in `POOL_REFUSAL_REASONS` terms.

    Returns a LIST, not a first-match: a league can be both truncated and un-refreshable, and a
    surface that reports only the first cause sends the reader to fix the wrong thing (the NF-C6b
    "an empty state that renders identically for three causes" lesson).

    ⚠️ A refusal is not an error. The caller still renders the league — it renders it WITHOUT a
    pool, saying which of these is true. Silence would be the defect.
    """
    reasons: list[str] = []
    rosters = record.get("league_rosters")
    if record.get("league_rosters_truncated"):
        reasons.append("rosters_truncated")
    if not rosters:
        reasons.append("no_league_rosters")
    else:
        declared = int(record.get("n_teams") or 0)
        held = sum(1 for e in rosters if isinstance(e, dict))
        if declared and held < declared:
            reasons.append("rosters_incomplete")
    if not platform_can_refresh:
        reasons.append("platform_cannot_refresh")
    return reasons


def free_agent_pool(board_players: list[dict], league_rosters: list[dict] | None) -> list[dict]:
    """The board rows nobody in the league rosters, grouped BY POSITION.

    Returns `[{"pos": "RB", "players": [...]}, ...]` — grouped rather than flat, because a flat list
    invites exactly the cross-position ordering PM ruling 2 forbids, and a shape that cannot express
    the wrong answer is a stronger guarantee than a comment asking for the right one.

    ⛔ THE PLAYERS INSIDE A POSITION ARE IN THE BOARD'S OWN ORDER AND CARRY NO RANK. Until NF-ROS1
    publishes a rest-of-season quantity, there is nothing here that honestly ORDERS available
    players: the preseason projection fails within-position for the same reason it fails across them
    (it cannot see 2026). The caller renders this as an explicitly NON-RANKED listing, or orders it
    by REALIZED FACT COLUMNS when those are available (PM ruling 2).
    """
    rostered = _rostered_keys(league_rosters)
    by_pos: dict[str, list[dict]] = {}
    for row in board_players or []:
        name = str(row.get("name") or "")
        if not name:
            continue
        key = league_scoring._join_key(name, row.get("pos"), row.get("team"))
        if key in rostered:
            continue
        by_pos.setdefault(league_scoring.normalize_position(row.get("pos")), []).append(row)
    return [{"pos": pos, "players": players} for pos, players in by_pos.items()]


def positional_need(my_roster_rows: list[dict], cfg: dict) -> dict:
    """Where the caller's roster is thin against their OWN league's lineup slots.

    Returns `{"positions": [...], "flex": {...}}`, each entry stating its own arithmetic — an
    INSPECTABLE adjustment, never an opaque composite score (the spec's requirement and the RC1
    power-rankings rule).

    ⭐ THIS IS THE CROSS-POSITION INSTRUMENT, AND IT SELECTS POSITIONS, NOT PLAYERS (PM ruling 2).
    It says "you have an open starting RB slot"; it never says which RB, and it never compares an RB
    to a WR.

    ⚠️⚠️ FLEX IS COUNTED ONCE, AT THE LEAGUE LEVEL — NOT ADDED TO EVERY POSITION IT ACCEPTS, which
    is the obvious implementation and is WRONG. Summing a RB/WR/TE flex into all three inflates a
    12-team full-PPR league's demand from its real 9 starting slots to 11, so a manager holding
    2 RB / 2 WR / 1 TE — who can fill every slot, with the flex taking one of them — would be told
    they are SHORT AT THREE POSITIONS. That is a confidently wrong annotation on the one number this
    surface exists to state, so the flex gets its own entry and `short_by` stays unambiguous:
    DEDICATED starters only.

    Allocating the flex to a particular position would need a value judgement about WHICH position
    should fill it — and this story has no number to make one (the board cannot see 2026), so
    deciding it here would smuggle a ranking in through the back door.

    `need` is an ORDERED LABEL, not a score:
      "open_starter" — fewer players than DEDICATED starting slots; a slot would go empty
      "thin"         — exactly enough, so a bye or an injury leaves a slot empty
      "covered"      — more than the dedicated slots require
    """
    held: dict[str, int] = {}
    for row in my_roster_rows or []:
        if not isinstance(row, dict):
            continue
        board = row.get("board")
        src = board if isinstance(board, dict) else row.get("roster")
        if not isinstance(src, dict):
            src = row
        pos = league_scoring.normalize_position(src.get("pos") or src.get("position"))
        if pos:
            held[pos] = held.get(pos, 0) + 1

    dedicated: dict[str, int] = {}
    flex_slots = 0
    flex_eligible: set[str] = set()
    for slot in cfg.get("roster") or []:
        count = int(slot.get("count") or 0)
        if slot.get("bench") or count <= 0:
            continue
        eligible = [league_scoring.normalize_position(p) for p in (slot.get("eligible") or []) if p]
        if not eligible:
            continue
        if len(eligible) == 1:
            pos = eligible[0]
            dedicated[pos] = dedicated.get(pos, 0) + count
        else:
            flex_slots += count
            flex_eligible.update(eligible)

    # Every position the league can start, including one it declares ONLY through a flex slot.
    positions = sorted(set(dedicated) | flex_eligible)
    out: list[dict] = []
    for pos in positions:
        req = dedicated.get(pos, 0)
        have = held.get(pos, 0)
        short = max(0, req - have)
        out.append({
            "pos": pos,
            "starters_required": req,          # DEDICATED slots only — see the docstring
            "flex_eligible": pos in flex_eligible,
            "held": have,
            "short_by": short,
            "need": "open_starter" if short > 0 else ("thin" if have == req else "covered"),
        })

    # The flex, counted ONCE. Surplus is what is left over after every dedicated slot is filled;
    # a flex slot that no surplus can fill is a genuinely open starting slot and says so.
    surplus = sum(max(0, held.get(p, 0) - dedicated.get(p, 0)) for p in flex_eligible)
    return {
        "positions": out,
        "flex": {
            "slots": flex_slots,
            "eligible": sorted(flex_eligible),
            "surplus_available": surplus,
            "short_by": max(0, flex_slots - surplus),
        },
    }

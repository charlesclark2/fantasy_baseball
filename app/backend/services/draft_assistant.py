"""NF-C-LDA-1 — the live-draft assistant's server half: RESOLVE, then RANK.

The Chrome extension (`extension/`) reads the live ESPN draft room and sends this service a
NORMALIZED draft state: the identity fields ESPN publishes for each player in the pool, plus which
of them have been taken, by whom, and whose pick it is. It sends nothing else — no session cookie,
no request headers, no raw response bodies (see `extension/README.md`).

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ EVERYTHING THAT DECIDES ANYTHING HAPPENS HERE, AND THAT IS THE POINT
═══════════════════════════════════════════════════════════════════════════════════════════════════
Three separate rule sets could plausibly have been re-implemented inside the extension — the
position derivation, the board join, and the optimizer — and each would have become a SECOND
implementation free to drift from the one the web app uses (E9.61: "two renderers of one field are
two rule sets"). A draft assistant that quietly recommends a different player from the website is
the worst version of that, because both answers look right.

So the extension ships NO board, NO matcher and NO ranker. It observes and reports; this module:

  1. derives each player's POSITION with `platform_import.espn._player_position` — the same function
     the paste-import uses, including its NF-C-LDA-1 two-way-player fix (`Travis Hunter`);
  2. joins the pool to our board with `league_scoring._join_key` — the same key the served
     `/fantasy/nfl/league-board` roster join uses, DST franchise resolution included;
  3. ranks with `fantasy_engine.draft.recommend` — the same optimizer as
     `frontend/lib/draft-optimizer.ts`, now pinned to it byte-for-byte by
     `betting_ml/tests/test_nf_c_lda_1_optimizer_parity.py`.

⚠️ THE RESOLUTION LADDER STOPS AT THE NAME RUNG ON PURPOSE, AND IT IS MEASURED. The spike's tier-1
rung (ESPN id → gsis via the nflverse crosswalk) needs a lakehouse read, and a wide DuckDB read
inside this Lambda is both slow and a documented SILENT-EMPTY hazard (E9.26b/E5.10) — on a live
draft clock that is the wrong trade. It is also unnecessary: measured on the committed 172-player
real-league fixture (`extension/tools/measure_resolution.py`, no flags), the NAME RUNG ALONE
resolves **170/172 = 98.8% with a 0.0% join-failure rate**, and both misses are NF-K1 cause 3
(absent from the board entirely — we do not project them). Tier 1 adds cross-validation, not
coverage. `resolution.tier1` therefore reports `not_attempted`, which is a NAMED state and not a
silent zero (NF1.7(a)).
"""

from __future__ import annotations

import collections
import logging
from typing import Any, Iterable

from app.backend.services import league_scoring
from app.backend.services.platform_import import espn as espn_import

logger = logging.getLogger(__name__)

#: A pool bigger than this is not a draft room. ESPN's real draftable pool measured 1,027 rows and
#: its whole player universe ~11,600; the cap is generous enough for either and stops an unbounded
#: request body reaching the join.
MAX_POOL_ROWS = 4000

#: Recommendations returned per request. The overlay shows a handful; the rest are the "best
#: available" list beside it.
DEFAULT_TOP_N = 8
MAX_TOP_N = 50


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The board row → engine row adapter
# ══════════════════════════════════════════════════════════════════════════════════════════════
def engine_row(row: dict, replacement: dict[str, float]) -> dict:
    """One `league_scoring.build_board` row → the row shape `fantasy_engine.draft` reads.

    ⭐ THE ONLY ADAPTER, AND THE PARITY GUARD IMPORTS THIS ONE. The two engines take their input in
    different vocabularies — the board publishes camelCase (`posRank`, `vorP10`) because that is
    what the browser reads, and the Python engine takes the mart's snake_case (`positional_rank`,
    `vor_p10`). A private copy of this mapping inside the test would measure a translation we do not
    ship; a private copy inside the router would be a second one that drifts. There is one, here.

    `replacement_points` has no board-row equivalent under that name — it is the per-position
    replacement level, carried on every row as `repl` — and the engine needs it both for the
    last-player VONA fallback and for the flex-seat re-basing.
    """
    pos = league_scoring.normalize_position(row.get("pos"))
    repl = row.get("repl")
    return {
        "player_id": row.get("id"),
        "player_name": row.get("name"),
        "position": pos,
        "team_id": row.get("team"),
        "vor": row.get("vor"),
        "league_points": row.get("pts"),
        # NF-C7 — expected GAMES PLAYED. The bench seat's insurance value is P(you need him) x his
        # upgrade over the next man up, and both halves are read off this: a rate is `pts / g`, and
        # an absence probability is `(17 - g) / 17`. A missing `g` scores the candidate as worthless
        # cover rather than raising, which is the safe direction — but it is a SILENT ZERO, so the
        # parity guard pins this key.
        "games": row.get("g"),
        "replacement_points": repl if repl is not None else replacement.get(pos, 0.0),
        "positional_rank": row.get("posRank"),
        "overall_rank": row.get("ovrRank"),
        "bye": row.get("bye"),
        "is_rookie": row.get("rookie"),
        "vor_p10": row.get("vorP10"),
        "vor_p90": row.get("vorP90"),
        "low_pred": row.get("lowPred"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Resolution — ESPN's pool → our board ids
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _identity(entry: dict) -> tuple[str, str, str | None, str | None]:
    """`(espn_id, name, position, pro_team)` for one ESPN pool row.

    POSITION AND TEAM ARE DERIVED HERE, NOT SENT BY THE EXTENSION. The extension forwards the five
    identity fields ESPN publishes (`id`, `fullName`, `proTeamId`, `defaultPositionId`,
    `eligibleSlots`) verbatim; deriving in the browser would be the second position-derivation this
    module's header refuses, and it would mean the two-way-player fix landed on the server while the
    overlay kept the old answer.
    """
    espn_id = str(entry.get("id") if entry.get("id") is not None else "").strip()
    name = str(entry.get("fullName") or "").strip()
    position = espn_import._player_position(entry)
    team = espn_import._PRO_TEAM_BY_ID.get(espn_import._as_int(entry.get("proTeamId"), default=-1))
    return espn_id, name, position, team


def resolve_pool(pool: Iterable[dict], board_players: list[dict]) -> dict[str, Any]:
    """ESPN's draftable pool → `{espn_id: board_id}`, plus a report of what did NOT resolve.

    ⛔ RULE (b) — AMBIGUITY IS AN UNRESOLVED, NOT A COIN FLIP. When two DIFFERENT ESPN players
    reduce to the same board key (the suffix stripper folds `Frank Gore Jr.` onto a retired
    `Frank Gore`), BOTH are dropped rather than one silently claiming the row. A wrong merge shows a
    real player's projection under another player's name, which is worse than showing nothing.

    ⚠️ DEFENSIVE, NOT URGENT, AND SAYING SO IS PART OF THE RECORD. The spike measured 10 such
    collisions against ESPN's ~11,600-row *whole universe* and **ZERO** against the 1,027-row real
    DRAFTABLE pool this endpoint actually receives — ESPN ships exactly one of each colliding pair.
    A larger population OVERSTATED the risk. The rule stays because it costs nothing and its failure
    mode is silent; it is not load-bearing today, and `collisions` reports when that changes.

    A non-match is reported by CAUSE, never as one number (NF-K1): "the position is not on our
    board", "the name is on the board but the key missed" and "we do not project this player" are
    three different findings, and collapsing them is what cost two prior investigations.
    """
    board_by_key: dict[str, dict] = {}
    for p in board_players:
        key = league_scoring._join_key(p.get("name") or "", p.get("pos"), p.get("team"))
        board_by_key.setdefault(key, p)          # board arrives VOR-sorted ⇒ first = highest VOR
    published = set(league_scoring.published_positions(board_players))
    board_names = {league_scoring.normalize_player_name(p.get("name") or "") for p in board_players}

    claims: dict[str, list[str]] = collections.defaultdict(list)
    keyed: dict[str, str] = {}
    unresolved: list[dict] = []
    skipped_non_projectable = 0

    for entry in pool:
        if not isinstance(entry, dict):
            continue
        espn_id, name, position, team = _identity(entry)
        if not espn_id or not name:
            continue
        if position not in league_scoring.PROJECTABLE_POSITIONS:
            # An IDP / punter / coach row. Working as intended — we never project these, so it is
            # not a miss and must not inflate the unresolved count.
            skipped_non_projectable += 1
            continue
        key = league_scoring._join_key(name, position, team)
        hit = board_by_key.get(key)
        if hit is None:
            if position not in published:
                cause = "position_absent_from_board"
            elif league_scoring.normalize_player_name(name) in board_names:
                cause = "join_failure"
            else:
                cause = "not_projected"
            unresolved.append({"espn_id": espn_id, "name": name, "pos": position, "cause": cause})
            continue
        keyed[espn_id] = str(hit.get("id"))
        claims[str(hit.get("id"))].append(espn_id)

    collisions = {bid: ids for bid, ids in claims.items() if len(ids) > 1}
    for ids in collisions.values():
        for espn_id in ids:
            keyed.pop(espn_id, None)
            unresolved.append({"espn_id": espn_id, "name": "", "pos": "", "cause": "ambiguous"})

    return {
        "by_espn_id": keyed,
        "report": {
            # ⚠️ A NAMED STATE, not a zero: tier 1 is not attempted at request time (see the module
            # header). Reporting `tier1: 0` would read as "the id rung resolved nothing".
            "tier1": "not_attempted",
            "resolved": len(keyed),
            "considered": len(keyed) + len(unresolved),
            "skipped_non_projectable": skipped_non_projectable,
            "collisions": len(collisions),
            "unresolved_by_cause": dict(collections.Counter(u["cause"] for u in unresolved)),
            "unresolved": unresolved[:40],
            "board_positions": sorted(published),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The recommendation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def recommend_for_state(
    *,
    board: dict,
    config: Any,
    pool: list[dict],
    drafted_espn_ids: Iterable[str],
    my_espn_ids: Iterable[str],
    top_n: int = DEFAULT_TOP_N,
    depth_targets: dict[str, int] | None = None,
    depth_targets_source: str = "none",
) -> dict[str, Any]:
    """Rank MY next pick from a live ESPN draft state.

    `board` is a `league_scoring.build_board` result; `config` a `LeagueConfig`. Returns the
    recommendations, the best-available list, my resolved roster, and the resolution report.

    ⚠️ IMPORTED LAZILY. `fantasy_engine.draft` is stdlib-only (see `deploy.sh` and
    `fantasy_engine/__init__.py`), but importing it at module scope would put it on EVERY route's
    cold-start path for the sake of one endpoint — the exact defect the PERF audit found and fixed
    (a transitive module-scope import that cost every caller 21.8% of cold init).
    """
    from quant_sports_intel_models.fantasy_engine.draft import recommend

    players = board.get("players") or []
    replacement = board.get("replacement") or {}
    resolution = resolve_pool(pool[:MAX_POOL_ROWS], players)
    by_espn = resolution["by_espn_id"]

    drafted_ids = [by_espn[e] for e in drafted_espn_ids if e in by_espn]
    my_ids = [by_espn[e] for e in my_espn_ids if e in by_espn]

    rows = [engine_row(r, replacement) for r in players]
    recs = recommend(
        rows,
        config=config,
        drafted_ids=drafted_ids,
        my_player_ids=my_ids,
        top_n=max(1, min(int(top_n or DEFAULT_TOP_N), MAX_TOP_N)),
        # NF-C7b — the caller's per-position depth targets, resolved from the SAVED LEAGUE (or the
        # account default) by `services.depth_targets`. Nothing new is sent by the extension: the
        # league record was already being fetched to build the board, so this arrived with it.
        depth_targets=depth_targets or None,
    )

    by_id = {str(r.get("id")): r for r in players}
    return {
        "recommendations": [
            {
                "player_id": r.player_id,
                "name": r.player_name,
                "pos": r.position,
                "team": r.team_id,
                "bye": r.bye,
                "score": r.score,
                "vor": r.vor,
                "pts": r.league_points,
                "pos_rank": r.positional_rank,
                "ovr_rank": r.overall_rank,
                "need_level": r.need_level,
                "need_bonus": r.need_bonus,
                "seat_value": r.seat_value,
                "positional_dropoff": r.positional_dropoff,
                "tier": r.tier,
                "last_in_tier": r.is_last_in_tier,
                "bye_conflict": r.bye_conflict,
                "must_fill": r.must_fill,
                "deferred": r.deferred,
                "rookie": r.is_rookie,
                "why": r.rationale,
            }
            for r in recs
        ],
        # MY roster, in board terms, so the overlay never has to re-join anything.
        "my_roster": [
            {
                "player_id": pid,
                "name": by_id.get(pid, {}).get("name"),
                "pos": by_id.get(pid, {}).get("pos"),
                "team": by_id.get(pid, {}).get("team"),
                "bye": by_id.get(pid, {}).get("bye"),
                "pts": by_id.get(pid, {}).get("pts"),
                "vor": by_id.get(pid, {}).get("vor"),
            }
            for pid in my_ids
        ],
        "resolution": resolution["report"],
        # ⭐ NF-C7b — WHAT WE APPLIED AND WHERE IT CAME FROM. A league target of `{"QB": 2}` and an
        # account default of `{"QB": 2}` produce a PIXEL-IDENTICAL recommendation, so a user who
        # wants to change it has no way to tell which screen to open. Echoing the source is the
        # same discipline as `state.overall_pick` above: two different causes that render the same
        # are indistinguishable until something names them.
        "depth_targets": {
            "applied": dict(depth_targets or {}),
            "source": depth_targets_source,
        },
    }

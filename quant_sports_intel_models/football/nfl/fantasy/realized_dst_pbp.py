"""realized_dst_pbp.py — the play-derived D/ST counters (NF-WK-ACC1 part 2).

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY A PLAY-LEVEL CONSTRUCTION AT ALL
═══════════════════════════════════════════════════════════════════════════════════════════════════

RC1 built a team defence's line from summed PLAYER rows plus the schedule's score, and it agreed with
the league on 35 of 48 started seats. The 13 residuals were not noise and not a settings gap — they
are terms a player-grain table structurally cannot carry:

  • a BLOCKED KICK has no player stat column at all in the seasons we hold (`def_*_blocks` exists
    only in the 2026 file and is NaN for ≤2025), and the league pays 2 for it;
  • which plays count as SPECIAL TEAMS decides whether a touchdown is charged to the defence's
    points allowed;
  • a SAFETY is credited to a team, not a player, so a summed player line misses some;
  • a FORCED FUMBLE is credited to the forcing player, and who forced it is a play fact.

⭐ SEA 2025 WEEK 1 IS THE CASE THAT MADE THE POINT, and it corrects RC1's record: ours 6.00 vs the
league's 8.00, with RC1 concluding "nothing in the 56-key settings can supply the 2". It was a
BLOCKED FIELD GOAL, and `blk_kick` (2 points) IS in those settings — the claim was wrong because the
term inventory it was measured against was incomplete, not because the league had invented a rule.
The lesson generalises past this story: a "nothing can explain this" claim inherits the completeness
of the inventory that produced it.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⛔ THE RULES ARE FROZEN AS OF 2026-09-18 (PM ruling ③) — DO NOT REFINE THEM AGAINST 2025
═══════════════════════════════════════════════════════════════════════════════════════════════════

The served D/ST seat stays on the league's published figure until a pre-registered trigger fires:
three completed 2026 weeks, scored through THESE rules, at 100% agreement on started defences, where
the only admissible miss is a documented both-directions vendor disagreement of the forced-fumble
class below. That test is only out-of-sample if the rules stop moving, so:

  ⛔ No rule here may be changed to close a 2025 disagreement. A 2025-driven refinement would make
     the 2026 tally in-sample polish wearing an out-of-sample badge (certification by hindsight —
     the E2.1-r inversion this program has been burned by).
  ✅ A rule may be changed for a REASON INDEPENDENT of the tally: a vendor schema change, a column
     that turns out to mean something else, or a defect in the code below. Say which, in the commit.

The frozen rule set, each with what it reproduced over all 544 team-weeks of 2025 against Sleeper's
own per-team stat lines (`/v1/stats/nfl/regular/2025/<week>`, an external authority we do not
produce):

  sacks                544/544   a play with `sack` set, where this team is the defence
  interceptions        544/544   a play with `interception` set, where this team is the defence
  defensive TDs        544/544   NON-special-teams play, touchdown scored BY this team while the
                                 OTHER team had possession
  special-teams TDs    544/544   a special-teams play whose touchdown is scored by this team
  safeties             544/544   a play flagged `safety` where the OTHER team had possession
  blocked kicks        544/544   a punt/FG/XP this team blocked (the SEA week-1 term)
  ST forced fumbles    544/544   a special-teams play this team's player forced
  ST fumble recoveries 544/544   a special-teams play where the fumbling team is not this team and
                                 this team recovered
  fumble recoveries    543/544   NON-ST play where the OTHER TEAM FUMBLED and this team recovered.
                                 Keyed on who fumbled, not on who had possession (that reads
                                 539/544) — they differ when a player fumbles while his side does
                                 not have the ball, as after an interception.
  forced fumbles       539/544   NON-ST play, the other team had possession, this team's player is
                                 credited as a forcer
  points allowed       544/544   the opponent's score MINUS 6 per touchdown their DEFENCE scored
                                 MINUS 2 per safety they scored. Their SPECIAL-TEAMS touchdowns stay
                                 charged (measured: excluding those too gives 518/544). RC1's rule —
                                 subtract 7 per non-offensive touchdown — reproduced 457/544; the 6
                                 is not a rounding of 7, because the extra point is a separate
                                 scoring event this defence's unit is not on the field for.
  yards allowed        544/544   unchanged from RC1: the opponent's passing + rushing yards plus
                                 sack yards lost, from the player table. NOT re-derived here, since
                                 nothing was wrong with it.

⚠️ THE TWO RESIDUALS ARE REPORTED, NOT CHASED (MH2.2). Forced fumbles disagree in BOTH directions
(we credit one the vendor does not, and vice versa) and no rule over these columns reconciles them,
so it is a vendor attribution difference rather than a rule gap. Scored against started defences the
frozen rules reach 48/48 on 2025 weeks 1-4 and 154/155 on weeks 5-17; the single miss is a
forced-fumble count. ⛔ That 154/155 is NOT a clean held-out figure and must not be quoted as one:
the counting conventions were chosen against every 2025 week. The week-1-4 mechanisms alone scored
143/155 on weeks 5-17. The clean test is 2026, which is what the trigger is for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: Play types that ARE special teams. ⭐ THIS SET IS A RULE, NOT A CONVENIENCE. nflverse also carries
#: a `special_teams_play` flag, and the two do not always agree; the touchdown terms are decided by
#: THIS classification, because "was this a special-teams touchdown?" is the question the league's
#: own scoring asks and a kickoff/punt/kick attempt is the answer to it.
SPECIAL_TEAMS_PLAY_TYPES: frozenset[str] = frozenset({"field_goal", "extra_point", "punt", "kickoff"})

#: Exactly the pbp columns the rules read — the READ CONTRACT. Kept here so a caller cannot select a
#: narrower set and have a term silently count zero (the NF-C0e wired-≠-invoked shape): every column
#: named here is asserted present by `team_game_counters`.
PBP_COLUMNS: tuple[str, ...] = (
    "game_id", "week", "posteam", "defteam", "play_type", "touchdown", "td_team",
    "sack", "interception", "fumble", "fumbled_1_team", "fumble_recovery_1_team",
    "fumble_recovery_2_team", "forced_fumble_player_1_team", "forced_fumble_player_2_team",
    "safety", "punt_blocked", "field_goal_result", "extra_point_result",
)

#: The counter keys this module produces, in the scorer's own vocabulary (`league_scoring`'s stat
#: keys), plus the two points-allowed adjustments the caller applies to the schedule's score.
COUNTER_KEYS: tuple[str, ...] = (
    "def_sacks", "def_int", "def_fumble_rec", "def_forced_fumble", "def_td", "st_td",
    "def_safety", "def_blocked_kick", "def_st_ff", "def_st_fum_rec",
)

#: Per-team adjustments to the OPPONENT's score, for the points-allowed rule above.
#: ⚠️ `defensive_tds_scored` COUNTS ONLY DEFENSIVE TOUCHDOWNS, NOT SPECIAL-TEAMS ONES, and the
#: difference is the rule rather than an oversight: a return touchdown IS charged to the defence's
#: points allowed (measured — excluding ST touchdowns too reproduces 518/544 instead of 544/544).
ADJUSTMENT_KEYS: tuple[str, ...] = ("defensive_tds_scored", "safeties_scored")


def _truthy(value: Any) -> bool:
    """Is this play flag set? nflverse serves these as 1.0/0.0/NaN, and NaN must read as NOT set.

    ⚠️ `bool(float("nan"))` is TRUE, so a bare truth test on a NaN flag counts every play — which
    would inflate every counter rather than failing, i.e. it would look like data.
    """
    if value is None:
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return bool(value)
    return f == f and f != 0.0


def _team(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _is_special_teams(play: Mapping) -> bool:
    return str(play.get("play_type") or "").strip().lower() in SPECIAL_TEAMS_PLAY_TYPES


def _blocked(play: Mapping) -> bool:
    if _truthy(play.get("punt_blocked")):
        return True
    return "blocked" in (str(play.get("field_goal_result") or "").lower(),
                         str(play.get("extra_point_result") or "").lower())


def team_game_counters(plays: Iterable[Mapping]) -> dict[str, dict[str, float]]:
    """One game's plays → `{team: {counter: value}}` for BOTH teams in it.

    PURE: no lake read, no scoring, no settings. The caller multiplies by the league's own weights,
    which is what keeps this module a statement about football rather than about one league.

    Every team named on any play gets a row, so a team with nothing to its name reports zeros rather
    than being absent — "no sacks" and "we did not look" must not share a representation.
    """
    plays = list(plays)
    missing = [c for c in PBP_COLUMNS if plays and c not in plays[0]]
    if missing:
        raise ValueError(
            f"the play rows are missing {missing}, which the frozen D/ST rules read. A narrower "
            "SELECT would make those terms count zero with no error — select `PBP_COLUMNS`.")

    teams: set[str] = set()
    for play in plays:
        for key in ("posteam", "defteam", "td_team"):
            t = _team(play.get(key))
            if t:
                teams.add(t)
    out = {t: {k: 0.0 for k in (*COUNTER_KEYS, *ADJUSTMENT_KEYS)} for t in teams}
    #: Who the other side is, for the possession-keyed terms. Only well defined for a real two-team
    #: game; anything else leaves those terms uncounted rather than guessed.
    opponent_of = {t: (set(out) - {t}).pop() for t in out} if len(out) == 2 else {}

    for play in plays:
        pos, dfn = _team(play.get("posteam")), _team(play.get("defteam"))
        special = _is_special_teams(play)
        forcers = {_team(play.get("forced_fumble_player_1_team")),
                   _team(play.get("forced_fumble_player_2_team"))} - {None}
        recoverers = {_team(play.get("fumble_recovery_1_team")),
                      _team(play.get("fumble_recovery_2_team"))} - {None}
        fumbled_by = _team(play.get("fumbled_1_team"))
        scorer = _team(play.get("td_team"))

        if dfn and dfn in out:
            if _truthy(play.get("sack")):
                out[dfn]["def_sacks"] += 1
            if _truthy(play.get("interception")):
                out[dfn]["def_int"] += 1
            if _blocked(play):
                out[dfn]["def_blocked_kick"] += 1

        # A safety is credited to the team NOT in possession; the team in possession CONCEDED it,
        # which is the adjustment the points-allowed rule needs.
        if _truthy(play.get("safety")):
            if dfn and dfn in out:
                out[dfn]["def_safety"] += 1
                out[dfn]["safeties_scored"] += 1

        if _truthy(play.get("touchdown")) and scorer and scorer in out:
            if special:
                out[scorer]["st_td"] += 1
            elif pos and scorer != pos:
                # Scored by the side that did NOT have the ball: a defensive touchdown.
                out[scorer]["def_td"] += 1
                out[scorer]["defensive_tds_scored"] += 1

        if special:
            for t in forcers & out.keys():
                out[t]["def_st_ff"] += 1
            if _truthy(play.get("fumble")):
                for t in (recoverers - {fumbled_by}) & out.keys():
                    out[t]["def_st_fum_rec"] += 1
            continue

        # ── from here: NON-special-teams plays only ──
        # ⭐ THE TWO FUMBLE TERMS KEY ON DIFFERENT THINGS, AND BOTH WERE MEASURED RATHER THAN
        # REASONED. A RECOVERY keys on WHO FUMBLED (`fumbled_1_team`): 543/544, against 539/544 for
        # the natural-looking "the other team had possession" — they differ on a fumble by a player
        # whose team does not have possession, e.g. after an interception, and the vendor credits the
        # recovery by the fumbling side. A FORCED FUMBLE keys on POSSESSION: 539/544 either way, and
        # possession is the form the record was measured with.
        for t in forcers & out.keys():
            if pos and opponent_of.get(t) == pos:
                out[t]["def_forced_fumble"] += 1
        if _truthy(play.get("fumble")) and fumbled_by:
            for t in recoverers & out.keys():
                if opponent_of.get(t) == fumbled_by:
                    out[t]["def_fumble_rec"] += 1

    return out


def points_allowed(opponent_score: float | None, opponent_counters: Mapping) -> float | None:
    """The frozen points-allowed rule. `None` score in ⇒ `None` out (the result is not known yet).

    ⚠️ THE SUBTRAHENDS ARE THE OPPONENT'S OWN DEFENSIVE SCORING, not ours and not their special
    teams': what is removed is what their DEFENCE put on the board, because this defence was not on
    the field for it. A return touchdown stays charged (measured; see `ADJUSTMENT_KEYS`). Floored at
    0 — a defence that conceded only a defensive touchdown allowed nothing.
    """
    if opponent_score is None:
        return None
    try:
        score = float(opponent_score)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    charged = (6.0 * float(opponent_counters.get("defensive_tds_scored") or 0.0)
               + 2.0 * float(opponent_counters.get("safeties_scored") or 0.0))
    return max(0.0, score - charged)

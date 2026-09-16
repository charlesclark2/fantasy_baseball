"""NF-WK-RC1 — fetch ONE played week's actual lineups and matchup results from Sleeper.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY THIS EXISTS (PM ruling D1 = option A, 2026-09-16)
═══════════════════════════════════════════════════════════════════════════════════════════════════

RC1's node 1 established that the saved league record cannot support a weekly recap: it holds no
team's STARTED LINEUP for any week (`LEAGUE_ROSTER_PLAYER_FIELDS` is `("name","position","team")` —
`starter` is deliberately dropped for other teams), no matchup schedule or results, and only an
IMPORT-TIME roster snapshot. The PM funded this fetch inside the story rather than spawning a
successor, because without it the story has no honest deliverable:

    "A recap crediting benched players beside a 'power ranking' that isn't the standings is
     plausible-but-wrong on a factual surface, and the factual surface is the one place this
     program can least afford it."

⭐ THE SEASON-SURFACE PRIVACY CHOICE IS SUPERSEDED ONLY HERE, AND ONLY NARROWLY. Dropping `starter`
for other teams was a deliberate privacy-of-comparison decision for the SEASON surface. A PLAYED
week's lineups are the league's own public record on the platform, so the ruling supersedes it FOR
RECAPS — the season fields stay untouched, and a recap sources its lineups ONLY from a fetched week,
never from the stored season snapshot.

───────────────────────────────────────────────────────────────────────────────────────────────────
🔎 PROBED LIVE 2026-09-16 AGAINST A REAL LEAGUE, NOT READ OFF DOCUMENTATION
───────────────────────────────────────────────────────────────────────────────────────────────────

Every field name below came out of the actual payload (league 1268257036043292672, the operator's
own, already used by NF-C0's tests). The kickoff rule, and MT1's two lost operator round-trips: a
probe that invents a field name reports a uniform absence that reads as an outage.

  `GET /v1/league/<id>/matchups/<week>` → a LIST, one entry per roster:
      matchup_id      int    the pairing — exactly two roster_ids share one
      roster_id       int    the team
      starters        list   ⭐ ORDERED player ids; the order IS the lineup's slot order
      starters_points list   ⭐ parallel to `starters` — SLEEPER'S OWN scoring of each starter
      players         list   the whole roster that week
      players_points  dict   per-player points
      points          float  the team total, Sleeper-scored
      custom_points   float|null  a commissioner override of the team total

⭐ `starters_points` IS AN INDEPENDENT CROSS-CHECK and it is the reason this module keeps it. It is
Sleeper scoring the SAME lineup under the SAME league's settings, computed by someone else — the
strongest available analogue of the parity anchor node 1 got from `fantasy_points_ppr`. It is
carried through, never used as an input: the recap's numbers come from OUR scorer over the realized
stat line, and Sleeper's are a comparison a guard can read.

⚠️ D/ST IS A TEAM CODE, NOT A NUMERIC ID (`"PHI"` sits in `starters` beside `"11563"`). A resolver
that assumes numeric ids drops exactly the defence slot — and in the probed league DEF is a STARTING
SLOT with no kicker at all, so that miss would be one ninth of every lineup.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ WHY THE SLOT ORDER IS CAPTURED HERE RATHER THAN READ OFF THE SAVED LEAGUE
───────────────────────────────────────────────────────────────────────────────────────────────────

`starters[i]` belongs to the i-th STARTING SEAT of `roster_positions`. The saved league record
cannot supply that order: `canonical.count_slots` COLLAPSES the per-seat listing into counted slots
(`["RB","WR","RB"]` → `RB:2, WR:1`), and its own docstring says so. Expanding counts back out
reproduces the seat order only when seats are not interleaved — and when they ARE, every slot label
after the first interleave is silently WRONG, which is a confidently mislabelled lineup rather than
a visible failure.

So the per-seat starting order is read from the league payload AT FETCH TIME and stored in the
point-in-time record beside the lineup it labels. That also makes the record self-describing and
immune to a later edit of the saved league's roster configuration — which is the PIT property the
ruling asked for.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.backend.services import league_scoring
from app.backend.services.platform_import import sleeper_players
from app.backend.services.platform_import.http import get_json
from app.backend.services.platform_import.sleeper import (
    BASE_URL,
    PLATFORM,
    SleeperInputError,
    _as_dict,
    _as_list,
)

#: Slots that never start. Mirrors `sleeper._SLOT_MAP`'s bench flags; a starting seat is anything
#: else, in `roster_positions` order.
BENCH_SLOTS: frozenset[str] = frozenset({"BN", "IR", "TAXI"})

#: 🔒 SSRF / path-injection guard, same posture as the import adapter: user-supplied values are
#: validated against the platform's real shapes BEFORE a URL is built, never sanitized after.
_ID_RE = re.compile(r"^[0-9]{1,24}$")

#: NFL regular season is 18 weeks; Sleeper numbers postseason weeks above that. Bounded so a
#: caller cannot walk the endpoint with an arbitrary integer.
MAX_WEEK = 22


class SleeperMatchupError(RuntimeError):
    """This league's week cannot be turned into a recap, and the message says which cause.

    Distinct from `PlatformHTTPError` so "Sleeper is unreachable" stays separable from "Sleeper
    answered, and what it returned cannot carry a recap" — the NF-C6b rule that a surface must be
    able to tell its failure causes apart without an investigation.
    """


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _validate(league_id: str, week: int) -> tuple[str, int]:
    lid = str(league_id or "").strip()
    if not _ID_RE.match(lid):
        raise SleeperInputError(f"{league_id!r} is not a Sleeper league id")
    try:
        wk = int(week)
    except (TypeError, ValueError) as exc:
        raise SleeperInputError(f"{week!r} is not a week number") from exc
    if not 1 <= wk <= MAX_WEEK:
        raise SleeperInputError(f"week {wk} is outside 1..{MAX_WEEK}")
    return lid, wk


def starting_slots(roster_positions: list) -> list[str]:
    """The league's STARTING seats, in the order `starters` is indexed by.

    ⛔ Order-preserving and NOT de-duplicated: two FLEX seats are two entries, because the whole
    point is that `starters[i]` names seat `i`. Collapsing them would reintroduce exactly the
    ambiguity this module exists to avoid (see the header).
    """
    return [str(s) for s in _as_list(roster_positions) if str(s) not in BENCH_SLOTS]


def _team_names(league_id: str) -> dict[str, str]:
    """`roster_id` → the team's display name, best-effort.

    ⚠️ BEST-EFFORT BY DESIGN, and it degrades to an empty map rather than raising: a missing team
    NAME costs a label, while a missing LINEUP costs the recap. Those are not the same failure and
    must not share an exception (E9.49 — one weak part must cost only itself).
    """
    try:
        rosters = _as_list(get_json(_url(f"/league/{league_id}/rosters")))
        users = {
            str(_as_dict(u).get("user_id")): _as_dict(u)
            for u in _as_list(get_json(_url(f"/league/{league_id}/users")))
        }
    except Exception:  # noqa: BLE001 — see the docstring; a label is not worth failing a recap
        return {}
    out: dict[str, str] = {}
    for raw in rosters:
        roster = _as_dict(raw)
        user = users.get(str(roster.get("owner_id") or ""), {})
        display = str(user.get("display_name") or "")
        name = str(_as_dict(user.get("metadata")).get("team_name") or "") or display
        if name:
            out[str(roster.get("roster_id") or "")] = name
    return out


def fetch_week(league_id: str, week: int) -> dict:
    """ONE played week of a Sleeper league, as the point-in-time record a recap is built from.

    Returns a self-describing blob: the starting-seat order, every team's actual lineup in that
    order, the matchup pairing, and Sleeper's own per-starter scoring carried alongside for
    comparison. It does NO scoring — that is `league_scoring`'s job over the realized stat line.

    ⛔ REFUSES rather than returning a thin blob. A week with no matchup rows, or one whose
    `starters` length does not match the league's starting-seat count, cannot be rendered per-slot;
    returning it anyway would produce a lineup whose labels are wrong, which reads as real. A
    refusal names the cause; a mislabelled lineup does not announce itself.
    """
    lid, wk = _validate(league_id, week)

    league = _as_dict(get_json(_url(f"/league/{lid}")))
    if not league:
        raise SleeperMatchupError(
            f"Sleeper has no league {lid} — it may have been deleted, or the id may be for a "
            "different season (Sleeper gives each season its own league id)."
        )
    slots = starting_slots(league.get("roster_positions"))
    if not slots:
        raise SleeperMatchupError(
            "this league declares no starting lineup slots, so there is no lineup to lay out."
        )

    raw = _as_list(get_json(_url(f"/league/{lid}/matchups/{wk}")))
    if not raw:
        raise SleeperMatchupError(
            f"Sleeper returned no matchups for week {wk}. A week that has not been played yet is "
            "the ordinary cause; a league that did not exist that week is the other."
        )

    names = _team_names(lid)

    # Resolve every starter ONCE across the league (the id→name artifact read is memoized but the
    # call is not free), and only the ones that actually started: a recap lays out lineups, not
    # rosters, so resolving bench players would be work nothing renders.
    numeric = {
        str(p) for e in raw for p in _as_list(_as_dict(e).get("starters"))
        if p and str(p) != "0" and str(p).isdigit()
    }
    resolved, artifact_loaded = sleeper_players.resolve(numeric)

    teams: list[dict] = []
    for entry in raw:
        e = _as_dict(entry)
        starters = [str(p) if p else "" for p in _as_list(e.get("starters"))]
        points = _as_list(e.get("starters_points"))
        if len(starters) != len(slots):
            raise SleeperMatchupError(
                f"roster {e.get('roster_id')} started {len(starters)} players into "
                f"{len(slots)} lineup slots. Laying that out per slot would label the wrong "
                "player with the wrong position, so the week is refused rather than guessed at."
            )
        lineup = []
        for i, (slot, pid) in enumerate(zip(slots, starters)):
            meta = resolved.get(pid) or {}
            # ⭐ D/ST ARRIVES AS A TEAM CODE, NOT A NUMERIC ID (`"PHI"`), so the id→name artifact
            # has nothing for it and a numeric-only resolver leaves the defence seat BLANK. The
            # module header called this trap out and the first cut did not implement it — the live
            # smoke rendered `DEF seat8` with an empty name, which is the NF-C0e "declaration
            # outran the production" shape in miniature. Resolved against the scorer's OWN team
            # vocabulary rather than a re-typed list, so a franchise rename moves both at once.
            dst = pid.upper() in league_scoring.NFL_TEAM_ABBREVIATIONS
            lineup.append({
                "slot": slot,
                "seat": i,
                "playerKey": pid,
                # An EMPTY id is Sleeper's own "this seat was left empty" — carried as-is so the
                # recap can say the seat was empty rather than inventing an absent player.
                "empty": not pid or pid == "0",
                "name": (f"{pid.upper()} D/ST" if dst
                         else str(meta.get("full_name") or meta.get("name") or "")),
                "position": "DST" if dst else str(meta.get("position") or ""),
                "team": pid.upper() if dst else str(meta.get("team") or ""),
                # ⭐ Sleeper's OWN score for this seat. Carried, never consumed — see the header.
                "platformPts": float(points[i]) if i < len(points) and points[i] is not None else None,
            })
        rid = str(e.get("roster_id") or "")
        teams.append({
            "teamKey": rid,
            "teamName": names.get(rid) or f"Team {rid}",
            "matchupId": e.get("matchup_id"),
            "lineup": lineup,
            "platformTotal": float(e.get("points")) if e.get("points") is not None else None,
            # A commissioner override of the team total. Carried because a league that uses it has
            # a REAL result different from the sum of its lineup, and silently ignoring it would
            # make our standings disagree with the league's own.
            "platformCustomTotal": (
                float(e["custom_points"]) if e.get("custom_points") is not None else None
            ),
        })

    return {
        "platform": PLATFORM,
        "leagueId": lid,
        "week": wk,
        "season": str(league.get("season") or ""),
        "startingSlots": slots,
        "teams": teams,
        # ⚠️ The id→name artifact can be absent; when it is, names come back empty and the recap
        # must say so rather than rendering blank rows that look like missing players (NF-C0c).
        "namesResolved": bool(artifact_loaded),
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

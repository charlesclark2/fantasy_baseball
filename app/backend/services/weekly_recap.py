"""NF-WK-RC1 — score ONE completed week's ACTUAL lineups, per slot, in the league's own scoring.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⛔ AN ADAPTER, NOT A SCORER — the same distinction `weekly_league_board` makes and for the same cost
═══════════════════════════════════════════════════════════════════════════════════════════════════

Nothing here multiplies a weight by a stat. Every player-seat point comes out of
`league_scoring.score_row` unchanged, read under `realized_stat_fields.REALIZED_STAT_FIELD`, and the
join is `league_scoring.match_roster_to_board` — the SAME join a season roster already goes through,
so a name that matches on the season board matches here. A second join implementation is exactly how
"my players disappeared on the recap tab" happens (NF-C6P3), and a fourth scoring implementation is
a tax paid forever.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ THE D/ST SEAT CARRIES THE LEAGUE'S OWN PUBLISHED FIGURE (PM disposition D2 = (C), 2026-09-16)
───────────────────────────────────────────────────────────────────────────────────────────────────

Our own team-defence construction reproduced only 35 of 48 team-weeks against Sleeper's scoring of
the same defences. The ruling, and the reasoning is the point:

    "For the D/ST seat, the league has applied its own settings and published the answer — on a
     factual surface, that number is the fact, and our 27%-divergent construction would be
     substituting an unvalidated estimate for a known value."

⛔ AND AN ABSENCE WAS REFUSED, on a ground worth restating because it is not obvious: D/ST is one of
NINE seats, so an absent D/ST does not leave a hole — it makes every TEAM TOTAL and therefore the
STANDINGS systematically disagree with the league's own page, which is the first thing a user checks
a recap against.

⭐ THE ONE-SCORER RULE IS NOT BREACHED. That rule exists to prevent a fourth IMPLEMENTATION of our
scoring policy; consuming a figure the league already published is not an implementation, it is
citing the authority. The provenance is carried per seat (`source`) and must be stated PLAINLY on
the surface — the disposition's words: "not a footnote".

───────────────────────────────────────────────────────────────────────────────────────────────────
🔬 THE DIVERGENCE RECORDER, AND ITS ONE HARD CONSTRAINT
───────────────────────────────────────────────────────────────────────────────────────────────────

Both seat kinds are compared against the platform's own figure, and THEIR EXPECTATIONS ARE DECLARED
SEPARATELY because they are opposite:

  • PLAYER seats   expect EQUALITY. A divergence is real signal and MAY alert.
  • The D/ST seat  expects DIVERGENCE (we know it fails ~27% of team-weeks). It RECORDS ONLY.

⛔ The D/ST comparison must never page. Quoting the constraint: "a comparison known to fail on ~27%
of team-weeks that paged would be the muted-monitor pattern arriving on day one." No threshold is
set on it until the (B) story explains the known residual, because until then a NEW mechanism and a
KNOWN one are indistinguishable in the stream.

⚠️ AND THE PLAYER-SEAT EXPECTATION IS ITSELF A MEASURED CLAIM, NOT AN ASSUMPTION. `player_expectation`
is reported by `compare_to_platform` from what the run actually saw, so a caller can tell "these
agree" from "we asserted they would".
"""

from __future__ import annotations

from app.backend.services import league_scoring, realized_stat_fields

#: Seat provenance, carried per seat and rendered plainly (never a footnote — the D2 disposition).
SOURCE_OUR_SCORER = "our_scorer"
SOURCE_LEAGUE_PUBLISHED = "league_published"

#: The sentence a surface may render as-is beside a league-published seat.
LEAGUE_PUBLISHED_NOTE = (
    "This score is your league's own published figure for the team defence, not ours. Every other "
    "slot is your league's scoring applied to the week's real stat line by us."
)

#: Why a started player has no realized line. ADDITIVE to `nfl_weekly.ROSTER_ABSENCE_REASONS` —
#: these describe a REALIZED week, where the causes are genuinely different from a projection's.
RECAP_ABSENCE_REASONS: tuple[str, ...] = (
    "seat_left_empty",        # the manager started nobody here; the platform says so itself
    "no_realized_line",       # started, but no stat line was recorded for him that week
    "name_unresolved",        # the platform gave an id we could not resolve to a name
)

_ABSENCE_DETAIL: dict[str, str] = {
    "seat_left_empty": "This lineup slot was left empty, so it scored nothing.",
    "no_realized_line": (
        "This player was started but no stat line was recorded for him this week — he did not "
        "appear in the game."
    ),
    "name_unresolved": (
        "Your league gave us an id for this slot that we could not resolve to a player, so we "
        "cannot look up what he did."
    ),
}


def _absence(reason: str) -> dict:
    return {"reason": reason, "detail": _ABSENCE_DETAIL[reason]}


def realized_board(realized_rows: list[dict], resolved: dict, stat_field: dict[str, str]) -> list[dict]:
    """Every realized player-week, scored in this league's terms — the side the lineup joins onto.

    Built ONCE per week rather than per team: twelve lineups join against the same board, and
    re-scoring per team would be twelve times the work for identical numbers.
    """
    out: list[dict] = []
    for row in realized_rows:
        if not isinstance(row, dict):
            continue
        pos = league_scoring.normalize_position(row.get("position"))
        flat = realized_stat_fields.flatten_realized_row(row)
        out.append({
            "name": str(row.get("player_display_name") or ""),
            "pos": pos,
            "team": str(row.get("team") or ""),
            "opp": str(row.get("opponent_team") or ""),
            "leaguePts": league_scoring.score_row(flat, pos, resolved, stat_field)["pts"],
            # The source's own PPR, carried for the points-head pair boundary (i) allows. NEVER
            # recomputed — a second computation of a number the source publishes is a drift
            # surface for no gain.
            "pprPts": row.get(realized_stat_fields.REALIZED_PPR_COLUMN),
        })
    return out


def score_week(
    *,
    fetched: dict,
    realized_rows: list[dict],
    cfg: dict,
    stat_field: dict[str, str] | None = None,
) -> dict:
    """One league-week: every team's actual lineup, scored per slot, plus the matchup results.

    `fetched` is the POINT-IN-TIME record (`weekly_recap_store`), never a live re-read — a rendered
    recap must be stable, which is the whole reason that store exists.
    """
    field_map = stat_field or realized_stat_fields.REALIZED_STAT_FIELD
    flat_rows = [realized_stat_fields.flatten_realized_row(r) for r in realized_rows
                 if isinstance(r, dict)]
    resolved, coverage = league_scoring.resolve_scoring(
        cfg.get("scoring") or {},
        stat_field=field_map,
        # ⭐ THE FIELDS ACTUALLY PRESENT, not the whole map — what makes a league's weight on a term
        # this week's line does not carry resolve CAPTURED instead of scoring zero behind an
        # "applied" label.
        fields=league_scoring.available_fields(flat_rows),
        captured_rules=list((cfg.get("captured_rules") or {}).keys()),
    )
    board = realized_board(realized_rows, resolved, field_map)

    teams: list[dict] = []
    for team in fetched.get("teams") or []:
        roster = [
            {"name": s.get("name") or "", "position": s.get("position") or "",
             "team": s.get("team") or ""}
            for s in team.get("lineup") or []
        ]
        matched = league_scoring.match_roster_to_board(roster, board)

        seats: list[dict] = []
        total = 0.0
        for seat, join in zip(team.get("lineup") or [], matched):
            row = dict(seat)
            hit = join.get("board")
            if seat.get("empty"):
                row.update({"points": None, "source": None, "absence": _absence("seat_left_empty")})
            elif seat.get("position") == "DST":
                # ⭐ THE LEAGUE'S OWN FIGURE — see the header. `platformPts` may legitimately be
                # None (a platform that did not publish a per-seat number), and that is an ABSENCE
                # rather than a zero: a zero would silently drag the team total and the standings.
                pts = seat.get("platformPts")
                row.update({
                    "points": pts,
                    "source": SOURCE_LEAGUE_PUBLISHED if pts is not None else None,
                    "sourceNote": LEAGUE_PUBLISHED_NOTE if pts is not None else None,
                    "absence": None if pts is not None else _absence("no_realized_line"),
                })
            elif not seat.get("name"):
                row.update({"points": None, "source": None, "absence": _absence("name_unresolved")})
            elif hit is None:
                row.update({"points": None, "source": None, "absence": _absence("no_realized_line")})
            else:
                row.update({
                    "points": hit["leaguePts"], "source": SOURCE_OUR_SCORER,
                    "pprPts": hit.get("pprPts"), "opp": hit.get("opp"), "absence": None,
                })
            if row.get("points") is not None:
                total += float(row["points"])
            seats.append(row)

        teams.append({
            "teamKey": team.get("teamKey"),
            "teamName": team.get("teamName"),
            "matchupId": team.get("matchupId"),
            "seats": seats,
            "total": total,
            "platformTotal": team.get("platformTotal"),
            "platformCustomTotal": team.get("platformCustomTotal"),
        })

    return {
        "season": fetched.get("season"),
        "week": fetched.get("week"),
        "platform": fetched.get("platform"),
        "leagueId": fetched.get("leagueId"),
        "capturedAt": fetched.get("capturedAt"),
        "startingSlots": fetched.get("startingSlots"),
        "teams": teams,
        "matchups": matchups(teams),
        "coverage": coverage,
    }


def matchups(teams: list[dict]) -> list[dict]:
    """The week's head-to-head results, paired by the platform's own `matchupId`.

    ⚠️ A pairing that is not exactly two teams is reported AS IT IS rather than dropped or padded.
    Sleeper uses a null `matchup_id` for a team on a bye and can carry an odd pairing in a
    consolation format; inventing an opponent for one, or hiding it, would both be worse than
    saying what the league actually recorded.
    """
    groups: dict[object, list[dict]] = {}
    for t in teams:
        groups.setdefault(t.get("matchupId"), []).append(t)
    out: list[dict] = []
    for mid, side in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0])):
        entry = {
            "matchupId": mid,
            "teams": [{"teamKey": s["teamKey"], "teamName": s["teamName"], "total": s["total"]}
                      for s in side],
        }
        if len(side) == 2:
            a, b = side
            entry["winnerTeamKey"] = (
                None if a["total"] == b["total"]
                else (a if a["total"] > b["total"] else b)["teamKey"]
            )
            entry["tied"] = a["total"] == b["total"]
        else:
            # Named rather than silent: "we could not pair this" is a fact the surface may render.
            entry["unpaired"] = True
        out.append(entry)
    return out


def compare_to_platform(
    scored: dict,
    *,
    dst_constructed: dict[str, float] | None = None,
    tolerance: float = 1e-9,
) -> dict:
    """Our per-seat points vs the platform's own, with the two seat kinds reported SEPARATELY.

    ⛔ THIS FUNCTION DOES NOT DECIDE TO ALERT, and that separation is deliberate: the D/ST leg is
    known to diverge and must never page (see the header), while the player leg is real signal. A
    caller reads `playerSeats` for an alert decision and `dstSeats` for the (B) artifact.

    ⭐ `playerExpectation` is MEASURED, not asserted — it reports what this run actually saw, so a
    reader can tell "these agree" from "someone wrote down that they would".
    """
    player_div: list[dict] = []
    dst_div: list[dict] = []
    player_n = dst_n = 0
    dst_unavailable: list[dict] = []
    for team in scored.get("teams") or []:
        for seat in team.get("seats") or []:
            ours, theirs = seat.get("points"), seat.get("platformPts")
            if ours is None or theirs is None:
                continue
            delta = float(ours) - float(theirs)
            rec = {
                "teamKey": team.get("teamKey"), "teamName": team.get("teamName"),
                "slot": seat.get("slot"), "seat": seat.get("seat"),
                "name": seat.get("name"), "ours": float(ours), "platform": float(theirs),
                "delta": delta,
            }
            if seat.get("position") == "DST":
                # ⚠️⚠️ THE SERVED D/ST POINT *IS* `platformPts` UNDER (C), SO COMPARING IT AGAINST
                # THE PLATFORM IS VACUOUS — it is 0 by construction, and the first cut of this
                # function did exactly that and reported "0 diverging" on a construction MEASURED to
                # fail 27% of team-weeks. A guard that cannot fail is worse than none (NF1.7(a)).
                # What the disposition asked to record is OUR UNWIRED CONSTRUCTION against the
                # league's figure, so the comparison only happens when that construction is
                # supplied — and its ABSENCE is reported rather than silently scoring as agreement.
                if dst_constructed is None:
                    continue
                key = league_scoring.normalize_team(seat.get("team") or seat.get("playerKey"))
                if key not in dst_constructed:
                    dst_unavailable.append({"teamKey": team.get("teamKey"), "defense": key})
                    continue
                dst_n += 1
                rec["ours"] = float(dst_constructed[key])
                rec["delta"] = rec["ours"] - float(theirs)
                if abs(rec["delta"]) > tolerance:
                    dst_div.append(rec)
            else:
                player_n += 1
                if abs(delta) > tolerance:
                    player_div.append(rec)
    return {
        "playerSeats": {
            "compared": player_n, "diverging": len(player_div), "rows": player_div,
            "expectation": "equality",
            "mayAlert": True,
            # MEASURED — see the docstring.
            "playerExpectation": "held" if not player_div else "violated",
        },
        "dstSeats": {
            "compared": dst_n, "diverging": len(dst_div), "rows": dst_div,
            # ⛔ NOT SILENCE. A seat whose construction could not be computed is reported, never
            # counted as agreement — otherwise "we could not check" and "it matched" are the same
            # number, which is how a vacuous comparison looks healthy.
            "notConstructed": dst_unavailable,
            "constructionSupplied": dst_constructed is not None,
            "expectation": "divergence_known",
            # ⛔ The hard constraint from the D2 disposition, carried in the data itself so a caller
            # cannot wire an alert onto it by reading only the numbers.
            "mayAlert": False,
            "note": (
                "The served D/ST seat carries the league's own published figure. This comparison "
                "records our unwired construction against it for the follow-up story; it is known "
                "to diverge and must not raise an alert."
            ),
        },
    }

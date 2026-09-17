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
⭐⭐ THE STANDINGS FACT IS THE LEAGUE'S TOTAL; OUR SCORER IS THE EXPLANATION (PM ruling (i), 2026-09-16)
───────────────────────────────────────────────────────────────────────────────────────────────────

Measuring (C) found that team totals agreed with the league on only 14 of 48 real team-weeks — not
from a defect, but because the league scores terms we legitimately CAPTURE (its `fum` any-fumble
penalty has no canonical scorer key; the three 40+ yard TD bonuses have no realized source, because
`passing_40` counts 40+ yard PLAYS and mapping it would be a wrong-key). So the property the D2
disposition required was not delivered by the D/ST fix alone.

The ruling extends the same reasoning one level up, and the DIVISION OF LABOUR is the design:

    the league's published `platformTotal` is the STANDINGS FACT;
    our scorer is the EXPLANATION — per-seat, per-term, with coverage —
    which is what no league page provides.

⛔ THE TWO ARE NEVER PRESENTED AS TWO ESTIMATES OF ONE NUMBER. One is the league's record; the other
is our itemisation of what we can itemise. `total` (ours) and `standingsTotal` (theirs) are
deliberately DIFFERENT FIELD NAMES so a consumer cannot casually swap them.

⛔ AND THE GAP IS DISCLOSED ADJACENT TO THE TOTAL, SPECIFICALLY (the MT1 ruling-③ adjacency rule —
not a panel, not a footnote), NAMING THE TERMS: the coverage report already knows which ones, so the
copy says "this league also scores fumbles and 40+ yard TD bonuses, which the breakdown doesn't
itemize yet" and never a vague "totals may differ". `itemisation_gap_note` builds exactly that
sentence from the resolved coverage rather than from a constant.

⚠️ A PLATFORM WE CANNOT FETCH HAS NO STANDINGS AT ALL, rather than approximate ones — the
stated-absence ruling applied consistently. ESPN/Yahoo league views say STANDINGS specifically, not
just recaps.

───────────────────────────────────────────────────────────────────────────────────────────────────
🔬 THE DIVERGENCE RECORDER: EVERY SEAT RECORDS, NO SEAT PAGES
───────────────────────────────────────────────────────────────────────────────────────────────────

The earlier clause had player seats expecting EQUALITY and permitted to alert. ⚠️ THAT PREMISE IS
NOW MEASURED FALSE, for legitimate reasons: 6-20 of ~94 player seats per week diverge, every one of
them explained by a captured term. So the ruling downgraded player seats to RECORD-ONLY alongside
D/ST — "an alert whose baseline includes known-legitimate divergence is the muted-monitor pattern".

⭐ ALERTING RETURNS TERM BY TERM AS THE CAPTURED SET SHRINKS, and this module prepares for that:
where the expected gap is COMPUTABLE from a captured term (`fum` = −1.0 x fumbles), the EXPLAINED
and UNEXPLAINED portions are recorded separately. The unexplained residual is the future alert's
clean signal; the explained portion is arithmetic and must never be mistaken for evidence.
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

        # ⭐ THE STANDINGS FACT. A commissioner override, where the league set one, IS the league's
        # record for that team — so it wins over the computed platform total rather than being
        # carried beside it and ignored (a league that uses one has a REAL result different from
        # the sum of its lineup, and our standings would otherwise disagree with its own page).
        standings = (team.get("platformCustomTotal")
                     if team.get("platformCustomTotal") is not None
                     else team.get("platformTotal"))
        teams.append({
            "teamKey": team.get("teamKey"),
            "teamName": team.get("teamName"),
            "matchupId": team.get("matchupId"),
            "seats": seats,
            # ⛔ TWO NAMES ON PURPOSE — see the header. `itemisedTotal` is OURS (the sum of what we
            # could itemise); `standingsTotal` is the LEAGUE'S record. Never interchangeable.
            "itemisedTotal": total,
            "standingsTotal": standings,
            "standingsSource": SOURCE_LEAGUE_PUBLISHED if standings is not None else None,
            # Snapped: a 1.4e-14 residue is not a gap, and serving one invites a surface to
            # render "-0.00" beside two numbers that match.
            "itemisationGap": (None if standings is None
                               else _snap(total - float(standings))),
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
        # ⛔ RENDERED ADJACENT TO THE TOTAL, never as a panel or a footnote (MT1 ruling ③). None
        # when the league captures nothing, so a surface shows no disclosure rather than an empty
        # one — a caveat that fires on nothing is one readers learn to skip.
        "itemisationGapNote": itemisation_gap_note(coverage, max_gap=_max_gap(teams)),
        "standingsNote": (
            "Team totals and results are your league's own published figures. The slot breakdown "
            "is your league's scoring applied by us to the week's real stat line."
        ),
    }


def _snap(value: float) -> float:
    """Float noise -> exactly 0.0. See `GAP_EPSILON`."""
    return 0.0 if abs(value) <= GAP_EPSILON else value


def _max_gap(teams: list[dict]) -> float:
    """The largest |itemisation gap| over the week's teams — the input to the disclosure decision.

    Zero when no team has a standings total to compare against: without the league's own number
    there is no gap to claim, which is the same honest answer as a gap of zero.
    """
    gaps = [abs(t["itemisationGap"]) for t in teams if t.get("itemisationGap") is not None]
    return max(gaps) if gaps else 0.0


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
            "teams": [{"teamKey": s["teamKey"], "teamName": s["teamName"],
                       "standingsTotal": s["standingsTotal"], "itemisedTotal": s["itemisedTotal"]}
                      for s in side],
        }
        # ⭐ THE RESULT IS DECIDED ON THE LEAGUE'S OWN TOTAL, never on our itemisation. Deciding a
        # head-to-head on our sum could hand a user a DIFFERENT WINNER from their league page,
        # which is the worst available form of the disagreement this ruling exists to prevent.
        a_t = side[0]["standingsTotal"] if side else None
        b_t = side[1]["standingsTotal"] if len(side) == 2 else None
        if len(side) == 2 and a_t is not None and b_t is not None:
            a, b = side
            entry["winnerTeamKey"] = (
                None if a_t == b_t else (a if a_t > b_t else b)["teamKey"]
            )
            entry["tied"] = a_t == b_t
        elif len(side) == 2:
            # Named, never guessed: without the league's totals there is no result to report.
            entry["resultUnavailable"] = True
        else:
            # Named rather than silent: "we could not pair this" is a fact the surface may render.
            entry["unpaired"] = True
        out.append(entry)
    return out


#: A CAPTURED term → the realized column that would supply it, where one exists. This is what lets
#: a divergence be split into an EXPLAINED portion (arithmetic) and an UNEXPLAINED residual (the
#: future alert's clean signal).
#:
#: ⚠️ DELIBERATELY TINY, AND THAT IS THE HONEST STATE. `fum` is the only captured term whose value
#: this line can supply today. The three 40+ yard TD bonuses CANNOT be explained here — deriving
#: them needs `pbp`, and `passing_40` counts 40+ yard PLAYS rather than touchdowns, so mapping it
#: would be a wrong-key that scores silently (node 1 measured it exceeding the touchdown count).
#: A term absent from this map leaves its share in the UNEXPLAINED residual, which is the correct
#: place for it: unexplained means "we cannot account for this", not "this is wrong".
EXPLAINABLE_CAPTURED_TERMS: dict[str, str] = {
    "fum": "fumbles_total",
}


#: Lake columns a caller must ALSO select for the explained/unexplained split to work — DERIVED, so
#: teaching a new captured term widens the read automatically.
#:
#: ⚠️ THIS CONSTANT EXISTS BECAUSE ITS ABSENCE WAS A SILENT NO-OP. `fumbles_total` is not among the
#: columns `realized_stat_fields.REALIZED_STAT_COLUMNS` selects (the fumble term maps to the three
#: per-phase columns), so the first cut of the split ran with no input and reported `explained` as
#: 0.0 for every seat — the explanation mechanism was declared and never fed, which reads exactly
#: like "nothing is explainable" (the NF-C0e wired-≠-invoked shape). The tell was that UNEXPLAINED
#: equalled DIVERGING in all four measured weeks while closing `fum` demonstrably moved agreement
#: from 14/48 to 27/48.
EXPLANATION_COLUMNS: tuple[str, ...] = tuple(sorted(set(EXPLAINABLE_CAPTURED_TERMS.values())))


#: Below this, an itemisation gap is FLOAT NOISE, not a gap. A real one is at least a scoring
#: increment (the smallest weight in the catalog is 0.01/yard territory, i.e. ~1e-2); IEEE-754 error
#: accumulated over ~9 seats is ~1e-13. 1e-6 sits far below any real difference and far above the
#: noise, so the classification can never be close.
GAP_EPSILON = 1e-6


def itemisation_gap_note(coverage: dict, *, max_gap: float | None = None) -> str | None:
    """The sentence rendered ADJACENT to the total, naming the terms that explain the gap.

    ⛔ SPECIFIC, NEVER GENERIC (the ruling): "the coverage report already names which terms explain
    the gap, so the copy says so, never a vague 'totals may differ'." Built from the RESOLVED
    coverage rather than a constant, so a league that captures nothing gets no sentence at all and
    a league that captures something gets its OWN terms named.

    ⚠️⚠️ AND IT REQUIRES A MEASURED GAP, WHICH THE RUNTIME GATE IS WHAT TAUGHT US. The first cut
    keyed the note on the league CAPTURING a term, which is a statement about its SCORING and is
    always true once any term is captured. On the operator's real 2026 league the captured terms
    (fumble-recovery touchdowns, missed extra points, return touchdowns) simply DID NOT OCCUR in
    week 1, so the itemisation was exact — `138.36` against `138.35999999999999` — and the note
    still asserted "the slot points don't add up to the total above" directly beside two numbers a
    reader can see are the same.

    A caveat that contradicts the figures printed next to it is worse than no caveat: it spends the
    trust the disclosure exists to protect. The terms are still in `coverage` for anyone who wants
    them; what is withheld is the false CONSEQUENCE clause.

    `max_gap` is the largest |itemisedTotal − standingsTotal| over the week's teams. Passing None
    keeps the old unconditional behaviour for a caller that genuinely cannot measure it — but
    `score_week` always can, and does.
    """
    captured = sorted(
        t["key"] for t in (coverage.get("terms") or [])
        if t.get("verdict") == "captured" and abs(float(t.get("weight") or 0.0)) > 0
    )
    if not captured:
        return None
    # ⭐ NO MEASURED GAP ⇒ NO CLAIM OF ONE. See the docstring: the captured terms are real, but
    # whether they MOVED anything this week is a different fact, and only the second licenses the
    # "doesn't add up" sentence.
    if max_gap is not None and abs(max_gap) <= GAP_EPSILON:
        return None
    labels = {
        "fum": "fumbles", "pass_td_40p": "40+ yard passing TD bonuses",
        "rush_td_40p": "40+ yard rushing TD bonuses", "rec_td_40p": "40+ yard receiving TD bonuses",
        "fumble_rec_td": "fumble-recovery touchdowns", "pat_missed": "missed extra points",
        "st_player_td": "return touchdowns",
    }
    named = []
    for key in captured:
        label = labels.get(key)
        if label and label not in named:
            named.append(label)
    if not named:
        # ⚠️ Honest rather than silent: we know the gap has a cause and cannot name it in words yet.
        return ("This league scores terms our breakdown does not itemize yet, so the slot points "
                "below do not add up to the total above.")
    if len(named) == 1:
        subject = named[0]
    else:
        subject = ", ".join(named[:-1]) + " and " + named[-1]
    return (f"This league also scores {subject}, which the breakdown below doesn't itemize yet — "
            "so the slot points don't add up to the total above.")


def compare_to_platform(
    scored: dict,
    *,
    dst_constructed: dict[str, float] | None = None,
    dst_result_pending: set[str] | None = None,
    captured_weights: dict[str, float] | None = None,
    realized_by_seat: dict[tuple, dict] | None = None,
    tolerance: float = 1e-9,
) -> dict:
    """Our per-seat points vs the platform's own, with the two seat kinds reported SEPARATELY.

    ⛔ NO SEAT PAGES — EVERY SEAT RECORDS (PM amendment, 2026-09-16). The earlier design let player
    seats alert on the premise that they reproduce the platform exactly; that premise was MEASURED
    FALSE (6-20 of ~94 per week, every one explained by a captured term), so alerting on it would
    be the muted-monitor pattern on day one. `mayAlert` is False on both legs and is carried IN THE
    DATA so a caller cannot wire an alert by reading only the numbers.

    ⭐ THE SPLIT IS WHAT ALERTING COMES BACK ON. Where a captured term's value is computable
    (`EXPLAINABLE_CAPTURED_TERMS`), its arithmetic contribution is recorded as `explained` and the
    remainder as `unexplained`. The residual is the future alert's clean signal; the explained part
    is arithmetic and must never be mistaken for evidence.

    ⚠️ `dst_result_pending` NAMES THE DEFENCES WHOSE GAME RESULT `schedules` HAS NOT PUBLISHED YET
    (PM card yOhLHprC — the Monday 06:15 PT refresh lands BEFORE Monday Night Football). Those two
    defences every week are missing their points-allowed term through a KNOWN cadence defect, so
    their divergence is an artifact of someone else's schedule. They are TAGGED and counted in their
    own bucket rather than dropped: the fXIYuvMN residual reads `divergingUnexplained`, and nothing
    is hidden from a reader who wants the raw count.
    """
    player_div: list[dict] = []
    dst_div: list[dict] = []
    player_n = dst_n = 0
    dst_unavailable: list[dict] = []
    dst_pending: list[dict] = []
    player_unexplained: list[dict] = []
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
                rec["scheduleResultPending"] = key in (dst_result_pending or set())
                if abs(rec["delta"]) > tolerance:
                    dst_div.append(rec)
                    if rec["scheduleResultPending"]:
                        dst_pending.append(rec)
            else:
                player_n += 1
                # ⭐ SPLIT THE DELTA. `explained` is what a captured term arithmetically accounts
                # for: we did not apply the league's weight, so our number is higher by exactly
                # (−weight × count). Sign follows `ours − theirs`.
                explained = 0.0
                key = (team.get("teamKey"), seat.get("seat"))
                realized = (realized_by_seat or {}).get(key) or {}
                for term, column in EXPLAINABLE_CAPTURED_TERMS.items():
                    weight = float((captured_weights or {}).get(term) or 0.0)
                    if weight and realized.get(column) is not None:
                        explained += -weight * float(realized[column])
                rec["explained"] = explained
                rec["unexplained"] = delta - explained
                if abs(delta) > tolerance:
                    player_div.append(rec)
                    if abs(rec["unexplained"]) > tolerance:
                        player_unexplained.append(rec)
    return {
        "playerSeats": {
            "compared": player_n, "diverging": len(player_div), "rows": player_div,
            # ⭐ THE RESIDUAL AFTER CAPTURED TERMS ARE ACCOUNTED FOR — the quantity a future
            # term-by-term alert keys on, kept separate from the raw divergence count.
            "unexplained": len(player_unexplained), "unexplainedRows": player_unexplained,
            "expectation": "divergence_known_pending_captured_terms",
            # ⛔ Downgraded from True by the 2026-09-16 amendment — see the docstring.
            "mayAlert": False,
            "explainedBy": sorted(EXPLAINABLE_CAPTURED_TERMS),
        },
        "dstSeats": {
            "compared": dst_n, "diverging": len(dst_div), "rows": dst_div,
            # ⚠️ THE KNOWN-CAUSE SPLIT (PM card yOhLHprC). `divergingUnexplained` is what
            # fXIYuvMN's residual should be read from; `divergingScheduleResultPending` is the
            # MNF artifact, reported rather than removed so the raw count stays visible.
            "divergingScheduleResultPending": len(dst_pending),
            "scheduleResultPendingRows": dst_pending,
            "divergingUnexplained": len(dst_div) - len(dst_pending),
            "resultPendingSupplied": dst_result_pending is not None,
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


#: How the standings order is decided, SERVED so a reader can reproduce it by hand. The spec's
#: constraint was "any additional ranking signal ONLY if it is a transparent arithmetic of served
#: numbers — no opaque composite score", and this is deliberately the plainest thing that is also
#: what a league page shows: record first, points for as the tiebreak.
RANKING_BASIS = (
    "Ranked by win-loss-tie record, then by total points for. Both are your league's own published "
    "figures, so this order is the one your league page shows."
)

POWER_RANKINGS_NOTE = (
    "Records and points here are your league's own published totals for each completed week."
)


def power_rankings(weeks: list[dict]) -> dict:
    """Standings accumulated across completed weeks, from the LEAGUE'S OWN totals.

    `weeks` are `score_week` outputs. ⛔ ONLY weeks whose result the league actually published are
    counted, and `weeksIncluded` says which — a week silently dropped for a missing total would
    make the record wrong with no way for a reader to notice.

    ⚠️ A team with NO standings total in a week is skipped FOR THAT WEEK rather than scored zero: a
    zero is a loss it did not necessarily suffer, and the ruling is explicit that a platform we
    cannot read has no standings rather than approximate ones.
    """
    acc: dict[str, dict] = {}
    included: list[int] = []
    for wk in weeks:
        week_no = wk.get("week")
        totals = {
            t["teamKey"]: t for t in wk.get("teams") or []
            if t.get("standingsTotal") is not None
        }
        counted = False
        for m in wk.get("matchups") or []:
            side = [totals.get(str(t.get("teamKey"))) for t in m.get("teams") or []]
            if len(side) != 2 or any(x is None for x in side):
                continue
            a, b = side
            for me, them in ((a, b), (b, a)):
                row = acc.setdefault(me["teamKey"], {
                    "teamKey": me["teamKey"], "teamName": me.get("teamName") or "",
                    "wins": 0, "losses": 0, "ties": 0,
                    "pointsFor": 0.0, "pointsAgainst": 0.0, "weeksCounted": 0,
                })
                row["teamName"] = me.get("teamName") or row["teamName"]
                row["pointsFor"] += float(me["standingsTotal"])
                row["pointsAgainst"] += float(them["standingsTotal"])
                row["weeksCounted"] += 1
                if me["standingsTotal"] > them["standingsTotal"]:
                    row["wins"] += 1
                elif me["standingsTotal"] < them["standingsTotal"]:
                    row["losses"] += 1
                else:
                    row["ties"] += 1
            counted = True
        if counted and week_no is not None:
            included.append(int(week_no))

    rows = sorted(
        acc.values(),
        key=lambda r: (-(r["wins"] + 0.5 * r["ties"]), -r["pointsFor"], r["teamName"]),
    )
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return {
        "rows": rows,
        "weeksIncluded": sorted(included),
        "throughWeek": max(included) if included else 0,
        "rankingBasis": RANKING_BASIS,
        "standingsNote": POWER_RANKINGS_NOTE,
    }

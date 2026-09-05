"""team_payloads.py — NCAAF-P3.3: PURE builders from mart/lake rows to the served TEAM page.

The sibling of `payloads.py` and held to the same discipline: no boto3, no lake read, no DuckDB
connection, no clock of its own. The IO lives in `scripts/write_ncaaf_serving_store.py`, so every
shape decision here is exercisable without touching AWS — which matters more than usual, because
CI mocks all IO and a builder entangled with its reader is a builder nothing can actually run.

It is a SEPARATE MODULE rather than more of `payloads.py` for one reason and it is not file size:
the two answer to different sources with different availability. `payloads.py` reads the NCAAF-PS
snapshot lake and is HALT-tier serving-critical; this reads the P1.1 dbt marts plus the P1.2
strength lake, and is ALERT-tier enrichment that must never be able to cost the game board. Keeping
them apart makes that tiering legible instead of a comment. The VALUE-COERCION helpers are IMPORTED
from `payloads` rather than re-written — two rule sets for "what is a null" is exactly the drift
E9.61 names, and `_f` in particular carries the honest-NaN-is-NULL rule this whole vertical rests on.

WHAT IT SERVES, AND FROM WHERE
------------------------------
  * strength + posterior band  ← `ncaaf/derived/team_strength_week` (P1.2, the LAKE)
  * opponent-adjusted efficiency ← `rollup_ncaaf_team_week_opponent_adjusted` (P1.1 mart)
  * trench + pace splits       ← `rollup_ncaaf_team_week_asof`               (P1.1 mart)
  * schedule + results         ← `dim_ncaaf_game`                            (P1.1 mart)
  * identity + CONFERENCE      ← `dim_ncaaf_team`, read POINT-IN-TIME        (P1.1 SCD-2 dim)

⭐ FOUR SOURCES, FOUR AVAILABILITIES, AND THAT IS THE DESIGN. On the Saturday of week 1 a CORRECT
page has a strength rating (a zero-game row is a real pre-season posterior, not a gap), a full
schedule (the roll-forward landed it in July), and three blocks that are structurally empty because
nobody has played yet. Rendering that identically to "our mart build failed" would cost an
investigation every September (NF-C6b / NF-K1), so each block carries its own `status` + machine-
readable `reason` and the causes are kept apart.

⛔ NOTHING IS RE-DERIVED AND NOTHING IS DEFAULTED TO ZERO. Every number is copied off the row that
owns it; a NaN becomes `null`. A fabricated 0.0 is a wrong number wearing the costume of a
measurement, and on a page whose entire claim is "here is the uncertainty" that is the one thing it
must not do.

🚨 SIGN CONVENTION (`ncaaf_team_strength_week`'s own, restated because it is easy to get backwards):
`strength_offense` and `strength_defense` are BOTH higher-is-better — defense is points PREVENTED.
Net strength is their SUM, and `strength_margin` is the number to read. `offense − defense` returns
approximately zero for every team in the league.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from app.backend.models import ncaaf as contract
from quant_sports_intel_models.football.ncaaf.serving.payloads import (
    _b,
    _f,
    _i,
    _iso_now,
    _s,
    game_day_for,
)

log = logging.getLogger("ncaaf.serving.team_payloads")

#: `status`/`reason` vocabulary, re-exported from the contract so the writer, the builder and the
#: guards all name the same strings (a second literal is a second rule set — E9.61).
REASON_NO_GAMES = contract.TEAM_BLOCK_REASON_NO_GAMES
REASON_NOT_BUILT = contract.TEAM_BLOCK_REASON_NOT_BUILT
REASON_NO_ROW = contract.TEAM_BLOCK_REASON_NO_ROW

#: How `NcaafTeamIdentity.conference_source` names where the conference came from.
CONFERENCE_SOURCE_DIM = "scd2_dim"
CONFERENCE_SOURCE_MODEL_INPUT = "model_input"


def _rows(frame: "pd.DataFrame | None") -> list[dict]:
    """A DataFrame as records, tolerating None/empty. Never raises on an absent source."""
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict("records")


def _latest_by_week(rows: Sequence[Mapping[str, Any]]) -> dict | None:
    """The row with the largest `as_of_week`, or None.

    ⚠️ Taken by comparing the WEEK, never by trusting row order — a DuckDB read's ordering is not a
    guarantee, and "the last row" silently becomes "an arbitrary row" the first time a mart's
    materialization changes.
    """
    best, best_week = None, None
    for row in rows:
        week = _i(row.get("as_of_week"))
        if week is None:
            continue
        if best_week is None or week > best_week:
            best, best_week = row, week
    return best


def _rollup_absence(*, marts_available: bool, has_any_row: bool) -> tuple[str, str]:
    """`(status, reason)` for an empty P1.1 ROLLUP block — the three causes, kept apart.

    ⭐ THE DISTINCTION IS THE WHOLE POINT OF THE FIELD. `source_marts_unavailable` is a DEFECT (our
    build did not run); `no_games_played_yet` is the CORRECT state of week 1 and needs no action;
    `no_row_for_this_team_and_season` means the rollup was readable and simply has nothing for this
    (team, season). A surface handed one blank for all three re-investigates the same symptom
    every September.

    ⚠️ `has_any_row` MAPS THE WAY IT READS, and the first cut had it BACKWARDS. Rows PRESENT but
    none with a game behind them is the literal statement "no games played yet" — the rollup
    emitted this team's weeks and each is a rollup of nothing. Rows ABSENT is the other fact
    entirely: the mart was readable and holds no week for this team and season at all, which on an
    in-progress season means it has not been rebuilt that far. Inverting them names the wrong cause
    with total confidence, which is worse than a bare null because it reads as a considered answer.

    ⛔ ROLLUPS ONLY. A SCHEDULE cannot be absent for "no games played yet" — it exists from the
    moment the season rolls forward — so `build_schedule` deliberately does not call this. The
    vocabulary is shared; its APPLICABILITY is not.
    """
    if not marts_available:
        return "unavailable", REASON_NOT_BUILT
    return "unavailable", (REASON_NO_GAMES if has_any_row else REASON_NO_ROW)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Identity — and the realignment resolution, which is the AC this story is graded on
# ══════════════════════════════════════════════════════════════════════════════════════════

def build_identity(*, team_id: int, season: int,
                   dim_row: Mapping[str, Any] | None,
                   prior_season_dim_row: Mapping[str, Any] | None,
                   strength_row: Mapping[str, Any] | None) -> dict:
    """Who the team is AS OF `season`, with the conference resolved point-in-time.

    ⭐ WHY THE SCD-2 DIM AND NOT THE HANDIEST ROW. Eleven FBS programs changed conference for 2026 —
    the Pac-12 rebuild took Boise State, Colorado State, Fresno State, San Diego State, Utah State
    and Texas State; UTEP and Northern Illinois moved to the Mountain West; Louisiana Tech to the
    Sun Belt — and Sacramento State and North Dakota State joined FBS outright. A "current"
    conference read would rewrite history for every prior season, and a stale one would file a 2026
    mover under its 2025 league on the page whose job is to say who they play. `dim_ncaaf_team`
    versions the conference by season precisely so this is a lookup rather than a judgement call.

    ⭐ AND THE MODEL'S OWN CONFERENCE IS CROSS-CHECKED, NOT ASSUMED. `ncaaf_team_strength_week`
    carries a conference too — it is the pooling level the posterior was shrunk toward, derived
    independently upstream. Agreement is the ordinary case; a DISAGREEMENT is a real finding about
    the model's inputs (the team was pooled into a conference it does not play in), so it is
    RECORDED on the payload rather than silently resolved in the dim's favour.

    `is_new_to_fbs` is True only when the team has NO prior-season dim row — a first-year FBS
    program whose pre-season covariates are absent BY CONSTRUCTION. Saying so keeps a reader (and a
    later story) from reading a structural absence as a data defect.
    """
    dim_conf = _s((dim_row or {}).get("conference"))
    model_conf = _s((strength_row or {}).get("conference"))

    if dim_conf is not None:
        conference, source = dim_conf, CONFERENCE_SOURCE_DIM
    elif model_conf is not None:
        # The dim had no row for this season. Serving the model's pooling level is better than
        # serving nothing, but it must SAY it is a different resolution — the two can disagree.
        conference, source = model_conf, CONFERENCE_SOURCE_MODEL_INPUT
    else:
        conference, source = None, None

    matches = None if (dim_conf is None or model_conf is None) else (dim_conf == model_conf)
    if matches is False:
        log.warning(
            "[ALERT] NCAAF team %s (%s) season %s: the SCD-2 dim says conference=%r while the P1.2 "
            "strength row was pooled under %r. Serving the dim's answer and recording the "
            "disagreement — the posterior was shrunk toward a conference this team does not play "
            "in, which is a finding about the model's inputs, not a display problem.",
            team_id, _s((dim_row or {}).get("team")) or _s((strength_row or {}).get("team")),
            season, dim_conf, model_conf)

    return {
        "team_id": int(team_id),
        "team": _s((dim_row or {}).get("team")) or _s((strength_row or {}).get("team")),
        "season": int(season),
        "conference": conference,
        "conference_division": _s((dim_row or {}).get("conference_division")),
        "classification": _s((dim_row or {}).get("classification")),
        "conference_source": source,
        "conference_matches_model_input": matches,
        "abbreviation": _s((dim_row or {}).get("abbreviation")),
        "mascot": _s((dim_row or {}).get("mascot")),
        "venue_name": _s((dim_row or {}).get("venue_name")),
        "venue_city": _s((dim_row or {}).get("venue_city")),
        "venue_state": _s((dim_row or {}).get("venue_state")),
        # ⚠️ Only claimable when we actually looked: with no dim row for THIS season we cannot tell
        # a first-year program from a team the dim is simply missing, and `False` would be a
        # fabricated answer (NF1.7 (a) — a check that did not run is not a pass).
        "is_new_to_fbs": None if dim_row is None else (prior_season_dim_row is None),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════
# The blocks
# ══════════════════════════════════════════════════════════════════════════════════════════

def _strength_week(row: Mapping[str, Any]) -> dict:
    return {
        "as_of_week": _i(row.get("as_of_week")),
        "games_in_window": _i(row.get("games_in_window")),
        "has_sufficient_sample": _b(row.get("has_sufficient_sample")),
        "strength_margin": _f(row.get("strength_margin")),
        "strength_margin_sd": _f(row.get("strength_margin_sd")),
        "strength_conference_component": _f(row.get("strength_conference_component")),
        "strength_covariate_component": _f(row.get("strength_covariate_component")),
        "strength_team_component": _f(row.get("strength_team_component")),
        "strength_offense": _f(row.get("strength_offense")),
        "strength_offense_sd": _f(row.get("strength_offense_sd")),
        "strength_defense": _f(row.get("strength_defense")),
        "strength_defense_sd": _f(row.get("strength_defense_sd")),
    }


def build_strength(rows: Sequence[Mapping[str, Any]], *, strength_available: bool = True,
                   ratings_as_of: str | None = None,
                   ratings_next_update: str | None = None) -> dict:
    """The P1.2 block: the current week's posterior plus the season's week-by-week series.

    ⚠️ THE BAND IS NOT OPTIONAL. At `as_of_week` 1 nothing has been played and the posterior IS the
    prior — the rating is real and the sd is wide (~7 points on the 2026 opener). Serving the
    rating without `strength_margin_sd` would publish a precision the model does not claim, which
    on this vertical is exactly the line between context and a pick.
    """
    # ⭐ ONE OWNER FOR "WHICH WEEK IS CURRENT", and it was not free. The first cut derived `current`
    # from `weeks[-1]` (the sorted series) while the fit-level context below came from
    # `_latest_by_week(rows)` — two selections of the same thing, free to disagree the moment one
    # changed, and the RED proof caught it exactly that way: breaking `_latest_by_week` left the
    # clause GREEN because nothing the clause read went through it (the E9.61 two-renderers class,
    # inside one function).
    latest_raw = _latest_by_week(rows)
    if latest_raw is None:
        return {
            "status": "unavailable",
            "reason": REASON_NO_ROW if strength_available else REASON_NOT_BUILT,
            "as_of_week": None, "current": None, "weeks": [],
            "league_base_points": None, "home_field_advantage": None, "residual_sigma": None,
            "model_version": None, "hyper_n_prior_seasons": None,
            # ⭐ CARRIED ON THE UNAVAILABLE BRANCH TOO (NCAAF-P3.3b). "when were the ratings last
            # written" has an answer even on a page whose posterior could not be read, and the two
            # absences are different facts: a block with no rating still has a lake behind it.
            "ratings_as_of": ratings_as_of, "ratings_next_update": ratings_next_update,
        }
    weeks = [_strength_week(r) for r in rows if _i(r.get("as_of_week")) is not None]
    weeks.sort(key=lambda w: w["as_of_week"])
    current = _strength_week(latest_raw)
    return {
        "status": "available", "reason": None,
        "as_of_week": current["as_of_week"],
        "current": current,
        "weeks": weeks,
        # ...and the fit-level context comes off THAT SAME ROW, so a page cannot quote one
        # week's rating against another week's league baseline.
        "league_base_points": _f(latest_raw.get("league_base_points")),
        "home_field_advantage": _f(latest_raw.get("home_field_advantage")),
        "residual_sigma": _f(latest_raw.get("residual_sigma")),
        "model_version": _s(latest_raw.get("model_version")),
        "hyper_n_prior_seasons": _i(latest_raw.get("hyper_n_prior_seasons")),
        # ⚠️ NOT read off `latest_raw`. The vintage is a property of the ARTIFACT, not of a row —
        # the posterior carries no timestamp column, and inventing one from `as_of_week` would turn
        # a week index into a date it does not mean. It is passed in from the writer, which reads
        # the Delta commit log (`ncaaf_ratings_vintage`).
        "ratings_as_of": ratings_as_of,
        "ratings_next_update": ratings_next_update,
    }


def build_efficiency(rows: Sequence[Mapping[str, Any]], *, marts_available: bool) -> dict:
    """Opponent-adjusted efficiency at the newest as-of week that has games behind it.

    ⚠️ A ZERO-GAME ROW IS NOT AN EFFICIENCY. `rollup_ncaaf_team_week_asof` emits a week-1 row whose
    every rate is NULL (a rollup of nothing is unknown — the deliberate contrast with the strength
    posterior, where a zero-game row is the prior). So the newest row is taken from rows with
    `games_played > 0`; where none exists the block is honestly `no_games_played_yet` rather than a
    row of nulls wearing `status: available`.
    """
    played = [r for r in rows if (_i(r.get("games_played")) or 0) > 0]
    row = _latest_by_week(played)
    if row is None:
        status, reason = _rollup_absence(marts_available=marts_available, has_any_row=bool(rows))
        return {"status": status, "reason": reason, "as_of_week": None, "games_played": None,
                **{k: None for k in (
                    "adj_off_ppa", "adj_def_ppa", "adj_net_ppa", "adj_off_success_rate",
                    "adj_def_success_rate", "adj_points_for_per_game",
                    "adj_points_against_per_game", "raw_off_ppa", "raw_def_ppa",
                    "raw_off_success_rate", "raw_def_success_rate", "raw_points_for_per_game",
                    "raw_points_against_per_game", "sos_opponent_net_ppa", "opponents_counted",
                    "adjustment_applied", "has_reliable_adjustment")}}
    return {
        "status": "available", "reason": None,
        "as_of_week": _i(row.get("as_of_week")),
        "games_played": _i(row.get("games_played")),
        "adj_off_ppa": _f(row.get("adj_off_ppa")),
        "adj_def_ppa": _f(row.get("adj_def_ppa")),
        "adj_net_ppa": _f(row.get("adj_net_ppa")),
        "adj_off_success_rate": _f(row.get("adj_off_success_rate")),
        "adj_def_success_rate": _f(row.get("adj_def_success_rate")),
        "adj_points_for_per_game": _f(row.get("adj_points_for_per_game")),
        "adj_points_against_per_game": _f(row.get("adj_points_against_per_game")),
        "raw_off_ppa": _f(row.get("raw_off_ppa")),
        "raw_def_ppa": _f(row.get("raw_def_ppa")),
        "raw_off_success_rate": _f(row.get("raw_off_success_rate")),
        "raw_def_success_rate": _f(row.get("raw_def_success_rate")),
        "raw_points_for_per_game": _f(row.get("raw_points_for_per_game")),
        "raw_points_against_per_game": _f(row.get("raw_points_against_per_game")),
        "sos_opponent_net_ppa": _f(row.get("sos_opponent_net_ppa")),
        "opponents_counted": _i(row.get("opponents_counted")),
        "adjustment_applied": _b(row.get("adjustment_applied")),
        "has_reliable_adjustment": _b(row.get("has_reliable_adjustment")),
    }


_SPLIT_FIELDS = (
    "off_line_yards", "def_line_yards", "off_stuff_rate", "def_stuff_rate",
    "off_plays_per_game", "possession_seconds_per_game", "points_per_drive",
    "scoring_opportunity_rate", "three_and_out_rate", "explosive_drive_rate",
    "avg_start_yards_to_goal", "off_explosiveness", "def_explosiveness",
)


def build_splits(rows: Sequence[Mapping[str, Any]], *, marts_available: bool) -> dict:
    """Trench (line yards, stuff rate) and pace (plays, drives, possession, points per drive).

    Same zero-game rule as `build_efficiency`, for the same reason: the week-1 rollup row exists and
    is entirely null, and `status: available` over a row of nulls is the blank-cell render this
    contract exists to prevent.
    """
    played = [r for r in rows if (_i(r.get("games_played")) or 0) > 0]
    row = _latest_by_week(played)
    if row is None:
        status, reason = _rollup_absence(marts_available=marts_available, has_any_row=bool(rows))
        return {"status": status, "reason": reason, "as_of_week": None, "games_played": None,
                "drives": None, **{k: None for k in _SPLIT_FIELDS}}
    return {
        "status": "available", "reason": None,
        "as_of_week": _i(row.get("as_of_week")),
        "games_played": _i(row.get("games_played")),
        "drives": _i(row.get("drives")),
        **{k: _f(row.get(k)) for k in _SPLIT_FIELDS},
    }


def _instant_iso(value: Any) -> str | None:
    """A kickoff instant as UTC ISO-8601, or None.

    ⚠️ `dim_ncaaf_game.start_date` is a NAIVE timestamp that HOLDS UTC — `stg_ncaaf_games` casts
    CFBD's `startDate` (a UTC instant) straight to `timestamp`, dropping the marker but not shifting
    the value. Verified against the served game board: game 401864577 reads 21:30 in the mart and
    `2026-08-29T21:30:00.000Z` on `/ncaaf/games`. So localising to UTC is a re-labelling of a value
    that was already UTC, not a conversion — and stating that here is what stops a later reader
    "fixing" it into a real shift (the LTZ/NTZ class this repo has produced four separate bugs from).
    """
    ts = pd.to_datetime(value, errors="coerce")
    if ts is pd.NaT or pd.isna(ts):
        return None
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _schedule_game(row: Mapping[str, Any], *, team_id: int) -> dict | None:
    """One `dim_ncaaf_game` row, oriented to `team_id`. None when the team is not in it."""
    home_id, away_id = _i(row.get("home_team_id")), _i(row.get("away_team_id"))
    if team_id == home_id:
        is_home = True
    elif team_id == away_id:
        is_home = False
    else:
        return None

    side, opp = ("home", "away") if is_home else ("away", "home")
    completed = _b(row.get("is_completed"))
    team_pts = _i(row.get(f"{side}_points"))
    opp_pts = _i(row.get(f"{opp}_points"))

    # ⛔ A SCORE ONLY EXISTS WHEN THE GAME WAS PLAYED. An upcoming fixture carries nulls, never
    # zeroes: 0-0 beside next Saturday's opponent reads as a played scoreless game.
    if not completed or team_pts is None or opp_pts is None:
        team_pts = opp_pts = margin = result = None
    else:
        margin = team_pts - opp_pts
        result = "W" if margin > 0 else ("L" if margin < 0 else "T")

    return {
        "game_id": int(row["game_id"]),
        # ⛔ NOT `dim_ncaaf_game.game_date`. That column is `start_date::date`, i.e. the UTC date,
        # so a 03:30-UTC kickoff lands on the wrong calendar day for every US timezone — INC-22, on
        # exactly the games (Saturday night) a college surface most needs to place correctly.
        # `game_day_for` is the SAME conversion `payloads.py` applies to the game board, so the two
        # payloads agree about a game rather than each computing its own answer (E9.61).
        "game_day": game_day_for(row.get("start_date")),
        "commence_time": _instant_iso(row.get("start_date")),
        "season_type": _s(row.get("season_type")),
        "is_postseason": _b(row.get("is_postseason")),
        "is_home": is_home,
        "is_neutral_site": _b(row.get("is_neutral_site")),
        "is_conference_game": _b(row.get("is_conference_game")),
        "is_fbs_matchup": _b(row.get("is_fbs_matchup")),
        "opponent_team_id": _i(row.get(f"{opp}_team_id")),
        "opponent": _s(row.get(f"{opp}_team")),
        "opponent_conference": _s(row.get(f"{opp}_conference")),
        "venue_name": _s(row.get("venue_name")),
        "is_completed": completed,
        "team_points": team_pts,
        "opponent_points": opp_pts,
        "margin": margin,
        "result": result,
    }


def build_schedule(rows: Sequence[Mapping[str, Any]], *, team_id: int,
                   marts_available: bool) -> dict:
    """The season's games in date order, with played/upcoming stated as counts.

    ⭐ THE RECORD IS COUNTED FROM THE PLAYED GAMES ONLY. Deriving it any other way — from a stored
    wins column, say — would make "3-0 through three games" and "3-0 with nine still to play" the
    same statement, and this page's job on a September Saturday is precisely to keep those apart.
    """
    games = [g for g in (_schedule_game(r, team_id=team_id) for r in rows) if g is not None]
    if not games:
        # ⛔ NOT `_rollup_absence`, and the difference is a real one rather than tidiness.
        # `no_games_played_yet` is the CORRECT reason for a rollup — a rollup of nothing is
        # unknown — but it is a WRONG statement about a SCHEDULE: a schedule exists from the
        # moment the season rolls forward, months before anyone plays. An empty one means the
        # mart has no rows for this team and season (a team we do not have a fixture list for),
        # or the mart could not be read at all. Saying "no games played yet" here would name the
        # wrong fact, which is precisely what these reasons exist to prevent.
        reason = REASON_NOT_BUILT if not marts_available else REASON_NO_ROW
        return {"status": "unavailable", "reason": reason, "n_games": 0, "n_completed": 0,
                "n_upcoming": 0, "wins": None, "losses": None, "ties": None, "games": []}
    # Date order, with the game id as a stable tie-break for a double-header-shaped date collision.
    games.sort(key=lambda g: (g.get("commence_time") or g.get("game_day") or "", g["game_id"]))
    played = [g for g in games if g["result"] is not None]
    return {
        "status": "available", "reason": None,
        "n_games": len(games),
        "n_completed": len(played),
        "n_upcoming": len(games) - len(played),
        "wins": sum(1 for g in played if g["result"] == "W"),
        "losses": sum(1 for g in played if g["result"] == "L"),
        "ties": sum(1 for g in played if g["result"] == "T"),
        "games": games,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════
# The page
# ══════════════════════════════════════════════════════════════════════════════════════════

def build_team_payload(*, team_id: int, season: int,
                       strength_rows: Sequence[Mapping[str, Any]] = (),
                       efficiency_rows: Sequence[Mapping[str, Any]] = (),
                       splits_rows: Sequence[Mapping[str, Any]] = (),
                       schedule_rows: Sequence[Mapping[str, Any]] = (),
                       dim_row: Mapping[str, Any] | None = None,
                       prior_season_dim_row: Mapping[str, Any] | None = None,
                       marts_available: bool = True,
                       strength_available: bool = True,
                       ratings_as_of: str | None = None,
                       ratings_next_update: str | None = None,
                       now: datetime | None = None) -> dict:
    """One team's served page (a plain dict, validated through the Pydantic contract).

    Validating INSIDE the builder — not only at the router — is what makes the E9.41 guarantee
    two-sided: a field the writer forgets fails the WRITE, rather than being discovered missing on
    a surface weeks later with the data correct in the store the whole time.
    """
    strength_latest = _latest_by_week(strength_rows) or {}
    payload = {
        "sport": "ncaaf",
        "season": int(season),
        "generated_at": _iso_now(now),
        "team": build_identity(team_id=team_id, season=season, dim_row=dim_row,
                               prior_season_dim_row=prior_season_dim_row,
                               strength_row=strength_latest),
        "strength": build_strength(strength_rows, strength_available=strength_available,
                                   ratings_as_of=ratings_as_of,
                                   ratings_next_update=ratings_next_update),
        "efficiency": build_efficiency(efficiency_rows, marts_available=marts_available),
        "splits": build_splits(splits_rows, marts_available=marts_available),
        "schedule": build_schedule(schedule_rows, team_id=team_id,
                                   marts_available=marts_available),
        "provenance": {
            "model_version": _s(strength_latest.get("model_version")),
            "model_form": "strength_posterior",
            "model_learner": None,
            "model_contract": None,
            "mean_artifact_version": None,
            "strength_as_of_week": _i(strength_latest.get("as_of_week")),
            "pace_term_active": None,
            "n_draws": None,
            "snapshot_ts": None,
            "snapshot_kind": None,
        },
        "framing": contract.NcaafHonestFraming().model_dump(),
    }
    return contract.NcaafTeamPage.model_validate(payload).model_dump()


# ══════════════════════════════════════════════════════════════════════════════════════════
# Standings — where a rating places a team, and how sure that placement is
# ══════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐⭐ WHY THIS IS A MONTE CARLO AND NOT A SORT.
#
# Sorting 138 ratings gives a rank in one line. It also publishes a number that is very nearly
# noise in September and says nothing about it. Measured on the live 2026 week-1 board — 138 teams,
# every posterior sd ≈ 7.3 against a rating range of −25.9 to +21.2 — the MEDIAN team's 80% rank
# range spans 77 of 138 places, and 130 of 138 span more than 40. Boise State ranks 42nd on the
# point estimate and 18th–97th once its own published spread is taken seriously.
#
# So the rank and the range are computed TOGETHER, from the same draws, and the contract makes the
# range non-optional (`NcaafTeamStanding`). The alternative considered and rejected was refusing to
# rank at all: correct in week 1, wrong by week 10, because the width is a function of a posterior
# sd that shrinks as games are played. Rank-with-range is right in both.
#
# ⛔ IT COMPUTES NO MODEL QUANTITY. Every input is a number already served on the same block — this
# is an ordering of the P1.2 posterior, not a new estimate of anything, so there is no selection to
# deflate and no §0.5 bake-off implied. It is the same line `distribution-curve.tsx` draws between
# rendering a served distribution and re-deriving one.
#
# ⚠️ IT READS THE FINISHED BLOBS, DELIBERATELY. Ranking off the raw strength frame would be a
# SECOND selection of "this team's current rating" living beside `build_strength`'s, free to
# disagree the moment one changed — the two-renderers class (E9.61) that `build_strength`'s own
# header records paying for once already. Reading the blob means the rank is an ordering of exactly
# the numbers the page displays, and cannot drift from them.

#: Draws per team. 20k puts the Monte-Carlo error on a rank percentile well under one place, which
#: is the resolution the field is reported at; the whole pass is ~2.8M normals for a full FBS board.
STANDING_DRAWS = 20_000

#: ⛔ FIXED, and it must stay fixed. The serving store is rewritten daily, and an unseeded draw
#: would jiggle every team's published rank range by a place or two on every write with nothing in
#: the model having changed — indistinguishable, to a reader or to a diff, from a real movement.
STANDING_SEED = 20260903


def _standing(*, scope: str, scope_label: str | None, rank: int | None,
              rank_lo: int | None, rank_hi: int | None, n_ranked: int) -> dict:
    return {
        "scope": scope,
        "scope_label": scope_label,
        "rank": rank,
        "rank_lo": rank_lo,
        "rank_hi": rank_hi,
        "n_ranked": n_ranked,
        "interval_lo_level": contract.TEAM_STANDING_INTERVAL_LO_LEVEL,
        "interval_hi_level": contract.TEAM_STANDING_INTERVAL_HI_LEVEL,
    }


def attach_standings(payloads: Mapping[int, dict]) -> Mapping[int, dict]:
    """Write `standing_fbs` / `standing_conference` onto each blob's strength block, in place.

    A team is RANKABLE when its strength block is available and carries a finite rating and a
    finite positive spread. Everything else — a team whose posterior did not build, a conference
    with one rankable member — gets `None` rather than a fabricated placement: a rank of 1 of 1 is
    not a standing, and an absent one must stay visibly absent (NF-C6b).
    """
    import numpy as np

    ranked: list[tuple[int, float, float, str | None]] = []
    for tid, blob in payloads.items():
        strength = blob.get("strength") or {}
        if strength.get("status") != "available":
            continue
        current = strength.get("current") or {}
        mu, sd = current.get("strength_margin"), current.get("strength_margin_sd")
        if not isinstance(mu, (int, float)) or not isinstance(sd, (int, float)):
            continue
        if not (math.isfinite(mu) and math.isfinite(sd)) or sd <= 0:
            continue
        conference = ((blob.get("team") or {}).get("conference")) or None
        ranked.append((tid, float(mu), float(sd), conference))

    # ⛔ TWO IS THE FLOOR FOR AN ORDERING. One team ranked first of one says nothing at all.
    if len(ranked) < 2:
        return payloads

    ids = [r[0] for r in ranked]
    mu = np.array([r[1] for r in ranked], dtype=float)
    sd = np.array([r[2] for r in ranked], dtype=float)
    confs = [r[3] for r in ranked]
    n = len(ids)

    draws = np.random.default_rng(STANDING_SEED).normal(mu, sd, size=(STANDING_DRAWS, n))
    lo_pct = contract.TEAM_STANDING_INTERVAL_LO_LEVEL * 100.0
    hi_pct = contract.TEAM_STANDING_INTERVAL_HI_LEVEL * 100.0

    def _ranks_for(cols: Sequence[int]) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
        """Point rank (by the served rating) and the rank range (from the draws), for a sub-population."""
        sub_mu = mu[list(cols)]
        # 1 = best. `argsort().argsort()` on the NEGATED values turns an ordering into a rank.
        point = (-sub_mu).argsort().argsort() + 1
        sub = draws[:, list(cols)]
        sub_ranks = (-sub).argsort(axis=1).argsort(axis=1) + 1
        lo = np.percentile(sub_ranks, lo_pct, axis=0)
        hi = np.percentile(sub_ranks, hi_pct, axis=0)
        k = len(cols)
        return (
            {cols[i]: int(point[i]) for i in range(k)},
            {cols[i]: int(min(max(round(float(lo[i])), 1), k)) for i in range(k)},
            {cols[i]: int(min(max(round(float(hi[i])), 1), k)) for i in range(k)},
        )

    all_cols = list(range(n))
    fbs_point, fbs_lo, fbs_hi = _ranks_for(all_cols)
    for i, tid in enumerate(ids):
        payloads[tid]["strength"]["standing_fbs"] = _standing(
            scope="fbs", scope_label="FBS", rank=fbs_point[i],
            rank_lo=fbs_lo[i], rank_hi=fbs_hi[i], n_ranked=n,
        )

    by_conf: dict[str, list[int]] = {}
    for i, conference in enumerate(confs):
        if conference:
            by_conf.setdefault(conference, []).append(i)
    for conference, cols in by_conf.items():
        if len(cols) < 2:
            continue
        c_point, c_lo, c_hi = _ranks_for(cols)
        for i in cols:
            payloads[ids[i]]["strength"]["standing_conference"] = _standing(
                scope="conference", scope_label=conference, rank=c_point[i],
                rank_lo=c_lo[i], rank_hi=c_hi[i], n_ranked=len(cols),
            )
    return payloads


def build_team_payloads(*, season: int,
                        strength: "pd.DataFrame | None",
                        efficiency: "pd.DataFrame | None" = None,
                        splits: "pd.DataFrame | None" = None,
                        schedule: "pd.DataFrame | None" = None,
                        team_dim: "pd.DataFrame | None" = None,
                        prior_team_dim: "pd.DataFrame | None" = None,
                        marts_available: bool = True,
                        ratings_as_of: str | None = None,
                        ratings_next_update: str | None = None,
                        now: datetime | None = None) -> dict[int, dict]:
    """`{team_id: blob}` for every FBS team the season knows about.

    ⭐ THE UNIVERSE IS THE UNION OF THE STRENGTH TABLE AND THE SEASON'S DIM, not the intersection.
    Both are legitimate on their own: the P1.2 fit emits a row for every team it modelled, and the
    dim knows every team the season rolled forward. Intersecting would silently drop a team from
    the site the moment one of the two lagged the other, which is exactly the failure a page
    promising "any FBS team" must not have.
    """
    strength_rows = _rows(strength)
    dim_rows = _rows(team_dim)
    prior_rows = _rows(prior_team_dim)

    by_team_strength: dict[int, list[dict]] = {}
    for row in strength_rows:
        tid = _i(row.get("team_id"))
        if tid is not None:
            by_team_strength.setdefault(tid, []).append(row)

    dim_by_team = {t: r for r in dim_rows if (t := _i(r.get("team_id"))) is not None}
    prior_by_team = {t: r for r in prior_rows if (t := _i(r.get("team_id"))) is not None}

    def _group(frame, key="team_id") -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        for row in _rows(frame):
            tid = _i(row.get(key))
            if tid is not None:
                out.setdefault(tid, []).append(row)
        return out

    eff_by_team = _group(efficiency)
    splits_by_team = _group(splits)

    # A game belongs to BOTH of its teams' schedules — one pass, two appends, rather than a scan
    # of the whole season per team.
    sched_by_team: dict[int, list[dict]] = {}
    for row in _rows(schedule):
        for side in ("home_team_id", "away_team_id"):
            tid = _i(row.get(side))
            if tid is not None:
                sched_by_team.setdefault(tid, []).append(row)

    universe = sorted(set(by_team_strength) | set(dim_by_team))
    payloads = {
        tid: build_team_payload(
            team_id=tid, season=season,
            strength_rows=by_team_strength.get(tid, ()),
            efficiency_rows=eff_by_team.get(tid, ()),
            splits_rows=splits_by_team.get(tid, ()),
            schedule_rows=sched_by_team.get(tid, ()),
            dim_row=dim_by_team.get(tid),
            prior_season_dim_row=prior_by_team.get(tid),
            marts_available=marts_available,
            strength_available=strength is not None,
            ratings_as_of=ratings_as_of,
            ratings_next_update=ratings_next_update,
            now=now,
        )
        for tid in universe
    }
    # ⭐ A POST-PASS, because a rank is the one field on this page that cannot be built from one
    # team's rows — it is a property of the whole board, and this is the only place that sees it.
    return attach_standings(payloads)

#!/usr/bin/env python3
"""NCAAF-P3.3 — the ONE team-page shape the live wire cannot produce today.

    uv run python frontend/e2e/fixtures/build-ncaaf-team-populated.py

⭐ THE OTHER TWO ARE CAPTURED. `ncaaf-team-68.json` and `ncaaf-team-2449.json` are verbatim
production bytes (`capture-fixtures.mjs`), taken the morning the route went live. This script exists
only for the shape prod has nothing to serve yet, and it is the output of the SHIPPING builder
rather than an authored payload — E9.63's rule is that a hand-written fixture encodes the assumption
under test, and NF-C0e's is that a fixture derived from the code's own output cannot disconfirm it.
Nothing below writes a served field by hand: every blob leaves through
`team_payloads.build_team_payload`, which validates against `app/backend/models/ncaaf.py` on the way
out.

WHY IT IS NEEDED, AND WHAT WOULD RETIRE IT
------------------------------------------
Both captures carry `efficiency` and `splits` as STATED ABSENCES
(`no_row_for_this_team_and_season`) because the P1.1 rollups hold no 2026 rows yet — the marts
materialize those once a game-day dbt build runs on a played season. So the AVAILABLE branch of two
of the page's four blocks has nothing to capture, exactly as the market panel's available branch had
nothing to capture in P3.2.

⚠️ ON THE FIRST RE-CAPTURE AFTER THE 2026 ROLLUPS MATERIALIZE: a captured payload will reach the
available branch on its own, at which point this file stops being the only route to it. RETIRE IT
THEN and re-anchor onto the capture — a generated stand-in for a payload that now exists is a
fixture testing the render against a shape derived from the transform under test. Keep the ABSENT
arm alive on whichever fixture still has it (the captures do today).

WHAT IT CARRIES, AND WHY EACH PIECE IS THERE
--------------------------------------------
One team, 2025-shaped, with all four blocks AVAILABLE:

  * a 16-week strength SERIES, so the page's week-by-week band has more than one point to draw and
    a component that plotted only `current` is visibly wrong;
  * opponent-adjusted efficiency WITH its raw counterpart, so the adjusted/raw pairing renders;
  * trench + pace splits;
  * a schedule mixing PLAYED and UPCOMING games, plus a non-FBS opponent and a neutral-site game —
    the three flags a schedule row branches on.

⚠️ ITS NUMBERS ARE SHAPED AFTER REAL 2025 ROWS (Boise State's, read from the marts on 2026-09-01)
rather than invented, so a reader comparing the fixture to the product sees plausible magnitudes.
The E2E asserts against the fixture's OWN values, never a number typed into a spec, so the exact
figures are free to move.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from quant_sports_intel_models.football.ncaaf.serving import team_payloads  # noqa: E402

OUT = REPO / "frontend/e2e/fixtures/api/ncaaf-team-populated.synthetic.json"

TEAM_ID, SEASON = 68, 2025

#: The fit-level context, identical on every week row (it is a property of the season's fit).
_FIT = {
    "league_base_points": 26.73993, "home_field_advantage": 2.848385, "residual_sigma": 16.6,
    "model_version": "ncaaf_team_strength_v1", "hyper_n_prior_seasons": 4,
}


def _strength_series() -> list[dict]:
    """16 weeks, with the band NARROWING as games accumulate.

    ⭐ THE NARROWING IS THE POINT. A posterior that starts wide (no games — the prior) and tightens
    is what makes the band worth drawing at all, and a series with a flat sd could not tell a
    component that plots the band from one that plots a constant.
    """
    rows = []
    for week in range(1, 17):
        played = max(0, week - 1)
        rows.append({
            "team_id": TEAM_ID, "team": "Boise State", "conference": "Mountain West",
            "season": SEASON, "as_of_week": week,
            "games_in_window": played, "has_sufficient_sample": played >= 3,
            "strength_margin": 3.0937 + 0.1 * played,
            # 7.29 at week 1 (the real 2026 opener figure) down toward 3.00 (the real week-17 one).
            "strength_margin_sd": 7.2891 - (7.2891 - 3.0021) * (played / 12) if played <= 12
            else 3.0021,
            "strength_conference_component": 0.4357,
            "strength_covariate_component": 4.5938 - 0.02 * played,
            "strength_team_component": -0.4353 + 0.12 * played,
            "strength_offense": 1.1231 + 0.05 * played,
            "strength_offense_sd": 4.9 - 0.24 * played,
            "strength_defense": 2.9384 + 0.05 * played,
            "strength_defense_sd": 4.8 - 0.24 * played,
            **_FIT,
        })
    return rows


#: Read from `rollup_ncaaf_team_week_opponent_adjusted` (Boise State, 2025, as_of_week 17).
_EFFICIENCY = {
    "team_id": TEAM_ID, "season": SEASON, "as_of_week": 17, "games_played": 12,
    "adj_off_ppa": 0.179262, "adj_def_ppa": 0.099161, "adj_net_ppa": 0.080101,
    "adj_off_success_rate": 0.419421, "adj_def_success_rate": 0.374528,
    "adj_points_for_per_game": 29.337193, "adj_points_against_per_game": 21.788575,
    "raw_off_ppa": 0.198, "raw_def_ppa": 0.118,
    "raw_off_success_rate": 0.428, "raw_def_success_rate": 0.381,
    "raw_points_for_per_game": 29.75, "raw_points_against_per_game": 23.75,
    "sos_opponent_net_ppa": -0.000713, "opponents_counted": 12,
    "adjustment_applied": True, "has_reliable_adjustment": True,
}

#: Read from `rollup_ncaaf_team_week_asof` (same team, season and week).
_SPLITS = {
    "team_id": TEAM_ID, "season": SEASON, "as_of_week": 17, "games_played": 12,
    "off_line_yards": 3.021031, "def_line_yards": 2.878525,
    "off_stuff_rate": 0.174334, "def_stuff_rate": 0.206322,
    "off_plays_per_game": 74.416667, "possession_seconds_per_game": 1997.5,
    "drives": 146, "points_per_drive": 2.273973, "scoring_opportunity_rate": 0.534247,
    "three_and_out_rate": 0.199, "explosive_drive_rate": 0.411,
    "avg_start_yards_to_goal": 69.521, "off_explosiveness": 1.266127,
    "def_explosiveness": 1.398,
}

_DIM = {
    "team_id": TEAM_ID, "team": "Boise State", "conference": "Mountain West",
    "conference_division": None, "classification": "fbs", "abbreviation": "BOIS",
    "mascot": "Broncos", "venue_name": "Albertsons Stadium", "venue_city": "Boise",
    "venue_state": "ID",
}


def _game(game_id, week, date, opponent, opp_id, opp_conf, *, home, completed,
          team_pts=None, opp_pts=None, neutral=False, fbs=True, conf_game=False):
    """One `dim_ncaaf_game` row, in the mart's own column shape.

    ⚠️ Written as the MART would emit it — `home_points`/`away_points`, a naive-UTC `start_date`,
    the mart's own `game_date` — so the builder's orientation, its null-on-upcoming rule and its
    INC-22 day conversion all actually RUN. A row pre-oriented to this team would route around the
    three things most worth exercising.
    """
    side = ("home", "away") if home else ("away", "home")
    return {
        "game_id": game_id, "season": SEASON, "season_order_week": week,
        "start_date": f"{date}T{'19:00:00' if home else '02:00:00'}",
        "game_date": date, "season_type": "regular", "is_postseason": False,
        "is_neutral_site": neutral, "is_conference_game": conf_game, "is_fbs_matchup": fbs,
        "venue_name": "Albertsons Stadium" if home else f"{opponent} Stadium",
        f"{side[0]}_team_id": TEAM_ID, f"{side[0]}_team": "Boise State",
        f"{side[0]}_conference": "Mountain West",
        f"{side[1]}_team_id": opp_id, f"{side[1]}_team": opponent,
        f"{side[1]}_conference": opp_conf,
        "is_completed": completed,
        f"{side[0]}_points": team_pts, f"{side[1]}_points": opp_pts,
    }


#: A season that MIXES the states a schedule row branches on: a win, a loss, a non-FBS opponent, a
#: neutral-site game, and two still to play. A fixture where every game is the same kind could not
#: tell a component that reads the row from one that renders a single template.
_SCHEDULE = [
    _game(401762522, 1, "2025-08-28", "South Florida", 58, "American Athletic",
          home=False, completed=True, team_pts=7, opp_pts=34),
    _game(401762600, 2, "2025-09-06", "Eastern Washington", 331, "Big Sky",
          home=True, completed=True, team_pts=42, opp_pts=10, fbs=False),
    _game(401762700, 3, "2025-09-20", "Air Force", 2005, "Mountain West",
          home=True, completed=True, team_pts=31, opp_pts=24, conf_game=True),
    # ⭐ A 02:00-UTC KICKOFF, which is the PRIOR evening in every US timezone. The mart's own
    # `game_date` says the 4th; the served `game_day` must say the 3rd (INC-22). Without a row like
    # this the day conversion is untestable from the browser.
    _game(401762800, 4, "2025-10-04", "Notre Dame", 87, "FBS Independents",
          home=False, completed=True, team_pts=17, opp_pts=28, neutral=True),
    _game(401762900, 5, "2025-10-11", "Nevada", 2440, "Mountain West",
          home=True, completed=False, conf_game=True),
    _game(401763000, 6, "2025-10-18", "Wyoming", 2751, "Mountain West",
          home=False, completed=False, conf_game=True),
]


def main() -> int:
    blob = team_payloads.build_team_payload(
        team_id=TEAM_ID, season=SEASON,
        strength_rows=_strength_series(),
        efficiency_rows=[_EFFICIENCY],
        splits_rows=[_SPLITS],
        schedule_rows=_SCHEDULE,
        dim_row=_DIM,
        prior_season_dim_row=_DIM,
        marts_available=True,
    )
    # A generated fixture must be REPRODUCIBLE, so the one non-deterministic field is pinned. Every
    # other value is the builder's own output.
    blob["generated_at"] = "2026-09-03T05:20:22.000Z"

    for block in ("strength", "efficiency", "splits", "schedule"):
        assert blob[block]["status"] == "available", (
            f"{block} came out unavailable — this fixture exists precisely to reach the AVAILABLE "
            f"branch of all four blocks (reason={blob[block]['reason']!r})")
    assert blob["schedule"]["n_completed"] and blob["schedule"]["n_upcoming"], (
        "the schedule must mix played and upcoming games")

    OUT.write_text(json.dumps(blob, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}  {OUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

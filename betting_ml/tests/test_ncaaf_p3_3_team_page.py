"""NCAAF-P3.3 — the TEAM STATS PAGE contract, its builders, and the route that serves it.

⭐ WHY THESE ARE THE CLAUSES. The team page assembles from FOUR independently-available sources, so
its whole failure surface is "a block that is empty for one reason renders as if it were empty for
another". On the Saturday of week 1 a CORRECT page has a strength rating, a full schedule, and three
structurally empty blocks — nobody has played. If that renders identically to "our mart build did
not run", the same investigation happens every September (NF-C6b / NF-K1). So most of what follows
asserts that the causes STAY APART, and the rest asserts the two things this vertical is graded on:
the band travels with the rating, and the conference is the SEASON's.

⚠️ CI MOCKS ALL IO, so nothing here touches the lake, the DuckDB or AWS. The builders are pure by
construction (that is why they live in `team_payloads.py` rather than in the writer), and the writer
clauses are exercised with the reads monkeypatched. The runtime gate — a real box serving-write and
a curl of the deployed route — is an OPERATOR step and is stated as one in the handoff.

RED-proven by `betting_ml/tests/ncaaf_p3_3_red_proof.py`; run it after refactoring this file.
"""
from __future__ import annotations

import inspect

import pandas as pd
import pytest

from app.backend.models import ncaaf as contract
from app.backend.routers import ncaaf as router_mod
from quant_sports_intel_models.football.ncaaf.serving import team_payloads as tp

# ── fixtures ─────────────────────────────────────────────────────────────────────────────────
#
# Shaped after REAL rows measured on 2026-09-01: Boise State (68) moved Mountain West → Pac-12 for
# 2026 and North Dakota State (2449) joined FBS outright. They are the named test cases the spec
# asks for, not invented ids — a realignment guard driven by a made-up team could pass while the
# actual movers were mis-filed.

BOISE, NDSU = 68, 2449


def _strength_row(**over):
    row = {
        "team_id": BOISE, "team": "Boise State", "conference": "Pac-12", "season": 2026,
        "as_of_week": 1, "games_in_window": 0, "has_sufficient_sample": False,
        "strength_margin": 3.0936, "strength_margin_sd": 7.2891,
        "strength_conference_component": 0.4, "strength_covariate_component": 2.9,
        "strength_team_component": -0.2, "strength_offense": 1.5124, "strength_offense_sd": 4.9,
        "strength_defense": 1.5395, "strength_defense_sd": 4.8, "league_base_points": 26.7399,
        "home_field_advantage": 2.8484, "residual_sigma": 16.6,
        "model_version": "ncaaf_team_strength_v1", "hyper_n_prior_seasons": 4,
    }
    row.update(over)
    return row


def _dim_row(**over):
    row = {
        "team_id": BOISE, "team": "Boise State", "conference": "Pac-12",
        "conference_division": None, "classification": "fbs", "abbreviation": "BOIS",
        "mascot": "Broncos", "venue_name": "Albertsons Stadium", "venue_city": "Boise",
        "venue_state": "ID",
    }
    row.update(over)
    return row


def _game_row(**over):
    row = {
        "game_id": 401864577, "season": 2026, "season_order_week": 1,
        "start_date": pd.Timestamp("2026-08-29 21:30:00"), "game_date": pd.Timestamp("2026-08-29"),
        "season_type": "regular", "is_postseason": False, "is_neutral_site": False,
        "is_conference_game": False, "is_fbs_matchup": True, "venue_name": "Gate City Bank Field",
        "home_team_id": NDSU, "home_team": "North Dakota State", "home_conference": "Mountain West",
        "away_team_id": 2026, "away_team": "Jacksonville State", "away_conference": "Conference USA",
        "is_completed": False, "home_points": None, "away_points": None,
    }
    row.update(over)
    return row


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The contract — every served field declared, no claim, nothing dropped on serialize
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_team_page_model_is_in_the_walked_registry():
    """A model declared in the contract but absent from `CONTRACT_MODELS` escapes EVERY schema
    guard below — which is exactly the vacuity that registry exists to prevent (NF1.7 (a))."""
    declared = {
        obj for _, obj in vars(contract).items()
        if inspect.isclass(obj) and issubclass(obj, contract.BaseModel)
        and obj is not contract.BaseModel and obj.__module__ == contract.__name__
    }
    missing = sorted(m.__name__ for m in declared - set(contract.CONTRACT_MODELS))
    assert not missing, f"{missing} are declared but not walked by the schema guards"


def test_the_team_page_declares_no_pick_or_edge_field():
    """A strength rating is CONTEXT, never a recommendation. `best_alpha = 0` — VAL1 came back
    ALL_BUCKETS_NULL — so a field named for a pick, an edge or a stake would assert something the
    evidence does not support. The walk is the contract's own, run over the new models."""
    contract.assert_no_edge_claim_in_schema()


def test_a_team_page_serialises_every_declared_field_including_the_nulls():
    """⛔ NEVER `exclude_none`. An ABSENT field and a NULL field are different facts, and a client
    that has to distinguish "the key is missing" from "the value is unknown" cannot (E9.41)."""
    blob = tp.build_team_payload(team_id=BOISE, season=2026, marts_available=False,
                                 strength_available=False)
    for block in ("strength", "efficiency", "splits", "schedule"):
        declared = set(getattr(contract, f"NcaafTeam{block.capitalize()}").model_fields)
        assert declared <= set(blob[block]), f"{block} dropped {declared - set(blob[block])}"
    assert blob["framing"]["best_alpha"] == 0.0
    contract.assert_best_alpha_is_zero(blob)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Realignment — the AC this story is graded on
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_conference_is_the_seasons_not_the_current_one():
    """⭐ THE NAMED 2026 MOVER. Boise State's dim row for 2026 says Pac-12; a type-1 read of a
    "current" row, or a value carried along from a 2025 source, would say Mountain West. Eleven FBS
    programs moved for 2026, so this is not a corner case — it is most of the Group-of-Five."""
    ident = tp.build_identity(
        team_id=BOISE, season=2026, dim_row=_dim_row(conference="Pac-12"),
        prior_season_dim_row=_dim_row(conference="Mountain West"),
        strength_row=_strength_row(conference="Pac-12"))
    assert ident["conference"] == "Pac-12"
    assert ident["conference_source"] == tp.CONFERENCE_SOURCE_DIM
    assert ident["is_new_to_fbs"] is False


def test_a_conference_disagreement_is_recorded_rather_than_silently_resolved():
    """The SCD-2 dim and the P1.2 pooling level are derived INDEPENDENTLY. A disagreement means the
    posterior was shrunk toward a conference the team does not play in — a finding about the
    model's inputs, not a display problem, so it rides on the payload."""
    ident = tp.build_identity(
        team_id=BOISE, season=2026, dim_row=_dim_row(conference="Pac-12"),
        prior_season_dim_row=_dim_row(conference="Mountain West"),
        strength_row=_strength_row(conference="Mountain West"))
    assert ident["conference"] == "Pac-12", "the dim is the authority for what a team plays in"
    assert ident["conference_matches_model_input"] is False
    # ...and agreement is not merely the absence of a flag (the two-sided half).
    agree = tp.build_identity(
        team_id=BOISE, season=2026, dim_row=_dim_row(), prior_season_dim_row=_dim_row(),
        strength_row=_strength_row())
    assert agree["conference_matches_model_input"] is True


def test_a_first_year_fbs_program_is_named_rather_than_looking_like_missing_data():
    """⭐ NDSU AND SACRAMENTO STATE JOINED FBS FOR 2026. Their pre-season covariates are absent BY
    CONSTRUCTION, and a page that could not say so would present a structural absence as a defect.

    The three-way outcome matters: True (no prior row), False (a prior row exists), and None when
    we could not look at all — a fabricated `False` on a team the dim is simply missing would be a
    check reporting a pass it never ran (NF1.7 (a))."""
    new = tp.build_identity(team_id=NDSU, season=2026,
                            dim_row=_dim_row(team_id=NDSU, conference="Mountain West"),
                            prior_season_dim_row=None, strength_row=None)
    assert new["is_new_to_fbs"] is True
    returning = tp.build_identity(team_id=BOISE, season=2026, dim_row=_dim_row(),
                                  prior_season_dim_row=_dim_row(conference="Mountain West"),
                                  strength_row=None)
    assert returning["is_new_to_fbs"] is False
    unknown = tp.build_identity(team_id=BOISE, season=2026, dim_row=None,
                                prior_season_dim_row=None, strength_row=_strength_row())
    assert unknown["is_new_to_fbs"] is None
    assert unknown["conference_source"] == tp.CONFERENCE_SOURCE_MODEL_INPUT


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The band travels with the rating
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_strength_block_carries_the_posterior_band_at_week_one():
    """⚠️ WEEK 1 IS THE CASE THAT MATTERS. Nothing has been played, the posterior IS the prior, and
    the sd is wide (~7.3 points on the real 2026 opener). A rating served without its band would
    publish a precision the model does not claim — which on this vertical is the whole line between
    context and a pick. A zero-game row is a REAL posterior, not a gap: `status` is available."""
    block = tp.build_strength([_strength_row(as_of_week=1, games_in_window=0)])
    assert block["status"] == "available" and block["reason"] is None
    assert block["current"]["strength_margin"] == pytest.approx(3.0936)
    assert block["current"]["strength_margin_sd"] == pytest.approx(7.2891)
    assert block["current"]["games_in_window"] == 0
    # ...and the zero-game week stays in the SERIES too. `build_efficiency` correctly REFUSES a
    # zero-game row (a rollup of nothing is unknown); copying that filter onto the posterior is
    # exactly backwards and would empty every team page in week 1.
    assert [w["as_of_week"] for w in block["weeks"]] == [1]


def test_the_current_week_is_the_LARGEST_as_of_week_not_the_last_row():
    """A DuckDB/Delta read's row ORDER is not a guarantee. "The last row" silently becomes "an
    arbitrary row" the first time a materialization changes, and the symptom is a page quoting a
    stale week's rating with no error anywhere."""
    rows = [_strength_row(as_of_week=w, strength_margin=float(w), league_base_points=float(w))
            for w in (3, 9, 1)]
    block = tp.build_strength(rows)
    assert block["as_of_week"] == 9
    assert block["current"]["strength_margin"] == pytest.approx(9.0)
    assert [w["as_of_week"] for w in block["weeks"]] == [1, 3, 9], "the series is week-ordered"
    # ⭐ AND THE FIT-LEVEL CONTEXT COMES OFF THE SAME ROW. The first cut of the builder selected
    # "current" twice — once as `weeks[-1]`, once as `_latest_by_week(rows)` — which is two rule
    # sets for one question (E9.61) and which made this clause VACUOUS: the RED proof broke the
    # selector and the test stayed green, because nothing it read went through it.
    assert block["league_base_points"] == pytest.approx(9.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The three absences stay apart — the NF-C6b clause
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("builder", [tp.build_efficiency, tp.build_splits])
def test_the_three_causes_of_an_empty_block_are_distinguishable(builder):
    """⭐ THE CLAUSE THIS WHOLE CONTRACT EXISTS FOR. "Nobody has played yet" is the CORRECT state of
    week 1 and needs no action; "our mart build did not run" is a defect; "this rollup has no row
    for this team" is a third thing. A surface handed one blank for all three re-investigates the
    same symptom every September."""
    not_built = builder([], marts_available=False)
    no_row = builder([], marts_available=True)
    zero_game = builder([{"as_of_week": 1, "games_played": 0}], marts_available=True)

    assert not_built["reason"] == tp.REASON_NOT_BUILT
    # ⚠️ THE MAPPING IS THE ASSERTION, and the first cut had it BACKWARDS. Rows PRESENT with no
    # game behind them is the literal "no games played yet"; rows ABSENT is "the rollup holds
    # nothing for this team and season". Naming the wrong cause with confidence is worse than a
    # bare null, because it reads as a considered answer.
    assert no_row["reason"] == tp.REASON_NO_ROW
    assert zero_game["reason"] == tp.REASON_NO_GAMES
    assert len({not_built["reason"], no_row["reason"], zero_game["reason"]}) == 3
    for block in (not_built, no_row, zero_game):
        assert block["status"] == "unavailable"


@pytest.mark.parametrize("builder", [tp.build_efficiency, tp.build_splits])
def test_a_zero_game_rollup_row_is_never_served_as_available(builder):
    """`rollup_ncaaf_team_week_asof` EMITS a week-1 row whose every rate is NULL — a rollup of
    nothing is unknown (the deliberate contrast with the strength posterior, where a zero-game row
    IS the prior). `status: available` over a row of nulls is precisely the blank-cell render this
    contract exists to prevent."""
    block = builder([{"as_of_week": 1, "games_played": 0, "adj_off_ppa": None,
                      "off_line_yards": None}], marts_available=True)
    assert block["status"] == "unavailable"
    assert block["as_of_week"] is None, "a refused row must not leak its week as if it counted"


def test_the_strength_block_distinguishes_an_unreadable_lake_from_an_absent_team():
    """Same discipline one source over: a lake we could not read and a team the fit did not model
    are different facts, and the strength block is the one that must never be quietly empty."""
    unreadable = tp.build_strength([], strength_available=False)
    absent = tp.build_strength([], strength_available=True)
    assert unreadable["reason"] == tp.REASON_NOT_BUILT
    assert absent["reason"] == tp.REASON_NO_ROW


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Schedule + results — realized vs upcoming, honestly
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_an_upcoming_game_carries_no_score_and_no_result():
    """⛔ NEVER A ZERO. `0-0` beside next Saturday's opponent reads as a played scoreless game —
    a fabricated result, which is worse than an empty cell because it looks like data."""
    sched = tp.build_schedule([_game_row(is_completed=False)], team_id=NDSU, marts_available=True)
    game = sched["games"][0]
    assert game["is_completed"] is False
    assert game["team_points"] is None and game["opponent_points"] is None
    assert game["margin"] is None and game["result"] is None
    assert sched["n_upcoming"] == 1 and sched["n_completed"] == 0


def test_a_completed_game_is_oriented_to_the_team_being_served():
    """The same row appears on BOTH teams' pages, and `home_points` is the HOME team's score
    whichever page you are on. A build that read the home column for the away team's page would
    invert every result on half the site."""
    row = _game_row(is_completed=True, home_points=21, away_points=35)
    home = tp.build_schedule([row], team_id=NDSU, marts_available=True)["games"][0]
    away = tp.build_schedule([row], team_id=2026, marts_available=True)["games"][0]
    assert (home["is_home"], home["team_points"], home["margin"], home["result"]) == (True, 21, -14, "L")
    assert (away["is_home"], away["team_points"], away["margin"], away["result"]) == (False, 35, 14, "W")
    assert home["opponent"] == "Jacksonville State" and away["opponent"] == "North Dakota State"


def test_the_record_counts_only_games_that_were_PLAYED():
    """⭐ "3-0 through three games" and "3-0 with nine still to play" are different statements, and
    keeping them apart is this block's job on a September Saturday."""
    rows = [
        _game_row(game_id=1, is_completed=True, home_points=30, away_points=10),
        _game_row(game_id=2, is_completed=True, home_points=10, away_points=30),
        _game_row(game_id=3, is_completed=False),
    ]
    sched = tp.build_schedule(rows, team_id=NDSU, marts_available=True)
    assert (sched["wins"], sched["losses"], sched["ties"]) == (1, 1, 0)
    assert (sched["n_games"], sched["n_completed"], sched["n_upcoming"]) == (3, 2, 1)


def test_a_completed_flag_without_scores_does_not_manufacture_a_tie():
    """`is_completed` true with null points is a real mart state (a game finished but not yet
    scored). Subtracting two nulls into a 0 would publish a tie that never happened."""
    game = tp.build_schedule([_game_row(is_completed=True, home_points=None, away_points=None)],
                             team_id=NDSU, marts_available=True)["games"][0]
    assert game["result"] is None and game["margin"] is None


def test_the_kickoff_day_is_the_LA_day_not_the_marts_utc_date():
    """⭐⭐ THE INC-22 TRAP, AND IT IS LIVE IN THE SOURCE. `dim_ncaaf_game.game_date` is
    `start_date::date` — the UTC date — so a 02:00-UTC kickoff (a Saturday NIGHT game everywhere in
    the US, i.e. the marquee window on a college slate) files under SUNDAY. Serving that column
    would make the team page disagree with the game board about the same game.

    Measured on the real 2026 schedule: NDSU at Air Force is `2026-09-13T02:00:00Z`, which is
    Saturday 2026-09-12 in Los Angeles, and the mart's own `game_date` says 2026-09-13."""
    row = _game_row(start_date=pd.Timestamp("2026-09-13 02:00:00"),
                    game_date=pd.Timestamp("2026-09-13"))
    game = tp.build_schedule([row], team_id=NDSU, marts_available=True)["games"][0]
    assert game["game_day"] == "2026-09-12", "the UTC date leaked into the served kickoff day"
    assert game["commence_time"] == "2026-09-13T02:00:00.000Z"
    # ...and the instant matches the game board's own field, so the two payloads agree.
    assert "game_day" in contract.NcaafGamePrediction.model_fields


def test_no_week_label_reaches_the_served_schedule():
    """⛔ THE BANNED TOKEN, AND THE REASON IS A NAME COLLISION.

    TWO different columns in this repo are called `season_order_week`. `dim_ncaaf_game`'s is a
    genuinely derived, postseason-safe ordering; `game_prediction_snapshot.py`'s is a VERBATIM
    ALIAS of CFBD's raw `week`, which restarts at 1 in the postseason. `test_ncaaf_p3_1_serving.py`
    bans the token from this layer outright, and serving the safe one under the unsafe one's name
    is how the next reader conflates them. The fixture DELIBERATELY carries the mart column so this
    asserts the builder drops it, rather than asserting a column that was never there.
    """
    game = tp.build_schedule([_game_row(season_order_week=1)], team_id=NDSU,
                             marts_available=True)["games"][0]
    assert not any("week" in k for k in game), f"a week label reached the wire: {sorted(game)}"
    assert not any("week" in f for f in contract.NcaafTeamGame.model_fields)
    # ...and what REPLACES it is on the payload, so this is a substitution rather than a hole.
    assert game["game_day"] and game["is_postseason"] is not None


def test_the_team_pages_are_published_by_DEFAULT():
    """⭐ THE OTHER SIDE OF THE P3.1 SUITE'S STUB. That suite monkeypatches `build_team_blobs` away
    so its blob counts stay about the predictions write — a correct scoping move, and one that
    would hide a team build quietly switched off. `with_teams` defaults to True and this is where
    that is asserted, because a flag documented as on and never set is this repo's most-repeated
    operational defect."""
    import inspect

    import scripts.write_ncaaf_serving_store as writer

    assert inspect.signature(writer.write_serving_store).parameters["with_teams"].default is True


def test_a_game_the_team_is_not_in_is_dropped_rather_than_mis_oriented():
    sched = tp.build_schedule([_game_row()], team_id=999999, marts_available=True)
    assert sched["games"] == [] and sched["status"] == "unavailable"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The universe, and the writer's tiering
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_an_empty_schedule_never_claims_that_nobody_has_played_yet():
    """⭐ THE SAME VOCABULARY, THE WRONG FACT. `no_games_played_yet` is correct for a ROLLUP — a
    rollup of nothing is unknown — and wrong for a SCHEDULE, which exists from the moment the
    season rolls forward, months before anyone plays. An empty schedule means we have no fixture
    list for this team, or we could not read the mart. Naming the wrong absence is exactly the
    defect the reasons exist to prevent, so the two must not share a helper by reflex."""
    unreadable = tp.build_schedule([], team_id=BOISE, marts_available=False)
    no_fixtures = tp.build_schedule([], team_id=BOISE, marts_available=True)
    assert unreadable["reason"] == tp.REASON_NOT_BUILT
    assert no_fixtures["reason"] == tp.REASON_NO_ROW
    assert tp.REASON_NO_GAMES not in {unreadable["reason"], no_fixtures["reason"]}


def test_the_team_universe_is_the_union_of_the_strength_fit_and_the_season_dim():
    """⭐ NOT THE INTERSECTION. Both sources are legitimate on their own, so intersecting would drop
    a team from the site the moment one lagged the other — which a page promising "any FBS team"
    must not do. The 2026 build measured 138 teams from exactly this union."""
    pages = tp.build_team_payloads(
        season=2026,
        strength=pd.DataFrame([_strength_row(team_id=BOISE)]),
        team_dim=pd.DataFrame([_dim_row(team_id=NDSU, team="North Dakota State",
                                        conference="Mountain West")]),
    )
    assert sorted(pages) == sorted([BOISE, NDSU])
    assert pages[BOISE]["strength"]["status"] == "available"
    # The dim-only team still gets a page — with its strength block stating its own absence.
    assert pages[NDSU]["strength"]["status"] == "unavailable"
    assert pages[NDSU]["team"]["conference"] == "Mountain West"


def test_the_team_pages_cannot_fail_the_serving_critical_write(monkeypatch):
    """🚦 THE TIER, ASSERTED RATHER THAN DOCUMENTED. The team pages read the P1.1 dbt marts, which
    is a heavier dependency than this job's lake-only contract. So a failure in that half must cost
    the team pages and NOTHING else — the manifest, the slates, the per-game blobs and the futures
    board still write. A tier enforced only by a docstring is not enforced at all (E11.30)."""
    import scripts.write_ncaaf_serving_store as writer
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    row = {
        "game_id": 1, "season": 2026, "commence_time": "2026-08-29T21:30:00Z",
        "p_home_win": 0.6, "home_team_id": BOISE, "away_team_id": NDSU,
        "snapshot_ts": "2026-08-25T16:00:44Z",
    }
    monkeypatch.setattr(writer, "read_snapshots",
                        lambda season, source, *, local_root=None:
                        pd.DataFrame([row]) if source == gps.SNAPSHOT_SOURCE else pd.DataFrame())
    monkeypatch.setattr(writer, "read_market_lines", lambda season: ({}, False))

    def _boom(*a, **k):
        raise RuntimeError("the P1.1 marts exploded")

    monkeypatch.setattr(writer, "build_team_blobs", _boom)
    result = writer.write_serving_store(2026, dry_run=True)
    assert result["status"] == "ok", "a team-page failure must never fail the serving write"
    assert result["n_games"] == 1, "the game board still published"
    assert result["team_pages"]["n_teams"] == 0
    assert "exploded" in result["team_pages"]["error"], "the failure is REPORTED, not swallowed"


def test_the_writer_reports_block_availability_per_block_never_pooled(monkeypatch):
    """⭐ MH2.1 (c): a pooled "n% populated" cannot tell a week-1 slate whose efficiency blocks are
    CORRECTLY empty from a mart build that did not run — and those are precisely the two states an
    operator needs to distinguish here. So the run report counts per block, per reason."""
    import scripts.write_ncaaf_serving_store as writer

    monkeypatch.setattr(writer, "read_team_strength",
                        lambda season: pd.DataFrame([_strength_row()]))
    monkeypatch.setattr(writer, "read_team_marts",
                        lambda season: ({}, contract.TEAM_BLOCK_REASON_NOT_BUILT))
    blobs, report = writer.build_team_blobs(2026)
    assert report["marts_available"] is False and report["strength_read_ok"] is True
    assert report["strength_blocks"] == {"available": 1}
    assert report["efficiency_blocks"] == {f"unavailable:{tp.REASON_NOT_BUILT}": 1}
    assert report["schedule_blocks"] == {f"unavailable:{tp.REASON_NOT_BUILT}": 1}
    # ⭐ THE LEAD NUMBER SURVIVES A DEAD DuckDB. The strength rating and its band come from the
    # LAKE, so an unreadable mart build degrades the page rather than emptying it.
    assert blobs[0]["strength"]["current"]["strength_margin_sd"] == pytest.approx(7.2891)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The route
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _team_route():
    return next(r for r in router_mod.router.routes if getattr(r, "path", "") ==
                "/ncaaf/teams/{team_id}")


def test_the_team_route_exists_and_is_free():
    """NCAAF is FREE (E9.45). A `Depends` here — on the route OR on the router — would gate a
    vertical the product deliberately does not gate."""
    route = _team_route()
    assert sorted(route.methods) == ["GET"]
    assert router_mod.router.dependencies == []
    assert route.dependencies == []
    assert route.response_model is contract.NcaafTeamPage


def test_a_team_with_no_published_page_is_a_404_not_an_empty_body(monkeypatch):
    """⛔ ABSENT ⇒ 404. An empty-but-successful body would make "we publish nothing for this team"
    and "we publish a page whose blocks are empty" render identically — the exact collapse every
    block's `status`/`reason` pair exists to prevent."""
    from fastapi import HTTPException

    monkeypatch.setattr(router_mod.ncaaf_serving, "read_team", lambda team_id: None)
    with pytest.raises(HTTPException) as exc:
        router_mod.ncaaf_team(team_id=BOISE)
    assert exc.value.status_code == 404
    assert str(BOISE) in exc.value.detail


def test_the_route_returns_the_stored_blob_through_the_response_model(monkeypatch):
    """The E9.41 half: a field the STORE carries but the model does not declare is silently
    stripped on serialize, with the data correct in the store the whole time."""
    blob = tp.build_team_payload(team_id=BOISE, season=2026,
                                 strength_rows=[_strength_row()], dim_row=_dim_row(),
                                 prior_season_dim_row=_dim_row(conference="Mountain West"))
    monkeypatch.setattr(router_mod.ncaaf_serving, "read_team", lambda team_id: blob)
    served = router_mod.ncaaf_team(team_id=BOISE).model_dump()
    assert served["team"]["conference"] == "Pac-12"
    assert served["strength"]["current"]["strength_margin_sd"] == pytest.approx(7.2891)
    assert served == blob, "the response model altered or dropped part of the stored payload"


def test_the_team_route_inherits_the_ncaaf_cost_guardrails_rather_than_needing_its_own():
    """⭐ THE G100-C1 CHECK, RUN IN THE DIRECTION IT ACTUALLY POINTS HERE.

    That lesson is about a GATED route placed under a PUBLIC prefix silently inheriting the
    prefix's CDN cache rule and degrade entry. This route is public, so inheritance is what we
    WANT — but "want" is not "verified", and both registries match by PREFIX, which is a property
    of `cost_guardrails.py` rather than something this story controls. So it is asserted: the team
    page is shared-cacheable for an anonymous caller, and a cost event does not blank an entire
    sport whose only weeks of relevance are these ones.

    ⛔ If a later NCAAF route is ever NOT free, it must NOT live under `/ncaaf/…` — it would
    inherit both of these, which is the defect G100-C1 measured.
    """
    from app.backend.services import cost_guardrails as cg

    path = "/ncaaf/teams/68"
    assert cg.public_cache_control(path), "an anonymous team page is not shared-cacheable"
    assert cg.public_cache_control(path) == cg.public_cache_control("/ncaaf/manifest"), (
        "the team page must share the vertical's cache window, not invent its own")
    # The degrade floor: NCAAF is unconditionally free, so a cost event must not 503 it.
    assert any(path == p or path.startswith(p + "/") for p in cg._DEGRADE_ALLOWED_PREFIXES)


def test_the_serving_key_is_namespaced_and_carries_no_season():
    """The `ncaaf/` prefix IS the isolation from the MLB lane (it is the DynamoDB partition key),
    and the key carries no season because the PAYLOAD declares one — so a reader never has to guess
    a season from a key, which is the INC-22-shaped read bug this scheme removes."""
    assert contract.team_cache_key(BOISE) == f"{contract.NAMESPACE}/team/{BOISE}"
    assert contract.team_s3_key(BOISE).startswith(f"{contract.S3_PREFIX}/")
    assert "2026" not in contract.team_cache_key(BOISE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Standings — the rank, and the range that is the only thing making it publishable
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ THE MEASUREMENT THESE CLAUSES DEFEND. On the live 2026 week-1 board — 138 teams, every
# posterior sd ≈ 7.3 against a rating range of −25.9 to +21.2 — the MEDIAN team's 80% rank range
# spans 77 of 138 places and 130 of 138 span more than 40. A bare rank is therefore the most
# over-precise number this page could publish, and the range is what converts it into the most
# interpretable one. Every clause below exists to keep those two shipped together.


def _board(n: int = 40, sd: float = 7.3) -> dict[int, dict]:
    """A synthetic FBS-shaped board: `n` teams spread over a realistic rating range."""
    step = 46.0 / max(n - 1, 1)
    return {
        1000 + i: {
            "team": {"team_id": 1000 + i, "team": f"T{i}",
                     "conference": ["A", "B", "C", "D"][i % 4]},
            # ⚠️ CONTRACT-SHAPED, not merely enough for `attach_standings` to read. The serialize
            # clause below is the one that would catch an E9.41 strip, and it can only do that
            # against a block the response model actually accepts.
            "strength": {"status": "available", "reason": None, "as_of_week": 1,
                         "weeks": [],
                         "current": {"as_of_week": 1,
                                     "strength_margin": 21.0 - i * step,
                                     "strength_margin_sd": sd}},
        }
        for i in range(n)
    }


def test_a_rank_is_never_attached_without_its_range():
    """⛔ THE CENTRAL CONTRACT. A payload carrying a rank and no bounds is the one shape the client
    is required to refuse to render, so the writer must never produce it."""
    out = tp.attach_standings(_board())
    seen = 0
    for blob in out.values():
        for key in ("standing_fbs", "standing_conference"):
            standing = blob["strength"].get(key)
            if standing is None:
                continue
            seen += 1
            assert standing["rank"] is not None
            assert standing["rank_lo"] is not None and standing["rank_hi"] is not None, (
                f"{key} carries a rank with no range")
            assert standing["rank_lo"] <= standing["rank_hi"]
    assert seen, "no standing was attached at all — this test asserted nothing"


def test_the_point_rank_lies_inside_its_own_range():
    """A range that excludes the number it qualifies reads as a bug to a reader and IS one."""
    out = tp.attach_standings(_board())
    checked = 0
    for blob in out.values():
        s = blob["strength"]["standing_fbs"]
        assert s["rank_lo"] <= s["rank"] <= s["rank_hi"], s
        assert 1 <= s["rank_lo"] and s["rank_hi"] <= s["n_ranked"]
        checked += 1
    assert checked >= 40


def test_the_range_is_wide_at_week_one_rather_than_cosmetic():
    """⭐ NON-VACUITY, AND IT IS THE POINT OF THE WHOLE FEATURE. If the computed range came out one
    or two places wide, the honest thing would be to publish a bare rank and this design would be
    unjustified. It does not: at the sd the model actually carries in week 1, the typical range
    spans a large fraction of the board — which is exactly why the range ships."""
    out = tp.attach_standings(_board(n=40, sd=7.3))
    widths = [b["strength"]["standing_fbs"]["rank_hi"] - b["strength"]["standing_fbs"]["rank_lo"]
              for b in out.values()]
    widths.sort()
    median = widths[len(widths) // 2]
    assert median >= 10, (
        f"the median 80% rank range is only {median} places wide on a 40-team board at sd=7.3 — "
        "if that is real, a bare rank would be defensible and this design is not")


def test_a_narrower_posterior_produces_a_narrower_range():
    """⏳ THE HAZARD EXPIRES, and that is why the fix is a range rather than a refusal to rank: the
    width is a function of the posterior sd, which shrinks as games are played. A November board
    must therefore rank more sharply than a September one WITH NO CODE CHANGE."""
    def median_width(sd: float) -> float:
        out = tp.attach_standings(_board(n=40, sd=sd))
        w = sorted(b["strength"]["standing_fbs"]["rank_hi"] - b["strength"]["standing_fbs"]["rank_lo"]
                   for b in out.values())
        return w[len(w) // 2]

    wide, narrow = median_width(7.3), median_width(1.5)
    assert narrow < wide, f"a sharper posterior did not sharpen the rank range ({narrow} vs {wide})"


def test_the_standings_are_deterministic_across_writes(monkeypatch):
    """⛔ THE SEED IS LOAD-BEARING, AND THAT IS A MEASUREMENT RATHER THAN AN ASSUMPTION.

    The serving store is rewritten daily. An unseeded draw would move a published rank range with
    nothing in the model having changed — indistinguishable, to a reader or to a diff, from a real
    movement. Measured on the LIVE 138-team 2026 board at this draw count: **29.65% of published
    bounds change under a reseed** (24 reseeds, 6,624 bounds).

    ⚠️ THE BOARD BELOW IS AT REAL DENSITY ON PURPOSE, and the first version of this test was
    VACUOUS for exactly that reason — its 40 evenly-spaced teams left every percentile far from a
    rounding boundary, so an unseeded run rounded to the same integers and deleting the seed left
    the clause GREEN (the red proof caught it). Rank-range sensitivity is a property of how tightly
    the population is PACKED, so a guard on it has to be run at the packing the board actually has.
    """
    dense = _board(n=138)
    a = tp.attach_standings(dense)
    b = tp.attach_standings(_board(n=138))
    for tid in a:
        assert a[tid]["strength"]["standing_fbs"] == b[tid]["strength"]["standing_fbs"]
        assert a[tid]["strength"]["standing_conference"] == b[tid]["strength"]["standing_conference"]

    # ⭐ NON-VACUITY, and it is what makes the clause above mean anything: a DIFFERENT seed must
    # actually move a bound at this density. If it does not, this test is asserting that a constant
    # equals itself and the seed could be deleted with nothing going red.
    monkeypatch.setattr(tp, "STANDING_SEED", tp.STANDING_SEED + 1)
    c = tp.attach_standings(_board(n=138))
    moved = sum(
        1 for tid in a
        if a[tid]["strength"]["standing_fbs"] != c[tid]["strength"]["standing_fbs"]
    )
    assert moved, (
        "a different seed changed nothing at all, so this board is too sparse to detect an "
        "unseeded draw and the determinism clause above is vacuous")


def test_a_population_too_small_to_rank_gets_no_standing():
    """A rank of 1 of 1 is not a standing. Both the whole-board and the per-conference floors."""
    single = {k: v for k, v in list(_board().items())[:1]}
    assert tp.attach_standings(single)[next(iter(single))]["strength"].get("standing_fbs") is None

    # A conference of one still gets an FBS standing — it is only its CONFERENCE rank that is
    # meaningless — so the two floors are independent, not one switch.
    board = _board(n=4)
    for i, blob in enumerate(board.values()):
        blob["team"]["conference"] = "Solo" if i == 0 else "Shared"
    out = tp.attach_standings(board)
    solo = next(b for b in out.values() if b["team"]["conference"] == "Solo")
    assert solo["strength"]["standing_fbs"] is not None
    assert solo["strength"].get("standing_conference") is None


def test_a_team_without_a_usable_posterior_is_left_unranked_and_out_of_the_denominator():
    """⛔ NOT RANKED, AND NOT COUNTED. `n_ranked` names the population a rank was taken within —
    inflating it with teams that had no rating would quietly weaken every other team's placement."""
    board = _board(n=10)
    ids = list(board)
    board[ids[0]]["strength"] = {"status": "unavailable", "current": None}
    board[ids[1]]["strength"]["current"]["strength_margin_sd"] = 0.0   # a spread of zero is not one
    board[ids[2]]["strength"]["current"]["strength_margin"] = None
    out = tp.attach_standings(board)
    for tid in ids[:3]:
        assert out[tid]["strength"].get("standing_fbs") is None
    assert out[ids[3]]["strength"]["standing_fbs"]["n_ranked"] == 7


def test_the_served_levels_match_the_band_the_rating_is_published_with():
    """⭐ ONE OWNER. "42nd, plausibly 18th–97th" beside "+3.1, plausibly −6.2 to +12.4" is only one
    coherent statement if both are taken at the same confidence — so the levels are served, not
    assumed on the client, and they are the SAME levels."""
    out = tp.attach_standings(_board())
    s = next(iter(out.values()))["strength"]["standing_fbs"]
    assert s["interval_lo_level"] == contract.TEAM_STANDING_INTERVAL_LO_LEVEL
    assert s["interval_hi_level"] == contract.TEAM_STANDING_INTERVAL_HI_LEVEL
    assert round((s["interval_hi_level"] - s["interval_lo_level"]) * 100) == 80


def test_the_standing_is_declared_on_the_contract_and_carries_no_claim_token():
    """E9.41: a field the store carries and the model does not declare is silently STRIPPED."""
    declared = contract.declared_field_names(contract.NcaafTeamStrength)
    assert "standing_fbs" in declared and "standing_conference" in declared
    assert contract.NcaafTeamStanding in contract.CONTRACT_MODELS
    contract.assert_no_edge_claim_in_schema()

    # ...and it survives a real serialize, which is the step that does the stripping.
    out = tp.attach_standings(_board())
    blob = next(iter(out.values()))["strength"]
    model = contract.NcaafTeamStrength.model_validate(blob)
    assert model.standing_fbs is not None and model.standing_fbs.rank_hi is not None


def test_the_writer_attaches_standings_rather_than_leaving_them_to_a_caller():
    """⭐ WIRED *AND* INVOKED (NF-C0e). `build_team_payloads` is the only place that sees the whole
    board, so the post-pass has to run THERE — a `attach_standings` that exists and is never called
    is the defect this repo has shipped before."""
    strength = pd.DataFrame([
        {"team_id": 1, "as_of_week": 1, "strength_margin": 10.0, "strength_margin_sd": 7.3},
        {"team_id": 2, "as_of_week": 1, "strength_margin": -4.0, "strength_margin_sd": 7.3},
        {"team_id": 3, "as_of_week": 1, "strength_margin": 1.0, "strength_margin_sd": 7.3},
    ])
    out = tp.build_team_payloads(season=2026, strength=strength)
    assert out[1]["strength"]["standing_fbs"]["rank"] == 1
    assert out[2]["strength"]["standing_fbs"]["rank"] == 3
    assert out[1]["strength"]["standing_fbs"]["n_ranked"] == 3

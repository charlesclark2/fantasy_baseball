"""NF-WK-ACC1 part 3 — the play-derived 40+ yard touchdown bonuses, and the two-way-player join.

⭐ WHAT PART 3 CLOSED, measured through the production path on the operator's own 2025 league
(weeks 1-4, `run_nf_wk_acc1_crosscheck`):

    team totals agreeing      27/48  →  42/48  (the 40+ yard bonuses)
                                     →  46/48  (the name+team join fallback)
    player seats diverging    24     →  2

The two that remain are the DJ Moore lost-fumble column choice and the Trey Benson IDP-at-offensive-
grain question, both of which need a ruling and neither of which this change touches.

Each clause below pins one property that was MEASURED rather than assumed. Where a measurement is
quoted, `realized_player_pbp`'s header carries its derivation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.services import league_scoring, realized_stat_fields, weekly_recap
from quant_sports_intel_models.football.nfl.fantasy import realized_player_pbp as PP

ROOT = Path(__file__).resolve().parents[2]


def _play(**over):
    """One pbp row carrying EVERY column the derivation reads — the read contract is enforced, so a
    fixture that omitted one would be refused rather than silently scoring zero."""
    play = {c: None for c in PP.PBP_PLAYER_COLUMNS}
    play.update({"season": 2025, "week": 1, "game_id": "g1",
                 "touchdown": 0.0, "pass_touchdown": 0.0, "rush_touchdown": 0.0,
                 "yards_gained": 0.0})
    play.update(over)
    return play


# ── the frozen rule ───────────────────────────────────────────────────────────────────────────────

def test_a_long_pass_touchdown_pays_the_passer_AND_the_receiver():
    """One play, two managers. This is why `pass_td_40p` and `rec_td_40p` are separate keys, and why
    their league-wide season totals are equal rather than one being a subset of the other."""
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, pass_touchdown=1.0, yards_gained=50.0,
        passer_player_id="QB1", receiver_player_id="WR1")])
    assert out["QB1"]["pass_td_40p"] == 1.0
    assert out["WR1"]["rec_td_40p"] == 1.0
    # ...and neither is credited with the other's term.
    assert out["QB1"]["rec_td_40p"] == 0.0
    assert out["WR1"]["pass_td_40p"] == 0.0


def test_a_long_rush_touchdown_pays_the_rusher_only():
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, rush_touchdown=1.0, yards_gained=46.0, rusher_player_id="RB1")])
    assert out["RB1"]["rush_td_40p"] == 1.0
    assert out["RB1"]["pass_td_40p"] == 0.0 and out["RB1"]["rec_td_40p"] == 0.0


def test_a_lateral_credits_the_player_who_SCORED_not_the_one_who_caught_it():
    """⭐ THE CASE THAT WOULD HAVE SHIPPED WRONG AND BEEN INVISIBLE. Measured 2024 wk17: Goff → 1 yard
    to Amon-Ra St. Brown, who laterals to Jameson Williams for 41 and the touchdown. Sleeper credits
    WILLIAMS and not St. Brown.

    ⛔ AND NEITHER OF THE TWO CHECKS WOULD HAVE CAUGHT IT ALONE. A lateral moves WHICH player is
    credited without changing HOW MANY are, so the weekly total is identical either way; and that
    week St. Brown scored a different, shorter receiving touchdown, so his `receiving_tds` was 1 and
    the subset-identity bound was satisfied by the wrong touchdown.
    """
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, pass_touchdown=1.0, yards_gained=42.0,
        passer_player_id="QB1", receiver_player_id="CAUGHT_IT",
        lateral_receiver_player_id="SCORED_IT")])
    assert out["SCORED_IT"]["rec_td_40p"] == 1.0
    assert "CAUGHT_IT" not in out, "the primary receiver did not score this touchdown"
    # the passer is unaffected — he threw it either way
    assert out["QB1"]["pass_td_40p"] == 1.0


def test_a_lateral_on_a_rush_credits_the_lateral_rusher():
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, rush_touchdown=1.0, yards_gained=56.0,
        rusher_player_id="HANDED_OFF", lateral_rusher_player_id="SCORED_IT")])
    assert out["SCORED_IT"]["rush_td_40p"] == 1.0
    assert "HANDED_OFF" not in out


@pytest.mark.parametrize("yards,pays", [(39.0, False), (40.0, True), (41.0, True)])
def test_the_threshold_is_exactly_forty_yards(yards, pays):
    """⛔ MEASURED, NOT TUNABLE: at 41 or at 39 the weekly totals disagree with the platform on 5 of
    18 weeks of 2025 (the control table in `realized_player_pbp`'s header)."""
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, rush_touchdown=1.0, yards_gained=yards, rusher_player_id="RB1")])
    assert bool(out) is pays


def test_a_long_RETURN_touchdown_pays_none_of_the_three():
    """An interception / fumble / kick-return touchdown is a touchdown of 40+ yards and is NOT a
    passing, rushing or receiving one. Measured: 2 such plays in the whole lake, both excluded."""
    out = PP.player_long_td_counts([_play(
        touchdown=1.0, yards_gained=80.0, passer_player_id="QB1", receiver_player_id="WR1",
        rusher_player_id="RB1")])
    assert out == {}, "neither flag is set, so no offensive bonus is earned"


def test_a_NaN_flag_reads_as_NOT_SET():
    """⚠️ `bool(float('nan'))` is True. pbp arrives through pandas, so an unpopulated flag is NaN —
    a truthiness test would turn every non-scoring play into a long touchdown."""
    nan = float("nan")
    out = PP.player_long_td_counts([_play(
        touchdown=nan, pass_touchdown=nan, rush_touchdown=nan, yards_gained=99.0,
        passer_player_id="QB1", rusher_player_id="RB1")])
    assert out == {}


def test_a_narrower_play_row_is_REFUSED_rather_than_scored_as_zero():
    """⛔ THE READ CONTRACT. Every helper here treats an absent column as 'not set', so a forgotten
    column in a caller's SELECT would zero a whole term with no error (NF-C0e). The refusal is what
    makes `PBP_PLAYER_COLUMNS` a contract instead of a comment."""
    thin = _play(touchdown=1.0, rush_touchdown=1.0, yards_gained=99.0, rusher_player_id="RB1")
    del thin["lateral_rusher_player_id"]
    with pytest.raises(ValueError, match="lateral_rusher_player_id"):
        PP.player_long_td_counts([thin])


# ── the subset-identity check, and its non-vacuity ────────────────────────────────────────────────

def test_the_subset_identity_catches_an_over_count_and_passes_a_legitimate_one():
    """The check that DISPROVED the `passing_40` wrong-key, run in the confirming direction: nobody's
    40+ yard touchdown count can exceed his touchdown count of that type. Measured over 1999-2026 —
    5,796 player-weeks, 0 violations under the frozen rule, 3 under the non-lateral one."""
    counts = {"WR1": {"rec_td_40p": 1.0}, "WR2": {"rec_td_40p": 2.0}}
    tds = {"WR1": {"rec_td_40p": 1.0}, "WR2": {"rec_td_40p": 1.0}}
    bad = PP.subset_identity_violations(counts, tds)
    # NON-VACUITY FIRST: the legitimate row must be in the population being judged, or "0 violations"
    # would be a statement about an empty check.
    assert counts["WR1"]["rec_td_40p"] > 0 and "WR1" in tds
    assert [v["playerId"] for v in bad] == ["WR2"]
    assert bad[0]["derived"] == 2.0 and bad[0]["touchdowns"] == 1.0


def test_a_player_absent_from_the_touchdown_side_is_a_violation_not_a_pass():
    """A derived long touchdown for someone with NO touchdown row is the strongest possible form of
    the defect, so an absent bound must read as 0 rather than as 'nothing to check' (NF1.7(a))."""
    assert PP.subset_identity_violations({"X": {"rush_td_40p": 1.0}}, {}) != []


# ── the map wiring ────────────────────────────────────────────────────────────────────────────────

def test_the_three_bonuses_are_no_longer_reported_as_unsupported():
    """They were in the declared-absent inventory because the weekly line cannot carry them. They are
    supplied now, so the inventory must stop naming them — an absence list that keeps listing a term
    we DO score is the NF-K1 declared-vs-derived rot."""
    unsupported = set(realized_stat_fields.unsupported_stat_keys())
    for key in PP.LONG_TD_KEYS:
        assert key not in unsupported
    # non-vacuity: the inventory is still reporting real absences (the team-grain D/ST family)
    assert any(k.startswith("dst_") for k in unsupported)


def test_the_two_declarations_of_the_derived_column_names_agree():
    """⛔ THE CROSS-SIDE PIN. The backend cannot import `quant_sports_intel_models` (the Lambda
    bundles neither it nor pandas), so the column names are declared on BOTH sides. This is the guard
    that makes the duplication safe — the writer and the reader must use the same string, or the term
    is written under a name the scorer never looks up and scores zero with no error."""
    assert PP.LONG_TD_COLUMN == {
        k: cols[0] for k, cols in realized_stat_fields.REALIZED_PBP_SOURCE.items()
    }
    assert set(PP.LONG_TD_KEYS) == set(realized_stat_fields.REALIZED_PBP_SOURCE)


def test_the_derived_columns_are_never_asked_of_the_weekly_stat_table():
    """`REALIZED_STAT_COLUMNS` is the SELECT list for `stats_player_week`, which has no column for
    any of these. Asking for one would fail the read outright."""
    weekly = set(realized_stat_fields.REALIZED_STAT_COLUMNS)
    for column in realized_stat_fields.REALIZED_PBP_COLUMNS:
        assert column not in weekly
    # ...and the wrong-key column that MEANS SOMETHING ELSE is not quietly mapped either
    assert "passing_40" not in weekly and "receiving_40" not in weekly


def test_a_row_carrying_the_column_applies_the_term_and_a_row_without_it_leaves_it_absent():
    """The APPLIED-vs-CAPTURED seam. An absent field must stay ABSENT rather than default to 0, or a
    league's weight would resolve APPLIED while contributing nothing."""
    field = realized_stat_fields.REALIZED_STAT_FIELD["pass_td_40p"]
    with_col = realized_stat_fields.flatten_realized_row({"attempts": 5, field: 1.0})
    without = realized_stat_fields.flatten_realized_row({"attempts": 5})
    assert with_col[field] == 1.0
    assert field not in without


# ── the build-side join ───────────────────────────────────────────────────────────────────────────

def _rw():
    return pytest.importorskip(
        "quant_sports_intel_models.football.nfl.fantasy.realized_week",
        reason="realized_week pulls pandas through the lake read")


def test_the_counts_are_written_as_ZERO_on_every_row_not_only_on_the_scorers():
    """⭐ THE LOAD-BEARING DETAIL. `available_fields` decides APPLIED vs CAPTURED by whether the field
    is present AT ALL, so populating it only for the handful of players who scored a long touchdown
    would make the verdict depend on whether anyone happened to score one. A week with none would
    then report the bonus as 'not in this number' when it was applied and correctly came to nothing.
    """
    RW = _rw()
    rows = [{"player_id": "A"}, {"player_id": "B"}]
    credited = RW.attach_long_td_counts(rows, {"A": {"pass_td_40p": 1.0}})
    assert credited == 1
    for row in rows:
        for column in realized_stat_fields.REALIZED_PBP_COLUMNS:
            assert column in row, "a row without the column would resolve CAPTURED"
    assert rows[0][PP.LONG_TD_COLUMN["pass_td_40p"]] == 1.0
    assert rows[1][PP.LONG_TD_COLUMN["pass_td_40p"]] == 0.0


def test_the_served_column_list_grows_ONLY_when_the_plays_were_joined():
    """A week whose plays are not published yet must not CLAIM the derived columns: `contract_report`
    refuses to publish when a claimed column carries no value, so declaring them unconditionally
    would turn a legitimate degraded build into an outage."""
    RW = _rw()
    joined = set(RW.served_columns(plays_joined=True))
    alone = set(RW.served_columns(plays_joined=False))
    assert joined - alone == set(realized_stat_fields.REALIZED_PBP_COLUMNS)
    assert not alone & set(realized_stat_fields.REALIZED_PBP_COLUMNS)


# ── publishing a week whose construction widened ──────────────────────────────────────────────────

def _man(columns, sha, completeness="final"):
    return {"season": 2026, "week": 1, "completeness": completeness,
            "columns": sorted(columns), "content_sha256": sha}


def test_deriving_a_NEW_term_is_a_widen_not_a_vendor_restatement():
    """⭐ WITHOUT THIS THE WHOLE STORY WOULD BE A NO-OP. Any new column changes every row's hash, so
    every already-published week would classify as `restate`, keep serving the old rows, and never
    show the bonus — while the log blamed the vendor for a change we made ourselves."""
    RW = _rw()
    old = [{"game_id": "g1", "player_id": "p1", "yards": 10}]
    new = [{"game_id": "g1", "player_id": "p1", "yards": 10, "pbp_pass_td_40p": 0.0}]
    prior = _man(["game_id", "player_id", "yards"], RW.content_hash(old))
    now = _man(["game_id", "player_id", "yards", "pbp_pass_td_40p"], RW.content_hash(new))
    d = RW.publish_decision(now, prior, new)
    assert d["action"] == "widen_columns"
    assert d["servingWrite"] is True and d["event"] is False
    assert d["addedColumns"] == ["pbp_pass_td_40p"]


def test_a_widen_that_ALSO_moves_a_published_column_is_still_a_restatement():
    """⛔ THE WIDEN MUST NOT BECOME A BACK DOOR. A vendor correction can land in the same build as a
    new term; the test is not 'did columns grow' but 'did anything the published week already carried
    move'. A restatement needs a human, and this is what keeps that true."""
    RW = _rw()
    old = [{"game_id": "g1", "player_id": "p1", "yards": 10}]
    moved = [{"game_id": "g1", "player_id": "p1", "yards": 11, "pbp_pass_td_40p": 0.0}]
    prior = _man(["game_id", "player_id", "yards"], RW.content_hash(old))
    now = _man(["game_id", "player_id", "yards", "pbp_pass_td_40p"], RW.content_hash(moved))
    d = RW.publish_decision(now, prior, moved)
    assert d["action"] == "restate"
    assert d["servingWrite"] is False and d["event"] is True


def test_without_the_rows_a_widen_refuses_to_assume_the_harmless_case():
    """The two causes are indistinguishable from the manifests alone, and one of them must never
    overwrite a served week — so the conservative answer is the default (NF1.7(a))."""
    RW = _rw()
    prior = _man(["game_id", "player_id", "yards"], "old")
    now = _man(["game_id", "player_id", "yards", "pbp_pass_td_40p"], "new")
    d = RW.publish_decision(now, prior, None)
    assert d["action"] == "restate" and d["servingWrite"] is False


def test_a_column_DISAPPEARING_is_never_a_widen():
    """A narrowed artifact is a regression, not an upgrade — it must not reach the served keys on the
    strength of some other column having been added.

    ⚠️ THE FIXTURE IS BUILT TO ISOLATE **THIS** CLAUSE, and the first cut was vacuous (the RED proof
    caught it). `widen_columns` needs BOTH "no column vanished" AND "the published columns are
    byte-identical"; a fixture whose rows also fail the hash clause passes whatever the disappearance
    clause does, so it proves nothing about the clause it names (the NF-D17 and-composed-guard rule).
    So the rows here STILL CARRY `gone` — only the MANIFEST stops claiming it — which makes the
    restricted hash match and leaves the disappearance clause as the only thing that can refuse.
    """
    RW = _rw()
    rows_old = [{"game_id": "g1", "player_id": "p1", "yards": 10, "gone": 1.0}]
    rows_new = [{"game_id": "g1", "player_id": "p1", "yards": 10, "gone": 1.0,
                 "pbp_pass_td_40p": 0.0}]
    was = ["game_id", "player_id", "yards", "gone"]
    prior = _man(was, RW.content_hash(rows_old))
    now = _man(["game_id", "player_id", "yards", "pbp_pass_td_40p"], RW.content_hash(rows_new))
    # THE ISOLATION, asserted rather than assumed: the hash clause is SATISFIED, so a `restate`
    # verdict can only be coming from the vanished column.
    assert RW.content_hash(rows_new, was) == prior["content_sha256"]
    assert RW.publish_decision(now, prior, rows_new)["action"] == "restate"


def test_the_restricted_hash_reads_only_the_named_columns():
    RW = _rw()
    a = [{"game_id": "g1", "player_id": "p1", "yards": 10, "extra": 1.0}]
    b = [{"game_id": "g1", "player_id": "p1", "yards": 10, "extra": 999.0}]
    shared = ["game_id", "player_id", "yards"]
    assert RW.content_hash(a, shared) == RW.content_hash(b, shared)
    # non-vacuity: the unrestricted hashes really do differ, so the equality above means something
    assert RW.content_hash(a) != RW.content_hash(b)


# ── the two-way-player join ───────────────────────────────────────────────────────────────────────

def _board(*rows):
    return [{"name": n, "pos": p, "team": t, "leaguePts": 1.0} for n, p, t in rows]


def test_a_two_way_player_whose_position_the_two_sides_DISAGREE_on_now_matches():
    """⭐ THE MEASURED CASE. Travis Hunter is `WR` on Sleeper and `CB` in `stats_player_week`, so
    `travis hunter|WR` never met `travis hunter|CB` and his seat came back unmatched in every week of
    2025 — 4 of the 6 team-weeks still disagreeing after the bonuses landed. His NAME matched all
    along, which is why the spec's 'fails the name join' was the wrong diagnosis."""
    board = _board(("Travis Hunter", "CB", "JAX"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Travis Hunter", "position": "WR", "team": "JAX"}], board)
    assert hit["board"] is board[0]
    assert hit["matchedOn"] == "name_team"


def test_the_same_name_on_a_DIFFERENT_team_does_not_match():
    """⛔ WHY THE FALLBACK IS NAME+TEAM AND NOT NAME. 'Josh Allen' is a quarterback on BUF and a
    linebacker on JAX; handing a manager the wrong man's stat line is strictly worse than the honest
    non-match it would replace."""
    board = _board(("Josh Allen", "LB", "JAX"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Josh Allen", "position": "QB", "team": "BUF"}], board)
    assert hit["board"] is None and hit["matchedOn"] is None


def test_an_AMBIGUOUS_name_and_team_is_dropped_rather_than_arbitrated():
    """Two board rows sharing a name AND a franchise cannot be told apart, so neither is chosen (the
    NF-W9-0 rule: drop an ambiguous id, never pick one)."""
    board = _board(("Mike Williams", "WR", "LAC"), ("Mike Williams", "CB", "LAC"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Mike Williams", "position": "TE", "team": "LAC"}], board)
    assert hit["board"] is None and hit["matchedOn"] is None


def test_the_fallback_never_overrides_a_primary_hit():
    """It can only ever convert a non-match into a match, so no seat that resolves today can move."""
    board = _board(("Real Player", "WR", "ATL"), ("Real Player", "RB", "ATL"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Real Player", "position": "RB", "team": "ATL"}], board)
    assert hit["matchedOn"] == "name_position"
    assert hit["board"]["pos"] == "RB", "the position-exact row must win"


def test_a_defence_seat_does_not_use_the_name_fallback():
    """A D/ST slot already joins on its franchise (NF-C6P3), and a rendered defence name must never
    become a candidate for a human player's seat."""
    board = _board(("Jacksonville Jaguars", "DST", "JAX"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Jaguars D/ST", "position": "DST", "team": "JAX"}], board)
    # it matches, but through the franchise key rather than the fallback
    assert hit["board"] is board[0] and hit["matchedOn"] == "name_position"


def test_an_unresolvable_name_is_still_an_honest_miss():
    board = _board(("Real Player", "WR", "ATL"))
    [hit] = league_scoring.match_roster_to_board(
        [{"name": "Notta Realplayer", "position": "WR", "team": "ATL"}], board)
    assert hit["board"] is None and hit["matchedOn"] is None


# ── a fallback match is scored at the position the LEAGUE used ─────────────────────────────────────

_TWO_WAY_ROW = {"player_display_name": "Travis Hunter", "position": "CB", "team": "JAX",
                "receptions": 6, "receiving_yards": 33}


def _fetched_two_way(platform_pts):
    return {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "L1",
        "startingSlots": ["WR"],
        "teams": [{
            "teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": platform_pts,
            "lineup": [{"slot": "WR", "seat": 0, "playerKey": "9", "empty": False,
                        "name": "Travis Hunter", "position": "WR", "team": "JAX",
                        "platformPts": platform_pts}],
        }],
    }


def test_a_fallback_match_is_scored_with_the_leagues_position_bonus_not_the_lakes():
    """⭐ A NAME+TEAM MATCH MEANS THE POSITIONS DISAGREE, so the board's own points were computed at
    the LAKE's position — and `score_row`'s one position-dependent term is the league's
    `position_bonuses`. A league paying a WR reception bonus would otherwise under-score a two-way
    player whose lake row says `CB`, silently and only for him.

    ⚠️ MEASURED AS INERT ON THE OPERATOR'S OWN LEAGUE (it publishes no position bonuses at all),
    which is exactly why it would have gone unnoticed there and shipped wrong for a league that does.
    """
    cfg = {"scoring": {"per_stat": {"rec": 0.5, "rec_yds": 0.1},
                       "position_bonuses": {"WR": {"rec": 1.0}}}}
    # base = 6 × 0.5 + 33 × 0.1 = 6.3 ; with the WR bonus = 6.3 + 6 × 1.0 = 12.3
    scored = weekly_recap.score_week(fetched=_fetched_two_way(12.3),
                                     realized_rows=[_TWO_WAY_ROW], cfg=cfg)
    seat = scored["teams"][0]["seats"][0]
    assert seat["points"] == pytest.approx(12.3), "the league's WR bonus must be applied"
    assert scored["teams"][0]["itemisationGap"] == pytest.approx(0.0)


def test_without_the_bonus_the_fallback_match_scores_the_plain_terms():
    """The two-sided half: the re-score must not INVENT points where the league pays no bonus."""
    cfg = {"scoring": {"per_stat": {"rec": 0.5, "rec_yds": 0.1}}}
    scored = weekly_recap.score_week(fetched=_fetched_two_way(6.3),
                                     realized_rows=[_TWO_WAY_ROW], cfg=cfg)
    assert scored["teams"][0]["seats"][0]["points"] == pytest.approx(6.3)


def test_the_board_row_kept_for_the_rescore_never_reaches_a_seat():
    """`flat` is internal to the join, like `explain`. A seat copies named fields only, and a served
    seat carrying the whole raw stat line would be an entitlement leak (NF-EPIC1)."""
    cfg = {"scoring": {"per_stat": {"rec": 0.5}}}
    scored = weekly_recap.score_week(fetched=_fetched_two_way(3.0),
                                     realized_rows=[_TWO_WAY_ROW], cfg=cfg)
    assert "flat" not in scored["teams"][0]["seats"][0]


# ── the disclosure narrows because the terms are really scored ─────────────────────────────────────

def test_the_disclosure_stops_naming_the_long_touchdown_bonuses_once_the_plays_are_there():
    """The measured-gap rule (#1155) plus the narrowing: a league that pays the bonus, on a week whose
    plays we have, must not be told the bonus is missing from its number."""
    cfg = {"scoring": {"per_stat": {"rec": 0.5, "rec_td_40p": 2.0}}}
    field = realized_stat_fields.REALIZED_STAT_FIELD["rec_td_40p"]
    with_plays = weekly_recap.score_week(
        fetched=_fetched_two_way(3.0),
        realized_rows=[{**_TWO_WAY_ROW, field: 0.0}], cfg=cfg)
    note = with_plays["itemisationGapNote"] or ""
    assert "40" not in note, f"the bonus is applied, so the disclosure must not name it: {note!r}"

    # NON-VACUITY, the other side: the SAME league on a week with no plays must still be told.
    without = weekly_recap.score_week(fetched=_fetched_two_way(99.0),
                                      realized_rows=[_TWO_WAY_ROW], cfg=cfg)
    assert "40" in (without["itemisationGapNote"] or ""), \
        "a week whose plays are absent must still disclose the missing bonus"

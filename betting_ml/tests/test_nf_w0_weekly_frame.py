"""NF-W0 — guards for the weekly point-in-time training/serving frame.

Every guard here was RED-PROVEN against deliberately-broken source before being trusted: the
zero-retention test fails if the label join is flipped to `how='inner'`, each `assert_no_leakage`
clause fails when its own clause is deleted, and the parity test fails on a leaky assembly.

⭐ ON ISOLATING AN `and`-COMPOSED GUARD (the NF-D17 lesson). `assert_no_leakage` rejects for three
INDEPENDENT reasons, and a fixture that trips two of them proves neither. The unknown-provenance and
source-week clauses get fixtures that satisfy every other clause, so only the clause under test can
fire. The leaky-column clause cannot be isolated that way — every leaky name is also, necessarily,
not in the allowed contract — so that test asserts on the RAISED MESSAGE instead. That distinction
matters: asserting merely "it raised" would stay green with the leaky-column clause deleted, because
the unknown-provenance clause would raise in its place.

Fast-gate safe: pure pandas, no IO, no `pipeline` import (E11.23).
"""
from __future__ import annotations

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
def _schedule() -> pd.DataFrame:
    """2 teams, 3 weeks. KC plays all 3; BUF is on BYE in week 2."""
    return pd.DataFrame(
        [
            (2024, 1, "KC", "BUF"),
            (2024, 2, "KC", "DEN"),
            (2024, 3, "KC", "BUF"),
        ],
        columns=["season", "week", "home_team", "away_team"],
    )


def _rosters() -> pd.DataFrame:
    rows = []
    for wk in (1, 2, 3):
        rows += [
            (2024, wk, "KC", "WR", "ACT", "P_STAR"),     # plays every week
            (2024, wk, "KC", "WR", "ACT", "P_SCRATCH"),  # dressed, never a stat line
            (2024, wk, "KC", "RB", "INA", "P_HURT"),     # declared inactive every week
            (2024, wk, "KC", "WR", "DEV", "P_PSQUAD"),   # practice squad — NOT game-day
        ]
    # BUF WR is rostered wks 1 and 3 only (the feed emits no row for the week-2 bye)
    rows += [(2024, 1, "BUF", "WR", "ACT", "P_BILL"), (2024, 3, "BUF", "WR", "ACT", "P_BILL")]
    return pd.DataFrame(rows, columns=["season", "week", "team", "position", "status", "gsis_id"])


def _stats() -> pd.DataFrame:
    """Only players who actually recorded a line. P_SCRATCH and P_HURT are absent BY DESIGN."""
    return pd.DataFrame(
        [
            (2024, 1, "P_STAR", 12.5, 1, 8, 0, 5),
            (2024, 2, "P_STAR", 9.0, 0, 6, 0, 4),
            (2024, 3, "P_STAR", 21.0, 0, 11, 0, 8),
            (2024, 1, "P_BILL", 4.0, 0, 3, 0, 2),
            (2024, 3, "P_BILL", 7.5, 0, 5, 0, 3),
        ],
        columns=["season", "week", "player_id", "fantasy_points_ppr",
                 "carries", "targets", "attempts", "receptions"],
    )


def _frame() -> pd.DataFrame:
    spine = WF.build_spine(_rosters(), _schedule())
    return WF.attach_labels(spine, _stats(), label_version="test.v1",
                            label_as_of_timestamp="2026-08-04T00:00:00Z")


# ── the spine ────────────────────────────────────────────────────────────────────────────────────
def test_practice_squad_is_excluded_but_inactives_are_kept():
    """Game-day roster only. A practice-squad row is not a startable player; an INACTIVE one is —
    he is precisely the zero a start/sit user is exposed to."""
    spine = WF.build_spine(_rosters(), _schedule())
    assert "P_PSQUAD" not in set(spine["gsis_id"]), "practice squad must not enter the spine"
    assert "P_HURT" in set(spine["gsis_id"]), "declared-inactive players must be RETAINED"


def test_bye_rows_are_constructed_because_the_roster_feed_omits_them():
    """The roster feed emits NO row for a team's bye week, so a spine built straight off it silently
    drops every bye. Deleting `_bye_rows` turns this red."""
    spine = WF.build_spine(_rosters(), _schedule())
    bill = spine[spine["gsis_id"] == "P_BILL"]
    assert set(bill["week"]) == {1, 2, 3}, "the bye week must be carried, not dropped"
    assert not bool(bill.loc[bill["week"] == 2, "_has_game"].iloc[0])


def test_a_bye_is_not_invented_outside_the_players_roster_tenure():
    """A player rostered only in week 3 must not be handed a phantom week-2 bye for a team he was
    not on — that would fabricate a zero he could never have been asked to start."""
    ros = pd.DataFrame(
        [(2024, 3, "BUF", "WR", "ACT", "P_LATE")],
        columns=["season", "week", "team", "position", "status", "gsis_id"],
    )
    spine = WF.build_spine(ros, _schedule())
    assert set(spine.loc[spine["gsis_id"] == "P_LATE", "week"]) == {3}


# ── zero retention (the core of the story) ───────────────────────────────────────────────────────
def test_zero_opportunity_outcomes_are_retained_not_dropped():
    """⭐ THE LOAD-BEARING TEST. Flipping the label join to `how='inner'` — i.e. building the frame
    stats-first, the natural mistake — deletes P_SCRATCH and P_HURT entirely and turns this red."""
    frame = _frame()
    kept = set(frame["gsis_id"])
    assert {"P_SCRATCH", "P_HURT"} <= kept, "non-playing players must survive as retained zeros"
    scratch = frame[frame["gsis_id"] == "P_SCRATCH"]
    assert len(scratch) == 3
    assert (scratch["fantasy_points"] == 0.0).all(), "a missing stat line scores 0.0, not NaN"
    assert (scratch["label"] == WF.LABEL_DRESSED_NO_STAT).all()


def test_the_three_zero_classes_stay_distinct():
    """A bye, an inactive and a dressed-no-stat are all 0.0 points and are NOT the same event: one is
    knowable at schedule release, one is a Sunday-morning event, one is a coaching decision."""
    frame = _frame()
    labels = dict(zip(frame["gsis_id"] + "_" + frame["week"].astype(str), frame["label"]))
    assert labels["P_BILL_2"] == WF.LABEL_BYE
    assert labels["P_HURT_1"] == WF.LABEL_INACTIVE
    assert labels["P_SCRATCH_1"] == WF.LABEL_DRESSED_NO_STAT
    assert labels["P_STAR_1"] == WF.LABEL_PLAYED
    assert len(set(WF.ZERO_LABELS)) == 3


def test_labels_carry_their_version_and_as_of_stamp():
    """A fantasy label is itself point-in-time data (v3 §12B): official stats get corrected, and
    re-scoring an old leaderboard against a later label silently changes model rankings."""
    frame = _frame()
    for col in ("label_version", "label_as_of_timestamp", "scoring_system_id", "stat_source"):
        assert col in frame.columns and frame[col].notna().all()
    assert frame["label_version"].unique().tolist() == ["test.v1"]


def test_a_stat_line_beats_an_inactive_flag_and_the_conflict_is_counted():
    """If a player is flagged INA yet has a stat line he demonstrably appeared — the stat line wins,
    but the conflict must be COUNTED rather than silently resolved."""
    stats = pd.concat([_stats(), pd.DataFrame(
        [(2024, 1, "P_HURT", 3.0, 2, 0, 0, 0)],
        columns=["season", "week", "player_id", "fantasy_points_ppr",
                 "carries", "targets", "attempts", "receptions"])], ignore_index=True)
    spine = WF.build_spine(_rosters(), _schedule())
    frame = WF.attach_labels(spine, stats, label_version="t", label_as_of_timestamp="t")
    hurt_w1 = frame[(frame["gsis_id"] == "P_HURT") & (frame["week"] == 1)].iloc[0]
    assert hurt_w1["label"] == WF.LABEL_PLAYED
    assert bool(hurt_w1["label_conflict"])
    assert int(frame["label_conflict"].sum()) == 1


# ── coverage ─────────────────────────────────────────────────────────────────────────────────────
def test_coverage_reports_the_zero_share_and_the_median():
    """The zero share and the MEDIAN are what decide NF-W1's scoring rule: a conditional median AT
    the floor is where MAE inverts and pays for pessimism (NF-D11/NF-D14)."""
    cov = WF.coverage_by_year_position(_frame())
    assert {"zero_share", "median_points", "n_bye", "n_inactive"} <= set(cov.columns)
    wr = cov[cov["position"] == "WR"].iloc[0]
    assert wr["n_rows"] == wr["n_played"] + wr["n_inactive"] + wr["n_bye"] + wr["n_dressed_no_stat"]


# ── leakage guard: one isolating fixture per clause ──────────────────────────────────────────────
def test_leaky_column_clause_rejects_realized_weather():
    """Asserts on the MESSAGE, not merely that it raised. `temp` is also absent from the allowed
    contract, so the unknown-provenance clause would raise in this clause's place — a bare
    `pytest.raises` would stay green with this clause deleted (NF-D17)."""
    with pytest.raises(WF.LeakageError, match="leaky feature columns"):
        WF.assert_no_leakage(pd.DataFrame(), feature_columns=["temp"], projection_week=5)
    with pytest.raises(WF.LeakageError, match="leaky feature columns"):
        WF.assert_no_leakage(pd.DataFrame(), feature_columns=["game_wind"], projection_week=5)
    with pytest.raises(WF.LeakageError, match="leaky feature columns"):
        WF.assert_no_leakage(pd.DataFrame(), feature_columns=["fantasy_points_ppr"], projection_week=5)


def test_unknown_provenance_clause_rejects_an_unaudited_feature():
    """Isolating: the name is not leaky and there is no source-week column, so only this clause can
    fire. An unaudited feature has no as-of rule by definition (v3 §13)."""
    with pytest.raises(WF.LeakageError, match="not in ALLOWED_FEATURE_CONTRACT"):
        WF.assert_no_leakage(pd.DataFrame(), feature_columns=["some_vendor_metric"],
                             projection_week=5)


def test_source_week_clause_rejects_a_window_containing_the_target():
    """Isolating: every feature name is in the allowed contract and none is leaky, so clauses 1 and 3
    pass and only the source-week clause can fire."""
    frame = pd.DataFrame({"src_week": [3, 4, 5]})
    with pytest.raises(WF.LeakageError, match="rolling window contains"):
        WF.assert_no_leakage(frame, feature_columns=["snap_share"], projection_week=5,
                             source_week_column="src_week")
    # …and the same call is CLEAN once the window stops short of the target week.
    WF.assert_no_leakage(pd.DataFrame({"src_week": [3, 4]}), feature_columns=["snap_share"],
                         projection_week=5, source_week_column="src_week")


def test_the_allowed_contract_admits_only_pit_safe_features():
    """A feature cannot sit in the allowed contract while declaring itself PIT-unsafe."""
    assert all(s.point_in_time_safe for s in WF.ALLOWED_FEATURE_CONTRACT)
    assert not any(s.point_in_time_safe for s in WF.DEFERRED_FEATURE_CONTRACT)
    names = [s.name for s in WF.ALLOWED_FEATURE_CONTRACT + WF.DEFERRED_FEATURE_CONTRACT]
    assert len(names) == len(set(names)), "a feature must not be in both contracts"


def test_realized_weather_and_gameday_inactives_are_deferred_not_allowed():
    """The two traps this audit exists to name: a realized value that LOOKS like a forecast, and a
    label-side field that LOOKS like a feature."""
    deferred = {s.name for s in WF.DEFERRED_FEATURE_CONTRACT}
    assert "weather_forecast" in deferred
    assert "gameday_inactive_status" in deferred
    assert "route_participation" in deferred


# ── train/serve parity ───────────────────────────────────────────────────────────────────────────
def _feat(week: int, values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "season": [2024] * len(values), "week": [week] * len(values),
        "gsis_id": list(values), "snap_share": list(values.values()),
    })


def test_parity_passes_when_the_two_assemblies_agree():
    res = WF.train_serve_parity(_feat(5, {"a": 0.5, "b": 0.7}), _feat(5, {"a": 0.5, "b": 0.7}),
                                compare_columns=["snap_share"])
    assert res["train_serve_parity"] == "PASS" and res["failures"] == []


def test_parity_fails_on_a_value_mismatch():
    """The signature of a leaky training assembly: serving, which cannot see the target week, computes
    a different value from the same code."""
    res = WF.train_serve_parity(_feat(5, {"a": 0.5, "b": 0.7}), _feat(5, {"a": 0.5, "b": 0.9}),
                                compare_columns=["snap_share"])
    assert res["train_serve_parity"] == "FAIL"
    assert any("value mismatches" in f for f in res["failures"])


def test_parity_fails_on_a_key_set_difference():
    res = WF.train_serve_parity(_feat(5, {"a": 0.5, "b": 0.7}), _feat(5, {"a": 0.5}),
                                compare_columns=["snap_share"])
    assert res["train_serve_parity"] == "FAIL"
    assert res["n_key_only_train"] == 1


def test_parity_fails_when_a_column_exists_on_one_side_only():
    """⭐ The depth-chart break's exact shape: a schema replacement upstream does not raise, it just
    produces a column on one side. Reported as a hard failure, never a coverage note."""
    train = _feat(5, {"a": 0.5}).assign(depth_team=1)
    res = WF.train_serve_parity(train, _feat(5, {"a": 0.5}), compare_columns=["snap_share"])
    assert res["train_serve_parity"] == "FAIL"
    assert any("TRAINING only" in f for f in res["failures"])


# ── status fields ────────────────────────────────────────────────────────────────────────────────
def test_status_emits_every_field_the_epic_names():
    frame = _frame()
    parity = WF.train_serve_parity(_feat(5, {"a": 0.5}), _feat(5, {"a": 0.5}),
                                   compare_columns=["snap_share"])
    status = WF.build_status(frame, parity, training_status="CERTIFIED",
                             serving_status="CERTIFIED_TIER0_LAGGED").to_dict()
    for fld in ("weekly_training_frame_status", "weekly_serving_frame_status", "point_in_time_safe",
                "train_serve_parity", "known_missingness", "allowed_feature_contract",
                "deferred_feature_contract"):
        assert fld in status, f"missing required status field {fld}"
    assert status["train_serve_parity"] == "PASS"
    assert status["point_in_time_safe"]["weather_forecast"] is False
    assert status["point_in_time_safe"]["snap_share"] is True
    assert status["known_missingness"]["zero_share_overall"] > 0


def test_contract_as_frame_is_reportable():
    df = WF.contract_as_frame(WF.ALLOWED_FEATURE_CONTRACT)
    assert {"name", "source", "tier", "license", "pit_fidelity", "point_in_time_safe"} <= set(df.columns)
    assert len(df) == len(WF.ALLOWED_FEATURE_CONTRACT)

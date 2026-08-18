"""NCAAF-PS guards — the pre-kickoff prediction snapshot.

Four things must hold, and each is RED-proven against deliberately broken source in
`betting_ml/tests/ncaaf_ps_red_proof.py` (a guard that cannot fail is worse than no guard —
NF1.7 (a) / INC-38):

  1. THE LEAKAGE GATE is DATE-BASED and refuses. `snapshot_ts < commence_time` on every persisted
     row, checked on instants — never on CFBD `week`, which restarts at 1 in the postseason, so a
     week-based assertion passes green on exactly the rows it should catch (the P1.1/P1.2 lesson).
     `test_the_gate_is_date_based_not_week_based` is the one that matters: its fixture is a row a
     week-based check calls fine and the clock calls a leak.
  2. A RE-RUN CAN NEVER LOSE A PRIOR WEEK. `write_season_partition` OVERWRITES a season partition,
     so the writer READ-MERGE-WRITEs. The regression pins that a second snapshot preserves the
     first (the P0.6b landmine), that an identical key is REPLACED rather than duplicated, and that
     an unreadable lake RAISES instead of being mistaken for "nothing to preserve."
  3. THE SCHEDULE IS WIRED. Registered, STOPPED by default, in-season cron, and the futures leaf is
     pinned DOWNSTREAM of the game snapshot by a real dependency EDGE on the compiled graph — not
     by source order, which a reorder would silently break (INC-38/INC-40).
  4. THE PAYLOAD MAKES NO CLAIM. Probabilities and intervals only; `best_alpha = 0`. P1.4's CLV leg
     came back a clean null, so an edge/pick column would assert what the evidence does not support.

Plus the contract-coverage guard: a served column that goes missing is mean-imputed to EXACTLY 0.0
and would silently serve a different model than the one certified (the NF-C0e class), so the
assembly refuses rather than degrades.

No IO: every test builds its own frames, or reads the two COMMITTED served JSON artifacts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

UTC = timezone.utc


# ══════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — small, hand-built, no lake
# ══════════════════════════════════════════════════════════════════════════════════════════

def _slate(kickoffs, *, week=1, season_type="regular", season=2026) -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": [1000 + i for i in range(len(kickoffs))],
        "season": season,
        "week": week,
        "season_type": season_type,
        "commence_time": [k.strftime("%Y-%m-%dT%H:%M:%S.000Z") for k in kickoffs],
        "start_time_tbd": False,
        "is_completed": False,
        "is_neutral_site": False,
        "is_conference_game": True,
        "home_team_id": [10 + i for i in range(len(kickoffs))],
        "home_team": [f"Home {i}" for i in range(len(kickoffs))],
        "home_conference": "SEC",
        "away_team_id": [50 + i for i in range(len(kickoffs))],
        "away_team": [f"Away {i}" for i in range(len(kickoffs))],
        "away_conference": "Big Ten",
        "home_points": np.nan,
        "away_points": np.nan,
    })


def _strength(team_ids) -> pd.DataFrame:
    n = len(team_ids)
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "team_id": list(team_ids),
        "team": [f"T{t}" for t in team_ids],
        "conference": "SEC",
        "as_of_week": 1,
        "games_in_window": 0,
        "has_sufficient_sample": False,
        "strength_margin": rng.normal(0, 8, n),
        "strength_margin_sd": np.full(n, 7.5),
        "strength_offense": rng.normal(0, 4, n),
        "strength_offense_sd": np.full(n, 5.0),
        "strength_defense": rng.normal(0, 4, n),
        "strength_defense_sd": np.full(n, 5.0),
        "strength_conference_component": 0.0,
        "strength_covariate_component": rng.normal(0, 3, n),
        "strength_team_component": 0.0,
        "covariate_component_roster_flux": rng.normal(0, 1, n),
        "covariate_component_coaching": 0.0,
        "covariate_component_talent": rng.normal(0, 1, n),
        "hyper_n_prior_seasons": 4,
        "home_field_advantage": 2.85,
        "league_base_points": 27.5,
    })


def _rows(snapshot: datetime, kickoffs) -> pd.DataFrame:
    """A minimal persisted-row frame — only what the gates read."""
    return pd.DataFrame({
        "game_id": range(len(kickoffs)),
        "snapshot_ts": gps._iso(snapshot),
        "commence_time": [k.strftime("%Y-%m-%dT%H:%M:%S.000Z") for k in kickoffs],
        "p_home_win": 0.5,
        "best_alpha": 0.0,
    })


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1 — the leakage gate
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_gate_passes_when_every_row_is_strictly_pre_kickoff():
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    gps.assert_pre_kickoff(_rows(snap, [snap + timedelta(days=4), snap + timedelta(minutes=30)]))


def test_gate_refuses_a_row_whose_game_already_kicked_off():
    snap = datetime(2026, 8, 30, 16, tzinfo=UTC)
    rows = _rows(snap, [snap + timedelta(days=1), snap - timedelta(hours=2)])
    with pytest.raises(ValueError, match="LEAKAGE GATE FAILED"):
        gps.assert_pre_kickoff(rows)


def test_gate_refuses_a_kickoff_exactly_at_the_snapshot_instant():
    """The bound is STRICT. A "prediction" made at the moment of kickoff is not a prediction, and a
    non-strict `<=` would quietly admit the whole boundary."""
    snap = datetime(2026, 8, 30, 16, tzinfo=UTC)
    with pytest.raises(ValueError, match="LEAKAGE GATE FAILED"):
        gps.assert_pre_kickoff(_rows(snap, [snap]))


def test_the_gate_is_date_based_not_week_based():
    """⭐ THE ONE THAT MATTERS. CFBD restarts `week` at 1 for the postseason, so a bowl game in
    January carries `week = 1` — the same label as September's opening slate. A week-based
    assertion ("this row's week is not behind us") therefore calls a JANUARY post-kickoff row fine,
    which is exactly the P1.1 leak. The clock cannot be fooled that way.

    The fixture is built so a week-based check PASSES and the real gate FAILS; the assertion on the
    week-based reading is what makes this test about the *mechanism*, not just about one bad row.
    """
    snap = datetime(2027, 1, 12, 2, tzinfo=UTC)          # the night of the title game
    bowl_already_started = snap - timedelta(hours=3)
    rows = _rows(snap, [bowl_already_started])
    rows["cfbd_week"] = 1                                # postseason week 1 — collides with Sept
    rows["snapshot_cfbd_week"] = 1

    # A week-based check sees "week 1 vs week 1 — not behind us" and passes on a leaked row:
    assert (rows["cfbd_week"] >= rows["snapshot_cfbd_week"]).all()
    # The DATE-based gate refuses it.
    with pytest.raises(ValueError, match="LEAKAGE GATE FAILED"):
        gps.assert_pre_kickoff(rows)


def test_gate_refuses_an_unparseable_kickoff_rather_than_passing_it():
    """An unevaluable gate is a REFUSAL, never a pass (NF1.7 (a)). Split from the missing-column
    case below so each break isolates ONE clause — a fixture that trips two clauses proves
    neither (NF-D17)."""
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    bad = _rows(snap, [snap + timedelta(days=1)])
    bad.loc[0, "commence_time"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="cannot be evaluated"):
        gps.assert_pre_kickoff(bad)


def test_gate_refuses_when_the_kickoff_column_is_absent_entirely():
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    rows = _rows(snap, [snap + timedelta(days=1)]).drop(columns=["commence_time"])
    with pytest.raises(KeyError, match="not a passed gate"):
        gps.assert_pre_kickoff(rows)


def test_gate_is_a_no_op_on_an_empty_frame_but_the_writer_never_writes_one():
    """An empty frame trivially satisfies the gate — which is only safe because the merge REFUSES
    an empty batch outright, so "zero rows" can never become a silent full-partition rewrite."""
    gps.assert_pre_kickoff(pd.DataFrame())
    with pytest.raises(ValueError, match="EMPTY new batch"):
        gps.merge_snapshot_rows(pd.DataFrame({"game_id": [1], "snapshot_ts": ["x"]}),
                                pd.DataFrame(), gps.GAME_SNAPSHOT_KEY)


def test_slate_selection_is_by_kickoff_instant_not_by_week():
    """The SELECTION half of the date-based discipline: two games labelled the same CFBD week land
    on opposite sides of the horizon purely by kickoff, and an already-started game is excluded."""
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    games = _slate([snap - timedelta(hours=1),      # already under way
                    snap + timedelta(days=3),       # inside the window
                    snap + timedelta(days=20)],     # beyond it
                   week=1)
    sel = gps.select_upcoming_slate(games, snap, horizon_days=7.0)
    assert list(sel["game_id"]) == [1001]
    assert games["week"].nunique() == 1, "the fixture must not let `week` do the discriminating"


def test_min_lead_minutes_is_a_k_minus_buffer():
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    games = _slate([snap + timedelta(minutes=5), snap + timedelta(hours=6)])
    assert list(gps.select_upcoming_slate(games, snap, min_lead_minutes=15.0)["game_id"]) == [1001]


def test_a_naive_snapshot_instant_is_read_as_utc_not_local():
    """Every instant in this vertical is UTC. Reading a naive one as machine-local would shift the
    leakage comparison by hours on a laptop (the LTZ/NTZ family, one layer down)."""
    aware = datetime(2026, 8, 25, 16, tzinfo=UTC)
    assert gps._utc_ts(datetime(2026, 8, 25, 16)) == gps._utc_ts(aware)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2 — never lose a prior week (the P0.6b landmine, on a second table)
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_a_second_snapshot_never_deletes_the_first():
    """THE REGRESSION. `write_season_partition` overwrites the season partition, so writing only
    the new batch would delete every earlier snapshot — and the whole point of this table is that
    the earlier snapshot is the one that proves what we said in advance."""
    wk1 = _rows(datetime(2026, 8, 25, 16, tzinfo=UTC), [datetime(2026, 8, 29, 16, tzinfo=UTC)] * 3)
    wk2 = _rows(datetime(2026, 9, 1, 16, tzinfo=UTC), [datetime(2026, 9, 5, 16, tzinfo=UTC)] * 4)
    merged = gps.merge_snapshot_rows(wk1, wk2, gps.GAME_SNAPSHOT_KEY)
    assert len(merged) == 7
    assert set(merged["snapshot_ts"]) == {wk1["snapshot_ts"].iloc[0], wk2["snapshot_ts"].iloc[0]}
    assert (merged["snapshot_ts"] == wk1["snapshot_ts"].iloc[0]).sum() == 3


def test_re_running_the_same_snapshot_replaces_rather_than_duplicates():
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    first = _rows(snap, [datetime(2026, 8, 29, 16, tzinfo=UTC)] * 3)
    again = first.copy()
    again["p_home_win"] = 0.6                       # a re-run under the same key is a REWRITE
    merged = gps.merge_snapshot_rows(first, again, gps.GAME_SNAPSHOT_KEY)
    assert len(merged) == 3
    assert (merged["p_home_win"] == 0.6).all()


def test_a_genuinely_absent_partition_writes_the_new_batch_alone():
    new = _rows(datetime(2026, 8, 25, 16, tzinfo=UTC), [datetime(2026, 8, 29, 16, tzinfo=UTC)])
    assert len(gps.merge_snapshot_rows(None, new, gps.GAME_SNAPSHOT_KEY)) == 1


def test_a_transient_lake_read_raises_instead_of_looking_like_an_empty_partition(monkeypatch):
    """"I could not read it" must never be mistaken for "there is nothing to preserve" — that
    mistake IS the destructive overwrite. Only a genuine missing-table error yields `None`."""
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    monkeypatch.setattr(query_lake, "_connect", lambda: _NoopConn())
    monkeypatch.setattr(query_lake, "q", lambda sql: (_ for _ in ()).throw(
        Exception("IO Error: connection reset by peer")))
    with pytest.raises(RuntimeError, match="NOT a missing-table error"):
        gps.read_existing_snapshots(2026, gps.SNAPSHOT_SOURCE, local_root="/tmp/nope")

    monkeypatch.setattr(query_lake, "q", lambda sql: (_ for _ in ()).throw(
        Exception('IO Error: DeltaKernel InvalidTableLocationError (28): Path does not exist: "x"')))
    assert gps.read_existing_snapshots(2026, gps.SNAPSHOT_SOURCE, local_root="/tmp/nope") is None


class _NoopConn:
    def execute(self, *a, **k):
        return None


def test_the_futures_snapshot_has_its_own_table_and_key():
    """The P1.5 `season_simulation_board` write is a season-partition OVERWRITE, so it holds only
    the CURRENT board and can never accrue a track record. The snapshot needs its own table."""
    from quant_sports_intel_models.football.ncaaf.models import run_season_simulation as p1_5

    assert gps.FUTURES_SNAPSHOT_SOURCE != p1_5._LAKE_SOURCE
    assert "snapshot_ts" in gps.FUTURES_SNAPSHOT_KEY


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3 — the served contract is covered, or we refuse to score
# ══════════════════════════════════════════════════════════════════════════════════════════

def _served():
    return gps.load_served_model()


def test_the_strength_map_produces_every_served_non_pace_column():
    """EXHAUSTIVENESS against the COMMITTED artifact. The assembly is a second renderer of the P1.3
    matrix's strength join, so it must produce the served contract in full — a column it silently
    fails to produce is mean-imputed to exactly 0.0 and we serve a different model with no error."""
    served = _served()
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 3)
    strength = _strength(list(slate["home_team_id"]) + list(slate["away_team_id"]))
    frame = gps.build_slate_frame(slate, strength)

    missing = [c for c in served.mean.columns if c not in frame.columns]
    assert not missing, f"the assembly cannot produce served column(s) {missing}"
    gps.assert_contract_covered(frame, served.mean)


def test_a_missing_served_column_refuses_rather_than_scoring_a_different_model():
    served = _served()
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 2)
    frame = gps.build_slate_frame(slate, _strength(list(slate["home_team_id"])
                                                   + list(slate["away_team_id"])))
    with pytest.raises(KeyError, match="quietly different model"):
        gps.assert_contract_covered(frame.drop(columns=["home_strength_offense"]), served.mean)


def test_an_all_null_non_pace_column_refuses_but_all_null_pace_is_allowed():
    """Pace is NULL by construction pre-season and is EXACTLY inert — that is the certified
    behaviour. Any OTHER all-NULL served column is a silently different model, not a prediction."""
    served = _served()
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 2)
    frame = gps.build_slate_frame(slate, _strength(list(slate["home_team_id"])
                                                   + list(slate["away_team_id"])))
    assert frame["pace_sum"].isna().all(), "the pre-season fixture must have NULL pace"
    gps.assert_contract_covered(frame, served.mean)          # pace-NULL is fine

    frame["home_strength_margin"] = np.nan
    with pytest.raises(ValueError, match="entirely NULL"):
        gps.assert_contract_covered(frame, served.mean)


def test_a_team_with_no_strength_row_is_dropped_not_imputed():
    """An unpriceable game must vanish, not become a confident prediction built from train means."""
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 3)
    strength = _strength(list(slate["home_team_id"]) + list(slate["away_team_id"][1:]))
    frame = gps.build_slate_frame(slate, strength)
    assert len(frame) == 2 and 1000 not in set(frame["game_id"])


def test_the_snapshot_scores_with_the_served_model_and_produces_sane_probabilities():
    """End-to-end on fixtures: the served artifacts drive μ and σ, and the read-off is P1.4's."""
    served = _served()
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 6)
    frame = gps.build_slate_frame(slate, _strength(list(slate["home_team_id"])
                                                   + list(slate["away_team_id"])))
    scored = gps.predict_slate(frame, served, n_draws=4000)
    rows = gps.build_snapshot_rows(scored, served, snapshot_ts=snap, strength_as_of_week=1)

    gps.assert_pre_kickoff(rows)
    gps.assert_no_edge_claim(rows)
    assert ((rows["p_home_win"] > 0.01) & (rows["p_home_win"] < 0.99)).all()
    assert (rows["margin_q10"] < rows["margin_q50"]).all()
    assert (rows["margin_q50"] < rows["margin_q90"]).all()
    assert (rows["total_q10"] < rows["total_q90"]).all()
    assert (rows["total_q50"] > 20).all() and (rows["total_q50"] < 100).all()
    assert (rows["margin_interval_width"] > 0).all()
    assert (rows["lead_minutes"] > 0).all()
    assert rows["model_version"].eq(served.version).all()
    assert not rows["pace_term_active"].any(), "week-1 pace must be inert"


def test_the_serving_path_is_the_full_posterior_predictive_not_the_season_sim_mode():
    """`fixed_strength=True` is the SEASON-SIM mode: it strips the k²·strength_var term the sim
    supplies through its own once-per-season draw. Using it for a standalone game would UNDER-state
    the interval — a narrower band is exactly the wrong error for an honest-uncertainty product."""
    served = _served()
    var = np.array([7.5 ** 2 * 2])
    full_m, full_t = gps.matchup_sigma(served.dispersion, var, fixed_strength=False)
    fixed_m, fixed_t = gps.matchup_sigma(served.dispersion, var, fixed_strength=True)
    assert full_m[0] > fixed_m[0] and full_t[0] > fixed_t[0]

    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 3)
    frame = gps.build_slate_frame(slate, _strength(list(slate["home_team_id"])
                                                   + list(slate["away_team_id"])))
    scored = gps.predict_slate(frame, served, n_draws=2000)
    assert np.allclose(scored["sigma_margin"].to_numpy(), full_m[0])


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4 — the payload makes no claim (best_alpha = 0)
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_persisted_schema_carries_no_edge_or_pick_column():
    served = _served()
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    slate = _slate([snap + timedelta(days=4)] * 2)
    frame = gps.build_slate_frame(slate, _strength(list(slate["home_team_id"])
                                                   + list(slate["away_team_id"])))
    rows = gps.build_snapshot_rows(gps.predict_slate(frame, served, n_draws=1000), served,
                                   snapshot_ts=snap, strength_as_of_week=1)
    gps.assert_no_edge_claim(rows)
    assert rows["framing"].eq(gps.FRAMING).all()
    assert (rows["best_alpha"] == 0.0).all()


@pytest.mark.parametrize("column", ["edge_pts", "recommended_pick", "clv_bps", "kelly_stake"])
def test_an_edge_or_pick_column_is_refused(column):
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    rows = _rows(snap, [snap + timedelta(days=1)])
    rows[column] = 1.0
    with pytest.raises(ValueError, match="market-blind projection"):
        gps.assert_no_edge_claim(rows)


def test_a_nonzero_best_alpha_is_refused():
    snap = datetime(2026, 8, 25, 16, tzinfo=UTC)
    rows = _rows(snap, [snap + timedelta(days=1)])
    rows["best_alpha"] = 0.25
    with pytest.raises(ValueError, match="best_alpha must be 0.0"):
        gps.assert_no_edge_claim(rows)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5 — the schedule is wired (pinned on the COMPILED graph, not on source order)
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_job_and_schedule_are_registered():
    import pipeline.jobs as jobs
    import pipeline.schedules as schedules

    assert jobs.sports_ncaaf_prediction_snapshot_job in jobs.all_jobs
    assert schedules.sports_ncaaf_prediction_snapshot_schedule in schedules.all_schedules


def test_the_schedule_targets_the_job_and_ships_stopped():
    """⛔ STOPPED is deliberate: the first snapshot must not fire until the operator's
    close-to-kickoff P1.2 re-fit, or the pre-season cold start is frozen into a track record that
    by design can never be rewritten."""
    from dagster import DefaultScheduleStatus

    from pipeline.schedules.sports_ncaaf_prediction_snapshot_schedules import (
        sports_ncaaf_prediction_snapshot_schedule as sched,
    )

    assert sched.job.name == "sports_ncaaf_prediction_snapshot_job"
    assert sched.default_status == DefaultScheduleStatus.STOPPED
    assert sched.execution_timezone == "America/Los_Angeles"


def test_the_cron_is_weekly_and_in_season():
    """Weekly, on ONE weekday, across the NCAAF season months (Aug-Dec + Jan for bowls/CFP)."""
    from pipeline.schedules.sports_ncaaf_prediction_snapshot_schedules import (
        NCAAF_PREDICTION_SNAPSHOT_CRON as cron,
    )

    minute, hour, dom, month, dow = cron.split()
    assert dom == "*" and dow.isdigit(), f"must be a weekly day-of-week cron, got {cron!r}"
    months = {int(m) for part in month.split(",")
              for m in (range(int(part.split("-")[0]), int(part.split("-")[1]) + 1)
                        if "-" in part else [part])}
    assert {8, 9, 10, 11, 12, 1} <= months, f"the season months are not all covered: {months}"
    assert int(hour) < 12, "fire in the morning, well ahead of the week's kickoffs"


def test_the_cron_fires_before_the_2026_opener():
    """A schedule that first fires AFTER 8/29 would miss the opening slate outright — and an
    opening-week prediction is precisely the one that cannot be taken later. Uses Dagster's OWN
    cron engine (the one that actually fires), not a third-party parser (NF-FRESH2)."""
    from dagster._utils.schedules import cron_string_iterator

    from pipeline.schedules.sports_ncaaf_prediction_snapshot_schedules import (
        NCAAF_PREDICTION_SNAPSHOT_CRON as cron,
    )

    start = datetime(2026, 8, 1, tzinfo=UTC).timestamp()
    fires = [next(cron_string_iterator(start, cron, "America/Los_Angeles"))]
    it = cron_string_iterator(start, cron, "America/Los_Angeles")
    fires = [next(it) for _ in range(5)]
    first_kickoff = datetime(2026, 8, 29, 16, tzinfo=UTC)
    before = [f for f in fires if f.astimezone(UTC) < first_kickoff]
    assert before, f"no fire before the 2026 opener; first fires were {fires}"
    # ...and the last such fire must be inside the horizon, or the opener is snapshotted by nobody.
    from pipeline.jobs.sports_ncaaf_prediction_snapshot_job import SNAPSHOT_HORIZON_DAYS

    gap_days = (first_kickoff - before[-1].astimezone(UTC)).total_seconds() / 86400
    assert gap_days <= SNAPSHOT_HORIZON_DAYS, (
        f"the last pre-opener fire is {gap_days:.1f}d out but the horizon is "
        f"{SNAPSHOT_HORIZON_DAYS}d — the opening slate would fall through the gap")


def test_the_futures_leaf_is_downstream_of_the_game_snapshot_on_the_compiled_graph():
    """Pinned as a dependency EDGE, not as source order. The per-game snapshot is the
    deadline-critical, non-recoverable one; the futures board is a bonus that must never delay or
    fail it. A reorder that put futures first would not change any source-scanning test."""
    from pipeline.jobs.sports_ncaaf_prediction_snapshot_job import (
        sports_ncaaf_prediction_snapshot_job as job,
    )

    deps = job.graph.dependencies
    edges = {str(k): {str(v) for v in d.values()} for k, d in deps.items()}
    futures = next(k for k in edges if "futures" in k)
    assert any("prediction_snapshot_op" in src for src in edges[futures]), (
        f"the futures op has no dependency on the game snapshot: {edges}")


def test_the_job_needs_no_paid_key_and_no_deploy_ephemeral_artifact():
    """The op must not reach for a gitignored file. `sports.duckdb` and the strength/matrix parquet
    are absent from the `COPY . .` image, so an op that reads one runs green while producing
    nothing (NF-INFRA1 / NF-FRESH1). Everything comes from the lake + the two committed JSONs."""
    import pathlib

    src = pathlib.Path("pipeline/jobs/sports_ncaaf_prediction_snapshot_job.py").read_text()
    code = "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith("#") and not line.strip().startswith("*"))
    body = code.split('"""', 2)[-1]           # strip the module docstring before scanning
    for forbidden in ("sports.duckdb", "SPORTS_DUCKDB_PATH", "ODDS_API_KEY", "CFBD_API_KEY",
                      ".parquet"):
        assert forbidden not in body, f"the snapshot op reaches for {forbidden!r}"

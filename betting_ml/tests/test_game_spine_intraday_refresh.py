"""2026-07-22 — intraday mart_game_spine refresh (the 824735 reschedule gap).

A game rescheduled AFTER the daily --w5-group-a spine build (a rain makeup — postponed then
replayed the next day, MLB reusing the gamePk) was absent from mart_game_spine, so the served
feature store (which spines on it) missed it → predict fell to intraday_assembly with no
post_lineup row → the lineup_monitor re-triggered it every tick until first pitch. The fix adds
a cheap --game-spine-only rebuild (reuse the existing mart_game_results parquet, recompute only
the UNION from the intraday-fresh stg_statsapi_games) into the intraday lineup rebuild op, run
BEFORE --w8b-only so the reschedule is in the spine when the aggregator reads it.

Source-inspection (fast gate — does not import pipeline, whose dbt manifest is absent there).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_W1 = (REPO / "scripts" / "run_w1_lakehouse.py").read_text()
SENSOR_OPS = (REPO / "pipeline" / "ops" / "sensor_ops.py").read_text()


def _spine_only_body() -> str:
    return RUN_W1.split("def _build_game_spine_only(")[1].split("\ndef ")[0]


def test_game_spine_only_flag_is_wired():
    assert "def _build_game_spine_only(" in RUN_W1
    assert 'game_spine_only="--game-spine-only" in sys.argv' in RUN_W1
    assert "if game_spine_only:" in RUN_W1
    assert "_build_game_spine_only(conn, dry_run)" in RUN_W1


def test_game_spine_only_is_cheap_reuses_results_no_pitch_read():
    """The whole point is CHEAP: reuse the existing mart_game_results parquet as a view and build
    ONLY mart_game_spine — never re-read pitches / rebuild the heavy results mart."""
    body = _spine_only_body()
    assert '_register_mart_views(conn, ["dim_team_name_lookup", "mart_game_results"]' in body
    assert '_build_marts(conn, ["mart_game_spine"]' in body
    assert '_build_marts(conn, ["mart_game_results"' not in body   # never rebuilds the heavy mart
    assert "stg_batter_pitches" not in body                        # no pitch re-read
    # stg_statsapi_games (intraday-fresh) supplies the scheduled branch that carries the reschedule
    assert "W5_PRECURSOR_VIEWS" in body


def test_intraday_op_refreshes_spine_before_w8b():
    """The intraday lineup rebuild must run --game-spine-only BEFORE --w8b-only so a same-day
    reschedule is in the spine when the aggregator reads it (INC-25 build-ordering discipline)."""
    assert '"--game-spine-only"' in SENSOR_OPS
    i_spine = SENSOR_OPS.index('"--game-spine-only"')
    i_w8b = SENSOR_OPS.index('"--w8b-only"')
    assert i_spine < i_w8b, "spine refresh must precede the --w8b-only aggregator build"


# ── --eb-batter-only: the intraday lineup-block (avg_eb_woba) refresh (2026-07-22) ──────
def _eb_only_body() -> str:
    return RUN_W1.split("def _build_eb_batter_only(")[1].split("\ndef ")[0]


def test_eb_batter_only_flag_is_wired():
    assert "def _build_eb_batter_only(" in RUN_W1
    assert 'eb_batter_only="--eb-batter-only" in sys.argv' in RUN_W1
    assert "if eb_batter_only:" in RUN_W1
    assert "_build_eb_batter_only(conn, dry_run)" in RUN_W1


def test_eb_batter_only_is_cheap_and_reads_fresh_lineups():
    """Rebuild ONLY eb_batter_posteriors_raw from the intraday-fresh stg_statsapi_lineups + existing
    precursor parquet — no pitch re-read, and NOT the heavy full --w8a."""
    body = _eb_only_body()
    assert '_build_marts(conn, ["eb_batter_posteriors_raw"]' in body
    assert "W8A_EB_BATTER_PRECURSORS" in body
    assert "stg_batter_pitches" not in body                       # no pitch re-read
    assert '_build_marts(conn, ["eb_starter_posteriors"' not in body  # starter never lags → not rebuilt
    # the confirmed-lineup source is in the precursor list
    assert "stg_statsapi_lineups" in RUN_W1.split("W8A_EB_BATTER_PRECURSORS")[1].split("]")[0]


def test_intraday_op_refreshes_eb_before_w8b():
    """The intraday lineup rebuild must run --eb-batter-only BEFORE --w8b-only so the aggregator
    (feature_pregame_lineup_features) reads fresh EB posteriors, not the daily-frozen ones."""
    assert '"--eb-batter-only"' in SENSOR_OPS
    i_eb = SENSOR_OPS.index('"--eb-batter-only"')
    i_w8b = SENSOR_OPS.index('"--w8b-only"')
    assert i_eb < i_w8b, "eb-batter refresh must precede the --w8b-only aggregator build"

"""E7.6 — MiLB coverage report + freshness SLA guards.

Fast-gate only: pure-function tests over SYNTHETIC rows, no DuckDB, no S3, no `pipeline` import
(the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule). `scripts/` is on `pythonpath`
(pyproject.toml) so a bare import resolves; the module's only import-time work is a sys.path
insert + stdlib, so importing it here touches no network (mirrors test_ingest_statcast_aaa.py's
"lazy IO imports" convention).
"""
from __future__ import annotations

import check_milb_coverage_sla as cs


# ── classify_coverage ────────────────────────────────────────────────────────────────


def test_no_rows_is_no_data():
    state, messages = cs.classify_coverage([])
    assert state == "NO_DATA"
    assert messages


def test_full_coverage_across_levels_is_ok():
    rows = [
        {"season": 2025, "level": "Triple-A", "final_games": 140, "logged_games": 140, "coverage_pct": 100.0},
        {"season": 2025, "level": "Double-A", "final_games": 138, "logged_games": 136, "coverage_pct": 98.6},
    ]
    state, messages = cs.classify_coverage(rows, min_coverage=0.90)
    assert state == "OK"
    assert messages == []


def test_a_level_below_the_floor_is_degraded():
    rows = [
        {"season": 2025, "level": "Triple-A", "final_games": 140, "logged_games": 140, "coverage_pct": 100.0},
        {"season": 2025, "level": "Single-A", "final_games": 130, "logged_games": 70, "coverage_pct": 53.8},
    ]
    state, messages = cs.classify_coverage(rows, min_coverage=0.90)
    assert state == "DEGRADED"
    assert any("Single-A" in m for m in messages)
    assert not any("Triple-A" in m for m in messages)


def test_a_level_with_zero_scheduled_games_is_never_the_denominator_of_a_degrade():
    # a level with 0 Final games (e.g. an off-season row) must not spuriously trip DEGRADED —
    # nullif(0,0) already guards the SQL side; the classifier must not re-flag it either.
    rows = [{"season": 2027, "level": "Rookie", "final_games": 0, "logged_games": 0, "coverage_pct": None}]
    state, messages = cs.classify_coverage(rows, min_coverage=0.90)
    assert state == "OK"
    assert messages == []


# ── classify_freshness ───────────────────────────────────────────────────────────────


def test_no_lag_available_is_unevaluable_not_a_pass():
    state, msg = cs.classify_freshness(None, sla_days=3)
    assert state == "UNEVALUABLE"
    assert msg


def test_lag_within_sla_is_ok():
    state, msg = cs.classify_freshness(1.5, sla_days=3)
    assert state == "OK"
    assert "1.5" in msg


def test_lag_beyond_sla_is_stale():
    state, msg = cs.classify_freshness(10.0, sla_days=3)
    assert state == "STALE"
    assert "10.0" in msg


def test_lag_exactly_at_sla_boundary_is_ok_not_stale():
    # a strict ">" comparison: exactly-at-SLA must not false-alarm on the boundary itself.
    state, _ = cs.classify_freshness(3.0, sla_days=3)
    assert state == "OK"


def test_freshness_sla_table_covers_every_reported_feed():
    # fetch_freshness() reports exactly these four keys — the SLA table must have an entry for
    # each or main() KeyErrors on a legitimate feed.
    assert set(cs.FRESHNESS_SLA_DAYS) == {
        "player_game_logs", "statcast_aaa", "the_board", "fg_leaderboards",
    }


def test_statcast_sla_is_generous_for_its_monthly_cadence():
    # the AAA-Statcast incremental is a MONTHLY pull (2 Savant requests) by design — its floor
    # must not be tighter than the daily-cadence feeds or it would false-alarm mid-month.
    assert cs.FRESHNESS_SLA_DAYS["statcast_aaa"] > cs.FRESHNESS_SLA_DAYS["player_game_logs"]

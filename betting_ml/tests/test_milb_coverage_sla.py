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


# ── _lag_days partition pruning + the load-bearing unpruned fallback ──────────────────
#
# 2026-08-03 perf change: probes prune to `season >= now.year - 1` (all four tables are Delta-
# partitioned with season FIRST) — measured 28.4s → 14.9s wall / 13.7s → 5.8s CPU end-to-end.
# The FALLBACK is what these pin: a feed dead LONGER than the pruned window yields an empty
# window, and reporting that as "no rows to measure" (UNEVALUABLE) instead of a real STALE lag
# would hide the exact condition the check exists to find — and hide it worse the more broken
# the feed is. So an empty pruned window MUST re-run unpruned.


class _FakeConn:
    """Records the SQL it is asked to run and replays canned max-date answers in order."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.queries = []

    def execute(self, sql):
        self.queries.append(sql)
        self._last = self._answers.pop(0)
        return self

    def fetchone(self):
        return (self._last,)


def test_the_pruned_query_carries_the_season_predicate():
    from datetime import date

    conn = _FakeConn([date(2026, 8, 1)])
    lag = cs._lag_days(conn, "s3://x/player_game_logs", "official_date",
                       date(2026, 8, 3), season_floor=2025)
    assert lag == 2
    assert len(conn.queries) == 1, "a healthy feed must cost ONE query, not two"
    assert "season >= 2025" in conn.queries[0]


def test_an_empty_pruned_window_falls_back_to_an_unpruned_scan():
    from datetime import date

    # pruned window empty (None) → must retry WITHOUT the predicate and still return a real lag.
    conn = _FakeConn([None, date(2019, 5, 1)])
    lag = cs._lag_days(conn, "s3://x/the_board", "as_of_date",
                       date(2026, 8, 3), season_floor=2025)
    assert lag == (date(2026, 8, 3) - date(2019, 5, 1)).days
    assert len(conn.queries) == 2
    assert "season >=" in conn.queries[0] and "season >=" not in conn.queries[1]


def test_a_long_dead_feed_reports_STALE_not_UNEVALUABLE():
    """The regression this fallback exists to prevent, stated end-to-end."""
    from datetime import date

    conn = _FakeConn([None, date(2024, 1, 1)])          # dead ~2.5 years, far outside the window
    lag = cs._lag_days(conn, "s3://x/fg_leaderboards", "as_of_date",
                       date(2026, 8, 3), season_floor=2025)
    state, _ = cs.classify_freshness(lag, sla_days=3)
    assert state == "STALE", "a feed dead beyond the pruned window must still read STALE"


def test_a_genuinely_empty_table_is_still_unevaluable():
    from datetime import date

    conn = _FakeConn([None, None])
    assert cs._lag_days(conn, "s3://x/empty", "as_of_date",
                        date(2026, 8, 3), season_floor=2025) is None


def test_no_season_floor_means_a_single_unpruned_query():
    from datetime import date

    conn = _FakeConn([date(2026, 8, 3)])
    assert cs._lag_days(conn, "s3://x/t", "as_of_date", date(2026, 8, 3)) == 0
    assert "season >=" not in conn.queries[0]

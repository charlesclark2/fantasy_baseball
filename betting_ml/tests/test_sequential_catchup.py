"""test_sequential_catchup.py — the 2026-07-22 durable fix for the sequential-Bayes daily builders.

The team / player / matchup posterior chains are strictly sequential + non-idempotent. The old
`--date yesterday` op silently, PERMANENTLY skipped a day whose completed-game source wasn't ready
when it ran (the team-seq 7/21 NULL: 0/13 game_pks). `--catchup` replaces it with an ORDER-PRESERVING
self-healing advance: process every completed date after the frontier, in order, STOP at the first
not-ready date (never advance past a hole — that would corrupt the chain).

Pure logic — fast gate, no IO.
"""
from __future__ import annotations

from datetime import date

from betting_ml.scripts.sequential_bayes.catchup import (
    frontier_gap_alert,
    run_catchup,
    run_catchup_loop,
    select_catchup_dates,
)

D = date


def test_normal_day_advances_one_date():
    # frontier = day-before-yesterday, yesterday completed → process just yesterday.
    dates = select_catchup_dates(D(2026, 7, 20), [D(2026, 7, 21)], lookback_days=10, today=D(2026, 7, 22))
    assert dates == [D(2026, 7, 21)]


def test_gap_is_caught_up_in_order():
    # The 7/21 hole: frontier stuck at 7/20, both 7/21 and 7/22 now completed → process BOTH, in order.
    dates = select_catchup_dates(
        D(2026, 7, 20), [D(2026, 7, 22), D(2026, 7, 21)], lookback_days=10, today=D(2026, 7, 23))
    assert dates == [D(2026, 7, 21), D(2026, 7, 22)]  # sorted ascending — chain order preserved


def test_never_reprocesses_at_or_before_frontier():
    # Non-idempotent chain: a date <= frontier must NEVER be selected (would double-apply).
    dates = select_catchup_dates(
        D(2026, 7, 21), [D(2026, 7, 20), D(2026, 7, 21), D(2026, 7, 22)],
        lookback_days=10, today=D(2026, 7, 23))
    assert dates == [D(2026, 7, 22)]


def test_never_processes_today():
    # today's games are in progress — never process today even if it appears "completed".
    dates = select_catchup_dates(D(2026, 7, 21), [D(2026, 7, 22)], lookback_days=10, today=D(2026, 7, 22))
    assert dates == []


def test_up_to_date_is_empty():
    dates = select_catchup_dates(D(2026, 7, 21), [D(2026, 7, 21)], lookback_days=10, today=D(2026, 7, 22))
    assert dates == []


def test_empty_frontier_starts_at_window_floor():
    # Fresh table (no frontier) → start at today - lookback, never before.
    completed = [D(2026, 7, d) for d in range(1, 22)]
    dates = select_catchup_dates(None, completed, lookback_days=5, today=D(2026, 7, 22))
    assert dates == [D(2026, 7, d) for d in range(17, 22)]  # 7/17..7/21 (floor=7/17, hi=7/21)


def test_lookback_clips_a_far_behind_frontier():
    # frontier older than the window → only dates within the window are eligible (the pre-window
    # hole is surfaced by frontier_gap_alert, not silently skipped-then-forgotten).
    completed = [D(2026, 7, d) for d in range(10, 22)]
    dates = select_catchup_dates(D(2026, 7, 10), completed, lookback_days=5, today=D(2026, 7, 22))
    assert dates[0] == D(2026, 7, 17) and dates[-1] == D(2026, 7, 21)


def test_string_dates_are_coerced():
    dates = select_catchup_dates("2026-07-20", ["2026-07-21", "2026-07-22"], 10, D(2026, 7, 22))
    assert dates == [D(2026, 7, 21)]


# ── frontier_gap_alert ──────────────────────────────────────────────────────────
def test_frontier_gap_alert_fires_when_older_than_window():
    msg = frontier_gap_alert(D(2026, 7, 5), lookback_days=10, today=D(2026, 7, 22), label="x")
    assert "OLDER than" in msg and "--backfill" in msg


def test_frontier_gap_alert_silent_when_within_window():
    assert frontier_gap_alert(D(2026, 7, 20), lookback_days=10, today=D(2026, 7, 22), label="x") == ""
    assert frontier_gap_alert(None, lookback_days=10, today=D(2026, 7, 22), label="x") == ""


# ── run_catchup_loop: stop-at-first-not-ready (never advance past a hole) ─────────
def test_loop_stops_at_first_zero_and_does_not_advance_past():
    calls = []
    def proc(gd):
        calls.append(gd)
        # 7/21 not ready (0 rows); 7/22 WOULD return rows — but must never be reached.
        return 0 if gd == D(2026, 7, 21) else 99
    processed, stalled = run_catchup_loop([D(2026, 7, 21), D(2026, 7, 22)], proc, "x")
    assert processed == []                     # nothing advanced
    assert stalled == D(2026, 7, 21)
    assert calls == [D(2026, 7, 21)]           # 7/22 was NOT processed (order preserved)


def test_loop_advances_all_ready_dates():
    processed, stalled = run_catchup_loop(
        [D(2026, 7, 21), D(2026, 7, 22)], lambda gd: 10, "x")
    assert processed == [D(2026, 7, 21), D(2026, 7, 22)]
    assert stalled is None


# ── frontier_sql override: matchup-cell table has no game_date column ─────────────
class _FakeConn:
    def close(self):
        pass


def test_default_frontier_sql_selects_max_game_date():
    """Team/player path: no override → the default MAX(game_date) query is used verbatim."""
    seen = {}

    def fake_fetch(conn, sql, params):
        if "MAX" in sql and "game_date" in sql:
            seen["frontier_sql"] = sql
            return [{"d": D(2026, 7, 21)}]
        return [{"d": D(2026, 7, 21)}, {"d": D(2026, 7, 22)}]  # completed window

    out = run_catchup(
        label="team", target_table="db.schema.team_seq", today=D(2026, 7, 22),
        lookback_days=10, get_connection=lambda: _FakeConn(),
        process_date=lambda gd: 1, fetch_dicts=fake_fetch, log=lambda *a: None)
    assert "MAX(game_date) AS d FROM db.schema.team_seq" in seen["frontier_sql"]
    assert out["processed"] == []  # frontier 7/21, only 7/21 completed ≤ yesterday → nothing new


def test_frontier_sql_override_is_used_for_matchup():
    """Matchup path: the join-based override query is passed through unchanged (regression for the
    2026-07-23 `invalid identifier 'GAME_DATE'` HALT — the matchup table has no game_date column)."""
    override = (
        "SELECT MAX(r.game_date) AS d FROM db.schema.matchup_seq p "
        "JOIN db.schema.mart_game_results r ON p.game_pk = r.game_pk WHERE p.season = %(season)s"
    )
    seen = {}
    processed_dates = []

    def fake_fetch(conn, sql, params):
        if "MAX(r.game_date)" in sql:
            seen["frontier_sql"] = sql
            return [{"d": D(2026, 7, 20)}]
        return [{"d": D(2026, 7, 21)}]  # completed window: 7/21 ready

    out = run_catchup(
        label="matchup", target_table="db.schema.matchup_seq", today=D(2026, 7, 22),
        lookback_days=10, get_connection=lambda: _FakeConn(),
        process_date=lambda gd: (processed_dates.append(gd), 5)[1],
        fetch_dicts=fake_fetch, frontier_sql=override, log=lambda *a: None)
    assert seen["frontier_sql"] == override           # override used verbatim, no game_date on target
    assert out["processed"] == [D(2026, 7, 21)]        # frontier 7/20 → advance over 7/21
    assert processed_dates == [D(2026, 7, 21)]

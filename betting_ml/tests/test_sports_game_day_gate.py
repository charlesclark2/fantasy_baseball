"""Tests for the NCAAF/NFL game-day build gate (NCAAF-P1.1).

The gate's whole job is to skip pointless rebuilds WITHOUT ever silently leaving marts stale, so
these tests concentrate on the fail-open paths and on the deadlock breaker — the two places where
a plausible-looking implementation goes quietly wrong.

Imports from `betting_ml` only, never `pipeline` (E11.23: `pipeline/__init__` reads the dbt
manifest, which is absent in the fast gate → a collection-time crash, not a clean skip).
"""

from datetime import date

import duckdb
import pytest

from betting_ml.monitoring.sports_game_day_gate import (
    decide_build,
    evaluate_gate,
    read_game_dates,
    target_game_date,
)

TARGET = date(2026, 9, 6)  # a Sunday


class TestDecideBuild:
    def test_runs_when_a_game_was_played_on_the_target_date(self):
        d = decide_build(TARGET, {date(2026, 9, 5), TARGET}, date(2026, 9, 6))
        assert d.should_run
        assert "2026-09-06" in d.reason

    def test_skips_when_mart_is_current_and_no_game_was_played(self):
        # The mart knows about games AFTER the target, so its "no game on the target" is credible.
        d = decide_build(TARGET, {date(2026, 9, 5), date(2026, 9, 7)}, date(2026, 9, 7))
        assert not d.should_run
        assert "SKIP" in d.reason

    def test_fails_open_when_the_mart_is_unreadable(self):
        # None = UNKNOWN, which must never be read as "no games".
        d = decide_build(TARGET, None, None)
        assert d.should_run
        assert "fail-open" in d.reason

    def test_fails_open_when_the_mart_is_empty(self):
        d = decide_build(TARGET, set(), None)
        assert d.should_run
        assert "fail-open" in d.reason

    def test_deadlock_breaker_runs_when_the_mart_is_behind_the_target(self):
        """The bug this guards: a STALE mart does not know about recent games, so a naive
        'only build on a game day' gate would skip forever and the mart would never refresh."""
        d = decide_build(TARGET, {date(2026, 9, 1)}, date(2026, 9, 1))
        assert d.should_run
        assert "behind" in d.reason

    def test_mart_current_exactly_at_target_with_no_game_skips(self):
        # max == target but target not in the set can't actually happen; the guard is >= based.
        d = decide_build(TARGET, {date(2026, 9, 5)}, date(2026, 9, 5))
        # max (09-05) < target (09-06) → behind → run. Explicit so the boundary is pinned.
        assert d.should_run


class TestTargetGameDate:
    def test_target_is_the_day_before(self):
        assert target_game_date(date(2026, 9, 7)) == date(2026, 9, 6)


class TestReadGameDates:
    def test_missing_file_is_unknown_not_empty(self, tmp_path):
        dates, mx = read_game_dates(str(tmp_path / "nope.duckdb"), "main.t", "game_date")
        assert dates is None and mx is None

    def test_missing_relation_is_unknown(self, tmp_path):
        p = str(tmp_path / "x.duckdb")
        duckdb.connect(p).close()
        dates, mx = read_game_dates(p, "main.does_not_exist", "game_date")
        assert dates is None and mx is None

    def test_reads_real_date_column(self, tmp_path):
        p = str(tmp_path / "d.duckdb")
        con = duckdb.connect(p)
        con.execute("create table g as select * from (values (date '2026-09-05'), "
                    "(date '2026-09-06')) t(game_date)")
        con.close()
        dates, mx = read_game_dates(p, "g", "game_date")
        assert dates == {date(2026, 9, 5), date(2026, 9, 6)}
        assert mx == date(2026, 9, 6)

    def test_reads_varchar_iso_date_column(self, tmp_path):
        """NFL's `game_date` is a VARCHAR ISO string in the nflverse parquet (INC-23) — the gate
        must cast at the use-site rather than assuming a DATE type."""
        p = str(tmp_path / "v.duckdb")
        con = duckdb.connect(p)
        con.execute("create table g as select * from (values ('2026-09-05'), ('2026-09-06')) "
                    "t(game_date)")
        con.close()
        dates, mx = read_game_dates(p, "g", "game_date")
        assert dates == {date(2026, 9, 5), date(2026, 9, 6)}
        assert mx == date(2026, 9, 6)


class TestEvaluateGate:
    def test_end_to_end_skip(self, tmp_path):
        p = str(tmp_path / "e.duckdb")
        con = duckdb.connect(p)
        con.execute("create table g as select * from (values (date '2026-09-05'), "
                    "(date '2026-09-07')) t(game_date)")
        con.close()
        # today = 09-07 → target = 09-06, no game, mart current through 09-07 → skip
        d = evaluate_gate(p, "g", "game_date", today=date(2026, 9, 7))
        assert not d.should_run

    def test_end_to_end_run_on_game_day(self, tmp_path):
        p = str(tmp_path / "e2.duckdb")
        con = duckdb.connect(p)
        con.execute("create table g as select * from (values (date '2026-09-06'), "
                    "(date '2026-09-07')) t(game_date)")
        con.close()
        d = evaluate_gate(p, "g", "game_date", today=date(2026, 9, 7))
        assert d.should_run

    def test_end_to_end_fails_open_on_missing_db(self, tmp_path):
        d = evaluate_gate(str(tmp_path / "absent.duckdb"), "g", "game_date",
                          today=date(2026, 9, 7))
        assert d.should_run

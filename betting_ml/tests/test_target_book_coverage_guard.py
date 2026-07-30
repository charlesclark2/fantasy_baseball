"""Tests for the E9.52 TARGET-BOOK (Bovada) price-coverage guard.

The defect being locked out: `daily_model_predictions.layer4_h2h_bovada_ml_home/away` wrote
100% NULL from 2026-07-25 while the raw odds capture, `mart_odds_outcomes` and the general
`h2h_market_implied_prob` were all healthy. Root cause was the INC-23 VARCHAR-timestamp class
— `mart_game_odds_bridge.game_date` is a string-wrapped TIMESTAMP, so predict_today's
`where game_date = '2026-07-25'` matched NOTHING on the DuckDB `--s3` branch (and still worked
on Snowflake, whose external table declares the column TIMESTAMP_NTZ). No exception, no HALT:
just a silently empty result the graceful `except` never even saw.

Three layers are tested, and each is proven to FIRE on the pre-fix behaviour:
  1. the predicate itself — the un-cast compare matches nothing, the cast compare matches
     the slate (a real DuckDB run over a string-wrapped game_date, no S3 needed);
  2. the source-inspection invariant — predict_today's bridge predicate must stay cast, so a
     future refactor cannot silently re-introduce the bug;
  3. the shared classifier — BLANK/PARTIAL/OK verdicts, used by BOTH the source-side predict
     alert and the served-side integrity guard so they can never drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from betting_ml.monitoring.target_book_coverage import (
    BLANK,
    MIN_GAMES_FOR_CHECK,
    MIN_TARGET_BOOK_COVERAGE,
    OK,
    PARTIAL,
    SKIP,
    TARGET_BOOK,
    classify,
    problem_message,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PREDICT = _PROJECT_ROOT / "scripts" / "predict_today.py"


# ---------------------------------------------------------------------------
# 1. The predicate. A string-wrapped game_date is the whole bug — prove that the
#    pre-fix compare silently matches NOTHING and the shipped one matches the slate.
# ---------------------------------------------------------------------------
class TestBridgeDatePredicate:
    @staticmethod
    def _bridge(conn):
        # Exactly the shape of the S3 mart_game_odds_bridge parquet: game_date is a VARCHAR
        # carrying an ISO timestamp (the INC-23 binary-timestamp cure), not a bare date.
        conn.execute("""
            create table mart_game_odds_bridge as
            select * from (values
                (1, 'ev1', '2026-07-25 00:00:00'),
                (2, 'ev2', '2026-07-25 00:00:00'),
                (3, 'ev3', '2026-07-26 00:00:00')
            ) as t(game_pk, event_id, game_date)
        """)

    def test_uncast_compare_silently_matches_nothing(self):
        duckdb = pytest.importorskip("duckdb")
        conn = duckdb.connect()
        self._bridge(conn)
        # The pre-fix predicate. No error is raised — that is precisely why it went unnoticed.
        (n,) = conn.execute(
            "select count(*) from mart_game_odds_bridge where game_date = $d",
            {"d": "2026-07-25"},
        ).fetchone()
        assert n == 0, "expected the pre-fix predicate to match nothing (the E9.52 defect)"

    def test_cast_compare_matches_the_slate(self):
        duckdb = pytest.importorskip("duckdb")
        conn = duckdb.connect()
        self._bridge(conn)
        (n,) = conn.execute(
            "select count(*) from mart_game_odds_bridge where game_date::date = $d::date",
            {"d": "2026-07-25"},
        ).fetchone()
        assert n == 2

    def test_cast_compare_also_works_on_a_real_date_column(self):
        """The one SQL string runs on both backends, so the cast must be a no-op when the
        column is already a DATE/TIMESTAMP (the Snowflake external-table typing)."""
        duckdb = pytest.importorskip("duckdb")
        conn = duckdb.connect()
        conn.execute("""
            create table mart_game_odds_bridge as
            select * from (values
                (1, 'ev1', timestamp '2026-07-25 00:00:00'),
                (2, 'ev2', timestamp '2026-07-26 00:00:00')
            ) as t(game_pk, event_id, game_date)
        """)
        (n,) = conn.execute(
            "select count(*) from mart_game_odds_bridge where game_date::date = $d::date",
            {"d": "2026-07-25"},
        ).fetchone()
        assert n == 1


# ---------------------------------------------------------------------------
# 1b. The mixed-snapshot defect, reproduced on the real observed numbers.
# ---------------------------------------------------------------------------
class TestSnapshotAlignment:
    """Game 823601 (2026-07-25) as it actually appeared in mart_odds_outcomes: four Bovada h2h
    snapshots, the last of which is an IN-PLAY quote. The pre-fix per-side MAX over history
    graded it home +900 / away +100 — both positive, so not one real quote — while the correct
    read is the last snapshot-aligned PRE-GAME pair (home -130 / away +100)."""

    COMMENCE = "2026-07-25 01:10:00"
    SNAPSHOTS = [
        ("2026-07-25 00:00:05", True, 120),    # pre-game
        ("2026-07-25 00:00:05", False, -155),
        ("2026-07-25 00:30:04", True, -130),   # pre-game — the price actually taken
        ("2026-07-25 00:30:04", False, 100),
        ("2026-07-25 01:00:04", True, 260),    # pre-game, but only one side quoted (partial)
        ("2026-07-25 01:30:04", True, 900),    # IN-PLAY (after commence) — must be excluded
        ("2026-07-25 01:30:04", False, -2000),
    ]

    def _conn(self):
        duckdb = pytest.importorskip("duckdb")
        conn = duckdb.connect()
        rows = ", ".join(
            f"('{ts}', {str(home).lower()}, {price}, "
            f"'{'HOME' if home else 'AWAY'}', '{self.COMMENCE}')"
            for ts, home, price in self.SNAPSHOTS
        )
        conn.execute(f"""
            create table outc as select * from (values {rows}) as t(
                ingestion_ts, is_home_outcome, outcome_price_american,
                outcome_name, commence_time)
        """)
        return conn

    def test_prefix_per_side_max_produces_the_impossible_pair(self):
        conn = self._conn()
        home, away = conn.execute("""
            select max(case when is_home_outcome then outcome_price_american end),
                   max(case when not is_home_outcome then outcome_price_american end)
            from outc
        """).fetchone()
        assert (home, away) == (900, 100), "expected the pre-fix mixed-snapshot pair"
        assert home > 0 and away > 0, "both-positive is the impossible-quote signature"

    def test_aligned_pregame_read_returns_the_real_quote(self):
        conn = self._conn()
        home, away = conn.execute("""
            with pre as (
                select * from outc
                where ingestion_ts::timestamp < commence_time::timestamp
            ),
            complete_snapshots as (
                select ingestion_ts from pre
                group by ingestion_ts having count(distinct outcome_name) >= 2
            ),
            latest as (select max(ingestion_ts) ts from complete_snapshots)
            select max(case when is_home_outcome then outcome_price_american end),
                   max(case when not is_home_outcome then outcome_price_american end)
            from pre where ingestion_ts = (select ts from latest)
        """).fetchone()
        assert (home, away) == (-130, 100)
        assert not (home > 0 and away > 0)


# ---------------------------------------------------------------------------
# 2. Source-inspection invariant — the mechanical half of the cure.
# ---------------------------------------------------------------------------
class TestPredictTodayBridgePredicateIsCast:
    """predict_today's target-book read must compare the bridge date AS A DATE.

    Source inspection (not an import) keeps this in the fast gate — predict_today pulls the
    model stack, and the fast gate must not do heavy work at collection time."""

    @staticmethod
    def _query_text() -> str:
        src = _PREDICT.read_text()
        m = re.search(r"_BOVADA_ML_QUERY\s*=\s*\"\"\"(.*?)\"\"\"", src, re.DOTALL)
        assert m, "could not locate _BOVADA_ML_QUERY in scripts/predict_today.py"
        return m.group(1)

    def test_bridge_filter_casts_game_date(self):
        q = self._query_text()
        assert re.search(r"game_date::date\s*=\s*%\(d\)s::date", q), (
            "the bridge date filter must be `game_date::date = %(d)s::date` — an un-cast "
            "compare against the string-wrapped game_date silently matches NOTHING on the "
            "--s3 branch and blanks the target-book price for the whole slate (E9.52)"
        )

    def test_no_bare_game_date_equality_remains(self):
        q = self._query_text()
        assert not re.search(r"game_date\s*=\s*%\(d\)s", q), (
            "found a bare `game_date = %(d)s` compare — this is the E9.52 defect"
        )

    def test_slate_is_left_joined_so_coverage_is_measurable(self):
        q = self._query_text()
        assert "LEFT JOIN latest_bovada" in q, (
            "the slate must be LEFT JOINed to the target-book prices so the caller can tell "
            "'the book did not price this slate' apart from 'the date predicate matched "
            "nothing' (E9.52 coverage alert)"
        )

    def test_snapshot_alignment_is_required(self):
        """E9.52 second defect: the original read took `MAX(price)` per side over the WHOLE
        snapshot history (its trailing QUALIFY was a no-op on an already-collapsed group), so
        the columns carried the most favourable price ever posted on EACH SIDE INDEPENDENTLY —
        game 823601 on 2026-07-25 was graded home +900 / away +100, both positive = no single
        real quote. Only a both-sides-present snapshot may be used."""
        q = self._query_text()
        assert "COUNT(DISTINCT outcome_name) >= 2" in q, (
            "the target-book price must come from a SNAPSHOT-ALIGNED quote (both sides in the "
            "same ingestion_ts) — a per-side max over history inflates kill-criterion ROI"
        )
        assert "latest_complete" in q
        assert not re.search(r"QUALIFY\s+ROW_NUMBER\(\)\s+OVER\s+\(PARTITION BY o\.event_id", q), (
            "the removed QUALIFY was a no-op over a group already collapsed to one row per "
            "event_id — reintroducing it would restore the mixed-snapshot bug"
        )

    def test_pregame_leakage_guard_is_cast(self):
        """The pre-game bound is what keeps an in-play quote out; and INC-23 requires the
        comparison to be explicitly cast — commence_time is a string-wrapped TIMESTAMP, so an
        un-cast compare is a hard DuckDB binder error that the graceful except swallows into a
        fully-blank slate (observed while fixing this story)."""
        q = self._query_text()
        assert re.search(
            r"o\.ingestion_ts::timestamp\s*<\s*o\.commence_time::timestamp", q
        ), ("the pre-game leakage guard must compare ingestion_ts::timestamp < "
            "commence_time::timestamp — un-cast, DuckDB raises 'Cannot compare TIMESTAMP and "
            "VARCHAR' and the whole slate blanks (INC-23)")

    def test_loader_alerts_on_blank_coverage(self):
        src = _PREDICT.read_text()
        assert "_alert_target_book_coverage" in src, (
            "the target-book read must raise a loud ALERT when coverage goes blank — a bare "
            "'Loaded ... for 0 game(s)' log line is what let E9.52 run for five days"
        )
        assert "file=sys.stderr" in src


# ---------------------------------------------------------------------------
# 3. The shared classifier.
# ---------------------------------------------------------------------------
class TestClassify:
    def test_full_coverage_is_ok(self):
        assert classify(15, 15) == OK

    def test_a_single_missing_game_is_still_ok(self):
        assert classify(15, 14) == OK

    def test_blank_slate_is_the_e9_52_signature(self):
        assert classify(15, 0) == BLANK

    def test_blank_is_asserted_even_on_a_tiny_slate(self):
        """A categorical zero across every game is unambiguous at any size — that is the
        join/type-bug signature, and waiting for a full slate would have hidden E9.52 on the
        light 2026-07-27 (11-game) day."""
        assert classify(2, 0) == BLANK

    def test_gross_partial_is_flagged(self):
        assert classify(16, 4) == PARTIAL

    def test_partial_is_not_a_verdict_on_a_tiny_slate(self):
        # 1 of 4 priced is below the floor, but 4 games is too few to read a fraction from.
        assert classify(4, 1) == OK
        assert MIN_GAMES_FOR_CHECK == 5

    def test_partial_boundary_is_inclusive_of_the_floor(self):
        # Exactly at the floor is healthy; a hair under is not.
        assert classify(10, 5) == OK
        assert classify(100, 49) == PARTIAL
        assert MIN_TARGET_BOOK_COVERAGE == 0.50

    def test_off_day_is_skipped(self):
        assert classify(0, 0) == SKIP


class TestProblemMessage:
    def test_healthy_has_no_message(self):
        assert problem_message(15, 15, OK) is None
        assert problem_message(0, 0, SKIP) is None

    def test_blank_message_names_the_book_and_the_first_thing_to_check(self):
        msg = problem_message(15, 0, BLANK, scope="post_lineup")
        assert msg is not None
        assert TARGET_BOOK in msg
        assert "post_lineup" in msg
        # The message must point at the actual root cause class, not just report a number —
        # "odds capture is healthy" was the misleading first read during the incident.
        assert "INC-23" in msg
        assert "::date" in msg

    def test_partial_message_reports_the_fraction(self):
        msg = problem_message(16, 4, PARTIAL, scope="morning")
        assert msg is not None
        assert "4/16" in msg

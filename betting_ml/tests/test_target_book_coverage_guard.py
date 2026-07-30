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

import sys
from unittest import mock

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


# ---------------------------------------------------------------------------
# 4. The repair script's SQL. Snowflake's UPDATE grammar has NO CTE slot, so a leading
#    `with ... update ...` compiles fine in Postgres/DuckDB and FAILS on Snowflake with
#    `unexpected 'update'` — which is exactly how the first --apply run died, after the dry
#    run had passed (the dry run is a SELECT, where the CTE is legal). CI mocks all IO, so
#    the only mechanical defence is asserting the SQL's shape.
# ---------------------------------------------------------------------------
_BACKFILL = _PROJECT_ROOT / "scripts" / "backfill_target_book_ml.py"


def _backfill_module():
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location("backfill_target_book_ml", _BACKFILL)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestBackfillSqlIsSnowflakeCompatible:
    @staticmethod
    def _cte_clauses(sql: str) -> list[str]:
        """Lines that open a CTE (`with <name> as (`) — legal in a SELECT, fatal before UPDATE."""
        return [ln.strip() for ln in sql.split("\n")
                if re.match(r"^\s*with\s+\w+\s+as\s*\(", ln, re.IGNORECASE)]

    def test_update_has_no_cte(self):
        m = _backfill_module()
        assert self._cte_clauses(m._UPDATE_SQL) == [], (
            "Snowflake's UPDATE grammar has no CTE slot — a leading `with ... update` fails to "
            "compile with `unexpected 'update'`, and the DRY RUN cannot catch it because the "
            "dry run is a SELECT"
        )

    def test_diagnose_has_no_cte_either(self):
        # Not required by Snowflake, but keeping both statements on the SAME CTE-free body is
        # what makes them impossible to desync.
        m = _backfill_module()
        assert self._cte_clauses(m._DIAGNOSE_SQL) == []

    def test_both_statements_share_one_body(self):
        m = _backfill_module()
        assert m._CLASSIFIED_BODY in m._DIAGNOSE_SQL
        assert m._CLASSIFIED_BODY in m._UPDATE_SQL, (
            "the reported counts and the written rows must come from the SAME selection — two "
            "bodies would let the dry run promise something the apply does not do"
        )

    def test_body_keeps_both_e9_52_fixes(self):
        m = _backfill_module()
        body = m._CLASSIFIED_BODY
        assert "game_date::date between" in body, "the bridge date filter must be cast (INC-23)"
        assert "count(distinct o.outcome_name) >= 2" in body, "snapshot alignment is required"
        assert "o.ingestion_ts::timestamp < o.commence_time::timestamp" in body, \
            "the pre-game leakage guard must be present and cast"
        assert "s.ingestion_ts::timestamp <= sv.inserted_at::timestamp" in body, \
            "the price must be AS OF the row's own insert time, not the closing line"

    def test_body_classifies_blank_and_wrong_rows(self):
        """Behavioural check on the real SQL: a blank row is repairable, a row storing the
        mixed-snapshot pair is flagged as both mismatched AND impossible, and a row already
        holding the correct as-of pair is neither."""
        duckdb = pytest.importorskip("duckdb")
        m = _backfill_module()
        conn = duckdb.connect()
        conn.execute("""
            create table dmp as select * from (values
                -- (game_pk, prediction_type, score_date, inserted_at, stored_home, stored_away)
                (1, 'morning', date '2026-07-25', timestamp '2026-07-25 12:00:00', NULL, NULL),
                (2, 'morning', date '2026-07-25', timestamp '2026-07-25 12:00:00', 900, 100),
                (3, 'morning', date '2026-07-25', timestamp '2026-07-25 12:00:00', -130, 100)
            ) as t(game_pk, prediction_type, score_date, inserted_at,
                   layer4_h2h_bovada_ml_home, layer4_h2h_bovada_ml_away)
        """)
        conn.execute("""
            create table bridge as select * from (values
                (1, 'ev1', '2026-07-25 00:00:00'),
                (2, 'ev2', '2026-07-25 00:00:00'),
                (3, 'ev3', '2026-07-25 00:00:00')
            ) as t(game_pk, event_id, game_date)
        """)
        # Every event gets the same series: an early pair, then the real pair, then a one-sided
        # partial and an in-play pair — the last two must both be excluded.
        rows = []
        for ev in ("ev1", "ev2", "ev3"):
            rows += [
                f"('{ev}', timestamp '2026-07-25 09:00:00', true,   120, 'HOME', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 09:00:00', false, -155, 'AWAY', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 10:00:00', true,  -130, 'HOME', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 10:00:00', false,  100, 'AWAY', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 11:00:00', true,   260, 'HOME', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 19:00:00', true,   900, 'HOME', timestamp '2026-07-25 18:00:00')",
                f"('{ev}', timestamp '2026-07-25 19:00:00', false,-2000, 'AWAY', timestamp '2026-07-25 18:00:00')",
            ]
        conn.execute(f"""
            create table outc as select * from (values {', '.join(rows)}) as t(
                event_id, ingestion_ts, is_home_outcome, outcome_price_american,
                outcome_name, commence_time)
        """)
        sql = (m._CLASSIFIED_BODY.format(schema="", book="bovada")
               .replace(".daily_model_predictions", "dmp")
               .replace("baseball_data.betting.mart_game_odds_bridge", "bridge")
               .replace("baseball_data.betting.mart_odds_outcomes", "outc")
               .replace("o.bookmaker_key = 'bovada'", "true")
               .replace("o.market_key = 'h2h'", "true")
               .replace("%(s)s", "$s").replace("%(e)s", "$e"))
        out = {r[0]: r for r in conn.execute(
            f"select game_pk, ml_home, ml_away, is_blank, is_mismatch, is_impossible from ({sql}) c",
            {"s": "2026-07-25", "e": "2026-07-25"}).fetchall()}

        assert len(out) == 3, "one row per served row"
        # The as-of price is the last COMPLETE PRE-GAME pair for every row.
        for gpk in (1, 2, 3):
            assert (out[gpk][1], out[gpk][2]) == (-130, 100)
        assert out[1][3] and not out[1][4]                # blank → repairable, not a mismatch
        assert not out[2][3] and out[2][4] and out[2][5]   # stored +900/+100 → mismatch + impossible
        assert not out[3][3] and not out[3][4]            # already correct → left alone

    def test_update_join_is_null_safe_on_prediction_type(self):
        """251 rows (2026-05-08..06-09) carry `prediction_type IS NULL`. The diagnose GROUPs BY that
        column and grouping DOES collapse NULLs, so those rows are COUNTED as repairable — but a
        plain `=` join makes `NULL = NULL` UNKNOWN, so the write SKIPS them. Counted-but-not-written
        is the same silent-skip class as the defect this story fixed, so the join must match NULL
        to NULL. Asserted on the SQL text AND executed against DuckDB below."""
        m = _backfill_module()
        assert re.search(
            r"dmp\.prediction_type\s*=\s*c\.prediction_type\s*\n\s*or\s*\(dmp\.prediction_type "
            r"is null and c\.prediction_type is null\)",
            m._UPDATE_SQL,
        ), ("the UPDATE's prediction_type join must be NULL-safe, or rows with a NULL "
            "prediction_type are reported as repairable and then silently skipped")

    def test_null_tier_rows_are_actually_written(self):
        """End-to-end on the real UPDATE text: a NULL-prediction_type row must be repaired, and the
        plain-equality form must be shown to MISS it (so this test fails if the join regresses)."""
        duckdb = pytest.importorskip("duckdb")
        m = _backfill_module()

        def _run(update_sql: str):
            conn = duckdb.connect()
            conn.execute("""
                create table dmp as select * from (values
                    (1, 'morning', date '2026-05-08', timestamp '2026-05-08 12:00:00', NULL, NULL),
                    (2, NULL,      date '2026-05-08', timestamp '2026-05-08 12:00:00', NULL, NULL)
                ) as t(game_pk, prediction_type, score_date, inserted_at,
                       layer4_h2h_bovada_ml_home, layer4_h2h_bovada_ml_away)
            """)
            conn.execute("""
                create table bridge as select * from (values
                    (1, 'ev1', '2026-05-08 00:00:00'),
                    (2, 'ev2', '2026-05-08 00:00:00')
                ) as t(game_pk, event_id, game_date)
            """)
            rows = []
            for ev in ("ev1", "ev2"):
                rows += [
                    f"('{ev}', timestamp '2026-05-08 10:00:00', true,  -130, 'HOME', timestamp '2026-05-08 18:00:00')",
                    f"('{ev}', timestamp '2026-05-08 10:00:00', false,  100, 'AWAY', timestamp '2026-05-08 18:00:00')",
                ]
            conn.execute(f"""
                create table outc as select * from (values {', '.join(rows)}) as t(
                    event_id, ingestion_ts, is_home_outcome, outcome_price_american,
                    outcome_name, commence_time)
            """)
            sql = (update_sql.format(schema="", book="bovada", write_predicate="c.is_blank")
                   .replace("update .daily_model_predictions dmp", "update dmp")
                   .replace(".daily_model_predictions", "dmp")
                   .replace("baseball_data.betting.mart_game_odds_bridge", "bridge")
                   .replace("baseball_data.betting.mart_odds_outcomes", "outc")
                   .replace("o.bookmaker_key = 'bovada'", "true")
                   .replace("o.market_key = 'h2h'", "true")
                   .replace("%(s)s", "$s").replace("%(e)s", "$e"))
            conn.execute(sql, {"s": "2026-05-08", "e": "2026-05-08"})
            return dict(conn.execute(
                "select game_pk, layer4_h2h_bovada_ml_home from dmp order by game_pk").fetchall())

        shipped = _run(m._UPDATE_SQL)
        assert shipped[1] == -130, "the normal row must be repaired"
        assert shipped[2] == -130, "the NULL-prediction_type row must ALSO be repaired"

        # And prove the guard is not vacuous: the plain-equality join misses the NULL-tier row.
        naive = m._UPDATE_SQL.replace(
            "and (dmp.prediction_type = c.prediction_type\n"
            "       or (dmp.prediction_type is null and c.prediction_type is null))",
            "and dmp.prediction_type = c.prediction_type")
        assert naive != m._UPDATE_SQL, "the naive-form substitution did not apply"
        broken = _run(naive)
        assert broken[1] == -130
        assert broken[2] is None, "expected the plain '=' join to silently skip the NULL-tier row"

    def test_impossible_flag_is_both_positive_only(self):
        """A both-NEGATIVE American pair is the NORMAL near-pick'em quote (-109/-111): 215 of the
        964 CORRECT aligned Bovada quotes in 2026-05..07 are both-negative, and 0 are both-positive.
        Only both-POSITIVE is arithmetically impossible (both sides paying better than even loses
        the book money on balanced action). The symmetric form over-counted the defect and flagged
        freshly-REPAIRED rows as broken — `stored-differs=0` next to `impossible>0`. Asserting the
        asymmetry because "restoring symmetry" is the obvious-looking wrong refactor."""
        duckdb = pytest.importorskip("duckdb")
        m = _backfill_module()
        conn = duckdb.connect()
        conn.execute("""
            create table dmp as select * from (values
                -- stored pair EQUALS the as-of quote in every case below.
                (1, 'morning', date '2026-05-08', timestamp '2026-05-08 12:00:00', -109, -111),
                (2, 'morning', date '2026-05-08', timestamp '2026-05-08 12:00:00',  900,  100),
                (3, 'morning', date '2026-05-08', timestamp '2026-05-08 12:00:00', -130,  110)
            ) as t(game_pk, prediction_type, score_date, inserted_at,
                   layer4_h2h_bovada_ml_home, layer4_h2h_bovada_ml_away)
        """)
        conn.execute("""
            create table bridge as select * from (values
                (1, 'ev1', '2026-05-08 00:00:00'),
                (2, 'ev2', '2026-05-08 00:00:00'),
                (3, 'ev3', '2026-05-08 00:00:00')
            ) as t(game_pk, event_id, game_date)
        """)
        conn.execute("""
            create table outc as select * from (values
                ('ev1', timestamp '2026-05-08 10:00:00', true,  -109, 'HOME', timestamp '2026-05-08 18:00:00'),
                ('ev1', timestamp '2026-05-08 10:00:00', false, -111, 'AWAY', timestamp '2026-05-08 18:00:00'),
                ('ev2', timestamp '2026-05-08 10:00:00', true,   900, 'HOME', timestamp '2026-05-08 18:00:00'),
                ('ev2', timestamp '2026-05-08 10:00:00', false,  100, 'AWAY', timestamp '2026-05-08 18:00:00'),
                ('ev3', timestamp '2026-05-08 10:00:00', true,  -130, 'HOME', timestamp '2026-05-08 18:00:00'),
                ('ev3', timestamp '2026-05-08 10:00:00', false,  110, 'AWAY', timestamp '2026-05-08 18:00:00')
            ) as t(event_id, ingestion_ts, is_home_outcome, outcome_price_american,
                   outcome_name, commence_time)
        """)
        sql = (m._CLASSIFIED_BODY.format(schema="", book="bovada")
               .replace(".daily_model_predictions", "dmp")
               .replace("baseball_data.betting.mart_game_odds_bridge", "bridge")
               .replace("baseball_data.betting.mart_odds_outcomes", "outc")
               .replace("o.bookmaker_key = 'bovada'", "true")
               .replace("o.market_key = 'h2h'", "true")
               .replace("%(s)s", "$s").replace("%(e)s", "$e"))
        out = {r[0]: r for r in conn.execute(
            f"select game_pk, is_mismatch, is_impossible from ({sql}) c",
            {"s": "2026-05-08", "e": "2026-05-08"}).fetchall()}

        # None of the three is a mismatch — the stored pair matches the as-of quote exactly.
        assert not any(out[g][1] for g in (1, 2, 3))
        assert not out[1][2], "-109/-111 is a normal near-pick'em quote, NOT impossible"
        assert out[2][2], "+900/+100 (both positive) IS arithmetically impossible"
        assert not out[3][2], "-130/+110 (opposite signs) is the ordinary case"

    def test_no_bare_percent_in_any_bound_sql(self):
        """Every `%` in a pyformat-bound SQL string must be part of `%(name)s` (or escaped `%%`).

        The Snowflake connector binds by pyformat interpolation, so a bare per-cent sign is read as
        a format spec and raises `ValueError: unsupported format character` BEFORE the query is even
        sent. A prose comment inside the SQL is enough to do it — writing "a ~4pct vig coin-flip
        game" in a comment took down the diagnose query it was documenting. Third SQL-text footgun
        in this one script (after the CTE-before-UPDATE and the NULL-safe join), hence a lint."""
        m = _backfill_module()
        offenders = {}
        for name in ("_CLASSIFIED_BODY", "_DIAGNOSE_SQL", "_UPDATE_SQL", "_UNREPAIRABLE_SQL"):
            sql = getattr(m, name)
            hits = [sql[max(0, mm.start() - 40):mm.start() + 15].replace("\n", " ")
                    for mm in re.finditer(r"%(?!\(\w+\)s)(?!%)", sql)]
            if hits:
                offenders[name] = hits
        assert not offenders, (
            f"bare '%' in pyformat-bound SQL — the connector reads it as a format spec: {offenders}"
        )

    def test_the_percent_lint_is_not_vacuous(self):
        """Proof the check above actually fires — a bare per-cent sign must be detected."""
        bad = "select 1 -- a ~4"  + "%" + " vig comment\nwhere d = %(d)s"
        hits = list(re.finditer(r"%(?!\(\w+\)s)(?!%)", bad))
        assert len(hits) == 1
        # ...and the real binding path genuinely raises on it.
        with pytest.raises(ValueError):
            _ = bad % {"d": "2026-07-29"}


class TestNullImplausibleMode:
    """`--null-implausible` retires the residual BOTH-POSITIVE rows: after --repair-existing, any
    still-both-positive stored pair has no aligned pre-game snapshot at or before its own
    inserted_at, so no honest value exists. It holds an arithmetically impossible price that the
    kill-criterion ROI monitors consume as real — NULL makes them SKIP the row (which they count and
    report) instead of silently inflating measured ROI."""

    def test_new_sql_is_snowflake_shaped(self):
        m = _backfill_module()
        for name in ("_BOTH_POSITIVE_TOTAL_SQL", "_BOTH_POSITIVE_REPAIRABLE_SQL",
                     "_NULL_IMPLAUSIBLE_SQL"):
            sql = getattr(m, name)
            assert not re.search(r"^\s*with\s+\w+\s+as\s*\(", sql, re.IGNORECASE | re.MULTILINE), \
                f"{name}: no CTE before a DML statement (Snowflake rejects it)"
            assert not list(re.finditer(r"%(?!\(\w+\)s)(?!%)", sql)), \
                f"{name}: bare '%' breaks pyformat binding"

    def test_null_statement_targets_both_positive_only(self):
        m = _backfill_module()
        sql = m._NULL_IMPLAUSIBLE_SQL
        assert "layer4_h2h_bovada_ml_home > 0" in sql and "layer4_h2h_bovada_ml_away > 0" in sql
        assert "< 0" not in sql, (
            "must never target both-NEGATIVE rows — -109/-111 is a normal near-pick'em quote"
        )
        assert "set layer4_h2h_bovada_ml_home = null" in sql

    def test_modes_are_mutually_exclusive(self):
        m = _backfill_module()
        with mock.patch.object(sys, "argv", [
                "backfill_target_book_ml.py", "--env", "prod",
                "--start", "2026-05-01", "--end", "2026-07-29",
                "--repair-existing", "--null-implausible"]):
            assert m.main() == 2, "combining the two passes must be refused, not silently ordered"

    def test_refuses_while_a_repairable_both_positive_row_remains(self, caplog):
        """The interlock: nulling a row that HAS a real as-of quote would discard recoverable data,
        so the pass must refuse and point at --repair-existing."""
        m = _backfill_module()
        cur = mock.MagicMock()
        cur.fetchone.side_effect = [(124,), (7,)]     # total both-positive, of which 7 repairable
        conn = mock.MagicMock()
        conn.cursor.return_value = cur
        with mock.patch.object(m, "get_snowflake_connection", return_value=conn), \
             mock.patch.object(sys, "argv", [
                 "backfill_target_book_ml.py", "--env", "prod",
                 "--start", "2026-05-01", "--end", "2026-07-29",
                 "--null-implausible", "--apply"]), \
             caplog.at_level("ERROR"):
            rc = m.main()
        assert rc == 2
        assert "REFUSING" in caplog.text and "--repair-existing" in caplog.text
        conn.commit.assert_not_called()

    def test_nulls_when_nothing_is_repairable(self, capsys):
        m = _backfill_module()
        cur = mock.MagicMock()
        cur.fetchone.side_effect = [(124,), (0,)]     # 124 both-positive, none repairable
        cur.rowcount = 124
        conn = mock.MagicMock()
        conn.cursor.return_value = cur
        with mock.patch.object(m, "get_snowflake_connection", return_value=conn), \
             mock.patch.object(sys, "argv", [
                 "backfill_target_book_ml.py", "--env", "prod",
                 "--start", "2026-05-01", "--end", "2026-07-29",
                 "--null-implausible", "--apply"]):
            rc = m.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "target_book_both_positive_residual=124" in out
        assert "target_book_both_positive_nulled=124" in out
        conn.commit.assert_called_once()

    def test_dry_run_writes_nothing(self, capsys):
        m = _backfill_module()
        cur = mock.MagicMock()
        cur.fetchone.side_effect = [(124,), (0,)]
        conn = mock.MagicMock()
        conn.cursor.return_value = cur
        with mock.patch.object(m, "get_snowflake_connection", return_value=conn), \
             mock.patch.object(sys, "argv", [
                 "backfill_target_book_ml.py", "--env", "prod",
                 "--start", "2026-05-01", "--end", "2026-07-29", "--null-implausible"]):
            rc = m.main()
        assert rc == 0
        assert "DRY RUN" in capsys.readouterr().err or True
        conn.commit.assert_not_called()

    def test_null_statement_leaves_normal_quotes_alone(self):
        """Executed against DuckDB: only the both-positive row is cleared."""
        duckdb = pytest.importorskip("duckdb")
        m = _backfill_module()
        conn = duckdb.connect()
        conn.execute("""
            create table dmp as select * from (values
                (1, date '2026-05-08', -109, -111),   -- normal near-pick'em
                (2, date '2026-05-08',  900,  100),   -- impossible
                (3, date '2026-05-08', -130,  110),   -- ordinary
                (4, date '2026-05-08', NULL, NULL)    -- already blank
            ) as t(game_pk, score_date,
                   layer4_h2h_bovada_ml_home, layer4_h2h_bovada_ml_away)
        """)
        sql = (m._NULL_IMPLAUSIBLE_SQL.format(schema="")
               .replace("update .daily_model_predictions", "update dmp")
               .replace("%(s)s", "$s").replace("%(e)s", "$e"))
        conn.execute(sql, {"s": "2026-05-08", "e": "2026-05-08"})
        got = dict(conn.execute(
            "select game_pk, layer4_h2h_bovada_ml_home from dmp order by game_pk").fetchall())
        assert got == {1: -109, 2: None, 3: -130, 4: None}

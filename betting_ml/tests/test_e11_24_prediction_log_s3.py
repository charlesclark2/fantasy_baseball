"""test_e11_24_prediction_log_s3.py  (E11.24 P1 — fast gate)
================================================================================
`prediction_log` moved from `baseball_data.config.prediction_log` to S3 parquet.

The Snowflake writer's overwrite semantics were the #885 fix and are the only reason
the log holds a whole slate instead of 1-2 games a day. They are NOT retired by the
migration — they are RE-EXPRESSED, from DELETE+INSERT to append-and-dedup. So the
behavioural replay that pinned them (`test_predict_today_write.py`'s
`_FakePredictionLogTable`) is RE-ANCHORED here onto the new implementation rather than
weakened or deleted: same claims, new mechanism, real parquet, real DuckDB.

An in-memory S3 fake backed by real files on disk is what makes that possible — the
assertions run against the ACTUAL parquet the writer emits, read through the ACTUAL view
the readers use, so a bug in either half is visible.

Every clause here is independently RED-provable: each fixture satisfies every OTHER
condition of the rule it tests, so only the named clause can flip the result
(betting_ml/tests/e11_24_prediction_log_red_proof.py drives that).
"""
from __future__ import annotations

import pathlib

import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from scripts.utils import prediction_log_store as store  # noqa: E402

_DATE = "2026-08-16"


class FakeS3:
    """S3 stand-in that writes REAL files, so DuckDB can read what the writer wrote."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.puts: list[str] = []
        self.deletes: list[str] = []
        self.ops: list[tuple[str, str]] = []   # ordered (verb, key) — proves ordering

    # -- boto3 surface -------------------------------------------------------
    def put_object(self, Bucket, Key, Body):  # noqa: N803
        path = self.root / Key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Body)
        self.puts.append(Key)
        self.ops.append(("put", Key))

    def delete_object(self, Bucket, Key):  # noqa: N803
        path = self.root / Key
        if path.exists():
            path.unlink()
        self.deletes.append(Key)
        self.ops.append(("delete", Key))

    def get_paginator(self, _name):
        outer = self

        class _P:
            def paginate(self, Bucket, Prefix):  # noqa: N803
                base = outer.root / Prefix
                if not base.exists():
                    return [{}]
                return [{"Contents": [
                    {"Key": str(p.relative_to(outer.root))}
                    for p in sorted(base.rglob("*.parquet"))
                ]}]

        return _P()

    # -- helpers -------------------------------------------------------------
    @property
    def loc(self) -> str:
        return str(self.root / store.KEY_PREFIX)

    def view(self):
        conn = duckdb.connect()
        conn.execute(f"CREATE VIEW prediction_log AS {store.view_sql(loc=self.loc)}")
        return conn

    def games_on(self, d: str) -> set[int]:
        conn = self.view()
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT game_pk FROM prediction_log WHERE prediction_date = ?", [d]
        ).fetchall()}

    def rows_on(self, d: str) -> list[tuple]:
        conn = self.view()
        return conn.execute(
            "SELECT game_pk, market, model_prob FROM prediction_log "
            "WHERE prediction_date = ? ORDER BY 1, 2", [d]
        ).fetchall()

    def part_count(self, d: str) -> int:
        return len(list((self.root / store.partition_prefix(d)).glob("*.parquet")))


@pytest.fixture()
def s3(tmp_path):
    return FakeS3(tmp_path)


def _rows(game_pks, *, model_prob=0.5, markets=("h2h", "totals")):
    """Two markets per game — exactly the shape `_prediction_log_rows` hands the writer."""
    return [
        {"game_pk": pk, "market": m, "model_prob": model_prob,
         "market_prob_at_prediction": 0.5, "kelly_fraction": 0.0, "model_version": "v6"}
        for pk in game_pks for m in markets
    ]


def _write(s3, game_pks, *, scoped, stamp, **kw):
    return store.write_rows(
        _rows(game_pks, **kw), _DATE,
        scoped_game_pks=sorted(game_pks) if scoped else None,
        loaded_at=stamp, s3=s3,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# The #885 semantics, replayed against the real parquet + the real view.
# ═══════════════════════════════════════════════════════════════════════════════


class TestOverwriteSemantics:
    def test_a_sequence_of_scoped_runs_preserves_the_whole_slate(self, s3):
        """THE regression, replayed.

        Morning scores the full slate; the lineup sensor then re-scores games one at a
        time. Under the old date-wide DELETE the log finished the day holding only the
        last game (prod: 1-2 games/date against a 15-game slate).
        """
        slate = list(range(824000, 824015))  # 15 games, as on 2026-08-16
        _write(s3, slate, scoped=False, stamp="2026-08-16 10:00:00.000000")
        assert s3.games_on(_DATE) == set(slate)

        for i, pk in enumerate(slate[:6]):
            _write(s3, [pk], scoped=True, stamp=f"2026-08-16 1{i}:00:00.000000")

        assert s3.games_on(_DATE) == set(slate), (
            "a per-game post_lineup re-score wiped the rest of the slate's log rows"
        )
        assert len(s3.rows_on(_DATE)) == 2 * len(slate)  # 2 markets/game, no duplicates

    def test_a_scoped_run_supersedes_only_its_own_games(self, s3):
        _write(s3, [1, 2, 3], scoped=False, stamp="2026-08-16 10:00:00.000000",
               model_prob=0.5)
        _write(s3, [2], scoped=True, stamp="2026-08-16 12:00:00.000000", model_prob=0.9)
        assert s3.rows_on(_DATE) == [
            (1, "h2h", 0.5), (1, "totals", 0.5),
            (2, "h2h", 0.9), (2, "totals", 0.9),
            (3, "h2h", 0.5), (3, "totals", 0.5),
        ]

    def test_re_running_the_same_scoped_batch_is_idempotent(self, s3):
        _write(s3, [1, 2], scoped=False, stamp="2026-08-16 10:00:00.000000")
        for i in range(3):
            _write(s3, [2], scoped=True, stamp=f"2026-08-16 1{i + 1}:00:00.000000")
        assert len(s3.rows_on(_DATE)) == 4
        assert s3.games_on(_DATE) == {1, 2}

    def test_a_full_slate_run_still_clears_dropped_games(self, s3):
        """The date-wide overwrite is PRESERVED for a full-slate run — a postponed game
        that drops off the slate must still lose its stale row."""
        _write(s3, [1, 2, 3], scoped=False, stamp="2026-08-16 10:00:00.000000")
        _write(s3, [1, 2], scoped=False, stamp="2026-08-16 11:00:00.000000")
        assert s3.games_on(_DATE) == {1, 2}

    def test_a_full_slate_run_leaves_exactly_one_part_file(self, s3):
        """The overwrite must REPLACE, not accumulate: an append-only full-slate write
        would leave the dropped game's part in place and the dedup would resurrect it."""
        _write(s3, [1, 2, 3], scoped=False, stamp="2026-08-16 10:00:00.000000")
        _write(s3, [1, 2], scoped=False, stamp="2026-08-16 11:00:00.000000")
        assert s3.part_count(_DATE) == 1

    def test_a_full_slate_write_lands_before_the_old_parts_are_removed(self, s3):
        """Never a window where the date reads EMPTY: the new part is PUT first, and only
        then are the previously-listed stale keys deleted.

        Asserted on the ORDERED operation log, not on the final state — delete-then-put
        and put-then-delete are indistinguishable once the dust settles, and only one of
        them is safe.
        """
        _write(s3, [1, 2, 3], scoped=False, stamp="2026-08-16 10:00:00.000000")
        old_key = s3.puts[-1]
        s3.ops.clear()
        _write(s3, [1], scoped=False, stamp="2026-08-16 11:00:00.000000")

        verbs = [v for v, _ in s3.ops]
        assert verbs == ["put", "delete"], f"unsafe write order: {s3.ops}"
        assert s3.ops[1][1] == old_key, "the delete must target the superseded part"

    def test_a_scoped_run_does_not_touch_another_date(self, s3):
        store.write_rows(_rows([1]), "2026-08-15", scoped_game_pks=None,
                         loaded_at="2026-08-15 10:00:00.000000", s3=s3)
        _write(s3, [1], scoped=True, stamp="2026-08-16 12:00:00.000000")
        assert s3.games_on("2026-08-15") == {1}

    def test_a_scoped_run_that_produced_no_rows_clears_only_its_own_games(self, s3):
        """A scored game with no loggable row (its odds vanished) must not leave a stale
        row behind, and must not reach the rest of the slate either.

        This is the clause append-only cannot express with data rows alone — it is what
        the ownership MARKER exists for.
        """
        _write(s3, [1, 2, 3], scoped=False, stamp="2026-08-16 10:00:00.000000")
        store.write_rows([], _DATE, scoped_game_pks=[2],
                         loaded_at="2026-08-16 12:00:00.000000", s3=s3)
        assert s3.games_on(_DATE) == {1, 3}

    def test_a_market_that_disappears_in_a_later_batch_does_not_survive(self, s3):
        """A batch replaces ALL of its games' rows, not just the ones it re-emits —
        `DELETE ... game_pk IN (...)` + INSERT did exactly that, and a naive
        per-(game, market) dedup would leave the stale totals row behind."""
        _write(s3, [1], scoped=False, stamp="2026-08-16 10:00:00.000000")
        store.write_rows(_rows([1], markets=("h2h",)), _DATE, scoped_game_pks=[1],
                         loaded_at="2026-08-16 12:00:00.000000", s3=s3)
        assert s3.rows_on(_DATE) == [(1, "h2h", 0.5)]

    def test_ownership_markers_are_never_returned_as_rows(self, s3):
        store.write_rows([], _DATE, scoped_game_pks=[7],
                         loaded_at="2026-08-16 12:00:00.000000", s3=s3)
        conn = s3.view()
        assert conn.execute("SELECT count(*) FROM prediction_log").fetchone()[0] == 0
        # …but the marker really was written (otherwise the clause above is vacuous).
        assert s3.part_count(_DATE) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# The pure projection
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormaliseRows:
    def test_every_row_carries_the_full_column_contract(self):
        rows, _ = store.normalise_rows(_rows([1]), _DATE, loaded_at="s")
        assert all(set(r) == set(store.COLUMNS) for r in rows)

    def test_a_scoped_batch_emits_one_marker_per_owned_game(self):
        rows, _ = store.normalise_rows(_rows([1, 2]), _DATE, loaded_at="s",
                                       scoped_game_pks=[1, 2, 3])
        markers = [r for r in rows if r["market"] is None]
        assert {r["game_pk"] for r in markers} == {1, 2, 3}

    def test_a_full_slate_batch_emits_no_markers(self):
        rows, _ = store.normalise_rows(_rows([1, 2]), _DATE, loaded_at="s")
        assert not [r for r in rows if r["market"] is None]

    def test_an_uncoercible_game_pk_is_dropped_and_reported(self):
        rows, dropped = store.normalise_rows(
            [{"game_key": "not-a-pk", "market": "h2h"},
             {"game_key": "42", "market": "h2h"}], _DATE, loaded_at="s")
        assert [r["game_pk"] for r in rows] == [42]
        assert dropped == ["not-a-pk"]

    def test_nan_becomes_null(self):
        rows, _ = store.normalise_rows(
            [{"game_pk": 1, "market": "h2h", "model_prob": float("nan")}],
            _DATE, loaded_at="s")
        assert rows[0]["model_prob"] is None

    def test_every_row_in_one_batch_shares_the_batch_stamp(self):
        """The dedup resolves a game to the latest BATCH — two rows of one batch carrying
        different stamps would split it."""
        rows, _ = store.normalise_rows(_rows([1, 2]), _DATE, loaded_at="stamp",
                                       scoped_game_pks=[1, 2])
        assert {r["loaded_at"] for r in rows} == {"stamp"}


class TestWithinBatchDuplicates:
    """The second dedup, and why the first one is not enough.

    The winner-join resolves ACROSS batches. It structurally CANNOT see a key duplicated
    WITHIN one, because every copy carries the same `loaded_at` and the same `filename` and
    therefore all of them match the winner. Measured on the real migration: Snowflake held
    4 keys duplicated 4x (2026-07-11), they landed in one part file, and 12 excess rows
    survived a view that was believed to collapse them — which would have counted those
    keys 4x in compute_model_health's sample.
    """

    def _dupe_rows(self, model_prob=0.5):
        row = {"game_pk": 1, "market": "h2h", "model_prob": model_prob,
               "market_prob_at_prediction": 0.5, "kelly_fraction": 0.0, "model_version": "v6"}
        return [dict(row), dict(row), dict(row), dict(row)]

    def test_a_key_duplicated_within_one_batch_is_returned_once(self, s3):
        store.write_rows(self._dupe_rows(), _DATE,
                         loaded_at="2026-08-16 10:00:00.000000", s3=s3)
        assert s3.rows_on(_DATE) == [(1, "h2h", 0.5)]

    def test_the_duplicates_really_were_written(self):
        """Non-vacuity: if the writer silently dropped them, the clause above would pass on
        nothing and the view would be untested."""
        rows, _ = store.normalise_rows(self._dupe_rows(), _DATE, loaded_at="s")
        assert len(rows) == 4

    def test_the_survivor_is_deterministic_when_the_copies_differ(self, s3):
        """Duplicates are not guaranteed identical, so the tiebreak orders by the value
        columns rather than leaving an arbitrary winner."""
        rows = self._dupe_rows(model_prob=0.9)[:1] + self._dupe_rows(model_prob=0.1)[:1]
        store.write_rows(rows, _DATE, loaded_at="2026-08-16 10:00:00.000000", s3=s3)
        first = s3.rows_on(_DATE)
        store.write_rows(list(reversed(rows)), _DATE,
                         loaded_at="2026-08-16 11:00:00.000000", s3=s3)
        assert s3.rows_on(_DATE) == first == [(1, "h2h", 0.1)]

    def test_a_later_batch_still_wins_over_a_duplicated_earlier_one(self, s3):
        """The two dedups must COMPOSE — the per-key uniqueness must not shadow the
        across-batch ordering."""
        store.write_rows(self._dupe_rows(model_prob=0.5), _DATE,
                         loaded_at="2026-08-16 10:00:00.000000", s3=s3)
        store.write_rows([{"game_pk": 1, "market": "h2h", "model_prob": 0.9}], _DATE,
                         scoped_game_pks=[1], loaded_at="2026-08-16 12:00:00.000000", s3=s3)
        assert s3.rows_on(_DATE) == [(1, "h2h", 0.9)]


class TestLoadedAtCoercion:
    """The defect that killed the first real migration run.

    `loaded_at` is stored as a fixed-width ISO VARCHAR and the dedup ORDERS BY it, so every
    value must be a str AND the same width. A database driver hands back a `datetime` —
    which is the normal thing for a caller to have — and pyarrow then raised
    `Expected bytes, got a 'datetime.datetime' object` while building the FIRST partition.

    Nothing caught it because every test passed a string and `--dry-run` returned before the
    write loop, so no test and no rehearsal ever ran the conversion.
    """

    def test_a_datetime_loaded_at_is_coerced_to_the_canonical_string(self):
        from datetime import datetime
        rows, _ = store.normalise_rows(
            [{"game_pk": 1, "market": "h2h",
              "loaded_at": datetime(2026, 8, 16, 17, 57, 7, 672000)}],
            _DATE, loaded_at="fallback")
        assert rows[0]["loaded_at"] == "2026-08-16 17:57:07.672000"

    def test_a_coerced_datetime_is_the_same_width_as_a_native_stamp(self):
        """Same width or it mis-sorts against the stamps around it — and mis-sorting IS the
        dedup picking the wrong batch."""
        from datetime import datetime, timezone
        coerced = store.canonical_stamp(datetime(2026, 8, 16, 0, 0, 0, 0))
        native = store.utc_stamp(datetime(2026, 8, 16, 0, 0, 0, 1, tzinfo=timezone.utc))
        assert len(coerced) == len(native)
        assert coerced < native

    def test_an_absent_loaded_at_falls_back_to_the_batch_stamp(self):
        rows, _ = store.normalise_rows([{"game_pk": 1, "market": "h2h"}],
                                       _DATE, loaded_at="batch")
        assert rows[0]["loaded_at"] == "batch"

    def test_a_datetime_row_actually_serialises(self):
        """The end-to-end claim, not just the coercion: the exact row shape the Snowflake
        read produces must reach parquet."""
        from datetime import datetime
        rows, _ = store.normalise_rows(
            [{"game_pk": 1, "market": "h2h", "model_prob": 0.5,
              "loaded_at": datetime(2026, 8, 16, 10, 0, 0)}],
            _DATE, loaded_at="fallback")
        table = store.rows_to_arrow_table(rows)
        assert table.num_rows == 1

    def test_a_hand_built_row_with_a_datetime_fails_by_NAME(self):
        """A caller bypassing normalise_rows must get an error that names the column —
        pyarrow's own message names neither the column nor the row."""
        from datetime import datetime
        bad = [{c: None for c in store.COLUMNS}]
        bad[0]["loaded_at"] = datetime(2026, 8, 16, 10, 0, 0)
        with pytest.raises(TypeError, match="loaded_at"):
            store.rows_to_arrow_table(bad)


class TestStampOrdering:
    def test_the_stamp_is_fixed_width_so_string_order_is_time_order(self):
        """Lexicographic order of these strings IS the dedup's ordering. Python's
        `isoformat()` DROPS `.000000` when the microsecond is zero, which would make a
        midnight-exact stamp sort BEFORE a same-second one — hence strftime."""
        from datetime import datetime, timezone
        a = store.utc_stamp(datetime(2026, 8, 16, 10, 0, 0, 0, tzinfo=timezone.utc))
        b = store.utc_stamp(datetime(2026, 8, 16, 10, 0, 0, 1, tzinfo=timezone.utc))
        assert len(a) == len(b)
        assert a < b


class TestViewIsTheOnlyDefinition:
    def test_lakehouse_read_serves_the_stores_dedup_body(self):
        """A consumer reaching `prediction_log` through `register_views()` must get the
        DEDUP, not a raw glob — a raw glob counts every superseded batch."""
        from scripts.utils import lakehouse_read
        assert lakehouse_read._view_sql("prediction_log") == store.view_sql()

    def test_the_view_body_is_not_a_bare_glob(self):
        sql = store.view_sql()
        assert "row_number() OVER" in sql
        assert "market IS NOT NULL" in sql


class TestEmptyPrefix:
    def test_register_view_degrades_to_an_empty_typed_relation(self, tmp_path):
        """DuckDB binds a parquet view at CREATE time, so an absent prefix raises. A
        monitoring read must report 'no rows', never take the connection down."""
        conn = duckdb.connect()
        assert store.register_view(conn, loc=str(tmp_path / "nothing")) is False
        cols = [r[0] for r in conn.execute("DESCRIBE prediction_log").fetchall()]
        assert cols == list(store.COLUMNS)
        assert conn.execute("SELECT count(*) FROM prediction_log").fetchone()[0] == 0

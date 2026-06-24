"""E13.11 — regression tests for the --is-backfill RANGE batching (cost optimization).

A multi-date backfill must:
  1. Buffer every date's prediction rows (no per-date write) and flush them in ONE
     transaction: a single DELETE scoped to the buffered (score_date, model_version)
     set, chunked executemany, and a single commit.
  2. Serve each date's features from the pre-pulled range frame (one Snowflake read for
     the window) instead of one read per date.
  3. Clean up: clear the feature cache + buffer and delete the local parquet on exit.

The live single-date / per-date write path is unaffected (buffer is None there).
"""

import importlib.util
from datetime import date
from pathlib import Path
from unittest import mock

from betting_ml.utils import data_loader

# scripts/ is not a package — load predict_today.py by path (mirrors test_predict_today_write).
_SCORER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "predict_today.py"
_spec = importlib.util.spec_from_file_location("predict_today_script_bf", _SCORER_PATH)
predict_today = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(predict_today)


def _row(score_date: str, version: str, game_pk: int) -> dict:
    return {"score_date": date.fromisoformat(score_date), "model_version": version,
            "game_pk": game_pk, "sigma_tier": "core"}


class _FakeCursor:
    def __init__(self):
        self.executed = []          # (sql, params)
        self.executemany_calls = []  # list of row-batches
        self.rowcount = 7

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, rows):
        self.executemany_calls.append(list(rows))

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class TestFlushBatchedWrite:
    def _flush_with(self, rows):
        cur = _FakeCursor()
        conn = _FakeConn(cur)
        predict_today._BACKFILL_BATCH = {"rows": list(rows)}
        with mock.patch.object(predict_today, "get_snowflake_connection", return_value=conn), \
             mock.patch.object(predict_today, "_migrate_prediction_columns"):
            try:
                predict_today._flush_backfill_predictions()
            finally:
                predict_today._BACKFILL_BATCH = None
        return cur, conn

    def test_single_commit_for_whole_range(self):
        rows = [_row("2026-04-01", "v6", 1), _row("2026-04-02", "v6", 2),
                _row("2026-04-03", "v6", 3)]
        cur, conn = self._flush_with(rows)
        assert conn.commits == 1, "the whole backfill must commit exactly once"
        assert conn.closed

    def test_delete_scoped_to_buffered_dates_and_versions(self):
        rows = [_row("2026-04-01", "v6", 1), _row("2026-04-02", "v6", 2)]
        cur, _ = self._flush_with(rows)
        deletes = [(s, p) for s, p in cur.executed if s.strip().upper().startswith("DELETE")]
        assert len(deletes) == 1, "exactly one range-scoped DELETE"
        sql, params = deletes[0]
        assert "is_backfill = TRUE" in sql
        assert "score_date IN" in sql and "model_version IN" in sql
        # params carry the buffered dates THEN versions, nothing wider.
        assert params == [date(2026, 4, 1), date(2026, 4, 2), "v6"]

    def test_all_rows_inserted_and_chunked(self):
        rows = [_row("2026-04-01", "v6", i) for i in range(1100)]
        cur, _ = self._flush_with(rows)
        inserted = sum(len(b) for b in cur.executemany_calls)
        assert inserted == 1100, "every buffered row is written"
        # 1100 rows / chunk 500 → 3 chunks, all under one connection+commit.
        assert len(cur.executemany_calls) == 3
        assert all(len(b) <= 500 for b in cur.executemany_calls)

    def test_empty_buffer_is_noop(self):
        cur, conn = self._flush_with([])
        assert conn.commits == 0
        assert not cur.executemany_calls

    def test_none_batch_is_noop(self):
        predict_today._BACKFILL_BATCH = None
        # Must not raise / not touch Snowflake.
        predict_today._flush_backfill_predictions()


class TestDeactivateCleansUp:
    def test_clears_cache_buffer_and_removes_parquet(self, tmp_path):
        pq = tmp_path / "feats.parquet"
        pq.write_text("x")
        data_loader.set_range_feature_cache(__import__("pandas").DataFrame({"a": [1]}))
        predict_today._BACKFILL_BATCH = {"rows": [1]}
        predict_today._deactivate_backfill_batch(str(pq))
        assert predict_today._BACKFILL_BATCH is None
        assert data_loader._RANGE_FEATURE_CACHE is None
        assert not pq.exists()

    def test_missing_parquet_is_tolerated(self):
        # finally-safe even if activation half-failed (no file).
        predict_today._deactivate_backfill_batch("/nonexistent/path.parquet")
        assert predict_today._BACKFILL_BATCH is None


class TestFeatureCacheSlicing:
    def test_cache_slice_served_without_snowflake(self):
        import pandas as pd
        # Two dates in the cache; requesting one returns only its rows, and must NOT
        # open a Snowflake connection (the whole point of the cache).
        frame = pd.DataFrame({
            "game_date": [date(2026, 4, 1), date(2026, 4, 1), date(2026, 4, 2)],
            "game_pk": [1, 2, 3],
        })
        data_loader.set_range_feature_cache(frame)
        try:
            with mock.patch.object(data_loader, "_connect",
                                   side_effect=AssertionError("must not hit Snowflake")), \
                 mock.patch.object(data_loader, "_feature_store_mean_coverage", return_value=1.0), \
                 mock.patch.object(data_loader, "_numeric_convert", side_effect=lambda d: d):
                out = data_loader.load_todays_features("2026-04-01")
            assert list(out["game_pk"]) == [1, 2]
            assert (out["data_source"] == "feature_store").all()
        finally:
            data_loader.set_range_feature_cache(None)

    def test_below_coverage_falls_through_to_live(self):
        import pandas as pd
        frame = pd.DataFrame({"game_date": [date(2026, 4, 1)], "game_pk": [1]})
        data_loader.set_range_feature_cache(frame)
        try:
            # Coverage below gate → must fall through to the live path (here: raises in
            # _connect, proving it did NOT serve from cache).
            with mock.patch.object(data_loader, "_feature_store_mean_coverage", return_value=0.0), \
                 mock.patch.object(data_loader, "_connect",
                                   side_effect=RuntimeError("fell through to live")):
                try:
                    data_loader.load_todays_features("2026-04-01")
                    raised = False
                except RuntimeError as exc:
                    raised = "fell through to live" in str(exc)
            assert raised, "below-coverage cached slice must fall through to live load"
        finally:
            data_loader.set_range_feature_cache(None)

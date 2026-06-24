"""Unit tests for scripts/savant_ingestion.py — column normalization, batch write, helpers."""

import unittest.mock as mock
from datetime import date

import pandas as pd
import pytest

import savant_ingestion as si


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn(deleted_rows: int = 0):
    """Return a minimal Snowflake connection mock."""
    cur = mock.MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = mock.MagicMock(return_value=False)
    cur.rowcount = deleted_rows

    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def _make_endpoint():
    return si.BATTER_PITCHES


# ---------------------------------------------------------------------------
# Tests for _normalize_df (extracted column-drop logic)
# ---------------------------------------------------------------------------

class TestNormalizeDf:
    """_normalize_df must uppercase columns, emit loud warning, and drop extras."""

    def test_extra_column_triggers_stderr_print(self, capsys):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "miss_distance": ["1.5"]})
        si._normalize_df(df, {"GAME_DATE"})
        assert "ACTION NEEDED" in capsys.readouterr().err

    def test_extra_column_name_appears_in_stderr(self, capsys):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "new_field": ["x"]})
        si._normalize_df(df, {"GAME_DATE"})
        assert "NEW_FIELD" in capsys.readouterr().err

    def test_extra_column_is_dropped(self):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "extra": ["z"]})
        result = si._normalize_df(df, {"GAME_DATE"})
        assert "EXTRA" not in result.columns
        assert "GAME_DATE" in result.columns

    def test_columns_are_uppercased(self):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "release_speed": ["94.5"]})
        result = si._normalize_df(df, {"GAME_DATE", "RELEASE_SPEED"})
        assert list(result.columns) == ["GAME_DATE", "RELEASE_SPEED"]

    def test_no_extra_columns_no_stderr(self, capsys):
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"]})
        si._normalize_df(df, {"GAME_DATE"})
        assert "ACTION NEEDED" not in capsys.readouterr().err

    def test_multiple_extra_columns_all_in_stderr(self, capsys):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "field_a": ["1"], "field_b": ["2"]})
        si._normalize_df(df, {"GAME_DATE"})
        captured = capsys.readouterr().err
        assert "FIELD_A" in captured
        assert "FIELD_B" in captured

    def test_does_not_mutate_input(self):
        df = pd.DataFrame({"game_date": ["2026-06-20"], "extra": ["z"]})
        original_cols = list(df.columns)
        si._normalize_df(df, {"GAME_DATE"})
        assert list(df.columns) == original_cols


# ---------------------------------------------------------------------------
# Tests for load_day (delegates to _normalize_df; tests end-to-end behavior)
# ---------------------------------------------------------------------------

class TestLoadDayColumnDrop:
    """load_day must propagate the loud-warning path through _normalize_df."""

    def _call_load_day(self, df, table_columns, conn):
        with mock.patch("savant_ingestion.write_pandas", return_value=(True, None, len(df), None)):
            return si.load_day(conn, _make_endpoint(), date(2026, 6, 20), df, table_columns)

    def test_extra_column_triggers_stderr_print(self, capsys):
        conn, _ = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"], "MISS_DISTANCE": ["1.5"]})
        self._call_load_day(df, {"GAME_DATE"}, conn)
        assert "ACTION NEEDED" in capsys.readouterr().err

    def test_extra_column_is_dropped_before_write(self):
        conn, _ = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"], "EXTRA_COL": ["z"]})
        written_df = None

        def capture_write(c, frame, **kwargs):
            nonlocal written_df
            written_df = frame
            return (True, None, 1, None)

        with mock.patch("savant_ingestion.write_pandas", side_effect=capture_write):
            si.load_day(conn, _make_endpoint(), date(2026, 6, 20), df, {"GAME_DATE"})

        assert "EXTRA_COL" not in written_df.columns
        assert "GAME_DATE" in written_df.columns

    def test_no_extra_columns_no_stderr(self, capsys):
        conn, _ = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"]})
        with mock.patch("savant_ingestion.write_pandas", return_value=(True, None, 1, None)):
            si.load_day(conn, _make_endpoint(), date(2026, 6, 20), df, {"GAME_DATE"})
        assert "ACTION NEEDED" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Tests for batch_write
# ---------------------------------------------------------------------------

class TestBatchWrite:
    """batch_write must issue one IN-clause DELETE and one write_pandas call."""

    def test_single_delete_and_write(self):
        conn, cur = _make_conn(deleted_rows=100)
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20", "2026-06-21"], "VAL": ["a", "b"]})
        dates = [date(2026, 6, 20), date(2026, 6, 21)]

        with mock.patch("savant_ingestion.write_pandas", return_value=(True, None, 2, None)) as wp:
            result = si.batch_write(conn, _make_endpoint(), dates, df)

        assert result == 2
        wp.assert_called_once()
        execute_call = cur.execute.call_args[0][0]
        assert "IN" in execute_call.upper()

    def test_returns_row_count(self):
        conn, _ = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"]})
        with mock.patch("savant_ingestion.write_pandas", return_value=(True, None, 42, None)):
            result = si.batch_write(conn, _make_endpoint(), [date(2026, 6, 20)], df)
        assert result == 42

    def test_raises_on_write_failure(self):
        conn, _ = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"]})
        with mock.patch("savant_ingestion.write_pandas", return_value=(False, None, 0, None)):
            with pytest.raises(RuntimeError, match="write_pandas failed"):
                si.batch_write(conn, _make_endpoint(), [date(2026, 6, 20)], df)

    def test_delete_uses_correct_number_of_placeholders(self):
        conn, cur = _make_conn()
        df = pd.DataFrame({"GAME_DATE": ["2026-06-20"] * 3})
        dates = [date(2026, 6, 20), date(2026, 6, 21), date(2026, 6, 22)]

        with mock.patch("savant_ingestion.write_pandas", return_value=(True, None, 3, None)):
            si.batch_write(conn, _make_endpoint(), dates, df)

        execute_sql = cur.execute.call_args[0][0]
        execute_params = cur.execute.call_args[0][1]
        assert execute_sql.count("%s") == 3
        assert len(execute_params) == 3


# ---------------------------------------------------------------------------
# Tests for get_last_loaded_date
# ---------------------------------------------------------------------------

class TestGetLastLoadedDate:
    def test_returns_date_when_table_has_rows(self):
        conn = mock.MagicMock()
        cur = mock.MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = mock.MagicMock(return_value=False)
        cur.fetchone.return_value = (date(2026, 6, 23),)
        conn.cursor.return_value = cur

        result = si.get_last_loaded_date(conn, _make_endpoint())
        assert result == date(2026, 6, 23)

    def test_returns_none_when_table_is_empty(self):
        conn = mock.MagicMock()
        cur = mock.MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = mock.MagicMock(return_value=False)
        cur.fetchone.return_value = (None,)
        conn.cursor.return_value = cur

        result = si.get_last_loaded_date(conn, _make_endpoint())
        assert result is None


# ---------------------------------------------------------------------------
# Tests for date_range
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_single_day(self):
        days = list(si.date_range(date(2026, 6, 20), date(2026, 6, 20)))
        assert days == [date(2026, 6, 20)]

    def test_multi_day(self):
        days = list(si.date_range(date(2026, 6, 20), date(2026, 6, 22)))
        assert days == [date(2026, 6, 20), date(2026, 6, 21), date(2026, 6, 22)]

    def test_start_after_end_yields_nothing(self):
        days = list(si.date_range(date(2026, 6, 22), date(2026, 6, 20)))
        assert days == []

"""E11.1-W7b — unit tests for the shared prediction/serving DuckDB-over-S3 read helper.

Offline (no S3/Snowflake): verifies the contract every W7b reader depends on —
FQN-strip, %(name)s→$name paramstyle, grep-driven table discovery, the universal
`**/*.parquet` glob (flat + partitioned), and the UPPERCASE-keyed fetch that matches
the Snowflake DictCursor contract.
"""
import os
import tempfile

import duckdb
import pytest

from utils import lakehouse_read as lr


def test_strip_fqn_all_schemas():
    sql = ("SELECT * FROM baseball_data.betting.mart_a a "
           "JOIN baseball_data.betting_features.feature_b f USING(game_pk) "
           "JOIN baseball_data.betting_ml.daily_model_predictions p USING(game_pk) "
           "JOIN baseball_data.statsapi.stg_c c USING(game_pk)")
    out = lr.strip_fqn(sql)
    assert "baseball_data." not in out
    for t in ("mart_a", "feature_b", "daily_model_predictions", "stg_c"):
        assert f" {t}" in out or out.endswith(t)


def test_param_translation():
    assert lr.to_duckdb_param_sql("WHERE d = %(today)s AND m = %(mkt)s") == \
        "WHERE d = $today AND m = $mkt"


def test_referenced_tables_grep_driven():
    sql = ("SELECT * FROM baseball_data.betting.mart_odds_outcomes o "
           "JOIN betting_features.feature_pregame_game_features f USING(game_pk)")
    assert lr.referenced_tables(sql) == ["mart_odds_outcomes", "feature_pregame_game_features"]


def test_register_and_query_upper_roundtrip(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setattr(lr, "LAKEHOUSE", t)
        os.makedirs(f"{t}/mart_clv_labeled_games")
        duckdb.connect().execute(
            f"COPY (SELECT 101 AS game_pk, 'h2h' AS market, 0.5 AS model_prob) "
            f"TO '{t}/mart_clv_labeled_games/data.parquet' (FORMAT PARQUET)")
        conn = duckdb.connect()
        sql = ("SELECT game_pk, model_prob FROM baseball_data.betting.mart_clv_labeled_games "
               "WHERE market = %(mkt)s")
        lr.register_views(conn, lr.referenced_tables(sql))
        rows = lr.query_upper(conn, sql, {"mkt": "h2h"})
        assert rows == [{"GAME_PK": 101, "MODEL_PROB": 0.5}]


def test_partitioned_glob_unions_history_and_current(monkeypatch):
    """mart_odds_outcomes _history/_current both picked up by one universal glob, no dupes."""
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setattr(lr, "LAKEHOUSE", t)
        for bucket, gp in (("_history", 1), ("_current", 2)):
            os.makedirs(f"{t}/mart_odds_outcomes/{bucket}")
            duckdb.connect().execute(
                f"COPY (SELECT {gp} AS game_pk) "
                f"TO '{t}/mart_odds_outcomes/{bucket}/data.parquet' (FORMAT PARQUET)")
        conn = duckdb.connect()
        lr.register_views(conn, ["mart_odds_outcomes"])
        assert conn.execute("SELECT count(*) FROM mart_odds_outcomes").fetchone()[0] == 2


def test_query_upper_batch(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setattr(lr, "LAKEHOUSE", t)
        os.makedirs(f"{t}/mart_x")
        duckdb.connect().execute(
            f"COPY (SELECT * FROM (VALUES (1),(2),(3)) v(game_pk)) "
            f"TO '{t}/mart_x/data.parquet' (FORMAT PARQUET)")
        conn = duckdb.connect()
        lr.register_views(conn, ["mart_x"])
        out = lr.query_upper_batch(
            conn, "SELECT game_pk FROM mart_x WHERE game_pk IN ({game_pk_list})", [1, 3])
        assert sorted(r["GAME_PK"] for r in out) == [1, 3]

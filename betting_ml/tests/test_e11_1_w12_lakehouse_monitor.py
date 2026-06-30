"""E11.1-W12 — fast-gate guards for the monitoring-sensor lakehouse migration.

Two halves, both network-free and fast (no dagster / pipeline / duckdb import):

  1. Unit tests for the betting_ml.utils.lakehouse_monitor read helper — pure string ops
     (path builders, the narrow SF→DuckDB SQL translation, FQN strip, table routing,
     missing-glob detection). These pin the contract the sensors + the model_health adapter
     rely on.

  2. AST/text migration guards over every migrated sensor file + the check_games_today op:
     the Snowflake read paths are GONE (no get_snowflake_connection / snowflake.connector /
     open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]) in CODE — docstrings may still mention them),
     the lakehouse_monitor helper is imported, and the E11.7 failure tier markers
     (raise Exception for the alert sensors, SkipReason for the fail-open ones) are preserved.

The genuine fire-tests (drive each sensor generator on a forced bad condition and assert it
raises / RunRequests) live in test_e11_1_w12_sensor_fire.py, which imports dagster + pipeline
and is therefore marked `slow`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from betting_ml.utils import lakehouse_monitor as lm

_REPO = Path(__file__).resolve().parents[2]

# Every sensor migrated by W12 (run_failure_alert_sensor reads no warehouse → not migrated).
_MIGRATED_SENSORS = [
    "odds_current_rebuild_sensor",
    "statcast_freshness_sensor",
    "schedule_freshness_alert_sensor",
    "clv_alert_sensor",
    "model_health_alert_sensor",
    "lineup_monitor_sensor",
    "morning_watchdog_sensor",
    "pregame_alert_sensor",
    "conviction_pick_alert_sensor",
    "odds_freshness_alert_sensor",
]
# Sensors whose E11.7 tier is ALERT/HALT (must RAISE on a real bad condition).
_ALERT_SENSORS = [
    "odds_freshness_alert_sensor",
    "schedule_freshness_alert_sensor",
    "clv_alert_sensor",
    "model_health_alert_sensor",
    "pregame_alert_sensor",
    "conviction_pick_alert_sensor",
    "statcast_freshness_sensor",
]


def _sensor_path(name: str) -> Path:
    return _REPO / "pipeline" / "sensors" / f"{name}.py"


def _read(p: Path) -> str:
    return p.read_text()


# ──────────────────────────────────────────────────────────────────────────────
# 1. lakehouse_monitor helper — pure-function contract
# ──────────────────────────────────────────────────────────────────────────────

class TestLakehouseMonitorPaths:
    def test_lh_points_at_lakehouse(self):
        assert lm.lh("stg_statsapi_games") == \
            "s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_statsapi_games/**/*.parquet"

    def test_lh_raw_points_at_lakehouse_raw(self):
        assert lm.lh_raw("mlb_odds_raw") == \
            "s3://baseball-betting-ml-artifacts/baseball/lakehouse_raw/mlb_odds_raw/**/*.parquet"

    def test_lh_year_scopes_to_partition(self):
        got = lm.lh_year("stg_batter_pitches", 2026)
        assert got.endswith("stg_batter_pitches/year=2026/**/*.parquet")

    def test_table_glob_routes_raw_tables_to_lakehouse_raw(self):
        # raw-ingestion exports live under lakehouse_raw/
        assert "/lakehouse_raw/" in lm.table_glob("mlb_odds_raw")
        assert "/lakehouse_raw/" in lm.table_glob("monthly_schedule")

    def test_table_glob_routes_marts_to_lakehouse(self):
        assert "/lakehouse/" in lm.table_glob("stg_statsapi_games")
        assert "/lakehouse_raw/" not in lm.table_glob("stg_statsapi_games")

    def test_region_is_us_east_2(self):
        # The lakehouse bucket is us-east-2; DuckDB needs it explicitly (boto3 is region-less).
        assert lm.S3_REGION == "us-east-2"


class TestLakehouseMonitorSqlTranslation:
    """The narrow SF→DuckDB translation used by the model_health adapter."""

    def test_iff_to_if(self):
        assert lm.translate_sql("select iff(a=1, 'x', 'y')") == "select if(a=1, 'x', 'y')"

    def test_iff_case_insensitive(self):
        assert "if(" in lm.translate_sql("select IFF(a, b, c)").lower()
        assert "iff(" not in lm.translate_sql("select IFF(a, b, c)").lower()

    def test_named_paramstyle_translated(self):
        assert lm.translate_sql("where d = %(start)s and t = %(pt)s") == "where d = $start and t = $pt"

    def test_strip_fqn_resolves_to_bare_view(self):
        assert lm.strip_fqn("baseball_data.betting_ml.daily_model_predictions") == \
            "daily_model_predictions"
        assert lm.strip_fqn("baseball_data.betting.mart_game_results") == "mart_game_results"

    def test_referenced_tables_grep(self):
        sql = ("from baseball_data.betting_ml.daily_model_predictions p "
               "join baseball_data.betting.mart_game_results r on r.game_pk = p.game_pk")
        assert lm.referenced_tables(sql) == ["daily_model_predictions", "mart_game_results"]

    def test_referenced_tables_dedup_preserves_order(self):
        sql = "from baseball_data.betting.x, baseball_data.betting.y, baseball_data.betting.x"
        assert lm.referenced_tables(sql) == ["x", "y"]


class TestMissingGlobDetection:
    def test_missing_glob_true(self):
        exc = Exception('IO Error: No files found that match the pattern "s3://.../year=2027/**"')
        assert lm.is_missing_glob(exc) is True

    def test_missing_glob_false_for_other_errors(self):
        assert lm.is_missing_glob(Exception("HTTP 503 from S3")) is False
        assert lm.is_missing_glob(Exception("Binder Error: column not found")) is False


class TestNoSnowflakeImportInHelper:
    """The helper must be Snowflake-free + must not import scripts/ (in-process sensor rule)."""

    def test_helper_does_not_import_snowflake_or_scripts(self):
        src = (_REPO / "betting_ml" / "utils" / "lakehouse_monitor.py").read_text()
        tree = ast.parse(src)
        mods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
        assert not any(m.startswith("snowflake") for m in mods), \
            "lakehouse_monitor must not import snowflake.connector (it is the Snowflake-free reader)"
        assert not any(m.startswith("scripts") for m in mods), \
            "in-process sensor helper must not import scripts/ (feedback_dagster_import_only_packaged_code)"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Migration guards over the sensor files
# ──────────────────────────────────────────────────────────────────────────────

def _import_module_names(tree: ast.Module) -> list[str]:
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
    return mods


def _imported_symbols(tree: ast.Module) -> set[str]:
    syms: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            syms.update(a.name for a in node.names)
    return syms


def _subscripts_env_key(tree: ast.Module, key: str) -> bool:
    """True if the AST contains os.environ["<key>"] (a Subscript with that constant) — the
    INC-21 footgun. AST-based so docstrings mentioning the string don't false-positive."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value == key:
                return True
    return False


@pytest.mark.parametrize("name", _MIGRATED_SENSORS)
def test_sensor_has_no_snowflake_read_in_code(name):
    """No migrated sensor may import snowflake.connector or get_snowflake_connection (AST —
    docstrings/comments referencing them are fine)."""
    tree = ast.parse(_read(_sensor_path(name)))
    mods = _import_module_names(tree)
    assert not any(m.startswith("snowflake") for m in mods), \
        f"{name} still imports snowflake.connector — migrate the read to the S3 lakehouse"
    assert "get_snowflake_connection" not in _imported_symbols(tree), \
        f"{name} still imports get_snowflake_connection — use betting_ml.utils.lakehouse_monitor"
    assert "betting_ml.utils.data_loader" not in mods, \
        f"{name} still imports betting_ml.utils.data_loader (the Snowflake reader)"


@pytest.mark.parametrize("name", _MIGRATED_SENSORS)
def test_sensor_imports_lakehouse_monitor(name):
    """Each migrated sensor must read through betting_ml.utils.lakehouse_monitor."""
    mods = _import_module_names(ast.parse(_read(_sensor_path(name))))
    assert "betting_ml.utils.lakehouse_monitor" in mods, \
        f"{name} does not import betting_ml.utils.lakehouse_monitor — it is not migrated to S3"


def test_inc21_footgun_removed_from_odds_current_rebuild():
    """odds_current_rebuild_sensor must no longer do open(os.environ['SNOWFLAKE_PRIVATE_KEY_PATH'])
    in code — the literal INC-21 silent-no-fire footgun."""
    tree = ast.parse(_read(_sensor_path("odds_current_rebuild_sensor")))
    assert not _subscripts_env_key(tree, "SNOWFLAKE_PRIVATE_KEY_PATH"), \
        "odds_current_rebuild_sensor still subscripts os.environ['SNOWFLAKE_PRIVATE_KEY_PATH'] (INC-21)"


def test_inc21_footgun_removed_from_check_games_today_op():
    """The check_games_today op shared the same KeyError footgun; it must be gone in code."""
    tree = ast.parse((_REPO / "pipeline" / "ops" / "intraday_ops.py").read_text())
    assert not _subscripts_env_key(tree, "SNOWFLAKE_PRIVATE_KEY_PATH"), \
        "intraday_ops still subscripts os.environ['SNOWFLAKE_PRIVATE_KEY_PATH'] (INC-21 class)"


@pytest.mark.parametrize("name", _ALERT_SENSORS)
def test_alert_tier_preserved(name):
    """E11.7 tier: the alert/HALT sensors must still RAISE on a real bad condition (the raise
    IS the page). A migration that quietly stopped raising would silence the monitor."""
    src = _read(_sensor_path(name))
    assert "raise Exception" in src, \
        f"{name} no longer contains 'raise Exception' — its alert/HALT tier was lost in migration"


@pytest.mark.parametrize("name", _MIGRATED_SENSORS)
def test_transient_failopen_preserved(name):
    """Every migrated sensor keeps a SkipReason path (transient lakehouse error → skip, not page)."""
    assert "SkipReason" in _read(_sensor_path(name)), \
        f"{name} lost its SkipReason fail-open path"

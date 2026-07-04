"""E11.1-W11-FG (the 2 FanGraphs ZiPS-pitching residual models → S3) — unit tests for the flip.

Offline (no S3/Snowflake). Verifies:
  • the ZiPS-pitching writer imports cleanly, targets the shared _LAKEHOUSE_SOURCE, and uses the
    W11 dual-write dispatcher (append_raw_rows_lakehouse + w11_write_mode);
  • the 2 dbt models render a clean DuckDB branch (no unresolved Jinja, no lakehouse_ext leak) and
    read the right sources (stg ← fg_zips_pitching_raw parquet; fct ← the two stg views);
  • the build / refresh / generator model lists agree AND both models sit AFTER their DuckDB deps;
  • fct was DROPPED from the W8b export mirror (its uppercase SELECT * would break the lowercase ext
    table) yet stays a W8b precursor VIEW (W8b reads the now-W4-built parquet).
"""
import importlib

_STG = "stg_fangraphs__zips_pitching"
_FCT = "fct_fangraphs_pitching_analytics"
_SOURCE = "fg_zips_pitching_raw"


def test_zips_pitching_writer_uses_shared_dispatcher():
    mod = importlib.import_module("ingest_fangraphs_zips_pitching")
    assert getattr(mod, "_LAKEHOUSE_SOURCE") == _SOURCE
    assert hasattr(mod, "append_raw_rows_lakehouse") and hasattr(mod, "w11_write_mode")


def test_default_write_mode_is_snowflake_only(monkeypatch):
    """The flip is NON-BREAKING by default: no W11_RAW_WRITE_MODE / LAKEHOUSE_RAW_WRITE_MODE set → 'snowflake'."""
    lrw = importlib.import_module("utils.lakehouse_raw_writer")
    monkeypatch.delenv("W11_RAW_WRITE_MODE", raising=False)
    monkeypatch.delenv("LAKEHOUSE_RAW_WRITE_MODE", raising=False)
    assert lrw.w11_write_mode() == "snowflake"


def test_models_render_clean_duckdb_branch():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    for m in (_STG, _FCT):
        sql = run_w1.extract_duckdb_sql(m)
        assert "{{" not in sql and "{%" not in sql, f"{m}: unresolved Jinja"
        assert "lakehouse_ext" not in sql.lower(), f"{m}: else-branch ext ref leaked into DuckDB SQL"
    stg_sql = run_w1.extract_duckdb_sql(_STG)
    assert "read_parquet" in stg_sql and _SOURCE in stg_sql, "stg must read the fg_zips_pitching_raw parquet"
    # The DuckDB fct joins the two registered stg VIEWS by bare name (no ext ref, no {{ ref() }}).
    fct_sql = run_w1.extract_duckdb_sql(_FCT).lower()
    assert "stg_fangraphs__stuff_plus" in fct_sql and "stg_fangraphs__zips_pitching" in fct_sql
    assert "projection_type = 'zips'" in fct_sql, "fct must keep the pre-season 'zips' filter (parity)"


def test_build_refresh_generator_lists_agree():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    refresh = importlib.import_module("refresh_w1_external_tables")
    gen = importlib.import_module("ddl.generate_w4_external_tables")
    for name in (_STG, _FCT):
        assert name in run_w1.W4_PRECURSOR_MODELS, f"{name} missing from W4_PRECURSOR_MODELS"
        assert name in refresh.W4_TABLES, f"{name} missing from W4_TABLES"
        assert name in gen.W4_MODELS, f"{name} missing from generate_w4 W4_MODELS"


def test_fct_built_after_its_duckdb_deps():
    """The DuckDB fct reads the stg VIEWS by bare name → both stg deps must be registered first."""
    run_w1 = importlib.import_module("run_w1_lakehouse")
    order = run_w1.W4_BUILD_MODELS
    assert order.index(_FCT) > order.index(_STG)
    assert order.index(_FCT) > order.index("stg_fangraphs__stuff_plus")


def test_ingestion_ts_ts_string_override_present():
    """ingestion_ts is ISO VARCHAR in parquet → the ext-table generator must force TIMESTAMP_NTZ via a
    string parse (else a full regen silently flips it to VARCHAR)."""
    gen = importlib.import_module("ddl.generate_w4_external_tables")
    assert "ingestion_ts" in gen.TS_STRING_COLS.get(_STG, set())


def test_fct_dropped_from_w8b_export_mirror():
    """E11.1-W11-FG: fct is now W4-built, so it must NOT be re-exported by the W8b mirror (its uppercase
    SELECT * columns would overwrite the W4 lowercase parquet and NULL the ext table)."""
    exp = importlib.import_module("export_w8b_precursors_to_s3")
    assert _FCT not in exp.MIRROR_TABLES, "fct must be dropped from the W8b export mirror"


def test_fct_still_a_w8b_precursor_view():
    """W8b still READS fct (feature_pregame_starter_features → ZiPS proj_fip); it registers the now-W4-built
    parquet at the same lakehouse location."""
    run_w1 = importlib.import_module("run_w1_lakehouse")
    assert _FCT in run_w1.W8B_PRECURSOR_VIEWS

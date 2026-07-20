"""E11.20 phase 1.5 — the post-drop reader-routing guard (2026-07-20 P0 outage).

Phase 1.5 dropped the SF `mart_pitch_*` objects and DELETED the legacy/compat parquet at
`lakehouse/<w1 table>/`. Under `LAKEHOUSE_DELTA_W1=cutover` those 7 marts live ONLY in
Delta (`lakehouse_delta/<table>/`). Every DuckDB consumer that still registered a bare
`read_parquet('<lakehouse>/<table>/**/*.parquet')` view therefore raised
"IO Error: No files found that match the pattern" — `generate_matchup_signals_op` died,
the daily job stopped before `predict_today`, and a full slate served ZERO predictions.
(`update_player_posteriors`, another DAILY op, imports the same helper and was next.)

The cure is central: `betting_ml/utils/delta_lakehouse.register_lakehouse_views` /
`lakehouse_view_sql` route per table — delta_scan for a cut-over W1 mart, the parquet glob
otherwise. This guard keeps every consumer on that path: a NEW hardcoded W1 glob fails
here instead of taking the daily job down again.
"""
from pathlib import Path

import pytest

from betting_ml.utils.delta_lakehouse import (
    DELTA_W1_TABLES,
    delta_scan_view_sql,
    lakehouse_view_sql,
)

_ROOT = Path(__file__).resolve().parents[2]

# Every module that registers lakehouse tables as bare-name DuckDB views for a
# Snowflake-name rewrite. Extend when a new consumer joins the pattern.
_READER_MODULES = [
    "betting_ml/scripts/eb_priors/generate_matchup_signals.py",
    "betting_ml/scripts/eb_priors/build_matchup_training_data.py",
    "betting_ml/scripts/eb_priors/fit_archetype_priors.py",
    "betting_ml/scripts/eb_priors/_lakehouse_duck.py",
]


@pytest.mark.parametrize("rel", _READER_MODULES)
def test_reader_registers_via_shared_delta_aware_helper(rel):
    src = (_ROOT / rel).read_text()
    assert "register_lakehouse_views" in src, (
        f"{rel} must register views via register_lakehouse_views (Delta-aware). A raw "
        f"read_parquet glob on a W1 mart resolves to NOTHING post-phase-1.5 and takes the "
        f"daily job down (2026-07-20 outage)."
    )


@pytest.mark.parametrize("rel", _READER_MODULES)
def test_reader_has_no_hardcoded_w1_parquet_glob(rel):
    """No consumer may name a W1 mart inside a lakehouse parquet-glob f-string."""
    src = (_ROOT / rel).read_text()
    for table in sorted(DELTA_W1_TABLES):
        for pattern in (f"lakehouse/{table}/", f"/{table}/**/*.parquet"):
            assert pattern not in src, (
                f"{rel} hardcodes a legacy parquet path for the Delta-backed W1 mart "
                f"{table} ({pattern!r}) — that key was deleted in phase 1.5; route "
                f"through lakehouse_view_sql/register_lakehouse_views instead."
            )


def test_view_sql_routes_w1_to_delta_under_cutover(monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_DELTA_W1", "cutover")
    for table in sorted(DELTA_W1_TABLES):
        assert lakehouse_view_sql(table) == delta_scan_view_sql(table)
        assert "lakehouse_delta" in lakehouse_view_sql(table)


def test_view_sql_routes_non_w1_to_parquet_under_cutover(monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_DELTA_W1", "cutover")
    sql = lakehouse_view_sql("mart_game_spine")
    assert "read_parquet(" in sql and "lakehouse_delta" not in sql


def test_view_sql_routes_w1_to_parquet_when_not_cutover(monkeypatch):
    """Rollback path: with the flag off/mirror the legacy parquet is authoritative again."""
    for mode in ("off", "mirror"):
        monkeypatch.setenv("LAKEHOUSE_DELTA_W1", mode)
        sql = lakehouse_view_sql("mart_pitch_play_event")
        assert "read_parquet(" in sql and "lakehouse_delta" not in sql, mode


def test_registry_homes_stay_byte_identical():
    """The two registry homes must not drift (sensors can't import scripts/; lean capture
    images can't import betting_ml) — the new helpers exist in BOTH."""
    a = (_ROOT / "betting_ml/utils/delta_lakehouse.py").read_text()
    b = (_ROOT / "scripts/utils/delta_lakehouse.py").read_text()
    assert a == b, "delta_lakehouse.py registry homes drifted"
    assert "def register_lakehouse_views" in a

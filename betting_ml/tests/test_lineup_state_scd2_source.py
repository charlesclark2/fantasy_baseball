"""test_lineup_state_scd2_source.py — the 2026-07-23 rewrite of backfill_lineup_state_scd2.py.

The writer used to flatten the native statsapi.monthly_schedule (retired 7/20 → frozen →
feature_pregame_lineup_state stuck at 7/20 → stale pre-lineup matchup features). It now reads the
fresh S3 lakehouse_ext.stg_statsapi_lineups with an idempotent compare-to-target SCD-2 upsert
(close prior is_current on a hash change; insert only when the current lineup isn't already current).

Pure source/structure inspection — fast gate, no IO (does not open a Snowflake connection).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_lineup_state_scd2.py"


def _load():
    spec = importlib.util.spec_from_file_location("backfill_lineup_state_scd2", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sources_fresh_ext_lineups_not_retired_native():
    mod = _load()
    for sql in (mod._CLOSE_SQL, mod._INSERT_SQL):
        assert "statsapi.monthly_schedule" not in sql          # the retired native source is gone
        assert "lakehouse_ext.stg_statsapi_lineups" in sql      # ...replaced by the fresh S3 feed


def test_templates_format_with_no_leftover_placeholders():
    mod = _load()
    close = mod._CLOSE_SQL.format(target="db.sch.tbl", since_filter="")
    ins = mod._INSERT_SQL.format(
        target="db.sch.tbl", since_filter="AND official_date >= '2026-07-21'::date")
    for rendered in (close, ins):
        assert "{" not in rendered and "}" not in rendered      # every placeholder filled


def test_upsert_is_idempotent_shaped():
    mod = _load()
    close = mod._CLOSE_SQL.format(target="t", since_filter="")
    ins = mod._INSERT_SQL.format(target="t", since_filter="")
    # CLOSE only touches a currently-current row whose lineup actually changed (hash differs).
    assert "is_current = TRUE" in close and "record_hash <> cs.record_hash" in close
    # INSERT opens a new current row ONLY when that exact lineup isn't already current → re-run no-op.
    assert "NOT EXISTS" in ins and "record_hash = cs.record_hash" in ins and "TRUE AS is_current" in ins


def test_hash_matches_the_historical_expression():
    # record_hash MUST be MD5 over the 9 player_ids in the SAME form as the historical rows, or the
    # upsert would treat every existing lineup as changed and churn the table.
    mod = _load()
    for i in range(1, 10):
        assert f"COALESCE(TO_VARCHAR(slot_{i}_player_id), '')" in mod._CURRENT_STATE
    assert "MD5(CONCAT_WS('|'," in mod._CURRENT_STATE


def test_all_nine_batting_slots_are_present():
    mod = _load()
    for i in range(1, 10):
        assert f"slot_{i}_player_id" in mod._INSERT_SQL
        assert f"slot_{i}_position" in mod._INSERT_SQL

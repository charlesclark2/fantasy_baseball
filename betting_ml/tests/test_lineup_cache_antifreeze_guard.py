"""test_lineup_cache_antifreeze_guard.py — INC-31 Defect B anti-freeze guard.

The bug: the game-detail serving cache froze FINAL games with lineups=null as PERMANENT
rows (never re-read). Root cause: the S3 stg_statsapi_lineups_wide parquet is re-exported
only in the daily (morning) run, so an evening Final game read via the --s3 path missed that
slate's lineups → lineups=None, and was written PERMANENT → served null forever (26 frozen
finals observed live).

The fix: NEVER write a PERMANENT game-detail blob while its lineups are null — gate permanence
on lineups being present, in BOTH writers (write_serving_store.py batch + picks.py API). A
null-lineup Final stays date-scoped and self-heals on the next cycle once the S3 parquet catches
up. These are source-inspection tests (fast-gate-safe: they do NOT import the FastAPI app or the
pipeline package, matching the other guard tests).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_WRITER = _REPO / "scripts" / "write_serving_store.py"
_PICKS = _REPO / "app" / "backend" / "routers" / "picks.py"
_PURGE = _REPO / "scripts" / "purge_frozen_null_lineup_cache.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_write_serving_store_gates_permanence_on_lineups():
    src = _src(_WRITER)
    # The DynamoDB permanent write must AND-in a lineups-present flag (not just is_final).
    assert "_lineups_ok" in src, "write_serving_store lost the _lineups_ok gate"
    assert "is_final and _has_expl and _lineups_ok" in src, \
        "DynamoDB permanent write must gate on lineups present (INC-31 anti-freeze)"
    # The S3 permanent write must also be gated on lineups (was only `is_final`).
    assert "if bucket and is_final and _lineups_ok:" in src, \
        "S3 api-cache/permanent write must gate on lineups present (INC-31 anti-freeze)"


def test_picks_api_gates_permanence_on_lineups():
    src = _src(_PICKS)
    assert "_lineups_ok" in src and "_permanent" in src, "picks.py lost the anti-freeze gate"
    # Both the DynamoDB (serving_cache.set_cache) and S3 (set_cache) permanent writes use _permanent,
    # and _permanent AND-s in lineups presence.
    assert "_permanent = _is_final and _lineups_ok" in src, \
        "picks.py permanent flag must AND-in lineups presence (INC-31)"
    assert "is_permanent=_permanent" in src and "permanent=_permanent" in src, \
        "picks.py must write both caches with the lineups-gated _permanent flag"


def test_no_bare_is_final_permanent_write_remains():
    # Regression guard: the old unconditional `is_permanent=_is_final` / `permanent=_is_final`
    # must be gone from picks.py's game-detail cache write.
    src = _src(_PICKS)
    assert "is_permanent=_is_final" not in src, "bare is_final permanence re-introduced (INC-31 regression)"
    assert "permanent=_is_final)" not in src, "bare is_final permanence re-introduced (INC-31 regression)"


def test_purge_script_targets_permanent_null_lineup_rows():
    # The one-time cleanup exists and is scoped to PERMANENT rows with null lineups.
    assert _PURGE.exists(), "purge_frozen_null_lineup_cache.py missing"
    src = _src(_PURGE)
    tree = ast.parse(src)  # must parse
    assert "#PERMANENT" in src and "_lineups_present" in src
    # Dry-run by default (an --apply flag must exist).
    assert "--apply" in src, "purge script must be dry-run by default with an --apply flag"


def test_purge_lineups_present_helper_logic():
    # Load just the helper to lock its semantics without importing boto3-heavy main().
    import importlib.util
    spec = importlib.util.spec_from_file_location("purge_frozen_null_lineup_cache", _PURGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._lineups_present({"lineups": {"home": [{"slot": 1}], "away": []}}) is True
    assert mod._lineups_present({"lineups": {"home": [], "away": [{"slot": 1}]}}) is True
    assert mod._lineups_present({"lineups": None}) is False
    assert mod._lineups_present({"lineups": {"home": [], "away": []}}) is False
    assert mod._lineups_present({}) is False

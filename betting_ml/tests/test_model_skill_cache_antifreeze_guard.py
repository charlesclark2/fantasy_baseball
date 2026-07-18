"""test_model_skill_cache_antifreeze_guard.py — E9.26b anti-freeze guard (INC-31 class).

The bug: the /performance/model "Model Skill — All Picks" endpoint cached a DEGENERATE
result — ``{"season": 2026, "markets": []}`` — written at the first request of the day
(the compute transiently returned nothing before the daily lakehouse export landed, and
``lakehouse_read.lakehouse_query`` swallows any DuckDB/S3 error → ``[]``). Because the blob
was accepted as a cache hit and served all day, the page rendered EMPTY even though a fresh
recompute returns the populated per-market tally.

The fix (app/backend/routers/performance.py):
  * READ  — an empty ``markets:[]`` cached blob is IGNORED (treated as a miss) so a frozen
            empty result never sticks.
  * WRITE — only a POPULATED tally is cached; an empty compute is returned uncached so the
            next request re-attempts and self-heals.

These are source-inspection + pure-helper-logic tests (fast-gate-safe: they do NOT import the
FastAPI app or the pipeline package, matching test_lineup_cache_antifreeze_guard.py).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).parents[2]
_PERF = _REPO / "app" / "backend" / "routers" / "performance.py"
_PURGE = _REPO / "scripts" / "purge_empty_model_skill_cache.py"


def _src(path: Path) -> str:
    return path.read_text()


def _load_helper(path: Path, name: str, attr: str):
    """Load a single module-level helper WITHOUT importing the heavy FastAPI router body
    (which pulls boto3/duckdb). We exec the source in a namespace and grab the function."""
    src = path.read_text()
    ns: dict = {"__name__": name, "__file__": str(path)}
    # The helper is pure (dict in → bool out); its only free names are builtins + `dict`/`list`
    # type checks, so exec-ing the whole module is unnecessary. Extract just the function def.
    import ast

    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == attr:
            mod = ast.Module(body=[node], type_ignores=[])
            exec(compile(mod, str(path), "exec"), ns)  # noqa: S102 — pure helper, test-only
            return ns[attr]
    raise AssertionError(f"{attr} not found in {path}")


def test_read_ignores_empty_cache_blob():
    src = _src(_PERF)
    assert "_model_cache_is_populated" in src, "lost the anti-freeze cache-populated gate"
    # The read must gate on the populated helper, not a bare `cached is not None`.
    assert "if _model_cache_is_populated(cached):" in src, \
        "read path must ignore an empty cached blob (INC-31 anti-freeze)"
    assert "if cached is not None:\n        return ModelMetricsResponse(**cached)" not in src, \
        "bare `cached is not None` read re-introduced (E9.26b regression)"


def test_write_only_caches_populated_result():
    src = _src(_PERF)
    # set_cache must be guarded by `if markets:` — never cache an empty tally.
    assert "if markets:\n        set_cache(cache_key" in src, \
        "write path must only cache a populated tally (INC-31 anti-freeze)"


def test_model_cache_is_populated_logic():
    fn = _load_helper(_PERF, "perf_helper", "_model_cache_is_populated")
    # Empty / degenerate → NOT populated (must recompute).
    assert fn({"season": 2026, "markets": []}) is False
    assert fn(None) is False
    assert fn([]) is False
    assert fn({"season": 2026}) is False
    # A real per-market tally → populated (serve it).
    assert fn({"season": 2026, "markets": [{"market_type": "h2h", "n_predictions": 1248}]}) is True


def test_purge_script_targets_empty_model_blobs():
    assert _PURGE.exists(), "purge_empty_model_skill_cache.py missing"
    src = _src(_PURGE)
    import ast

    ast.parse(src)  # must parse
    assert "--apply" in src, "purge script must be dry-run by default with an --apply flag"
    assert "/performance/model_" in src, "purge must target performance/model_*.json blobs"


def test_purge_is_empty_helper_logic():
    spec = importlib.util.spec_from_file_location("purge_empty_model_skill_cache", _PURGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import json

    assert mod._is_empty_model_blob(json.dumps({"season": 2026, "markets": []}).encode()) is True
    assert mod._is_empty_model_blob(json.dumps({"markets": None}).encode()) is True
    assert mod._is_empty_model_blob(
        json.dumps({"season": 2026, "markets": [{"market_type": "h2h"}]}).encode()
    ) is False
    assert mod._is_empty_model_blob(b"not json") is False  # unparseable → left alone

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


def test_base_query_does_not_join_wide_predictions_table():
    """E9.26b: the per-market tally must come from mart_clv_labeled_games ALONE. The old
    LEFT JOIN to the 94-column daily_model_predictions typed view (present in BOTH the incl
    and excl paths) is the read that failed in the Lambda and zeroed the page — it must be
    gone from the aggregation query."""
    src = _src(_PERF)
    # Isolate the aggregation-query constant.
    start = src.index("_MODEL_METRICS_QUERY = ")
    q = src[start:src.index('"""', src.index('"""', start) + 3) + 3]
    assert "mart_clv_labeled_games" in q, "base query lost its source mart"
    assert "daily_model_predictions" not in q, \
        "base tally query must NOT join daily_model_predictions (E9.26b — that wide read zeroed the page)"
    assert "LEFT JOIN" not in q.upper(), "base tally query must be a single-table read"


def test_degraded_exclusion_is_best_effort_and_isolated():
    src = _src(_PERF)
    assert "_fetch_degraded_game_pks" in src, "lost the best-effort degraded lookup"
    assert "_DEGRADED_GAME_PKS_QUERY" in src, "lost the narrow degraded-pk query"
    # It must be called from the endpoint to build the NOT IN filter.
    assert "degraded_pks = _fetch_degraded_game_pks()" in src, \
        "endpoint must fetch degraded pks as a separate step"
    assert "NOT IN" in src, "degraded exclusion must be a NOT IN filter built from the fetched pks"
    # And it must degrade to an EMPTY set (include all) rather than raise.
    assert "return set()" in src, "degraded lookup must degrade to an empty set on failure"


def test_fetch_degraded_game_pks_degrades_gracefully(monkeypatch):
    """A failing/empty wide-table read must NOT propagate — it returns an empty set so the
    caller includes all games (page still populates)."""
    import app.backend.routers.performance as perf

    # lakehouse_query raising → empty set (belt-and-suspenders path).
    monkeypatch.setattr(perf, "lakehouse_query", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert perf._fetch_degraded_game_pks() == set()

    # lakehouse_query returning [] (the observed Lambda symptom) → empty set, no raise.
    monkeypatch.setattr(perf, "lakehouse_query", lambda *a, **k: [])
    assert perf._fetch_degraded_game_pks() == set()

    # Normal rows → the pk set.
    monkeypatch.setattr(perf, "lakehouse_query", lambda *a, **k: [{"GAME_PK": 1}, {"GAME_PK": 2}, {"GAME_PK": None}])
    assert perf._fetch_degraded_game_pks() == {1, 2}


def test_endpoint_populates_and_does_not_cache_when_degraded_read_fails(monkeypatch):
    """End-to-end: even when the degraded read fails, the tally populates from the base mart,
    and (anti-freeze) a populated result IS cached while an empty one is NOT."""
    import app.backend.routers.performance as perf

    writes: dict[str, object] = {}
    monkeypatch.setattr(perf, "get_cache", lambda key: None)  # cache miss
    monkeypatch.setattr(perf, "set_cache", lambda key, data: writes.__setitem__(key, data))
    # Degraded read fails; base tally read returns two populated markets.
    monkeypatch.setattr(perf, "_fetch_degraded_game_pks", lambda: set())

    base_rows = [
        {"SEASON": 2026, "MARKET_TYPE": "h2h", "N_PREDICTIONS": 1311, "BRIER_SCORE": 0.24,
         "AVG_CLV": 0.0, "CLV_POSITIVE_PCT": 0.49, "WIN_RATE": 0.546},
        {"SEASON": 2026, "MARKET_TYPE": "totals", "N_PREDICTIONS": 1176, "BRIER_SCORE": 0.25,
         "AVG_CLV": 0.0, "CLV_POSITIVE_PCT": 0.50, "WIN_RATE": 0.520},
    ]
    monkeypatch.setattr(perf, "lakehouse_query", lambda *a, **k: base_rows)
    resp = perf.get_model_metrics(season=2026, include_degraded=False)
    assert len(resp.markets) == 2, "page must populate from the base mart even when degraded read fails"
    assert writes, "a populated result must be cached"

    # Empty compute → returned but NOT cached (anti-freeze).
    writes.clear()
    monkeypatch.setattr(perf, "lakehouse_query", lambda *a, **k: [])
    resp2 = perf.get_model_metrics(season=2026, include_degraded=False)
    assert resp2.markets == [], "empty compute returns empty markets"
    assert not writes, "an empty result must NOT be cached (INC-31 anti-freeze)"


def test_base_tally_survives_a_failing_degraded_refinement(monkeypatch):
    """E9.26b reorder: the reliable base query runs FIRST; if the degraded re-aggregation
    then fails or returns empty, the base (all-games) tally is KEPT — never zeroed."""
    import app.backend.routers.performance as perf

    monkeypatch.setattr(perf, "get_cache", lambda key: None)
    monkeypatch.setattr(perf, "set_cache", lambda key, data: None)
    # There ARE degraded games (so the refinement path is taken).
    monkeypatch.setattr(perf, "_fetch_degraded_game_pks", lambda: {823812, 824335})

    base_rows = [
        {"SEASON": 2026, "MARKET_TYPE": "h2h", "N_PREDICTIONS": 1311, "BRIER_SCORE": 0.24,
         "AVG_CLV": 0.0, "CLV_POSITIVE_PCT": 0.49, "WIN_RATE": 0.546},
        {"SEASON": 2026, "MARKET_TYPE": "totals", "N_PREDICTIONS": 1176, "BRIER_SCORE": 0.25,
         "AVG_CLV": 0.0, "CLV_POSITIVE_PCT": 0.50, "WIN_RATE": 0.520},
    ]
    calls = {"n": 0}

    def fake_lakehouse_query(sql, params=None):
        calls["n"] += 1
        # 1st call = base (no exclusion) → populated; 2nd call = excl re-aggregation → EMPTY.
        return base_rows if calls["n"] == 1 else []

    monkeypatch.setattr(perf, "lakehouse_query", fake_lakehouse_query)
    resp = perf.get_model_metrics(season=2026, include_degraded=False)
    assert calls["n"] == 2, "base query then excl re-aggregation should both be attempted"
    assert [m.n_predictions for m in resp.markets] == [1311, 1176], \
        "a failing/empty excl re-aggregation must KEEP the base all-games tally, not zero it"


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

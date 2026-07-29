"""Root pytest conftest.

WHY THIS EXISTS — the intermittent `snowflake.connector is not a package` collection error
-------------------------------------------------------------------------------------------
`snowflake` (snowflake-connector-python) is a NAMESPACE package, so its `__path__` is assembled
from every matching entry on `sys.path`. The repo vendors a PARTIAL copy at
`.lambda_build/package/snowflake` (a Lambda build artifact) and also has an unrelated
`app/backend/services/snowflake.py`. During a FULL test collection, pytest's per-test sys.path
churn can let one of those entries join the `snowflake` namespace before the real
`snowflake.connector` submodule is bound — after which `scripts/tests/test_savant_ingestion.py`'s
`from snowflake.connector.pandas_tools import write_pandas` fails with
`ModuleNotFoundError: ... 'snowflake.connector' is not a package`. The failure is ORDER-DEPENDENT
(it only surfaces for some collection orders), so it appears/disappears as test files are added.

THE FIX: import the real `snowflake.connector.pandas_tools` ONCE, here, before any test module is
collected. That binds `sys.modules['snowflake.connector']` (and `…pandas_tools`) to the genuine
site-packages package; every later `import snowflake.connector…` then hits the cache and cannot be
shadowed by the vendored/partial copy. Best-effort: if snowflake isn't installed at all, tests that
need it skip on their own.
"""

try:  # pragma: no cover - import-ordering guard, not logic under test
    import snowflake.connector.pandas_tools  # noqa: F401
except Exception:
    pass


# ── dummy Snowflake env so importing `pipeline` never needs real credentials ──────────────────
# `pipeline/resources/__init__.py` builds a SnowflakeResource at IMPORT with BRACKET env access
# (`os.environ["SNOWFLAKE_ACCOUNT"]`), so merely importing `pipeline` raises KeyError when those
# vars are absent — as they are on a CI runner. No connection is ever made; only construction.
#
# WHY THIS LIVES HERE (2026-07-27). These defaults used to be set at MODULE level inside
# `test_e11_1_w12_sensor_fire.py`, which happens to sort before `test_monitor_health_wiring.py`.
# Collection imported the first module, its env leak landed, and the second module's `import
# pipeline` then worked — so a LOAD-BEARING side effect was disguised as an unrelated test's
# setup. Moving that leak into a properly-scoped fixture (correct, per the import-time isolation
# rule) removed the crutch and exposed the real, pre-existing dependency: it broke the slow gate,
# which builds the dbt manifest and therefore actually reaches the `pipeline` import.
#
# conftest is the right owner: it runs ONCE per process, BEFORE any test module is collected, so
# the guarantee is deterministic instead of depending on filename order. `setdefault` means a real
# local/box value always wins — this only ever fills an absent var.
#
# NOTE the fast gate never hits this: `test_monitor_health_wiring.py` skips at module level when
# dbt/target/manifest.json is missing, and only the slow job runs `dbtf parse` to build it.
def pytest_configure(config):  # noqa: ARG001 - pytest hook signature
    import os

    for _var in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_ROLE"):
        os.environ.setdefault(_var, "dummy_for_tests")

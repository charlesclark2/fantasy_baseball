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

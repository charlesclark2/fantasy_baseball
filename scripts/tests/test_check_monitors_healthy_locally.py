"""NF-INFRA1 follow-up — import-safety + off-box behaviour for the on-demand heartbeat runner.

`DagsterInstance.get()` needs `DAGSTER_HOME` — it is only meaningful ON THE BOX (see the module
docstring). Off-box (CI, the laptop) it must fail with a clear message, not a raw traceback or a
silent success that would mislead an operator into thinking the real state was checked.

Importing `check_monitors_healthy_locally` itself must stay MANIFEST-FREE (E11.23): the script
defers its `pipeline.ops.daily_ingestion_ops` import inside `_build_standalone_job()`, called only
from `main()` — never at module scope — so this whole test file is fast-gate safe. A second test
that DOES need the real op (proving the job wraps it, not a stand-in) lives in
`test_monitor_health_wiring.py`'s style: it SKIPS when the compiled dbt manifest is absent, exactly
like the rest of the manifest-guarded suite.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import check_monitors_healthy_locally as target

_MANIFEST = Path(__file__).resolve().parents[2] / "dbt" / "target" / "manifest.json"


def test_off_box_without_dagster_home_fails_clearly(monkeypatch, capsys):
    monkeypatch.delenv("DAGSTER_HOME", raising=False)
    rc = target.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "DAGSTER_HOME is not set" in out
    assert "docker compose" in out and "dagster-codeloc" in out


@pytest.mark.skipif(
    not _MANIFEST.exists(),
    reason="pipeline import requires dbt/target/manifest.json (absent in the fast gate); "
           "runs locally / on the box after a dbt compile.",
)
def test_the_wrapping_job_contains_the_real_op():
    """Not a stand-in — the same op object the daily job runs."""
    from pipeline.ops.daily_ingestion_ops import check_monitors_healthy_op

    standalone_job = target._build_standalone_job()
    node_names = {node.name for node in standalone_job.nodes}
    assert check_monitors_healthy_op.name in node_names

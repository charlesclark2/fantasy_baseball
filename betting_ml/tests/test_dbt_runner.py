"""Tests for E11.0 — dbt-runner container integration.

Covers:
  1. DbtRunnerResource — successful run, failure, auth headers, polling, timeout
  2. _run_dbt_remote() in both ops files — success, failure, auth env var
  3. server.py _execute() helper — correct command assembly, failure status

Import strategy: pipeline.* modules are loaded via importlib.util.spec_from_file_location
to avoid triggering pipeline/__init__.py (which loads Dagster Definitions + assets and
requires Snowflake credentials not present in the test env).

Patch strategy: patch.object(module, 'attr') instead of string-path patch so that
unittest.mock doesn't resolve the module name via importlib.import_module (which would
also trigger pipeline/__init__.py).
"""
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

_REPO = Path(__file__).parents[2]


def _load(name: str, rel: str):
    """Load a module from a repo-relative path without going through pipeline/__init__.py."""
    path = str(_REPO / rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── DbtRunnerResource ────────────────────────────────────────────────────────

class TestDbtRunnerResource:
    @pytest.fixture(autouse=True)
    def _setup(self):
        mod = _load("_dbt_runner_resource", "pipeline/resources/dbt_runner_resource.py")
        self._DbtRunnerResource = mod.DbtRunnerResource
        self._mod = mod

    def _resource(self, endpoint="http://runner:8080", token=""):
        return self._DbtRunnerResource(
            endpoint_url=endpoint, auth_token=token, poll_interval_seconds=0
        )

    def _mock_context(self):
        ctx = MagicMock()
        ctx.job_name = "test_job"
        return ctx

    def test_success(self):
        resource = self._resource()
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "abc123"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "OK", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()
        mock_sleep = MagicMock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", mock_sleep):
            result = resource.run(ctx, ["run", "--select", "mart_odds_outcomes"])

        assert result["status"] == "success"
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["args"] == ["run", "--select", "mart_odds_outcomes"]
        assert payload["env"]["DBT_JOB_NAME"] == "test_job"

    def test_failure_raises(self):
        resource = self._resource()
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "fail1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "failed", "returncode": 1, "stdout": "", "stderr": "model error"}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            with pytest.raises(Exception, match="failed"):
                resource.run(ctx, ["build"])

    def test_auth_header_sent(self):
        resource = self._resource(token="my-secret")
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "a1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            resource.run(ctx, ["run"])

        sent = mock_post.call_args.kwargs["headers"]
        assert sent.get("Authorization") == "Bearer my-secret"

    def test_no_auth_header_when_empty_token(self):
        resource = self._resource(token="")
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "a2"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            resource.run(ctx, ["run"])

        sent = mock_post.call_args.kwargs["headers"]
        assert "Authorization" not in sent

    def test_polls_until_complete(self):
        resource = self._resource()
        ctx = self._mock_context()
        running = {"status": "running", "returncode": None, "stdout": "", "stderr": ""}
        done = {"status": "success", "returncode": 0, "stdout": "Done", "stderr": ""}
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "poll1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.raise_for_status = Mock()
        mock_get.return_value.json.side_effect = [running, running, done]

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            result = resource.run(ctx, ["run"])

        assert result["status"] == "success"
        assert mock_get.call_count == 3

    def test_timeout_raises(self):
        resource = self._DbtRunnerResource(
            endpoint_url="http://runner:8080", timeout_seconds=0, poll_interval_seconds=0
        )
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "slow"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "running"}
        mock_get.return_value.raise_for_status = Mock()
        # monotonic returns 0 (deadline=0), then 100 (past deadline) → loop exits immediately
        mock_monotonic = MagicMock(side_effect=[0, 100, 200])

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()), \
             patch.object(self._mod.time, "monotonic", mock_monotonic):
            with pytest.raises(TimeoutError):
                resource.run(ctx, ["run"])


# ── _dbt_exec shared helper ───────────────────────────────────────────────────
# E11.0c: _run_dbt_remote and _run_dbt now live in pipeline/ops/_dbt_exec.py.
# Tests load that module directly so patches target the right requests/time/subprocess.

class TestDbtExecRemote:
    """Tests for _dbt_exec._run_dbt_remote (the consolidated remote-delegation helper)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        mod = _load("pipeline.ops._dbt_exec", "pipeline/ops/_dbt_exec.py")
        self._fn = mod._run_dbt_remote
        self._mod = mod

    def _mock_context(self, job_name="test_job"):
        ctx = MagicMock()
        ctx.job_name = job_name
        return ctx

    def test_success(self):
        ctx = self._mock_context("daily_job")
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "d1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "OK", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            self._fn(ctx, ["run", "--select", "stg_oddsapi_odds"], "http://runner:8080")

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["env"]["DBT_JOB_NAME"] == "daily_job"

    def test_failure_raises(self):
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "d2"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "failed", "returncode": 1, "stdout": "", "stderr": "bad sql"}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            with pytest.raises(Exception, match="failed"):
                self._fn(ctx, ["build"], "http://runner:8080")

    def test_auth_env_var_forwarded(self, monkeypatch):
        monkeypatch.setenv("DBT_RUNNER_AUTH_TOKEN", "tok123")
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "d3"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            self._fn(ctx, ["run"], "http://runner:8080")

        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok123"

    def test_timeout_param_controls_deadline(self):
        """timeout_seconds=0 forces immediate timeout when the run stays in 'running'."""
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "slow"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "running"}
        mock_get.return_value.raise_for_status = Mock()
        mock_monotonic = MagicMock(side_effect=[0, 1, 100])

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()), \
             patch.object(self._mod.time, "monotonic", mock_monotonic):
            with pytest.raises(TimeoutError):
                self._fn(ctx, ["run"], "http://runner:8080", timeout_seconds=0)

    def test_busy_409_raises_retry_requested(self):
        """409 (runner busy) raises RetryRequested so Dagster releases the compute slot.

        INC-3b (2026-06-19): the original fix used a sleep loop inside the op, which
        held Dagster run-minutes open for the full wait. RetryRequested tells Dagster
        to reschedule the step after seconds_to_wait without keeping compute alive.
        """
        from dagster import RetryRequested as _RetryRequested
        ctx = self._mock_context()

        busy_resp = MagicMock()
        busy_resp.status_code = 409

        mock_post = MagicMock(return_value=busy_resp)

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            with pytest.raises(_RetryRequested):
                self._fn(ctx, ["run", "--select", "mart_odds_outcomes"], "http://runner:8080")

        mock_post.assert_called_once()

    def test_use_state_forwarded_in_payload(self):
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "s1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            self._fn(ctx, ["build"], "http://runner:8080", use_state=True)

        assert mock_post.call_args.kwargs["json"]["use_state"] is True


class TestDbtExecSubprocess:
    """Tests for _dbt_exec._run_dbt subprocess path (DBT_RUNNER_URL unset)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        mod = _load("pipeline.ops._dbt_exec", "pipeline/ops/_dbt_exec.py")
        self._run_dbt = mod._run_dbt
        self._mod = mod

    def _mock_context(self):
        ctx = MagicMock()
        ctx.job_name = "test_job"
        return ctx

    def test_success_runs_dbtf(self, monkeypatch):
        """subprocess path builds the right dbtf command and succeeds."""
        monkeypatch.delenv("DBT_RUNNER_URL", raising=False)
        ctx = self._mock_context()
        result = MagicMock()
        result.returncode = 0
        result.stdout = "OK"
        result.stderr = ""
        with patch.object(self._mod.subprocess, "run", return_value=result) as mock_run:
            self._run_dbt(ctx, ["run", "--select", "mart_odds_outcomes", "--target", "prod"])
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "dbtf"
        assert "run" in cmd
        assert "--project-dir" in cmd

    def test_job_name_injected_in_env(self, monkeypatch):
        """DBT_JOB_NAME and DAGSTER_JOB_NAME are added to the subprocess env."""
        monkeypatch.delenv("DBT_RUNNER_URL", raising=False)
        ctx = self._mock_context()
        ctx.job_name = "my_dagster_job"
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        with patch.object(self._mod.subprocess, "run", return_value=result) as mock_run:
            self._run_dbt(ctx, ["run", "--select", "foo"])
        env = mock_run.call_args.kwargs["env"]
        assert env["DBT_JOB_NAME"] == "my_dagster_job"
        assert env["DAGSTER_JOB_NAME"] == "my_dagster_job"

    def test_nonzero_exit_raises(self, monkeypatch):
        """Non-zero returncode raises Exception with failure detail."""
        monkeypatch.delenv("DBT_RUNNER_URL", raising=False)
        ctx = self._mock_context()
        result = MagicMock()
        result.returncode = 1
        result.stdout = "a" * 5000  # long stdout — should use tail
        result.stderr = ""
        with patch.object(self._mod.subprocess, "run", return_value=result):
            with pytest.raises(Exception, match="failed"):
                self._run_dbt(ctx, ["run", "--select", "bad_model"])

    def test_timeout_expired_raises_exception(self, monkeypatch):
        """A wedged subprocess (TimeoutExpired) is re-raised as Exception — not a silent hang.

        INC-3 (2026-06-19): statcast_catchup_job ran dbtf in-process on Dagster compute
        and hung ~1h because sensor_ops._run_dbt had no DBT_RUNNER_URL check. This test
        verifies that the hard timeout ceiling on the subprocess path actually kills the
        process and surfaces a fast, visible failure so the op retries rather than hanging.
        """
        monkeypatch.delenv("DBT_RUNNER_URL", raising=False)
        ctx = self._mock_context()
        import subprocess as _subprocess
        exc = _subprocess.TimeoutExpired(cmd=["dbtf", "run"], timeout=5, output=b"partial output")

        with patch.object(self._mod.subprocess, "run", side_effect=exc):
            with pytest.raises(Exception, match="hard timeout"):
                self._run_dbt(ctx, ["run", "--select", "stg_batter_pitches"], timeout=5)

    def test_delegates_to_remote_when_url_set(self, monkeypatch):
        """When DBT_RUNNER_URL is set, the subprocess is never called."""
        monkeypatch.setenv("DBT_RUNNER_URL", "http://runner:8080")
        ctx = self._mock_context()
        mock_remote = MagicMock()
        with patch.object(self._mod, "_run_dbt_remote", mock_remote):
            # _run_dbt_remote is mocked — subprocess.run should never fire
            with patch.object(self._mod.subprocess, "run", side_effect=AssertionError("subprocess called")):
                self._run_dbt(ctx, ["run", "--select", "foo"])
        mock_remote.assert_called_once()
        _, kwargs = mock_remote.call_args[0], mock_remote.call_args.kwargs
        # runner_url should be the env var value
        assert "http://runner:8080" in mock_remote.call_args[0]

    def test_state_aware_local_args_include_view_selector(self):
        """INC-13 regression: _local_state_aware_args must union config.materialized:view
        with source_status:fresher+ so unmodified views are always rebuilt (DDL-only,
        cheap) rather than silently skipped, which causes cryptic 'object does not exist'
        errors when a downstream model references a never-built view.
        """
        ctx = self._mock_context()
        mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            result = self._mod._local_state_aware_args(
                ctx, ["build", "--target", "prod"], {}
            )

        assert "--select" in result, "state-aware args must contain --select"
        select_val = result[result.index("--select") + 1]
        assert "source_status:fresher+" in select_val, "must keep incremental selector"
        assert "config.materialized:view" in select_val, "INC-13: views must always be rebuilt"


# ── server._execute command assembly ─────────────────────────────────────────

class TestServerExecute:
    """Import services/dbt_runner/server.py and verify _execute behaviour."""

    @pytest.fixture(autouse=True)
    def _server_mod(self, monkeypatch, tmp_path):
        runner_dir = str(_REPO / "services" / "dbt_runner")
        monkeypatch.syspath_prepend(runner_dir)
        sys.modules.pop("server", None)
        monkeypatch.setenv("DBT_PROJECT_DIR", str(tmp_path))
        self._server = importlib.import_module("server")
        yield
        sys.modules.pop("server", None)

    def test_command_includes_project_dir(self):
        captured: dict = {}

        def fake_run(cmd, **_kw):
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stdout = "ok"
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self._server._execute("x1", ["build", "--select", "my_model"], {})

        assert "dbtf" in captured["cmd"]
        assert "--project-dir" in captured["cmd"]
        assert "--profiles-dir" in captured["cmd"]
        assert "build" in captured["cmd"]
        assert "--select" in captured["cmd"]

    def test_failed_run_sets_status(self):
        self._server._runs["fail1"] = {"status": "running"}

        def fake_run(cmd, **_kw):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "compilation error"
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self._server._execute("fail1", ["build"], {})

        assert self._server._runs["fail1"]["status"] == "failed"
        assert self._server._runs["fail1"]["returncode"] == 1
        assert "compilation error" in self._server._runs["fail1"]["stderr"]

    def test_state_aware_select_includes_view_selector(self):
        """INC-13 regression: server _execute with use_state=True must include
        config.materialized:view in the --select to prevent the view-skip bug
        where state:fresher+ omits unmodified views that downstream models need.
        """
        captured: dict = {}

        def fake_run(cmd, **_kw):
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=fake_run), \
             patch.object(self._server, "_download_state", return_value=True), \
             patch.object(self._server, "_upload_state"):
            self._server._execute("x_inc13", ["build"], {}, use_state=True)

        assert "--select" in captured["cmd"], "state-aware build must have --select"
        select_idx = captured["cmd"].index("--select")
        select_val = captured["cmd"][select_idx + 1]
        assert "source_status:fresher+" in select_val, "must keep incremental selector"
        assert "config.materialized:view" in select_val, "INC-13: views must always be rebuilt"

    # ── INC-32: the wedge that held the single-tenant lock forever ────────────────
    def test_run_cmd_passes_hard_timeout(self):
        """_run_cmd must pass a finite timeout so a wedged dbtf is KILLED, not hung forever."""
        captured: dict = {}

        def fake_run(cmd, **kw):
            captured["timeout"] = kw.get("timeout")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self._server._run_cmd(["dbtf", "run"], {})
        assert captured["timeout"] is not None and captured["timeout"] > 0, (
            "INC-32: _run_cmd must set a finite subprocess timeout"
        )

    def test_wedged_dbtf_timeout_marks_run_failed_and_frees_lock(self):
        """A wedged dbtf (TimeoutExpired) must transition the run to 'failed' — NOT leave it
        'running' (which would 409 every subsequent /run forever)."""
        import subprocess as _sp
        self._server._runs["wedged"] = {"status": "running", "started_monotonic": 0.0}

        def fake_run(cmd, **_kw):
            raise _sp.TimeoutExpired(cmd=cmd, timeout=5, output=b"partial")

        with patch("subprocess.run", side_effect=fake_run):
            self._server._execute("wedged", ["run"], {})

        assert self._server._runs["wedged"]["status"] == "failed", (
            "INC-32: a timed-out run must be marked failed so the single-tenant lock frees"
        )
        assert self._server._runs["wedged"]["returncode"] == 124

    def test_execute_crash_marks_run_failed(self):
        """Any unexpected exception in _execute must still set a terminal status (lock frees)."""
        self._server._runs["boom"] = {"status": "running", "started_monotonic": 0.0}
        with patch.object(self._server, "_execute_impl", side_effect=RuntimeError("kaboom")):
            self._server._execute("boom", ["run"], {})
        assert self._server._runs["boom"]["status"] == "failed"
        assert "kaboom" in self._server._runs["boom"]["stderr"]

    def test_reaper_frees_dead_running_entry(self):
        """A 'running' entry older than the ceiling is reaped → a new /run is not 409'd forever."""
        ceiling = self._server._MAX_RUN_SECONDS + self._server._REAP_GRACE_SECONDS
        now = 1_000_000.0
        self._server._runs.clear()
        self._server._runs["dead"] = {
            "status": "running", "started_monotonic": now - ceiling - 10,
        }
        self._server._reap_stale_runs(now)
        assert self._server._runs["dead"]["status"] == "failed", (
            "INC-32: a run stuck 'running' past the ceiling must be reaped so the lock frees"
        )

    def test_reaper_leaves_healthy_running_entry(self):
        """A fresh in-flight run must NOT be reaped (real concurrency still 409s correctly)."""
        now = 1_000_000.0
        self._server._runs.clear()
        self._server._runs["live"] = {"status": "running", "started_monotonic": now - 5}
        self._server._reap_stale_runs(now)
        assert self._server._runs["live"]["status"] == "running"

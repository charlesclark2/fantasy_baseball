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


# ── _run_dbt_remote (daily_ingestion_ops) ────────────────────────────────────

class TestRunDbtRemoteDailyOps:
    @pytest.fixture(autouse=True)
    def _setup(self):
        mod = _load("_daily_ingestion_ops", "pipeline/ops/daily_ingestion_ops.py")
        self._fn = mod._run_dbt_remote
        self._mod = mod

    def _mock_context(self):
        ctx = MagicMock()
        ctx.job_name = "daily_job"
        return ctx

    def test_success(self):
        ctx = self._mock_context()
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


# ── _run_dbt_remote (intraday_ops) ───────────────────────────────────────────

class TestRunDbtRemoteIntradayOps:
    @pytest.fixture(autouse=True)
    def _setup(self):
        mod = _load("_intraday_ops", "pipeline/ops/intraday_ops.py")
        self._fn = mod._run_dbt_remote
        self._mod = mod

    def _mock_context(self):
        ctx = MagicMock()
        ctx.job_name = "intraday_job"
        return ctx

    def test_success(self):
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "i1"}
        mock_post.return_value.raise_for_status = Mock()
        mock_get = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "returncode": 0, "stdout": "", "stderr": ""}
        mock_get.return_value.raise_for_status = Mock()

        with patch.object(self._mod.requests, "post", mock_post), \
             patch.object(self._mod.requests, "get", mock_get), \
             patch.object(self._mod.time, "sleep", MagicMock()):
            self._fn(ctx, ["run", "--select", "mart_odds_outcomes"], "http://runner:8080")

        mock_post.assert_called_once()

    def test_timeout_param_forwarded(self):
        """Caller-supplied timeout_seconds controls the deadline."""
        ctx = self._mock_context()
        mock_post = MagicMock()
        mock_post.return_value.json.return_value = {"run_id": "slow2"}
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

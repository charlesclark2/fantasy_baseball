"""E11.0 — DbtRunnerResource.

Dagster ConfigurableResource that delegates dbt execution to the external
dbt-runner Railway HTTP service (services/dbt_runner/). When this resource
is active, Dagster only coordinates — dbt runs in the container, not on
Dagster+ metered compute.

The simpler env-var dispatch path in pipeline/ops/*_ops.py checks
DBT_RUNNER_URL directly (see _run_dbt_remote there) so existing ops can
pick up the container without being refactored to accept resources. This
module is the proper Dagster-resource interface for future op migrations
and direct injection.
"""
import time
from typing import Any

import requests
from dagster import ConfigurableResource, OpExecutionContext


class DbtRunnerResource(ConfigurableResource):
    """Triggers dbt builds on the dbt-runner Railway HTTP service.

    endpoint_url: full URL of the Railway service, e.g.
                  https://dbt-runner-prod.railway.app
    auth_token:   must match DBT_RUNNER_AUTH_TOKEN on the service side.
                  Leave empty to disable auth (dev/local only).
    """
    endpoint_url: str
    auth_token: str = ""
    poll_interval_seconds: int = 15
    timeout_seconds: int = 2700  # 45-minute ceiling matches the Snowflake job SLA

    def _headers(self) -> dict[str, str]:
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    def run(
        self,
        context: OpExecutionContext,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Trigger a dbtf invocation on the container and block until it completes.

        args:      the dbt sub-command and flags, e.g. ["run", "--select", "mart_odds_outcomes"]
        extra_env: forwarded to the container as additional env vars (e.g. DBT_JOB_NAME).
        Returns the final status dict {status, returncode, stdout, stderr}.
        Raises on dbt failure or timeout.
        """
        url = self.endpoint_url.rstrip("/")
        payload: dict[str, Any] = {
            "args": args,
            "env": {
                "DBT_JOB_NAME": context.job_name,
                "DAGSTER_JOB_NAME": context.job_name,
                **(extra_env or {}),
            },
        }

        resp = requests.post(f"{url}/run", json=payload, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        run_id = resp.json()["run_id"]
        context.log.info(f"[dbt-runner] started run {run_id} — dbtf {' '.join(args[:3])} …")

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval_seconds)
            status_resp = requests.get(
                f"{url}/status/{run_id}", headers=self._headers(), timeout=15
            )
            status_resp.raise_for_status()
            data: dict[str, Any] = status_resp.json()
            if data["status"] == "running":
                context.log.debug(f"[dbt-runner] {run_id} still running …")
                continue
            if data.get("stdout"):
                context.log.info(data["stdout"])
            if data.get("stderr"):
                context.log.warning(data["stderr"])
            if data["status"] == "failed":
                raise Exception(
                    f"[dbt-runner] run {run_id} failed (exit {data.get('returncode')})\n"
                    f"{data.get('stderr', '')}"
                )
            context.log.info(f"[dbt-runner] run {run_id} succeeded")
            return data

        raise TimeoutError(
            f"[dbt-runner] run {run_id} exceeded {self.timeout_seconds}s timeout"
        )

"""pipeline/ops/_dbt_exec.py — shared dbt execution helper (E11.0c).

Single source of truth replacing the three diverged private copies in
sensor_ops, intraday_ops, and daily_ingestion_ops.  Import via:
    from pipeline.ops._dbt_exec import _run_dbt, _failure_detail
"""
import json
import os
import subprocess
import time
from datetime import datetime

import requests
from dagster import RetryRequested

APP_DIR = "/app"
DBT_DIR = "/app/dbt"
_SUBPROCESS_TIMEOUT = 1800  # seconds (30 min) — hard ceiling per subprocess op


def _failure_detail(result) -> str:
    """Diagnostic tail for a failed subprocess.

    dbt-fusion writes everything to STDOUT and leaves stderr empty, so a bare
    {stderr} loses the real error to Dagster's 50k log truncation (incident
    2026-06-11). Prefer stderr; fall back to the stdout tail (dbt's end-of-run
    failure summary lives there).
    """
    err = (result.stderr or "").strip()
    if err:
        return err[-4000:]
    out_tail = (result.stdout or "")[-4000:]
    return f"(stderr empty — stdout tail)\n{out_tail}"


def _run_dbt_remote(
    context,
    args: list[str],
    runner_url: str,
    timeout_seconds: int = _SUBPROCESS_TIMEOUT,
    use_state: bool = False,
    run_ref: dict | None = None,
) -> None:
    """Delegate a dbt run to the E11.0 dbt-runner Railway service (services/dbt_runner/).

    Called when DBT_RUNNER_URL is set — dbt execution runs in the Railway container,
    not on Dagster+ metered compute. Falls back to in-process dbtf when absent.
    use_state=True (E11.2): the runner downloads prior manifest/sources.json from S3
    and selects source_status:fresher+ instead of the full DAG.
    """
    auth_token = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    extra_env = {"DBT_JOB_NAME": context.job_name, "DAGSTER_JOB_NAME": context.job_name}

    url = runner_url.rstrip("/")
    deadline = time.monotonic() + timeout_seconds

    # 409 = runner busy (single-tenant). Raise RetryRequested so Dagster releases the
    # compute slot during the wait — sleeping in the op holds run-minutes open for nothing.
    resp = requests.post(
        f"{url}/run",
        json={"args": args, "env": extra_env, "use_state": use_state},
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 409:
        context.log.info("[dbt-runner] runner busy (409) — releasing compute slot, retry in 30s")
        raise RetryRequested(max_retries=40, seconds_to_wait=30)
    resp.raise_for_status()

    run_id = resp.json()["run_id"]
    # INC-41: record the run_id for a caller that wants to fetch this invocation's
    # target/run_results.json afterwards (see capture_dbt_results). Written BEFORE the poll loop
    # so it survives the failure path — an error-severity dbt test failure raises out of this
    # function, and that is precisely the case the pager needs the run_id for.
    if run_ref is not None:
        run_ref["run_id"] = run_id
        run_ref["runner_url"] = url
    context.log.info(f"[dbt-runner] started run {run_id} — dbtf {' '.join(args[:3])} …")
    while time.monotonic() < deadline:
        time.sleep(15)
        status_resp = requests.get(f"{url}/status/{run_id}", headers=headers, timeout=15)
        status_resp.raise_for_status()
        data = status_resp.json()
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
        return
    raise TimeoutError(f"[dbt-runner] run {run_id} timed out after {timeout_seconds}s")


def _run_dbt(
    context,
    args: list[str],
    timeout: int = _SUBPROCESS_TIMEOUT,
    use_state: bool = False,
    run_ref: dict | None = None,
) -> None:
    """Run a dbt command, delegating to the E11.0 runner when DBT_RUNNER_URL is set.

    Falls back to a local dbtf subprocess for dev/CI (DBT_RUNNER_URL unset).
    A hard timeout kills the subprocess if it wedges (incidents 2026-06-15/19).

    run_ref (INC-41): optional dict the caller supplies to receive this invocation's provenance
    (`run_id` + `runner_url` on the remote path, `local_target` on the local one), so it can then
    fetch target/run_results.json via `capture_dbt_results`. Purely an OUT-parameter: omitting it
    is the default and changes nothing, which is why the other callers of this HALT-tier helper
    are untouched. It is not a return value because this function raises on a failed dbt run —
    and a failed run is exactly when the results matter most.
    """
    runner_url = os.environ.get("DBT_RUNNER_URL")
    if runner_url:
        _run_dbt_remote(context, args, runner_url, timeout_seconds=timeout,
                        use_state=use_state, run_ref=run_ref)
        return

    if run_ref is not None:
        run_ref["local_target"] = os.path.join(DBT_DIR, "target", "run_results.json")

    env = {**os.environ, "DBT_JOB_NAME": context.job_name, "DAGSTER_JOB_NAME": context.job_name}
    if use_state:
        effective_args = _local_state_aware_args(context, args, env)
    else:
        effective_args = args
    cmd = ["dbtf"] + effective_args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)} (timeout {timeout}s)")
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        stdout_tail = ""
        if isinstance(e.stdout, bytes):
            stdout_tail = e.stdout[-2000:].decode(errors="replace")
        elif isinstance(e.stdout, str):
            stdout_tail = e.stdout[-2000:]
        raise Exception(
            f"dbtf {args[0]} exceeded {timeout}s hard timeout and was killed\n"
            f"(stdout tail)\n{stdout_tail}"
        ) from e
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        detail = _failure_detail(result)
        context.log.error(f"dbtf {args[0]} failed (exit {result.returncode}) — failure tail:\n{detail}")
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{detail}")
    if use_state:
        _local_state_upload(context, args, env)


# ── INC-41: capturing the dbt test results for the pager ─────────────────────
#
# The daily dbt test step is WARN-tier by design (INC-6) — a peripheral data-quality failure must
# never block predictions. The consequence INC-41 exposed is that a red SERVING-CRITICAL contract
# is caught, logged, and silently forgotten until someone opens the next PR. `check_dbt_test_results_op`
# closes that; these helpers are how the results reach it.
#
# The artifact does NOT live where you would expect. On the box `DBT_RUNNER_URL` is always set
# (compose: http://dbt-runner:8080), so dbt executes in the dbt-runner CONTAINER, which shares no
# volume with dagster-codeloc — `/app/dbt/target/run_results.json` in the op's own filesystem is
# NOT the daily suite's output and would be silently stale forever. Hence the runner's
# GET /run_results/{run_id}. The local file path is the dev/CI fallback only.
DBT_RESULTS_DIR = "/tmp/credence_dbt_test_results"

# dbt commands that actually execute tests. `run` does not; reading its run_results.json and
# reporting "0 failures" would be a clean bill of health from an artifact that tested nothing.
_TEST_BEARING_COMMANDS = frozenset({"test", "build"})


def _results_path(context) -> str:
    """Per-Dagster-run path. Keying on context.run_id (not a constant filename) means the pager
    op cannot read a PREVIOUS daily run's results if this run's capture failed — the stale-artifact
    class this repo keeps hitting. A missing file reads as UNVERIFIED, which is the honest state."""
    return os.path.join(DBT_RESULTS_DIR, f"{context.run_id}.json")


def _fetch_run_results(context, run_ref: dict) -> tuple[dict | None, str]:
    """Retrieve this invocation's run_results.json. Returns (payload, reason_if_missing)."""
    run_id = run_ref.get("run_id")
    runner_url = run_ref.get("runner_url")
    if run_id and runner_url:
        auth_token = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        try:
            resp = requests.get(f"{runner_url}/run_results/{run_id}", headers=headers, timeout=30)
        except Exception as exc:  # noqa: BLE001 — observability only; never fail the dbt op
            return None, f"dbt-runner unreachable for run_results ({type(exc).__name__}: {exc})"
        if resp.status_code == 404:
            return None, f"dbt-runner has no run_results for run {run_id} (older image? no artifact written)"
        if resp.status_code != 200:
            return None, f"dbt-runner returned HTTP {resp.status_code} for run_results"
        try:
            return resp.json(), ""
        except ValueError as exc:
            return None, f"dbt-runner run_results was not valid JSON ({exc})"

    local = run_ref.get("local_target")
    if not local:
        return None, "no dbt invocation provenance was recorded (run_ref never populated)"
    if not os.path.exists(local):
        return None, f"{local} does not exist"
    try:
        with open(local) as fh:
            return json.load(fh), ""
    except (OSError, ValueError) as exc:
        return None, f"could not read {local} ({exc})"


def _verify_provenance(payload: dict, started_at: float) -> tuple[dict, str]:
    """Return (provenance, reason_if_untrustworthy) for a fetched run_results payload.

    Two ways a run_results.json can describe something OTHER than the test step we just ran, both
    of which would otherwise be reported as a clean suite:
      1. It is the `run` step's artifact (dbt overwrites the same file per invocation), so it
         contains zero test nodes — "0 failures" from a command that ran no tests.
      2. It is a PREVIOUS day's artifact, left behind because this invocation died before writing.
    Neither is distinguishable from a healthy result by content alone, so the command and the
    generation time are checked explicitly. This is the INC-39 lesson — a monitor parsing another
    process's output must be able to verify WHICH invocation the numbers describe; replayed or
    stale output parses byte-identically to a live read.
    """
    args = payload.get("args") or {}
    metadata = payload.get("metadata") or {}
    command = str((args.get("command") or args.get("which") or "")).strip().lower()
    generated_at = str(metadata.get("generated_at") or "")
    provenance = {
        "command": command,
        "generated_at": generated_at,
        "invocation_id": str(metadata.get("invocation_id") or ""),
        "dbt_version": str(metadata.get("dbt_version") or ""),
    }
    if command and command not in _TEST_BEARING_COMMANDS:
        return provenance, (
            f"the captured run_results is from a `dbt {command}` invocation, which executes no "
            f"tests — it cannot certify the test suite"
        )
    if generated_at:
        try:
            stamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            # 120s of slack: the runner's clock and this process's monotonic start are independent.
            if stamp.timestamp() < started_at - 120:
                return provenance, (
                    f"the captured run_results was generated at {generated_at}, BEFORE this dbt "
                    f"invocation started — it is a stale artifact, not this run's results"
                )
        except ValueError:
            pass  # unparseable stamp is not itself disqualifying; the command check already ran
    return provenance, ""


def capture_dbt_results(context, run_ref: dict, started_at: float, tested: bool = True) -> None:
    """Persist this dbt invocation's test results for `check_dbt_test_results_op`. Never raises.

    Written to a per-Dagster-run path rather than returned, because the pager is a SEPARATE op:
    keeping it out of `dbt_daily_build` means a bug in the pager can never touch the HALT-tier op
    that gates predictions. Ops in one Dagster run share a process (DefaultRunLauncher), so the
    file is simply handed forward.

    `tested=False` records that the invocation legitimately ran no tests — a routine cadence, not
    a gap in measurement, and reported SILENT rather than WARN (see betting_ml.monitoring.dbt_test_results).
    """
    payload: dict
    try:
        if not tested:
            payload = {"available": False, "tested": False,
                       "reason": "this dbt invocation ran no test suite"}
        else:
            results, reason = _fetch_run_results(context, run_ref)
            if results is None:
                payload = {"available": False, "tested": True, "reason": reason}
            else:
                provenance, bad = _verify_provenance(results, started_at)
                if bad:
                    payload = {"available": False, "tested": True, "reason": bad,
                               "provenance": provenance}
                else:
                    payload = {"available": True, "tested": True,
                               "provenance": provenance, "run_results": results}

        os.makedirs(DBT_RESULTS_DIR, exist_ok=True)
        with open(_results_path(context), "w") as fh:
            json.dump(payload, fh)
        if not payload.get("available"):
            context.log.info(f"[dbt test results] not captured: {payload.get('reason')}")
    except Exception as exc:  # noqa: BLE001 — capture is observability only (best_alpha=0).
        # A failure here must never affect dbt_daily_build, which is HALT-tier and gates the
        # slate. The pager then finds no file and reports UNVERIFIED — never healthy.
        context.log.warning(f"[dbt test results] capture failed ({exc}) — the pager will "
                            f"report this run's dbt tests as UNVERIFIED, not as passing")


def load_dbt_results(context) -> dict | None:
    """Read back what capture_dbt_results persisted for THIS Dagster run. None if absent."""
    path = _results_path(context)
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _local_state_aware_args(context, args: list[str], env: dict) -> list[str]:
    """Download S3 state and return source_status:fresher+ args (or full-build fallback)."""
    state_dir = "/tmp/dbt-state"
    try:
        import pathlib

        import boto3
        bucket = os.environ.get("DBT_STATE_BUCKET", "baseball-betting-ml-artifacts")
        prefix = os.environ.get("DBT_STATE_PREFIX", "dbt_state")
        target_env = os.environ.get("TARGET_ENV", "dev")
        s3 = boto3.client("s3")
        pathlib.Path(state_dir).mkdir(parents=True, exist_ok=True)
        for fname in ("manifest.json", "sources.json"):
            s3.download_file(bucket, f"{prefix}/{target_env}/{fname}", f"{state_dir}/{fname}")
        target_args: list[str] = []
        try:
            idx = args.index("--target")
            target_args = ["--target", args[idx + 1]]
        except (ValueError, IndexError):
            pass
        context.log.info("[dbt-runner] local state: source_status:fresher+ + views mode")
        # INC-13: union config.materialized:view so views are always rebuilt
        # (pure DDL, cheap) — skipping them causes cryptic "object does not
        # exist" errors when a fresh consumer references an unbuilt view.
        return ["build", "--select", "source_status:fresher+ config.materialized:view",
                "--state", state_dir] + target_args
    except Exception as exc:
        context.log.warning(f"[dbt-runner] local state download failed ({exc}) — full build")
        return args


def _local_state_upload(context, args: list[str], env: dict) -> None:
    """After a successful build, run source freshness and upload state to S3."""
    try:
        target_args: list[str] = []
        try:
            idx = args.index("--target")
            target_args = ["--target", args[idx + 1]]
        except (ValueError, IndexError):
            pass
        freshness_cmd = (
            ["dbtf", "source", "freshness", "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
            + target_args
        )
        freshness = subprocess.run(
            freshness_cmd, env=env, capture_output=True, text=True, cwd=APP_DIR
        )
        if freshness.returncode != 0:
            context.log.warning(
                f"[dbt-runner] source freshness failed (rc={freshness.returncode}) — state NOT uploaded"
            )
            return
        import pathlib

        import boto3
        bucket = os.environ.get("DBT_STATE_BUCKET", "baseball-betting-ml-artifacts")
        prefix = os.environ.get("DBT_STATE_PREFIX", "dbt_state")
        target_env = os.environ.get("TARGET_ENV", "dev")
        s3 = boto3.client("s3")
        target_dir = pathlib.Path(DBT_DIR) / "target"
        for fname in ("manifest.json", "sources.json"):
            local = target_dir / fname
            if local.exists():
                s3.upload_file(str(local), bucket, f"{prefix}/{target_env}/{fname}")
    except Exception as exc:
        context.log.warning(
            f"[dbt-runner] local state upload failed — next run will full-build. ({exc})"
        )

import os
import subprocess
import sys

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

from pipeline.jobs.sensor_jobs import pregame_snapshot_job

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"


def _parse_output(stdout: str, key: str) -> str | None:
    """Extract value from '[OUTPUT] key=value' lines written by the monitor scripts."""
    for line in stdout.splitlines():
        if line.startswith(f"[OUTPUT] {key}="):
            return line.split("=", 1)[1].strip()
    return None


@sensor(job=pregame_snapshot_job, minimum_interval_seconds=1800)
def pregame_snapshot_sensor(context: SensorEvaluationContext):
    """
    30-minute sensor: runs pregame_snapshot.py to check whether any games are
    entering the pre-game window (5-40 min before first pitch) without an
    existing odds snapshot. Emits a RunRequest if capture is needed.

    Transient subprocess failures are caught and logged as SkipReason so a
    flaky Snowflake connection doesn't cascade into a failed sensor tick.
    """
    script = os.path.join(SCRIPTS_DIR, "pregame_snapshot.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            cwd=APP_DIR,
        )
        if result.stdout:
            context.log.info(result.stdout)
        if result.stderr:
            context.log.warning(result.stderr)
        if result.returncode != 0:
            yield SkipReason(
                f"pregame_snapshot.py exited {result.returncode} — skipping tick. "
                f"stderr: {result.stderr[:400]}"
            )
            return
    except Exception as e:
        yield SkipReason(f"pregame_snapshot.py failed to run: {e}")
        return

    needs_snapshot = _parse_output(result.stdout, "needs_snapshot")

    if needs_snapshot != "true":
        yield SkipReason("No games entering pre-game window — nothing to capture.")
        return

    context.log.info("Games detected in pre-game window — triggering odds snapshot.")
    yield RunRequest(tags={"triggered_by": "pregame_snapshot_sensor"})

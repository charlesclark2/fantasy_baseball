import os
import subprocess
import sys

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

from pipeline.jobs.sensor_jobs import lineup_monitor_job

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"


def _parse_output(stdout: str, key: str) -> str | None:
    """Extract value from '[OUTPUT] key=value' lines written by the monitor scripts."""
    for line in stdout.splitlines():
        if line.startswith(f"[OUTPUT] {key}="):
            return line.split("=", 1)[1].strip()
    return None


@sensor(job=lineup_monitor_job, minimum_interval_seconds=3600)
def lineup_monitor_sensor(context: SensorEvaluationContext):
    """
    Hourly sensor: runs lineup_monitor.py to detect newly confirmed starting
    lineups. Emits a RunRequest (with game_pks in op config) when new lineups
    are found; yields SkipReason otherwise.

    Transient subprocess failures are caught and logged as SkipReason so a
    flaky Snowflake connection doesn't cascade into a failed sensor tick.
    """
    script = os.path.join(SCRIPTS_DIR, "lineup_monitor.py")
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
                f"lineup_monitor.py exited {result.returncode} — skipping tick. "
                f"stderr: {result.stderr[:400]}"
            )
            return
    except Exception as e:
        yield SkipReason(f"lineup_monitor.py failed to run: {e}")
        return

    has_new = _parse_output(result.stdout, "has_new_games")
    game_pks = _parse_output(result.stdout, "new_game_pks") or ""

    if has_new != "true":
        yield SkipReason("No newly confirmed lineups — nothing to trigger.")
        return

    context.log.info(f"New lineups confirmed for game_pks: {game_pks}")
    yield RunRequest(
        run_key=f"lineup_{game_pks}",
        run_config={
            "ops": {
                "lineup_predict": {
                    "config": {"game_pks": game_pks}
                }
            }
        },
        tags={"triggered_by": "lineup_monitor_sensor", "game_pks": game_pks},
    )

import os
import subprocess
import sys
from datetime import date, timedelta

from dagster import AssetExecutionContext, Config, asset

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"


class HistoricalMatchesCatchupConfig(Config):
    start_date: str = ""  # YYYY-MM-DD; defaults to 14 days ago
    end_date: str = ""    # YYYY-MM-DD; defaults to yesterday


@asset(compute_kind="python", group_name="parlay_api")
def parlay_historical_matches_catchup(
    context: AssetExecutionContext,
    config: HistoricalMatchesCatchupConfig,
):
    today = date.today()
    start = config.start_date or (today - timedelta(days=14)).isoformat()
    end = config.end_date or (today - timedelta(days=1)).isoformat()

    context.log.info(f"Historical matches backfill: {start} → {end}")

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "parlay_api_ingestion.py"),
            "historical-matches",
            "--start-date", start,
            "--end-date", end,
        ],
        capture_output=True,
        text=True,
        cwd=APP_DIR,
    )
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"parlay_api_ingestion.py historical-matches failed (exit {result.returncode}): "
            f"{result.stderr[:400]}"
        )

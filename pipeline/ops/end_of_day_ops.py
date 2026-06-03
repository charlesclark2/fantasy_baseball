"""End-of-day posterior update ops (Epic O.4 / Epic 16.4).

Runs after the day's games are Final and have landed in mart_game_results
(~midnight ET), but before the 12:00 UTC morning daily_ingestion_job. Advances
the sequential-Bayes chains one day so the morning pipeline's as-of lookups
(game_date < scoring_date) include yesterday's games.

Three independent posterior updates (player / team / matchup-cell) fan out from a
games-check gate — they write to different tables and have no inter-dependency.

KNOWN LIMITATION (team bullpen metric): update_team_posteriors' bullpen_xwoba
chain identifies relievers via eb_bullpen_posteriors membership, which lags the
current date by a few days. For dates where eb_bullpen is not yet populated the
team op still updates off_xwoba + win_prob; bullpen yields 0 rows and backfills
on a later run once EB catches up. See project_epic16_status memory.
"""

import os
import subprocess
import sys
from datetime import date, timedelta

from dagster import In, Nothing, Out, OpExecutionContext, op

APP_DIR = "/app"
_SEQ_DIR = f"{APP_DIR}/betting_ml/scripts/sequential_bayes"


def _run_script(context: OpExecutionContext, script: str, args: list[str] | None = None) -> None:
    path = script if os.path.isabs(script) else f"{APP_DIR}/scripts/{script}"
    cmd = [sys.executable, path] + (args or [])
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")


@op(out=Out(bool))
def check_games_yesterday(context: OpExecutionContext) -> bool:
    """Gate: count yesterday's completed regular-season games in mart_game_results.

    Returns True if any games completed. On an off-day (count = 0) the downstream
    posterior ops short-circuit, avoiding unnecessary Snowflake hits. mart_game_results
    contains only completed games, so a plain game_type='R' count is sufficient (there
    is no game_state column to filter on)."""
    import snowflake.connector
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, load_pem_private_key,
    )

    yesterday = _yesterday()
    key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    with open(key_path, "rb") as f:
        pem = f.read()
    key = load_pem_private_key(pem, password=None, backend=default_backend())
    private_key_bytes = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role=os.environ.get("SNOWFLAKE_ROLE", ""),
        database="baseball_data",
        private_key=private_key_bytes,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM baseball_data.betting.mart_game_results "
            "WHERE game_date = %s AND game_type = 'R'",
            [yesterday],
        )
        count = cur.fetchone()[0]
        cur.close()
    finally:
        conn.close()

    has_games = count > 0
    if has_games:
        context.log.info(f"Found {count} completed regular-season game(s) for {yesterday} — running posterior updates.")
    else:
        context.log.info(f"No completed regular-season games for {yesterday} (off-day) — skipping posterior updates.")
    return has_games


@op(ins={"has_games": In(bool)}, out=Out(Nothing))
def update_player_posteriors_op(context: OpExecutionContext, has_games: bool) -> None:
    """Story 16.1 — advance per-player sequential xwOBA posteriors for yesterday."""
    if not has_games:
        context.log.info("No games yesterday — skipping player posterior update.")
        return
    _run_script(context, f"{_SEQ_DIR}/update_player_posteriors.py", ["--date", _yesterday()])


@op(ins={"has_games": In(bool)}, out=Out(Nothing))
def update_team_posteriors_op(context: OpExecutionContext, has_games: bool) -> None:
    """Story 16.3 — advance team-level sequential posteriors (off_xwoba / bullpen_xwoba / win_prob).

    Bullpen metric lags eb_bullpen_posteriors (see module docstring); off_xwoba and
    win_prob always update for yesterday."""
    if not has_games:
        context.log.info("No games yesterday — skipping team posterior update.")
        return
    _run_script(context, f"{_SEQ_DIR}/update_team_posteriors.py", ["--date", _yesterday()])


@op(ins={"has_games": In(bool)}, out=Out(Nothing))
def update_matchup_cell_posteriors_op(context: OpExecutionContext, has_games: bool) -> None:
    """Epic 8.5 — advance archetype-cell sequential posteriors for yesterday."""
    if not has_games:
        context.log.info("No games yesterday — skipping matchup-cell posterior update.")
        return
    _run_script(context, f"{_SEQ_DIR}/update_matchup_cell_posteriors.py", ["--date", _yesterday()])

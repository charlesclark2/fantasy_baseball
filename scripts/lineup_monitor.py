"""
lineup_monitor.py
-----------------
Checks Snowflake for newly confirmed starting lineups and writes the result
to $GITHUB_OUTPUT so the caller (lineup_monitor.yml) can decide whether to
trigger a dbt feature rebuild.

Logic:
  1. Query stg_statsapi_lineups_wide for today's games where both home and
     away lineups are confirmed (slot_1_player_id populated for both sides).
  2. Compare against lineup_monitor_state to find games not yet triggered.
  3. Insert new entries into lineup_monitor_state (idempotent with NOT EXISTS).
  4. Write has_new_games (true/false) and new_game_pks (comma-separated) to
     $GITHUB_OUTPUT. If not running in GHA, prints to stdout instead.

Snowflake authentication — private key (preferred) or password fallback:
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH      path to PEM private key
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  (optional)
    SNOWFLAKE_ROLE                  (optional)
    SNOWFLAKE_PASSWORD              fallback when no private key is set

Usage:
    uv run lineup_monitor.py
"""

import logging
import os
from datetime import date

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

TASK = "lineup_monitor"


def _load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def get_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  "baseball_data",
    }

    key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if key_path:
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(key_path, passphrase)
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        kwargs["password"] = password

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


def write_github_output(key: str, value: str) -> None:
    gho = os.environ.get("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"[OUTPUT] {key}={value}")


def main() -> None:
    today = date.today().isoformat()
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Step 1 — find games where both home and away lineups are confirmed
        cur.execute(
            """
            SELECT game_pk
            FROM baseball_data.betting.stg_statsapi_lineups_wide
            WHERE official_date = %s::date
            GROUP BY game_pk
            HAVING COUNT(DISTINCT home_away) = 2
            """,
            [today],
        )
        confirmed = {row[0] for row in cur.fetchall()}
        log.info("Confirmed games today: %d", len(confirmed))

        # Step 2 — find which games have already been triggered today
        cur.execute(
            """
            SELECT game_pk
            FROM baseball_data.config.lineup_monitor_state
            WHERE run_date = %s::date
            """,
            [today],
        )
        already_triggered = {row[0] for row in cur.fetchall()}
        log.info("Already triggered today: %d", len(already_triggered))

        new_game_pks = sorted(confirmed - already_triggered)
        log.info("New game_pks to trigger: %s", new_game_pks)

        # Step 3 — record new entries in the state table
        for pk in new_game_pks:
            cur.execute(
                """
                INSERT INTO baseball_data.config.lineup_monitor_state
                    (run_date, game_pk, triggered_at)
                SELECT %s::date, %s::int, CURRENT_TIMESTAMP()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM baseball_data.config.lineup_monitor_state
                    WHERE run_date = %s::date AND game_pk = %s::int
                )
                """,
                [today, pk, today, pk],
            )

        # Audit log
        cur.execute(
            """
            INSERT INTO baseball_data.config.pipeline_run_log
                (task_name, run_ts, status, rows_affected)
            VALUES (%s, CURRENT_TIMESTAMP(), 'SUCCESS', %s)
            """,
            [TASK, len(new_game_pks)],
        )
        conn.commit()

        # Step 4 — write GHA outputs
        write_github_output("has_new_games", "true" if new_game_pks else "false")
        write_github_output("new_game_pks", ",".join(str(pk) for pk in new_game_pks))
        log.info("Done. has_new_games=%s", bool(new_game_pks))

    except Exception as e:
        log.error("lineup_monitor failed: %s", e)
        try:
            cur.execute(
                """
                INSERT INTO baseball_data.config.pipeline_run_log
                    (task_name, run_ts, status, rows_affected, error_message)
                VALUES (%s, CURRENT_TIMESTAMP(), 'FAILED', 0, %s)
                """,
                [TASK, str(e)[:400]],
            )
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

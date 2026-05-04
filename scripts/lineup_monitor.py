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
  3. For already-triggered games, check if the starting pitcher changed —
     if so, re-trigger so updated features and predictions are produced.
  4. Insert new entries into lineup_monitor_state (idempotent with NOT EXISTS).
     Update existing entries when a pitcher change is detected.
  5. Write has_new_games (true/false) and new_game_pks (comma-separated) to
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
        # Step 1 — confirmed games (both batting lineups posted) with current probable pitchers.
        # In the universal DH era pitchers don't appear in batting lineups, so we join
        # stg_statsapi_probable_pitchers to track starter changes separately.
        cur.execute(
            """
            SELECT
                l.game_pk,
                p_home.probable_pitcher_id AS home_starter_id,
                p_away.probable_pitcher_id AS away_starter_id
            FROM (
                SELECT game_pk
                FROM baseball_data.betting.stg_statsapi_lineups_wide
                WHERE official_date = %s::date
                GROUP BY game_pk
                HAVING COUNT(DISTINCT home_away) = 2
            ) l
            LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers p_home
                ON l.game_pk = p_home.game_pk AND p_home.side = 'home'
            LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers p_away
                ON l.game_pk = p_away.game_pk AND p_away.side = 'away'
            """,
            [today],
        )
        confirmed: dict[int, tuple[int | None, int | None]] = {
            row[0]: (row[1], row[2]) for row in cur.fetchall()
        }
        log.info("Confirmed games today: %d", len(confirmed))

        # Step 2 — games already triggered today, with stored starter IDs
        cur.execute(
            """
            SELECT game_pk, home_starter_id, away_starter_id
            FROM baseball_data.config.lineup_monitor_state
            WHERE run_date = %s::date
            """,
            [today],
        )
        already_triggered: dict[int, tuple[int | None, int | None]] = {
            row[0]: (row[1], row[2]) for row in cur.fetchall()
        }
        log.info("Already triggered today: %d", len(already_triggered))

        new_game_pks: list[int] = []
        pitcher_change_pks: list[int] = []

        for pk, (home_starter, away_starter) in confirmed.items():
            if pk not in already_triggered:
                new_game_pks.append(pk)
            else:
                stored_home, stored_away = already_triggered[pk]
                # If stored starters are NULL (pre-migration rows), skip — treat as unknown.
                # On the next run the starters will be populated and changes can be detected.
                if stored_home is None or stored_away is None:
                    continue
                if stored_home != home_starter or stored_away != away_starter:
                    log.info(
                        "Pitcher change detected for game_pk=%d: "
                        "home %s→%s, away %s→%s",
                        pk, stored_home, home_starter, stored_away, away_starter,
                    )
                    pitcher_change_pks.append(pk)

        all_trigger_pks = sorted(new_game_pks + pitcher_change_pks)
        log.info(
            "New game_pks: %s | Pitcher change pks: %s",
            new_game_pks,
            pitcher_change_pks,
        )

        # Step 3 — record new entries; update starter IDs for pitcher changes
        for pk in new_game_pks:
            home_starter, away_starter = confirmed[pk]
            # Probable pitcher may be NULL if not yet announced — store NULL rather than cast error
            home_cast = f"{home_starter}::int" if home_starter is not None else "NULL::int"
            away_cast = f"{away_starter}::int" if away_starter is not None else "NULL::int"
            cur.execute(
                f"""
                INSERT INTO baseball_data.config.lineup_monitor_state
                    (run_date, game_pk, triggered_at, home_starter_id, away_starter_id)
                SELECT %s::date, %s::int, CURRENT_TIMESTAMP(), {home_cast}, {away_cast}
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM baseball_data.config.lineup_monitor_state
                    WHERE run_date = %s::date AND game_pk = %s::int
                )
                """,
                [today, pk, today, pk],
            )

        for pk in pitcher_change_pks:
            home_starter, away_starter = confirmed[pk]
            home_cast = f"{home_starter}::int" if home_starter is not None else "NULL::int"
            away_cast = f"{away_starter}::int" if away_starter is not None else "NULL::int"
            cur.execute(
                f"""
                UPDATE baseball_data.config.lineup_monitor_state
                SET home_starter_id = {home_cast},
                    away_starter_id = {away_cast},
                    triggered_at    = CURRENT_TIMESTAMP()
                WHERE run_date = %s::date AND game_pk = %s::int
                """,
                [today, pk],
            )

        # Audit log
        cur.execute(
            """
            INSERT INTO baseball_data.config.pipeline_run_log
                (task_name, run_ts, status, rows_affected)
            VALUES (%s, CURRENT_TIMESTAMP(), 'SUCCESS', %s)
            """,
            [TASK, len(all_trigger_pks)],
        )
        conn.commit()

        # Step 4 — write GHA outputs
        write_github_output("has_new_games", "true" if all_trigger_pks else "false")
        write_github_output("new_game_pks", ",".join(str(pk) for pk in all_trigger_pks))
        log.info("Done. has_new_games=%s", bool(all_trigger_pks))

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

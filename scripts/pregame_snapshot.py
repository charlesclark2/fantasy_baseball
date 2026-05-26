"""
pregame_snapshot.py
-------------------
Checks for MLB games starting within the next 5-40 minutes that don't yet
have a pre-game odds snapshot. Writes needs_snapshot (true/false) to
$GITHUB_OUTPUT.

A pre-game snapshot is considered "captured" if there is already an
ingestion_ts in the window [commence_time - 40min, commence_time - 5min].
Games approaching that window (commence_time in [now+5min, now+40min])
without a captured snapshot are flagged.

Also prints a per-game snapshot status table for today so the pipeline
state is visible in CI logs.

Run from scripts/ directory:
    uv run pregame_snapshot.py
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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

# Pre-game snapshot window: capture at least 5 min before start, at most 40 min before.
PREGAME_MIN_MINUTES = 5
PREGAME_MAX_MINUTES = 40


def _load_private_key(path: str, passphrase: str | None = None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database": "baseball_data",
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
    gho = os.environ.get("GITHUB_OUTPUT", "")
    if gho:
        with open(gho, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"[OUTPUT] {key}={value}")


def main() -> None:
    now = datetime.now(timezone.utc)
    today_et = datetime.now(ZoneInfo("America/New_York")).date()

    # Window: games starting in the next 5-40 minutes need a pre-game snapshot
    window_start = now + timedelta(minutes=PREGAME_MIN_MINUTES)
    window_end = now + timedelta(minutes=PREGAME_MAX_MINUTES)

    conn = get_connection()
    cur = conn.cursor()

    try:
        # --- Today's full game snapshot status (for CI visibility) ---
        cur.execute(
            """
            SELECT
                e.home_team,
                e.away_team,
                e.commence_time,
                CONVERT_TIMEZONE('UTC', 'America/New_York', e.commence_time::timestamp_ntz) AS commence_time_et,
                COUNT(DISTINCT o.ingestion_ts)  AS n_snapshots,
                MIN(o.ingestion_ts)             AS first_snapshot,
                MAX(o.ingestion_ts)             AS last_snapshot,
                -- Pre-game: snapshot within [commence_time - 40min, commence_time - 5min]
                MAX(
                    CASE WHEN o.ingestion_ts BETWEEN
                        DATEADD('minute', -%s, e.commence_time) AND
                        DATEADD('minute', -%s, e.commence_time)
                    THEN 1 ELSE 0 END
                ) AS has_pregame_snapshot,
                -- Opening: first snapshot on game day (ET)
                MAX(
                    CASE WHEN CONVERT_TIMEZONE('UTC', 'America/New_York', o.ingestion_ts::timestamp_ntz)::date = %s
                    THEN 1 ELSE 0 END
                ) AS has_opening_snapshot
            FROM baseball_data.betting.stg_parlayapi_canonical_events e
            LEFT JOIN baseball_data.betting.stg_parlayapi_odds o ON o.canonical_event_id = e.canonical_event_id
            WHERE CONVERT_TIMEZONE('UTC', 'America/New_York', e.commence_time::timestamp_ntz)::date = %s
                AND e.sport_key = 'baseball_mlb'
            GROUP BY e.home_team, e.away_team, e.commence_time
            ORDER BY e.commence_time
            """,
            [PREGAME_MAX_MINUTES, PREGAME_MIN_MINUTES, today_et.isoformat(), today_et.isoformat()],
        )
        rows = cur.fetchall()

        log.info("Today's game snapshot status (%s ET):", today_et.isoformat())
        log.info(
            "  %-25s %-25s %-8s %-6s %-7s %-7s",
            "Home", "Away", "Start ET", "Snaps", "Opening", "PreGame",
        )
        log.info("  " + "-" * 85)
        for home, away, _, commence_et, n_snaps, _, _, has_pregame, has_opening in rows:
            start_str = commence_et.strftime("%H:%M") if commence_et else "?"
            log.info(
                "  %-25s %-25s %-8s %-6s %-7s %-7s",
                home[:25], away[:25], start_str, n_snaps or 0,
                "YES" if has_opening else "no",
                "YES" if has_pregame else "no",
            )

        # --- Check for games needing a pre-game snapshot RIGHT NOW ---
        cur.execute(
            """
            SELECT
                e.canonical_event_id,
                e.home_team,
                e.away_team,
                e.commence_time,
                -- Flag: does a snapshot exist in the pre-game window?
                MAX(
                    CASE WHEN o.ingestion_ts BETWEEN
                        DATEADD('minute', -%s, e.commence_time) AND
                        DATEADD('minute', -%s, e.commence_time)
                    THEN 1 ELSE 0 END
                ) AS has_pregame_snapshot
            FROM baseball_data.betting.stg_parlayapi_canonical_events e
            LEFT JOIN baseball_data.betting.stg_parlayapi_odds o ON o.canonical_event_id = e.canonical_event_id
            WHERE e.commence_time BETWEEN %s AND %s
                AND e.sport_key = 'baseball_mlb'
            GROUP BY e.canonical_event_id, e.home_team, e.away_team, e.commence_time
            HAVING has_pregame_snapshot = 0
            """,
            [PREGAME_MAX_MINUTES, PREGAME_MIN_MINUTES, window_start, window_end],
        )
        needs_snapshot_rows = cur.fetchall()
        needs_snapshot = len(needs_snapshot_rows) > 0

        if needs_snapshot:
            log.info(
                "Found %d game(s) needing pre-game snapshot (starting in %d-%d min):",
                len(needs_snapshot_rows), PREGAME_MIN_MINUTES, PREGAME_MAX_MINUTES,
            )
            for _, home, away, commence_time, _ in needs_snapshot_rows:
                mins_until = int((commence_time.replace(tzinfo=timezone.utc) - now).total_seconds() / 60)
                log.info("  %s @ %s in %d min (%s UTC)", away, home, mins_until, commence_time)
        else:
            log.info(
                "No games need pre-game snapshot in the next %d-%d minutes.",
                PREGAME_MIN_MINUTES, PREGAME_MAX_MINUTES,
            )

        write_github_output("needs_snapshot", "true" if needs_snapshot else "false")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

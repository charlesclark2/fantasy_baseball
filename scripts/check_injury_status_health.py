#!/usr/bin/env python3
"""check_injury_status_health.py — E9.48 injury / IL status guard.

WHY THIS EXISTS (E9.48, 2026-07-29 — a P1 user-facing TRUST failure)
    Player pages served a WRONG IL status for 62 of the 187 players flagged as
    currently on the Injured List. Jesús Luzardo's page read "On IL since
    2024-06-19" while he was starting for Philadelphia. The wrongness was SILENT:
    no error, no empty result, no HALT — just a boolean frozen since a missed
    clearing event, in some cases for five seasons.

    Root cause + the source fix live in
    dbt/models/staging/statsapi/stg_statsapi_player_injury_status.sql. This script is
    the RECURRENCE guard the fix ships with: the failure is only ever visible by
    asserting on the data, so the data gets asserted on, every day.

WHAT IT CHECKS (betting_ml/monitoring/injury_status_health.py holds the pure logic)
    1. FEED FRESHNESS — newest roster transaction vs the current baseball day. A gap
       means ingest_transactions stopped and every status is frozen at that date.
       ⚠️ Fires in the OFF-SEASON on purpose: the ingest's 7-day lookback only runs
       from the in-season daily job, so Nov–Feb is a genuine hole in the feed — and
       that hole is exactly what stranded Luzardo (MLB reinstates the 60-day IL en
       masse in November). Surfacing it is the point.
    2. IL PLAUSIBILITY — any player reported CURRENTLY on the IL who has appeared in
       an MLB game since their il_since. This is the bug signature stated directly;
       it reads no description text, so a Stats API rewording cannot blind it.

TIER: ALERT-loud-but-continue (E11.7). Exits 0 and WARNs by default — a stale IL badge
    must not take down the daily job. `--strict` (or INJURY_STATUS_STRICT=1) promotes a
    failure to exit 1 → HALT at the calling op.

SNOWFLAKE-FREE: reads the S3 lakehouse through the shared Delta-aware registrar
    (register_lakehouse_views), per the E11.20 phase-1.5 reader-routing rule.

USAGE
    # LAPTOP or BOX — plain run (ALERT tier, always exits 0 unless --strict)
    uv run python scripts/check_injury_status_health.py

    # BOX, as the daily op runs it
    docker compose -f services/dagster/aws/docker-compose.yml exec -T \\
        -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \\
        python scripts/check_injury_status_health.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from betting_ml.monitoring.injury_status_health import (  # noqa: E402
    MAX_FEED_LAG_DAYS,
    Check,
    classify_feed_freshness,
    classify_il_plausibility,
    summarize,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("check_injury_status_health")

# The tables this guard reads, registered as bare-name DuckDB views.
TABLES = [
    "stg_statsapi_transactions",
    "feature_pregame_injury_status",
    "mart_batter_rolling_stats",
    "mart_pitcher_rolling_stats",
]


def _duck():
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, TABLES)
    return conn


def _as_date(value) -> date | None:
    """Lakehouse date columns are ISO VARCHAR in parquet (the W8a binary-timestamp
    cure) but real dates elsewhere — coerce both, never assume (INC-23)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def run_checks(conn, asof: date, max_lag_days: int = MAX_FEED_LAG_DAYS) -> list[Check]:
    latest = conn.execute(
        "SELECT max(coalesce(effective_date, transaction_date)) FROM stg_statsapi_transactions"
    ).fetchone()[0]

    # Current IL population + how many of them have an MLB appearance after il_since.
    # is_current is the SCD-2 "no later event" flag — the exact thing that goes stale.
    current_il, implausible = conn.execute(
        """
        WITH appearances AS (
            SELECT batter_id  AS player_id, game_date::date AS game_date FROM mart_batter_rolling_stats
            UNION ALL
            SELECT pitcher_id AS player_id, game_date::date AS game_date FROM mart_pitcher_rolling_stats
        ),
        current_il AS (
            SELECT player_id, valid_from::date AS il_since
            FROM feature_pregame_injury_status
            WHERE is_current AND is_injured
        )
        SELECT
            count(*),
            count(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM appearances a
                    WHERE a.player_id = c.player_id AND a.game_date > c.il_since
                )
            )
        FROM current_il c
        """
    ).fetchone()

    return [
        classify_feed_freshness(_as_date(latest), asof, max_lag_days),
        classify_il_plausibility(int(current_il), int(implausible)),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="E9.48 injury / IL status guard (freshness + plausibility)")
    ap.add_argument(
        "--strict",
        action="store_true",
        default=os.environ.get("INJURY_STATUS_STRICT") == "1",
        help="Exit 1 on any failing check (HALT). Default from INJURY_STATUS_STRICT (=1 to enable).",
    )
    ap.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                    help="As-of baseball day. Default: the current baseball day (America/Los_Angeles).")
    ap.add_argument("--max-lag-days", type=int, default=MAX_FEED_LAG_DAYS,
                    help=f"Feed-freshness tolerance in days (default {MAX_FEED_LAG_DAYS}).")
    args = ap.parse_args()

    if args.date:
        asof = date.fromisoformat(args.date)
    else:
        # NEVER date.today() on a serving path — the box runs UTC (INC-22).
        from betting_ml.utils.game_day import current_game_date

        asof = current_game_date()

    conn = _duck()
    try:
        checks = run_checks(conn, asof, args.max_lag_days)
    finally:
        conn.close()

    for c in checks:
        log.info("  %-16s %-12s %s", c.name, c.status, c.detail)
    ok, banner = summarize(checks)

    # Machine-readable lines on STDOUT for the calling op to scrape — `logging` writes
    # to stderr, and _run_script only returns stdout.
    print(f"[METRIC] injury_status_ok={1 if ok else 0}")
    for c in checks:
        print(f"[METRIC] injury_status_{c.name}={c.status}")

    if ok:
        log.info("%s", banner)
        return 0
    if args.strict:
        log.error("[HALT] %s", banner)
        return 1
    log.warning("[ALERT] %s  (non-blocking: set INJURY_STATUS_STRICT=1 to HALT.)", banner)
    return 0


if __name__ == "__main__":
    sys.exit(main())

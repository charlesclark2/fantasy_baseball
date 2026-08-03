#!/usr/bin/env python3
"""check_milb_coverage_sla.py — E7.6: MiLB coverage report (by level/season) + freshness SLA.

WHY THIS EXISTS
----------------
The E7.1/E7.2/E7.7 MiLB ingest ops (`milb_ops.py`) are WARN-tier and degrade quietly by design —
a Stats-API hiccup or an S3 blip never fails the daily run, which is correct for research-substrate
data. But "degrades quietly" also means a genuine multi-day outage (a level's boxscore feed
silently stops matching the schedule, the FanGraphs Cloudflare solve starts failing every day, a
Savant endpoint shape change) has NOTHING watching it — the WARN log line scrolls past in a
Dagster run nobody reads. This script is that watcher: a standing coverage + freshness report,
SF-free, that a human (or a future ALERT wiring) can read to answer "is the MiLB substrate actually
current, and how complete is it, by level and season."

TWO REPORTS
-----------
1. COVERAGE — for each (season, level), what fraction of Stats-API-Final regular-season games
   have a matching `player_game_logs` row. Ground truth = E7.1's own `schedule` table (the game
   universe), so this needs no external source. AAA-Statcast coverage is reported the same way
   against `statcast_aaa` (Triple-A only — E7.2's grain).
2. FRESHNESS SLA — for each MiLB feed (game logs, AAA Statcast, FanGraphs THE BOARD, FanGraphs
   leaderboards), how many days since its newest row vs. what the feed's own ingest cadence
   promises (daily feeds: a few days; the AAA-Statcast monthly incremental: ~5 weeks).

USAGE (SF-free — pure DuckDB over the S3 lakehouse, AWS creds via the instance role / env only):
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/check_milb_coverage_sla.py
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/check_milb_coverage_sla.py --strict

Exit 0 always, UNLESS --strict AND something is DEGRADED/STALE (mirrors check_feature_block_coverage's
--strict convention). WARN-tier when wired into Dagster (E7.6 / E11.7): a failure here logs loud
and never HALTs a run — MiLB is off the MLB serving path.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"

DEFAULT_MIN_COVERAGE = 0.90

# Per-feed freshness SLA in days. Game logs / prospect feeds ingest DAILY (milb_ops.py) so a small
# floor catches a real stall; AAA-Statcast is a MONTHLY incremental by design (2 Savant requests —
# see milb_ops.py's STATCAST_AAA_INGEST_TIMEOUT_SECONDS comment) so its floor must not false-alarm
# mid-month.
FRESHNESS_SLA_DAYS = {
    "player_game_logs": 3,
    "statcast_aaa": 35,
    "the_board": 3,
    "fg_leaderboards": 3,
}


# ══════════════════════════════════════════════════════════════════════════════════════
# Pure classifiers — no DB access, fast-gate testable on synthetic input.
# ══════════════════════════════════════════════════════════════════════════════════════


def classify_coverage(rows: list[dict], min_coverage: float = DEFAULT_MIN_COVERAGE) -> tuple[str, list[str]]:
    """rows: each has season, level, final_games, logged_games, coverage_pct (0-100).

    DEGRADED if any (season, level) with final_games>0 falls below min_coverage. The row for the
    NEWEST season is expected to be incomplete mid-season by construction (games keep getting
    added to the schedule as they're played) — callers should pass rows for COMPLETED seasons
    only, or accept that the current season legitimately runs low until it ends (mirrors the
    check_feature_block_coverage newest-date exemption, at season grain here)."""
    if not rows:
        return "NO_DATA", ["no (season, level) rows with any Final scheduled games to compare"]
    degraded = [r for r in rows if r["final_games"] > 0 and r["coverage_pct"] < min_coverage * 100]
    if degraded:
        return "DEGRADED", [
            f"{r['season']} {r['level']}: {r['logged_games']}/{r['final_games']} games logged "
            f"({r['coverage_pct']:.1f}%) — below the {min_coverage:.0%} floor"
            for r in degraded
        ]
    return "OK", []


def classify_freshness(lag_days: float | None, sla_days: float) -> tuple[str, str]:
    """lag_days = days between the feed's newest row and 'now'. None = no rows to measure."""
    if lag_days is None:
        return "UNEVALUABLE", "no rows to measure freshness against"
    if lag_days > sla_days:
        return "STALE", f"{lag_days:.1f}d since the newest row (SLA: {sla_days:.0f}d)"
    return "OK", f"{lag_days:.1f}d lag (SLA: {sla_days:.0f}d)"


# ══════════════════════════════════════════════════════════════════════════════════════
# Live reads
# ══════════════════════════════════════════════════════════════════════════════════════


def _connect():
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("INSTALL delta; LOAD delta")
    conn.execute(
        "CREATE OR REPLACE SECRET baseball_s3 (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    return conn


def fetch_coverage_rows(conn, seasons: list[int]) -> list[dict]:
    season_list = ", ".join(str(s) for s in seasons)
    sql = f"""
        with sched as (
            select season, level_name, count(distinct game_pk) as final_games
            from delta_scan('{MILB}/schedule')
            where status_abstract = 'Final' and game_type = 'R' and season in ({season_list})
            group by 1, 2
        ),
        logs as (
            select season, level_name, count(distinct game_pk) as logged_games
            from delta_scan('{MILB}/player_game_logs')
            where season in ({season_list})
            group by 1, 2
        )
        select sched.season, sched.level_name as level, sched.final_games,
               coalesce(logs.logged_games, 0) as logged_games,
               round(100.0 * coalesce(logs.logged_games, 0) / nullif(sched.final_games, 0), 1)
                   as coverage_pct
        from sched
        left join logs on logs.season = sched.season and logs.level_name = sched.level_name
        order by sched.season, coverage_pct asc
    """
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def fetch_statcast_coverage_rows(conn, seasons: list[int]) -> list[dict]:
    """AAA-only (Statcast's grain), keyed the same shape as fetch_coverage_rows so both can share
    classify_coverage."""
    season_list = ", ".join(str(s) for s in seasons)
    sql = f"""
        with sched as (
            select season, count(distinct game_pk) as final_games
            from delta_scan('{MILB}/schedule')
            where status_abstract = 'Final' and game_type = 'R' and sport_id = 11
              and season in ({season_list})
            group by 1
        ),
        sc as (
            select season, count(distinct game_pk) as logged_games
            from delta_scan('{MILB}/statcast_aaa')
            where season in ({season_list})
            group by 1
        )
        select sched.season, 'Triple-A (Statcast)' as level, sched.final_games,
               coalesce(sc.logged_games, 0) as logged_games,
               round(100.0 * coalesce(sc.logged_games, 0) / nullif(sched.final_games, 0), 1)
                   as coverage_pct
        from sched
        left join sc on sc.season = sched.season
        order by sched.season
    """
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _lag_days(conn, table_uri: str, date_col: str, now: date, *, board: bool = False) -> float | None:
    if board:
        # THE BOARD's void-typed mlbam_id column breaks delta_scan — read via the Delta ACID file
        # list, the same landmine dodge player_xref.register_board uses.
        from betting_ml.scripts.milb_xref.player_xref import register_board

        register_board(conn, uri=table_uri, view="_freshness_board")
        row = conn.execute(f"select max({date_col}::date) from _freshness_board").fetchone()
    else:
        row = conn.execute(
            f"select max({date_col}::date) from delta_scan('{table_uri}')"
        ).fetchone()
    newest = row[0] if row else None
    if newest is None:
        return None
    if isinstance(newest, datetime):
        newest = newest.date()
    return (now - newest).days


def fetch_freshness(conn, now: date) -> dict[str, float | None]:
    return {
        "player_game_logs": _lag_days(conn, f"{MILB}/player_game_logs", "official_date", now),
        "statcast_aaa": _lag_days(conn, f"{MILB}/statcast_aaa", "game_date", now),
        "the_board": _lag_days(conn, f"{MILB}/the_board", "as_of_date", now, board=True),
        "fg_leaderboards": _lag_days(conn, f"{MILB}/fg_leaderboards", "as_of_date", now),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════


def _print_coverage_table(title: str, rows: list[dict]) -> None:
    print(f"\n{title}")
    print(f"{'season':>6}  {'level':<22}  {'final':>7}  {'logged':>7}  {'coverage':>9}")
    print("-" * 62)
    for r in rows:
        print(f"{r['season']:>6}  {r['level']:<22}  {r['final_games']:>7}  {r['logged_games']:>7}  "
              f"{(r['coverage_pct'] if r['coverage_pct'] is not None else 0):>8.1f}%")


def main(argv: list[str] | None = None) -> int:
    from betting_ml.utils.game_day import current_game_date

    today = current_game_date()

    p = argparse.ArgumentParser(description="E7.6 — MiLB coverage report + freshness SLA (SF-free)")
    p.add_argument("--seasons", default=f"{today.year - 1},{today.year}",
                   help="comma-separated seasons to report coverage for (default: prior + current)")
    p.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    p.add_argument("--strict", action="store_true",
                   help="exit 1 if any coverage is DEGRADED or any feed is STALE (default: report only)")
    args = p.parse_args(argv)
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]

    conn = _connect()
    problems: list[str] = []

    # ── 1. coverage by level/season ──────────────────────────────────────────────
    rows = fetch_coverage_rows(conn, seasons)
    _print_coverage_table("[coverage] player_game_logs vs schedule, by (season, level)", rows)
    cov_state, cov_msgs = classify_coverage(rows, args.min_coverage)
    print(f"\n[coverage] game-log verdict: {cov_state}")
    for m in cov_msgs:
        print(f"   • {m}")
    if cov_state == "DEGRADED":
        problems.extend(cov_msgs)

    sc_rows = fetch_statcast_coverage_rows(conn, seasons)
    _print_coverage_table("[coverage] statcast_aaa vs schedule (Triple-A), by season", sc_rows)
    sc_state, sc_msgs = classify_coverage(sc_rows, args.min_coverage)
    print(f"\n[coverage] AAA-Statcast verdict: {sc_state}")
    for m in sc_msgs:
        print(f"   • {m}")
    if sc_state == "DEGRADED":
        problems.extend(sc_msgs)

    # ── 2. freshness SLA ──────────────────────────────────────────────────────────
    print("\n[freshness] per-feed lag vs SLA")
    lags = fetch_freshness(conn, today)
    for feed, sla in FRESHNESS_SLA_DAYS.items():
        state, msg = classify_freshness(lags.get(feed), sla)
        print(f"   {feed:<18} {state:<12} {msg}")
        print(f"[METRIC] milb_freshness_lag_days.{feed}={lags.get(feed)}")
        if state == "STALE":
            problems.append(f"{feed}: {msg}")

    print(f"\n[METRIC] milb_coverage_verdict={cov_state}")
    print(f"[METRIC] milb_statcast_coverage_verdict={sc_state}")

    if problems and args.strict:
        print("\n❌ --strict: one or more coverage/freshness checks failed")
        for pr in problems:
            print(f"   • {pr}")
        return 1
    if problems:
        print(f"\n⚠️ {len(problems)} coverage/freshness issue(s) found (non-strict — reported, not "
              "failed; MiLB is WARN-tier / off the MLB serving path)")
    else:
        print("\n✅ MiLB coverage + freshness all within SLA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

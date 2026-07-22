"""catchup.py — shared catch-up frontier logic for the sequential-Bayes daily builders.

The team / player / matchup-cell posterior chains are STRICTLY SEQUENTIAL and NON-IDEMPOTENT:
`update_for_date` reads the latest `is_current` state and advances it, so a date must be
processed EXACTLY ONCE, in chronological order (re-processing double-applies; processing
out-of-order corrupts the chain).

The daily ops historically ran `--date <yesterday>` unconditionally. Two failure modes:
  1. Source not ready — if yesterday's completed-game data (stg_batter_pitches / mart_game_results)
     hadn't landed when the op ran (~12:50 UTC, and West-coast games finish ~06:00 UTC), the day
     produced 0 rows and was PERMANENTLY skipped — no catch-up (the 2026-07-22 team_sequential 7/21
     hole: 0 of 13 game_pks, so the served sequential block went NULL for that slate).
  2. Out-of-order — the NEXT day was then processed on top of the stale state, so even a later
     backfill of the hole can't repair the subsequent dates.

This helper replaces `--date yesterday` with a `--catchup` that advances the frontier forward over
every completed date that is ready, IN ORDER, and STOPS at the first not-ready date — so a hole can
never form (mode 2 is eliminated) and a transiently-late day self-heals on the next run (mode 1).

Pure `select_catchup_dates` is unit-tested; `run_catchup` does the IO wiring.
See project memory: project_inc32_recurrence_824735_spine_gap (the 7/21 sequential-null follow-up).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta


def _coerce_date(v) -> date:
    """Snowflake/DuckDB may hand back a date, a datetime, or an ISO string."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def select_catchup_dates(
    frontier: date | None, completed_dates, lookback_days: int, today: date
) -> list[date]:
    """PURE. The completed game_dates to advance the chain over, in chronological order.

    Eligible = strictly AFTER the frontier (never re-process — the chain is non-idempotent) AND
    within the [today - lookback_days, today - 1] window (never `today`: its games are in progress).
    An empty frontier (fresh table) starts at the window floor.
    """
    frontier = None if frontier is None else _coerce_date(frontier)
    floor = today - timedelta(days=lookback_days)
    lo = floor if frontier is None else max(floor, frontier + timedelta(days=1))
    hi = today - timedelta(days=1)
    return sorted({_coerce_date(d) for d in completed_dates if lo <= _coerce_date(d) <= hi})


def frontier_gap_alert(frontier: date | None, lookback_days: int, today: date, label: str) -> str:
    """An [ALERT] string when the frontier has fallen OLDER than the catch-up window — the dates
    between it and the window floor can never be auto-caught-up (a manual --backfill is required),
    else ''. Belt-and-suspenders for a multi-day outage that outran the lookback."""
    if frontier is not None and frontier < today - timedelta(days=lookback_days):
        floor = today - timedelta(days=lookback_days)
        return (
            f"[ALERT] [{label}] frontier {frontier} is OLDER than the {lookback_days}-day catch-up "
            f"window (floor {floor}) — dates before {floor} can NOT be auto-caught-up (they would be "
            f"skipped, breaking the ordered chain). Run a manual --backfill --season {today.year}."
        )
    return ""


def run_catchup_loop(dates, process_date, label: str, log=print):
    """Advance the chain over `dates` (must already be chronological). `process_date(gd)` returns
    the work count (rows/players updated) for that date. STOP at the first date that yields 0 (its
    completed games exist but the pitch/results source isn't ready yet) — advancing past it would
    process a later date out of order. Loudly ALERTs on a stop. Returns (processed, stalled_at)."""
    processed: list[date] = []
    stalled_at: date | None = None
    for gd in dates:
        work = process_date(gd)
        if not work:
            stalled_at = gd
            print(
                f"[ALERT] [{label}] STOPPED at {gd}: it has completed games but produced 0 "
                f"observations — the pitch/results source is not ready. NOT advancing past it "
                f"(strictly-ordered chain); it will retry on the next run. If this persists, the "
                f"upstream ingest for {gd} is stuck.",
                file=sys.stderr,
            )
            break
        processed.append(gd)
    return processed, stalled_at


def _default_fetch_dicts(conn, sql: str, params: dict) -> list[dict]:
    """Standard Snowflake DictCursor fetch (lowercased column names) — used when a script does not
    supply its own `_fetch_dicts`."""
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


_COMPLETED_DATES_SQL = (
    "SELECT DISTINCT game_date AS d FROM baseball_data.betting.mart_game_results "
    "WHERE game_type = 'R' AND home_team_won IS NOT NULL AND game_date >= %(since)s"
)


def run_catchup(
    *,
    label: str,
    target_table: str,
    today: date,
    lookback_days: int,
    get_connection,
    process_date,
    fetch_dicts=None,
    log=print,
) -> dict:
    """Wire the frontier + completed-dates reads (Snowflake) to the pure selection + the loop.

    - frontier = MAX(game_date) already in `target_table` this season (None if empty).
    - completed = distinct decided regular-season game_dates in mart_game_results within the window.
    - `process_date(gd) -> int` advances the chain one date (the script's update_for_date).
    """
    fetch_dicts = fetch_dicts or _default_fetch_dicts
    season = today.year
    conn = get_connection()
    try:
        fr = fetch_dicts(
            conn,
            f"SELECT MAX(game_date) AS d FROM {target_table} WHERE season = %(season)s",
            {"season": season},
        )
        frontier = _coerce_date(fr[0]["d"]) if fr and fr[0].get("d") is not None else None
        cr = fetch_dicts(
            conn, _COMPLETED_DATES_SQL,
            {"since": (today - timedelta(days=lookback_days)).isoformat()},
        )
        completed = [_coerce_date(r["d"]) for r in cr]
    finally:
        conn.close()

    log(f"[{label}] frontier={frontier}  completed_in_window={len(completed)}  today={today}")
    gap = frontier_gap_alert(frontier, lookback_days, today, label)
    if gap:
        print(gap, file=sys.stderr)

    dates = select_catchup_dates(frontier, completed, lookback_days, today)
    if not dates:
        log(f"[{label}] up to date (frontier={frontier}) — nothing to process.")
        return {"processed": [], "stalled_at": None}

    log(f"[{label}] advancing over {len(dates)} date(s) in order: {dates}")
    processed, stalled_at = run_catchup_loop(dates, process_date, label, log=log)
    log(
        f"[{label}] done — advanced {len(processed)} date(s): {processed}"
        + (f"; STALLED at {stalled_at} (retries next run)" if stalled_at else "")
    )
    return {"processed": processed, "stalled_at": stalled_at}

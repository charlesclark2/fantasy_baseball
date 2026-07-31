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
    frontier_sql=None,
    log=print,
) -> dict:
    """Wire the frontier + completed-dates reads (Snowflake) to the pure selection + the loop.

    - frontier = MAX(game_date) already in `target_table` this season (None if empty).
    - completed = distinct decided regular-season game_dates in mart_game_results within the window.
    - `process_date(gd) -> int` advances the chain one date (the script's update_for_date).

    `frontier_sql` overrides the frontier query for a table WITHOUT a `game_date` column (must
    return one column aliased `d` = the latest processed game_date, take a `%(season)s` bind). The
    matchup-cell chain is grained on `game_pk` only, so it joins game_pk → mart_game_results.game_date.
    """
    fetch_dicts = fetch_dicts or _default_fetch_dicts
    frontier_sql = frontier_sql or (
        f"SELECT MAX(game_date) AS d FROM {target_table} WHERE season = %(season)s"
    )
    season = today.year
    conn = get_connection()
    try:
        fr = fetch_dicts(conn, frontier_sql, {"season": season})
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


# ═══════════════════════════════════════════════════════════════════════════════════════
# 🚨 BACKFILL IDEMPOTENCY GUARD (2026-07-31)
#
# THE DEFECT THIS PREVENTS: `run_backfill` replays a whole season on top of whatever state
# already exists. `_load_current_seq` loads the existing posterior as the PRIOR and `_prep` only
# ensures DDL — there is no truncate and no check. So every backfill run against a POPULATED
# table applies an ENTIRE EXTRA SEASON of observations to the same chains.
#
# Measured on baseball_data.betting.team_sequential_posteriors, 2026-07-31: `win_prob` absorbs
# exactly one observation per team per game (`n_obs=1`), so `n_cumulative == games played` is an
# EXACT identity — and it was violated on all 30 teams at ratio 2.72-2.76 (KC: 110 games but
# n_cumulative 303, param_a 133 ⇒ 129 wins in 110 games, which is impossible). Three replays had
# accumulated: the original 2026-06-03 backfill (correct, on an empty table), an undetected
# re-run on 2026-06-04, and one on 2026-07-31.
#
# WHY IT WENT UNSEEN FOR TWO MONTHS: the duplicates are replays of the SAME games, so
# `posterior_mu` stays ≈ the true record — the mean looks perfect. Only the VARIANCE is wrong:
# `posterior_sigma2 ∝ 1/(a+b)`, so the served posterior is ~2.7× OVERCONFIDENT. A mean-based
# eyeball check can never catch this; only the count identity can. That is the whole lesson —
# ⭐ WHEN A REPLAY CORRUPTS ONLY THE SECOND MOMENT, ASSERT ON A COUNT, NOT ON A VALUE.
#
# The chain is NON-IDEMPOTENT by design (see the module docstring), so the only correct repair is
# delete-then-replay-once. Hence: refuse to backfill onto a populated season unless the caller
# explicitly asks for the reset.
# ═══════════════════════════════════════════════════════════════════════════════════════

def season_row_count(conn, target_table: str, season: int, fetch_dicts=None) -> int:
    """Rows already stored for `season` in `target_table` (0 when the table does not yet exist)."""
    fetch_dicts = fetch_dicts or _default_fetch_dicts
    try:
        rows = fetch_dicts(
            conn, f"SELECT COUNT(*) AS N FROM {target_table} WHERE season = %(season)s",
            {"season": season},
        )
    except Exception:
        return 0
    if not rows:
        return 0
    row = {str(k).lower(): v for k, v in rows[0].items()}
    return int(row.get("n") or 0)


def guard_or_reset_backfill(*, conn, target_table: str, season: int, reset: bool,
                            label: str, fetch_dicts=None, dry_run: bool = False,
                            log=print) -> None:
    """RAISE unless the season is empty — or, with `reset=True`, DELETE it first.

    A dry run never writes, so it is always allowed to proceed (it only reads).
    """
    n = season_row_count(conn, target_table, season, fetch_dicts)
    if n == 0:
        log(f"[{label}] {target_table} has no {season} rows — safe to backfill.")
        return
    if dry_run:
        log(f"[{label}] DRY RUN over a populated season ({n:,} rows) — no writes, proceeding. "
            f"⚠️ A REAL run would need --reset.")
        return
    if not reset:
        raise SystemExit(
            f"[{label}] REFUSING TO BACKFILL: {target_table} already holds {n:,} rows for season "
            f"{season}. These chains are NON-IDEMPOTENT — replaying a season on top of existing "
            f"state applies an ENTIRE EXTRA SEASON of observations to the same chains, which "
            f"leaves posterior_mu looking correct while inflating n_cumulative and making "
            f"posterior_sigma2 ~N× OVERCONFIDENT (measured 2.7× on 2026-07-31 before this guard "
            f"existed). Re-run with --reset to DELETE season {season} and replay it exactly once."
        )
    log(f"[{label}] --reset: DELETING {n:,} existing rows for season {season} from {target_table} "
        f"so the replay starts from a cold prior.")
    cur = conn.cursor()
    try:
        cur.execute(f"DELETE FROM {target_table} WHERE season = {int(season)}")
        conn.commit()
    finally:
        cur.close()
    log(f"[{label}] reset complete — {n:,} rows deleted.")

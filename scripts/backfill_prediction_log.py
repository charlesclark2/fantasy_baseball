#!/usr/bin/env python3
"""
backfill_prediction_log.py   (E11.24 P1 — Snowflake-free)
---------------------------------------------------------
Nightly enrichment of `actual_outcome` and `closing_market_prob` in the S3
`prediction_log` (s3://baseball-betting-ml-artifacts/baseball/lakehouse/prediction_log/).

WHAT CHANGED AT E11.24 P1
  The table left Snowflake. Six `UPDATE baseball_data.config.prediction_log ...` sweeps
  became one DuckDB-over-S3 pass that rewrites only the date partitions whose values
  actually changed. Same arithmetic, same idempotence (a value is filled only while it is
  NULL), no warehouse.

  The redundant twin of these sweeps — `predict_today._backfill_outcomes()`, which re-ran
  all six on EVERY predict invocation — is GONE. This script is now the only enrichment.

⚠️ THE `dt < today` BOUND IS LOAD-BEARING, TWICE
  1. CORRECTNESS. `closing_market_prob` is the last pre-game price. The pre-game filter
     (`ingestion_ts < commence_time`) is satisfied by a MORNING snapshot too, so enriching
     a game that has not started yet freezes a "closing" price hours before the close —
     and because enrichment only fills NULLs, that premature value STICKS. This is not
     hypothetical: it is what the removed intraday sweeps did. Game 822859 (2026-08-18)
     carried 0.605935, an ~18:00-21:00 UTC snapshot, against a true last pre-game price of
     0.592235. Restricting to dates strictly before the current baseball day means every
     row enriched here belongs to a game that has already been played.
  2. CONCURRENCY. Compaction rewrites a date partition. Today's partition is the only one
     an overlapping `predict_today` can append to, and this bound puts it out of reach.
     (Compaction additionally deletes ONLY the part keys it listed before reading, so a
     part that appears mid-flight is never collateral damage.)

⚠️ KNOWN CAVEAT, CARRIED FORWARD DELIBERATELY (E9.52 class)
  The FALLBACK closing price averages `1/decimal` across every snapshot of the event
  rather than a snapshot-ALIGNED read, so it can mix quotes taken at different times. That
  is exactly what the Snowflake version did; this is a faithful port, not an endorsement.
  `closing_market_prob` has NO live reader today (grep: nothing in dbt/, app/backend/ or
  frontend/ touches it), so fixing it is a separate, unforced decision.

Usage:
    uv run python scripts/backfill_prediction_log.py                  # default 45-day lookback
    uv run python scripts/backfill_prediction_log.py --all            # every partition
    uv run python scripts/backfill_prediction_log.py --start 2026-08-01 --end 2026-08-15
    uv run python scripts/backfill_prediction_log.py --dry-run
    uv run python scripts/backfill_prediction_log.py --recompute-clv  # see below

`--recompute-clv` RE-derives closing_market_prob even where it is already set. OFF by
default: the historical values were frozen mid-slate by the removed sweeps and are
therefore wrong, but rewriting history is the operator's call, not this script's.

AWS only — no Snowflake env. DuckDB reads S3 via `credential_chain`; the writer uses the
instance-role-safe `make_s3_client()`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.game_day import current_game_date  # noqa: E402
from scripts.utils import prediction_log_store as pred_log  # noqa: E402
from scripts.utils.lakehouse_read import register_views  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 45

_MARTS = (
    "mart_game_results",
    "feature_pregame_odds_features",
    "mart_odds_outcomes",
    "mart_game_odds_bridge",
)

# ---------------------------------------------------------------------------
# The enrichment — one query per concern, both scoped to the games that need it.
# ---------------------------------------------------------------------------

# actual_outcome. h2h = did the home team win. totals = final total vs the consensus line
# (a PUSH stays NULL, exactly as the Snowflake CASE did).
_OUTCOMES_SQL = """
SELECT
    r.game_pk,
    CASE WHEN r.home_team_won THEN 1.0 ELSE 0.0 END                       AS h2h_outcome,
    CASE
        WHEN (r.home_final_score + r.away_final_score) > f.total_line_consensus THEN 1.0
        WHEN (r.home_final_score + r.away_final_score) < f.total_line_consensus THEN 0.0
    END                                                                    AS totals_outcome
FROM mart_game_results r
JOIN _needed n ON n.game_pk = r.game_pk
LEFT JOIN feature_pregame_odds_features f
       ON f.game_pk = r.game_pk AND f.total_line_consensus IS NOT NULL
"""

# closing_market_prob. `pre` is the snapshot-aligned last PRE-GAME price; `fb` is the
# all-snapshot fallback used only where no pre-game snapshot exists (a game whose odds
# were ingested retroactively via the historical endpoint).
#   ⚠️ `commence_time` is a string-wrapped timestamp in the lakehouse parquet (the W8a
#   binary-timestamp cure), so the pre-game comparison MUST cast it — an un-cast compare
#   against a TIMESTAMP is the INC-23 binder failure, and an un-cast `=` would be the
#   silent-empty variant (E9.52).
_CLOSING_SQL = """
WITH ev AS (
    SELECT DISTINCT b.game_pk, b.event_id
    FROM mart_game_odds_bridge b
    JOIN _needed n ON n.game_pk = b.game_pk
),
o AS (
    SELECT ev.game_pk,
           moe.market_key,
           moe.ingestion_ts,
           moe.outcome_price_decimal,
           moe.commence_time::timestamp AS commence_ts
    FROM mart_odds_outcomes moe
    JOIN ev ON ev.event_id = moe.event_id
    WHERE moe.outcome_price_decimal > 0
      AND (   (moe.market_key = 'h2h'    AND moe.is_home_outcome)
           OR (moe.market_key = 'totals' AND moe.outcome_name = 'Over'))
),
last_pre AS (
    SELECT game_pk, market_key, MAX(ingestion_ts) AS last_ts
    FROM o WHERE ingestion_ts < commence_ts GROUP BY 1, 2
),
pre AS (
    SELECT o.game_pk, o.market_key, AVG(1.0 / o.outcome_price_decimal) AS p
    FROM o
    JOIN last_pre l ON l.game_pk = o.game_pk
                   AND l.market_key = o.market_key
                   AND o.ingestion_ts = l.last_ts
    GROUP BY 1, 2
),
fb AS (
    SELECT game_pk, market_key, AVG(1.0 / outcome_price_decimal) AS p
    FROM o GROUP BY 1, 2
)
SELECT COALESCE(pre.game_pk, fb.game_pk)         AS game_pk,
       COALESCE(pre.market_key, fb.market_key)   AS market,
       COALESCE(pre.p, fb.p)                     AS closing_market_prob,
       pre.p IS NOT NULL                         AS from_pregame_snapshot
FROM fb FULL JOIN pre USING (game_pk, market_key)
"""


def _connect():
    conn = pred_log.connect()          # duckdb + the prediction_log dedup view
    register_views(conn, _MARTS)
    return conn


def _candidate_dates(conn, start: date | None, end: date, recompute_clv: bool) -> list[date]:
    need = ("actual_outcome IS NULL OR closing_market_prob IS NULL"
            if not recompute_clv else "TRUE")
    sql = f"""
        SELECT DISTINCT prediction_date
        FROM prediction_log
        WHERE prediction_date < ?
          AND ({need})
        ORDER BY 1
    """
    params: list = [end]
    if start is not None:
        sql = sql.replace("WHERE prediction_date < ?",
                          "WHERE prediction_date < ? AND prediction_date >= ?")
        params.append(start)
    return [r[0] for r in conn.execute(sql, params).fetchall()]


def _needed_game_pks(conn, dates: list[date], recompute_clv: bool) -> list[int]:
    need = ("actual_outcome IS NULL OR closing_market_prob IS NULL"
            if not recompute_clv else "TRUE")
    rows = conn.execute(
        f"""SELECT DISTINCT game_pk FROM prediction_log
            WHERE prediction_date IN (SELECT * FROM _dates) AND ({need})"""
    ).fetchall() if dates else []
    return [r[0] for r in rows]


def _register_scratch(conn, dates: list[date], game_pks: list[int]) -> None:
    conn.execute("CREATE OR REPLACE TEMP TABLE _dates(prediction_date DATE)")
    if dates:
        conn.executemany("INSERT INTO _dates VALUES (?)", [(d,) for d in dates])
    conn.execute("CREATE OR REPLACE TEMP TABLE _needed(game_pk BIGINT)")
    if game_pks:
        conn.executemany("INSERT INTO _needed VALUES (?)", [(pk,) for pk in game_pks])


def _enriched_rows(conn, recompute_clv: bool) -> list[dict]:
    """The full, enriched row set for every candidate date — deduped by the view, so this
    is exactly what the compacted partitions should contain."""
    clv_expr = ("c.closing_market_prob" if recompute_clv
                else "COALESCE(pl.closing_market_prob, c.closing_market_prob)")
    sql = f"""
    WITH outcomes AS ({_OUTCOMES_SQL}),
         closing  AS ({_CLOSING_SQL})
    SELECT
        pl.prediction_date,
        pl.game_pk,
        pl.market,
        pl.model_prob,
        pl.market_prob_at_prediction,
        {clv_expr}                                          AS closing_market_prob,
        COALESCE(pl.actual_outcome,
                 CASE WHEN pl.market = 'h2h'    THEN o.h2h_outcome
                      WHEN pl.market = 'totals' THEN o.totals_outcome END) AS actual_outcome,
        pl.decimal_odds,
        pl.ev,
        pl.kelly_fraction,
        pl.model_version,
        pl.loaded_at,
        pl.closing_market_prob                              AS _prior_clv,
        pl.actual_outcome                                   AS _prior_outcome
    FROM prediction_log pl
    JOIN _dates d ON d.prediction_date = pl.prediction_date
    LEFT JOIN outcomes o ON o.game_pk = pl.game_pk
    LEFT JOIN closing  c ON c.game_pk = pl.game_pk AND c.market = pl.market
    ORDER BY pl.prediction_date, pl.game_pk, pl.market
    """
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _changed(row: dict) -> bool:
    return (row["closing_market_prob"] != row["_prior_clv"]
            or row["actual_outcome"] != row["_prior_outcome"])


def run(*, start: date | None, end: date, dry_run: bool, recompute_clv: bool) -> int:
    conn = _connect()
    dates = _candidate_dates(conn, start, end, recompute_clv)
    if not dates:
        log.info("Nothing to enrich (no partition before %s carries a NULL outcome/CLV).", end)
        return 0
    _register_scratch(conn, dates, [])
    game_pks = _needed_game_pks(conn, dates, recompute_clv)
    _register_scratch(conn, dates, game_pks)
    log.info("Enriching %d partition(s) / %d game(s) [%s .. %s], recompute_clv=%s",
             len(dates), len(game_pks), dates[0], dates[-1], recompute_clv)

    rows = _enriched_rows(conn, recompute_clv)
    by_date: dict[date, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["prediction_date"], []).append(r)

    total_changed = 0
    rewritten = 0
    for d in dates:
        part = by_date.get(d, [])
        changed = [r for r in part if _changed(r)]
        if not changed:
            continue
        total_changed += len(changed)
        n_out = sum(1 for r in changed if r["actual_outcome"] != r["_prior_outcome"])
        n_clv = sum(1 for r in changed if r["closing_market_prob"] != r["_prior_clv"])
        log.info("  %s: %d row(s) change (%d actual_outcome, %d closing_market_prob)",
                 d, len(changed), n_out, n_clv)
        if dry_run:
            continue
        # List the parts BEFORE materialising, and delete only those — a part that lands
        # mid-flight survives (the compaction is not allowed to be a truncate).
        replace_keys = pred_log.list_partition_keys(d)
        payload = [{c: r[c] for c in pred_log.COLUMNS} for r in part]
        result = pred_log.compact_partition(payload, d, replace_keys=replace_keys)
        rewritten += 1
        log.info("     → compacted %d row(s) into %s (replaced %d part file(s))",
                 result["rows"], result["key"], result["replaced_parts"])

    log.info("Backfill complete — %d row(s) enriched across %d partition(s)%s.",
             total_changed, rewritten, " [DRY RUN — nothing written]" if dry_run else "")
    return total_changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich actual_outcome / closing_market_prob in the S3 prediction_log.")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD",
                        help=f"Earliest prediction_date to consider "
                             f"(default: {DEFAULT_LOOKBACK_DAYS} days back).")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD",
                        help="Exclusive upper bound (default: the current baseball day — "
                             "see the module docstring, this bound is load-bearing).")
    parser.add_argument("--all", action="store_true",
                        help="Consider every partition, ignoring the lookback.")
    parser.add_argument("--recompute-clv", action="store_true",
                        help="Re-derive closing_market_prob even where it is already set.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change; write nothing.")
    args = parser.parse_args()

    end = date.fromisoformat(args.end) if args.end else current_game_date()
    if args.all:
        start = None
    elif args.start:
        start = date.fromisoformat(args.start)
    else:
        start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    run(start=start, end=end, dry_run=args.dry_run, recompute_clv=args.recompute_clv)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log.error("Backfill failed: %s", exc)
        sys.exit(1)

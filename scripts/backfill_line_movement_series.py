#!/usr/bin/env python
"""Backfill the E9.37 `line_movement_series` field into existing game-detail blobs.

WHY: `write_serving_store` only writes game-detail blobs for *today's* slate, so
games predicted before E9.37 shipped have no `line_movement_series` and show no
"Line Movement Over Time" chart. This patches that field into the already-cached
PERMANENT `picks/game/<pk>` blobs for the last N days — no full rebuild, no
Snowflake.

SCOPE = permanent blobs only. A past game that is Final *and* has a model
explanation is stored at the PERMANENT SK, which the backend serves first
(date-independent — see app/backend/routers/picks.py get_game_detail →
serving_cache.get_cache, which tries the permanent SK before the date row). So
patching the permanent blob surfaces immediately. Past games that are NOT
permanent (no explanation, or still pre-game) are served via the live-Snowflake
fallback and are deliberately out of scope (that path doesn't carry the field).

SNOWFLAKE-FREE: reads the Bovada intraday odds snapshots straight from the S3
lakehouse via DuckDB —
  baseball/lakehouse/mart_odds_outcomes/{_history,_current}/data.parquet
  baseball/lakehouse/mart_game_odds_bridge/data.parquet
(the same marts write_serving_store reads through Snowflake today; W7b will
repoint the live writer to this direct-S3 read too). Needs AWS creds only
(DuckDB credential_chain + boto3 for DynamoDB).

RUN (operator — writes to the prod serving cache):
    AWS_REGION=us-east-1 uv run python -m scripts.backfill_line_movement_series --days 14
    # preview first:
    AWS_REGION=us-east-1 uv run python -m scripts.backfill_line_movement_series --days 14 --dry-run
    # single game:
    AWS_REGION=us-east-1 uv run python -m scripts.backfill_line_movement_series --game-pk 824422

⚠️ `_build_line_movement_series` / `_downsample_series` are intentionally
DUPLICATED from scripts/write_serving_store.py (importing that module would pull
in pipeline.resources → a hard Snowflake-env dependency, defeating the
Snowflake-free goal). Keep the two copies in sync.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
S3_REGION = "us-east-2"  # the lakehouse bucket region (DuckDB S3 secret)

# E9.37 — cap points so the patched blob stays lean (intraday snapshots run to
# dozens of rows per market). Mirror of write_serving_store._LM_SERIES_MAX_POINTS.
_LM_SERIES_MAX_POINTS = 24
# Curated book set + display order (mirror of write_serving_store._BOOK_ORDER).
_BOOK_ORDER = ["pinnacle", "betmgm", "caesars", "fanduel", "draftkings", "fanatics", "bovada"]


# ── coercion helpers (local; mirror write_serving_store) ──────────────────────
def _flt(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _ts(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


# ── DUPLICATED from write_serving_store.py — keep in sync ─────────────────────
def _downsample_series(points: list[dict], value_key: str, cap: int = _LM_SERIES_MAX_POINTS) -> list[dict]:
    """Collapse consecutive no-change snapshots, then cap to `cap` points via even
    stride — always pinning the first (open) and last (current). Time-ordered in."""
    if not points:
        return []
    deduped = [points[0]]
    for p in points[1:]:
        if p[value_key] != deduped[-1][value_key]:
            deduped.append(p)
    if deduped[-1] is not points[-1]:
        deduped.append(points[-1])
    if len(deduped) <= cap:
        return deduped
    step = (len(deduped) - 1) / (cap - 1)
    idxs = sorted({round(i * step) for i in range(cap)})
    return [deduped[i] for i in idxs]


def _build_line_movement_series(rows: list[dict]) -> dict | None:
    """Group time-ordered odds snapshots into a compact per-book, per-market
    open→current series. Returns {"books": [...], "series": {book: {"h2h":
    [{ts,home_win_prob}], "totals": [{ts,line}]}}} or None. h2h is de-vigged.
    Input must be time-ordered ascending per (book, market)."""
    by_book: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"h2h": [], "totals": []})
    for r in rows:
        ts = _ts(r.get("SNAPSHOT_TS"))
        if ts is None:
            continue
        book = str(r.get("BOOK") or "").lower()
        if not book:
            continue
        mkt = str(r.get("MARKET_KEY") or "").lower()
        if mkt == "h2h":
            v = _flt(r.get("HOME_WIN_PROB"))
            if v is not None:
                by_book[book]["h2h"].append({"ts": ts, "home_win_prob": round(v, 4)})
        elif mkt == "totals":
            v = _flt(r.get("TOTAL_LINE"))
            if v is not None:
                by_book[book]["totals"].append({"ts": ts, "line": v})
    series: dict[str, dict] = {}
    for book, mkts in by_book.items():
        h2h_pts = _downsample_series(mkts["h2h"], "home_win_prob")
        tot_pts = _downsample_series(mkts["totals"], "line")
        if h2h_pts or tot_pts:
            series[book] = {"h2h": h2h_pts, "totals": tot_pts}
    if not series:
        return None
    books = [b for b in _BOOK_ORDER if b in series]
    books += [b for b in series if b not in books]
    return {"books": books, "series": series}


# ── DuckDB-over-S3 read (mirrors run_w1_lakehouse connection setup) ───────────
def _duckdb_conn():
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    try:
        conn.execute("INSTALL icu; LOAD icu")
    except Exception as e:  # noqa: BLE001
        print(f"  (note: ICU not loaded: {e})")
    try:
        conn.execute("SET TimeZone='UTC'")
    except Exception:  # noqa: BLE001
        pass
    conn.execute(
        f"CREATE OR REPLACE SECRET baseball_s3 (TYPE S3, PROVIDER credential_chain, REGION '{S3_REGION}')"
    )
    for pragma in (
        "SET http_timeout = 600000",
        "SET http_retries = 8",
        "SET http_retry_wait_ms = 500",
        "SET http_retry_backoff = 4",
    ):
        try:
            conn.execute(pragma)
        except Exception:  # noqa: BLE001
            pass
    return conn


_SERIES_SQL = """
WITH br AS (
    SELECT game_pk, event_id
    FROM read_parquet('{bridge}')
    WHERE event_id IS NOT NULL AND game_pk IN ({pks})
),
moo AS (
    SELECT * FROM read_parquet(['{hist}', '{curr}'], union_by_name=true)
),
snaps AS (
    SELECT
        b.game_pk,
        CASE o.bookmaker_key WHEN 'williamhill_us' THEN 'caesars' ELSE o.bookmaker_key END AS book,
        o.market_key,
        o.ingestion_ts AS snapshot_ts,
        CASE WHEN o.market_key = 'h2h' AND o.is_home_outcome THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN abs(o.outcome_price_american) / (abs(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS home_imp,
        CASE WHEN o.market_key = 'h2h' AND o.is_away_outcome THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN abs(o.outcome_price_american) / (abs(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS away_imp,
        CASE WHEN o.market_key = 'totals' THEN o.outcome_point END AS total_line
    FROM moo o
    JOIN br b ON b.event_id = o.event_id
    WHERE o.bookmaker_key IN ('pinnacle', 'betmgm', 'williamhill_us', 'fanduel', 'draftkings', 'fanatics', 'bovada')
      AND o.market_key IN ('h2h', 'totals')
      AND o.ingestion_ts < o.commence_time
),
agg AS (
    SELECT
        game_pk, book, market_key, snapshot_ts,
        max(home_imp)   AS home_imp,
        max(away_imp)   AS away_imp,
        max(total_line) AS total_line
    FROM snaps
    GROUP BY game_pk, book, market_key, snapshot_ts
)
SELECT
    game_pk     AS GAME_PK,
    book        AS BOOK,
    market_key  AS MARKET_KEY,
    snapshot_ts AS SNAPSHOT_TS,
    CASE WHEN home_imp IS NOT NULL AND away_imp IS NOT NULL AND (home_imp + away_imp) > 0
         THEN home_imp / (home_imp + away_imp) END AS HOME_WIN_PROB,
    total_line  AS TOTAL_LINE
FROM agg
WHERE (home_imp IS NOT NULL AND away_imp IS NOT NULL) OR total_line IS NOT NULL
ORDER BY game_pk, book, market_key, snapshot_ts
"""


def _fetch_series_rows(conn, game_pks: list[int]) -> list[dict]:
    if not game_pks:
        return []
    sql = _SERIES_SQL.format(
        bridge=f"{LAKEHOUSE}/mart_game_odds_bridge/data.parquet",
        hist=f"{LAKEHOUSE}/mart_odds_outcomes/_history/data.parquet",
        curr=f"{LAKEHOUSE}/mart_odds_outcomes/_current/data.parquet",
        pks=",".join(str(int(g)) for g in game_pks),
    )
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14,
                    help="Patch permanent game blobs with game_date within the last N days (default 14).")
    ap.add_argument("--game-pk", type=int, default=None,
                    help="Patch a single game_pk (ignores --days).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap the number of blobs processed (testing).")
    args = ap.parse_args()

    import app.backend.services.serving_cache as cache

    blobs = cache.list_cache_by_prefix("picks/game/")
    print(f"Found {len(blobs)} permanent game-detail blobs in {cache._TABLE_NAME}.")

    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    targets: dict[int, dict] = {}
    for payload in blobs:
        picks = payload.get("picks") or []
        if not picks:
            continue
        gp = picks[0].get("game_pk")
        gd = picks[0].get("game_date")
        if gp is None:
            continue
        gp = int(gp)
        if args.game_pk is not None:
            if gp != args.game_pk:
                continue
        elif gd is not None and str(gd)[:10] < cutoff:
            continue
        targets[gp] = payload

    if args.limit is not None:
        targets = dict(list(targets.items())[: args.limit])

    scope = f"game_pk={args.game_pk}" if args.game_pk is not None else f"last {args.days}d (>= {cutoff})"
    print(f"Scoped to {len(targets)} blobs ({scope}).")
    if not targets:
        print("Nothing to do.")
        return 0

    conn = _duckdb_conn()
    rows = _fetch_series_rows(conn, list(targets))
    by_pk: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_pk[int(r["GAME_PK"])].append(r)
    print(f"Fetched odds snapshots for {len(by_pk)} of {len(targets)} games from the S3 lakehouse.")

    patched = no_data = 0
    for gp, payload in targets.items():
        series = _build_line_movement_series(by_pk.get(gp, []))
        if series is None:
            no_data += 1
            continue
        payload["line_movement_series"] = series
        if args.dry_run:
            books = series["books"]
            print(f"  [dry] {gp}: {len(books)} books [{', '.join(books)}]")
        else:
            cache.set_cache(f"picks/game/{gp}", cache._PERMANENT, payload, is_permanent=True)
        patched += 1

    verb = "would patch" if args.dry_run else "patched"
    print(f"\nDone: {verb} {patched} blobs; {no_data} had no curated-book snapshots (left unchanged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

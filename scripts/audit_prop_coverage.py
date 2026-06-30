"""
audit_prop_coverage.py
──────────────────────
Event-id coverage audit for an S3 prop market: diffs the event-ids The Odds API
*historical events* endpoint returns for a sample of dates against the event-ids
actually present in S3 (mlb/props/market={key}/season=/date=/data.parquet).

A gap = a game the events endpoint knows about but that has NO row in S3 for the
market — i.e. an uncaptured (or leakage-skipped, or book-less) game. Run this
AFTER a backfill of a market to confirm coverage and surface dates to re-grab.

Cost: 1 credit per sampled date (events endpoint only; no odds calls). Read-only
on S3 (DuckDB credential_chain, us-east-2). No writes.

USAGE
    # audit specific dates (cheapest — explicit list)
    uv run scripts/audit_prop_coverage.py --market batter_runs_scored \
        --dates 2023-05-03,2023-05-04

    # audit an evenly-spaced sample across a market's S3 footprint
    uv run scripts/audit_prop_coverage.py --market batter_runs_scored --sample 12
"""

import argparse
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BASE   = "https://api.the-odds-api.com/v4"
SPORT  = "baseball_mlb"
BUCKET = "baseball-betting-ml-artifacts"
SNAP   = "17:00"  # the events-list snapshot the backfill uses


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain, REGION 'us-east-2');")
    return con


def s3_event_ids(con, market: str) -> dict[str, set[str]]:
    """date(str) -> set(event_id) present in S3 for this market."""
    glob = f"s3://{BUCKET}/mlb/props/market={market}/season=*/date=*/data.parquet"
    try:
        rows = con.execute(
            f"SELECT date, event_id FROM read_parquet('{glob}', hive_partitioning=true) "
            "GROUP BY 1, 2"
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        print(f"  (no S3 data for market={market}: {exc})")
        return {}
    out: dict[str, set[str]] = {}
    for d, eid in rows:
        out.setdefault(str(d), set()).add(eid)
    return out


def fetch_events(d: date, api_key: str) -> tuple[set[str], int]:
    params = {
        "apiKey": api_key,
        "date": f"{d}T{SNAP}:00Z",
        "commenceTimeFrom": f"{d}T00:00:00Z",
        "commenceTimeTo": f"{d + timedelta(days=1)}T07:00:00Z",
    }
    r = requests.get(f"{BASE}/historical/sports/{SPORT}/events", params=params, timeout=20)
    r.raise_for_status()
    rem = int(r.headers.get("x-requests-remaining", -1))
    return {e["id"] for e in r.json().get("data", [])}, rem


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market", required=True)
    p.add_argument("--dates", default=None, help="Comma-separated YYYY-MM-DD list to audit.")
    p.add_argument("--sample", type=int, default=0, help="Evenly-spaced sample size across the S3 footprint.")
    args = p.parse_args()

    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        raise SystemExit("ODDS_API_KEY not set")

    con = _con()
    s3map = s3_event_ids(con, args.market)
    s3_dates = sorted(s3map)
    print(f"market={args.market}  S3 dates={len(s3_dates)}  "
          f"({s3_dates[0] if s3_dates else '—'} → {s3_dates[-1] if s3_dates else '—'})  "
          f"total S3 event-rows={sum(len(v) for v in s3map.values())}")

    if args.dates:
        audit = [date.fromisoformat(x.strip()) for x in args.dates.split(",") if x.strip()]
    elif args.sample and s3_dates:
        step = max(1, len(s3_dates) // args.sample)
        audit = [date.fromisoformat(s3_dates[i]) for i in range(0, len(s3_dates), step)][: args.sample]
    else:
        raise SystemExit("provide --dates or --sample")

    print(f"\nAuditing {len(audit)} date(s) — 1 credit each:\n")
    total_api = total_s3 = total_gap = 0
    rem = -1
    for d in audit:
        api_ids, rem = fetch_events(d, api_key)
        s3_ids = s3map.get(str(d), set())
        gap = api_ids - s3_ids  # in API events list but missing from S3
        total_api += len(api_ids); total_s3 += len(s3_ids); total_gap += len(gap)
        flag = "✓" if not gap else f"⚠ {len(gap)} missing"
        print(f"  {d}  api={len(api_ids):2d}  s3={len(s3_ids):2d}  {flag}")
        time.sleep(1)

    print(f"\nTOTAL  api_events={total_api}  s3_events={total_s3}  "
          f"gap={total_gap} ({100*total_gap/total_api:.1f}% uncaptured)  credits_remaining={rem}")
    print("Note: a non-zero gap is expected for leakage-skipped late games (started by the "
          "17:00Z snapshot) and book-less games; a LARGE gap means re-grab those dates.")


if __name__ == "__main__":
    main()

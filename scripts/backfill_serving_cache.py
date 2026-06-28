"""INC-16-P2b — Backfill DynamoDB serving cache from S3 (fast path) or Snowflake.

After the Railway-PG → DynamoDB cutover (2026-06-27), the new table
`credence-prod-serving-cache` started empty.  This script repopulates it
with 2026 season-to-date historical entries so the app can show past picks,
game detail, and line-shopping for dates before today.

Strategy
--------
1. PROBE  — list s3://CACHE_BUCKET/api-cache/{date}/ to see which dates
            write_serving_store.py previously wrote.
2. COPY   — for each S3-covered date, read the JSON blobs and upsert them
            into DynamoDB with the correct PK/SK schema.  Fast: no Snowflake.
3. REGEN  — print the write_serving_store.py commands for dates NOT in S3
            (operator runs them; each is >1-min).

S3 → DynamoDB key mapping
--------------------------
S3 path                                  DDB pk         DDB sk
api-cache/{D}/picks/today.json           picks          today#{D}
api-cache/{D}/picks/ev.json              picks          ev#{D}
api-cache/{D}/picks/line-shopping.json   picks          line-shopping#{D}
api-cache/{D}/picks/game/{gp}.json       picks          game/{gp}#PERMANENT  ← historical final
api-cache/{D}/performance/summary.json   performance    summary#{D}
api-cache/permanent/picks/game/{gp}.json picks          game/{gp}#PERMANENT  ← already perm

Keys NOT in S3 (write_serving_store writes DynamoDB-only):
  picks/featured, picks/book-odds/{gp}, picks/line-shopping
  → regenerate from Snowflake via write_serving_store.py --date D

Safety
------
* Never writes to today's date (D < today enforced).
* Idempotent: put_item overwrites existing entries.
* --dry-run prints what would be written without touching DynamoDB.

Usage
-----
  # 1. Probe S3 coverage (no writes):
  uv run python scripts/backfill_serving_cache.py --probe

  # 2. Copy all covered S3 dates to DynamoDB (dry-run first):
  uv run python scripts/backfill_serving_cache.py --copy-s3 --dry-run
  uv run python scripts/backfill_serving_cache.py --copy-s3

  # 3. Print Snowflake-regen commands for dates NOT in S3:
  uv run python scripts/backfill_serving_cache.py --regen-missing \
      --start 2026-03-26 --end 2026-06-27

Required env vars (same as write_serving_store.py):
  CACHE_BUCKET             S3 bucket (credence-prod-s3-api-cache)
  SERVING_CACHE_TABLE      DynamoDB table (credence-prod-serving-cache)
  AWS_REGION               default us-east-1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterator

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_CACHE_BUCKET = os.environ.get("CACHE_BUCKET", "")
_SERVING_CACHE_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_PERMANENT = "PERMANENT"

# Season start: first game date with predictions in 2026.
# Run --probe first to confirm; adjust if the earliest covered S3 date differs.
_DEFAULT_SEASON_START = "2026-03-26"


# ── AWS clients ───────────────────────────────────────────────────────────────

def _s3() -> "boto3.client":
    return boto3.client("s3", region_name=_REGION)


def _ddb_table():
    return boto3.resource("dynamodb", region_name=_REGION).Table(_SERVING_CACHE_TABLE)


# ── S3 listing ────────────────────────────────────────────────────────────────

def _list_s3_objects(prefix: str) -> Iterator[str]:
    """Yield all S3 object keys under prefix (paginated)."""
    s3 = _s3()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_CACHE_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def _read_s3_json(key: str) -> dict | list | None:
    s3 = _s3()
    try:
        resp = s3.get_object(Bucket=_CACHE_BUCKET, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            log.debug("S3 miss: %s", key)
        else:
            log.warning("S3 read error for %s: %s", key, e)
        return None
    except Exception as e:
        log.warning("S3 read error for %s: %s", key, e)
        return None


# ── Key parsing ───────────────────────────────────────────────────────────────

# Regex for date-scoped blobs: api-cache/YYYY-MM-DD/...
_DATE_RE = re.compile(r"^api-cache/(\d{4}-\d{2}-\d{2})/(.+)$")
# Regex for permanent blobs: api-cache/permanent/...
_PERM_RE = re.compile(r"^api-cache/permanent/(.+)$")

# Sub-path → (namespace, rest) for DynamoDB PK/SK.
# The DDB schema: pk=namespace, sk="{rest}#{date}" or "{rest}#PERMANENT"
_SUBPATH_MAP: dict[str, tuple[str, str]] = {
    "picks/today.json":          ("picks",       "today"),
    "picks/ev.json":             ("picks",       "ev"),
    "picks/history.json":        ("picks",       "history"),
    "picks/line-shopping.json":  ("picks",       "line-shopping"),
    "performance/summary.json":  ("performance", "summary"),
}

# Regex for game-detail blobs: picks/game/{gp}.json → permanent DDB entry
_GAME_RE = re.compile(r"^picks/game/(\d+)\.json$")
# Regex for book-odds blobs: picks/book-odds/{gp}.json
_BOOK_ODDS_RE = re.compile(r"^picks/book-odds/(\d+)\.json$")


def _parse_s3_key(key: str) -> tuple[str | None, str | None, bool]:
    """Return (pk, sk, is_permanent) for a S3 key, or (None, None, False) if unrecognised.

    game-detail blobs from date-scoped paths are treated as PERMANENT because
    the router always reads them with today's date (get_cache checks PERMANENT first).
    """
    m_perm = _PERM_RE.match(key)
    if m_perm:
        subpath = m_perm.group(1)
        gm = _GAME_RE.match(subpath)
        if gm:
            return "picks", f"game/{gm.group(1)}#{_PERMANENT}", True
        # Other permanent blobs — use generic parsing
        ns, sep, rest = subpath.partition("/")
        rest_no_ext = rest.rsplit(".", 1)[0] if "." in rest else rest
        return ns, f"{rest_no_ext}#{_PERMANENT}", True

    m_date = _DATE_RE.match(key)
    if not m_date:
        return None, None, False
    date_str, subpath = m_date.group(1), m_date.group(2)

    # Known simple mappings
    if subpath in _SUBPATH_MAP:
        ns, rest_name = _SUBPATH_MAP[subpath]
        return ns, f"{rest_name}#{date_str}", False

    # Game-detail blobs from date-scoped path → treat as PERMANENT
    gm = _GAME_RE.match(subpath)
    if gm:
        gp = gm.group(1)
        return "picks", f"game/{gp}#{_PERMANENT}", True

    # Book-odds blobs: date-scoped (get_cache_latest used by router, so any date works)
    bo = _BOOK_ODDS_RE.match(subpath)
    if bo:
        gp = bo.group(1)
        return "picks", f"book-odds/{gp}#{date_str}", False

    return None, None, False


# ── DynamoDB write ────────────────────────────────────────────────────────────

def _ddb_put(tbl, pk: str, sk: str, payload: dict | list,
             is_permanent: bool, dry_run: bool) -> bool:
    """Upsert one item into DynamoDB.  Returns True on success."""
    if dry_run:
        log.info("[DRY-RUN] pk=%-15s sk=%s", pk, sk)
        return True
    try:
        tbl.put_item(Item={
            "pk": pk,
            "sk": sk,
            "value": json.dumps(payload, default=str),
            "is_permanent": is_permanent,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "cache_date": _PERMANENT if is_permanent else sk.rsplit("#", 1)[-1],
        })
        return True
    except Exception as e:
        log.warning("DDB put failed pk=%s sk=%s: %s", pk, sk, e)
        return False


# ── Date helpers ──────────────────────────────────────────────────────────────

def _date_range(start: str, end: str) -> list[str]:
    """Return ISO date strings from start to end inclusive."""
    from datetime import timedelta
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ── Probe ─────────────────────────────────────────────────────────────────────

def cmd_probe(args: argparse.Namespace) -> int:
    if not _CACHE_BUCKET:
        log.error("CACHE_BUCKET env var not set — cannot probe S3")
        return 1

    log.info("Probing S3 bucket: s3://%s/api-cache/", _CACHE_BUCKET)

    # Collect all date-scoped keys and permanent keys
    date_keys: dict[str, list[str]] = defaultdict(list)   # date → [subpaths]
    perm_keys: list[str] = []
    total_objects = 0

    for key in _list_s3_objects("api-cache/"):
        total_objects += 1
        m_perm = _PERM_RE.match(key)
        if m_perm:
            perm_keys.append(m_perm.group(1))
            continue
        m_date = _DATE_RE.match(key)
        if m_date:
            date_keys[m_date.group(1)].append(m_date.group(2))

    log.info("Total S3 objects under api-cache/: %d", total_objects)
    log.info("Permanent blobs: %d", len(perm_keys))

    today = date.today().isoformat()
    covered_dates = sorted(d for d in date_keys if d < today)
    today_date = date_keys.get(today, [])

    print(f"\n{'='*60}")
    print(f"S3 COVERAGE REPORT  (bucket: {_CACHE_BUCKET})")
    print(f"{'='*60}")
    print(f"Today ({today}): {len(today_date)} objects (not backfilled)")
    print(f"Historical dates covered: {len(covered_dates)}")
    print(f"Permanent game blobs: {len([k for k in perm_keys if k.startswith('picks/game/')])}")

    if covered_dates:
        print(f"\nEarliest covered date: {covered_dates[0]}")
        print(f"Latest covered date:   {covered_dates[-1]}")
        print("\nDate  →  object count")
        for d_str in covered_dates:
            subpaths = date_keys[d_str]
            # Summarise by type
            game_count = sum(1 for s in subpaths if s.startswith("picks/game/"))
            other = [s for s in subpaths if not s.startswith("picks/game/")]
            print(f"  {d_str}: {game_count} game blobs + {len(other)} bulk keys ({', '.join(sorted(other))})")
    else:
        print("\nNo historical dates found in S3.")
        print("→ Will need Snowflake regeneration for all dates.")

    if args.start:
        start_str = args.start
    else:
        start_str = covered_dates[0] if covered_dates else _DEFAULT_SEASON_START
    end_str = args.end or (date.fromisoformat(today) - __import__("datetime").timedelta(days=1)).isoformat()

    all_dates = set(_date_range(start_str, end_str))
    missing_dates = sorted(all_dates - set(covered_dates))

    print(f"\nDate range checked: {start_str} → {end_str}")
    print(f"Dates in range: {len(all_dates)}")
    print(f"S3-covered: {len(all_dates) - len(missing_dates)}")
    print(f"Missing (need Snowflake regen): {len(missing_dates)}")
    if missing_dates and len(missing_dates) <= 20:
        for d_str in missing_dates:
            print(f"  {d_str}")
    elif missing_dates:
        print(f"  {missing_dates[0]} … {missing_dates[-1]}")

    print(f"\n{'='*60}")
    print("NEXT STEPS")
    print(f"{'='*60}")
    if covered_dates:
        print("1. Copy S3 → DynamoDB (fast, no Snowflake):")
        print("   uv run python scripts/backfill_serving_cache.py --copy-s3 --dry-run")
        print("   uv run python scripts/backfill_serving_cache.py --copy-s3")
    if missing_dates:
        print("2. Print Snowflake-regen commands for missing dates:")
        print(f"   uv run python scripts/backfill_serving_cache.py --regen-missing"
              f" --start {start_str} --end {end_str}")
    return 0


# ── Copy S3 → DynamoDB ────────────────────────────────────────────────────────

def cmd_copy_s3(args: argparse.Namespace) -> int:
    if not _CACHE_BUCKET:
        log.error("CACHE_BUCKET env var not set")
        return 1

    dry_run = args.dry_run
    today = date.today().isoformat()

    tbl = None if dry_run else _ddb_table()

    written = 0
    skipped = 0
    errors = 0
    seen_permanent: set[str] = set()  # dedupe permanent game blobs

    log.info("Scanning s3://%s/api-cache/ … (dry_run=%s)", _CACHE_BUCKET, dry_run)

    for key in _list_s3_objects("api-cache/"):
        # Guard: skip today's date-scoped entries (preserve live data)
        m_date = _DATE_RE.match(key)
        if m_date and m_date.group(1) >= today:
            skipped += 1
            continue

        pk, sk, is_permanent = _parse_s3_key(key)
        if pk is None:
            log.debug("Unrecognised S3 key format: %s", key)
            skipped += 1
            continue

        # Deduplicate permanent game blobs: permanent/picks/game/X.json overrides
        # date-scoped api-cache/D/picks/game/X.json when both exist.
        if is_permanent:
            if sk in seen_permanent:
                skipped += 1
                continue
            seen_permanent.add(sk)

        payload = _read_s3_json(key)
        if payload is None:
            errors += 1
            continue

        ok = _ddb_put(tbl, pk, sk, payload, is_permanent, dry_run)
        if ok:
            written += 1
        else:
            errors += 1

        if (written + errors) % 100 == 0:
            log.info("Progress: %d written, %d errors, %d skipped",
                     written, errors, skipped)

    log.info("Done. written=%d  errors=%d  skipped=%d", written, errors, skipped)
    if dry_run:
        log.info("DRY-RUN — no DynamoDB writes performed. Re-run without --dry-run to apply.")
    return 0 if errors == 0 else 1


# ── Regen missing dates (Snowflake) ──────────────────────────────────────────

def cmd_regen_missing(args: argparse.Namespace) -> int:
    """Print write_serving_store.py commands for dates not covered by S3.

    The operator runs these; each takes >1 minute (Snowflake queries).
    """
    today = date.today().isoformat()
    start_str = args.start or _DEFAULT_SEASON_START
    end_str = args.end or (
        date.fromisoformat(today) - __import__("datetime").timedelta(days=1)
    ).isoformat()

    if not _CACHE_BUCKET:
        log.warning("CACHE_BUCKET not set — treating all dates as missing")
        covered_dates: set[str] = set()
    else:
        log.info("Collecting S3-covered dates …")
        covered_dates = set()
        for key in _list_s3_objects("api-cache/"):
            m = _DATE_RE.match(key)
            if m and m.group(1) < today:
                covered_dates.add(m.group(1))
        log.info("S3-covered dates: %d", len(covered_dates))

    all_dates = set(_date_range(start_str, end_str))
    missing = sorted(all_dates - covered_dates)

    if not missing:
        log.info("No missing dates — S3 covers the full range.")
        return 0

    log.info("Missing dates (not in S3): %d", len(missing))
    print("\n# ── Snowflake regeneration commands ─────────────────────────────────────────")
    print(f"# {len(missing)} dates missing from S3; run each to rebuild DynamoDB for that date.")
    print("# Each takes ~2–5 minutes (Snowflake queries). Run in parallel if desired.")
    print("# WARNING: these write to the LIVE DynamoDB table.")
    print("# Set these env vars before running:")
    print("#   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE,")
    print("#   SNOWFLAKE_PRIVATE_KEY_PATH (or SNOWFLAKE_PRIVATE_KEY),")
    print("#   SERVING_CACHE_TABLE, CACHE_BUCKET, AWS_REGION")
    print()
    for d_str in missing:
        if d_str >= today:
            continue  # safety: never regenerate today or future
        print(
            f"uv run python scripts/write_serving_store.py"
            f" --picks --game-detail --performance --book-odds"
            f" --date {d_str}"
        )
    print()
    print(f"# Total: {len(missing)} commands")
    return 0


# ── Single-date verify ────────────────────────────────────────────────────────

def cmd_spot_check(args: argparse.Namespace) -> int:
    """Spot-check DynamoDB entries for one or more past dates.

    For each date, queries DDB for picks/today#{date} and prints the
    game count. Helps verify the backfill worked.
    """
    dates = args.dates or []
    if not dates:
        log.error("Provide one or more dates via --dates YYYY-MM-DD [YYYY-MM-DD ...]")
        return 1

    tbl = _ddb_table()
    for d_str in dates:
        sk = f"today#{d_str}"
        try:
            resp = tbl.get_item(Key={"pk": "picks", "sk": sk})
            item = resp.get("Item")
            if not item:
                print(f"{d_str}: MISSING from DynamoDB (picks/today#{d_str})")
                continue
            val = json.loads(item.get("value", "{}"))
            n = len(val.get("picks") or [])
            print(f"{d_str}: picks/today found — {n} picks")
        except Exception as e:
            print(f"{d_str}: ERROR — {e}")
    return 0


# ── Arg parsing ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="INC-16-P2b: backfill DynamoDB serving cache from S3 or Snowflake.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    # --probe
    p = sub.add_parser("probe", help="Inventory S3 coverage and report which dates are missing.")
    p.add_argument("--start", help="Season start date (default: 2026-03-26)")
    p.add_argument("--end", help="End date (default: yesterday)")

    # --copy-s3
    c = sub.add_parser("copy-s3", help="Copy S3 blobs → DynamoDB for all historical dates.")
    c.add_argument("--dry-run", action="store_true",
                   help="Print what would be written without touching DynamoDB.")

    # --regen-missing
    r = sub.add_parser("regen-missing",
                        help="Print write_serving_store.py commands for S3-missing dates.")
    r.add_argument("--start", help="Season start (default: 2026-03-26)")
    r.add_argument("--end", help="End date (default: yesterday)")

    # --spot-check
    s = sub.add_parser("spot-check",
                        help="Verify DynamoDB entries exist for given dates.")
    s.add_argument("dates", nargs="+", metavar="YYYY-MM-DD")

    # Legacy positional flags for backward compat (--probe / --copy-s3 / etc.)
    parser.add_argument("--probe", action="store_true", help="(alias) same as subcommand probe")
    parser.add_argument("--copy-s3", action="store_true", help="(alias) same as subcommand copy-s3")
    parser.add_argument("--dry-run", action="store_true", help="(with --copy-s3) dry run")
    parser.add_argument("--regen-missing", action="store_true",
                        help="(alias) same as subcommand regen-missing")
    parser.add_argument("--start", help="Season start date")
    parser.add_argument("--end", help="End date")
    parser.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD",
                        help="(with --spot-check) dates to verify")
    parser.add_argument("--spot-check", action="store_true",
                        help="(alias) same as subcommand spot-check")

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # Resolve sub-command vs legacy flags
    cmd = args.cmd
    if cmd is None:
        if args.probe:
            cmd = "probe"
        elif getattr(args, "copy_s3", False):
            cmd = "copy-s3"
        elif getattr(args, "regen_missing", False):
            cmd = "regen-missing"
        elif getattr(args, "spot_check", False):
            cmd = "spot-check"

    if cmd == "probe":
        return cmd_probe(args)
    elif cmd == "copy-s3":
        return cmd_copy_s3(args)
    elif cmd == "regen-missing":
        return cmd_regen_missing(args)
    elif cmd == "spot-check":
        return cmd_spot_check(args)
    else:
        log.error(
            "Specify a command: probe | copy-s3 | regen-missing | spot-check\n"
            "  uv run python scripts/backfill_serving_cache.py probe\n"
            "  uv run python scripts/backfill_serving_cache.py copy-s3 [--dry-run]\n"
            "  uv run python scripts/backfill_serving_cache.py regen-missing [--start YYYY-MM-DD --end YYYY-MM-DD]\n"
            "  uv run python scripts/backfill_serving_cache.py spot-check YYYY-MM-DD [...]"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""write_ncaaf_serving_store.py — NCAAF-P3.1: the lake → serving-store write for college football.

WHAT IT DOES
------------
Reads the two NCAAF-PS lake tables — `ncaaf/derived/game_prediction_snapshots` (the pre-kickoff
per-game predictive) and `ncaaf/derived/futures_board_snapshots` (the P1.5 season simulation) —
takes the LATEST vintage of each, and writes the blobs the app reads:

    ncaaf/manifest              → which LA game-days have a slate, and the current one
    ncaaf/slate/{YYYY-MM-DD}    → every FBS projection kicking off on that LA day
    ncaaf/game/{game_id}        → one game's full projection
    ncaaf/futures/board         → the P1.5 futures board

to **DynamoDB (primary) + S3 (fallback)** — the same two stores, and the same read order, the MLB
serving path already uses, under a key namespace nothing else writes.

⭐ IT RE-DERIVES NOTHING. Every probability, μ, σ and quantile is copied verbatim off the persisted
snapshot row: the served model is exactly the registered artifact. No re-scoring, no correction, no
week-conditional branch. The VAL3b cold-start correction is CERTIFIED but DEPLOY-HELD and is not
expressible in the served contract — expressing any part of it here would serve a model nobody
deployed (that is NCAAF-VAL3c, post-opener).

🛣️ OFF THE MLB SERVING LANE, BY KEY — NOT BY A SECOND STORE
------------------------------------------------------------
`serving_cache` derives the DynamoDB partition key from the cache key up to the first "/", so
`ncaaf/…` IS a partition no MLB read can reach and no MLB write can touch; S3 uses its own
`ncaaf-cache/` prefix rather than the MLB lane's `api-cache/`. Reusing the same TABLE and BUCKET is
deliberate: the box role and the API Lambda role already hold table-wide DynamoDB RW and
bucket-wide S3 Get/Put on exactly these two resources, so this story needs NO new IAM grant — and
an un-granted first write is a failure that only shows up live (E8.5).

🕐 LA GAME-DAY, NEVER UTC (INC-22)
-----------------------------------
The box runs UTC. A UTC "today" rolls over at 00:00 UTC — which is Saturday EVENING in the US, i.e.
the middle of a college slate. Both the manifest's `current_game_day` and every per-game day come
from `betting_ml.utils.game_day.current_game_date`, the latter applied to the KICKOFF INSTANT so a
03:30-UTC Sunday kickoff is filed under Saturday where it belongs.

⛔ NOTHING KEYS ON A WEEK. CFBD restarts `week` at 1 for the postseason and
`game_prediction_snapshot.py`'s `season_order_week` is a verbatim alias of that raw week (the
recorded alias landmine). The serving grain is the kickoff DAY; `cfbd_week` rides along as a display
label only.

🚦 TIERS (the E11.7 failure contract)
--------------------------------------
  * the PREDICTIONS write (manifest + slates + per-game) = **HALT**. It is the serving-critical
    path: if it fails, the app has no board and the run must go red where an operator sees it.
  * the MARKET-LINE join = **WARN**. It is enrichment beside the model line; a market read that
    fails must never cost the slate. The failure is not swallowed into a blank, though — the served
    `market.status`/`market.reason` says WHICH null this is (`market_read_failed` vs
    `no_line_captured_for_this_kickoff`), because a null that means several things costs an
    investigation every time (NF-C6b).
  * the FUTURES write = **ALERT-loud-but-continue**. A bonus board; a season-simulation read must
    never turn the predictions write red. Same tiering NCAAF-PS already gives its futures fan-out.

⚠️ "NOTHING TO WRITE" IS A NO-OP, NOT A SUCCESS AND NOT A FAILURE. An empty snapshot table before
the opener is a genuine no-op (`status="no_snapshots"`); a lake we could not READ raises
(`query_or_missing`). The two must never look the same — a write that "succeeded" over a frozen or
unreadable input is the 19-green-runs class (NF-FRESH1).

USAGE
-----
    # what WOULD be written, computed in full, written nowhere (the safe pre-flight)
    uv run python scripts/write_ncaaf_serving_store.py --dry-run

    # the real write (this is what the Dagster op runs)
    uv run python scripts/write_ncaaf_serving_store.py

    # write the blobs to local JSON files too, for eyeballing / a verification diff
    uv run python scripts/write_ncaaf_serving_store.py --dry-run --out-dir /tmp/ncaaf_serving
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.backend.models import ncaaf as contract  # noqa: E402
from betting_ml.utils.game_day import current_game_date_iso  # noqa: E402  (INC-22)
from quant_sports_intel_models.football.ncaaf.serving import payloads  # noqa: E402

try:
    from pipeline.utils.alerting import send_alert as _send_alert
except Exception:  # noqa: BLE001 — alerting is non-essential to the write; never crash on it
    def _send_alert(*args, **kwargs):  # type: ignore[misc]
        return False

log = logging.getLogger("ncaaf.serving_write")

#: The DynamoDB table + S3 bucket the MLB serving path already uses. Same resources, disjoint keys.
SERVING_CACHE_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
CACHE_BUCKET_ENV = "CACHE_BUCKET"

#: DynamoDB's per-item ceiling. A slate blob for a big Saturday is the only thing that could
#: approach it, and an oversized item is REPORTED rather than silently dropped (the S3 fallback
#: still serves the key, but a reader must be able to see that DynamoDB is not carrying it).
DYNAMO_ITEM_LIMIT_BYTES = 400_000

#: The sort key permanent rows live at in `serving_cache`. Every NCAAF key already carries its own
#: date/identity, so nothing here is date-scoped at the STORE level — which removes a whole class of
#: read-time date-mismatch bug from the Lambda (it can look a key up without guessing a date).
_PERMANENT_SK = "PERMANENT"


# ══════════════════════════════════════════════════════════════════════════════════════════
# Store handles
# ══════════════════════════════════════════════════════════════════════════════════════════

def _dynamo_table():
    """The boto3 DynamoDB Table, or None (⇒ S3-only, degraded but servable).

    ⛔ No explicit `aws_access_key_id=os.environ.get(...)`: on the EC2 box those vars are UNSET,
    and passing `None` DISABLES boto3's default credential chain outright
    (`AuthorizationHeaderMalformed`). The instance role must be allowed to resolve itself.
    """
    try:
        import boto3
        return boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")).Table(
            SERVING_CACHE_TABLE)
    except Exception as exc:  # noqa: BLE001
        log.warning("[ALERT] DynamoDB init failed — NCAAF serving writes will be S3-only: %s", exc)
        _send_alert(
            "NCAAF serving write — DynamoDB unavailable (S3-only)",
            f"boto3 DynamoDB Table init raised: {exc}\nTable: {SERVING_CACHE_TABLE}\n"
            "NCAAF serving reads fall back to S3 until resolved.",
            severity="ERROR", dedup_key="ncaaf-dynamodb-connect-failed")
        return None


def _s3_client():
    import boto3
    # us-east-1: the api-cache bucket's region. Pinned PER RESOURCE, never inherited from a global
    # AWS_DEFAULT_REGION (which on the box is us-east-2 for the DuckDB lakehouse) — INC-45.
    return boto3.client("s3", region_name="us-east-1")


def _put_dynamo(table, cache_key: str, payload: dict) -> bool:
    """Upsert one permanent serving-cache item. Non-raising: the S3 write keeps the key servable."""
    if table is None:
        return False
    ns, _, rest = cache_key.partition("/")
    body = json.dumps(payload, default=str)
    if len(body.encode()) > DYNAMO_ITEM_LIMIT_BYTES:
        log.warning("[ALERT] %s is %d bytes (> the %d DynamoDB item limit) — S3 fallback carries "
                    "it, DynamoDB does not.", cache_key, len(body.encode()), DYNAMO_ITEM_LIMIT_BYTES)
        return False
    try:
        table.put_item(Item={
            "pk": ns, "sk": f"{rest or '_'}#{_PERMANENT_SK}", "value": body,
            "is_permanent": True, "updated_at": datetime.now(timezone.utc).isoformat(),
            "cache_date": _PERMANENT_SK,
        })
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("[ALERT] DynamoDB put failed for %s (S3 fallback covers): %s", cache_key, exc)
        return False


def _put_s3(client, bucket: str, key: str, payload: dict) -> bool:
    try:
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(payload, default=str),
                          ContentType="application/json")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("[ALERT] S3 put failed for s3://%s/%s: %s", bucket, key, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════════════════
# Lake reads
# ══════════════════════════════════════════════════════════════════════════════════════════

#: What delta-kernel says when a Delta table location holds no committed `_delta_log` — i.e. the
#: table has never been written. MEASURED on duckdb 1.5.3 against both a never-written NCAAF-PS
#: table and a random non-existent prefix; `query_lake.MISSING_TABLE_MARKERS`
#: ("InvalidTableLocationError", "Path does not exist") does NOT contain it on this version.
_EMPTY_LOG_SEGMENT_MARKER = "No files in log segment"


def read_snapshots(season: int, source: str, *, local_root: str | None = None):
    """The season's snapshot rows, or None iff the table genuinely has nothing to read yet.

    Delegates to NCAAF-PS's own reader, so "absent partition" vs "transient read failure" is decided
    in ONE place and a transient failure RAISES rather than being guessed as empty.

    ⭐ ONE CASE IS HANDLED HERE AND DELIBERATELY NOT PUSHED INTO THE SHARED HELPER, because the
    right answer differs by CALLER and that asymmetry is the whole point:

      * `query_lake.MISSING_TABLE_MARKERS` is deliberately narrow. Its consumers are READ-MERGE-WRITE
        writers (`odds_recurring_capture`, `game_prediction_snapshot.write_snapshot`) that PRESERVE
        what is already in the lake by reading it first — so for them, mistaking a transient blip for
        "nothing there" silently DELETES every prior week. A read-after-write visibility blip on a
        just-written `_delta_log` could plausibly surface as an empty log segment, which is exactly
        the CI flake that hardened that helper. Widening the shared list would re-open it for every
        caller (MH2.7: changing a shared instrument reaches further than the story that touches it).
      * THIS caller is an idempotent PUBLISH. It writes only to the serving store and never merges
        into a lake partition, so the worst case of treating an unreadable snapshot table as "nothing
        to publish" is a serving store that stays one cycle stale — never data loss. And the
        alternative is worse in a way that matters before the opener: a `sports_ncaaf_serving_write_job`
        fired before the FIRST snapshot exists would go RED with "lake read failed 3x" rather than
        logging the clean no-op the operator should see.

    ⚠️ RECORDED FOR THE OPERATOR, because it is NOT this story's to fix and it bites earlier:
    `game_prediction_snapshot.write_snapshot` reads the table back before its FIRST-EVER write, so on
    a duckdb whose delta-kernel raises this message the very first NCAAF-PS snapshot run cannot
    bootstrap its own table. Measured on duckdb 1.5.3 with both NCAAF-PS tables absent from S3.
    """
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    try:
        return gps.read_existing_snapshots(season, source, local_root=local_root)
    except Exception as exc:  # noqa: BLE001 — narrowed immediately below; anything else re-raises
        if _EMPTY_LOG_SEGMENT_MARKER not in str(exc) and not query_lake.is_missing_table_error(exc):
            raise
        log.info("the `%s` Delta table has no committed log yet — treating it as EMPTY, not as a "
                 "read failure. This is a publish, not a merge: nothing in the lake can be lost by "
                 "the choice. (%s)", source, str(exc).splitlines()[0][:160])
        return None


def read_market_lines(season: int) -> tuple[dict[int, dict], bool]:
    """`{game_id: close-line row}` for `season`, plus a `read_failed` flag. WARN tier: never raises.

    ⭐ Delegates to P1.4's OWN `build_clv_staging` rather than re-implementing the odds→game join.
    That join is subtle (Odds-API team names ⋈ CFBD names by prefix, season + kickoff proximity) and
    a second copy of it would be a second rule set free to drift from the one the model was
    validated against (E9.61). It is already leakage-safe by construction — only snapshots with
    `_snapshot_ts < commence_time` are eligible, and the LATEST such snapshot per event wins, which
    is the P0.6c-correct read now that close and T-1 rows coexist per kickoff.

    ⚠️ EXPECT THIS TO BE EMPTY FOR AN UPCOMING SLATE, and that is not a defect: the paid
    `/historical` capture can only reach a kickoff once that kickoff is past its snapshot instant,
    so a board written days ahead has no line to show yet. The served `market.reason` says so.
    """
    try:
        from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game import (
            build_clv_staging,
        )
        clv = build_clv_staging(min_year=int(season))
        if clv is None or clv.empty:
            return {}, False
        return {int(r["game_id"]): r for r in clv.to_dict("records")}, False
    except Exception as exc:  # noqa: BLE001 — WARN tier: enrichment must never cost the slate
        log.warning("[ALERT] NCAAF market-line read FAILED (the slate is unaffected; every game's "
                    "market block is served status=unavailable reason=market_read_failed): %s", exc)
        return {}, True


# ══════════════════════════════════════════════════════════════════════════════════════════
# The write
# ══════════════════════════════════════════════════════════════════════════════════════════

def write_serving_store(season: int, *, dry_run: bool = False, local_root: str | None = None,
                        with_market: bool = True, with_futures: bool = True,
                        out_dir: str | None = None, now: datetime | None = None) -> dict:
    """Build + write every NCAAF serving blob. Returns a manifest dict (what the Dagster op logs)."""
    current_day = current_game_date_iso()  # INC-22 — LA, never UTC
    result: dict = {"season": int(season), "current_game_day": current_day, "dry_run": bool(dry_run)}

    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    raw = read_snapshots(season, gps.SNAPSHOT_SOURCE, local_root=local_root)
    if raw is None or raw.empty:
        # A genuine no-op (pre-opener / nothing snapshotted yet) — NOT a failure, and NOT a success
        # that overwrote anything. Distinguishable from an unreadable lake, which raised above.
        result.update(status="no_snapshots", n_games=0, n_game_days=0, keys_written=0)
        return result

    latest = payloads.latest_snapshot_per_key(raw, ("game_id",))

    market_by_game, market_failed = ({}, False)
    if with_market:
        market_by_game, market_failed = read_market_lines(season)

    slates = payloads.build_slate_payloads(
        latest, season=season, now=now, market_by_game=market_by_game,
        market_read_failed=market_failed)

    futures_payload = None
    if with_futures:
        try:
            f_raw = read_snapshots(season, gps.FUTURES_SNAPSHOT_SOURCE, local_root=local_root)
            if f_raw is not None and not f_raw.empty:
                f_latest = payloads.latest_snapshot_per_key(f_raw, ("team_id",))
                futures_payload = payloads.build_futures_payload(f_latest, season=season, now=now)
        except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (the bonus board)
            log.warning("[ALERT] NCAAF futures board unavailable for season=%s: %s — the per-game "
                        "slates are unaffected and were written.", season, exc)

    any_game = next(iter(next(iter(slates.values()))["games"]), None) if slates else None
    manifest = payloads.build_manifest_payload(
        slates, season=season, current_game_day=current_day,
        futures_available=futures_payload is not None,
        provenance=(any_game or {}).get("provenance"), now=now)

    blobs: list[tuple[str, str, dict]] = [
        (contract.MANIFEST_CACHE_KEY, contract.MANIFEST_S3_KEY, manifest)]
    for game_day, slate in sorted(slates.items()):
        blobs.append((contract.slate_cache_key(game_day), contract.slate_s3_key(game_day), slate))
        for game in slate["games"]:
            gid = game["game_id"]
            blobs.append((contract.game_cache_key(gid), contract.game_s3_key(gid), game))
    if futures_payload is not None:
        blobs.append((contract.FUTURES_CACHE_KEY, contract.FUTURES_S3_KEY, futures_payload))

    # The honest-framing gate, applied to the ACTUAL bytes about to be written — not to the model
    # defaults that produced them. A writer that assembled a framing block from lake values could
    # otherwise carry a non-zero through, and the stamp is a fact about the program, not a row value.
    for cache_key, _s3_key, payload in blobs:
        contract.assert_best_alpha_is_zero(payload)

    if out_dir:
        base = Path(out_dir)
        for _ck, s3_key, payload in blobs:
            dest = base / s3_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(payload, indent=2, default=str))
        log.info("wrote %d blob(s) to %s (local inspection copy)", len(blobs), base)

    n_dynamo = n_s3 = 0
    if not dry_run:
        table = _dynamo_table()
        bucket = os.environ.get(CACHE_BUCKET_ENV)
        s3 = _s3_client() if bucket else None
        if not bucket:
            log.warning("[ALERT] %s is unset — NCAAF serving blobs go to DynamoDB only, with no S3 "
                        "fallback behind them.", CACHE_BUCKET_ENV)
        for cache_key, s3_key, payload in blobs:
            n_dynamo += int(_put_dynamo(table, cache_key, payload))
            if s3 is not None:
                n_s3 += int(_put_s3(s3, bucket, s3_key, payload))
        if n_dynamo == 0 and n_s3 == 0:
            # HALT tier: nothing reached either store, so the app has no board. Loud + red.
            raise RuntimeError(
                f"NCAAF serving write reached NEITHER store for season {season} "
                f"({len(blobs)} blob(s) built). DynamoDB table={SERVING_CACHE_TABLE}, "
                f"{CACHE_BUCKET_ENV}={bucket!r}. The app has no NCAAF board until this is fixed.")

    result.update(
        status="ok",
        n_games=sum(int(s["n_games"]) for s in slates.values()),
        n_game_days=len(slates),
        game_days=sorted(slates),
        n_blobs=len(blobs),
        dynamo_writes=n_dynamo,
        s3_writes=n_s3,
        futures_teams=(futures_payload or {}).get("n_teams", 0),
        market_lines_attached=sum(
            1 for s in slates.values() for g in s["games"] if g["market"]["status"] == "available"),
        market_read_failed=bool(market_failed),
        model_version=(any_game or {}).get("provenance", {}).get("model_version"),
        snapshot_ts=(any_game or {}).get("provenance", {}).get("snapshot_ts"),
    )
    return result


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="NCAAF-P3.1 lake → serving-store write")
    p.add_argument("--season", type=int, default=None,
                   help="default: the clock-derived current_season() — never pin a season")
    p.add_argument("--dry-run", action="store_true", help="build everything, write nothing")
    p.add_argument("--local-root", default=None, help="read the lake from a local Delta root")
    p.add_argument("--no-market", action="store_true", help="skip the market-line enrichment join")
    p.add_argument("--no-futures", action="store_true", help="skip the P1.5 futures board")
    p.add_argument("--out-dir", default=None, help="also write each blob to a local JSON file")
    args = p.parse_args(argv)

    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    season = args.season or current_season()

    manifest = write_serving_store(
        season, dry_run=args.dry_run, local_root=args.local_root,
        with_market=not args.no_market, with_futures=not args.no_futures, out_dir=args.out_dir)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

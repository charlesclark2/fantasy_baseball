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

def read_snapshots(season: int, source: str, *, local_root: str | None = None):
    """The season's snapshot rows, or None iff the table genuinely has nothing to read yet.

    Delegates to NCAAF-PS's own reader, so "absent table" vs "transient read failure" is decided in
    ONE place: `query_lake.query_or_missing` establishes absence by LISTING the store's
    `_delta_log/`, and RAISES on anything it cannot prove absent.

    🩹 NCAAF-LAKE1 (2026-08-24) REMOVED a local branch that used to live here. P3.1 shipped with its
    own message match for "No files in log segment", scoped to this publish path because an
    idempotent publish cannot lose lake data by treating an unreadable table as empty. The shared
    helper now handles that case correctly for every caller, so the local branch became a SECOND
    rule for one question — and a dead fallback that message-matches is the same bomb on a longer
    fuse. Its two guards were RE-ANCHORED onto the shared helper rather than deleted (MH2.7): the
    properties they pinned (an absent table reads empty; a genuine failure still raises) are now
    proven where they are actually implemented.
    """
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps
    return gps.read_existing_snapshots(season, source, local_root=local_root)


# ══════════════════════════════════════════════════════════════════════════════════════════
# The re-serve tier (NCAAF-ODDS-LIVE followUp ⑦ — operator chose option (b), 2026-08-29)
# ══════════════════════════════════════════════════════════════════════════════════════════

#: The America/Los_Angeles hour the BASELINE re-serve fires at. This is the schedule that has
#: always run — daily 06:00 PT, before the earliest ~09:00 PT kickoff window — and it is preserved
#: EXACTLY, so this whole tier is MONOTONE: every write that happened before still happens, and
#: the dense tier only ADDS refreshes. A cadence change that can only add work is a change whose
#: worst case is "no better than today", which is the only reason it is safe to make in-season.
SERVING_BASELINE_HOUR_LOCAL = 6

#: The timezone `SERVING_BASELINE_HOUR_LOCAL` is expressed in — the same US baseball/football day
#: the whole serving path is keyed on (INC-22).
SERVING_TZ = "America/Los_Angeles"


def upcoming_kickoffs(season: int, *, now: datetime | None = None,
                      local_root: str | None = None) -> list[datetime]:
    """Kickoff instants, for games WE SERVE, that have not happened yet.

    ⛔ NOT `sources._season_kickoffs` — that is a CFBD call, and this job's contract is
    lake-only-plus-AWS (no CFBD key, no Odds credits, no gitignored parquet). Putting a CFBD
    dependency behind a HALT-tier serving write would mean a missing key could stop the board from
    refreshing, which is a strictly worse failure than the staleness this tier exists to fix.

    ⭐ Reading the SNAPSHOT table instead is also the better gate on its merits: it answers "is a
    game we actually have a projection for about to kick off?", and a kickoff we serve nothing for
    is a kickoff no re-serve could improve.
    """
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    now = now or datetime.now(timezone.utc)
    raw = read_snapshots(season, gps.SNAPSHOT_SOURCE, local_root=local_root)
    if raw is None or getattr(raw, "empty", True) or "commence_time" not in raw.columns:
        return []
    kicks = pd.to_datetime(raw["commence_time"], utc=True, errors="coerce").dropna().unique()
    return [k.to_pydatetime() for k in pd.to_datetime(kicks) if k.to_pydatetime() > now]


def should_reserve(kickoffs, *, now: datetime | None = None,
                   baseline_hour_local: int = SERVING_BASELINE_HOUR_LOCAL,
                   tz: str = SERVING_TZ) -> tuple[bool, str]:
    """Does THIS hourly tick re-publish the serving store? A pure function of the clock.

    Mirrors `odds_live_capture.should_capture` deliberately, and shares its window by IMPORT rather
    than by copy — the producer's cadence defines the consumer's, so a change to
    `DENSE_WINDOW_HOURS` moves both at once (E9.61).

      * inside the capture's dense window → re-serve EVERY hour. This is the whole point: the
        capture is hourly there, so a daily re-serve would leave a Saturday-morning line move
        reaching the reader after the games (an INC-25 ordering mismatch on the REFRESH axis
        rather than the build axis).
      * otherwise → the baseline daily write, unchanged.
      * otherwise → skip, and SAY SO. A silent skip is indistinguishable from a schedule that has
        stopped firing (NF-FRESH1), and this job is cheap and always-succeeding, which is exactly
        the shape that invites 19 green runs over a frozen store.

    ⭐ The tier is CLOCK-driven, not lake-diff-driven, on purpose: "has a newer odds row landed
    since the last serve?" needs persisted state, and the write is idempotent anyway, so a diff
    would buy nothing but a thing to go wrong.
    """
    from zoneinfo import ZoneInfo

    from quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture import in_dense_window

    now = now or datetime.now(timezone.utc)
    dense, why = in_dense_window(kickoffs, now=now)
    if dense:
        return True, (f"dense tier: {why} — re-serving every hour so a moving line reaches the "
                      "reader before kickoff, not after")
    local_hour = now.astimezone(ZoneInfo(tz)).hour
    if local_hour == baseline_hour_local:
        return True, (f"baseline tier: the daily {baseline_hour_local:02d}:00 {tz} write "
                      f"({why})")
    return False, (f"skip: {local_hour:02d}:00 {tz} is not the {baseline_hour_local:02d}:00 "
                   f"baseline write and {why} — nothing to refresh, 0 writes")


def read_market_lines(season: int) -> tuple[dict[int, dict], bool]:
    """`{game_id: close-line row}` for `season`, plus a `read_failed` flag. WARN tier: never raises.

    ⭐ Delegates to P1.4's OWN `build_clv_staging` rather than re-implementing the odds→game join.
    That join is subtle (Odds-API team names ⋈ CFBD names by prefix, season + kickoff proximity) and
    a second copy of it would be a second rule set free to drift from the one the model was
    validated against (E9.61). It is already leakage-safe by construction — only snapshots with
    `_snapshot_ts < commence_time` are eligible.

    ⭐ NCAAF-P3.1b — `with_t1=True`. P0.6c captures TWO snapshots per kickoff (a ~24h-prior T-1 and
    a K−5min close) and this asks the SAME join for both, so `payloads._market` can prefer the
    market's own PRE-kickoff line beside a pre-kickoff projection and stamp WHICH line it served.
    It also removes a mislabel: the kind-blind `close_` leg takes the latest pre-commence snapshot,
    so on a kickoff that has a T-1 and no close yet it was already serving T-1 VALUES under a
    `close` LABEL. The flag is opt-in because a `t1_*` column in the DEFAULT frame would be picked
    up as a model FEATURE by `feature_columns` (see that function's docstring) — this serving read
    is the only caller that wants it.

    ⭐ NCAAF-ODDS-LIVE — `with_live=True`. The third leg reads `odds_ncaaf_live`, the
    ahead-of-kickoff board captured on a tiered in-season cadence, which is what puts a line beside
    the model DAYS before kickoff. `_market` then serves the FRESHEST strictly-pre-kickoff
    observation of the three.

    ⚠️ THE TWO `/historical` LEGS CAN STILL BE EMPTY FOR AN UPCOMING SLATE, and that is not a
    defect: that capture only reaches a kickoff once it is past its snapshot instant (K−24h for
    T-1, K−5min for the close). Before NCAAF-ODDS-LIVE that meant an upcoming board had no line at
    all; now the live leg covers exactly that window. A game with nothing from any leg still says
    so through `market.reason`.
    """
    try:
        from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game import (
            build_clv_staging,
        )
        clv = build_clv_staging(min_year=int(season), with_t1=True, with_live=True)
        if clv is None or clv.empty:
            return {}, False
        return {int(r["game_id"]): r for r in clv.to_dict("records")}, False
    except Exception as exc:  # noqa: BLE001 — WARN tier: enrichment must never cost the slate
        log.warning("[ALERT] NCAAF market-line read FAILED (the slate is unaffected; every game's "
                    "market block is served status=unavailable reason=market_read_failed): %s", exc)
        return {}, True



# ══════════════════════════════════════════════════════════════════════════════════════════
# NCAAF-P3.3 — the TEAM PAGE inputs
# ══════════════════════════════════════════════════════════════════════════════════════════
#
# 🚦 TIER: ALERT-loud-but-continue, and the tiering is the design rather than caution.
#
# The team page assembles from a source the predictions write does NOT use: the P1.1 dbt marts,
# which live in the sports DuckDB rather than the lake. That is a strictly heavier dependency than
# this job's stated contract (lake + AWS, nothing else), so it is added at a tier where it cannot
# reach the HALT-tier board:
#
#   * the STRENGTH block reads the LAKE (`ncaaf/derived/team_strength_week`), so the page's LEAD
#     number — the rating and its band — never depends on the DuckDB at all;
#   * the P1.1 blocks (efficiency, trench/pace, schedule) read the marts, and when the DuckDB is
#     absent they are served as STATED absences with `reason=source_marts_unavailable` rather than
#     omitted, so a reader is told which half is missing instead of shown a thinner page that looks
#     complete;
#   * a failure anywhere in here writes no team blobs and leaves the previous ones in place. The
#     manifest / slates / per-game / futures write is untouched.
#
# ⚠️ WHY A DuckDB DEPENDENCY IS ACCEPTABLE HERE WHEN THIS MODULE'S HEADER SAYS "NO sports.duckdb".
# That line predates NF-INFRA1, which moved the file onto the `sports_duckdb` NAMED VOLUME and made
# `SPORTS_DUCKDB_PATH` a deploy-gated required env var. The hazard it named — a HALT-tier op quietly
# depending on a deploy-EPHEMERAL artifact and running green over a frozen table (NF-FRESH1) — is
# answered on both counts: the artifact is persistent, and this read is not HALT-tier and says so
# loudly when it cannot run. ⛔ The predictions path stays lake-only; do not move it.
#
# ⭐ VINTAGE IS SERVED, NOT INFERRED (NF-FRESH2). The marts are rebuilt by a DIFFERENT job on a
# different cadence, so a team page can legitimately be a build behind. Every block states the
# `as_of_week` it describes, and the run log reports the mart vintage — staleness must be visible
# rather than something a reader has to deduce from a number that looks fine.

#: The mart schema `_run_sports_dbt` materializes the NCAAF project into.
NCAAF_MARTS_SCHEMA = "main_ncaaf_marts"


def _team_marts_query(table: str, season: int) -> str:
    return f"select * from {NCAAF_MARTS_SCHEMA}.{table} where season = {int(season)}"


def read_team_marts(season: int) -> tuple[dict[str, "pd.DataFrame"], str | None]:
    """The P1.1 mart frames for `season`, or `({}, reason)` when the DuckDB cannot be read.

    ⭐ ONE RESOLVER FOR THE PATH (NF-INFRA1). `sports_duckdb_path()` is the single owner;
    a literal here would re-create the four-owners divergence that made an NFL gate read a file
    nothing wrote. Opened READ-ONLY: this process must never be able to write, lock or vacuum a
    database a dbt build owns.

    ⚠️ RETURNS A REASON, NEVER RAISES. This is ALERT tier — a missing mart build must degrade the
    team pages, not fail the serving write. But an ABSENT DuckDB is reported with the shared
    `missing_duckdb_remedy()` string so the operator is told what to run, rather than seeing a
    green job that quietly published pages with three empty blocks.
    """
    from betting_ml.utils.sports_duckdb import missing_duckdb_remedy, resolve_sports_duckdb

    resolved = resolve_sports_duckdb()
    if not resolved.exists():
        log.warning("[ALERT] NCAAF team pages: %s", missing_duckdb_remedy(resolved))
        _send_alert(
            "NCAAF team pages — the sports DuckDB is missing",
            missing_duckdb_remedy(resolved),
            severity="WARN", dedup_key="ncaaf-team-pages-duckdb-missing")
        return {}, contract.TEAM_BLOCK_REASON_NOT_BUILT

    try:
        import duckdb
        con = duckdb.connect(str(resolved), read_only=True)
    except Exception as exc:  # noqa: BLE001 — ALERT tier
        log.warning("[ALERT] NCAAF team pages: cannot open %s read-only (%s) — the P1.1 blocks are "
                    "served as stated absences.", resolved, exc)
        return {}, contract.TEAM_BLOCK_REASON_NOT_BUILT

    frames: dict[str, pd.DataFrame] = {}
    try:
        for key, table in (
            ("efficiency", "rollup_ncaaf_team_week_opponent_adjusted"),
            ("splits", "rollup_ncaaf_team_week_asof"),
            ("schedule", "dim_ncaaf_game"),
        ):
            frames[key] = con.execute(_team_marts_query(table, season)).df()
        # ⭐ THE SCD-2 READ, POINT-IN-TIME AND EXPLICIT. `dim_ncaaf_team` is season-VERSIONED, so a
        # team's row is the version whose validity range CONTAINS the season — never `is_current`,
        # which would file every 2026 conference mover under whatever league it ends up in last.
        # The PRIOR season is read too, and only for one purpose: a team with no prior-season row
        # is new to FBS, whose absent pre-season covariates are structural rather than a defect.
        for key, yr in (("team_dim", season), ("prior_team_dim", season - 1)):
            frames[key] = con.execute(
                f"select * from {NCAAF_MARTS_SCHEMA}.dim_ncaaf_team "
                f"where {int(yr)} between valid_from_season and coalesce(valid_to_season, 9999)"
            ).df()
    except Exception as exc:  # noqa: BLE001 — ALERT tier
        log.warning("[ALERT] NCAAF team pages: a P1.1 mart read FAILED (%s) — the affected blocks "
                    "are served as stated absences; the game board is unaffected.", exc)
        return {}, contract.TEAM_BLOCK_REASON_NOT_BUILT
    finally:
        con.close()

    return frames, None


def read_team_strength(season: int) -> "pd.DataFrame | None":
    """The season's P1.2 posterior rows from the LAKE, or None when it cannot be read.

    Uses NCAAF's own `query_or_missing`, so "the table does not exist yet" and "a read failed" are
    decided in ONE place — by LISTING the Delta log, never by matching an engine's error text
    (NCAAF-LAKE1: a message match against an unpinned dependency is a time bomb, and it fired).
    """
    try:
        from quant_sports_intel_models.football.ncaaf.ingest import query_lake as ql
        table = ql.delta("team_strength_week", tier="derived")
        return ql.query_or_missing(f"select * from {table} where season = {int(season)}")
    except Exception as exc:  # noqa: BLE001 — ALERT tier
        log.warning("[ALERT] NCAAF team pages: the P1.2 strength read FAILED (%s) — team pages are "
                    "served with the strength block absent; the game board is unaffected.", exc)
        return None


def build_team_blobs(season: int, *, now: datetime | None = None) -> tuple[list[dict], dict]:
    """`(team payloads, a report dict)`. Never raises — ALERT tier throughout."""
    from quant_sports_intel_models.football.ncaaf.serving import team_payloads

    strength = read_team_strength(season)
    frames, marts_reason = read_team_marts(season)
    marts_available = marts_reason is None

    # ⭐ THE RATING'S OWN DATE (NCAAF-P3.3b). Read from the strength artifact's Delta commit log,
    # NOT from `generated_at` — that is when THIS write ran (hourly), so a page whose posterior was
    # last fit in August would print today's date beside it and read as fresh. That is the exact
    # misread P3.3 measured, and the fix is a date the reader can see.
    #
    # ⚠️ ALERT TIER, LIKE EVERY OTHER READ HERE: an unreadable lake costs the page its STAMP, never
    # its ratings, so the failure is logged and both halves go out as null (which the surface
    # renders as a stated absence, never as a fabricated date — NF1.7(a)).
    try:
        from betting_ml.monitoring import ncaaf_ratings_vintage as vintage

        stamp = vintage.ratings_vintage_fields(now=now)
    except Exception as exc:  # noqa: BLE001 — ALERT tier
        log.warning("[ALERT] NCAAF team pages: the ratings VINTAGE read FAILED (%s) — the pages are "
                    "served without the update stamp; every rating and rank is unaffected.", exc)
        stamp = {"ratings_as_of": None, "ratings_next_update": None}
    log.info("NCAAF team pages: ratings_as_of=%s next_update=%s",
             stamp["ratings_as_of"], stamp["ratings_next_update"] or "(none scheduled)")

    payloads_by_team = team_payloads.build_team_payloads(
        season=season,
        strength=strength,
        efficiency=frames.get("efficiency"),
        splits=frames.get("splits"),
        schedule=frames.get("schedule"),
        team_dim=frames.get("team_dim"),
        prior_team_dim=frames.get("prior_team_dim"),
        marts_available=marts_available,
        ratings_as_of=stamp["ratings_as_of"],
        ratings_next_update=stamp["ratings_next_update"],
        now=now,
    )
    blobs = [payloads_by_team[t] for t in sorted(payloads_by_team)]

    def _block_counts(block: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for blob in blobs:
            key = blob[block]["status"] if blob[block]["status"] == "available" else                 f"unavailable:{blob[block]['reason']}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    report = {
        "n_teams": len(blobs),
        "marts_available": marts_available,
        "strength_read_ok": strength is not None,
        # ⭐ PER-BLOCK, NEVER POOLED (MH2.1 (c)). "82% coverage" cannot tell a week-1 slate whose
        # efficiency blocks are correctly empty from a mart build that did not run, and those are
        # the two states an operator most needs to distinguish here.
        "strength_blocks": _block_counts("strength"),
        "efficiency_blocks": _block_counts("efficiency"),
        "splits_blocks": _block_counts("splits"),
        "schedule_blocks": _block_counts("schedule"),
        # A conference the SCD-2 dim and the P1.2 pooling level DISAGREE on is a finding about the
        # model's inputs, so it is counted rather than logged once and lost.
        "conference_mismatches": sorted(
            b["team"]["team_id"] for b in blobs
            if b["team"]["conference_matches_model_input"] is False),
        "teams_new_to_fbs": sorted(
            b["team"]["team_id"] for b in blobs if b["team"]["is_new_to_fbs"] is True),
    }
    return blobs, report


# ══════════════════════════════════════════════════════════════════════════════════════════
# The write
# ══════════════════════════════════════════════════════════════════════════════════════════

def _count_by(slates: dict, field: str) -> dict[str, int]:
    """`{value: n}` over every served game's `market[field]`, skipping nulls. Sorted for a stable
    run log — an operator diffing two runs should see a value change, not a dict reordering."""
    counts: dict[str, int] = {}
    for slate in slates.values():
        for game in slate["games"]:
            value = game["market"].get(field)
            if value is None:
                continue
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))



def write_serving_store(season: int, *, dry_run: bool = False, local_root: str | None = None,
                        with_market: bool = True, with_futures: bool = True,
                        with_teams: bool = True, out_dir: str | None = None,
                        now: datetime | None = None) -> dict:
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

    # NCAAF-P3.3 — team pages. ALERT tier: a failure here writes no team blobs and leaves the
    # previous ones in place; the manifest / slates / per-game / futures write is untouched.
    team_blobs: list[dict] = []
    team_report: dict = {"n_teams": 0, "skipped": True}
    if with_teams:
        try:
            team_blobs, team_report = build_team_blobs(season, now=now)
        except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (the bonus surface)
            log.warning("[ALERT] NCAAF team pages unavailable for season=%s: %s — the game board "
                        "and futures are unaffected and were written.", season, exc)
            team_report = {"n_teams": 0, "error": str(exc)}

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
    for team_blob in team_blobs:
        tid = team_blob["team"]["team_id"]
        blobs.append((contract.team_cache_key(tid), contract.team_s3_key(tid), team_blob))

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
        # NCAAF-P3.1b: WHICH line attached, and which nulls we produced, counted per value rather
        # than as one total. A run log saying "12 lines attached" cannot answer "did the T-1 leg
        # actually fire?" — and the runtime gate for this story is exactly that question, per key
        # shape (the P3.1 positive-control lesson). A REFUSED count is separated from an
        # unattached one because a leakage refusal is a defect and an absent capture is not.
        market_lines_by_source=_count_by(slates, "source"),
        market_reasons=_count_by(slates, "reason"),
        market_read_failed=bool(market_failed),
        model_version=(any_game or {}).get("provenance", {}).get("model_version"),
        snapshot_ts=(any_game or {}).get("provenance", {}).get("snapshot_ts"),
        team_pages=team_report,
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
    p.add_argument("--no-teams", action="store_true", help="skip the P3.3 per-team pages")
    p.add_argument("--out-dir", default=None, help="also write each blob to a local JSON file")
    args = p.parse_args(argv)

    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    season = args.season or current_season()

    manifest = write_serving_store(
        season, dry_run=args.dry_run, local_root=args.local_root,
        with_market=not args.no_market, with_futures=not args.no_futures,
        with_teams=not args.no_teams, out_dir=args.out_dir)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

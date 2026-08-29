"""odds_live_capture.py  (NCAAF-ODDS-LIVE — the AHEAD-OF-KICKOFF line feed)
==========================================================================================
Captures the market's CURRENT board on a recurring in-season cadence, so a line stands beside
the model DAYS before kickoff rather than only after the game is over.

🎯 WHY THIS EXISTS, AND WHY IT IS NOT MORE `/historical`
--------------------------------------------------------
P0.6b chose option (A) — a paid `/historical` CATCH-UP — over option (B), a live feed. That was
right for its consumer: `/historical` snapshots a PAST instant, which is what makes
`odds_ncaaf_historical` a leakage-safe CLV benchmark. But it means the module only ever asks for a
kickoff once `K − buffer` has already passed, so a Saturday game gets no line until Friday
(T-1) at the earliest and, on the weekly Monday cadence, not until AFTER it is played.

Football is bet days ahead. So this module adds the missing half: the live bulk `/odds` endpoint,
which returns the WHOLE upcoming board in ONE call. Measured 2026-08-27 against the live API:

    109 upcoming events, 1.6 → 92.6 days to kickoff, Bovada quoting 51 of them,  for 3 CREDITS.

⭐ THAT IS TEN TIMES CHEAPER THAN WHAT WE ALREADY DO. `/historical` costs 10 × markets × regions
= 30 credits per ±30-min KICKOFF WINDOW per snapshot; the live board is 1 × markets × regions = 3
credits for EVERY upcoming game at once. So capturing far more, far earlier, several times a day
costs a small fraction of the existing weekly catch-up: the tiered cadence below is ~4,900
credits/season against a ~4.49M balance (0.11%). Cost was never the constraint here — nobody had
wired the feed. `sources.SourceSpec("odds_ncaaf", …)` has DECLARED it since P0.1 and nothing has
ever ingested it (the NF-C0e "wired ≠ invoked" class, on an ingest).

⛔⛔ IT WRITES ITS OWN TABLE, AND THAT IS LOAD-BEARING
------------------------------------------------------
Live rows land in `odds_ncaaf_live`, NEVER in `odds_ncaaf_historical`. `build_clv_staging`'s
default leg takes the LATEST pre-commence snapshot per event with no kind filter, so a live
snapshot taken minutes before kickoff would silently BECOME "the close" for the CLV mart — and
P1.4's model selection and VAL1's CLV null were both decided on that mart. A serving convenience
must not be able to move a recorded result (the same reason `build_clv_staging(with_t1=…)` is
opt-in). Separate table ⇒ the evals structurally cannot see this feed.

🔒 LEAKAGE, TWICE
------------------
The live `/odds` endpoint returns IN-PLAY games too — an in-play price served as a "pre-game
line" is the one thing the NCAAF surface must never do. Two independent defences, because one of
them is a request parameter a future edit could drop:

  1. the request carries `commenceTimeFrom=<now>`, so only upcoming events come back at all;
  2. `_pre_kickoff_only()` DROPS any record whose `commence_time` is not strictly after the
     snapshot instant, counts what it dropped, and says so out loud.

`payloads._market` then applies the serving-side guard a third time against the CFBD kickoff.

⚠️ THE OVERWRITE LANDMINE (the reason this module is a module and not four lines in an op)
-------------------------------------------------------------------------------------------
`s3io.write_season_partition` does a season-grained `replaceWhere` overwrite. A naive
"fetch → write" on an hourly cadence would therefore DELETE the entire season's captured history
on every single fire. This does READ-MERGE-WRITE, deduping on `(event id, _snapshot_ts)` — the
same shape `odds_recurring_capture._merge_and_write` uses, for the same reason. Two snapshots of
one event at different instants are BOTH kept: that history is the line-movement asset.

⏱️ THE TIERED CADENCE (operator-chosen 2026-08-27)
---------------------------------------------------
One hourly schedule, and the OP decides whether a given tick captures:

  * within `DENSE_WINDOW_HOURS` (24) of the next kickoff  → capture EVERY hour (lines move most
    on game-eve and game-day);
  * otherwise                                             → capture only on a `BASELINE_EVERY_H`
    (6) UTC tick, i.e. 4×/day.

ONE schedule with a data-driven decision, deliberately, rather than two crons: "one logical job,
two execution owners" is this repo's most-repeated operational defect (INC-30's double-installed
crontab, INC-36's raced deploy, INC-38's per-caller flag). A skipped tick spends ZERO credits and
says why.

USAGE
-----
    # what WOULD be captured + the exact credit cost; ZERO paid calls
    uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture --dry-run

    # one real capture (3 credits), honouring the tier decision
    uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture

    # capture regardless of the tier decision (an operator override)
    uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture --force
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from . import s3io
from .sources import (
    NCAAF_GAME_LINE_MARKETS,
    build_ctx,
    current_season,
    _iso,
    _odds_ncaaf,
)
from . import query_lake

log = logging.getLogger("ncaaf.odds_live")

#: The Delta table this feed owns. ⛔ NOT `odds_ncaaf_historical` — see the module docstring.
ODDS_LIVE_SOURCE = "odds_ncaaf_live"

#: `_snapshot_kind` stamped on every row. Distinct from the P0.6c close/T-1 vocabulary because
#: these rows answer a different question ("what does the board say NOW") and live in a different
#: table; a reader must never have to infer which feed a row came from.
SNAPSHOT_KIND_LIVE = "live"

#: The tiering the operator chose (2026-08-27): hourly inside a day of the next kickoff, 6-hourly
#: otherwise. Both are DESIGN constants — change them here, not at a call site.
DENSE_WINDOW_HOURS = 24
BASELINE_EVERY_H = 6

#: The live `/odds` endpoint's credit cost: 1 × markets × regions, for the WHOLE upcoming board.
#: (`/historical` is 10 × markets × regions per kickoff window — see the module docstring.)
CREDITS_PER_LIVE_CALL_PER_MARKET_REGION = 1


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def season_for_kickoff(commence: str | datetime) -> int:
    """The NCAAF season a kickoff belongs to. A season YYYY runs Aug YYYY → mid-Jan YYYY+1, so a
    January bowl belongs to the PRIOR calendar year's season.

    ⚠️ Derived per EVENT, not taken from `current_season()`: the live board reaches ~93 days out,
    which in December spans a season boundary, and filing a January bowl under the wrong season
    would put it in a partition the serving read never looks at.
    """
    ts = commence if isinstance(commence, datetime) else datetime.fromisoformat(
        str(commence).replace("Z", "+00:00"))
    return ts.year if ts.month >= 7 else ts.year - 1


def _commence(record: dict) -> datetime | None:
    raw = record.get("commence_time")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _pre_kickoff_only(records: list[dict], snapshot: datetime) -> tuple[list[dict], int]:
    """Keep only records whose kickoff is STRICTLY after the snapshot instant.

    The second of the two leakage defences (the first is the request's `commenceTimeFrom`). It is
    not redundant: the request parameter is one edit away from being dropped, and a record with an
    unreadable `commence_time` must be refused rather than guessed — a check that cannot run is
    not a pass (NF1.7 (a)).
    """
    kept, dropped = [], 0
    for rec in records:
        c = _commence(rec)
        if c is None or not snapshot < c:
            dropped += 1
            continue
        kept.append(rec)
    return kept, dropped


def _tag(records: list[dict], snapshot: datetime) -> list[dict]:
    """Stamp the observation instant + kind on every record, in place.

    ⭐ `_snapshot_ts` is OUR request instant, not a vendor field: the live endpoint returns no
    envelope timestamp (only `/historical` does). Each bookmaker's own `last_update` rides along
    inside the raw JSON untouched, so a movement study can use the finer signal without this
    module having to pick one for it.
    """
    stamp = _iso(snapshot)
    for rec in records:
        rec["_snapshot_ts"] = stamp
        rec["_snapshot_kind"] = SNAPSHOT_KIND_LIVE
    return records


def _event_key(raw_json_str: str) -> tuple:
    """The merge identity of a live row: (event id, the instant we observed it).

    ⛔ NOT (event id) alone — that would keep one row per game and throw away the movement history
    this feed exists to build. Two snapshots of one event at different instants are two rows.
    """
    try:
        d = json.loads(raw_json_str)
    except Exception:  # noqa: BLE001 — a malformed stored row must not break the merge
        return (None, None)
    return (d.get("id"), d.get("_snapshot_ts"))


def _existing_raw_rows(season: int, *, bucket: str = s3io.DEFAULT_BUCKET,
                       local_root: str | None = None):
    """Rows already captured for this season — a pure lake read.

    `None` ONLY when the partition genuinely does not exist yet; a transient read failure RAISES
    (`query_or_missing`), because `_merge_and_write` treats `None` as "nothing to preserve" and a
    guessed-empty read there is the destructive overwrite this module exists to prevent.
    """
    expr = (query_lake.local(ODDS_LIVE_SOURCE, local_root) if local_root
            else query_lake.delta(ODDS_LIVE_SOURCE))
    df = query_lake.query_or_missing(
        f"select season, week, source, ingested_at, raw_json from {expr} "
        f"where season = {int(season)}")
    return None if df is None or df.empty else df


def _merge_and_write(season: int, new_records: list[dict], *,
                     bucket: str = s3io.DEFAULT_BUCKET,
                     local_root: str | None = None) -> int:
    """READ this season's rows → DROP the ones this fetch re-observed → WRITE the union back.

    ⚠️ Never a plain overwrite of `new_records`: `write_season_partition` is a season-grained
    `replaceWhere`, so an hourly plain write would delete the whole season on every fire.
    """
    import pandas as pd
    import pyarrow as pa

    new_table = s3io.records_to_arrow(new_records, source=ODDS_LIVE_SOURCE, season=season,
                                      week=None)
    existing = _existing_raw_rows(season, bucket=bucket, local_root=local_root)
    if existing is None or existing.empty:
        combined = new_table
    else:
        new_keys = {(r.get("id"), r.get("_snapshot_ts")) for r in new_records}
        kept = existing[~existing["raw_json"].map(_event_key).isin(new_keys)]
        existing_table = pa.table({
            "season": pa.array(kept["season"].astype("int64"), type=pa.int64()),
            "week": pa.array([None if pd.isna(w) else int(w) for w in kept["week"]],
                             type=pa.int64()),
            "source": pa.array(kept["source"].astype(str), type=pa.string()),
            "ingested_at": pa.array(kept["ingested_at"].astype(str), type=pa.string()),
            "raw_json": pa.array(kept["raw_json"].astype(str), type=pa.string()),
        })
        combined = pa.concat_tables([existing_table, new_table])
    uri = (s3io.local_table_uri(local_root, "ncaaf", ODDS_LIVE_SOURCE) if local_root
           else s3io.table_uri("ncaaf", ODDS_LIVE_SOURCE, bucket=bucket))
    return s3io.write_season_partition(combined, uri, season)


def estimate_credits(regions: str) -> int:
    """The FREE cost estimate for ONE live capture (no call made)."""
    n_regions = len([r for r in regions.split(",") if r])
    n_markets = len(NCAAF_GAME_LINE_MARKETS.split(","))
    return CREDITS_PER_LIVE_CALL_PER_MARKET_REGION * n_markets * n_regions


def next_kickoff(kickoffs, *, now: datetime | None = None) -> datetime | None:
    now = _now(now)
    future = [k for k in kickoffs if k > now]
    return min(future) if future else None


def should_capture(kickoffs, *, now: datetime | None = None,
                   dense_window_hours: int = DENSE_WINDOW_HOURS,
                   baseline_every_h: int = BASELINE_EVERY_H) -> tuple[bool, str]:
    """The tier decision, as a PURE function of the clock and the schedule — so it is testable
    without a lake, a network or a Dagster context, and so both the CLI and the op ask the SAME
    question (E9.61: two callers of one rule must not be two rules).

    Returns `(capture?, why)`. The reason is returned rather than logged here because the caller
    must state it on BOTH branches: a skipped tick that says nothing is indistinguishable from a
    schedule that stopped firing (the NF-FRESH1 19-green-runs class).
    """
    now = _now(now)
    nxt = next_kickoff(kickoffs, now=now)
    if nxt is not None:
        hours = (nxt - now).total_seconds() / 3600.0
        if hours <= dense_window_hours:
            return True, (f"dense tier: next kickoff in {hours:.1f}h (≤{dense_window_hours}h) — "
                          "capturing every hour while the line is moving")
    if now.hour % baseline_every_h == 0:
        return True, (f"baseline tier: {baseline_every_h}-hourly tick (UTC hour {now.hour})"
                      + ("" if nxt is None else
                         f"; next kickoff in {(nxt - now).total_seconds()/3600.0:.1f}h"))
    return False, (f"skip: UTC hour {now.hour} is not a {baseline_every_h}-hourly tick and no "
                   f"kickoff is within {dense_window_hours}h"
                   + ("" if nxt is None else
                      f" (next in {(nxt - now).total_seconds()/3600.0:.1f}h)") + " — 0 credits")


def fetch_live_board(ctx, *, now: datetime | None = None) -> list[dict]:
    """The whole upcoming board in ONE call, bounded to events that have NOT started.

    `commence_from` is the FIRST leakage defence — without it the live endpoint returns in-play
    games with in-play prices.
    """
    return _odds_ncaaf(ctx, current_season(), commence_from=_iso(_now(now)))


def run_live_capture(*, ctx=None, now: datetime | None = None, force: bool = False,
                     dry_run: bool = False, bucket: str = s3io.DEFAULT_BUCKET,
                     local_root: str | None = None, kickoffs=None) -> dict:
    """One tick: decide the tier, capture the board if this tick captures, merge-write per season.

    Returns a manifest the Dagster op logs. Never raises for "nothing to do" — a skipped tick and
    an empty board are both legitimate, and both say which they are.
    """
    now = _now(now)
    ctx = ctx or build_ctx()
    if ctx.cfbd is None and kickoffs is None:
        raise RuntimeError(
            "CFBD_API_KEY not set — the tier decision needs the season's kickoff times to know "
            "whether a game is within the dense window.")
    if kickoffs is None:
        from .sources import _season_kickoffs
        kickoffs = _season_kickoffs(ctx, current_season())

    capture, why = should_capture(kickoffs, now=now)
    if force and not capture:
        capture, why = True, f"forced by the caller (would otherwise have been: {why})"
    result: dict = {"captured": bool(capture), "reason": why, "credits_estimate":
                    estimate_credits(ctx.odds_regions), "dry_run": bool(dry_run)}
    if not capture:
        log.info("NCAAF live odds capture — %s", why)
        return {**result, "events": 0, "rows_written": 0, "seasons": {}}

    if dry_run:
        log.info("[dry-run] NCAAF live odds capture WOULD fire (%s) for ~%d credits; no call made",
                 why, result["credits_estimate"])
        return {**result, "events": None, "rows_written": 0, "seasons": {}}

    records = fetch_live_board(ctx, now=now)
    records, dropped = _pre_kickoff_only(records, now)
    if dropped:
        log.warning("[ALERT] NCAAF live odds capture DROPPED %d record(s) that were not strictly "
                    "pre-kickoff at the snapshot instant — an in-play price must never enter a "
                    "store a pre-game line is served from.", dropped)
    _tag(records, now)

    by_season: dict[int, list[dict]] = {}
    for rec in records:
        c = _commence(rec)
        if c is None:
            continue
        by_season.setdefault(season_for_kickoff(c), []).append(rec)

    written: dict[str, int] = {}
    for season, recs in sorted(by_season.items()):
        written[str(season)] = _merge_and_write(season, recs, bucket=bucket,
                                                local_root=local_root)
    total = sum(written.values())
    log.info("NCAAF live odds capture — %s: %d event(s) across season(s) %s, %d row(s) in the "
             "partition after merge; credits used=%s remaining=%s",
             why, len(records), sorted(by_season), total, ctx.credits_used, ctx.credits_remaining)
    return {**result, "events": len(records), "dropped_not_pre_kickoff": dropped,
            "rows_written": total, "seasons": written,
            "credits_used": ctx.credits_used, "credits_remaining": ctx.credits_remaining}


def _cli() -> None:
    p = argparse.ArgumentParser(
        description="NCAAF live (ahead-of-kickoff) odds board capture — the live /odds bulk feed "
                    "into the odds_ncaaf_live Delta table.")
    p.add_argument("--dry-run", action="store_true",
                   help="report the tier decision + credit cost; ZERO paid Odds calls")
    p.add_argument("--force", action="store_true",
                   help="capture even if this tick is not a scheduled capture tick")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--local-root", help="write/read Delta from a local dir instead of S3")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run_live_capture(force=args.force, dry_run=args.dry_run, bucket=args.bucket,
                           local_root=args.local_root)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    _cli()

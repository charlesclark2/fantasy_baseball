"""odds_recurring_capture.py  (NCAAF-P0.6b — the recurring 2026+ closing-line catch-up)
==========================================================================================
Bridges P0.6's one-time 2020-2025 historical closing-line backfill into an ONGOING feed: a
weekly IN-SEASON catch-up that lands each newly-kicked-off game's leakage-safe CLOSING line into
the SAME `odds_ncaaf_historical` Delta table, so the CLV benchmark (P1.4's vs-market eval + all
of Phase 2) keeps extending season-over-season instead of freezing at the 2025 backfill.

🎯 THE DECISION (stated per the P0.6b story prompt): periodic `/historical` CATCH-UP — option
(A) — NOT a live-feed snapshot-at-kickoff scheduler (option B). This reuses the exact PROVEN
P0.6 path (the same paid `/historical` endpoint, the same leakage-safe K−buffer snapshot, the
same `verify_odds_historical.py` acceptance gate) over building a new commence-time scheduler,
because NCAAF's weekly cadence makes a once-a-week catch-up trivially affordable and there is
nothing new to prove beyond "which kickoff(s) haven't been captured yet."

⚠️ THE LANDMINE THIS MODULE EXISTS TO AVOID: `s3io.write_season_partition` does a season-grained
`replaceWhere` overwrite (the P0.2 idempotent-per-season contract — see that module's docstring:
"a weekly re-pull that supplies ALL weeks of the current season overwrites the season partition
wholesale"). So naively re-running `odds_backfill.py --seasons 2026 --weeks <this week>` on a
WEEKLY cadence would overwrite the ENTIRE 2026 partition with ONLY that week's rows, silently
DELETING every previously-captured week. This module does a READ-MERGE-WRITE instead: read back
whatever `odds_ncaaf_historical` rows already exist for the season (a pure, free lake read),
fetch ONLY the kickoff(s) not yet covered (bounding paid-credit spend to genuinely new games each
run), and write the UNION back as the season partition — so a weekly re-run never loses a prior
week and never re-pays for a game already captured.

🩹 **CI-FLAKE HARDENING (found + fixed post-merge):** the "read back what already exists" step
used to swallow ANY read exception into "nothing captured yet" — indistinguishable from a
genuinely fresh season. On CI this let a transient `delta_scan` hiccup (reading a partition the
SAME test had just written — a read-after-write visibility blip) silently trigger the exact
destructive overwrite this module exists to prevent. `_q_or_missing` now only treats the
DeltaKernel "table does not exist" error as "nothing captured yet"; every other read failure is
retried a bounded number of times and then RAISED, never guessed as empty.

🚧 WHY KICKOFF-GRAIN, NOT WEEK-GRAIN (found live against real 2025 data while building this):
CFBD's `week` field is AMBIGUOUS — postseason bowl games are numbered "week 1, 2, 3…" WITHIN the
postseason, colliding with regular-season "week 1, 2, 3…" once games of both `seasonType`s are
pulled together (the CFBD default, `season_type="both"`, that every existing fetcher already
uses). A per-CFBD-week coverage check therefore mixed August season-openers with December bowl
games under the same "week 1" bucket and produced a nonsense "week 1 needs recapturing" result
against a season that was already ~85%+ covered. Comparing individual kickoff `commence_time`
values directly against what's already in the lake sidesteps the ambiguity entirely — it never
needs to know what CFBD calls a "week."

CANDIDATE DETECTION: a kickoff K is captured once it's (a) already past its closing-snapshot
instant (K − buffer ≤ now — the `/historical` endpoint has nothing real to serve for a game that
hasn't reached that instant yet, so an early run just waits, 0 credits, no error) and (b) its ISO
`commence_time` is NOT already present among the lake's captured commence times. This is also
what makes the module SAFE to build and deploy now, ahead of the 2026 kickoff: run before any
2026 game has kicked off and the candidate list is `[]` every time (a clean no-op) — exactly the
"verify the mechanism, don't block on live 2026 data" posture the story asks for.

CREDIT COST: bounded to whichever kickoff(s) newly became "past and uncaptured" since the last
run — for a weekly cadence that is normally one NCAAF week's worth of games (~60-70 FBS games ×
10 credits × 3 markets × 1 region ≈ 1,800-2,100 credits/week ⇒ ~15 weeks/season ⇒ ~27-32k
credits/season, the same per-game cost the P0.6 backfill already paid for 2020-2025 — see
`--dry-run` for the live per-run estimate). A missed run just catches up the backlog of kickoffs
on the next fire (still merge-safe, still deduped on (event id, requested snapshot) — re-fetching
an already-captured kickoff is a value-identical, non-duplicating rewrite).

USAGE:
  # Dry run — lists the new kickoffs to capture + the credit estimate; ZERO paid calls:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture --dry-run

  # Live weekly catch-up (season defaults to current_season(), clock-derived):
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture

  # FORCE a specific week of a PRIOR season (operator override — bypasses the kickoff diff and
  # calls the proven odds_backfill.py fetch path directly; e.g. to re-pull a known gap):
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture \
      --season 2025 --weeks 1

Recurring orchestration: the Dagster `sports_ncaaf_odds_capture_job` /
`sports_ncaaf_odds_capture_schedule` (weekly, in-season Aug-Jan, `default_status=STOPPED` —
operator-gated, same E11.23 carve-out as the sports schedules: needs `ODDS_API_KEY` (the paid
MAIN key) + `CFBD_API_KEY` provisioned first). This module is the pure driver, mirroring how
`roll_forward.py` is the pure driver behind `sports_ncaaf_roll_forward_job` (P0.7) — same
clock-derived-season + idempotent-module + STOPPED-gated-schedule shape, different (in-season
vs. pre-season) cadence window. `verify_odds_historical.py` (unchanged from P0.6) is the
post-capture acceptance gate — pass `--seasons <season>` explicitly to check the in-progress
season (its own default range stops at the last COMPLETED season).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import s3io
from .handler import load_env
from .odds_backfill import CREDITS_PER_CALL_PER_MARKET_REGION
from .sources import (
    NCAAF_GAME_LINE_MARKETS,
    _iso,
    _odds_historical_for_kickoffs,
    _odds_ncaaf_historical,
    _season_kickoffs,
    build_ctx,
    current_season,
)

log = logging.getLogger(__name__)

ODDS_HISTORICAL_SOURCE = "odds_ncaaf_historical"


def _new_kickoffs_to_capture(
    ctx,
    season: int,
    captured_commence: set[str],
    *,
    now: datetime | None = None,
    buffer_min: int = 5,
) -> list[datetime]:
    """The season's FBS kickoffs (one free CFBD call, regular + postseason together — same
    universe the P0.6 full-season backfill already reads) that are (a) already past their
    closing-snapshot instant and (b) not yet represented in the lake. Pure/CFBD-only (no paid
    Odds calls) — safe to call on every run, including `--dry-run`."""
    now = now or datetime.now(timezone.utc)
    buffer = timedelta(minutes=buffer_min)
    kicks = _season_kickoffs(ctx, season)
    new = [k for k in kicks if (k - buffer) <= now and _iso(k) not in captured_commence]
    return sorted(new)


# The DeltaKernel error DuckDB's delta_scan raises when a table/partition genuinely doesn't
# exist yet (verified empirically: `IO Error: DeltaKernel InvalidTableLocationError (28): Invalid
# table location: Path does not exist: "..."`). This is the ONLY error class that may be treated
# as "nothing captured yet" — see `_q_or_missing`.
_MISSING_TABLE_MARKERS = ("InvalidTableLocationError", "Path does not exist")


def _is_missing_table_error(exc: Exception) -> bool:
    """True only when `exc` means the Delta table/partition genuinely doesn't exist yet (a
    season's first-ever run). Anything else — a network hiccup, an extension-load glitch, a
    read-after-write visibility blip on a partition just written this same run — must NOT be
    mistaken for "nothing's there yet"; see `_q_or_missing`."""
    msg = str(exc)
    return any(marker in msg for marker in _MISSING_TABLE_MARKERS)


def _q_or_missing(sql: str, *, retries: int = 2, retry_sleep: float = 0.15):
    """Run a read-only lake SELECT. Returns the DataFrame, or `None` if the table/partition
    genuinely doesn't exist yet. Any OTHER failure is retried a bounded number of times (a
    transient delta_scan hiccup — e.g. right after a partition was just written — usually clears
    within one retry) and then RAISED — never silently swallowed into "nothing captured yet."

    THE BUG THIS FIXES (a real data-loss fragility, caught by a CI-only flake): the previous
    `_existing_raw_rows` wrapped its lake read in a bare `except Exception: return None`, and
    `_merge_and_write` treats `None` as "fresh season, nothing to preserve" → writes ONLY the new
    records. A transient read failure is therefore indistinguishable from "no partition yet," so
    a flaky read of a partition this very run had just written (e.g. a read-after-write
    visibility blip) silently took the destructive overwrite branch and dropped every prior week.
    A caller that can't CONFIRM what's already in the lake must fail loud, never guess "empty."
    """
    from .query_lake import _connect, q

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return q(sql)
        except Exception as exc:  # noqa: BLE001 — inspected immediately below, never blindly swallowed
            if _is_missing_table_error(exc):
                return None
            last_exc = exc
            if attempt < retries:
                try:
                    _connect().execute("LOAD delta")  # defensive re-affirm; cheap, idempotent
                except Exception:  # noqa: BLE001 — best-effort; a persistent problem still surfaces below
                    pass
                time.sleep(retry_sleep)
    raise RuntimeError(
        f"lake read failed {retries + 1}x and is NOT a missing-table error — refusing to treat "
        f"this as 'nothing captured yet' (that would risk a destructive merge overwrite): "
        f"{last_exc}"
    ) from last_exc


def _captured_commence_times(
    season: int,
    *,
    source: str = ODDS_HISTORICAL_SOURCE,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
) -> set[str]:
    """Distinct `commence_time` values already captured for this season — a PURE lake read (zero
    CFBD/Odds calls). Empty set only if the partition genuinely doesn't exist yet (a season's
    first-ever run) — a transient read failure raises instead (see `_q_or_missing`)."""
    from .query_lake import delta, local

    expr = local(source, local_root) if local_root else delta(source)
    df = _q_or_missing(
        f"select distinct json_extract_string(raw_json,'$.commence_time') as ct "
        f"from {expr} where season = {int(season)}"
    )
    if df is None:
        log.info(
            "  [odds_recurring_capture] no existing %s/%s partition yet — treating as a fresh "
            "season (full-to-date capture)", source, season,
        )
        return set()
    return set(df["ct"].dropna())


def _existing_raw_rows(
    season: int,
    *,
    source: str = ODDS_HISTORICAL_SOURCE,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
):
    """The full raw Delta rows already captured for this season (season/week/source/ingested_at/
    raw_json) — a pure lake read. `None` only if the partition genuinely doesn't exist yet for
    this season — a transient read failure raises instead (see `_q_or_missing`); `_merge_and_write`
    relies on this so it can never mistake "couldn't read" for "nothing to preserve.\""""
    from .query_lake import delta, local

    expr = local(source, local_root) if local_root else delta(source)
    df = _q_or_missing(
        f"select season, week, source, ingested_at, raw_json from {expr} "
        f"where season = {int(season)}"
    )
    return None if df is None or df.empty else df


def _event_key(raw_json_str: str) -> tuple:
    """(event id, requested snapshot) — the exact grain `verify_odds_historical.py` already
    dedupes on. Used to drop a stale existing row when the merge re-captures its kickoff, so a
    re-run of an already-covered kickoff is a value-identical rewrite, not an accumulating dupe."""
    try:
        d = json.loads(raw_json_str)
    except Exception:  # noqa: BLE001 — a malformed existing row; keep it, don't crash the merge
        return (None, None)
    return (d.get("id"), d.get("_requested_snapshot"))


def _merge_and_write(
    season: int,
    new_records: list[dict],
    *,
    source: str = ODDS_HISTORICAL_SOURCE,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
) -> int:
    """READ existing season rows → DROP any whose (id, requested_snapshot) the new fetch also
    covers (idempotent re-capture) → WRITE the union back as the season partition.

    Never a plain overwrite of just `new_records` — that would delete every prior week (the
    landmine this module exists to avoid; see the module docstring). Belt-and-suspenders: this
    relies on `_existing_raw_rows` RAISING when it can't confirm what's already in the lake
    (rather than returning `None`, which this function treats as "genuinely nothing captured
    yet") — a transient read failure must never fall through to the destructive overwrite branch
    below. Do not wrap the call in a try/except here; let it propagate."""
    import pandas as pd
    import pyarrow as pa

    new_table = s3io.records_to_arrow(new_records, source=source, season=season, week=None)
    existing = _existing_raw_rows(season, source=source, bucket=bucket, local_root=local_root)
    if existing is None or existing.empty:
        combined = new_table
    else:
        new_keys = {(r.get("id"), r.get("_requested_snapshot")) for r in new_records}
        keep = ~existing["raw_json"].map(_event_key).isin(new_keys)
        kept = existing[keep]
        existing_table = pa.table(
            {
                "season": pa.array(kept["season"].astype("int64"), type=pa.int64()),
                "week": pa.array(
                    [None if pd.isna(w) else int(w) for w in kept["week"]], type=pa.int64()
                ),
                "source": pa.array(kept["source"].astype(str), type=pa.string()),
                "ingested_at": pa.array(kept["ingested_at"].astype(str), type=pa.string()),
                "raw_json": pa.array(kept["raw_json"].astype(str), type=pa.string()),
            }
        )
        combined = pa.concat_tables([existing_table, new_table])
    uri = (
        s3io.local_table_uri(local_root, "ncaaf", source)
        if local_root
        else s3io.table_uri("ncaaf", source, bucket=bucket)
    )
    return s3io.write_season_partition(combined, uri, season)


def _estimate_credits(n_kickoffs: int, regions: str) -> dict:
    """FREE credit estimate for exactly `n_kickoffs` snapshots (no calls made)."""
    n_regions = len([r for r in regions.split(",") if r])
    n_markets = len(NCAAF_GAME_LINE_MARKETS.split(","))
    return {"kickoffs": n_kickoffs, "credits": n_kickoffs * CREDITS_PER_CALL_PER_MARKET_REGION * n_markets * n_regions}


def run_recurring_capture(
    season: int | None = None,
    *,
    ctx=None,
    weeks: list[int] | None = None,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
    buffer_min: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The P0.6b driver: figure out which kickoff(s) of `season` (default `current_season()`,
    clock-derived) are newly past their closing-snapshot instant and not yet lake-covered, fetch
    ONLY those (paid, leakage-safe), and merge them into the existing season partition without
    disturbing any previously-captured game.

    `weeks` FORCES a specific CFBD week (or weeks) instead of auto-detecting — an operator
    override (e.g. to re-pull a known gap for a PRIOR season); bypasses the kickoff diff entirely
    and calls the proven `_odds_ncaaf_historical` (odds_backfill.py's own) fetch path. Returns a
    manifest with what was captured, rows written, and the running credit usage `ctx` observed.
    """
    season = int(season) if season is not None else current_season()
    if ctx is None:
        ctx = build_ctx()
    if ctx.cfbd is None:
        raise RuntimeError(
            "CFBD_API_KEY not set — the catch-up reads CFBD /games for kickoff times "
            "(leakage-safe snapshots + the lake-coverage diff)."
        )

    captured = _captured_commence_times(season, bucket=bucket, local_root=local_root)

    if weeks is not None:
        log.info(
            "NCAAF odds recurring capture: season=%s FORCED weeks=%s (operator override, "
            "bypasses the kickoff diff)", season, list(weeks),
        )
        new_records = _odds_ncaaf_historical(ctx, season, weeks=list(weeks))
        n_kickoffs = None
    else:
        target_kickoffs = _new_kickoffs_to_capture(ctx, season, captured, now=now, buffer_min=buffer_min)
        if not target_kickoffs:
            log.info(
                "NCAAF odds recurring capture: season=%s — no newly-past, uncaptured kickoff; "
                "nothing to do (0 credits).", season,
            )
            return {
                "season": season, "new_kickoffs": 0, "rows_written": 0,
                "credits_used": ctx.credits_used, "credits_remaining": ctx.credits_remaining,
            }
        log.info(
            "NCAAF odds recurring capture: season=%s — %d new kickoff(s) to snapshot (bounded "
            "catch-up, not the whole season)", season, len(target_kickoffs),
        )
        new_records = _odds_historical_for_kickoffs(ctx, target_kickoffs)
        n_kickoffs = len(target_kickoffs)

    rows = _merge_and_write(season, new_records, bucket=bucket, local_root=local_root)
    log.info(
        "  merged %d new row(s) into odds_ncaaf_historical/season=%s; credits used=%s "
        "remaining=%s", rows, season, ctx.credits_used, ctx.credits_remaining,
    )
    return {
        "season": season, "new_kickoffs": n_kickoffs,
        "forced_weeks": list(weeks) if weeks is not None else None,
        "rows_written": rows, "credits_used": ctx.credits_used,
        "credits_remaining": ctx.credits_remaining,
    }


def _cli() -> None:
    p = argparse.ArgumentParser(
        description="NCAAF recurring in-season closing-line catch-up (P0.6b)."
    )
    p.add_argument(
        "--season", type=int, default=None,
        help="season to catch up (default: current_season() — clock-derived, the in-progress "
             "NCAAF season)",
    )
    p.add_argument(
        "--weeks",
        help="comma list — FORCE this specific CFBD week (or weeks) instead of auto-detecting "
             "newly-past/uncovered kickoffs (an operator override, e.g. to re-pull a known gap "
             "for a PRIOR season). Bypasses the kickoff diff.",
    )
    p.add_argument("--regions", default="us", help="Odds-API regions (default us; incl. Bovada)")
    p.add_argument("--buffer-min", type=int, default=5, help="snapshot = kickoff − buffer minutes")
    p.add_argument("--sleep", type=float, default=0.5, help="inter-call sleep seconds")
    p.add_argument("--local-root", help="write/read Delta from a local dir instead of S3 (dry dev)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument(
        "--dry-run", action="store_true",
        help="list the new kickoff(s) to capture + the credit estimate; ZERO paid Odds calls",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # ODDS_API_KEY (MAIN key) + CFBD_API_KEY from .env for standalone laptop runs
    season = args.season if args.season is not None else current_season()
    weeks_override = [int(w) for w in args.weeks.split(",")] if args.weeks else None

    ctx = build_ctx(regions=args.regions, snapshot_buffer_min=args.buffer_min, sleep_seconds=args.sleep)
    if ctx.cfbd is None:
        raise SystemExit("CFBD_API_KEY not set.")

    if args.dry_run:
        captured = _captured_commence_times(season, bucket=args.bucket, local_root=args.local_root)
        if weeks_override is not None:
            kicks = _season_kickoffs(ctx, season, weeks=weeks_override)
            log.info("[dry-run] season=%s FORCED weeks=%s → %d kickoff(s)",
                     season, weeks_override, len(kicks))
            est = _estimate_credits(len(kicks), args.regions)
        else:
            target = _new_kickoffs_to_capture(ctx, season, captured, buffer_min=args.buffer_min)
            log.info(
                "[dry-run] season=%s (clock-derived current_season=%s) — %d new kickoff(s) to "
                "capture", season, current_season(), len(target),
            )
            if not target:
                log.info("[dry-run] nothing to capture right now (0 credits).")
                return
            est = _estimate_credits(len(target), args.regions)
        log.info("ESTIMATED TOTAL ≈ %d credits — NO calls made (dry run): %s", est["credits"], est)
        return

    manifest = run_recurring_capture(
        season, ctx=ctx, weeks=weeks_override, bucket=args.bucket, local_root=args.local_root,
        buffer_min=args.buffer_min,
    )
    for k, v in manifest.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()

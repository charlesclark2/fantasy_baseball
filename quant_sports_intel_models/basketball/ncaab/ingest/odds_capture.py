"""odds_capture.py — the NCAAB forward market capture (NCAAB-P0 node 1).

⛔ NOTHING HERE RUNS UNTIL AN OPERATOR ENABLES THE SCHEDULE. This module exists so that
enabling is a Dagit toggle rather than a code change during the season — the same posture
`sports_ncaaf_odds_capture_schedule` takes. The spend decision it is gated on is
`docs/ncaab_p0_credit_arithmetic.md`.

⚠️⚠️ THE LANDMINE THIS MODULE EXISTS TO AVOID, inherited from NCAAF-P0.6b rather than
rediscovered: `write_season_partition` does a season-grained `replaceWhere` OVERWRITE. Odds
captures ACCUMULATE across a season — every 30 minutes for five months — so writing a fresh
capture with the ordinary path would DELETE every prior snapshot in that season, atomically
and silently, on the very first fire. This module therefore does a READ-MERGE-WRITE: read back
the season's existing rows (a free lake read), append the new capture, and write the UNION.

⭐ AND THE MERGE IS DEDUPLICATED ON `(capture_timestamp, market_tier, event_id)`, not appended
blindly. A re-fire of the same tick — a retry, a manual run beside the cron, a backfill
overlapping live capture — must be idempotent, or the store silently accumulates duplicate
snapshots that every downstream "latest price" read would then average over.

CADENCE IS A PURE FUNCTION OF THE TICK, NOT A SECOND CRON. One schedule fires every 30
minutes; `should_capture_futures()` decides from the tick time alone whether this is also the
day's futures capture. Two crons for one logical job is the INC-30 / INC-36 / INC-38 class
(one logical thing, two execution owners), and it is how this repo has repeatedly ended up
with a job that double-fires or silently half-fires.

WHY AN OUT-OF-SEASON TICK IS FREE, measured rather than assumed: the Odds API bills per market
x region only when there is something to return, and an empty board bills **0** (measured
2026-09-14). So a 30-minute cron running year-round costs nothing until games post lines,
which is why this needs no month range and therefore has no seasonal boundary hole.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import budget, lake, sources as S

log = logging.getLogger(__name__)

#: The lake tables the capture writes.
FUTURES_TABLE = "odds_futures"
GAME_LINES_TABLE = "odds_game_lines"

#: The UTC hour on which the once-daily futures capture rides. Any hour works; 14:00 is chosen
#: to sit with the free ingest so a reader comparing the two sees one daily vintage.
FUTURES_CAPTURE_HOUR_UTC = 14


def should_capture_futures(now: datetime | None = None) -> bool:
    """Is THIS tick the day's futures capture?

    A pure function of the tick instant — no stored state, so a missed tick cannot leave the
    decision wedged and a replay is deterministic. Futures cost 1 credit and move slowly; at
    the 30-minute game-line cadence a per-tick futures call would be 48x the price for no
    additional information.
    """
    now = now or datetime.now(timezone.utc)
    return now.hour == FUTURES_CAPTURE_HOUR_UTC and now.minute < 30


@dataclass
class CaptureResult:
    """One leg's outcome. Records ATTEMPTS, so a skip is distinguishable from a no-op."""

    table: str
    attempted: bool = False
    events: int = 0
    rows_total_after_merge: int = 0
    credits_spent: int | None = None
    credits_remaining: int | None = None
    skipped_reason: str | None = None
    error: str | None = None
    escalation: str | None = None


@dataclass
class CaptureReceipt:
    started_at: str = ""
    finished_at: str = ""
    season: int = 0
    results: list[CaptureResult] = field(default_factory=list)

    @property
    def escalations(self) -> list[str]:
        return [r.escalation for r in self.results if r.escalation]

    @property
    def errors(self) -> list[str]:
        return [f"{r.table}: {r.error}" for r in self.results if r.error]


def _read_existing(season: int, table: str, *, local_root: str | None = None) -> list[dict]:
    """The season's already-captured rows. A MISSING table is empty; an UNREADABLE one RAISES.

    ⛔ The distinction is the whole safety of the merge. If an unreadable table returned []
    the merge would write only the new capture and the `replaceWhere` would delete a season of
    history — the exact failure this module exists to prevent, reached through the error path
    instead of the happy one. "Not there yet" and "there but I could not read it" are different
    facts and only the first is safe to treat as empty.
    """
    import duckdb

    uri = (lake.local_table_uri(local_root, table) if local_root else lake.table_uri(table))
    con = duckdb.connect()
    try:
        if not local_root:
            lake.configure_duckdb_lake_auth(con)
        else:
            con.execute("INSTALL delta; LOAD delta")
        cols = ", ".join(ODDS_COLUMNS)
        return con.execute(
            f"SELECT {cols} FROM delta_scan('{uri}') WHERE season = {int(season)}"
        ).df().to_dict("records")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        absent = ("No files in log segment" in msg or "not a Delta table" in msg
                  or "InvalidTableLocation" in msg or "No files found" in msg
                  or "IO Error" in msg and "No such file" in msg)
        if absent:
            log.info("  %s: no existing Delta table for season %s — first capture", table, season)
            return []
        raise RuntimeError(
            f"{table}: the season-{season} partition exists but could not be READ ({msg[:160]}). "
            f"REFUSING the merge — writing only the new capture would replaceWhere away every "
            f"prior snapshot in this season."
        ) from exc


#: The columns an odds capture row carries. TYPED, not wrapped in `raw_json`.
#:
#: ⚠️ THE RAW-JSON PATH IS WRONG FOR THIS TABLE AND A REAL RUN IS WHAT PROVED IT.
#: `lake.write_records` (the CFBD-shaped path) json.dumps each record into a single `raw_json`
#: VARCHAR, so the read-back carries `season/week/source/ingested_at/raw_json` and NONE of the
#: columns below. `_merge_key` then found `capture_timestamp` and `payload` missing on every
#: EXISTING row, keyed them all to `(None, None, None)`, and collapsed an entire season of
#: prior snapshots into ONE row — silently, on the second capture. Measured: two captures
#: merged back to 1 unique key. The merge must read back the SAME SHAPE it writes, so odds
#: rows go through the TYPED path where `capture_timestamp` is a real column — which is also
#: what the point-in-time story needs it to be.
ODDS_COLUMNS = ("capture_timestamp", "market_tier", "event_id", "snapshot_timestamp",
                "x_requests_last", "x_requests_remaining", "payload", "season")


def _merge_key(row) -> tuple:
    """Identity of a captured snapshot row: which tick, which tier, which event.

    Reads the TYPED columns. A row missing any of them is a shape the merge does not
    understand, and returning a constant key for it would silently collapse history — so a
    missing `capture_timestamp` RAISES rather than defaulting.
    """
    get = row.get if hasattr(row, "get") else (lambda k, d=None: getattr(row, k, d))
    stamp = get("capture_timestamp")
    if stamp is None:
        raise RuntimeError(
            "odds merge: a row carries no `capture_timestamp`. REFUSING rather than keying it "
            "to a default — a constant key collapses every such row into one and destroys "
            "prior captures. This is the raw_json-vs-typed shape mismatch; see ODDS_COLUMNS."
        )
    return (str(stamp), get("market_tier"), get("event_id"))


def capture_leg(ctx: S.Ctx, season: int, *, source_name: str, table: str,
                local_root: str | None = None,
                today: date | None = None) -> CaptureResult:
    """Capture ONE leg and READ-MERGE-WRITE it into the season partition."""
    spec = S.SOURCES[source_name]
    res = CaptureResult(table=table, attempted=True)
    try:
        fresh = spec.fetch(ctx, season)
        res.events = len(fresh)
        res.credits_remaining = ctx.credits_remaining

        # ⛔ An empty capture must not trigger a write at all: a merge of nothing is a no-op,
        # but a write of nothing is a replaceWhere that empties the partition.
        if not fresh:
            res.skipped_reason = ("empty board — nothing to merge (out of season this is the "
                                  "expected, and measured FREE, state)")
            res.escalation = S.check_landing(spec, 0, when=today)
            return res

        existing = _read_existing(season, table, local_root=local_root)
        merged: dict[tuple, dict] = {_merge_key(r): r for r in existing}
        for r in fresh:
            merged[_merge_key(r)] = r          # idempotent on a re-fired tick
        rows = list(merged.values())
        res.rows_total_after_merge = len(rows)

        import pandas as pd

        df = pd.DataFrame(rows, columns=list(ODDS_COLUMNS))
        df["season"] = int(season)
        # TYPED write — see ODDS_COLUMNS for why this is not the raw_json path.
        lake.write_dataframe(df, source=table, season=season, local_root=local_root)
        log.info("  %s: +%d events -> %d rows in season %s", table, len(fresh), len(rows), season)
    except Exception as exc:  # noqa: BLE001 — recorded; the caller decides the tier
        res.error = f"{type(exc).__name__}: {exc}"
        log.warning("  %s: FAILED %s", table, res.error)
    return res


def run_capture(*, season: int | None = None, ctx: S.Ctx | None = None,
                local_root: str | None = None, now: datetime | None = None,
                force_futures: bool = False) -> CaptureReceipt:
    """One capture tick: game lines always, futures once a day."""
    now = now or datetime.now(timezone.utc)
    ctx = ctx or S.Ctx()
    season = season or S.season_for(now.date())
    rec = CaptureReceipt(started_at=S.now_iso(), season=season)

    rec.results.append(capture_leg(ctx, season, source_name="odds_game_lines",
                                   table=GAME_LINES_TABLE, local_root=local_root,
                                   today=now.date()))

    if force_futures or should_capture_futures(now):
        rec.results.append(capture_leg(ctx, season, source_name="odds_futures",
                                       table=FUTURES_TABLE, local_root=local_root,
                                       today=now.date()))
    else:
        rec.results.append(CaptureResult(
            table=FUTURES_TABLE, attempted=False,
            skipped_reason=(f"not the daily futures tick (fires at {FUTURES_CAPTURE_HOUR_UTC:02d}:00 "
                            f"UTC; this tick is {now:%H:%M})")))

    rec.finished_at = S.now_iso()
    return rec


def estimate_tick_credits(*, futures: bool) -> int:
    """What one tick costs at the measured unit prices — for the operator's own arithmetic."""
    return budget.LIVE_GAME_LINE_SNAPSHOT + (budget.LIVE_FUTURES_SNAPSHOT if futures else 0)

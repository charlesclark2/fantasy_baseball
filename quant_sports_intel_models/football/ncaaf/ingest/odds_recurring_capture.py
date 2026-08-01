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

NCAAF-P0.6c — DAY-PRIOR (T-1) LINE-MOVEMENT EXTENSION
======================================================
Adds a SECOND, ~24h-pre-kickoff `/historical` snapshot ("T-1", `SNAPSHOT_KIND_T1`) alongside the
existing K−5min "close" snapshot (`SNAPSHOT_KIND_CLOSE`), so the lake carries close-vs-T-1 line
MOVEMENT for every captured kickoff — a transparency/content feature (show the move) and a
Phase-2 microstructure signal. Both snapshots are inherently leakage-safe (T-1 is even further
pre-kickoff than the close; `_snapshot_ts < commence_time` holds for both by construction).

🎯 WHY THE WEEKLY CADENCE STILL WORKS FOR A "DAY-PRIOR" SNAPSHOT: this is a paid `/historical`
CATCH-UP (not a live-feed scheduler — same P0.6b decision), so a snapshot instant is fetched by
passing a past `date=` to the API; it does not matter how long AFTER that instant the fetch
actually runs. By the time the weekly Monday run fires, a kickoff's T-1 instant (K−24h) has
*already* passed for every kickoff whose CLOSE instant (K−5min) has passed too — so the SAME
kickoff-grain "past + uncaptured" diff this module already does for the close works unmodified
for T-1, just anchored on a 1440-minute buffer instead of 5. The one case they diverge (a
still-upcoming kickoff whose T-1 instant has passed but whose close instant hasn't) is exactly
the useful case — it captures T-1 a day early instead of waiting for kickoff.

🚨 THE CORRECTNESS CRUX (why this was SAFE to build as a REUSE, not a rewrite): `_merge_and_write`
already dedups on `_event_key` = (event id, `_requested_snapshot`) — snapshot-GRAIN, not
event-grain — because `_requested_snapshot` was already part of the P0.6b contract
(`verify_odds_historical.py` relies on it too). A close snapshot (K−5min) and a T-1 snapshot
(K−1440min) of the SAME event always compute a different `_requested_snapshot`, so the existing
merge guard already prevents one from clobbering the other with ZERO changes to
`_merge_and_write`/`_event_key`. `test_merge_and_write_never_loses_a_prior_snapshot_of_a_different_kind`
proves this holds, rather than asserting it by inspection alone.

`_snapshot_kind` ("close" | "t_minus_1", `SNAPSHOT_KIND_CLOSE` / `SNAPSHOT_KIND_T1`) is stamped on
every fetched record for queryability (distinguishing the two kinds without inferring it from a
snapshot-vs-commence time delta) and so the PER-KIND coverage diff (`_captured_commence_times`'s
new `kind=` filter) can independently track "does this kickoff have a close?" vs "does this
kickoff have a T-1?" — a kickoff can be missing one, both, or neither. A row landed before P0.6c
carries no `_snapshot_kind` field at all; the SQL coalesces a missing field to "close" (the only
kind P0.6/P0.6b ever captured), so legacy rows count correctly without a backfill migration.

💳 CREDIT GATING (the story's "scope the credit math first"): T-1 capture roughly DOUBLES this
run's paid Odds-API spend (a second `/historical` call per kickoff) — so it is OFF by default
(`run_recurring_capture(capture_t1=False)`) and only turns on when the caller explicitly opts in.
The Dagster op gates it behind `NCAAF_ODDS_CAPTURE_T1` (default unset = off), the same
env-flag-gated-behind-a-flag shape as the rest of this codebase's default-OFF cutover levers
(CLAUDE.md's `os.environ.get("<FLAG>") == "1"` convention) — an operator turns it on only after
confirming `ctx.credits_remaining` (or `--dry-run --capture-t1`) covers the added cost. This is
a SEPARATE gate from the schedule's own `default_status=STOPPED` — both must be turned on.

USAGE (T-1 additions):
  # Dry run WITH T-1 — credit estimate for close-only vs close+T-1, still ZERO paid calls:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture \
      --dry-run --capture-t1

  # Live weekly catch-up WITH T-1 day-prior capture enabled:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture \
      --capture-t1
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
    _season_kickoffs,
    build_ctx,
    current_season,
)

log = logging.getLogger(__name__)

ODDS_HISTORICAL_SOURCE = "odds_ncaaf_historical"

# ── P0.6c snapshot kinds ────────────────────────────────────────────────────────────────────
SNAPSHOT_KIND_CLOSE = "close"          # K − 5min (P0.6/P0.6b, unchanged)
SNAPSHOT_KIND_T1 = "t_minus_1"         # K − ~24h day-prior line-movement snapshot (P0.6c)
T1_BUFFER_MIN = 24 * 60                # 1440 — the default T-1 snapshot offset


def _filter_uncaptured_kickoffs(
    kicks: list[datetime],
    captured_commence: set[str],
    *,
    now: datetime | None = None,
    buffer_min: int = 5,
) -> list[datetime]:
    """Kind-agnostic, kickoff-list-agnostic filter: of `kicks`, keep only those (a) already past
    their SNAPSHOT instant (kickoff − `buffer_min`) and (b) not yet represented in the lake for
    the snapshot kind `captured_commence` was built from. Pure/no paid Odds calls — safe to call
    on every run, including `--dry-run`.

    Factored out of `_new_kickoffs_to_capture` (P0.6c) so the SAME "already captured for this
    kind? skip it" guard applies whether the candidate kickoffs come from the whole-season
    auto-detect diff OR an operator's explicit `--weeks` list — see `run_recurring_capture`'s
    forced-weeks path, which used to always re-fetch (and re-pay for) whatever a forced week
    already had captured; it now shares this exact filter by default (an explicit `force=True`
    still bypasses it, for genuinely re-pulling a known-bad capture)."""
    now = now or datetime.now(timezone.utc)
    buffer = timedelta(minutes=buffer_min)
    new = [k for k in kicks if (k - buffer) <= now and _iso(k) not in captured_commence]
    return sorted(new)


def _new_kickoffs_to_capture(
    ctx,
    season: int,
    captured_commence: set[str],
    *,
    now: datetime | None = None,
    buffer_min: int = 5,
) -> list[datetime]:
    """The season's FBS kickoffs (one free CFBD call, regular + postseason together — same
    universe the P0.6 full-season backfill already reads), filtered by `_filter_uncaptured_kickoffs`.
    Kind-agnostic: P0.6c calls this twice per run (once for the close buffer, once for the T-1
    buffer) against two independently-diffed `captured_commence` sets — see
    `_captured_commence_times`'s `kind=` filter."""
    kicks = _season_kickoffs(ctx, season)
    return _filter_uncaptured_kickoffs(kicks, captured_commence, now=now, buffer_min=buffer_min)


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
    kind: str = SNAPSHOT_KIND_CLOSE,
    source: str = ODDS_HISTORICAL_SOURCE,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
) -> set[str]:
    """Distinct `commence_time` values already captured for this season UNDER THIS SNAPSHOT KIND
    — a PURE lake read (zero CFBD/Odds calls). Empty set only if the partition genuinely doesn't
    exist yet (a season's first-ever run) — a transient read failure raises instead (see
    `_q_or_missing`).

    `kind` (P0.6c) scopes the read to one snapshot kind ("close" or "t_minus_1") so the close and
    T-1 capture paths diff independently — a kickoff already covered by a close snapshot still
    needs its OWN T-1 candidacy check, and vice versa. A row landed before P0.6c carries no
    `_snapshot_kind` field at all; it is implicitly a CLOSE snapshot (the only kind P0.6/P0.6b
    ever captured), so the SQL coalesces a missing field to `SNAPSHOT_KIND_CLOSE` rather than
    excluding those legacy rows from the close-kind set."""
    from .query_lake import delta, local

    expr = local(source, local_root) if local_root else delta(source)
    df = _q_or_missing(
        f"select distinct json_extract_string(raw_json,'$.commence_time') as ct "
        f"from {expr} where season = {int(season)} "
        f"and coalesce(json_extract_string(raw_json,'$._snapshot_kind'), '{SNAPSHOT_KIND_CLOSE}') "
        f"= '{kind}'"
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


def _tag_snapshot_kind(records: list[dict], kind: str) -> list[dict]:
    """Stamp `_snapshot_kind` (P0.6c) on every fetched record in place — "close" or "t_minus_1" —
    so the coverage diff (`_captured_commence_times(kind=...)`) and any downstream consumer can
    tell the two apart without inferring it from a snapshot-vs-commence time delta. Does NOT
    affect the merge dedup key: `_event_key` already keys on (id, `_requested_snapshot`), which
    differs between kinds by construction (5min vs `T1_BUFFER_MIN` buffers) — see the module
    docstring's correctness-crux note."""
    for r in records:
        r["_snapshot_kind"] = kind
    return records


def run_recurring_capture(
    season: int | None = None,
    *,
    ctx=None,
    weeks: list[int] | None = None,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
    buffer_min: int = 5,
    capture_t1: bool = False,
    t1_buffer_min: int = T1_BUFFER_MIN,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The P0.6b driver: figure out which kickoff(s) of `season` (default `current_season()`,
    clock-derived) are newly past their closing-snapshot instant and not yet lake-covered, fetch
    ONLY those (paid, leakage-safe), and merge them into the existing season partition without
    disturbing any previously-captured game.

    `weeks` TARGETS a specific CFBD week (or weeks) instead of auto-detecting the whole season —
    an operator override (e.g. to backfill/re-check a known gap for a PRIOR season). By DEFAULT
    (`force=False`) this still SKIPS whatever a targeted kickoff already has captured PER KIND —
    a `--weeks` backfill no longer silently re-buys credits for data already in the lake (fixed
    post-P0.6c: the original forced-weeks path unconditionally re-fetched, including the close,
    even when only adding a NEW kind like T-1 to an already-close-captured week). Pass
    `force=True` to bypass that skip and unconditionally re-fetch every kickoff `weeks` selects
    (e.g. to genuinely re-pull a known-BAD existing capture, not just fill a gap or add a kind).

    `capture_t1` (P0.6c, default OFF): ALSO snapshot each target kickoff `t1_buffer_min` minutes
    before kickoff (default `T1_BUFFER_MIN` = 1440 = ~24h) — the day-prior line-movement point.
    Roughly DOUBLES this run's paid Odds-API credit spend (a second `/historical` call per
    kickoff) — confirm against `ctx.credits_remaining` (or `--dry-run --capture-t1`) before
    turning this on. Defaults False so a plain call behaves EXACTLY like P0.6b (zero extra Odds
    calls) until a caller explicitly opts in — mirrors this whole module's `on_demand` /
    `default_status=STOPPED` gating (see the module docstring's "CREDIT GATING" note). The close
    and T-1 diffs run independently (each against its OWN `_captured_commence_times(kind=...)`
    set), so a kickoff can be captured for one kind, both, or neither on a given run.
    """
    season = int(season) if season is not None else current_season()
    if ctx is None:
        ctx = build_ctx()
    if ctx.cfbd is None:
        raise RuntimeError(
            "CFBD_API_KEY not set — the catch-up reads CFBD /games for kickoff times "
            "(leakage-safe snapshots + the lake-coverage diff)."
        )

    captured_close = _captured_commence_times(
        season, kind=SNAPSHOT_KIND_CLOSE, bucket=bucket, local_root=local_root
    )
    captured_t1 = (
        _captured_commence_times(season, kind=SNAPSHOT_KIND_T1, bucket=bucket, local_root=local_root)
        if capture_t1 else set()
    )

    if weeks is not None:
        kicks = _season_kickoffs(ctx, season, weeks=list(weeks))
        if force:
            close_targets = kicks
            t1_targets = kicks if capture_t1 else []
            log.info(
                "NCAAF odds recurring capture: season=%s FORCED weeks=%s force=True — "
                "re-fetching ALL %d kickoff(s) regardless of existing lake coverage%s",
                season, list(weeks), len(kicks),
                " (close + T-1)" if capture_t1 else " (close only)",
            )
        else:
            close_targets = _filter_uncaptured_kickoffs(
                kicks, captured_close, now=now, buffer_min=buffer_min
            )
            t1_targets = (
                _filter_uncaptured_kickoffs(kicks, captured_t1, now=now, buffer_min=t1_buffer_min)
                if capture_t1 else []
            )
            log.info(
                "NCAAF odds recurring capture: season=%s weeks=%s — %d/%d CLOSE kickoff(s) "
                "already captured (skipping those)%s. Pass force=True to re-fetch anyway.",
                season, list(weeks), len(kicks) - len(close_targets), len(kicks),
                (f"; {len(kicks) - len(t1_targets)}/{len(kicks)} T-1 already captured"
                 if capture_t1 else ""),
            )
    else:
        close_targets = _new_kickoffs_to_capture(
            ctx, season, captured_close, now=now, buffer_min=buffer_min
        )
        t1_targets = (
            _new_kickoffs_to_capture(ctx, season, captured_t1, now=now, buffer_min=t1_buffer_min)
            if capture_t1 else []
        )

    n_close = len(close_targets)
    n_t1 = len(t1_targets) if capture_t1 else None

    if not close_targets and not t1_targets:
        log.info(
            "NCAAF odds recurring capture: season=%s%s — nothing new to capture (close%s); "
            "0 credits.", season, f" weeks={list(weeks)}" if weeks is not None else "",
            " or T-1" if capture_t1 else "",
        )
        return {
            "season": season, "new_kickoffs": 0,
            "new_kickoffs_t1": (0 if capture_t1 else None),
            "forced_weeks": list(weeks) if weeks is not None else None, "rows_written": 0,
            "credits_used": ctx.credits_used, "credits_remaining": ctx.credits_remaining,
        }

    new_records: list[dict] = []
    if close_targets:
        log.info(
            "NCAAF odds recurring capture: season=%s — %d CLOSE kickoff(s) to snapshot",
            season, len(close_targets),
        )
        close_records = _odds_historical_for_kickoffs(ctx, close_targets, buffer_min=buffer_min)
        new_records.extend(_tag_snapshot_kind(close_records, SNAPSHOT_KIND_CLOSE))
    if t1_targets:
        log.info(
            "NCAAF odds recurring capture: season=%s — %d T-1 (day-prior) kickoff(s) to snapshot",
            season, len(t1_targets),
        )
        t1_records = _odds_historical_for_kickoffs(ctx, t1_targets, buffer_min=t1_buffer_min)
        new_records.extend(_tag_snapshot_kind(t1_records, SNAPSHOT_KIND_T1))

    rows = _merge_and_write(season, new_records, bucket=bucket, local_root=local_root)
    log.info(
        "  merged %d new row(s) into odds_ncaaf_historical/season=%s; credits used=%s "
        "remaining=%s", rows, season, ctx.credits_used, ctx.credits_remaining,
    )
    return {
        "season": season, "new_kickoffs": n_close, "new_kickoffs_t1": n_t1,
        "forced_weeks": list(weeks) if weeks is not None else None,
        "rows_written": rows, "credits_used": ctx.credits_used,
        "credits_remaining": ctx.credits_remaining,
    }


def _cli() -> None:
    p = argparse.ArgumentParser(
        description="NCAAF recurring in-season closing-line catch-up (P0.6b) + optional T-1 "
                    "day-prior line-movement capture (P0.6c)."
    )
    p.add_argument(
        "--season", type=int, default=None,
        help="season to catch up (default: current_season() — clock-derived, the in-progress "
             "NCAAF season)",
    )
    p.add_argument(
        "--weeks",
        help="comma list — TARGET this specific CFBD week (or weeks) instead of auto-detecting "
             "(an operator override, e.g. to backfill/re-check a known gap for a PRIOR season). "
             "By default still SKIPS whatever's already captured per kind (pass --force to "
             "re-fetch regardless).",
    )
    p.add_argument(
        "--force", action="store_true",
        help="with --weeks: re-fetch EVERY targeted kickoff unconditionally, even ones already "
             "captured (e.g. to genuinely re-pull a known-BAD existing capture). Default OFF — "
             "a --weeks run normally skips whatever's already in the lake per kind.",
    )
    p.add_argument("--regions", default="us", help="Odds-API regions (default us; incl. Bovada)")
    p.add_argument("--buffer-min", type=int, default=5, help="close snapshot = kickoff − buffer minutes")
    p.add_argument(
        "--capture-t1", action="store_true",
        help="P0.6c (default OFF): ALSO snapshot each target kickoff ~t1-buffer-min before "
             "kickoff (the day-prior line move). Roughly DOUBLES this run's paid Odds-API "
             "credit spend — confirm against the remaining balance first (--dry-run --capture-t1).",
    )
    p.add_argument(
        "--t1-buffer-min", type=int, default=T1_BUFFER_MIN,
        help=f"T-1 snapshot = kickoff − buffer minutes (default {T1_BUFFER_MIN} = ~24h); only "
             "used with --capture-t1",
    )
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
        captured_close = _captured_commence_times(
            season, kind=SNAPSHOT_KIND_CLOSE, bucket=args.bucket, local_root=args.local_root
        )
        captured_t1 = (
            _captured_commence_times(
                season, kind=SNAPSHOT_KIND_T1, bucket=args.bucket, local_root=args.local_root
            ) if args.capture_t1 else set()
        )
        if weeks_override is not None:
            kicks = _season_kickoffs(ctx, season, weeks=weeks_override)
            if args.force:
                close_target, t1_target = kicks, (kicks if args.capture_t1 else [])
            else:
                close_target = _filter_uncaptured_kickoffs(
                    kicks, captured_close, buffer_min=args.buffer_min
                )
                t1_target = (
                    _filter_uncaptured_kickoffs(kicks, captured_t1, buffer_min=args.t1_buffer_min)
                    if args.capture_t1 else []
                )
            log.info(
                "[dry-run] season=%s weeks=%s → %d kickoff(s) total; %d/%d CLOSE already "
                "captured%s%s", season, weeks_override, len(kicks),
                len(kicks) - len(close_target), len(kicks),
                (f"; {len(kicks) - len(t1_target)}/{len(kicks)} T-1 already captured"
                 if args.capture_t1 else ""),
                " (--force: re-fetching all regardless)" if args.force else "",
            )
            if not close_target and not t1_target:
                log.info("[dry-run] nothing new to capture for these weeks (0 credits).")
                return
            est_close = _estimate_credits(len(close_target), args.regions)
            est_t1 = _estimate_credits(len(t1_target), args.regions) if args.capture_t1 else {"credits": 0}
        else:
            close_target = _new_kickoffs_to_capture(
                ctx, season, captured_close, buffer_min=args.buffer_min
            )
            t1_target = (
                _new_kickoffs_to_capture(ctx, season, captured_t1, buffer_min=args.t1_buffer_min)
                if args.capture_t1 else []
            )
            log.info(
                "[dry-run] season=%s (clock-derived current_season=%s) — %d new CLOSE kickoff(s)"
                "%s to capture", season, current_season(), len(close_target),
                f", {len(t1_target)} new T-1 kickoff(s)" if args.capture_t1 else "",
            )
            if not close_target and not t1_target:
                log.info("[dry-run] nothing to capture right now (0 credits).")
                return
            est_close = _estimate_credits(len(close_target), args.regions)
            est_t1 = _estimate_credits(len(t1_target), args.regions) if args.capture_t1 else {"credits": 0}
        total = est_close["credits"] + est_t1["credits"]
        log.info(
            "ESTIMATED TOTAL ≈ %d credits — NO calls made (dry run): close=%s%s",
            total, est_close, (" t_minus_1=" + str(est_t1)) if args.capture_t1 else "",
        )
        return

    manifest = run_recurring_capture(
        season, ctx=ctx, weeks=weeks_override, bucket=args.bucket, local_root=args.local_root,
        buffer_min=args.buffer_min, capture_t1=args.capture_t1, t1_buffer_min=args.t1_buffer_min,
        force=args.force,
    )
    for k, v in manifest.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()

"""market_capture.py — TIME-CRITICAL Tue/Fri point-in-time NFL market snapshots.

⏰ WHY THIS CANNOT BE BACKFILLED. The Odds API's `/historical` endpoint is what the lake already
uses (`odds_nfl_historical`), and NFL-N0.4 deliberately snapshots it at `kickoff − 5min` — i.e.
the CLOSING line, because closing is what a CLV benchmark needs. That is the right capture for
CLV and the WRONG capture for a Tuesday model: a market feature in a Tuesday build must be the
market AS IT STOOD ON TUESDAY, and no amount of later fetching reconstructs that. (The historical
endpoint can serve a past instant, but only for instants inside the vendor's retained window and
only for the markets it retained — it is not a substitute for having looked.) So this leg fetches
the **LIVE** endpoint on a Tue/Fri cadence and stamps `capture_timestamp` at the moment of the
fetch. That stamp is the whole product: it is what makes an early-build market feature
BACKTESTABLE later.

CREDITS (the Odds API bills 10 × #markets × #regions per call):
  • GAME LINES (default): one `/odds` call = 10 × 3 markets × 1 region = **30 credits** per
    snapshot. Two snapshots a week × ~22 weeks ≈ **1,320 credits/season**. Negligible.
  • PLAYER PROPS (opt-in, `NFL_PIT_CAPTURE_PROPS=1`): props are the PER-EVENT endpoint, so a
    snapshot costs 10 × 12 markets × #events ≈ **120 cr/event ≈ 1,700 cr per slate snapshot**,
    i.e. **~75,000 credits/season** at two snapshots a week. That is a real budget decision, so
    it is OFF by default and must be turned on deliberately — the same `on_demand` discipline
    `ingest/sources.py` applies to the paid `/historical` feeds so a routine run can never
    silently burn the balance.

TIER: WARN. A missed snapshot loses that snapshot (it cannot be recovered), but it must never
fail a job — and the next cadence fire still captures. A zero-event capture during the season is
escalated, because "0 rows, no error" is this repo's silent-empty signature.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from . import store
from .schedule import current_season, read_schedule
from .timestamps import CaptureStamps, now_utc

log = logging.getLogger(__name__)

CAPTURE_SOURCE = "market"

#: Env gate for the per-event PROPS leg (default OFF — see the credit note above).
PROPS_ENV_FLAG = "NFL_PIT_CAPTURE_PROPS"

#: A snapshot taken this close to kickoff is CLOSING-tier and must never join an earlier
#: projection. Mirrors `leakage_guard.DEFAULT_CLOSING_WINDOW_MINUTES` so the phase this writer
#: STAMPS and the phase the guard ENFORCES cannot drift apart.
CLOSING_WINDOW_MINUTES = 240


def props_enabled() -> bool:
    return os.environ.get(PROPS_ENV_FLAG, "0").strip() == "1"


def classify_market_phase(capture_ts: datetime, kickoff_ts: datetime | None) -> str:
    """The market phase of a snapshot, from its distance to kickoff.

    Phases are what the leakage guard keys its LATE_MARKET_JOIN clause on, so they are computed
    from the two timestamps rather than from the cadence label — a Tuesday cron that slips to
    Sunday morning must produce a `closing` row, not a row labelled `open` because the cron is
    called "the Tuesday one".
    """
    if kickoff_ts is None:
        return "unknown"
    delta_h = (kickoff_ts - capture_ts).total_seconds() / 3600.0
    if delta_h < 0:
        return "inplay"
    if delta_h * 60 <= CLOSING_WINDOW_MINUTES:
        return "closing"
    if delta_h <= 36:
        return "gameday"
    if delta_h <= 96:
        return "late_week"
    return "open"


def _parse_commence(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _rows_for_events(events, *, now: datetime, cadence_label: str, market_tier: str,
                     kickoff_by_event: dict) -> list[dict]:
    rows: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        event_id = ev.get("id")
        if not event_id:
            continue
        kickoff = _parse_commence(ev.get("commence_time")) or kickoff_by_event.get(event_id)
        phase = classify_market_phase(now, kickoff)
        subject = f"{market_tier}|{event_id}"
        stamps = CaptureStamps.build(
            capture_source=CAPTURE_SOURCE,
            subject_key=subject,
            checkpoint=cadence_label,
            payload=ev,
            # The market's value is as-of the fetch: a live odds board has no earlier validity.
            feature_timestamp=now,
            capture_timestamp=now,
            # The API's own `last_update` lives per-bookmaker inside the payload, not on the
            # event, so there is no single event-level vendor as-of. Declared, not invented.
            source_timestamp=None,
            vendor_release_timestamp=None,
        )
        row = stamps.as_dict()
        row.update(
            {
                "record_tier": "market",
                "source_timestamp_absent_reason": (
                    "odds-api publishes `last_update` per bookmaker inside the payload, not at "
                    "event level; the per-book stamps are retained in the raw payload"
                ),
                "market_tier": market_tier,
                "event_id": event_id,
                "home_team": ev.get("home_team"),
                "away_team": ev.get("away_team"),
                "kickoff_timestamp": kickoff.isoformat() if kickoff else None,
                "market_phase": phase,
                "cadence_label": cadence_label,
                "hours_to_kickoff": (
                    round((kickoff - now).total_seconds() / 3600.0, 3) if kickoff else None
                ),
                "bookmaker_count": len(ev.get("bookmakers") or []),
                # The board itself is retained write-once in the raw payload; the tabular row
                # stays narrow so a reader does not have to parse JSON to filter a slate.
                "payload": ev,
            }
        )
        rows.append(row)
    return rows


def run_market_capture(
    season: int | None = None,
    *,
    cadence_label: str | None = None,
    now: datetime | None = None,
    capture_props: bool | None = None,
    bucket: str | None = None,
    local_root: str | None = None,
    dry_run: bool = False,
    odds_key: str | None = None,
    ctx=None,
    fetch_game_lines=None,
    fetch_props=None,
    kickoff_by_event: dict | None = None,
) -> dict:
    """Capture ONE point-in-time NFL market snapshot. Returns a manifest.

    `fetch_game_lines` / `fetch_props` are injectable so the stamping + phase-classification path
    is testable offline; by default they are the live Odds-API fetchers the lake already uses,
    so this leg and `ingest/sources.py` cannot drift in market list or region.
    """
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    cadence_label = cadence_label or f"{now.strftime('%a').lower()}-{now.strftime('%Y-%m-%d')}"
    capture_props = props_enabled() if capture_props is None else capture_props

    manifest = {
        "season": season, "cadence_label": cadence_label, "now": now.isoformat(),
        "capture_props": capture_props, "game_line_events": 0, "prop_events": 0,
        "written": 0, "skipped_duplicate": 0, "skipped_recapture": 0, "revisions": [],
        "errors": [], "escalate": False,
    }

    if dry_run:
        manifest["note"] = (
            "dry-run: would spend 30 credits (game lines)"
            + (" + ~120 credits/event (props)" if capture_props else "")
        )
        return manifest

    if fetch_game_lines is None or (capture_props and fetch_props is None):
        from ..ingest.sources import _odds_nfl, _odds_nfl_props, build_ctx

        ctx = ctx or build_ctx(odds_key=odds_key)
        fetch_game_lines = fetch_game_lines or (lambda: _odds_nfl(ctx, season))
        fetch_props = fetch_props or (lambda: _odds_nfl_props(ctx, season))

    kickoff_by_event = kickoff_by_event or {}
    rows: list[dict] = []

    try:
        events = fetch_game_lines() or []
        manifest["game_line_events"] = len(events)
        rows.extend(_rows_for_events(events, now=now, cadence_label=cadence_label,
                                     market_tier="game_lines", kickoff_by_event=kickoff_by_event))
    except Exception as exc:  # noqa: BLE001 — WARN tier: never sink the job
        manifest["errors"].append(f"game_lines: {exc}")
        log.warning("ALERT [nfl/pit/market] game-line snapshot FAILED: %s", exc)

    if capture_props:
        try:
            events = fetch_props() or []
            manifest["prop_events"] = len(events)
            rows.extend(_rows_for_events(events, now=now, cadence_label=cadence_label,
                                         market_tier="props", kickoff_by_event=kickoff_by_event))
        except Exception as exc:  # noqa: BLE001
            manifest["errors"].append(f"props: {exc}")
            log.warning("ALERT [nfl/pit/market] props snapshot FAILED: %s", exc)

    if rows:
        written = store.append_captures(
            rows, source=CAPTURE_SOURCE, bucket=bucket, local_root=local_root,
            # An odds board MOVES continuously: a re-read inside the same cadence label is not a
            # vendor revision. The first capture stands as that snapshot's point-in-time record.
            semantics=store.LIVE_VALUE_SEMANTICS,
        )
        manifest.update(
            {k: written[k] for k in ("written", "skipped_duplicate", "skipped_recapture", "revisions")}
        )
    else:
        manifest["escalate"] = True
        log.warning(
            "ALERT [nfl/pit/market] ZERO market events captured for the %s snapshot — this "
            "point-in-time board is LOST (only closing lines exist historically).", cadence_label,
        )
    return manifest


def upcoming_kickoffs(season: int, *, now: datetime | None = None, horizon_days: int = 10) -> dict:
    """`(home,away) -> kickoff` for the near slate, read FREE from nflverse schedules.

    Belt-and-braces for the phase classification: an Odds-API event whose `commence_time` is
    missing would otherwise classify `unknown`, and an unknown phase is UNEVALUABLE to the
    leakage guard — which rejects. Supplying the free kickoff keeps a good snapshot usable.
    """
    now = now or now_utc()
    out: dict = {}
    for g in read_schedule(season):
        if 0 <= (g.kickoff_utc - now).total_seconds() <= horizon_days * 86400:
            out[(g.home_team, g.away_team)] = g.kickoff_utc
    return out


__all__ = [
    "CAPTURE_SOURCE", "CLOSING_WINDOW_MINUTES", "PROPS_ENV_FLAG",
    "classify_market_phase", "props_enabled", "run_market_capture", "upcoming_kickoffs",
]

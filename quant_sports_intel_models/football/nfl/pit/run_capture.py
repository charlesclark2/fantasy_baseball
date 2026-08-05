"""run_capture.py — the ONE CLI/callable that drives every NF-W0a forward-capture leg.

    # hourly ladder capture (the leg the 2026-09-10 opener puts the clock on)
    uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture --leg weather

    # the weekly-build (Tuesday) forecast snapshot
    uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture \
        --leg weather --observation-type forecast_pregame

    # a Tue/Fri point-in-time market board (30 credits; props are opt-in via NFL_PIT_CAPTURE_PROPS)
    uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture --leg market

    # everything, offline, into a local Delta tree (no bucket, no creds, no paid calls)
    uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture \
        --leg all --dry-run --local-root /tmp/nfl_pit

Every leg is ALERT-loud-but-continue: one failing leg never sinks the others, because the legs
are independent captures of independent moments and a market outage must not cost the week's
weather. `escalate` in a leg's manifest is the signal a caller (the Dagster op) turns into a page.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from .schedule import current_season
from .timestamps import now_utc

log = logging.getLogger(__name__)

LEGS = ("weather", "market", "injuries", "schema")


def load_env() -> None:
    """Load a repo/cwd `.env` for standalone CLI runs (`uv run` does not auto-load it).
    Never overrides an already-set var, so the box/CI env wins. No-op without python-dotenv."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def run_legs(
    legs=LEGS,
    *,
    season: int | None = None,
    now: datetime | None = None,
    observation_type: str | None = None,
    checkpoint: int | None = None,
    cadence_label: str | None = None,
    bucket: str | None = None,
    local_root: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the named legs. Returns `{leg: manifest}` — each leg's failure is captured, not raised."""
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    out: dict = {}

    for leg in legs:
        try:
            if leg == "weather":
                from .weather_capture import OBS_INTRADAY, run_weather_capture

                out[leg] = run_weather_capture(
                    season, observation_type=observation_type or OBS_INTRADAY,
                    checkpoint=checkpoint, now=now, bucket=bucket, local_root=local_root,
                    dry_run=dry_run,
                )
            elif leg == "market":
                from .market_capture import run_market_capture

                out[leg] = run_market_capture(
                    season, cadence_label=cadence_label, now=now, bucket=bucket,
                    local_root=local_root, dry_run=dry_run,
                )
            elif leg == "injuries":
                from .injury_capture import run_injury_capture

                out[leg] = run_injury_capture(
                    season, now=now, cadence_label=cadence_label, bucket=bucket,
                    local_root=local_root, dry_run=dry_run,
                )
            elif leg == "schema":
                from .schema_snapshot import run_schema_snapshot

                out[leg] = run_schema_snapshot(
                    season, now=now, bucket=bucket, local_root=local_root, dry_run=dry_run,
                )
            else:
                raise ValueError(f"unknown leg {leg!r} (valid: {LEGS})")
        except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue, per leg
            log.warning("ALERT [nfl/pit] leg %s FAILED: %s", leg, exc)
            out[leg] = {"error": str(exc), "escalate": True}
    return out


def escalations(manifests: dict) -> list[str]:
    """The legs whose manifest asked to be paged about — the caller's page condition.

    ⭐ A leg whose manifest is ABSENT or unreadable counts as an escalation, not as silence: an
    unevaluable check is never scored healthy (NF1.7 (a)).
    """
    out = []
    for leg, m in manifests.items():
        if not isinstance(m, dict) or m.get("escalate") or m.get("error"):
            out.append(leg)
    return out


def _cli() -> None:
    p = argparse.ArgumentParser(description="NF-W0a NFL point-in-time forward capture.")
    p.add_argument("--leg", default="all", help=f"comma list of {LEGS}, or 'all'")
    p.add_argument("--season", type=int, help="default: the clock-derived current NFL season")
    p.add_argument("--observation-type", choices=("forecast_pregame", "forecast_intraday"),
                   help="weather leg only (default forecast_intraday = the ladder)")
    p.add_argument("--checkpoint", type=int,
                   help="weather leg: pin ONE ladder rung (hours-to-kickoff) instead of auto")
    p.add_argument("--cadence-label", help="market/injury leg: the snapshot label (default: day+date)")
    p.add_argument("--now", help="ISO-8601 UTC instant to treat as now (testing/replay)")
    p.add_argument("--bucket", help="override the sports lake bucket")
    p.add_argument("--local-root", help="write Delta + raw payloads to a local dir instead of S3")
    p.add_argument("--dry-run", action="store_true", help="decide + report, write nothing, spend nothing")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    load_env()

    legs = LEGS if args.leg == "all" else tuple(x.strip() for x in args.leg.split(","))
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00")).astimezone(timezone.utc)
        if args.now else None
    )
    manifests = run_legs(
        legs, season=args.season, now=now, observation_type=args.observation_type,
        checkpoint=args.checkpoint, cadence_label=args.cadence_label, bucket=args.bucket,
        local_root=args.local_root, dry_run=args.dry_run,
    )
    print(json.dumps(manifests, indent=2, default=str))
    esc = escalations(manifests)
    if esc:
        print(f"\nALERT — legs needing attention: {esc}")


if __name__ == "__main__":
    _cli()

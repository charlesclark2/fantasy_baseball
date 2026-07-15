"""handler.py  (NCAAF-P0.2 — the registry-driven ingest entrypoint)
====================================================================
ONE entrypoint that drives the `sources.py` registry. Runnable three ways so the scaffold
serves both the platform doc's original Lambda sketch AND the CURRENT cross-sport decision
(sport_data_platform.md §16.3: pulls run as **Dagster ops on the existing EC2 box**, NOT
Lambda+EventBridge — Dagster+ is gone, the box is unmetered):

  • `lambda_handler(event, ctx)`   — AWS Lambda shape (kept for the platform-doc sketch).
  • `run_ingest(...)`              — the plain callable a Dagster op / cron / test invokes.
  • `python -m ...ingest.handler`  — CLI for a manual box/laptop run.

Event/args: {sources?, seasons, weeks?, mode?}. Each (source, season) is fetched via its
registry `SourceSpec.fetch` and landed as ONE Delta season partition (idempotent overwrite).
Failures are per-source ALERT-loud-but-continue (one bad feed never sinks the batch) — the
platform's weekly-batch job is peripheral, not serving-critical (MLB WARN/ALERT tier).
"""
from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from . import s3io
from .sources import SOURCES, SPORT, build_ctx

log = logging.getLogger(__name__)


def load_env() -> None:
    """Load a repo/cwd `.env` into the environment for STANDALONE CLI runs (laptop backfills)
    so CFBD_API_KEY / ODDS_API_KEY don't have to be manually exported — `uv run` does NOT
    auto-load `.env`, and a fresh terminal won't have them (the 2026-07-16 laptop backfill:
    every CFBD/Odds source failed with cfbd=None / 'ODDS_API_KEY not set').

    No-op when python-dotenv is absent (the box container gets its env via docker env_file, not
    a repo .env) or no .env is found. NEVER overrides an already-set var, so the box/CI env wins.
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def _resolve_sources(names) -> list[str]:
    if not names:
        return list(SOURCES)
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s) {unknown}. Valid: {sorted(SOURCES)}")
    return list(names)


def run_ingest(
    seasons,
    *,
    sources=None,
    weeks=None,
    local_root: str | None = None,
    bucket: str = s3io.DEFAULT_BUCKET,
    cfbd_key: str | None = None,
    odds_key: str | None = None,
) -> dict[str, Any]:
    """Fetch + land each (source, season). Returns a manifest {source/season: rows|error}.

    `local_root` writes Delta to a local FS tree instead of S3 (offline smoke / pre-bucket
    dev). `weeks` scopes week-grained/per-game pulls (the smoke path; None = whole season).
    """
    src_names = _resolve_sources(sources)
    ctx = build_ctx(cfbd_key=cfbd_key, odds_key=odds_key)
    manifest: dict[str, Any] = {}

    for name in src_names:
        spec = SOURCES[name]
        for season in seasons:
            key = f"{name}/{season}"
            try:
                records = spec.fetch(ctx, int(season), weeks=weeks)
                part_season = int(season) if spec.season_scoped else 0
                n = s3io.write_records(
                    records, sport=SPORT, source=name, season=part_season,
                    bucket=bucket, local_root=local_root,
                )
                manifest[key] = n
                if not spec.season_scoped:
                    break  # not season-grained (nflverse_players): one write covers all
            except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (peripheral batch)
                log.warning("ALERT ingest failed for %s: %s", key, exc)
                manifest[key] = f"ERROR: {exc}"
    rem = getattr(ctx.cfbd, "last_calls_remaining", None) if ctx.cfbd else None
    if rem is not None:
        log.info("CFBD calls remaining this month: %s", rem)
    manifest["_cfbd_calls_remaining"] = rem
    return manifest


def lambda_handler(event: dict, _ctx=None) -> dict:
    """AWS Lambda entrypoint (kept for the platform-doc sketch; prod orchestration is a
    Dagster op calling run_ingest). event = {sport?, sources?, seasons, weeks?}."""
    return run_ingest(
        event["seasons"],
        sources=event.get("sources"),
        weeks=event.get("weeks"),
        bucket=event.get("bucket", s3io.DEFAULT_BUCKET),
    )


def _cli() -> None:
    p = argparse.ArgumentParser(description="NCAAF lakehouse ingest (registry-driven).")
    p.add_argument("--seasons", required=True, help="comma list or A-B range, e.g. 2024 or 2014-2025")
    p.add_argument("--sources", help="comma list of source names (default: all)")
    p.add_argument("--weeks", help="comma list to scope week-grained/per-game pulls (default: whole season)")
    p.add_argument("--local-root", help="write Delta to this local dir instead of S3 (offline dev)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # pick up CFBD_API_KEY / ODDS_API_KEY from .env for standalone runs
    seasons = _parse_seasons(args.seasons)
    sources = args.sources.split(",") if args.sources else None
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None
    manifest = run_ingest(seasons, sources=sources, weeks=weeks,
                          local_root=args.local_root, bucket=args.bucket)
    for k, v in manifest.items():
        print(f"  {k}: {v}")


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


if __name__ == "__main__":
    _cli()

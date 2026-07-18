"""handler.py  (NFL-N0.2 — the registry-driven ingest entrypoint)
=================================================================
ONE entrypoint that drives the `sources.py` registry. Runnable three ways (mirrors NCAAF-P0.2
so the scaffold serves the platform-doc Lambda sketch AND the CURRENT cross-sport decision —
sport_data_platform.md §16.3: pulls run as **Dagster ops on the existing EC2 box**, NOT
Lambda+EventBridge — Dagster+ is gone, the box is unmetered):

  • `lambda_handler(event, ctx)`   — AWS Lambda shape (kept for the platform-doc sketch).
  • `run_ingest(...)`              — the plain callable a Dagster op / cron / test invokes.
  • `python -m ...ingest.handler`  — CLI for a manual box/laptop run.

Each (source, season) is fetched via its registry `SourceSpec.fetch` and landed as ONE Delta
season partition (idempotent overwrite). The write path forks on `spec.typed`: nflverse feeds
return a typed DataFrame → `s3io.write_dataframe`; Odds API feeds return `list[dict]` →
`s3io.write_records` (raw_json). Failures are per-source ALERT-loud-but-continue (one bad feed
never sinks the batch) — the weekly-batch job is peripheral, not serving-critical (MLB
WARN/ALERT tier).
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
    so ODDS_API_KEY doesn't have to be manually exported — `uv run` does NOT auto-load `.env`.
    No-op when python-dotenv is absent (the box container gets its env via docker env_file) or
    no `.env` is found. NEVER overrides an already-set var, so the box/CI env wins."""
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


def _land(spec, records_or_df, *, season: int, bucket: str, local_root: str | None) -> int:
    """Write ONE fetched (source, season) slice to Delta, forking on the feed's typing."""
    if spec.typed:
        return s3io.write_dataframe(
            records_or_df, sport=SPORT, source=spec.name, season=season,
            bucket=bucket, local_root=local_root,
        )
    return s3io.write_records(
        records_or_df, sport=SPORT, source=spec.name, season=season,
        bucket=bucket, local_root=local_root,
    )


def run_ingest(
    seasons,
    *,
    sources=None,
    weeks=None,
    local_root: str | None = None,
    bucket: str = s3io.DEFAULT_BUCKET,
    odds_key: str | None = None,
    ctx=None,
    skip_existing: bool = False,
) -> dict[str, Any]:
    """Fetch + land each (source, season). Returns a manifest {source/season: rows|error}.

    `local_root` writes Delta to a local FS tree instead of S3 (offline smoke / pre-bucket dev).
    `ctx` lets a caller REUSE one DuckDB connection across seasons (the backfill passes a single
    ctx so the httpfs connection + cache persist). `skip_existing` skips any (source, season)
    whose Delta partition already exists — a pure S3/metadata check (ZERO network fetches) so a
    resumed backfill doesn't re-pull landed seasons."""
    src_names = _resolve_sources(sources)
    if ctx is None:
        ctx = build_ctx(odds_key=odds_key)
    manifest: dict[str, Any] = {}

    for name in src_names:
        spec = SOURCES[name]
        present = (
            s3io.existing_seasons(SPORT, name, bucket=bucket, local_root=local_root)
            if skip_existing else set()
        )
        for season in seasons:
            key = f"{name}/{season}"
            part_season = int(season) if spec.season_scoped else 0
            if skip_existing and part_season in present:
                manifest[key] = "skipped (already ingested)"
                log.info("  [%s/%s] already ingested — skip (no fetch)", name, season)
                if not spec.season_scoped:
                    break
                continue
            try:
                fetched = spec.fetch(ctx, int(season), weeks=weeks)
                n = _land(spec, fetched, season=part_season, bucket=bucket, local_root=local_root)
                manifest[key] = n
                if not spec.season_scoped:
                    break  # not season-grained (nflverse_players): one write covers all
            except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (peripheral batch)
                log.warning("ALERT ingest failed for %s: %s", key, exc)
                manifest[key] = f"ERROR: {exc}"
    return manifest


def lambda_handler(event: dict, _ctx=None) -> dict:
    """AWS Lambda entrypoint (kept for the platform-doc sketch; prod orchestration is a Dagster
    op calling run_ingest). event = {sources?, seasons, weeks?, bucket?}."""
    return run_ingest(
        event["seasons"],
        sources=event.get("sources"),
        weeks=event.get("weeks"),
        bucket=event.get("bucket", s3io.DEFAULT_BUCKET),
    )


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


def _cli() -> None:
    p = argparse.ArgumentParser(description="NFL lakehouse ingest (registry-driven).")
    p.add_argument("--seasons", required=True, help="comma list or A-B range, e.g. 2025 or 2016-2025")
    p.add_argument("--sources", help="comma list of source names (default: all)")
    p.add_argument("--weeks", help="(reserved) scope for week-grained pulls; nflverse reads whole seasons")
    p.add_argument("--local-root", help="write Delta to this local dir instead of S3 (offline dev)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--skip-existing", action="store_true",
                   help="skip (source, season) partitions already landed (zero fetches)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # pick up ODDS_API_KEY from .env for standalone runs
    seasons = _parse_seasons(args.seasons)
    sources = args.sources.split(",") if args.sources else None
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None
    manifest = run_ingest(seasons, sources=sources, weeks=weeks,
                          local_root=args.local_root, bucket=args.bucket,
                          skip_existing=args.skip_existing)
    for k, v in manifest.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()

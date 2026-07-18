"""odds_backfill.py  (NFL-N0.4 — the PAID Odds-API historical/props runner)
===========================================================================
The credit-aware driver for the NET-NEW betting-market data the old stack LACKS — the leakage-
safe CLOSING lines (for CLV) + the DEEP player props. It is SEPARATE from `backfill.py` (the
free nflverse re-pull) because these feeds hit the **paid** Odds-API `/historical` path and the
per-event props endpoint — a plain nflverse backfill must never trigger that credit burn, so the
odds sources are `on_demand=True` in the registry and only ever named explicitly, here.

Three on_demand sources (registry `sources.py`), all landed as raw_json Delta on the shared lake
(`s3://credence-sports-lakehouse/nfl/raw/<source>/season=YYYY/`) via the same `run_ingest` write
path as everything else:
  • odds_nfl_props              — CURRENT player props (event endpoint; no historical floor).
  • odds_nfl_historical         — paid /historical CLOSING game lines (h2h/spread/total), the
                                  leakage-safe CLV benchmark. Floor 2020 (N0.1 §3).
  • odds_nfl_props_historical   — paid /historical CLOSING player props (CLV/props backtest).
                                  COST-HEAVY (per-event × per-snapshot) — scope deliberately.

LEAKAGE-SAFE CLOSE (the AC): for each distinct season kickoff K (read FREE from nflverse
schedules), the historical snapshot is taken at K−buffer, so the captured market is strictly
pre-kickoff. Every row also carries the API's own `commence_time` + `_snapshot_ts`, so the
Phase-1 CLV mart enforces the hard guard (keep only snapshot_ts < commence_time).

CREDIT ACCOUNTING (the AC): `--dry-run` reads the schedules (free) to count kickoffs/events and
prints the credit estimate WITHOUT firing a paid call; a live run reports the x-requests-used /
-remaining the API returns. Odds-API cost model = 10 × #markets × #regions per call
(`backfill_multisport_odds_to_s3` note). Rough per-season:
  • historical game lines: ~90 kickoffs × 10 × 3 markets × 1 region  ≈  2,700 cr
  • historical props:      ~285 events × 10 × 12 markets × 1 region   ≈ 34,200 cr  ← the heavy one

USAGE (all >1 min for a full season → hand the LIVE ones to the operator; --dry-run is instant):
  # Instant credit estimate (no API calls), historical game lines 2020-2024:
  uv run python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
      --sources odds_nfl_historical --seasons 2020-2024 --dry-run

  # Tiny live VERIFICATION pull (proves the path; caps events/snapshot), one week:
  uv run python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
      --sources odds_nfl_historical --seasons 2024 --weeks 1 --max-events 3

  # BOX — full historical game-line backfill (operator; resumable via --skip-existing):
  docker compose -f services/dagster/aws/docker-compose.yml exec -T \
      -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
      python -m quant_sports_intel_models.football.nfl.ingest.odds_backfill \
      --sources odds_nfl_historical --seasons 2020-2024 --skip-existing

Idempotent: each season is a Delta partition overwrite (resume with --skip-existing to skip
seasons already landed — a pure S3 check, zero fetches, zero credits).
"""
from __future__ import annotations

import argparse
import logging

from . import s3io
from .handler import _parse_seasons, load_env, run_ingest
from .sources import (
    NFL_GAME_LINE_MARKETS,
    NFL_PROP_MARKETS,
    ODDS_ON_DEMAND,
    SOURCES,
    build_ctx,
)

log = logging.getLogger(__name__)

# The Odds-API historical floor for NFL (N0.1 §3 — 6-season CLV window). The CURRENT-season
# live feeds (odds_nfl / odds_nfl_props) are cadence-driven, not backfilled here.
DEFAULT_HIST_SEASONS = "2020-2024"
CREDITS_PER_CALL_PER_MARKET_REGION = 10  # Odds-API cost model: 10 × #markets × #regions per call


def _estimate_credits(ctx, source: str, seasons, weeks, regions: str, prop_markets) -> dict:
    """FREE credit estimate — reads nflverse schedules (no paid call) to count the kickoff
    snapshots / events each season would fire, then applies the 10×markets×regions cost model."""
    from .sources import _season_kickoffs, _season_game_count  # local import (test-friendly)

    n_regions = len([r for r in regions.split(",") if r])
    per_season: dict[int, dict] = {}
    total = 0
    for yr in seasons:
        n_kicks = len(_season_kickoffs(ctx, yr, weeks=weeks))
        if source == "odds_nfl_historical":
            n_markets = len(NFL_GAME_LINE_MARKETS.split(","))
            cr = n_kicks * CREDITS_PER_CALL_PER_MARKET_REGION * n_markets * n_regions
            per_season[yr] = {"kickoff_snapshots": n_kicks, "markets": n_markets, "credits": cr}
        elif source == "odds_nfl_props_historical":
            # per-event props call (10×markets×regions) is the dominant cost; #events ≈ #games.
            n_games = _season_game_count(ctx, yr, weeks=weeks)
            n_markets = len(prop_markets)
            cr = n_games * CREDITS_PER_CALL_PER_MARKET_REGION * n_markets * n_regions
            per_season[yr] = {"kickoff_snapshots": n_kicks, "games": n_games,
                              "markets": n_markets, "credits": cr}
        else:  # odds_nfl_props (current) — one events call + N event-odds calls
            per_season[yr] = {"note": "current feed — event count known only at fetch time",
                              "markets": len(prop_markets), "credits": None}
            continue
        total += per_season[yr]["credits"]
    return {"per_season": per_season, "total_credits": total}


def main() -> None:
    p = argparse.ArgumentParser(description="NFL PAID Odds-API historical/props backfill (N0.4).")
    p.add_argument("--sources", default="odds_nfl_historical",
                   help=f"comma list from {ODDS_ON_DEMAND} (default: odds_nfl_historical)")
    p.add_argument("--seasons", default=DEFAULT_HIST_SEASONS,
                   help=f"comma list or A-B range (default {DEFAULT_HIST_SEASONS}; NFL /historical floor=2020)")
    p.add_argument("--weeks", help="scope to these week(s) (comma list) — a small verification pull")
    p.add_argument("--regions", default="us", help="Odds-API regions (default us; US books incl. Bovada)")
    p.add_argument("--markets", help="override the prop-market set (comma list; props sources only)")
    p.add_argument("--buffer-min", type=int, default=5,
                   help="snapshot = kickoff − buffer minutes (leakage-safe close; default 5)")
    p.add_argument("--sleep", type=float, default=0.5, help="inter-call sleep seconds (429 cushion)")
    p.add_argument("--max-events", type=int,
                   help="cap events/snapshot — the small verification pull (default: no cap = full)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (dry dev)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--skip-existing", action="store_true",
                   help="skip (source, season) partitions already landed (resume; zero fetches/credits)")
    p.add_argument("--dry-run", action="store_true",
                   help="estimate credits from the FREE schedules read; make NO paid API calls")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # ODDS_API_KEY (the MAIN key — /historical needs it) from .env for standalone runs

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in SOURCES or not SOURCES[s].on_demand]
    if unknown:
        raise SystemExit(f"--sources must be on_demand odds source(s) {ODDS_ON_DEMAND}; got {unknown}")
    seasons = _parse_seasons(args.seasons)
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None
    prop_markets = tuple(m.strip() for m in args.markets.split(",")) if args.markets else NFL_PROP_MARKETS

    ctx = build_ctx(regions=args.regions, prop_markets=prop_markets,
                    snapshot_buffer_min=args.buffer_min, sleep_seconds=args.sleep,
                    max_events=args.max_events)

    if args.dry_run:
        log.info("DRY RUN — credit estimate (FREE schedules read; NO paid calls)")
        grand = 0
        for src in sources:
            est = _estimate_credits(ctx, src, seasons, weeks, args.regions, prop_markets)
            log.info("  %s:", src)
            for yr, d in est["per_season"].items():
                log.info("    season %s: %s", yr, d)
            if est["total_credits"]:
                log.info("    → %s subtotal ≈ %d credits", src, est["total_credits"])
                grand += est["total_credits"]
        log.info("ESTIMATED TOTAL ≈ %d credits (2020+ floor; the props-historical figure is the "
                 "heavy one — scope seasons/markets before firing).", grand)
        return

    log.info("Odds backfill (PAID) sources=%s seasons=%s weeks=%s regions=%s → %s",
             sources, seasons, weeks, args.regions,
             args.local_root or f"s3://{args.bucket}/nfl/raw")
    total = {}
    for season in seasons:
        manifest = run_ingest([season], sources=sources, weeks=weeks,
                              local_root=args.local_root, bucket=args.bucket, ctx=ctx,
                              skip_existing=args.skip_existing)
        total.update(manifest)
        landed = sum(1 for v in manifest.values() if isinstance(v, int) and v > 0)
        log.info("  season %s done (%d landed); credits used=%s remaining=%s",
                 season, landed, ctx.credits_used, ctx.credits_remaining)

    landed = [k for k, v in total.items() if isinstance(v, int) and v > 0]
    empty = [k for k, v in total.items() if isinstance(v, int) and v == 0]
    skipped = [k for k, v in total.items() if isinstance(v, str) and v.startswith("skipped")]
    errs = [k for k, v in total.items() if isinstance(v, str) and v.startswith("ERROR")]
    log.info("Odds backfill complete: %d landed, %d empty, %d skipped, %d ERRORS%s. "
             "Final credits remaining=%s",
             len(landed), len(empty), len(skipped), len(errs),
             (": " + ", ".join(errs)) if errs else "", ctx.credits_remaining)


if __name__ == "__main__":
    main()

"""odds_backfill.py  (NCAAF-P0.6 — the PAID Odds-API historical closing-line runner)
=====================================================================================
The credit-aware driver for the NET-NEW betting-market data the NCAAF stack LACKS — the
leakage-safe CLOSING game lines (for CLV). It is SEPARATE from `backfill.py` (the free
CFBD/nflverse pull) because this feed hits the **paid** Odds-API `/historical` path — a plain
data backfill must never trigger that credit burn, so the source is `on_demand=True` in the
registry (`sources.py`) and only ever named explicitly, here.

⚠️ WHY THIS EXISTS (P0.2's flag): the P0.2 `odds_ncaaf` feed is CURRENT odds fetched live and
mis-tagged `season=YYYY` — it is NOT historical closing lines. Without real closing lines there
is NO market benchmark + NO CLV → this GATES P1.4's vs-market eval + all of Phase 2 (sharp-
anchor / microstructure). This runner lands inventory §8 table #21 `odds_ncaaf_historical`.

One on_demand source (`sources.py`), landed as raw_json Delta on the shared lake
(`s3://credence-sports-lakehouse/ncaaf/raw/odds_ncaaf_historical/season=YYYY/`) via the same
`run_ingest` write path as everything else:
  • odds_ncaaf_historical — paid /historical CLOSING game lines (h2h/spread/total), the
                            leakage-safe CLV benchmark. Floor 2020 (P0.1 §3 + N0.4-confirmed).
NCAAF player PROPS are THIN + carry a harder 2023 vendor floor → NOT pulled here (GAME LINES
ONLY, per P0.6).

LEAKAGE-SAFE CLOSE (the AC): for each distinct FBS kickoff K (read from CFBD `/games.startDate`,
already UTC — no paid Odds call), the historical snapshot is taken at K−buffer, so the captured
market is strictly pre-kickoff. Every row also carries the API's own `commence_time` +
`_snapshot_ts`, so the Phase-1 CLV mart enforces the hard guard (keep only snapshot_ts <
commence_time) belt-and-suspenders.

CREDIT ACCOUNTING (the AC): `--dry-run` reads the CFBD schedule (a flat-subscription call, NOT a
paid Odds credit) to count kickoffs/season and prints the credit estimate WITHOUT firing a paid
Odds call; a live run reports the x-requests-used / -remaining the API returns. Odds-API cost
model = 10 × #markets × #regions per call. NCAAF slates are DENSER than the NFL (many staggered
college start times) so per-season kickoff counts — hence credits — run materially higher than
the NFL's ~90/season; ALWAYS `--dry-run` first and scope seasons before firing.

⚙️ RUN THIS ON THE LAPTOP (repo root), NOT the box. It is a one-time, I/O-bound paid pull
(Odds-API calls with inter-call sleeps + raw-JSON Delta writes) — zero heavy compute — so it
should NOT compete with the box's live serving resources. The laptop has everything it needs:
`load_env()` picks up ODDS_API_KEY (the MAIN key) + CFBD_API_KEY from `.env`, and the S3 Delta
write resolves AWS creds through the botocore chain (env / `~/.aws` profile) with the region
defaulting to us-east-2 (`SPORTS_LAKE_REGION`) — no box instance role / `AWS_DEFAULT_REGION`
export needed.

USAGE (a full season is >1 min → hand the LIVE runs to the operator; --dry-run is quick):
  # Credit estimate (reads CFBD schedule; NO paid Odds calls), 2020-2024:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_backfill \
      --seasons 2020-2024 --dry-run

  # Tiny live VERIFICATION pull (proves the path; caps snapshots), week 1 of 2024:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_backfill \
      --seasons 2024 --weeks 1 --max-events 3

  # LAPTOP — full historical game-line backfill (resumable via --skip-existing):
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.odds_backfill \
      --seasons 2020-2024 --skip-existing

Idempotent: each season is a Delta partition overwrite (resume with --skip-existing to skip
seasons already landed — a pure S3 check, zero fetches, zero credits).
"""
from __future__ import annotations

import argparse
import logging

from . import s3io
from .handler import _parse_seasons, load_env, run_ingest
from .sources import (
    NCAAF_GAME_LINE_MARKETS,
    NCAAF_HISTORICAL_FLOOR,
    ODDS_ON_DEMAND,
    SOURCES,
    build_ctx,
)

log = logging.getLogger(__name__)

DEFAULT_HIST_SEASONS = "2020-2024"
CREDITS_PER_CALL_PER_MARKET_REGION = 10  # Odds-API cost model: 10 × #markets × #regions per call


def _estimate_credits(ctx, seasons, weeks, regions: str) -> dict:
    """FREE credit estimate — reads the CFBD schedule (a flat-subscription call, NOT a paid Odds
    credit) to count the distinct FBS kickoff snapshots each season would fire, then applies the
    10 × markets × regions cost model. A season below `NCAAF_HISTORICAL_FLOOR` is a clean skip."""
    from .sources import _season_kickoffs  # local import (test-friendly)

    n_regions = len([r for r in regions.split(",") if r])
    n_markets = len(NCAAF_GAME_LINE_MARKETS.split(","))
    per_season: dict[int, dict] = {}
    total = 0
    for yr in seasons:
        if yr < NCAAF_HISTORICAL_FLOOR:
            per_season[yr] = {"below_floor": NCAAF_HISTORICAL_FLOOR,
                              "note": f"no historical odds pre-{NCAAF_HISTORICAL_FLOOR} → SKIPPED",
                              "credits": 0}
            continue
        n_kicks = len(_season_kickoffs(ctx, yr, weeks=weeks))
        cr = n_kicks * CREDITS_PER_CALL_PER_MARKET_REGION * n_markets * n_regions
        per_season[yr] = {"kickoff_snapshots": n_kicks, "markets": n_markets, "credits": cr}
        total += cr
    return {"per_season": per_season, "total_credits": total}


def main() -> None:
    p = argparse.ArgumentParser(description="NCAAF PAID Odds-API historical closing-line backfill (P0.6).")
    p.add_argument("--sources", default="odds_ncaaf_historical",
                   help=f"comma list from {ODDS_ON_DEMAND} (default: odds_ncaaf_historical)")
    p.add_argument("--seasons", default=DEFAULT_HIST_SEASONS,
                   help=f"comma list or A-B range (default {DEFAULT_HIST_SEASONS}; NCAAF /historical floor="
                        f"{NCAAF_HISTORICAL_FLOOR})")
    p.add_argument("--weeks", help="scope to these week(s) (comma list) — a small verification pull")
    p.add_argument("--regions", default="us", help="Odds-API regions (default us; US books incl. Bovada)")
    p.add_argument("--buffer-min", type=int, default=5,
                   help="snapshot = kickoff − buffer minutes (leakage-safe close; default 5)")
    p.add_argument("--sleep", type=float, default=0.5, help="inter-call sleep seconds (429 cushion)")
    p.add_argument("--max-events", type=int,
                   help="cap kickoff snapshots/season — the small verification pull (default: no cap = full)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (dry dev)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--skip-existing", action="store_true",
                   help="skip (source, season) partitions already landed (resume; zero fetches/credits)")
    p.add_argument("--dry-run", action="store_true",
                   help="estimate credits from the FREE CFBD schedule read; make NO paid Odds calls")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # ODDS_API_KEY (the MAIN key — /historical needs it) + CFBD_API_KEY (kickoffs) from .env

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in SOURCES or not SOURCES[s].on_demand]
    if unknown:
        raise SystemExit(f"--sources must be on_demand odds source(s) {ODDS_ON_DEMAND}; got {unknown}")
    seasons = _parse_seasons(args.seasons)
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None

    # build_ctx picks up CFBD_API_KEY from env → the CFBD client `_season_kickoffs` needs.
    ctx = build_ctx(regions=args.regions, snapshot_buffer_min=args.buffer_min,
                    sleep_seconds=args.sleep, max_events=args.max_events)
    if ctx.cfbd is None:
        raise SystemExit("CFBD_API_KEY not set — the /historical pull reads CFBD /games for kickoff "
                         "times (leakage-safe snapshots). Provision it (the free tier suffices here).")

    if args.dry_run:
        log.info("DRY RUN — credit estimate (FREE CFBD schedule read; NO paid Odds calls)")
        grand = 0
        for src in sources:
            est = _estimate_credits(ctx, seasons, weeks, args.regions)
            log.info("  %s:", src)
            for yr, d in est["per_season"].items():
                log.info("    season %s: %s", yr, d)
            if est["total_credits"]:
                log.info("    → %s subtotal ≈ %d credits", src, est["total_credits"])
                grand += est["total_credits"]
        log.info("ESTIMATED TOTAL ≈ %d credits (floor %d; NCAAF slates are DENSE — scope seasons "
                 "before firing).", grand, NCAAF_HISTORICAL_FLOOR)
        return

    log.info("Odds backfill (PAID) sources=%s seasons=%s weeks=%s regions=%s → %s",
             sources, seasons, weeks, args.regions,
             args.local_root or f"s3://{args.bucket}/ncaaf/raw")
    total = {}
    for season in seasons:
        manifest = run_ingest([season], sources=sources, weeks=weeks,
                              local_root=args.local_root, bucket=args.bucket, ctx=ctx,
                              skip_existing=args.skip_existing)
        total.update({k: v for k, v in manifest.items() if not k.startswith("_")})
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

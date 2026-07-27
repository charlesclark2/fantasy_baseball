"""run_contract_ingest.py — NF-D8 CONTRACT/FINANCIAL feature source: probe + coverage + landing.

No §0.5 bake-off here (NF-D8 carries no 🔬 tag) — this is a DATA story: the deliverable is the
reusable `contract_source.load_contract_features(season)` + a live availability probe + a
coverage/face-validity report, not a modeling ablation (NF1.2/NF1.5 own that gate downstream).

  --probe          live-fetch the nflverse contracts release + report shape/coverage/vocabulary
                   (PROBE, don't code to docs — catches an upstream schema drift immediately).
  --season/--coverage   build one season's features + the join-match-rate report (needs the
                   sports.duckdb for the fct_player_week crosswalk check).
  --land SEASON [--s3 | --lake-root ROOT]   compute + land one season to the lake.
  --land-range --from Y1 --to Y2 [--s3 | --lake-root ROOT]   land every season in the range (the
                   NF1.2/NF1.5 backtest needs multiple historical seasons, not just the current
                   board year).

RUN (LAPTOP):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_contract_ingest --probe

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_contract_ingest \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --season 2026 --coverage

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_contract_ingest \
      --land-range --from 2017 --to 2026 --s3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import contract_source as C  # noqa: E402

log = logging.getLogger("nfl.fantasy.contract_ingest")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"

# The contracts dataset's own observed season floor/ceiling (2017–2026 per --probe); the NF1.2/
# NF1.5 backtest range this module lands by default when --land-range is passed with no --from/--to.
DEFAULT_LAND_FROM, DEFAULT_LAND_TO = 2017, 2026


def probe() -> int:
    """Live availability probe: fetch the nflverse contracts release fresh, report shape,
    `gsis_id` coverage, position vocabulary, and any team nickname our crosswalk doesn't
    recognize (printed, not asserted — an upstream schema drift is visible immediately rather
    than silently mis-parsed downstream)."""
    raw = C.fetch_historical_contracts(refresh=True)
    print(f"source: {C.CONTRACTS_URL}")
    print(f"historical_contracts: {len(raw)} contracts, {len(raw.columns)} columns")
    print(f"columns: {list(raw.columns)}")
    print(f"gsis_id coverage (all-time): {raw['gsis_id'].notna().mean():.3f}")
    print(f"positions: {sorted(raw['position'].dropna().unique())}")

    flat = C.flatten_contract_years(raw)
    print(f"flattened year-rows: {len(flat)}; year range {int(flat['year'].min())}-"
          f"{int(flat['year'].max())}")

    unmapped = set()
    for arr in raw["cols"]:
        if arr is None:
            continue
        for r in arr:
            t = r.get("team")
            if t and t != "Total" and C.team_abbr(t) is None:
                unmapped.add(t)
    print(f"unmapped team nicknames: {sorted(unmapped) or 'none'}")
    return 0


def _season_report(con, season: int, *, cache_dir=None, refresh: bool = False,
                   contracts=None) -> dict:
    player, team = C.build_contract_features(season, cache_dir=cache_dir, refresh=refresh,
                                             contracts=contracts)
    cov = C.coverage_report(con, player, season) if con is not None else {
        "season": season, "n_contract_rows": len(player), "note": "no DuckDB — crosswalk skipped"}
    top_ol = team.sort_values("team_ol_cap_total", ascending=False).head(5)[
        ["team_abbr", "team_ol_cap_total", "team_ol_cap_pct"]].round(2).to_dict("records")
    top_conc = team.dropna(subset=["team_skill_cap_concentration"]).sort_values(
        "team_skill_cap_concentration", ascending=False).head(5)[
        ["team_abbr", "team_skill_cap_concentration", "team_skill_cap_total"]].round(3).to_dict("records")
    return {"coverage": cov, "n_teams": len(team), "top_ol_cap_teams": top_ol,
           "top_skill_concentration_teams": top_conc}


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-D8 — Contract / financial feature source (salary as a team-investment proxy)")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()}. Data source: nflverse's "
      f"`historical_contracts.parquet` release (CC-BY-4.0), NOT a direct OverTheCap/Spotrac "
      f"scrape — see the disposition note below. Edge-independent, `best_alpha=0` — a "
      f"projection FEATURE for NF1.2/NF1.5, not an edge claim.")
    p("")
    probe_out = out["probe"]
    p("## 1. Dataset probe")
    p("")
    p(f"- {probe_out['n_contracts']} contracts, `gsis_id` coverage (all-time) "
      f"{probe_out['gsis_coverage']:.3f}")
    p(f"- positions: {probe_out['positions']}")
    p(f"- unmapped team nicknames: {probe_out['unmapped_teams']}")
    p("")
    p("## 2. Per-season coverage + face-validity")
    p("")
    p("Join match-rate = our skill-position (QB/RB/WR/TE) `fct_player_week` universe matched to "
      "a contract row for that season (the `sport_data_platform.md` crosswalk check).")
    p("")
    p("| season | contract rows | skill players (ours) | matched | % matched | QB | RB | WR | TE |")
    p("|--------|---------------|-----------------------|---------|-----------|----|----|----|----|")
    for season, r in out["seasons"].items():
        cov = r["coverage"]
        bp = cov.get("match_rate_by_position", {})
        p(f"| {season} | {cov.get('n_contract_rows', '—')} | "
          f"{cov.get('n_skill_players_ours', '—')} | {cov.get('n_matched', '—')} | "
          f"{cov.get('pct_matched', '—')} | {bp.get('QB', '—')} | {bp.get('RB', '—')} | "
          f"{bp.get('WR', '—')} | {bp.get('TE', '—')} |")
    p("")
    latest = max(out["seasons"])
    lr = out["seasons"][latest]
    p(f"### Face-validity ({latest}) — top O-line cap investment")
    p("")
    p("| team | O-line cap ($M) | % of team cap |")
    p("|------|-----------------|---------------|")
    for row in lr["top_ol_cap_teams"]:
        p(f"| {row['team_abbr']} | {row['team_ol_cap_total']} | {row['team_ol_cap_pct']} |")
    p("")
    p(f"### Face-validity ({latest}) — most cap-CONCENTRATED skill-position rooms (HHI)")
    p("")
    p("| team | skill-cap HHI | skill cap total ($M) |")
    p("|------|---------------|------------------------|")
    for row in lr["top_skill_concentration_teams"]:
        p(f"| {row['team_abbr']} | {row['team_skill_cap_concentration']} | "
          f"{row['team_skill_cap_total']} |")
    p("")
    p("## 3. Honest gaps")
    p("")
    p("- A rookie drafted for a projection season may not yet appear in the nflverse contracts "
      "release if it hasn't been refreshed since the draft — a preseason board built too early "
      "in the cycle will show that player with no contract row (NaN features, not a fabricated "
      "0). Re-run `--refresh` closer to Week 1.")
    p("- `gsis_id` is null for ~8% of all-time contract rows (mostly non-skill positions / very "
      "old / retired players outside our skill-position universe) — the join-match-rate table "
      "above is the number that actually matters (QB/RB/WR/TE, current era).")
    p("- Mid-season restructures are not captured intra-season — this is a snapshot read at "
      "ingest time, not a point-in-time-versioned history; a restructure changes a future year's "
      "cap number, which the next `--refresh` will pick up.")
    p("- `team_total_cap` / `team_*_cap_*` are computed by SUMMING this dataset's own listed "
      "contracts per team-season — a proxy for the team's real accounted cap (practice-squad / "
      "minimum-tender players not carrying a filed contract row are undercounted), not the "
      "league's official cap-compliance number.")
    p("")
    p("## Disposition")
    p("")
    p("- **Ship:** `contract_source.load_contract_features(season)` — per-player cap hit / base "
      "salary / guaranteed $ / `guaranteed_ratio` / `log_investment` WITH the team's O-line-cap "
      "and skill-cap-concentration aggregates merged in; `load_team_cap_aggregates(season)` for "
      "the team table alone. Landed to `nfl/fantasy/contracts/player_contract_features` + "
      "`nfl/fantasy/contracts/team_cap_aggregates` (season-partitioned Delta).")
    p("- **Source:** nflverse's `historical_contracts.parquet` release (CC-BY-4.0), not a direct "
      "OverTheCap/Spotrac scrape — overthecap.com's `robots.txt` explicitly disallows the "
      "Anthropic-AI crawler and Spotrac hard-blocks automated fetches (both probed live "
      "2026-07-27), so this session did not build a scraper against either site. nflverse "
      "already fetches + redistributes the same OTC contract data under an open license, and is "
      "the SAME upstream vendor this repo already reads pbp/rosters/snap_counts from — a "
      "trusted, terms-compliant substitute with a strictly better join key (`gsis_id`, not a "
      "fuzzy name crosswalk).")
    p("- Leakage-safe: only contracts signed on/before the projection season are used (free-"
      "agent/rookie deals are public well before Week 1). `best_alpha=0` — delivered as CANDIDATE "
      "features; the lift is proven in NF1.2/NF1.5's ablation under deflation, not here.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def land(season: int, *, to_s3: bool, local_root: str | None, cache_dir=None,
        contracts=None) -> tuple[int, int]:
    """Compute SEASON's player + team features and write both to the lake (season partitions)."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    player, team = C.build_contract_features(season, cache_dir=cache_dir, contracts=contracts)
    if not (to_s3 or local_root):
        log.info("computed %d player rows / %d team rows for season=%d (no --s3/--lake-root ⇒ "
                 "not landed)", len(player), len(team), season)
        return 0, 0
    n_p = s3io.write_dataframe(player, sport=C.LAKE_SPORT, source=C.LAKE_SOURCE_PLAYER,
                               season=season, tier=C.LAKE_TIER, local_root=local_root)
    n_t = s3io.write_dataframe(team, sport=C.LAKE_SPORT, source=C.LAKE_SOURCE_TEAM,
                               season=season, tier=C.LAKE_TIER, local_root=local_root)
    log.info("landed season=%d: %d player rows → %s, %d team rows → %s", season, n_p,
             C.LAKE_SOURCE_PLAYER, n_t, C.LAKE_SOURCE_TEAM)
    return n_p, n_t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D8 contract/financial feature source")
    ap.add_argument("--probe", action="store_true", help="live availability probe (no lake/DB needed)")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--season", type=int, help="single season for --coverage")
    ap.add_argument("--from", dest="from_season", type=int, default=DEFAULT_LAND_FROM)
    ap.add_argument("--to", dest="to_season", type=int, default=DEFAULT_LAND_TO)
    ap.add_argument("--refresh", action="store_true", help="force re-fetch the nflverse release")
    ap.add_argument("--coverage", action="store_true", help="build + report join-match-rate + face-validity")
    ap.add_argument("--land", type=int, metavar="SEASON", help="compute + land one SEASON")
    ap.add_argument("--land-range", action="store_true", help="land every season in --from/--to")
    ap.add_argument("--s3", action="store_true")
    ap.add_argument("--lake-root", default=None, help="land to a local-FS Delta tree (offline)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if args.probe:
        return probe()

    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")

    # fetch/parse the release ONCE (assemble-once); every season build reuses this in-memory frame.
    raw = C.fetch_historical_contracts(refresh=args.refresh)

    if args.coverage:
        if not Path(args.duckdb).exists():
            ap.error(f"DuckDB not found at {args.duckdb} (needed for --coverage)")
        import duckdb

        seasons = [args.season] if args.season else list(range(args.from_season, args.to_season + 1))
        con = duckdb.connect(args.duckdb, read_only=True)
        try:
            out = {
                "probe": {
                    "n_contracts": int(len(raw)),
                    "gsis_coverage": round(float(raw["gsis_id"].notna().mean()), 4),
                    "positions": sorted(raw["position"].dropna().unique().tolist()),
                    "unmapped_teams": sorted({t for arr in raw["cols"] if arr is not None
                                              for t in [r.get("team") for r in arr]
                                              if t and t != "Total" and C.team_abbr(t) is None}),
                },
                "seasons": {},
            }
            for s in seasons:
                r = _season_report(con, s, contracts=raw)
                out["seasons"][s] = r
                cov = r["coverage"]
                print(f"season={s}: {cov.get('n_contract_rows')} contract rows, "
                      f"{cov.get('pct_matched')}% skill-position match "
                      f"({cov.get('match_rate_by_position')})")
        finally:
            con.close()
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (_REPORT_DIR / "nf_d8_contract_features.json").write_text(json.dumps(out, indent=2, default=str))
        if not args.no_report:
            write_report(out, _REPORT_DIR / "nf_d8_contract_features.md")

    if args.land is not None:
        land(args.land, to_s3=args.s3, local_root=args.lake_root, contracts=raw)
    elif args.land_range:
        for s in range(args.from_season, args.to_season + 1):
            land(s, to_s3=args.s3, local_root=args.lake_root, contracts=raw)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

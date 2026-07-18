# NFL raw lake tables (dbt source reference)

The locked Phase-0 raw tables (`nfl_data_inventory.md` §7) land as **Delta** tables at
`s3://<lake_bucket>/nfl/raw/<source>/` (season is a Delta partition). Staging models read them
via the `{{ nfl_delta('<source>') }}` macro rather than dbt `source()` external tables, because
the raw tier is Delta (`delta_scan`) not a parquet glob, and the macro also routes to a local-FS
Delta tree for offline dev (`--vars 'lake_root: /path'`).

⭐ **NFL divergence from NCAAF:** the nflverse feeds are **typed** release Parquet (columns
preserved through Delta), so their staging models are plain renames — NO `json_extract`. Only
the two Odds API feeds are JSON (`raw_json` → flattened, like NCAAF).

§7 lists 24 rows; several expand to multiple physical S3 tables (NGS ×3, PFR week ×4, PFR season
×4, QBR ×2, stats_player reg/post ×2) → **32 registry entries** (30 nflverse + 2 Odds API).

| source | nflverse asset / Odds API | typed | grain | partition | cadence |
|--------|---------------------------|-------|-------|-----------|---------|
| stats_player_week | stats_player/stats_player_week_YYYY | ✅ | player·wk | season | weekly |
| stats_player_reg | stats_player/stats_player_reg_YYYY | ✅ | player·season | season | weekly |
| stats_player_post | stats_player/stats_player_post_YYYY | ✅ | player·season | season | weekly |
| stats_team_week | stats_team/stats_team_week_YYYY | ✅ | team·wk | season | weekly |
| rosters | rosters/roster_YYYY | ✅ | player·season | season | weekly |
| weekly_rosters | weekly_rosters/roster_weekly_YYYY | ✅ | player·wk | season | weekly |
| depth_charts | depth_charts/depth_charts_YYYY | ✅ | player·wk | season | weekly |
| snap_counts | snap_counts/snap_counts_YYYY | ✅ | player·game | season | weekly |
| schedules | schedules/games (single) | ✅ | game | season | weekly |
| ngs_passing / ngs_rushing / ngs_receiving | nextgen_stats/ngs_* (single, filter season) | ✅ | player·wk | season | weekly |
| pfr_advstats_week_{pass,rush,rec,def} | pfr_advstats/advstats_week_*_YYYY | ✅ | player·game | season | weekly |
| pfr_advstats_season_{pass,rush,rec,def} | pfr_advstats/advstats_season_* (single) | ✅ | player·season | season | weekly |
| pbp | pbp/play_by_play_YYYY (372 cols) | ✅ | play | season | weekly |
| pbp_participation | pbp_participation/pbp_participation_YYYY (no season col) | ✅ | play | season | weekly |
| ftn_charting | ftn_charting/ftn_charting_YYYY (2022+) | ✅ | play | season | weekly |
| qbr_week / qbr_season | espn_data/qbr_*_level (single) | ✅ | player | season | weekly |
| injuries | injuries/injuries_YYYY | ✅ | player·wk | season | weekly (in-season, N0.4) |
| nflverse_draft_picks | draft_picks/draft_picks (single) | ✅ | player | season | seasonal |
| nflverse_combine | combine/combine (single) | ✅ | player | season | seasonal |
| nflverse_players | players/players (single, NOT season-scoped) | ✅ | player | season=0 | seasonal |
| officials | officials/officials (single) | ✅ | game | season | seasonal |
| odds_nfl | Odds API /odds (h2h/spreads/totals) | ❌ JSON | game | season/week | intraday (N0.4) |
| odds_nfl_scores | Odds API /scores | ❌ JSON | game | season/week | intraday (N0.4) |

**Backfill window 2016–2025** for the advanced stack (NGS/participation floor 2016, PFR 2018,
FTN 2022; below-floor per-year reads 404 → clean empty skip); team/box/roster/schedule extend to
1999, draft/combine/players all-time. Props + historical odds (§7 tables 22 & 24) are **N0.4**.
Cost: nflverse **$0** · Odds API **$0** incremental.

**Staging built in N0.2 (a first layer proving the typed + JSON reads):** `stg_nfl_schedules`,
`stg_nfl_player_week`, `stg_nfl_snap_counts`, `stg_nfl_injuries`, `stg_nfl_players`,
`stg_nfl_odds`. N0.3 ports the full `refined` mart IP (`nfl_data_inventory.md` §6) over these.

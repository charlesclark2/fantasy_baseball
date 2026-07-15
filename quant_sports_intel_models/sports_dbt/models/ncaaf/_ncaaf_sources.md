# NCAAF raw lake tables (dbt source reference)

The 24 locked Phase-0 raw tables (`ncaaf_data_inventory.md §8`) land as **Delta** tables at
`s3://<lake_bucket>/ncaaf/raw/<source>/` (season is a Delta partition). Staging models read
them via the `{{ ncaaf_delta('<source>') }}` macro rather than dbt `source()` external
tables, because the raw tier is Delta (`delta_scan`) not a parquet glob, and the macro also
routes to a local-FS Delta tree for offline dev (`--vars 'lake_root: /path'`).

| # | source | endpoint | grain | partition | cadence |
|---|--------|----------|-------|-----------|---------|
| 1 | games | CFBD /games | game | season/week | weekly |
| 2 | game_team_stats | CFBD /games/teams | team | season/week | weekly |
| 3 | game_player_stats | CFBD /games/players | player | season/week | weekly |
| 4 | plays | CFBD /plays (week REQUIRED) | play | season/week | weekly |
| 5 | play_stats | CFBD /plays/stats per gameId (2000-cap) | player | season/week | weekly |
| 6 | drives | CFBD /drives | game | season/week | weekly |
| 7 | game_advanced | CFBD /stats/game/advanced | team | season | weekly |
| 8 | box_advanced | CFBD /game/box/advanced (id=) | team | season/week | weekly |
| 9 | ppa_players_games | CFBD /ppa/players/games (2014+) | player | season | weekly |
| 10 | player_usage | CFBD /player/usage (year-only) | player | season | weekly |
| 11 | roster | CFBD /roster (year-only) | player | season | weekly |
| 12 | team_advanced_season | CFBD /stats/season/advanced | team | season | weekly |
| 13 | ratings_sp | CFBD /ratings/sp | team | season | weekly |
| 14 | talent | CFBD /talent | team | season | seasonal |
| 15 | recruiting_players | CFBD /recruiting/players | player | season | seasonal |
| 16 | transfer_portal | CFBD /player/portal | player | season | seasonal |
| 17 | returning_production | CFBD /player/returning | team | season | seasonal |
| 18 | teams | CFBD /teams/fbs | season | season | seasonal |
| 19 | cfbd_draft_picks | CFBD /draft/picks | player | season | seasonal |
| 20 | odds_ncaaf | Odds API /odds (h2h/spreads/totals) | game | season/week | intraday |
| 21 | odds_ncaaf_scores | Odds API /scores | game | season/week | intraday |
| 22 | nflverse_draft_picks | nflverse release parquet | player | season | seasonal |
| 23 | nflverse_combine | nflverse release parquet | player | season | seasonal |
| 24 | nflverse_players | nflverse release parquet | player | (season=0) | seasonal |

Backfill window **2014–2025** (player-advanced floor). Cost: CFBD $10/mo (Tier 3) · Odds $0
incremental · nflverse $0.

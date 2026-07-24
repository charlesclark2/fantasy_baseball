# NFL mart inventory & vertical-readiness gap table (N1.0)

The audit that opens N1.0. Answers one question: **does the `sports_dbt/models/nfl/` mart layer
support all three NFL verticals** — game-lines (N1.1), player-props (N1.2), fantasy (N1.3) — or are
there holes? N0.3 ported the jaffle_shop **player-week** IP (great for props/fantasy) but built **no
team-game layer** (which the game-line vertical needs) and **no CLV/closing-line mart** (the market
benchmark every vertical scores against). N1.0 fills exactly those two gaps.

## What existed before N1.0 (N0.3 port + N0.4 lake)

Marts (`models/nfl/marts/`) — all **player-week / player-season grain**:

| mart | grain | vertical it serves |
|------|-------|--------------------|
| `fct_player_week` | player·week | props, fantasy |
| `mart_opportunity_player_week` | player·week | props, fantasy |
| `mart_efficiency_player_week` | player·week | props, fantasy |
| `mart_player_season` | player·season | props, fantasy |
| `mart_projections_preseason` | player·season | fantasy (superseded for the draft tool by ↓) |
| `mart_nfl_fantasy_season_projection` | player·season | fantasy (NF-FASTPATH — raw stat-line + rookies + uncertainty; MVP-2/NF-C1 input) |
| `sat_{passing,rushing,receiving}_ngs_weekly`, `sat_snap_counts_weekly` | player·week | props, fantasy |
| `dim_player`, `dim_player_role` (SCD-2) | player | all |
| `dim_nfl_betting` | game (nflverse consensus line only) | (thin — a single consensus line, not per-book/CLV) |
| `team_week_calendar`, `week_clock_bounds` | team·week | plumbing |

Raw lake (N0.2 + N0.4), available but **not yet staged/marted for team-game or CLV**:
`pbp` (1.28M plays, full EPA/success/wp), `stats_team_week` (team box, 133 cols), `schedules`
(game spine w/ rest/roof/surface/temp/wind/stadium/consensus line), `odds_nfl_historical`
(closing game lines 2020–2024, 1,697 event-snapshots, 25 books incl. Bovada),
`odds_nfl_props_historical` (closing props 2023–2024, 570 events).

## The gap table (per vertical)

| need | vertical | before N1.0 | N1.0 delivers |
|------|----------|-------------|---------------|
| team-game box + result (2 rows/game) | game-lines | ❌ none | ✅ `fct_nfl_team_game` |
| team offense/defense EPA·success·explosive (from pbp) | game-lines | ❌ none | ✅ `fct_nfl_team_game` (pbp-derived) |
| pace / plays-per-game | game-lines | ❌ none | ✅ `fct_nfl_team_game.off_plays` + rollups |
| situational: home / rest / travel / dome / weather | game-lines | ❌ none | ✅ `dim_nfl_game` |
| point-in-time as-of-kickoff team strength | game-lines | ❌ none | ✅ `rollup_nfl_team_week_asof` |
| opponent-adjusted efficiency (SoS-corrected) | game-lines | ❌ none | ✅ `rollup_nfl_team_week_opponent_adjusted` (feeds the N1.1 strength model) |
| season-final team rollup (priors / reporting) | all | ❌ none | ✅ `rollup_nfl_team_season` |
| leakage-safe **closing** game line + CLV scoreboard (per book) | all | ⚠️ only `dim_nfl_betting` (1 consensus line, no close/CLV) | ✅ `mart_nfl_clv_game_lines` (`snapshot_ts < commence_time`) |
| leakage-safe **closing** props line + CLV | props | ❌ none | ✅ `mart_nfl_clv_props` |
| player opportunity / efficiency / projections | props, fantasy | ✅ N0.3 (confirmed sufficient) | (unchanged — verified below) |

### Player-week marts (N0.3) confirmed sufficient for props/fantasy
`fct_player_week` (145-col box), `mart_opportunity_player_week` (targets/carries/routes/red-zone
share), `mart_efficiency_player_week` (per-opportunity EPA/YPRR-style), `mart_player_season`,
`mart_projections_preseason`, and the NGS/snap satellites cover the per-player opportunity,
efficiency, and usage signal props/fantasy models need. The one thing they lacked — the
**closing-line market benchmark** to score projections against — N1.0 adds as `mart_nfl_clv_props`.
No player-week rebuild needed; the gap was purely the market side.

## Why NFL is leaner than the NCAAF P1.1 template

- **One division** — no FBS/FCS universe filter (`is_fbs_matchup`/`is_fbs_involved` collapse away).
- **`week` is monotone within a season** (reg 1–18, playoffs 19–22, no reset — *verified on the real
  lake*, 2020–2024; the CFBD postseason-week=1 trap does NOT apply). So raw `week` is a safe as-of
  ordering anchor; the leakage **test** still uses each game's own **kickoff date** (belt-and-braces).
- **pbp already carries `epa`, `success`, `wp`, `qb_epa`** — no bespoke EPA model to derive; win-prob
  garbage-time filtering is a column read, not a re-computation.
- **`schedules` carries rest / roof / surface / temp / wind / stadium** directly — situational
  features are renames, not joins to a separate venue source. Travel needs stadium coordinates, which
  NFL has no lake source for → a static 32-team geo crosswalk (`stg_nfl_team_geo`).

## N1.0 deliverables (models added)

Staging: `stg_nfl_pbp`, `stg_nfl_team_week`, `stg_nfl_historical_odds`, `stg_nfl_props_historical`,
`stg_nfl_team_geo` (32-team code→name/lat/long crosswalk).
Marts: `dim_nfl_game`, `fct_nfl_team_game`, `rollup_nfl_team_week_asof`,
`rollup_nfl_team_week_opponent_adjusted`, `rollup_nfl_team_season`, `mart_nfl_clv_game_lines`,
`mart_nfl_clv_props`.
Leakage/CLV gates (HALT, kickoff-date-based): `assert_nfl_asof_week_has_no_future_games`,
`assert_nfl_opponent_adjustment_is_point_in_time`, `assert_nfl_clv_is_pre_kickoff`.

⇒ N1.1 (game-lines) / N1.2 (props) / N1.3 (fantasy) all start on a ready mart layer.

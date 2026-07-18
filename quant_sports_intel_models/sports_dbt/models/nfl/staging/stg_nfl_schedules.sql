-- stg_nfl_schedules — the NFL game spine (nflverse schedules/games), NFL-N0.2.
--
-- nflverse is TYPED release Parquet (not CFBD JSON), so this staging is plain column renames
-- over the typed Delta table — NO json_extract (the NFL divergence from the NCAAF staging).
-- One row per game, 1999–2026. Carries nflverse's FREE consensus betting lines (moneyline /
-- spread / total) as a cross-check to the per-book Odds API feed (N0.4). Cross-IDs (pfr/pff/
-- espn/gsis/old_game_id) are the game-key rosetta for joining the advanced feeds.
-- ⭐ sport-tagged (the multi-sport serving/entitlement decision — baked in from day one).
select
    'nfl'                          as sport,
    game_id,
    season,
    week,
    game_type                      as season_type,
    gameday                        as game_date,     -- ISO date string in the parquet (VARCHAR)
    gametime,
    -- kickoff timestamp (N0.3): the calendar/week-clock marts anchor the NFL week on it.
    -- gameday+gametime are VARCHAR → try_cast (null gametime → null datetime). INC-23 use-site.
    try_cast(gameday || ' ' || gametime as timestamp) as game_datetime,
    weekday,
    -- team codes normalized to the canonical franchise (N0.3) so the calendar joins the
    -- normalized roster/depth/snap teams: LA/STL→LAR, SD→LAC, OAK→LV (relocations).
    case when away_team in ('LA', 'STL') then 'LAR'
         when away_team in ('SD', 'LAC') then 'LAC'
         when away_team in ('OAK', 'LV') then 'LV'
         else away_team end        as away_team,
    case when home_team in ('LA', 'STL') then 'LAR'
         when home_team in ('SD', 'LAC') then 'LAC'
         when home_team in ('OAK', 'LV') then 'LV'
         else home_team end        as home_team,
    away_score,
    home_score,
    result,                                           -- home margin (home_score - away_score)
    total                          as total_points,   -- combined final score
    (game_type = 'REG')            as is_regular_season,
    (div_game = 1)                 as div_game,
    location,
    roof,
    surface,
    temp,
    wind,
    away_rest,
    home_rest,
    -- free consensus betting lines (cross-check to the per-book Odds API feed)
    away_moneyline,
    home_moneyline,
    spread_line,
    away_spread_odds,
    home_spread_odds,
    total_line,
    over_odds,
    under_odds,
    away_qb_id,
    home_qb_id,
    away_qb_name,
    home_qb_name,
    referee,
    stadium_id,
    stadium,
    -- game-key rosetta (join the advanced feeds)
    old_game_id,
    gsis                           as gsis_game_id,
    pfr                            as pfr_game_id,
    pff                            as pff_game_id,
    espn                           as espn_game_id,
    ftn                            as ftn_game_id
from {{ nfl_delta('schedules') }}
where game_id is not null

-- dim_nfl_betting — the game betting spine (N0.3 port of jaffle `dim_nfl_betting`).
--
-- One row per game with the FREE nflverse consensus lines (moneyline / spread / total) + the
-- game-key rosetta (pfr/pff/espn/ftn ids) for joining the per-book feeds. The betting head-start.
-- ⚠️ PORT DIVERGENCE: jaffle hardcoded season=2025; here ALL seasons are kept so it is the full
-- historical betting spine (the free lines exist 1999+). N0.4 layers the per-book Odds API
-- (Bovada/CLV) onto this key. ⭐ sport-tagged.
with base as (
    select *
    from {{ ref('stg_nfl_schedules') }}
)
select
    'nfl'                          as sport,
    game_id,
    pfr_game_id,
    pff_game_id,
    espn_game_id,
    ftn_game_id,
    season,
    week,
    game_date,
    gametime                       as game_time,
    game_datetime,
    home_team,
    away_team,
    home_score,
    away_score,
    location                       as game_location,
    result                         as home_score_differential,
    total_points,
    home_moneyline,
    away_moneyline,
    spread_line,
    home_spread_odds,
    away_spread_odds,
    total_line,
    over_odds,
    under_odds
from base

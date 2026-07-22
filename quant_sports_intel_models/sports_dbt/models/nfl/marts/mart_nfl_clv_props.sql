-- mart_nfl_clv_props — the leakage-safe CLOSING player-prop line (NFL-N1.0), the market benchmark
--   for the props vertical. GRAIN: one row per (game_id, bookmaker, market, player, side).
--
-- Same closing mechanic as mart_nfl_clv_game_lines: keep only `snapshot_ts < commence_time`, take
--   the LATEST such snapshot per player-outcome. Coverage EXPECTED 2023–2024 (the N0.4 props vendor
--   floor). Bovada present (reference_target_bookmaker).
--
-- ⚠️ Realized settlement is NOT attached here — that requires a player-name → nflverse-id xref +
--   the player game log, which a dedicated props-CLV story owns. This mart is the pregame closing
--   line only, joined to game_id for context; N1.2 layers the realized side on top.
{{ config(materialized='table') }}

with props as (
    select * from {{ ref('stg_nfl_props_historical') }}
    where is_leakage_safe
      and home_team is not null and away_team is not null
),

closing as (
    select
        event_id, season, commence_time, snapshot_ts, home_team, away_team,
        bookmaker, market, player_name, lower(outcome_side) as side, price, point
    from props
    qualify row_number() over (
        partition by event_id, bookmaker, market, player_name, lower(outcome_side)
        order by snapshot_ts desc
    ) = 1
),

games as (
    select game_id, season, home_team, away_team, game_date, is_completed
    from {{ ref('dim_nfl_game') }}
),

bridged as (
    select
        c.*, g.game_id, g.is_completed,
        row_number() over (
            partition by c.event_id, c.bookmaker, c.market, c.player_name, c.side
            order by abs(date_diff('day', (c.commence_time - interval 5 hour)::date, g.game_date::date))
        ) as game_match_rank
    from closing c
    left join games g
      on g.season = c.season and g.home_team = c.home_team and g.away_team = c.away_team
)

select
    'nfl'                                                    as sport,
    game_id,
    event_id,
    season,
    commence_time,
    snapshot_ts,
    date_diff('minute', snapshot_ts, commence_time)         as minutes_before_kickoff,
    home_team,
    away_team,
    bookmaker,
    (bookmaker = 'bovada')                                  as is_target_book,
    market,
    player_name,
    side,
    point                                                   as closing_point,
    price                                                   as closing_price,
    is_completed
from bridged
where game_match_rank = 1
  and game_id is not null

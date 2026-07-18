-- stg_nfl_receiving_pfr — PFR weekly receiving advanced (N0.3 port of jaffle `stg_receiving_pfr`).
--
-- Drops, broken tackles, receiving interceptions + passer-rating-when-targeted (WR/TE quality —
-- §2.4). Lake asset: `pfr_advstats_week_rec`. Keyed pfr_player_id; joins opportunity/efficiency
-- on (pfr_id, season, week). Typed Delta → plain renames. 2018+. ⭐ sport-tagged.
select
    'nfl'                                             as sport,
    upper(trim(pfr_player_id))                        as player_id,
    upper(trim(pfr_player_name))                      as player_name,
    upper(trim(game_id))                              as game_id,
    upper(trim(pfr_game_id))                          as pfr_game_id,
    season,
    week,
    case when upper(trim(team))     in ('OAK', 'LV') then 'LV' else upper(trim(team))     end as team_id,
    case when upper(trim(opponent)) in ('OAK', 'LV') then 'LV' else upper(trim(opponent)) end as opponent_id,
    coalesce(rushing_broken_tackles, 0.0)             as rushing_broken_tackles,
    coalesce(receiving_broken_tackles, 0.0)           as receiving_broken_tackles,
    coalesce(passing_drops, 0.0)                      as passing_drops,
    coalesce(passing_drop_pct, 0.0)                   as passing_drop_pct,
    coalesce(receiving_drop, 0.0)                     as receiving_drop,
    coalesce(receiving_drop_pct, 0.0)                 as receiving_drop_pct,
    coalesce(receiving_int, 0.0)                      as receiving_interceptions,
    coalesce(receiving_rat, 0.0)                      as receiving_rating
from {{ nfl_delta('pfr_advstats_week_rec') }}
where game_type ilike 'reg'

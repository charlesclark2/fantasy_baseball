-- stg_nfl_rushing_pfr — PFR weekly rushing advanced (N0.3 port of jaffle `stg_rushing_pfr`).
--
-- Yards before/after contact + broken tackles (the RB "created yardage" signal — §2.4). Lake
-- asset: `pfr_advstats_week_rush`. Keyed pfr_player_id; joins opportunity/efficiency on
-- (pfr_id, season, week). Typed Delta → plain renames. 2018+. ⭐ sport-tagged.
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
    coalesce(carries, 0.0)                            as carries,
    coalesce(rushing_yards_before_contact, 0.0)       as rushing_yards_before_contact,
    coalesce(rushing_yards_before_contact_avg, 0.0)   as rushing_yards_before_contact_avg,
    coalesce(rushing_yards_after_contact, 0.0)        as rushing_yards_after_contact,
    coalesce(rushing_yards_after_contact_avg, 0.0)    as rushing_yards_after_contact_avg,
    coalesce(rushing_broken_tackles, 0.0)             as rushing_broken_tackles,
    coalesce(receiving_broken_tackles, 0.0)           as receiving_broken_tackles
from {{ nfl_delta('pfr_advstats_week_rush') }}
where game_type ilike 'reg'

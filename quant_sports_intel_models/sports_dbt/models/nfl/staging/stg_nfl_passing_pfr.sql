-- stg_nfl_passing_pfr — PFR weekly passing advanced (N0.3 port of jaffle `stg_passing_pfr`).
--
-- Pressure/blitz/hurry/hit + bad-throw + drop context (NCAAF's PFF gap, filled free — §2.4).
-- Lake asset: `pfr_advstats_week_pass`. Keyed pfr_player_id + game_id; joins the efficiency /
-- opportunity marts on (pfr_id, season, week). Typed Delta → plain renames. 2018+. ⭐ sport-tag.
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
    coalesce(passing_drops, 0.0)                      as passing_drops,
    coalesce(passing_drop_pct, 0.0)                   as passing_drops_pct,
    coalesce(receiving_drop, 0.0)                     as receiving_drops,
    coalesce(receiving_drop_pct, 0.0)                 as receiving_drops_pct,
    coalesce(passing_bad_throws, 0.0)                 as passing_bad_throws,
    coalesce(passing_bad_throw_pct, 0.0)              as passing_bad_throws_pct,
    coalesce(times_sacked, 0.0)                       as times_sacked,
    coalesce(times_blitzed, 0.0)                      as times_blitzed,
    coalesce(times_hurried, 0.0)                      as times_hurried,
    coalesce(times_hit, 0.0)                          as times_hit,
    coalesce(times_pressured, 0.0)                    as times_pressured,
    coalesce(times_pressured_pct, 0.0)                as times_pressured_pct,
    coalesce(def_times_blitzed, 0.0)                  as def_times_blitzed,
    coalesce(def_times_hurried, 0.0)                  as def_times_hurried,
    coalesce(def_times_hitqb, 0.0)                    as def_times_hit_qb
from {{ nfl_delta('pfr_advstats_week_pass') }}
where game_type ilike 'reg'

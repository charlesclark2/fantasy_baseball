-- stg_nfl_passing_ngs_weekly — Next Gen Stats weekly passing (N0.3 port of jaffle
-- `stg_passing_ngs_weekly`). Tracking-derived QB metrics (time-to-throw, air-yards, CPOE,
-- aggressiveness) — the FREE tracking layer NCAAF has no equivalent for (§2.3). Lake asset:
-- `ngs_passing`; keyed player_gsis_id + season/week. Typed Delta → plain renames. 2016+.
-- ⭐ sport-tagged.
select
    'nfl'                                             as sport,
    upper(trim(player_gsis_id))                       as player_id,
    case
        when player_display_name is null then upper(trim(concat(player_first_name, ' ', player_last_name)))
        else upper(trim(player_display_name))
    end                                               as player_name,
    season,
    week,
    upper(trim(player_position))                      as position,
    team_abbr,
    coalesce(avg_time_to_throw, 0.0)                  as avg_time_to_throw,
    coalesce(avg_completed_air_yards, 0.0)            as avg_completed_air_yards,
    coalesce(avg_intended_air_yards, 0.0)             as avg_intended_air_yards,
    coalesce(avg_air_yards_differential, 0.0)         as avg_air_yards_differential,
    coalesce(aggressiveness, 0.0)                     as aggressiveness,
    coalesce(max_completed_air_distance, 0.0)         as max_completed_air_distance,
    coalesce(avg_air_yards_to_sticks, 0.0)            as avg_air_yards_to_sticks,
    coalesce(attempts, 0)                             as attempts,
    coalesce(completions, 0)                          as completions,
    coalesce(pass_yards, 0)                           as passing_yards,
    coalesce(pass_touchdowns, 0)                      as passing_touchdowns,
    coalesce(interceptions, 0)                        as interceptions,
    coalesce(passer_rating, 0.0)                      as passer_rating,
    coalesce(completion_percentage, 0.0)              as completion_percentage,
    coalesce(expected_completion_percentage, 0.0)     as expected_completion_percentage,
    coalesce(completion_percentage_above_expectation, 0.0) as completion_percentage_above_expectation
from {{ nfl_delta('ngs_passing') }}
where season_type ilike 'reg'
  and week != 0

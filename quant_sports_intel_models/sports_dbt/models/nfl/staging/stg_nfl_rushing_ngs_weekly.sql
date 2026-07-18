-- stg_nfl_rushing_ngs_weekly — Next Gen Stats weekly rushing (N0.3 port of jaffle
-- `stg_rushing_ngs_weekly`). Tracking-derived RB metrics (efficiency, 8+-defender box rate,
-- rush yards over expected) — FREE tracking layer (§2.3). Lake asset: `ngs_rushing`; keyed
-- player_gsis_id + season/week. Typed Delta → plain renames. 2016+. ⭐ sport-tagged.
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
    coalesce(efficiency, 0.0)                         as efficiency,
    coalesce(percent_attempts_gte_eight_defenders, 0.0) as percent_attempts_gte_eight_defenders,
    coalesce(avg_time_to_los, 0.0)                    as avg_time_to_line_of_scrimmage,
    coalesce(rush_attempts, 0)                        as rush_attempts,
    coalesce(rush_yards, 0)                           as rushing_yards,
    coalesce(avg_rush_yards, 0.0)                     as avg_rushing_yards,
    coalesce(rush_touchdowns, 0)                      as rushing_touchdowns,
    coalesce(expected_rush_yards, 0.0)                as expected_rushing_yards,
    coalesce(rush_yards_over_expected, 0.0)           as rushing_yards_over_expected,
    coalesce(rush_yards_over_expected_per_att, 0.0)   as rushing_yards_over_expected_per_attempt,
    coalesce(rush_pct_over_expected, 0.0)             as rush_percentage_over_expected
from {{ nfl_delta('ngs_rushing') }}
where season_type ilike 'reg'
  and week != 0

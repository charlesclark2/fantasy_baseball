-- stg_nfl_receiving_ngs_weekly — Next Gen Stats weekly receiving (N0.3 port of jaffle
-- `stg_receiving_ngs_weekly`). Tracking-derived WR/TE metrics (cushion, separation, YAC over
-- expected, share of intended air yards) — FREE tracking layer (§2.3). Lake asset:
-- `ngs_receiving`; keyed player_gsis_id + season/week. Typed Delta → plain renames. 2016+.
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
    coalesce(avg_cushion, 0.0)                        as avg_cushion,
    coalesce(avg_separation, 0.0)                     as avg_separation,
    coalesce(avg_intended_air_yards, 0.0)            as avg_intended_air_yards,
    coalesce(percent_share_of_intended_air_yards, 0.0) as percent_share_of_intended_air_yards,
    coalesce(receptions, 0)                           as receptions,
    coalesce(targets, 0)                              as targets,
    coalesce(yards, 0)                                as receiving_yards,
    coalesce(rec_touchdowns, 0)                       as receiving_touchdowns,
    coalesce(catch_percentage, 0.0)                   as catch_percentage,
    coalesce(avg_yac, 0.0)                            as avg_yards_after_catch,
    coalesce(avg_expected_yac, 0.0)                   as avg_expected_yards_after_catch,
    coalesce(avg_yac_above_expectation, 0.0)          as avg_yards_after_catch_above_expectation
from {{ nfl_delta('ngs_receiving') }}
where season_type ilike 'reg'
  and week != 0

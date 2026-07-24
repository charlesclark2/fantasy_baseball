-- stg_nfl_weekly_data — the weekly player box score, the fct_player_week source (N0.3 port).
--
-- Ports jaffle `stg_weekly_data` onto the fresh lake. The OLD project read the legacy nflverse
-- `weekly_data` (player_stats, 53 cols, caps 2024); the NEW lake stores the richer
-- `stats_player_week` (145 cols, through 2025 — N0.1 §1). So this is a rename port WITH the
-- nflverse column-drift remap baked in (legacy name → stats_player_week name):
--   interceptions→passing_interceptions · sacks→sacks_suffered · sack_yards→sack_yards_lost
--   recent_team→team · opponent_team unchanged.
-- ⚠️ `dakota` (the old qb_efficiency_index) does NOT exist in stats_player_week → carried NULL
--    (fct coalesces it to 0). The one metric lost in the port; nothing else drops.
-- Typed Delta → plain renames, no json_extract (the NFL divergence). ⭐ sport-tagged.
select
    'nfl'                                             as sport,
    trim(player_id)                                   as player_id,
    -- prefer the FULL display name ("Ashton Jeanty") over the abbreviated box name ("A.Jeanty") —
    -- for stat-only players (rookies with no role segment) this is the name fct_player_week carries
    coalesce(nullif(trim(player_display_name), ''), trim(player_name)) as player_name,
    position,
    position_group,
    headshot_url,
    team                                              as team_id,        -- legacy recent_team
    season,
    week,
    opponent_team                                     as opponent_id,
    -- passing
    completions,
    attempts,
    passing_yards,
    passing_tds,
    passing_interceptions                             as interceptions,  -- legacy `interceptions`
    sacks_suffered                                    as sacks,          -- legacy `sacks`
    sack_yards_lost                                   as sack_yards,     -- legacy `sack_yards`
    sack_fumbles,
    sack_fumbles_lost,
    passing_air_yards,
    passing_yards_after_catch,
    passing_first_downs,
    passing_epa                                       as passing_expected_points_added,
    passing_2pt_conversions,
    pacr                                              as passing_air_conversion_ratio,
    cast(null as double)                              as qb_efficiency_index,  -- legacy `dakota`: absent in stats_player_week
    -- rushing
    carries,
    rushing_yards,
    rushing_tds,
    rushing_fumbles,
    rushing_fumbles_lost,
    rushing_first_downs,
    rushing_epa                                       as rushing_expected_points_added,
    rushing_2pt_conversions,
    -- receiving
    receptions,
    targets,
    receiving_yards,
    receiving_tds,
    receiving_fumbles,
    receiving_fumbles_lost,
    receiving_air_yards,
    receiving_yards_after_catch,
    receiving_first_downs,
    receiving_epa                                     as receiving_expected_points_added,
    receiving_2pt_conversions,
    racr                                              as receiving_air_conversion_ratio,
    target_share,
    air_yards_share,
    wopr                                              as weighted_opportunity_rating,
    special_teams_tds,
    fantasy_points                                    as fantasy_points_std,
    fantasy_points_ppr
from {{ nfl_delta('stats_player_week') }}
where position in ('K', 'QB', 'FB', 'TE', 'WR', 'HB', 'RB')
  and season_type ilike 'reg'
  and player_id is not null

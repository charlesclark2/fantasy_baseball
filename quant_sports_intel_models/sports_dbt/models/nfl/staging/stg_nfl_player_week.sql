-- stg_nfl_player_week — the core weekly player fact (nflverse stats_player_week), NFL-N0.2.
--
-- The 145-col `stats_player_week` (through 2025), NOT legacy player_stats (53 cols, caps 2024)
-- — N0.1 §1. Typed Delta → plain renames. This is the P1 fantasy/props modelling backbone
-- (fct_player_week port target, `nfl_data_inventory.md` §6). A curated projection of the
-- load-bearing box + advanced columns (native target_share / air_yards_share / wopr / cpoe);
-- the full 145 cols remain in the raw Delta for later marts. season_type disambiguates REG
-- (1–18) from POST (19–22) — filter on it, don't assume week ≤ 18 (§1).
select
    'nfl'                          as sport,
    player_id,
    player_display_name            as player_name,
    position,
    position_group,
    season,
    week,
    season_type,
    game_id,
    team,
    opponent_team,
    -- passing
    completions,
    attempts,
    passing_yards,
    passing_tds,
    passing_interceptions,
    sacks_suffered,
    passing_air_yards,
    passing_yards_after_catch,
    passing_epa,
    passing_cpoe,
    -- rushing
    carries,
    rushing_yards,
    rushing_tds,
    rushing_epa,
    rushing_first_downs,
    -- receiving
    receptions,
    targets,
    receiving_yards,
    receiving_tds,
    receiving_air_yards,
    receiving_yards_after_catch    as receiving_yac,
    target_share,
    air_yards_share,
    wopr,
    receiving_epa,
    -- fantasy
    fantasy_points,
    fantasy_points_ppr
from {{ nfl_delta('stats_player_week') }}
where player_id is not null

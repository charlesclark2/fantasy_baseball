-- =============================================================================
-- feature_pregame_game_features.sql
-- Grain: one row per game_pk (regular season games only)
-- Purpose: Master pre-game ML feature assembly. Joins all four pre-game feature
--          tables into a single wide row per game. Direct ML input and Phase 2
--          acceptance gate.
--
-- Column prefix scheme:
--   home_ / away_                  lineup and team context features (by side)
--   home_starter_ / away_starter_  starting pitcher features (by side)
--   (no prefix)                    park features (game-level)
--
-- has_full_data: true when both lineups are full, both starters have prior
-- Statcast history, and the park has a prior-season run factor. Use this flag
-- to select the data-complete training subset.
--
-- LEAKAGE NOTE: all leakage guards are enforced in upstream feature models.
-- This model assembles pre-computed features only — no new stat joins here.
-- =============================================================================

{{ config(materialized='table') }}

with

games as (
    select
        game_pk,
        game_date::date     as game_date,
        game_year::integer  as game_year,
        home_team,
        away_team
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
),

home_lineup as (
    select * from {{ ref('feature_pregame_lineup_features') }}
    where side = 'home'
),

away_lineup as (
    select * from {{ ref('feature_pregame_lineup_features') }}
    where side = 'away'
),

-- Deduplicate to one starter per side in case of rare data duplicates
home_starter as (
    select * from (
        select *,
            row_number() over (partition by game_pk order by pitcher_id) as rn
        from {{ ref('feature_pregame_starter_features') }}
        where side = 'home'
    ) where rn = 1
),

away_starter as (
    select * from (
        select *,
            row_number() over (partition by game_pk order by pitcher_id) as rn
        from {{ ref('feature_pregame_starter_features') }}
        where side = 'away'
    ) where rn = 1
),

home_team as (
    select * from {{ ref('feature_pregame_team_features') }}
    where side = 'home'
),

away_team as (
    select * from {{ ref('feature_pregame_team_features') }}
    where side = 'away'
),

final as (
    select

        -- ── Game identifiers ──────────────────────────────────────────────────
        g.game_pk,
        g.game_date,
        g.game_year,
        g.home_team,
        g.away_team,
        pk.venue_id,
        pk.venue_name,

        -- ── Data completeness flag ─────────────────────────────────────────────
        -- true = both lineups confirmed, both starters have prior history, park
        -- has prior-season run factor. Use for data-complete training subset.
        (
            coalesce(h_ln.has_full_lineup,       false)
            and coalesce(a_ln.has_full_lineup,   false)
            and coalesce(h_st.has_starter_data,  false)
            and coalesce(a_st.has_starter_data,  false)
            and pk.runs_per_game_at_park is not null
        )::boolean                              as has_full_data,

        -- ── Home lineup ───────────────────────────────────────────────────────
        h_ln.has_full_lineup                    as home_has_full_lineup,
        h_ln.lhb_count                          as home_lhb_count,
        h_ln.rhb_count                          as home_rhb_count,
        h_ln.avg_woba_30d                       as home_avg_woba_30d,
        h_ln.avg_xwoba_30d                      as home_avg_xwoba_30d,
        h_ln.avg_k_pct_30d                      as home_avg_k_pct_30d,
        h_ln.avg_bb_pct_30d                     as home_avg_bb_pct_30d,
        h_ln.avg_hard_hit_pct_30d               as home_avg_hard_hit_pct_30d,
        h_ln.avg_barrel_pct_30d                 as home_avg_barrel_pct_30d,
        h_ln.avg_whiff_rate_30d                 as home_avg_whiff_rate_30d,
        h_ln.avg_chase_rate_30d                 as home_avg_chase_rate_30d,
        h_ln.avg_woba_std                       as home_avg_woba_std,
        h_ln.avg_xwoba_std                      as home_avg_xwoba_std,
        h_ln.avg_k_pct_std                      as home_avg_k_pct_std,
        h_ln.avg_bb_pct_std                     as home_avg_bb_pct_std,
        h_ln.avg_hard_hit_pct_std               as home_avg_hard_hit_pct_std,
        h_ln.avg_barrel_pct_std                 as home_avg_barrel_pct_std,
        h_ln.avg_woba_vs_lhp                    as home_avg_woba_vs_lhp,
        h_ln.avg_xwoba_vs_lhp                   as home_avg_xwoba_vs_lhp,
        h_ln.avg_k_pct_vs_lhp                   as home_avg_k_pct_vs_lhp,
        h_ln.avg_bb_pct_vs_lhp                  as home_avg_bb_pct_vs_lhp,
        h_ln.avg_hard_hit_pct_vs_lhp            as home_avg_hard_hit_pct_vs_lhp,
        h_ln.avg_woba_vs_rhp                    as home_avg_woba_vs_rhp,
        h_ln.avg_xwoba_vs_rhp                   as home_avg_xwoba_vs_rhp,
        h_ln.avg_k_pct_vs_rhp                   as home_avg_k_pct_vs_rhp,
        h_ln.avg_bb_pct_vs_rhp                  as home_avg_bb_pct_vs_rhp,
        h_ln.avg_hard_hit_pct_vs_rhp            as home_avg_hard_hit_pct_vs_rhp,

        -- ── Away lineup ───────────────────────────────────────────────────────
        a_ln.has_full_lineup                    as away_has_full_lineup,
        a_ln.lhb_count                          as away_lhb_count,
        a_ln.rhb_count                          as away_rhb_count,
        a_ln.avg_woba_30d                       as away_avg_woba_30d,
        a_ln.avg_xwoba_30d                      as away_avg_xwoba_30d,
        a_ln.avg_k_pct_30d                      as away_avg_k_pct_30d,
        a_ln.avg_bb_pct_30d                     as away_avg_bb_pct_30d,
        a_ln.avg_hard_hit_pct_30d               as away_avg_hard_hit_pct_30d,
        a_ln.avg_barrel_pct_30d                 as away_avg_barrel_pct_30d,
        a_ln.avg_whiff_rate_30d                 as away_avg_whiff_rate_30d,
        a_ln.avg_chase_rate_30d                 as away_avg_chase_rate_30d,
        a_ln.avg_woba_std                       as away_avg_woba_std,
        a_ln.avg_xwoba_std                      as away_avg_xwoba_std,
        a_ln.avg_k_pct_std                      as away_avg_k_pct_std,
        a_ln.avg_bb_pct_std                     as away_avg_bb_pct_std,
        a_ln.avg_hard_hit_pct_std               as away_avg_hard_hit_pct_std,
        a_ln.avg_barrel_pct_std                 as away_avg_barrel_pct_std,
        a_ln.avg_woba_vs_lhp                    as away_avg_woba_vs_lhp,
        a_ln.avg_xwoba_vs_lhp                   as away_avg_xwoba_vs_lhp,
        a_ln.avg_k_pct_vs_lhp                   as away_avg_k_pct_vs_lhp,
        a_ln.avg_bb_pct_vs_lhp                  as away_avg_bb_pct_vs_lhp,
        a_ln.avg_hard_hit_pct_vs_lhp            as away_avg_hard_hit_pct_vs_lhp,
        a_ln.avg_woba_vs_rhp                    as away_avg_woba_vs_rhp,
        a_ln.avg_xwoba_vs_rhp                   as away_avg_xwoba_vs_rhp,
        a_ln.avg_k_pct_vs_rhp                   as away_avg_k_pct_vs_rhp,
        a_ln.avg_bb_pct_vs_rhp                  as away_avg_bb_pct_vs_rhp,
        a_ln.avg_hard_hit_pct_vs_rhp            as away_avg_hard_hit_pct_vs_rhp,

        -- ── Home starting pitcher ─────────────────────────────────────────────
        h_st.pitcher_id                         as home_starter_pitcher_id,
        h_st.pitcher_name                       as home_starter_pitcher_name,
        h_st.pitcher_hand                       as home_starter_pitcher_hand,
        h_st.has_starter_data                   as home_starter_has_starter_data,
        h_st.days_rest                          as home_starter_days_rest,
        h_st.k_pct_7d                           as home_starter_k_pct_7d,
        h_st.bb_pct_7d                          as home_starter_bb_pct_7d,
        h_st.xwoba_against_7d                   as home_starter_xwoba_against_7d,
        h_st.hard_hit_pct_7d                    as home_starter_hard_hit_pct_7d,
        h_st.barrel_pct_7d                      as home_starter_barrel_pct_7d,
        h_st.whiff_rate_7d                      as home_starter_whiff_rate_7d,
        h_st.batter_chase_rate_7d               as home_starter_batter_chase_rate_7d,
        h_st.avg_fastball_velo_7d               as home_starter_avg_fastball_velo_7d,
        h_st.k_pct_14d                          as home_starter_k_pct_14d,
        h_st.bb_pct_14d                         as home_starter_bb_pct_14d,
        h_st.xwoba_against_14d                  as home_starter_xwoba_against_14d,
        h_st.hard_hit_pct_14d                   as home_starter_hard_hit_pct_14d,
        h_st.barrel_pct_14d                     as home_starter_barrel_pct_14d,
        h_st.whiff_rate_14d                     as home_starter_whiff_rate_14d,
        h_st.batter_chase_rate_14d              as home_starter_batter_chase_rate_14d,
        h_st.avg_fastball_velo_14d              as home_starter_avg_fastball_velo_14d,
        h_st.k_pct_30d                          as home_starter_k_pct_30d,
        h_st.bb_pct_30d                         as home_starter_bb_pct_30d,
        h_st.xwoba_against_30d                  as home_starter_xwoba_against_30d,
        h_st.hard_hit_pct_30d                   as home_starter_hard_hit_pct_30d,
        h_st.barrel_pct_30d                     as home_starter_barrel_pct_30d,
        h_st.whiff_rate_30d                     as home_starter_whiff_rate_30d,
        h_st.batter_chase_rate_30d              as home_starter_batter_chase_rate_30d,
        h_st.avg_fastball_velo_30d              as home_starter_avg_fastball_velo_30d,
        h_st.k_pct_std                          as home_starter_k_pct_std,
        h_st.bb_pct_std                         as home_starter_bb_pct_std,
        h_st.xwoba_against_std                  as home_starter_xwoba_against_std,
        h_st.hard_hit_pct_std                   as home_starter_hard_hit_pct_std,
        h_st.barrel_pct_std                     as home_starter_barrel_pct_std,
        h_st.whiff_rate_std                     as home_starter_whiff_rate_std,
        h_st.batter_chase_rate_std              as home_starter_batter_chase_rate_std,
        h_st.avg_fastball_velo_std              as home_starter_avg_fastball_velo_std,
        h_st.fastball_velo_trend                as home_starter_fastball_velo_trend,
        h_st.k_pct_vs_lhb                       as home_starter_k_pct_vs_lhb,
        h_st.bb_pct_vs_lhb                      as home_starter_bb_pct_vs_lhb,
        h_st.xwoba_vs_lhb                       as home_starter_xwoba_vs_lhb,
        h_st.whiff_rate_vs_lhb                  as home_starter_whiff_rate_vs_lhb,
        h_st.k_pct_vs_rhb                       as home_starter_k_pct_vs_rhb,
        h_st.bb_pct_vs_rhb                      as home_starter_bb_pct_vs_rhb,
        h_st.xwoba_vs_rhb                       as home_starter_xwoba_vs_rhb,
        h_st.whiff_rate_vs_rhb                  as home_starter_whiff_rate_vs_rhb,

        -- ── Away starting pitcher ─────────────────────────────────────────────
        a_st.pitcher_id                         as away_starter_pitcher_id,
        a_st.pitcher_name                       as away_starter_pitcher_name,
        a_st.pitcher_hand                       as away_starter_pitcher_hand,
        a_st.has_starter_data                   as away_starter_has_starter_data,
        a_st.days_rest                          as away_starter_days_rest,
        a_st.k_pct_7d                           as away_starter_k_pct_7d,
        a_st.bb_pct_7d                          as away_starter_bb_pct_7d,
        a_st.xwoba_against_7d                   as away_starter_xwoba_against_7d,
        a_st.hard_hit_pct_7d                    as away_starter_hard_hit_pct_7d,
        a_st.barrel_pct_7d                      as away_starter_barrel_pct_7d,
        a_st.whiff_rate_7d                      as away_starter_whiff_rate_7d,
        a_st.batter_chase_rate_7d               as away_starter_batter_chase_rate_7d,
        a_st.avg_fastball_velo_7d               as away_starter_avg_fastball_velo_7d,
        a_st.k_pct_14d                          as away_starter_k_pct_14d,
        a_st.bb_pct_14d                         as away_starter_bb_pct_14d,
        a_st.xwoba_against_14d                  as away_starter_xwoba_against_14d,
        a_st.hard_hit_pct_14d                   as away_starter_hard_hit_pct_14d,
        a_st.barrel_pct_14d                     as away_starter_barrel_pct_14d,
        a_st.whiff_rate_14d                     as away_starter_whiff_rate_14d,
        a_st.batter_chase_rate_14d              as away_starter_batter_chase_rate_14d,
        a_st.avg_fastball_velo_14d              as away_starter_avg_fastball_velo_14d,
        a_st.k_pct_30d                          as away_starter_k_pct_30d,
        a_st.bb_pct_30d                         as away_starter_bb_pct_30d,
        a_st.xwoba_against_30d                  as away_starter_xwoba_against_30d,
        a_st.hard_hit_pct_30d                   as away_starter_hard_hit_pct_30d,
        a_st.barrel_pct_30d                     as away_starter_barrel_pct_30d,
        a_st.whiff_rate_30d                     as away_starter_whiff_rate_30d,
        a_st.batter_chase_rate_30d              as away_starter_batter_chase_rate_30d,
        a_st.avg_fastball_velo_30d              as away_starter_avg_fastball_velo_30d,
        a_st.k_pct_std                          as away_starter_k_pct_std,
        a_st.bb_pct_std                         as away_starter_bb_pct_std,
        a_st.xwoba_against_std                  as away_starter_xwoba_against_std,
        a_st.hard_hit_pct_std                   as away_starter_hard_hit_pct_std,
        a_st.barrel_pct_std                     as away_starter_barrel_pct_std,
        a_st.whiff_rate_std                     as away_starter_whiff_rate_std,
        a_st.batter_chase_rate_std              as away_starter_batter_chase_rate_std,
        a_st.avg_fastball_velo_std              as away_starter_avg_fastball_velo_std,
        a_st.fastball_velo_trend                as away_starter_fastball_velo_trend,
        a_st.k_pct_vs_lhb                       as away_starter_k_pct_vs_lhb,
        a_st.bb_pct_vs_lhb                      as away_starter_bb_pct_vs_lhb,
        a_st.xwoba_vs_lhb                       as away_starter_xwoba_vs_lhb,
        a_st.whiff_rate_vs_lhb                  as away_starter_whiff_rate_vs_lhb,
        a_st.k_pct_vs_rhb                       as away_starter_k_pct_vs_rhb,
        a_st.bb_pct_vs_rhb                      as away_starter_bb_pct_vs_rhb,
        a_st.xwoba_vs_rhb                       as away_starter_xwoba_vs_rhb,
        a_st.whiff_rate_vs_rhb                  as away_starter_whiff_rate_vs_rhb,

        -- ── Home team context ─────────────────────────────────────────────────
        h_tm.wins                               as home_wins,
        h_tm.losses                             as home_losses,
        h_tm.games_played                       as home_games_played,
        h_tm.win_pct                            as home_win_pct,
        h_tm.games_back                         as home_games_back,
        h_tm.streak_direction                   as home_streak_direction,
        h_tm.streak_length                      as home_streak_length,
        h_tm.off_runs_per_game_7d               as home_off_runs_per_game_7d,
        h_tm.off_runs_per_game_14d              as home_off_runs_per_game_14d,
        h_tm.off_runs_per_game_30d              as home_off_runs_per_game_30d,
        h_tm.off_runs_per_game_std              as home_off_runs_per_game_std,
        h_tm.off_woba_7d                        as home_off_woba_7d,
        h_tm.off_woba_14d                       as home_off_woba_14d,
        h_tm.off_woba_30d                       as home_off_woba_30d,
        h_tm.off_woba_std                       as home_off_woba_std,
        h_tm.off_xwoba_7d                       as home_off_xwoba_7d,
        h_tm.off_xwoba_14d                      as home_off_xwoba_14d,
        h_tm.off_xwoba_30d                      as home_off_xwoba_30d,
        h_tm.off_xwoba_std                      as home_off_xwoba_std,
        h_tm.off_k_pct_7d                       as home_off_k_pct_7d,
        h_tm.off_k_pct_30d                      as home_off_k_pct_30d,
        h_tm.off_k_pct_std                      as home_off_k_pct_std,
        h_tm.off_bb_pct_7d                      as home_off_bb_pct_7d,
        h_tm.off_bb_pct_30d                     as home_off_bb_pct_30d,
        h_tm.off_bb_pct_std                     as home_off_bb_pct_std,
        h_tm.off_hard_hit_pct_7d                as home_off_hard_hit_pct_7d,
        h_tm.off_hard_hit_pct_30d               as home_off_hard_hit_pct_30d,
        h_tm.off_hard_hit_pct_std               as home_off_hard_hit_pct_std,
        h_tm.off_barrel_pct_30d                 as home_off_barrel_pct_30d,
        h_tm.off_slugging_30d                   as home_off_slugging_30d,
        h_tm.pit_runs_allowed_7d                as home_pit_runs_allowed_7d,
        h_tm.pit_runs_allowed_14d               as home_pit_runs_allowed_14d,
        h_tm.pit_runs_allowed_30d               as home_pit_runs_allowed_30d,
        h_tm.pit_runs_allowed_std               as home_pit_runs_allowed_std,
        h_tm.pit_woba_against_7d                as home_pit_woba_against_7d,
        h_tm.pit_woba_against_14d               as home_pit_woba_against_14d,
        h_tm.pit_woba_against_30d               as home_pit_woba_against_30d,
        h_tm.pit_woba_against_std               as home_pit_woba_against_std,
        h_tm.pit_xwoba_against_7d               as home_pit_xwoba_against_7d,
        h_tm.pit_xwoba_against_14d              as home_pit_xwoba_against_14d,
        h_tm.pit_xwoba_against_30d              as home_pit_xwoba_against_30d,
        h_tm.pit_xwoba_against_std              as home_pit_xwoba_against_std,
        h_tm.pit_k_pct_7d                       as home_pit_k_pct_7d,
        h_tm.pit_k_pct_30d                      as home_pit_k_pct_30d,
        h_tm.pit_k_pct_std                      as home_pit_k_pct_std,
        h_tm.pit_bb_pct_7d                      as home_pit_bb_pct_7d,
        h_tm.pit_bb_pct_30d                     as home_pit_bb_pct_30d,
        h_tm.pit_bb_pct_std                     as home_pit_bb_pct_std,
        h_tm.pit_hard_hit_pct_7d                as home_pit_hard_hit_pct_7d,
        h_tm.pit_hard_hit_pct_30d               as home_pit_hard_hit_pct_30d,
        h_tm.pit_hard_hit_pct_std               as home_pit_hard_hit_pct_std,
        h_tm.pit_barrel_pct_30d                 as home_pit_barrel_pct_30d,
        h_tm.vs_lhp_woba_30d                    as home_vs_lhp_woba_30d,
        h_tm.vs_lhp_xwoba_30d                   as home_vs_lhp_xwoba_30d,
        h_tm.vs_lhp_k_pct_30d                   as home_vs_lhp_k_pct_30d,
        h_tm.vs_lhp_bb_pct_30d                  as home_vs_lhp_bb_pct_30d,
        h_tm.vs_lhp_hard_hit_pct_30d            as home_vs_lhp_hard_hit_pct_30d,
        h_tm.vs_lhp_slugging_30d                as home_vs_lhp_slugging_30d,
        h_tm.vs_lhp_woba_std                    as home_vs_lhp_woba_std,
        h_tm.vs_lhp_xwoba_std                   as home_vs_lhp_xwoba_std,
        h_tm.vs_rhp_woba_30d                    as home_vs_rhp_woba_30d,
        h_tm.vs_rhp_xwoba_30d                   as home_vs_rhp_xwoba_30d,
        h_tm.vs_rhp_k_pct_30d                   as home_vs_rhp_k_pct_30d,
        h_tm.vs_rhp_bb_pct_30d                  as home_vs_rhp_bb_pct_30d,
        h_tm.vs_rhp_hard_hit_pct_30d            as home_vs_rhp_hard_hit_pct_30d,
        h_tm.vs_rhp_slugging_30d                as home_vs_rhp_slugging_30d,
        h_tm.vs_rhp_woba_std                    as home_vs_rhp_woba_std,
        h_tm.vs_rhp_xwoba_std                   as home_vs_rhp_xwoba_std,
        h_tm.bullpen_pitches_prev_1d            as home_bullpen_pitches_prev_1d,
        h_tm.bullpen_pitches_prev_3d            as home_bullpen_pitches_prev_3d,
        h_tm.bullpen_pitches_prev_7d            as home_bullpen_pitches_prev_7d,
        h_tm.pitchers_used_prev_3d              as home_pitchers_used_prev_3d,
        h_tm.pitchers_used_prev_7d              as home_pitchers_used_prev_7d,
        h_tm.reliever_appearances_prev_3d       as home_reliever_appearances_prev_3d,
        h_tm.reliever_appearances_prev_7d       as home_reliever_appearances_prev_7d,
        h_tm.high_leverage_used_prev_2d         as home_high_leverage_used_prev_2d,
        h_tm.closer_used_prev_1d                as home_closer_used_prev_1d,
        h_tm.closer_used_prev_2d                as home_closer_used_prev_2d,
        h_tm.bp_k_pct_14d                       as home_bp_k_pct_14d,
        h_tm.bp_bb_pct_14d                      as home_bp_bb_pct_14d,
        h_tm.bp_xwoba_against_14d               as home_bp_xwoba_against_14d,
        h_tm.bp_hard_hit_pct_14d                as home_bp_hard_hit_pct_14d,
        h_tm.bp_whiff_rate_14d                  as home_bp_whiff_rate_14d,
        h_tm.bp_innings_pitched_14d             as home_bp_innings_pitched_14d,
        h_tm.bp_k_pct_30d                       as home_bp_k_pct_30d,
        h_tm.bp_bb_pct_30d                      as home_bp_bb_pct_30d,
        h_tm.bp_xwoba_against_30d               as home_bp_xwoba_against_30d,
        h_tm.bp_hard_hit_pct_30d                as home_bp_hard_hit_pct_30d,
        h_tm.bp_whiff_rate_30d                  as home_bp_whiff_rate_30d,
        h_tm.bp_innings_pitched_30d             as home_bp_innings_pitched_30d,
        h_tm.days_rest                          as home_days_rest,
        h_tm.games_last_7d                      as home_games_last_7d,
        h_tm.games_last_14d                     as home_games_last_14d,
        h_tm.consecutive_home_games             as home_consecutive_home_games,
        h_tm.consecutive_away_games             as home_consecutive_away_games,
        h_tm.tz_changed_from_last_game          as home_tz_changed_from_last_game,

        -- ── Away team context ─────────────────────────────────────────────────
        a_tm.wins                               as away_wins,
        a_tm.losses                             as away_losses,
        a_tm.games_played                       as away_games_played,
        a_tm.win_pct                            as away_win_pct,
        a_tm.games_back                         as away_games_back,
        a_tm.streak_direction                   as away_streak_direction,
        a_tm.streak_length                      as away_streak_length,
        a_tm.off_runs_per_game_7d               as away_off_runs_per_game_7d,
        a_tm.off_runs_per_game_14d              as away_off_runs_per_game_14d,
        a_tm.off_runs_per_game_30d              as away_off_runs_per_game_30d,
        a_tm.off_runs_per_game_std              as away_off_runs_per_game_std,
        a_tm.off_woba_7d                        as away_off_woba_7d,
        a_tm.off_woba_14d                       as away_off_woba_14d,
        a_tm.off_woba_30d                       as away_off_woba_30d,
        a_tm.off_woba_std                       as away_off_woba_std,
        a_tm.off_xwoba_7d                       as away_off_xwoba_7d,
        a_tm.off_xwoba_14d                      as away_off_xwoba_14d,
        a_tm.off_xwoba_30d                      as away_off_xwoba_30d,
        a_tm.off_xwoba_std                      as away_off_xwoba_std,
        a_tm.off_k_pct_7d                       as away_off_k_pct_7d,
        a_tm.off_k_pct_30d                      as away_off_k_pct_30d,
        a_tm.off_k_pct_std                      as away_off_k_pct_std,
        a_tm.off_bb_pct_7d                      as away_off_bb_pct_7d,
        a_tm.off_bb_pct_30d                     as away_off_bb_pct_30d,
        a_tm.off_bb_pct_std                     as away_off_bb_pct_std,
        a_tm.off_hard_hit_pct_7d                as away_off_hard_hit_pct_7d,
        a_tm.off_hard_hit_pct_30d               as away_off_hard_hit_pct_30d,
        a_tm.off_hard_hit_pct_std               as away_off_hard_hit_pct_std,
        a_tm.off_barrel_pct_30d                 as away_off_barrel_pct_30d,
        a_tm.off_slugging_30d                   as away_off_slugging_30d,
        a_tm.pit_runs_allowed_7d                as away_pit_runs_allowed_7d,
        a_tm.pit_runs_allowed_14d               as away_pit_runs_allowed_14d,
        a_tm.pit_runs_allowed_30d               as away_pit_runs_allowed_30d,
        a_tm.pit_runs_allowed_std               as away_pit_runs_allowed_std,
        a_tm.pit_woba_against_7d                as away_pit_woba_against_7d,
        a_tm.pit_woba_against_14d               as away_pit_woba_against_14d,
        a_tm.pit_woba_against_30d               as away_pit_woba_against_30d,
        a_tm.pit_woba_against_std               as away_pit_woba_against_std,
        a_tm.pit_xwoba_against_7d               as away_pit_xwoba_against_7d,
        a_tm.pit_xwoba_against_14d              as away_pit_xwoba_against_14d,
        a_tm.pit_xwoba_against_30d              as away_pit_xwoba_against_30d,
        a_tm.pit_xwoba_against_std              as away_pit_xwoba_against_std,
        a_tm.pit_k_pct_7d                       as away_pit_k_pct_7d,
        a_tm.pit_k_pct_30d                      as away_pit_k_pct_30d,
        a_tm.pit_k_pct_std                      as away_pit_k_pct_std,
        a_tm.pit_bb_pct_7d                      as away_pit_bb_pct_7d,
        a_tm.pit_bb_pct_30d                     as away_pit_bb_pct_30d,
        a_tm.pit_bb_pct_std                     as away_pit_bb_pct_std,
        a_tm.pit_hard_hit_pct_7d                as away_pit_hard_hit_pct_7d,
        a_tm.pit_hard_hit_pct_30d               as away_pit_hard_hit_pct_30d,
        a_tm.pit_hard_hit_pct_std               as away_pit_hard_hit_pct_std,
        a_tm.pit_barrel_pct_30d                 as away_pit_barrel_pct_30d,
        a_tm.vs_lhp_woba_30d                    as away_vs_lhp_woba_30d,
        a_tm.vs_lhp_xwoba_30d                   as away_vs_lhp_xwoba_30d,
        a_tm.vs_lhp_k_pct_30d                   as away_vs_lhp_k_pct_30d,
        a_tm.vs_lhp_bb_pct_30d                  as away_vs_lhp_bb_pct_30d,
        a_tm.vs_lhp_hard_hit_pct_30d            as away_vs_lhp_hard_hit_pct_30d,
        a_tm.vs_lhp_slugging_30d                as away_vs_lhp_slugging_30d,
        a_tm.vs_lhp_woba_std                    as away_vs_lhp_woba_std,
        a_tm.vs_lhp_xwoba_std                   as away_vs_lhp_xwoba_std,
        a_tm.vs_rhp_woba_30d                    as away_vs_rhp_woba_30d,
        a_tm.vs_rhp_xwoba_30d                   as away_vs_rhp_xwoba_30d,
        a_tm.vs_rhp_k_pct_30d                   as away_vs_rhp_k_pct_30d,
        a_tm.vs_rhp_bb_pct_30d                  as away_vs_rhp_bb_pct_30d,
        a_tm.vs_rhp_hard_hit_pct_30d            as away_vs_rhp_hard_hit_pct_30d,
        a_tm.vs_rhp_slugging_30d                as away_vs_rhp_slugging_30d,
        a_tm.vs_rhp_woba_std                    as away_vs_rhp_woba_std,
        a_tm.vs_rhp_xwoba_std                   as away_vs_rhp_xwoba_std,
        a_tm.bullpen_pitches_prev_1d            as away_bullpen_pitches_prev_1d,
        a_tm.bullpen_pitches_prev_3d            as away_bullpen_pitches_prev_3d,
        a_tm.bullpen_pitches_prev_7d            as away_bullpen_pitches_prev_7d,
        a_tm.pitchers_used_prev_3d              as away_pitchers_used_prev_3d,
        a_tm.pitchers_used_prev_7d              as away_pitchers_used_prev_7d,
        a_tm.reliever_appearances_prev_3d       as away_reliever_appearances_prev_3d,
        a_tm.reliever_appearances_prev_7d       as away_reliever_appearances_prev_7d,
        a_tm.high_leverage_used_prev_2d         as away_high_leverage_used_prev_2d,
        a_tm.closer_used_prev_1d                as away_closer_used_prev_1d,
        a_tm.closer_used_prev_2d                as away_closer_used_prev_2d,
        a_tm.bp_k_pct_14d                       as away_bp_k_pct_14d,
        a_tm.bp_bb_pct_14d                      as away_bp_bb_pct_14d,
        a_tm.bp_xwoba_against_14d               as away_bp_xwoba_against_14d,
        a_tm.bp_hard_hit_pct_14d                as away_bp_hard_hit_pct_14d,
        a_tm.bp_whiff_rate_14d                  as away_bp_whiff_rate_14d,
        a_tm.bp_innings_pitched_14d             as away_bp_innings_pitched_14d,
        a_tm.bp_k_pct_30d                       as away_bp_k_pct_30d,
        a_tm.bp_bb_pct_30d                      as away_bp_bb_pct_30d,
        a_tm.bp_xwoba_against_30d               as away_bp_xwoba_against_30d,
        a_tm.bp_hard_hit_pct_30d                as away_bp_hard_hit_pct_30d,
        a_tm.bp_whiff_rate_30d                  as away_bp_whiff_rate_30d,
        a_tm.bp_innings_pitched_30d             as away_bp_innings_pitched_30d,
        a_tm.days_rest                          as away_days_rest,
        a_tm.games_last_7d                      as away_games_last_7d,
        a_tm.games_last_14d                     as away_games_last_14d,
        a_tm.consecutive_home_games             as away_consecutive_home_games,
        a_tm.consecutive_away_games             as away_consecutive_away_games,
        a_tm.tz_changed_from_last_game          as away_tz_changed_from_last_game,

        -- ── Park features ─────────────────────────────────────────────────────
        pk.elevation_ft,
        pk.turf_type,
        pk.roof_type,
        pk.left_line_ft,
        pk.left_ft,
        pk.left_center_ft,
        pk.center_ft,
        pk.right_center_ft,
        pk.right_line_ft,
        pk.runs_per_game_at_park,
        pk.park_run_factor_3yr

    from games g
    left join home_lineup h_ln  on  h_ln.game_pk = g.game_pk
    left join away_lineup a_ln  on  a_ln.game_pk = g.game_pk
    left join home_starter h_st on  h_st.game_pk = g.game_pk
    left join away_starter a_st on  a_st.game_pk = g.game_pk
    left join home_team h_tm    on  h_tm.game_pk = g.game_pk
    left join away_team a_tm    on  a_tm.game_pk = g.game_pk
    left join {{ ref('feature_pregame_park_features') }} pk
        on  pk.game_pk = g.game_pk
)

select * from final

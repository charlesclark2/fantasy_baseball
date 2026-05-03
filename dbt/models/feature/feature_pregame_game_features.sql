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

odds as (
    select * from {{ ref('feature_pregame_odds_features') }}
),

weather as (
    select * from {{ ref('feature_pregame_weather_features') }}
),

umpire_feats as (
    select * from {{ ref('feature_pregame_umpire_features') }}
),

game_context as (
    select
        game_pk,
        (day_night = 'day')::boolean    as is_day_game,
        series_game_number
    from {{ ref('stg_statsapi_games') }}
),

home_win_rate as (
    select
        spine.game_pk,
        round(
            avg(hist.home_team_won::integer)
        , 4)                            as home_win_rate_trailing_3yr
    from games spine
    left join {{ ref('mart_game_results') }} hist
        on  hist.game_type = 'R'
        and hist.game_date::date >= dateadd('year', -3, spine.game_date)
        and hist.game_date::date <  spine.game_date
        and hist.home_team_won is not null
    group by spine.game_pk
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

        -- ── Game context and era flags ────────────────────────────────────────
        gc.is_day_game,
        gc.series_game_number,
        hwr.home_win_rate_trailing_3yr,
        (g.game_year >= 2023)::boolean          as post_2022_rules,

        -- ── Data completeness flags ────────────────────────────────────────────
        -- has_full_data: both lineups confirmed, both starters have prior history,
        -- park has prior-season run factor. Use for data-complete training subset.
        (
            coalesce(h_ln.has_full_lineup,       false)
            and coalesce(a_ln.has_full_lineup,   false)
            and coalesce(h_st.has_starter_data,  false)
            and coalesce(a_st.has_starter_data,  false)
            and pk.runs_per_game_at_park is not null
        )::boolean                              as has_full_data,

        -- has_odds: event_id matched in mart_game_odds_bridge (does not guarantee
        -- price columns are populated — Card 3 backfill is partial).
        -- Intentionally excluded from has_full_data: odds are an optional block.
        od.has_odds,

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

        -- ── Home injury-adjusted lineup quality (Card 7.I) ────────────────────
        h_ln.injured_player_count               as home_injured_player_count,
        h_ln.injury_adj_avg_woba_30d            as home_injury_adj_avg_woba_30d,
        h_ln.injury_adj_avg_xwoba_30d           as home_injury_adj_avg_xwoba_30d,

        -- ── Home lineup vs. starter pitch-archetype matchup (Card 7.J) ────────
        h_ln.lineup_woba_vs_starter_archetype   as home_lineup_woba_vs_starter_archetype,
        h_ln.lineup_xwoba_vs_starter_archetype  as home_lineup_xwoba_vs_starter_archetype,
        h_ln.lineup_k_pct_vs_starter_archetype  as home_lineup_k_pct_vs_starter_archetype,
        h_ln.lineup_iso_vs_starter_archetype    as home_lineup_iso_vs_starter_archetype,
        h_ln.lineup_archetype_pa_coverage       as home_lineup_archetype_pa_coverage,
        h_ln.starter_pitch_archetype            as home_starter_pitch_archetype,

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

        -- ── Away injury-adjusted lineup quality (Card 7.I) ────────────────────
        a_ln.injured_player_count               as away_injured_player_count,
        a_ln.injury_adj_avg_woba_30d            as away_injury_adj_avg_woba_30d,
        a_ln.injury_adj_avg_xwoba_30d           as away_injury_adj_avg_xwoba_30d,

        -- ── Away lineup vs. starter pitch-archetype matchup (Card 7.J) ────────
        a_ln.lineup_woba_vs_starter_archetype   as away_lineup_woba_vs_starter_archetype,
        a_ln.lineup_xwoba_vs_starter_archetype  as away_lineup_xwoba_vs_starter_archetype,
        a_ln.lineup_k_pct_vs_starter_archetype  as away_lineup_k_pct_vs_starter_archetype,
        a_ln.lineup_iso_vs_starter_archetype    as away_lineup_iso_vs_starter_archetype,
        a_ln.lineup_archetype_pa_coverage       as away_lineup_archetype_pa_coverage,
        a_ln.starter_pitch_archetype            as away_starter_pitch_archetype,

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
        h_st.k_pct_7d_minus_std                 as home_starter_k_pct_7d_minus_std,
        h_st.xwoba_7d_minus_std                 as home_starter_xwoba_7d_minus_std,
        h_st.appearances_30d                    as home_starter_appearances_30d,
        h_st.appearances_std                    as home_starter_appearances_std,
        h_st.k_pct_vs_lhb                       as home_starter_k_pct_vs_lhb,
        h_st.bb_pct_vs_lhb                      as home_starter_bb_pct_vs_lhb,
        h_st.xwoba_vs_lhb                       as home_starter_xwoba_vs_lhb,
        h_st.whiff_rate_vs_lhb                  as home_starter_whiff_rate_vs_lhb,
        h_st.k_pct_vs_rhb                       as home_starter_k_pct_vs_rhb,
        h_st.bb_pct_vs_rhb                      as home_starter_bb_pct_vs_rhb,
        h_st.xwoba_vs_rhb                       as home_starter_xwoba_vs_rhb,
        h_st.whiff_rate_vs_rhb                  as home_starter_whiff_rate_vs_rhb,
        h_st.avg_ip_last_3                      as home_starter_avg_ip_last_3,
        h_st.avg_ip_season                      as home_starter_avg_ip_season,
        h_st.has_ip_history                     as home_starter_has_ip_history,

        -- ── Home starter: FanGraphs Stuff+ arsenal features (Card 7.F) ────────
        h_st.starter_stuff_plus                 as home_starter_stuff_plus,
        h_st.starter_primary_pitch_type         as home_starter_primary_pitch_type,
        h_st.starter_fastball_pct               as home_starter_fastball_pct,
        h_st.starter_breaking_pct               as home_starter_breaking_pct,
        h_st.starter_offspeed_pct               as home_starter_offspeed_pct,
        h_st.starter_fastball_stuff_plus        as home_starter_fastball_stuff_plus,
        h_st.starter_slider_stuff_plus          as home_starter_slider_stuff_plus,
        h_st.starter_curveball_stuff_plus       as home_starter_curveball_stuff_plus,
        h_st.starter_changeup_stuff_plus        as home_starter_changeup_stuff_plus,
        h_st.starter_avg_fastball_velo          as home_starter_avg_fastball_velo,

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
        a_st.k_pct_7d_minus_std                 as away_starter_k_pct_7d_minus_std,
        a_st.xwoba_7d_minus_std                 as away_starter_xwoba_7d_minus_std,
        a_st.appearances_30d                    as away_starter_appearances_30d,
        a_st.appearances_std                    as away_starter_appearances_std,
        a_st.k_pct_vs_lhb                       as away_starter_k_pct_vs_lhb,
        a_st.bb_pct_vs_lhb                      as away_starter_bb_pct_vs_lhb,
        a_st.xwoba_vs_lhb                       as away_starter_xwoba_vs_lhb,
        a_st.whiff_rate_vs_lhb                  as away_starter_whiff_rate_vs_lhb,
        a_st.k_pct_vs_rhb                       as away_starter_k_pct_vs_rhb,
        a_st.bb_pct_vs_rhb                      as away_starter_bb_pct_vs_rhb,
        a_st.xwoba_vs_rhb                       as away_starter_xwoba_vs_rhb,
        a_st.whiff_rate_vs_rhb                  as away_starter_whiff_rate_vs_rhb,
        a_st.avg_ip_last_3                      as away_starter_avg_ip_last_3,
        a_st.avg_ip_season                      as away_starter_avg_ip_season,
        a_st.has_ip_history                     as away_starter_has_ip_history,

        -- ── Away starter: FanGraphs Stuff+ arsenal features (Card 7.F) ────────
        a_st.starter_stuff_plus                 as away_starter_stuff_plus,
        a_st.starter_primary_pitch_type         as away_starter_primary_pitch_type,
        a_st.starter_fastball_pct               as away_starter_fastball_pct,
        a_st.starter_breaking_pct               as away_starter_breaking_pct,
        a_st.starter_offspeed_pct               as away_starter_offspeed_pct,
        a_st.starter_fastball_stuff_plus        as away_starter_fastball_stuff_plus,
        a_st.starter_slider_stuff_plus          as away_starter_slider_stuff_plus,
        a_st.starter_curveball_stuff_plus       as away_starter_curveball_stuff_plus,
        a_st.starter_changeup_stuff_plus        as away_starter_changeup_stuff_plus,
        a_st.starter_avg_fastball_velo          as away_starter_avg_fastball_velo,

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
        h_tm.off_woba_7d_minus_30d              as home_off_woba_7d_minus_30d,
        h_tm.pit_xwoba_7d_minus_30d             as home_pit_xwoba_7d_minus_30d,
        h_tm.off_games_played_7d                as home_games_played_7d,
        h_tm.off_games_played_14d               as home_games_played_14d,
        h_tm.off_games_played_30d               as home_games_played_30d,
        h_tm.off_games_played_std               as home_games_played_std,

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
        a_tm.off_woba_7d_minus_30d              as away_off_woba_7d_minus_30d,
        a_tm.pit_xwoba_7d_minus_30d             as away_pit_xwoba_7d_minus_30d,
        a_tm.off_games_played_7d                as away_games_played_7d,
        a_tm.off_games_played_14d               as away_games_played_14d,
        a_tm.off_games_played_30d               as away_games_played_30d,
        a_tm.off_games_played_std               as away_games_played_std,

        -- ── Lineup-vs-starter handedness matchup adjustments ─────────────────
        -- Weighted average of the opposing starter's platoon splits, weighted by
        -- the lineup's handedness composition (pct_rhb × split_vs_rhb + pct_lhb × split_vs_lhb).
        -- Null when starter platoon splits are null (debut pitcher or first-season data gap).
        -- Null when the lineup has zero batters with known handedness (nullif guard).

        -- Home offense vs away starter
        round(
            (h_ln.rhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.xwoba_vs_rhb
            + (h_ln.lhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.xwoba_vs_lhb
        , 3)                                    as home_lineup_vs_away_starter_xwoba_adj,

        round(
            (h_ln.rhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.k_pct_vs_rhb
            + (h_ln.lhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.k_pct_vs_lhb
        , 3)                                    as home_lineup_vs_away_starter_k_pct_adj,

        round(
            (h_ln.rhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.bb_pct_vs_rhb
            + (h_ln.lhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
                * a_st.bb_pct_vs_lhb
        , 3)                                    as home_lineup_vs_away_starter_bb_pct_adj,

        -- Away offense vs home starter
        round(
            (a_ln.rhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.xwoba_vs_rhb
            + (a_ln.lhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.xwoba_vs_lhb
        , 3)                                    as away_lineup_vs_home_starter_xwoba_adj,

        round(
            (a_ln.rhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.k_pct_vs_rhb
            + (a_ln.lhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.k_pct_vs_lhb
        , 3)                                    as away_lineup_vs_home_starter_k_pct_adj,

        round(
            (a_ln.rhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.bb_pct_vs_rhb
            + (a_ln.lhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
                * h_st.bb_pct_vs_lhb
        , 3)                                    as away_lineup_vs_home_starter_bb_pct_adj,

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
        pk.park_run_factor_3yr,

        -- ── Betting market features ────────────────────────────────────────────
        od.odds_bookmaker_key,
        od.odds_ingestion_ts,
        od.odds_hours_before_game,
        od.home_moneyline_american,
        od.away_moneyline_american,
        od.home_moneyline_decimal,
        od.away_moneyline_decimal,
        od.home_implied_prob,
        od.away_implied_prob,
        od.total_market_vig,
        od.total_line,
        od.over_american,
        od.under_american,
        od.over_implied_prob,
        od.under_implied_prob,
        od.totals_market_vig,

        -- ── Consensus market features (mart_odds_consensus, Card 3.11) ────────
        od.home_win_prob_consensus,
        od.home_win_prob_sharp,
        od.home_win_prob_soft,
        od.sharp_soft_ml_delta,
        od.ml_consensus_std,
        od.market_bookmaker_count,
        od.total_line_consensus,
        od.total_line_std,
        od.over_prob_consensus,

        -- ── Weather features ──────────────────────────────────────────────────
        -- NULL for dome parks; imputation applied in Python preprocessing layer.
        wpf.temp_f,
        wpf.wind_speed_mph,
        wpf.wind_direction_deg,
        wpf.wind_component_mph,
        wpf.humidity_pct,
        wpf.is_dome,

        -- ── HP umpire tendency features (Card 7.H) ────────────────────────────
        -- Trailing 3-year z-scores relative to league average.
        -- NULL when no HP umpire is listed for the game.
        uf.umpire_name,
        uf.ump_games_sample,
        uf.ump_k_pct_zscore,
        uf.ump_bb_pct_zscore,
        uf.ump_runs_per_game_zscore,
        uf.ump_run_impact_zscore,
        uf.ump_accuracy_zscore

    from games g
    left join home_lineup h_ln  on  h_ln.game_pk = g.game_pk
    left join away_lineup a_ln  on  a_ln.game_pk = g.game_pk
    left join home_starter h_st on  h_st.game_pk = g.game_pk
    left join away_starter a_st on  a_st.game_pk = g.game_pk
    left join home_team h_tm    on  h_tm.game_pk = g.game_pk
    left join away_team a_tm    on  a_tm.game_pk = g.game_pk
    left join {{ ref('feature_pregame_park_features') }} pk
        on  pk.game_pk = g.game_pk
    left join odds od
        on  od.game_pk = g.game_pk
    left join game_context gc
        on  gc.game_pk = g.game_pk
    left join home_win_rate hwr
        on  hwr.game_pk = g.game_pk
    left join weather wpf
        on  wpf.game_pk = g.game_pk
    left join umpire_feats uf
        on  uf.game_pk = g.game_pk
)

select * from final

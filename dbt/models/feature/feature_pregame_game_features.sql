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

cluster_matchups as (
    select * from {{ ref('feature_pitcher_cluster_matchups') }}
),

batter_archetype_matchups as (
    select * from {{ ref('feature_batter_archetype_matchups') }}
),

h2h_matchups as (
    select * from {{ ref('feature_pitcher_batter_h2h_matchups') }}
),

line_movement as (
    select * from {{ ref('mart_odds_line_movement') }}
    where bookmaker = 'bovada'
    -- Future enhancement: make bookmaker configurable via a dbt variable
),

bookmaker_disagreement as (
    select * from {{ ref('mart_bookmaker_disagreement') }}
),

-- Card 8.R — Action Network public betting percentages (joined on
-- game_date + normalized team abbreviations). Doubleheaders produce two
-- distinct an_game_id rows on the same date for the same matchup; dedupe
-- to one row per (game_date, home, away) to keep the join 1:1 against
-- mart_game_results. Both halves of a doubleheader inherit the same
-- aggregated public-betting percentages (Action Network does not
-- differentiate the two games at the public-betting grain).
public_betting as (
    select
        game_date,
        home_team_id,
        away_team_id,
        home_ml_money_pct,
        home_ml_ticket_pct,
        over_money_pct,
        over_ticket_pct,
        ml_sharp_signal,
        total_sharp_signal
    from (
        select
            *,
            row_number() over (
                partition by game_date, home_team_id, away_team_id
                order by ingestion_timestamp desc, an_game_id
            ) as rn
        from {{ ref('stg_actionnetwork_public_betting') }}
    )
    where rn = 1
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
        h_st.velo_delta_3start                  as home_starter_velo_delta_3start,
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

        -- ── Home starter: ZiPS FIP projections and trailing FIP/RA9 (Card 8.B) ─
        h_st.starter_proj_fip                   as home_starter_proj_fip,
        h_st.starter_proj_xfip                  as home_starter_proj_xfip,
        h_st.starter_trailing_fip_30g           as home_starter_trailing_fip_30g,
        h_st.starter_trailing_ra9_30g           as home_starter_trailing_ra9_30g,
        h_st.starter_fip_ra9_gap                as home_starter_fip_ra9_gap,

        -- ── Home starter: CSW% rolling stats (Card 8.Q) ──────────────────────
        -- NULL for debut starters; imputed to ~0.285 in preprocessing.py.
        h_st.csw_pct_3start                     as home_starter_csw_pct_3start,
        h_st.csw_pct_season                     as home_starter_csw_pct_season,

        -- ── Home starter: arsenal drift (Card 8.M) ───────────────────────────
        -- Trailing 5-start mix pct minus season-to-date mix pct, per pitch
        -- group. 0.0 (no drift) for starters with < 5 career starts.
        h_st.fastball_pct_drift_5start          as home_starter_fastball_pct_drift_5start,
        h_st.breaking_pct_drift_5start          as home_starter_breaking_pct_drift_5start,
        h_st.offspeed_pct_drift_5start          as home_starter_offspeed_pct_drift_5start,

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
        a_st.velo_delta_3start                  as away_starter_velo_delta_3start,
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

        -- ── Away starter: ZiPS FIP projections and trailing FIP/RA9 (Card 8.B) ─
        a_st.starter_proj_fip                   as away_starter_proj_fip,
        a_st.starter_proj_xfip                  as away_starter_proj_xfip,
        a_st.starter_trailing_fip_30g           as away_starter_trailing_fip_30g,
        a_st.starter_trailing_ra9_30g           as away_starter_trailing_ra9_30g,
        a_st.starter_fip_ra9_gap                as away_starter_fip_ra9_gap,

        -- ── Away starter: CSW% rolling stats (Card 8.Q) ──────────────────────
        -- NULL for debut starters; imputed to ~0.285 in preprocessing.py.
        a_st.csw_pct_3start                     as away_starter_csw_pct_3start,
        a_st.csw_pct_season                     as away_starter_csw_pct_season,

        -- ── Away starter: arsenal drift (Card 8.M) ───────────────────────────
        -- Trailing 5-start mix pct minus season-to-date mix pct, per pitch
        -- group. 0.0 (no drift) for starters with < 5 career starts.
        a_st.fastball_pct_drift_5start          as away_starter_fastball_pct_drift_5start,
        a_st.breaking_pct_drift_5start          as away_starter_breaking_pct_drift_5start,
        a_st.offspeed_pct_drift_5start          as away_starter_offspeed_pct_drift_5start,

        -- ── Home team context ─────────────────────────────────────────────────
        h_tm.wins                               as home_wins,
        h_tm.losses                             as home_losses,
        h_tm.games_played                       as home_games_played,
        h_tm.win_pct                            as home_win_pct,
        h_tm.pythagorean_win_exp                as home_pythagorean_win_exp,
        h_tm.pythagorean_residual_season        as home_pythagorean_residual_season,   -- Card 8.X
        h_tm.pythagorean_residual_30d           as home_pythagorean_residual_30d,      -- Card 8.X
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
        h_tm.bullpen_ip_prev_1d                 as home_bullpen_ip_prev_1d,
        h_tm.bullpen_ip_prev_2d                 as home_bullpen_ip_prev_2d,
        h_tm.pitchers_used_prev_2d              as home_pitchers_used_prev_2d,
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
        a_tm.pythagorean_win_exp                as away_pythagorean_win_exp,
        a_tm.pythagorean_residual_season        as away_pythagorean_residual_season,   -- Card 8.X
        a_tm.pythagorean_residual_30d           as away_pythagorean_residual_30d,      -- Card 8.X
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
        a_tm.bullpen_ip_prev_1d                 as away_bullpen_ip_prev_1d,
        a_tm.bullpen_ip_prev_2d                 as away_bullpen_ip_prev_2d,
        a_tm.pitchers_used_prev_2d              as away_pitchers_used_prev_2d,
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

        -- ── Elo team strength ratings (Card 8.D) ─────────────────────────────
        -- Pre-game snapshot from compute_elo.py. NULL until backfill is run.
        h_tm.elo_rating                         as home_elo,
        a_tm.elo_rating                         as away_elo,
        h_tm.elo_rating - a_tm.elo_rating       as elo_diff,

        -- ── Team defensive quality: OAA (Card 8.C) ───────────────────────────
        -- Prior-season OAA from FanGraphs. NULL pre-2017 (no 2016 prior season).
        -- team_oaa_blended coalesces NULL to 0 (league average).
        h_tm.team_oaa_prior_season              as home_team_oaa_prior_season,
        a_tm.team_oaa_prior_season              as away_team_oaa_prior_season,
        h_tm.team_oaa_blended                   as home_team_oaa_blended,
        a_tm.team_oaa_blended                   as away_team_oaa_blended,

        -- ── Pythagorean win expectation differential ───────────────────────────
        round(
            h_tm.pythagorean_win_exp - a_tm.pythagorean_win_exp,
            4
        )                                       as pythagorean_win_exp_diff,

        -- Card 8.X — pythagorean residual differential (home − away, season-level).
        -- Imputed to 0.0 in preprocessing.py when either side is NULL (early
        -- season; reliability gate is 10 games of cumulative play).
        round(
            h_tm.pythagorean_residual_season - a_tm.pythagorean_residual_season,
            4
        )                                       as pythagorean_residual_diff,

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
        uf.ump_accuracy_zscore,

        -- ── Pitcher cluster matchup features (Card 7.K) ───────────────────────
        -- Rolling wOBA each lineup scored vs. pitchers in the opposing starter's
        -- cluster. Null before 2021 (cluster data begins 2020, prior-season lag).
        cm.home_lineup_avg_woba_vs_cluster,
        cm.home_lineup_avg_xwoba_vs_cluster,
        cm.home_lineup_cluster_slot_coverage,
        cm.away_lineup_avg_woba_vs_cluster,
        cm.away_lineup_avg_xwoba_vs_cluster,
        cm.away_lineup_cluster_slot_coverage,
        cm.home_starter_cluster_id,
        cm.away_starter_cluster_id,

        -- ── Batter archetype × pitcher archetype matchup features (Card 7.K2) ──
        -- Population-level expected wOBA based on lineup batter archetypes vs.
        -- opposing starter's pitcher cluster. Null before 2021 (prior-season lag).
        bam.home_lineup_archetype_avg_woba,
        bam.home_lineup_archetype_avg_xwoba,
        bam.home_lineup_archetype_slot_coverage,
        bam.away_lineup_archetype_avg_woba,
        bam.away_lineup_archetype_avg_xwoba,
        bam.away_lineup_archetype_slot_coverage,
        bam.home_batter_cluster_mode,
        bam.away_batter_cluster_mode,

        -- ── Line movement features (Card 7.P3) ───────────────────────────────────
        -- Bookmaker: bovada (matches odds_snapshots_historical Card 7.P2 backfill).
        -- h2h_line_movement / total_line_movement imputed to 0.0 when only 1 snapshot
        -- exists (no detectable sharp action = meaningful signal, not missing data).
        -- open_home_win_prob / open_total_line left NULL — imputing 0.0 for a
        -- probability is semantically meaningless; models handle nulls or exclude.
        coalesce(lm.h2h_line_movement,  0.0)    as home_h2h_line_movement,
        lm.open_home_win_prob                   as home_open_win_prob,
        coalesce(lm.total_line_movement, 0.0)   as total_line_movement,
        lm.open_total_line,

        -- ── Bookmaker disagreement features (Card 8.T) ───────────────────────────
        -- Morning snapshot dispersion across books. NULL when fewer than 2 books
        -- have morning odds coverage. Imputed in preprocessing.py.
        bd.ml_implied_prob_std,
        bd.ml_implied_prob_range,
        bd.totals_line_std,
        bd.totals_line_range,
        bd.sharp_soft_ml_spread,
        bd.n_books_available,
        bd.stale_book_flag,

        -- ── Percentage-difference encoded matchup features (Card 8.A) ─────────────
        -- (home_val - away_val) / ABS(away_val) * 100; positive = home advantage.
        -- NULL when away denominator is 0 or NULL.
        case when a_tm.off_woba_30d = 0 or a_tm.off_woba_30d is null then null
             else round((h_tm.off_woba_30d - a_tm.off_woba_30d) / abs(a_tm.off_woba_30d) * 100, 4)
        end                                     as home_away_off_woba_30d_pct_diff,

        case when a_tm.off_xwoba_30d = 0 or a_tm.off_xwoba_30d is null then null
             else round((h_tm.off_xwoba_30d - a_tm.off_xwoba_30d) / abs(a_tm.off_xwoba_30d) * 100, 4)
        end                                     as home_away_off_xwoba_30d_pct_diff,

        case when a_tm.off_k_pct_30d = 0 or a_tm.off_k_pct_30d is null then null
             else round((h_tm.off_k_pct_30d - a_tm.off_k_pct_30d) / abs(a_tm.off_k_pct_30d) * 100, 4)
        end                                     as home_away_off_k_pct_30d_pct_diff,

        case when a_st.xwoba_against_std = 0 or a_st.xwoba_against_std is null then null
             else round((h_st.xwoba_against_std - a_st.xwoba_against_std) / abs(a_st.xwoba_against_std) * 100, 4)
        end                                     as home_away_starter_xwoba_against_std_pct_diff,

        case when a_st.k_pct_std = 0 or a_st.k_pct_std is null then null
             else round((h_st.k_pct_std - a_st.k_pct_std) / abs(a_st.k_pct_std) * 100, 4)
        end                                     as home_away_starter_k_pct_std_pct_diff,

        case when a_tm.bp_xwoba_against_30d = 0 or a_tm.bp_xwoba_against_30d is null then null
             else round((h_tm.bp_xwoba_against_30d - a_tm.bp_xwoba_against_30d) / abs(a_tm.bp_xwoba_against_30d) * 100, 4)
        end                                     as home_away_bp_xwoba_against_30d_pct_diff,

        case when a_ln.injury_adj_avg_woba_30d = 0 or a_ln.injury_adj_avg_woba_30d is null then null
             else round((h_ln.injury_adj_avg_woba_30d - a_ln.injury_adj_avg_woba_30d) / abs(a_ln.injury_adj_avg_woba_30d) * 100, 4)
        end                                     as home_away_injury_adj_avg_woba_30d_pct_diff,

        case when a_tm.pythagorean_win_exp = 0 or a_tm.pythagorean_win_exp is null then null
             else round((h_tm.pythagorean_win_exp - a_tm.pythagorean_win_exp) / abs(a_tm.pythagorean_win_exp) * 100, 4)
        end                                     as home_away_pythagorean_win_exp_pct_diff,

        -- ── Bullpen handedness matchup quality (Card 8.L) ────────────────────
        -- home_bp_matchup_xwoba: expected xwOBA the home lineup generates vs the
        -- away bullpen, weighted by the home lineup's LHB/RHB composition.
        -- away_bp_matchup_xwoba: same metric for the away lineup vs the home bullpen.
        -- Higher value = more permissive bullpen for that lineup composition.
        -- NULL when bullpen handedness splits or lineup counts are unavailable.
        round(
            a_bph.bp_xwoba_vs_rhb_30d
                * (h_ln.rhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
            + a_bph.bp_xwoba_vs_lhb_30d
                * (h_ln.lhb_count::float / nullif(h_ln.lhb_count + h_ln.rhb_count, 0))
        , 4)                                    as home_bp_matchup_xwoba,

        round(
            h_bph.bp_xwoba_vs_rhb_30d
                * (a_ln.rhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
            + h_bph.bp_xwoba_vs_lhb_30d
                * (a_ln.lhb_count::float / nullif(a_ln.lhb_count + a_ln.rhb_count, 0))
        , 4)                                    as away_bp_matchup_xwoba,

        -- ── Bullpen leverage exhaustion (Card 8.U) ───────────────────────────
        -- Leverage = sum |delta_home_win_exp| per reliever plate appearance,
        -- rolling over the trailing 1 and 3 calendar days. Captures situational
        -- intensity beyond raw inning/pitch counts from mart_bullpen_workload.
        -- NULL when no reliever appearances in the trailing window. Impute 0.0.
        h_blev.bp_leverage_sum_3d               as home_bp_leverage_sum_3d,
        a_blev.bp_leverage_sum_3d               as away_bp_leverage_sum_3d,
        h_blev.bp_high_lev_appearances_3d       as home_bp_high_lev_appearances_3d,
        a_blev.bp_high_lev_appearances_3d       as away_bp_high_lev_appearances_3d,
        h_blev.bp_leverage_sum_1d               as home_bp_leverage_sum_1d,
        a_blev.bp_leverage_sum_1d               as away_bp_leverage_sum_1d,

        -- ── Catcher metrics (Card 8.K) ────────────────────────────────────────
        -- Source: FanGraphs leaderboard API (xMLBAMID → MLBAM player_id).
        -- Blended 70% current + 30% prior season, regressed toward 0 for < 60 innings.
        -- 0 = league average; imputed to 0 when catcher or lineup is unavailable.
        -- framing_runs: CFraming (pure pitch-framing)
        -- defensive_runs: FRP (framing + blocking + arm + range — comprehensive)
        coalesce(h_ln.catcher_framing_runs,   0) as home_catcher_framing_runs,
        coalesce(a_ln.catcher_framing_runs,   0) as away_catcher_framing_runs,
        coalesce(h_ln.catcher_defensive_runs, 0) as home_catcher_defensive_runs,
        coalesce(a_ln.catcher_defensive_runs, 0) as away_catcher_defensive_runs,

        -- ── Bat tracking matchup features (Card 8.E) ─────────────────────────
        -- NULL for pre-2023-07-14 games (Hawk-Eye bat sensors not available).
        -- ~50% of 2021+ training rows will be NULL; impute league average in
        -- preprocessing.py. lineup_bat_speed_vs_starter_velo > 1.0 means the
        -- lineup's bat speed exceeds the opposing starter's fastball velocity.
        h_ln.lineup_avg_bat_speed               as home_lineup_avg_bat_speed,
        h_ln.lineup_bat_speed_std               as home_lineup_bat_speed_std,
        h_ln.lineup_avg_swing_length            as home_lineup_avg_swing_length,
        h_ln.lineup_avg_attack_angle            as home_lineup_avg_attack_angle,
        h_ln.lineup_bat_speed_vs_starter_velo   as home_lineup_bat_speed_vs_starter_velo,
        a_ln.lineup_avg_bat_speed               as away_lineup_avg_bat_speed,
        a_ln.lineup_bat_speed_std               as away_lineup_bat_speed_std,
        a_ln.lineup_avg_swing_length            as away_lineup_avg_swing_length,
        a_ln.lineup_avg_attack_angle            as away_lineup_avg_attack_angle,
        a_ln.lineup_bat_speed_vs_starter_velo   as away_lineup_bat_speed_vs_starter_velo,

        -- ── Pitcher-batter H2H matchup history (Card 8.J) ────────────────────
        -- Lineup-average Bayesian-shrunk wOBA / xwOBA each batter has produced
        -- against the OPPOSING starter, weighted toward a league prior at low
        -- PA counts (k=50, woba_prior=0.320, xwoba_prior=0.310). Coverage is
        -- the fraction of the 9 lineup slots with >= 10 career PA vs. the
        -- starter. NULL only when the lineup or the opposing starter is
        -- unknown — debut starters return shrinkage-to-prior values.
        h2h.home_lineup_vs_away_starter_h2h_woba,
        h2h.home_lineup_vs_away_starter_h2h_xwoba,
        h2h.home_lineup_h2h_pa_coverage,
        h2h.away_lineup_vs_home_starter_h2h_woba,
        h2h.away_lineup_vs_home_starter_h2h_xwoba,
        h2h.away_lineup_h2h_pa_coverage,

        -- ── Base-state-split performance metrics (Card 8.Y) ──────────────────
        -- Trailing 30-day pre-game wOBA / xwOBA splits by base state at PA
        -- start, plus a pure sequencing rate (runs scored per PA with runners
        -- on). Defensive equivalents for the headline wOBA splits. NULL when
        -- the trailing 30-day window contains fewer than 50 PAs with runners
        -- on; per-column league-average priors imputed in preprocessing.py.
        h_bs.woba_with_runners_on_30d           as home_woba_with_runners_on_30d,
        h_bs.xwoba_with_runners_on_30d          as home_xwoba_with_runners_on_30d,
        h_bs.woba_with_risp_30d                 as home_woba_with_risp_30d,
        h_bs.xwoba_with_risp_30d                as home_xwoba_with_risp_30d,
        h_bs.runs_per_baserunner_30d            as home_runs_per_baserunner_30d,
        h_bs.woba_against_with_runners_on_30d   as home_woba_against_with_runners_on_30d,
        h_bs.woba_against_with_risp_30d         as home_woba_against_with_risp_30d,
        a_bs.woba_with_runners_on_30d           as away_woba_with_runners_on_30d,
        a_bs.xwoba_with_runners_on_30d          as away_xwoba_with_runners_on_30d,
        a_bs.woba_with_risp_30d                 as away_woba_with_risp_30d,
        a_bs.xwoba_with_risp_30d                as away_xwoba_with_risp_30d,
        a_bs.runs_per_baserunner_30d            as away_runs_per_baserunner_30d,
        a_bs.woba_against_with_runners_on_30d   as away_woba_against_with_runners_on_30d,
        a_bs.woba_against_with_risp_30d         as away_woba_against_with_risp_30d,

        -- ── Public betting percentages (Card 8.R) ────────────────────────────
        -- Action Network money% / ticket% on the home moneyline and the Over of
        -- the totals market, plus money−ticket "sharp signal" derivatives.
        -- NULL for games without an Action Network row (off-days, dates the
        -- API never tracked, pre-coverage seasons). Imputed to 50.0 (neutral)
        -- in preprocessing.py.
        pb.home_ml_money_pct,
        pb.home_ml_ticket_pct,
        pb.over_money_pct,
        pb.over_ticket_pct,
        pb.ml_sharp_signal,
        pb.total_sharp_signal,

        -- ── Public betting: era indicator + masked variants (Card 8.W) ───────
        -- has_public_betting_data: 1 when an Action Network row exists for this
        -- game (2024+ coverage); 0 for all pre-coverage games and within-era
        -- gaps. Lets the model distinguish "no data → neutral 50.0 imputation"
        -- from a genuine 50/50 split.
        (pb.home_ml_money_pct is not null)::integer             as has_public_betting_data,

        -- Masked variants: actual value when data exists, 0 when no coverage.
        -- Complement the raw columns: the raw column uses 50.0 neutral
        -- imputation for nulls; the masked column uses 0, so a linear model
        -- can learn separate coefficients for the data-available regime.
        coalesce(pb.home_ml_money_pct,  0)                      as home_ml_money_pct_active,
        coalesce(pb.home_ml_ticket_pct, 0)                      as home_ml_ticket_pct_active,
        coalesce(pb.over_money_pct,     0)                      as over_money_pct_active,
        coalesce(pb.over_ticket_pct,    0)                      as over_ticket_pct_active,
        coalesce(pb.ml_sharp_signal,    0)                      as ml_sharp_signal_active,
        coalesce(pb.total_sharp_signal, 0)                      as total_sharp_signal_active

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
    left join cluster_matchups cm
        on  cm.game_pk = g.game_pk
    left join batter_archetype_matchups bam
        on  bam.game_pk = g.game_pk
    left join h2h_matchups h2h
        on  h2h.game_pk = g.game_pk
    left join line_movement lm
        on  lm.game_pk = g.game_pk
    left join bookmaker_disagreement bd
        on  bd.game_pk = g.game_pk
    left join {{ ref('mart_bullpen_handedness_splits') }} h_bph
        on  h_bph.team_abbrev = g.home_team
        and h_bph.game_pk     = g.game_pk
    left join {{ ref('mart_bullpen_handedness_splits') }} a_bph
        on  a_bph.team_abbrev = g.away_team
        and a_bph.game_pk     = g.game_pk
    left join {{ ref('mart_bullpen_leverage') }} h_blev
        on  h_blev.team_abbrev = g.home_team
        and h_blev.game_pk     = g.game_pk
    left join {{ ref('mart_bullpen_leverage') }} a_blev
        on  a_blev.team_abbrev = g.away_team
        and a_blev.game_pk     = g.game_pk
    left join {{ ref('mart_team_base_state_splits') }} h_bs
        on  h_bs.team_abbrev = g.home_team
        and h_bs.game_pk     = g.game_pk
    left join {{ ref('mart_team_base_state_splits') }} a_bs
        on  a_bs.team_abbrev = g.away_team
        and a_bs.game_pk     = g.game_pk
    left join public_betting pb
        on  pb.game_date    = g.game_date
        and pb.home_team_id = g.home_team
        and pb.away_team_id = g.away_team
)

select * from final

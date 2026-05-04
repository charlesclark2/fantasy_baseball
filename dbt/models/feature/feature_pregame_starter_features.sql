-- =============================================================================
-- feature_pregame_starter_features.sql
-- Grain: one row per game_pk × pitcher_id (confirmed probable starters only)
-- Purpose: Pre-game starter features for ML. Provides rolling pitcher stats,
--          days rest, handedness, and prior-season platoon splits.
--
-- LEAKAGE GUARD: all joins use rs.game_date::date < pp.game_date (strictly
-- less than). Platoon splits use prior season (game_year - 1) to avoid
-- in-season leakage from full-season aggregates.
--
-- has_starter_data = false when the pitcher has no prior Statcast history
-- (e.g. MLB debut). Rows with null probable_pitcher_id are excluded — the
-- master assembly (feature_pregame_game_features) LEFT JOINs this model and
-- detects missing starters via null.
-- =============================================================================

{{ config(materialized='table') }}

with

probable_pitchers as (
    select
        game_pk,
        game_date,
        side,
        probable_pitcher_id     as pitcher_id,
        probable_pitcher_name   as pitcher_name
    from {{ ref('stg_statsapi_probable_pitchers') }}
    where probable_pitcher_id is not null
),

-- Most recent pre-game rolling stats row per pitcher (LEAKAGE GUARD applied)
rolling_ranked as (
    select
        pp.game_pk,
        pp.pitcher_id,
        rs.pitcher_hand,
        rs.game_date                        as stats_game_date,

        -- Sample size flags
        rs.games_30d,
        rs.games_std,

        -- 7-day rolling
        rs.k_pct_7d,
        rs.bb_pct_7d,
        rs.xwoba_against_7d,
        rs.hard_hit_pct_7d,
        rs.barrel_pct_7d,
        rs.whiff_rate_7d,
        rs.batter_chase_rate_7d,
        rs.avg_fastball_velo_7d,

        -- 14-day rolling
        rs.k_pct_14d,
        rs.bb_pct_14d,
        rs.xwoba_against_14d,
        rs.hard_hit_pct_14d,
        rs.barrel_pct_14d,
        rs.whiff_rate_14d,
        rs.batter_chase_rate_14d,
        rs.avg_fastball_velo_14d,

        -- 30-day rolling
        rs.k_pct_30d,
        rs.bb_pct_30d,
        rs.xwoba_against_30d,
        rs.hard_hit_pct_30d,
        rs.barrel_pct_30d,
        rs.whiff_rate_30d,
        rs.batter_chase_rate_30d,
        rs.avg_fastball_velo_30d,

        -- Season-to-date
        rs.k_pct_std,
        rs.bb_pct_std,
        rs.xwoba_against_std,
        rs.hard_hit_pct_std,
        rs.barrel_pct_std,
        rs.whiff_rate_std,
        rs.batter_chase_rate_std,
        rs.avg_fastball_velo_std,

        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by rs.game_date::date desc
        )                                   as rn

    from probable_pitchers pp
    left join {{ ref('mart_pitcher_rolling_stats') }} rs
        on  rs.pitcher_id       = pp.pitcher_id
        and rs.game_date::date  < pp.game_date   -- LEAKAGE GUARD
),

pre_game_rolling as (
    select * from rolling_ranked where rn = 1
),

-- Days since most recent start (from game log, not rolling stats — relievers
-- don't reset the rest clock for starters)
prior_start as (
    select
        pp.game_pk,
        pp.pitcher_id,
        max(gl.game_date::date)             as last_start_date
    from probable_pitchers pp
    left join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id       = pp.pitcher_id
        and gl.game_date::date  < pp.game_date
    group by pp.game_pk, pp.pitcher_id
),

-- Average innings pitched: last 3 starts and season-to-date (LEAKAGE GUARD applied)
-- Uses outs_recorded / 3.0 for proper decimal averaging (not the traditional 7.2 format).
ip_starts as (
    select
        pp.game_pk,
        pp.pitcher_id,
        gl.outs_recorded,
        year(gl.game_date)                      as start_year,
        year(pp.game_date)                      as target_year,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by gl.game_date::date desc
        )                                       as recency_rank
    from probable_pitchers pp
    inner join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id       = pp.pitcher_id
        and gl.game_date::date  < pp.game_date   -- LEAKAGE GUARD
),

ip_stats as (
    select
        game_pk,
        pitcher_id,
        round(
            avg(case when recency_rank <= 3 then outs_recorded::float / 3.0 end),
        2)                                      as avg_ip_last_3,
        round(
            avg(case when start_year = target_year then outs_recorded::float / 3.0 end),
        2)                                      as avg_ip_season
    from ip_starts
    group by game_pk, pitcher_id
),

-- Start-count fastball velocity: last ≤3 prior starts with valid velo data.
-- Mirrors the ip_starts / ip_stats pattern. LEAKAGE GUARD identical: strictly < pp.game_date.
-- avg_fastball_velo from mart_starting_pitcher_game_log is the per-start mean across FF/SI/FC,
-- so a single outlier pitch or mislabeled pitch type cannot skew the result.
velo_starts as (
    select
        pp.game_pk,
        pp.pitcher_id,
        gl.avg_fastball_velo,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by gl.game_date::date desc
        )  as recency_rank
    from probable_pitchers pp
    inner join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id       = pp.pitcher_id
        and gl.game_date::date  < pp.game_date   -- LEAKAGE GUARD
        and gl.avg_fastball_velo is not null
),

velo_stats as (
    select
        game_pk,
        pitcher_id,
        round(
            avg(case when recency_rank <= 3 then avg_fastball_velo end),
        1)  as avg_fastball_velo_3start
    from velo_starts
    group by game_pk, pitcher_id
),

-- FanGraphs Stuff+ arsenal features (Card 7.F)
-- Joined on mlbam_pitcher_id (integer) × season from fct_fangraphs_pitcher_arsenal_wide.
-- All columns are nullable — missing Stuff+ data does not drop the game row.
-- Exposed in feature_pregame_game_features as:
--   home_starter_stuff_plus, away_starter_stuff_plus,
--   home_starter_primary_pitch_type, away_starter_primary_pitch_type,
--   home_starter_fastball_pct, away_starter_fastball_pct,
--   home_starter_breaking_pct, away_starter_breaking_pct,
--   home_starter_offspeed_pct, away_starter_offspeed_pct,
--   home_starter_fastball_stuff_plus, away_starter_fastball_stuff_plus,
--   home_starter_slider_stuff_plus, away_starter_slider_stuff_plus,
--   home_starter_curveball_stuff_plus, away_starter_curveball_stuff_plus,
--   home_starter_changeup_stuff_plus, away_starter_changeup_stuff_plus,
--   home_starter_avg_fastball_velo, away_starter_avg_fastball_velo
arsenal_features as (
    select
        mlbam_pitcher_id,
        season,
        overall_stuff_plus,
        primary_pitch_type,
        fastball_pct,
        breaking_pct,
        offspeed_pct,
        fastball_stuff_plus,
        slider_stuff_plus,
        curveball_stuff_plus,
        changeup_stuff_plus,
        avg_fastball_velo_mph
    from {{ ref('fct_fangraphs_pitcher_arsenal_wide') }}
    where mlbam_pitcher_id is not null
),

-- ZiPS pre-season FIP projections (Card 8.B)
-- proj_xfip is NULL in current ingestion (FanGraphs ZiPS export does not include xFIP).
-- fip_era_gap omitted: earned runs are not available in the pipeline.
zips_fip as (
    select
        mlbam_pitcher_id::integer   as pitcher_id,
        season,
        proj_fip,
        proj_xfip
    from {{ ref('fct_fangraphs_pitching_analytics') }}
    where mlbam_pitcher_id is not null
),

-- Trailing FIP over last 30 starts (Card 8.B)
-- FIP = (13×HR + 3×(BB+HBP) - 2×K) / IP + 3.10
-- NULL when IP sum < 10 (debut or very short career).
fip_starts as (
    select
        pp.game_pk,
        pp.pitcher_id,
        gl.home_runs_allowed,
        gl.walks,
        gl.hit_by_pitch,
        gl.strikeouts,
        gl.innings_pitched,
        gl.runs_allowed,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by gl.game_date::date desc
        ) as recency_rank
    from probable_pitchers pp
    inner join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id      = pp.pitcher_id
        and gl.game_date::date < pp.game_date   -- LEAKAGE GUARD
),

fip_stats as (
    select
        game_pk,
        pitcher_id,
        case
            when sum(case when recency_rank <= 30 then innings_pitched end) >= 10
            then round(
                (  13.0 * sum(case when recency_rank <= 30 then home_runs_allowed end)
                 + 3.0  * (  sum(case when recency_rank <= 30 then walks end)
                           + sum(case when recency_rank <= 30 then hit_by_pitch end))
                 - 2.0  * sum(case when recency_rank <= 30 then strikeouts end))
                / nullif(sum(case when recency_rank <= 30 then innings_pitched end), 0)
                + 3.10,
                2)
            else null
        end as trailing_fip_30g,
        -- RA/9: runs allowed per 9 innings (proxy for ERA; no earned/unearned distinction)
        case
            when sum(case when recency_rank <= 30 then innings_pitched end) >= 10
            then round(
                sum(case when recency_rank <= 30 then runs_allowed end) * 9.0
                / nullif(sum(case when recency_rank <= 30 then innings_pitched end), 0),
                2)
            else null
        end as trailing_ra9_30g
    from fip_starts
    group by game_pk, pitcher_id
),

-- Prior-season platoon splits vs LHB (game_year - 1 to prevent in-season leakage)
platoon_lhb as (
    select
        pp.game_pk,
        pp.pitcher_id,
        hs.k_pct                            as k_pct_vs_lhb,
        hs.bb_pct                           as bb_pct_vs_lhb,
        hs.xwoba_against                    as xwoba_vs_lhb,
        hs.whiff_rate                       as whiff_rate_vs_lhb
    from probable_pitchers pp
    left join {{ ref('mart_pitcher_vs_handedness_splits') }} hs
        on  hs.pitcher_id   = pp.pitcher_id
        and hs.batter_hand  = 'L'
        and hs.game_year    = year(pp.game_date) - 1
),

-- Prior-season platoon splits vs RHB
platoon_rhb as (
    select
        pp.game_pk,
        pp.pitcher_id,
        hs.k_pct                            as k_pct_vs_rhb,
        hs.bb_pct                           as bb_pct_vs_rhb,
        hs.xwoba_against                    as xwoba_vs_rhb,
        hs.whiff_rate                       as whiff_rate_vs_rhb
    from probable_pitchers pp
    left join {{ ref('mart_pitcher_vs_handedness_splits') }} hs
        on  hs.pitcher_id   = pp.pitcher_id
        and hs.batter_hand  = 'R'
        and hs.game_year    = year(pp.game_date) - 1
),

final as (
    select
        pp.game_pk,
        pp.game_date,
        year(pp.game_date)                  as game_year,
        pp.side,
        pp.pitcher_id,
        pp.pitcher_name,
        pgr.pitcher_hand,

        -- False for debut pitchers with no prior Statcast history
        (pgr.stats_game_date is not null)::boolean  as has_starter_data,

        -- Days since last start (null if no prior starts in the dataset)
        datediff('day', ps.last_start_date, pp.game_date)   as days_rest,

        -- ── 7-day rolling ────────────────────────────────────────────────────
        pgr.k_pct_7d,
        pgr.bb_pct_7d,
        pgr.xwoba_against_7d,
        pgr.hard_hit_pct_7d,
        pgr.barrel_pct_7d,
        pgr.whiff_rate_7d,
        pgr.batter_chase_rate_7d,
        pgr.avg_fastball_velo_7d,

        -- ── 14-day rolling ───────────────────────────────────────────────────
        pgr.k_pct_14d,
        pgr.bb_pct_14d,
        pgr.xwoba_against_14d,
        pgr.hard_hit_pct_14d,
        pgr.barrel_pct_14d,
        pgr.whiff_rate_14d,
        pgr.batter_chase_rate_14d,
        pgr.avg_fastball_velo_14d,

        -- ── 30-day rolling ───────────────────────────────────────────────────
        pgr.k_pct_30d,
        pgr.bb_pct_30d,
        pgr.xwoba_against_30d,
        pgr.hard_hit_pct_30d,
        pgr.barrel_pct_30d,
        pgr.whiff_rate_30d,
        pgr.batter_chase_rate_30d,
        pgr.avg_fastball_velo_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────
        pgr.k_pct_std,
        pgr.bb_pct_std,
        pgr.xwoba_against_std,
        pgr.hard_hit_pct_std,
        pgr.barrel_pct_std,
        pgr.whiff_rate_std,
        pgr.batter_chase_rate_std,
        pgr.avg_fastball_velo_std,

        -- ── Fastball velocity trend (positive = velocity trending up) ────────
        round(pgr.avg_fastball_velo_7d - pgr.avg_fastball_velo_30d, 1) as fastball_velo_trend,

        -- ── Start-count velocity delta (Card 7.S): last 3 starts avg minus season avg ──
        -- Independent of calendar gaps; captures IL returns, skipped starts, 6-man rotations.
        -- NULL when pitcher has no prior starts with valid fastball velo data.
        vs.avg_fastball_velo_3start,
        round(
            vs.avg_fastball_velo_3start - pgr.avg_fastball_velo_std,
            1
        )  as velo_delta_3start,

        -- ── Momentum deltas: 7-day minus season-to-date (positive = trending up)
        pgr.k_pct_7d - pgr.k_pct_std                as k_pct_7d_minus_std,
        pgr.xwoba_against_7d - pgr.xwoba_against_std as xwoba_7d_minus_std,

        -- ── Sample size flags: appearances in each rolling window ─────────────
        pgr.games_30d                                as appearances_30d,
        pgr.games_std                                as appearances_std,

        -- ── Prior-season platoon splits vs LHB ───────────────────────────────
        pl.k_pct_vs_lhb,
        pl.bb_pct_vs_lhb,
        pl.xwoba_vs_lhb,
        pl.whiff_rate_vs_lhb,

        -- ── Prior-season platoon splits vs RHB ───────────────────────────────
        pr.k_pct_vs_rhb,
        pr.bb_pct_vs_rhb,
        pr.xwoba_vs_rhb,
        pr.whiff_rate_vs_rhb,

        -- ── Recent IP trend and history flag ─────────────────────────────────
        -- avg_ip_last_3: average decimal innings over the 3 most recent starts
        -- avg_ip_season: season-to-date average decimal innings per start
        -- has_ip_history: false for debut starters with no prior starts in the dataset
        ips.avg_ip_last_3,
        ips.avg_ip_season,
        (ips.game_pk is not null)::boolean       as has_ip_history,

        -- ── FanGraphs Stuff+ arsenal features (Card 7.F) ─────────────────────
        af.overall_stuff_plus                    as starter_stuff_plus,
        af.primary_pitch_type                    as starter_primary_pitch_type,
        af.fastball_pct                          as starter_fastball_pct,
        af.breaking_pct                          as starter_breaking_pct,
        af.offspeed_pct                          as starter_offspeed_pct,
        af.fastball_stuff_plus                   as starter_fastball_stuff_plus,
        af.slider_stuff_plus                     as starter_slider_stuff_plus,
        af.curveball_stuff_plus                  as starter_curveball_stuff_plus,
        af.changeup_stuff_plus                   as starter_changeup_stuff_plus,
        af.avg_fastball_velo_mph                 as starter_avg_fastball_velo,

        -- ── ZiPS projected FIP and trailing FIP/RA9 (Card 8.B) ───────────────
        -- proj_xfip is NULL in current ingestion (FanGraphs ZiPS export omits xFIP).
        -- trailing_fip_30g / trailing_ra9_30g: last 30 starts. NULL if IP < 10.
        zf.proj_fip                              as starter_proj_fip,
        zf.proj_xfip                             as starter_proj_xfip,
        fs.trailing_fip_30g                      as starter_trailing_fip_30g,
        fs.trailing_ra9_30g                      as starter_trailing_ra9_30g,
        round(fs.trailing_fip_30g - fs.trailing_ra9_30g, 2)
                                                 as starter_fip_ra9_gap

    from probable_pitchers pp
    left join pre_game_rolling pgr
        on  pgr.game_pk     = pp.game_pk
        and pgr.pitcher_id  = pp.pitcher_id
    left join prior_start ps
        on  ps.game_pk      = pp.game_pk
        and ps.pitcher_id   = pp.pitcher_id
    left join platoon_lhb pl
        on  pl.game_pk      = pp.game_pk
        and pl.pitcher_id   = pp.pitcher_id
    left join platoon_rhb pr
        on  pr.game_pk      = pp.game_pk
        and pr.pitcher_id   = pp.pitcher_id
    left join ip_stats ips
        on  ips.game_pk     = pp.game_pk
        and ips.pitcher_id  = pp.pitcher_id
    left join velo_stats vs
        on  vs.game_pk      = pp.game_pk
        and vs.pitcher_id   = pp.pitcher_id
    left join arsenal_features af
        on  af.mlbam_pitcher_id = pp.pitcher_id
        and af.season           = year(pp.game_date)
    left join zips_fip zf
        on  zf.pitcher_id   = pp.pitcher_id
        and zf.season       = year(pp.game_date)
    left join fip_stats fs
        on  fs.game_pk      = pp.game_pk
        and fs.pitcher_id   = pp.pitcher_id
)

select * from final

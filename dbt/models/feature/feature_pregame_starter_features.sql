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
--
-- E11.1-W8b (serving-aggregator wave): dual-branch. DuckDB branch (real compute → S3,
-- run_w1_lakehouse._build_w8b) reads the migrated marts/staging (mart_pitcher_rolling_stats,
-- mart_starting_pitcher_game_log, mart_pitcher_vs_handedness_splits, mart_starter_*,
-- fct_fangraphs_pitcher_arsenal_wide, the S3-mirrored fct_fangraphs_pitching_analytics,
-- stg_statsapi_probable_pitchers, eb_starter_posteriors) + lakehouse_clusters; body is
-- dialect-clean (Snowflake float casts → DuckDB ::double; datediff is DuckDB-native). The
-- Snowflake (else) branch reads the lakehouse_ext external table (parity_check_w8b.py).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8b_lakehouse']) }}

with

-- Story 30.6 (fix A, 2026-06-14): source the CURRENT probable from the FRESH
-- stg_statsapi_probable_pitchers staging, NOT the SCD-2 feature_pregame_starter_status.
-- The SCD-2 chain (stg_statsapi_starter_snapshots -> ...starter_status) lags the latest
-- monthly_schedule ingestion (~80% null for +1/+2-day games vs 0% in stg_probable_pitchers),
-- which left the entire starter-EB block NULL at serve time and collapsed live home_win to a
-- coinflip (corr 0.016 served vs 0.61 offline-dense, same model). This model only used the
-- SCD-2's is_current state (never its temporal replay), so repointing to the fresh staging
-- restores serve-time density without changing historical training rows (for played games the
-- latest probable == the SCD-2 final state). Take the LATEST ingestion per (game_pk, side) so
-- scratches resolve to the most recent probable; filter null AFTER the latest pick so a
-- scratched-to-null latest is excluded (master assembly then detects the missing starter).
-- The durable build-ordering/freshness fix for the SCD-2 chain is tracked in Story 30.13.
probable_pitchers as (
    select
        game_pk,
        game_date,
        side,
        probable_pitcher_id     as pitcher_id,
        probable_pitcher_name   as pitcher_name
    from (
        select
            game_pk, game_date, side, probable_pitcher_id, probable_pitcher_name,
            row_number() over (
                partition by game_pk, side
                order by ingestion_ts desc nulls last
            ) as rn
        from {{ ref('stg_statsapi_probable_pitchers') }}
    )
    where rn = 1
      and probable_pitcher_id is not null
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
-- Also computes cumulative season IP and pitch count (total through all prior starts this season).
ip_starts as (
    select
        pp.game_pk,
        pp.pitcher_id,
        gl.outs_recorded,
        gl.total_pitches,
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
            avg(case when recency_rank <= 3 then outs_recorded::double / 3.0 end),
        2)                                      as avg_ip_last_3,
        round(
            avg(case when start_year = target_year then outs_recorded::double / 3.0 end),
        2)                                      as avg_ip_season,
        round(
            sum(case when start_year = target_year then outs_recorded::double / 3.0 end),
        2)                                      as cumulative_season_ip,
        sum(case when start_year = target_year then total_pitches end)
                                                as cumulative_season_pitches
    from ip_starts
    group by game_pk, pitcher_id
),

-- ── E1.11 START-INDEXED starter form (last ≤3 prior STARTS; IL/offseason-aware) ──
-- The CORRECTNESS fix for the E1.11 audit's flagship miscalc: a starter works a
-- rotation, so the calendar 7/14/30-day rolling windows (pgr.*, sourced from
-- mart_pitcher_rolling_stats with rn=1 and NO max-staleness bound) silently carry a
-- prior season's / pre-IL numbers forward across a long gap. Measured rate: 100% of the
-- 9.43% of starter-rows with days_rest>15 still show a *populated* "7-day" window — a
-- definitionally-impossible stale carry-forward. Lead case: Julio Teheran, game_pk 634573
-- (2021-04-03 DET season debut) wore his final-2020 LAA form (k_pct_7d=0.188) 189 days
-- stale. Start-indexed aggregates are gap-immune ("the last 3 real starts", whenever they
-- were) and are paired in `final` with an explicit source-age + long-layoff flag so a
-- model can down-weight or gate old form instead of trusting a phantom calendar window.
-- LEAKAGE GUARD: strict gl.game_date < pp.game_date. BF-weighted so a 1-batter opener
-- cameo cannot distort the rate. Validated vs ground truth (Teheran): sp_k_pct_l3=0.115,
-- sp_bb_pct_l3=0.192, sp_xwoba_against_l3=0.6846, sp_form_start_count=3.
sp_form as (
    select
        pp.game_pk,
        pp.pitcher_id,
        gl.game_date::date                      as start_date,
        gl.strikeouts,
        gl.walks,
        gl.batters_faced,
        gl.xwoba_against,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by gl.game_date::date desc
        ) as recency_rank
    from probable_pitchers pp
    inner join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id       = pp.pitcher_id
        and gl.game_date::date  < pp.game_date   -- LEAKAGE GUARD
),

sp_form_stats as (
    select
        game_pk,
        pitcher_id,
        round(sum(case when recency_rank <= 3 then strikeouts end)
              / nullif(sum(case when recency_rank <= 3 then batters_faced end), 0), 4) as sp_k_pct_l3,
        round(sum(case when recency_rank <= 3 then walks end)
              / nullif(sum(case when recency_rank <= 3 then batters_faced end), 0), 4) as sp_bb_pct_l3,
        round(sum(case when recency_rank <= 3 then xwoba_against * batters_faced end)
              / nullif(sum(case when recency_rank <= 3 then batters_faced end), 0), 4) as sp_xwoba_against_l3,
        sum(case when recency_rank <= 3 then batters_faced end)                        as sp_form_bf_l3,
        sum(case when recency_rank <= 3 then 1 else 0 end)                             as sp_form_start_count
    from sp_form
    group by game_pk, pitcher_id
),

-- ── E1.11 Phase 2 — RECENTLY-ACQUIRED / traded-pitcher context ────────────────
-- A mid-season-acquired starter's calendar (*_7d/_30d) AND start-indexed (sp_*_l3) form
-- BLEND his old-team and new-team starts — the rolling marts partition by pitcher_id
-- ONLY, never team — and the market + our own features are slow to re-rate a pitcher in
-- a new context (the information-timing signal). acquired_date = the most recent
-- team-change transaction (Trade/Acquired/Claimed-off-Waivers/Obtained/Purchase; the
-- Stats-API team_id is the ACQUIRING team, verified against post-trade game logs) on or
-- before this game. LEAKAGE-safe (transaction_date <= pp.game_date). Bounded to 400 days
-- so an ancient rookie call-up cannot register as the "current" acquisition; max() then
-- takes the most recent. Offseason moves clear the 30-day window by opening day and are
-- correctly NOT flagged (a full spring to adjust ⇒ not a live context switch).
pitcher_acquisition as (
    select
        pp.game_pk,
        pp.pitcher_id,
        max(t.transaction_date::date) as acquired_date
    from probable_pitchers pp
    inner join {{ ref('stg_statsapi_transactions') }} t
        on  t.player_id = pp.pitcher_id
        and t.type_code in ('TR','ACQ','CLW','OBT','PUR','CP')
        and t.transaction_date::date <= pp.game_date
        and datediff('day', t.transaction_date::date, pp.game_date) <= 400
    group by pp.game_pk, pp.pitcher_id
),

-- NEW-CONTEXT (same-team) start-indexed form: sp_*_l3 restricted to starts made ON or
-- AFTER acquired_date (the new team only), re-ranked within the post-acquisition subset.
-- NULL when a just-acquired starter has no post-acquisition starts yet — honestly
-- signalling "no new-team form" rather than silently reusing the blended pre-trade numbers.
sp_form_same_team as (
    select
        sf.game_pk,
        sf.pitcher_id,
        sf.strikeouts,
        sf.walks,
        sf.batters_faced,
        sf.xwoba_against,
        row_number() over (
            partition by sf.game_pk, sf.pitcher_id
            order by sf.start_date desc
        ) as recency_rank_st
    from sp_form sf
    inner join pitcher_acquisition acq
        on  acq.game_pk    = sf.game_pk
        and acq.pitcher_id = sf.pitcher_id
    where sf.start_date >= acq.acquired_date
),

sp_form_same_team_stats as (
    select
        game_pk,
        pitcher_id,
        round(sum(case when recency_rank_st <= 3 then strikeouts end)
              / nullif(sum(case when recency_rank_st <= 3 then batters_faced end), 0), 4) as sp_k_pct_l3_same_team,
        round(sum(case when recency_rank_st <= 3 then walks end)
              / nullif(sum(case when recency_rank_st <= 3 then batters_faced end), 0), 4) as sp_bb_pct_l3_same_team,
        round(sum(case when recency_rank_st <= 3 then xwoba_against * batters_faced end)
              / nullif(sum(case when recency_rank_st <= 3 then batters_faced end), 0), 4) as sp_xwoba_against_l3_same_team,
        sum(case when recency_rank_st <= 3 then 1 else 0 end)                             as sp_form_start_count_same_team
    from sp_form_same_team
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

-- ── E13.7 cold-start league baselines (rookie / call-up fallback prior) ──────────────
-- Pitchers with no prior-season profile (true rookies / call-ups, ~87% of NULL-archetype
-- pitchers per the E13.7 scoping note) leave the prior-season Stuff+/platoon/archetype joins
-- blank — ~15-27% of starters, RISING into the late-season recent window the E13.4 lift-tests
-- judge edge on. Instead of a blank (preprocessing → train-mean / "__NA__"), fill with a
-- LEAK-CLEAN league/role baseline = the EB prior at n=0 (full shrinkage to the population mean,
-- since a true rookie has no MLB sample). PRODUCT/COVERAGE fix, NOT an edge play — the
-- pitcher-specific prior is the MiLB-equivalent (Epic 7). See E13_7_cold_start_scoping.md.
--
-- Leak-clean: per-season league means are joined on year-1 in `final` (strictly prior season,
-- mirroring the existing arsenal / platoon prior-season convention). `*_all_baseline` is an
-- all-seasons fallback for the earliest data year only (year-1 absent); it pools full-history
-- league means, which for a strictly-prior fill is leakage-immaterial (a stationary population
-- constant, not a pitcher-specific or current-season value).
arsenal_yr_baseline as (
    select
        season,
        avg(overall_stuff_plus)    as base_stuff_plus,
        avg(fastball_pct)          as base_fastball_pct,
        avg(breaking_pct)          as base_breaking_pct,
        avg(offspeed_pct)          as base_offspeed_pct,
        avg(fastball_stuff_plus)   as base_fastball_stuff_plus,
        avg(slider_stuff_plus)     as base_slider_stuff_plus,
        avg(curveball_stuff_plus)  as base_curveball_stuff_plus,
        avg(changeup_stuff_plus)   as base_changeup_stuff_plus,
        avg(avg_fastball_velo_mph) as base_avg_fastball_velo
    from arsenal_features
    group by season
),

arsenal_all_baseline as (
    select
        avg(overall_stuff_plus)    as base_stuff_plus,
        avg(fastball_pct)          as base_fastball_pct,
        avg(breaking_pct)          as base_breaking_pct,
        avg(offspeed_pct)          as base_offspeed_pct,
        avg(fastball_stuff_plus)   as base_fastball_stuff_plus,
        avg(slider_stuff_plus)     as base_slider_stuff_plus,
        avg(curveball_stuff_plus)  as base_curveball_stuff_plus,
        avg(changeup_stuff_plus)   as base_changeup_stuff_plus,
        avg(avg_fastball_velo_mph) as base_avg_fastball_velo
    from arsenal_features
),

platoon_yr_baseline as (
    select
        game_year   as season,
        batter_hand,
        avg(k_pct)          as base_k_pct,
        avg(bb_pct)         as base_bb_pct,
        avg(xwoba_against)  as base_xwoba,
        avg(whiff_rate)     as base_whiff
    from {{ ref('mart_pitcher_vs_handedness_splits') }}
    group by game_year, batter_hand
),

platoon_all_baseline as (
    select
        batter_hand,
        avg(k_pct)          as base_k_pct,
        avg(bb_pct)         as base_bb_pct,
        avg(xwoba_against)  as base_xwoba,
        avg(whiff_rate)     as base_whiff
    from {{ ref('mart_pitcher_vs_handedness_splits') }}
    group by batter_hand
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

-- CSW% rolling stats (Card 8.Q)
-- Trailing 3-start and season-to-date called-strike-plus-whiff rate.
-- LEAKAGE GUARD: strict < on game_date; rn=1 selects the most recent start
-- completed before the prediction game.
csw_ranked as (
    select
        pp.game_pk,
        pp.pitcher_id,
        cs.csw_pct_3start,
        cs.csw_pct_season,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by cs.game_date::date desc
        ) as rn
    from probable_pitchers pp
    left join {{ ref('mart_starter_csw_rolling') }} cs
        on  cs.pitcher_id      = pp.pitcher_id
        and cs.game_date::date < pp.game_date   -- LEAKAGE GUARD
),

csw_pre_game as (
    select * from csw_ranked where rn = 1
),

-- Pitch mix rolling stats (Card 8.M)
-- Trailing 5-start vs. season-to-date pitch group percentages used to compute
-- arsenal drift columns. LEAKAGE GUARD: strict < on game_date; rn=1 selects
-- the most recent completed start before the prediction game.
pitch_mix_ranked as (
    select
        pp.game_pk,
        pp.pitcher_id,
        pmr.fastball_pct_5start,
        pmr.breaking_pct_5start,
        pmr.offspeed_pct_5start,
        pmr.fastball_pct_season,
        pmr.breaking_pct_season,
        pmr.offspeed_pct_season,
        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by pmr.game_date::date desc
        ) as rn
    from probable_pitchers pp
    left join {{ ref('mart_starter_pitch_mix_rolling') }} pmr
        on  pmr.pitcher_id      = pp.pitcher_id
        and pmr.game_date::date < pp.game_date   -- LEAKAGE GUARD
),

pitch_mix_pre_game as (
    select * from pitch_mix_ranked where rn = 1
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

-- Prior-season pitcher archetype label (Story 7.4).
-- Prefers season - 1; falls back to season - 2 when season - 1 is unavailable
-- (handles pitchers who missed a season due to injury, COVID-2020 data thinness, etc.).
-- Both lookbacks are leakage-safe (strictly prior seasons). NULL only when the pitcher
-- has no MLB cluster assignment in either of the prior two seasons (true rookies).
pitcher_archetype as (
    select
        pp.game_pk,
        pp.pitcher_id,
        coalesce(pc1.cluster_label, pc2.cluster_label) as starter_pitcher_archetype
    from probable_pitchers pp
    left join {{ source('lakehouse_clusters', 'pitcher_clusters') }} pc1
        on  pc1.pitcher_id = pp.pitcher_id
        and pc1.season     = year(pp.game_date) - 1
    left join {{ source('lakehouse_clusters', 'pitcher_clusters') }} pc2
        on  pc2.pitcher_id = pp.pitcher_id
        and pc2.season     = year(pp.game_date) - 2
),

-- EB posteriors: pre-game xwOBA-against, K%, BB%, and uncertainty (Story 5A.3).
-- Leakage guard is baked into eb_starter_posteriors at write time (the script
-- uses game_date < target_date before aggregating current-season stats).
-- Casting VARCHAR keys to integer to match probable_pitchers grain types.
eb_posteriors as (
    select
        game_pk::integer        as game_pk,
        pitcher_id::integer     as pitcher_id,
        eb_xwoba_against,
        eb_xwoba_against_sequential,
        eb_k_pct,
        eb_bb_pct,
        eb_xwoba_uncertainty,
        eb_data_source,
        posterior_source
    -- Story A2.11: eb_starter_posteriors is now a dbt model (was a Python table);
    -- ref() so dbt builds the posterior before this feature.
    from {{ ref('eb_starter_posteriors') }}
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

-- ── E13.4 Candidate B1: times-through-order penalty (prior season; leak-clean) ──
-- The starter's prior-season 3rd-time-through xwOBA-against fade. Joined on
-- game_year - 1 (same doctrine as platoon/arsenal). NULL for rookies/first-MLB-season
-- starters → the downstream shrink collapses to the league baseline below.
tto_splits as (
    select
        pp.game_pk,
        pp.pitcher_id,
        ts.tto3_xwoba_penalty,
        ts.tto_min_bf
    from probable_pitchers pp
    left join {{ ref('mart_starter_tto_splits') }} ts
        on  ts.pitcher_id = pp.pitcher_id
        and ts.season     = year(pp.game_date) - 1
),

-- BF-weighted prior-season league-mean TTO penalty — the empirical-Bayes shrink prior
-- (and the cold-start fill). Weighted by the binding bucket's batters-faced so noisy
-- small-sample pitcher-seasons don't distort the league anchor.
tto_yr_baseline as (
    select
        season,
        sum(tto3_xwoba_penalty * tto_min_bf) / nullif(sum(tto_min_bf), 0) as league_tto_penalty
    from {{ ref('mart_starter_tto_splits') }}
    where tto3_xwoba_penalty is not null
    group by season
),

-- All-seasons pooled fallback for the earliest data year (no prior season to anchor on).
tto_all_baseline as (
    select
        sum(tto3_xwoba_penalty * tto_min_bf) / nullif(sum(tto_min_bf), 0) as league_tto_penalty_all
    from {{ ref('mart_starter_tto_splits') }}
    where tto3_xwoba_penalty is not null
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

        -- ── E1.11 START-INDEXED form (last ≤3 prior starts; gap-immune) ──────
        -- Trustworthy replacement for the stale-prone calendar *_7d/_14d/_30d block:
        -- BF-weighted rates over the pitcher's last ≤3 actual starts, whenever they
        -- occurred. NULL only for a true debut (no prior starts). See sp_form above.
        sfs.sp_k_pct_l3,
        sfs.sp_bb_pct_l3,
        sfs.sp_xwoba_against_l3,
        coalesce(sfs.sp_form_start_count, 0)        as sp_form_start_count,

        -- ── E1.11 form-staleness diagnostics ────────────────────────────────
        -- starter_form_source_age_days: calendar days between the CALENDAR-rolling source
        -- row (pgr.stats_game_date) and this game. When it exceeds a window length, that
        -- window's *_Nd value is a stale carry-forward, NOT current form. NULL for debuts.
        datediff('day', pgr.stats_game_date::date, pp.game_date)             as starter_form_source_age_days,
        -- starter_form_stale: the calendar 7/14/30-day rolling source is older than its
        -- widest (30-day) window ⇒ the *_7d/_14d/_30d columns are NOT "recent form" for
        -- this start; prefer sp_*_l3. (Teheran 634573: age 189 ⇒ true.)
        (datediff('day', pgr.stats_game_date::date, pp.game_date) > 30)::boolean as starter_form_stale,
        -- starter_long_layoff: >30 days since the pitcher's last START (offseason debut /
        -- IL return). Makes a large, correct days_rest (e.g. 189) legible to the model.
        (datediff('day', ps.last_start_date, pp.game_date) > 30)::boolean    as starter_long_layoff,

        -- ── E1.11 Phase 2 — recently-acquired / traded-pitcher context ────────
        -- starter_days_on_team: days since the pitcher's most recent team-change txn
        -- (NULL = no acquisition in the last 400d ⇒ settled / homegrown / long tenure).
        -- starter_is_recently_acquired: acquired ≤30d ago (the in-season context-switch
        -- window). starter_starts_since_acquired: post-acquisition starts backing the
        -- new-context form. sp_*_l3_same_team: the gap-immune l3 form over NEW-TEAM starts
        -- only (NULL for a just-acquired starter with no new-team start yet — honest, not
        -- the blend). starter_form_spans_team_change: the last-3 form mixes old + new team.
        datediff('day', acq.acquired_date, pp.game_date)                     as starter_days_on_team,
        coalesce(datediff('day', acq.acquired_date, pp.game_date) <= 30, false)::boolean as starter_is_recently_acquired,
        coalesce(sfst.sp_form_start_count_same_team, 0)                      as starter_starts_since_acquired,
        sfst.sp_k_pct_l3_same_team,
        sfst.sp_bb_pct_l3_same_team,
        sfst.sp_xwoba_against_l3_same_team,
        coalesce(
            datediff('day', acq.acquired_date, pp.game_date) <= 30
            and coalesce(sfst.sp_form_start_count_same_team, 0) < coalesce(sfs.sp_form_start_count, 0),
            false
        )::boolean                                                           as starter_form_spans_team_change,

        -- ── Sample size flags: appearances in each rolling window ─────────────
        pgr.games_30d                                as appearances_30d,
        pgr.games_std                                as appearances_std,

        -- ── Prior-season platoon splits vs LHB (E13.7: cold-start → league baseline) ──
        coalesce(pl.k_pct_vs_lhb,      plbl.base_k_pct,  plal.base_k_pct)  as k_pct_vs_lhb,
        coalesce(pl.bb_pct_vs_lhb,     plbl.base_bb_pct, plal.base_bb_pct) as bb_pct_vs_lhb,
        coalesce(pl.xwoba_vs_lhb,      plbl.base_xwoba,  plal.base_xwoba)  as xwoba_vs_lhb,
        coalesce(pl.whiff_rate_vs_lhb, plbl.base_whiff,  plal.base_whiff)  as whiff_rate_vs_lhb,

        -- ── Prior-season platoon splits vs RHB (E13.7: cold-start → league baseline) ──
        coalesce(pr.k_pct_vs_rhb,      plbr.base_k_pct,  plar.base_k_pct)  as k_pct_vs_rhb,
        coalesce(pr.bb_pct_vs_rhb,     plbr.base_bb_pct, plar.base_bb_pct) as bb_pct_vs_rhb,
        coalesce(pr.xwoba_vs_rhb,      plbr.base_xwoba,  plar.base_xwoba)  as xwoba_vs_rhb,
        coalesce(pr.whiff_rate_vs_rhb, plbr.base_whiff,  plar.base_whiff)  as whiff_rate_vs_rhb,

        -- ── Recent IP trend, cumulative workload, and history flag ──────────
        -- avg_ip_last_3: average decimal innings over the 3 most recent starts
        -- avg_ip_season: season-to-date average decimal innings per start
        -- cumulative_season_ip: total innings pitched this season before this start
        -- cumulative_season_pitches: total pitches thrown this season before this start
        -- has_ip_history: false for debut starters with no prior starts in the dataset
        ips.avg_ip_last_3,
        ips.avg_ip_season,
        coalesce(ips.cumulative_season_ip, 0.0)  as cumulative_season_ip,
        coalesce(ips.cumulative_season_pitches, 0) as cumulative_season_pitches,
        (ips.game_pk is not null)::boolean       as has_ip_history,

        -- ── FanGraphs Stuff+ arsenal features (Card 7.F) ─────────────────────
        -- E13.7: cold-start (rookie / call-up) NULLs → leak-clean prior-season league
        -- baseline (year-1 first, all-seasons fallback for the earliest data year).
        coalesce(af.overall_stuff_plus,   ayb.base_stuff_plus,           aab.base_stuff_plus)           as starter_stuff_plus,
        coalesce(af.primary_pitch_type, 'league_baseline')               as starter_primary_pitch_type,
        coalesce(af.fastball_pct,         ayb.base_fastball_pct,         aab.base_fastball_pct)         as starter_fastball_pct,
        coalesce(af.breaking_pct,         ayb.base_breaking_pct,         aab.base_breaking_pct)         as starter_breaking_pct,
        coalesce(af.offspeed_pct,         ayb.base_offspeed_pct,         aab.base_offspeed_pct)         as starter_offspeed_pct,
        coalesce(af.fastball_stuff_plus,  ayb.base_fastball_stuff_plus,  aab.base_fastball_stuff_plus)  as starter_fastball_stuff_plus,
        coalesce(af.slider_stuff_plus,    ayb.base_slider_stuff_plus,    aab.base_slider_stuff_plus)    as starter_slider_stuff_plus,
        coalesce(af.curveball_stuff_plus, ayb.base_curveball_stuff_plus, aab.base_curveball_stuff_plus) as starter_curveball_stuff_plus,
        coalesce(af.changeup_stuff_plus,  ayb.base_changeup_stuff_plus,  aab.base_changeup_stuff_plus)  as starter_changeup_stuff_plus,
        coalesce(af.avg_fastball_velo_mph, ayb.base_avg_fastball_velo,   aab.base_avg_fastball_velo)    as starter_avg_fastball_velo,

        -- ── ZiPS projected FIP and trailing FIP/RA9 (Card 8.B) ───────────────
        -- proj_xfip is NULL in current ingestion (FanGraphs ZiPS export omits xFIP).
        -- trailing_fip_30g / trailing_ra9_30g: last 30 starts. NULL if IP < 10.
        zf.proj_fip                              as starter_proj_fip,
        zf.proj_xfip                             as starter_proj_xfip,
        fs.trailing_fip_30g                      as starter_trailing_fip_30g,
        fs.trailing_ra9_30g                      as starter_trailing_ra9_30g,
        round(fs.trailing_fip_30g - fs.trailing_ra9_30g, 2)
                                                 as starter_fip_ra9_gap,

        -- ── CSW% rolling stats (Card 8.Q) ────────────────────────────────────
        -- NULL for debut starters or when no prior starts exist before this game.
        -- Imputed to league-average (~0.285) in preprocessing.py.
        cswg.csw_pct_3start,
        cswg.csw_pct_season,

        -- ── Arsenal drift (Card 8.M) ─────────────────────────────────────────
        -- drift = trailing_5start_pct − season_to_date_pct. Positive = more
        -- recent usage than season average; negative = less. Imputed to 0.0
        -- (no drift = league-average behavior) for starters with < 5 career
        -- starts, where the source mart returns NULL pcts.
        coalesce(
            round(pmpg.fastball_pct_5start - pmpg.fastball_pct_season, 4),
            0.0
        )                                       as fastball_pct_drift_5start,
        coalesce(
            round(pmpg.breaking_pct_5start - pmpg.breaking_pct_season, 4),
            0.0
        )                                       as breaking_pct_drift_5start,
        coalesce(
            round(pmpg.offspeed_pct_5start - pmpg.offspeed_pct_season, 4),
            0.0
        )                                       as offspeed_pct_drift_5start,

        -- ── EB posteriors (Story 5A.3) ────────────────────────────────────────
        -- Shrinkage toward experience-band prior; null when game has no entry
        -- (pre-2016 or pitcher not listed as a probable starter at run time).
        eb.eb_xwoba_against,
        -- Epic 16.2 — as-of sequential xwOBA-against posterior (parallel to
        -- eb_xwoba_against; leakage-safe, strict game_date<T at write time).
        eb.eb_xwoba_against_sequential,
        eb.eb_k_pct,
        eb.eb_bb_pct,
        eb.eb_xwoba_uncertainty,
        eb.eb_data_source,
        -- Epic 16B.3 — per-pitcher posterior source label; NULL pre-2021.
        eb.posterior_source,

        -- ── Prior-season pitcher archetype label (Story 7.4) ─────────────────
        -- E13.7: NULL (rookies / not in prior-season cluster table) → explicit
        -- 'league_baseline' category — an honest "generic starter, profile unknown"
        -- bucket (NOT the modal cluster, which would mislabel the pitcher). Paired
        -- with is_cold_start so a retrained model can learn a rookie-specific offset.
        coalesce(pa.starter_pitcher_archetype, 'league_baseline') as starter_pitcher_archetype,

        -- ── E13.7 cold-start flag ─────────────────────────────────────────────
        -- True when the starter had no prior-season archetype (the broadest of the
        -- three cold-start blocks; ~87% true rookies/call-ups). Signals that the
        -- archetype/Stuff+/platoon values above are population baselines, not the
        -- pitcher's own prior-season profile. Exposed for the E13.4 lift-tests
        -- (stratify) and future MiLB-prior models (Epic 7) to condition on.
        (pa.starter_pitcher_archetype is null)::boolean as is_cold_start,

        -- ── E13.4 Candidate B1: times-through-order penalty (eval-only) ────────
        -- The starter's 3rd-time-through xwOBA-against fade (3rd+ minus 1st time),
        -- from his PRIOR season, empirical-Bayes shrunk toward the prior-season
        -- league mean by the binding bucket's batters-faced (k=150 pseudo-PA, so a
        -- <150-BF sample regresses hard — a short-sample fade is mostly variance).
        -- Cold-start starters (no prior season) collapse to the league baseline.
        -- NOT yet in any production contract — surfaced for the E13.4 lift-test only.
        round(
            (
                coalesce(tts.tto_min_bf, 0)
                  * coalesce(tts.tto3_xwoba_penalty,
                             coalesce(tyb.league_tto_penalty, tab.league_tto_penalty_all))
                + 150 * coalesce(tyb.league_tto_penalty, tab.league_tto_penalty_all)
            ) / nullif(coalesce(tts.tto_min_bf, 0) + 150, 0)
        , 4)                                    as starter_tto3_xwoba_penalty,
        -- prior-season batters-faced backing the penalty (0 = cold-start, baseline-only).
        coalesce(tts.tto_min_bf, 0)             as starter_tto_min_bf_prior

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
    -- E1.11 start-indexed form (last ≤3 prior starts; gap-immune)
    left join sp_form_stats sfs
        on  sfs.game_pk     = pp.game_pk
        and sfs.pitcher_id  = pp.pitcher_id
    -- E1.11 Phase 2 — recently-acquired context + new-team (same-team) form
    left join pitcher_acquisition acq
        on  acq.game_pk     = pp.game_pk
        and acq.pitcher_id  = pp.pitcher_id
    left join sp_form_same_team_stats sfst
        on  sfst.game_pk    = pp.game_pk
        and sfst.pitcher_id = pp.pitcher_id
    left join velo_stats vs
        on  vs.game_pk      = pp.game_pk
        and vs.pitcher_id   = pp.pitcher_id
    left join arsenal_features af
        on  af.mlbam_pitcher_id = pp.pitcher_id
        -- E1.8 LEAKAGE FIX (was `year(pp.game_date)`): the FanGraphs arsenal is a
        -- full-season pitcher×season value taken at the LATEST ingestion, so joining the
        -- CURRENT season embedded game-G-and-later pitches (LEAKY-season-to-date). The
        -- prior season keeps the stable pitch-shape signal (Stuff+ is ~stationary across a
        -- season) without the peek; rookies / first-MLB-season starters → NULL (imputed).
        -- A/B (clustered MDA): `home_starter_stuff_plus` importance collapsed ~88%
        -- (Δmae +0.0065 → +0.0008) when repointed → ~the entire signal was the peek.
        -- Mirrors the platoon-split / park-factor prior-season convention. NOTE: ZiPS
        -- (zips_fip below) deliberately stays CURRENT season — it is a PRE-season projection
        -- published before opening day, not a leak. See ablation_results/feature_leakage_audit.md §3.
        and af.season           = year(pp.game_date) - 1
    left join zips_fip zf
        on  zf.pitcher_id   = pp.pitcher_id
        and zf.season       = year(pp.game_date)
    left join fip_stats fs
        on  fs.game_pk      = pp.game_pk
        and fs.pitcher_id   = pp.pitcher_id
    left join csw_pre_game cswg
        on  cswg.game_pk    = pp.game_pk
        and cswg.pitcher_id = pp.pitcher_id
    left join pitch_mix_pre_game pmpg
        on  pmpg.game_pk    = pp.game_pk
        and pmpg.pitcher_id = pp.pitcher_id
    left join eb_posteriors eb
        on  eb.game_pk      = pp.game_pk
        and eb.pitcher_id   = pp.pitcher_id
    left join pitcher_archetype pa
        on  pa.game_pk      = pp.game_pk
        and pa.pitcher_id   = pp.pitcher_id
    -- E13.4 Candidate B1 TTO: prior-season penalty + year-1 league anchor + pooled fallback.
    left join tto_splits tts
        on  tts.game_pk     = pp.game_pk
        and tts.pitcher_id  = pp.pitcher_id
    left join tto_yr_baseline tyb
        on  tyb.season      = year(pp.game_date) - 1
    cross join tto_all_baseline tab
    -- E13.7 cold-start baselines: year-1 league means (leak-clean, prior season) with an
    -- all-seasons pooled fallback for the earliest data year. Platoon baselines are
    -- hand-specific (L for the LHB split, R for the RHB split).
    left join arsenal_yr_baseline ayb
        on  ayb.season      = year(pp.game_date) - 1
    cross join arsenal_all_baseline aab
    left join platoon_yr_baseline plbl
        on  plbl.season     = year(pp.game_date) - 1
        and plbl.batter_hand = 'L'
    left join platoon_yr_baseline plbr
        on  plbr.season     = year(pp.game_date) - 1
        and plbr.batter_hand = 'R'
    left join platoon_all_baseline plal
        on  plal.batter_hand = 'L'
    left join platoon_all_baseline plar
        on  plar.batter_hand = 'R'
)

select * from final

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_starter_features

{% endif %}

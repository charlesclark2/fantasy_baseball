-- =============================================================================
-- mart_starter_pitch_mix_rolling.sql
-- Grain: one row per pitcher_id × game_pk (regular-start games only)
-- Purpose: Within-season pitch mix percentages for starting pitchers, used to
--          compute arsenal drift (trailing 5-start mix vs. season-to-date mix).
--
-- Pitch groups (per Card 8.M spec):
--   fastball : FF, SI, FC
--   breaking : SL, CU, SV, KC
--   offspeed : CH, FS, FO
--   (everything else is 'other' and is included in the total_pitches denominator
--    but not surfaced as a feature column)
--
-- Rolling windows use the current start as the right edge:
--   *_pct_5start  — trailing 5 starts (current + 4 preceding)
--   *_pct_season  — season-to-date through current start
--
-- LEAKAGE GUARD: applied in the consuming feature model
-- (feature_pregame_starter_features) via strict game_date < prediction_game_date.
-- Selecting the most recent row strictly before the prediction date gives
-- trailing-5 = the 5 most recent completed starts and season = season-to-date
-- through the previous start, both of which are leakage-safe.
--
-- NULL pct columns when career_starts_before_game < 5 (debut and very early
-- career starters have unstable mix estimates). career_starts_before_game
-- counts strictly-prior career starts; the consuming feature model imputes
-- drift to 0.0 for these cases.
--
-- Card 8.M.
-- =============================================================================

{{ config(materialized='table') }}

with

pitch_events as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        case when pitch_type in ('FF', 'SI', 'FC')      then 1 else 0 end as is_fastball,
        case when pitch_type in ('SL', 'CU', 'SV', 'KC') then 1 else 0 end as is_breaking,
        case when pitch_type in ('CH', 'FS', 'FO')      then 1 else 0 end as is_offspeed
    from {{ ref('mart_pitch_characteristics') }}
    where game_year >= 2015
),

-- Restrict to starting pitchers via the same ≥20-pitch threshold used in
-- mart_starter_csw_rolling (mirrors mart_starting_pitcher_game_log starter rule).
pitcher_game_pitches as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        sum(is_fastball) as fastball_pitches,
        sum(is_breaking) as breaking_pitches,
        sum(is_offspeed) as offspeed_pitches,
        count(*)         as total_pitches
    from pitch_events
    group by pitcher_id, game_pk, game_date, game_year
    having count(*) >= 20
),

rolling as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        fastball_pitches,
        breaking_pitches,
        offspeed_pitches,
        total_pitches,

        -- Trailing 5-start sums (current + 4 preceding starts)
        sum(fastball_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between 4 preceding and current row
        ) as fastball_pitches_5start,
        sum(breaking_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between 4 preceding and current row
        ) as breaking_pitches_5start,
        sum(offspeed_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between 4 preceding and current row
        ) as offspeed_pitches_5start,
        sum(total_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between 4 preceding and current row
        ) as total_pitches_5start,

        -- Season-to-date sums through current start
        sum(fastball_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between unbounded preceding and current row
        ) as fastball_pitches_season,
        sum(breaking_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between unbounded preceding and current row
        ) as breaking_pitches_season,
        sum(offspeed_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between unbounded preceding and current row
        ) as offspeed_pitches_season,
        sum(total_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between unbounded preceding and current row
        ) as total_pitches_season,

        -- Career start number including current (1-indexed). Strictly-prior
        -- career starts = this value - 1.
        row_number() over (
            partition by pitcher_id
            order by game_date, game_pk
        ) as career_start_number

    from pitcher_game_pitches
),

final as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        total_pitches_5start,
        career_start_number - 1 as career_starts_before_game,

        -- Trailing 5-start mix percentages. NULL when fewer than 5 strictly-prior
        -- career starts exist (career_starts_before_game < 5).
        case
            when career_start_number - 1 < 5 then null
            else round(fastball_pitches_5start::float
                       / nullif(total_pitches_5start, 0), 4)
        end as fastball_pct_5start,
        case
            when career_start_number - 1 < 5 then null
            else round(breaking_pitches_5start::float
                       / nullif(total_pitches_5start, 0), 4)
        end as breaking_pct_5start,
        case
            when career_start_number - 1 < 5 then null
            else round(offspeed_pitches_5start::float
                       / nullif(total_pitches_5start, 0), 4)
        end as offspeed_pct_5start,

        -- Season-to-date mix percentages (also gated on career experience to
        -- match the trailing-5 nullability and keep drift well-defined).
        case
            when career_start_number - 1 < 5 then null
            else round(fastball_pitches_season::float
                       / nullif(total_pitches_season, 0), 4)
        end as fastball_pct_season,
        case
            when career_start_number - 1 < 5 then null
            else round(breaking_pitches_season::float
                       / nullif(total_pitches_season, 0), 4)
        end as breaking_pct_season,
        case
            when career_start_number - 1 < 5 then null
            else round(offspeed_pitches_season::float
                       / nullif(total_pitches_season, 0), 4)
        end as offspeed_pct_season

    from rolling
)

select * from final

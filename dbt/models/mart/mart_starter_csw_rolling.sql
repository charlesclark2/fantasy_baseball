-- =============================================================================
-- mart_starter_csw_rolling.sql
-- Grain: one row per pitcher_id × game_pk (regular season starts only)
-- Purpose: Called Strike plus Whiff rate (CSW%) for starting pitchers.
--          CSW% = (called_strike + swinging_strike + swinging_strike_blocked)
--                 / total_pitches. More responsive to current form than Stuff+
--          because it reflects actual command outcomes in recent starts.
--
-- Rolling windows (including current start — leakage guard applied at join):
--   csw_pct_3start  — trailing 3-start CSW% (3-start sum / total pitches)
--   csw_pct_season  — season-to-date CSW%
--   pitches_3start  — total pitches in trailing 3 starts (reliability flag)
--
-- LEAKAGE GUARD: enforced in the consuming feature model
-- (feature_pregame_starter_features) via strict game_date < prediction_game_date.
-- This mart's rolling windows include the current start, which is correct —
-- the most recent completed start is fair game for predicting the next one.
--
-- NULL when a pitcher has no prior starts in the season (debut starters).
-- Card 8.Q.
-- =============================================================================

{{ config(materialized='table') }}

with

pitch_events as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        -- CSW pitch: called strike, swinging strike, or swinging strike blocked
        case
            when pitch_description in (
                'called_strike',
                'swinging_strike',
                'swinging_strike_blocked'
            ) then 1 else 0
        end as is_csw
    from {{ ref('mart_pitch_play_event') }}
    where game_year >= 2015
),

-- Restrict to starting pitchers only (≥ 20 pitches per game — mirrors
-- mart_starting_pitcher_game_log starter definition threshold)
pitcher_game_pitches as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        sum(is_csw)  as csw_pitches,
        count(*)     as total_pitches
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
        csw_pitches,
        total_pitches,

        -- Trailing 3-start CSW%: current start + 2 preceding starts
        -- ROWS BETWEEN 2 PRECEDING AND CURRENT ROW gives a 3-row window
        round(
            sum(csw_pitches) over (
                partition by pitcher_id, game_year
                order by game_date
                rows between 2 preceding and current row
            )::float
            / nullif(
                sum(total_pitches) over (
                    partition by pitcher_id, game_year
                    order by game_date
                    rows between 2 preceding and current row
                ),
                0
            ),
            4
        ) as csw_pct_3start,

        -- Season-to-date CSW% through the current start
        round(
            sum(csw_pitches) over (
                partition by pitcher_id, game_year
                order by game_date
                rows between unbounded preceding and current row
            )::float
            / nullif(
                sum(total_pitches) over (
                    partition by pitcher_id, game_year
                    order by game_date
                    rows between unbounded preceding and current row
                ),
                0
            ),
            4
        ) as csw_pct_season,

        -- Total pitches in trailing 3 starts (reliability flag)
        -- < 150 pitches (~50 pitches/start × 3) indicates a thin sample
        sum(total_pitches) over (
            partition by pitcher_id, game_year
            order by game_date
            rows between 2 preceding and current row
        ) as pitches_3start,

        -- Season start count (for debut detection; NULL guard applied below)
        row_number() over (
            partition by pitcher_id, game_year
            order by game_date
        ) as season_start_number

    from pitcher_game_pitches
),

final as (
    select
        pitcher_id,
        game_pk,
        game_date,
        game_year,
        -- NULL out metrics when this is the pitcher's first start of the season
        -- (no prior data to compute rolling stats from)
        case when season_start_number = 1 then null else csw_pct_3start end as csw_pct_3start,
        case when season_start_number = 1 then null else csw_pct_season  end as csw_pct_season,
        case when season_start_number = 1 then null else pitches_3start  end as pitches_3start
    from rolling
)

select * from final

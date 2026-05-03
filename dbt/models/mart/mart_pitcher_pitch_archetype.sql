{{ config(materialized='table') }}

-- Grain: pitcher_id × game_year
-- Classifies each pitcher × season into a pitch-mix archetype based on
-- Statcast pitch_type usage proportions.
--
-- ARCHETYPE CLASSIFICATION (first match wins):
--   fastball_dominant  — (FF+SI+FT+FC) share > 60% of classified pitches
--   breaking_dominant  — (SL+CU+KC+SV+CS) share > 50% of classified pitches
--   mixed              — everything else
--
-- Unknown/rare types (KN, FA, EP, PO, UN, null) excluded from denominator.
-- Minimum gate: 100 classified pitches (~3 starts) to suppress noise.

with pitch_source as (
    select
        pitcher_id,
        game_year,
        pitch_type
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and pitch_type is not null
      and pitcher_id is not null
),

pitch_counts as (
    select
        pitcher_id,
        game_year,
        count(*)                                        as total_pitches,
        sum(case when pitch_type in
            ('FF','SI','FT','FC')    then 1 else 0 end) as fastball_pitches,
        sum(case when pitch_type in
            ('SL','CU','KC','SV','CS') then 1 else 0 end) as breaking_pitches,
        sum(case when pitch_type in
            ('CH','FS','SC')         then 1 else 0 end) as offspeed_pitches
    from pitch_source
    group by pitcher_id, game_year
),

with_pcts as (
    select
        pitcher_id,
        game_year,
        total_pitches,
        fastball_pitches,
        breaking_pitches,
        offspeed_pitches,
        fastball_pitches + breaking_pitches + offspeed_pitches
                                                    as classified_pitches,
        round(fastball_pitches::float /
              nullif(fastball_pitches + breaking_pitches + offspeed_pitches, 0), 3)
                                                    as fastball_pct,
        round(breaking_pitches::float /
              nullif(fastball_pitches + breaking_pitches + offspeed_pitches, 0), 3)
                                                    as breaking_pct,
        round(offspeed_pitches::float /
              nullif(fastball_pitches + breaking_pitches + offspeed_pitches, 0), 3)
                                                    as offspeed_pct
    from pitch_counts
    where fastball_pitches + breaking_pitches + offspeed_pitches >= 100
)

select
    pitcher_id,
    game_year,
    total_pitches,
    classified_pitches,
    fastball_pct,
    breaking_pct,
    offspeed_pct,
    case
        when fastball_pct > 0.60  then 'fastball_dominant'
        when breaking_pct > 0.50  then 'breaking_dominant'
        else                           'mixed'
    end                                             as pitch_archetype
from with_pcts

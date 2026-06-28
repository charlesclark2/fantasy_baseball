{{
    config(
        materialized = 'view',
        tags         = ['w3_lakehouse']
    )
}}

-- Grain: batter_id × pitch_archetype × game_year
-- Aggregates batter outcomes against each pitcher pitch-mix archetype.
--
-- PA-level stats use plate_appearance_event IS NOT NULL to isolate terminal
-- pitches (one row per PA). Outcome flags are derived from plate_appearance_event
-- following the same definitions as mart_batter_vs_handedness_splits.
--
-- Shrinkage toward league average for small samples:
--   shrink_weight = pa_count / (pa_count + 50)
-- Cells with fewer PA blend toward league-average constants so sparse rows
-- don't produce extreme feature values.
--
-- E11.1-W3: dual-branch lakehouse model. Upstream stg_batter_pitches (W1) and
-- mart_pitcher_pitch_archetype (W3, built + registered as a view immediately
-- before this model by run_w1_lakehouse.py) are S3 parquet; the Snowflake branch
-- is a thin view over the lakehouse_ext external table.

{% if target.name == 'duckdb' %}

with pitches as (
    select
        bp.batter_id,
        bp.pitcher_id,
        bp.game_year,
        bp.plate_appearance_event,
        bp.woba_value,
        bp.woba_denom,
        bp.xwoba,
        pa.pitch_archetype
    from stg_batter_pitches bp
    inner join mart_pitcher_pitch_archetype pa
        on  pa.pitcher_id = bp.pitcher_id
        and pa.game_year  = bp.game_year
    where bp.game_type = 'R'
),

pitches_tagged as (
    select
        batter_id,
        pitch_archetype,
        game_year,
        plate_appearance_event,
        woba_value,
        woba_denom,
        xwoba,

        case when plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end                                     as is_strikeout,

        case when plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ) then 1 else 0 end                                     as is_hit,

        case
            when plate_appearance_event = 'single'   then 1
            when plate_appearance_event = 'double'   then 2
            when plate_appearance_event = 'triple'   then 3
            when plate_appearance_event = 'home_run' then 4
            else 0
        end                                                     as total_bases,

        case when plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'catcher_interf'
        ) then 1 else 0 end                                     as is_at_bat

    from pitches
),

pa_terminal as (
    select * from pitches_tagged
    where plate_appearance_event is not null
),

batter_archetype_agg as (
    select
        batter_id,
        pitch_archetype,
        game_year,
        count(*)                                                as pa_count,
        round(sum(woba_value)
              / nullif(sum(woba_denom), 0), 3)                 as raw_woba,
        round(avg(xwoba), 3)                                   as raw_xwoba,
        round(sum(is_strikeout)
              / nullif(count(*), 0)::float, 3)                 as raw_k_pct,
        round((sum(total_bases) - sum(is_hit))
              / nullif(sum(is_at_bat), 0)::float, 3)           as raw_iso
    from pa_terminal
    group by batter_id, pitch_archetype, game_year
),

with_shrinkage as (
    select
        batter_id,
        pitch_archetype,
        game_year,
        pa_count,
        raw_woba,
        raw_xwoba,
        raw_k_pct,
        raw_iso,
        pa_count / (pa_count + 50.0)                           as shrink_weight,
        round(
            (pa_count / (pa_count + 50.0)) * coalesce(raw_woba,  0.320)
            + (1 - pa_count / (pa_count + 50.0)) * 0.320, 3
        )                                                      as adj_woba,
        round(
            (pa_count / (pa_count + 50.0)) * coalesce(raw_xwoba, 0.315)
            + (1 - pa_count / (pa_count + 50.0)) * 0.315, 3
        )                                                      as adj_xwoba,
        round(
            (pa_count / (pa_count + 50.0)) * coalesce(raw_k_pct, 0.225)
            + (1 - pa_count / (pa_count + 50.0)) * 0.225, 3
        )                                                      as adj_k_pct,
        round(
            (pa_count / (pa_count + 50.0)) * coalesce(raw_iso,   0.165)
            + (1 - pa_count / (pa_count + 50.0)) * 0.165, 3
        )                                                      as adj_iso
    from batter_archetype_agg
)

select * from with_shrinkage

{% else %}

select * from baseball_data.lakehouse_ext.mart_batter_vs_pitch_archetype

{% endif %}

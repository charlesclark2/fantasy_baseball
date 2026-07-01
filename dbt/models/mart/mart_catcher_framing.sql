-- =============================================================================
-- mart_catcher_framing.sql
-- Grain: player_id × season (latest weekly snapshot)
-- Source: FanGraphs leaderboard API via ingest_catcher_framing.py
--
-- Blended metrics: 70% current season + 30% prior season.
--   NULL prior season → 100% current season weight.
-- Reliability regression: scale toward 0 for catchers with < 60 innings caught
--   (≈ 500 called pitches). Applied to all three metrics.
--
-- Columns exposed:
--   framing_runs_above_average   -- CFraming blended + regressed
--   defensive_runs_above_average -- FRP blended + regressed (total catcher defense)
--   stolen_base_runs_above_average -- rSB blended + regressed (arm/throwing)
--   is_reliable                  -- true when innings_caught >= 60
-- Card 8.K
-- =============================================================================

-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- catcher_framing_raw S3 parquet (exported by scripts/export_w4_raw_to_s3.py); the
-- Snowflake branch is a thin view over the lakehouse_ext external table written by
-- run_w1_lakehouse.py --w4. The transform is value-identical to the prior Snowflake
-- table (reads only the flat typed columns — no raw_json).
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with

-- Pick the most recent weekly snapshot per player × season
latest as (
    select
        player_id,
        season,
        framing_runs,
        defensive_runs,
        stolen_base_runs,
        innings_caught,
        row_number() over (
            partition by player_id, season
            order by snapshot_date desc, ingestion_timestamp desc
        )   as rn
    -- E11.1-W11 read-repoint: live-writer raw mirror (lakehouse_raw/, dual-written by
    -- ingest_catcher_framing.py under W11_RAW_WRITE_MODE); snapshot_date desc wins latest.
    from read_parquet('{{ lakehouse_raw_loc("catcher_framing_raw") }}**/*.parquet', union_by_name=true)
    where framing_runs is not null
),

current_season as (
    select player_id, season, framing_runs, defensive_runs, stolen_base_runs, innings_caught
    from latest
    where rn = 1
),

-- Self-join to attach prior season alongside current season
with_prior as (
    select
        c.player_id,
        c.season,
        c.innings_caught,
        c.framing_runs          as framing_curr,
        c.defensive_runs        as defense_curr,
        c.stolen_base_runs      as sb_curr,
        p.framing_runs          as framing_prior,
        p.defensive_runs        as defense_prior,
        p.stolen_base_runs      as sb_prior
    from current_season c
    left join current_season p
        on  p.player_id = c.player_id
        and p.season    = c.season - 1
),

blended as (
    select
        player_id,
        season,
        innings_caught,
        -- 70/30 blend; NULL prior falls back to 100% current
        case when framing_prior is null then framing_curr
             else 0.70 * framing_curr + 0.30 * framing_prior
        end     as framing_blended,
        case when defense_prior is null then defense_curr
             else 0.70 * defense_curr + 0.30 * defense_prior
        end     as defense_blended,
        case when sb_prior is null then sb_curr
             else 0.70 * sb_curr + 0.30 * sb_prior
        end     as sb_blended
    from with_prior
),

final as (
    select
        player_id,
        season,
        innings_caught,
        (coalesce(innings_caught, 0) >= 60)::boolean    as is_reliable,
        -- Reliability regression: scale toward 0 for < 60 innings
        round(
            framing_blended
                * least(coalesce(innings_caught, 0), 60) / 60.0
        , 4)    as framing_runs_above_average,
        round(
            defense_blended
                * least(coalesce(innings_caught, 0), 60) / 60.0
        , 4)    as defensive_runs_above_average,
        round(
            sb_blended
                * least(coalesce(innings_caught, 0), 60) / 60.0
        , 4)    as stolen_base_runs_above_average
    from blended
)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_catcher_framing

{% endif %}

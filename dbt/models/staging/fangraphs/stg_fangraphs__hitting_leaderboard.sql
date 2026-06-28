-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- fg_hitting_leaderboard_raw S3 parquet (flattening the VARCHAR raw_json); the
-- Snowflake branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with source as (
    select * from read_parquet('{{ lakehouse_loc("fg_hitting_leaderboard_raw") }}**/*.parquet', union_by_name=true)
),

extracted as (
    select
        -- ── Identity ──────────────────────────────────────────────────────────
        json_extract_string(raw_json, '$.playerid')::varchar           as fg_batter_id,
        json_extract_string(raw_json, '$.PlayerName')::varchar         as batter_name,
        json_extract_string(raw_json, '$.xMLBAMID')::varchar           as mlbam_batter_id,
        json_extract_string(raw_json, '$.Team')::varchar               as team_abbrev,
        json_extract_string(raw_json, '$.Age')::integer                as age,
        json_extract_string(raw_json, '$.Pos')::varchar                as position,
        season,
        window_type,
        window_start,
        window_end,

        -- ── Volume / counting ─────────────────────────────────────────────────
        json_extract_string(raw_json, '$.PA')::float                   as pa,
        json_extract_string(raw_json, '$.AB')::float                   as ab,
        json_extract_string(raw_json, '$.G')::float                    as g,
        json_extract_string(raw_json, '$.HR')::float                   as hr,
        json_extract_string(raw_json, '$.R')::float                    as r,
        json_extract_string(raw_json, '$.RBI')::float                  as rbi,
        json_extract_string(raw_json, '$.SB')::float                   as sb,

        -- ── Traditional rates ─────────────────────────────────────────────────
        json_extract_string(raw_json, '$.AVG')::float                  as avg,
        json_extract_string(raw_json, '$.OBP')::float                  as obp,
        json_extract_string(raw_json, '$.SLG')::float                  as slg,
        json_extract_string(raw_json, '$.OPS')::float                  as ops,
        json_extract_string(raw_json, '$.ISO')::float                  as iso,
        json_extract_string(raw_json, '$.BABIP')::float                as babip,

        -- ── Walk / strikeout ──────────────────────────────────────────────────
        json_extract_string(raw_json, '$."K%"')::float                 as k_pct,
        json_extract_string(raw_json, '$."BB%"')::float                as bb_pct,
        json_extract_string(raw_json, '$."BB/K"')::float               as bb_per_k,
        json_extract_string(raw_json, '$."TTO%"')::float               as tto_pct,

        -- ── Weighted run metrics ──────────────────────────────────────────────
        json_extract_string(raw_json, '$."wRC+"')::float               as wrc_plus,
        json_extract_string(raw_json, '$.wOBA')::float                 as woba,
        json_extract_string(raw_json, '$.wRAA')::float                 as wraa,
        json_extract_string(raw_json, '$.WAR')::float                  as war,

        -- ── Plate discipline / swing ──────────────────────────────────────────
        json_extract_string(raw_json, '$."O-Swing%"')::float           as o_swing_pct,
        json_extract_string(raw_json, '$."Z-Swing%"')::float           as z_swing_pct,
        json_extract_string(raw_json, '$."Swing%"')::float             as swing_pct,
        json_extract_string(raw_json, '$."O-Contact%"')::float         as o_contact_pct,
        json_extract_string(raw_json, '$."Z-Contact%"')::float         as z_contact_pct,
        json_extract_string(raw_json, '$."Contact%"')::float           as contact_pct,
        json_extract_string(raw_json, '$."Zone%"')::float              as zone_pct,
        json_extract_string(raw_json, '$."SwStr%"')::float             as swstr_pct,
        json_extract_string(raw_json, '$."F-Strike%"')::float          as f_strike_pct,

        -- ── Exit velocity / batted ball quality ───────────────────────────────
        json_extract_string(raw_json, '$.EV')::float                   as ev_avg,
        json_extract_string(raw_json, '$.EV90')::float                 as ev_90th,
        json_extract_string(raw_json, '$.maxEV')::float                as ev_max,
        json_extract_string(raw_json, '$."Barrel%"')::float            as barrel_pct,
        json_extract_string(raw_json, '$."HardHit%"')::float           as hard_hit_pct,

        -- ── Batted ball profile ───────────────────────────────────────────────
        json_extract_string(raw_json, '$."GB%"')::float                as gb_pct,
        json_extract_string(raw_json, '$."LD%"')::float                as ld_pct,
        json_extract_string(raw_json, '$."FB%"')::float                as fb_pct,
        json_extract_string(raw_json, '$."IFFB%"')::float              as iffb_pct,
        json_extract_string(raw_json, '$."HR/FB"')::float              as hr_per_fb,
        json_extract_string(raw_json, '$.LA')::float                   as launch_angle_avg,
        json_extract_string(raw_json, '$."Pull%"')::float              as pull_pct,
        json_extract_string(raw_json, '$."Cent%"')::float              as cent_pct,
        json_extract_string(raw_json, '$."Oppo%"')::float              as oppo_pct,

        -- ── Expected stats (Statcast-era) ──────────────────────────────────────
        json_extract_string(raw_json, '$.xwOBA')::float                as xwoba,
        json_extract_string(raw_json, '$.xAVG')::float                 as xavg,
        json_extract_string(raw_json, '$.xSLG')::float                 as xslg,

        -- ── Bat tracking (2023+) ───────────────────────────────────────────────
        json_extract_string(raw_json, '$.AvgBatSpeed')::float          as avg_bat_speed,
        json_extract_string(raw_json, '$.AttackAngle')::float          as attack_angle,
        json_extract_string(raw_json, '$.SwingLength')::float          as swing_length,
        json_extract_string(raw_json, '$."BlastContact%"')::float      as blast_contact_pct,
        json_extract_string(raw_json, '$."BlastSwing%"')::float        as blast_swing_pct,
        json_extract_string(raw_json, '$."FastSwing%"')::float         as fast_swing_pct,
        json_extract_string(raw_json, '$."SquaredUpContact%"')::float  as squared_up_contact_pct,
        json_extract_string(raw_json, '$."SquaredUpSwing%"')::float    as squared_up_swing_pct,

        -- ── Baserunning ───────────────────────────────────────────────────────
        json_extract_string(raw_json, '$.wBsR')::float                 as wbsr,
        json_extract_string(raw_json, '$.UBR')::float                  as ubr,
        json_extract_string(raw_json, '$.Spd')::float                  as spd_score,

        -- ── Metadata ──────────────────────────────────────────────────────────
        ingestion_ts,
        load_id,
        row_number() over (
            partition by json_extract_string(raw_json, '$.playerid')::varchar, season, window_type, window_start
            order by ingestion_ts desc
        ) as _rn
    from source
)

select
    -- Identity
    fg_batter_id,
    batter_name,
    mlbam_batter_id,
    team_abbrev,
    age,
    position,
    season,
    window_type,
    window_start,
    window_end,

    -- Volume
    pa,
    ab,
    g,
    hr,
    r,
    rbi,
    sb,

    -- Traditional rates
    avg,
    obp,
    slg,
    ops,
    iso,
    babip,

    -- Walk / strikeout
    k_pct,
    bb_pct,
    bb_per_k,
    tto_pct,

    -- Weighted run metrics
    wrc_plus,
    woba,
    wraa,
    war,

    -- Plate discipline
    o_swing_pct,
    z_swing_pct,
    swing_pct,
    o_contact_pct,
    z_contact_pct,
    contact_pct,
    zone_pct,
    swstr_pct,
    f_strike_pct,

    -- Exit velocity / quality
    ev_avg,
    ev_90th,
    ev_max,
    barrel_pct,
    hard_hit_pct,

    -- Batted ball profile
    gb_pct,
    ld_pct,
    fb_pct,
    iffb_pct,
    hr_per_fb,
    launch_angle_avg,
    pull_pct,
    cent_pct,
    oppo_pct,

    -- Expected stats
    xwoba,
    xavg,
    xslg,

    -- Bat tracking
    avg_bat_speed,
    attack_angle,
    swing_length,
    blast_contact_pct,
    blast_swing_pct,
    fast_swing_pct,
    squared_up_contact_pct,
    squared_up_swing_pct,

    -- Baserunning
    wbsr,
    ubr,
    spd_score,

    -- Metadata
    ingestion_ts,
    load_id
from extracted
where _rn = 1

{% else %}

select * from baseball_data.lakehouse_ext.stg_fangraphs__hitting_leaderboard

{% endif %}

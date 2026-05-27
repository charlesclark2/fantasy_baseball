{{
    config(
        materialized='table'
    )
}}

with source as (
    select * from {{ source('fangraphs', 'fg_hitting_leaderboard_raw') }}
),

extracted as (
    select
        -- ── Identity ──────────────────────────────────────────────────────────
        raw_json:playerid::varchar                                      as fg_batter_id,
        raw_json:PlayerName::varchar                                    as batter_name,
        raw_json:xMLBAMID::varchar                                      as mlbam_batter_id,
        raw_json:Team::varchar                                          as team_abbrev,
        raw_json:Age::integer                                           as age,
        raw_json:Pos::varchar                                           as position,
        season,
        window_type,
        window_start,
        window_end,

        -- ── Volume / counting ─────────────────────────────────────────────────
        raw_json:PA::float                                              as pa,
        raw_json:AB::float                                              as ab,
        raw_json:G::float                                               as g,
        raw_json:HR::float                                              as hr,
        raw_json:R::float                                               as r,
        raw_json:RBI::float                                             as rbi,
        raw_json:SB::float                                              as sb,

        -- ── Traditional rates ─────────────────────────────────────────────────
        raw_json:AVG::float                                             as avg,
        raw_json:OBP::float                                             as obp,
        raw_json:SLG::float                                             as slg,
        raw_json:OPS::float                                             as ops,
        raw_json:ISO::float                                             as iso,
        raw_json:BABIP::float                                           as babip,

        -- ── Walk / strikeout ──────────────────────────────────────────────────
        raw_json['K%']::float                                           as k_pct,
        raw_json['BB%']::float                                          as bb_pct,
        raw_json['BB/K']::float                                         as bb_per_k,
        raw_json['TTO%']::float                                         as tto_pct,

        -- ── Weighted run metrics ──────────────────────────────────────────────
        raw_json['wRC+']::float                                         as wrc_plus,
        raw_json:wOBA::float                                            as woba,
        raw_json:wRAA::float                                            as wraa,
        raw_json:WAR::float                                             as war,

        -- ── Plate discipline / swing ──────────────────────────────────────────
        raw_json['O-Swing%']::float                                     as o_swing_pct,
        raw_json['Z-Swing%']::float                                     as z_swing_pct,
        raw_json['Swing%']::float                                       as swing_pct,
        raw_json['O-Contact%']::float                                   as o_contact_pct,
        raw_json['Z-Contact%']::float                                   as z_contact_pct,
        raw_json['Contact%']::float                                     as contact_pct,
        raw_json['Zone%']::float                                        as zone_pct,
        raw_json['SwStr%']::float                                       as swstr_pct,
        raw_json['F-Strike%']::float                                    as f_strike_pct,

        -- ── Exit velocity / batted ball quality ───────────────────────────────
        raw_json:EV::float                                              as ev_avg,
        raw_json:EV90::float                                            as ev_90th,
        raw_json:maxEV::float                                           as ev_max,
        raw_json['Barrel%']::float                                      as barrel_pct,
        raw_json['HardHit%']::float                                     as hard_hit_pct,

        -- ── Batted ball profile ───────────────────────────────────────────────
        raw_json['GB%']::float                                          as gb_pct,
        raw_json['LD%']::float                                          as ld_pct,
        raw_json['FB%']::float                                          as fb_pct,
        raw_json['IFFB%']::float                                        as iffb_pct,
        raw_json['HR/FB']::float                                        as hr_per_fb,
        raw_json:LA::float                                              as launch_angle_avg,
        raw_json['Pull%']::float                                        as pull_pct,
        raw_json['Cent%']::float                                        as cent_pct,
        raw_json['Oppo%']::float                                        as oppo_pct,

        -- ── Expected stats (Statcast-era) ──────────────────────────────────────
        raw_json:xwOBA::float                                           as xwoba,
        raw_json:xAVG::float                                            as xavg,
        raw_json:xSLG::float                                            as xslg,

        -- ── Bat tracking (2023+) ───────────────────────────────────────────────
        raw_json:AvgBatSpeed::float                                     as avg_bat_speed,
        raw_json:AttackAngle::float                                     as attack_angle,
        raw_json:SwingLength::float                                     as swing_length,
        raw_json['BlastContact%']::float                                as blast_contact_pct,
        raw_json['BlastSwing%']::float                                  as blast_swing_pct,
        raw_json['FastSwing%']::float                                   as fast_swing_pct,
        raw_json['SquaredUpContact%']::float                            as squared_up_contact_pct,
        raw_json['SquaredUpSwing%']::float                              as squared_up_swing_pct,

        -- ── Baserunning ───────────────────────────────────────────────────────
        raw_json:wBsR::float                                            as wbsr,
        raw_json:UBR::float                                             as ubr,
        raw_json:Spd::float                                             as spd_score,

        -- ── Metadata ──────────────────────────────────────────────────────────
        ingestion_ts,
        load_id,
        row_number() over (
            partition by raw_json:playerid::varchar, season, window_type, window_start
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

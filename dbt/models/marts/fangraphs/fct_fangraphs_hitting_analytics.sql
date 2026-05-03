{{
    config(
        materialized='view'
    )
}}

with zips as (
    select *
    from {{ ref('stg_fangraphs__zips_hitting') }}
    where projection_type = 'zips'
),

-- For each batter × season × window_type, take the most recent snapshot
-- (highest window_start = latest completed window)
latest_windows as (
    select
        fg_batter_id,
        season,
        max(case when window_type = '7d'     then wrc_plus  end) as rolling_wrc_plus_7d,
        max(case when window_type = '14d'    then wrc_plus  end) as rolling_wrc_plus_14d,
        max(case when window_type = '30d'    then wrc_plus  end) as rolling_wrc_plus_30d,
        max(case when window_type = 'season' then wrc_plus  end) as season_wrc_plus,
        max(case when window_type = '7d'     then obp       end) as rolling_obp_7d,
        max(case when window_type = '14d'    then obp       end) as rolling_obp_14d,
        max(case when window_type = '30d'    then obp       end) as rolling_obp_30d,
        max(case when window_type = 'season' then obp       end) as season_obp,
        max(case when window_type = '7d'     then pa        end) as rolling_pa_7d,
        max(case when window_type = '14d'    then pa        end) as rolling_pa_14d,
        max(case when window_type = '30d'    then pa        end) as rolling_pa_30d,
        max(case when window_type = 'season' then pa        end) as season_pa
    from {{ ref('stg_fangraphs__hitting_leaderboard') }}
    group by fg_batter_id, season
)

select
    z.fg_batter_id,
    z.batter_name,
    z.season,
    -- ZiPS pre-season projections
    z.proj_wrc_plus,
    z.proj_obp,
    z.proj_slg,
    z.proj_k_pct,
    z.proj_bb_pct,
    z.proj_pa,
    z.proj_hr,
    z.proj_war,
    z.mlbam_batter_id,
    -- In-season rolling leaderboard snapshots (null when no leaderboard data)
    l.rolling_wrc_plus_7d,
    l.rolling_wrc_plus_14d,
    l.rolling_wrc_plus_30d,
    l.season_wrc_plus,
    l.rolling_obp_7d,
    l.rolling_obp_14d,
    l.rolling_obp_30d,
    l.season_obp,
    l.rolling_pa_7d,
    l.rolling_pa_14d,
    l.rolling_pa_30d,
    l.season_pa
from zips z
left join latest_windows l
    on  z.fg_batter_id = l.fg_batter_id
    and z.season       = l.season

-- sat_snap_counts_weekly — snap-usage satellite on the fct spine (N0.3 port of jaffle
-- `sat_snap_counts_weekly`). Left-joins offense/ST snap counts+pct onto every fct player-week
-- row, keyed on the pfr player id. ⭐ sport-tagged.
with base as (
    -- rename the reused N0.2 snap staging to the mart contract
    select
        upper(trim(pfr_player_id)) as player_id,
        season,
        week,
        offense_snaps,
        offense_pct,
        st_snaps                   as special_teams_snaps,
        st_pct                     as special_teams_pct
    from {{ ref('stg_nfl_snap_counts') }}
),
fct_player_week as (
    select * from {{ ref('fct_player_week') }}
),
joined as (
    select
        'nfl' as sport,
        f.season, f.week, f.player_id, f.pfr_id, f.gsis_it_id, f.player_name, f.team_id,
        f.position, f.status, f.depth_chart_position_rank, f.is_bye, f.week_start_et, f.week_end_et,
        coalesce(b.offense_snaps, 0)                  as offense_snaps,
        coalesce(b.offense_pct, 0.0)                  as offense_pct,
        coalesce(b.special_teams_snaps, 0)            as special_teams_snaps,
        coalesce(b.special_teams_pct, 0.0)            as special_teams_pct
    from fct_player_week f
    left join base b
        on upper(trim(f.pfr_id)) = upper(trim(b.player_id))
       and f.season = b.season
       and f.week = b.week
)
select *
from joined

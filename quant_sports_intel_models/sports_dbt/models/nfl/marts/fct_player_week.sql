-- fct_player_week — the core weekly player fact (N0.3 port of jaffle `fct_player_week`).
--
-- One row per (player, season, week) on the team-week spine (byes included). Assembles the
-- box score (stg_nfl_weekly_data), snap usage (stg_nfl_snap_counts), team volume totals, and the
-- as-of SCD-2 role (dim_player_role joined on week_start_et ∈ [effective, end]). Point-in-time /
-- leakage-safe: the role/opponent/window all come from that week's calendar, never future weeks.
-- Carries the platform PPR/STD fantasy points + a "the_league" custom scoring calc. The richer
-- 145-col stats_player_week source means every legacy column survives EXCEPT `dakota`
-- (qb_efficiency_index → 0; absent upstream — see stg_nfl_weekly_data). ⭐ sport-tagged.
with player_role as (
    select
        player_id, player_name, player_team as team_id, position, status,
        depth_chart_position_rank, record_effective_ts, record_end_ts
    from {{ ref('dim_player_role') }}
),
team_week_calendar as (
    select season, week, team_id, opponent_id, is_bye, week_start_et, week_end_et
    from {{ ref('team_week_calendar') }}
),
weekly_stats as (
    -- one box-score row per (player, season, week) — safety dedup so no left join fans out
    select * from {{ ref('stg_nfl_weekly_data') }}
    qualify row_number() over (partition by season, week, player_id order by team_id) = 1
),
snap_counts as (
    -- rename the reused N0.2 snap staging to the mart contract (pfr_player_id → player_id, st_* → special_teams_*)
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
dim_player as (
    select * from {{ ref('dim_player') }}
),
-- 🐛 SPINE FIX (2026-07-24): the fact universe was `calendar JOIN dim_player_role` — anchored on
-- the depth-chart-derived role dimension. When `depth_charts` lags a season (it has NO 2025 rows),
-- players with no prior depth-chart segment — the ENTIRE 2025 rookie class (Jeanty, Egbuka, …) — get
-- no role window and are DROPPED, even though they have a full box-score line. And an overlapping
-- SCD-2 window fanned the fact out. The durable cure: anchor the universe on the BOX SCORE (which is
-- complete + rookie-inclusive) UNION the role/bye weeks, with role LEFT-joined + deduped so it can
-- never drop or duplicate a stat line. Depth-chart rank is best-effort (NULL when depth_charts lags).
role_windowed as (
    -- the as-of role for a (season, week, player), deduped to ONE segment per player-week so an
    -- overlapping SCD-2 window can never fan the fact out
    select
        t.season, t.week, pr.player_id, t.team_id,
        pr.player_name, pr.position, pr.status, pr.depth_chart_position_rank
    from team_week_calendar t
    join player_role pr
        on pr.team_id = t.team_id
       and t.week_start_et >= pr.record_effective_ts
       and t.week_start_et <= pr.record_end_ts
    qualify row_number() over (
        partition by t.season, t.week, pr.player_id
        order by pr.depth_chart_position_rank asc nulls last, pr.record_effective_ts desc
    ) = 1
),
stat_rows as (
    -- the player-week universe from the box score — includes players with no role segment
    select season, week, player_id, team_id, player_name, position from weekly_stats
),
player_week_keys as (
    select season, week, player_id from role_windowed
    union
    select season, week, player_id from stat_rows
),
resolved as (
    -- resolve team + identity per (season, week, player): prefer the box-score team (where the player
    -- recorded stats), fall back to the role team (bye / DNP weeks that carry a known role)
    select
        k.season, k.week, k.player_id,
        coalesce(st.team_id, rw.team_id)         as team_id,
        coalesce(rw.player_name, st.player_name) as player_name,
        coalesce(rw.position, st.position)       as position,
        rw.status,
        rw.depth_chart_position_rank
    from player_week_keys k
    left join role_windowed rw using (season, week, player_id)
    left join stat_rows     st using (season, week, player_id)
),
spine as (
    -- attach the calendar (bye / opponent / week window) on the resolved team for role AND stat rows
    select
        r.season, r.week, r.player_id, r.player_name, r.team_id,
        c.opponent_id, coalesce(c.is_bye, false) as is_bye,
        r.position, r.status, r.depth_chart_position_rank, c.week_start_et, c.week_end_et
    from resolved r
    left join team_week_calendar c
        on c.season = r.season and c.week = r.week and c.team_id = r.team_id
),
team_totals as (
    select
        season, week, team_id,
        sum(attempts) as team_pass_attempts,
        sum(carries)  as team_rush_attempts,
        sum(targets)  as team_targets
    from weekly_stats
    group by season, week, team_id
),
player_week as (
    select
        s.season,
        s.week,
        s.player_id,
        d.pfr_id,
        d.gsis_it_id,
        s.player_name,
        s.team_id,
        s.opponent_id,
        s.position,
        s.status,
        s.depth_chart_position_rank,
        s.is_bye,
        s.week_start_et,
        s.week_end_et,
        tt.team_pass_attempts,
        tt.team_rush_attempts,
        tt.team_targets,
        coalesce(sc.offense_snaps, 0)                 as offense_snaps,
        coalesce(sc.offense_pct, 0.0)                 as offense_pct,
        coalesce(sc.special_teams_snaps, 0)           as special_teams_snaps,
        coalesce(sc.special_teams_pct, 0.0)           as special_teams_pct,
        coalesce(w.completions, 0)                    as pass_completions,
        coalesce(w.attempts, 0)                       as pass_attempts,
        coalesce(w.passing_yards, 0)                  as passing_yards,
        coalesce(w.passing_tds, 0)                    as passing_touchdowns,
        coalesce(w.interceptions, 0)                  as interceptions,
        coalesce(w.sacks, 0)                          as sacks_taken,
        coalesce(w.sack_yards, 0)                     as sack_yards_lost,
        coalesce(w.sack_fumbles, 0)                   as sack_fumbles,
        coalesce(w.sack_fumbles_lost, 0)              as sack_fumbles_lost,
        coalesce(w.passing_air_yards, 0)              as passing_air_yards,
        coalesce(w.passing_yards_after_catch, 0)      as passing_yards_after_catch,
        coalesce(w.passing_first_downs, 0)            as passing_first_downs,
        coalesce(round(w.passing_expected_points_added, 4), 0) as passing_expected_points_added,
        coalesce(w.passing_2pt_conversions, 0)        as passing_2pt_conversions,
        coalesce(round(w.qb_efficiency_index, 4), 0)  as qb_efficiency_index,
        coalesce(w.carries, 0)                        as rushing_carries,
        coalesce(w.rushing_yards, 0)                  as rushing_yards,
        coalesce(w.rushing_tds, 0)                    as rushing_touchdowns,
        coalesce(w.rushing_fumbles, 0)                as rushing_fumbles,
        coalesce(w.rushing_fumbles_lost, 0)           as rushing_fumbles_lost,
        coalesce(w.rushing_first_downs, 0)            as rushing_first_downs,
        coalesce(round(w.rushing_expected_points_added, 4), 0) as rushing_expected_points_added,
        coalesce(w.rushing_2pt_conversions, 0)        as rushing_2pt_conversions,
        case when tt.team_rush_attempts > 0
            then round(coalesce(w.carries, 0) / tt.team_rush_attempts, 4)
            else 0.0
        end                                           as carry_share,
        coalesce(w.receptions, 0)                     as receptions,
        coalesce(w.targets, 0)                        as receiving_targets,
        coalesce(w.receiving_yards, 0)                as receiving_yards,
        coalesce(w.receiving_tds, 0)                  as receiving_touchdowns,
        coalesce(w.receiving_fumbles, 0)              as receiving_fumbles,
        coalesce(w.receiving_fumbles_lost, 0)         as receiving_fumbles_lost,
        coalesce(w.receiving_air_yards, 0)            as receiving_air_yards,
        coalesce(w.receiving_yards_after_catch, 0)    as receiving_yards_after_catch,
        coalesce(w.receiving_first_downs, 0)          as receiving_first_downs,
        coalesce(round(w.receiving_expected_points_added, 4), 0) as receiving_expected_points_added,
        coalesce(w.receiving_2pt_conversions, 0)      as receiving_2pt_conversions,
        coalesce(round(w.receiving_air_conversion_ratio, 4), 0) as receiving_air_conversion_ratio,
        coalesce(round(w.target_share, 4), 0)         as target_share,
        coalesce(round(w.air_yards_share, 4), 0)      as air_yards_share,
        coalesce(round(w.weighted_opportunity_rating, 4), 0) as weighted_opportunity_rating,
        coalesce(w.special_teams_tds, 0)              as special_teams_touchdowns,
        coalesce(round(w.fantasy_points_std, 4), 0)   as fantasy_points_std,
        coalesce(round(w.fantasy_points_ppr, 4), 0)   as fantasy_points_ppr,
        -- the-league custom scoring
        coalesce(
            round((coalesce(w.passing_tds, 0) * 4.0) + (coalesce(w.interceptions, 0) * -1) + (coalesce(w.passing_yards, 0) / 25.0)
            + (coalesce(w.rushing_yards, 0) / 10.0) + (coalesce(w.rushing_tds, 0) * 6.0)
            + (coalesce(w.receptions, 0) * 0.5) + (coalesce(w.receiving_yards, 0) / 10.0) + (coalesce(w.receiving_tds, 0) * 6.0)
            + (coalesce(w.rushing_2pt_conversions, 0) * 2.0) + (coalesce(w.receiving_2pt_conversions, 0) * 2.0)
            + (coalesce(w.receiving_fumbles_lost, 0) * -2.0) + (coalesce(w.rushing_fumbles_lost, 0) * -2.0), 2),
            0.0
        )                                             as the_league_fantasy_points,
        -- played = took a snap OR recorded a box-score line (robust when snap_counts lags a rookie)
        ((coalesce(sc.offense_snaps, 0) + coalesce(sc.special_teams_snaps, 0)) > 0
         or w.season is not null) as played_flag
    from spine s
    left join dim_player d
        on s.player_id = d.player_id
    left join weekly_stats w
        on w.season = s.season and w.week = s.week and w.player_id = s.player_id
    left join snap_counts sc
        on sc.season = s.season and sc.week = s.week and d.pfr_id = sc.player_id
    left join team_totals tt
        on tt.season = s.season and tt.week = s.week and tt.team_id = s.team_id
)
select 'nfl' as sport, *
from player_week
order by player_id

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
-- NF-W0b: the CROSS-SEASON pfr bridge. `weekly_rosters.pfr_id` is 25–53% NULL in any GIVEN season
-- (measured 2022–2025), but a pfr id is a stable property of a PLAYER — so a player whose 2024 row
-- omits it usually carries it in another season. Keying the bridge on the id ALONE recovers the
-- entire high-value cohort at the strongest rung (`high_value_unmatched_count` 0 for every season):
-- e.g. Michael Woods II, whose 100%-snap CLE week-15 2024 line the per-season key could not attach.
-- `having count(distinct player_id) = 1` is load-bearing: an id claimed by two gsis ids is an
-- ambiguity and resolves to NOTHING rather than to an arbitrary pick.
pfr_bridge as (
    select upper(trim(pfr_id)) as pfr_id, min(player_id) as player_id
    from {{ ref('stg_nfl_weekly_rosters') }}
    where pfr_id is not null and trim(pfr_id) <> '' and player_id is not null
    group by 1
    having count(distinct player_id) = 1
),
snap_counts_bridged as (
    -- Resolve each snap row to our gsis player_id. LEFT join + a retained NULL: a snap row we
    -- cannot attribute must stay VISIBLE (v3 §12A silent_drop_count = 0), never be inner-joined away.
    select coalesce(b.player_id, s.player_id) as player_id, s.season, s.week,
           s.offense_snaps, s.offense_pct, s.special_teams_snaps, s.special_teams_pct,
           (b.player_id is not null)          as is_bridged
    from snap_counts s
    left join pfr_bridge b on b.pfr_id = s.player_id
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
        -- 🐛 NF-W0b SILENT-ZERO FIX (v3 §12A). These were `coalesce(sc.*, 0)`, which turned an
        -- unresolved IDENTITY into an observed 0.0 snap share. A snap share is a rate in [0, 1]
        -- where 0.0 is a legal observation ("dressed, played no offensive snaps"), so the
        -- fabricated zero was INDISTINGUISHABLE from a real one — no error, no NULL, invisible to
        -- every coverage check, and trained on as fact. The absence is now VISIBLE as NULL, and
        -- `snap_source_tier` says which kind of absence it is.
        sc.offense_snaps                              as offense_snaps,
        sc.offense_pct                                as offense_pct,
        sc.special_teams_snaps                        as special_teams_snaps,
        sc.special_teams_pct                          as special_teams_pct,
        case
            when sc.season is not null then 'observed'      -- a real snap row; 0.0 here is REAL
            when s.is_bye                then 'bye'         -- no game, so no snaps to have
            else 'no_snap_row'                              -- inactive / feed lag / unresolved id
        end                                           as snap_source_tier,
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
        -- played = took a snap OR recorded a box-score line (robust when snap_counts lags a rookie).
        -- Written with `is true` rather than `coalesce(sc.<snap col>, 0)` on purpose: this is a
        -- boolean about whether we SAW the player play, so an unknown correctly contributes
        -- nothing — but reaching for a coalesce on a snap VALUE, even in a boolean, is the habit
        -- that produced the silent zero, and the NF-W0b guard bans it outright rather than relying
        -- on a reader to judge which uses are benign. Semantics are identical (NULL is not true).
        ((sc.offense_snaps > 0) is true
         or (sc.special_teams_snaps > 0) is true
         or w.season is not null) as played_flag
    from spine s
    left join dim_player d
        on s.player_id = d.player_id
    left join weekly_stats w
        on w.season = s.season and w.week = s.week and w.player_id = s.player_id
    -- NF-W0b: joined on the CANONICAL player id (the bridge already resolved pfr → gsis), not on
    -- `dim_player.pfr_id` — that per-player pfr column is exactly the sparse key whose misses used
    -- to become silent zeros.
    left join snap_counts_bridged sc
        on sc.season = s.season and sc.week = s.week and sc.player_id = s.player_id
    left join team_totals tt
        on tt.season = s.season and tt.week = s.week and tt.team_id = s.team_id
)
select 'nfl' as sport, *
from player_week
order by player_id

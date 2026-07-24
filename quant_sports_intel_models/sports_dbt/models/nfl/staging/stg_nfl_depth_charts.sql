-- stg_nfl_depth_charts — weekly depth chart (N0.3 port of jaffle `stg_depth_charts`).
--
-- Feeds dim_player_role (position rank + the SCD-2 change signal). Lake asset: `depth_charts`.
--
-- ⭐ TWO SOURCE SCHEMAS unioned — nflverse RESHAPED the feed provider starting 2025:
--   • OLD (≤2024): weekly rows keyed on game_type/formation/depth_team/position (nflverse jaffle-era,
--     15 cols). `depth_team` is dirty VARCHAR across the 1999–2024 span; newer old-format seasons
--     populate the typed `pos_rank` instead → rank = try_cast(depth_team) coalesced to pos_rank
--     (INC-23 use-site-cast discipline). `club_code` coalesced to `team` so format-shift rows survive.
--   • NEW (2025+): ESPN DAILY depth-chart snapshots (`dt`/`team`/`pos_abb`/`pos_rank`, 12 cols) — NO
--     week/game_type/formation. `pos_rank` IS the per-position depth rank (QB 1/2/3, RB 1/2/3…). Each
--     daily snapshot is bucketed to an NFL week via an ASOF join to the schedule-derived Tuesday-00:00
--     week starts (self-contained — mirrors team_week_calendar's window; staging→staging, no mart dep),
--     then deduped to the LATEST snapshot per (season, week, player, position). Snapshots before a
--     season's week 1 (preseason) or without a scheduled week (e.g. a not-yet-scheduled future season)
--     drop out of the ASOF inner join — in-season weeks are fully covered.
-- The two branches are disjoint by `dt IS NULL` (old) vs `dt IS NOT NULL` (new). Offensive skill
-- positions only (the fantasy universe: QB/WR/RB/TE/FB + K). ⭐ sport-tagged.
with base as (
    select *
    from {{ nfl_delta('depth_charts') }}
),
-- ============================== OLD FORMAT (≤2024) ==============================
old_norm as (
    select
        'nfl'                                         as sport,
        trim(gsis_id)                                 as player_id,
        season,
        week,
        case when full_name is null then trim(concat(first_name, ' ', last_name)) else trim(full_name) end as player_name,
        case
            when coalesce(club_code, team) in ('SD', 'LAC')  then 'LAC'
            when coalesce(club_code, team) in ('STL', 'LA')  then 'LAR'
            when coalesce(club_code, team) in ('OAK', 'LV')  then 'LV'
            else coalesce(club_code, team)
        end                                           as player_team,
        position,
        coalesce(try_cast(depth_team as integer), pos_rank) as depth_chart_position_rank,
        case
            when position in ('QB', 'WR', 'RB', 'TE', 'FB') and formation ilike 'offense' then 1
            when position ilike 'k' then 1
            else 0
        end                                           as is_offensive_player
    from base
    where dt is null                                  -- old-format rows only
      and game_type ilike 'reg'
      and coalesce(club_code, team) is not null
      and position in ('QB', 'WR', 'K', 'RB', 'TE', 'FB')
),
-- ============================== NEW FORMAT (2025+) ==============================
-- Schedule-derived NFL week starts (Tue 00:00 ET) — same derivation team_week_calendar uses.
week_starts as (
    select
        season,
        week,
        date_trunc('week', min(game_datetime)) + interval '1 day' as week_start_et
    from {{ ref('stg_nfl_schedules') }}
    group by 1, 2
),
new_raw as (
    select
        trim(gsis_id)                                 as player_id,
        season,
        try_cast(replace(dt, 'Z', '') as timestamp)   as snap_ts,
        case
            when team in ('SD', 'LAC') then 'LAC'
            when team in ('STL', 'LA') then 'LAR'
            when team in ('OAK', 'LV') then 'LV'
            else team
        end                                           as player_team,
        trim(player_name)                             as player_name,
        case upper(pos_abb) when 'PK' then 'K' else upper(pos_abb) end as position,
        try_cast(pos_rank as integer)                 as depth_chart_position_rank
    from base
    where dt is not null                              -- new-format rows only
      and gsis_id is not null
      and team is not null
      and upper(pos_abb) in ('QB', 'WR', 'RB', 'TE', 'FB', 'PK')
),
-- ASOF: assign each snapshot to the latest scheduled week whose start ≤ the snapshot ts (same season).
new_weeked as (
    select
        n.player_id, n.season, n.player_team, n.player_name, n.position,
        n.depth_chart_position_rank, n.snap_ts, ws.week
    from new_raw n
    asof join week_starts ws
        on ws.season = n.season
       and n.snap_ts >= ws.week_start_et
),
-- One row per (season, week, player, position): the latest snapshot landing in that week.
new_dedup as (
    select player_id, season, week, player_name, player_team, position, depth_chart_position_rank
    from (
        select *,
               row_number() over (
                   partition by season, week, player_id, position
                   order by snap_ts desc
               ) as rn
        from new_weeked
    )
    where rn = 1
),
new_norm as (
    select
        'nfl'                                         as sport,
        player_id,
        season,
        week,
        player_name,
        player_team,
        position,
        depth_chart_position_rank,
        1                                             as is_offensive_player
    from new_dedup
),
unioned as (
    select * from old_norm
    union all
    select * from new_norm
)
select * exclude(is_offensive_player)
from unioned
where is_offensive_player = 1

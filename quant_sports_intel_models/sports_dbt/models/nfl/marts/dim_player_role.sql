-- dim_player_role — Type-2 SCD of a player's weekly role (N0.3 port of jaffle `dim_player_role`).
--
-- One row per contiguous (team, position, status, depth-rank) segment per player, with an ET
-- effective/end window. Pure-SQL SCD-2 (feedback: SCD-2 via dbt, not Python): normalize inputs →
-- hash the SCD-relevant fields → detect week-over-week boundary changes → collapse equal-hash
-- runs into intervals. The `record_hash` follows the SCD-2 convention (MD5 over COALESCE'd
-- payload cols). dbt_utils.generate_surrogate_key → MD5 (no dbt_utils dependency); Snowflake
-- timestamp_ntz → DuckDB timestamp. The open segment ends at 2100-12-31 (current_record='Y').
-- ⭐ sport-tagged. Leakage-safe: a segment's window is anchored on that week's calendar, no
-- post-game info folds back.
{{ config(materialized='table') }}

with
weekly_rosters as (
    select * from {{ ref('stg_nfl_weekly_rosters') }}
),
depth_charts as (
    select * from {{ ref('stg_nfl_depth_charts') }}
),
twc as (
    select season, week, team_id, week_start_et, week_end_et, is_bye
    from {{ ref('team_week_calendar') }}
),
-- 1) Canonicalize / normalize inputs (avoid noisy SCD churn)
role_src as (
    select
        d.player_id,
        upper(trim(d.player_name))                    as player_name,
        d.season,
        d.week,
        upper(trim(d.player_team))                    as team_id_norm,
        upper(trim(d.position))                       as position_norm,
        coalesce(d.depth_chart_position_rank, 999)    as depth_chart_position_rank_norm,
        case upper(trim(w.status))
            when 'ACT' then 'ACT'
            when 'INA' then 'INA'
            when 'IR'  then 'IR'
            when 'PUP' then 'RES'
            when 'NFI' then 'RES'
            when 'PS'  then 'PS'
            when 'RES' then 'RES'
            else coalesce(upper(trim(w.status)), 'UNK')
        end                                           as status_bucket,
        w.jersey_number,
        w.age
    from depth_charts d
    left join weekly_rosters w
        on w.player_id = d.player_id
       and w.season    = d.season
       and w.week      = d.week
       and upper(trim(w.team)) = upper(trim(d.player_team))
),
-- 2) Attach team-week calendar (ensures BYE/DNP weeks exist; no filter!)
joined as (
    select
        r.*,
        c.week_start_et,
        c.week_end_et,
        c.is_bye
    from role_src r
    left join twc c
        on c.season = r.season and c.week = r.week and c.team_id = r.team_id_norm
),
-- 3) Row-hash on the normalized, truly SCD-relevant fields (SCD-2 convention: MD5 over COALESCE'd payload)
hashed as (
    select
        md5(concat_ws('|', coalesce(player_id::varchar, ''))) as player_surrogate_key,
        player_id,
        player_name,
        season,
        week,
        team_id_norm,
        position_norm,
        jersey_number,
        status_bucket,
        age,
        depth_chart_position_rank_norm,
        week_start_et,
        week_end_et,
        is_bye,
        md5(concat_ws('|',
            coalesce(team_id_norm, ''),
            coalesce(position_norm, ''),
            coalesce(status_bucket, ''),
            coalesce(depth_chart_position_rank_norm::varchar, '')
        ))                                            as row_hash
    from joined
),
-- 4) Detect boundary changes week-over-week per player
marked as (
    select
        h.*,
        lag(row_hash) over (partition by player_id order by season, week) as prev_hash,
        case when row_hash != lag(row_hash) over (partition by player_id order by season, week)
             then 1 else 0 end                        as is_change
    from hashed h
),
-- 5) Collapse consecutive equal-hash weeks into SCD-2 intervals
grouped as (
    select
        m.*,
        sum(is_change) over (partition by player_id order by season, week
                             rows between unbounded preceding and current row) as grp
    from marked m
),
scd2 as (
    select
        player_surrogate_key,
        player_id,
        max(player_name)                              as player_name,
        team_id_norm                                  as player_team,
        position_norm                                 as position,
        max(jersey_number)                            as jersey_number,
        status_bucket                                 as status,
        max(age)                                      as age,
        depth_chart_position_rank_norm                as depth_chart_position_rank,
        min(season)                                   as start_season,
        min(week)                                     as start_week,
        max(season)                                   as end_season,
        max(week)                                     as end_week,
        min(week_start_et)                            as record_effective_ts,
        max(week_end_et)                              as record_end_ts,
        max(row_hash)                                 as row_hash_final
    from grouped
    group by player_surrogate_key, player_id, player_team, position, status,
             depth_chart_position_rank, grp
),
final as (
    select
        'nfl'                                         as sport,
        player_surrogate_key,
        player_id,
        player_name,
        player_team,
        position,
        jersey_number,
        status,
        age,
        depth_chart_position_rank,
        record_effective_ts::timestamp                as record_effective_ts,
        case
            when record_end_ts = max(record_end_ts) over (partition by player_id)
            then '2100-12-31'::timestamp
            else record_end_ts::timestamp
        end                                           as record_end_ts,
        case
            when record_end_ts = max(record_end_ts) over (partition by player_id) then 'Y'
            else 'N'
        end                                           as current_record_indicator,
        row_hash_final                                as role_hash
    from scd2
)
select *
from final

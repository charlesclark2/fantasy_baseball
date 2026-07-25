-- stg_nfl_depth_charts_current — the LATEST known depth-chart snapshot per (season, player,
-- position), independent of the in-season week grain (NF-D1 cold-start fix, 2026-07-25).
--
-- ⭐ WHY THIS MODEL EXISTS: `stg_nfl_depth_charts` ASOF-maps each daily ESPN snapshot (2025+) to
-- an NFL week via an INNER join against the schedule-derived week starts — a snapshot captured
-- BEFORE a season's week 1 has kicked off (the entire Mar–Aug pre-season/camp-battle window) has
-- no week to map to and is correctly dropped (see that model's docstring: "in-season weeks are
-- fully covered"). That's right for the IN-SEASON week grain `dim_player_role`'s SCD-2 is built
-- on, but it leaves a gap for an UPCOMING season that hasn't started yet: `dim_player_role`'s
-- "current" record stays pinned to the PRIOR season's final week until real games begin, even
-- though nflverse/ESPN is already publishing fresh roster-battle depth all summer. Verified live
-- 2026-07-25 (NF-D1): 365,771 raw 2026 depth_charts rows span 2026-03-22 → 2026-07-24, entirely
-- BEFORE the 2026 week-1 kickoff of 2026-09-09 — so NONE of it reaches `stg_nfl_depth_charts` /
-- `dim_player_role` yet, even though the 2026 schedule is landed. This is the NFL analog of
-- NCAAF-P1.2's cold-start gap (a season with a published schedule but no games played yet needs
-- its own prior, not a silent inheritance of the prior season's frozen state).
--
-- One row per (season, player_id, position): the single MOST RECENT ESPN snapshot for that
-- season regardless of whether the season has a mapped week yet. A downstream consumer (MVP-1's
-- role signal in `run_season_projection.load_base_season`) prefers THIS over `dim_player_role`'s
-- SCD "current" record whenever a row exists for the target season — it is strictly fresher than
-- any record that predates the season starting, and for an in-season target it is at least as
-- fresh (ESPN publishes daily; the week-mapped record only updates weekly).
--
-- Deliberately new-format (2025+) only, mirroring `stg_nfl_depth_charts`'s `new_raw`/`new_dedup`
-- CTEs (team-code + position normalization) minus the week ASOF step: the old (≤2024) weekly rows
-- are already grained to real, played games, so there is no "before week 1" gap to cover for them.
with base as (
    select *
    from {{ nfl_delta('depth_charts') }}
    where dt is not null                              -- new-format rows only (2025+)
      and gsis_id is not null
      and team is not null
      and upper(pos_abb) in ('QB', 'WR', 'RB', 'TE', 'FB', 'PK')
),
norm as (
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
),
latest as (
    select * exclude(rn)
    from (
        select *,
               row_number() over (
                   partition by season, player_id, position
                   order by snap_ts desc
               ) as rn
        from norm
    )
    where rn = 1
)
select
    'nfl'                                              as sport,
    player_id,
    season,
    snap_ts,
    player_name,
    player_team,
    position,
    depth_chart_position_rank
from latest

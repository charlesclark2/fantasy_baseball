-- DEPTH-CHART FEED-RESHAPE GUARD (2026-07-24): nflverse RESHAPED the depth_charts feed provider in
-- 2025 — weekly game_type/formation/depth_team rows (≤2024) became daily ESPN pos_abb/pos_rank
-- snapshots (2025+) with NO week/game_type/formation. stg_nfl_depth_charts now UNIONs both branches
-- and buckets the new daily snapshots to NFL weeks via an ASOF join. If a FUTURE feed reshape (or a
-- broken ASOF/week map) silently drops a branch again, an entire season's skill players lose their
-- depth rank → dim_player_role goes to the 999 default → expected-games (the fantasy playing-time
-- model) degrades to the games-only heuristic with no error. This was the exact "lake lacks 2025"
-- gap that shipped stale role for weeks.
--
-- Fail (rows > 0) if any season with a real box-score skill population has < 40% of those players
-- covered by a depth-chart rank. (Observed healthy coverage: ~0.9–1.4× box players per season.)
with box as (
    select season, count(distinct player_id) as box_players
    from {{ ref('stg_nfl_weekly_data') }}
    where season >= 2019
      and position in ('QB', 'RB', 'WR', 'TE', 'FB')
    group by 1
),
depth as (
    select season, count(distinct player_id) as depth_players
    from {{ ref('stg_nfl_depth_charts') }}
    group by 1
)
select
    b.season,
    b.box_players,
    coalesce(d.depth_players, 0)                                          as depth_players,
    round(coalesce(d.depth_players, 0)::double / nullif(b.box_players, 0), 3) as covered_ratio
from box b
left join depth d using (season)
where coalesce(d.depth_players, 0)::double / nullif(b.box_players, 0) < 0.40

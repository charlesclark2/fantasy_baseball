-- mart_projections_preseason — the fantasy head-start (N0.3 port of jaffle
-- `mart_projections_preseason`). Regresses each player's prior-season per-game rates toward the
-- league mean (70/30) and multiplies by team pace to project weekly + full-season PPR points.
-- ⚠️ PORT DIVERGENCE: jaffle hardcoded season=2024; here the base season is DYNAMIC
-- (`max(season)` in mart_player_season) so the projection always rolls off the latest completed
-- season and populates without an annual edit. ⭐ sport-tagged. Point-in-time-safe: uses only
-- completed-season aggregates as the projection prior.
{{ config(materialized='table') }}

with base_season as (
    select max(season) as s from {{ ref('mart_player_season') }}
),
team as (
    select team_id,
           avg(team_pass_attempts) as team_pa_pg,
           avg(team_rush_attempts) as team_ru_pg
    from {{ ref('mart_opportunity_player_week') }}
    where season = (select s from base_season) and week > 0
    group by 1
),
mart_player_season as (
    select * from {{ ref('mart_player_season') }}
),
lg as (  -- league averages for regression
    select
        avg(catch_rate_pg) catch_rate_league,
        avg(ypt_pg)        ypt_league,
        avg(rush_td_rate_pg) rush_td_rate_league,
        avg(ypc_pg)        ypc_league,
        avg(pass_td_rate_pg) pass_td_rate_league,
        avg(ypa_pg)        ypa_league
    from mart_player_season
    where season = (select s from base_season)
),
s as (
    select ps.*, t.team_pa_pg, t.team_ru_pg, l.*
    from mart_player_season ps
    left join team t using (team_id)
    cross join lg l
    where ps.season = (select s from base_season)
),
proj as (
    select
        s.*,
        0.7 * s.catch_rate_pg + 0.3 * s.catch_rate_league as catch_rate_reg,
        0.7 * s.ypt_pg + 0.3 * s.ypt_league as ypt_reg,
        0.7 * s.ypc_pg            + 0.3 * s.ypc_league            as ypc_reg,
        0.7 * s.rush_td_rate_pg   + 0.3 * s.rush_td_rate_league   as rush_td_rate_reg,
        0.7 * s.pass_td_rate_pg   + 0.3 * s.pass_td_rate_league   as pass_td_rate_reg,
        0.7 * s.ypa_pg            + 0.3 * s.ypa_league            as ypa_reg,
        case when position in ('WR', 'TE') then s.target_share_pg * s.team_pa_pg end as proj_targets,
        case when position = 'RB' then s.carry_share_pg * s.team_ru_pg end as proj_carries,
        case when position = 'QB' then s.dropback_share_pg * s.team_pa_pg end as proj_dropbacks,
        case
            when position in ('WR', 'TE') then
                (s.target_share_pg * s.team_pa_pg) * (catch_rate_reg)
                + ((s.target_share_pg * s.team_pa_pg) * ypt_reg) / 10.0
                + ((s.target_share_pg * s.team_pa_pg) * s.rec_td_rate_pg) * 6.0
                + ((s.carry_share_pg * s.team_ru_pg) * ypc_reg) / 10.0
                + ((s.carry_share_pg * s.team_ru_pg) * rush_td_rate_reg) * 6.0
            when position = 'RB' then
                ((s.carry_share_pg * s.team_ru_pg) * ypc_reg) / 10.0
                + ((s.carry_share_pg * s.team_ru_pg) * rush_td_rate_reg) * 6.0
                + ((s.target_share_pg * s.team_pa_pg) * ypt_reg) / 10.0
                + ((s.target_share_pg * s.team_pa_pg) * s.rec_td_rate_pg) * 6.0
            when position = 'QB' then
                (s.team_pa_pg * ypa_reg) / 25.0
                + (s.team_pa_pg * pass_td_rate_reg) * 4
                + ((s.carry_share_pg * s.team_ru_pg) * ypc_reg) / 10.0
                + ((s.carry_share_pg * s.team_ru_pg) * rush_td_rate_reg) * 6.0
                - (0 * 2.0)
        end as projected_fantasy_points_ppr_week
    from s
)
select
    'nfl' as sport,
    season,
    player_name,
    player_id,
    team_id,
    position,
    catch_rate_reg,
    projected_fantasy_points_ppr_week,
    projected_fantasy_points_ppr_week * 17.0 as projected_fantasy_points_ppr_season
from proj
where projected_fantasy_points_ppr_week is not null
  and games_played > 2
order by projected_fantasy_points_ppr_week desc

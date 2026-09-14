-- dim_ncaab_conference — conference identity, id → NAME, with its observed lifespan.
--
-- ⚠️ MEMBERSHIP IS NOT HERE — it drifts, so it lives on dim_ncaab_team's SCD-2 rows. What this
-- carries is the conference's own identity plus its size trace across seasons, which is how a
-- conference that collapsed is visible at all (the Pac-12, id 21, falls to a rump and then to
-- nothing across 2024-2026 in this very data).
--
-- ⭐ THE NAME JOIN IS DELIBERATELY ONE-SIDED. The crosswalk publishes only the CURRENT season,
-- so names are resolved from the latest season and applied to the id across history. That is
-- sound because ESPN's conference IDs are stable while names are not — but it means a
-- conference that no longer exists has NO name available, and this model says so explicitly
-- (`conference_name is null` + `is_defunct`) rather than inventing one or dropping the row.
-- A silently-dropped defunct conference would make historical Pac-12 games unattributable.
{{ config(materialized='table') }}

with membership as (
    select conference_id, valid_from_season, valid_to_season, team_id
    from {{ ref('dim_ncaab_team') }}
),

-- explode each SCD run back to per-season membership so a conference's size trace is real
by_season as (
    select m.conference_id, s.season, count(distinct m.team_id) as n_teams
    from membership m
    join (select distinct season from {{ ref('stg_ncaab_schedule') }}) s
      on s.season between m.valid_from_season and m.valid_to_season
    group by 1, 2
),

names as (
    select conference_id, any_value(conference_name) as conference_name
    from (
        select x.conference_name, d.conference_id
        from {{ ref('stg_ncaab_team_crosswalk') }} x
        join {{ ref('dim_ncaab_team') }} d
          on d.team_id = x.team_id
         and x.season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
        where x.conference_name is not null
    )
    group by conference_id
),

latest as (select max(season) as max_season from by_season)

select
    'ncaab'                                     as sport,
    b.conference_id,
    n.conference_name,
    (n.conference_name is null)                 as name_unresolved,
    min(b.season)                               as first_season,
    max(b.season)                               as last_season,
    min(b.n_teams)                              as min_teams,
    max(b.n_teams)                              as max_teams,
    (max(b.season) < any_value(l.max_season))   as is_defunct
from by_season b
left join names n on n.conference_id = b.conference_id
cross join latest l
group by b.conference_id, n.conference_name

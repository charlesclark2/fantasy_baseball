-- dim_ncaaf_conference — the conference dimension (NCAAF-P1.1).
--
-- ONE row per conference in the FBS universe. Small, but a real conformed dimension: it is the
-- grain every "vs Power-4 / Group-of-5" split and every conference-strength rollup hangs off, and
-- it gives realignment a stable anchor (dim_ncaaf_team's SCD-2 rows point at these names).
--
-- ⚠️ Membership is NOT here — it DRIFTS, so it lives on the SCD-2 dim_ncaaf_team rows. What this
-- dimension carries is the conference's own identity plus its observed lifespan and size trace,
-- which is how you spot a conference that folded (Pac-12 → 2 members in 2024) or was born.
--
-- `is_power_conference` is the standard P4/P5 grouping *as of the current alignment* — a coarse
-- label, deliberately NOT season-varying (the Pac-12's collapse would otherwise make it a
-- time-series of its own). Use conference membership + the opponent-adjusted rollups for real
-- strength; this flag is for slicing, not for modelling.
{{ config(materialized='table') }}

with teams as (
    select * from {{ ref('stg_ncaaf_teams') }}
    where conference is not null
),

by_season as (
    select
        conference,
        season,
        count(distinct team_id) as n_teams
    from teams
    group by 1, 2
),

latest as (
    select conference, n_teams as n_teams_latest_season, season as latest_season
    from (
        select conference, season, n_teams,
               row_number() over (partition by conference order by season desc) as rn
        from by_season
    )
    where rn = 1
)

select
    'ncaaf'                                      as sport,
    b.conference                                 as conference,
    'ncaaf-' || b.conference                     as conference_key,
    min(b.season)                                as first_season,
    max(b.season)                                as last_season,
    l.latest_season,
    l.n_teams_latest_season,
    min(b.n_teams)                               as min_teams,
    max(b.n_teams)                               as max_teams,
    -- a conference last seen before the newest ingested season no longer exists (or left FBS)
    (max(b.season) < (select max(season) from teams)) as is_defunct,
    b.conference in (
        'ACC', 'Big Ten', 'Big 12', 'SEC', 'Pac-12', 'FBS Independents'
    )                                            as is_power_conference
from by_season b
join latest l on l.conference = b.conference
group by 1, 2, 3, l.latest_season, l.n_teams_latest_season, b.conference

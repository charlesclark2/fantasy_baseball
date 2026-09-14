-- dim_ncaab_team — the team dimension, SCD-2 over the attributes that DRIFT (NCAAB-P0).
--
-- ⭐ WHY SCD-2. Conference realignment is the consequential attribute drift in college sport,
-- and NCAAB has just lived through the largest in its history. MEASURED in this source over
-- 2023-2027 alone: 52 teams changed conference. Arizona / Arizona State / Colorado went
-- Pac-12 → Big 12; California went Pac-12 → ACC; BYU / Cincinnati / Houston → Big 12; and the
-- 2027 season moves Austin Peay, Central Arkansas and Eastern Kentucky again. A type-1
-- dimension carrying only "today's" conference would retroactively rewrite history — a 2023
-- Arizona game would report as a Big 12 game — silently corrupting every conference-strength
-- feature and every "vs high-major" split computed from it. So the drifting attribute is
-- VERSIONED.
--
-- GRAIN: one row per (team_id, contiguous run of seasons with an identical payload).
--   payload  = (team name, conference_id)
--   validity = [valid_from_season, valid_to_season] INCLUSIVE, season-grained
--   is_current = the run that includes the newest ingested season
--
-- ⚠️ SEASON-GRAINED, not timestamp-grained, and that is a claim about the SOURCE: conference
-- membership is a season-level fact here, so timestamps would imply a precision the data does
-- not have. This mirrors dim_ncaaf_team's deliberate departure from MLB's timestamp SCD.
--
-- ⭐ POINT-IN-TIME LOOKUP — how a downstream model must resolve a team:
--     join dim_ncaab_team d
--       on d.team_id = f.team_id
--      and f.season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
--
-- ⚠️ MEMBERSHIP IS READ FROM BOTH SIDES OF THE SCHEDULE. A team's conference id appears as
-- `home_conference_id` when it hosts and `away_conference_id` when it travels; reading only
-- the home side would drop every team in a season it happened never to host in, and would
-- bias toward teams with home-heavy schedules. The per-season mode is taken over both sides
-- because a handful of rows carry a stale or event-specific id (neutral-site tournaments),
-- and a single odd row must not open a spurious SCD version.
{{ config(materialized='table') }}

with sides as (
    select season, home_team_id as team_id, home_team as team,
           home_conference_id as conference_id
    from {{ ref('stg_ncaab_schedule') }}
    union all
    select season, away_team_id, away_team, away_conference_id
    from {{ ref('stg_ncaab_schedule') }}
),

-- one (team, season) row, conference by MODE over that team's games in that season.
-- The >= 5 floor keeps a D-II opponent that played two guarantee games out of the D-I
-- dimension; it is a universe filter, not a data-quality fudge.
team_season as (
    select
        team_id,
        season,
        any_value(team)        as team,
        mode(conference_id)    as conference_id,
        count(*)               as games
    from sides
    where team_id is not null and conference_id is not null
    group by team_id, season
    having count(*) >= 5
),

max_season as (select max(season) as max_season from team_season),

hashed as (
    select *,
           md5(concat_ws('|', coalesce(team, ''), coalesce(conference_id::varchar, '')))
               as record_hash
    from team_season
),

marked as (
    select *,
           lag(record_hash) over (partition by team_id order by season) as prev_hash,
           lag(season)      over (partition by team_id order by season) as prev_season
    from hashed
),

versioned as (
    select *,
           sum(case
                   when prev_hash is null          then 1   -- first observation
                   when record_hash <> prev_hash   then 1   -- payload changed
                   when season <> prev_season + 1  then 1   -- gap (left D-I and returned)
                   else 0
               end) over (partition by team_id order by season
                          rows between unbounded preceding and current row) as version_number
    from marked
),

collapsed as (
    select
        team_id,
        version_number,
        any_value(team)        as team,
        any_value(conference_id) as conference_id,
        min(season)            as valid_from_season,
        max(season)            as valid_to_season,
        sum(games)             as games_in_version
    from versioned
    group by team_id, version_number
)

select
    'ncaab'                                                   as sport,
    c.team_id,
    c.version_number,
    c.team,
    c.conference_id,
    c.valid_from_season,
    c.valid_to_season,
    (c.valid_to_season = m.max_season)                        as is_current,
    c.games_in_version,
    -- how many DISTINCT versions this team has — a realignment counter that makes the movers
    -- queryable without re-deriving the SCD.
    count(*) over (partition by c.team_id)                    as n_versions
from collapsed c
cross join max_season m

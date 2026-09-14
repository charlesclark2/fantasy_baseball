-- The SCD-2 invariant that everything downstream silently depends on: a team has EXACTLY ONE
-- version covering any given season.
--
-- ⭐ WHY THIS TEST AND NOT A ROW-COUNT CHECK. Every point-in-time join in the vertical is
--     ... between d.valid_from_season and coalesce(d.valid_to_season, 9999)
-- so overlapping versions do not error — they FAN OUT, duplicating a team's games and
-- double-counting it in every conference rollup. The failure is silent and it is upstream of
-- the whole model, which is exactly the shape that must be asserted at the dimension rather
-- than discovered as a strange number in a mart.
--
-- Returns offending (team_id, season) rows; dbt fails the test when any row comes back.
with spans as (
    select team_id, valid_from_season, valid_to_season
    from {{ ref('dim_ncaab_team') }}
),
seasons as (
    select distinct season from {{ ref('stg_ncaab_schedule') }}
)
select
    s.team_id,
    y.season,
    count(*) as versions_covering_season
from spans s
join seasons y
  on y.season between s.valid_from_season and coalesce(s.valid_to_season, 9999)
group by s.team_id, y.season
having count(*) > 1

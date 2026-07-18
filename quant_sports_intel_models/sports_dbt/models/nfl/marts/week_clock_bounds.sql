-- week_clock_bounds — per (season, week) ET window (N0.3 port of jaffle `week_clock_bounds`).
--
-- The league-week clock without the team fan-out (team_week_calendar carries the same bounds
-- per team). Kept as a faithful IP port; a thin reference spine for week-grain joins.
-- Snowflake `dateadd` → DuckDB interval math. ⭐ sport-tagged.
with sched as (
    select season, week, game_datetime as kickoff_et
    from {{ ref('stg_nfl_schedules') }}
),
week_clock as (
    select season, week, min(kickoff_et) as min_kickoff_et
    from sched
    group by season, week
),
bounds_et as (
    select
        season,
        week,
        date_trunc('week', min_kickoff_et) + interval '1 day' as week_start_et,
        date_trunc('week', min_kickoff_et) + interval '8 day' as next_week_start_et
    from week_clock
)
select
    'nfl'                                             as sport,
    season,
    week,
    week_start_et,
    next_week_start_et - interval '1 second'          as week_end_et
from bounds_et

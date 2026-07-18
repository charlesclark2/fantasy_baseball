-- team_week_calendar — the (season, week, team) spine with byes (N0.3 port of jaffle
-- `team_week_calendar`). One row per team per week — including BYE weeks (no game) — with the
-- ET week window [Tue 00:00 → next Tue 00:00). The point-in-time backbone: fct_player_week
-- joins the SCD-2 role as-of `week_start_et`, so a week's row can only carry that-week state
-- (leakage-safe by construction). Snowflake `dateadd` → DuckDB interval math. ⭐ sport-tagged.
with stg_schedules as (
    select * from {{ ref('stg_nfl_schedules') }}
),
game_rows as (
    select season, week, home_team as team_id, away_team as opponent_id, game_datetime as game_kickoff_et
    from stg_schedules
    union all
    select season, week, away_team as team_id, home_team as opponent_id, game_datetime as game_kickoff_et
    from stg_schedules
),
-- League week bounds: Tue 00:00 ET → next Tue 00:00 ET per (season, week).
-- DuckDB date_trunc('week') truncates to Monday → +1 day = Tuesday (matches the old intent).
week_bounds as (
    select
        season,
        week,
        date_trunc('week', min(game_kickoff_et)) + interval '1 day' as week_start_et,
        date_trunc('week', min(game_kickoff_et)) + interval '8 day' as next_week_start_et
    from game_rows
    group by 1, 2
),
all_weeks as (
    select distinct season, week from stg_schedules
),
all_teams as (
    select distinct team_id from (
        select home_team as team_id from stg_schedules
        union
        select away_team as team_id from stg_schedules
    )
),
calendar_base as (
    select w.season, w.week, t.team_id
    from all_weeks w
    cross join all_teams t
),
joined as (
    select cb.season, cb.week, cb.team_id, gr.opponent_id, gr.game_kickoff_et
    from calendar_base cb
    left join game_rows gr
        on gr.season = cb.season and gr.week = cb.week and gr.team_id = cb.team_id
),
with_bounds as (
    select
        j.season, j.week, j.team_id, j.opponent_id, j.game_kickoff_et,
        (j.game_kickoff_et is null) as is_bye,
        b.week_start_et, b.next_week_start_et
    from joined j
    join week_bounds b using (season, week)
)
select
    'nfl'                                             as sport,
    season,
    week,
    team_id,
    opponent_id,
    is_bye,
    game_kickoff_et,
    week_start_et,
    next_week_start_et - interval '1 second'          as week_end_et
from with_bounds
order by season, week, team_id

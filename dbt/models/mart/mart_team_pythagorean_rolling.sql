-- =============================================================================
-- mart_team_pythagorean_rolling.sql
-- Card 8.X — Pythagorean Residual Features.
--
-- Grain: one row per team × game_pk (regular season only).
--
-- Per (team, game_pk) we compute pre-game trailing 30-day actual win pct,
-- pythagorean win expectation, and the residual (actual − expected). Joe Peta
-- (Trading Bases) and the broader sabermetric literature treat this residual
-- as the strongest single regression-to-mean signal in baseball.
--
-- LEAKAGE GUARD: the rolling window upper bound is `interval '1 day' preceding`
-- so the row's own game day is excluded. Doubleheaders inherit the same
-- pre-game window — both halves see identical rolling stats.
--
-- RELIABILITY GATE: rolling outputs are NULL when fewer than 10 games occurred
-- in the trailing 30-day window (early-season noise floor; matches the gate
-- used by mart_team_season_record.pythagorean_win_exp).
-- =============================================================================

{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

-- E11.1-W5 dual-branch lakehouse model (was incremental). DuckDB branch reads the
-- migrated mart_game_results + the ref_teams seed (registered as DuckDB views);
-- Snowflake branch is a thin view over the lakehouse_ext external table. The
-- `ref_teams` CTE is renamed `team_ref` to avoid colliding with the base ref_teams
-- view name in DuckDB. game_date::date already in team_games (mart_game_results is
-- DATE; the cast is a harmless no-op). Full rebuild — the incremental WHERE arms are
-- dropped.
{% if target.name == 'duckdb' %}

with

game_results as (
    select * from mart_game_results
    where game_type = 'R'
      and home_team_won is not null
),

team_ref as (
    select * from ref_teams
    where not is_legacy_abbrev
),

-- Expand to one row per (team, game_pk) — both home and away perspectives.
team_games as (
    select
        ht.team_id,
        gr.home_team               as team_abbrev,
        gr.game_pk,
        gr.game_date::date         as game_date,
        gr.game_year,
        gr.home_team_won           as is_win,
        gr.home_final_score        as runs_scored,
        gr.away_final_score        as runs_allowed
    from game_results gr
    inner join team_ref ht on gr.home_team = ht.team_abbrev

    union all

    select
        at_.team_id,
        gr.away_team               as team_abbrev,
        gr.game_pk,
        gr.game_date::date         as game_date,
        gr.game_year,
        (not gr.home_team_won)     as is_win,
        gr.away_final_score        as runs_scored,
        gr.home_final_score        as runs_allowed
    from game_results gr
    inner join team_ref at_ on gr.away_team = at_.team_abbrev
),

-- Aggregate to the calendar-date level (doubleheader-safe). Both halves of a
-- doubleheader contribute to the daily totals once but receive identical
-- pre-game rolling values when joined back below.
team_daily as (
    select
        team_id,
        team_abbrev,
        game_year,
        game_date,
        sum(case when is_win     then 1 else 0 end)::integer as wins_today,
        sum(case when not is_win then 1 else 0 end)::integer as losses_today,
        count(*)::integer                                    as games_today,
        sum(runs_scored)::integer                            as runs_scored_today,
        sum(runs_allowed)::integer                           as runs_allowed_today
    from team_games
    group by team_id, team_abbrev, game_year, game_date
),

-- Rolling 30-day window strictly before each calendar date.
-- RANGE-based bounds operate over date values, so non-game days are skipped
-- (no contribution) while every game day in the prior 30 calendar days
-- contributes once. Matches the Phase 7 rolling-stats pattern.
rolling as (
    select
        team_id,
        team_abbrev,
        game_year,
        game_date,
        sum(wins_today) over (
            partition by team_id
            order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                as wins_30d,
        sum(losses_today) over (
            partition by team_id
            order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                as losses_30d,
        sum(games_today) over (
            partition by team_id
            order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                as games_30d,
        sum(runs_scored_today) over (
            partition by team_id
            order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                as runs_scored_30d,
        sum(runs_allowed_today) over (
            partition by team_id
            order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                as runs_allowed_30d
    from team_daily
),

-- Map back to the team × game_pk grain. Both legs of a doubleheader join to
-- the same daily rolling row (calendar date is the join key) and inherit the
-- same pre-game stats — correct, since the window is `< game_date` and both
-- halves are played on the same date.
final as (
    select
        tg.team_id,
        tg.team_abbrev,
        tg.game_pk,
        tg.game_date,
        tg.game_year,

        case when r.games_30d >= 10 then r.games_30d else null end
                                          as games_30d,

        case when r.games_30d >= 10
             then round(
                 r.wins_30d::numeric / nullif(r.games_30d, 0),
                 4
             )
             else null
        end                              as actual_win_pct_30d,

        case when r.games_30d >= 10
             then round(
                 pow(r.runs_scored_30d::float, 1.83)
                 / nullif(
                     pow(r.runs_scored_30d::float, 1.83)
                   + pow(r.runs_allowed_30d::float, 1.83),
                     0
                 ),
                 4
             )
             else null
        end                              as pythagorean_win_exp_30d,

        case when r.games_30d >= 10
             then round(
                 (r.wins_30d::numeric / nullif(r.games_30d, 0))
                 - (
                     pow(r.runs_scored_30d::float, 1.83)
                     / nullif(
                         pow(r.runs_scored_30d::float, 1.83)
                       + pow(r.runs_allowed_30d::float, 1.83),
                         0
                     )
                 ),
                 4
             )
             else null
        end                              as pythagorean_residual_30d

    from team_games tg
    left join rolling r
        on  r.team_id   = tg.team_id
        and r.game_date = tg.game_date
)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_team_pythagorean_rolling

{% endif %}

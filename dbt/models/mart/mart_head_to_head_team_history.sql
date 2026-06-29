-- =============================================================================
-- mart_head_to_head_team_history.sql
-- Grain: team_a × team_b × game_year (season).
--        team_a is always alphabetically less than team_b, so each franchise
--        pair appears exactly once per season row regardless of home/away.
--        Team abbreviations are normalized to canonical form (e.g. OAK → ATH)
--        so franchise history is continuous across rebrands.
-- Purpose: Head-to-head regular-season record, run context, and cumulative
--          franchise history for every team pairing. Captures persistent
--          matchup asymmetry (e.g. contact-heavy lineups vs. extreme-strikeout
--          rotations) that is not explained by each team's overall record alone.
-- Metrics: Season-level (single season) and historical (cumulative through
--          and including the given season).
-- Join keys: team_a, team_b, game_year
-- Source: mart_game_results (regular season only, game_type = 'R')
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model. DuckDB branch reads the migrated
-- mart_game_results + the ref_teams seed (registered as DuckDB views); Snowflake
-- branch is a thin view over the lakehouse_ext external table. The `ref_teams` CTE
-- is renamed `team_ref` to avoid colliding with the base ref_teams view name in
-- DuckDB. Aggregates by game_year only — no game_date cast needed.

{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

games as (

    select * from mart_game_results
    where game_type = 'R'

),

team_ref as (

    select team_abbrev, canonical_abbrev
    from ref_teams

),

-- Normalize abbreviations to canonical form (OAK → ATH) so franchise history
-- is continuous across rebrands. Coalesce falls back to raw abbreviation if
-- a team is unexpectedly absent from the seed.
games_normalized as (

    select
        g.game_pk,
        g.game_date,
        g.game_year,
        coalesce(ht.canonical_abbrev,  g.home_team)  as home_team,
        coalesce(at_.canonical_abbrev, g.away_team)  as away_team,
        g.home_final_score,
        g.away_final_score,
        g.home_team_won,
        g.is_extra_innings,
        g.is_tie

    from games         g
    left join team_ref ht  on g.home_team = ht.team_abbrev
    left join team_ref at_ on g.away_team = at_.team_abbrev

),

-- Establish canonical pair ordering (team_a < team_b alphabetically).
-- All metrics are expressed from team_a's perspective so the model can be
-- read in a single direction.
game_pairs as (

    select
        game_pk,
        game_date,
        game_year,

        least(home_team, away_team)                                 as team_a,
        greatest(home_team, away_team)                              as team_b,

        -- Runs scored by each team, keyed to canonical ordering
        case
            when home_team < away_team then home_final_score
            else away_final_score
        end                                                         as team_a_runs,

        case
            when home_team < away_team then away_final_score
            else home_final_score
        end                                                         as team_b_runs,

        -- team_a_won: true=team_a won, false=team_b won, null=tie.
        -- After the is_tie guard, home_team_won is guaranteed non-null.
        case
            when is_tie                then null
            when home_team < away_team then home_team_won           -- team_a is home
            else                            not home_team_won       -- team_a is away
        end                                                         as team_a_won,

        is_extra_innings,
        is_tie

    from games_normalized
    where home_team != away_team   -- guard: teams must differ after normalization

),

-- Aggregate to season level: one row per (team_a, team_b, game_year).
-- Raw totals are retained alongside rates so the historical window CTEs can
-- sum them without reintroducing rounding errors from averaging averages.
season_stats as (

    select
        team_a,
        team_b,
        game_year,

        count(*)                                                              as games_played,
        sum(case when team_a_won = true  then 1 else 0 end)                  as team_a_wins,
        sum(case when team_a_won = false then 1 else 0 end)                  as team_b_wins,
        sum(case when is_tie             then 1 else 0 end)                  as ties,

        -- raw totals for historical window aggregation
        sum(team_a_runs - team_b_runs)                                       as total_run_diff,
        sum(team_a_runs)                                                     as total_team_a_runs,
        sum(team_b_runs)                                                     as total_team_b_runs,
        sum(team_a_runs + team_b_runs)                                       as total_combined_runs,

        -- season-level rates (from team_a's perspective)
        round(avg(team_a_runs - team_b_runs), 3)                             as avg_run_differential,
        round(avg(team_a_runs), 3)                                           as avg_team_a_runs,
        round(avg(team_b_runs), 3)                                           as avg_team_b_runs,
        round(avg(team_a_runs + team_b_runs), 3)                             as avg_total_runs,

        round(
            sum(case when team_a_won = true then 1 else 0 end)::numeric
            / nullif(count(*) - sum(case when is_tie then 1 else 0 end), 0)
        , 3)                                                                 as team_a_win_pct,

        sum(case when is_extra_innings then 1 else 0 end)                    as extra_innings_games,
        round(
            sum(case when is_extra_innings then 1 else 0 end)::numeric
            / count(*)
        , 3)                                                                 as extra_innings_pct,

        -- null when the season series ended tied
        case
            when sum(case when team_a_won = true  then 1 else 0 end)
                 > sum(case when team_a_won = false then 1 else 0 end) then team_a
            when sum(case when team_a_won = false then 1 else 0 end)
                 > sum(case when team_a_won = true  then 1 else 0 end) then team_b
            else null
        end                                                                  as season_series_winner

    from game_pairs
    group by team_a, team_b, game_year

)

select

    -- ── Grain ────────────────────────────────────────────────────────────────
    team_a,
    team_b,
    game_year,

    -- ── Season metrics ───────────────────────────────────────────────────────
    games_played,
    team_a_wins,
    team_b_wins,
    ties,
    team_a_win_pct,
    season_series_winner,
    avg_run_differential,
    avg_team_a_runs,
    avg_team_b_runs,
    avg_total_runs,
    extra_innings_games,
    extra_innings_pct,

    -- ── Historical cumulative through and including this season ──────────────
    -- Snowflake does not support named WINDOW clauses; all OVER specs are inlined.
    sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row)   as all_time_games_played,
    sum(team_a_wins)  over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row)   as all_time_team_a_wins,
    sum(team_b_wins)  over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row)   as all_time_team_b_wins,
    sum(ties)         over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row)   as all_time_ties,

    round(
        (sum(team_a_wins) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row))::numeric
        / nullif(
            sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row)
            - sum(ties)       over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row),
            0
          )
    , 3)                                                                         as all_time_team_a_win_pct,

    round(
        (sum(total_run_diff) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row))::numeric
        / nullif(sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row), 0)
    , 3)                                                                         as all_time_avg_run_differential,

    round(
        (sum(total_team_a_runs) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row))::numeric
        / nullif(sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row), 0)
    , 3)                                                                         as all_time_avg_team_a_runs,

    round(
        (sum(total_team_b_runs) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row))::numeric
        / nullif(sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row), 0)
    , 3)                                                                         as all_time_avg_team_b_runs,

    round(
        (sum(total_combined_runs) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row))::numeric
        / nullif(sum(games_played) over (partition by team_a, team_b order by game_year rows between unbounded preceding and current row), 0)
    , 3)                                                                         as all_time_avg_total_runs

from season_stats
order by team_a, team_b, game_year

{% else %}

select * from baseball_data.lakehouse_ext.mart_head_to_head_team_history

{% endif %}

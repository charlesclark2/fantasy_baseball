-- =============================================================================
-- mart_team_season_record.sql
-- Grain: one row per team per calendar date within the regular season
-- Type: Type-2 Slowly Changing Dimension
-- Purpose: A team's win-loss record as of every calendar day in the regular
--          season, with SCD2 columns tracking when each record state became
--          effective and when it expired. Covers every day from the first
--          game of the season to the last, filling forward on non-game days.
--          Scope: Regular season (game_type = 'R') only; ties excluded.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with

game_results as (

    select * from {{ ref('mart_game_results') }}
    -- Regular season only; exclude ties (no W/L credited)
    where game_type = 'R'
      and home_team_won is not null

),

-- One canonical row per team (no legacy abbreviation aliases)
ref_teams as (

    select * from {{ ref('ref_teams') }}
    where not is_legacy_abbrev

),

-- ── Step 1: Expand to one row per team per game ───────────────────────────────
-- Union home and away perspectives so each team has one row per game.

team_games as (

    select
        ht.team_id,
        gr.home_team               as team_abbrev,
        gr.game_pk,
        gr.game_date,
        gr.game_year,
        gr.home_team_won           as is_win,
        gr.home_final_score        as runs_scored,
        gr.away_final_score        as runs_allowed
    from game_results gr
    inner join ref_teams ht on gr.home_team = ht.team_abbrev

    union all

    select
        at.team_id,
        gr.away_team               as team_abbrev,
        gr.game_pk,
        gr.game_date,
        gr.game_year,
        (not gr.home_team_won)     as is_win,
        gr.away_final_score        as runs_scored,
        gr.home_final_score        as runs_allowed
    from game_results gr
    inner join ref_teams at on gr.away_team = at.team_abbrev

),

-- ── Step 2: Cumulative W/L and streak after each game ────────────────────────
-- Order by game_date + game_pk so doubleheaders are sequenced correctly.

running_totals as (

    select
        team_id,
        team_abbrev,
        game_pk,
        game_date,
        game_year,
        is_win,

        sum(case when is_win     then 1 else 0 end) over (
            partition by team_id, game_year
            order by game_date, game_pk
            rows between unbounded preceding and current row
        )                          as wins,

        sum(case when not is_win then 1 else 0 end) over (
            partition by team_id, game_year
            order by game_date, game_pk
            rows between unbounded preceding and current row
        )                          as losses,

        sum(runs_scored) over (
            partition by team_id, game_year
            order by game_date, game_pk
            rows between unbounded preceding and current row
        )                          as runs_scored_ytd,

        sum(runs_allowed) over (
            partition by team_id, game_year
            order by game_date, game_pk
            rows between unbounded preceding and current row
        )                          as runs_allowed_ytd,

        -- Streak isolation: the group increments every time is_win flips,
        -- allowing COUNT to give the current consecutive-game streak length.
        row_number() over (
            partition by team_id, game_year
            order by game_date, game_pk
        )
        - row_number() over (
            partition by team_id, game_year, is_win
            order by game_date, game_pk
        )                          as streak_group

    from team_games

),

streak_added as (

    select
        *,
        count(*) over (
            partition by team_id, game_year, streak_group
            order by game_date, game_pk
            rows between unbounded preceding and current row
        )                          as streak_length,

        case when is_win then 'W' else 'L' end as streak_direction

    from running_totals

),

-- ── Step 3: One row per team per game date ────────────────────────────────────
-- For doubleheaders, keep the record after the final game of the day (rn = 1).

daily_ranked as (

    select
        team_id,
        team_abbrev,
        game_date,
        game_year,
        wins,
        losses,
        wins + losses              as games_played,
        streak_direction,
        streak_length,
        runs_scored_ytd,
        runs_allowed_ytd,
        row_number() over (
            partition by team_id, game_date, game_year
            order by game_pk desc
        )                          as rn

    from streak_added

),

game_day_records as (

    select
        team_id,
        team_abbrev,
        game_date,
        game_year,
        wins,
        losses,
        games_played,
        streak_direction,
        streak_length,
        runs_scored_ytd,
        runs_allowed_ytd
    from daily_ranked
    where rn = 1

),

-- ── Step 4: SCD2 expiration dates ─────────────────────────────────────────────
-- Record expires the day before the next game changes it.
-- The last game of the season has next_game_date = null → is_current = true.

game_day_with_expiry as (

    select
        *,
        game_date                  as record_effective_date,
        lead(game_date) over (
            partition by team_id, game_year
            order by game_date
        )                          as next_game_date
    from game_day_records

),

-- ── Step 5: Date spine covering the full Statcast era ─────────────────────────

date_spine as (

    {{ dbt_utils.date_spine(
        datepart   = "day",
        start_date = "cast('2015-01-01' as date)",
        end_date   = "cast('2030-12-31' as date)"
    ) }}

),

-- ── Step 6: Expand each game record across all calendar days it covers ────────
-- Each game record is valid from game_date up to (but not including) the next
-- game date, and no later than the last game of the season.

season_bounds as (

    select
        team_id,
        game_year,
        min(game_date)             as season_start,
        max(game_date)             as season_end
    from game_day_records
    group by team_id, game_year

),

expanded as (

    select
        gde.team_id,
        gde.team_abbrev,
        gde.game_year,
        ds.date_day                as record_date,
        gde.wins,
        gde.losses,
        gde.games_played,
        round(
            gde.wins::numeric / nullif(gde.games_played, 0),
            3
        )                          as win_pct,
        gde.streak_direction,
        gde.streak_length,
        gde.runs_scored_ytd,
        gde.runs_allowed_ytd,
        gde.record_effective_date,
        case
            when gde.next_game_date is null then null
            else gde.next_game_date - 1
        end                        as record_expiration_date,
        (gde.next_game_date is null)::boolean as is_current
    from game_day_with_expiry gde
    inner join season_bounds sb
        on gde.team_id = sb.team_id
       and gde.game_year = sb.game_year
    inner join date_spine ds
        on ds.date_day >= gde.game_date
       and ds.date_day <= sb.season_end
       and (gde.next_game_date is null or ds.date_day < gde.next_game_date)

),

-- ── Step 7: Enrich with team metadata and division standings ──────────────────

with_team_info as (

    select
        e.*,
        rt.team_name,
        rt.league,
        rt.division,
        rt.league_division
    from expanded e
    inner join ref_teams rt on e.team_id = rt.team_id

),

-- ── Step 8: Games back from division leader ───────────────────────────────────
-- Games Back = ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2
-- Division leader shows 0.0 GB. Computed fresh each day using window functions.

final as (

    select
        team_id,
        team_abbrev,
        team_name,
        league,
        division,
        league_division,
        game_year,
        record_date,

        -- ── Record ───────────────────────────────────────────────────────────────
        wins,
        losses,
        games_played,
        win_pct,
        runs_scored_ytd,
        runs_allowed_ytd,
        case
            when games_played >= 10
            then round(
                pow(runs_scored_ytd::float, 1.83)
                / nullif(
                    pow(runs_scored_ytd::float, 1.83)
                  + pow(runs_allowed_ytd::float, 1.83),
                    0
                ),
                4
            )
            else null
        end                        as pythagorean_win_exp,

        -- Pythagorean residual = actual win pct minus pythagorean expectation.
        -- Positive = team is winning more than run differential implies (sequencing
        -- "luck"); negative = team is winning less than expected. Cumulative through
        -- end-of-day on this record_date — leakage guard at consuming layer pulls
        -- record_date = dateadd('day', -1, game_date). Card 8.X.
        case
            when games_played >= 10
            then round(
                (wins::numeric / nullif(games_played, 0))
                - (pow(runs_scored_ytd::float, 1.83)
                   / nullif(
                       pow(runs_scored_ytd::float, 1.83)
                     + pow(runs_allowed_ytd::float, 1.83),
                       0
                     )),
                4
            )
            else null
        end                        as pythagorean_residual_season,

        -- ── Division standing ────────────────────────────────────────────────────
        (
            (max(wins)   over (partition by division, game_year, record_date) - wins)
          + (losses - min(losses) over (partition by division, game_year, record_date))
        ) / 2.0                    as games_back,

        (wins = max(wins) over (partition by division, game_year, record_date)
         and losses = min(losses) over (partition by division, game_year, record_date)
        )::boolean                 as is_division_leader,

        -- ── Streak ───────────────────────────────────────────────────────────────
        streak_direction,
        streak_length,

        -- ── SCD2 metadata ────────────────────────────────────────────────────────
        record_effective_date,
            -- Date this W-L record was first achieved (date of the last game that changed it)
        record_expiration_date,
            -- Last calendar day this record was valid; null = still current
        is_current
            -- True for the most recent record of each team-season

    from with_team_info

)

select * from final

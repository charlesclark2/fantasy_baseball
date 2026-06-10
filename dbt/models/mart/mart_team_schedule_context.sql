-- =============================================================================
-- mart_team_schedule_context.sql
-- Grain: one row per team_abbrev × game_pk (regular season only)
-- Purpose: Schedule fatigue context features entering each game: days rest,
--          recent game frequency, home/away streak length, and timezone travel
--          signal. Designed as a direct join target for
--          feature_pregame_team_features on team_abbrev + game_pk.
--          No leakage risk: all values are computed from games strictly before
--          the current game_date.
-- =============================================================================

{{ config(materialized='table') }}

with

-- ── Step 1: One row per team per game ─────────────────────────────────────────

team_spine as (

    -- A1.11 — spine on mart_game_spine so today's scheduled games get a row.
    -- All fields below are window-function derived (lag/count over '1 day
    -- preceding'), so today's rest/streaks compute correctly from prior games and
    -- the NULL scores on a scheduled row are never read. Historical rows unchanged.
    select
        game_pk,
        game_date::date         as game_date,
        game_year::integer      as game_year,
        home_team               as team_abbrev,
        'home'                  as side,
        venue_id
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'

    union all

    select
        game_pk,
        game_date::date,
        game_year::integer,
        away_team,
        'away',
        venue_id
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'

),

-- ── Step 2: Attach timezone from most recent venue record ─────────────────────

venue_tz as (

    select
        venue_id,
        timezone_id
    from {{ ref('stg_statsapi_venues') }}
    qualify row_number() over (partition by venue_id order by ingest_date desc) = 1

),

team_games as (

    select
        ts.game_pk,
        ts.game_date,
        ts.game_year,
        ts.team_abbrev,
        ts.side,
        v.timezone_id
    from team_spine ts
    left join venue_tz v on v.venue_id = ts.venue_id

),

-- ── Step 3: Rest, game frequency, and travel signal ───────────────────────────

rest_and_frequency as (

    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,
        side,
        timezone_id,

        -- Days since this team's last game; null on first game of each season
        datediff(
            'day',
            lag(game_date) over (
                partition by team_abbrev, game_year
                order by game_date, game_pk
            ),
            game_date
        )                               as days_rest,

        -- Games played in the prior 7 and 14 calendar days (excludes today)
        count(*) over (
            partition by team_abbrev
            order by game_date
            range between interval '7 days' preceding and interval '1 day' preceding
        )                               as games_last_7d,

        count(*) over (
            partition by team_abbrev
            order by game_date
            range between interval '14 days' preceding and interval '1 day' preceding
        )                               as games_last_14d,

        -- Previous game's timezone (for travel signal)
        lag(timezone_id) over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )                               as prev_timezone_id

    from team_games

),

-- ── Step 4: Home/away streak grouping ─────────────────────────────────────────
-- streak_group increments each time the team switches between home and away,
-- matching the pattern in mart_team_season_record. row_number within
-- (team, year, streak_group) gives the length of the current home or road stand.

streak_grouped as (

    select
        *,
        row_number() over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )
        - row_number() over (
            partition by team_abbrev, game_year, side
            order by game_date, game_pk
        )                               as streak_group

    from rest_and_frequency

),

final as (

    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,
        side,

        -- ── Rest and schedule compression ─────────────────────────────────────
        days_rest,
            -- Null for the first game of each season; 0 is valid for game 2
            -- of a doubleheader.
        games_last_7d,
        games_last_14d,

        -- ── Home/away context ─────────────────────────────────────────────────
        (side = 'home')::boolean        as is_home_game,

        case when side = 'home'
            then row_number() over (
                     partition by team_abbrev, game_year, streak_group
                     order by game_date, game_pk
                 )
        end                             as consecutive_home_games,
            -- Length of current home stand, including this game. Null when away.

        case when side = 'away'
            then row_number() over (
                     partition by team_abbrev, game_year, streak_group
                     order by game_date, game_pk
                 )
        end                             as consecutive_away_games,
            -- Length of current road trip, including this game. Null when home.

        -- ── Travel signal ─────────────────────────────────────────────────────
        coalesce(
            (prev_timezone_id is not null
             and prev_timezone_id != timezone_id)::boolean,
            false
        )                               as tz_changed_from_last_game
            -- True when team traveled across timezone boundaries since last game.
            -- False on Opening Day and when venue data is unavailable.

    from streak_grouped

)

select * from final

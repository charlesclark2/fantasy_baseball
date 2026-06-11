{{
    config(
        materialized='table'
    )
}}

-- Team defensive quality composite signal for pregame feature store.
-- Grain: game_pk × side  (one row per game-side — the FIELDING team perspective)
--
-- Signal composition (Story 27.4):
--   1. Prior-season OAA from Baseball Savant (leakage-safe: known before first pitch)
--   2. Prior-season team mean sprint speed from Statcast (EB-smoothed toward league mean)
--   3. Per-season z-scored composite: defense_quality_mu = normalized(oaa_z + sprint_z)
--
-- Leakage guard: only game_year-1 data joins for both components.  Within-season
-- OAA totals are excluded — they include post-game information.
--
-- EB smoothing for sprint speed: alpha = n_players / (n_players + EB_K), EB_K=8.
-- Teams with few measured players are shrunk toward the league mean.
-- NULL imputation: 0.0 (league average z-score) for any missing component.
--
-- Shared signal for Epic 27 (totals) and Epic 28 (H2H) — see R33.

with oaa_season as (
    -- Deduplicate OAA to latest loaded snapshot per team × year
    select
        team_abbrev,
        game_year,
        oaa
    from {{ source('external', 'oaa_team_season_raw') }}
    qualify row_number() over (
        partition by team_abbrev, game_year
        order by loaded_at desc nulls last
    ) = 1
),

oaa_league_stats as (
    -- Per-season league OAA statistics for z-score normalization
    select
        game_year,
        avg(oaa)             as league_oaa_mean,
        nullif(stddev(oaa), 0) as league_oaa_std
    from oaa_season
    group by game_year
),

sprint_player as (
    -- Player-level sprint speed, latest snapshot per player × season
    -- competitive_runs > 0 guard filters placeholder rows with no measured runs
    select
        team_abbrev,
        season as game_year,
        sprint_speed_fts
    from {{ ref('stg_batter_sprint_speed') }}
    where sprint_speed_fts is not null
      and competitive_runs > 0
),

sprint_league_stats as (
    -- Per-season league sprint speed statistics (for EB prior + z-scoring)
    select
        game_year,
        avg(sprint_speed_fts)               as league_sprint_mean,
        nullif(stddev(sprint_speed_fts), 0) as league_sprint_std
    from sprint_player
    group by game_year
),

sprint_team_raw as (
    -- Team × season mean sprint speed (raw, before EB smoothing)
    select
        team_abbrev,
        game_year,
        avg(sprint_speed_fts) as team_sprint_raw,
        count(*)              as n_sprint_players
    from sprint_player
    group by team_abbrev, game_year
),

sprint_team_eb as (
    -- EB-smoothed team sprint speed.  K=8 pseudo-observations from the league
    -- prior: teams with <8 measured players are substantially shrunk.
    select
        t.team_abbrev,
        t.game_year,
        t.team_sprint_raw,
        t.n_sprint_players,
        l.league_sprint_mean,
        l.league_sprint_std,
        -- alpha = n / (n + K); K=8
        (t.n_sprint_players::float / (t.n_sprint_players + 8.0)) * t.team_sprint_raw
            + (8.0 / (t.n_sprint_players + 8.0)) * l.league_sprint_mean
                                              as team_sprint_eb
    from sprint_team_raw t
    inner join sprint_league_stats l on l.game_year = t.game_year
),

games as (
    -- Game spine: one row per game-side (fielding-team perspective)
    select game_pk, game_date, game_year, home_team as team_abbrev, 'home' as side
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'

    union all

    select game_pk, game_date, game_year, away_team as team_abbrev, 'away' as side
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'
),

joined as (
    select
        g.game_pk,
        g.game_date,
        g.game_year,
        g.team_abbrev,
        g.side,

        -- Prior-season OAA (fully leakage-safe)
        o.oaa                       as oaa_prior_season,
        ol.league_oaa_mean,
        ol.league_oaa_std,

        -- Prior-season EB-smoothed sprint speed
        s.team_sprint_eb            as sprint_speed_prior_eb,
        s.team_sprint_raw           as sprint_speed_prior_raw,
        s.n_sprint_players,
        s.league_sprint_mean,
        s.league_sprint_std

    from games g

    left join oaa_season o
        on  o.team_abbrev = g.team_abbrev
        and o.game_year   = g.game_year - 1

    left join oaa_league_stats ol
        on  ol.game_year  = g.game_year - 1

    left join sprint_team_eb s
        on  s.team_abbrev = g.team_abbrev
        and s.game_year   = g.game_year - 1
),

z_scored as (
    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,
        side,
        oaa_prior_season,
        sprint_speed_prior_eb,
        sprint_speed_prior_raw,
        n_sprint_players,

        -- OAA z-score: positive = better fielding (more outs above average)
        case
            when oaa_prior_season is not null and league_oaa_std is not null
            then (oaa_prior_season - league_oaa_mean) / league_oaa_std
            else 0.0
        end as oaa_z,

        -- Sprint speed z-score: positive = faster roster (better range)
        case
            when sprint_speed_prior_eb is not null and league_sprint_std is not null
            then (sprint_speed_prior_eb - league_sprint_mean) / league_sprint_std
            else 0.0
        end as sprint_z,

        -- Component availability flags
        (oaa_prior_season is not null)    as oaa_available,
        (sprint_speed_prior_eb is not null) as sprint_available

    from joined
)

select
    game_pk,
    game_date,
    game_year,
    team_abbrev,
    side,
    oaa_prior_season,
    sprint_speed_prior_eb,
    sprint_speed_prior_raw,
    n_sprint_players,
    oaa_z,
    sprint_z,
    oaa_available,
    sprint_available,

    -- Composite defensive quality z-score.
    -- When both components are available: (oaa_z + sprint_z) / sqrt(2) → N(0,1)
    -- When only one is available: that component's z-score.
    -- When neither: 0.0 (imputed league average).
    -- Higher value = better team defense.
    case
        when oaa_available and sprint_available
        then (oaa_z + sprint_z) / sqrt(2.0)
        when oaa_available
        then oaa_z
        when sprint_available
        then sprint_z
        else 0.0
    end as defense_quality_mu

from z_scored

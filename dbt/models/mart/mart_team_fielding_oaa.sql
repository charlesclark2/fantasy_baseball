-- E11.1-W5 dual-branch lakehouse model (W4-deferred Group B). DuckDB branch reads the
-- oaa_team_season_raw S3 parquet (exported by scripts/export_w5_raw_to_s3.py) + the
-- Group-A mart_game_spine (registered as a DuckDB view); Snowflake branch is a thin view
-- over the lakehouse_ext external table. The FanGraphs OAA ingest KEEPS its Snowflake
-- write — this reads the one-time/opt-in S3 mirror. game_date is a passthrough from the
-- spine (TIMESTAMP) — no RANGE-interval window, so no cast needed.
{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

-- Team defensive quality per game, sourced from FanGraphs season-level OAA/DRS.
-- Grain: game_pk × team_abbrev (home and away rows per game).
--
-- LEAKAGE GUARD: only prior-season OAA is used as a pre-game feature.
-- Within-season OAA totals are available in the source table but cannot be used
-- directly because the season total includes post-game information. Prior-season
-- OAA is fully known before the first pitch.
--
-- Blended OAA: for Bayesian shrinkage during a new season, we keep the prior-season
-- value as the signal rather than attempting a weighted blend. This is appropriate
-- since FanGraphs season totals only update periodically, not daily.
--
-- Coverage: OAA is Statcast-era (2016+). Games before 2017 (first year where
-- 2016 prior-season OAA is available) will have NULL.

with oaa_raw as (
    select
        team_abbrev,
        game_year,
        oaa,
        drs,
        n_opportunities
    from read_parquet('{{ lakehouse_loc("oaa_team_season_raw") }}**/*.parquet', union_by_name=true)
    qualify row_number() over (
        partition by team_abbrev, game_year
        order by loaded_at desc nulls last
    ) = 1
),

games as (
    -- A1.11 — spine on mart_game_spine; only prior-season OAA (game_year-1) is
    -- joined as a feature, so today's scheduled row attaches the leakage-free
    -- prior-season value. Historical rows unchanged.
    select
        game_pk,
        game_date,
        game_year,
        home_team    as team_abbrev,
        'home'       as side
    from mart_game_spine
    where game_type = 'R'

    union all

    select
        game_pk,
        game_date,
        game_year,
        away_team    as team_abbrev,
        'away'       as side
    from mart_game_spine
    where game_type = 'R'
)

select
    g.game_pk,
    g.game_date,
    g.game_year,
    g.team_abbrev,
    g.side,

    -- Prior-season OAA: fully known before the season begins (leakage-free)
    prior.oaa                                       as team_oaa_prior_season,
    prior.drs                                       as team_drs_prior_season,

    -- Current-season OAA: included for monitoring only; NOT for use as a feature
    -- (season totals include post-game info — leakage if used mid-season)
    current_yr.oaa                                  as team_oaa_current_season,

    -- Blended: prior-season value, coalesced to 0 (league average) for games
    -- before OAA data begins (pre-2017) or expansion teams with no history
    coalesce(prior.oaa, 0)                          as team_oaa_blended

from games g
left join oaa_raw prior
    on  prior.team_abbrev = g.team_abbrev
    and prior.game_year   = g.game_year - 1
left join oaa_raw current_yr
    on  current_yr.team_abbrev = g.team_abbrev
    and current_yr.game_year   = g.game_year

{% else %}

select * from baseball_data.lakehouse_ext.mart_team_fielding_oaa

{% endif %}

-- =============================================================================
-- stg_actionnetwork_public_betting_snapshots.sql
-- Story 15.6 — all ingestion snapshots from public_betting_raw, normalized and
-- joined to the pregame game-feature spine for game_pk resolution.
--
-- Grain: one row per (game_pk, loaded_at) after dedup.
--
-- Coverage: 2026-05-07 onward (Epic T.3 raw-capture start date).
-- game_pk resolution uses feature_pregame_game_features (the canonical pregame
-- spine: regular-season games only, INCLUDES today's not-yet-completed games and
-- retains full history). Previously this joined mart_game_results, which only
-- contains COMPLETED games — so public betting for today's slate was silently
-- dropped until each game finished (the "Market Action" panel was blank pre-game,
-- which is exactly the window it serves). The pregame spine has no public-betting
-- dependency, so this join stays acyclic.
--
-- Record hash covers the 4 independent pct columns:
--   home_ml_money_pct, home_ml_ticket_pct, over_money_pct, over_ticket_pct
-- away_ml and under columns are near-complements (100 - home/over) and would
-- produce redundant change detection; sharp signals are derived from these four.
--
-- E11.1-W11 Tier-D lakehouse migration. The DuckDB branch reads the public_betting_raw S3 raw mirror
-- and joins feature_pregame_game_features (registered as a DuckDB VIEW over its W8b native parquet by
-- run_w1_lakehouse._build_w11d — referenced by BARE name, NOT a Jinja ref, because the stg-layout
-- extractor does not resolve Jinja refs and dbt-fusion would try to compile a bare ref() call even
-- inside a SQL comment). The Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table (rollback path). loaded_at = ingestion_timestamp via try_cast(... as
-- timestamp) — the INC-23 use-site cast for the SF-bridge(TIMESTAMP)↔live-writer(ISO VARCHAR) union
-- that union_by_name reconciles to VARCHAR (also the SCD-2 valid_from — must be a real timestamp for
-- the lag/lead ordering in feature_pregame_public_betting_status).

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11d_lakehouse']) }}

with source as (
    select
        game_date::date                                         as game_date,
        an_game_id::varchar                                     as an_game_id,
        case upper(home_team_abbr)
            when 'ARI' then 'AZ'
            else upper(home_team_abbr)
        end                                                     as home_team_norm,
        case upper(away_team_abbr)
            when 'ARI' then 'AZ'
            else upper(away_team_abbr)
        end                                                     as away_team_norm,
        try_cast(home_ml_money_pct as double)                   as home_ml_money_pct,
        try_cast(away_ml_money_pct as double)                   as away_ml_money_pct,
        try_cast(home_ml_ticket_pct as double)                  as home_ml_ticket_pct,
        try_cast(away_ml_ticket_pct as double)                  as away_ml_ticket_pct,
        try_cast(over_money_pct as double)                      as over_money_pct,
        try_cast(under_money_pct as double)                     as under_money_pct,
        try_cast(over_ticket_pct as double)                     as over_ticket_pct,
        try_cast(under_ticket_pct as double)                    as under_ticket_pct,
        (try_cast(home_ml_money_pct as double) - try_cast(home_ml_ticket_pct as double)) as ml_sharp_signal,
        (try_cast(over_money_pct as double)    - try_cast(over_ticket_pct as double))    as total_sharp_signal,
        try_cast(ingestion_timestamp as timestamp)              as loaded_at
    from read_parquet('{{ lakehouse_raw_loc("public_betting_raw") }}**/*.parquet', union_by_name=true)
),

with_game_pk as (
    select
        g.game_pk,
        s.an_game_id,
        s.home_ml_money_pct,
        s.away_ml_money_pct,
        s.home_ml_ticket_pct,
        s.away_ml_ticket_pct,
        s.over_money_pct,
        s.under_money_pct,
        s.over_ticket_pct,
        s.under_ticket_pct,
        s.ml_sharp_signal,
        s.total_sharp_signal,
        md5(
            coalesce(cast(s.home_ml_money_pct  as varchar), '') || '|' ||
            coalesce(cast(s.home_ml_ticket_pct as varchar), '') || '|' ||
            coalesce(cast(s.over_money_pct     as varchar), '') || '|' ||
            coalesce(cast(s.over_ticket_pct    as varchar), '')
        )                                                       as record_hash,
        s.loaded_at
    from source s
    -- Pregame spine (regular-season, includes today + full history) → resolves game_pk for
    -- not-yet-completed games. Registered as a DuckDB view by _build_w11d (BARE name — no Jinja ref).
    inner join feature_pregame_game_features g
        on  s.game_date      = g.game_date::date
        and s.home_team_norm = g.home_team
        and s.away_team_norm = g.away_team
)

select *
from with_game_pk
qualify row_number() over (
    partition by game_pk, loaded_at
    order by home_ml_money_pct nulls last
) = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_actionnetwork_public_betting_snapshots

{% endif %}

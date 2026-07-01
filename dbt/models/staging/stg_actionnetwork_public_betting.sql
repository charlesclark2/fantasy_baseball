-- =============================================================================
-- stg_actionnetwork_public_betting.sql
-- Card 8.R — normalize Action Network public-betting raw data.
-- Grain: one row per (game_date, an_game_id).
--
-- Action Network team abbreviations are nearly identical to the project's
-- ref_teams.team_abbrev convention. The only mismatch observed in 2025
-- responses is "ARI" (Action Network) vs. "AZ" (project / MLB Stats API);
-- we normalize ARI → AZ so joins on (game_date, home_team_id, away_team_id)
-- against feature_pregame_game_features.home_team / .away_team work cleanly.
--
-- Sharp signal columns:
--   ml_sharp_signal    = home_ml_money_pct - home_ml_ticket_pct
--   total_sharp_signal = over_money_pct    - over_ticket_pct
-- Positive = money side heavier than ticket side (proxy for sharp lean).
--
-- E11.1-W11 Tier-D lakehouse migration. This model feeds the W8b serving aggregator
-- (feature_pregame_game_features_raw's public_betting CTE) as a precursor. The DuckDB branch reads
-- the public_betting_raw S3 raw mirror (lakehouse_raw/public_betting_raw/, dual-written by
-- ingest_actionnetwork_betting under W11_RAW_WRITE_MODE + the one-time export_w11_raw_to_s3.py
-- bridge); the Snowflake (else) branch is a thin view over the lakehouse_ext external table (rollback
-- path). Once the native parquet lands at lakehouse/stg_actionnetwork_public_betting/, the W8b
-- precursor VIEW reads it directly, replacing the export_w8b_precursors_to_s3.py mirror at the same
-- key. ingestion_timestamp is read via try_cast(... as timestamp) — the INC-23 use-site cast: the raw
-- mirror UNIONs the SF-typed bridge (TIMESTAMP) with live-writer rows (ISO VARCHAR from
-- public_betting_mirror_rows), which union_by_name reconciles to VARCHAR; try_cast parses both.

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11d_lakehouse']) }}

with raw as (
    select * from read_parquet('{{ lakehouse_raw_loc("public_betting_raw") }}**/*.parquet', union_by_name=true)
),

normalized as (
    select
        game_date::date                                  as game_date,
        an_game_id::varchar                              as an_game_id,

        -- Normalize Action Network abbreviations to ref_teams.team_abbrev.
        case upper(home_team_abbr)
            when 'ARI' then 'AZ'
            else upper(home_team_abbr)
        end                                              as home_team_id,
        case upper(away_team_abbr)
            when 'ARI' then 'AZ'
            else upper(away_team_abbr)
        end                                              as away_team_id,

        try_cast(home_ml_money_pct as double)            as home_ml_money_pct,
        try_cast(away_ml_money_pct as double)            as away_ml_money_pct,
        try_cast(home_ml_ticket_pct as double)           as home_ml_ticket_pct,
        try_cast(away_ml_ticket_pct as double)           as away_ml_ticket_pct,

        try_cast(over_money_pct as double)               as over_money_pct,
        try_cast(under_money_pct as double)              as under_money_pct,
        try_cast(over_ticket_pct as double)              as over_ticket_pct,
        try_cast(under_ticket_pct as double)             as under_ticket_pct,

        (try_cast(home_ml_money_pct as double) - try_cast(home_ml_ticket_pct as double)) as ml_sharp_signal,
        (try_cast(over_money_pct as double)    - try_cast(over_ticket_pct as double))    as total_sharp_signal,

        try_cast(ingestion_timestamp as timestamp)       as ingestion_timestamp
    from raw
)

select * from normalized
qualify row_number() over (
    partition by game_date, an_game_id
    order by ingestion_timestamp desc
) = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_actionnetwork_public_betting

{% endif %}

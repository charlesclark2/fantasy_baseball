-- =============================================================================
-- feature_pregame_public_betting_features.sql
-- Story 15.6 — current-state view over the SCD-2 public betting status table.
--
-- Grain: one row per game_pk (is_current = true rows only).
-- Upstream: feature_pregame_public_betting_status (SCD-2, story 15.6).
--
-- For point-in-time historical queries use feature_pregame_public_betting_status
-- directly with valid_from / valid_to / is_current filters.
-- Pre-cutoff approximation: games before 2026-05-07 produce NULL for all columns;
-- two permanent gaps: Action Network API (pre-2024-02-22) + pre-Epic-T snapshots.
--
-- E11.1-W11 Tier-D lakehouse migration + the W8a-deferred straggler the W8b aggregator tail reads
-- (feature_pregame_meta_model_features). The DuckDB branch reads the migrated
-- feature_pregame_public_betting_status (registered as a DuckDB view by _build_w11d); once the native
-- parquet lands at lakehouse/feature_pregame_public_betting_features/, the export_features_to_s3.py
-- mirror at that SAME key is superseded (trim it at cutover). The Snowflake (else) branch is a thin
-- view over the lakehouse_ext external table (rollback path).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11d_lakehouse']) }}

select
    game_pk,
    an_game_id,
    home_ml_money_pct,
    away_ml_money_pct,
    home_ml_ticket_pct,
    away_ml_ticket_pct,
    over_money_pct,
    under_money_pct,
    over_ticket_pct,
    under_ticket_pct,
    ml_sharp_signal,
    total_sharp_signal,
    valid_from                      as public_betting_snapshot_ts
from {{ ref('feature_pregame_public_betting_status') }}
where is_current = true

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_public_betting_features

{% endif %}

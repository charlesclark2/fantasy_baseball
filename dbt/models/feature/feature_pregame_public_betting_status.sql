-- =============================================================================
-- feature_pregame_public_betting_status.sql
-- Story 15.6 — SCD-2 table for Action Network public betting percentages.
--
-- Grain: one row per (game_pk, valid_from) — one SCD-2 row per intraday shift.
-- Natural key: game_pk (single denormalized row per game; ML and totals co-located).
--
-- Coverage: 2026-05-07 onward (Epic T.3 raw-capture date).
-- Dual coverage gap documented:
--   (1) Action Network API gap: pre-2024-02-22 permanently unrecoverable.
--   (2) Pre-Epic-T gap: raw snapshots were not captured before 2026-05-07.
-- Pre-cutoff approximation: no rows exist for pre-2026-05-07 games; downstream
-- feature_pregame_public_betting_features returns NULL for all betting percentage
-- columns for those games. Models trained on pre-T data treat public betting as
-- missing (NULL-imputed) for those observations.
-- For the current season, most games will have a single SCD-2 row (the fetcher
-- runs once daily); multiple rows appear when the intraday data shifts noticeably.
--
-- AS-OF point-in-time query pattern:
--   WHERE game_pk = :gk
--     AND valid_from <= :prediction_ts
--     AND (valid_to IS NULL OR valid_to > :prediction_ts)
--
-- E11.1-W11 Tier-D lakehouse migration. The DuckDB branch recomputes the SCD-2 spans over the
-- migrated stg_actionnetwork_public_betting_snapshots (registered as a DuckDB view by
-- run_w1_lakehouse._build_w11d) with a Snowflake→DuckDB dialect rewrite (sysdate()→current_timestamp).
-- The Snowflake (else) branch is a thin view over the lakehouse_ext external table (rollback path).
-- The valid_from/valid_to/is_current spans are parity-verified SF-vs-S3 on a REAL box run before
-- cutover (a parity SELECT alone won't prove the lag/lead change-boundary logic).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11d_lakehouse']) }}

with snapshots as (
    select * from {{ ref('stg_actionnetwork_public_betting_snapshots') }}
),

with_lag as (
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
        record_hash,
        loaded_at,
        lag(record_hash) over (
            partition by game_pk
            order by loaded_at
        )                                                       as prev_hash
    from snapshots
),

change_boundaries as (
    select * from with_lag
    where prev_hash is distinct from record_hash
),

with_scd2 as (
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
        loaded_at                                               as valid_from,
        lead(loaded_at) over (
            partition by game_pk
            order by loaded_at
        )                                                       as valid_to,
        record_hash,
        current_timestamp::timestamp                            as computed_at
    from change_boundaries
)

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
    valid_from,
    valid_to,
    (valid_to is null)                                          as is_current,
    record_hash,
    computed_at
from with_scd2

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_public_betting_status

{% endif %}

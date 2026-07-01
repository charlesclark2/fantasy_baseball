-- feature_pregame_umpire_status.sql
-- SCD-2 for HP umpire assignments. Grain: one row per (game_pk, valid_from).
-- Natural key: game_pk (source has one HP ump per game; no ump_position column).
--
-- Coverage gap: Epic T.4 onward (~2026-05-02). For historical games (pre-T),
-- use stg_statsapi_umpire_game_log which holds the final deduped assignment.
-- Pre-T loss risk is low — umpire substitutions are rare and UmpScorecards
-- provides authoritative final assignments via annual bulk refresh.
--
-- Change detection: LAG on record_hash (umpire_name + tendency stats).
-- Note: umpire_id is null for all umpscorecards rows (99% of source); umpire_name
-- is the canonical identifier used in both the hash and downstream trailing joins.
-- Most games will have a single SCD-2 row (one assignment, no intraday change).
--
-- E11.1-W11 Tier-B lakehouse migration. DuckDB branch recomputes the SCD-2 spans over the
-- migrated stg_statsapi_umpire_snapshots (registered as a DuckDB view by run_w1_lakehouse
-- ._build_w11b) with a Snowflake→DuckDB dialect rewrite (sysdate()→current_timestamp). The
-- Snowflake (else) branch is a thin view over the lakehouse_ext external table (rollback path).
-- The valid_from/valid_to/is_current spans are parity-verified SF-vs-S3 on a REAL box run
-- before cutover (a parity SELECT alone won't prove the snapshot/hash change-boundary logic).

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11b_lakehouse']) }}

with snapshots as (
    select * from {{ ref('stg_statsapi_umpire_snapshots') }}
),

with_lag as (
    select *,
        lag(record_hash) over (partition by game_pk order by loaded_at) as prev_hash
    from snapshots
),

change_boundaries as (
    select * from with_lag
    where prev_hash is distinct from record_hash
),

with_scd2 as (
    select
        game_pk,
        game_date,
        season,
        umpire_name,
        umpire_id,
        total_runs,
        total_run_impact,
        accuracy_above_expected,
        data_source,
        loaded_at                                                       as valid_from,
        lead(loaded_at) over (partition by game_pk order by loaded_at) as valid_to,
        record_hash,
        current_timestamp::timestamp                                    as computed_at
    from change_boundaries
)

select *, (valid_to is null) as is_current
from with_scd2

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_umpire_status

{% endif %}

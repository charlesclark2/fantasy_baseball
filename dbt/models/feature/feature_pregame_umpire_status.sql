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

{{ config(materialized='table') }}

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
        sysdate()                                                       as computed_at
    from change_boundaries
)

select *, (valid_to is null) as is_current
from with_scd2

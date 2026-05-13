-- =============================================================================
-- feature_pregame_sub_model_signals.sql
-- Grain: one row per (game_pk, side)
-- Purpose: Wide-format consumption view over mart_sub_model_signals. Each
--          (signal_name, sub_model_version) pair becomes its own column, so
--          downstream feature joins to this model on (game_pk, side) and
--          receive all sub-model signals without knowing their names.
--
-- PIVOT strategy: dynamic pivot via aggregation (Snowflake does not support
-- true dynamic PIVOT with unknown column names at parse time). We use
-- MAX(CASE WHEN ...) to produce one column per known (signal_name, version)
-- pair. When a new signal is registered, add its column block here and run
-- `dbtf build --select feature_pregame_sub_model_signals`.
--
-- Currently registered signals (add as Epics 3–8 ship):
--   run_env_v1.run_env_signal          → run_env_signal_v1
--   run_env_v1.environment_volatility  → environment_volatility_v1
--   [test_signal_v1]                   → test_signal_v1  (synthetic; remove post-validation)
--
-- SCD-2 note: only is_current = true rows are used here (latest state).
--             For AS-OF historical replay see mart_sub_model_signals directly.
-- =============================================================================

{{ config(
    materialized='table',
    schema='betting_features'
) }}

with current_signals as (
    select
        game_pk,
        side,
        signal_name,
        sub_model_version,
        signal_value,
        uncertainty,
        signal_available
    from {{ source('betting', 'mart_sub_model_signals') }}
    where is_current = true
),

pivoted as (
    select
        game_pk,
        side,

        -- ------------------------------------------------------------------
        -- Run environment sub-model (Epic 3)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v1' then signal_value end)     as run_env_signal_v1,
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v1' then uncertainty end)      as run_env_signal_v1_uncertainty,
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v1' then signal_available end) as run_env_signal_v1_available,
        max(case when signal_name = 'environment_volatility' and sub_model_version = 'v1' then signal_value end)     as environment_volatility_v1,
        max(case when signal_name = 'environment_volatility' and sub_model_version = 'v1' then signal_available end) as environment_volatility_v1_available,

        -- ------------------------------------------------------------------
        -- Offensive quality sub-model (Epic 4)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'lineup_run_creation_signal' and sub_model_version = 'v1' then signal_value end)     as lineup_run_creation_signal_v1,
        max(case when signal_name = 'lineup_run_creation_signal' and sub_model_version = 'v1' then signal_available end) as lineup_run_creation_signal_v1_available,

        -- ------------------------------------------------------------------
        -- Starter suppression sub-model (Epic 5)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'starter_suppression_signal' and sub_model_version = 'v1' then signal_value end)     as starter_suppression_signal_v1,
        max(case when signal_name = 'starter_suppression_signal' and sub_model_version = 'v1' then signal_available end) as starter_suppression_signal_v1_available,

        -- ------------------------------------------------------------------
        -- Bullpen state sub-model (Epic 6)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'bullpen_state_signal' and sub_model_version = 'v1' then signal_value end)     as bullpen_state_signal_v1,
        max(case when signal_name = 'bullpen_state_signal' and sub_model_version = 'v1' then signal_available end) as bullpen_state_signal_v1_available,

        -- ------------------------------------------------------------------
        -- Matchup sub-model (Epic 8)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'matchup_advantage_signal' and sub_model_version = 'v1' then signal_value end)     as matchup_advantage_signal_v1,
        max(case when signal_name = 'matchup_advantage_signal' and sub_model_version = 'v1' then signal_available end) as matchup_advantage_signal_v1_available,

        -- ------------------------------------------------------------------
        -- Synthetic test signal (remove after 2.1 validation is confirmed)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'test_signal' and sub_model_version = 'v1' then signal_value end)     as test_signal_v1,
        max(case when signal_name = 'test_signal' and sub_model_version = 'v1' then signal_available end) as test_signal_v1_available

    from current_signals
    group by game_pk, side
)

select * from pivoted

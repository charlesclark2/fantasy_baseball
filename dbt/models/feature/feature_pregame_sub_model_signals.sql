-- =============================================================================
-- feature_pregame_sub_model_signals.sql
-- Grain: one row per (game_pk, side)
-- Purpose: Wide-format consumption view over mart_sub_model_signals plus
--          dedicated signal tables. Downstream features join on (game_pk, side)
--          and receive all sub-model signals without knowing table internals.
--
-- PIVOT strategy: dynamic pivot via aggregation (Snowflake does not support
-- true dynamic PIVOT with unknown column names at parse time). We use
-- MAX(CASE WHEN ...) to produce one column per known (signal_name, version)
-- pair. When a new signal is registered, add its column block here and run
-- `dbtf build --select feature_pregame_sub_model_signals`.
--
-- Currently registered signals:
--   run_env_v4.run_env_mu              → run_env_mu_v4          (champion; NegBin μ)
--   run_env_v4.run_env_dispersion      → run_env_dispersion_v4  (NegBin r; constant per model)
--   run_env_v4.run_env_signal          → run_env_signal_v4      (z-score of μ; primary signal)
--   run_env_v3.run_env_signal          → run_env_signal_v3      (deprecated; retained for continuity)
--   run_env_v3.environment_volatility  → environment_volatility_v3  (deprecated)
--   offense_v1_signals.pred_runs_raw   → pred_runs_raw_v1   (Epic 4; LightGBM, bias-corrected)
--   offense_v1_signals.runs_index      → runs_index_v1       (100 = season avg)
--   [test_signal_v1]                   → test_signal_v1  (synthetic; remove post-validation)
--
-- SCD-2 note: only is_current = true rows are used for mart_sub_model_signals.
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
        -- Run environment sub-model v4 (Epic 3D — champion; Ridge + NegBin)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'run_env_mu'         and sub_model_version = 'v4' then signal_value end)     as run_env_mu_v4,
        max(case when signal_name = 'run_env_mu'         and sub_model_version = 'v4' then uncertainty end)      as run_env_mu_v4_uncertainty,
        max(case when signal_name = 'run_env_mu'         and sub_model_version = 'v4' then signal_available end) as run_env_mu_v4_available,
        max(case when signal_name = 'run_env_dispersion' and sub_model_version = 'v4' then signal_value end)     as run_env_dispersion_v4,
        max(case when signal_name = 'run_env_dispersion' and sub_model_version = 'v4' then signal_available end) as run_env_dispersion_v4_available,
        max(case when signal_name = 'run_env_signal'     and sub_model_version = 'v4' then signal_value end)     as run_env_signal_v4,
        max(case when signal_name = 'run_env_signal'     and sub_model_version = 'v4' then uncertainty end)      as run_env_signal_v4_uncertainty,
        max(case when signal_name = 'run_env_signal'     and sub_model_version = 'v4' then signal_available end) as run_env_signal_v4_available,

        -- ------------------------------------------------------------------
        -- Run environment sub-model v3 (deprecated; retained for continuity)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v3' then signal_value end)     as run_env_signal_v3,
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v3' then uncertainty end)      as run_env_signal_v3_uncertainty,
        max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v3' then signal_available end) as run_env_signal_v3_available,
        max(case when signal_name = 'environment_volatility' and sub_model_version = 'v3' then signal_value end)     as environment_volatility_v3,
        max(case when signal_name = 'environment_volatility' and sub_model_version = 'v3' then signal_available end) as environment_volatility_v3_available,

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

select
    p.game_pk,
    p.side,

    -- Run environment signals v4 (Epic 3D — champion)
    p.run_env_mu_v4,
    p.run_env_mu_v4_uncertainty,
    p.run_env_mu_v4_available,
    p.run_env_dispersion_v4,
    p.run_env_dispersion_v4_available,
    p.run_env_signal_v4,
    p.run_env_signal_v4_uncertainty,
    p.run_env_signal_v4_available,

    -- Run environment signals v3 (deprecated; retained for continuity)
    p.run_env_signal_v3,
    p.run_env_signal_v3_uncertainty,
    p.run_env_signal_v3_available,
    p.environment_volatility_v3,
    p.environment_volatility_v3_available,

    -- Offensive quality signals (Epic 4 — from dedicated offense_v1_signals table)
    o.pred_runs_raw                                         as pred_runs_raw_v1,
    o.runs_index                                            as runs_index_v1,
    (o.pred_runs_raw is not null)                          as pred_runs_raw_v1_available,

    -- Starter suppression signals (Epic 5)
    p.starter_suppression_signal_v1,
    p.starter_suppression_signal_v1_available,

    -- Bullpen state signals (Epic 6)
    p.bullpen_state_signal_v1,
    p.bullpen_state_signal_v1_available,

    -- Matchup signals (Epic 8)
    p.matchup_advantage_signal_v1,
    p.matchup_advantage_signal_v1_available,

    -- Synthetic test signal
    p.test_signal_v1,
    p.test_signal_v1_available

from pivoted p
left join {{ source('betting_features', 'offense_v1_signals') }} o
    on  o.game_pk       = p.game_pk
    and o.side          = p.side
    and o.model_version = 'offense_v1'

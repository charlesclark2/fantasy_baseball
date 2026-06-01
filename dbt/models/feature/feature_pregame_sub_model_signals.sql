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
--   offense_v2_signals.pred_runs_mu    → pred_runs_mu_v2     (Epic 4D; LightGBM+NegBin μ; champion)
--   offense_v2_signals.pred_runs_dispersion → pred_runs_dispersion_v2  (NegBin r; constant per model)
--   offense_v2_signals.pred_runs_raw   → pred_runs_raw_v2    (alias for pred_runs_mu; no bias correction)
--   offense_v2_signals.uncertainty     → pred_runs_uncertainty_v2  (80% PI width)
--   starter_suppression_signals.starter_suppression_mu     → starter_suppression_mu_v1     (Epic 5; Normal μ)
--   starter_suppression_signals.starter_suppression_sigma  → starter_suppression_sigma_v1  (Normal σ; constant per model)
--   starter_suppression_signals.starter_suppression_signal → starter_suppression_signal_v1 (z-score; negative = better suppression)
--   starter_suppression_signals.uncertainty                → starter_uncertainty_v1         (80% PI width: 2×1.28×σ)
--   bullpen_v1.bullpen_availability_index       → bullpen_availability_index_v1   (rules-based [0,1]; higher = more rested)
--   bullpen_v1.bullpen_fatigue_signal           → bullpen_fatigue_signal_v1       (1 - availability_index)
--   bullpen_v1.bullpen_quality_mu               → bullpen_quality_mu_v1           (NGBoost predicted xwOBA; Normal μ)
--   bullpen_v1.bullpen_quality_sigma            → bullpen_quality_sigma_v1        (per-row NGBoost σ; predictive uncertainty)
--   bullpen_v1.bullpen_quality_signal           → bullpen_quality_signal_v1       (z-score of mu; negative = strong bullpen)
--   bullpen_v1.high_leverage_availability_proxy → high_leverage_availability_proxy_v1  (closer/hi-lev arm availability [0,1])
--   bullpen_v1.late_game_volatility_signal      → late_game_volatility_signal_v1  (80% PI width: 2×1.28×σ)
--   bullpen_v2.bullpen_mu                  → bullpen_mu_v2                  (Epic 6D; LightGBM+NegBin μ; expected runs allowed)
--   bullpen_v2.bullpen_dispersion          → bullpen_dispersion_v2          (NegBin r = 1.4474; lower = higher overdispersion)
--   bullpen_v2.bullpen_fatigue_adjusted_mu → bullpen_fatigue_adjusted_mu_v2 (μ × eb_xwoba/season_avg; quality-corrected expected runs)
--   bullpen_v2.uncertainty                 → bullpen_uncertainty_v2         (80% NegBin PI width: ppf(0.90)−ppf(0.10))
--   starter_ip_signals.starter_ip_mu       → starter_ip_mu_v1       (Epic 5D; LightGBM+NegBin μ; outs recorded)
--   starter_ip_signals.starter_ip_dispersion → starter_ip_dispersion_v1   (NegBin r; per-decile)
--   starter_ip_signals.starter_ip_signal   → starter_ip_signal_v1   (z-score of μ vs season mean)
--   starter_ip_signals.starter_ip_p80_outs → starter_ip_p80_outs_v1 (optimistic depth; outs)
--   starter_ip_signals.starter_ip_p20_outs → starter_ip_p20_outs_v1 (pessimistic depth; outs — key input to 6D Candidate B)
--   starter_ip_signals.uncertainty         → starter_ip_uncertainty_v1  (80% PI width: p80−p20 outs)
--   starter_ip_signals.is_bulk_usage       → starter_ip_is_bulk_usage_v1  (TRUE when mu < 9 outs)
--   NOTE: IP mu/p80/p20 are in OUTS — divide by 3.0 for innings-pitched display;
--         keep as outs for NegBin CDF computations in 6D Candidate B.
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

        -- (starter suppression signals sourced from dedicated table below; no pivot needed)

        -- ------------------------------------------------------------------
        -- Bullpen state sub-model v1 (Epic 6 — NGBoost Normal; champion)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'bullpen_availability_index'       and sub_model_version = 'v1' then signal_value end)     as bullpen_availability_index_v1,
        max(case when signal_name = 'bullpen_availability_index'       and sub_model_version = 'v1' then signal_available end) as bullpen_availability_index_v1_available,
        max(case when signal_name = 'bullpen_fatigue_signal'           and sub_model_version = 'v1' then signal_value end)     as bullpen_fatigue_signal_v1,
        max(case when signal_name = 'bullpen_fatigue_signal'           and sub_model_version = 'v1' then signal_available end) as bullpen_fatigue_signal_v1_available,
        max(case when signal_name = 'bullpen_quality_mu'               and sub_model_version = 'v1' then signal_value end)     as bullpen_quality_mu_v1,
        max(case when signal_name = 'bullpen_quality_mu'               and sub_model_version = 'v1' then uncertainty end)      as bullpen_quality_mu_v1_uncertainty,
        max(case when signal_name = 'bullpen_quality_mu'               and sub_model_version = 'v1' then signal_available end) as bullpen_quality_mu_v1_available,
        max(case when signal_name = 'bullpen_quality_sigma'            and sub_model_version = 'v1' then signal_value end)     as bullpen_quality_sigma_v1,
        max(case when signal_name = 'bullpen_quality_sigma'            and sub_model_version = 'v1' then signal_available end) as bullpen_quality_sigma_v1_available,
        max(case when signal_name = 'bullpen_quality_signal'           and sub_model_version = 'v1' then signal_value end)     as bullpen_quality_signal_v1,
        max(case when signal_name = 'bullpen_quality_signal'           and sub_model_version = 'v1' then uncertainty end)      as bullpen_quality_signal_v1_uncertainty,
        max(case when signal_name = 'bullpen_quality_signal'           and sub_model_version = 'v1' then signal_available end) as bullpen_quality_signal_v1_available,
        max(case when signal_name = 'high_leverage_availability_proxy' and sub_model_version = 'v1' then signal_value end)     as high_leverage_availability_proxy_v1,
        max(case when signal_name = 'high_leverage_availability_proxy' and sub_model_version = 'v1' then signal_available end) as high_leverage_availability_proxy_v1_available,
        max(case when signal_name = 'late_game_volatility_signal'      and sub_model_version = 'v1' then signal_value end)     as late_game_volatility_signal_v1,
        max(case when signal_name = 'late_game_volatility_signal'      and sub_model_version = 'v1' then signal_available end) as late_game_volatility_signal_v1_available,

        -- ------------------------------------------------------------------
        -- Bullpen distributional sub-model v2 (Epic 6D — LightGBM+NegBin; champion)
        -- ------------------------------------------------------------------
        max(case when signal_name = 'bullpen_mu'                  and sub_model_version = 'v2' then signal_value end)     as bullpen_mu_v2,
        max(case when signal_name = 'bullpen_mu'                  and sub_model_version = 'v2' then uncertainty end)      as bullpen_mu_v2_uncertainty,
        max(case when signal_name = 'bullpen_mu'                  and sub_model_version = 'v2' then signal_available end) as bullpen_mu_v2_available,
        max(case when signal_name = 'bullpen_dispersion'          and sub_model_version = 'v2' then signal_value end)     as bullpen_dispersion_v2,
        max(case when signal_name = 'bullpen_dispersion'          and sub_model_version = 'v2' then signal_available end) as bullpen_dispersion_v2_available,
        max(case when signal_name = 'bullpen_fatigue_adjusted_mu' and sub_model_version = 'v2' then signal_value end)     as bullpen_fatigue_adjusted_mu_v2,
        max(case when signal_name = 'bullpen_fatigue_adjusted_mu' and sub_model_version = 'v2' then uncertainty end)      as bullpen_fatigue_adjusted_mu_v2_uncertainty,
        max(case when signal_name = 'bullpen_fatigue_adjusted_mu' and sub_model_version = 'v2' then signal_available end) as bullpen_fatigue_adjusted_mu_v2_available,
        max(case when signal_name = 'uncertainty'                 and sub_model_version = 'v2' then signal_value end)     as bullpen_uncertainty_v2,
        max(case when signal_name = 'uncertainty'                 and sub_model_version = 'v2' then signal_available end) as bullpen_uncertainty_v2_available,

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

    -- Offensive quality signals v1 (Epic 4 — LightGBM, bias-corrected; deprecated)
    o.pred_runs_raw                                         as pred_runs_raw_v1,
    o.runs_index                                            as runs_index_v1,
    (o.pred_runs_raw is not null)                          as pred_runs_raw_v1_available,

    -- Offensive quality signals v2 (Epic 4D — LightGBM+NegBin distributional; champion)
    o2.pred_runs_mu                                         as pred_runs_mu_v2,
    o2.pred_runs_dispersion                                 as pred_runs_dispersion_v2,
    o2.pred_runs_raw                                        as pred_runs_raw_v2,
    o2.uncertainty                                          as pred_runs_uncertainty_v2,
    (o2.pred_runs_mu is not null)                          as pred_runs_mu_v2_available,

    -- Starter suppression signals v1 (Epic 5 — LightGBM+Normal distributional; champion)
    ss.starter_suppression_mu                                   as starter_suppression_mu_v1,
    ss.starter_suppression_sigma                                as starter_suppression_sigma_v1,
    ss.starter_suppression_signal                               as starter_suppression_signal_v1,
    ss.uncertainty                                              as starter_uncertainty_v1,
    (ss.starter_suppression_mu is not null)                    as starter_suppression_mu_v1_available,

    -- Bullpen state signals v1 (Epic 6 — NGBoost Normal; champion)
    p.bullpen_availability_index_v1,
    p.bullpen_availability_index_v1_available,
    p.bullpen_fatigue_signal_v1,
    p.bullpen_fatigue_signal_v1_available,
    p.bullpen_quality_mu_v1,
    p.bullpen_quality_mu_v1_uncertainty,
    p.bullpen_quality_mu_v1_available,
    p.bullpen_quality_sigma_v1,
    p.bullpen_quality_sigma_v1_available,
    p.bullpen_quality_signal_v1,
    p.bullpen_quality_signal_v1_uncertainty,
    p.bullpen_quality_signal_v1_available,
    p.high_leverage_availability_proxy_v1,
    p.high_leverage_availability_proxy_v1_available,
    p.late_game_volatility_signal_v1,
    p.late_game_volatility_signal_v1_available,

    -- Bullpen distributional signals v2 (Epic 6D — LightGBM+NegBin; champion)
    p.bullpen_mu_v2,
    p.bullpen_mu_v2_uncertainty,
    p.bullpen_mu_v2_available,
    p.bullpen_dispersion_v2,
    p.bullpen_dispersion_v2_available,
    p.bullpen_fatigue_adjusted_mu_v2,
    p.bullpen_fatigue_adjusted_mu_v2_uncertainty,
    p.bullpen_fatigue_adjusted_mu_v2_available,
    p.bullpen_uncertainty_v2,
    p.bullpen_uncertainty_v2_available,

    -- Matchup signals (Epic 8)
    p.matchup_advantage_signal_v1,
    p.matchup_advantage_signal_v1_available,

    -- Starter IP depth signals v1 (Epic 5D — LightGBM+NegBin; outs units)
    ip.starter_ip_mu                                      as starter_ip_mu_v1,
    ip.starter_ip_dispersion                              as starter_ip_dispersion_v1,
    ip.starter_ip_signal                                  as starter_ip_signal_v1,
    ip.starter_ip_p80_outs                                as starter_ip_p80_outs_v1,
    ip.starter_ip_p20_outs                                as starter_ip_p20_outs_v1,
    ip.uncertainty                                        as starter_ip_uncertainty_v1,
    ip.is_bulk_usage                                      as starter_ip_is_bulk_usage_v1,
    (ip.starter_ip_mu is not null)                        as starter_ip_mu_v1_available,

    -- Synthetic test signal
    p.test_signal_v1,
    p.test_signal_v1_available

from pivoted p
left join {{ source('betting_features', 'offense_v1_signals') }} o
    on  o.game_pk       = p.game_pk
    and o.side          = p.side
    and o.model_version = 'offense_v1'
left join {{ source('betting_features', 'offense_v2_signals') }} o2
    on  o2.game_pk       = p.game_pk
    and o2.side          = p.side
    and o2.model_version = 'offense_v2'
left join {{ source('betting_features', 'starter_suppression_signals') }} ss
    on  ss.game_pk       = p.game_pk
    and ss.side          = p.side
    and ss.model_version = 'starter_v1'
left join {{ source('betting_features', 'starter_ip_signals') }} ip
    on  ip.game_pk       = p.game_pk
    and ip.side          = p.side
    and ip.model_version = 'starter_ip_v1'

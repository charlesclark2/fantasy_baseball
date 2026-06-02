-- =============================================================================
-- mart_clv_label_count.sql
-- Grain: one row total
--
-- Purpose: Canonical gate threshold tracker for Epic 12.
--          Downstream stories gate on specific live_total_count thresholds:
--            ≥ 10  → 12.2 (descriptive monitoring) — already met
--            ≥ 50  → 12.3 (proxy analysis), 12.4 (Bayesian meta-model)
--            ≥ 100 → 12.5 (Bayesian → Epic 19 integration)
--            ≥ 200 → 12.4 posterior CIs narrow enough for operational use
--            ≥ 500 → 12.6 (frequentist exploratory meta-model)
--            ≥ 1000 → 12.7 (production meta-model)
--
--          pct_clv_positive is the fraction of rows where clv > 0, measured
--          across all market types. Used in 12.2 monitoring alerts.
-- =============================================================================

{{ config(materialized='view') }}

select
    count(case when market_type = 'h2h'    then 1 end)          as live_h2h_count,
    count(case when market_type = 'totals' then 1 end)          as live_totals_count,
    count(*)                                                    as live_total_count,
    min(game_date)                                              as earliest_game_date,
    max(game_date)                                              as latest_game_date,
    round(
        avg(case when clv_positive then 1.0 else 0.0 end),
        4
    )                                                           as pct_clv_positive
from {{ ref('mart_clv_labeled_games') }}

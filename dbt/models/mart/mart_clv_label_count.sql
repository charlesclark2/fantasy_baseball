-- =============================================================================
-- mart_clv_label_count.sql
-- Grain: one row total
-- Purpose: Canonical gate threshold tracker for Epic 12 (count of CLV-labeled
--          games + pct_clv_positive across all market types).
--
-- DuckDB branch (E11.1-W6): aggregates the migrated mart_clv_labeled_games; the
-- Snowflake (else) branch is a thin view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

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
from mart_clv_labeled_games

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_clv_label_count

{% endif %}

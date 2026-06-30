-- =============================================================================
-- feature_league_contact_baseline.sql  (Story 27.7, Task 1)
-- Grain: one row per (game_year, game_date)
-- Purpose: strictly-prior AS-OF league baseline (mean + std) for every
--          contact-quality feature, used to season-normalize those features in
--          feature_pregame_game_features. Leakage-safe: each date sees only
--          STRICTLY-PRIOR same-season games (the window frame excludes today),
--          shrunk toward the prior season's full-season stats early so a
--          baseline exists before the current season accrues.
--
-- This is the dbt counterpart of the Task-1 league run-environment monitor
-- (run_env_regime_monitor.py): the same as-of + prior-anchor methodology,
-- applied per contact feature instead of to the league run rate.
--
-- All statistics + shrinkage live in the as_of_contact_baseline() macro so the
-- column list can never drift from the application side (the public feature
-- model). Shrinkage pseudo-count: var contact_baseline_shrinkage_k (default 200).
-- =============================================================================

-- E11.1-W8b (serving-aggregator wave): dual-branch. DuckDB branch (real compute → S3,
-- run_w1_lakehouse special-cases this macro model in a Python builder — extract_duckdb_sql can't
-- render the as_of_contact_baseline() per-column loops) reads the migrated
-- feature_pregame_game_features_raw (registered DuckDB view). The Snowflake (else) branch reads the
-- lakehouse_ext external table (parity-gated by parity_check_w8b.py). The macro stays the single
-- source of truth for the contact-quality column list on the Snowflake side.
{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8b_lakehouse']) }}

{{ as_of_contact_baseline(ref('feature_pregame_game_features_raw')) }}

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_league_contact_baseline

{% endif %}

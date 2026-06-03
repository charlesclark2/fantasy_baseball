-- =============================================================================
-- add_layer3_totals_columns.sql
-- Epic 10 Story 10.3 (2026-06-02)
-- =============================================================================
-- Adds the Layer 3 totals model (totals_v1) output columns to
-- daily_model_predictions. These run in parallel (shadow) with the existing
-- NGBoost totals columns (p_over_ngboost, total_line_consensus, …) — the Layer 3
-- model does not become the production totals source until Story 10.6 → 10.7.
-- Safe to run multiple times — each ALTER uses ADD COLUMN IF NOT EXISTS.
--
-- Run once against prod (no --target flag needed for DDL). Use execute_string,
-- which parses comments + multiple statements correctly:
--   uv run python -c "from betting_ml.utils.data_loader import get_snowflake_connection as g; c=g(); list(c.execute_string(open('scripts/ddl/add_layer3_totals_columns.sql').read())); c.commit(); c.close(); print('done')"
-- =============================================================================

-- NegBin predictive distribution over total runs (champion totals_v1).
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_mu FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_r FLOAT;

-- Epistemic uncertainty about mu (across-model disagreement; drives the P(over) CI).
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS combined_sigma FLOAT;

-- Over/under/push probabilities from the NegBin CDF.
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_p_over FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_p_under FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_p_push FLOAT;

-- 80% credible interval on P(over) (delta method on combined_sigma).
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_p_over_ci_low FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_p_over_ci_high FLOAT;

-- Bovada (de-vigged) market reference + the line, and the resulting edge.
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS bovada_devig_over_prob FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS bovada_line FLOAT;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS total_line_source VARCHAR;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS totals_edge FLOAT;

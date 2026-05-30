-- =============================================================================
-- add_bet_gate_columns.sql
-- Story 19.2 (2026-05-29)
-- =============================================================================
-- Adds bet permission gate output columns to daily_model_predictions.
-- Safe to run multiple times — each ALTER uses ADD COLUMN IF NOT EXISTS.
--
-- Run once against prod (no --target flag needed for DDL):
--   Execute via Snowflake UI or: uv run python -c "
--       from betting_ml.utils.data_loader import get_snowflake_connection
--       conn = get_snowflake_connection(); cur = conn.cursor()
--       [cur.execute(s.strip()) for s in open('scripts/ddl/add_bet_gate_columns.sql').read().split(';') if s.strip()]
--       conn.commit(); conn.close()
--   "
-- =============================================================================

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS qualified_bet BOOLEAN;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS gate_signals_met INTEGER;

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS game_conviction_score FLOAT;

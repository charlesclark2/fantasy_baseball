-- Migration: add sub_model_versions_used column to daily_model_predictions
-- Story: Epic 2 / Story 2.2
-- Purpose: Record which sub-model versions contributed features to each
--          prediction row. Enables historical audit of signal provenance and
--          supports per-version attribution in future CLV meta-analysis.
--
-- Format: JSON array of {name, version} objects
--   e.g. [{"name": "run_env", "version": "v1"}, {"name": "offense", "version": "v1"}]
--
-- NULL when no sub-model signals were used (all pre-Epic 3 predictions).
-- Apply in dev first: dbtf run-operation or direct Snowflake execution.

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS sub_model_versions_used VARIANT;

-- Apply same migration to dev schema
ALTER TABLE baseball_data.betting_ml_dev.daily_model_predictions
    ADD COLUMN IF NOT EXISTS sub_model_versions_used VARIANT;

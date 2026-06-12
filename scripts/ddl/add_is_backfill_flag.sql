-- =============================================================================
-- add_is_backfill_flag.sql
-- Story 30.7 (model & prediction provenance) — explicit, non-overloaded backfill
-- flag on the main predictions table.
--
-- BEFORE: provenance was overloaded onto prediction_type ('morning'|'post_lineup'
-- carried live-timing AND 'backfill' carried provenance — a backfilled row lost its
-- live-timing meaning and the two axes were not independent).
-- AFTER:  is_backfill is the single source of truth for "was this row generated in
-- real time before the game (FALSE) vs backfilled after a promotion (TRUE)";
-- prediction_type returns to meaning live-timing only.
--
-- Run once. All table references fully qualified; no USE statements.
-- =============================================================================

-- 1. Add the explicit flag, defaulted to live (FALSE) so existing/new live rows are correct.
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
    ADD COLUMN IF NOT EXISTS is_backfill BOOLEAN DEFAULT FALSE;

-- 2. Migrate existing rows: anything historically tagged prediction_type='backfill'
--    is a backfill; everything else (morning / post_lineup / NULL) was live.
UPDATE baseball_data.betting_ml.daily_model_predictions
SET is_backfill = TRUE
WHERE prediction_type = 'backfill'
  AND (is_backfill IS NULL OR is_backfill = FALSE);

UPDATE baseball_data.betting_ml.daily_model_predictions
SET is_backfill = FALSE
WHERE is_backfill IS NULL
  AND (prediction_type IS NULL OR prediction_type <> 'backfill');

-- Verify (run manually after migration):
-- SELECT is_backfill, prediction_type, COUNT(*) AS row_count
-- FROM baseball_data.betting_ml.daily_model_predictions
-- GROUP BY is_backfill, prediction_type
-- ORDER BY is_backfill, prediction_type;

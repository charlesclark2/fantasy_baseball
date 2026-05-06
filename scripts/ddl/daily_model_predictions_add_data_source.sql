-- Migration: add data_source column to daily_model_predictions
-- Applied: 2026-05-05
-- Purpose: distinguish feature-store rows from intraday-fallback rows
ALTER TABLE baseball_data.betting_ml.daily_model_predictions
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50);

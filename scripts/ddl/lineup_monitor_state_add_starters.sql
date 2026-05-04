-- Migration: add starter tracking columns to lineup_monitor_state
-- Run once against baseball_data (ACCOUNTADMIN or role with ALTER TABLE privilege).
-- Safe to re-run — IF NOT EXISTS prevents errors on repeat execution.
--
-- Purpose: enables lineup_monitor to detect starting pitcher changes for already-triggered
-- games and re-score affected predictions (e.g. ace scratched post-lineup confirmation).

ALTER TABLE baseball_data.config.lineup_monitor_state
    ADD COLUMN IF NOT EXISTS home_starter_id INT;

ALTER TABLE baseball_data.config.lineup_monitor_state
    ADD COLUMN IF NOT EXISTS away_starter_id INT;

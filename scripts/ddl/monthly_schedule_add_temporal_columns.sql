-- Epic T, Story T.1 — Add temporal columns to monthly_schedule
-- Run this migration BEFORE deploying the append-only ingest_statsapi.py change.
-- Safe to run multiple times (IF NOT EXISTS guard).
--
-- Existing rows will get NULL for ingestion_ts and load_id — this is acceptable.
-- The staging models handle NULL ingestion_ts by treating older rows (NULL) as
-- lower priority than newly ingested rows (non-NULL) via NULLS LAST semantics.

ALTER TABLE baseball_data.statsapi.monthly_schedule
    ADD COLUMN ingestion_ts TIMESTAMP_NTZ;

ALTER TABLE baseball_data.statsapi.monthly_schedule
    ADD COLUMN load_id VARCHAR;

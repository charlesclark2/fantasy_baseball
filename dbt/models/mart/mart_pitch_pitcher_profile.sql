-- =============================================================================
-- mart_pitch_pitcher_profile.sql  (E11.1-W1d decommission)
-- Thin view over the S3 lakehouse external table.
-- Served from baseball_data.lakehouse_ext.mart_pitch_pitcher_profile (parquet
-- written daily by run_w1_lakehouse.py; metadata refreshed by
-- refresh_w1_external_tables.py). Excluded from dbtf run via tag:w1_lakehouse.
-- =============================================================================

{{
    config(
        materialized = 'view',
        tags         = ['w1_lakehouse']
    )
}}

select * from baseball_data.lakehouse_ext.mart_pitch_pitcher_profile

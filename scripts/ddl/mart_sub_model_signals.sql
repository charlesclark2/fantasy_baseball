-- =============================================================================
-- DDL: baseball_data.betting.mart_sub_model_signals
-- Purpose: Long-format storage for all sub-model signals (run_env, offense,
--          starter, bullpen, matchup). One row per (game_pk, side, signal_name,
--          sub_model_version, valid_from). SCD-2 pattern tracks state changes.
--
-- Grain: (game_pk, side, signal_name, sub_model_version, valid_from)
-- Populated by: sub-model inference scripts (Epics 3–8)
-- Consumed by: feature_pregame_sub_model_signals (wide PIVOT view)
--
-- DO NOT reference feature_pregame_* marts from this table — it is a training
-- label / signal store, not a feature mart. Downstream consumers join to it
-- via the wide view.
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting.mart_sub_model_signals (

    -- -------------------------------------------------------------------------
    -- Natural key
    -- -------------------------------------------------------------------------
    game_pk             NUMBER          NOT NULL,
    side                VARCHAR(10)     NOT NULL,   -- 'home' | 'away' | 'game'
    signal_name         VARCHAR(100)    NOT NULL,   -- e.g. 'run_env_signal'
    sub_model_name      VARCHAR(100)    NOT NULL,   -- e.g. 'run_env'
    sub_model_version   VARCHAR(20)     NOT NULL,   -- e.g. 'v1'

    -- -------------------------------------------------------------------------
    -- Payload
    -- -------------------------------------------------------------------------
    signal_value        FLOAT,                      -- central estimate; NULL when signal_available=false
    uncertainty         FLOAT,                      -- optional std dev / confidence interval; NULL if not produced
    signal_available    BOOLEAN         NOT NULL,   -- false for games outside the sub-model's effective window

    -- -------------------------------------------------------------------------
    -- Audit / lineage
    -- -------------------------------------------------------------------------
    input_feature_hash  VARCHAR(32),                -- MD5 of upstream feature values; used for drift detection
    computed_at         TIMESTAMP_NTZ   NOT NULL,   -- when the inference script wrote this row

    -- -------------------------------------------------------------------------
    -- SCD-2 columns (Story 2.4)
    -- valid_from / valid_to bracket the period during which this row is the
    -- current state for its natural key. is_current duplicates (valid_to IS NULL)
    -- for query convenience. record_hash detects payload changes.
    -- -------------------------------------------------------------------------
    valid_from          TIMESTAMP_NTZ   NOT NULL,
    valid_to            TIMESTAMP_NTZ,              -- NULL when current
    is_current          BOOLEAN         NOT NULL,
    record_hash         VARCHAR(32)     NOT NULL    -- MD5(signal_value || uncertainty || signal_available)

);

-- Primary key constraint (Snowflake does not support IF NOT EXISTS on ADD CONSTRAINT)
ALTER TABLE baseball_data.betting.mart_sub_model_signals
    ADD CONSTRAINT pk_sub_model_signals
    PRIMARY KEY (game_pk, side, signal_name, sub_model_version, valid_from);

COMMENT ON TABLE baseball_data.betting.mart_sub_model_signals IS
    'Long-format SCD-2 store for sub-model output signals. One row per (game_pk, side, signal_name, sub_model_version) per state change. Pivot to wide format via feature_pregame_sub_model_signals.';

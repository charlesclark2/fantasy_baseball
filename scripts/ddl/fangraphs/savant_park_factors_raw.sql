-- =============================================================================
-- savant_park_factors_raw
-- Grain: one row per (venue_id, season, bat_side, num_years_rolling).
-- Source: Baseball Savant statcast-park-factors page (server-rendered JSON
--         embedded in page JS). Provides HR, 1B, 2B/3B, BB, SO, wOBA factors
--         indexed to 100 (league average = 100).
-- Written by scripts/ingest_savant_park_factors.py.
-- MERGE-upserted on (venue_id, season, bat_side, num_years_rolling) each run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.fangraphs.savant_park_factors_raw (

    -- ── Grain ───────────────────────────────────────────────────────────────
    venue_id                INTEGER         NOT NULL,
    venue_name              VARCHAR(256)    NOT NULL,
    season                  INTEGER         NOT NULL,
    bat_side                VARCHAR(8)      NOT NULL,   -- 'All', 'L', 'R'
    num_years_rolling       INTEGER         NOT NULL,   -- 3 for 3yr rolling

    -- ── Sample size ─────────────────────────────────────────────────────────
    n_pa                    INTEGER,

    -- ── Park factors (index; 100 = league average) ──────────────────────────
    index_runs              INTEGER,
    index_hr                INTEGER,
    index_1b                INTEGER,
    index_2b                INTEGER,
    index_3b                INTEGER,
    index_bb                INTEGER,
    index_so                INTEGER,
    index_woba              INTEGER,
    index_hardhit           INTEGER,
    index_wobacon           INTEGER,
    index_xwobacon          INTEGER,

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id                  VARCHAR(64)     NOT NULL,

    CONSTRAINT pk_savant_park_factors PRIMARY KEY (venue_id, season, bat_side, num_years_rolling)
);

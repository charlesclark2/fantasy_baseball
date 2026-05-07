-- Drop and recreate with expanded schema.
-- Source changed from Baseball Savant (broken) to FanGraphs leaderboard API.
-- snapshot_date enables weekly captures; raw_json preserves API response for
-- schema resilience (columns can be re-derived if FanGraphs renames fields).
--
-- Run once to apply. Idempotent on repeated runs.

CREATE SCHEMA IF NOT EXISTS baseball_data.savant;

DROP TABLE IF EXISTS baseball_data.savant.catcher_framing_raw;

CREATE TABLE baseball_data.savant.catcher_framing_raw (
    player_id           VARCHAR(20)    NOT NULL,  -- MLBAM player ID (xMLBAMID from FanGraphs)
    season              INTEGER        NOT NULL,
    snapshot_date       DATE           NOT NULL,  -- date this row was captured (run weekly)
    framing_runs        FLOAT,                    -- CFraming: pure pitch-framing runs above average
    defensive_runs      FLOAT,                    -- FRP: total catcher defensive value (framing + blocking + arm + range)
    stolen_base_runs    FLOAT,                    -- rSB: arm/throwing runs saved on stolen base attempts
    innings_caught      FLOAT,                    -- Inn: sample size proxy for reliability regression
    raw_json            VARIANT,                  -- full FanGraphs API record; survives column renames
    ingestion_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (player_id, season, snapshot_date)
);

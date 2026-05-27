-- Sprint speed leaderboard from Baseball Savant.
-- Grain: one row per player × season × snapshot_date (captured weekly on Sundays).
-- sprint_speed is in ft/s (Statcast sprint speed, not FanGraphs Spd score).
-- competitive_runs: total HP-to-2B attempts used to compute the sprint speed metric.
--
-- Run once to create. Idempotent (CREATE TABLE IF NOT EXISTS).

CREATE SCHEMA IF NOT EXISTS baseball_data.savant;

CREATE TABLE IF NOT EXISTS baseball_data.savant.sprint_speed_raw (
    player_mlbam_id     VARCHAR(20)    NOT NULL,
    player_name         VARCHAR(100),
    team_abbrev         VARCHAR(10),
    season              INTEGER        NOT NULL,
    sprint_speed_fts    FLOAT,                    -- ft/s; Statcast sprint speed
    competitive_runs    INTEGER,                  -- sample size (HP-to-2B attempts)
    hp_to_1b            FLOAT,                    -- avg seconds HP-to-1B (right-handed)
    hp_to_2b            FLOAT,                    -- avg seconds HP-to-2B
    age                 INTEGER,
    position            VARCHAR(5),
    snapshot_date       DATE           NOT NULL,  -- date captured (weekly Sunday run)
    raw_json            VARIANT,                  -- full CSV row as JSON for schema resilience
    ingestion_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (player_mlbam_id, season, snapshot_date)
);

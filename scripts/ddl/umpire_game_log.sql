-- umpire_game_log.sql
-- One row per game_pk. HP umpire assignment and per-game tendency metrics.
--
-- Source A: UmpScorecards historical bulk export (2015-present)
--   Loaded via scripts/ingest_umpires_historical.py (manual/annual refresh).
--   Includes tendency metrics: total_runs, called_strikes_above_avg,
--   run_expectancy_delta, total_run_impact, accuracy_above_expected.
--   NOTE: k_pct and bb_pct are not available in the by-game export;
--   columns are retained for potential future population from Statcast.
--
-- Source B: MLB Stats API schedule?hydrate=officials (daily going forward)
--   Loaded via scripts/ingest_umpires.py --date YYYY-MM-DD.
--   Writes umpire_name and umpire_id only; tendency columns are NULL.
--   The dbt feature model computes trailing z-scores from Source A rows;
--   Source B rows allow today's game_pk to join via umpire_name.

CREATE TABLE IF NOT EXISTS baseball_data.statsapi.umpire_game_log (
    -- Game identifiers
    game_pk                  INTEGER       NOT NULL,
    game_date                DATE          NOT NULL,
    season                   INTEGER       NOT NULL,

    -- Umpire assignment
    umpire_name              VARCHAR(100)  NOT NULL,
    umpire_id                VARCHAR(50),  -- statsapi umpire ID when available

    -- Per-game tendency metrics (from UmpScorecards; NULL for daily-only rows)
    k_pct                    FLOAT,        -- K% for that game (not in by-game export)
    bb_pct                   FLOAT,        -- BB% for that game (not in by-game export)
    total_runs               INTEGER,      -- total runs scored (home + away)
    called_strikes_above_avg FLOAT,        -- Correct Calls Above Expected from UmpScorecards
    run_expectancy_delta     FLOAT,        -- Favor (Home) run expectancy impact
    total_run_impact         FLOAT,        -- Total Run Impact from UmpScorecards
    accuracy_above_expected  FLOAT,        -- Accuracy Above Expected from UmpScorecards

    -- Source metadata
    data_source              VARCHAR(50)   NOT NULL, -- 'umpscorecards' or 'statsapi'
    loaded_at                TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Unique constraint: one HP umpire per game
ALTER TABLE baseball_data.statsapi.umpire_game_log
ADD CONSTRAINT uq_umpire_game_log_game_pk UNIQUE (game_pk);

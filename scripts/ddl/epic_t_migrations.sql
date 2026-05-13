-- Epic T migrations — run each statement individually in the Snowflake UI.

-- T.4.A: Drop informational UNIQUE constraint on umpire_game_log.
-- Snowflake does not enforce UNIQUE constraints, but the constraint signals
-- the old one-row-per-game-pk intent. Append-only insert requires it gone.
ALTER TABLE baseball_data.statsapi.umpire_game_log
    DROP CONSTRAINT uq_umpire_game_log_game_pk;

-- T.4.C: Add loaded_at to oaa_team_season_raw for append-only dedup.
ALTER TABLE baseball_data.external.oaa_team_season_raw
    ADD COLUMN loaded_at TIMESTAMP_NTZ;

-- T.1.B: Add capture_reason to monthly_schedule.
-- Values: 'daily_full_month' (once-daily full-month pull),
--         'intraday_gameday' (30-min high-frequency game-day capture).
ALTER TABLE baseball_data.statsapi.monthly_schedule
    ADD COLUMN capture_reason VARCHAR;

-- T.2.A: Add weather_observation_type to weather_raw.
-- Values: 'forecast_pregame' (existing behavior),
--         'forecast_intraday' (T-24h/T-6h/T-3h/T-1h snapshots),
--         'observed_at_first_pitch' (archive-based actual conditions).
ALTER TABLE baseball_data.statsapi.weather_raw
    ADD COLUMN weather_observation_type VARCHAR;

-- T.2.D: Add hours_to_first_pitch to weather_raw.
-- Literal enum value set at ingest time for forecast_intraday rows: {24, 6, 3, 1}.
-- NULL for forecast_pregame and observed_at_first_pitch rows.
ALTER TABLE baseball_data.statsapi.weather_raw
    ADD COLUMN hours_to_first_pitch INTEGER;

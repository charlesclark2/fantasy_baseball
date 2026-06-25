-- =============================================================================
-- E11.1-W1d  W1 DECOMMISSION: Snowflake External Tables over S3 Parquet
-- =============================================================================
-- Run ONCE by the operator BEFORE removing mart_pitch_* from the dbt build.
-- The dbt mart_pitch_*.sql models become thin views over these external tables
-- after this DDL executes, so ref('mart_pitch_*') resolves identically.
--
-- Prerequisites:
--   1. AWS credentials (key_id + secret) with s3:GetObject / s3:ListBucket on
--      s3://baseball-betting-ml-artifacts/baseball/lakehouse/*
--      → These are the same credentials already in the pipeline env as
--        AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
--   2. run_w1_lakehouse.py has been run at least once (S3 parquets exist).
--
-- Rollback: the original Snowflake-built mart_pitch_* tables are NOT dropped
-- here; they stay in baseball_data.betting as instant rollback.  If S3 serving
-- wobbles, re-enable the Snowflake builds (see ROLLBACK section at bottom).
--
-- Security note: storing credentials in the stage avoids a storage-integration
-- setup, which requires AWS console work.  Upgrade to STORAGE_INTEGRATION later.
-- =============================================================================

-- ── Step 1: Schema ──────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS baseball_data.lakehouse_ext
    COMMENT = 'E11.1-W1 lakehouse external tables — Snowflake views over S3 Parquet';

-- ── Step 2: Parquet file format ──────────────────────────────────────────────

CREATE OR REPLACE FILE FORMAT baseball_data.lakehouse_ext.parquet_snappy
    TYPE = 'PARQUET'
    SNAPPY_COMPRESSION = TRUE
    COMMENT = 'E11.1-W1: parquet format for lakehouse external tables';

-- ── Step 3: External stage (replace key placeholders with real values) ───────
--
-- Operator: replace <AWS_ACCESS_KEY_ID> and <AWS_SECRET_ACCESS_KEY> below with
-- the values from your .env / environment (same keys the pipeline uses).

CREATE OR REPLACE STAGE baseball_data.lakehouse_ext.s3_lakehouse
    URL = 's3://baseball-betting-ml-artifacts/baseball/lakehouse/'
    CREDENTIALS = (
        AWS_KEY_ID     = '<AWS_ACCESS_KEY_ID>',
        AWS_SECRET_KEY = '<AWS_SECRET_ACCESS_KEY>'
    )
    FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
    COMMENT = 'E11.1-W1: S3 lakehouse stage for mart_pitch_* external tables';

-- Verify the stage sees the parquet files:
-- LIST @baseball_data.lakehouse_ext.s3_lakehouse;

-- ── Step 4: External tables ──────────────────────────────────────────────────
-- One external table per mart.  Column definitions use VALUE:<name>::<type> to
-- pull fields out of the parquet row VARIANT.  Types match the existing Snowflake
-- mart_pitch_* tables exactly (verified 2026-06-25 via INFORMATION_SCHEMA query).
-- DuckDB writes parquet column names in lowercase, so VALUE: accessors use lowercase.
--
-- AUTO_REFRESH = FALSE — the daily pipeline runs ALTER EXTERNAL TABLE ... REFRESH
-- via refresh_w1_external_tables.py after each S3 write.

-- ── mart_pitch_characteristics ───────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_characteristics (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    pitch_type                  VARCHAR      AS (VALUE:pitch_type::VARCHAR),
    pitch_name                  VARCHAR      AS (VALUE:pitch_name::VARCHAR),
    pitch_category              VARCHAR      AS (VALUE:pitch_category::VARCHAR),
    release_speed_mph           FLOAT        AS (VALUE:release_speed_mph::FLOAT),
    effective_speed_mph         FLOAT        AS (VALUE:effective_speed_mph::FLOAT),
    speed_vs_perceived_diff     FLOAT        AS (VALUE:speed_vs_perceived_diff::FLOAT),
    release_spin_rate_rpm       NUMBER(38,0) AS (VALUE:release_spin_rate_rpm::NUMBER(38,0)),
    spin_axis_degrees           NUMBER(38,0) AS (VALUE:spin_axis_degrees::NUMBER(38,0)),
    release_pos_x_ft            FLOAT        AS (VALUE:release_pos_x_ft::FLOAT),
    release_pos_y_ft            FLOAT        AS (VALUE:release_pos_y_ft::FLOAT),
    release_pos_z_ft            FLOAT        AS (VALUE:release_pos_z_ft::FLOAT),
    release_extension_ft        FLOAT        AS (VALUE:release_extension_ft::FLOAT),
    pitcher_arm_angle_degrees   FLOAT        AS (VALUE:pitcher_arm_angle_degrees::FLOAT),
    pitch_movement_x_ft         FLOAT        AS (VALUE:pitch_movement_x_ft::FLOAT),
    pitch_movement_z_ft         FLOAT        AS (VALUE:pitch_movement_z_ft::FLOAT),
    api_break_z_with_gravity_in FLOAT        AS (VALUE:api_break_z_with_gravity_in::FLOAT),
    api_break_x_arm_in          FLOAT        AS (VALUE:api_break_x_arm_in::FLOAT),
    api_break_x_batter_in       FLOAT        AS (VALUE:api_break_x_batter_in::FLOAT),
    vx0_fps                     FLOAT        AS (VALUE:vx0_fps::FLOAT),
    vy0_fps                     FLOAT        AS (VALUE:vy0_fps::FLOAT),
    vz0_fps                     FLOAT        AS (VALUE:vz0_fps::FLOAT),
    ax_fps2                     FLOAT        AS (VALUE:ax_fps2::FLOAT),
    ay_fps2                     FLOAT        AS (VALUE:ay_fps2::FLOAT),
    az_fps2                     FLOAT        AS (VALUE:az_fps2::FLOAT),
    plate_x_ft                  FLOAT        AS (VALUE:plate_x_ft::FLOAT),
    plate_z_ft                  FLOAT        AS (VALUE:plate_z_ft::FLOAT),
    strike_zone_top_ft          FLOAT        AS (VALUE:strike_zone_top_ft::FLOAT),
    strike_zone_bot_ft          FLOAT        AS (VALUE:strike_zone_bot_ft::FLOAT),
    pitch_zone                  NUMBER(38,0) AS (VALUE:pitch_zone::NUMBER(38,0)),
    is_in_zone                  BOOLEAN      AS (VALUE:is_in_zone::BOOLEAN),
    pitch_side                  VARCHAR      AS (VALUE:pitch_side::VARCHAR)
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_characteristics/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch physical characteristics from S3 lakehouse parquet';

-- ── mart_pitch_play_event ────────────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_play_event (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    pitch_result_code           VARCHAR      AS (VALUE:pitch_result_code::VARCHAR),
    pitch_description           VARCHAR      AS (VALUE:pitch_description::VARCHAR),
    plate_appearance_event      VARCHAR      AS (VALUE:plate_appearance_event::VARCHAR),
    plate_appearance_description VARCHAR     AS (VALUE:plate_appearance_description::VARCHAR),
    is_strike                   BOOLEAN      AS (VALUE:is_strike::BOOLEAN),
    is_ball                     BOOLEAN      AS (VALUE:is_ball::BOOLEAN),
    is_in_play                  BOOLEAN      AS (VALUE:is_in_play::BOOLEAN),
    is_swing_and_miss           BOOLEAN      AS (VALUE:is_swing_and_miss::BOOLEAN),
    is_swing                    BOOLEAN      AS (VALUE:is_swing::BOOLEAN),
    is_called_strike            BOOLEAN      AS (VALUE:is_called_strike::BOOLEAN),
    is_called_ball              BOOLEAN      AS (VALUE:is_called_ball::BOOLEAN),
    is_terminal_pitch           BOOLEAN      AS (VALUE:is_terminal_pitch::BOOLEAN),
    is_strikeout                BOOLEAN      AS (VALUE:is_strikeout::BOOLEAN),
    is_walk                     BOOLEAN      AS (VALUE:is_walk::BOOLEAN),
    is_hit_by_pitch             BOOLEAN      AS (VALUE:is_hit_by_pitch::BOOLEAN),
    is_hit                      BOOLEAN      AS (VALUE:is_hit::BOOLEAN),
    is_home_run                 BOOLEAN      AS (VALUE:is_home_run::BOOLEAN),
    is_on_base_event            BOOLEAN      AS (VALUE:is_on_base_event::BOOLEAN),
    is_out_event                BOOLEAN      AS (VALUE:is_out_event::BOOLEAN),
    error_on_play               BOOLEAN      AS (VALUE:error_on_play::BOOLEAN),
    error_type                  VARCHAR      AS (VALUE:error_type::VARCHAR),
    error_position              VARCHAR      AS (VALUE:error_position::VARCHAR),
    woba_value                  FLOAT        AS (VALUE:woba_value::FLOAT),
    woba_denom                  FLOAT        AS (VALUE:woba_denom::FLOAT),
    xwoba                       FLOAT        AS (VALUE:xwoba::FLOAT),
    delta_run_exp               FLOAT        AS (VALUE:delta_run_exp::FLOAT),
    delta_pitcher_run_exp       NUMBER(19,5) AS (VALUE:delta_pitcher_run_exp::NUMBER(19,5)),
    delta_home_win_exp          FLOAT        AS (VALUE:delta_home_win_exp::FLOAT)
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_play_event/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch play event outcomes from S3 lakehouse parquet';

-- ── mart_pitch_game_context ───────────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_game_context (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    game_type                   VARCHAR      AS (VALUE:game_type::VARCHAR),
    home_team                   VARCHAR      AS (VALUE:home_team::VARCHAR),
    away_team                   VARCHAR      AS (VALUE:away_team::VARCHAR),
    inning                      NUMBER(38,0) AS (VALUE:inning::NUMBER(38,0)),
    inning_half                 VARCHAR      AS (VALUE:inning_half::VARCHAR),
    outs_when_up                NUMBER(38,0) AS (VALUE:outs_when_up::NUMBER(38,0)),
    balls                       NUMBER(38,0) AS (VALUE:balls::NUMBER(38,0)),
    strikes                     NUMBER(38,0) AS (VALUE:strikes::NUMBER(38,0)),
    count_state                 VARCHAR      AS (VALUE:count_state::VARCHAR),
    count_leverage              VARCHAR      AS (VALUE:count_leverage::VARCHAR),
    base_state                  VARCHAR      AS (VALUE:base_state::VARCHAR),
    runner_on_1b                BOOLEAN      AS (VALUE:runner_on_1b::BOOLEAN),
    runner_on_2b                BOOLEAN      AS (VALUE:runner_on_2b::BOOLEAN),
    runner_on_3b                BOOLEAN      AS (VALUE:runner_on_3b::BOOLEAN),
    runners_on_base             BOOLEAN      AS (VALUE:runners_on_base::BOOLEAN),
    pre_pitch_home_score        NUMBER(38,0) AS (VALUE:pre_pitch_home_score::NUMBER(38,0)),
    pre_pitch_away_score        NUMBER(38,0) AS (VALUE:pre_pitch_away_score::NUMBER(38,0)),
    pre_pitch_bat_score         NUMBER(38,0) AS (VALUE:pre_pitch_bat_score::NUMBER(38,0)),
    pre_pitch_fld_score         NUMBER(38,0) AS (VALUE:pre_pitch_fld_score::NUMBER(38,0)),
    post_pitch_home_score       NUMBER(38,0) AS (VALUE:post_pitch_home_score::NUMBER(38,0)),
    post_pitch_away_score       NUMBER(38,0) AS (VALUE:post_pitch_away_score::NUMBER(38,0)),
    post_pitch_bat_score        NUMBER(38,0) AS (VALUE:post_pitch_bat_score::NUMBER(38,0)),
    post_pitch_fld_score        NUMBER(38,0) AS (VALUE:post_pitch_fld_score::NUMBER(38,0)),
    home_score_diff             NUMBER(38,0) AS (VALUE:home_score_diff::NUMBER(38,0)),
    bat_score_diff              NUMBER(38,0) AS (VALUE:bat_score_diff::NUMBER(38,0)),
    pre_pitch_home_win_exp      FLOAT        AS (VALUE:pre_pitch_home_win_exp::FLOAT),
    pre_pitch_bat_win_exp       FLOAT        AS (VALUE:pre_pitch_bat_win_exp::FLOAT),
    delta_home_win_exp          FLOAT        AS (VALUE:delta_home_win_exp::FLOAT),
    delta_run_exp               FLOAT        AS (VALUE:delta_run_exp::FLOAT),
    delta_pitcher_run_exp       NUMBER(19,5) AS (VALUE:delta_pitcher_run_exp::NUMBER(19,5))
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_game_context/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch game context from S3 lakehouse parquet';

-- ── mart_pitch_fielding ───────────────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_fielding (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    if_fielding_alignment       VARCHAR      AS (VALUE:if_fielding_alignment::VARCHAR),
    of_fielding_alignment       VARCHAR      AS (VALUE:of_fielding_alignment::VARCHAR),
    is_infield_shift            BOOLEAN      AS (VALUE:is_infield_shift::BOOLEAN),
    is_infield_shade            BOOLEAN      AS (VALUE:is_infield_shade::BOOLEAN),
    is_infield_strategic        BOOLEAN      AS (VALUE:is_infield_strategic::BOOLEAN),
    is_infield_non_standard     BOOLEAN      AS (VALUE:is_infield_non_standard::BOOLEAN),
    is_outfield_extreme_shift   BOOLEAN      AS (VALUE:is_outfield_extreme_shift::BOOLEAN),
    is_fourth_outfielder        BOOLEAN      AS (VALUE:is_fourth_outfielder::BOOLEAN),
    is_outfield_strategic       BOOLEAN      AS (VALUE:is_outfield_strategic::BOOLEAN),
    is_outfield_non_standard    BOOLEAN      AS (VALUE:is_outfield_non_standard::BOOLEAN),
    is_any_shade_or_shift       BOOLEAN      AS (VALUE:is_any_shade_or_shift::BOOLEAN),
    catcher_id                  NUMBER(38,0) AS (VALUE:catcher_id::NUMBER(38,0)),
    first_base_id               NUMBER(38,0) AS (VALUE:first_base_id::NUMBER(38,0)),
    second_base_id              NUMBER(38,0) AS (VALUE:second_base_id::NUMBER(38,0)),
    third_base_id               NUMBER(38,0) AS (VALUE:third_base_id::NUMBER(38,0)),
    shortstop_id                NUMBER(38,0) AS (VALUE:shortstop_id::NUMBER(38,0)),
    left_field_id               NUMBER(38,0) AS (VALUE:left_field_id::NUMBER(38,0)),
    center_field_id             NUMBER(38,0) AS (VALUE:center_field_id::NUMBER(38,0)),
    right_field_id              NUMBER(38,0) AS (VALUE:right_field_id::NUMBER(38,0))
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_fielding/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch fielding alignment from S3 lakehouse parquet';

-- ── mart_pitch_hitter_profile ─────────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_hitter_profile (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    batter_first_name           VARCHAR      AS (VALUE:batter_first_name::VARCHAR),
    batter_last_name            VARCHAR      AS (VALUE:batter_last_name::VARCHAR),
    batter_name                 VARCHAR      AS (VALUE:batter_name::VARCHAR),
    batter_hand                 VARCHAR      AS (VALUE:batter_hand::VARCHAR),
    batter_age                  NUMBER(38,0) AS (VALUE:batter_age::NUMBER(38,0)),
    batter_age_legacy           NUMBER(38,0) AS (VALUE:batter_age_legacy::NUMBER(38,0)),
    pitcher_hand                VARCHAR      AS (VALUE:pitcher_hand::VARCHAR),
    matchup_handedness          VARCHAR      AS (VALUE:matchup_handedness::VARCHAR),
    batter_prior_pas_this_game  NUMBER(38,0) AS (VALUE:batter_prior_pas_this_game::NUMBER(38,0)),
    batter_days_since_prev_game FLOAT        AS (VALUE:batter_days_since_prev_game::FLOAT),
    batter_days_until_next_game FLOAT        AS (VALUE:batter_days_until_next_game::FLOAT),
    runner_on_1b_id             NUMBER(38,0) AS (VALUE:runner_on_1b_id::NUMBER(38,0)),
    runner_on_2b_id             NUMBER(38,0) AS (VALUE:runner_on_2b_id::NUMBER(38,0)),
    runner_on_3b_id             NUMBER(38,0) AS (VALUE:runner_on_3b_id::NUMBER(38,0))
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_hitter_profile/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch hitter profile from S3 lakehouse parquet';

-- ── mart_pitch_pitcher_profile ────────────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_pitcher_profile (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    pitcher_first_name          VARCHAR      AS (VALUE:pitcher_first_name::VARCHAR),
    pitcher_last_name           VARCHAR      AS (VALUE:pitcher_last_name::VARCHAR),
    pitcher_name                VARCHAR      AS (VALUE:pitcher_name::VARCHAR),
    pitcher_hand                VARCHAR      AS (VALUE:pitcher_hand::VARCHAR),
    pitcher_age                 NUMBER(38,0) AS (VALUE:pitcher_age::NUMBER(38,0)),
    pitcher_age_legacy          NUMBER(38,0) AS (VALUE:pitcher_age_legacy::NUMBER(38,0)),
    pitcher_times_thru_order    NUMBER(38,0) AS (VALUE:pitcher_times_thru_order::NUMBER(38,0)),
    pitcher_days_since_prev_game NUMBER(38,0) AS (VALUE:pitcher_days_since_prev_game::NUMBER(38,0)),
    pitcher_days_until_next_game FLOAT        AS (VALUE:pitcher_days_until_next_game::FLOAT),
    pitcher_rest_bucket         VARCHAR      AS (VALUE:pitcher_rest_bucket::VARCHAR)
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_pitcher_profile/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: pitch pitcher profile from S3 lakehouse parquet';

-- ── mart_pitch_hit_characteristics ───────────────────────────────────────────
CREATE OR REPLACE EXTERNAL TABLE baseball_data.lakehouse_ext.mart_pitch_hit_characteristics (
    pitch_sk                    NUMBER(38,0) AS (VALUE:pitch_sk::NUMBER(38,0)),
    game_pk                     NUMBER(38,0) AS (VALUE:game_pk::NUMBER(38,0)),
    game_date                   DATE         AS (VALUE:game_date::DATE),
    game_year                   NUMBER(38,0) AS (VALUE:game_year::NUMBER(38,0)),
    at_bat_number               NUMBER(38,0) AS (VALUE:at_bat_number::NUMBER(38,0)),
    pitch_number                NUMBER(38,0) AS (VALUE:pitch_number::NUMBER(38,0)),
    pitcher_id                  NUMBER(38,0) AS (VALUE:pitcher_id::NUMBER(38,0)),
    batter_id                   NUMBER(38,0) AS (VALUE:batter_id::NUMBER(38,0)),
    batted_ball_type            VARCHAR      AS (VALUE:batted_ball_type::VARCHAR),
    launch_speed_angle_zone     NUMBER(38,0) AS (VALUE:launch_speed_angle_zone::NUMBER(38,0)),
    contact_quality             VARCHAR      AS (VALUE:contact_quality::VARCHAR),
    exit_velocity_mph           FLOAT        AS (VALUE:exit_velocity_mph::FLOAT),
    launch_angle_degrees        FLOAT        AS (VALUE:launch_angle_degrees::FLOAT),
    hit_distance_ft             FLOAT        AS (VALUE:hit_distance_ft::FLOAT),
    is_barrel                   BOOLEAN      AS (VALUE:is_barrel::BOOLEAN),
    is_hard_hit                 BOOLEAN      AS (VALUE:is_hard_hit::BOOLEAN),
    is_sweet_spot               BOOLEAN      AS (VALUE:is_sweet_spot::BOOLEAN),
    is_hard_hit_sweet_spot      BOOLEAN      AS (VALUE:is_hard_hit_sweet_spot::BOOLEAN),
    hit_coord_x                 FLOAT        AS (VALUE:hit_coord_x::FLOAT),
    hit_coord_y                 FLOAT        AS (VALUE:hit_coord_y::FLOAT),
    hit_location_fielder        NUMBER(38,0) AS (VALUE:hit_location_fielder::NUMBER(38,0)),
    xba                         FLOAT        AS (VALUE:xba::FLOAT),
    xwoba                       FLOAT        AS (VALUE:xwoba::FLOAT),
    xslg                        FLOAT        AS (VALUE:xslg::FLOAT),
    woba_value                  FLOAT        AS (VALUE:woba_value::FLOAT),
    woba_denom                  FLOAT        AS (VALUE:woba_denom::FLOAT),
    babip_value                 FLOAT        AS (VALUE:babip_value::FLOAT),
    iso_value                   FLOAT        AS (VALUE:iso_value::FLOAT),
    bat_speed_mph               FLOAT        AS (VALUE:bat_speed_mph::FLOAT),
    swing_length_ft             FLOAT        AS (VALUE:swing_length_ft::FLOAT),
    attack_angle_degrees        FLOAT        AS (VALUE:attack_angle_degrees::FLOAT),
    attack_direction_degrees    FLOAT        AS (VALUE:attack_direction_degrees::FLOAT),
    swing_path_tilt_degrees     FLOAT        AS (VALUE:swing_path_tilt_degrees::FLOAT),
    hyper_speed                 FLOAT        AS (VALUE:hyper_speed::FLOAT),
    intercept_offset_x_inches   FLOAT        AS (VALUE:intercept_offset_x_inches::FLOAT),
    intercept_offset_y_inches   FLOAT        AS (VALUE:intercept_offset_y_inches::FLOAT),
    is_fast_swing               BOOLEAN      AS (VALUE:is_fast_swing::BOOLEAN),
    is_ideal_attack_angle       BOOLEAN      AS (VALUE:is_ideal_attack_angle::BOOLEAN)
)
WITH LOCATION = @baseball_data.lakehouse_ext.s3_lakehouse/mart_pitch_hit_characteristics/
FILE_FORMAT = baseball_data.lakehouse_ext.parquet_snappy
AUTO_REFRESH = FALSE
COMMENT = 'E11.1-W1: batted ball / hit characteristics from S3 lakehouse parquet';

-- ── Verification queries (run after CREATE to confirm data visible) ──────────
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_characteristics;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_play_event;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_game_context;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_fielding;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_hitter_profile;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_pitcher_profile;
-- SELECT COUNT(*) FROM baseball_data.lakehouse_ext.mart_pitch_hit_characteristics;

-- ── ROLLBACK (if S3 serving wobbles after decommission) ──────────────────────
-- Re-enable the Snowflake incremental builds in dbt_project.yml:
--   Under models.baseball_betting_and_fantasy.mart:
--     mart_pitch_characteristics: {+enabled: true, +tags: []}
--   (repeat for all 7)
-- Re-add mart_pitch_* to the dbt build (remove --exclude tag:w1_lakehouse from
--   _dbt_daily_build_args() in pipeline/ops/daily_ingestion_ops.py).
-- Move ingest_statcast_to_s3_op + run_w1_lakehouse_op back to the dead-end tail
--   in daily_ingestion_job.py (restore soft-fail WARN tier).
-- Run: dbtf run --select mart_pitch_*  (rebuild from Snowflake stg_batter_pitches)

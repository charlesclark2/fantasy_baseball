-- =============================================================================
-- stg_batter_pitches.sql
-- Source: baseball_data.savant.batter_pitches
-- Grain: one row per pitch per plate appearance per game
-- Purpose: Rename to snake_case, cast types, document all fields,
--          drop deprecated columns, and add surrogate key.
--
-- Materialization: incremental (delete+insert) partitioned on game_date. The
-- source is 7.6M+ pitches back to 2015; a full CTAS re-scans the entire history
-- every run (~58s, a top dbt-run choke point). Each incremental run only reads
-- and replaces the trailing `batter_pitches_lookback_days` window (default 14),
-- which re-absorbs late Statcast revisions (xwOBA, bat tracking, etc.) for
-- recently-played games. delete+insert keyed on game_date deletes exactly the
-- window's dates and re-inserts them — a game_pk maps to a single game_date, so
-- pitch_sk stays unique across the whole table. The complete 2015→present
-- history is retained for the ~30 downstream marts that scan it. Use
-- `--full-refresh` (after DROP) to rebuild from scratch.
-- =============================================================================

{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='game_date',
        on_schema_change='append_new_columns'
    )
}}

with

source as (

    select * from {{ source('savant', 'batter_pitches') }}
    {% if is_incremental() %}
    where game_date >= dateadd('day', -{{ var('batter_pitches_lookback_days', 14) }}, current_date)
    {% endif %}

),

renamed as (

    select
        -- -----------------------------------------------------------------------
        -- Game identifiers
        -- -----------------------------------------------------------------------
        game_pk::integer                                    as game_pk,
            -- Unique MLB game identifier

        game_date::date                                     as game_date,
            -- Date of the game

        game_year::integer                                  as game_year,
            -- Season year the game took place

        game_type                                           as game_type,
            -- E=Exhibition, S=Spring Training, R=Regular Season,
            -- F=Wild Card, D=Division Series, L=LCS, W=World Series

        home_team                                           as home_team,
            -- Abbreviation of the home team

        away_team                                           as away_team,
            -- Abbreviation of the away team

        inning::integer                                     as inning,
            -- Pre-pitch inning number

        inning_topbot                                       as inning_half,
            -- "Top" or "Bot" — which half of the inning

        -- -----------------------------------------------------------------------
        -- Plate appearance context
        -- -----------------------------------------------------------------------
        at_bat_number::integer                              as at_bat_number,
            -- Sequential plate appearance number within the game

        pitch_number::integer                               as pitch_number,
            -- Pitch sequence number within the current plate appearance

        balls::integer                                      as balls,
            -- Pre-pitch ball count

        strikes::integer                                    as strikes,
            -- Pre-pitch strike count

        outs_when_up::integer                               as outs_when_up,
            -- Pre-pitch number of outs in the inning

        on_1b::integer                                      as runner_on_1b_id,
            -- Pre-pitch MLB Player ID of runner on 1st base (null if empty)

        on_2b::integer                                      as runner_on_2b_id,
            -- Pre-pitch MLB Player ID of runner on 2nd base (null if empty)

        on_3b::integer                                      as runner_on_3b_id,
            -- Pre-pitch MLB Player ID of runner on 3rd base (null if empty)

        -- -----------------------------------------------------------------------
        -- Player identifiers & handedness
        -- -----------------------------------------------------------------------
        batter::integer                                     as batter_id,
            -- MLB Player ID for the batter

        pitcher::integer                                    as pitcher_id,
            -- MLB Player ID for the pitcher

        player_name                                         as player_name,
            -- Player name tied to the search event (typically the pitcher)

        stand                                               as batter_hand,
            -- Side of plate batter stands: L or R

        p_throws                                            as pitcher_hand,
            -- Pitching hand: L or R

        -- -----------------------------------------------------------------------
        -- Fielder IDs at time of pitch
        -- -----------------------------------------------------------------------
        fielder_2::integer                                  as catcher_id,
        fielder_3::integer                                  as first_base_id,
        fielder_4::integer                                  as second_base_id,
        fielder_5::integer                                  as third_base_id,
        fielder_6::integer                                  as shortstop_id,
        fielder_7::integer                                  as left_field_id,
        fielder_8::integer                                  as center_field_id,
        fielder_9::integer                                  as right_field_id,

        -- -----------------------------------------------------------------------
        -- Pitch classification
        -- -----------------------------------------------------------------------
        pitch_type                                          as pitch_type,
            -- Statcast pitch type abbreviation (FF, SL, CH, CU, etc.)

        pitch_name                                          as pitch_name,
            -- Human-readable pitch name (4-Seam Fastball, Slider, etc.)

        -- -----------------------------------------------------------------------
        -- Pitch result / play outcome
        -- -----------------------------------------------------------------------
        type                                                as pitch_result_code,
            -- B=Ball, S=Strike, X=In Play

        description                                         as pitch_description,
            -- Verbose description of pitch outcome (called_strike, swinging_strike, etc.)

        events                                              as plate_appearance_event,
            -- Terminal plate appearance result if this was the last pitch
            -- (single, strikeout, home_run, walk, etc.); null on non-terminal pitches

        des                                                 as plate_appearance_description,
            -- Full game-day text description of the plate appearance

        zone::integer                                       as pitch_zone,
            -- Strike zone region (1-9 = zone, 11-14 = out of zone) from catcher's POV

        -- -----------------------------------------------------------------------
        -- Pitch physics — release point
        -- -----------------------------------------------------------------------
        release_speed::float                                as release_speed_mph,
            -- Pitch velocity out of hand (mph). Pre-2017: PitchF/X adjusted;
            -- 2017+: Statcast

        effective_speed::float                              as effective_speed_mph,
            -- Velocity adjusted for pitcher's extension — what the batter perceives

        release_pos_x::float                                as release_pos_x_ft,
            -- Horizontal release position in feet from catcher's perspective

        release_pos_y::float                                as release_pos_y_ft,
            -- Depth of release from home plate in feet

        release_pos_z::float                                as release_pos_z_ft,
            -- Vertical release height in feet from catcher's perspective

        release_extension::float                            as release_extension_ft,
            -- How far off the mound (in feet) the pitcher releases the ball

        release_spin_rate::integer                          as release_spin_rate_rpm,
            -- Spin rate at release in revolutions per minute

        spin_axis::integer                                  as spin_axis_degrees,
            -- Spin axis in degrees (0-360); 180 = pure backspin, 0 = pure topspin

        -- -----------------------------------------------------------------------
        -- Pitch physics — movement & trajectory
        -- -----------------------------------------------------------------------
        pfx_x::float                                        as pitch_movement_x_ft,
            -- Horizontal pitch movement in feet (catcher's POV)

        pfx_z::float                                        as pitch_movement_z_ft,
            -- Vertical pitch movement in feet (catcher's POV)

        plate_x::float                                      as plate_x_ft,
            -- Horizontal position at home plate crossing (catcher's POV)

        plate_z::float                                      as plate_z_ft,
            -- Vertical position at home plate crossing (catcher's POV)

        sz_top::float                                       as strike_zone_top_ft,
            -- Top of the batter's strike zone (measured when ball is halfway to plate)

        sz_bot::float                                       as strike_zone_bot_ft,
            -- Bottom of the batter's strike zone

        -- Kinematic parameters measured at y=50 ft reference plane
        vx0::float                                          as vx0_fps,
            -- Pitch velocity in x-dimension at y=50 ft (ft/sec)

        vy0::float                                          as vy0_fps,
            -- Pitch velocity in y-dimension at y=50 ft (ft/sec)

        vz0::float                                          as vz0_fps,
            -- Pitch velocity in z-dimension at y=50 ft (ft/sec)

        ax::float                                           as ax_fps2,
            -- Pitch acceleration in x-dimension at y=50 ft (ft/sec²)

        ay::float                                           as ay_fps2,
            -- Pitch acceleration in y-dimension at y=50 ft (ft/sec²)

        az::float                                           as az_fps2,
            -- Pitch acceleration in z-dimension at y=50 ft (ft/sec²)

        -- API break fields — added by Statcast API exports, not in legacy CSV docs
        api_break_z_with_gravity::float                     as api_break_z_with_gravity_in,
            -- Vertical break including gravity effect (inches). Reflects true drop
            -- of the pitch relative to a gravity-only trajectory.

        api_break_x_arm::float                              as api_break_x_arm_in,
            -- Horizontal break from arm-side perspective (inches). Positive = arm side.

        api_break_x_batter_in::float                        as api_break_x_batter_in,
            -- Horizontal break from the batter's perspective (inches).
            -- Sign convention: positive = moving in toward a same-handed batter.

        arm_angle::float                                    as pitcher_arm_angle_degrees,
            -- Pitcher's arm angle at release in degrees. Lower values = more sidearm;
            -- higher values = more over-the-top. Aligns with Savant Arm Angle leaderboard.

        -- -----------------------------------------------------------------------
        -- Batted ball tracking
        -- -----------------------------------------------------------------------
        hc_x::float                                         as hit_coord_x,
            -- Hit coordinate X of the batted ball (field diagram pixel space)

        hc_y::float                                         as hit_coord_y,
            -- Hit coordinate Y of the batted ball (field diagram pixel space)

        hit_location::integer                               as hit_location_fielder,
            -- Jersey position number of the first fielder to touch the ball

        bb_type                                             as batted_ball_type,
            -- ground_ball, line_drive, fly_ball, popup

        hit_distance_sc::float                              as hit_distance_ft,
            -- Projected hit distance of the batted ball in feet

        launch_speed::float                                 as exit_velocity_mph,
            -- Exit velocity of batted ball (mph)

        launch_angle::float                                 as launch_angle_degrees,
            -- Launch angle of batted ball (degrees)

        launch_speed_angle::integer                         as launch_speed_angle_zone,
            -- Contact quality zone: 1=Weak, 2=Topped, 3=Under,
            -- 4=Flare/Burner, 5=Solid Contact, 6=Barrel

        -- -----------------------------------------------------------------------
        -- Expected / advanced metrics
        -- -----------------------------------------------------------------------
        estimated_ba_using_speedangle::float                as xba,
            -- Expected Batting Average based on exit velo + launch angle

        estimated_woba_using_speedangle::float              as xwoba,
            -- Expected wOBA based on exit velo + launch angle

        estimated_slg_using_speedangle::float               as xslg,
            -- Expected SLG based on exit velo + launch angle.
            -- Not in legacy CSV docs; added in newer Statcast API exports.

        woba_value::float                                   as woba_value,
            -- Realized wOBA value based on actual play result

        woba_denom::float                                   as woba_denom,
            -- wOBA denominator (1 if PA counts, 0 if not — e.g., IBB, sac bunt)

        babip_value::float                                  as babip_value,
            -- BABIP value: 1 if hit (excl. HR), 0 if out, null otherwise

        iso_value::float                                    as iso_value,
            -- Isolated power value based on play result

        -- -----------------------------------------------------------------------
        -- Win/run expectancy
        -- -----------------------------------------------------------------------
        home_win_exp::float                                 as pre_pitch_home_win_exp,
            -- Home team win expectancy before the pitch (0–1).
            -- Not in legacy CSV docs; standard Statcast API field.

        bat_win_exp::float                                  as pre_pitch_bat_win_exp,
            -- Batting team win expectancy before the pitch (0–1).
            -- Not in legacy CSV docs; standard Statcast API field.

        delta_home_win_exp::float                           as delta_home_win_exp,
            -- Change in home team win expectancy for the plate appearance

        delta_run_exp::float                                as delta_run_exp,
            -- Change in run expectancy for the pitch

        delta_run_exp * -1.0                                as delta_pitcher_run_exp,
            -- Run expectancy delta from the pitcher's perspective
            -- (inverse of delta_run_exp). Matches delta_pitcher_run_exp source column.

        -- -----------------------------------------------------------------------
        -- Score context
        -- -----------------------------------------------------------------------
        home_score::integer                                 as pre_pitch_home_score,
        away_score::integer                                 as pre_pitch_away_score,
        bat_score::integer                                  as pre_pitch_bat_score,
        fld_score::integer                                  as pre_pitch_fld_score,

        post_home_score::integer                            as post_pitch_home_score,
        post_away_score::integer                            as post_pitch_away_score,
        post_bat_score::integer                             as post_pitch_bat_score,
        post_fld_score::integer                             as post_pitch_fld_score,

        home_score_diff::integer                            as home_score_diff,
            -- Score differential from home team's perspective (pre-pitch).
            -- Not in legacy CSV docs; derived field included in Statcast API exports.

        bat_score_diff::integer                             as bat_score_diff,
            -- Score differential from batting team's perspective (pre-pitch).
            -- Not in legacy CSV docs; derived field included in Statcast API exports.

        -- -----------------------------------------------------------------------
        -- Bat tracking (2023+)
        -- -----------------------------------------------------------------------
        bat_speed::float                                    as bat_speed_mph,
            -- Bat speed at the sweet spot (mph). Top 90% of swings averaged per player.
            -- Available from 2023 season onward.

        swing_length::float                                 as swing_length_ft,
            -- Total distance (ft) the bat head travels from tracking start to contact.

        attack_angle::float                                 as attack_angle_degrees,
            -- Vertical angle of bat sweet spot at point of contact (degrees).
            -- Positive = upswing, negative = downswing.

        attack_direction::float                             as attack_direction_degrees,
            -- Horizontal angle of bat at contact relative to pull/oppo direction.

        swing_path_tilt::float                              as swing_path_tilt_degrees,
            -- Vertical angle of the swing arc over the 40ms prior to contact.
            -- Higher = steeper swing, lower = flatter.

        hyper_speed::float                                  as hyper_speed,
            -- Internal Statcast bat tracking metric related to bat speed.
            -- Not publicly documented; likely a speed derivative used in
            -- quality-of-contact models.

        -- -----------------------------------------------------------------------
        -- Batter intercept / stance metrics (2024+)
        -- -----------------------------------------------------------------------
        intercept_ball_minus_batter_pos_x_inches::float     as intercept_offset_x_inches,
            -- Horizontal distance (inches) between where the ball crosses the plate
            -- and the batter's contact-point position. Used in batting stance analysis.
            -- Not in legacy CSV docs; part of Savant's batting stance/intercept feature.

        intercept_ball_minus_batter_pos_y_inches::float     as intercept_offset_y_inches,
            -- Vertical (depth) distance (inches) between ball and batter intercept point.
            -- Companion to intercept_offset_x_inches. Same source/vintage.

        -- -----------------------------------------------------------------------
        -- Fielding alignment
        -- -----------------------------------------------------------------------
        if_fielding_alignment                               as if_fielding_alignment,
            -- Infield alignment (Standard, Shift, Strategic, etc.)

        of_fielding_alignment                               as of_fielding_alignment,
            -- Outfield alignment

        -- -----------------------------------------------------------------------
        -- Age & pitcher usage context
        -- -----------------------------------------------------------------------
        age_pit::integer                                    as pitcher_age,
            -- Pitcher age during the season (current calculation method).

        age_bat::integer                                    as batter_age,
            -- Batter age during the season (current calculation method).

        age_pit_legacy::integer                             as pitcher_age_legacy,
            -- Pitcher age using the legacy MLB calculation (as of June 30).

        age_bat_legacy::integer                             as batter_age_legacy,
            -- Batter age using the legacy MLB calculation.

        n_thruorder_pitcher::integer                        as pitcher_times_thru_order,
            -- How many times the pitcher has been through the batting order in this game.

        n_priorpa_thisgame_player_at_bat::integer           as batter_prior_pas_this_game,
            -- Number of plate appearances the batter has had earlier in this game.

        pitcher_days_since_prev_game::integer               as pitcher_days_since_prev_game,
            -- Calendar days since the pitcher last appeared in a game.

        batter_days_since_prev_game::float                  as batter_days_since_prev_game,
            -- Calendar days since the batter last appeared in a game.

        pitcher_days_until_next_game::float                 as pitcher_days_until_next_game,
            -- Calendar days until the pitcher's next game appearance.

        batter_days_until_next_game::float                  as batter_days_until_next_game,
            -- Calendar days until the batter's next game appearance.

        -- -----------------------------------------------------------------------
        -- Deprecated / legacy columns — retained as null aliases for lineage
        -- traceability; exclude from downstream models.
        -- -----------------------------------------------------------------------
        null::float                                         as _deprecated_spin_dir,
        null::float                                         as _deprecated_spin_rate,
        null::float                                         as _deprecated_break_angle,
        null::float                                         as _deprecated_break_length,
        null::float                                         as _deprecated_tfs,
        null::float                                         as _deprecated_tfs_zulu,
        null::float                                         as _deprecated_umpire,
        null::float                                         as _deprecated_sv_id

        -- NOTE: delta_pitcher_run_exp is derived above from delta_run_exp * -1.
        -- The source column is retained there rather than as a passthrough to avoid
        -- confusion with the derived alias.

    from source

)

select 
        -- -----------------------------------------------------------------------
        -- Surrogate key
        -- Pitch is uniquely identified by game + at-bat + pitch sequence number.
        -- game_pk + at_bat_number + pitch_number should be unique per row, but
        -- sv_id (play event id) is non-unique per game, so we derive our own key.
        -- -----------------------------------------------------------------------
    md5_number_upper64(
        concat(
            game_pk::varchar,
            at_bat_number::int::varchar,
            batter_id::int::varchar, 
            pitch_number::int::varchar, 
            pitcher_id::int::varchar, 
            inning_half::varchar
        )
    )                                                   as pitch_sk,
    * 
from renamed
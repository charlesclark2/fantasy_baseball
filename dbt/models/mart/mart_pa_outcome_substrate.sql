-- =============================================================================
-- mart_pa_outcome_substrate.sql
-- Grain: one row per plate appearance (game_pk × at_bat_number)
-- Purpose: Training substrate for E13.2 (PA-outcome model + Monte-Carlo sim).
--          Carries the ENTERING 24-state base-out context + score/inning +
--          batter/pitcher handedness + the PA result mapped to a multinomial
--          outcome label.
--
-- Cost posture (E11.1-W1): run with --target duckdb; reads stg_batter_pitches
-- which resolves to S3 Parquet on the duckdb target. Avoid Snowflake runs.
--
-- Entering state: pulled from the FIRST pitch of each PA (pitch_number = 1,
-- or MIN(pitch_number) in case of data gaps). At PA entry, balls = 0, strikes = 0.
--
-- PA outcome: pulled from the terminal pitch (plate_appearance_event is not null,
-- deduplicated by taking the last pitch_number per PA). Mapped to a 9-class
-- multinomial label: {1B, 2B, 3B, HR, BB, IBB, HBP, K, out, other}.
--
-- Leak-clean: historical record only. Any serving or eval consumer must filter
-- WHERE game_date < <target_date> before joining to player-level stats or
-- prior-season aggregates.
--
-- Gates: E13.2 (PA-outcome model), E13.10 (downstream enrichment).
-- =============================================================================

{{ config(materialized='table') }}

with

pitches as (

    select * from {{ ref('stg_batter_pitches') }}

),

-- First pitch number per PA — used to anchor the entering state
first_pitch_per_pa as (

    select
        game_pk,
        at_bat_number,
        min(pitch_number)   as first_pitch_number
    from pitches
    group by game_pk, at_bat_number

),

-- Entering state: context at the START of each plate appearance.
-- All columns sourced from the first pitch so they reflect the state BEFORE
-- any pitches were thrown in this PA. At PA entry, balls = 0, strikes = 0
-- (confirmed: pre-pitch count on pitch_number = 1 is always 0-0 in Statcast).
entering as (

    select
        p.game_pk,
        p.at_bat_number,

        -- Game identifiers
        p.game_date,
        p.game_year,
        p.game_type,
        p.home_team,
        p.away_team,

        -- Inning context at PA entry
        p.inning,
        p.inning_half,
        p.outs_when_up                                              as outs_at_entry,

        -- 8-way base state (matches mart_pitch_game_context convention)
        case when p.runner_on_1b_id is not null then '1' else '-' end
            || case when p.runner_on_2b_id is not null then '2' else '-' end
            || case when p.runner_on_3b_id is not null then '3' else '-' end
                                                                    as base_state,

        -- 24-state base × outs enum: '<base_state>|<outs>'
        -- e.g. '---|0' = no runners 0 out, '1-3|2' = corners 2 out
        (case when p.runner_on_1b_id is not null then '1' else '-' end
            || case when p.runner_on_2b_id is not null then '2' else '-' end
            || case when p.runner_on_3b_id is not null then '3' else '-' end)
            || '|' || p.outs_when_up::varchar                      as base_out_state,

        (p.runner_on_1b_id is not null)                            as runner_on_1b,
        (p.runner_on_2b_id is not null)                            as runner_on_2b,
        (p.runner_on_3b_id is not null)                            as runner_on_3b,

        -- Score context at PA entry (batting-team perspective)
        p.bat_score_diff                                            as entry_bat_score_diff,
        p.pre_pitch_home_score                                      as entry_home_score,
        p.pre_pitch_away_score                                      as entry_away_score,

        -- Player identifiers and handedness
        p.batter_id,
        p.pitcher_id,
        p.batter_hand,
        p.pitcher_hand,

        -- Platoon matchup: same = batter and pitcher share handedness (disadvantage for batter)
        case
            when p.batter_hand = p.pitcher_hand then 'same'
            when p.batter_hand is null or p.pitcher_hand is null   then null
            else 'opposite'
        end                                                         as platoon_matchup,

        -- Batter's PA count earlier in this game (useful for lineup-order features)
        p.batter_prior_pas_this_game,

        -- Pitcher's times through the order at PA entry
        p.pitcher_times_thru_order                                  as pitcher_times_thru_order_at_entry

    from pitches p
    inner join first_pitch_per_pa fpn
        on  p.game_pk       = fpn.game_pk
        and p.at_bat_number = fpn.at_bat_number
        and p.pitch_number  = fpn.first_pitch_number

),

-- Terminal pitch: carries the PA-ending event.
-- plate_appearance_event is non-null only on the last pitch of each PA.
-- Dedup via row_number in case (rarely) Statcast publishes a duplicate.
terminal_pitches as (

    select
        game_pk,
        at_bat_number,
        plate_appearance_event,
        woba_value,
        woba_denom,
        row_number() over (
            partition by game_pk, at_bat_number
            order by pitch_number desc
        )                                                           as rn
    from pitches
    where plate_appearance_event is not null

),

-- Map raw Statcast events to the 9+1 multinomial outcome label.
-- 'out' covers all ball-in-play outs, sacrifice plays, and errors that end a PA.
-- 'other' covers rare events (catcher interference, etc.) not in the main 9.
outcomes as (

    select
        game_pk,
        at_bat_number,
        plate_appearance_event                                      as raw_event,
        case plate_appearance_event
            when 'single'                           then '1B'
            when 'double'                           then '2B'
            when 'triple'                           then '3B'
            when 'home_run'                         then 'HR'
            when 'walk'                             then 'BB'
            when 'intent_walk'                      then 'IBB'
            when 'hit_by_pitch'                     then 'HBP'
            when 'strikeout'                        then 'K'
            when 'strikeout_double_play'            then 'K'
            when 'field_out'                        then 'out'
            when 'force_out'                        then 'out'
            when 'grounded_into_double_play'        then 'out'
            when 'double_play'                      then 'out'
            when 'triple_play'                      then 'out'
            when 'fielders_choice'                  then 'out'
            when 'fielders_choice_out'              then 'out'
            when 'sac_fly'                          then 'out'
            when 'sac_bunt'                         then 'out'
            when 'sac_fly_double_play'              then 'out'
            when 'sac_bunt_double_play'             then 'out'
            when 'field_error'                      then 'out'
            else                                         'other'
        end                                                         as pa_outcome_label,
        woba_value,
        woba_denom
    from terminal_pitches
    where rn = 1

),

final as (

    select
        -- Keys (unique together)
        e.game_pk,
        e.at_bat_number,

        -- Game metadata
        e.game_date,
        e.game_year,
        e.game_type,
        e.home_team,
        e.away_team,

        -- Inning / outs at PA entry
        e.inning,
        e.inning_half,
        e.outs_at_entry,

        -- Base state at PA entry
        e.base_state,
        e.base_out_state,
        e.runner_on_1b,
        e.runner_on_2b,
        e.runner_on_3b,

        -- Score context at PA entry
        e.entry_bat_score_diff,
        e.entry_home_score,
        e.entry_away_score,

        -- Players and handedness
        e.batter_id,
        e.pitcher_id,
        e.batter_hand,
        e.pitcher_hand,
        e.platoon_matchup,

        -- Game-state usage context
        e.batter_prior_pas_this_game,
        e.pitcher_times_thru_order_at_entry,

        -- PA outcome
        o.raw_event,
        o.pa_outcome_label,
        o.woba_value,
        o.woba_denom

    from entering e
    inner join outcomes o
        on  e.game_pk       = o.game_pk
        and e.at_bat_number = o.at_bat_number

)

select * from final

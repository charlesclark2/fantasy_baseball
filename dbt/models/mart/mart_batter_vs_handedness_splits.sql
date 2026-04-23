{{
    config(
        materialized='table'
    )
}}

-- Grain: batter_id × pitcher_hand × game_year.
-- One row per batter per pitcher handedness (L or R) per season.
-- Mirror of mart_pitcher_vs_handedness_splits from the hitter's perspective.
--
-- Together these two tables allow full platoon advantage assessment for every
-- batter-pitcher matchup: how this pitcher performs vs. a batter's handedness
-- combined with how this batter performs vs. the pitcher's throwing hand.
--
-- Key metric definitions:
--   Hard hit    — exit_velocity_mph >= 95 mph on a batted ball
--   Barrel      — launch_speed_angle_zone = 6 (Statcast barrel classification)
--   Batted ball — plate_appearance_event is an in-play event (single, double,
--                 triple, home_run, field_out, force_out, etc.)
--   AT-bat      — PA minus walk, intent_walk, hit_by_pitch, sac_fly,
--                 sac_fly_double_play, sac_bunt, sac_bunt_double_play,
--                 catcher_interf
--   OBP denom   — PA minus sac_bunt, sac_bunt_double_play, catcher_interf
--   Chase       — swing at a pitch in zone 11–14 (out of the strike zone)
--
-- Small-sample caution: rows with fewer than ~50 PA should be interpreted
-- carefully. No minimum PA filter is applied here — filter downstream.

with pitches as (
    select *
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and pitcher_hand in ('L', 'R')
),

pitches_tagged as (
    select
        batter_id,
        pitcher_hand,
        game_year,
        plate_appearance_event,
        woba_value,
        woba_denom,
        xwoba,
        exit_velocity_mph,
        launch_speed_angle_zone,
        pitch_zone,

        -- ── Swing / whiff flags ───────────────────────────────────────────────
        case when pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_bunt',
            'foul_tip', 'bunt_foul_tip', 'missed_bunt',
            'hit_into_play', 'hit_into_play_score', 'hit_into_play_no_out'
        ) then 1 else 0 end                                                 as is_swing,

        case when pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'
        ) then 1 else 0 end                                                 as is_whiff,

        -- ── Zone flags ────────────────────────────────────────────────────────
        case when pitch_zone between 11 and 14 then 1 else 0 end            as is_out_of_zone,
        case when pitch_zone between 1  and  9 then 1 else 0 end            as is_in_zone,

        -- ── PA outcome flags (used only on terminal pitch) ────────────────────
        case when plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end                                                 as is_strikeout,

        case when plate_appearance_event in (
            'walk', 'intent_walk'
        ) then 1 else 0 end                                                 as is_walk,

        case when plate_appearance_event = 'hit_by_pitch'
            then 1 else 0 end                                               as is_hbp,

        case when plate_appearance_event = 'single'    then 1 else 0 end    as is_single,
        case when plate_appearance_event = 'double'    then 1 else 0 end    as is_double,
        case when plate_appearance_event = 'triple'    then 1 else 0 end    as is_triple,
        case when plate_appearance_event = 'home_run'  then 1 else 0 end    as is_home_run,

        case when plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ) then 1 else 0 end                                                 as is_hit,

        -- Total bases for SLG
        case
            when plate_appearance_event = 'single'   then 1
            when plate_appearance_event = 'double'   then 2
            when plate_appearance_event = 'triple'   then 3
            when plate_appearance_event = 'home_run' then 4
            else 0
        end                                                                 as total_bases,

        -- AT-bat (excludes walk, HBP, sac fly, sac bunt, catcher interf)
        case when plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'catcher_interf'
        ) then 1 else 0 end                                                 as is_at_bat,

        -- OBP denominator (excludes sac bunt and catcher interf only)
        case when plate_appearance_event not in (
            'sac_bunt', 'sac_bunt_double_play', 'catcher_interf'
        ) then 1 else 0 end                                                 as is_obp_denom,

        -- On-base events (hits + walks + HBP)
        case when plate_appearance_event in (
            'single', 'double', 'triple', 'home_run',
            'walk', 'intent_walk', 'hit_by_pitch'
        ) then 1 else 0 end                                                 as is_on_base,

        -- Batted ball in play (excludes strikeouts, walks, HBP)
        case when plate_appearance_event in (
            'single', 'double', 'triple', 'home_run',
            'field_out', 'force_out', 'grounded_into_double_play',
            'double_play', 'triple_play', 'fielders_choice_out',
            'fielders_choice', 'field_error', 'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play', 'other_out'
        ) then 1 else 0 end                                                 as is_batted_ball,

        -- Quality of contact flags (on terminal pitch where exit velo is recorded)
        case when exit_velocity_mph >= 95               then 1 else 0 end   as is_hard_hit,
        case when launch_speed_angle_zone = 6           then 1 else 0 end   as is_barrel

    from pitches
),

-- ── Pitch-level aggregation ───────────────────────────────────────────────────
pitch_agg as (
    select
        batter_id,
        pitcher_hand,
        game_year,

        count(*)                                                            as pitches_seen,
        sum(is_swing)                                                       as swings,
        sum(is_whiff)                                                       as whiffs,
        sum(is_out_of_zone)                                                 as out_of_zone_pitches,
        sum(case when is_out_of_zone = 1
            then is_swing else 0 end)                                       as out_of_zone_swings,
        sum(is_in_zone)                                                     as in_zone_pitches,
        sum(case when is_in_zone = 1
            then is_swing else 0 end)                                       as in_zone_swings

    from pitches_tagged
    group by batter_id, pitcher_hand, game_year
),

-- ── PA-level aggregation (terminal pitch of each PA only) ─────────────────────
pa_agg as (
    select
        batter_id,
        pitcher_hand,
        game_year,

        count(*)                                                            as plate_appearances,
        sum(is_strikeout)                                                   as strikeouts,
        sum(is_walk)                                                        as walks,
        sum(is_hbp)                                                         as hit_by_pitch,
        sum(is_single)                                                      as singles,
        sum(is_double)                                                      as doubles,
        sum(is_triple)                                                      as triples,
        sum(is_home_run)                                                    as home_runs,
        sum(is_hit)                                                         as hits,
        sum(total_bases)                                                    as total_bases,
        sum(is_at_bat)                                                      as at_bats,
        sum(is_obp_denom)                                                   as obp_denom,
        sum(is_on_base)                                                     as on_base_events,
        sum(is_batted_ball)                                                 as batted_balls,
        sum(is_hard_hit)                                                    as hard_hits,
        sum(is_barrel)                                                      as barrels,

        -- wOBA components
        sum(woba_value)                                                     as woba_numerator,
        sum(woba_denom)                                                     as woba_denom,

        -- xwOBA components
        sum(case when woba_denom = 1
            then coalesce(xwoba, woba_value)
            else 0
        end)                                                                as xwoba_numerator,
        sum(woba_denom)                                                     as xwoba_denom

    from pitches_tagged
    where plate_appearance_event is not null
      and plate_appearance_event != 'truncated_pa'
    group by batter_id, pitcher_hand, game_year
)

select
    pa.batter_id,
    pa.pitcher_hand,
    pa.game_year,

    -- ── Volume ────────────────────────────────────────────────────────────────
    pa.plate_appearances,
    pa.at_bats,
    p.pitches_seen,
    pa.strikeouts,
    pa.walks,
    pa.hit_by_pitch,
    pa.singles,
    pa.doubles,
    pa.triples,
    pa.home_runs,
    pa.hits,
    pa.total_bases,
    pa.batted_balls,
    pa.hard_hits,
    pa.barrels,
    p.swings,
    p.whiffs,

    -- ── Outcome rates ─────────────────────────────────────────────────────────
    round(pa.strikeouts    / nullif(pa.plate_appearances, 0), 4)            as k_pct,
    round(pa.walks         / nullif(pa.plate_appearances, 0), 4)            as bb_pct,
    pa.obp_denom, 
    round(pa.on_base_events / nullif(pa.obp_denom, 0), 4)                  as obp,
    round(pa.total_bases   / nullif(pa.at_bats, 0), 4)                     as slg,
    round(
        pa.on_base_events / nullif(pa.obp_denom, 0) +
        pa.total_bases    / nullif(pa.at_bats, 0),
        4
    )                                                                       as ops,
    round(pa.woba_numerator  / nullif(pa.woba_denom, 0), 4)                as woba,
    round(pa.xwoba_numerator / nullif(pa.xwoba_denom, 0), 4)               as xwoba,

    -- ── Quality of contact rates ──────────────────────────────────────────────
    round(pa.hard_hits / nullif(pa.batted_balls, 0), 4)                    as hard_hit_pct,
    round(pa.barrels   / nullif(pa.batted_balls, 0), 4)                    as barrel_pct,

    -- ── Swing / whiff / discipline rates ─────────────────────────────────────
    round(p.swings     / nullif(p.pitches_seen, 0), 4)                     as swing_rate,
    round(p.whiffs     / nullif(p.swings, 0), 4)                           as whiff_rate,
    round(p.whiffs     / nullif(p.pitches_seen, 0), 4)                     as swinging_strike_rate,
    round(p.out_of_zone_swings / nullif(p.out_of_zone_pitches, 0), 4)      as chase_rate,
    round(p.in_zone_swings     / nullif(p.in_zone_pitches, 0), 4)          as zone_contact_rate

from pa_agg pa
inner join pitch_agg p
    on  pa.batter_id    = p.batter_id
    and pa.pitcher_hand = p.pitcher_hand
    and pa.game_year    = p.game_year

{{
    config(
        materialized='table'
    )
}}

-- Grain: pitcher_id × batter_hand × game_year.
-- One row per pitcher per batter handedness per season.
--
-- Pitch type buckets:
--   Fastball  — FF (4-seam), SI (sinker), FC (cutter)
--   Breaking  — SL (slider), CU (curveball), KC (knuckle curve), CS (slow curve),
--               SV (slurve), ST (sweeper), SC (screwball)
--   Offspeed  — CH (changeup), FS (split-finger), FO (forkball), EP (eephus)
--   Other     — KN, IN, PO, FA, AB, null (excluded from pitch mix percentages
--               but included in total_pitches)
--
-- Count situation definitions (pre-pitch balls–strikes):
--   pitcher_ahead — 0-2 or 1-2  (two strikes, at most one ball)
--   hitter_ahead  — 2-0, 3-0, or 3-1  (balls lead strikes by ≥ 2)
--   two_strike    — any count with 2 strikes (0-2, 1-2, 2-2, 3-2)
--
-- Small-sample caution: rows with fewer than ~50 PA should be interpreted
-- carefully. No minimum PA filter is applied in this model — filter downstream.

with pitches as (
    select *
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and batter_hand in ('L', 'R')
),

pitches_tagged as (
    select
        pitcher_id,
        batter_hand,
        game_year,
        plate_appearance_event,
        xwoba,
        woba_value,
        woba_denom,

        -- Swing / whiff flags
        case when pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_bunt',
            'foul_tip', 'bunt_foul_tip', 'missed_bunt',
            'hit_into_play', 'hit_into_play_score', 'hit_into_play_no_out'
        ) then 1 else 0 end                                                 as is_swing,

        case when pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'
        ) then 1 else 0 end                                                 as is_whiff,

        -- Pitch type classification
        case when pitch_type in ('FF', 'SI', 'FC')
            then 1 else 0 end                                               as is_fastball,
        case when pitch_type in ('SL', 'CU', 'KC', 'CS', 'SV', 'ST', 'SC')
            then 1 else 0 end                                               as is_breaking,
        case when pitch_type in ('CH', 'FS', 'FO', 'EP')
            then 1 else 0 end                                               as is_offspeed,

        -- Count situation flags (pre-pitch count)
        case when strikes = 2 and balls in (0, 1)
            then 1 else 0 end                                               as is_pitcher_ahead,
        case when balls in (2, 3) and balls > strikes
            then 1 else 0 end                                               as is_hitter_ahead,
        case when strikes = 2
            then 1 else 0 end                                               as is_two_strike

    from pitches
),

-- ── Pitch-level aggregation: whiff rate, pitch mix, count tendencies ──────────
pitch_agg as (
    select
        pitcher_id,
        batter_hand,
        game_year,

        count(*)                                                            as total_pitches,
        sum(is_swing)                                                       as swings,
        sum(is_whiff)                                                       as whiffs,

        -- Overall pitch mix counts
        sum(is_fastball)                                                    as fastball_pitches,
        sum(is_breaking)                                                    as breaking_pitches,
        sum(is_offspeed)                                                    as offspeed_pitches,

        -- Pitcher-ahead count (0-2, 1-2) pitch tendencies
        sum(is_pitcher_ahead)                                               as pitches_pitcher_ahead,
        sum(case when is_pitcher_ahead = 1 then is_fastball else 0 end)    as fastballs_pitcher_ahead,
        sum(case when is_pitcher_ahead = 1 then is_breaking else 0 end)    as breaking_pitcher_ahead,
        sum(case when is_pitcher_ahead = 1 then is_offspeed else 0 end)    as offspeed_pitcher_ahead,

        -- Hitter-ahead count (2-0, 3-0, 3-1) pitch tendencies
        sum(is_hitter_ahead)                                                as pitches_hitter_ahead,
        sum(case when is_hitter_ahead = 1 then is_fastball else 0 end)     as fastballs_hitter_ahead,
        sum(case when is_hitter_ahead = 1 then is_breaking else 0 end)     as breaking_hitter_ahead,
        sum(case when is_hitter_ahead = 1 then is_offspeed else 0 end)     as offspeed_hitter_ahead,

        -- Two-strike tendencies
        sum(is_two_strike)                                                  as pitches_two_strike,
        sum(case when is_two_strike = 1 then is_whiff else 0 end)          as whiffs_two_strike,
        sum(case when is_two_strike = 1 then is_fastball else 0 end)       as fastballs_two_strike,
        sum(case when is_two_strike = 1 then is_breaking else 0 end)       as breaking_two_strike,
        sum(case when is_two_strike = 1 then is_offspeed else 0 end)       as offspeed_two_strike

    from pitches_tagged
    group by pitcher_id, batter_hand, game_year
),

-- ── PA-level aggregation: K%, BB%, xwOBA (terminal pitch of each PA only) ────
pa_agg as (
    select
        pitcher_id,
        batter_hand,
        game_year,

        count(*)                                                            as plate_appearances,

        sum(case when plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end)                                               as strikeouts,

        sum(case when plate_appearance_event in (
            'walk', 'intent_walk'
        ) then 1 else 0 end)                                               as walks,

        sum(case when plate_appearance_event = 'hit_by_pitch'
            then 1 else 0 end)                                             as hit_by_pitch,

        sum(case when plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ) then 1 else 0 end)                                               as hits,

        sum(case when plate_appearance_event = 'home_run'
            then 1 else 0 end)                                             as home_runs,

        -- xwOBA: expected value for batted balls, actual for non-contact events
        sum(case when woba_denom = 1
            then coalesce(xwoba, woba_value)
            else 0
        end)                                                               as xwoba_numerator,
        sum(woba_denom)                                                    as xwoba_denom

    from pitches_tagged
    where plate_appearance_event is not null
    group by pitcher_id, batter_hand, game_year
)

select
    pa.pitcher_id,
    pa.batter_hand,
    pa.game_year,

    -- ── Volume ─────────────────────────────────────────────────────────────────
    pa.plate_appearances,
    p.total_pitches,
    pa.strikeouts,
    pa.walks,
    pa.hit_by_pitch,
    pa.hits,
    pa.home_runs,
    p.swings,
    p.whiffs,

    -- ── Outcome rates ──────────────────────────────────────────────────────────
    round(pa.strikeouts   / nullif(pa.plate_appearances, 0), 4)            as k_pct,
    round(pa.walks        / nullif(pa.plate_appearances, 0), 4)            as bb_pct,
    round(pa.home_runs    / nullif(pa.plate_appearances, 0), 4)            as hr_pct,
    round(pa.xwoba_numerator / nullif(pa.xwoba_denom, 0), 4)              as xwoba_against,

    -- ── Swing / whiff rates ────────────────────────────────────────────────────
    round(p.whiffs / nullif(p.swings, 0), 4)                              as whiff_rate,
    round(p.whiffs / nullif(p.total_pitches, 0), 4)                       as swinging_strike_rate,

    -- ── Overall pitch mix ──────────────────────────────────────────────────────
    round(p.fastball_pitches / nullif(p.total_pitches, 0), 4)             as fastball_pct,
    round(p.breaking_pitches / nullif(p.total_pitches, 0), 4)             as breaking_pct,
    round(p.offspeed_pitches / nullif(p.total_pitches, 0), 4)             as offspeed_pct,

    -- ── Pitcher-ahead count tendencies (0-2, 1-2) ─────────────────────────────
    p.pitches_pitcher_ahead,
    round(p.fastballs_pitcher_ahead / nullif(p.pitches_pitcher_ahead, 0), 4) as fastball_pct_pitcher_ahead,
    round(p.breaking_pitcher_ahead  / nullif(p.pitches_pitcher_ahead, 0), 4) as breaking_pct_pitcher_ahead,
    round(p.offspeed_pitcher_ahead  / nullif(p.pitches_pitcher_ahead, 0), 4) as offspeed_pct_pitcher_ahead,

    -- ── Hitter-ahead count tendencies (2-0, 3-0, 3-1) ────────────────────────
    p.pitches_hitter_ahead,
    round(p.fastballs_hitter_ahead / nullif(p.pitches_hitter_ahead, 0), 4)  as fastball_pct_hitter_ahead,
    round(p.breaking_hitter_ahead  / nullif(p.pitches_hitter_ahead, 0), 4)  as breaking_pct_hitter_ahead,
    round(p.offspeed_hitter_ahead  / nullif(p.pitches_hitter_ahead, 0), 4)  as offspeed_pct_hitter_ahead,

    -- ── Two-strike tendencies ─────────────────────────────────────────────────
    p.pitches_two_strike,
    round(p.whiffs_two_strike   / nullif(p.pitches_two_strike, 0), 4)      as whiff_rate_two_strike,
    round(p.fastballs_two_strike / nullif(p.pitches_two_strike, 0), 4)     as fastball_pct_two_strike,
    round(p.breaking_two_strike  / nullif(p.pitches_two_strike, 0), 4)     as breaking_pct_two_strike,
    round(p.offspeed_two_strike  / nullif(p.pitches_two_strike, 0), 4)     as offspeed_pct_two_strike

from pa_agg pa
inner join pitch_agg p
    on  pa.pitcher_id  = p.pitcher_id
    and pa.batter_hand = p.batter_hand
    and pa.game_year   = p.game_year

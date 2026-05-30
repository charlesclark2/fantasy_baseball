{{ config(materialized='table') }}

-- Grain: pitcher_id × game_year
-- One-row-per-pitcher-season profile vector for k-means pitcher archetype clustering (Card 7.2).
--
-- Joins mart_pitcher_arsenal_summary (pitch mix, velocity, movement, arm angle, Stuff+)
-- with season-level outcome metrics (K%, BB%, whiff rate, GB rate) from stg_batter_pitches.
-- Player birth_date joined from stg_statsapi_player_profiles for age_at_season_start
-- computation in Python (same pattern as mart_batter_profile_summary).
--
-- Season coverage: 2015+ — mart_pitcher_arsenal_summary extended from 2020 to 2015.
-- Statcast velocity and movement are ≥99% populated from 2015.
-- Stratum-B features (arm_angle, overall_stuff_plus) are NULL for 2015-2019; the
-- clustering script uses only stratum-A features to maintain a consistent feature space
-- across all seasons (same pattern as batter archetype stratum-A exclusion in Story 7.1).
--
-- Whiff rate denominator: total swings (swinging_strike + swinging_strike_blocked +
-- missed_bunt + foul + foul_tip + foul_bunt + hit_into_play + bunt_foul_tip).
-- Numerator: swinging_strike + swinging_strike_blocked + missed_bunt (true misses only).
--
-- Minimum 100 BF gate filters mop-up / very-short-stint pitchers. The arsenal mart
-- already requires ≥ 200 pitches; the 100 BF gate additionally ensures K%/BB%/whiff
-- estimates are based on enough plate appearances to be statistically meaningful.

with outcomes as (
    select
        pitcher_id,
        game_year,
        count(distinct concat(game_pk, '-', at_bat_number))                   as bf_count,

        -- K%: strikeouts / batters faced
        sum(case when plate_appearance_event in ('strikeout', 'strikeout_double_play')
                 then 1 else 0 end)::float
            / nullif(count(distinct concat(game_pk, '-', at_bat_number)), 0)  as k_pct,

        -- BB%: walks / batters faced
        sum(case when plate_appearance_event in ('walk', 'intent_walk')
                 then 1 else 0 end)::float
            / nullif(count(distinct concat(game_pk, '-', at_bat_number)), 0)  as bb_pct,

        -- Whiff rate: swinging strikes / total swings
        sum(case when pitch_description in
                ('swinging_strike', 'swinging_strike_blocked', 'missed_bunt')
                 then 1 else 0 end)::float
            / nullif(sum(case when pitch_description in (
                'swinging_strike', 'swinging_strike_blocked', 'missed_bunt',
                'foul', 'foul_tip', 'foul_bunt', 'hit_into_play', 'bunt_foul_tip'
            ) then 1 else 0 end), 0)                                          as whiff_pct,

        -- GB rate: ground balls / balls in play
        sum(case when batted_ball_type = 'ground_ball' then 1 else 0 end)::float
            / nullif(count(case when batted_ball_type is not null then 1 end), 0)
                                                                              as gb_pct

    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and game_year >= 2015
    group by pitcher_id, game_year
    having count(distinct concat(game_pk, '-', at_bat_number)) >= 100
),

player_info as (
    select
        player_id,
        birth_date
    from {{ ref('stg_statsapi_player_profiles') }}
)

select
    a.pitcher_id,
    a.game_year,
    o.bf_count,
    a.total_pitches,

    -- Pitch mix (family-level; sums to ~1.0)
    a.fastball_pct,
    a.breaking_pct,
    a.offspeed_pct,

    -- Velocity and physical pitch characteristics
    a.fb_avg_velocity,
    a.fb_arm_angle,
    a.fb_avg_hmov,
    a.fb_avg_vmov,
    a.brk_avg_hmov,
    a.brk_avg_vmov,

    -- Composite stuff quality (fully populated 2020+ — 0 nulls in mart)
    a.overall_stuff_plus,

    -- Outcome metrics from pitch-level data
    o.k_pct,
    o.bb_pct,
    o.whiff_pct,
    o.gb_pct,

    -- For age_at_season_start computation in Python
    p.birth_date

from {{ ref('mart_pitcher_arsenal_summary') }} a
inner join outcomes o
    on  o.pitcher_id = a.pitcher_id
    and o.game_year  = a.game_year
left join player_info p
    on  p.player_id = a.pitcher_id

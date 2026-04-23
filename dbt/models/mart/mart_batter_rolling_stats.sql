-- =============================================================================
-- mart_batter_rolling_stats.sql
-- Grain: one row per batter × game (regular season appearances only)
-- Purpose: Rolling batter performance statistics over 7/14/30-day and
--          season-to-date windows. Covers traditional rate stats (AVG, OBP,
--          SLG, OPS, wOBA), expected metrics (xwOBA, xBA, xSLG), batted-ball
--          quality (hard-hit rate, barrel rate), and plate-discipline metrics
--          (K%, BB%, whiff rate, swinging strike rate, chase rate).
-- Join keys: batter_id, game_date
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with

pitches as (

    select * from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Annotate every pitch with batting team and swing/contact discipline flags
-- ─────────────────────────────────────────────────────────────────────────────
pitches_tagged as (

    select
        game_pk,
        game_date,
        game_year,
        at_bat_number,
        pitch_number,
        batter_id,
        batter_hand,

        case when inning_half = 'Top' then away_team else home_team end  as batting_team,
        case when inning_half = 'Top' then home_team else away_team end  as opposing_team,

        plate_appearance_event,
        pitch_description,
        pitch_zone,

        exit_velocity_mph,
        launch_speed_angle_zone,
        xwoba,
        xba,
        xslg,
        woba_value,
        woba_denom,
        babip_value,
        iso_value,

        -- Swing: batter offered at the pitch
        (pitch_description in (
            'swinging_strike', 'swinging_strike_blocked',
            'foul', 'foul_bunt', 'foul_tip', 'bunt_foul_tip', 'missed_bunt',
            'hit_into_play', 'hit_into_play_score', 'hit_into_play_no_out'
        ))::boolean                                                         as is_swing,

        -- Whiff: swing and complete miss
        (pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'
        ))::boolean                                                         as is_whiff,

        -- Out-of-zone: Statcast zones 11-14; in-zone: 1-9
        (pitch_zone between 11 and 14)::boolean                             as is_out_of_zone,
        (pitch_zone between 1 and 9)::boolean                               as is_in_zone

    from pitches

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Plate-appearance level: terminal pitches only, traditional stat components
-- ─────────────────────────────────────────────────────────────────────────────
plate_appearances as (

    select
        game_pk,
        game_date,
        game_year,
        batter_id,
        batter_hand,
        batting_team,
        opposing_team,

        -- ── wOBA / xwOBA ───────────────────────────────────────────────────────
        woba_value,
        woba_denom,
        xwoba,
        xba,
        xslg,

        -- ── Outcome flags ──────────────────────────────────────────────────────

        -- Hit types
        (plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ))::boolean                                                         as is_hit,

        (plate_appearance_event = 'single')::boolean                        as is_single,
        (plate_appearance_event = 'double')::boolean                        as is_double,
        (plate_appearance_event = 'triple')::boolean                        as is_triple,
        (plate_appearance_event = 'home_run')::boolean                      as is_home_run,

        -- Walk / HBP
        (plate_appearance_event in ('walk', 'intent_walk'))::boolean        as is_walk,
        (plate_appearance_event = 'hit_by_pitch')::boolean                  as is_hbp,

        -- Strikeout
        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                                         as is_strikeout,

        -- At-bat denominator (excludes BB, IBB, HBP, SF, sac bunt, catcher interf)
        (plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'catcher_interf'
        ))::boolean                                                         as is_at_bat,

        -- OBP denominator: AB + BB + HBP + SF (excludes sac bunt, catcher interf)
        (plate_appearance_event not in (
            'sac_bunt', 'sac_bunt_double_play', 'catcher_interf'
        ))::boolean                                                         as is_obp_denom,

        -- OBP numerator: hit + walk + HBP
        (plate_appearance_event in (
            'single', 'double', 'triple', 'home_run',
            'walk', 'intent_walk', 'hit_by_pitch'
        ))::boolean                                                         as is_on_base,

        -- Total bases for SLG
        case plate_appearance_event
            when 'single'    then 1
            when 'double'    then 2
            when 'triple'    then 3
            when 'home_run'  then 4
            else 0
        end                                                                 as total_bases,

        -- Batted-ball quality
        (exit_velocity_mph >= 95)::boolean                                  as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean                              as is_barrel,
        (exit_velocity_mph is not null)::boolean                            as is_batted_ball

    from pitches_tagged
    where plate_appearance_event is not null
      and plate_appearance_event != 'truncated_pa'

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Pitch-level aggregates per batter × game
-- ─────────────────────────────────────────────────────────────────────────────
pitch_game_agg as (

    select
        game_pk,
        batter_id,

        count(*)                                                            as pitches_seen,
        sum(is_swing::integer)                                              as swings,
        sum(is_whiff::integer)                                              as whiffs,
        sum(is_out_of_zone::integer)                                        as out_of_zone_pitches,
        sum((is_out_of_zone and is_swing)::integer)                         as out_of_zone_swings,
        sum(is_in_zone::integer)                                            as in_zone_pitches,
        sum((is_in_zone and is_swing)::integer)                             as in_zone_swings

    from pitches_tagged
    group by game_pk, batter_id

),

-- ─────────────────────────────────────────────────────────────────────────────
-- PA-level aggregates per batter × game
-- ─────────────────────────────────────────────────────────────────────────────
pa_game_agg as (

    select
        game_pk,
        game_date,
        game_year,
        batter_id,
        batter_hand,
        batting_team,
        opposing_team,

        count(*)                                                            as pa_count,
        sum(woba_value)                                                     as woba_value_sum,
        sum(woba_denom)                                                     as woba_denom_sum,
        sum(xwoba)                                                          as xwoba_sum,
        count(xwoba)                                                        as xwoba_denom,
        sum(xba)                                                            as xba_sum,
        count(xba)                                                          as xba_denom,
        sum(xslg)                                                           as xslg_sum,
        count(xslg)                                                         as xslg_denom,
        sum(is_hit::integer)                                                as hits,
        sum(is_single::integer)                                             as singles,
        sum(is_double::integer)                                             as doubles,
        sum(is_triple::integer)                                             as triples,
        sum(is_home_run::integer)                                           as home_runs,
        sum(is_walk::integer)                                               as walks,
        sum(is_hbp::integer)                                                as hbp,
        sum(is_strikeout::integer)                                          as strikeouts,
        sum(is_at_bat::integer)                                             as at_bats,
        sum(is_obp_denom::integer)                                          as obp_denom,
        sum(is_on_base::integer)                                            as on_base_events,
        sum(total_bases)                                                    as total_bases,
        sum(is_hard_hit::integer)                                           as hard_hit_balls,
        sum(is_barrel::integer)                                             as barrels,
        sum(is_batted_ball::integer)                                        as batted_balls

    from plate_appearances
    group by game_pk, game_date, game_year, batter_id, batter_hand, batting_team, opposing_team

),

-- Combine PA and pitch aggregates into one game-level row per batter
game_stats as (

    select
        pa.game_pk,
        pa.game_date,
        pa.game_year,
        pa.batter_id,
        pa.batter_hand,
        pa.batting_team,
        pa.opposing_team,
        pa.pa_count,
        pm.pitches_seen,
        pm.swings,
        pm.whiffs,
        pm.out_of_zone_pitches,
        pm.out_of_zone_swings,
        pm.in_zone_pitches,
        pm.in_zone_swings,
        pa.woba_value_sum,
        pa.woba_denom_sum,
        pa.xwoba_sum,
        pa.xwoba_denom,
        pa.xba_sum,
        pa.xba_denom,
        pa.xslg_sum,
        pa.xslg_denom,
        pa.hits,
        pa.singles,
        pa.doubles,
        pa.triples,
        pa.home_runs,
        pa.walks,
        pa.hbp,
        pa.strikeouts,
        pa.at_bats,
        pa.obp_denom,
        pa.on_base_events,
        pa.total_bases,
        pa.hard_hit_balls,
        pa.barrels,
        pa.batted_balls

    from pa_game_agg pa
    join pitch_game_agg pm
        on pa.game_pk = pm.game_pk
        and pa.batter_id = pm.batter_id

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Rolling windows — inline window specs for Snowflake compatibility
-- ─────────────────────────────────────────────────────────────────────────────
rolling as (

    select
        game_pk,
        game_date,
        game_year,
        batter_id,
        batter_hand,
        batting_team,
        opposing_team,

        -- ── Single-game actuals ─────────────────────────────────────────────────
        pa_count,
        pitches_seen,
        hits,
        home_runs,
        strikeouts,
        walks,

        -- Traditional rate stats (single game — high variance, use rolling for ML)
        round(
            case when at_bats > 0 then (hits::numeric / at_bats) else null end, 3
        )                                                                   as avg,
        round(
            case when obp_denom > 0
                 then (on_base_events::numeric / obp_denom) else null end, 3
        )                                                                   as obp,
        round(
            case when at_bats > 0 then (total_bases::numeric / at_bats) else null end, 3
        )                                                                   as slg,
        round(
            case when obp_denom > 0 and at_bats > 0
                 then (on_base_events::numeric / obp_denom)
                    + (total_bases::numeric / at_bats)
                 else null end, 3
        )                                                                   as ops,
        round(
            case when woba_denom_sum > 0
                 then (woba_value_sum / woba_denom_sum)::numeric else null end, 3
        )                                                                   as woba,
        round(
            case when xwoba_denom > 0
                 then (xwoba_sum / xwoba_denom)::numeric else null end, 3
        )                                                                   as xwoba,
        round(
            case when xba_denom > 0
                 then (xba_sum / xba_denom)::numeric else null end, 3
        )                                                                   as xba,
        round(
            case when xslg_denom > 0
                 then (xslg_sum / xslg_denom)::numeric else null end, 3
        )                                                                   as xslg,
        round(
            case when pa_count > 0
                 then (strikeouts::numeric / pa_count) else null end, 3
        )                                                                   as k_pct,
        round(
            case when pa_count > 0
                 then (walks::numeric / pa_count) else null end, 3
        )                                                                   as bb_pct,
        round(
            case when batted_balls > 0
                 then (hard_hit_balls::numeric / batted_balls) else null end, 3
        )                                                                   as hard_hit_pct,
        round(
            case when batted_balls > 0
                 then (barrels::numeric / batted_balls) else null end, 3
        )                                                                   as barrel_pct,
        round(
            case when swings > 0
                 then (whiffs::numeric / swings) else null end, 3
        )                                                                   as whiff_rate,
        round(
            case when pitches_seen > 0
                 then (whiffs::numeric / pitches_seen) else null end, 3
        )                                                                   as swinging_strike_rate,
        round(
            case when out_of_zone_pitches > 0
                 then (out_of_zone_swings::numeric / out_of_zone_pitches) else null end, 3
        )                                                                   as chase_rate,
        round(
            case when in_zone_pitches > 0
                 then (in_zone_swings::numeric / in_zone_pitches) else null end, 3
        )                                                                   as zone_swing_rate,

        -- ── Rolling 7-day ────────────────────────────────────────────────────────
        count(*) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row) as games_7d,
        sum(pa_count) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row) as pa_count_7d,

        round(
            sum(hits) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as avg_7d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as obp_7d,
        round(
            sum(total_bases) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as slg_7d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
            + sum(total_bases) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as ops_7d,
        round(
            sum(woba_value_sum) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as woba_7d,
        round(
            sum(xwoba_sum) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xwoba_7d,
        round(
            sum(xba_sum) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xba_denom) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xba_7d,
        round(
            sum(xslg_sum) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xslg_denom) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xslg_7d,
        round(
            sum(strikeouts) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as k_pct_7d,
        round(
            sum(walks) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bb_pct_7d,
        round(
            sum(hard_hit_balls) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as hard_hit_pct_7d,
        round(
            sum(barrels) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as barrel_pct_7d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(swings) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as whiff_rate_7d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pitches_seen) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_7d,
        round(
            sum(out_of_zone_swings) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as chase_rate_7d,
        round(
            sum(in_zone_swings) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(in_zone_pitches) over (partition by batter_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as zone_swing_rate_7d,

        -- ── Rolling 14-day ───────────────────────────────────────────────────────
        count(*) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row) as games_14d,
        sum(pa_count) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row) as pa_count_14d,

        round(
            sum(hits) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as avg_14d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as obp_14d,
        round(
            sum(total_bases) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as slg_14d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
            + sum(total_bases) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as ops_14d,
        round(
            sum(woba_value_sum) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as woba_14d,
        round(
            sum(xwoba_sum) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xwoba_14d,
        round(
            sum(xba_sum) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xba_denom) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xba_14d,
        round(
            sum(xslg_sum) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xslg_denom) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xslg_14d,
        round(
            sum(strikeouts) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as k_pct_14d,
        round(
            sum(walks) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bb_pct_14d,
        round(
            sum(hard_hit_balls) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as hard_hit_pct_14d,
        round(
            sum(barrels) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as barrel_pct_14d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(swings) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as whiff_rate_14d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pitches_seen) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_14d,
        round(
            sum(out_of_zone_swings) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as chase_rate_14d,
        round(
            sum(in_zone_swings) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(in_zone_pitches) over (partition by batter_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as zone_swing_rate_14d,

        -- ── Rolling 30-day ───────────────────────────────────────────────────────
        count(*) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row) as games_30d,
        sum(pa_count) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row) as pa_count_30d,

        round(
            sum(hits) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as avg_30d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as obp_30d,
        round(
            sum(total_bases) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as slg_30d,
        round(
            sum(on_base_events) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
            + sum(total_bases) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as ops_30d,
        round(
            sum(woba_value_sum) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as woba_30d,
        round(
            sum(xwoba_sum) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xwoba_30d,
        round(
            sum(xba_sum) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xba_denom) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xba_30d,
        round(
            sum(xslg_sum) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xslg_denom) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xslg_30d,
        round(
            sum(strikeouts) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as k_pct_30d,
        round(
            sum(walks) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bb_pct_30d,
        round(
            sum(hard_hit_balls) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as hard_hit_pct_30d,
        round(
            sum(barrels) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as barrel_pct_30d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(swings) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as whiff_rate_30d,
        round(
            sum(whiffs) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pitches_seen) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_30d,
        round(
            sum(out_of_zone_swings) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as chase_rate_30d,
        round(
            sum(in_zone_swings) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(in_zone_pitches) over (partition by batter_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as zone_swing_rate_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────────
        count(*) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row) as games_std,
        sum(pa_count) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row) as pa_count_std,

        round(
            sum(hits) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as avg_std,
        round(
            sum(on_base_events) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as obp_std,
        round(
            sum(total_bases) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as slg_std,
        round(
            sum(on_base_events) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(obp_denom) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
            + sum(total_bases) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(at_bats) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as ops_std,
        round(
            sum(woba_value_sum) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as woba_std,
        round(
            sum(xwoba_sum) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xwoba_std,
        round(
            sum(xba_sum) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xba_denom) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xba_std,
        round(
            sum(xslg_sum) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xslg_denom) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xslg_std,
        round(
            sum(strikeouts) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as k_pct_std,
        round(
            sum(walks) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bb_pct_std,
        round(
            sum(hard_hit_balls) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as hard_hit_pct_std,
        round(
            sum(barrels) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as barrel_pct_std,
        round(
            sum(whiffs) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(swings) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as whiff_rate_std,
        round(
            sum(whiffs) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pitches_seen) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as swinging_strike_rate_std,
        round(
            sum(out_of_zone_swings) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as chase_rate_std,
        round(
            sum(in_zone_swings) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(in_zone_pitches) over (partition by batter_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as zone_swing_rate_std

    from game_stats

)

select * from rolling
order by batter_id, game_date

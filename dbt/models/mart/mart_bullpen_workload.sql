{{
    config(
        materialized='table'
    )
}}

-- Grain: pitching_team × game_pk.
-- Each row represents a team's bullpen fatigue profile *entering* a given game.
-- Rolling windows look exclusively at preceding days (upper bound = 1 day prior)
-- so no current-game data leaks into the fatigue predictors.
--
-- Bullpen definition: any pitcher who appears in a game but is NOT the
-- qualifying starter per mart_starting_pitcher_game_log.
--
-- Closer / high-leverage proxy:
--   high_leverage  = reliever who pitched in inning 7 or later
--   closer         = reliever who pitched in inning 9 or later
-- These are positional heuristics rather than role labels, since role data
-- is not available in the Statcast source.
--
-- Doubleheader note: rolling windows aggregate to the calendar-date level
-- before computing preceding-day sums. Both games of a doubleheader share
-- the same prior-day fatigue values. Bullpen usage within the first game of
-- a doubleheader is NOT reflected in the same-day second game's fatigue row.

with pitches as (
    select
        game_pk,
        game_date,
        game_year,
        pitcher_id,
        inning,
        home_team,
        away_team,
        plate_appearance_event,
        case when inning_half = 'Top' then home_team else away_team end as pitching_team
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
),

starters as (
    select game_pk, pitcher_id, pitching_team
    from {{ ref('mart_starting_pitcher_game_log') }}
),

-- All pitches thrown by non-starters, aggregated per pitcher per game
bullpen_pitcher_game as (
    select
        p.game_pk,
        p.game_date,
        p.game_year,
        p.pitcher_id,
        p.pitching_team,
        p.home_team,
        p.away_team,
        max(p.inning)   as max_inning_pitched,
        count(*)        as pitches_thrown,
        sum(case when p.plate_appearance_event in (
            'strikeout', 'strikeout_double_play',
            'field_out', 'force_out',
            'grounded_into_double_play', 'double_play', 'triple_play',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'fielders_choice_out',
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'other_out'
        ) then 1 else 0 end)  as outs_recorded
    from pitches p
    left join starters s
        on  p.game_pk       = s.game_pk
        and p.pitcher_id    = s.pitcher_id
        and p.pitching_team = s.pitching_team
    where s.pitcher_id is null  -- exclude starters
    group by
        p.game_pk, p.game_date, p.game_year, p.pitcher_id,
        p.pitching_team, p.home_team, p.away_team
),

-- Collapse to team × game level
game_bullpen as (
    select
        game_pk,
        game_date,
        game_year,
        pitching_team,
        home_team,
        away_team,
        sum(pitches_thrown)                                         as bullpen_pitches,
        count(distinct pitcher_id)                                  as pitchers_used,
        count(*)                                                    as reliever_appearances,
        sum(outs_recorded)                                          as outs_recorded,
        max(case when max_inning_pitched >= 7 then 1 else 0 end)   as had_high_leverage_appearance,
        max(case when max_inning_pitched >= 9 then 1 else 0 end)   as had_closer_appearance
    from bullpen_pitcher_game
    group by game_pk, game_date, game_year, pitching_team, home_team, away_team
),

-- Collapse to team × date level for rolling window accuracy across doubleheaders
date_bullpen as (
    select
        game_date,
        game_year,
        pitching_team,
        sum(bullpen_pitches)                                        as bullpen_pitches,
        sum(pitchers_used)                                          as pitchers_used,
        sum(reliever_appearances)                                   as reliever_appearances,
        sum(outs_recorded)                                          as outs_recorded,
        max(had_high_leverage_appearance)                           as had_high_leverage_appearance,
        max(had_closer_appearance)                                  as had_closer_appearance
    from game_bullpen
    group by game_date, game_year, pitching_team
),

-- Rolling windows — upper bound is 1 day prior so current-game bullpen
-- usage never appears in the fatigue predictors
rolling as (
    select
        game_date,
        pitching_team,

        sum(bullpen_pitches) over (
            partition by pitching_team
            order by game_date
            range between interval '1 day' preceding and interval '1 day' preceding
        )                                                           as bullpen_pitches_prev_1d,

        sum(bullpen_pitches) over (
            partition by pitching_team
            order by game_date
            range between interval '3 days' preceding and interval '1 day' preceding
        )                                                           as bullpen_pitches_prev_3d,

        sum(bullpen_pitches) over (
            partition by pitching_team
            order by game_date
            range between interval '7 days' preceding and interval '1 day' preceding
        )                                                           as bullpen_pitches_prev_7d,

        -- Pitchers used: sum of per-game distinct counts across the window.
        -- Overcounts pitchers who appear on multiple days; use as a
        -- "total reliever slots consumed" proxy, not a strict distinct count.
        sum(pitchers_used) over (
            partition by pitching_team
            order by game_date
            range between interval '3 days' preceding and interval '1 day' preceding
        )                                                           as pitchers_used_prev_3d,

        sum(pitchers_used) over (
            partition by pitching_team
            order by game_date
            range between interval '7 days' preceding and interval '1 day' preceding
        )                                                           as pitchers_used_prev_7d,

        sum(reliever_appearances) over (
            partition by pitching_team
            order by game_date
            range between interval '3 days' preceding and interval '1 day' preceding
        )                                                           as reliever_appearances_prev_3d,

        sum(reliever_appearances) over (
            partition by pitching_team
            order by game_date
            range between interval '7 days' preceding and interval '1 day' preceding
        )                                                           as reliever_appearances_prev_7d,

        -- High-leverage usage: any reliever in inning 7+ in prior 2 days
        max(had_high_leverage_appearance) over (
            partition by pitching_team
            order by game_date
            range between interval '2 days' preceding and interval '1 day' preceding
        )                                                           as high_leverage_used_prev_2d,

        -- Closer usage: any reliever in inning 9+ in prior 1 and 2 days
        max(had_closer_appearance) over (
            partition by pitching_team
            order by game_date
            range between interval '1 day' preceding and interval '1 day' preceding
        )                                                           as closer_used_prev_1d,

        max(had_closer_appearance) over (
            partition by pitching_team
            order by game_date
            range between interval '2 days' preceding and interval '1 day' preceding
        )                                                           as closer_used_prev_2d,

        -- Innings pitched (outs / 3): prior 1 day
        round(
            coalesce(sum(outs_recorded) over (
                partition by pitching_team
                order by game_date
                range between interval '1 day' preceding
                          and interval '1 day' preceding
            ), 0) / 3.0, 1
        )                                                           as bullpen_ip_prev_1d,

        -- Innings pitched (outs / 3): prior 2 days
        round(
            coalesce(sum(outs_recorded) over (
                partition by pitching_team
                order by game_date
                range between interval '2 days' preceding
                          and interval '1 day' preceding
            ), 0) / 3.0, 1
        )                                                           as bullpen_ip_prev_2d,

        -- Innings pitched (outs / 3): prior 3 days
        round(
            coalesce(sum(outs_recorded) over (
                partition by pitching_team
                order by game_date
                range between interval '3 days' preceding
                          and interval '1 day' preceding
            ), 0) / 3.0, 1
        )                                                           as bullpen_ip_prev_3d,

        -- Pitchers used: prior 2 days (2d window complement to existing 3d/7d)
        sum(pitchers_used) over (
            partition by pitching_team
            order by game_date
            range between interval '2 days' preceding
                      and interval '1 day' preceding
        )                                                           as pitchers_used_prev_2d

    from date_bullpen
)

-- Join rolling fatigue stats back to game_pk grain
select
    gb.game_pk,
    gb.game_date,
    gb.game_year,
    gb.pitching_team,
    gb.home_team,
    gb.away_team,

    -- Current game bullpen context (useful for downstream rolling model validation)
    gb.bullpen_pitches           as bullpen_pitches_today,
    gb.pitchers_used             as pitchers_used_today,
    gb.reliever_appearances      as reliever_appearances_today,
    gb.had_high_leverage_appearance,
    gb.had_closer_appearance,

    -- Preceding-day fatigue predictors
    r.bullpen_pitches_prev_1d,
    r.bullpen_pitches_prev_3d,
    r.bullpen_pitches_prev_7d,
    r.pitchers_used_prev_3d,
    r.pitchers_used_prev_7d,
    r.reliever_appearances_prev_3d,
    r.reliever_appearances_prev_7d,
    r.high_leverage_used_prev_2d,
    r.closer_used_prev_1d,
    r.closer_used_prev_2d,
    r.bullpen_ip_prev_1d,
    r.bullpen_ip_prev_2d,
    r.bullpen_ip_prev_3d,
    r.pitchers_used_prev_2d

from game_bullpen gb
left join rolling r
    on  gb.game_date    = r.game_date
    and gb.pitching_team = r.pitching_team

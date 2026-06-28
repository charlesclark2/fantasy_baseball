{{
    config(
        materialized = 'view',
        tags         = ['w3_lakehouse']
    )
}}

-- E11.1-W3: dual-branch lakehouse model. Upstream stg_batter_pitches (W1) and
-- mart_starting_pitcher_game_log (W2) are S3 parquet (registered as views by
-- run_w1_lakehouse.py); the Snowflake branch is a thin view over the lakehouse_ext
-- external table. game_date is cast ::date in the pitches CTE so the RANGE-interval
-- rolling windows work on the VARCHAR game_date the parquet carries.
--
-- Grain: team_abbrev × game_pk.
-- Rolling 30-day bullpen xwOBA-against split by batter handedness (L or R).
-- Leakage guard: rolling window upper bound is interval '1 day' preceding (same
-- as mart_bullpen_effectiveness). Only appearances strictly before the game date
-- are included.
--
-- Reliever definition: same as mart_bullpen_effectiveness — any pitcher who is
-- NOT the qualifying starter per mart_starting_pitcher_game_log.
--
-- Doubleheader handling: stats are aggregated to the calendar-date level before
-- rolling windows are computed. Both games of a doubleheader share the same
-- prior-day handedness values.
--
-- PA-count columns (bp_pa_vs_rhb_30d / bp_pa_vs_lhb_30d) capture sample size.
-- Null when fewer than 1 PA against that handedness in the rolling window.
--
-- Companion models:
--   mart_bullpen_workload      — fatigue / workload metrics
--   mart_bullpen_effectiveness — overall effectiveness (xwOBA, K%, BB%, etc.)
-- Join all three on team_abbrev + game_pk for a full pre-game bullpen view.

{% if target.name == 'duckdb' %}

with pitches as (

    select
        game_pk,
        game_date::date as game_date,   -- VARCHAR (ISO) in parquet → DATE for RANGE windows [E11.1-W3]
        game_year,
        pitcher_id,
        batter_hand,
        home_team,
        away_team,
        inning_half,
        xwoba,
        woba_value,
        woba_denom
    from stg_batter_pitches
    where game_type = 'R'
      and batter_hand in ('L', 'R')

),

pitches_tagged as (

    select
        *,
        case when inning_half = 'Top' then home_team else away_team end
            as pitching_team
    from pitches

),

starters as (

    select game_pk, pitcher_id, pitching_team
    from mart_starting_pitcher_game_log

),

reliever_pitches as (

    select pt.*
    from pitches_tagged pt
    left join starters s
        on  pt.game_pk       = s.game_pk
        and pt.pitcher_id    = s.pitcher_id
        and pt.pitching_team = s.pitching_team
    where s.pitcher_id is null

),

-- Aggregate per (game_pk, game_date, pitching_team, batter_hand)
game_hand as (

    select
        game_pk,
        game_date,
        game_year,
        pitching_team,
        batter_hand,
        sum(case when woba_denom = 1
            then coalesce(xwoba, woba_value)
            else 0
        end)                    as xwoba_num,
        sum(coalesce(woba_denom, 0)) as xwoba_denom
    from reliever_pitches
    group by game_pk, game_date, game_year, pitching_team, batter_hand

),

-- Collapse to date level for doubleheader-safe rolling windows
date_hand as (

    select
        game_date,
        game_year,
        pitching_team,
        batter_hand,
        sum(xwoba_num)   as xwoba_num,
        sum(xwoba_denom) as xwoba_denom
    from game_hand
    group by game_date, game_year, pitching_team, batter_hand

),

-- Pivot to one row per (game_date, pitching_team): RHB and LHB side by side
date_pivoted as (

    select
        game_date,
        game_year,
        pitching_team,
        sum(case when batter_hand = 'R' then xwoba_num   else 0 end) as rhb_xwoba_num,
        sum(case when batter_hand = 'R' then xwoba_denom else 0 end) as rhb_xwoba_denom,
        sum(case when batter_hand = 'L' then xwoba_num   else 0 end) as lhb_xwoba_num,
        sum(case when batter_hand = 'L' then xwoba_denom else 0 end) as lhb_xwoba_denom
    from date_hand
    group by game_date, game_year, pitching_team

),

-- Rolling 30-day windows; upper bound = 1 day prior (no leakage)
rolling as (

    select
        game_date,
        pitching_team,

        round(
            sum(rhb_xwoba_num) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(rhb_xwoba_denom) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                               as bp_xwoba_vs_rhb_30d,

        round(
            sum(lhb_xwoba_num) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(lhb_xwoba_denom) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                               as bp_xwoba_vs_lhb_30d,

        sum(rhb_xwoba_denom) over (
            partition by pitching_team order by game_date
            range between interval '30 days' preceding
                      and interval '1 day'  preceding
        )                                               as bp_pa_vs_rhb_30d,

        sum(lhb_xwoba_denom) over (
            partition by pitching_team order by game_date
            range between interval '30 days' preceding
                      and interval '1 day'  preceding
        )                                               as bp_pa_vs_lhb_30d

    from date_pivoted

),

-- Game-pk spine: one row per (game_pk, pitching_team) where team used relievers
game_spine as (

    select distinct game_pk, game_date, game_year, pitching_team
    from game_hand

)

select
    gs.game_pk,
    gs.game_date,
    gs.game_year,
    gs.pitching_team                as team_abbrev,
    r.bp_xwoba_vs_rhb_30d,
    r.bp_xwoba_vs_lhb_30d,
    r.bp_pa_vs_rhb_30d,
    r.bp_pa_vs_lhb_30d

from game_spine gs
left join rolling r
    on  r.game_date     = gs.game_date
    and r.pitching_team = gs.pitching_team

{% else %}

select * from baseball_data.lakehouse_ext.mart_bullpen_handedness_splits

{% endif %}

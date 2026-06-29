-- =============================================================================
-- mart_home_away_splits.sql
-- Grain: one row per team × home_away_flag × game date (regular season only)
-- Purpose: Separates each team's offensive and pitching performance into home
--          and away contexts. Home field advantage varies significantly by team
--          and stadium; this model surfaces that asymmetry.
--          Rolling windows are computed separately within each context so that
--          a team's home 7-day window only includes home games.
-- Join keys: team, home_away_flag, game_date
-- Source: stg_batter_pitches, mart_game_results
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model. DuckDB branch reads the W1 stg_batter_pitches
-- + the migrated mart_game_results (registered as DuckDB views); Snowflake branch is a
-- thin view over the lakehouse_ext external table. game_date is cast ::date in the
-- pitches CTE (via SELECT * REPLACE) so the RANGE-interval rolling windows operate on
-- DATE (stg_batter_pitches stores game_date as VARCHAR; mart_game_results is already DATE).

{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

pitches as (

    select * replace (game_date::date as game_date) from stg_batter_pitches
    where game_type = 'R'

),

game_results as (

    select * from mart_game_results
    where game_type = 'R'

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Offense: tag each terminal pitch with batting team and home/away context.
-- Top of inning = away team bats; bottom = home team bats.
-- ─────────────────────────────────────────────────────────────────────────────
offense_pas as (

    select
        game_pk,
        game_date,
        game_year,

        case when inning_half = 'Top' then away_team else home_team end  as team,
        case when inning_half = 'Top' then 'Away'    else 'Home'   end  as home_away_flag,

        woba_value,
        woba_denom,
        xwoba,

        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                                      as is_strikeout,

        (plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                                      as is_walk,

        case plate_appearance_event
            when 'single'    then 1
            when 'double'    then 2
            when 'triple'    then 3
            when 'home_run'  then 4
            else 0
        end                                                              as total_bases,

        (plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_bunt', 'sac_fly_double_play'
        ) and plate_appearance_event is not null)::boolean               as is_at_bat,

        (exit_velocity_mph >= 95)::boolean                               as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean                           as is_barrel,
        exit_velocity_mph

    from pitches
    where plate_appearance_event is not null

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Game-level offense: one row per team × home_away_flag × game
-- ─────────────────────────────────────────────────────────────────────────────
game_offense as (

    select
        game_pk,
        game_date,
        game_year,
        team,
        home_away_flag,

        count(*)                                                          as pa_count,
        sum(woba_value)                                                   as woba_value_sum,
        sum(woba_denom)                                                   as woba_denom_sum,
        sum(xwoba)                                                        as xwoba_sum,
        count(xwoba)                                                      as xwoba_denom,
        sum(is_strikeout::integer)                                        as strikeouts,
        sum(is_walk::integer)                                             as walks,
        sum(total_bases)                                                  as total_bases,
        sum(is_at_bat::integer)                                           as at_bats,
        sum(is_hard_hit::integer)                                         as hard_hit_balls,
        sum(is_barrel::integer)                                           as barrels,
        count(case when exit_velocity_mph is not null then 1 end)         as batted_balls

    from offense_pas
    group by game_pk, game_date, game_year, team, home_away_flag

),

game_offense_with_runs as (

    select
        go.game_pk,
        go.game_date,
        go.game_year,
        go.team,
        go.home_away_flag,
        go.pa_count,
        go.woba_value_sum,
        go.woba_denom_sum,
        go.xwoba_sum,
        go.xwoba_denom,
        go.strikeouts,
        go.walks,
        go.total_bases,
        go.at_bats,
        go.hard_hit_balls,
        go.barrels,
        go.batted_balls,

        case
            when gr.home_team = go.team then gr.home_final_score
            else gr.away_final_score
        end                                                               as runs_scored

    from game_offense go
    join game_results gr on go.game_pk = gr.game_pk

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Pitching: tag each terminal pitch with pitching team and home/away context.
-- Top of inning = home team pitches; bottom = away team pitches.
-- ─────────────────────────────────────────────────────────────────────────────
pitching_pas as (

    select
        game_pk,
        game_date,
        game_year,

        case when inning_half = 'Top' then home_team else away_team end  as team,
        case when inning_half = 'Top' then 'Home'    else 'Away'   end  as home_away_flag,

        woba_value,
        woba_denom,
        xwoba,

        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                                      as is_strikeout,

        (plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                                      as is_walk,

        (exit_velocity_mph >= 95)::boolean                               as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean                           as is_barrel,
        exit_velocity_mph

    from pitches
    where plate_appearance_event is not null

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Game-level pitching: one row per team × home_away_flag × game
-- ─────────────────────────────────────────────────────────────────────────────
game_pitching as (

    select
        game_pk,
        game_date,
        game_year,
        team,
        home_away_flag,

        count(*)                                                          as pa_count_against,
        sum(woba_value)                                                   as woba_value_sum_against,
        sum(woba_denom)                                                   as woba_denom_sum_against,
        sum(xwoba)                                                        as xwoba_sum_against,
        count(xwoba)                                                      as xwoba_denom_against,
        sum(is_strikeout::integer)                                        as strikeouts_recorded,
        sum(is_walk::integer)                                             as walks_allowed,
        sum(is_hard_hit::integer)                                         as hard_hit_against,
        sum(is_barrel::integer)                                           as barrels_against,
        count(case when exit_velocity_mph is not null then 1 end)         as batted_balls_against

    from pitching_pas
    group by game_pk, game_date, game_year, team, home_away_flag

),

game_pitching_with_runs as (

    select
        gp.game_pk,
        gp.game_date,
        gp.game_year,
        gp.team,
        gp.home_away_flag,
        gp.pa_count_against,
        gp.woba_value_sum_against,
        gp.woba_denom_sum_against,
        gp.xwoba_sum_against,
        gp.xwoba_denom_against,
        gp.strikeouts_recorded,
        gp.walks_allowed,
        gp.hard_hit_against,
        gp.barrels_against,
        gp.batted_balls_against,

        case
            when gr.home_team = gp.team then gr.away_final_score
            else gr.home_final_score
        end                                                               as runs_allowed

    from game_pitching gp
    join game_results gr on gp.game_pk = gr.game_pk

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Combine offense and pitching for each team × game × home_away_flag.
-- The join is 1:1: a team is either home or away for the entire game, so
-- its offense home_away_flag equals its pitching home_away_flag.
-- ─────────────────────────────────────────────────────────────────────────────
game_combined as (

    select
        o.game_pk,
        o.game_date,
        o.game_year,
        o.team,
        o.home_away_flag,

        -- offense raw totals (needed for accurate rolling window aggregation)
        o.runs_scored,
        o.pa_count,
        o.woba_value_sum,
        o.woba_denom_sum,
        o.xwoba_sum,
        o.xwoba_denom,
        o.strikeouts,
        o.walks,
        o.total_bases,
        o.at_bats,
        o.hard_hit_balls,
        o.barrels,
        o.batted_balls,

        -- pitching raw totals
        p.runs_allowed,
        p.pa_count_against,
        p.woba_value_sum_against,
        p.woba_denom_sum_against,
        p.xwoba_sum_against,
        p.xwoba_denom_against,
        p.strikeouts_recorded,
        p.walks_allowed,
        p.hard_hit_against,
        p.barrels_against,
        p.batted_balls_against

    from game_offense_with_runs o
    join game_pitching_with_runs p
        on  o.game_pk        = p.game_pk
        and o.team           = p.team
        and o.home_away_flag = p.home_away_flag

)

select

    -- ── Grain ────────────────────────────────────────────────────────────────
    game_pk,
    game_date,
    game_year,
    team,
    home_away_flag,

    -- ── Game-level offense actuals ───────────────────────────────────────────
    runs_scored,
    pa_count,
    round(
        case when woba_denom_sum  > 0
             then (woba_value_sum  / woba_denom_sum)::numeric  else null end, 3
    )                                                           as woba,
    round(
        case when xwoba_denom     > 0
             then (xwoba_sum      / xwoba_denom)::numeric      else null end, 3
    )                                                           as xwoba,
    round(
        case when pa_count        > 0
             then (strikeouts::numeric / pa_count)             else null end, 3
    )                                                           as k_pct,
    round(
        case when pa_count        > 0
             then (walks::numeric     / pa_count)              else null end, 3
    )                                                           as bb_pct,
    round(
        case when at_bats         > 0
             then (total_bases::numeric / at_bats)             else null end, 3
    )                                                           as slugging,
    round(
        case when batted_balls    > 0
             then (hard_hit_balls::numeric / batted_balls)     else null end, 3
    )                                                           as hard_hit_pct,
    round(
        case when batted_balls    > 0
             then (barrels::numeric / batted_balls)            else null end, 3
    )                                                           as barrel_pct,

    -- ── Game-level pitching actuals ──────────────────────────────────────────
    runs_allowed,
    pa_count_against,
    round(
        case when woba_denom_sum_against  > 0
             then (woba_value_sum_against / woba_denom_sum_against)::numeric  else null end, 3
    )                                                           as woba_against,
    round(
        case when xwoba_denom_against     > 0
             then (xwoba_sum_against      / xwoba_denom_against)::numeric     else null end, 3
    )                                                           as xwoba_against,
    round(
        case when pa_count_against        > 0
             then (strikeouts_recorded::numeric / pa_count_against)           else null end, 3
    )                                                           as k_pct_recorded,
    round(
        case when pa_count_against        > 0
             then (walks_allowed::numeric      / pa_count_against)            else null end, 3
    )                                                           as bb_pct_allowed,
    round(
        case when batted_balls_against    > 0
             then (hard_hit_against::numeric   / batted_balls_against)        else null end, 3
    )                                                           as hard_hit_pct_allowed,
    round(
        case when batted_balls_against    > 0
             then (barrels_against::numeric    / batted_balls_against)        else null end, 3
    )                                                           as barrel_pct_allowed,

    -- ── Rolling 7-day offense ────────────────────────────────────────────────
    count(*) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)   as games_7d,
    round(avg(runs_scored) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 3) as runs_per_game_7d,
    round(
        sum(woba_value_sum) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(woba_denom_sum) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as woba_7d,
    round(
        sum(xwoba_sum) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(xwoba_denom) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as xwoba_7d,
    round(
        sum(strikeouts) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as k_pct_7d,
    round(
        sum(walks) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as bb_pct_7d,
    round(
        sum(total_bases) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(at_bats) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as slugging_7d,
    round(
        sum(hard_hit_balls) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as hard_hit_pct_7d,
    round(
        sum(barrels) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as barrel_pct_7d,

    -- ── Rolling 7-day pitching ────────────────────────────────────────────────
    round(avg(runs_allowed) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 3) as runs_allowed_per_game_7d,
    round(
        sum(woba_value_sum_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(woba_denom_sum_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as woba_against_7d,
    round(
        sum(xwoba_sum_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(xwoba_denom_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as xwoba_against_7d,
    round(
        sum(strikeouts_recorded) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as k_pct_recorded_7d,
    round(
        sum(walks_allowed) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as bb_pct_allowed_7d,
    round(
        sum(hard_hit_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as hard_hit_pct_allowed_7d,
    round(
        sum(barrels_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '7 days' preceding and current row), 0)
    , 3) as barrel_pct_allowed_7d,

    -- ── Rolling 14-day offense ────────────────────────────────────────────────
    count(*) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)  as games_14d,
    round(avg(runs_scored) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 3) as runs_per_game_14d,
    round(
        sum(woba_value_sum) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(woba_denom_sum) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as woba_14d,
    round(
        sum(xwoba_sum) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(xwoba_denom) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as xwoba_14d,
    round(
        sum(strikeouts) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as k_pct_14d,
    round(
        sum(walks) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as bb_pct_14d,
    round(
        sum(total_bases) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(at_bats) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as slugging_14d,
    round(
        sum(hard_hit_balls) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as hard_hit_pct_14d,
    round(
        sum(barrels) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as barrel_pct_14d,

    -- ── Rolling 14-day pitching ───────────────────────────────────────────────
    round(avg(runs_allowed) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 3) as runs_allowed_per_game_14d,
    round(
        sum(woba_value_sum_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(woba_denom_sum_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as woba_against_14d,
    round(
        sum(xwoba_sum_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(xwoba_denom_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as xwoba_against_14d,
    round(
        sum(strikeouts_recorded) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as k_pct_recorded_14d,
    round(
        sum(walks_allowed) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as bb_pct_allowed_14d,
    round(
        sum(hard_hit_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as hard_hit_pct_allowed_14d,
    round(
        sum(barrels_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '14 days' preceding and current row), 0)
    , 3) as barrel_pct_allowed_14d,

    -- ── Rolling 30-day offense ────────────────────────────────────────────────
    count(*) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)  as games_30d,
    round(avg(runs_scored) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 3) as runs_per_game_30d,
    round(
        sum(woba_value_sum) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(woba_denom_sum) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as woba_30d,
    round(
        sum(xwoba_sum) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(xwoba_denom) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as xwoba_30d,
    round(
        sum(strikeouts) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as k_pct_30d,
    round(
        sum(walks) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as bb_pct_30d,
    round(
        sum(total_bases) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(at_bats) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as slugging_30d,
    round(
        sum(hard_hit_balls) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as hard_hit_pct_30d,
    round(
        sum(barrels) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as barrel_pct_30d,

    -- ── Rolling 30-day pitching ───────────────────────────────────────────────
    round(avg(runs_allowed) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 3) as runs_allowed_per_game_30d,
    round(
        sum(woba_value_sum_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(woba_denom_sum_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as woba_against_30d,
    round(
        sum(xwoba_sum_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(xwoba_denom_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as xwoba_against_30d,
    round(
        sum(strikeouts_recorded) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as k_pct_recorded_30d,
    round(
        sum(walks_allowed) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as bb_pct_allowed_30d,
    round(
        sum(hard_hit_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as hard_hit_pct_allowed_30d,
    round(
        sum(barrels_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag order by game_date range between interval '30 days' preceding and current row), 0)
    , 3) as barrel_pct_allowed_30d,

    -- ── Season-to-date offense ────────────────────────────────────────────────
    count(*) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)  as games_std,
    round(avg(runs_scored) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 3) as runs_per_game_std,
    round(
        sum(woba_value_sum) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(woba_denom_sum) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as woba_std,
    round(
        sum(xwoba_sum) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(xwoba_denom) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as xwoba_std,
    round(
        sum(strikeouts) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as k_pct_std,
    round(
        sum(walks) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(pa_count) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as bb_pct_std,
    round(
        sum(total_bases) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(at_bats) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as slugging_std,
    round(
        sum(hard_hit_balls) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as hard_hit_pct_std,
    round(
        sum(barrels) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(batted_balls) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as barrel_pct_std,

    -- ── Season-to-date pitching ───────────────────────────────────────────────
    round(avg(runs_allowed) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 3) as runs_allowed_per_game_std,
    round(
        sum(woba_value_sum_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(woba_denom_sum_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as woba_against_std,
    round(
        sum(xwoba_sum_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(xwoba_denom_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as xwoba_against_std,
    round(
        sum(strikeouts_recorded) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as k_pct_recorded_std,
    round(
        sum(walks_allowed) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(pa_count_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as bb_pct_allowed_std,
    round(
        sum(hard_hit_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as hard_hit_pct_allowed_std,
    round(
        sum(barrels_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row)
        / nullif(sum(batted_balls_against) over (partition by team, home_away_flag, game_year order by game_date rows between unbounded preceding and current row), 0)
    , 3) as barrel_pct_allowed_std

from game_combined
order by team, home_away_flag, game_date

{% else %}

select * from baseball_data.lakehouse_ext.mart_home_away_splits

{% endif %}

-- =============================================================================
-- mart_team_rolling_pitching.sql
-- Grain: one row per team × game date (regular season games only)
-- Purpose: Rolling pitching statistics at 7/14/30-day and season-to-date
--          windows for use in game outcome prediction models.
--          Metrics reflect runs allowed and batted-ball quality against,
--          with starter vs. bullpen splits.
-- Join keys: team (team_abbrev), game_date
-- =============================================================================

{{
    config(
        materialized = 'incremental',
        unique_key = ['game_pk', 'team'],
        on_schema_change = 'sync_all_columns'
    )
}}

with

pitches as (

    select p.*
    from {{ ref('stg_batter_pitches') }} p
    {% if is_incremental() %}
    where p.game_type = 'R'
      and p.game_date >= (select date_trunc('year', max(game_date)) from {{ this }})
    {% else %}
    where p.game_type = 'R'
    {% endif %}

),

game_results as (

    select gr.*
    from {{ ref('mart_game_results') }} gr
    {% if is_incremental() %}
    where gr.game_type = 'R'
      and gr.game_date >= (select date_trunc('year', max(game_date)) from {{ this }})
    {% else %}
    where gr.game_type = 'R'
    {% endif %}

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Tag each pitch with the fielding (pitching) team and whether the pitcher
-- is the starter (first pitcher to throw in the game for that team).
-- ─────────────────────────────────────────────────────────────────────────────
pitches_tagged as (

    select
        game_pk,
        game_date,
        game_year,
        at_bat_number,
        pitch_number,
        pitcher_id,

        case
            when inning_half = 'Top' then home_team
            else away_team
        end                                                         as pitching_team,

        plate_appearance_event,
        exit_velocity_mph,
        launch_speed_angle_zone,
        woba_value,
        woba_denom,
        xwoba,

        -- Is this the starter? Starter = pitcher who throws the first pitch of
        -- the game for this team. Use dense_rank so doubleheaders don't bleed.
        (dense_rank() over (
            partition by game_pk,
            case when inning_half = 'Top' then home_team else away_team end
            order by at_bat_number, pitch_number
        ) = 1)::boolean                                             as _is_first_pitch,

        -- Identify which pitcher_id started for this team in this game
        first_value(pitcher_id) over (
            partition by game_pk,
            case when inning_half = 'Top' then home_team else away_team end
            order by at_bat_number, pitch_number
            rows between unbounded preceding and unbounded following
        )                                                           as starting_pitcher_id

    from pitches

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Plate-appearance level: terminal pitches only, with starter/reliever flag
-- ─────────────────────────────────────────────────────────────────────────────
plate_appearances as (

    select
        game_pk,
        game_date,
        game_year,
        pitching_team,

        (pitcher_id = starting_pitcher_id)::boolean                as is_starter_pa,

        -- PA outcomes from the pitching team's perspective
        woba_value,
        woba_denom,
        xwoba,

        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                                 as is_strikeout,

        (plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                                 as is_walk,

        -- Batted ball quality allowed
        (exit_velocity_mph >= 95)::boolean                          as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean                      as is_barrel, 
        exit_velocity_mph

    from pitches_tagged
    where plate_appearance_event is not null

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Game-level pitching: one row per pitching team × game
-- ─────────────────────────────────────────────────────────────────────────────
game_pitching as (

    select
        pa.game_pk,
        pa.game_date,
        pa.game_year,
        pa.pitching_team                                            as team,

        -- Overall
        count(*)                                                    as pa_count,
        sum(pa.woba_value)                                          as woba_value_sum,
        sum(pa.woba_denom)                                          as woba_denom_sum,
        sum(pa.xwoba)                                               as xwoba_sum,
        count(pa.xwoba)                                             as xwoba_denom,
        sum(pa.is_strikeout::integer)                               as strikeouts,
        sum(pa.is_walk::integer)                                    as walks,
        sum(pa.is_hard_hit::integer)                                as hard_hit_balls,
        sum(pa.is_barrel::integer)                                  as barrels,
        count(case when pa.exit_velocity_mph is not null then 1 end) as batted_balls,

        -- Starter split
        sum(pa.is_starter_pa::integer)                              as starter_pa_count,
        sum(case when pa.is_starter_pa then pa.woba_value  else 0 end) as starter_woba_value_sum,
        sum(case when pa.is_starter_pa then pa.woba_denom  else 0 end) as starter_woba_denom_sum,
        sum(case when pa.is_starter_pa then pa.xwoba       else null end) as starter_xwoba_sum,
        count(case when pa.is_starter_pa and pa.xwoba is not null then 1 end) as starter_xwoba_denom,
        sum(case when pa.is_starter_pa then pa.is_strikeout::integer else 0 end) as starter_strikeouts,
        sum(case when pa.is_starter_pa then pa.is_walk::integer     else 0 end) as starter_walks,
        sum(case when pa.is_starter_pa then pa.is_hard_hit::integer else 0 end) as starter_hard_hit,
        sum(case when pa.is_starter_pa then pa.is_barrel::integer   else 0 end) as starter_barrels,
        count(case when pa.is_starter_pa and pa.exit_velocity_mph is not null then 1 end) as starter_batted_balls,

        -- Bullpen split
        sum((not pa.is_starter_pa)::integer)                        as bullpen_pa_count,
        sum(case when not pa.is_starter_pa then pa.woba_value  else 0 end) as bullpen_woba_value_sum,
        sum(case when not pa.is_starter_pa then pa.woba_denom  else 0 end) as bullpen_woba_denom_sum,
        sum(case when not pa.is_starter_pa then pa.xwoba       else null end) as bullpen_xwoba_sum,
        count(case when not pa.is_starter_pa and pa.xwoba is not null then 1 end) as bullpen_xwoba_denom,
        sum(case when not pa.is_starter_pa then pa.is_strikeout::integer else 0 end) as bullpen_strikeouts,
        sum(case when not pa.is_starter_pa then pa.is_walk::integer     else 0 end) as bullpen_walks,
        sum(case when not pa.is_starter_pa then pa.is_hard_hit::integer else 0 end) as bullpen_hard_hit,
        sum(case when not pa.is_starter_pa then pa.is_barrel::integer   else 0 end) as bullpen_barrels,
        count(case when not pa.is_starter_pa and pa.exit_velocity_mph is not null then 1 end) as bullpen_batted_balls

    from plate_appearances pa
    group by pa.game_pk, pa.game_date, pa.game_year, pa.pitching_team

),

-- Attach runs allowed from mart_game_results
game_pitching_with_runs as (

    select
        gp.game_pk,
        gp.game_date,
        gp.game_year,
        gp.team,
        gp.pa_count,
        gp.woba_value_sum,
        gp.woba_denom_sum,
        gp.xwoba_sum,
        gp.xwoba_denom,
        gp.strikeouts,
        gp.walks,
        gp.hard_hit_balls,
        gp.barrels,
        gp.batted_balls,
        gp.starter_pa_count,
        gp.starter_woba_value_sum,
        gp.starter_woba_denom_sum,
        gp.starter_xwoba_sum,
        gp.starter_xwoba_denom,
        gp.starter_strikeouts,
        gp.starter_walks,
        gp.starter_hard_hit,
        gp.starter_barrels,
        gp.starter_batted_balls,
        gp.bullpen_pa_count,
        gp.bullpen_woba_value_sum,
        gp.bullpen_woba_denom_sum,
        gp.bullpen_xwoba_sum,
        gp.bullpen_xwoba_denom,
        gp.bullpen_strikeouts,
        gp.bullpen_walks,
        gp.bullpen_hard_hit,
        gp.bullpen_barrels,
        gp.bullpen_batted_balls,

        -- Runs allowed = opponent's final score
        case
            when gr.home_team = gp.team then gr.away_final_score
            else gr.home_final_score
        end                                                         as runs_allowed

    from game_pitching gp
    join game_results gr on gp.game_pk = gr.game_pk

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Rolling windows
-- ─────────────────────────────────────────────────────────────────────────────
rolling as (

    select
        game_pk,
        game_date,
        game_year,
        team,

        -- ── Game-level actuals ──────────────────────────────────────────────────
        runs_allowed,
        pa_count,
        round(
            case when woba_denom_sum  > 0
                 then (woba_value_sum  / woba_denom_sum)::numeric else null end, 3
        )                                                           as woba_against,
        round(
            case when xwoba_denom     > 0
                 then (xwoba_sum      / xwoba_denom)::numeric     else null end, 3
        )                                                           as xwoba_against,
        round(
            case when pa_count        > 0
                 then (strikeouts::numeric / pa_count)            else null end, 3
        )                                                           as k_pct,
        round(
            case when pa_count        > 0
                 then (walks::numeric     / pa_count)             else null end, 3
        )                                                           as bb_pct,
        round(
            case when batted_balls    > 0
                 then (hard_hit_balls::numeric / batted_balls)    else null end, 3
        )                                                           as hard_hit_pct_allowed,
        round(
            case when batted_balls    > 0
                 then (barrels::numeric / batted_balls)           else null end, 3
        )                                                           as barrel_pct_allowed,

        -- ── Rolling 7-day ────────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '7 days' preceding and current row) as games_7d,
        round(avg(runs_allowed) over (partition by team order by game_date range between interval '7 days' preceding and current row), 3) as runs_allowed_per_game_7d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as woba_against_7d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xwoba_against_7d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as k_pct_7d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bb_pct_7d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as hard_hit_pct_allowed_7d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as barrel_pct_allowed_7d,

        -- Starter 7d
        round(
            sum(starter_woba_value_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_woba_denom_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_woba_against_7d,
        round(
            sum(starter_xwoba_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_xwoba_denom) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_xwoba_against_7d,
        round(
            sum(starter_strikeouts) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_k_pct_7d,
        round(
            sum(starter_walks) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_bb_pct_7d,
        round(
            sum(starter_hard_hit) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_hard_hit_pct_7d,
        round(
            sum(starter_barrels) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as starter_barrel_pct_7d,

        -- Bullpen 7d
        round(
            sum(bullpen_woba_value_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_woba_denom_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_woba_against_7d,
        round(
            sum(bullpen_xwoba_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_xwoba_denom) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_xwoba_against_7d,
        round(
            sum(bullpen_strikeouts) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_k_pct_7d,
        round(
            sum(bullpen_walks) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_bb_pct_7d,
        round(
            sum(bullpen_hard_hit) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_hard_hit_pct_7d,
        round(
            sum(bullpen_barrels) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bullpen_barrel_pct_7d,

        -- ── Rolling 14-day ───────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '14 days' preceding and current row) as games_14d,
        round(avg(runs_allowed) over (partition by team order by game_date range between interval '14 days' preceding and current row), 3) as runs_allowed_per_game_14d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as woba_against_14d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xwoba_against_14d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as k_pct_14d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bb_pct_14d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as hard_hit_pct_allowed_14d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as barrel_pct_allowed_14d,

        -- Starter 14d
        round(
            sum(starter_woba_value_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_woba_denom_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_woba_against_14d,
        round(
            sum(starter_xwoba_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_xwoba_denom) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_xwoba_against_14d,
        round(
            sum(starter_strikeouts) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_k_pct_14d,
        round(
            sum(starter_walks) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_bb_pct_14d,
        round(
            sum(starter_hard_hit) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_hard_hit_pct_14d,
        round(
            sum(starter_barrels) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as starter_barrel_pct_14d,

        -- Bullpen 14d
        round(
            sum(bullpen_woba_value_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_woba_denom_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_woba_against_14d,
        round(
            sum(bullpen_xwoba_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_xwoba_denom) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_xwoba_against_14d,
        round(
            sum(bullpen_strikeouts) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_k_pct_14d,
        round(
            sum(bullpen_walks) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_bb_pct_14d,
        round(
            sum(bullpen_hard_hit) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_hard_hit_pct_14d,
        round(
            sum(bullpen_barrels) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bullpen_barrel_pct_14d,

        -- ── Rolling 30-day ───────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '30 days' preceding and current row) as games_30d,
        round(avg(runs_allowed) over (partition by team order by game_date range between interval '30 days' preceding and current row), 3) as runs_allowed_per_game_30d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as woba_against_30d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xwoba_against_30d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as k_pct_30d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bb_pct_30d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as hard_hit_pct_allowed_30d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as barrel_pct_allowed_30d,

        -- Starter 30d
        round(
            sum(starter_woba_value_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_woba_denom_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_woba_against_30d,
        round(
            sum(starter_xwoba_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_xwoba_denom) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_xwoba_against_30d,
        round(
            sum(starter_strikeouts) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_k_pct_30d,
        round(
            sum(starter_walks) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_bb_pct_30d,
        round(
            sum(starter_hard_hit) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_hard_hit_pct_30d,
        round(
            sum(starter_barrels) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as starter_barrel_pct_30d,

        -- Bullpen 30d
        round(
            sum(bullpen_woba_value_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_woba_denom_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_woba_against_30d,
        round(
            sum(bullpen_xwoba_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_xwoba_denom) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_xwoba_against_30d,
        round(
            sum(bullpen_strikeouts) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_k_pct_30d,
        round(
            sum(bullpen_walks) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_bb_pct_30d,
        round(
            sum(bullpen_hard_hit) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_hard_hit_pct_30d,
        round(
            sum(bullpen_barrels) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bullpen_barrel_pct_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────────
        count(*) over (partition by team, game_year order by game_date rows between unbounded preceding and current row) as games_std,
        round(avg(runs_allowed) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 3) as runs_allowed_per_game_std,
        round(
            sum(woba_value_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as woba_against_std,
        round(
            sum(xwoba_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xwoba_against_std,
        round(
            sum(strikeouts) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as k_pct_std,
        round(
            sum(walks) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bb_pct_std,
        round(
            sum(hard_hit_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as hard_hit_pct_allowed_std,
        round(
            sum(barrels) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as barrel_pct_allowed_std,

        -- Starter std
        round(
            sum(starter_woba_value_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_woba_denom_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_woba_against_std,
        round(
            sum(starter_xwoba_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_xwoba_denom) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_xwoba_against_std,
        round(
            sum(starter_strikeouts) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_k_pct_std,
        round(
            sum(starter_walks) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_bb_pct_std,
        round(
            sum(starter_hard_hit) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_hard_hit_pct_std,
        round(
            sum(starter_barrels) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(starter_batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as starter_barrel_pct_std,

        -- Bullpen std
        round(
            sum(bullpen_woba_value_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_woba_denom_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_woba_against_std,
        round(
            sum(bullpen_xwoba_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_xwoba_denom) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_xwoba_against_std,
        round(
            sum(bullpen_strikeouts) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_k_pct_std,
        round(
            sum(bullpen_walks) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_bb_pct_std,
        round(
            sum(bullpen_hard_hit) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_hard_hit_pct_std,
        round(
            sum(bullpen_barrels) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(bullpen_batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bullpen_barrel_pct_std

    from game_pitching_with_runs

)

select * from rolling
{% if is_incremental() %}
where game_date > (select max(game_date) from {{ this }})
{% endif %}
order by team, game_date

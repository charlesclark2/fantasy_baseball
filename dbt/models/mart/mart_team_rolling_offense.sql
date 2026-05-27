-- =============================================================================
-- mart_team_rolling_offense.sql
-- Grain: one row per team × game date (regular season games only)
-- Purpose: Rolling offensive statistics at 7/14/30-day and season-to-date
--          windows for use in game outcome prediction models.
--          Metrics reflect the batting team's output in that game, then
--          smoothed over trailing windows ending on that game date.
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
-- Plate-appearance level: one row per terminal pitch, tagged with batting team
-- ─────────────────────────────────────────────────────────────────────────────
plate_appearances as (

    select
        game_pk,
        game_date,
        game_year,
        at_bat_number,

        -- Which team is batting this PA
        case
            when inning_half = 'Top' then away_team
            else home_team
        end                                                 as batting_team,

        -- PA-level offense metrics (populated only on terminal pitch)
        woba_value,
        woba_denom,
        xwoba,

        -- Strikeout / walk flags
        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                         as is_strikeout,

        (plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                         as is_walk,

        -- Slugging numerator: TB per PA event
        case plate_appearance_event
            when 'single'           then 1
            when 'double'           then 2
            when 'triple'           then 3
            when 'home_run'         then 4
            else 0
        end                                                 as total_bases,

        -- AB denominator for slugging (exclude walks, HBP, sac flies/bunts)
        (plate_appearance_event not in (
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_bunt', 'sac_fly_double_play'
        ) and plate_appearance_event is not null)::boolean  as is_at_bat,

        -- Batted ball quality (non-null only on in-play pitches)
        (exit_velocity_mph >= 95)::boolean                  as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean              as is_barrel, 
        exit_velocity_mph

    from pitches
    where plate_appearance_event is not null

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Game-level offense: one row per team × game
-- ─────────────────────────────────────────────────────────────────────────────
game_offense as (

    select
        pa.game_pk,
        pa.game_date,
        pa.game_year,
        pa.batting_team                                     as team,

        count(*)                                            as pa_count,
        sum(pa.woba_value)                                  as woba_value_sum,
        sum(pa.woba_denom)                                  as woba_denom_sum,
        sum(pa.xwoba)                                       as xwoba_sum,
        -- xwoba denom: only in-play PAs have xwoba populated
        count(pa.xwoba)                                     as xwoba_denom,

        sum(pa.is_strikeout::integer)                       as strikeouts,
        sum(pa.is_walk::integer)                            as walks,
        sum(pa.total_bases)                                 as total_bases,
        sum(pa.is_at_bat::integer)                          as at_bats,

        -- Hard-hit and barrel: only count PAs with batted ball data
        sum(pa.is_hard_hit::integer)                        as hard_hit_balls,
        sum(pa.is_barrel::integer)                          as barrels,
        count(case when exit_velocity_mph is not null then 1 end) as batted_balls

    from plate_appearances pa
    group by pa.game_pk, pa.game_date, pa.game_year, pa.batting_team

),

-- Attach runs scored from mart_game_results
game_offense_with_runs as (

    select
        go.game_pk,
        go.game_date,
        go.game_year,
        go.team,
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
        end                                                 as runs_scored

    from game_offense go
    join game_results gr on go.game_pk = gr.game_pk

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Rolling windows
-- Window frames use RANGE so date arithmetic drives the boundary, not row count.
-- Season-to-date uses ROWS UNBOUNDED (restart each season year).
-- ─────────────────────────────────────────────────────────────────────────────
rolling as (

    select
        game_pk,
        game_date,
        game_year,
        team,

        -- ── Game-level actuals ──────────────────────────────────────────────────
        runs_scored,
        pa_count,
        round(
            case when woba_denom_sum  > 0
                 then (woba_value_sum  / woba_denom_sum)::numeric else null end, 3
        )                                                   as woba,
        round(
            case when xwoba_denom     > 0
                 then (xwoba_sum      / xwoba_denom)::numeric     else null end, 3
        )                                                   as xwoba,
        round(
            case when pa_count        > 0
                 then (strikeouts::numeric / pa_count)            else null end, 3
        )                                                   as k_pct,
        round(
            case when pa_count        > 0
                 then (walks::numeric     / pa_count)             else null end, 3
        )                                                   as bb_pct,
        round(
            case when at_bats         > 0
                 then (total_bases::numeric / at_bats)            else null end, 3
        )                                                   as slugging,
        round(
            case when batted_balls    > 0
                 then (hard_hit_balls::numeric / batted_balls)    else null end, 3
        )                                                   as hard_hit_pct,
        round(
            case when batted_balls    > 0
                 then (barrels::numeric / batted_balls)           else null end, 3
        )                                                   as barrel_pct,

        -- ── Rolling 7-day ────────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '7 days' preceding and current row)  as games_7d,
        round(avg(runs_scored) over (partition by team order by game_date range between interval '7 days' preceding and current row), 3) as runs_per_game_7d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as woba_7d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xwoba_7d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as k_pct_7d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bb_pct_7d,
        round(
            sum(total_bases) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as slugging_7d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as hard_hit_pct_7d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as barrel_pct_7d,

        -- ── Rolling 14-day ───────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '14 days' preceding and current row) as games_14d,
        round(avg(runs_scored) over (partition by team order by game_date range between interval '14 days' preceding and current row), 3) as runs_per_game_14d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as woba_14d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xwoba_14d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as k_pct_14d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bb_pct_14d,
        round(
            sum(total_bases) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as slugging_14d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as hard_hit_pct_14d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as barrel_pct_14d,

        -- ── Rolling 30-day ───────────────────────────────────────────────────────
        count(*) over (partition by team order by game_date range between interval '30 days' preceding and current row) as games_30d,
        round(avg(runs_scored) over (partition by team order by game_date range between interval '30 days' preceding and current row), 3) as runs_per_game_30d,
        round(
            sum(woba_value_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as woba_30d,
        round(
            sum(xwoba_sum) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xwoba_30d,
        round(
            sum(strikeouts) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as k_pct_30d,
        round(
            sum(walks) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pa_count) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bb_pct_30d,
        round(
            sum(total_bases) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(at_bats) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as slugging_30d,
        round(
            sum(hard_hit_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as hard_hit_pct_30d,
        round(
            sum(barrels) over (partition by team order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by team order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as barrel_pct_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────────
        count(*) over (partition by team, game_year order by game_date rows between unbounded preceding and current row) as games_std,
        round(avg(runs_scored) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 3) as runs_per_game_std,
        round(
            sum(woba_value_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as woba_std,
        round(
            sum(xwoba_sum) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xwoba_std,
        round(
            sum(strikeouts) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as k_pct_std,
        round(
            sum(walks) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pa_count) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bb_pct_std,
        round(
            sum(total_bases) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(at_bats) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as slugging_std,
        round(
            sum(hard_hit_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as hard_hit_pct_std,
        round(
            sum(barrels) over (partition by team, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by team, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as barrel_pct_std

    from game_offense_with_runs

)

select * from rolling
{% if is_incremental() %}
where game_date > (select max(game_date) from {{ this }})
{% endif %}
order by team, game_date

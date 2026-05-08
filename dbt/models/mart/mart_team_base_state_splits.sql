-- =============================================================================
-- mart_team_base_state_splits.sql
-- Card 8.Y — Base-state-split performance metrics.
--
-- Grain: one row per (team_abbrev, game_pk) for every regular-season game.
--
-- For each team, we expose pre-game trailing 30-day wOBA / xwOBA splits by
-- base state (any runners on; runners in scoring position) plus a pure
-- sequencing rate (runs scored per PA with runners on). Defensive equivalents
-- (pitching-team perspective) are computed for the headline wOBA splits.
--
-- The wOBA gap (wOBA − xwOBA) restricted to base states isolates the
-- sequencing-luck component the model otherwise can't see — a team
-- converting traffic into runs above what contact quality predicts is a
-- regression candidate the market may not fully price.
--
-- LEAKAGE GUARD: rolling window upper bound is `interval '1 day' preceding`,
-- matching mart_bullpen_handedness_splits (Card 8.L). Doubleheader-safe:
-- aggregation collapses to calendar-date level before windowing.
--
-- RELIABILITY GATE: outputs are NULL when fewer than 50 plate appearances
-- with runners on occurred in the trailing 30-day window for that team
-- (early-season noise floor; PA-count threshold avoids spurious rolling
-- windows where the rolling denominators are tiny).
--
-- Imputation priors (applied in betting_ml/utils/preprocessing.py — never
-- COALESCE in dbt):
--   wOBA-with-runners-on            ~0.330  (slightly elevated vs. league wOBA)
--   xwOBA-with-runners-on           ~0.325
--   wOBA-with-RISP                  ~0.335  (pitchers pitch carefully with RISP)
--   xwOBA-with-RISP                 ~0.325
--   runs_per_baserunner             ~0.25   (typical conversion rate)
--   wOBA-against splits             mirror offensive priors
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with

pitches as (

    select
        game_pk,
        game_date,
        game_year,
        at_bat_number,
        pitch_number,
        home_team,
        away_team,
        inning_half,
        runner_on_1b_id,
        runner_on_2b_id,
        runner_on_3b_id,
        plate_appearance_event,
        woba_value,
        woba_denom,
        xwoba,
        pre_pitch_bat_score,
        post_pitch_bat_score
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'

),

-- ── Base state at PA START (first pitch of each PA) ──────────────────────────
-- Within a PA the pre-pitch base state can shift due to pickoffs/steals/balks,
-- so we anchor base state at PA-start to match the standard wOBA-with-RISP
-- convention. Both runners_on and risp filters use these PA-start values.
pa_start_state as (

    select
        game_pk,
        at_bat_number,
        (runner_on_1b_id is not null
            or runner_on_2b_id is not null
            or runner_on_3b_id is not null)             as runners_on,
        (runner_on_2b_id is not null
            or runner_on_3b_id is not null)             as risp
    from pitches
    where pitch_number = 1

),

-- ── Per-PA terminal stats with batting / pitching team labels ────────────────
pa_terminal as (

    select
        game_pk,
        game_date::date    as game_date,
        game_year,
        at_bat_number,
        case when inning_half = 'Top' then away_team else home_team end
                            as batting_team,
        case when inning_half = 'Top' then home_team else away_team end
                            as pitching_team,
        woba_value,
        woba_denom,
        xwoba,
        coalesce(post_pitch_bat_score - pre_pitch_bat_score, 0)
                            as runs_scored_pa
    from pitches
    where plate_appearance_event is not null

),

pa_combined as (

    select
        t.*,
        s.runners_on,
        s.risp
    from pa_terminal t
    inner join pa_start_state s
        on  t.game_pk        = s.game_pk
        and t.at_bat_number  = s.at_bat_number

),

-- ── Per-PA labeled rows: one for each team perspective (offense + defense) ──
-- A PA has the batting team contribute on offense and the pitching team
-- contribute on defense. Tagging both rows here lets us aggregate by team
-- once and keep offensive and defensive numerators separate via role-gated
-- conditional sums.
pa_labeled as (

    select
        game_pk,
        game_date,
        game_year,
        batting_team       as team_abbrev,
        'off'              as role,
        runners_on,
        risp,
        woba_value,
        woba_denom,
        xwoba,
        runs_scored_pa
    from pa_combined

    union all

    select
        game_pk,
        game_date,
        game_year,
        pitching_team      as team_abbrev,
        'def'              as role,
        runners_on,
        risp,
        woba_value,
        woba_denom,
        xwoba,
        runs_scored_pa
    from pa_combined

),

-- ── Game × team aggregation ─────────────────────────────────────────────────
-- Conditional sums isolate offensive vs. defensive contributions inside a
-- single team's row. xwoba sums use the same coalesce-onto-woba_value pattern
-- as mart_bullpen_handedness_splits so non-in-play PAs (which have NULL
-- xwoba but non-NULL woba_value) still contribute to the xwoba aggregate.
game_team as (

    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,

        -- ── Offensive: runners_on filter ────────────────────────────────────
        sum(case when role = 'off' and runners_on
                 then woba_value end)                       as off_woba_num_ron,
        sum(case when role = 'off' and runners_on
                 then woba_denom end)                       as off_woba_denom_ron,
        sum(case when role = 'off' and runners_on and woba_denom = 1
                 then coalesce(xwoba, woba_value)
                 else 0 end)                                as off_xwoba_num_ron,
        sum(case when role = 'off' and runners_on
                 then coalesce(woba_denom, 0)
                 else 0 end)                                as off_xwoba_denom_ron,

        -- ── Offensive: risp filter ──────────────────────────────────────────
        sum(case when role = 'off' and risp
                 then woba_value end)                       as off_woba_num_risp,
        sum(case when role = 'off' and risp
                 then woba_denom end)                       as off_woba_denom_risp,
        sum(case when role = 'off' and risp and woba_denom = 1
                 then coalesce(xwoba, woba_value)
                 else 0 end)                                as off_xwoba_num_risp,
        sum(case when role = 'off' and risp
                 then coalesce(woba_denom, 0)
                 else 0 end)                                as off_xwoba_denom_risp,

        -- ── Offensive: sequencing rate ──────────────────────────────────────
        sum(case when role = 'off' and runners_on
                 then runs_scored_pa
                 else 0 end)                                as off_runs_with_ron,
        sum(case when role = 'off' and runners_on
                 then 1 else 0 end)                         as off_pa_with_ron,

        -- ── Defensive: runners_on (woba-against) ────────────────────────────
        sum(case when role = 'def' and runners_on
                 then woba_value end)                       as def_woba_num_ron,
        sum(case when role = 'def' and runners_on
                 then woba_denom end)                       as def_woba_denom_ron,

        -- ── Defensive: risp (woba-against) ──────────────────────────────────
        sum(case when role = 'def' and risp
                 then woba_value end)                       as def_woba_num_risp,
        sum(case when role = 'def' and risp
                 then woba_denom end)                       as def_woba_denom_risp

    from pa_labeled
    group by game_pk, game_date, game_year, team_abbrev

),

-- ── Collapse to calendar-date level (doubleheader-safe) ─────────────────────
date_team as (

    select
        game_date,
        game_year,
        team_abbrev,

        sum(coalesce(off_woba_num_ron, 0))      as off_woba_num_ron,
        sum(coalesce(off_woba_denom_ron, 0))    as off_woba_denom_ron,
        sum(off_xwoba_num_ron)                  as off_xwoba_num_ron,
        sum(off_xwoba_denom_ron)                as off_xwoba_denom_ron,

        sum(coalesce(off_woba_num_risp, 0))     as off_woba_num_risp,
        sum(coalesce(off_woba_denom_risp, 0))   as off_woba_denom_risp,
        sum(off_xwoba_num_risp)                 as off_xwoba_num_risp,
        sum(off_xwoba_denom_risp)               as off_xwoba_denom_risp,

        sum(off_runs_with_ron)                  as off_runs_with_ron,
        sum(off_pa_with_ron)                    as off_pa_with_ron,

        sum(coalesce(def_woba_num_ron, 0))      as def_woba_num_ron,
        sum(coalesce(def_woba_denom_ron, 0))    as def_woba_denom_ron,

        sum(coalesce(def_woba_num_risp, 0))     as def_woba_num_risp,
        sum(coalesce(def_woba_denom_risp, 0))   as def_woba_denom_risp
    from game_team
    group by game_date, game_year, team_abbrev

),

-- ── Rolling 30-day windows (strictly before each game date) ─────────────────
-- Snowflake does not support the SQL-standard `WINDOW w AS (...)` clause, so
-- each `OVER (...)` spec is inlined.
rolling as (

    select
        game_date,
        team_abbrev,

        -- Reliability gate input — total PAs with runners on across the window.
        sum(off_pa_with_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding
                      and interval '1 day'   preceding
        )                                       as pa_with_runners_on_30d,

        -- ── Offensive aggregates ────────────────────────────────────────────
        sum(off_woba_num_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_woba_num_ron_30d,
        sum(off_woba_denom_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_woba_denom_ron_30d,
        sum(off_xwoba_num_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_xwoba_num_ron_30d,
        sum(off_xwoba_denom_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_xwoba_denom_ron_30d,

        sum(off_woba_num_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_woba_num_risp_30d,
        sum(off_woba_denom_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_woba_denom_risp_30d,
        sum(off_xwoba_num_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_xwoba_num_risp_30d,
        sum(off_xwoba_denom_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_xwoba_denom_risp_30d,

        sum(off_runs_with_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as off_runs_with_ron_30d,

        -- ── Defensive aggregates ────────────────────────────────────────────
        sum(def_woba_num_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as def_woba_num_ron_30d,
        sum(def_woba_denom_ron) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as def_woba_denom_ron_30d,

        sum(def_woba_num_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as def_woba_num_risp_30d,
        sum(def_woba_denom_risp) over (
            partition by team_abbrev order by game_date
            range between interval '30 days' preceding and interval '1 day' preceding
        )                                       as def_woba_denom_risp_30d
    from date_team

),

-- ── Apply reliability gate + project back to game_pk grain ──────────────────
-- Each game_pk on a date inherits the rolling values for its team. For
-- doubleheaders both halves get the same pre-game values.
game_spine as (

    select distinct game_pk, game_date, game_year, team_abbrev
    from game_team

),

final as (

    select
        gs.game_pk,
        gs.game_date,
        gs.game_year,
        gs.team_abbrev,

        r.pa_with_runners_on_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.off_woba_num_ron_30d::float
                 / nullif(r.off_woba_denom_ron_30d, 0),
                 4
             )
             else null
        end                                       as woba_with_runners_on_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.off_xwoba_num_ron_30d::float
                 / nullif(r.off_xwoba_denom_ron_30d, 0),
                 4
             )
             else null
        end                                       as xwoba_with_runners_on_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.off_woba_num_risp_30d::float
                 / nullif(r.off_woba_denom_risp_30d, 0),
                 4
             )
             else null
        end                                       as woba_with_risp_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.off_xwoba_num_risp_30d::float
                 / nullif(r.off_xwoba_denom_risp_30d, 0),
                 4
             )
             else null
        end                                       as xwoba_with_risp_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.off_runs_with_ron_30d::float
                 / nullif(r.pa_with_runners_on_30d, 0),
                 4
             )
             else null
        end                                       as runs_per_baserunner_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.def_woba_num_ron_30d::float
                 / nullif(r.def_woba_denom_ron_30d, 0),
                 4
             )
             else null
        end                                       as woba_against_with_runners_on_30d,

        case when r.pa_with_runners_on_30d >= 50
             then round(
                 r.def_woba_num_risp_30d::float
                 / nullif(r.def_woba_denom_risp_30d, 0),
                 4
             )
             else null
        end                                       as woba_against_with_risp_30d

    from game_spine gs
    left join rolling r
        on  r.game_date    = gs.game_date
        and r.team_abbrev  = gs.team_abbrev

)

select * from final

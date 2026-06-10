-- =============================================================================
-- feature_pitcher_batter_h2h_matchups.sql
-- Grain: one row per game_pk
-- Purpose: Lineup-level historical head-to-head matchup quality between each
--          batter in the lineup and the OPPOSING starting pitcher. Aggregates
--          per-pair PA history from mart_pitcher_batter_history with strict
--          leakage guard (game_date < prediction game_date) and applies Bayesian
--          shrinkage toward the league prior at low PA counts.
--
-- Shrinkage:
--   adjusted_woba  = (career_pa * raw_woba  + k * woba_prior)  / (career_pa + k)
--   adjusted_xwoba = (career_pa * raw_xwoba + k * xwoba_prior) / (career_pa + k)
--   k = 50, woba_prior = 0.320, xwoba_prior = 0.310
--   For zero-PA pairs the formula returns the prior automatically.
--
-- Lineup-level columns (per side, computed across the 9 lineup slots):
--   *_h2h_woba          simple AVG of adjusted_woba across slots with a known batter
--   *_h2h_xwoba         simple AVG of adjusted_xwoba across slots with a known batter
--   *_h2h_pa_coverage   fraction of slots with career_pa >= 10 against this starter
--
-- Card 8.J.
-- =============================================================================

{{ config(materialized='table') }}

with games as (
    select
        game_pk,
        game_date::date as game_date
    -- A2.4: spine on mart_game_spine (completed + today's scheduled games) instead of
    -- completed-only mart_game_results, so pitcher-batter h2h matchups exist for today's
    -- slate once lineups post. Downstream leakage guards stay game_date < anchor_date.
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'
),

-- Probable starter per side
starters as (
    select
        game_pk,
        side,
        probable_pitcher_id as pitcher_id
    from {{ ref('stg_statsapi_probable_pitchers') }}
    where probable_pitcher_id is not null
),

home_starter as (
    select game_pk, pitcher_id from starters where side = 'home'
),
away_starter as (
    select game_pk, pitcher_id from starters where side = 'away'
),

lineups as (
    select
        game_pk,
        home_away,
        slot_1_player_id,
        slot_2_player_id,
        slot_3_player_id,
        slot_4_player_id,
        slot_5_player_id,
        slot_6_player_id,
        slot_7_player_id,
        slot_8_player_id,
        slot_9_player_id
    from {{ ref('stg_statsapi_lineups_wide') }}
),

-- Unpivot: one row per (game_pk, side, slot, batter_id)
lineup_slots as (
    select game_pk, home_away as side, 1 as slot, slot_1_player_id as batter_id from lineups
    union all
    select game_pk, home_away, 2, slot_2_player_id from lineups
    union all
    select game_pk, home_away, 3, slot_3_player_id from lineups
    union all
    select game_pk, home_away, 4, slot_4_player_id from lineups
    union all
    select game_pk, home_away, 5, slot_5_player_id from lineups
    union all
    select game_pk, home_away, 6, slot_6_player_id from lineups
    union all
    select game_pk, home_away, 7, slot_7_player_id from lineups
    union all
    select game_pk, home_away, 8, slot_8_player_id from lineups
    union all
    select game_pk, home_away, 9, slot_9_player_id from lineups
),

-- Attach the OPPOSING starter to each lineup slot
slot_opp_pitcher as (
    select
        ls.game_pk,
        ls.side,
        ls.slot,
        ls.batter_id,
        case when ls.side = 'home' then a_st.pitcher_id else h_st.pitcher_id end
            as opp_pitcher_id
    from lineup_slots ls
    left join home_starter h_st on h_st.game_pk = ls.game_pk
    left join away_starter a_st on a_st.game_pk = ls.game_pk
    where ls.batter_id is not null
),

-- Aggregate H2H history for each (batter, opposing pitcher) pair, leakage-guarded
slot_h2h as (
    select
        sop.game_pk,
        sop.side,
        sop.slot,
        sop.batter_id,
        sop.opp_pitcher_id,
        coalesce(sum(h.pa_count),       0)  as career_pa,
        coalesce(sum(h.woba_value_sum), 0)  as woba_value_sum,
        coalesce(sum(h.woba_denom_sum), 0)  as woba_denom_sum,
        coalesce(sum(h.xwoba_sum),      0)  as xwoba_sum,
        coalesce(sum(h.xwoba_obs),      0)  as xwoba_obs
    from slot_opp_pitcher sop
    join games g
        on g.game_pk = sop.game_pk
    left join {{ ref('mart_pitcher_batter_history') }} h
        on  h.pitcher_id = sop.opp_pitcher_id
        and h.batter_id  = sop.batter_id
        and h.game_date  < g.game_date
    group by sop.game_pk, sop.side, sop.slot, sop.batter_id, sop.opp_pitcher_id
),

-- Bayesian shrinkage. With k=50 and zero PA, both adjusted_* return the prior.
slot_adj as (
    select
        s.game_pk,
        s.side,
        s.slot,
        s.batter_id,
        s.opp_pitcher_id,
        s.career_pa,
        case when s.opp_pitcher_id is null then null
             else (coalesce(s.woba_value_sum, 0) + 50 * 0.320)
                  / (coalesce(s.woba_denom_sum, 0) + 50)
        end                                                     as adjusted_woba,
        case when s.opp_pitcher_id is null then null
             else (coalesce(s.xwoba_sum, 0)      + 50 * 0.310)
                  / (coalesce(s.xwoba_obs, 0)    + 50)
        end                                                     as adjusted_xwoba
    from slot_h2h s
),

-- Lineup-level aggregation: simple average across the 9 slots
lineup_agg as (
    select
        game_pk,
        side,
        avg(adjusted_woba)                                                  as h2h_woba,
        avg(adjusted_xwoba)                                                 as h2h_xwoba,
        sum(case when career_pa >= 10 then 1 else 0 end)::float
            / nullif(count(*), 0)                                           as h2h_pa_coverage
    from slot_adj
    where adjusted_woba is not null   -- exclude slots where the opposing starter is unknown
    group by game_pk, side
),

home_agg as (select * from lineup_agg where side = 'home'),
away_agg as (select * from lineup_agg where side = 'away')

select
    g.game_pk,

    -- Home lineup vs. away starter
    round(h_agg.h2h_woba,         4)        as home_lineup_vs_away_starter_h2h_woba,
    round(h_agg.h2h_xwoba,        4)        as home_lineup_vs_away_starter_h2h_xwoba,
    round(h_agg.h2h_pa_coverage,  4)        as home_lineup_h2h_pa_coverage,

    -- Away lineup vs. home starter
    round(a_agg.h2h_woba,         4)        as away_lineup_vs_home_starter_h2h_woba,
    round(a_agg.h2h_xwoba,        4)        as away_lineup_vs_home_starter_h2h_xwoba,
    round(a_agg.h2h_pa_coverage,  4)        as away_lineup_h2h_pa_coverage

from games g
left join home_agg h_agg on h_agg.game_pk = g.game_pk
left join away_agg a_agg on a_agg.game_pk = g.game_pk

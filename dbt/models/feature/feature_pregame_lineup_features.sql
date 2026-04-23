-- =============================================================================
-- feature_pregame_lineup_features.sql
-- Grain: one row per game_pk × side (home/away)
-- Purpose: Pre-game batting lineup features for ML. Aggregates rolling batter
--          stats and prior-season platoon splits across all 9 lineup slots.
--
-- LEAKAGE GUARD: all joins on mart_batter_rolling_stats use
--   rs.game_date::date < ls.official_date   (strictly less than)
-- Platoon splits use prior season only (game_year - 1) to avoid in-season
-- leakage from full-season aggregates.
-- =============================================================================

{{ config(materialized='table') }}

with

lineups as (
    select
        game_pk,
        official_date,
        home_away,
        (
            slot_1_player_id is not null and
            slot_2_player_id is not null and
            slot_3_player_id is not null and
            slot_4_player_id is not null and
            slot_5_player_id is not null and
            slot_6_player_id is not null and
            slot_7_player_id is not null and
            slot_8_player_id is not null and
            slot_9_player_id is not null
        )::boolean                          as has_full_lineup,
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

-- Unpivot lineup slots to one row per game × side × slot
lineup_slots as (
    select game_pk, official_date, home_away, 1 as slot, slot_1_player_id as batter_id from lineups
    union all
    select game_pk, official_date, home_away, 2, slot_2_player_id from lineups
    union all
    select game_pk, official_date, home_away, 3, slot_3_player_id from lineups
    union all
    select game_pk, official_date, home_away, 4, slot_4_player_id from lineups
    union all
    select game_pk, official_date, home_away, 5, slot_5_player_id from lineups
    union all
    select game_pk, official_date, home_away, 6, slot_6_player_id from lineups
    union all
    select game_pk, official_date, home_away, 7, slot_7_player_id from lineups
    union all
    select game_pk, official_date, home_away, 8, slot_8_player_id from lineups
    union all
    select game_pk, official_date, home_away, 9, slot_9_player_id from lineups
),

-- Most recent pre-game rolling stats for each slot
slot_stats_ranked as (
    select
        ls.game_pk,
        ls.official_date,
        ls.home_away,
        ls.slot,
        ls.batter_id,
        rs.batter_hand,
        rs.woba_30d,
        rs.xwoba_30d,
        rs.k_pct_30d,
        rs.bb_pct_30d,
        rs.hard_hit_pct_30d,
        rs.barrel_pct_30d,
        rs.whiff_rate_30d,
        rs.chase_rate_30d,
        rs.woba_std,
        rs.xwoba_std,
        rs.k_pct_std,
        rs.bb_pct_std,
        rs.hard_hit_pct_std,
        rs.barrel_pct_std,
        row_number() over (
            partition by ls.game_pk, ls.home_away, ls.slot
            order by rs.game_date::date desc
        )                                   as rn
    from lineup_slots ls
    left join {{ ref('mart_batter_rolling_stats') }} rs
        on  rs.batter_id        = ls.batter_id
        and rs.game_date::date  < ls.official_date   -- LEAKAGE GUARD
    where ls.batter_id is not null
),

-- Keep only the most recent row per slot (pre-game)
slot_pre_game as (
    select * from slot_stats_ranked where rn = 1
),

-- Aggregate slot-level stats to game × side level
lineup_agg as (
    select
        game_pk,
        official_date,
        home_away,
        count(case when batter_hand = 'L' then 1 end)           as lhb_count,
        count(case when batter_hand = 'R' then 1 end)           as rhb_count,
        round(avg(woba_30d),        3)                          as avg_woba_30d,
        round(avg(xwoba_30d),       3)                          as avg_xwoba_30d,
        round(avg(k_pct_30d),       3)                          as avg_k_pct_30d,
        round(avg(bb_pct_30d),      3)                          as avg_bb_pct_30d,
        round(avg(hard_hit_pct_30d),3)                          as avg_hard_hit_pct_30d,
        round(avg(barrel_pct_30d),  3)                          as avg_barrel_pct_30d,
        round(avg(whiff_rate_30d),  3)                          as avg_whiff_rate_30d,
        round(avg(chase_rate_30d),  3)                          as avg_chase_rate_30d,
        round(avg(woba_std),        3)                          as avg_woba_std,
        round(avg(xwoba_std),       3)                          as avg_xwoba_std,
        round(avg(k_pct_std),       3)                          as avg_k_pct_std,
        round(avg(bb_pct_std),      3)                          as avg_bb_pct_std,
        round(avg(hard_hit_pct_std),3)                          as avg_hard_hit_pct_std,
        round(avg(barrel_pct_std),  3)                          as avg_barrel_pct_std
    from slot_pre_game
    group by game_pk, official_date, home_away
),

-- Prior-season platoon splits (game_year - 1) to prevent in-season leakage
slot_platoon as (
    select
        ls.game_pk,
        ls.home_away,
        round(avg(case when hs.pitcher_hand = 'L' then hs.woba        end), 3) as avg_woba_vs_lhp,
        round(avg(case when hs.pitcher_hand = 'L' then hs.xwoba       end), 3) as avg_xwoba_vs_lhp,
        round(avg(case when hs.pitcher_hand = 'L' then hs.k_pct       end), 3) as avg_k_pct_vs_lhp,
        round(avg(case when hs.pitcher_hand = 'L' then hs.bb_pct      end), 3) as avg_bb_pct_vs_lhp,
        round(avg(case when hs.pitcher_hand = 'L' then hs.hard_hit_pct end), 3) as avg_hard_hit_pct_vs_lhp,
        round(avg(case when hs.pitcher_hand = 'R' then hs.woba        end), 3) as avg_woba_vs_rhp,
        round(avg(case when hs.pitcher_hand = 'R' then hs.xwoba       end), 3) as avg_xwoba_vs_rhp,
        round(avg(case when hs.pitcher_hand = 'R' then hs.k_pct       end), 3) as avg_k_pct_vs_rhp,
        round(avg(case when hs.pitcher_hand = 'R' then hs.bb_pct      end), 3) as avg_bb_pct_vs_rhp,
        round(avg(case when hs.pitcher_hand = 'R' then hs.hard_hit_pct end), 3) as avg_hard_hit_pct_vs_rhp
    from lineup_slots ls
    left join {{ ref('mart_batter_vs_handedness_splits') }} hs
        on  hs.batter_id    = ls.batter_id
        and hs.game_year    = year(ls.official_date) - 1   -- prior season only
    where ls.batter_id is not null
    group by ls.game_pk, ls.home_away
),

final as (
    select
        l.game_pk,
        l.official_date                             as game_date,
        year(l.official_date)                       as game_year,
        l.home_away                                 as side,
        l.has_full_lineup,

        -- Handedness composition
        coalesce(la.lhb_count, 0)                   as lhb_count,
        coalesce(la.rhb_count, 0)                   as rhb_count,

        -- 30-day rolling averages across lineup
        la.avg_woba_30d,
        la.avg_xwoba_30d,
        la.avg_k_pct_30d,
        la.avg_bb_pct_30d,
        la.avg_hard_hit_pct_30d,
        la.avg_barrel_pct_30d,
        la.avg_whiff_rate_30d,
        la.avg_chase_rate_30d,

        -- Season-to-date rolling averages across lineup
        la.avg_woba_std,
        la.avg_xwoba_std,
        la.avg_k_pct_std,
        la.avg_bb_pct_std,
        la.avg_hard_hit_pct_std,
        la.avg_barrel_pct_std,

        -- Prior-season platoon splits
        sp.avg_woba_vs_lhp,
        sp.avg_xwoba_vs_lhp,
        sp.avg_k_pct_vs_lhp,
        sp.avg_bb_pct_vs_lhp,
        sp.avg_hard_hit_pct_vs_lhp,
        sp.avg_woba_vs_rhp,
        sp.avg_xwoba_vs_rhp,
        sp.avg_k_pct_vs_rhp,
        sp.avg_bb_pct_vs_rhp,
        sp.avg_hard_hit_pct_vs_rhp

    from lineups l
    left join lineup_agg la
        on  la.game_pk   = l.game_pk
        and la.home_away = l.home_away
    left join slot_platoon sp
        on  sp.game_pk   = l.game_pk
        and sp.home_away = l.home_away
)

select * from final

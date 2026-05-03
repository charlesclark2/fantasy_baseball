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

-- Point-in-time IL status per lineup slot as of official_date
-- LEAKAGE GUARD: status_start_date <= official_date ensures only pre-game transactions used
slot_injury as (
    select
        sp.game_pk,
        sp.official_date,
        sp.home_away,
        sp.slot,
        sp.batter_id,
        coalesce(inj.is_injured, false)  as is_injured
    from slot_pre_game sp
    left join {{ ref('stg_statsapi_player_injury_status') }} inj
        on  inj.player_id         = sp.batter_id
        and inj.status_start_date <= sp.official_date   -- LEAKAGE GUARD
        and (
                inj.status_end_date  > sp.official_date
                or inj.status_end_date is null
            )
),

-- Injury-adjusted lineup quality aggregates
-- Divides by 9 (not active count) so IL slots impose a penalty on the aggregate
injury_agg as (
    select
        si.game_pk,
        si.official_date,
        si.home_away,
        count(case when si.is_injured then 1 end)       as injured_player_count,
        round(
            sum(case when not si.is_injured
                     then coalesce(sp.woba_30d,  0) else 0 end
            ) / 9.0, 3
        )                                               as injury_adj_avg_woba_30d,
        round(
            sum(case when not si.is_injured
                     then coalesce(sp.xwoba_30d, 0) else 0 end
            ) / 9.0, 3
        )                                               as injury_adj_avg_xwoba_30d
    from slot_injury si
    left join slot_pre_game sp
        on  sp.game_pk    = si.game_pk
        and sp.home_away  = si.home_away
        and sp.slot       = si.slot
    group by si.game_pk, si.official_date, si.home_away
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

-- Starter pitch archetype for each game × side (prior-season LEAKAGE GUARD)
starter_archetype as (
    select
        sf.game_pk,
        sf.side                                     as home_away,
        sf.pitcher_id,
        pa.pitch_archetype
    from {{ ref('feature_pregame_starter_features') }} sf
    left join {{ ref('mart_pitcher_pitch_archetype') }} pa
        on  pa.pitcher_id = sf.pitcher_id
        and pa.game_year  = year(sf.game_date) - 1   -- LEAKAGE GUARD: prior season
),

-- Per-slot batter performance vs. the opposing starter's pitch archetype
slot_archetype_stats as (
    select
        ls.game_pk,
        ls.home_away,
        ls.slot,
        ls.batter_id,
        bva.adj_woba    as batter_woba_vs_archetype,
        bva.adj_xwoba   as batter_xwoba_vs_archetype,
        bva.adj_k_pct   as batter_k_pct_vs_archetype,
        bva.adj_iso     as batter_iso_vs_archetype,
        coalesce(bva.pa_count, 0) as batter_archetype_pa
    from lineup_slots ls
    -- opposing starter: home lineup faces away starter, away lineup faces home starter
    left join starter_archetype sa
        on  sa.game_pk   = ls.game_pk
        and sa.home_away = case
                              when ls.home_away = 'home' then 'away'
                              else 'home'
                          end
    left join {{ ref('mart_batter_vs_pitch_archetype') }} bva
        on  bva.batter_id      = ls.batter_id
        and bva.pitch_archetype = sa.pitch_archetype
        and bva.game_year       = year(ls.official_date) - 1   -- LEAKAGE GUARD
    where ls.batter_id is not null
),

-- Lineup-level aggregation of archetype matchup stats
archetype_agg as (
    select
        game_pk,
        home_away,
        round(avg(batter_woba_vs_archetype),  3) as lineup_woba_vs_starter_archetype,
        round(avg(batter_xwoba_vs_archetype), 3) as lineup_xwoba_vs_starter_archetype,
        round(avg(batter_k_pct_vs_archetype), 3) as lineup_k_pct_vs_starter_archetype,
        round(avg(batter_iso_vs_archetype),   3) as lineup_iso_vs_starter_archetype,
        round(avg(batter_archetype_pa),       0) as lineup_archetype_pa_coverage
    from slot_archetype_stats
    group by game_pk, home_away
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
        sp.avg_hard_hit_pct_vs_rhp,

        -- Injury-adjusted lineup quality (Card 7.I)
        -- injury_adj columns divide by 9 so IL absences reduce the aggregate
        coalesce(ia.injured_player_count, 0)    as injured_player_count,
        ia.injury_adj_avg_woba_30d,
        ia.injury_adj_avg_xwoba_30d,

        -- Hitter vs. starter pitch-archetype matchup features (Card 7.J)
        -- Prior-season archetype lookup; shrinkage-adjusted for small samples
        aa.lineup_woba_vs_starter_archetype,
        aa.lineup_xwoba_vs_starter_archetype,
        aa.lineup_k_pct_vs_starter_archetype,
        aa.lineup_iso_vs_starter_archetype,
        aa.lineup_archetype_pa_coverage,
        opp_sa.pitch_archetype                  as starter_pitch_archetype

    from lineups l
    left join lineup_agg la
        on  la.game_pk   = l.game_pk
        and la.home_away = l.home_away
    left join slot_platoon sp
        on  sp.game_pk   = l.game_pk
        and sp.home_away = l.home_away
    left join injury_agg ia
        on  ia.game_pk   = l.game_pk
        and ia.home_away = l.home_away
    left join archetype_agg aa
        on  aa.game_pk   = l.game_pk
        and aa.home_away = l.home_away
    -- opposing starter archetype: home lineup faces away starter
    left join starter_archetype opp_sa
        on  opp_sa.game_pk   = l.game_pk
        and opp_sa.home_away = case
                                   when l.home_away = 'home' then 'away'
                                   else 'home'
                               end
)

select * from final

-- =============================================================================
-- feature_pregame_expected_lineup.sql   (Story 33.3)
-- Grain: one row per (game_pk, home_away).
-- Purpose: the PRE-LINEUP-available replacement for the dropped Class-B
--          lineup-AVERAGED batter aggregates (home_avg_woba_30d / *_vs_lhp / …).
--          Instead of averaging over the 9 CONFIRMED starters (unknown pre-lineup),
--          we take the PROBABILITY-WEIGHTED expectation over the candidate roster:
--              expected_stat = Σ P(start)·stat / Σ P(start)
--          where P(start) comes from mart_player_start_probability (Story 33.1) and
--          the per-batter stats are resolved strictly-prior (leakage-safe as-of).
--
-- WHY THIS IS LEAKAGE-SAFE / PRE-LINEUP:
--   * P(start) is walk-forward (33.1: year Y scored by a model fit on <Y) and needs
--     no confirmed lineup — it is computed from each team's recent start history.
--   * Batter stats use the SAME as-of carry-forward as feature_pregame_lineup_features:
--     the latest rolling-stats row STRICTLY BEFORE official_date (demand rows sort
--     before same-date data via is_demand desc), so no same-day leak.
--   * Prior-season platoon splits use game_year - 1 only.
--   * INJURIES ARE SUBSUMED: P(start) already downweights injured players (the model
--     has is_injured), so no separate injury-adjustment is needed here.
--
-- v1 SCOPE: rolling-30d + std + prior-season platoon (vs-LHP/RHP) expected aggregates —
-- the bulk of the dropped offense signal, and recoverable WITHOUT the opposing starter.
-- The matchup families (vs-pitch-archetype / vs-cluster / bat-tracking) are a documented
-- 33.3 follow-on (they need the opposing probable starter joined in).
-- =============================================================================

{{ config(materialized='table') }}

with candidates as (

    select
        game_pk,
        side                   as home_away,
        player_id              as batter_id,
        official_date::date    as official_date,
        start_probability      as p
    from {{ source('betting', 'mart_player_start_probability') }}
    where start_probability > 0      -- ignore ~0-weight candidates (no contribution)

),

-- as-of carry-forward: latest strictly-prior rolling-stats date per (batter, official_date).
-- Demand rows (is_demand=1) sort BEFORE same-date data rows → enforces strict < (no leak).
asof_demand as (
    select distinct batter_id, official_date from candidates
),

asof_combined as (
    select batter_id, game_date::date as evt_date, 0 as is_demand
    from {{ ref('mart_batter_rolling_stats') }}
    union all
    select batter_id, official_date as evt_date, 1 as is_demand
    from asof_demand
),

asof_date as (
    select batter_id, official_date, asof_date
    from (
        select
            batter_id,
            evt_date as official_date,
            is_demand,
            last_value(case when is_demand = 0 then evt_date end ignore nulls) over (
                partition by batter_id
                order by evt_date asc, is_demand desc
                rows between unbounded preceding and current row
            ) as asof_date
        from asof_combined
    )
    where is_demand = 1
),

-- candidate × resolved pre-game rolling stats
cand_stats as (
    select
        c.game_pk,
        c.home_away,
        c.batter_id,
        c.p,
        rs.batter_hand,
        rs.woba_30d, rs.xwoba_30d, rs.k_pct_30d, rs.bb_pct_30d,
        rs.hard_hit_pct_30d, rs.barrel_pct_30d, rs.whiff_rate_30d, rs.chase_rate_30d,
        rs.woba_std, rs.xwoba_std, rs.k_pct_std, rs.bb_pct_std,
        rs.hard_hit_pct_std, rs.barrel_pct_std
    from candidates c
    left join asof_date ad
        on  ad.batter_id     = c.batter_id
        and ad.official_date = c.official_date
    left join {{ ref('mart_batter_rolling_stats') }} rs
        on  rs.batter_id      = c.batter_id
        and rs.game_date::date = ad.asof_date
    qualify row_number() over (
        partition by c.game_pk, c.home_away, c.batter_id order by 1
    ) = 1
),

-- P-weighted expected rolling aggregates.
-- expected_stat = Σ(p·stat) / Σ(p over candidates with a non-null stat) — missing-stat
-- candidates drop out of BOTH numerator and denominator (no dilution toward 0).
expected_rolling as (
    select
        game_pk,
        home_away,
        round(sum(p), 3)                                            as expected_lineup_mass,
        count(*)                                                    as n_candidates,
        round(sum(p * case when batter_hand = 'L' then 1 else 0 end), 2) as exp_lhb_count,
        round(sum(p * case when batter_hand = 'R' then 1 else 0 end), 2) as exp_rhb_count,
        {% set _roll = ['woba_30d','xwoba_30d','k_pct_30d','bb_pct_30d','hard_hit_pct_30d',
                        'barrel_pct_30d','whiff_rate_30d','chase_rate_30d',
                        'woba_std','xwoba_std','k_pct_std','bb_pct_std','hard_hit_pct_std','barrel_pct_std'] %}
        {% for s in _roll %}
        round(sum(p * {{ s }}) / nullif(sum(case when {{ s }} is not null then p end), 0), 3) as exp_{{ s }}{{ ',' if not loop.last }}
        {% endfor %}
    from cand_stats
    group by game_pk, home_away
),

-- prior-season platoon splits (game_year - 1), P-weighted by candidate.
cand_platoon as (
    select
        c.game_pk,
        c.home_away,
        c.p,
        hs.pitcher_hand,
        hs.woba, hs.xwoba, hs.k_pct, hs.bb_pct, hs.hard_hit_pct
    from candidates c
    left join {{ ref('mart_batter_vs_handedness_splits') }} hs
        on  hs.batter_id = c.batter_id
        and hs.game_year = year(c.official_date) - 1
),

expected_platoon as (
    select
        game_pk,
        home_away,
        {% set _plat = ['woba','xwoba','k_pct','bb_pct','hard_hit_pct'] %}
        {% for s in _plat %}
        round(sum(case when pitcher_hand='L' then p * {{ s }} end)
              / nullif(sum(case when pitcher_hand='L' and {{ s }} is not null then p end), 0), 3) as exp_{{ s }}_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * {{ s }} end)
              / nullif(sum(case when pitcher_hand='R' and {{ s }} is not null then p end), 0), 3) as exp_{{ s }}_vs_rhp{{ ',' if not loop.last }}
        {% endfor %}
    from cand_platoon
    group by game_pk, home_away
)

select
    r.*,
    p.exp_woba_vs_lhp,  p.exp_xwoba_vs_lhp,  p.exp_k_pct_vs_lhp,
    p.exp_bb_pct_vs_lhp, p.exp_hard_hit_pct_vs_lhp,
    p.exp_woba_vs_rhp,  p.exp_xwoba_vs_rhp,  p.exp_k_pct_vs_rhp,
    p.exp_bb_pct_vs_rhp, p.exp_hard_hit_pct_vs_rhp
from expected_rolling r
left join expected_platoon p
    on  p.game_pk   = r.game_pk
    and p.home_away = r.home_away

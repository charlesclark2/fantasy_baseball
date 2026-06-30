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
--   * P(start) is walk-forward (33.1) and needs no confirmed lineup.
--   * Batter stats use the SAME as-of carry-forward as feature_pregame_lineup_features.
--   * Prior-season platoon splits use game_year - 1 only.
--   * INJURIES ARE SUBSUMED: P(start) already downweights injured players.
--
-- E11.1-W8a (upstream feature-layer migration): DuckDB branch reads the migrated
-- mart_batter_rolling_stats / mart_batter_vs_handedness_splits (registered as DuckDB
-- views by run_w1_lakehouse._build_w8a) + mart_player_start_probability (registered
-- from its S3 export-mirror, scripts/export_w8a_precursors_to_s3.py). The Jinja
-- for-loops in the Snowflake source are EXPANDED inline here — run_w1_lakehouse's
-- extract_duckdb_sql is a regex pseudo-renderer (no loop expansion). The Snowflake
-- (else) branch is a thin view over the lakehouse_ext external table; the
-- column set is identical (parity-gated by scripts/parity_check_w8a.py).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8a_lakehouse']) }}

with candidates as (

    select
        game_pk,
        side                   as home_away,
        player_id              as batter_id,
        official_date::date    as official_date,
        start_probability      as p
    from mart_player_start_probability
    where start_probability > 0      -- ignore ~0-weight candidates (no contribution)

),

-- as-of carry-forward: latest strictly-prior rolling-stats date per (batter, official_date).
asof_demand as (
    select distinct batter_id, official_date from candidates
),

asof_combined as (
    select batter_id, game_date::date as evt_date, 0 as is_demand
    from mart_batter_rolling_stats
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
    left join mart_batter_rolling_stats rs
        on  rs.batter_id      = c.batter_id
        and rs.game_date::date = ad.asof_date
    qualify row_number() over (
        partition by c.game_pk, c.home_away, c.batter_id order by 1
    ) = 1
),

-- P-weighted expected rolling aggregates (Jinja for-loops EXPANDED for the DuckDB branch).
expected_rolling as (
    select
        game_pk,
        home_away,
        round(sum(p), 3)                                            as expected_lineup_mass,
        count(*)                                                    as n_candidates,
        round(sum(p * case when batter_hand = 'L' then 1 else 0 end), 2) as exp_lhb_count,
        round(sum(p * case when batter_hand = 'R' then 1 else 0 end), 2) as exp_rhb_count,
        round(sum(p * woba_30d)         / nullif(sum(case when woba_30d         is not null then p end), 0), 3) as exp_woba_30d,
        round(sum(p * xwoba_30d)        / nullif(sum(case when xwoba_30d        is not null then p end), 0), 3) as exp_xwoba_30d,
        round(sum(p * k_pct_30d)        / nullif(sum(case when k_pct_30d        is not null then p end), 0), 3) as exp_k_pct_30d,
        round(sum(p * bb_pct_30d)       / nullif(sum(case when bb_pct_30d       is not null then p end), 0), 3) as exp_bb_pct_30d,
        round(sum(p * hard_hit_pct_30d) / nullif(sum(case when hard_hit_pct_30d is not null then p end), 0), 3) as exp_hard_hit_pct_30d,
        round(sum(p * barrel_pct_30d)   / nullif(sum(case when barrel_pct_30d   is not null then p end), 0), 3) as exp_barrel_pct_30d,
        round(sum(p * whiff_rate_30d)   / nullif(sum(case when whiff_rate_30d   is not null then p end), 0), 3) as exp_whiff_rate_30d,
        round(sum(p * chase_rate_30d)   / nullif(sum(case when chase_rate_30d   is not null then p end), 0), 3) as exp_chase_rate_30d,
        round(sum(p * woba_std)         / nullif(sum(case when woba_std         is not null then p end), 0), 3) as exp_woba_std,
        round(sum(p * xwoba_std)        / nullif(sum(case when xwoba_std        is not null then p end), 0), 3) as exp_xwoba_std,
        round(sum(p * k_pct_std)        / nullif(sum(case when k_pct_std        is not null then p end), 0), 3) as exp_k_pct_std,
        round(sum(p * bb_pct_std)       / nullif(sum(case when bb_pct_std       is not null then p end), 0), 3) as exp_bb_pct_std,
        round(sum(p * hard_hit_pct_std) / nullif(sum(case when hard_hit_pct_std is not null then p end), 0), 3) as exp_hard_hit_pct_std,
        round(sum(p * barrel_pct_std)   / nullif(sum(case when barrel_pct_std   is not null then p end), 0), 3) as exp_barrel_pct_std
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
    left join mart_batter_vs_handedness_splits hs
        on  hs.batter_id = c.batter_id
        and hs.game_year = year(c.official_date) - 1
),

expected_platoon as (
    select
        game_pk,
        home_away,
        round(sum(case when pitcher_hand='L' then p * woba end)         / nullif(sum(case when pitcher_hand='L' and woba         is not null then p end), 0), 3) as exp_woba_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * woba end)         / nullif(sum(case when pitcher_hand='R' and woba         is not null then p end), 0), 3) as exp_woba_vs_rhp,
        round(sum(case when pitcher_hand='L' then p * xwoba end)        / nullif(sum(case when pitcher_hand='L' and xwoba        is not null then p end), 0), 3) as exp_xwoba_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * xwoba end)        / nullif(sum(case when pitcher_hand='R' and xwoba        is not null then p end), 0), 3) as exp_xwoba_vs_rhp,
        round(sum(case when pitcher_hand='L' then p * k_pct end)        / nullif(sum(case when pitcher_hand='L' and k_pct        is not null then p end), 0), 3) as exp_k_pct_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * k_pct end)        / nullif(sum(case when pitcher_hand='R' and k_pct        is not null then p end), 0), 3) as exp_k_pct_vs_rhp,
        round(sum(case when pitcher_hand='L' then p * bb_pct end)       / nullif(sum(case when pitcher_hand='L' and bb_pct       is not null then p end), 0), 3) as exp_bb_pct_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * bb_pct end)       / nullif(sum(case when pitcher_hand='R' and bb_pct       is not null then p end), 0), 3) as exp_bb_pct_vs_rhp,
        round(sum(case when pitcher_hand='L' then p * hard_hit_pct end) / nullif(sum(case when pitcher_hand='L' and hard_hit_pct is not null then p end), 0), 3) as exp_hard_hit_pct_vs_lhp,
        round(sum(case when pitcher_hand='R' then p * hard_hit_pct end) / nullif(sum(case when pitcher_hand='R' and hard_hit_pct is not null then p end), 0), 3) as exp_hard_hit_pct_vs_rhp
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

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_expected_lineup

{% endif %}

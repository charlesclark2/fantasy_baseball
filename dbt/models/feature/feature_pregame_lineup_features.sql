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
--
-- E11.1-W8b (serving-aggregator wave): dual-branch. DuckDB branch (real compute → S3,
-- run_w1_lakehouse._build_w8b) reads the migrated marts/staging + the S3-mirrored
-- feature_pregame_lineup_state (INC-17-P2 dual-source CTE: SCD-2 lineup_state UNION historical
-- stg_statsapi_lineups_wide) + feature_pregame_injury_status + feature_pregame_starter_features
-- (W8b) + eb_batter_posteriors_raw (W8a) + lakehouse_clusters. Dialect: Snowflake float casts →
-- DuckDB ::double, Snowflake ::timestamp_ntz → DuckDB ::timestamp, current_timestamp() → current_timestamp. The
-- Snowflake (else) branch reads the lakehouse_ext external table (parity_check_w8b.py). ⚠️ The
-- lineup dual-source MUST stay intact (else 2026 slot_*_player_id NULL → constant imputation).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8b_lakehouse']) }}

with

-- Lineup composition: SCD-2 state (2026 onward) unioned with historical staging
-- table for pre-SCD-2 games. The SCD-2 state is preferred when available — it
-- tracks intra-day lineup changes with point-in-time accuracy. Historical games
-- use stg_statsapi_lineups_wide (confirmed post-game lineups, 2015–2025).
-- The NOT IN guard prevents duplicates in games covered by both sources.
lineups as (
    -- SCD-2 lineup state: confirmed current lineup for each game × side (2026+)
    select
        game_pk,
        official_date,
        home_away,
        has_full_lineup,
        slot_1_player_id,
        slot_2_player_id,
        slot_3_player_id,
        slot_4_player_id,
        slot_5_player_id,
        slot_6_player_id,
        slot_7_player_id,
        slot_8_player_id,
        slot_9_player_id,
        slot_1_position,
        slot_2_position,
        slot_3_position,
        slot_4_position,
        slot_5_position,
        slot_6_position,
        slot_7_position,
        slot_8_position,
        slot_9_position
    from {{ source('betting_features', 'feature_pregame_lineup_state') }}
    where is_current = true
    -- INC-14 fix: a postponed/rescheduled game can leave is_current=true on BOTH the
    -- original and the rescheduled official_date (the SCD-2 writer fails to close the
    -- superseded row — valid_to stays NULL on both). Those two rows carry different
    -- official_dates that cartesian-fan-out through the date-keyed downstream joins
    -- (observed: game 823613 → 16 away / 4 home rows, breaking the (game_pk, side)
    -- grain and the offense-signal MERGE). Keep only the latest-asserted lineup per
    -- game-side. No-op for normal games (single is_current row). Upstream root cause:
    -- the SCD-2 writer should set valid_to / is_current=false on the old official_date
    -- when a game is rescheduled (tracked separately as the SCD-2-writer fix).
    qualify row_number() over (partition by game_pk, home_away order by valid_from desc) = 1

    union all

    -- Historical lineups (2015–2025): from stg_statsapi_lineups_wide for games
    -- not yet in the SCD-2 state. has_full_lineup derived from null slot checks.
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
        slot_9_player_id,
        slot_1_position,
        slot_2_position,
        slot_3_position,
        slot_4_position,
        slot_5_position,
        slot_6_position,
        slot_7_position,
        slot_8_position,
        slot_9_position
    from {{ ref('stg_statsapi_lineups_wide') }}
    where game_pk not in (
        select distinct game_pk
        from {{ source('betting_features', 'feature_pregame_lineup_state') }}
        where is_current = true
    )
),

-- Identify the catcher for each lineup.
-- Primary: scan all 9 slots for position_abbreviation = 'C'.
-- Fallback: batting slot 2 (convention — catchers bat second in most orders).
catcher_id as (
    select
        game_pk,
        official_date,
        home_away,
        coalesce(
            case when slot_1_position = 'C' then slot_1_player_id end,
            case when slot_2_position = 'C' then slot_2_player_id end,
            case when slot_3_position = 'C' then slot_3_player_id end,
            case when slot_4_position = 'C' then slot_4_player_id end,
            case when slot_5_position = 'C' then slot_5_player_id end,
            case when slot_6_position = 'C' then slot_6_player_id end,
            case when slot_7_position = 'C' then slot_7_player_id end,
            case when slot_8_position = 'C' then slot_8_player_id end,
            case when slot_9_position = 'C' then slot_9_player_id end,
            slot_2_player_id  -- fallback: batting slot 2
        )                                   as catcher_player_id
    from lineups
),

-- Join catcher to mart_catcher_framing for the current game season.
-- COALESCE to 0 (league average) when catcher is unidentified or not in mart.
catcher_framing as (
    select
        ci.game_pk,
        ci.home_away,
        coalesce(cf.framing_runs_above_average,   0) as catcher_framing_runs,
        coalesce(cf.defensive_runs_above_average, 0) as catcher_defensive_runs
    from catcher_id ci
    left join {{ ref('mart_catcher_framing') }} cf
        on  cf.player_id = ci.catcher_player_id
        and cf.season    = year(ci.official_date)
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

-- A2.8 perf — most recent pre-game rolling stats for each lineup slot, resolved
-- via an as-of CARRY-FORWARD instead of the old "left join EVERY prior row per
-- slot + row_number()=1". That join fanned lineup_slots × all-prior-rows out to
-- ~166.8M rows whose windowed sort was 82% of the build. Here we carry the latest
-- strictly-prior game_date per (batter, official_date) in ONE ordered pass over
-- (rolling_stats ∪ demand), then equi-join back to fetch that row's stats in their
-- NATIVE types (no OBJECT round-trip → no precision drift). Byte-for-byte identical:
--   * leakage guard stays strict — demand rows sort BEFORE same-date data rows
--     (is_demand desc), so a data row ON official_date is excluded.
--   * the 6% of (batter, date) pairs with duplicate rolling-stats rows were verified
--     to carry IDENTICAL stat values, so the final dedup pick is value-invariant.
--   * batters with no prior row get asof_date = NULL → NULL stats (matches the old
--     LEFT join), and doubleheaders (same batter+date, 2 game_pks) both resolve to
--     the same as-of row.
slot_asof_demand as (
    select distinct batter_id, official_date
    from lineup_slots
    where batter_id is not null
),

slot_asof_combined as (
    -- data rows (is_demand = 0)
    select batter_id, game_date::date as evt_date, 0 as is_demand
    from {{ ref('mart_batter_rolling_stats') }}
    union all
    -- demand rows (is_demand = 1 → sort before same-date data, enforcing strict <)
    select batter_id, official_date as evt_date, 1 as is_demand
    from slot_asof_demand
),

slot_asof_date as (
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
        from slot_asof_combined
    )
    where is_demand = 1
),

-- Re-attach the resolved stats to each slot (equi-joins only; dedup the verified
-- identical-valued duplicate rolling-stats rows).
slot_pre_game as (
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
        rs.barrel_pct_std
    from lineup_slots ls
    left join slot_asof_date ad
        on  ad.batter_id     = ls.batter_id
        and ad.official_date = ls.official_date
    left join {{ ref('mart_batter_rolling_stats') }} rs
        on  rs.batter_id       = ls.batter_id
        and rs.game_date::date  = ad.asof_date
    where ls.batter_id is not null
    qualify row_number() over (
        partition by ls.game_pk, ls.home_away, ls.slot
        order by 1
    ) = 1
),

-- Point-in-time IL status per lineup slot as of official_date
-- LEAKAGE GUARD: valid_from <= official_date ensures only pre-game transactions used
slot_injury as (
    select
        sp.game_pk,
        sp.official_date,
        sp.home_away,
        sp.slot,
        sp.batter_id,
        coalesce(inj.is_injured, false)  as is_injured
    from slot_pre_game sp
    left join {{ ref('feature_pregame_injury_status') }} inj
        on  inj.player_id  = sp.batter_id
        -- LEAKAGE GUARD. INC-23: valid_from/valid_to are TIMESTAMP in dbt/Snowflake but the
        -- W8a/W8b cure stores them as ISO-VARCHAR in the S3 parquet, so the DuckDB --w8b build
        -- cannot compare them to the DATE official_date (binder error → silent --w8b abort →
        -- stale S3 feature tables). Cast ::timestamp at the use-site (DuckDB-only branch);
        -- value-preserving — official_date promotes to midnight, matching the SF semantics.
        and inj.valid_from::timestamp <= sp.official_date
        and (
                inj.valid_to::timestamp  > sp.official_date
                or inj.valid_to is null
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

-- Prior-season batter archetype distribution across 9 lineup slots (Story 7.4)
-- Leakage guard: season = year(official_date) - 1 (prior season only)
-- n_no_label: slots where batter has no prior-season archetype (rookie / debut)
batter_archetype_dist as (
    select
        ls.game_pk,
        ls.home_away,
        count(case when bc.cluster_label = 'power_pull'       then 1 end) as n_power_pull,
        count(case when bc.cluster_label = 'patient_obp'      then 1 end) as n_patient_obp,
        count(case when bc.cluster_label = 'high_whiff'       then 1 end) as n_high_whiff,
        count(case when bc.cluster_label = 'groundball_speed' then 1 end) as n_groundball_speed,
        count(case when bc.cluster_label = 'contact_spray'    then 1 end) as n_contact_spray,
        count(case when bc.cluster_label is null               then 1 end) as n_no_label
    from lineup_slots ls
    left join {{ source('lakehouse_clusters', 'batter_clusters') }} bc
        on  bc.batter_id = ls.batter_id
        and bc.season    = year(ls.official_date) - 1
    where ls.batter_id is not null
    group by ls.game_pk, ls.home_away
),

-- Starter pitch archetype and fastball velocity for each game × side
-- pitch_archetype: prior-season LEAKAGE GUARD (game_year - 1)
-- avg_fastball_velo_7d: rolling pre-game window already leakage-free in source
starter_archetype as (
    select
        sf.game_pk,
        sf.side                                     as home_away,
        sf.pitcher_id,
        sf.avg_fastball_velo_7d,
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

-- Per-slot bat tracking profile (most recent pre-game row)
-- LEAKAGE GUARD: game_date < official_date ensures only prior-day data
slot_bat_tracking_ranked as (
    select
        ls.game_pk,
        ls.official_date,
        ls.home_away,
        ls.slot,
        ls.batter_id,
        bt.bat_speed_30d,
        bt.swing_length_30d,
        bt.attack_angle_30d,
        row_number() over (
            partition by ls.game_pk, ls.home_away, ls.slot
            order by bt.game_date::date desc
        )                                           as rn
    from lineup_slots ls
    left join {{ ref('mart_batter_bat_tracking_profile') }} bt
        on  bt.batter_id       = ls.batter_id
        and bt.game_date::date < ls.official_date   -- LEAKAGE GUARD
    where ls.batter_id is not null
),

slot_bat_tracking as (
    select * from slot_bat_tracking_ranked where rn = 1
),

-- Lineup-level bat tracking aggregates across all 9 slots (Card 8.E)
-- NULL when no batter in the lineup has 2023+ bat tracking data
bat_tracking_agg as (
    select
        game_pk,
        home_away,
        round(avg(bat_speed_30d),    2)             as lineup_avg_bat_speed,
        round(stddev(bat_speed_30d), 2)             as lineup_bat_speed_std,
        round(avg(swing_length_30d), 2)             as lineup_avg_swing_length,
        round(avg(attack_angle_30d), 2)             as lineup_avg_attack_angle
    from slot_bat_tracking
    group by game_pk, home_away
),

-- -------------------------------------------------------------------------
-- ZiPS pre-season projections (Story 2.6)
-- -------------------------------------------------------------------------

-- Per-slot ZiPS: current-season with prior-season fallback.
-- Joins on MLBAM ID; validated 99.7% coverage for 2024 active batters.
-- wOBA proxy = 0.7 * OBP + 0.3 * SLG (no wOBA column in ZiPS source).
slot_zips as (
    select
        ls.game_pk,
        ls.official_date,
        ls.home_away,
        ls.slot,
        ls.batter_id,
        coalesce(zc.proj_wrc_plus,  zp.proj_wrc_plus)              as proj_wrc_plus,
        coalesce(
            0.7 * zc.proj_obp + 0.3 * zc.proj_slg,
            0.7 * zp.proj_obp + 0.3 * zp.proj_slg
        )                                                           as zips_woba_proxy,
        coalesce(zc.proj_k_pct,     zp.proj_k_pct)                 as proj_k_pct,
        coalesce(zc.proj_iso,       zp.proj_iso)                    as proj_iso,
        coalesce(zc.proj_pa,        zp.proj_pa)                     as proj_pa,
        (zc.fg_batter_id is null and zp.fg_batter_id is null)       as no_zips_data
    from lineup_slots ls
    left join {{ ref('stg_fangraphs__zips_hitting') }} zc
        on  zc.mlbam_batter_id = ls.batter_id::varchar
        and zc.season          = year(ls.official_date)
    left join {{ ref('stg_fangraphs__zips_hitting') }} zp
        on  zp.mlbam_batter_id = ls.batter_id::varchar
        and zp.season          = year(ls.official_date) - 1
    where ls.batter_id is not null
),

-- Lineup-level ZiPS aggregates and rookie-proxy coverage count
zips_agg as (
    select
        game_pk,
        home_away,
        round(avg(proj_wrc_plus),   1)                              as avg_zips_wrc_plus,
        round(avg(zips_woba_proxy), 3)                              as avg_zips_woba_proxy,
        round(avg(proj_k_pct),      3)                              as avg_zips_k_pct,
        round(avg(proj_iso),        3)                              as avg_zips_iso,
        round(
            sum(case when not no_zips_data then 1 else 0 end)::double / 9.0
        , 3)                                                        as zips_coverage_pct,
        -- Proxy for rookies / unknowns: slots with no ZiPS in current or prior season
        sum(case when no_zips_data then 1 else 0 end)               as lineup_rookie_count
    from slot_zips
    group by game_pk, home_away
),

-- PA-weighted average ZiPS wOBA proxy for batting slots 7–9 (lineup depth)
lineup_depth as (
    select
        game_pk,
        home_away,
        round(
            sum(zips_woba_proxy * coalesce(proj_pa, 1.0))
            / nullif(sum(case when zips_woba_proxy is not null
                              then coalesce(proj_pa, 1.0) end), 0)
        , 3)                                                        as lineup_depth_score
    from slot_zips
    where slot >= 7
    group by game_pk, home_away
),

-- Shannon entropy of slot-wise ZiPS wOBA proxy distribution.
-- High entropy → balanced; low entropy → production concentrated in a few bats.
lineup_entropy_base as (
    select
        game_pk,
        home_away,
        sum(zips_woba_proxy) as total_woba_proxy
    from slot_zips
    where zips_woba_proxy is not null and zips_woba_proxy > 0
    group by game_pk, home_away
),

lineup_entropy as (
    select
        sz.game_pk,
        sz.home_away,
        round(
            -sum(
                (sz.zips_woba_proxy / eb.total_woba_proxy)
                * ln(sz.zips_woba_proxy / eb.total_woba_proxy)
            )
        , 4)                                                        as lineup_entropy
    from slot_zips sz
    join lineup_entropy_base eb
        on  eb.game_pk   = sz.game_pk
        and eb.home_away = sz.home_away
    where sz.zips_woba_proxy is not null
      and sz.zips_woba_proxy > 0
      and eb.total_woba_proxy > 0
    group by sz.game_pk, sz.home_away
),

-- -------------------------------------------------------------------------
-- EB lineup posteriors (Epic 4A.3)
-- -------------------------------------------------------------------------

-- Per-slot EB posterior: join posteriors written by compute_lineup_posteriors.py.
-- No LEAKAGE GUARD needed — posteriors are pre-computed per game_pk/date by the
-- script and stored keyed on game_pk, so they cannot contain future data.
-- NULLs are left as-is (no coalesce to rolling stats) to keep ablation clean.
slot_eb as (
    select
        ls.game_pk,
        ls.home_away,
        ls.slot,
        ls.batter_id,
        eb.eb_woba,
        eb.eb_woba_sequential,
        eb.eb_k_pct,
        eb.eb_bb_pct,
        eb.eb_iso,
        eb.eb_woba_uncertainty,
        eb.posterior_source
    from lineup_slots ls
    left join {{ ref('eb_batter_posteriors_raw') }} eb  -- Story A2.11: dbt model (was source table)
        on  eb.game_pk      = ls.game_pk::varchar
        and eb.batting_slot = ls.slot
        and eb.batter_id    = ls.batter_id::varchar
    where ls.batter_id is not null
),

-- Lineup-level EB posterior aggregates
eb_agg as (
    select
        game_pk,
        home_away,
        round(avg(eb_woba),              3) as avg_eb_woba,
        -- Epic 16.2 — lineup-mean of the as-of sequential xwOBA posterior (parallel
        -- to avg_eb_woba; leakage-safe — eb_woba_sequential is the strict game_date<T
        -- belief written by compute_lineup_posteriors.py).
        round(avg(eb_woba_sequential),   3) as avg_eb_woba_sequential,
        round(avg(eb_k_pct),             3) as avg_eb_k_pct,
        round(avg(eb_bb_pct),            3) as avg_eb_bb_pct,
        round(avg(eb_iso),               3) as avg_eb_iso,
        round(avg(eb_woba_uncertainty),  4) as avg_eb_woba_uncertainty,
        round(
            count(case when eb_woba is not null then 1 end)::double / 9.0
        , 3)                               as eb_coverage_pct,
        -- Epic 16B.1 — least-informed-wins aggregation across 9 slots.
        -- Informativeness order: sequential > season_eb > prior_only.
        -- A single prior_only slot makes the whole side prior_only, etc.
        -- NULL (no EB data, pre-2021) propagates as NULL → trainer maps to __NA__.
        case
            when count(case when posterior_source = 'prior_only' then 1 end) > 0 then 'prior_only'
            when count(case when posterior_source = 'season_eb'  then 1 end) > 0 then 'season_eb'
            when count(case when posterior_source = 'sequential' then 1 end) > 0 then 'sequential'
            else null
        end                                as posterior_source
    from slot_eb
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
        opp_sa.pitch_archetype                  as starter_pitch_archetype,

        -- Catcher metrics (Card 8.K)
        -- 0 = league average when catcher is not identified or not in mart
        cf.catcher_framing_runs,
        cf.catcher_defensive_runs,

        -- Bat tracking matchup features (Card 8.E / Story 2.9)
        -- NULL for all pre-2023-07-14 games; ~50% null in 2021+ training set
        bta.lineup_avg_bat_speed,
        bta.lineup_bat_speed_std,
        bta.lineup_avg_swing_length,
        bta.lineup_avg_attack_angle,
        round(
            bta.lineup_avg_bat_speed / nullif(opp_sa.avg_fastball_velo_7d, 0)
        , 4)                                        as lineup_bat_speed_vs_starter_velo,

        -- ZiPS pre-season projections (Story 2.6)
        -- Current-season with prior-season fallback; NULL when no ZiPS data
        za.avg_zips_wrc_plus,
        za.avg_zips_woba_proxy,
        za.avg_zips_k_pct,
        za.avg_zips_iso,
        za.zips_coverage_pct,

        -- Lineup depth: PA-weighted ZiPS wOBA proxy for slots 7–9 (Story 2.6)
        ld.lineup_depth_score,

        -- Lineup entropy: Shannon entropy of slot-wise ZiPS wOBA proxy (Story 2.6)
        le.lineup_entropy,

        -- Rookie / unknown proxy: slots with no ZiPS in current or prior season (Story 2.6)
        coalesce(za.lineup_rookie_count, 9)                         as lineup_rookie_count,
        round(coalesce(za.lineup_rookie_count, 9) / 9.0, 3)        as lineup_rookie_pa_share,

        -- EB lineup posteriors (Epic 4A.3)
        -- Shrinkage-regularised estimates blending prior, ZiPS, and current-season data.
        -- NULL when posteriors not yet computed for this game_pk (run compute_lineup_posteriors.py).
        -- Do NOT coalesce to rolling stats — ablation requires true NULLs for coverage tracking.
        ea.avg_eb_woba,
        ea.avg_eb_woba_sequential,
        ea.avg_eb_k_pct,
        ea.avg_eb_bb_pct,
        ea.avg_eb_iso,
        ea.avg_eb_woba_uncertainty,
        coalesce(ea.eb_coverage_pct, 0.0)                           as eb_coverage_pct,
        -- Epic 16B.1 — least-informed-wins side-level posterior quality label.
        -- NULL for pre-2021 games (no sequential backfill); trainer maps to __NA__.
        ea.posterior_source,

        -- Prior-season batter archetype distribution (Story 7.4)
        -- Count of lineup slots assigned to each batter archetype (prior season).
        -- n_no_label: slots with no prior-season archetype (rookies, debuts).
        -- Sums to 9 for full lineups; may be < 9 when batter_id is null for a slot.
        coalesce(bad.n_power_pull,       0)                         as n_power_pull,
        coalesce(bad.n_patient_obp,      0)                         as n_patient_obp,
        coalesce(bad.n_high_whiff,       0)                         as n_high_whiff,
        coalesce(bad.n_groundball_speed, 0)                         as n_groundball_speed,
        coalesce(bad.n_contact_spray,    0)                         as n_contact_spray,
        coalesce(bad.n_no_label,         9)                         as n_no_label,

        -- SCD-2 sentinel columns (Story 2.4 convention — born SCD-2-ready)
        current_timestamp::timestamp                          as valid_from,
        null::timestamp                                         as valid_to,
        true                                                        as is_current,
        current_timestamp::timestamp                          as computed_at,
        md5(concat_ws('|',
            coalesce(la.avg_woba_30d::varchar,              ''),
            coalesce(la.avg_xwoba_30d::varchar,             ''),
            coalesce(ia.injury_adj_avg_xwoba_30d::varchar,  ''),
            coalesce(za.avg_zips_wrc_plus::varchar,         ''),
            coalesce(za.avg_zips_woba_proxy::varchar,       ''),
            coalesce(ld.lineup_depth_score::varchar,        ''),
            coalesce(le.lineup_entropy::varchar,            '')
        ))                                                          as record_hash

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
    left join catcher_framing cf
        on  cf.game_pk   = l.game_pk
        and cf.home_away = l.home_away
    left join bat_tracking_agg bta
        on  bta.game_pk   = l.game_pk
        and bta.home_away = l.home_away
    left join zips_agg za
        on  za.game_pk   = l.game_pk
        and za.home_away = l.home_away
    left join lineup_depth ld
        on  ld.game_pk   = l.game_pk
        and ld.home_away = l.home_away
    left join lineup_entropy le
        on  le.game_pk   = l.game_pk
        and le.home_away = l.home_away
    left join eb_agg ea
        on  ea.game_pk   = l.game_pk
        and ea.home_away = l.home_away
    left join batter_archetype_dist bad
        on  bad.game_pk   = l.game_pk
        and bad.home_away = l.home_away
)

select * from final

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_lineup_features

{% endif %}

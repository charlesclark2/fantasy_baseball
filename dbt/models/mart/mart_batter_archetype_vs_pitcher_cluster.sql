-- E11.1-W5b dual-branch lakehouse model (was incremental → full-rebuild). DuckDB branch
-- reads the W1 mart_pitch_play_event (registered view) + the mart_player_archetype_posteriors
-- S3 parquet (written by compute_archetype_posteriors.py --s3, or seeded one-time from
-- Snowflake); Snowflake branch is a thin view over the lakehouse_ext external table.
-- ⚠️ TOLERANCE parity (NOT row-exact): the upstream posteriors are Bayesian (the rolling-stat
-- SQL's float precision differs Snowflake↔DuckDB → exp(-dist²) shifts cluster_probs ~1e-4),
-- so this mart's adj_woba/adj_xwoba carry that into the 3rd decimal. The Snowflake VARIANT
-- `lateral flatten(input => cluster_probs)` is rewritten to a DuckDB json_keys/json_extract
-- unnest over the VARCHAR-JSON parquet column. game_date is cast ::date (parquet stores it
-- VARCHAR) to match the retired DATE type + drive the 180-day RANGE-interval window.

{{ config(materialized='view', tags=['w5b_lakehouse']) }}

{% if target.name == 'duckdb' %}

-- Grain: batter_cluster_label × pitcher_cluster_label × game_date (anchor)
-- Population-level rolling soft-weighted wOBA for each batter-archetype × pitcher-archetype pair.
--
-- Soft-assignment weighting (Epic 7A.3):
--   Each PA contributes fractionally to all 25 cells with weight p_batter_b × p_pitcher_p,
--   drawn from mart_player_archetype_posteriors using the latest snapshot before game_date.
--   pa_weight (sum of joint weights in 180-day window) replaces the old hard pa_count.
--
-- Leakage guard: posteriors joined on as_of_date < game_date (strict less-than).
--
-- Rolling window: 180-day preceding (population stats benefit from larger sample).
--
-- Shrinkage toward league average (wOBA=0.320, xwOBA=0.315):
--   shrink_weight = pa_weight / (pa_weight + 100)
--
-- Gate: emit rows where pa_weight >= 50.
-- Availability: posteriors backfilled to 2016 (2026-06-02); effective from 2016 games.

with

posteriors as (
    select
        player_id,
        player_type,
        season,
        as_of_date::date as as_of_date,
        cluster_probs
    from read_parquet('{{ lakehouse_loc("mart_player_archetype_posteriors") }}data.parquet')
),

pa_events as (
    select
        ppe.game_date::date as game_date,
        ppe.game_year,
        ppe.batter_id,
        ppe.pitcher_id,
        ppe.woba_value,
        ppe.woba_denom,
        ppe.xwoba
    from mart_pitch_play_event ppe
    where ppe.plate_appearance_event is not null
      and ppe.game_year >= 2016
),

pa_batter_dates as (
    select distinct batter_id, game_date, game_year from pa_events
),

pa_pitcher_dates as (
    select distinct pitcher_id, game_date, game_year from pa_events
),

-- Latest batter posterior as_of_date strictly before each game_date in window
batter_latest as (
    select
        pd.batter_id,
        pd.game_date,
        pd.game_year,
        max(bap.as_of_date) as latest_as_of
    from pa_batter_dates pd
    join posteriors bap
        on  bap.player_id   = pd.batter_id
        and bap.player_type = 'batter'
        and bap.season      = pd.game_year
        and bap.as_of_date  < pd.game_date
    group by pd.batter_id, pd.game_date, pd.game_year
),

-- Flatten batter cluster probs: (batter_id, game_date) × 5 cluster labels.
-- DuckDB analogue of Snowflake `lateral flatten(input => cluster_probs)`: cluster_probs is
-- a VARCHAR-JSON object {label: prob}; unnest a list-comprehension of (key, value) structs
-- built from json_keys + json_extract.
batter_probs as (
    select
        bl.batter_id,
        bl.game_date,
        u.e.lab::varchar as batter_cluster_label,
        u.e.p::double    as p_batter
    from batter_latest bl
    join posteriors bap
        on  bap.player_id   = bl.batter_id
        and bap.player_type = 'batter'
        and bap.season      = bl.game_year
        and bap.as_of_date  = bl.latest_as_of,
    unnest([
        {'lab': k, 'p': json_extract(bap.cluster_probs, '$."' || k || '"')::double}
        for k in json_keys(bap.cluster_probs)
    ]) as u(e)
),

-- Latest pitcher posterior as_of_date strictly before each game_date
pitcher_latest as (
    select
        pd.pitcher_id,
        pd.game_date,
        pd.game_year,
        max(pap.as_of_date) as latest_as_of
    from pa_pitcher_dates pd
    join posteriors pap
        on  pap.player_id   = pd.pitcher_id
        and pap.player_type = 'pitcher'
        and pap.season      = pd.game_year
        and pap.as_of_date  < pd.game_date
    group by pd.pitcher_id, pd.game_date, pd.game_year
),

-- Flatten pitcher cluster probs: (pitcher_id, game_date) × 5 cluster labels (DuckDB JSON unnest)
pitcher_probs as (
    select
        pl.pitcher_id,
        pl.game_date,
        u.e.lab::varchar as pitcher_cluster_label,
        u.e.p::double    as p_pitcher
    from pitcher_latest pl
    join posteriors pap
        on  pap.player_id   = pl.pitcher_id
        and pap.player_type = 'pitcher'
        and pap.season      = pl.game_year
        and pap.as_of_date  = pl.latest_as_of,
    unnest([
        {'lab': k, 'p': json_extract(pap.cluster_probs, '$."' || k || '"')::double}
        for k in json_keys(pap.cluster_probs)
    ]) as u(e)
),

-- Join PA events × batter probs × pitcher probs
-- Each PA expands to 25 rows (5 batter clusters × 5 pitcher clusters)
pa_weighted as (
    select
        pe.game_date,
        bp.batter_cluster_label,
        pp.pitcher_cluster_label,
        pe.woba_value,
        pe.woba_denom,
        pe.xwoba,
        bp.p_batter * pp.p_pitcher as joint_weight
    from pa_events pe
    join batter_probs bp
        on  bp.batter_id = pe.batter_id
        and bp.game_date = pe.game_date
    join pitcher_probs pp
        on  pp.pitcher_id = pe.pitcher_id
        and pp.game_date  = pe.game_date
),

-- Daily soft-weighted aggregation per (batter_cluster, pitcher_cluster, game_date)
daily_weighted as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        sum(joint_weight)                                             as daily_weight,
        sum(woba_value * joint_weight)                               as daily_woba_num,
        sum(woba_denom * joint_weight)                               as daily_woba_denom,
        sum(case when xwoba is not null
                 then xwoba * joint_weight else 0 end)               as daily_xwoba_num,
        sum(case when xwoba is not null
                 then joint_weight else 0 end)                       as daily_xwoba_weight
    from pa_weighted
    group by 1, 2, 3
),

-- 180-day rolling window, excluding same day (1 day preceding gap)
rolling as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        sum(daily_weight) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as pa_weight,
        sum(daily_woba_num) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as woba_num,
        sum(daily_woba_denom) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as woba_denom,
        sum(daily_xwoba_num) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as xwoba_num,
        sum(daily_xwoba_weight) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as xwoba_weight
    from daily_weighted
),

with_shrinkage as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        pa_weight,
        round(woba_num / nullif(woba_denom, 0), 3)                   as raw_woba,
        round(xwoba_num / nullif(xwoba_weight, 0), 3)                as raw_xwoba,
        pa_weight / (pa_weight + 100.0)                              as shrink_weight,
        round(
            (pa_weight / (pa_weight + 100.0))
                * coalesce(woba_num / nullif(woba_denom, 0), 0.320)
            + (1 - pa_weight / (pa_weight + 100.0)) * 0.320,
            3
        )                                                            as adj_woba,
        round(
            (pa_weight / (pa_weight + 100.0))
                * coalesce(xwoba_num / nullif(xwoba_weight, 0), 0.315)
            + (1 - pa_weight / (pa_weight + 100.0)) * 0.315,
            3
        )                                                            as adj_xwoba
    from rolling
    where pa_weight >= 50
)

select * from with_shrinkage

{% else %}

select * from baseball_data.lakehouse_ext.mart_batter_archetype_vs_pitcher_cluster

{% endif %}

-- feature_pregame_umpire_features.sql
-- Grain: one row per game_pk (for games with a known HP umpire).
-- Purpose: trailing 3-year z-scores for HP umpire tendency relative to
-- league average. Leakage guard: only games strictly before the current
-- game date are used to compute trailing averages.
--
-- k_pct/bb_pct z-scores are retained in schema but default to 0.0 because
-- the UmpScorecards by-game export does not include those metrics. If
-- per-game k%/bb% is populated in future, the z-scores will compute correctly.
-- Primary predictive signals are ump_runs_per_game_zscore,
-- ump_run_impact_zscore, and ump_accuracy_zscore.
--
-- Minimum sample gate: ump_games_sample < 10 → all z-scores = 0.0.
--
-- E11.1-W11 Tier-B lakehouse migration. DuckDB branch recomputes the trailing z-scores over
-- the migrated stg_statsapi_umpire_game_log (registered as a DuckDB view by run_w1_lakehouse
-- ._build_w11b) with a Snowflake→DuckDB dialect rewrite (dateadd('year',-3,x) → x - interval
-- '3' year). The Snowflake (else) branch is a thin view over the lakehouse_ext external table
-- (rollback path). This is the W8a-deferred straggler the W8b aggregator reads — once the
-- native parquet lands at lakehouse/feature_pregame_umpire_features/, the W8b precursor VIEW
-- reads it directly (replacing the W7b-1 export_features_to_s3.py mirror at the same S3 path).

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11b_lakehouse']) }}

with

ump_history as (
    select
        game_pk,
        game_date,
        season,
        umpire_name,
        k_pct,
        bb_pct,
        total_runs,
        total_run_impact,
        accuracy_above_expected
    from {{ ref('stg_statsapi_umpire_game_log') }}
    where total_runs is not null  -- exclude daily-only assignment rows
),

-- League average and stddev per season for z-score normalization
league_avg as (
    select
        season,
        avg(k_pct)                    as lg_k_pct_avg,
        stddev(k_pct)                 as lg_k_pct_std,
        avg(bb_pct)                   as lg_bb_pct_avg,
        stddev(bb_pct)                as lg_bb_pct_std,
        avg(total_runs)               as lg_runs_avg,
        stddev(total_runs)            as lg_runs_std,
        avg(total_run_impact)         as lg_run_impact_avg,
        stddev(total_run_impact)      as lg_run_impact_std,
        avg(accuracy_above_expected)  as lg_accuracy_avg,
        stddev(accuracy_above_expected) as lg_accuracy_std
    from ump_history
    group by season
),

-- Per-umpire trailing 3-year averages for each target game
-- LEAKAGE GUARD: only historical games strictly before the current game date
ump_trailing as (
    select
        a.game_pk                             as target_game_pk,
        a.game_date                           as target_game_date,
        a.umpire_name,
        avg(b.k_pct)                          as ump_k_pct_trailing,
        avg(b.bb_pct)                         as ump_bb_pct_trailing,
        avg(b.total_runs)                     as ump_runs_trailing,
        avg(b.total_run_impact)               as ump_run_impact_trailing,
        avg(b.accuracy_above_expected)        as ump_accuracy_trailing,
        count(*)                              as ump_games_sample
    from {{ ref('stg_statsapi_umpire_game_log') }} a
    join ump_history b
        on  b.umpire_name = a.umpire_name
        and b.game_date  >= (a.game_date - interval '3' year)  -- DuckDB: dateadd('year',-3,a.game_date)
        and b.game_date   < a.game_date   -- LEAKAGE GUARD: strictly before target
    group by a.game_pk, a.game_date, a.umpire_name
),

final as (
    select
        t.target_game_pk                                 as game_pk,
        t.umpire_name,
        t.ump_games_sample,
        t.ump_k_pct_trailing,
        t.ump_bb_pct_trailing,
        t.ump_runs_trailing,
        t.ump_run_impact_trailing,
        t.ump_accuracy_trailing,

        -- k_pct z-score (defaults to 0.0; k_pct not in UmpScorecards by-game export)
        case
            when t.ump_games_sample < 10 then 0.0
            when coalesce(l.lg_k_pct_std, 0) = 0 then 0.0
            when t.ump_k_pct_trailing is null then 0.0
            else (t.ump_k_pct_trailing - l.lg_k_pct_avg) / l.lg_k_pct_std
        end                                              as ump_k_pct_zscore,

        -- bb_pct z-score (defaults to 0.0; bb_pct not in UmpScorecards by-game export)
        case
            when t.ump_games_sample < 10 then 0.0
            when coalesce(l.lg_bb_pct_std, 0) = 0 then 0.0
            when t.ump_bb_pct_trailing is null then 0.0
            else (t.ump_bb_pct_trailing - l.lg_bb_pct_avg) / l.lg_bb_pct_std
        end                                              as ump_bb_pct_zscore,

        -- Runs per game z-score
        case
            when t.ump_games_sample < 10 then 0.0
            when coalesce(l.lg_runs_std, 0) = 0 then 0.0
            else (t.ump_runs_trailing - l.lg_runs_avg) / l.lg_runs_std
        end                                              as ump_runs_per_game_zscore,

        -- Total run impact z-score (direct umpire zone effect on run expectancy)
        case
            when t.ump_games_sample < 10 then 0.0
            when coalesce(l.lg_run_impact_std, 0) = 0 then 0.0
            else (t.ump_run_impact_trailing - l.lg_run_impact_avg) / l.lg_run_impact_std
        end                                              as ump_run_impact_zscore,

        -- Accuracy above expected z-score
        case
            when t.ump_games_sample < 10 then 0.0
            when coalesce(l.lg_accuracy_std, 0) = 0 then 0.0
            else (t.ump_accuracy_trailing - l.lg_accuracy_avg) / l.lg_accuracy_std
        end                                              as ump_accuracy_zscore

    from ump_trailing t
    left join league_avg l
        on l.season = year(t.target_game_date)
)

select * from final

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_umpire_features

{% endif %}

-- =============================================================================
-- int_bullpen_ali_by_season.sql  —  Story A2.11 (bullpen support model)
-- Grain: one row per (season, pitcher_id) for relievers with ≥20 appearances.
--
-- Normalized average Leverage Index (aLI) per reliever-season, ported from
-- compute_bullpen_posteriors._load_normalized_ali_map. The downstream bullpen
-- posterior joins this TWICE: season-1 → leverage_role; season (full) → the
-- role_changed flag. Both use the FULL-SEASON aLI (no as-of) to match the
-- BACKFILL path that built the historical eb_bullpen_posteriors table — NOT the
-- daily as-of path (role_changed is informational metadata, not a posterior input).
--
-- aLI = (pitcher's mean per-at-bat |Δ home win-exp|) / (season mean per-at-bat
-- |Δ home win-exp| across all relievers). Starters excluded by anti-join on
-- (game_pk, pitcher_id, pitching_team).
-- =============================================================================

-- Story A2.11: incremental by season (delete+insert). aLI for a CLOSED season is
-- immutable, but the current season's aLI shifts as games accumulate (and the
-- prior season is the leverage_role basis), so incremental runs recompute current
-- + prior season only — avoiding a daily all-seasons pitch-level rescan.

-- E11.1-W8a: dual-branch. DuckDB branch (real compute -> S3, run_w1_lakehouse._build_w8a)
-- reads the migrated upstream marts/staging (registered DuckDB views) + the S3-mirrored
-- player_sequential_posteriors where applicable; is_incremental blocks are stripped by
-- extract_duckdb_sql (DuckDB = full rebuild -> COPY). The TYPE-PIN block (gen_type_contract
-- --write) casts every FLOAT output ::double (INC-19 cure) so the S3 parquet / lakehouse_ext
-- type is stable; guarded by test_type_contract_guard.py. The Snowflake (else) branch MERGEs
-- from the lakehouse_ext external table; at cutover the operator DROPs+rebuilds this
-- incremental so the stored NUMBER cols adopt the FLOAT type (INC-19).

{% if target.name == 'duckdb' %}

{{ config(materialized='incremental', unique_key='season', incremental_strategy='delete+insert', tags=['w8a_lakehouse']) }}

with reliever_at_bats as (
    select
        bp.game_year as season,
        bp.game_pk,
        bp.at_bat_number,
        bp.pitcher_id,
        case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end as pitching_team,
        abs(ppe.delta_home_win_exp) as abs_delta
    from stg_batter_pitches bp
    join mart_pitch_play_event ppe on ppe.pitch_sk = bp.pitch_sk
    where bp.game_type = 'R'
      and ppe.delta_home_win_exp is not null
      and bp.game_year between 2015 and year(current_date())
    {% if is_incremental() %}
      and bp.game_year >= year(current_date()) - 1
    {% endif %}
),

starters as (
    select game_pk, pitcher_id, pitching_team
    from mart_starting_pitcher_game_log
),

reliever_only as (
    select rab.*
    from reliever_at_bats rab
    left join starters s
      on  s.game_pk       = rab.game_pk
      and s.pitcher_id    = rab.pitcher_id
      and s.pitching_team = rab.pitching_team
    where s.pitcher_id is null
),

at_bat_scores as (
    select season, pitcher_id, game_pk, at_bat_number, sum(abs_delta) as ab_score
    from reliever_only
    group by season, pitcher_id, game_pk, at_bat_number
),

season_avg as (
    select season, avg(ab_score) as season_mean_ab_score
    from at_bat_scores
    group by season
),

pitcher_season as (
    select season, pitcher_id,
        count(distinct game_pk) as appearances,
        avg(ab_score)           as raw_ali
    from at_bat_scores
    group by season, pitcher_id
),

final as (

select
    ps.season,
    ps.pitcher_id::varchar                       as pitcher_id,
    ps.appearances,
    ps.raw_ali / sa.season_mean_ab_score         as normalized_ali
from pitcher_season ps
join season_avg sa on sa.season = ps.season
where ps.appearances >= 20

)

-- ============================================================================
-- INC-19 DURABLE TYPE-PIN (2026-06-29) — see CLAUDE.md "type-contract guard".
-- Every FLOAT output column is cast to an explicit ::double so an upstream
-- NUMBER<->FLOAT migration (a lakehouse dual-branch flip) can NEVER drift this
-- incremental's stored column type again — the recurring HALT class that fired
-- 5x (INC-15 / W1d / INC-16-P0 / INC-19 / INC-19-recurrence). ::double (NOT
-- ::float = 32-bit in DuckDB) is value-preserving 64-bit; it ADOPTS the FLOAT
-- types the table already holds, so this is a no-op incremental (no type ALTER).
--
-- This pinned set is contract-checked by betting_ml/tests/test_type_contract_guard.py
-- against dbt/type_contracts/int_bullpen_ali_by_season.types.json. If you ADD a column or
-- INTEND a type change, update BOTH this block AND that manifest in the SAME PR
-- (regenerate via scripts/gen_type_contract.py --write) or CI goes red. A new
-- numeric column that can ever be FLOAT MUST be ::double-pinned here.
-- NOTE: the explicit outer select is intentional — a column added to `final` but
-- not added here is DROPPED; the guard's set-equality check catches that too.
-- TYPE-PIN-START (generated; do not hand-edit individual lines)
select
    season,
    pitcher_id,
    appearances,
    normalized_ali::double as normalized_ali
from final
-- TYPE-PIN-END
{% else %}

{{ config(materialized='incremental', unique_key='season', incremental_strategy='delete+insert') }}

select * from baseball_data.lakehouse_ext.int_bullpen_ali_by_season
{% if is_incremental() %}
  where season >= year(current_date()) - 1
{% endif %}

{% endif %}

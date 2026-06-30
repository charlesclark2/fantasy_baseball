-- =============================================================================
-- eb_bullpen_team_posteriors.sql  —  Story E1.7 (de-leak; was A2.11)
-- Grain: one row per (game_pk, team) — LEAKAGE-SAFE pre-game bullpen aggregate.
--
-- ⭐ E1.7 DE-LEAK (2026-06-18). The prior construction had a WITHIN-GAME LEAK
-- (proven by E2.1b — see quant_sports_intel_models/.../E2_1b_HANDOFF.md). It
-- aggregated the per-reliever EB over:
--   (a) ROSTER  = the arms that ACTUALLY PITCHED in the eval game, and
--   (b) WEIGHT  = `outs_in_game` = the outs each recorded IN the eval game.
-- Both read the game-G outcome, so the feature could not be formed before first
-- pitch and its backfilled values peeked at the result. It ranked #1/#2 on every
-- champion offline, then collapsed to statistical noise once de-leaked, and was
-- null/imputed at serve time — a NAMED cause of the offline→live skill collapse
-- (project_prod_model_audit_jun2026 corr 0.42→0.001 / project_epic30_3_status).
--
-- THE FIX (Path A — pure-dbt port of compute_bullpen_v3.aggregate_team_v3 with
-- weight_mode='equal'; the per-reliever EBs in eb_bullpen_posteriors are ALREADY
-- as-of-safe, so ONLY the roster + weight + spine change):
--   * SPINE   → mart_game_spine (completed + today's SCHEDULED slate) instead of
--     the appeared-in-game roster. The old base only ever produced rows for
--     COMPLETED games, so the feature was structurally NULL for tonight's slate at
--     serve time; spining on mart_game_spine POPULATES it PRE-GAME.
--   * ROSTER  → the team's LEAKAGE-SAFE trailing-30d pre-game relief POOL: every
--     reliever who made >=1 relief appearance for the team in
--     [game_date - 30d, game_date) (STRICTLY prior). Each pool arm carries its EB
--     posterior as of its MOST-RECENT prior appearance (as-of-safe; at most one
--     appearance stale vs a fresh as-of-tonight recompute — and that recompute
--     would itself only add already-public prior games, so the difference is
--     leakage-safe; see the parity note below).
--   * WEIGHT  → EQUAL (plain mean). Equal ≈ expected-leverage to 0.001 per-side
--     NegBin NLL (E2.1b), so the SIMPLEST leakage-safe aggregate is the right
--     replacement (validated-better, not most-elaborate).
--
-- Output columns are UNCHANGED (team_eb_bullpen_xwoba / _uncertainty / n_relievers
-- / n_prior_only) so mart_bullpen_effectiveness and the downstream feature marts
-- need no rename. coverage_pct downstream = n_relievers / (n_relievers +
-- n_prior_only) retains its exact prior semantics over the new (pre-game) pool.
--
-- ⚠️ Validation: the de-leaked feature WILL look worse on offline NLL/Brier/
-- importance — that is CORRECT (a peek was removed), NOT a regression. Gate on
-- live/forward + the serving-parity harness, never offline metrics. Structural
-- parity vs the tested Python aggregate_team_v3(weight_mode='equal') is checked by
-- betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py (operator-run).
--
-- ⚠️ First deploy: the construction changed (new keys for scheduled games; some
-- empty-pool completed games no longer emit a row), so DROP this table and rebuild
-- with --full-refresh — a plain incremental MERGE would leave stale leaked rows.
-- =============================================================================

-- Story A2.11: incremental (merge on grain), scoped to recent games to match the
-- per-reliever model's daily window.

-- E11.1-W8a: dual-branch. DuckDB branch (real compute -> S3, run_w1_lakehouse._build_w8a)
-- reads the migrated upstream marts/staging (registered DuckDB views) + the S3-mirrored
-- player_sequential_posteriors where applicable; is_incremental blocks are stripped by
-- extract_duckdb_sql (DuckDB = full rebuild -> COPY). The TYPE-PIN block (gen_type_contract
-- --write) casts every FLOAT output ::double (INC-19 cure) so the S3 parquet / lakehouse_ext
-- type is stable; guarded by test_type_contract_guard.py. The Snowflake (else) branch MERGEs
-- from the lakehouse_ext external table; at cutover the operator DROPs+rebuilds this
-- incremental so the stored NUMBER cols adopt the FLOAT type (INC-19).

{% if target.name == 'duckdb' %}

{{ config(materialized='incremental', unique_key=['game_pk', 'team'], incremental_strategy='merge', tags=['w8a_lakehouse']) }}

with spine as (
    -- mart_game_spine = completed + today's SCHEDULED games (A1.11), so the live
    -- pre-game serve has a row for tonight's slate (the old appeared-in-game roster
    -- did not). game_year is the season; game_type 'R' only.
    select
        game_pk,
        game_date::date as game_date,
        game_year       as season,
        home_team,
        away_team
    from mart_game_spine
    where game_type = 'R'
    {% if is_incremental() %}
    and game_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
    {% endif %}
),

-- one (game_pk, game_date, season, team) target row per side
target_team_games as (
    select game_pk, game_date, season, home_team as team from spine
    union all
    select game_pk, game_date, season, away_team as team from spine
),

-- Per-reliever EB posteriors. These are ALREADY as-of-safe (season-to-date summed
-- strictly < the reliever's own appearance date — see eb_bullpen_posteriors). E1.7
-- re-rosters + re-weights these values; it does NOT recompute them.
reliever_eb as (
    select
        pitcher_id,
        game_date     as appearance_date,
        pitching_team,
        eb_xwoba_against,
        eb_xwoba_uncertainty,
        eb_data_source
    from eb_bullpen_posteriors
),

-- LEAKAGE-SAFE pre-game pool: relievers who appeared for the team in the strictly
-- prior 30 days, ranked to each reliever's MOST-RECENT prior appearance.
pool as (
    select
        ttg.game_pk,
        ttg.game_date,
        ttg.season,
        ttg.team,
        re.pitcher_id,
        re.eb_xwoba_against,
        re.eb_xwoba_uncertainty,
        re.eb_data_source,
        row_number() over (
            partition by ttg.game_pk, ttg.team, re.pitcher_id
            order by re.appearance_date desc
        ) as rn
    from target_team_games ttg
    join reliever_eb re
        on  re.pitching_team    = ttg.team
        and re.appearance_date  <  ttg.game_date                          -- STRICTLY prior (leakage guard)
        and re.appearance_date  >= (ttg.game_date - interval '30' day)
),

pool_latest as (
    select * from pool where rn = 1
),

final as (

select
    game_pk,
    any_value(game_date) as game_date,
    any_value(season)    as season,
    team,
    -- EQUAL-weight team aggregate. avg() ignores NULL EBs, mirroring the old
    -- nullif-guarded weighted mean.
    round(avg(eb_xwoba_against), 4)                               as team_eb_bullpen_xwoba,
    round(avg(eb_xwoba_uncertainty), 4)                           as team_eb_bullpen_uncertainty,
    count(*)                                                      as n_relievers,
    sum(case when eb_data_source = 'prior_only' then 1 else 0 end) as n_prior_only,
    current_date()        as fit_date,
    '{{ invocation_id }}' as run_id
from pool_latest
group by game_pk, team

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
-- against dbt/type_contracts/eb_bullpen_team_posteriors.types.json. If you ADD a column or
-- INTEND a type change, update BOTH this block AND that manifest in the SAME PR
-- (regenerate via scripts/gen_type_contract.py --write) or CI goes red. A new
-- numeric column that can ever be FLOAT MUST be ::double-pinned here.
-- NOTE: the explicit outer select is intentional — a column added to `final` but
-- not added here is DROPPED; the guard's set-equality check catches that too.
-- TYPE-PIN-START (generated; do not hand-edit individual lines)
select
    game_pk,
    game_date,
    season,
    team,
    team_eb_bullpen_xwoba::double as team_eb_bullpen_xwoba,
    team_eb_bullpen_uncertainty::double as team_eb_bullpen_uncertainty,
    n_relievers,
    n_prior_only,
    fit_date,
    run_id
from final
-- TYPE-PIN-END
{% else %}

{{ config(materialized='incremental', unique_key=['game_pk', 'team'], incremental_strategy='merge') }}

select * from baseball_data.lakehouse_ext.eb_bullpen_team_posteriors
{% if is_incremental() %}
  where game_date >= (select dateadd('day', -7, max(game_date)) from {{ this }})
{% endif %}

{% endif %}

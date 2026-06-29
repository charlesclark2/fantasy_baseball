-- =============================================================================
-- mart_player_profile_identity.sql   (E11.1-W7b lakehouse decommission)
-- Grain: one row per (player_id, player_type) for every active 2026 player
--        who appears in mart_batter_rolling_stats OR mart_starting_pitcher_game_log.
--
-- Purpose: single source of truth for the player-profile serving path
--          (write_serving_store.py → api_cache player/{id} blobs).
--
-- Columns:
--   player_id, player_type ('batter'|'pitcher')
--   full_name, first_name, last_name  — profiles primary, lineups fallback
--   position_abbreviation              — profiles primary, lineups fallback
--   team                               — most-recent batting_team / pitching_team
--   bats                               — batter_hand (batters only)
--   birth_date                         — from stg_statsapi_player_profiles (NULL for lineup-only)
--   age                                — floor(days since birth / 365.25); NULL if birth_date unknown
--   height_inches                      — total height in inches (NULL for lineup-only players)
--   weight_lbs                         — weight in pounds (NULL for lineup-only players)
--   is_on_il                           — TRUE if feature_pregame_injury_status
--                                        has is_current = TRUE for this player
--   il_since                           — date the current IL stint started (NULL if healthy)
--
-- E11.1-W7b dual-branch lakehouse model (from-scratch S3 mini-wave). DuckDB branch
-- reads the migrated upstreams — mart_batter_rolling_stats (W2),
-- mart_starting_pitcher_game_log (W2), stg_statsapi_player_profiles (W4),
-- stg_statsapi_lineups (W6), feature_pregame_injury_status (W7b) — all registered
-- as DuckDB views by run_w1_lakehouse.py, and writes the S3 parquet. The Snowflake
-- (else) branch is the UNCHANGED native build (rollback path) — cutover to the
-- lakehouse_ext external table is a later step, gated on the parity check, NOT done
-- here. Snowflake→DuckDB dialect rewrites in the duckdb arm:
--   split_part(x, ' ', -1)  → str_split(x, ' ')[-1]   (DuckDB split_part has no
--                                                       negative index; array idx does)
--   datediff('day', a, b)   → date_diff('day', a, b)
-- Deterministic SQL → row-exact parity (not a TOLERANCE-class model).
-- =============================================================================

{{ config(materialized='table') }}

{% if target.name == 'duckdb' %}

with

-- ── Batter universe: distinct 2026 batters, most-recent team + bats ──────────
batter_latest as (
    select
        batter_id                                             as player_id,
        batting_team                                          as team,
        batter_hand                                           as bats,
        row_number() over (
            partition by batter_id
            order by game_date desc nulls last
        )                                                     as _rn
    from mart_batter_rolling_stats
    where game_year = 2026
),

batters as (
    select player_id, team, bats
    from batter_latest
    where _rn = 1
),

-- ── Pitcher universe: distinct 2026 starters, most-recent team ───────────────
pitcher_latest as (
    select
        pitcher_id                                            as player_id,
        pitching_team                                         as team,
        row_number() over (
            partition by pitcher_id
            order by game_date desc nulls last
        )                                                     as _rn
    from mart_starting_pitcher_game_log
    where game_year = 2026
),

pitchers as (
    select player_id, team
    from pitcher_latest
    where _rn = 1
),

-- ── Combined universe with player_type label ─────────────────────────────────
universe as (
    select player_id, 'batter'  as player_type, team, bats from batters
    union all
    select player_id, 'pitcher' as player_type, team, null  from pitchers
),

-- ── Identity: stg_statsapi_player_profiles (primary source) ─────────────────
profiles as (
    select
        player_id,
        full_name,
        birth_date,
        height_inches,
        weight_lbs,
        case primary_position_code
            when '1'  then 'SP' when '2'  then 'C'  when '3'  then '1B'
            when '4'  then '2B' when '5'  then '3B' when '6'  then 'SS'
            when '7'  then 'LF' when '8'  then 'CF' when '9'  then 'RF'
            when '10' then 'DH' when 'O'  then 'OF' else null
        end                                                   as position_abbreviation
    from stg_statsapi_player_profiles
),

-- ── Identity fallback: most-recent row per player in stg_statsapi_lineups ────
lineups_deduped as (
    select
        player_id,
        first_value(full_name) over (
            partition by player_id order by official_date desc nulls last
        )                                                     as full_name,
        first_value(position_abbreviation) over (
            partition by player_id order by official_date desc nulls last
        )                                                     as position_abbreviation,
        row_number() over (
            partition by player_id order by official_date desc nulls last
        )                                                     as _rn
    from stg_statsapi_lineups
),

lineups as (
    select player_id, full_name, position_abbreviation
    from lineups_deduped
    where _rn = 1
),

-- ── Current IL status from SCD-2 feature layer ───────────────────────────────
current_il as (
    select
        player_id,
        true                                                  as is_on_il,
        valid_from::date                                      as il_since
    from feature_pregame_injury_status
    where is_current = true
      and is_injured = true
)

-- ── Final join ────────────────────────────────────────────────────────────────
select
    u.player_id,
    u.player_type,
    coalesce(p.full_name, l.full_name)                        as full_name,
    split_part(coalesce(p.full_name, l.full_name, ''), ' ', 1) as first_name,
    str_split(coalesce(p.full_name, l.full_name, ''), ' ')[-1] as last_name,
    coalesce(
        p.position_abbreviation,
        l.position_abbreviation,
        case u.player_type when 'pitcher' then 'SP' else 'POS' end
    )                                                         as position_abbreviation,
    u.team,
    u.bats,
    p.birth_date,
    floor(date_diff('day', p.birth_date, current_date) / 365.25)::int as age,
    p.height_inches,
    p.weight_lbs,
    coalesce(il.is_on_il, false)                              as is_on_il,
    il.il_since
from universe u
left join profiles  p  on p.player_id  = u.player_id
left join lineups   l  on l.player_id  = u.player_id
left join current_il il on il.player_id = u.player_id

{% else %}

with

-- ── Batter universe: distinct 2026 batters, most-recent team + bats ──────────
batter_latest as (
    select
        batter_id                                             as player_id,
        batting_team                                          as team,
        batter_hand                                           as bats,
        row_number() over (
            partition by batter_id
            order by game_date desc nulls last
        )                                                     as _rn
    from {{ ref('mart_batter_rolling_stats') }}
    where game_year = 2026
),

batters as (
    select player_id, team, bats
    from batter_latest
    where _rn = 1
),

-- ── Pitcher universe: distinct 2026 starters, most-recent team ───────────────
pitcher_latest as (
    select
        pitcher_id                                            as player_id,
        pitching_team                                         as team,
        row_number() over (
            partition by pitcher_id
            order by game_date desc nulls last
        )                                                     as _rn
    from {{ ref('mart_starting_pitcher_game_log') }}
    where game_year = 2026
),

pitchers as (
    select player_id, team
    from pitcher_latest
    where _rn = 1
),

-- ── Combined universe with player_type label ─────────────────────────────────
universe as (
    select player_id, 'batter'  as player_type, team, bats from batters
    union all
    select player_id, 'pitcher' as player_type, team, null  from pitchers
),

-- ── Identity: stg_statsapi_player_profiles (primary source) ─────────────────
profiles as (
    select
        player_id,
        full_name,
        birth_date,
        height_inches,
        weight_lbs,
        case primary_position_code
            when '1'  then 'SP' when '2'  then 'C'  when '3'  then '1B'
            when '4'  then '2B' when '5'  then '3B' when '6'  then 'SS'
            when '7'  then 'LF' when '8'  then 'CF' when '9'  then 'RF'
            when '10' then 'DH' when 'O'  then 'OF' else null
        end                                                   as position_abbreviation
    from {{ ref('stg_statsapi_player_profiles') }}
),

-- ── Identity fallback: most-recent row per player in stg_statsapi_lineups ────
lineups_deduped as (
    select
        player_id,
        first_value(full_name) over (
            partition by player_id order by official_date desc nulls last
        )                                                     as full_name,
        first_value(position_abbreviation) over (
            partition by player_id order by official_date desc nulls last
        )                                                     as position_abbreviation,
        row_number() over (
            partition by player_id order by official_date desc nulls last
        )                                                     as _rn
    from {{ ref('stg_statsapi_lineups') }}
),

lineups as (
    select player_id, full_name, position_abbreviation
    from lineups_deduped
    where _rn = 1
),

-- ── Current IL status from SCD-2 feature layer ───────────────────────────────
current_il as (
    select
        player_id,
        true                                                  as is_on_il,
        valid_from::date                                      as il_since
    from {{ ref('feature_pregame_injury_status') }}
    where is_current = true
      and is_injured = true
)

-- ── Final join ────────────────────────────────────────────────────────────────
select
    u.player_id,
    u.player_type,
    coalesce(p.full_name, l.full_name)                        as full_name,
    split_part(coalesce(p.full_name, l.full_name, ''), ' ', 1) as first_name,
    split_part(coalesce(p.full_name, l.full_name, ''), ' ', -1) as last_name,
    coalesce(
        p.position_abbreviation,
        l.position_abbreviation,
        case u.player_type when 'pitcher' then 'SP' else 'POS' end
    )                                                         as position_abbreviation,
    u.team,
    u.bats,
    p.birth_date,
    floor(datediff('day', p.birth_date, current_date) / 365.25)::int as age,
    p.height_inches,
    p.weight_lbs,
    coalesce(il.is_on_il, false)                              as is_on_il,
    il.il_since
from universe u
left join profiles  p  on p.player_id  = u.player_id
left join lineups   l  on l.player_id  = u.player_id
left join current_il il on il.player_id = u.player_id

{% endif %}

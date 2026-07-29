-- =============================================================================
-- stg_statsapi_player_injury_status.sql   (E11.1-W7b lakehouse decommission)
-- Grain: one row per player_id × status interval (status_start_date, status_end_date)
-- Source: stg_statsapi_transactions (+ the rolling appearance marts, E9.48)
-- Card 7.I — Injury / Confirmed Lineup Features
-- =============================================================================
-- Derives point-in-time injury status from roster transaction events.
-- For each player × game_date, join on:
--   inj.player_id         = batter_id
--   inj.status_start_date <= official_date   -- LEAKAGE GUARD: strictly pre-game
--   (inj.status_end_date  >  official_date OR inj.status_end_date IS NULL)
--
-- is_injured = true  → IL placement (player unavailable)
-- is_injured = false → activation / reinstatement (player returned)
-- No matching row   → assume available (is_injured = false via COALESCE in consumer)
--
-- The Stats API uses type_code='SC' (Status Change) for all IL-related events.
-- Classification relies on description text patterns confirmed via dry-run output.
--
-- =============================================================================
-- 🐞 E9.48 (2026-07-29) — "HEALTHY PLAYERS PERMANENTLY FLAGGED ON THE IL"
-- =============================================================================
-- SYMPTOM: 62 of the 187 players this model reported as CURRENTLY on the IL were
-- provably active — e.g. Jesús Luzardo (666200) served `is_on_il=true,
-- il_since=2024-06-19` on his player page while starting for PHI on 2026-07-24.
--
-- MECHANISM: an interval is "current" iff `status_end_date is null` — i.e. iff no
-- LATER classified event exists. So a MISSED clearing event is not a one-day blip,
-- it pins the player as injured FOREVER. Three independent ways the clear went
-- missing (all measured against the live lakehouse, 2026-07-29):
--
--   (a) BARE ACTIVATION TEXT — 21 players. The Stats API very often writes the
--       activation WITHOUT the list suffix: "Arizona Diamondbacks activated C
--       Adrian Del Castillo." / "Tampa Bay Rays activated RHP Drew Rasmussen."
--       The old pattern REQUIRED '% activated%from the % injured list%', so every
--       bare activation classified NULL → dropped → the placement stayed open.
--
--   (b) RETURN VIA A ROSTER MOVE, NOT AN 'SC' — 29 players. A player can come off
--       the IL by being optioned/recalled/selected, with no activation SC at all
--       (Anthony Volpe: 10-day IL 3/22 → rehab → OPT 5/4 → CU 5/12, still flagged).
--       CU / SE / OPT are mutually exclusive with being on the MLB IL.
--
--   (c) THE FEED HAS A STRUCTURAL OFF-SEASON HOLE — 12 players with NO clearing
--       transaction of any kind. ingest_transactions.py runs on a 7-day lookback
--       from the daily job, which only runs in-season: the transaction table holds
--       ZERO rows for Nov/Dec/Jan/Feb of EVERY year — and that is exactly when MLB
--       reinstates the 60-day IL en masse (the live API returns 843 IL-related
--       transactions for 2025-11-01..10 alone, incl. "…activated … from the 60-day
--       injured list"). That is Luzardo: his last classified event is the
--       2024-06-19 transfer to the 60-day IL; his reinstatement fell in the hole.
--
-- FIX (at the source, three parts — do NOT patch the display):
--   1. BROADEN the clearing classification to the bare activated/reinstated text.
--   2. Treat CU (Recalled) / SE (Selected) / OPT (Optioned) as clearing events.
--   3. GROUND-TRUTH RECONCILIATION: a player who APPEARED IN AN MLB GAME is not on
--      the IL. Any injured interval containing an appearance is truncated at that
--      first appearance. This is the durable backstop — it is immune to (c) and to
--      any future Stats API description drift, because it never reads the text.
--      NOT leakage: the appearance PROVES the activation happened at or before that
--      date, so closing the interval AT the appearance is the LATEST (most
--      conservative) admissible end — it can only shorten a wrong injured window,
--      never extend one. The consumer's point-in-time join is `valid_to >
--      official_date`, so a player is available from the game he played onward; the
--      pregame consumers (feature_pregame_lineup_features / _expected_lineup) key
--      off the CONFIRMED LINEUP, which already knows he is playing.
--   Also: consecutive same-state events are now COMPRESSED, so a 15-day → 60-day IL
--   transfer is one interval and `il_since` reports the ORIGINAL placement date
--   rather than the transfer date, and the window ordering is made DETERMINISTIC
--   (event_date, transaction_id) — it was previously event_date alone, so same-day
--   events tie-broke arbitrarily between runs.
--
-- GUARD: scripts/check_injury_status_health.py (ALERT tier, wired into the daily
--   job) fails on a STALE transaction feed and on the correctness signature itself
--   — any player reported currently-IL who has played since. Never let a wrong
--   status serve silently again.
-- ⚠️ Off-season coverage is a SEPARATE, still-open source gap: the ingest must be
--   backfilled over the Nov–Feb windows (see the E9.48 handoff). The appearance
--   reconciliation makes the SERVED status correct regardless, but the transaction
--   history stays incomplete until that backfill runs.
-- =============================================================================
--
-- DuckDB branch (E11.1-W7b): reads the migrated stg_statsapi_transactions
-- (registered as a DuckDB view by run_w1_lakehouse.py). The classification +
-- lead()-window logic is plain relational SQL (ilike / coalesce / lead are all
-- DuckDB-native), so the branch is the same body — value-identical to Snowflake.
-- INC-23: the lakehouse parquet stores the date columns as ISO VARCHAR, so the
-- DuckDB branch casts ::date AT THE USE-SITE for the appearance comparison and
-- casts the truncation back to VARCHAR so the output type contract is unchanged.
-- The Snowflake (else) branch reads the same columns as native DATEs.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w7b_lakehouse']) }}

with

transactions as (
    select * from stg_statsapi_transactions
),

-- E9.48: every MLB regular-season appearance, batters + pitchers (both marts are
-- one row per player × game). This is the ground-truth "he is not on the IL"
-- signal. Registered as S3-parquet views by run_w1_lakehouse.py (W7B_PRECURSOR_VIEWS).
appearances as (
    select batter_id  as player_id, game_date::date as game_date from mart_batter_rolling_stats
    union all
    select pitcher_id as player_id, game_date::date as game_date from mart_pitcher_rolling_stats
),

status_classified as (
    select
        transaction_id,
        player_id,
        player_name,
        coalesce(effective_date, transaction_date) as event_date,
        type_code,
        case
            -- IL / restricted list placements → player unavailable.
            -- Evaluated FIRST so a combined "activated … and placed on the …
            -- injured list" description can never be read as a clear.
            when type_code = 'SC' and (
                description ilike '% on the % injured list%'
                or description ilike '% transferred to the % injured list%'
                or description ilike '% on the paternity list%'
                or description ilike '% on the bereavement list%'
                or description ilike '% on the family%emergency list%'
            ) then true
            -- Activations / returns → player available again
            when type_code = 'SC' and (
                description ilike '% activated%from the % injured list%'
                or description ilike '% activated%from the paternity list%'
                or description ilike '% activated%from the bereavement list%'
                or description ilike '% reinstated%from the % injured list%'
            ) then false
            -- E9.48 (a): BARE activation / reinstatement — the Stats API frequently
            -- omits the list suffix ("Tampa Bay Rays activated RHP Drew Rasmussen.").
            when type_code = 'SC' and (
                description ilike '%activated%'
                or description ilike '%reinstated%'
            ) then false
            -- E9.48 (b): roster moves that are mutually exclusive with being on the
            -- MLB IL — you cannot be recalled, have your contract selected, or be
            -- optioned while on it. (TR/CLW/REL/DES are NOT here: a player can be
            -- traded, claimed, released or DFA'd while still injured.)
            when type_code in ('CU', 'SE', 'OPT') then false
            else null
        end                                         as is_injured
    from transactions
),

filtered as (
    select * from status_classified
    where is_injured is not null
),

-- E9.48: DETERMINISTIC event order. transaction_id is a numeric string from the
-- Stats API and increases with posting order, so it is the natural same-day
-- tiebreak; the try_cast keeps it numeric rather than lexicographic.
ordered as (
    select
        *,
        lag(is_injured) over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        ) as prev_is_injured
    from filtered
),

-- E9.48: COMPRESS consecutive same-state events, so a 15-day → 60-day IL transfer
-- is ONE interval starting at the original placement (a truer `il_since`) and a
-- run of roster moves does not shatter an available span into many rows.
state_changes as (
    select * from ordered
    where prev_is_injured is null or prev_is_injured <> is_injured
),

with_next_event as (
    select
        player_id,
        player_name,
        event_date           as status_start_date,
        lead(event_date) over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        )                    as status_end_date,   -- null = still current
        row_number() over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        )                    as interval_seq,      -- join key only; not selected out
        type_code,
        is_injured
    from state_changes
),

-- E9.48 (c): the ground-truth backstop. For every INJURED interval, the first MLB
-- appearance strictly inside it — the proof that a clearing event was missed.
appearance_close as (
    select
        w.player_id,
        w.interval_seq,
        min(a.game_date) as first_appearance
    from with_next_event w
    join appearances a
      on  a.player_id = w.player_id
      and a.game_date > w.status_start_date::date
      and (w.status_end_date is null or a.game_date < w.status_end_date::date)
    where w.is_injured
    group by 1, 2
)

select
    w.player_id,
    w.player_name,
    w.status_start_date,
    coalesce(ac.first_appearance::varchar, w.status_end_date) as status_end_date,
    w.type_code,
    w.is_injured
from with_next_event w
left join appearance_close ac
       on  ac.player_id    = w.player_id
       and ac.interval_seq = w.interval_seq

{% else %}

{{ config(materialized='table') }}

with

transactions as (
    select * from {{ ref('stg_statsapi_transactions') }}
),

-- E9.48: see the DuckDB branch. Both marts are views over the lakehouse_ext
-- external tables on this target, so this is a cheap column-pruned S3 read.
appearances as (
    select batter_id  as player_id, game_date from {{ ref('mart_batter_rolling_stats') }}
    union all
    select pitcher_id as player_id, game_date from {{ ref('mart_pitcher_rolling_stats') }}
),

status_classified as (
    select
        transaction_id,
        player_id,
        player_name,
        coalesce(effective_date, transaction_date) as event_date,
        type_code,
        case
            -- IL / restricted list placements → player unavailable.
            -- Evaluated FIRST so a combined "activated … and placed on the …
            -- injured list" description can never be read as a clear.
            when type_code = 'SC' and (
                description ilike '% on the % injured list%'
                or description ilike '% transferred to the % injured list%'
                or description ilike '% on the paternity list%'
                or description ilike '% on the bereavement list%'
                or description ilike '% on the family%emergency list%'
            ) then true
            -- Activations / returns → player available again
            when type_code = 'SC' and (
                description ilike '% activated%from the % injured list%'
                or description ilike '% activated%from the paternity list%'
                or description ilike '% activated%from the bereavement list%'
                or description ilike '% reinstated%from the % injured list%'
            ) then false
            -- E9.48 (a): BARE activation / reinstatement — the Stats API frequently
            -- omits the list suffix ("Tampa Bay Rays activated RHP Drew Rasmussen.").
            when type_code = 'SC' and (
                description ilike '%activated%'
                or description ilike '%reinstated%'
            ) then false
            -- E9.48 (b): roster moves that are mutually exclusive with being on the
            -- MLB IL — you cannot be recalled, have your contract selected, or be
            -- optioned while on it. (TR/CLW/REL/DES are NOT here: a player can be
            -- traded, claimed, released or DFA'd while still injured.)
            when type_code in ('CU', 'SE', 'OPT') then false
            else null
        end                                         as is_injured
    from transactions
),

filtered as (
    select * from status_classified
    where is_injured is not null
),

-- E9.48: DETERMINISTIC event order (see the DuckDB branch).
ordered as (
    select
        *,
        lag(is_injured) over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        ) as prev_is_injured
    from filtered
),

-- E9.48: COMPRESS consecutive same-state events (see the DuckDB branch).
state_changes as (
    select * from ordered
    where prev_is_injured is null or prev_is_injured <> is_injured
),

with_next_event as (
    select
        player_id,
        player_name,
        event_date           as status_start_date,
        lead(event_date) over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        )                    as status_end_date,   -- null = still current
        row_number() over (
            partition by player_id
            order by event_date, try_cast(transaction_id as bigint), transaction_id
        )                    as interval_seq,      -- join key only; not selected out
        type_code,
        is_injured
    from state_changes
),

-- E9.48 (c): the ground-truth backstop (see the DuckDB branch).
appearance_close as (
    select
        w.player_id,
        w.interval_seq,
        min(a.game_date) as first_appearance
    from with_next_event w
    join appearances a
      on  a.player_id = w.player_id
      and a.game_date > w.status_start_date
      and (w.status_end_date is null or a.game_date < w.status_end_date)
    where w.is_injured
    group by 1, 2
)

select
    w.player_id,
    w.player_name,
    w.status_start_date,
    coalesce(ac.first_appearance, w.status_end_date) as status_end_date,
    w.type_code,
    w.is_injured
from with_next_event w
left join appearance_close ac
       on  ac.player_id    = w.player_id
       and ac.interval_seq = w.interval_seq

{% endif %}

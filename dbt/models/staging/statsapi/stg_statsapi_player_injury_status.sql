-- =============================================================================
-- stg_statsapi_player_injury_status.sql
-- Grain: one row per player_id × status interval (status_start_date, status_end_date)
-- Source: stg_statsapi_transactions
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
-- =============================================================================

{{ config(materialized='table') }}

with

transactions as (
    select * from {{ ref('stg_statsapi_transactions') }}
),

status_classified as (
    select
        player_id,
        player_name,
        coalesce(effective_date, transaction_date) as event_date,
        type_code,
        case
            -- IL / restricted list placements → player unavailable
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
            else null
        end                                         as is_injured
    from transactions
),

filtered as (
    select * from status_classified
    where is_injured is not null
),

with_next_event as (
    select
        player_id,
        player_name,
        event_date           as status_start_date,
        lead(event_date) over (
            partition by player_id
            order by event_date
        )                    as status_end_date,   -- null = still current
        type_code,
        is_injured
    from filtered
)

select * from with_next_event

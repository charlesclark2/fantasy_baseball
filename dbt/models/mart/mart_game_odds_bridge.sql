-- =============================================================================
-- mart_game_odds_bridge.sql
-- Grain: one row per game_pk
-- Purpose: Bridge table linking every game in mart_game_spine to its
--          corresponding odds event_id(s) from The Odds API. Enables downstream
--          models to join game outcomes with pre-game odds.
--          (Full join/doubleheader notes preserved below — see git history.)
--
--          Two source-specific columns preserve full audit trail:
--            odds_api_event_id   — from mart_odds_outcomes (Odds API; all eras)
--            parlay_api_event_id — NULL since the E11.6 Parlay decommission
--          The coalesced event_id column provides a single join key for all
--          downstream models. Names (Stats API, Odds API) are resolved to a
--          team_id through the canonical team dimension, so the join is immune to
--          feed name drift. Doubleheader handling: odds_events assigns a game_slot
--          (1=earliest, 2=next) per (date, home, away) ordered by commence_time;
--          the final join adds game_number = game_slot to route each Stats API
--          game_pk to its correct event.
--
-- ⚠️ SERVING-COUPLED (E11.1-W6): downstream of mart_odds_outcomes; feeds the
-- odds/CLV serving subtree. Value-identical parity required before cutover.
--
-- DuckDB branch (E11.1-W6): plain-name reads of the migrated W5 chain
-- (dim_team_name_lookup / mart_game_spine), stg_statsapi_games (W3pre) and
-- mart_odds_outcomes (W6); the Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with team_lookup as (

    -- A1.9 canonical resolver: any feed/Stats API name -> team_id.
    -- Consumer contract: lower(regexp_replace(trim(name), '^G[12] ', '')).
    select name_lower, team_id
    from dim_team_name_lookup

),

game_results as (

    select
        gr.game_pk,
        gr.game_date,
        gr.game_type,
        gr.home_team,
        gr.home_team_name,
        gr.away_team,
        gr.away_team_name,
        h.team_id as home_team_id,
        a.team_id as away_team_id,
        coalesce(sg.game_number, 1) as game_number
    from mart_game_spine gr
    left join stg_statsapi_games sg on sg.game_pk = gr.game_pk
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(gr.home_team_name), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(gr.away_team_name), '^G[12] ', ''))

),

-- ── Odds API events (all eras) ────────────────────────────────────────────────
-- INC-2 fix (2026-06-22): resolve events from mart_odds_outcomes (the live /odds
-- feed) instead of mart_odds_events. mart_odds_outcomes carries the Odds API
-- event_id + commence_date + team names (all eras), stays live with /odds, and
-- shares the event_id space mart_odds_consensus joins on downstream.

odds_events_resolved as (

    select
        o.event_id,
        o.commence_date,
        o.commence_time,
        h.team_id as home_team_id,
        a.team_id as away_team_id,
        max(o.ingestion_ts) as ingestion_ts
    from mart_odds_outcomes o
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(o.home_team), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(o.away_team), '^G[12] ', ''))
    group by 1, 2, 3, 4, 5

),

odds_events as (

    select
        event_id          as odds_api_event_id,
        commence_date,
        home_team_id,
        away_team_id,
        row_number() over (
            partition by commence_date, home_team_id, away_team_id
            order by commence_time asc
        ) as game_slot
    from odds_events_resolved

)

-- E11.6 (2026-06-21): Parlay API permanently decommissioned. parlay_api_event_id
-- is preserved as a NULL column so downstream consumers compile without changes.

select

    -- ── Game keys ─────────────────────────────────────────────────────────────
    gr.game_pk,
    gr.game_date,
    gr.game_type,

    -- ── Teams (from game spine; authoritative abbreviation + full name) ───────
    gr.home_team                                                    as home_team_abbrev,
    gr.home_team_name,
    gr.away_team                                                    as away_team_abbrev,
    gr.away_team_name,
    gr.home_team_id,
    gr.away_team_id,

    -- ── Source-specific event keys ────────────────────────────────────────────
    oe.odds_api_event_id,
    null::varchar                                                   as parlay_api_event_id,

    -- ── Coalesced event key: Odds API only post-E11.6 ────────────────────────
    oe.odds_api_event_id                                            as event_id,

    -- ── Match quality ─────────────────────────────────────────────────────────
    (oe.odds_api_event_id is not null)::boolean                     as has_odds

from game_results gr
left join odds_events oe
    on  gr.game_date    = oe.commence_date
    and gr.home_team_id = oe.home_team_id
    and gr.away_team_id = oe.away_team_id
    and gr.game_number  = oe.game_slot

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_game_odds_bridge

{% endif %}

{{ config(materialized='table') }}

-- =============================================================================
-- stg_actionnetwork_public_betting_snapshots.sql
-- Story 15.6 — all ingestion snapshots from public_betting_raw, normalized and
-- joined to the pregame game-feature spine for game_pk resolution.
--
-- Grain: one row per (game_pk, loaded_at) after dedup.
--
-- Coverage: 2026-05-07 onward (Epic T.3 raw-capture start date).
-- game_pk resolution uses feature_pregame_game_features (the canonical pregame
-- spine: regular-season games only, INCLUDES today's not-yet-completed games and
-- retains full history). Previously this joined mart_game_results, which only
-- contains COMPLETED games — so public betting for today's slate was silently
-- dropped until each game finished (the "Market Action" panel was blank pre-game,
-- which is exactly the window it serves). The pregame spine has no public-betting
-- dependency, so this join stays acyclic.
--
-- Record hash covers the 4 independent pct columns:
--   home_ml_money_pct, home_ml_ticket_pct, over_money_pct, over_ticket_pct
-- away_ml and under columns are near-complements (100 - home/over) and would
-- produce redundant change detection; sharp signals are derived from these four.
-- =============================================================================

with source as (
    select
        game_date::date                                         as game_date,
        an_game_id::varchar                                     as an_game_id,
        case upper(home_team_abbr)
            when 'ARI' then 'AZ'
            else upper(home_team_abbr)
        end                                                     as home_team_norm,
        case upper(away_team_abbr)
            when 'ARI' then 'AZ'
            else upper(away_team_abbr)
        end                                                     as away_team_norm,
        home_ml_money_pct::float                                as home_ml_money_pct,
        away_ml_money_pct::float                                as away_ml_money_pct,
        home_ml_ticket_pct::float                               as home_ml_ticket_pct,
        away_ml_ticket_pct::float                               as away_ml_ticket_pct,
        over_money_pct::float                                   as over_money_pct,
        under_money_pct::float                                  as under_money_pct,
        over_ticket_pct::float                                  as over_ticket_pct,
        under_ticket_pct::float                                 as under_ticket_pct,
        (home_ml_money_pct - home_ml_ticket_pct)::float        as ml_sharp_signal,
        (over_money_pct - over_ticket_pct)::float              as total_sharp_signal,
        ingestion_timestamp::timestamp_ntz                      as loaded_at
    from {{ source('actionnetwork', 'public_betting_raw') }}
),

with_game_pk as (
    select
        g.game_pk,
        s.an_game_id,
        s.home_ml_money_pct,
        s.away_ml_money_pct,
        s.home_ml_ticket_pct,
        s.away_ml_ticket_pct,
        s.over_money_pct,
        s.under_money_pct,
        s.over_ticket_pct,
        s.under_ticket_pct,
        s.ml_sharp_signal,
        s.total_sharp_signal,
        md5(
            coalesce(cast(s.home_ml_money_pct  as varchar), '') || '|' ||
            coalesce(cast(s.home_ml_ticket_pct as varchar), '') || '|' ||
            coalesce(cast(s.over_money_pct     as varchar), '') || '|' ||
            coalesce(cast(s.over_ticket_pct    as varchar), '')
        )                                                       as record_hash,
        s.loaded_at
    from source s
    -- Pregame spine (regular-season, includes today + full history) → resolves
    -- game_pk for not-yet-completed games, unlike the completed-only mart_game_results.
    inner join {{ ref('feature_pregame_game_features') }} g
        on  s.game_date      = g.game_date::date
        and s.home_team_norm = g.home_team
        and s.away_team_norm = g.away_team
)

select *
from with_game_pk
qualify row_number() over (
    partition by game_pk, loaded_at
    order by home_ml_money_pct nulls last
) = 1

{{
    config(
        materialized='table'
    )
}}

-- =============================================================================
-- stg_actionnetwork_public_betting.sql
-- Card 8.R — normalize Action Network public-betting raw data.
-- Grain: one row per (game_date, an_game_id).
--
-- Action Network team abbreviations are nearly identical to the project's
-- ref_teams.team_abbrev convention. The only mismatch observed in 2025
-- responses is "ARI" (Action Network) vs. "AZ" (project / MLB Stats API);
-- we normalize ARI → AZ so joins on (game_date, home_team_id, away_team_id)
-- against feature_pregame_game_features.home_team / .away_team work cleanly.
--
-- Sharp signal columns:
--   ml_sharp_signal    = home_ml_money_pct - home_ml_ticket_pct
--   total_sharp_signal = over_money_pct    - over_ticket_pct
-- Positive = money side heavier than ticket side (proxy for sharp lean).
-- =============================================================================

with raw as (
    select * from {{ source('actionnetwork', 'public_betting_raw') }}
),

normalized as (
    select
        game_date::date                                  as game_date,
        an_game_id::varchar                              as an_game_id,

        -- Normalize Action Network abbreviations to ref_teams.team_abbrev.
        case upper(home_team_abbr)
            when 'ARI' then 'AZ'
            else upper(home_team_abbr)
        end                                              as home_team_id,
        case upper(away_team_abbr)
            when 'ARI' then 'AZ'
            else upper(away_team_abbr)
        end                                              as away_team_id,

        home_ml_money_pct::float                         as home_ml_money_pct,
        away_ml_money_pct::float                         as away_ml_money_pct,
        home_ml_ticket_pct::float                        as home_ml_ticket_pct,
        away_ml_ticket_pct::float                        as away_ml_ticket_pct,

        over_money_pct::float                            as over_money_pct,
        under_money_pct::float                           as under_money_pct,
        over_ticket_pct::float                           as over_ticket_pct,
        under_ticket_pct::float                          as under_ticket_pct,

        (home_ml_money_pct - home_ml_ticket_pct)::float  as ml_sharp_signal,
        (over_money_pct - over_ticket_pct)::float        as total_sharp_signal,

        ingestion_timestamp::timestamp_ntz               as ingestion_timestamp
    from raw
)

select * from normalized

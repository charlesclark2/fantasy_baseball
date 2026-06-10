-- A1.9 — guard against an MLB odds event whose team name fails to resolve to a
-- team_id via dim_team_name_lookup (a renamed/relocated franchise we forgot to
-- add to the ref_team_aliases seed). Such an event silently produces has_odds =
-- false in mart_game_odds_bridge, dropping odds for a real game.
--
-- The feeds also carry non-MLB noise (NCAA, Mexican league, team-total prop
-- markets) that CORRECTLY does not resolve. We isolate genuine MLB matchups by
-- the "exactly one side resolves" signal: a real h2h matchup where one franchise
-- mapped and the other did not. Both sides unresolved = non-MLB noise (ignored);
-- both resolved = healthy. Parlay events are restricted to market_key = 'h2h'
-- so team-total props ("Washington Total Runs") are excluded.
--
-- Returns offending events → the test fails and names the franchise to alias.

with parlay_resolved as (

    select distinct
        'parlay'            as source,
        po.event_id,
        po.game_date,
        po.home_team,
        po.away_team,
        h.team_id           as home_team_id,
        a.team_id           as away_team_id
    from {{ ref('stg_parlayapi_odds') }} po
    left join {{ ref('dim_team_name_lookup') }} h
        on h.name_lower = lower(regexp_replace(trim(po.home_team), '^G[12] ', ''))
    left join {{ ref('dim_team_name_lookup') }} a
        on a.name_lower = lower(regexp_replace(trim(po.away_team), '^G[12] ', ''))
    where po.market_key = 'h2h'

),

odds_api_resolved as (

    select distinct
        'odds_api'          as source,
        oe.event_id,
        oe.commence_date    as game_date,
        oe.home_team,
        oe.away_team,
        h.team_id           as home_team_id,
        a.team_id           as away_team_id
    from {{ ref('mart_odds_events') }} oe
    left join {{ ref('dim_team_name_lookup') }} h
        on h.name_lower = lower(regexp_replace(trim(oe.home_team), '^G[12] ', ''))
    left join {{ ref('dim_team_name_lookup') }} a
        on a.name_lower = lower(regexp_replace(trim(oe.away_team), '^G[12] ', ''))

),

all_events as (
    select * from parlay_resolved
    union all
    select * from odds_api_resolved
)

select
    source,
    event_id,
    game_date,
    home_team,
    away_team,
    home_team_id,
    away_team_id
from all_events
-- exactly one side unresolved → a real MLB matchup with an unmapped franchise
where (home_team_id is null) <> (away_team_id is null)

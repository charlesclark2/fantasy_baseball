-- stg_nfl_odds — flatten the raw Odds API NFL game-lines Delta table (NFL-N0.2).
--
-- The ONE JSON feed in NFL (the nflverse feeds are typed) — the raw event carries a nested
-- bookmakers[]→markets[]→outcomes[] array, unnested here to one row per (event, bookmaker,
-- market, outcome). h2h/spreads/totals across the 11 US books incl. Bovada (the target book —
-- reference_target_bookmaker). Point/price live on the outcome; commence_time cast at the
-- use-site (ISO string in raw_json — the INC-23 discipline). Mirrors stg_ncaaf_odds.
with raw as (
    select raw_json
    from {{ nfl_delta('odds_nfl') }}
),
events as (
    select
        json_extract_string(raw_json, '$.id')            as event_id,
        json_extract_string(raw_json, '$.sport_key')     as sport_key,
        json_extract_string(raw_json, '$.commence_time')::timestamp as commence_time,
        json_extract_string(raw_json, '$.home_team')     as home_team,
        json_extract_string(raw_json, '$.away_team')     as away_team,
        json_extract(raw_json, '$.bookmakers')           as bookmakers
    from raw
),
books as (
    select e.event_id, e.sport_key, e.commence_time, e.home_team, e.away_team,
           unnest(json_extract(e.bookmakers, '$[*]')) as bk
    from events e
    where e.bookmakers is not null
),
markets as (
    select b.event_id, b.sport_key, b.commence_time, b.home_team, b.away_team,
           json_extract_string(b.bk, '$.key')   as bookmaker,
           unnest(json_extract(b.bk, '$.markets[*]')) as mkt
    from books b
)
select
    'nfl'                                        as sport,
    m.event_id,
    m.sport_key,
    m.commence_time,
    m.home_team,
    m.away_team,
    m.bookmaker,
    json_extract_string(m.mkt, '$.key')          as market,
    json_extract_string(o.outcome, '$.name')     as outcome_name,
    json_extract_string(o.outcome, '$.price')::double as price,
    json_extract_string(o.outcome, '$.point')::double as point
from markets m,
     unnest(json_extract(m.mkt, '$.outcomes[*]')) as o(outcome)

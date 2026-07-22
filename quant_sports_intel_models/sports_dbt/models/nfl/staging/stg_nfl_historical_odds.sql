-- stg_nfl_historical_odds — flatten the paid Odds API historical CLOSING game lines (NFL-N1.0,
-- over N0.4's `odds_nfl_historical`, seasons 2020–2024, 25 books incl. Bovada).
--
-- The leakage-safe CLV benchmark: each raw event was captured at `_snapshot_ts` a few minutes
-- BEFORE `commence_time` (N0.4's pre-kickoff mechanic). This model unnests
-- bookmakers[]→markets[]→outcomes[] to one row per (event, snapshot, book, market, outcome) and
-- carries BOTH timestamps so mart_nfl_clv_game_lines can enforce `snapshot_ts < commence_time`
-- (belt-and-suspenders, per N0.4) and pick the true closing line.
--
-- ⭐ TEAM-NAME → CODE: the Odds feed keys on full names ("Kansas City Chiefs"); schedules/pbp use
-- codes. Normalized through stg_nfl_team_geo (the Washington rename folded here: both
-- "Washington Commanders" and "Washington Football Team" → the single geo row → WAS). Verified on
-- the real lake: 0 unmapped names, 1,424 distinct leakage-safe closing events.
--
-- ⚠️ Drops the `h2h_lay` market (a betting-exchange lay side, not a book price). commence_time and
-- the snapshot timestamps are ISO strings in raw_json → cast at the use-site (INC-23).
with raw as (
    select raw_json, season from {{ nfl_delta('odds_nfl_historical') }}
),
events as (
    select
        json_extract_string(raw_json, '$.id')                          as event_id,
        json_extract_string(raw_json, '$.sport_key')                   as sport_key,
        json_extract_string(raw_json, '$.commence_time')::timestamp    as commence_time,
        json_extract_string(raw_json, '$._snapshot_ts')::timestamp     as snapshot_ts,
        json_extract_string(raw_json, '$._requested_snapshot')::timestamp as requested_snapshot,
        -- fold the Washington rename so both historical names resolve to one geo row
        case when json_extract_string(raw_json, '$.home_team') = 'Washington Football Team'
             then 'Washington Commanders'
             else json_extract_string(raw_json, '$.home_team') end     as home_name,
        case when json_extract_string(raw_json, '$.away_team') = 'Washington Football Team'
             then 'Washington Commanders'
             else json_extract_string(raw_json, '$.away_team') end     as away_name,
        json_extract(raw_json, '$.bookmakers')                         as bookmakers,
        season
    from raw
),
books as (
    select e.*, unnest(json_extract(e.bookmakers, '$[*]')) as bk
    from events e
    where e.bookmakers is not null
),
markets as (
    select b.event_id, b.sport_key, b.commence_time, b.snapshot_ts, b.requested_snapshot,
           b.home_name, b.away_name, b.season,
           json_extract_string(b.bk, '$.key')             as bookmaker,
           unnest(json_extract(b.bk, '$.markets[*]'))     as mkt
    from books b
),
flat as (
    select
        m.event_id, m.sport_key, m.commence_time, m.snapshot_ts, m.requested_snapshot,
        m.home_name, m.away_name, m.season, m.bookmaker,
        json_extract_string(m.mkt, '$.key')               as market,
        json_extract_string(o.outcome, '$.name')          as outcome_name,
        json_extract_string(o.outcome, '$.price')::double as price,
        json_extract_string(o.outcome, '$.point')::double as point
    from markets m,
         unnest(json_extract(m.mkt, '$.outcomes[*]')) as o(outcome)
)
select
    'nfl'                                                 as sport,
    f.event_id,
    f.season,
    f.commence_time,
    f.snapshot_ts,
    f.requested_snapshot,
    (f.snapshot_ts < f.commence_time)                     as is_leakage_safe,
    f.home_name,
    f.away_name,
    hg.code                                               as home_team,
    ag.code                                               as away_team,
    f.bookmaker,
    f.market,
    f.outcome_name,
    f.price,
    f.point
from flat f
left join {{ ref('stg_nfl_team_geo') }} hg on hg.team_name = f.home_name
left join {{ ref('stg_nfl_team_geo') }} ag on ag.team_name = f.away_name
where f.market in ('h2h', 'spreads', 'totals')

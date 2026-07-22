-- stg_nfl_props_historical — flatten the paid Odds API historical CLOSING player props (NFL-N1.0,
-- over N0.4's `odds_nfl_props_historical`, seasons 2023–2024 — the vendor floor, 570 events).
--
-- Same leakage-safe closing mechanic as stg_nfl_historical_odds, at PLAYER-PROP grain: one row per
-- (event, book, market, player-outcome). The player is on the outcome's `description`; `name` is
-- the side (Over/Under/Yes/No). `point` is the prop line (yards / attempts / receptions);
-- anytime-TD has no point. Both timestamps carried so mart_nfl_clv_props can enforce
-- `snapshot_ts < commence_time` and take the closing line.
--
-- ⚠️ `_requested_snapshot` is not always present on props events → left NULL when absent. Player
-- names are NOT resolved to nflverse ids here (a later props-CLV story can xref on name+team);
-- home/away codes carried for game context. Timestamps ISO → cast at use-site (INC-23).
with raw as (
    select raw_json, season from {{ nfl_delta('odds_nfl_props_historical') }}
),
events as (
    select
        json_extract_string(raw_json, '$.id')                          as event_id,
        json_extract_string(raw_json, '$.commence_time')::timestamp    as commence_time,
        json_extract_string(raw_json, '$._snapshot_ts')::timestamp     as snapshot_ts,
        try_cast(json_extract_string(raw_json, '$._requested_snapshot') as timestamp) as requested_snapshot,
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
    select b.event_id, b.commence_time, b.snapshot_ts, b.requested_snapshot,
           b.home_name, b.away_name, b.season,
           json_extract_string(b.bk, '$.key')             as bookmaker,
           unnest(json_extract(b.bk, '$.markets[*]'))     as mkt
    from books b
),
flat as (
    select
        m.event_id, m.commence_time, m.snapshot_ts, m.requested_snapshot,
        m.home_name, m.away_name, m.season, m.bookmaker,
        json_extract_string(m.mkt, '$.key')               as market,
        json_extract_string(o.outcome, '$.name')          as outcome_side,
        json_extract_string(o.outcome, '$.description')   as player_name,
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
    hg.code                                               as home_team,
    ag.code                                               as away_team,
    f.bookmaker,
    f.market,
    f.player_name,
    f.outcome_side,
    f.price,
    f.point
from flat f
left join {{ ref('stg_nfl_team_geo') }} hg on hg.team_name = f.home_name
left join {{ ref('stg_nfl_team_geo') }} ag on ag.team_name = f.away_name

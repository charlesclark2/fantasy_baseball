-- stg_ncaaf_game_team_stats — flatten CFBD /games/teams (NCAAF-P1.1).
--
-- ONE row per (game_id, team_id) — the team-game BOX line. The raw record nests
-- `teams[] -> stats[]` as a long {category, stat} list where EVERY value is a STRING (CFBD
-- returns stats as text, incl. composites like "12-15" and "31:14"), so this model does two
-- things: EXPLODE the two arrays, then PIVOT the ~35 categories into typed columns.
--
-- Composite categories are SPLIT here (once, at the boundary) rather than left for every
-- downstream consumer to re-parse:
--   completionAttempts   "27-39" → completions / pass_attempts
--   thirdDownEff         "2-8"   → third_down_conversions / third_down_attempts
--   fourthDownEff        "1-2"   → fourth_down_conversions / fourth_down_attempts
--   totalPenaltiesYards  "5-45"  → penalties / penalty_yards
--   possessionTime       "31:14" → possession_seconds
--
-- The raw record has NO season field (a per-week pull) → `season` comes from the Delta partition;
-- `week` comes from the ingest's `_week` tag with the partition column as the fallback.
-- Materialized as a TABLE (the delta_scan-stacking cure — the N0.3 landmine).
{{ config(materialized='table') }}

{% set num = {
    'firstDowns': 'first_downs',
    'totalYards': 'total_yards',
    'netPassingYards': 'net_passing_yards',
    'rushingYards': 'rushing_yards',
    'rushingAttempts': 'rushing_attempts',
    'rushingTDs': 'rushing_tds',
    'passingTDs': 'passing_tds',
    'turnovers': 'turnovers',
    'fumblesLost': 'fumbles_lost',
    'totalFumbles': 'total_fumbles',
    'fumblesRecovered': 'fumbles_recovered',
    'passesIntercepted': 'passes_intercepted',
    'interceptions': 'interceptions_thrown',
    'interceptionYards': 'interception_return_yards',
    'interceptionTDs': 'interception_tds',
    'defensiveTDs': 'defensive_tds',
    'sacks': 'sacks',
    'tackles': 'tackles',
    'tacklesForLoss': 'tackles_for_loss',
    'qbHurries': 'qb_hurries',
    'passesDeflected': 'passes_deflected',
    'kickingPoints': 'kicking_points',
    'kickReturns': 'kick_returns',
    'kickReturnYards': 'kick_return_yards',
    'kickReturnTDs': 'kick_return_tds',
    'puntReturns': 'punt_returns',
    'puntReturnYards': 'punt_return_yards',
    'puntReturnTDs': 'punt_return_tds'
} %}
{% set rate = {
    'yardsPerPass': 'yards_per_pass',
    'yardsPerRushAttempt': 'yards_per_rush_attempt'
} %}

with raw as (
    select season, week as partition_week, raw_json
    from {{ ncaaf_delta('game_team_stats') }}
),

-- explode teams[] → one row per team-game, still carrying the nested stats list
team_rows as (
    select
        season,
        partition_week,
        json_extract_string(raw_json, '$.id')::bigint as game_id,
        try_cast(json_extract_string(raw_json, '$._week') as integer) as tagged_week,
        unnest(cast(json_extract(raw_json, '$.teams') as json[])) as team_json
    from raw
    where json_extract_string(raw_json, '$.id') is not null
),

-- explode stats[] → the long {category, stat} grain the pivot reads
kv as (
    select
        season,
        coalesce(tagged_week, partition_week)                       as week,
        game_id,
        json_extract_string(team_json, '$.teamId')::bigint          as team_id,
        json_extract_string(team_json, '$.team')                    as team,
        json_extract_string(team_json, '$.conference')              as conference,
        json_extract_string(team_json, '$.homeAway')                as home_away,
        try_cast(json_extract_string(team_json, '$.points') as integer) as points,
        json_extract_string(stat_json, '$.category')                as category,
        json_extract_string(stat_json, '$.stat')                    as stat
    from (
        select season, partition_week, tagged_week, game_id, team_json,
               unnest(cast(json_extract(team_json, '$.stats') as json[])) as stat_json
        from team_rows
    )
)

select
    'ncaaf'      as sport,
    season,
    week,
    game_id,
    team_id,
    team,
    conference,
    home_away,
    (home_away = 'home')                              as is_home,
    max(points)                                       as points,

    -- ── plain numeric categories ────────────────────────────────────────────────────────
    {%- for cat, col in num.items() %}
    max(case when category = '{{ cat }}' then try_cast(stat as double) end) as {{ col }},
    {%- endfor %}
    {%- for cat, col in rate.items() %}
    max(case when category = '{{ cat }}' then try_cast(stat as double) end) as {{ col }},
    {%- endfor %}

    -- ── composite categories, split ONCE at the boundary ────────────────────────────────
    max(case when category = 'completionAttempts'
             then try_cast(split_part(stat, '-', 1) as integer) end)  as completions,
    max(case when category = 'completionAttempts'
             then try_cast(split_part(stat, '-', 2) as integer) end)  as pass_attempts,
    max(case when category = 'thirdDownEff'
             then try_cast(split_part(stat, '-', 1) as integer) end)  as third_down_conversions,
    max(case when category = 'thirdDownEff'
             then try_cast(split_part(stat, '-', 2) as integer) end)  as third_down_attempts,
    max(case when category = 'fourthDownEff'
             then try_cast(split_part(stat, '-', 1) as integer) end)  as fourth_down_conversions,
    max(case when category = 'fourthDownEff'
             then try_cast(split_part(stat, '-', 2) as integer) end)  as fourth_down_attempts,
    max(case when category = 'totalPenaltiesYards'
             then try_cast(split_part(stat, '-', 1) as integer) end)  as penalties,
    max(case when category = 'totalPenaltiesYards'
             then try_cast(split_part(stat, '-', 2) as integer) end)  as penalty_yards,
    -- "MM:SS" of possession → seconds (a single comparable scalar)
    max(case when category = 'possessionTime'
             then try_cast(split_part(stat, ':', 1) as integer) * 60
                  + try_cast(split_part(stat, ':', 2) as integer) end) as possession_seconds

from kv
where team_id is not null
group by 1, 2, 3, 4, 5, 6, 7, 8, 9

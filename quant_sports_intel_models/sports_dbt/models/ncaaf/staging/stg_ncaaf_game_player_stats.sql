-- stg_ncaaf_game_player_stats — flatten CFBD /games/players (NCAAF-P1.1).
--
-- The raw record is FOUR levels deep: `teams[] -> categories[] -> types[] -> athletes[]`.
-- This model explodes all four into the LONG grain CFBD actually publishes:
--     one row per (game_id, player_id, category, stat_type)
-- e.g. (…, 'passing', 'YDS', '229') / (…, 'rushing', 'CAR', '16').
--
-- ⚠️ It stays LONG on purpose. The stat VOCABULARY differs per category (passing has C/ATT,
-- YDS, AVG, TD, INT; defensive has TOT, SOLO, SACKS, …) and CFBD adds types over time, so a
-- pivot here would silently drop any type not enumerated. `fact_player_game` does the pivot
-- for the modelled subset; anything else stays reachable from this long table.
--
-- Values are STRINGS (CFBD's wire format) and are kept as strings here — including composites
-- like passing C/ATT "27/39". The fact model casts/splits at the use-site.
--
-- ⚠️ /games/players carries NO teamId — only the team NAME — so the team key here is the name.
-- `dim_team` resolves (season, team-name) → team_id for anything that needs the id.
-- season comes from the Delta partition (no season in the record); week from the `_week` tag.
-- Materialized as a TABLE (the delta_scan-stacking cure — the N0.3 landmine).
--
-- 🧯 MEMORY: this is the one genuinely EXPLOSIVE model in the DAG — four chained UNNESTs turn
-- ~13.8k game records into ~5.2M rows, and the intermediate levels each carry a JSON string.
-- On the profile default (4 GB / 4 DuckDB threads) it OOMs: every parallel thread holds its own
-- copy of the intermediate. Single-threaded + no insertion-order preservation it completes in
-- ~40s well inside 4 GB, so both are pinned here and RESTORED afterwards (they are connection-
-- global in dbt-duckdb, and leaving them set would silently de-parallelize every later model).
-- ⚠️ If you raise the box's SPORTS_DUCKDB_MEMORY, do NOT drop these — the amplification scales
-- with seasons ingested, so the headroom is temporary but the pin is not.
{{ config(
    materialized='table',
    pre_hook=[
        "SET preserve_insertion_order = false",
        "SET threads = 1"
    ],
    post_hook=[
        "SET preserve_insertion_order = true",
        "SET threads = " ~ env_var('SPORTS_DUCKDB_THREADS', '4')
    ]
) }}

with raw as (
    select season, week as partition_week, raw_json
    from {{ ncaaf_delta('game_player_stats') }}
),

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

category_rows as (
    select
        season, partition_week, tagged_week, game_id,
        json_extract_string(team_json, '$.team')       as team,
        json_extract_string(team_json, '$.conference') as conference,
        json_extract_string(team_json, '$.homeAway')   as home_away,
        unnest(cast(json_extract(team_json, '$.categories') as json[])) as category_json
    from team_rows
),

type_rows as (
    select
        season, partition_week, tagged_week, game_id, team, conference, home_away,
        json_extract_string(category_json, '$.name') as category,
        unnest(cast(json_extract(category_json, '$.types') as json[])) as type_json
    from category_rows
),

athlete_rows as (
    select
        season, partition_week, tagged_week, game_id, team, conference, home_away, category,
        json_extract_string(type_json, '$.name') as stat_type,
        unnest(cast(json_extract(type_json, '$.athletes') as json[])) as athlete_json
    from type_rows
)

select
    'ncaaf'                                              as sport,
    season,
    coalesce(tagged_week, partition_week)                as week,
    game_id,
    team,
    conference,
    home_away,
    (home_away = 'home')                                 as is_home,
    json_extract_string(athlete_json, '$.id')            as player_id,
    json_extract_string(athlete_json, '$.name')          as player_name,
    category,
    stat_type,
    json_extract_string(athlete_json, '$.stat')          as stat
from athlete_rows
where json_extract_string(athlete_json, '$.id') is not null

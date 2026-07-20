-- stg_ncaaf_game_advanced — flatten CFBD /stats/game/advanced (NCAAF-P1.1).
--
-- ONE row per (game_id, team) — CFBD's own PBP-derived advanced box, offense AND defense, with
-- the down-split (standardDowns / passingDowns) and run-game (lineYards / secondLevelYards /
-- openFieldYards / powerSuccess / stuffRate) blocks. This is the modelling grain the inventory
-- calls out (§2.3) and the primary input to the opponent-adjusted efficiency rollup.
--
-- ⚠️ `defense.*` on a row is what THIS team's DEFENSE allowed (not the opponent's offense row) —
-- CFBD emits both sides on each team's record. Column names keep the off_/def_ prefix so the
-- perspective can never be misread downstream.
--
-- Unlike the box/PBP tables this record DOES carry its own season/week/team → no partition
-- fallback needed. Materialized as a TABLE (the delta_scan-stacking cure — the N0.3 landmine).
{{ config(materialized='table') }}

{% set side_cols = {
    'plays': 'plays',
    'drives': 'drives',
    'ppa': 'ppa',
    'totalPPA': 'total_ppa',
    'successRate': 'success_rate',
    'explosiveness': 'explosiveness',
    'powerSuccess': 'power_success',
    'stuffRate': 'stuff_rate',
    'lineYards': 'line_yards',
    'secondLevelYards': 'second_level_yards',
    'openFieldYards': 'open_field_yards'
} %}
{% set split_blocks = {
    'standardDowns': 'standard_downs',
    'passingDowns': 'passing_downs',
    'rushingPlays': 'rushing_plays',
    'passingPlays': 'passing_plays'
} %}
{% set split_metrics = {'ppa': 'ppa', 'successRate': 'success_rate', 'explosiveness': 'explosiveness'} %}

-- ⚙️ The offense/defense OBJECTS are extracted ONCE per row here. Reaching into the full
-- document ~100× with `$.offense.standardDowns.ppa`-style paths re-parses the whole JSON on
-- every column and OOM'd a 4 GB DuckDB on this table; pulling the two sub-objects first makes
-- each of the ~46 scalar reads parse a tiny object instead.
with raw as (
    select raw_json
    from {{ ncaaf_delta('game_advanced') }}
    where json_extract_string(raw_json, '$.gameId') is not null
      and json_extract_string(raw_json, '$.team') is not null
),

sides as (
    select
        try_cast(json_extract_string(raw_json, '$.season') as integer) as season,
        try_cast(json_extract_string(raw_json, '$.week')   as integer) as week,
        json_extract_string(raw_json, '$.seasonType')                  as season_type,
        json_extract_string(raw_json, '$.gameId')::bigint              as game_id,
        json_extract_string(raw_json, '$.team')                        as team,
        json_extract_string(raw_json, '$.opponent')                    as opponent,
        json_extract(raw_json, '$.offense')                            as offense,
        json_extract(raw_json, '$.defense')                            as defense
    from raw
)

select
    'ncaaf'      as sport,
    season,
    week,
    season_type,
    game_id,
    team,
    opponent,

    -- ── the team's OFFENSE, then what its DEFENSE allowed ───────────────────────────────
    {%- for side, prefix in [('offense', 'off'), ('defense', 'def')] %}
    {%- for key, col in side_cols.items() %}
    try_cast(json_extract_string({{ side }}, '$.{{ key }}') as double) as {{ prefix }}_{{ col }},
    {%- endfor %}
    {%- for block, block_col in split_blocks.items() %}
    {%- for key, col in split_metrics.items() %}
    try_cast(json_extract_string({{ side }}, '$.{{ block }}.{{ key }}') as double)
        as {{ prefix }}_{{ block_col }}_{{ col }},
    {%- endfor %}
    {%- endfor %}
    {%- endfor %}

    -- the run-game TOTALS (levels, not per-carry rates — kept for weighting a rollup)
    try_cast(json_extract_string(offense, '$.lineYardsTotal')        as double) as off_line_yards_total,
    try_cast(json_extract_string(offense, '$.secondLevelYardsTotal') as double) as off_second_level_yards_total,
    try_cast(json_extract_string(offense, '$.openFieldYardsTotal')   as double) as off_open_field_yards_total,
    try_cast(json_extract_string(defense, '$.lineYardsTotal')        as double) as def_line_yards_total,
    try_cast(json_extract_string(defense, '$.secondLevelYardsTotal') as double) as def_second_level_yards_total,
    try_cast(json_extract_string(defense, '$.openFieldYardsTotal')   as double) as def_open_field_yards_total
from sides

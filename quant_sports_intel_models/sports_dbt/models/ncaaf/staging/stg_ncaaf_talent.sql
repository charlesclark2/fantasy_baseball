-- stg_ncaaf_talent — flatten CFBD /talent (NCAAF-P0.4).
--
-- The 247Sports team TALENT composite (roster-recruiting-rating rollup) per (season, team) —
-- a level indicator of accumulated roster talent, complementary to the FLUX signals (portal /
-- returning production). Computed from recruiting rankings ⇒ known pre-season (leakage-safe).
-- CFBD coverage starts 2015; some early seasons include non-FBS teams (the mart's returning-
-- production spine keeps the universe FBS). `season` is the Delta partition (== $.year).
-- Sport-tagged. Materialized as a TABLE (the delta_scan-stacking cure).
{{ config(materialized='table') }}
with raw as (
    select season, raw_json
    from {{ ncaaf_delta('talent') }}
)
select
    'ncaaf'                                          as sport,
    season                                           as season,
    json_extract_string(raw_json, '$.team')          as team,
    try_cast(json_extract_string(raw_json, '$.talent') as double) as team_talent
from raw
where json_extract_string(raw_json, '$.team') is not null

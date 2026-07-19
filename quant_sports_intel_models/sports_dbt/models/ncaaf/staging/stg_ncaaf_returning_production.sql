-- stg_ncaaf_returning_production — flatten CFBD /player/returning (NCAAF-P0.4).
--
-- CFBD's canonical RETURNING-PRODUCTION metric (Bill Connelly's returning production): for
-- each FBS team, the share of the prior season's PPA/usage carried by players who RETURN for
-- `season`. One row per (season, team). This is the production-weighted roster-continuity
-- signal, ready-made (percent_ppa = the headline "returning production %").
--
-- ⭐ Leakage-safe: computed pre-season (which players return is known before week 1) — a valid
--   as-of-preseason feature for `season`. Sport-tagged. `season` is the Delta partition column
--   (the writer stamps it), used in preference to $.season so it can't drift.
--
-- Materialized as a TABLE (not the staging-default view): the P0.4 mart stacks this with 3
-- other Delta sources + a self-join, and DuckDB's delta extension cannot serialize a plan
-- containing multiple delta_scan operators ("DeltaScan serialization not implemented" — the
-- N0.3 landmine). A physical table reads the Delta once so the mart plan holds no delta_scan.
{{ config(materialized='table') }}
with raw as (
    select season, raw_json
    from {{ ncaaf_delta('returning_production') }}
)
select
    'ncaaf'                                                     as sport,
    season                                                     as season,
    json_extract_string(raw_json, '$.team')                    as team,
    json_extract_string(raw_json, '$.conference')              as conference,
    try_cast(json_extract_string(raw_json, '$.totalPPA')            as double) as returning_ppa_total,
    try_cast(json_extract_string(raw_json, '$.totalPassingPPA')     as double) as returning_pass_ppa_total,
    try_cast(json_extract_string(raw_json, '$.totalReceivingPPA')   as double) as returning_rec_ppa_total,
    try_cast(json_extract_string(raw_json, '$.totalRushingPPA')     as double) as returning_rush_ppa_total,
    -- the headline returning-production shares (0-1); percent_ppa is THE roster-continuity %.
    try_cast(json_extract_string(raw_json, '$.percentPPA')          as double) as returning_ppa_pct,
    try_cast(json_extract_string(raw_json, '$.percentPassingPPA')   as double) as returning_pass_ppa_pct,
    try_cast(json_extract_string(raw_json, '$.percentReceivingPPA') as double) as returning_rec_ppa_pct,
    try_cast(json_extract_string(raw_json, '$.percentRushingPPA')   as double) as returning_rush_ppa_pct,
    try_cast(json_extract_string(raw_json, '$.usage')              as double) as returning_usage,
    try_cast(json_extract_string(raw_json, '$.passingUsage')       as double) as returning_pass_usage,
    try_cast(json_extract_string(raw_json, '$.receivingUsage')     as double) as returning_rec_usage,
    try_cast(json_extract_string(raw_json, '$.rushingUsage')       as double) as returning_rush_usage
from raw
where json_extract_string(raw_json, '$.team') is not null

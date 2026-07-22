-- stg_ncaaf_recruiting_players — flatten CFBD /recruiting/players (NCAAF-P1.2b).
--
-- One row per recruit per recruiting class (CFBD recruiting-record `id` = the stable key,
-- and the ONE that bridges into the college universe via roster.recruitIds — see
-- stg_ncaaf_roster). `year` is the RECRUITING CLASS year (the class that signed), which is
-- the recruit's expected college-arrival season. `rating` is the 247Sports COMPOSITE on a
-- 0–1 scale (0.9998 = a generational 5-star); `stars` is the 1–5 bucket; `ranking` is the
-- national rank within the class. `committed_to` is the COLLEGE the recruit signed with
-- (NOT the high school — `school` is the HS). Covers HighSchool / JUCO / PrepSchool recruits;
-- `recruit_type` is carried so a downstream model can restrict to HighSchool if it wants a
-- clean HS→college signal. CFBD coverage 2000+; the usable window is bounded by the PRODUCTION
-- floor (player-advanced starts 2014), not by recruiting.
--
-- Recruiting is a pre-signing quantity, known long before a snap is ever played ⇒ inherently
-- leakage-safe as a feature. `season` is the Delta partition (== $.year). Sport-tagged.
-- Materialized as a TABLE (the delta_scan-stacking cure inherited from P1.1).
{{ config(materialized='table') }}
with raw as (
    select season, raw_json
    from {{ ncaaf_delta('recruiting_players') }}
)
select
    'ncaaf'                                                    as sport,
    season                                                    as season,          -- Delta partition == recruiting class year
    json_extract_string(raw_json, '$.id')                     as recruit_id,       -- ⭐ the bridge key (↔ roster.recruit_ids)
    json_extract_string(raw_json, '$.athleteId')              as athlete_id,       -- ESPN-style; DOES NOT match roster (kept for reference only)
    try_cast(json_extract_string(raw_json, '$.year') as int)  as class_year,
    json_extract_string(raw_json, '$.recruitType')            as recruit_type,     -- HighSchool / JUCO / PrepSchool
    json_extract_string(raw_json, '$.name')                   as recruit_name,
    json_extract_string(raw_json, '$.committedTo')            as committed_to,     -- ⚠️ the COLLEGE, not the HS
    json_extract_string(raw_json, '$.school')                 as high_school,
    json_extract_string(raw_json, '$.position')               as recruit_position,
    try_cast(json_extract_string(raw_json, '$.stars') as int)    as stars,
    try_cast(json_extract_string(raw_json, '$.rating') as double) as composite_rating,  -- 247 composite, 0–1
    try_cast(json_extract_string(raw_json, '$.ranking') as int)   as national_ranking,
    try_cast(json_extract_string(raw_json, '$.height') as double) as height_in,
    try_cast(json_extract_string(raw_json, '$.weight') as double) as weight_lb
from raw
where json_extract_string(raw_json, '$.id') is not null

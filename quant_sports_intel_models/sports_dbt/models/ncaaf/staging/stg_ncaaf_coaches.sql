-- stg_ncaaf_coaches — flatten CFBD /coaches (NCAAF-P0.5).
--
-- CFBD's head-coach history: one API record per coach, carrying a `seasons` array of that
-- coach's per-year rows (school, year, wins/losses, srs, and the ⭐ SP+ splits
-- spOverall/spOffense/spDefense). We EXPLODE the array to a flat coach-school-season grain —
-- one row per (coach, team, season) — which is what the P0.5 mart windows over to derive
-- HC-change flags + tenure + each coach's PRIOR-season SP+ track record.
--
-- The ingest pulls /coaches YEAR-ONLY (1 call/season), so within a single `season` Delta
-- partition every coach's array holds only that season's row(s); reading ALL partitions (a
-- plain delta_scan of the whole table) reconstructs the full coach-school-year grid, so a
-- coach's prior-season SP+ (from earlier partitions) is available to the mart. `season` here
-- is taken from the SEASON ROW itself ($.year), not the partition, so the grain is authoritative.
--
-- ⚠️ SP+/wins/losses on a row are that SEASON's OUTCOME (post-season) — the mart treats them as
--   leakage-safe ONLY when read from a STRICTLY-PRIOR season (year < the target season). The
--   current-season row is used solely to identify WHO the coach is (a hire is known pre-season).
--
-- Materialized as a TABLE (not the staging-default view): the mart joins this to
-- stg_ncaaf_returning_production, and DuckDB's delta extension cannot serialize a plan holding
-- multiple delta_scan operators ("DeltaScan serialization not implemented" — the N0.3 landmine).
-- A physical table reads the Delta once so the mart plan contains no delta_scan.
{{ config(materialized='table') }}

with raw as (
    select raw_json
    from {{ ncaaf_delta('coaches') }}
),

-- explode the per-coach `seasons` array → one row per coach-season (robust to a coach who
-- appears at >1 school in a year, e.g. a mid-season move: each such row is emitted separately)
exploded as (
    select
        raw_json,
        unnest(cast(json_extract(raw_json, '$.seasons') as json[])) as season_json
    from raw
)

select
    'ncaaf'                                                           as sport,
    -- the authoritative grain year is the SEASON ROW's year (== the partition for a year-only
    -- pull; taken from the row so it can't drift if a partition ever holds a multi-year array)
    try_cast(json_extract_string(season_json, '$.year')  as integer) as season,
    json_extract_string(season_json, '$.school')                     as team,
    -- coach identity: no coach id is exposed by CFBD → the (first,last) NAME is the only stable
    -- cross-school/-season key (a coach's track record follows the person, not the school)
    trim(coalesce(json_extract_string(raw_json, '$.firstName'), '') || ' ' ||
         coalesce(json_extract_string(raw_json, '$.lastName'),  '')) as coach_name,
    json_extract_string(raw_json, '$.firstName')                     as coach_first,
    json_extract_string(raw_json, '$.lastName')                      as coach_last,
    json_extract_string(raw_json, '$.hireDate')                      as hire_date,
    -- this-season identity/context columns (games disambiguates the coach-of-record in a
    -- mid-season-change cell; the mart NEVER exposes current-season sp_*/wins as a feature)
    try_cast(json_extract_string(season_json, '$.games')     as integer) as games,
    try_cast(json_extract_string(season_json, '$.wins')      as integer) as wins,
    try_cast(json_extract_string(season_json, '$.losses')    as integer) as losses,
    try_cast(json_extract_string(season_json, '$.srs')       as double)  as srs,
    -- ⭐ the SP+ splits — the coach's per-year performance profile (read PRIOR-only in the mart)
    try_cast(json_extract_string(season_json, '$.spOverall') as double)  as sp_overall,
    try_cast(json_extract_string(season_json, '$.spOffense') as double)  as sp_offense,
    try_cast(json_extract_string(season_json, '$.spDefense') as double)  as sp_defense
from exploded
where json_extract_string(season_json, '$.school') is not null
  and try_cast(json_extract_string(season_json, '$.year') as integer) is not null

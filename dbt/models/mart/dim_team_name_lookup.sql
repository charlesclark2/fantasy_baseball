-- =============================================================================
-- dim_team_name_lookup.sql
-- Grain: one row per distinct team-name variant (lowercased).
-- Purpose: Epic A1.9 — the single canonical resolver from ANY feed team-name
--          variant to team_id + canonical abbrev/name. Replaces the per-site
--          inline CASE / _normalize_team_name band-aids that kept silently
--          dropping odds for relocated/renamed franchises (the Athletics:
--          "Athletics" in Stats API vs "Oakland Athletics" in the odds feeds).
--
-- Resolves: the Stats API canonical names (from ref_teams) + every known
--           odds-feed display variant (from the ref_team_aliases seed).
--
-- CONSUMER CONTRACT — normalize the input name the SAME way before joining:
--     lower(regexp_replace(trim(<feed_name>), '^G[12] ', ''))
--   The '^G[12] ' strip removes the Parlay feed's doubleheader marker
--   ("G1 Baltimore Orioles" → "Baltimore Orioles"). Non-MLB rows (college,
--   Mexican league, prop markets) intentionally do NOT resolve — they have no
--   team_id and should not join to an MLB game.
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model. DuckDB branch reads the ref_teams +
-- ref_team_aliases seeds (registered as DuckDB views over their S3 parquet by
-- run_w1_lakehouse.py); Snowflake branch is a thin view over the lakehouse_ext
-- external table. mart_game_spine reads this resolver for scheduled-game
-- abbreviation normalization, so it is built/registered before the spine.

{{ config(materialized='view', tags=['w5_lakehouse']) }}

{% if target.name == 'duckdb' %}

with team_dim as (
    -- One canonical row per team_id. ref_teams carries a legacy + an active row
    -- for relocated franchises (e.g. OAK + ATH share team_id 13); both share the
    -- same canonical_abbrev and team_name, so max() collapses them safely.
    select
        team_id,
        max(canonical_abbrev) as canonical_abbrev,
        max(team_name)        as canonical_name
    from ref_teams
    group by team_id
),

canonical_names as (
    -- The Stats API canonical name resolves to itself.
    select distinct
        lower(team_name) as name_lower,
        team_id
    from ref_teams
),

alias_names as (
    -- Odds-feed display variants (Oakland Athletics, Cleveland Indians, …).
    select
        lower(alias_name) as name_lower,
        team_id
    from ref_team_aliases
),

all_names as (
    select name_lower, team_id from canonical_names
    union
    select name_lower, team_id from alias_names
)

select
    n.name_lower,
    n.team_id,
    d.canonical_abbrev,
    d.canonical_name
from all_names n
join team_dim d on d.team_id = n.team_id

{% else %}

select * from baseball_data.lakehouse_ext.dim_team_name_lookup

{% endif %}

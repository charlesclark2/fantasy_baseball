-- dim_ncaaf_team — the team dimension, SCD-2 over the attributes that DRIFT (NCAAF-P1.1).
--
-- ⭐ WHY SCD-2 (the scd2_convention.md pattern, season-grained): conference realignment is the
-- single most consequential attribute drift in this sport — Texas/Oklahoma Big 12→SEC, the entire
-- Pac-12 diaspora, UCF/Cincinnati/Houston/BYU. A type-1 dimension carrying only "today's"
-- conference would retroactively rewrite history: a 2021 Texas game would report as an SEC game,
-- silently corrupting every conference-strength feature and every "vs Power-4" split ever
-- computed from it. So the drifting attributes are VERSIONED.
--
-- GRAIN: one row per (team_id, contiguous run of seasons with an identical payload).
--   payload = (team name, conference, conference_division, classification)
--   validity = [valid_from_season, valid_to_season] INCLUSIVE, season-grained
--   is_current = the run that includes the newest ingested season
--
-- ⚠️ SEASON-GRAINED, not timestamp-grained — a deliberate departure from MLB's
-- `valid_from`/`valid_to` TIMESTAMP columns. The source (CFBD /teams/fbs) is a once-a-season
-- snapshot: there is no intra-season "as of 3pm" truth to represent, and faking timestamps would
-- imply a precision the data does not have. `record_hash` + the change-detection rule are the
-- convention's, unchanged.
--
-- ⭐ POINT-IN-TIME LOOKUP — this is how every downstream model resolves a team:
--     join dim_ncaaf_team d
--       on d.team = f.team                       -- or d.team_id = f.team_id
--      and f.season between d.valid_from_season
--                       and coalesce(d.valid_to_season, 9999)
--   Because the team NAME is in the payload, a rename opens a new row too, which makes
--   (season, team-name) a sound key for the CFBD sources that carry no teamId (e.g.
--   /games/players, /drives, /plays — all name-keyed).
--
-- ⭐ FBS-filtered by construction: the source is /teams/fbs, so every row is FBS. Non-FBS
-- opponents appear in the fact tables as names with no dim row — that is the intended signal,
-- and `is_fbs_matchup` on dim_ncaaf_game is what the modelling universe filters on.
{{ config(materialized='table') }}

with src as (
    select * from {{ ref('stg_ncaaf_teams') }}
),

max_season as (
    select max(season) as max_season from src
),

-- ── the SCD-2 payload + its hash (scd2_convention.md formula: MD5 over payload cols,
--    NULL → '' so a NULL→non-NULL flip is always detected) ─────────────────────────────────
hashed as (
    select
        *,
        md5(concat_ws('|',
            coalesce(team, ''),
            coalesce(conference, ''),
            coalesce(conference_division, ''),
            coalesce(classification, '')
        )) as record_hash
    from src
),

-- ── change detection: a row STARTS a new version when its hash differs from the prior
--    season's, or when the team reappears after a gap (left FBS and came back) ─────────────
marked as (
    select
        *,
        lag(record_hash) over (partition by team_id order by season) as prev_hash,
        lag(season)      over (partition by team_id order by season) as prev_season
    from hashed
),

versioned as (
    select
        *,
        sum(case
                when prev_hash is null then 1              -- first observation
                when record_hash <> prev_hash then 1       -- payload changed
                when season <> prev_season + 1 then 1      -- non-contiguous (gap) → new version
                else 0
            end) over (partition by team_id order by season
                       rows between unbounded preceding and current row) as version_number
    from marked
),

-- ── collapse each contiguous run to ONE row ────────────────────────────────────────────────
runs as (
    select
        team_id,
        version_number,
        min(season) as valid_from_season,
        max(season) as valid_to_season_inclusive,
        any_value(record_hash) as record_hash,
        -- payload (constant within a run by construction)
        any_value(team)                as team,
        any_value(conference)          as conference,
        any_value(conference_division) as conference_division,
        any_value(classification)      as classification,
        -- the run's LAST-season non-payload attributes (venue can be renovated/relocated
        -- without opening a new version — it is descriptive, not a modelling key)
        max(season)                    as attrs_season
    from versioned
    group by 1, 2
),

attrs as (
    select
        v.team_id, v.season,
        v.mascot, v.abbreviation,
        v.venue_name, v.venue_city, v.venue_state, v.venue_timezone,
        v.venue_latitude, v.venue_longitude, v.venue_elevation_m, v.venue_capacity,
        v.venue_is_dome, v.venue_is_grass
    from versioned v
)

select
    'ncaaf'                                                   as sport,
    r.team_id,
    r.version_number,
    -- the surrogate key for this VERSION of the team (join target for a versioned fact)
    'ncaaf-' || r.team_id || '-v' || r.version_number         as team_surrogate_key,
    r.team,
    r.conference,
    r.conference_division,
    r.classification,
    (r.classification = 'fbs')                                as is_fbs,

    -- ── SCD-2 validity (season-grained, INCLUSIVE) ─────────────────────────────────────
    r.valid_from_season,
    -- open-ended for the run that reaches the newest ingested season (the convention's
    -- valid_to IS NULL ⇔ is_current TRUE)
    case when r.valid_to_season_inclusive = m.max_season
         then null else r.valid_to_season_inclusive end       as valid_to_season,
    (r.valid_to_season_inclusive = m.max_season)              as is_current,
    r.record_hash,
    (r.valid_to_season_inclusive - r.valid_from_season + 1)   as seasons_in_version,

    -- ── descriptive (non-payload) attributes, as of the run's last season ──────────────
    a.mascot,
    a.abbreviation,
    a.venue_name,
    a.venue_city,
    a.venue_state,
    a.venue_timezone,
    a.venue_latitude,
    a.venue_longitude,
    a.venue_elevation_m,
    a.venue_capacity,
    a.venue_is_dome,
    a.venue_is_grass
from runs r
cross join max_season m
left join attrs a
    on a.team_id = r.team_id and a.season = r.attrs_season

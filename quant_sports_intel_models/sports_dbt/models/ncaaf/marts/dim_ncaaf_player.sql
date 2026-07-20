-- dim_ncaaf_player — the player dimension, SCD-2 over the attributes that DRIFT (NCAAF-P1.1).
--
-- ⭐ WHY SCD-2: in college football the roster IS the drift. A player's team changes (the
-- transfer portal moved 4,499 players in 2025 alone), their position changes, their class year
-- advances every season. A type-1 "current team" dimension would attribute a player's 2023
-- production at his old school to his new one — the exact silent-wrong the portal era makes
-- routine. So team + position are VERSIONED, season-grained, same convention as
-- dim_ncaaf_team (see that model's header for why season- and not timestamp-grained).
--
-- GRAIN: one row per (player_id, contiguous run of seasons with an identical payload).
--   payload = (team, position)  →  a transfer or a position switch opens a new row
--
-- ⚠️ `class_year` is deliberately NOT in the payload. It advances every season by construction,
-- so hashing it would open a new version for a player who did nothing but come back — measured
-- on the real lake, 20,672 of 30,433 version breaks were class-year-only vs 9,761 genuine
-- team/position changes, i.e. 2:1 noise burying the signal. A "version" here means A REAL ROSTER
-- CHANGE. Class year is carried descriptively as the run's first/last observed value instead.
--
-- ⭐ POINT-IN-TIME LOOKUP (the ONLY correct way to resolve a player-season):
--     join dim_ncaaf_player d
--       on d.player_id = f.player_id
--      and f.season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
--
-- ⭐ FBS-FILTERED: CFBD /roster returns ~30k players across ALL divisions. A player is kept only
-- for the seasons in which his team was an FBS member (resolved through dim_ncaaf_team's SCD-2
-- range — NOT through today's membership, or a 2016 Big-12 season would be judged by 2025's map).
-- A player who moves FCS→FBS therefore appears from the FBS season onward, which is exactly the
-- window in which his production is observable in our fact tables.
--
-- Roster is a PRE-SEASON snapshot ⇒ every attribute here is leakage-safe for that season.
{{ config(materialized='table') }}

with roster as (
    select * from {{ ref('stg_ncaaf_roster') }}
),

teams as (
    select * from {{ ref('dim_ncaaf_team') }}
),

-- ⭐ the FBS restriction, resolved AS-OF each season through the team dimension's SCD-2 range
fbs_roster as (
    select
        r.sport,
        r.season,
        r.player_id,
        r.team,
        t.team_id,
        t.conference,
        r.position,
        r.class_year,
        r.first_name,
        r.last_name
    from roster r
    join teams t
      on t.team = r.team
     and r.season between t.valid_from_season and coalesce(t.valid_to_season, 9999)
     and t.is_fbs
),

-- a player can appear only once per season; if CFBD ever emits a dup, keep one deterministically
deduped as (
    select * from (
        select *, row_number() over (
            partition by player_id, season order by team, position
        ) as rn
        from fbs_roster
    )
    where rn = 1
),

max_season as (
    select max(season) as max_season from deduped
),

hashed as (
    select
        *,
        md5(concat_ws('|',
            coalesce(team, ''),
            coalesce(position, '')
        )) as record_hash
    from deduped
),

marked as (
    select
        *,
        lag(record_hash) over (partition by player_id order by season) as prev_hash,
        lag(season)      over (partition by player_id order by season) as prev_season
    from hashed
),

versioned as (
    select
        *,
        sum(case
                when prev_hash is null then 1              -- first observation
                when record_hash <> prev_hash then 1       -- transfer / position change
                when season <> prev_season + 1 then 1      -- gap (redshirt, injury, absence)
                else 0
            end) over (partition by player_id order by season
                       rows between unbounded preceding and current row) as version_number
    from marked
),

runs as (
    select
        player_id,
        version_number,
        min(season)                as valid_from_season,
        max(season)                as valid_to_season_inclusive,
        any_value(record_hash)     as record_hash,
        any_value(team)            as team,
        any_value(team_id)         as team_id,
        any_value(conference)      as conference,
        any_value(position)        as position,
        -- class year is descriptive, not payload (see header) → carry the run's span
        min(class_year)            as class_year_first,
        max(class_year)            as class_year_last,
        any_value(first_name)      as first_name,
        any_value(last_name)       as last_name
    from versioned
    group by 1, 2
),

-- career-level context (constant across a player's versions — handy for cohort filters)
career as (
    select
        player_id,
        min(season)                as first_fbs_season,
        max(season)                as last_fbs_season,
        count(distinct season)     as fbs_seasons,
        count(distinct team)       as n_teams
    from deduped
    group by 1
)

select
    'ncaaf'                                                     as sport,
    r.player_id,
    r.version_number,
    'ncaaf-' || r.player_id || '-v' || r.version_number         as player_surrogate_key,
    trim(coalesce(r.first_name, '') || ' ' || coalesce(r.last_name, '')) as player_name,
    r.first_name,
    r.last_name,
    r.team,
    r.team_id,
    r.conference,
    r.position,
    r.class_year_first,
    r.class_year_last,

    -- ── SCD-2 validity (season-grained, INCLUSIVE) ─────────────────────────────────────
    r.valid_from_season,
    case when r.valid_to_season_inclusive = m.max_season
         then null else r.valid_to_season_inclusive end         as valid_to_season,
    (r.valid_to_season_inclusive = m.max_season)                as is_current,
    r.record_hash,
    (r.valid_to_season_inclusive - r.valid_from_season + 1)     as seasons_in_version,
    -- version 2+ means the payload changed at least once; a team change is the interesting case
    (r.version_number > 1)                                      as is_post_change_version,

    -- ── career context ────────────────────────────────────────────────────────────────
    c.first_fbs_season,
    c.last_fbs_season,
    c.fbs_seasons,
    c.n_teams,
    (c.n_teams > 1)                                             as is_transfer_career
from runs r
cross join max_season m
join career c on c.player_id = r.player_id

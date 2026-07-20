-- dim_ncaaf_game — the game dimension (NCAAF-P1.1).
--
-- ONE row per game_id — the conformed spine every fact in this layer hangs off (fact_ncaaf_*
-- all filter their universe through this model's `is_fbs_matchup`).
--
-- ⭐ FBS FILTER (the P0.2 flag this story absorbs): CFBD /games lands ALL divisions — a season
-- carries ~3,800 games including FCS/D-II/NAIA opponents, versus ~800 FBS-vs-FBS. This dimension
-- keeps EVERY game (an FBS team's cupcake game is real and its result counts) but classifies it
-- three ways so nothing downstream has to re-derive the universe:
--     is_fbs_matchup  — BOTH sides FBS. The modelling universe. This is what facts filter on.
--     is_fbs_involved — at least one side FBS. The right universe for a TEAM's season record.
--     neither         — pure non-FBS. Never modelled; retained so counts reconcile to the lake.
--
-- ⚠️ OUTCOME COLUMNS ARE POST-KICKOFF. home_points/away_points/margin/winner/is_upset describe
-- what HAPPENED. They are correct on this dimension (a game dimension legitimately carries its
-- own result) but they are NEVER to be folded into a pregame feature row — the as-of-week
-- rollups only read them for games with week < the as-of week. `is_completed` marks a game whose
-- outcome is real; a scheduled-but-unplayed game has NULL points and must not be treated as 0-0.
--
-- `start_date` is cast ::timestamp here from the raw ISO string (INC-23: raw stays VARCHAR, the
-- reader casts) — staging already did the cast, so this model consumes it typed.
{{ config(materialized='table') }}

-- 🚨 `week` IS NOT A SEASON ORDERING — postseason RESTARTS AT 1.
-- CFBD numbers the regular season 1..15/16 and then numbers the postseason 1 as well: every bowl
-- and every CFP game in a season carries week = 1, played in DECEMBER/JANUARY. Ordering or
-- filtering a season by raw `week` therefore places the national-championship game BEFORE
-- regular-season week 2. Measured on the real lake, 2024 Ohio State had FIVE games at `week <= 1`
-- (its opener plus four playoff games), and every as-of-week rollup row from week 2 onward was
-- silently absorbing them — a textbook post-kickoff leak that no `week < W` filter can catch,
-- because the filter was right and the ORDERING was wrong.
--
-- ⭐ `season_order_week` is the fix and the ONLY column that may be used to order or window a
-- season: regular-season weeks keep their number, postseason weeks are offset past the last
-- regular-season week of that same season. It is monotone in game_date by construction.
-- `week` is retained as the CFBD-native value for reporting/joins — never for ordering.
with games as (
    select * from {{ ref('stg_ncaaf_games') }}
),

-- the last regular-season week actually played in each season (2020 was short; it varies)
season_bounds as (
    select season, max(week) as max_regular_week
    from games
    where season_type = 'regular'
    group by 1
),

home_dim as (
    select team_id, team, conference, venue_name, venue_city, venue_state, venue_timezone,
           venue_elevation_m, venue_is_dome, venue_is_grass, venue_capacity,
           valid_from_season, valid_to_season
    from {{ ref('dim_ncaaf_team') }}
)

select
    'ncaaf'                                          as sport,
    g.game_id,
    'ncaaf-' || g.game_id                            as game_key,
    g.season,
    g.week,                                          -- ⚠️ CFBD-native; NOT a season ordering
    -- ⭐ the ONLY safe season ordering (see header) — monotone in game_date
    case when g.season_type = 'regular' then g.week
         else sb.max_regular_week + g.week end       as season_order_week,
    g.season_type,
    (g.season_type <> 'regular')                     as is_postseason,
    g.start_date,
    g.start_date::date                               as game_date,

    -- ── participants ──────────────────────────────────────────────────────────────────
    g.home_team_id,
    g.home_team,
    g.home_conference,
    g.home_classification,
    g.away_team_id,
    g.away_team,
    g.away_conference,
    g.away_classification,

    -- ── ⭐ the universe classification (see header) ────────────────────────────────────
    g.is_fbs_matchup,
    -- coalesce → FALSE for the same reason as is_fbs_matchup: an UNKNOWN classification is
    -- not FBS, and a NULL flag would make every downstream filter three-valued.
    coalesce(g.home_classification = 'fbs' or g.away_classification = 'fbs', false)
                                                     as is_fbs_involved,
    g.conference_game                                as is_conference_game,
    g.neutral_site                                   as is_neutral_site,

    -- ── venue / environment (the home team's, unless neutral — then unknown, not the
    --    home team's stadium, which would be plainly wrong for a bowl or a kickoff game) ─
    case when g.neutral_site then null else h.venue_name end     as venue_name,
    case when g.neutral_site then null else h.venue_city end     as venue_city,
    case when g.neutral_site then null else h.venue_state end    as venue_state,
    case when g.neutral_site then null else h.venue_timezone end as venue_timezone,
    case when g.neutral_site then null else h.venue_elevation_m end as venue_elevation_m,
    case when g.neutral_site then null else h.venue_is_dome end  as venue_is_dome,
    case when g.neutral_site then null else h.venue_is_grass end as venue_is_grass,
    case when g.neutral_site then null else h.venue_capacity end as venue_capacity,

    -- ── ⚠️ OUTCOME — post-kickoff. Pregame rows must never read these directly. ────────
    g.completed                                      as is_completed,
    g.home_points,
    g.away_points,
    case when g.completed then g.home_points + g.away_points end  as total_points,
    case when g.completed then g.home_points - g.away_points end  as home_margin,
    case when not g.completed then null
         when g.home_points > g.away_points then g.home_team_id
         when g.away_points > g.home_points then g.away_team_id
    end                                              as winning_team_id,
    case when not g.completed then null
         when g.home_points = g.away_points then true else false
    end                                              as is_tie
from games g
join season_bounds sb on sb.season = g.season
left join home_dim h
    on h.team_id = g.home_team_id
   and g.season between h.valid_from_season and coalesce(h.valid_to_season, 9999)

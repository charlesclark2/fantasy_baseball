-- ncaaf_recruit_production_pairs — the P1.2b training + emission substrate.
--
-- GRAIN: one row per (player_id, arrival_season) — a recruit who signed with an FBS program
-- and appeared on its roster, paired with WHAT they did as a true/redshirt freshman in their
-- FIRST FBS season. This is the substrate `run_freshman_projection.py` learns the recruit-
-- rating → freshman-production map from, and the population it emits a per-recruit prior for.
--
-- ⭐ THE BRIDGE (verified on the real lake, 2026-07-20): recruiting.id ↔ roster.recruit_ids.
-- The data inventory originally documented recruiting.athleteId ↔ roster.recruitIds; that is
-- WRONG on the real data (7 matches in 12 seasons). recruit_ids → recruiting_players.id
-- matches 60,883 → 18,891 distinct recruit↔player pairs, all carrying a composite rating.
--
-- ⏳ ARRIVAL SEASON = the player's FIRST FBS ROSTER SEASON (not the recruiting class year).
-- Class year is when they signed; arrival is when they first appear on an FBS roster. On the
-- real data the two agree for ~90% of pairs (gap 0) with a ~9% one-year redshirt lag — using
-- the observed first FBS season is the honest, data-driven choice and absorbs grayshirts /
-- reclassifications without a hardcoded offset.
--
-- 📊 PRODUCTION (the LABEL — POST-hoc, only for pairs where it is OBSERVED): season totals from
-- fact_ncaaf_player_game over the arrival season. Two honest raw quantities are carried and the
-- Python model chooses + STANDARDIZES per position group (so the raw scale never matters — only
-- within-group ordering does):
--   • scrimmage_prod  = passing + rushing + receiving yards           (offense skill signal)
--   • defense_prod    = tackles + 2·(sacks+TFL) + 3·(PBU+INT)         (havoc-weighted defense)
--   • games_played    = games with ANY stat line                       (participation — the ONLY
--                       production signal box scores carry for OL and deep special teams)
-- `has_production` is FALSE for a bridged recruit who made an FBS roster but recorded no stat
-- line (redshirt / walk-on depth / an OL freshman). NULL means UNKNOWN and STAYS NULL — it is
-- NOT coalesced to 0 (a freshman who didn't play is not a freshman who played and did nothing).
--
-- 🔒 LEAKAGE: every recruiting attribute is a pre-signing quantity, known before a snap is
-- played. The production columns are the LABEL and are never fed back as a feature. The
-- point-in-time discipline (fit the rating→production map only on STRICTLY PRIOR recruit
-- classes) lives in the Python model, not here — this mart is the raw, class-tagged substrate.
{{ config(materialized='table') }}

with recruits as (
    -- One recruiting record per recruit_id. HighSchool + PrepSchool + JUCO all kept; the model
    -- can filter recruit_type. Rating must be present (the whole signal).
    select
        recruit_id,
        class_year,
        recruit_type,
        recruit_name,
        committed_to,
        recruit_position,
        stars,
        composite_rating,
        national_ranking
    from {{ ref('stg_ncaaf_recruiting_players') }}
    where composite_rating is not null
),

-- Explode roster.recruit_ids and join back to the recruiting record. One row per
-- (player_id, roster_season, team) that carries a matched recruiting record.
roster_links as (
    select
        r.player_id,
        r.season                                as roster_season,
        r.team                                  as team,
        unnest(r.recruit_ids)                   as rid
    from {{ ref('stg_ncaaf_roster') }} r
    where len(r.recruit_ids) > 0
),

bridged as (
    select
        rl.player_id,
        rl.roster_season,
        rl.team,
        rec.class_year,
        rec.recruit_type,
        rec.recruit_name,
        rec.recruit_position,
        rec.stars,
        rec.composite_rating,
        rec.national_ranking,
        -- a player can (rarely) link to >1 recruiting record; rank the best-rated so the
        -- dedup below is deterministic and keeps the strongest signal.
        row_number() over (
            partition by rl.player_id
            order by rec.composite_rating desc, rec.class_year asc
        )                                       as rec_rank
    from roster_links rl
    join recruits rec on rec.recruit_id = rl.rid
),

-- Restrict the roster seasons to the FBS universe, point-in-time through dim_ncaaf_team's
-- SCD-2 range (a recruit's first NON-FBS roster season must not count as their FBS arrival).
fbs_roster as (
    select b.*
    from bridged b
    join {{ ref('dim_ncaaf_team') }} d
      on d.team = b.team
     and d.is_fbs
     and b.roster_season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
),

-- Arrival = the earliest FBS roster season per player, with the team + recruiting attributes
-- read at that arrival (rec_rank = 1 = the best-rated matched recruiting record).
arrival as (
    select
        player_id,
        min(roster_season)                                       as arrival_season
    from fbs_roster
    group by player_id
),

arrival_row as (
    select
        f.player_id,
        f.roster_season                                          as arrival_season,
        f.team                                                   as arrival_team,
        f.class_year,
        f.recruit_type,
        f.recruit_name,
        f.recruit_position,
        f.stars,
        f.composite_rating,
        f.national_ranking,
        row_number() over (
            partition by f.player_id
            order by f.rec_rank asc, f.team asc
        )                                                        as pick
    from fbs_roster f
    join arrival a
      on a.player_id = f.player_id
     and a.arrival_season = f.roster_season
),

-- First-FBS-season production. Season totals of the box-score lines; a player absent from the
-- fact for that season simply has no row here (→ has_production = false downstream).
production as (
    select
        player_id,
        season,
        count(distinct game_id)                                                 as games_played,
        coalesce(sum(passing_yards), 0) + coalesce(sum(rushing_yards), 0)
            + coalesce(sum(receiving_yards), 0)                                 as scrimmage_prod,
        coalesce(sum(passing_tds), 0) + coalesce(sum(rushing_tds), 0)
            + coalesce(sum(receiving_tds), 0)                                   as scrimmage_tds,
        coalesce(sum(tackles_total), 0)
            + 2.0 * (coalesce(sum(sacks), 0) + coalesce(sum(tackles_for_loss), 0))
            + 3.0 * (coalesce(sum(passes_defended), 0) + coalesce(sum(interceptions_caught), 0))
                                                                                as defense_prod
    from {{ ref('fact_ncaaf_player_game') }}
    group by player_id, season
)

select
    'ncaaf'                                                      as sport,
    ar.player_id,
    ar.recruit_name,
    ar.arrival_season,
    ar.arrival_team,
    ar.class_year,
    ar.recruit_type,
    ar.recruit_position,
    -- ── position GROUP: the model is position-specific; CFBD's granular recruiting labels
    --    collapse to nine modelling groups. OL and deep special teams carry NO box production
    --    (flagged below) and are modelled on participation only.
    case
        when ar.recruit_position in ('QB', 'DUAL', 'PRO')                          then 'QB'
        when ar.recruit_position in ('RB', 'APB', 'FB', 'HB', 'TB')                then 'RB'
        when ar.recruit_position in ('WR')                                         then 'WR'
        when ar.recruit_position in ('TE')                                         then 'TE'
        when ar.recruit_position in ('OT', 'OG', 'OC', 'IOL', 'OL', 'C', 'G', 'T') then 'OL'
        when ar.recruit_position in ('DL', 'DT', 'NT', 'DE', 'SDE', 'WDE', 'EDGE') then 'DL'
        when ar.recruit_position in ('LB', 'OLB', 'ILB', 'MLB')                    then 'LB'
        when ar.recruit_position in ('CB', 'S', 'DB', 'SAF', 'FS', 'SS')           then 'DB'
        when ar.recruit_position in ('K', 'P', 'LS', 'PK')                         then 'ST'
        when ar.recruit_position in ('ATH')                                        then 'ATH'
        else 'OTHER'
    end                                                          as position_group,
    ar.stars,
    ar.composite_rating,
    ar.national_ranking,
    -- ── the LABEL (POST-hoc; NULL where unobserved, never coalesced to 0) ──────────────────
    coalesce(p.games_played, 0)                                 as games_played,
    p.scrimmage_prod,
    p.scrimmage_tds,
    p.defense_prod,
    (p.player_id is not null)                                   as has_production
from arrival_row ar
left join production p
  on p.player_id = ar.player_id
 and p.season    = ar.arrival_season
where ar.pick = 1

-- ncaaf_team_roster_continuity — the per-team-season roster-continuity / talent-flux signal
-- (NCAAF-P0.4). ONE row per (season, team), FBS universe.
--
-- WHY (roadmap P0.4): the transfer portal + NIL money are re-shaping lower-conference power —
-- talent moves fast now, so the game model needs a roster-continuity / talent-flux input or it
-- will misprice teams whose roster turned over. This is the FREE signal (CFBD only); the PAID
-- NIL-$ valuations (On3/Rivals) are documented + deferred (ncaaf_data_inventory.md §10) — NOT a
-- dependency here. Feeds P1.2 (a team-strength covariate) + P1.3 (features).
--
-- ⭐ LEAKAGE-SAFE / point-in-time: every input is set PRE-SEASON for `season` —
--     • returning production (which players return) — known before week 1
--     • the portal class (season=N entries transfer in the N-1/N off-season)
--     • the roster snapshot + the 247 talent composite (recruiting-based)
--   so a downstream model joins this by `season` (constant within a season) as-of kickoff with
--   no future leakage. It carries NO in-season / outcome columns.
--
-- Spine = returning_production (the ~125-134 FBS teams/season). Portal/talent/roster left-join;
-- portal is 0/NULL before 2021 (pre-portal-era) → portal_data_covered flags it honestly, and
-- talent is NULL for 2014 (CFBD talent starts 2015) + a couple of 2025 expansion teams.
{{ config(materialized='table') }}

with ret_prod as (
    select * from {{ ref('stg_ncaaf_returning_production') }}
),

-- ── transfer-portal flux, aggregated per team-season ────────────────────────────────────
portal_in as (
    select
        season,
        destination                                     as team,
        count(*)                                        as portal_in_count,
        sum(stars)                                      as portal_in_stars_sum,
        sum(rating)                                     as portal_in_rating_sum,
        sum(case when is_blue_chip then 1 else 0 end)   as portal_in_blue_chip
    from {{ ref('stg_ncaaf_transfer_portal') }}
    where destination is not null
    group by 1, 2
),
portal_out as (
    select
        season,
        origin                                          as team,
        count(*)                                        as portal_out_count,
        sum(stars)                                      as portal_out_stars_sum,
        sum(rating)                                     as portal_out_rating_sum,
        sum(case when is_blue_chip then 1 else 0 end)   as portal_out_blue_chip,
        -- players who left with no landing spot (left CFB / uncommitted) = pure attrition
        sum(case when destination is null then 1 else 0 end) as portal_out_uncommitted
    from {{ ref('stg_ncaaf_transfer_portal') }}
    where origin is not null
    group by 1, 2
),

-- ── year-over-year roster continuity (same player, same team, season N and N-1) ─────────
roster as (
    select season, team, player_id from {{ ref('stg_ncaaf_roster') }}
),
roster_size as (
    -- per-team-season head count (also the prior-year denominator, self-joined below)
    select season, team, count(*) as roster_size
    from roster
    group by 1, 2
),
roster_returning as (
    -- players on the team's roster in BOTH season N and N-1 (a portal arrival is NOT counted
    -- here — it wasn't on this team last year). One row per (season, team); the prev-season
    -- match is on player_id so no cartesian blow-up.
    select
        cur.season,
        cur.team,
        count(prev.player_id) as roster_returning_players
    from roster cur
    left join roster prev
        on  prev.team = cur.team
        and prev.season = cur.season - 1
        and prev.player_id = cur.player_id
    group by 1, 2
),
roster_continuity as (
    select
        cs.season,
        cs.team,
        cs.roster_size,
        rr.roster_returning_players,
        ps.roster_size as roster_prev_size
    from roster_size cs
    join roster_returning rr on rr.season = cs.season and rr.team = cs.team
    left join roster_size ps on ps.team = cs.team and ps.season = cs.season - 1
),

-- ── talent composite (+ its year-over-year delta) ───────────────────────────────────────
talent as (
    select season, team, team_talent from {{ ref('stg_ncaaf_talent') }}
),
talent_yoy as (
    select
        t.season,
        t.team,
        t.team_talent,
        p.team_talent                                   as team_talent_prev,
        t.team_talent - p.team_talent                   as team_talent_yoy_delta
    from talent t
    left join talent p
        on p.team = t.team and p.season = t.season - 1
)

select
    r.sport,
    r.season,
    r.team,
    r.conference,
    -- grain surrogate (one row per season+team) — tested unique (built-in; no dbt_utils dep)
    r.season || '-' || r.team                           as team_season_key,

    -- returning production (the production-weighted continuity signal)
    r.returning_ppa_pct,
    r.returning_pass_ppa_pct,
    r.returning_rec_ppa_pct,
    r.returning_rush_ppa_pct,
    r.returning_ppa_total,
    r.returning_usage,

    -- roster continuity (raw head-count continuity)
    rc.roster_size,
    rc.roster_returning_players,
    rc.roster_prev_size,
    -- NULL (not 0) when there's NO prior-year roster in the lake (the 2014 backfill floor) —
    -- continuity is UNKNOWN there, not zero. Honest for a downstream as-of join.
    case when rc.roster_prev_size is null then null
         else round(rc.roster_returning_players::double / nullif(rc.roster_size, 0), 4) end as roster_continuity_pct,
    round(rc.roster_returning_players::double / nullif(rc.roster_prev_size, 0), 4) as roster_retention_pct,

    -- transfer-portal flux (0 when covered-but-none; NULL only in pre-2021 no-data seasons)
    coalesce(pin.portal_in_count, 0)                    as portal_in_count,
    coalesce(pout.portal_out_count, 0)                  as portal_out_count,
    coalesce(pin.portal_in_count, 0) - coalesce(pout.portal_out_count, 0) as portal_net_count,
    coalesce(pin.portal_in_stars_sum, 0)                as portal_in_stars_sum,
    coalesce(pout.portal_out_stars_sum, 0)              as portal_out_stars_sum,
    coalesce(pin.portal_in_stars_sum, 0) - coalesce(pout.portal_out_stars_sum, 0) as portal_net_stars,
    coalesce(pin.portal_in_rating_sum, 0)               as portal_in_rating_sum,
    coalesce(pout.portal_out_rating_sum, 0)             as portal_out_rating_sum,
    coalesce(pin.portal_in_blue_chip, 0)                as portal_in_blue_chip,
    coalesce(pout.portal_out_blue_chip, 0)              as portal_out_blue_chip,
    coalesce(pin.portal_in_blue_chip, 0) - coalesce(pout.portal_out_blue_chip, 0) as portal_net_blue_chip,
    coalesce(pout.portal_out_uncommitted, 0)            as portal_out_uncommitted,
    -- honest coverage flag: CFBD portal data exists only from 2021 (the portal era)
    (r.season >= 2021)                                  as portal_data_covered,

    -- talent level + flux
    ty.team_talent,
    ty.team_talent_prev,
    ty.team_talent_yoy_delta

from ret_prod r
left join portal_in         pin  on pin.season  = r.season and pin.team  = r.team
left join portal_out        pout on pout.season = r.season and pout.team = r.team
left join roster_continuity rc   on rc.season   = r.season and rc.team   = r.team
left join talent_yoy        ty   on ty.season   = r.season and ty.team   = r.team

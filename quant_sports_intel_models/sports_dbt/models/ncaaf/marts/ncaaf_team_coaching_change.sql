-- ncaaf_team_coaching_change — the per-team-season head-coaching-continuity signal (NCAAF-P0.5).
-- ONE row per (season, team), FBS universe (spine = CFBD returning production, same as P0.4).
--
-- WHY (roadmap P0.5): a new HC can flip a team's scheme + scoring profile overnight (~63–71 new
-- Power-4 coordinators in the 2026 cycle alone) → the game model needs a coaching-continuity
-- input. This ships the FREE HEAD-COACH signal from CFBD /coaches; the OC/DC coordinator layer is
-- a GAP not in CFBD (no free API) → documented + DEFERRED (ncaaf_data_inventory.md §11), gated
-- like NIL-$ — NOT a dependency of this model. Feeds P1.3 (the coaching feature block).
--
-- ⭐ WHAT'S NOVEL vs a binary flag: CFBD /coaches carries each coach-year's SP+ splits, so a NEW
--   coach's expected impact ≈ their PRIOR track record (hc_prior_sp_* / hc_recent_sp_*), not just
--   "the coach changed". A washed-out retread and a proven winner both trip hc_change_from_prev,
--   but their prior-SP+ profiles are very different.
--
-- ⭐ LEAKAGE-SAFE / point-in-time. Everything here is known as-of kickoff of `season`:
--     • WHO the head coach is — a hire is announced pre-season (identity only; never this
--       season's wins/SP+).
--     • hc_change_from_prev / tenure — derived purely from coach IDENTITY across seasons.
--     • the prior-SP+ profile — aggregated STRICTLY over seasons with year < `season` (the
--       coach's history at ANY school). The current-season SP+ row is used ONLY to identify the
--       coach of record, NEVER emitted as a feature.
--   So a downstream model joins this by `season` (constant within a season) with no future leak.
--
-- COVERAGE / honesty caveats:
--   • The observed coaching history is 2014–2025 (the backfill floor). So for `season`=2014 there
--     is no prior year → hc_change_from_prev is NULL (unknown, not "no change"), and hc_tenure /
--     hc_prior_* are LEFT-CENSORED (a coach hired pre-2014 shows tenure starting at 2014).
--     is_hc_history_censored flags the 2014 floor so a consumer can treat it as unknown.
--   • ~7% of (season, team) cells had >1 coach (a mid-season change / interim). The coach of
--     record is the one with the most games that season (tie-break by name); hc_midseason_change
--     flags the cell. n_coaches_in_season carries the raw count.
--   • A first-time HC (no prior CFBD head-coaching season in-window) has NULL prior-SP+ and
--     is_first_time_hc = true (an honest NULL, not a zeroed profile).
{{ config(materialized='table') }}

with coaches as (
    select * from {{ ref('stg_ncaaf_coaches') }}
),

-- ── the FBS team-season spine (same universe as P0.4's roster-continuity mart) ───────────
spine as (
    select sport, season, team, conference
    from {{ ref('stg_ncaaf_returning_production') }}
),

-- ── coach of record per (season, team): the most-games coach, tie-broken by name ─────────
ranked as (
    select
        season, team, coach_name, coach_first, coach_last, hire_date, games,
        row_number() over (
            partition by season, team
            order by games desc nulls last, coach_name
        ) as rn,
        count(*) over (partition by season, team) as n_coaches_in_season
    from coaches
),
coach_of_record as (
    select
        season, team, coach_name, coach_first, coach_last, hire_date,
        n_coaches_in_season,
        (n_coaches_in_season > 1) as hc_midseason_change
    from ranked
    where rn = 1
),

-- ── year-over-year HC change (identity only → leakage-safe) ──────────────────────────────
hc_change as (
    select
        c.season,
        c.team,
        p.coach_name as prev_head_coach,
        -- NULL when there is NO prior-year row for the team (the 2014 floor / a brand-new
        -- program) — the change is UNKNOWN there, not false.
        case
            when p.coach_name is null then null
            else (c.coach_name <> p.coach_name)
        end as hc_change_from_prev
    from coach_of_record c
    left join coach_of_record p
        on p.team = c.team
       and p.season = c.season - 1
),

-- ── HC tenure at the school (gaps-and-islands over the coach-of-record stint) ────────────
stint as (
    select
        season, team, coach_name,
        -- consecutive seasons with the same coach at the same team collapse to one island:
        -- (season − dense rank within the coach-team) is constant across a contiguous run.
        season - row_number() over (
            partition by team, coach_name order by season
        ) as stint_grp
    from coach_of_record
),
tenure as (
    select
        season, team,
        row_number() over (
            partition by team, coach_name, stint_grp order by season
        ) as hc_tenure_years
    from stint
),

-- ── each coach-of-record's PRIOR track record (STRICTLY year < season → leakage-safe) ────
-- career-to-date aggregate over all prior seasons at ANY school, keyed on coach name.
prior_agg as (
    select
        c.season,
        c.team,
        count(h.season)                    as hc_prior_seasons,
        avg(h.sp_overall)                  as hc_prior_sp_overall_avg,
        avg(h.sp_offense)                  as hc_prior_sp_offense_avg,
        avg(h.sp_defense)                  as hc_prior_sp_defense_avg,
        sum(h.wins)                        as hc_prior_wins,
        sum(h.losses)                      as hc_prior_losses
    from coach_of_record c
    left join coaches h
        on h.coach_name = c.coach_name
       and h.season < c.season
    group by 1, 2
),
-- the MOST-RECENT prior season's SP+ (the freshest track-record read)
recent_prior as (
    select season, team, hc_recent_prior_season,
           hc_recent_sp_overall, hc_recent_sp_offense, hc_recent_sp_defense
    from (
        select
            c.season,
            c.team,
            h.season    as hc_recent_prior_season,
            h.sp_overall as hc_recent_sp_overall,
            h.sp_offense as hc_recent_sp_offense,
            h.sp_defense as hc_recent_sp_defense,
            row_number() over (
                partition by c.season, c.team order by h.season desc
            ) as rn
        from coach_of_record c
        join coaches h
            on h.coach_name = c.coach_name
           and h.season < c.season
    )
    where rn = 1
)

select
    sp.sport,
    sp.season,
    sp.team,
    sp.conference,
    sp.season || '-' || sp.team                          as team_season_key,

    -- head-coach identity + tenure
    cor.coach_name                                       as head_coach,
    cor.hire_date                                        as head_coach_hire_date,
    ten.hc_tenure_years,
    (ten.hc_tenure_years = 1)                            as is_first_year_at_school,
    cor.n_coaches_in_season,
    coalesce(cor.hc_midseason_change, false)             as hc_midseason_change,

    -- year-over-year change (NULL at the 2014 floor = unknown)
    chg.prev_head_coach,
    chg.hc_change_from_prev,
    -- the 2014 backfill floor left-censors change + tenure + prior history
    (sp.season = 2014)                                   as is_hc_history_censored,

    -- ⭐ the new/returning HC's PRIOR SP+ track record (strictly prior seasons; leakage-safe)
    coalesce(pa.hc_prior_seasons, 0)                     as hc_prior_seasons,
    (coalesce(pa.hc_prior_seasons, 0) = 0)               as is_first_time_hc,
    pa.hc_prior_sp_overall_avg,
    pa.hc_prior_sp_offense_avg,
    pa.hc_prior_sp_defense_avg,
    pa.hc_prior_wins,
    pa.hc_prior_losses,
    rp.hc_recent_prior_season,
    rp.hc_recent_sp_overall,
    rp.hc_recent_sp_offense,
    rp.hc_recent_sp_defense

from spine sp
left join coach_of_record cor on cor.season = sp.season and cor.team = sp.team
left join hc_change       chg on chg.season = sp.season and chg.team = sp.team
left join tenure          ten on ten.season = sp.season and ten.team = sp.team
left join prior_agg       pa  on pa.season  = sp.season and pa.team  = sp.team
left join recent_prior    rp  on rp.season  = sp.season and rp.team  = sp.team

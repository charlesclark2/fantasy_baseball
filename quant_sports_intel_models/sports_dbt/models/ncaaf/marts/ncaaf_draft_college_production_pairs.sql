-- ncaaf_draft_college_production_pairs — the NCAAF-P1A training + emission substrate.
--
-- GRAIN: one row per matched NFL player (`gsis_id`) in the P0.3 xref — their PRE-DRAFT college
-- body of work (final 1–2 FBS seasons of box production + combine measurables + recruiting
-- pedigree) paired with their POST-draft NFL early-career outcome (`target_*`, the LABEL). This
-- is the substrate `run_college_nfl_translation.py` learns the college→NFL translation from, and
-- the population it emits a per-player rookie projection for — the football analog of MLB Edge
-- E7's MiLB→MLB MLE.
--
-- ⭐ START FROM THE XREF (NCAAF-P0.3 — do NOT rebuild the draft-slot join). The xref already
-- keys a CFBD `college_athlete_id` to an NFL `gsis_id` (99.11% of 2015–25 picks), stamps match
-- provenance (`deterministic_slot` = drafted, high conf | `fuzzy_udfa` = undrafted, med/low),
-- and carries the combine attach + the `target_*` NFL outcomes. This mart JOINS P1.1 college
-- production ONTO that spine on `college_athlete_id = fact.player_id` (both are the CFBD/ESPN
-- numeric athlete id — the game box score's `player_id` and the draft pick's `collegeAthleteId`
-- share the ESPN id space; verified by coverage-count on the real lake, see the run report).
--
-- 🔑 THE JOIN-COVERAGE LESSON (PM note #4, the P1.2b dead-bridge trap): a drafted player in the
-- xref may carry NO P1.1 college production (pre-2014 final season below the box floor, an FCS
-- transfer year, or a missing box). Such a row keeps `has_college_production = false` and a NULL
-- production block — it is NEVER coalesced to 0 (no snaps ≠ zero production). The Python model
-- trains on rows that DO carry production and the run report prints the join-coverage %; a
-- silently-thin join under-trains the model, so the coverage is surfaced, not hidden.
--
-- ⏳ FINAL 1–2 COLLEGE SEASONS, strictly < draft_year and ≥ the 2014 box-production floor. College
-- is by construction pre-draft, but the `< draft_year` cap makes the leakage-safety explicit and
-- the FLOOR (fact_ncaaf_player_game — the CFBD box vocabulary — is reliable from 2014) bounds the
-- window. A 2015 draftee (final college ~2013–14) may therefore carry only a partial window; that
-- thinness is a coverage limit surfaced in the report, not a bias.
--
-- 📊 PRODUCTION (features — PRE-draft, leakage-safe): season-window sums of the honest box lines
-- (Python builds the position-specific composite + STANDARDIZES per position group, so the raw
-- scale never matters — only within-position ordering does). Combine measurables ride along from
-- the xref (partially present — impute/flag-missing, never dropped). Recruiting pedigree is a best-
-- effort LEFT JOIN through the same roster.recruit_ids ↔ recruiting.id bridge P1.2b proved.
--
-- 🔒 LEAKAGE: every feature column (college production, combine, recruiting pedigree, draft slot)
-- is a fact known BEFORE the player's first NFL snap. The `target_*` columns are POST-draft NFL
-- outcomes = the LABEL, carried here (they already live in nflverse draft_picks — no extra source)
-- and NEVER fed back as a feature (prefixed `target_`; the Python feature build cannot pick them
-- up). The point-in-time discipline (fit the map only on STRICTLY-PRIOR draft classes) lives in
-- the Python model, not here — this mart is the raw, class-tagged substrate.
{{ config(materialized='table') }}

with xref as (
    -- the P0.3 spine: one row per matched NFL player. Drafted (deterministic_slot, has target_*)
    -- AND UDFA (fuzzy_udfa, target_* NULL) rows both flow through — the model trains on drafted
    -- (needs a label) and can still EMIT a college-only projection for a UDFA (flagged low conf).
    select
        gsis_id,
        college_athlete_id,
        player_name,
        position                                                as nfl_position,
        college,
        college_conference,
        draft_year,
        draft_overall,
        draft_round,
        match_method,
        match_confidence,
        is_udfa,
        forty, vertical, bench, broad_jump, cone, shuttle, combine_ht, combine_wt,
        has_combine, has_forty,
        target_car_av, target_w_av, target_dr_av, target_games,
        target_seasons_started, target_probowls, target_allpro, target_hof
    from {{ ref('xref_college_nfl_players') }}
    where college_athlete_id is not null
      -- gsis_id IS the NFL-vertical join key + the mart grain, so a null-gsis_id row is useless for
      -- the feeder and would collide on the grain. P0.3 leaves ~25 draft-pick partners with a null
      -- gsis_id (nflverse coverage vintage, concentrated 2015–17); drop them here.
      and gsis_id is not null
    -- NOTE: drafted (deterministic_slot, draft_year present) AND UDFA (fuzzy_udfa, draft_year NULL)
    -- rows both flow through. A UDFA has no draft year → its class is derived below as
    -- final_college_season + 1 (its NFL-entry year), so it can still be EMITTED (flagged is_udfa,
    -- no target → excluded from training). The GATE requires UDFAs handled, not dropped.
),

-- The pre-draft college season window: a player's FBS box-score seasons strictly before their
-- draft year and at/after the 2014 floor, ranked most-recent-first so we keep the FINAL 1–2.
college_seasons as (
    select
        f.player_id,
        f.season,
        count(distinct f.game_id)                                       as games,
        coalesce(sum(f.passing_yards), 0)                               as passing_yards,
        coalesce(sum(f.passing_tds), 0)                                 as passing_tds,
        coalesce(sum(f.rushing_yards), 0)                               as rushing_yards,
        coalesce(sum(f.rushing_tds), 0)                                 as rushing_tds,
        coalesce(sum(f.receiving_yards), 0)                             as receiving_yards,
        coalesce(sum(f.receiving_tds), 0)                               as receiving_tds,
        coalesce(sum(f.receptions), 0)                                  as receptions,
        coalesce(sum(f.pass_attempts), 0)                               as pass_attempts,
        coalesce(sum(f.rushing_attempts), 0)                            as rushing_attempts,
        coalesce(sum(f.tackles_total), 0)                               as tackles_total,
        coalesce(sum(f.sacks), 0)                                       as sacks,
        coalesce(sum(f.tackles_for_loss), 0)                            as tackles_for_loss,
        coalesce(sum(f.passes_defended), 0)                             as passes_defended,
        coalesce(sum(f.interceptions_caught), 0)                        as interceptions_caught,
        coalesce(sum(f.defensive_tds), 0)                               as defensive_tds
    from {{ ref('fact_ncaaf_player_game') }} f
    where f.season >= 2014
    group by f.player_id, f.season
),

-- Attach each college season to its drafted player (ESPN id join; cast the xref bigint to the
-- fact's varchar player_id), keep only seasons strictly before the draft, rank final-first.
windowed as (
    select
        x.gsis_id,
        cs.*,
        row_number() over (partition by x.gsis_id order by cs.season desc) as season_recency
    from xref x
    join college_seasons cs
      on cs.player_id = cast(x.college_athlete_id as varchar)
     -- college is by construction pre-draft; for a UDFA (draft_year NULL) there is no draft cap,
     -- so take all their FBS seasons (coalesce to a far-future sentinel).
     and cs.season    < coalesce(x.draft_year, 9999)
),

-- Sum the FINAL 1–2 college seasons into the pre-draft production block.
final_window as (
    select
        gsis_id,
        count(*)                                                as n_college_seasons,
        max(season)                                             as final_college_season,
        sum(games)                                              as games,
        sum(passing_yards)                                      as passing_yards,
        sum(passing_tds)                                        as passing_tds,
        sum(rushing_yards)                                      as rushing_yards,
        sum(rushing_tds)                                        as rushing_tds,
        sum(receiving_yards)                                    as receiving_yards,
        sum(receiving_tds)                                      as receiving_tds,
        sum(receptions)                                         as receptions,
        sum(pass_attempts)                                      as pass_attempts,
        sum(rushing_attempts)                                   as rushing_attempts,
        sum(tackles_total)                                      as tackles_total,
        sum(sacks)                                              as sacks,
        sum(tackles_for_loss)                                   as tackles_for_loss,
        sum(passes_defended)                                    as passes_defended,
        sum(interceptions_caught)                               as interceptions_caught,
        sum(defensive_tds)                                      as defensive_tds
    from windowed
    where season_recency <= 2          -- ⭐ the final 1–2 college seasons
    group by gsis_id
),

-- Best-effort recruiting pedigree via the P1.2b bridge (roster.recruit_ids ↔ recruiting.id),
-- keyed on the same ESPN athlete id. A player with no roster→recruiting link is simply absent
-- (walk-ons, some transfers) → NULL pedigree, imputed/flagged downstream, never dropped.
roster_links as (
    select r.player_id, unnest(r.recruit_ids) as rid
    from {{ ref('stg_ncaaf_roster') }} r
    where len(r.recruit_ids) > 0
),

pedigree as (
    select
        rl.player_id,
        max(rec.composite_rating)                               as recruit_composite_rating,
        max(rec.stars)                                          as recruit_stars,
        min(rec.national_ranking)                               as recruit_national_ranking
    from roster_links rl
    join {{ ref('stg_ncaaf_recruiting_players') }} rec
      on rec.recruit_id = rl.rid
    where rec.composite_rating is not null
    group by rl.player_id
)

select
    'ncaaf'                                                      as sport,
    x.gsis_id,
    x.college_athlete_id,
    x.player_name,
    x.college,
    x.college_conference,
    -- ⭐ the CLASS the projection is emitted for: the real draft year for drafted players; for a
    -- UDFA (no draft year) their NFL-entry year = final college season + 1. NULL only if a UDFA
    -- carries no college production at all (nothing to project from → the harness skips it).
    coalesce(x.draft_year, fw.final_college_season + 1)         as draft_year,
    x.draft_year                                                as draft_year_actual,
    x.draft_overall,
    x.draft_round,
    x.match_method,
    x.match_confidence,
    x.is_udfa,

    -- ── position GROUP: the translation is position-specific; the NFL position label collapses
    --    to nine modelling groups. OL and specialists carry NO box production (flagged) and are
    --    modelled on combine + pedigree only. EDGE folds into DL (the box has no edge split).
    case
        when upper(x.nfl_position) in ('QB')                                  then 'QB'
        when upper(x.nfl_position) in ('RB', 'HB', 'FB', 'TB')                 then 'RB'
        when upper(x.nfl_position) in ('WR')                                   then 'WR'
        when upper(x.nfl_position) in ('TE')                                   then 'TE'
        when upper(x.nfl_position) in ('T', 'G', 'C', 'OT', 'OG', 'OL', 'IOL') then 'OL'
        when upper(x.nfl_position) in ('DL', 'DT', 'NT', 'DE', 'EDGE')         then 'DL'
        when upper(x.nfl_position) in ('LB', 'ILB', 'OLB', 'MLB')              then 'LB'
        when upper(x.nfl_position) in ('CB', 'S', 'DB', 'FS', 'SS', 'SAF')     then 'DB'
        when upper(x.nfl_position) in ('K', 'P', 'LS', 'PK')                   then 'ST'
        else 'OTHER'
    end                                                         as position_group,
    x.nfl_position,

    -- ── combine measurables (features — pre-draft; partially present, impute/flag downstream) ──
    x.forty, x.vertical, x.bench, x.broad_jump, x.cone, x.shuttle, x.combine_ht, x.combine_wt,
    x.has_combine, x.has_forty,

    -- ── recruiting pedigree (features — pre-college; best-effort, NULL where unbridged) ────────
    ped.recruit_composite_rating,
    ped.recruit_stars,
    ped.recruit_national_ranking,

    -- ── PRE-DRAFT college production (features — final 1–2 FBS seasons; NULL where none) ───────
    fw.n_college_seasons,
    fw.final_college_season,
    coalesce(fw.games, 0)                                       as college_games,
    fw.passing_yards, fw.passing_tds,
    fw.rushing_yards, fw.rushing_tds,
    fw.receiving_yards, fw.receiving_tds, fw.receptions,
    fw.pass_attempts, fw.rushing_attempts,
    fw.tackles_total, fw.sacks, fw.tackles_for_loss,
    fw.passes_defended, fw.interceptions_caught, fw.defensive_tds,
    (fw.gsis_id is not null)                                    as has_college_production,

    -- ── the LABEL (POST-draft NFL outcome; NULL for UDFAs — never a feature) ──────────────────
    x.target_car_av, x.target_w_av, x.target_dr_av, x.target_games,
    x.target_seasons_started, x.target_probowls, x.target_allpro, x.target_hof,
    (x.target_w_av is not null)                                 as has_nfl_outcome
from xref x
left join final_window fw on fw.gsis_id = x.gsis_id
left join pedigree ped     on ped.player_id = cast(x.college_athlete_id as varchar)

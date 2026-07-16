-- xref_college_nfl_players — the college↔NFL player-ID crosswalk (NCAAF-P0.3).
--
-- The spine of the NFL feeder (college production → NFL rookie projections; the MLB Edge-E7
-- MiLB→MLB analog). This is a thin, typed VIEW over the versioned Delta MART that the Python
-- builder writes (football/ncaaf/feeder/xref.py → ncaaf/marts/xref_college_nfl_players).
--
-- WHY a Python builder + a dbt view (not a pure dbt model): the deterministic slot join is
-- trivially SQL, but the UDFA fuzzy residual + the anti-cartesian row-count ASSERTIONS (the
-- NaN-to-NaN trap that faked a ~100% match in P0.1) live far more safely in the tested Python
-- builder — one copy of the join, provable offline against local Delta fixtures AND on the S3
-- box. dbt reads the result (mirrors MLB run_w1_lakehouse → dbt-reads-the-Delta-mart).
--
-- match_method: deterministic_slot (high, the 99.7% spine, match_score=1.0) | fuzzy_udfa
--   (medium/low, undrafted players fuzzy-matched name+school+position, match_score=Jaro-Winkler).
-- ⚠️ target_* are POST-draft NFL outcomes = the P1A TARGET, NOT features (leakage-safe).
{{ config(materialized='view') }}

select
    sport,
    gsis_id,
    pfr_player_id,
    cfb_player_id,
    college_athlete_id,
    player_name,
    position,
    college,
    college_conference,
    draft_year,
    draft_overall,
    draft_round,
    match_method,
    match_confidence,
    match_score,
    surname_agree,
    is_udfa,
    -- combine measurables (attached on the slot path via the cfb_player_id slug)
    forty, vertical, bench, broad_jump, cone, shuttle, combine_ht, combine_wt,
    has_combine, has_forty,
    -- TARGET outcomes (drafted players only; UDFA rows NULL by construction). NOT features.
    target_car_av, target_w_av, target_dr_av, target_games,
    target_seasons_started, target_probowls, target_allpro, target_hof,
    xref_version,
    built_at
from {{ ncaaf_delta('xref_college_nfl_players', tier='marts') }}

-- =============================================================================
-- int_bullpen_ali_by_season.sql  —  Story A2.11 (bullpen support model)
-- Grain: one row per (season, pitcher_id) for relievers with ≥20 appearances.
--
-- Normalized average Leverage Index (aLI) per reliever-season, ported from
-- compute_bullpen_posteriors._load_normalized_ali_map. The downstream bullpen
-- posterior joins this TWICE: season-1 → leverage_role; season (full) → the
-- role_changed flag. Both use the FULL-SEASON aLI (no as-of) to match the
-- BACKFILL path that built the historical eb_bullpen_posteriors table — NOT the
-- daily as-of path (role_changed is informational metadata, not a posterior input).
--
-- aLI = (pitcher's mean per-at-bat |Δ home win-exp|) / (season mean per-at-bat
-- |Δ home win-exp| across all relievers). Starters excluded by anti-join on
-- (game_pk, pitcher_id, pitching_team).
-- =============================================================================

-- Story A2.11: incremental by season (delete+insert). aLI for a CLOSED season is
-- immutable, but the current season's aLI shifts as games accumulate (and the
-- prior season is the leverage_role basis), so incremental runs recompute current
-- + prior season only — avoiding a daily all-seasons pitch-level rescan.
{{ config(materialized='incremental', unique_key='season', incremental_strategy='delete+insert') }}

with reliever_at_bats as (
    select
        bp.game_year as season,
        bp.game_pk,
        bp.at_bat_number,
        bp.pitcher_id,
        case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end as pitching_team,
        abs(ppe.delta_home_win_exp) as abs_delta
    from {{ ref('stg_batter_pitches') }} bp
    join {{ ref('mart_pitch_play_event') }} ppe on ppe.pitch_sk = bp.pitch_sk
    where bp.game_type = 'R'
      and ppe.delta_home_win_exp is not null
      and bp.game_year between 2015 and year(current_date())
    {% if is_incremental %}
      and bp.game_year >= year(current_date()) - 1
    {% endif %}
),

starters as (
    select game_pk, pitcher_id, pitching_team
    from {{ ref('mart_starting_pitcher_game_log') }}
),

reliever_only as (
    select rab.*
    from reliever_at_bats rab
    left join starters s
      on  s.game_pk       = rab.game_pk
      and s.pitcher_id    = rab.pitcher_id
      and s.pitching_team = rab.pitching_team
    where s.pitcher_id is null
),

at_bat_scores as (
    select season, pitcher_id, game_pk, at_bat_number, sum(abs_delta) as ab_score
    from reliever_only
    group by season, pitcher_id, game_pk, at_bat_number
),

season_avg as (
    select season, avg(ab_score) as season_mean_ab_score
    from at_bat_scores
    group by season
),

pitcher_season as (
    select season, pitcher_id,
        count(distinct game_pk) as appearances,
        avg(ab_score)           as raw_ali
    from at_bat_scores
    group by season, pitcher_id
)

select
    ps.season,
    ps.pitcher_id::varchar                       as pitcher_id,
    ps.appearances,
    ps.raw_ali / sa.season_mean_ab_score         as normalized_ali
from pitcher_season ps
join season_avg sa on sa.season = ps.season
where ps.appearances >= 20

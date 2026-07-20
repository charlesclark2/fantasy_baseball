-- fact_ncaaf_drive — the drive fact (NCAAF-P1.1).
--
-- GRAIN: one row per drive. The drive is the unit that answers "did this team turn field position
-- into points?" — scoring-opportunity rate, points-per-opportunity, and drive-efficiency all live
-- at this grain and nowhere else. The team-game box can tell you a team gained 420 yards; only the
-- drive fact tells you it stalled inside the 40 six times.
--
-- ⭐ FBS-FILTERED (both sides FBS, via dim_ncaaf_game) + SPORT-TAGGED.
-- Offense/defense team ids are resolved point-in-time through dim_ncaaf_team's SCD-2 range.
--
-- ⭐ Derived ONCE here (so every consumer agrees):
--   • is_scoring_opportunity — the drive reached the opponent's 40 (yards_to_goal ≤ 40). This is
--     the standard CFB definition and the denominator of points-per-opportunity.
--   • points_scored — the offense's points on the drive, from the score delta. ⚠️ Derived from
--     the OFFENSE's score change, so a defensive/special-teams score on the drive is NOT
--     attributed to the offense.
--   • is_explosive_drive / is_three_and_out — the tails that drive variance.
--
-- ⚠️ POST-KICKOFF outcome fact.
{{ config(materialized='table') }}

with games as (
    select game_id, season, week, season_order_week, season_type, game_date, is_neutral_site,
           is_conference_game, is_postseason
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup            -- ⭐ the modelling universe
),

drives as (
    select * from {{ ref('stg_ncaaf_drives') }}
),

teams as (
    select team_id, team, conference, valid_from_season, valid_to_season
    from {{ ref('dim_ncaaf_team') }}
)

select
    'ncaaf'                                              as sport,
    d.drive_id,
    'ncaaf-' || d.drive_id                               as drive_key,
    d.game_id,
    g.season,
    g.week,
    g.season_order_week,
    g.season_type,
    g.game_date,
    d.drive_number,

    -- ── participants (point-in-time resolved team ids) ────────────────────────────────
    d.offense_team,
    ot.team_id                                           as offense_team_id,
    d.offense_conference,
    d.defense_team,
    dt.team_id                                           as defense_team_id,
    d.defense_conference,
    d.is_home_offense,

    -- ── drive shape ───────────────────────────────────────────────────────────────────
    d.drive_result,
    d.is_scoring_drive,
    d.plays,
    d.yards,
    d.elapsed_seconds,
    d.start_period,
    d.end_period,
    d.start_yardline,
    d.start_yards_to_goal,
    d.end_yardline,
    d.end_yards_to_goal,

    -- ── derived, once ─────────────────────────────────────────────────────────────────
    -- reached the opponent's 40 → a genuine chance to score (the PPO denominator)
    (d.end_yards_to_goal is not null and d.end_yards_to_goal <= 40) as is_scoring_opportunity,
    -- points the OFFENSE put up on this drive (score delta; excludes defensive scores)
    greatest(coalesce(d.end_offense_score, 0) - coalesce(d.start_offense_score, 0), 0)
                                                         as points_scored,
    (coalesce(d.plays, 0) <= 3 and not coalesce(d.is_scoring_drive, false)
        and d.drive_result not in ('END OF HALF', 'END OF GAME', 'END OF 4TH QUARTER'))
                                                         as is_three_and_out,
    (coalesce(d.yards, 0) >= 40)                         as is_explosive_drive,
    -- yards gained per play on the drive
    case when d.plays > 0 then d.yards::double / d.plays end as yards_per_play,
    d.start_offense_score,
    d.start_defense_score,
    d.end_offense_score,
    d.end_defense_score
from drives d
join games g on g.game_id = d.game_id
left join teams ot
    on ot.team = d.offense_team
   and g.season between ot.valid_from_season and coalesce(ot.valid_to_season, 9999)
left join teams dt
    on dt.team = d.defense_team
   and g.season between dt.valid_from_season and coalesce(dt.valid_to_season, 9999)

-- feature_ncaaf_pregame_matrix — the BROAD, leakage-safe, point-in-time pregame feature matrix
-- (NCAAF-P1.3). ONE row per FBS-vs-FBS game; the input P1.4's game-model bake-off trains on.
--
-- ══════════════════════════════════════════════════════════════════════════════════════════
-- GRAIN: one row per game in the FBS modelling universe (`is_fbs_matchup`), keyed `game_id`.
--   A MATCHUP row: the home team's pregame features and the away team's pregame features side by
--   side, each snapshot AS OF this game's own kickoff, plus the situational context and — set
--   apart under a `label_` prefix — the POST-KICKOFF outcome P1.4 uses as its target.
--
-- ⭐ WHY GAME GRAIN, NOT TEAM-GAME: P1.4 models the JOINT scoring distribution ONCE and derives
--   all three markets from it (H2H = P(margin>0), spread = P(margin>line), total = P(total>line)).
--   That is a per-MATCHUP prediction, so the matrix is per matchup. A team's features appear twice
--   in a season's file (once as home, once as away), which is correct — the leakage boundary is
--   each SPECIFIC game's kickoff, not the team's week.
--
-- ══════════════════════════════════════════════════════════════════════════════════════════
-- 🔒 THE LEAKAGE CONTRACT (as-of THIS game's kickoff — the whole point):
--   Every `home_*` / `away_*` feature is read at `as_of_week = this game's season_order_week`,
--   which the upstream rollups define as "only games with season_order_week < W". So no feature
--   can see the game it is describing, nor any later game.
--   • Week-grained families (rollup, opponent-adjusted, strength) join 1:1 on
--     (season, team_id, as_of_week = season_order_week).
--   • Season-grained families (roster continuity, coaching, freshman prior) are PRE-SEASON
--     constants and BROADCAST across every week by joining on (season, team-name).
--   Enforced structurally by the joins below and audited by the DATE-based singular test
--   `assert_pregame_matrix_is_point_in_time` — which, per the P1.1 lesson, checks the CLOCK, not
--   the week ordering (a week-based test passes green on a bad ordering; this one cannot).
--
-- 🚨 season_order_week, NEVER raw CFBD `week` — postseason restarts at 1 (the P1.1 leak).
-- 🚨 NULL = UNKNOWN, kept NULL. Week-1 rows, teams with no coverage, first-time HCs, pre-2021
--    portal, 2014 (no strength emitted) — all honest NULLs. NEVER coalesced to 0 (that tells a
--    learner something false). P1.4's learners handle missingness.
-- 🚨 SIGN TRAP (P1.2): strength_offense + strength_defense are BOTH higher-is-better (defense =
--    points PREVENTED). Net strength is their SUM. `strength_margin` already encodes this — use it.
-- 🚨 The `label_*` columns are POST-KICKOFF. They are the TARGET, never a feature. Prefixed so a
--    careless `select * except (label_*)` in P1.4 cannot feed them in (the xref `target_*` rule).
--
-- BUILD ORDER (INC-25): P1.1 marts → run_team_strength.py → run_freshman_projection.py →
--   dbt run (strength_week + team_freshman_prior views) → dbt run (this model). Tagged
--   `ncaaf_p1_3` so it is opt-in and cannot break a build before its parquet-backed inputs exist.
--   `run_feature_matrix.py` then reads THIS table once → the cached parquet the bake-off consumes.
{{ config(materialized='table', tags=['ncaaf_p1_3']) }}

-- ── the matrix spine: every FBS-vs-FBS game + its situational context + the POST-KICKOFF label ──
with games as (
    select
        game_id, season, week, season_order_week, season_type, is_postseason,
        game_date, start_date,
        home_team_id, home_team, home_conference,
        away_team_id, away_team, away_conference,
        is_conference_game, is_neutral_site,
        -- venue/environment of the game itself (the home team's stadium unless neutral → NULL)
        venue_elevation_m           as game_venue_elevation_m,
        venue_is_dome               as game_venue_is_dome,
        venue_is_grass              as game_venue_is_grass,
        venue_timezone              as game_venue_timezone,
        -- ⛔ POST-KICKOFF outcome (the P1.4 target)
        is_completed, home_points, away_points, total_points, home_margin, winning_team_id, is_tie
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup
),

-- ── rest days: gap since each team's PREVIOUS game (over its FULL schedule incl. FCS opponents,
--    so a tune-up game or bye is reflected honestly). Opener → NULL (no prior game = unknown). ──
team_schedule as (
    select season, home_team_id as team_id, game_id, game_date, season_order_week
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_involved and season_order_week is not null
    union all
    select season, away_team_id as team_id, game_id, game_date, season_order_week
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_involved and season_order_week is not null
),
rest as (
    select
        game_id, team_id,
        date_diff('day',
            lag(game_date) over (partition by season, team_id
                                 order by season_order_week, game_date, game_id),
            game_date)                                          as rest_days
    from team_schedule
),

-- ── each team's home-venue geography, point-in-time through dim_team's SCD-2 range (for the
--    travel/altitude environment block — lat/long ARE staged on stg_ncaaf_teams). ──
team_venue as (
    select
        team_id, valid_from_season, valid_to_season,
        venue_latitude, venue_longitude, venue_elevation_m
    from {{ ref('dim_ncaaf_team') }}
),

-- ── QB continuity (the pivotal position, no injury source in CFB → the DERIVABLE half only):
--    the per-game primary QB = the qualified passer (≥8 attempts) with the most attempts. ──
qb_starter as (
    select game_id, team_id, season, season_order_week, player_id as qb_player_id,
           passing_yards_per_attempt as qb_ypa, qbr as qb_qbr
    from (
        select game_id, team_id, season, season_order_week, player_id,
               passing_yards_per_attempt, qbr,
               row_number() over (partition by game_id, team_id order by pass_attempts desc, player_id) as rn
        from {{ ref('fact_ncaaf_player_game') }}
        where has_passing_line and pass_attempts >= 8
    )
    where rn = 1
),
-- a `_changed_at_start` flag per start: did this game's QB differ from the team's PREVIOUS start's
-- QB? (the lag looks strictly BACKWARD, so it stays leakage-safe when read for prior starts only)
qb_seq as (
    select game_id, team_id, season, season_order_week, qb_player_id, qb_ypa, qb_qbr,
        (qb_player_id <> lag(qb_player_id) over (
            partition by season, team_id order by season_order_week, game_id))::integer as qb_changed_at_start
    from qb_starter
),
matrix_sides as (
    select game_id, season, home_team_id as team_id, season_order_week from games
    union all
    select game_id, season, away_team_id as team_id, season_order_week from games
),
-- as-of the matrix game, the team's TRAILING QB picture from strictly-prior starts only
qb_asof as (
    select
        m.game_id, m.team_id,
        count(s.game_id)                                        as qb_starts_prior,
        count(distinct s.qb_player_id)                          as qb_distinct_starters_prior,
        avg(s.qb_ypa)                                           as qb_trailing_ypa,
        avg(s.qb_qbr)                                           as qb_trailing_qbr,
        -- was the MOST-RECENT prior start a QB change vs the one before it? (an instability signal
        -- fully observed before this kickoff). arg_max picks the flag at the latest prior start;
        -- NULL when there is no prior start (unknown, kept NULL).
        (arg_max(s.qb_changed_at_start, s.season_order_week) = 1) as qb_starter_changed_recent
    from matrix_sides m
    left join qb_seq s
      on s.season = m.season
     and s.team_id = m.team_id
     and s.season_order_week < m.season_order_week
    group by 1, 2
)

select
    'ncaaf'                                                     as sport,

    -- ══ identity + situational context (all pregame-safe) ══════════════════════════════════
    g.game_id,
    g.season,
    g.week,                                    -- ⚠️ reporting only; never order/window on this
    g.season_order_week,                       -- ⭐ the as-of week the features are snapshot at
    g.season_type,
    g.is_postseason,
    g.game_date,
    g.start_date,
    g.home_team_id, g.home_team, g.home_conference,
    g.away_team_id, g.away_team, g.away_conference,
    g.is_conference_game,
    g.is_neutral_site,
    (g.home_conference = g.away_conference)                    as is_same_conference,
    r_home.rest_days                                           as home_rest_days,
    r_away.rest_days                                           as away_rest_days,
    r_home.rest_days - r_away.rest_days                        as rest_days_diff,

    -- ══ environment (travel/altitude — non-neutral only; NULL on neutral is honest, §7 gap 2) ══
    g.game_venue_elevation_m,
    g.game_venue_is_dome,
    g.game_venue_is_grass,
    g.game_venue_timezone,
    -- the away team's altitude change vs its own home venue (a real body-adjustment signal)
    case when g.is_neutral_site then null
         else g.game_venue_elevation_m - tv_away.venue_elevation_m end as away_altitude_change_m,
    -- the away team's travel distance to the game venue (great-circle km). Home travels ~0 at its
    -- own stadium; neutral-site venue geography is not attributed → NULL, not a wrong 0.
    case when g.is_neutral_site
              or tv_away.venue_latitude is null or tv_home.venue_latitude is null then null
         else 6371.0 * acos(least(1.0, greatest(-1.0,
                 sin(radians(tv_away.venue_latitude)) * sin(radians(tv_home.venue_latitude))
               + cos(radians(tv_away.venue_latitude)) * cos(radians(tv_home.venue_latitude))
                 * cos(radians(tv_home.venue_longitude - tv_away.venue_longitude)))))
    end                                                        as away_travel_km,

    -- ══════════════════════════════════════════════════════════════════════════════════════
    --  HOME TEAM FEATURES (as of season_order_week)
    -- ══════════════════════════════════════════════════════════════════════════════════════
    -- ── team strength (P1.2) — 1:1 on (season, team_id, as_of_week) ──
    hs.strength_margin                                         as home_strength_margin,
    hs.strength_margin_sd                                      as home_strength_margin_sd,
    hs.strength_offense                                        as home_strength_offense,
    hs.strength_defense                                        as home_strength_defense,
    hs.strength_conference_component                           as home_strength_conf_component,
    hs.strength_covariate_component                            as home_strength_cov_component,
    hs.strength_team_component                                 as home_strength_team_component,
    hs.covariate_component_roster_flux                         as home_strength_cov_roster_flux,
    hs.covariate_component_coaching                            as home_strength_cov_coaching,
    hs.covariate_component_talent                              as home_strength_cov_talent,
    hs.hyper_n_prior_seasons                                   as home_strength_hyper_prior_seasons,
    hs.has_sufficient_sample                                   as home_strength_has_sufficient_sample,
    -- ── raw efficiency (P1.1 rollup) ──
    hr.games_played                                            as home_games_played,
    hr.has_sufficient_sample                                   as home_has_sufficient_sample,
    hr.win_pct                                                 as home_win_pct,
    hr.points_for_per_game                                     as home_points_for_per_game,
    hr.points_against_per_game                                 as home_points_against_per_game,
    hr.margin_per_game                                         as home_margin_per_game,
    hr.off_ppa                                                 as home_off_ppa,
    hr.def_ppa                                                 as home_def_ppa,
    hr.off_success_rate                                        as home_off_success_rate,
    hr.def_success_rate                                        as home_def_success_rate,
    hr.off_explosiveness                                       as home_off_explosiveness,
    hr.def_explosiveness                                       as home_def_explosiveness,
    hr.off_clean_ppa                                           as home_off_clean_ppa,
    hr.def_clean_ppa                                           as home_def_clean_ppa,
    hr.off_clean_success_rate                                  as home_off_clean_success_rate,
    hr.def_clean_success_rate                                  as home_def_clean_success_rate,
    -- line/trench UNIT proxies (individual-OL is the confirmed gap)
    hr.off_line_yards                                          as home_off_line_yards,
    hr.def_line_yards                                          as home_def_line_yards,
    hr.off_stuff_rate                                          as home_off_stuff_rate,
    hr.def_stuff_rate                                          as home_def_stuff_rate,
    -- pace / style
    hr.off_plays_per_game                                      as home_off_plays_per_game,
    hr.possession_seconds_per_game                             as home_possession_seconds_per_game,
    hr.possession_seconds_per_game / nullif(hr.off_plays_per_game, 0) as home_seconds_per_play,
    -- box + drive quality
    hr.total_yards_per_game                                    as home_total_yards_per_game,
    hr.rushing_yards_per_game                                  as home_rushing_yards_per_game,
    hr.passing_yards_per_game                                  as home_passing_yards_per_game,
    hr.turnovers_per_game                                      as home_turnovers_per_game,
    hr.third_down_rate                                         as home_third_down_rate,
    hr.completion_rate                                         as home_completion_rate,
    hr.points_per_drive                                        as home_points_per_drive,
    hr.scoring_opportunity_rate                                as home_scoring_opportunity_rate,
    hr.three_and_out_rate                                      as home_three_and_out_rate,
    hr.explosive_drive_rate                                    as home_explosive_drive_rate,
    hr.avg_start_yards_to_goal                                 as home_avg_start_yards_to_goal,
    -- ── opponent-adjusted efficiency + strength of schedule (P1.1) ──
    ha.adj_off_ppa                                             as home_adj_off_ppa,
    ha.adj_def_ppa                                             as home_adj_def_ppa,
    ha.adj_net_ppa                                             as home_adj_net_ppa,
    ha.adj_off_success_rate                                    as home_adj_off_success_rate,
    ha.adj_def_success_rate                                    as home_adj_def_success_rate,
    ha.adj_points_for_per_game                                 as home_adj_points_for_per_game,
    ha.adj_points_against_per_game                             as home_adj_points_against_per_game,
    ha.sos_opponent_net_ppa                                    as home_sos_opponent_net_ppa,
    ha.has_reliable_adjustment                                 as home_has_reliable_adjustment,
    -- ── roster continuity / portal flux / talent (P0.4) — season-level, broadcast ──
    hc.returning_ppa_pct                                       as home_returning_ppa_pct,
    hc.returning_usage                                         as home_returning_usage,
    hc.roster_continuity_pct                                   as home_roster_continuity_pct,
    hc.roster_retention_pct                                    as home_roster_retention_pct,
    hc.portal_net_count                                        as home_portal_net_count,
    hc.portal_in_blue_chip                                     as home_portal_in_blue_chip,
    hc.portal_out_blue_chip                                    as home_portal_out_blue_chip,
    hc.team_talent                                             as home_team_talent,
    hc.team_talent_yoy_delta                                   as home_team_talent_yoy_delta,
    hc.portal_data_covered                                     as home_portal_data_covered,
    -- ── freshman prior (P1.2b) — season-level, broadcast ──
    hf.n_incoming_freshmen                                     as home_n_incoming_freshmen,
    hf.freshman_class_projected_production                     as home_freshman_proj_production,
    hf.freshman_class_top_projected_production                 as home_freshman_top_proj_production,
    hf.freshman_class_avg_rating                               as home_freshman_avg_rating,
    hf.blue_chip_count                                         as home_freshman_blue_chip_count,
    -- ── coaching (P0.5, HC-only) — season-level, broadcast ──
    hco.hc_tenure_years                                        as home_hc_tenure_years,
    hco.is_first_year_at_school                                as home_hc_first_year_at_school,
    hco.hc_change_from_prev                                    as home_hc_change_from_prev,
    hco.hc_prior_sp_overall_avg                                as home_hc_prior_sp_overall,
    hco.hc_prior_sp_offense_avg                                as home_hc_prior_sp_offense,
    hco.hc_prior_sp_defense_avg                                as home_hc_prior_sp_defense,
    hco.is_first_time_hc                                       as home_hc_is_first_time,
    -- ── QB continuity (derivable half; no CFB injury source) ──
    hq.qb_starts_prior                                         as home_qb_starts_prior,
    hq.qb_distinct_starters_prior                              as home_qb_distinct_starters_prior,
    hq.qb_starter_changed_recent                               as home_qb_starter_changed_recent,
    hq.qb_trailing_ypa                                         as home_qb_trailing_ypa,
    hq.qb_trailing_qbr                                         as home_qb_trailing_qbr,

    -- ══════════════════════════════════════════════════════════════════════════════════════
    --  AWAY TEAM FEATURES (as of season_order_week)
    -- ══════════════════════════════════════════════════════════════════════════════════════
    aws.strength_margin                                        as away_strength_margin,
    aws.strength_margin_sd                                     as away_strength_margin_sd,
    aws.strength_offense                                       as away_strength_offense,
    aws.strength_defense                                       as away_strength_defense,
    aws.strength_conference_component                          as away_strength_conf_component,
    aws.strength_covariate_component                           as away_strength_cov_component,
    aws.strength_team_component                                as away_strength_team_component,
    aws.covariate_component_roster_flux                        as away_strength_cov_roster_flux,
    aws.covariate_component_coaching                           as away_strength_cov_coaching,
    aws.covariate_component_talent                             as away_strength_cov_talent,
    aws.hyper_n_prior_seasons                                  as away_strength_hyper_prior_seasons,
    aws.has_sufficient_sample                                  as away_strength_has_sufficient_sample,
    ar.games_played                                            as away_games_played,
    ar.has_sufficient_sample                                  as away_has_sufficient_sample,
    ar.win_pct                                                 as away_win_pct,
    ar.points_for_per_game                                     as away_points_for_per_game,
    ar.points_against_per_game                                 as away_points_against_per_game,
    ar.margin_per_game                                         as away_margin_per_game,
    ar.off_ppa                                                 as away_off_ppa,
    ar.def_ppa                                                 as away_def_ppa,
    ar.off_success_rate                                        as away_off_success_rate,
    ar.def_success_rate                                        as away_def_success_rate,
    ar.off_explosiveness                                       as away_off_explosiveness,
    ar.def_explosiveness                                       as away_def_explosiveness,
    ar.off_clean_ppa                                           as away_off_clean_ppa,
    ar.def_clean_ppa                                           as away_def_clean_ppa,
    ar.off_clean_success_rate                                  as away_off_clean_success_rate,
    ar.def_clean_success_rate                                  as away_def_clean_success_rate,
    ar.off_line_yards                                          as away_off_line_yards,
    ar.def_line_yards                                          as away_def_line_yards,
    ar.off_stuff_rate                                          as away_off_stuff_rate,
    ar.def_stuff_rate                                          as away_def_stuff_rate,
    ar.off_plays_per_game                                      as away_off_plays_per_game,
    ar.possession_seconds_per_game                             as away_possession_seconds_per_game,
    ar.possession_seconds_per_game / nullif(ar.off_plays_per_game, 0) as away_seconds_per_play,
    ar.total_yards_per_game                                    as away_total_yards_per_game,
    ar.rushing_yards_per_game                                  as away_rushing_yards_per_game,
    ar.passing_yards_per_game                                  as away_passing_yards_per_game,
    ar.turnovers_per_game                                      as away_turnovers_per_game,
    ar.third_down_rate                                         as away_third_down_rate,
    ar.completion_rate                                         as away_completion_rate,
    ar.points_per_drive                                        as away_points_per_drive,
    ar.scoring_opportunity_rate                                as away_scoring_opportunity_rate,
    ar.three_and_out_rate                                      as away_three_and_out_rate,
    ar.explosive_drive_rate                                    as away_explosive_drive_rate,
    ar.avg_start_yards_to_goal                                 as away_avg_start_yards_to_goal,
    aa.adj_off_ppa                                             as away_adj_off_ppa,
    aa.adj_def_ppa                                             as away_adj_def_ppa,
    aa.adj_net_ppa                                             as away_adj_net_ppa,
    aa.adj_off_success_rate                                    as away_adj_off_success_rate,
    aa.adj_def_success_rate                                    as away_adj_def_success_rate,
    aa.adj_points_for_per_game                                 as away_adj_points_for_per_game,
    aa.adj_points_against_per_game                             as away_adj_points_against_per_game,
    aa.sos_opponent_net_ppa                                    as away_sos_opponent_net_ppa,
    aa.has_reliable_adjustment                                 as away_has_reliable_adjustment,
    ac.returning_ppa_pct                                       as away_returning_ppa_pct,
    ac.returning_usage                                         as away_returning_usage,
    ac.roster_continuity_pct                                   as away_roster_continuity_pct,
    ac.roster_retention_pct                                    as away_roster_retention_pct,
    ac.portal_net_count                                        as away_portal_net_count,
    ac.portal_in_blue_chip                                     as away_portal_in_blue_chip,
    ac.portal_out_blue_chip                                    as away_portal_out_blue_chip,
    ac.team_talent                                             as away_team_talent,
    ac.team_talent_yoy_delta                                   as away_team_talent_yoy_delta,
    ac.portal_data_covered                                     as away_portal_data_covered,
    af.n_incoming_freshmen                                     as away_n_incoming_freshmen,
    af.freshman_class_projected_production                     as away_freshman_proj_production,
    af.freshman_class_top_projected_production                 as away_freshman_top_proj_production,
    af.freshman_class_avg_rating                               as away_freshman_avg_rating,
    af.blue_chip_count                                         as away_freshman_blue_chip_count,
    aco.hc_tenure_years                                        as away_hc_tenure_years,
    aco.is_first_year_at_school                                as away_hc_first_year_at_school,
    aco.hc_change_from_prev                                    as away_hc_change_from_prev,
    aco.hc_prior_sp_overall_avg                                as away_hc_prior_sp_overall,
    aco.hc_prior_sp_offense_avg                                as away_hc_prior_sp_offense,
    aco.hc_prior_sp_defense_avg                                as away_hc_prior_sp_defense,
    aco.is_first_time_hc                                       as away_hc_is_first_time,
    aq.qb_starts_prior                                         as away_qb_starts_prior,
    aq.qb_distinct_starters_prior                              as away_qb_distinct_starters_prior,
    aq.qb_starter_changed_recent                               as away_qb_starter_changed_recent,
    aq.qb_trailing_ypa                                         as away_qb_trailing_ypa,
    aq.qb_trailing_qbr                                         as away_qb_trailing_qbr,

    -- ══ headline DIFFERENTIALS (home − away; the single-number reads P1.4 will reach for) ══
    hs.strength_margin - aws.strength_margin                  as strength_margin_diff,
    ha.adj_net_ppa - aa.adj_net_ppa                           as adj_net_ppa_diff,
    hc.team_talent - ac.team_talent                           as team_talent_diff,

    -- ══ ⛔ LABELS — POST-KICKOFF. The P1.4 TARGET, NEVER a feature. ══════════════════════════
    g.is_completed                                            as label_is_completed,
    g.home_points                                             as label_home_points,
    g.away_points                                             as label_away_points,
    g.total_points                                            as label_total_points,
    g.home_margin                                             as label_home_margin,
    case when not g.is_completed or g.is_tie then null
         when g.winning_team_id = g.home_team_id then true else false end as label_home_win

from games g
left join rest        r_home  on r_home.game_id = g.game_id and r_home.team_id = g.home_team_id
left join rest        r_away  on r_away.game_id = g.game_id and r_away.team_id = g.away_team_id
left join team_venue  tv_home on tv_home.team_id = g.home_team_id
                             and g.season between tv_home.valid_from_season
                                              and coalesce(tv_home.valid_to_season, 9999)
left join team_venue  tv_away on tv_away.team_id = g.away_team_id
                             and g.season between tv_away.valid_from_season
                                              and coalesce(tv_away.valid_to_season, 9999)
-- week-grained families: 1:1 on (season, team_id, as_of_week = this game's season_order_week)
left join {{ ref('rollup_ncaaf_team_week_asof') }} hr
       on hr.season = g.season and hr.team_id = g.home_team_id and hr.as_of_week = g.season_order_week
left join {{ ref('rollup_ncaaf_team_week_asof') }} ar
       on ar.season = g.season and ar.team_id = g.away_team_id and ar.as_of_week = g.season_order_week
left join {{ ref('rollup_ncaaf_team_week_opponent_adjusted') }} ha
       on ha.season = g.season and ha.team_id = g.home_team_id and ha.as_of_week = g.season_order_week
left join {{ ref('rollup_ncaaf_team_week_opponent_adjusted') }} aa
       on aa.season = g.season and aa.team_id = g.away_team_id and aa.as_of_week = g.season_order_week
left join {{ ref('ncaaf_team_strength_week') }} hs
       on hs.season = g.season and hs.team_id = g.home_team_id and hs.as_of_week = g.season_order_week
left join {{ ref('ncaaf_team_strength_week') }} aws
       on aws.season = g.season and aws.team_id = g.away_team_id and aws.as_of_week = g.season_order_week
-- season-grained families: BROADCAST across weeks on (season, team-name)
left join {{ ref('ncaaf_team_roster_continuity') }} hc on hc.season = g.season and hc.team = g.home_team
left join {{ ref('ncaaf_team_roster_continuity') }} ac on ac.season = g.season and ac.team = g.away_team
left join {{ ref('ncaaf_team_freshman_prior') }}    hf on hf.season = g.season and hf.team = g.home_team
left join {{ ref('ncaaf_team_freshman_prior') }}    af on af.season = g.season and af.team = g.away_team
left join {{ ref('ncaaf_team_coaching_change') }}   hco on hco.season = g.season and hco.team = g.home_team
left join {{ ref('ncaaf_team_coaching_change') }}   aco on aco.season = g.season and aco.team = g.away_team
-- QB continuity (keyed per matrix side on game_id + team_id)
left join qb_asof hq on hq.game_id = g.game_id and hq.team_id = g.home_team_id
left join qb_asof aq on aq.game_id = g.game_id and aq.team_id = g.away_team_id

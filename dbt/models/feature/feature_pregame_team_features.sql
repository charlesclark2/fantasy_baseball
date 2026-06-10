-- =============================================================================
-- feature_pregame_team_features.sql
-- Grain: one row per game_pk × team_abbrev (home and away)
-- Purpose: Pre-game team context features for ML. Joins rolling offense,
--          rolling pitching, platoon splits, season record, bullpen workload,
--          and bullpen effectiveness into a single team context row.
--
-- LEAKAGE GUARD: all rolling stat joins use game_date::date < spine.game_date::date
-- (strictly less than). Season record joins on record_date = game_date - 1.
-- Bullpen workload and effectiveness already use '1 day preceding' upper bounds
-- internally; they are joined directly on game_pk.
--
-- Column prefixes:
--   off_   rolling team offense (mart_team_rolling_offense)
--   pit_   rolling team pitching allowed (mart_team_rolling_pitching)
--   vs_lhp_ / vs_rhp_  platoon splits (mart_team_vs_pitcher_hand)
--   bp_    bullpen effectiveness (mart_bullpen_effectiveness)
--   bullpen workload columns retain their source names (no prefix)
-- =============================================================================

{{ config(materialized='table') }}

with

-- Spine: one row per game_pk × team; both teams per game
games as (
    -- A1.11 — spine on mart_game_spine (adds today's scheduled games); the
    -- rolling/platoon joins below are as-of (game_date < spine.game_date), so
    -- today's row carries forward each team's latest completed-game stats.
    select
        game_pk,
        game_date,
        game_year,
        home_team    as team_abbrev,
        'home'       as side,
        is_scheduled
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'

    union all

    select
        game_pk,
        game_date,
        game_year,
        away_team    as team_abbrev,
        'away'       as side,
        is_scheduled
    from {{ ref('mart_game_spine') }}
    where game_type = 'R'
),

-- ── Rolling offense (most recent pre-game row per game × team) ─────────────────
offense_ranked as (
    select
        g.game_pk,
        g.team_abbrev,
        ro.games_7d,
        ro.games_14d,
        ro.games_30d,
        ro.games_std,
        ro.runs_per_game_7d,
        ro.runs_per_game_14d,
        ro.runs_per_game_30d,
        ro.runs_per_game_std,
        ro.woba_7d,
        ro.woba_14d,
        ro.woba_30d,
        ro.woba_std,
        ro.xwoba_7d,
        ro.xwoba_14d,
        ro.xwoba_30d,
        ro.xwoba_std,
        ro.k_pct_7d,
        ro.k_pct_30d,
        ro.k_pct_std,
        ro.bb_pct_7d,
        ro.bb_pct_30d,
        ro.bb_pct_std,
        ro.hard_hit_pct_7d,
        ro.hard_hit_pct_30d,
        ro.hard_hit_pct_std,
        ro.barrel_pct_30d,
        ro.slugging_30d,
        row_number() over (
            partition by g.game_pk, g.team_abbrev
            order by ro.game_date::date desc
        ) as rn
    from games g
    left join {{ ref('mart_team_rolling_offense') }} ro
        on  ro.team            = g.team_abbrev
        and ro.game_date::date < g.game_date::date   -- LEAKAGE GUARD
),

offense_pre_game as (
    select * from offense_ranked where rn = 1
),

-- ── Rolling pitching (most recent pre-game row per game × team) ────────────────
pitching_ranked as (
    select
        g.game_pk,
        g.team_abbrev,
        rp.runs_allowed_per_game_7d,
        rp.runs_allowed_per_game_14d,
        rp.runs_allowed_per_game_30d,
        rp.runs_allowed_per_game_std,
        rp.woba_against_7d,
        rp.woba_against_14d,
        rp.woba_against_30d,
        rp.woba_against_std,
        rp.xwoba_against_7d,
        rp.xwoba_against_14d,
        rp.xwoba_against_30d,
        rp.xwoba_against_std,
        rp.k_pct_7d,
        rp.k_pct_30d,
        rp.k_pct_std,
        rp.bb_pct_7d,
        rp.bb_pct_30d,
        rp.bb_pct_std,
        rp.hard_hit_pct_allowed_7d,
        rp.hard_hit_pct_allowed_30d,
        rp.hard_hit_pct_allowed_std,
        rp.barrel_pct_allowed_30d,
        row_number() over (
            partition by g.game_pk, g.team_abbrev
            order by rp.game_date::date desc
        ) as rn
    from games g
    left join {{ ref('mart_team_rolling_pitching') }} rp
        on  rp.team            = g.team_abbrev
        and rp.game_date::date < g.game_date::date   -- LEAKAGE GUARD
),

pitching_pre_game as (
    select * from pitching_ranked where rn = 1
),

-- ── Platoon splits vs LHP (most recent pre-game row) ──────────────────────────
vs_lhp_ranked as (
    select
        g.game_pk,
        g.team_abbrev,
        vh.woba_30d,
        vh.xwoba_30d,
        vh.k_pct_30d,
        vh.bb_pct_30d,
        vh.hard_hit_pct_30d,
        vh.slugging_30d,
        vh.woba_std,
        vh.xwoba_std,
        row_number() over (
            partition by g.game_pk, g.team_abbrev
            order by vh.game_date::date desc
        ) as rn
    from games g
    left join {{ ref('mart_team_vs_pitcher_hand') }} vh
        on  vh.team             = g.team_abbrev
        and vh.opp_starter_hand = 'L'
        and vh.game_date::date  < g.game_date::date   -- LEAKAGE GUARD
),

vs_lhp_pre_game as (
    select * from vs_lhp_ranked where rn = 1
),

-- ── Platoon splits vs RHP (most recent pre-game row) ──────────────────────────
vs_rhp_ranked as (
    select
        g.game_pk,
        g.team_abbrev,
        vh.woba_30d,
        vh.xwoba_30d,
        vh.k_pct_30d,
        vh.bb_pct_30d,
        vh.hard_hit_pct_30d,
        vh.slugging_30d,
        vh.woba_std,
        vh.xwoba_std,
        row_number() over (
            partition by g.game_pk, g.team_abbrev
            order by vh.game_date::date desc
        ) as rn
    from games g
    left join {{ ref('mart_team_vs_pitcher_hand') }} vh
        on  vh.team             = g.team_abbrev
        and vh.opp_starter_hand = 'R'
        and vh.game_date::date  < g.game_date::date   -- LEAKAGE GUARD
),

vs_rhp_pre_game as (
    select * from vs_rhp_ranked where rn = 1
),

-- ── Season record as of the day before the game ───────────────────────────────
-- A1.11 Stage 4 — exact "day-before" record for completed games (byte-for-byte
-- unchanged), as-of latest prior record for today's SCHEDULED games. The old
-- join required record_date to equal EXACTLY game_date-1; for a not-yet-played
-- game that demands a record row dated yesterday, which is absent whenever
-- mart_team_season_record is even a day stale (or the team had an off-day), so
-- the whole standings + season-pythagorean block (wins/losses/games_back/streak/
-- pythagorean_win_exp/pythagorean_residual_season) went NULL for today. Gating on
-- is_scheduled keeps historical rows on the exact day-before record (their value,
-- incl. intentional early-season NULLs, is preserved); scheduled games carry the
-- team's latest available record forward. Mirrors the pythagorean_30d branch below.
season_record as (
    select
        g.game_pk,
        g.team_abbrev,
        tsr.wins,
        tsr.losses,
        tsr.games_played,
        tsr.win_pct,
        tsr.pythagorean_win_exp,
        tsr.pythagorean_residual_season,   -- Card 8.X
        tsr.games_back,
        tsr.streak_direction,
        tsr.streak_length
    from games g
    left join {{ ref('mart_team_season_record') }} tsr
        on  tsr.team_abbrev = g.team_abbrev
        and (
            (not g.is_scheduled and tsr.record_date = dateadd('day', -1, g.game_date::date))
            or (g.is_scheduled and tsr.record_date::date < g.game_date::date)
        )
    qualify row_number() over (
        partition by g.game_pk, g.team_abbrev
        order by tsr.record_date::date desc nulls last
    ) = 1
),

-- ── Pythagorean rolling residual (trailing 30 days, pre-game) ─────────────────
-- Card 8.X. Leakage guard already enforced inside the mart's window.
-- A1.11 — exact pre-game row for completed games (byte-for-byte unchanged);
-- as-of latest prior row for today's SCHEDULED games (which have no exact row,
-- as this mart is results-derived). The branch is gated on is_scheduled so
-- historical rows keep their exact value (incl. intentional <10-game NULLs).
pythagorean_30d as (
    select
        g.game_pk,
        g.team_abbrev,
        pr.pythagorean_residual_30d
    from games g
    left join {{ ref('mart_team_pythagorean_rolling') }} pr
        on  pr.team_abbrev = g.team_abbrev
        and (
            (not g.is_scheduled and pr.game_pk = g.game_pk)
            or (g.is_scheduled and pr.game_date::date < g.game_date::date)
        )
    qualify row_number() over (
        partition by g.game_pk, g.team_abbrev
        order by iff(pr.game_pk = g.game_pk, 1, 0) desc, pr.game_date::date desc nulls last
    ) = 1
),

-- ── Bullpen workload / effectiveness (A1.11 exact-or-as-of) ───────────────────
-- These two marts are pitch-derived (completed games only), so today's
-- scheduled games can never have an exact row. Same pattern as pythagorean:
-- exact game_pk row for completed games (unchanged); for scheduled games carry
-- forward the team's most recent prior row (matches the A1.8 assembly's
-- carry-forward semantics so the feature_store path reaches coverage parity).
bullpen_workload_resolved as (
    select
        g.game_pk,
        g.team_abbrev,
        bw.bullpen_pitches_prev_1d,
        bw.bullpen_pitches_prev_3d,
        bw.bullpen_pitches_prev_7d,
        bw.pitchers_used_prev_3d,
        bw.pitchers_used_prev_7d,
        bw.reliever_appearances_prev_3d,
        bw.reliever_appearances_prev_7d,
        bw.high_leverage_used_prev_2d,
        bw.closer_used_prev_1d,
        bw.closer_used_prev_2d,
        bw.bullpen_ip_prev_1d,
        bw.bullpen_ip_prev_2d,
        bw.pitchers_used_prev_2d
    from games g
    left join {{ ref('mart_bullpen_workload') }} bw
        on  bw.pitching_team = g.team_abbrev
        and (
            (not g.is_scheduled and bw.game_pk = g.game_pk)
            or (g.is_scheduled and bw.game_date::date < g.game_date::date)
        )
    qualify row_number() over (
        partition by g.game_pk, g.team_abbrev
        order by iff(bw.game_pk = g.game_pk, 1, 0) desc, bw.game_date::date desc nulls last
    ) = 1
),

bullpen_effectiveness_resolved as (
    select
        g.game_pk,
        g.team_abbrev,
        be.k_pct_14d,
        be.bb_pct_14d,
        be.xwoba_against_14d,
        be.hard_hit_pct_14d,
        be.whiff_rate_14d,
        be.innings_pitched_14d,
        be.k_pct_30d,
        be.bb_pct_30d,
        be.xwoba_against_30d,
        be.hard_hit_pct_30d,
        be.whiff_rate_30d,
        be.innings_pitched_30d,
        be.eb_bullpen_xwoba,
        be.eb_bullpen_uncertainty,
        be.eb_bullpen_coverage_pct
    from games g
    left join {{ ref('mart_bullpen_effectiveness') }} be
        on  be.team_abbrev = g.team_abbrev
        and (
            (not g.is_scheduled and be.game_pk = g.game_pk)
            or (g.is_scheduled and be.game_date::date < g.game_date::date)
        )
    qualify row_number() over (
        partition by g.game_pk, g.team_abbrev
        order by iff(be.game_pk = g.game_pk, 1, 0) desc, be.game_date::date desc nulls last
    ) = 1
),

-- ── Elo rating as of before this game (Card 8.D) ─────────────────────────────
elo_ratings as (
    select
        game_pk,
        team_abbrev,
        elo_before_game
    from {{ source('betting', 'team_elo_history') }}
),

final as (
    select
        g.game_pk,
        g.game_date::date                       as game_date,
        g.game_year,
        g.team_abbrev,
        g.side,

        -- ── Season record ─────────────────────────────────────────────────────
        sr.wins,
        sr.losses,
        sr.games_played,
        sr.win_pct,
        sr.pythagorean_win_exp,
        sr.pythagorean_residual_season,         -- Card 8.X
        py30.pythagorean_residual_30d,          -- Card 8.X
        sr.games_back,
        sr.streak_direction,
        sr.streak_length,

        -- ── Rolling offense ───────────────────────────────────────────────────
        off.runs_per_game_7d                    as off_runs_per_game_7d,
        off.runs_per_game_14d                   as off_runs_per_game_14d,
        off.runs_per_game_30d                   as off_runs_per_game_30d,
        off.runs_per_game_std                   as off_runs_per_game_std,
        off.woba_7d                             as off_woba_7d,
        off.woba_14d                            as off_woba_14d,
        off.woba_30d                            as off_woba_30d,
        off.woba_std                            as off_woba_std,
        off.xwoba_7d                            as off_xwoba_7d,
        off.xwoba_14d                           as off_xwoba_14d,
        off.xwoba_30d                           as off_xwoba_30d,
        off.xwoba_std                           as off_xwoba_std,
        off.k_pct_7d                            as off_k_pct_7d,
        off.k_pct_30d                           as off_k_pct_30d,
        off.k_pct_std                           as off_k_pct_std,
        off.bb_pct_7d                           as off_bb_pct_7d,
        off.bb_pct_30d                          as off_bb_pct_30d,
        off.bb_pct_std                          as off_bb_pct_std,
        off.hard_hit_pct_7d                     as off_hard_hit_pct_7d,
        off.hard_hit_pct_30d                    as off_hard_hit_pct_30d,
        off.hard_hit_pct_std                    as off_hard_hit_pct_std,
        off.barrel_pct_30d                      as off_barrel_pct_30d,
        off.slugging_30d                        as off_slugging_30d,

        -- ── Rolling pitching allowed ──────────────────────────────────────────
        pit.runs_allowed_per_game_7d            as pit_runs_allowed_7d,
        pit.runs_allowed_per_game_14d           as pit_runs_allowed_14d,
        pit.runs_allowed_per_game_30d           as pit_runs_allowed_30d,
        pit.runs_allowed_per_game_std           as pit_runs_allowed_std,
        pit.woba_against_7d                     as pit_woba_against_7d,
        pit.woba_against_14d                    as pit_woba_against_14d,
        pit.woba_against_30d                    as pit_woba_against_30d,
        pit.woba_against_std                    as pit_woba_against_std,
        pit.xwoba_against_7d                    as pit_xwoba_against_7d,
        pit.xwoba_against_14d                   as pit_xwoba_against_14d,
        pit.xwoba_against_30d                   as pit_xwoba_against_30d,
        pit.xwoba_against_std                   as pit_xwoba_against_std,
        pit.k_pct_7d                            as pit_k_pct_7d,
        pit.k_pct_30d                           as pit_k_pct_30d,
        pit.k_pct_std                           as pit_k_pct_std,
        pit.bb_pct_7d                           as pit_bb_pct_7d,
        pit.bb_pct_30d                          as pit_bb_pct_30d,
        pit.bb_pct_std                          as pit_bb_pct_std,
        pit.hard_hit_pct_allowed_7d             as pit_hard_hit_pct_7d,
        pit.hard_hit_pct_allowed_30d            as pit_hard_hit_pct_30d,
        pit.hard_hit_pct_allowed_std            as pit_hard_hit_pct_std,
        pit.barrel_pct_allowed_30d              as pit_barrel_pct_30d,

        -- ── Platoon splits vs LHP ─────────────────────────────────────────────
        lhp.woba_30d                            as vs_lhp_woba_30d,
        lhp.xwoba_30d                           as vs_lhp_xwoba_30d,
        lhp.k_pct_30d                           as vs_lhp_k_pct_30d,
        lhp.bb_pct_30d                          as vs_lhp_bb_pct_30d,
        lhp.hard_hit_pct_30d                    as vs_lhp_hard_hit_pct_30d,
        lhp.slugging_30d                        as vs_lhp_slugging_30d,
        lhp.woba_std                            as vs_lhp_woba_std,
        lhp.xwoba_std                           as vs_lhp_xwoba_std,

        -- ── Platoon splits vs RHP ─────────────────────────────────────────────
        rhp.woba_30d                            as vs_rhp_woba_30d,
        rhp.xwoba_30d                           as vs_rhp_xwoba_30d,
        rhp.k_pct_30d                           as vs_rhp_k_pct_30d,
        rhp.bb_pct_30d                          as vs_rhp_bb_pct_30d,
        rhp.hard_hit_pct_30d                    as vs_rhp_hard_hit_pct_30d,
        rhp.slugging_30d                        as vs_rhp_slugging_30d,
        rhp.woba_std                            as vs_rhp_woba_std,
        rhp.xwoba_std                           as vs_rhp_xwoba_std,

        -- ── Bullpen workload (preceding-day predictors only) ──────────────────
        bw.bullpen_pitches_prev_1d,
        bw.bullpen_pitches_prev_3d,
        bw.bullpen_pitches_prev_7d,
        bw.pitchers_used_prev_3d,
        bw.pitchers_used_prev_7d,
        bw.reliever_appearances_prev_3d,
        bw.reliever_appearances_prev_7d,
        bw.high_leverage_used_prev_2d,
        bw.closer_used_prev_1d,
        bw.closer_used_prev_2d,
        bw.bullpen_ip_prev_1d,
        bw.bullpen_ip_prev_2d,
        bw.pitchers_used_prev_2d,

        -- ── Schedule context ──────────────────────────────────────────────────
        sc.days_rest,
        sc.games_last_7d,
        sc.games_last_14d,
        sc.consecutive_home_games,
        sc.consecutive_away_games,
        sc.tz_changed_from_last_game,

        -- ── Bullpen effectiveness (14d / 30d rolling, current-game excluded) ──
        be.k_pct_14d                            as bp_k_pct_14d,
        be.bb_pct_14d                           as bp_bb_pct_14d,
        be.xwoba_against_14d                    as bp_xwoba_against_14d,
        be.hard_hit_pct_14d                     as bp_hard_hit_pct_14d,
        be.whiff_rate_14d                       as bp_whiff_rate_14d,
        be.innings_pitched_14d                  as bp_innings_pitched_14d,
        be.k_pct_30d                            as bp_k_pct_30d,
        be.bb_pct_30d                           as bp_bb_pct_30d,
        be.xwoba_against_30d                    as bp_xwoba_against_30d,
        be.hard_hit_pct_30d                     as bp_hard_hit_pct_30d,
        be.whiff_rate_30d                       as bp_whiff_rate_30d,
        be.innings_pitched_30d                  as bp_innings_pitched_30d,

        -- ── Empirical Bayes bullpen estimates (Epic 6A) ───────────────────────
        be.eb_bullpen_xwoba                     as bp_eb_xwoba,
        be.eb_bullpen_uncertainty               as bp_eb_uncertainty,
        be.eb_bullpen_coverage_pct              as bp_eb_coverage_pct,

        -- ── Momentum deltas: 7-day minus 30-day (positive = trending up) ─────
        off.woba_7d - off.woba_30d                   as off_woba_7d_minus_30d,
        pit.xwoba_against_7d - pit.xwoba_against_30d as pit_xwoba_7d_minus_30d,

        -- ── Sample size flags: games played in each rolling window ────────────
        off.games_7d                                 as off_games_played_7d,
        off.games_14d                                as off_games_played_14d,
        off.games_30d                                as off_games_played_30d,
        off.games_std                                as off_games_played_std,

        -- ── Elo team strength rating (Card 8.D) ──────────────────────────────
        -- Pre-game snapshot; NULL until compute_elo.py backfill is run.
        er.elo_before_game                           as elo_rating,

        -- ── Defensive fielding quality (Card 8.C) ────────────────────────────
        -- Prior-season OAA from FanGraphs (season-level; leakage-free).
        -- NULL for games before 2017 (first year 2016 OAA is available as prior).
        -- Coalesced to 0 (league average) in team_oaa_blended.
        fo.team_oaa_prior_season,
        fo.team_oaa_blended

    from games g
    left join offense_pre_game off
        on  off.game_pk     = g.game_pk
        and off.team_abbrev = g.team_abbrev
    left join pitching_pre_game pit
        on  pit.game_pk     = g.game_pk
        and pit.team_abbrev = g.team_abbrev
    left join vs_lhp_pre_game lhp
        on  lhp.game_pk     = g.game_pk
        and lhp.team_abbrev = g.team_abbrev
    left join vs_rhp_pre_game rhp
        on  rhp.game_pk     = g.game_pk
        and rhp.team_abbrev = g.team_abbrev
    left join season_record sr
        on  sr.game_pk      = g.game_pk
        and sr.team_abbrev  = g.team_abbrev
    left join pythagorean_30d py30
        on  py30.game_pk     = g.game_pk
        and py30.team_abbrev = g.team_abbrev
    left join bullpen_workload_resolved bw
        on  bw.team_abbrev   = g.team_abbrev
        and bw.game_pk       = g.game_pk
    left join bullpen_effectiveness_resolved be
        on  be.team_abbrev   = g.team_abbrev
        and be.game_pk       = g.game_pk
    left join {{ ref('mart_team_schedule_context') }} sc
        on  sc.team_abbrev   = g.team_abbrev
        and sc.game_pk       = g.game_pk
    left join elo_ratings er
        on  er.team_abbrev   = g.team_abbrev
        and er.game_pk       = g.game_pk
    left join {{ ref('mart_team_fielding_oaa') }} fo
        on  fo.team_abbrev   = g.team_abbrev
        and fo.game_pk       = g.game_pk
)

select * from final

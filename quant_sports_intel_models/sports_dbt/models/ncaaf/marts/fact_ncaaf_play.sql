-- fact_ncaaf_play — the play fact (NCAAF-P1.1). The finest grain in the model.
--
-- GRAIN: one row per play. ~1.7M FBS-vs-FBS plays over 2014–2025 — the atom every derived
-- efficiency metric decomposes to, and the only place a bespoke split (garbage time, red zone,
-- 3rd-and-long, tempo) can be computed without re-deriving it from raw JSON.
--
-- ⭐ FBS-FILTERED (both sides FBS, via dim_ncaaf_game) + SPORT-TAGGED.
-- The play-level derivations (`is_successful_play`, `is_scrimmage_play`, `is_passing_down`) are
-- defined in stg_ncaaf_plays — ONE definition, applied everywhere. This model adds the
-- game-context derivations that need the dimension: score state and garbage time.
--
-- ⭐ GARBAGE TIME (`is_garbage_time`) is the single most important filter here and it is NOT
-- optional hygiene — a blowout's fourth quarter is played by backups against a prevent defense,
-- and including it systematically inflates the losing team's efficiency and deflates the winner's.
-- The standard CFB thresholds are applied (score margin by quarter):
--     Q1 > 43 · Q2 > 37 · Q3 > 27 · Q4 > 22
-- The plays are FLAGGED, never dropped — the rollups exclude them, but anything that genuinely
-- wants the full game (drive charting, situational counts) still can.
--
-- ⚠️ `wallclock` stays VARCHAR (INC-23: raw stays VARCHAR, the reader casts at the use-site).
-- ⚠️ POST-KICKOFF outcome fact.
--
-- 🧯 MEMORY: same pin as stg_ncaaf_game_player_stats — this is the other million-row model, and
-- the joins to two dimensions on top of a 1.7M-row scan OOM the default 4 GB / 4-thread profile.
{{ config(
    materialized='table',
    pre_hook=[
        "SET preserve_insertion_order = false",
        "SET threads = 1"
    ],
    post_hook=[
        "SET preserve_insertion_order = true",
        "SET threads = " ~ env_var('SPORTS_DUCKDB_THREADS', '4')
    ]
) }}

with games as (
    select game_id, season, week, season_order_week, season_type, game_date, is_neutral_site,
           is_conference_game, is_postseason
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup            -- ⭐ the modelling universe
),

plays as (
    select * from {{ ref('stg_ncaaf_plays') }}
),

teams as (
    select team_id, team, valid_from_season, valid_to_season
    from {{ ref('dim_ncaaf_team') }}
)

select
    'ncaaf'                                              as sport,
    p.play_id,
    'ncaaf-' || p.play_id                                as play_key,
    p.game_id,
    p.drive_id,
    g.season,
    g.week,
    g.season_order_week,
    g.season_type,
    g.game_date,
    p.drive_number,
    p.play_number,

    -- ── participants (point-in-time resolved team ids) ────────────────────────────────
    p.offense_team,
    ot.team_id                                           as offense_team_id,
    p.offense_conference,
    p.defense_team,
    dt.team_id                                           as defense_team_id,
    p.defense_conference,
    (p.offense_team = p.home_team)                       as is_home_offense,

    -- ── situation ─────────────────────────────────────────────────────────────────────
    p.period,
    p.clock_seconds_remaining,
    p.down,
    p.distance,
    p.yardline,
    p.yards_to_goal,
    p.yards_gained,
    p.offense_score,
    p.defense_score,
    (p.offense_score - p.defense_score)                  as offense_score_margin,
    (p.yards_to_goal is not null and p.yards_to_goal <= 20) as is_red_zone,

    -- ── play classification (defined once in staging) ─────────────────────────────────
    p.play_type,
    p.play_text,
    p.is_scrimmage_play,
    p.is_pass_play,
    p.is_rush_play,
    p.is_passing_down,
    p.is_scoring_play,
    p.is_successful_play,
    p.ppa,

    -- ── ⭐ garbage time (standard CFB margin-by-quarter thresholds; see header) ────────
    case
        when p.period = 1 then abs(p.offense_score - p.defense_score) > 43
        when p.period = 2 then abs(p.offense_score - p.defense_score) > 37
        when p.period = 3 then abs(p.offense_score - p.defense_score) > 27
        when p.period >= 4 then abs(p.offense_score - p.defense_score) > 22
        else false
    end                                                  as is_garbage_time,

    p.wallclock                                          -- ISO VARCHAR (INC-23)
from plays p
join games g on g.game_id = p.game_id
left join teams ot
    on ot.team = p.offense_team
   and g.season between ot.valid_from_season and coalesce(ot.valid_to_season, 9999)
left join teams dt
    on dt.team = p.defense_team
   and g.season between dt.valid_from_season and coalesce(dt.valid_to_season, 9999)

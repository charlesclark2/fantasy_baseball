-- stg_nfl_pbp — the play-by-play staging (NFL-N1.0). The atom every team-game efficiency metric
-- (EPA / success / explosiveness / pace) in fct_nfl_team_game decomposes to.
--
-- nflverse pbp is TYPED release Parquet (~372 cols) → plain renames, NO json_extract. This model
-- keeps only the ~40 columns the team-game layer needs and defines the play CLASSIFICATIONS ONCE
-- (is_scrimmage_play / is_pass_play / is_rush_play / is_success / is_explosive / is_garbage_time)
-- so no two consumers can disagree on a definition — the NCAAF stg_ncaaf_plays discipline.
--
-- ⭐ EPA/success/wp are ALREADY on the raw play (nflverse computes them) — this is a read, not a
-- re-derivation. `epa` = expected points added, `success` = (epa > 0), `wp` = posteam win prob.
--
-- ⭐ GARBAGE TIME = win-prob outside [0.05, 0.95] (the standard nflverse filter). A blowout's
-- late plays are backups vs a prevent defense and systematically distort efficiency, so the
-- rollups exclude them — but they are FLAGGED here, never dropped (drive/situational counts still
-- want the full game). A NULL wp (rare, malformed play) is treated as NOT garbage (kept).
--
-- ⚠️ game_date stays VARCHAR (INC-23: raw stays VARCHAR, the reader casts at the use-site).
-- 🧯 MEMORY: 1.28M plays over delta_scan from S3 → pin DuckDB to 1 thread during the build so a
-- parallel scan can't blow the box's DuckDB memory budget (the NCAAF fact_ncaaf_play pattern).
{{ config(
    materialized='table',
    pre_hook="SET threads = 1",
    post_hook="SET threads = " ~ env_var('SPORTS_DUCKDB_THREADS', '4')
) }}

with src as (
    select * from {{ nfl_delta('pbp') }}
    where game_id is not null
      and play_id is not null
)

select
    'nfl'                                               as sport,
    game_id,
    md5(game_id || '-' || play_id::varchar)             as play_key,
    play_id,
    season,
    week,                                               -- monotone within season (verified N1.0)
    season_type,
    game_date,                                          -- ISO VARCHAR (INC-23)
    -- team codes normalized to the canonical franchise (matches stg_nfl_schedules)
    {{ nfl_team_norm('home_team') }}                    as home_team,
    {{ nfl_team_norm('away_team') }}                    as away_team,
    {{ nfl_team_norm('posteam') }}                      as posteam,
    {{ nfl_team_norm('defteam') }}                      as defteam,
    posteam_type,

    -- situation
    qtr,
    down,
    ydstogo,
    yardline_100,
    goal_to_go,
    play_type,
    yards_gained,
    shotgun,
    no_huddle,
    qb_dropback,
    fixed_drive,
    score_differential,
    wp,
    vegas_wp,

    -- ── outcome / efficiency (already computed on the raw play) ──────────────────────
    epa,
    qb_epa,
    wpa,
    success,                                            -- nflverse: (epa > 0)
    touchdown,
    first_down,
    interception,
    fumble_lost,
    penalty,
    sack,

    -- ── play classifications, defined ONCE (the whole reason this staging exists) ─────
    (coalesce(play_type, '') in ('run', 'pass'))        as is_scrimmage_play,
    (coalesce(pass, 0) = 1)                             as is_pass_play,
    (coalesce(rush, 0) = 1)                             as is_rush_play,
    (coalesce(success, 0) = 1)                          as is_success,
    -- explosive: 10+ rush yards OR 20+ pass yards (standard NFL thresholds)
    case
        when coalesce(rush, 0) = 1 and yards_gained >= 10 then true
        when coalesce(pass, 0) = 1 and yards_gained >= 20 then true
        else false
    end                                                 as is_explosive,
    -- ⭐ garbage time: posteam win prob outside [0.05, 0.95]; NULL wp → not garbage (kept)
    (wp is not null and (wp < 0.05 or wp > 0.95))       as is_garbage_time
from src

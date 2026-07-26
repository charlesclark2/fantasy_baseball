-- stg_nfl_sleeper_injuries — Sleeper `v1/players/nfl` forward-availability snapshot (NF-D5).
--
-- Sibling to stg_nfl_injuries (nflverse's IN-SEASON-ONLY weekly injury report), but sourced from
-- Sleeper's free player feed, which surfaces offseason surgery/PUP/IR designations MONTHS before
-- nflverse publishes. `proj_status` is already mapped to the shared RES/PUP/NFI/SUS vocabulary at
-- ingest time (`sleeper_injuries_source.map_injury_status`) — weekly game-report tags
-- (Questionable/Doubtful/Out) are deliberately left unmapped (NF-D2 slice 5 already found that
-- channel weak/confounded; this feed stays scoped to the forward long-absence signal).
-- `player_id` is Sleeper's own native gsis_id, backfilled at ingest by a deterministic (name,
-- position) crosswalk when Sleeper's own gsis_id is null. A snapshot table (no week grain) —
-- `run_sleeper_injuries_ingest.py` overwrites the current season's Delta partition on each
-- (daily, through camp) capture, so `ingested_at desc` picks the freshest row per player.
select
    'nfl'                          as sport,
    season,
    sleeper_player_id,
    player_id,
    player_name,
    position,
    team,
    gsis_id                        as sleeper_native_gsis_id,
    injury_status,
    injury_body_part,
    proj_status,
    ingested_at
from {{ nfl_delta('sleeper_injuries') }}
where player_id is not null

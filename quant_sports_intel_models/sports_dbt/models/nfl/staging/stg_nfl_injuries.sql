-- stg_nfl_injuries — weekly injury report/practice status (nflverse injuries), NFL-N0.2.
--
-- ⭐ the net-new high-leverage NFL status feed — CLV moves on report_status (Out/Doubtful/
-- Questionable). Typed Delta → plain renames. Keyed gsis_id + season/week. 2009+. Weekly
-- in-season cadence (N0.4 wires the intraday schedule + the props name→gsis resolver).
select
    'nfl'                          as sport,
    season,
    game_type                      as season_type,
    week,
    team,
    gsis_id,
    full_name                      as player_name,
    position,
    report_primary_injury,
    report_secondary_injury,
    report_status,
    practice_primary_injury,
    practice_secondary_injury,
    practice_status,
    date_modified
from {{ nfl_delta('injuries') }}
where gsis_id is not null

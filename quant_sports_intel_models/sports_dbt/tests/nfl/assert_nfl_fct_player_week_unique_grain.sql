-- GRAIN GUARD (2026-07-24): fct_player_week must be UNIQUE on (player_id, season, week).
-- A duplicate grain is the "36-game season" corruption class — a fan-out from a dim_player dupe or
-- an overlapping dim_player_role window doubling a player's every stat line. Fails (rows > 0) if any
-- player-week appears more than once.
select player_id, season, week, count(*) as n
from {{ ref('fct_player_week') }}
group by 1, 2, 3
having count(*) > 1

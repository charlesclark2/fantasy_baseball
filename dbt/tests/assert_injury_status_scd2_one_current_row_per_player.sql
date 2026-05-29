-- SCD-2 invariant: each player_id must have at most one is_current = TRUE row.
-- Returns player_ids with more than one current row.
-- Expects 0 rows.

select
    player_id,
    count(*) as current_row_count
from {{ ref('feature_pregame_injury_status') }}
where is_current = true
group by player_id
having count(*) > 1

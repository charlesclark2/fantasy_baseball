-- SCD-2 invariant: each (game_pk, side) must have at most one is_current = TRUE row.
select game_pk, side, count(*) as current_row_count
from {{ ref('feature_pregame_starter_status') }}
where is_current = true
group by game_pk, side
having count(*) > 1

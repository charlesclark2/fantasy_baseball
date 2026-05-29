-- Fail if any venue has more than one is_current = true row.
select venue_id, count(*) as current_row_count
from {{ ref('feature_pregame_park_status') }}
where is_current = true
group by venue_id
having count(*) > 1

-- Fail if is_current and valid_to are inconsistent:
--   is_current = true  must have valid_to IS NULL
--   is_current = false must have valid_to IS NOT NULL
select *
from {{ ref('feature_pregame_park_status') }}
where (is_current = true  and valid_to is not null)
   or (is_current = false and valid_to is null)

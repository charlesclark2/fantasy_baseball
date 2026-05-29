-- SCD-2 invariant: is_current = TRUE iff valid_to IS NULL.
-- Returns rows that violate either direction of the invariant.
-- Expects 0 rows.

select *
from {{ ref('feature_pregame_injury_status') }}
where
    (is_current = true  and valid_to is not null)
    or
    (is_current = false and valid_to is null)

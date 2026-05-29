-- SCD-2 invariant: is_current = TRUE iff valid_to IS NULL.
-- Any violation means the is_current flag is inconsistent with the interval.
select *
from {{ ref('feature_pregame_starter_status') }}
where
    (is_current = true  and valid_to is not null)
    or
    (is_current = false and valid_to is null)

-- SCD-2 invariant: no two rows for the same player_id should have overlapping
-- [valid_from, valid_to) intervals. Two intervals [a,b) and [c,d) overlap when
-- a < d AND c < b (treating NULL valid_to as +infinity).
-- Expects 0 rows.

select
    a.player_id,
    a.valid_from     as a_valid_from,
    a.valid_to       as a_valid_to,
    b.valid_from     as b_valid_from,
    b.valid_to       as b_valid_to
from {{ ref('feature_pregame_injury_status') }} a
join {{ ref('feature_pregame_injury_status') }} b
    on  a.player_id   = b.player_id
    and a.valid_from  < b.valid_from    -- b starts after a; avoids self-match and duplicates
    and (
            a.valid_to is null          -- a is open-ended → always overlaps a later interval
            or a.valid_to > b.valid_from
        )

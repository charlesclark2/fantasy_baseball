-- Fail if any two rows for the same venue have overlapping valid_from/valid_to intervals.
select
    a.venue_id,
    a.season          as a_season,
    a.valid_from      as a_valid_from,
    a.valid_to        as a_valid_to,
    b.season          as b_season,
    b.valid_from      as b_valid_from,
    b.valid_to        as b_valid_to
from {{ ref('feature_pregame_park_status') }} a
join {{ ref('feature_pregame_park_status') }} b
    on  a.venue_id   = b.venue_id
    and a.valid_from < b.valid_from
    and (a.valid_to is null or a.valid_to > b.valid_from)

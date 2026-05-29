-- SCD-2 invariant: no two rows for the same (game_pk, side) should have
-- overlapping [valid_from, valid_to) intervals.
select
    a.game_pk,
    a.side,
    a.valid_from,
    a.valid_to,
    b.valid_from as b_valid_from,
    b.valid_to   as b_valid_to
from {{ ref('feature_pregame_starter_status') }} a
join {{ ref('feature_pregame_starter_status') }} b
    on  a.game_pk    = b.game_pk
    and a.side       = b.side
    and a.valid_from < b.valid_from
    and (
            a.valid_to is null
            or a.valid_to > b.valid_from
        )

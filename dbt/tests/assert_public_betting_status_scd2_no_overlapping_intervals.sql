select a.game_pk, a.valid_from, a.valid_to, b.valid_from as b_valid_from, b.valid_to as b_valid_to
from {{ ref('feature_pregame_public_betting_status') }} a
join {{ ref('feature_pregame_public_betting_status') }} b
    on  a.game_pk    = b.game_pk
    and a.valid_from < b.valid_from
    and (a.valid_to is null or a.valid_to > b.valid_from)

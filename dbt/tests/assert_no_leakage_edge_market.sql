-- Leakage guard for feature_pregame_edge_market (Edge Program — Story E3.0).
-- Every sharp quote used as the anchor must be strictly PRE first pitch. Returns
-- rows when the freshest Pinnacle quote timestamp is at/after commence_time, which
-- would mean a post-first-pitch (in-/post-game) price leaked into the feature.
-- All rows must be empty.
select
    game_pk,
    market_type,
    pinnacle_quote_ts,
    commence_time
from {{ ref('feature_pregame_edge_market') }}
where pinnacle_quote_ts is not null
  and pinnacle_quote_ts >= commence_time

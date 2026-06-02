-- Leakage guard for feature_pregame_meta_model_features.
-- Returns rows when hours_to_first_pitch_at_prediction <= 0, which would indicate
-- that a prediction was made after first pitch (post-game feature leak).
-- All rows must have positive values — negative means we used post-game information.
select
    game_pk,
    market_type,
    predicted_at,
    hours_to_first_pitch_at_prediction
from {{ ref('feature_pregame_meta_model_features') }}
where hours_to_first_pitch_at_prediction is not null
  and hours_to_first_pitch_at_prediction < 0

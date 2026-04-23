-- Temporary verification model. Confirms that dbtf routes the feature/ layer
-- into baseball_data.betting_features. Safe to delete once the first real
-- feature model is built and the schema is confirmed.
select
    game_pk,
    game_date,
    'feature_layer_ok' as verification_status
from {{ ref('mart_game_results') }}
limit 1

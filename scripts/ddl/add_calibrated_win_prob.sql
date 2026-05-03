-- Card 7.C: Add calibrated_win_prob column to daily_model_predictions.
-- calibrated_win_prob is consensus_win_prob after in-season Platt recalibration.
-- consensus_win_prob is retained as an audit column.

ALTER TABLE baseball_data.betting_ml.daily_model_predictions
ADD COLUMN IF NOT EXISTS calibrated_win_prob FLOAT;

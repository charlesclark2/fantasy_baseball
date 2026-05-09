-- =============================================================================
-- model_tracking_migration.sql
-- Phase 8 pre-8.W: Snowflake model performance and version tracking improvements
-- Run once. All table references are fully qualified.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Add model_version to prediction_log
-- -----------------------------------------------------------------------------
ALTER TABLE baseball_data.config.prediction_log
    ADD COLUMN IF NOT EXISTS model_version VARCHAR(20);

-- Backfill historical rows using production deployment date boundaries:
--   v0  = XGBoost (production before Card 7.L2 on 2026-05-04)
--   v1  = elasticnet home_win / run_diff v1 (from 2026-05-04)
--   v2  = total_runs NGBoost decay-weighted (from 2026-05-08)
UPDATE baseball_data.config.prediction_log
SET model_version = CASE
    WHEN prediction_date >= '2026-05-08' THEN 'v2'
    WHEN prediction_date >= '2026-05-04' THEN 'v1'
    ELSE 'v0'
END
WHERE model_version IS NULL;

-- -----------------------------------------------------------------------------
-- 2. Add model_version to model_health_log
-- -----------------------------------------------------------------------------
ALTER TABLE baseball_data.betting_ml.model_health_log
    ADD COLUMN IF NOT EXISTS model_version VARCHAR(20);

-- -----------------------------------------------------------------------------
-- 3. Create model_registry table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.model_registry (
    target                  VARCHAR(50)    NOT NULL,
    model_version           VARCHAR(20)    NOT NULL,
    model_name              VARCHAR(100),
    artifact_path           VARCHAR(500),
    feature_columns_path    VARCHAR(500),
    features                INTEGER,
    training_rows           INTEGER,
    training_cutoff         VARCHAR(20),
    cv_metric_name          VARCHAR(50),
    cv_metric_value         FLOAT,
    promoted_date           DATE,
    deprecated_date         DATE,
    is_current              BOOLEAN        DEFAULT TRUE,
    notes                   VARCHAR(4000),
    created_at              TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_model_registry PRIMARY KEY (target, model_version)
);

-- -----------------------------------------------------------------------------
-- 4. Seed model_registry — home_win
-- -----------------------------------------------------------------------------
INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('home_win', 'v0', 'xgboost',
     'betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl',
     'betting_ml/models/feature_columns.json',
     294, 10272, '2021+', 'brier', 0.2439,
     NULL, '2026-05-04', FALSE,
     'Card 7.MA XGBoost classifier. Replaced by elasticnet v1 on 2026-05-04.');

INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('home_win', 'v1', 'elasticnet',
     'betting_ml/models/home_win/elasticnet_2026.pkl',
     'betting_ml/models/home_win/elasticnet_feature_columns.json',
     487, 10272, '2021+', 'brier', 0.2422,
     '2026-05-04', NULL, TRUE,
     'Card 7.L2. LogisticRegression elasticnet l1_ratio=0.5 C=0.01, 487-feature set. CV Brier 0.2422. Rolling Platt calibrator (Card 8.O) last fit 2026-05-08.');

-- -----------------------------------------------------------------------------
-- 5. Seed model_registry — total_runs
-- -----------------------------------------------------------------------------
INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('total_runs', 'v0', 'ngboost_lognormal',
     'betting_ml/models/total_runs/ngboost_tuned_prod.pkl',
     'betting_ml/models/feature_columns.json',
     267, 10243, '2021+', 'mae', 3.4856,
     NULL, '2026-05-04', FALSE,
     'Card 7.F baseline NGBoost LogNormal. Replaced by v1 on 2026-05-04.');

INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('total_runs', 'v1', 'ngboost_lognormal',
     'betting_ml/models/total_runs/ngboost_tuned_2026.pkl',
     'betting_ml/models/feature_columns.json',
     294, 10256, '2021+', 'mae', 3.5190,
     '2026-05-04', '2026-05-08', FALSE,
     'Card 7.MA NGBoost LogNormal on full Phase 7 feature set. Replaced by Normal v2 on 2026-05-08.');

INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('total_runs', 'v2', 'ngboost_normal_decay',
     'betting_ml/models/total_runs/ngboost_decay_weighted.pkl',
     'betting_ml/models/total_runs/feature_columns_v2.json',
     311, 10264, '2021+', 'mae', 3.5107,
     '2026-05-08', NULL, TRUE,
     'Cards 7.V + 8.N. NGBoost Normal max_depth=3 n_estimators=500, decay-weighted half_life=162. 311 post-pipeline features.');

-- -----------------------------------------------------------------------------
-- 6. Seed model_registry — run_differential
-- -----------------------------------------------------------------------------
INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('run_differential', 'v0', 'ngboost_normal',
     'betting_ml/models/run_differential/ngboost_tuned_prod.pkl',
     'betting_ml/models/feature_columns.json',
     267, 10243, '2021+', 'mae', 3.4586,
     NULL, '2026-05-04', FALSE,
     'Card 7.F baseline NGBoost Normal. LogNormal excluded (run_diff can be negative). Replaced by v1 on 2026-05-04.');

INSERT INTO baseball_data.betting_ml.model_registry
    (target, model_version, model_name, artifact_path, feature_columns_path,
     features, training_rows, training_cutoff, cv_metric_name, cv_metric_value,
     promoted_date, deprecated_date, is_current, notes)
VALUES
    ('run_differential', 'v1', 'ngboost_normal',
     'betting_ml/models/run_differential/ngboost_tuned_2026.pkl',
     'betting_ml/models/feature_columns.json',
     294, 10256, '2021+', 'mae', 3.4724,
     '2026-05-04', NULL, TRUE,
     'Card 7.MA NGBoost Normal on full Phase 7 feature set. LogNormal excluded per project constraint.');

-- -----------------------------------------------------------------------------
-- 7. Remap 'prod' version tag in daily_model_predictions
--    score_date < 2026-05-04  → v0 (XGBoost was production)
--    score_date >= 2026-05-04 → v1 (elasticnet promoted that day)
-- -----------------------------------------------------------------------------
UPDATE baseball_data.betting_ml.daily_model_predictions
SET model_version = 'v0'
WHERE model_version = 'prod'
  AND score_date < '2026-05-04';

UPDATE baseball_data.betting_ml.daily_model_predictions
SET model_version = 'v1'
WHERE model_version = 'prod'
  AND score_date >= '2026-05-04';

-- Verify (run manually after migration):
-- SELECT model_version, COUNT(*) AS row_count
-- FROM baseball_data.betting_ml.daily_model_predictions
-- GROUP BY model_version ORDER BY model_version;
--
-- SELECT model_version, COUNT(*) AS row_count
-- FROM baseball_data.config.prediction_log
-- GROUP BY model_version ORDER BY model_version;
--
-- SELECT target, model_version, is_current, promoted_date, deprecated_date
-- FROM baseball_data.betting_ml.model_registry
-- ORDER BY target, model_version;

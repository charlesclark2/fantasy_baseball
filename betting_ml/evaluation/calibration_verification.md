# Home Win Calibration Verification (Phase 5)

Generated: 2026-04-25T17:40:04Z

## Configuration

calibration_method: sigmoid
reference_cv_ece_source: Card 4.11 xgb_platt mean CV ECE
verification_train_years: 2016-2023 (2020 excluded by data loader)
verification_calib_year: 2024
verification_eval_year: 2025
production_train_years: 2016-2024 (2020 excluded)
production_calib_year: 2025

## Results

CV ECE (Card 4.11 Platt mean): 0.0119
verification_ece: 0.0147
verification_brier: 0.2439
delta: +0.0028
ECE threshold: 0.0050
verdict: PASS

## Method Note

Card 4.11 isotonic CV ECE (0.0000) is in-sample degenerate: isotonic regression
perfectly fits any training set, so the ECE trivially equals 0 when calibrator and
evaluator use the same fold. Platt (sigmoid) CV ECE (0.0119) is a valid out-of-sample
reference — LogisticRegression on raw XGB scores is a smooth parametric calibrator
that generalizes without memorizing the calibration set.

A delta ≤ 0.005 (verification ECE vs. Platt CV ECE) confirms that the Platt calibrator
generalizes from the 2024 hold-out to unseen 2025 data within acceptable tolerance.

## Artifact

`betting_ml/models/home_win/xgboost_sigmoid_prod_calibrated.pkl`
(CalibratedXGBClassifier wrapping XGBClassifier + LogisticRegression; calibration_split=2025)

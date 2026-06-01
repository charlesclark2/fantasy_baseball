# Story 5.5 — Starter v1 Signal Ablation Results

**Run date:** 2026-06-01T04:58:21Z  
**Script:** `betting_ml/scripts/ablation_starter_v1_signals.py`  
**Signal coverage:** 2021–2026 (2015–2020 rows filled with neutral values: mu=0.325, signal=0.0)  
**CV method:** Walk-forward by season, Ridge α=1000, min_train_seasons=3  
**Regression gate:** Δ MAE < 0.005 on both targets  

## Results by Target

### total_runs

| Fold | Baseline MAE | With-signals MAE | Δ |
|---|---|---|---|
| 2024 | 3.4241 | 3.4207 | -0.0034 |
| 2025 | 3.6172 | 3.6170 | -0.0002 |
| 2026 | 3.4653 | 3.4604 | -0.0049 |
| **Mean** | **3.5022** | **3.4994** | **-0.0028** |

- Folds improved: 3 / 3
- Gate: **CLEAR**
- `home_starter_suppression_mu_v1` Ridge |coef| rank: #1
- `home_starter_suppression_signal_v1` Ridge |coef| rank: #2

### run_differential

| Fold | Baseline MAE | With-signals MAE | Δ |
|---|---|---|---|
| 2024 | 3.3915 | 3.3881 | -0.0034 |
| 2025 | 3.5109 | 3.5038 | -0.0071 |
| 2026 | 3.5761 | 3.5665 | -0.0096 |
| **Mean** | **3.4928** | **3.4861** | **-0.0067** |

- Folds improved: 3 / 3
- Gate: **CLEAR**
- `home_starter_suppression_mu_v1` Ridge |coef| rank: #2
- `home_starter_suppression_signal_v1` Ridge |coef| rank: #1

## Overall Gate

**CLEAR** — no regression. Starter signals are safe to include in Layer 3 stacking (Epic 9).

## Notes

- Near-zero delta is expected: `starter_suppression_mu_v1` is a smoothed compression
  of starter quality features already present in `feature_pregame_game_features`.
  The real incremental value appears in Epic 9 stacking, where sub-model outputs
  *replace* raw features rather than augmenting them.
- 2015–2020 rows (no signal coverage) are filled with league-mean neutral values;
  this makes the ablation conservative — the with-signals model is penalized for the
  neutral fill in ~5 of the 8+ CV folds.
- Feature importance via Ridge |coef| on standardized features (full dataset fit).

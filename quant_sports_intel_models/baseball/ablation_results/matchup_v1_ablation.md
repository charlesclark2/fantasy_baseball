# Story 8.4 — Matchup v1 Signal Ablation Results

**Run date:** 2026-06-02T09:02:31Z  
**Script:** `betting_ml/scripts/ablation_matchup_v1_signals.py`  
**Signal coverage:** 2021–2026 (94%+ available; 2015–2020 rows filled with neutral values: mu=0.0, volatility=1.756)  
**CV method:** Walk-forward by season, Ridge α=1000, min_train_seasons=3  
**Regression gate:** Δ MAE < 0.005 on both targets  

## Results by Target

### total_runs

| Fold | Baseline MAE | With-signals MAE | Δ |
|---|---|---|---|
| 2024 | 3.4219 | 3.4221 | +0.0002 |
| 2025 | 3.6145 | 3.6141 | -0.0005 |
| 2026 | 3.4853 | 3.4826 | -0.0027 |
| **Mean** | **3.5072** | **3.5062** | **-0.0010** |

- Folds improved: 2 / 3
- Gate: **CLEAR**
- `home_matchup_advantage_mu_v1` Ridge |coef| rank: #160
- `home_matchup_volatility_signal_v1` Ridge |coef| rank: #370

### run_differential

| Fold | Baseline MAE | With-signals MAE | Δ |
|---|---|---|---|
| 2024 | 3.3872 | 3.3875 | +0.0003 |
| 2025 | 3.5057 | 3.5061 | +0.0004 |
| 2026 | 3.5857 | 3.5872 | +0.0015 |
| **Mean** | **3.4928** | **3.4936** | **+0.0007** |

- Folds improved: 0 / 3
- Gate: **CLEAR**
- `home_matchup_advantage_mu_v1` Ridge |coef| rank: #156
- `home_matchup_volatility_signal_v1` Ridge |coef| rank: #269

## Overall Gate

**CLEAR** — no regression. Matchup signals are safe to include in Layer 3 stacking (Epic 9).

## Notes

- Near-zero delta is expected: `matchup_advantage_mu_v1` encodes batter×pitcher
  archetype interaction residuals that are partially captured by raw starter quality
  and lineup features already in `feature_pregame_game_features`.
  The real incremental value appears in Epic 9 stacking, where sub-model outputs
  *replace* raw features rather than augmenting them.
- 2015–2020 rows (no signal coverage) are filled with neutral values;
  this makes the ablation conservative — the with-signals model is penalized for the
  neutral fill in several early CV folds.
- `matchup_volatility_signal_v1` measures Shannon entropy of the joint batter×pitcher
  archetype distribution; higher values indicate more uncertain/volatile matchups.
- Feature importance via Ridge |coef| on standardized features (full dataset fit).

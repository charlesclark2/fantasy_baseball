# Model Selection v1 — Card 7.MB

**Date:** 2026-05-04  
**Evaluation method:** Walk-forward cross-validation, 4 temporal folds (fold_2022–fold_2025)  
**Primary metric:** Brier score (lower = better)  
**Edge metric:** Mean head-to-head edge = model_prob − market_implied_prob (positive = model favors the home team more than the market)  
**Selection threshold:** Cohen's d ≥ 0.10 on Brier vs. baseline counts as a meaningful degradation

---

## 1. Candidate Models

| # | Model | Description |
|---|-------|-------------|
| 1 | `elasticnet` | LogisticRegression (elasticnet, inner-CV C) + Ridge; full feature set including market signals |
| 2 | `elastic_no_market` | Same as above but 18 market-derived columns excluded |
| 3 | `ensemble_stacked` | XGBoost + LightGBM + CatBoost base; LogisticRegression meta; full features |
| 4 | `catboost` | CatBoostClassifier (500 iter, lr=0.05, depth=6); full features |
| 5 | `lightgbm` | LGBMClassifier (500 iter, lr=0.05, 63 leaves); full features |
| 6 | `xgb_no_market` | XGBClassifier (400 est, max_depth=5, lr=0.05); 18 market columns excluded |
| 7 | `xgboost_ngboost` | XGBClassifier + NGBoost for uncertainty; full features |

---

## 2. Primary Results — Win-Probability Head

All metrics are mean across 4 folds. Edge metrics use market `home_implied_prob` as the reference.

| Model | Brier ↓ | LogLoss ↓ | Mean H2H Edge ↑ | % Pos Edge ↑ | Totals MAE ↓ | RL ROI |
|-------|---------|-----------|-----------------|--------------|-------------|--------|
| `elasticnet` | **0.2425** | **0.6778** | +0.0018 | 0.5164 | 3.731 | −0.420 |
| `elastic_no_market` | 0.2433 | 0.6795 | +0.0043 | **0.5276** | 3.669 | −0.430 |
| `ensemble_stacked` | 0.2439 | 0.6808 | −0.0123 | 0.3893 | 3.487 | −0.334 |
| `catboost` | 0.2445 | 0.6820 | −0.0005 | 0.4887 | 3.497 | −0.315 |
| `lightgbm` | 0.2501 | 0.6939 | −0.0019 | 0.4937 | 3.513 | −0.359 |
| `xgb_no_market` | 0.2589 | 0.7184 | **+0.0118** | 0.5177 | 3.546 | −0.395 |
| `xgboost_ngboost` | 0.2594 | 0.7199 | +0.0086 | 0.5274 | 3.535 | −0.397 |

### Per-fold Brier (xgb_no_market, elasticnet, elastic_no_market)

| Fold | elasticnet | elastic_no_market | xgb_no_market |
|------|------------|-------------------|---------------|
| fold_2022 | 0.2385 | 0.2410 | 0.2652 |
| fold_2023 | 0.2473 | 0.2467 | 0.2673 |
| fold_2024 | 0.2416 | 0.2421 | 0.2516 |
| fold_2025 | 0.2428 | 0.2435 | 0.2516 |

---

## 3. Cohen's d vs. Baseline (elasticnet)

Baseline: `elasticnet` (best Brier). Positive d = challenger is worse.

| Challenger | Δ Brier (mean) | Cohen's d | Verdict |
|------------|---------------|-----------|---------|
| `elastic_no_market` | +0.0008 | **+0.25** | Exceeds d=0.10 threshold; small but detectable cost |
| `ensemble_stacked` | +0.0014 | +0.41 | Worse on accuracy AND negative edge — eliminated |
| `catboost` | +0.0020 | +0.52 | Worse on accuracy, near-zero edge — eliminated |
| `lightgbm` | +0.0075 | +1.16 | Clearly worse — eliminated |
| `xgb_no_market` | +0.0164 | +2.50 | Much worse on accuracy — edge story only |
| `xgboost_ngboost` | +0.0169 | +2.37 | Much worse on accuracy — eliminated |

**Key finding:** Every challenger is statistically worse than `elasticnet` on Brier (all d > 0.10). However, `elastic_no_market` is the only challenger with a legitimate edge story (mean H2H edge = +0.0043, %PosEdge = 52.76%), and its Brier penalty is the smallest of any challenger.

---

## 4. Market Circularity Analysis

`elasticnet` and other market-aware models include `home_win_prob_consensus` as a feature. SHAP analysis (fold_2025) shows this is the single largest contributor (mean |SHAP| = 0.054). This creates a fundamental tension:

- **Better Brier** — anchoring to the consensus helps predict outcomes
- **Near-zero edge** — the model predicts roughly what the market already prices, so `model_prob − implied_prob ≈ 0`

Market-blind models sacrifice ~0.001–0.002 Brier but generate genuine, non-circular edge estimates:

| Model | Mean H2H Edge | % Positive Edge |
|-------|--------------|-----------------|
| `elasticnet` (market-aware) | +0.0018 | 51.6% |
| `elastic_no_market` (blind) | +0.0043 | **52.8%** |
| `xgb_no_market` (blind) | +0.0118 | 51.8% |

The edge trend over folds shows degradation in later years for both models — fold_2024 and fold_2025 have near-zero or slightly negative mean edge, suggesting market efficiency has tightened.

---

## 5. Calibration Analysis

Method: last 15% of each training window held out for calibration fitting; ECE (10-bin uniform-width) and Brier reported on test split.

| Model | ECE raw | ECE isotonic | ECE Platt | Brier raw | Brier Platt |
|-------|---------|--------------|-----------|-----------|-------------|
| `catboost` | **0.0169** | 0.0292 | 0.0179 | 0.2436 | 0.2437 |
| `elastic_no_market` | 0.0181 | 0.0419 | 0.0282 | 0.2436 | 0.2439 |
| `elasticnet` | 0.0202 | 0.0394 | 0.0238 | 0.2425 | 0.2427 |
| `xgb_no_market` | 0.0994 | 0.0373 | **0.0287** | 0.2609 | **0.2472** |

### Calibration findings

1. **`xgb_no_market` is poorly calibrated out-of-the-box** (ECE=0.0994). Platt scaling reduces ECE to 0.0287 and improves Brier by 0.014 — a calibration layer is required for this model.

2. **Linear models (`elasticnet`, `elastic_no_market`) are naturally well-calibrated** (ECE < 0.022). Neither isotonic nor Platt calibration improves them meaningfully; isotonic consistently makes them worse, likely overfitting on the small 15% holdout.

3. **CatBoost is the best-calibrated raw model** (ECE=0.0169). No calibration layer adds value.

4. **Isotonic calibration hurts all models** in this regime — the 15% holdout (≈1,200 rows) appears too small for monotone regression to generalize reliably.

5. **Platt scaling recommendation by model:**
   - `elasticnet`: not needed (raw is better)
   - `elastic_no_market`: not needed (raw is better)
   - `catboost`: not needed
   - `xgb_no_market`: **required** — apply Platt before using probabilities for Kelly sizing

---

## 6. Selection Decision

### Retained: `elasticnet` (primary model)

- Best Brier (0.2425), best LogLoss (0.6778), best-tuned across all folds
- Naturally calibrated (ECE=0.0202) — no calibration layer in production
- Positive mean edge (+0.0018) though modest
- **Use for:** probability estimation, Kelly stake sizing, risk management

### Retained: `elastic_no_market` (market-blind challenger)

- Brier penalty vs baseline: d=+0.25 (small but detectable)
- Best % positive-edge among all models (52.76%)
- Naturally calibrated (ECE=0.0181)
- Edge estimate is non-circular — model has no knowledge of the market signal it is compared against
- **Use for:** edge detection, bet filtering, identifying games where model and market disagree

### Eliminated

| Model | Reason |
|-------|--------|
| `ensemble_stacked` | Negative mean edge (−0.0123), only 38.9% positive-edge, d=+0.41 vs baseline |
| `catboost` | Negative mean edge (−0.0005), d=+0.52; complexity not justified |
| `lightgbm` | d=+1.16 vs baseline, no edge advantage |
| `xgb_no_market` | d=+2.50; raw ECE=0.0994 requires mandatory Platt calibration; edge advantage (+0.0118) is noisy (fold_2022 drives the mean with +0.0713) |
| `xgboost_ngboost` | d=+2.37, negative mean edge in 3 of 4 folds |

---

## 7. Limitations

- **n=4 folds** — Cohen's d is computed on 4-sample fold-level means; confidence intervals are wide. The d=0.10 threshold is a practical heuristic, not a significance test.
- **Edge trend degradation** — mean H2H edge has declined monotonically from fold_2022 to fold_2025 for both retained models. fold_2025 shows near-zero/negative edge. Whether this is a real trend (market efficiency) or overfitting to earlier years is unclear.
- **Run line ROI is negative for all models** — no model produces a positive run-line ROI across any fold. This metric should not drive selection but warrants investigation.
- **`xgb_no_market` edge concentration** — fold_2022 H2H edge (+0.0713) is 6× larger than any other fold. The mean edge of +0.0118 is not stable.
- **Market column set may be incomplete** — 18 columns excluded as market-derived. Features like `park_factor` or game-level schedule features could still be indirectly correlated with the market.
- **No walk-forward evaluation of Kelly ROI** — the edge and calibration results here are necessary but not sufficient. Actual profitability requires backtesting the full betting pipeline (bet selection, stake sizing, vig deduction).

---

## 8. Next Steps

- **7M (pre-retrain):** Retrain both `elasticnet` and `elastic_no_market` on the full 2022–2025 dataset before the 2026 season. This was deferred from prior cards due to NGBoost runtime constraints — linear models do not have that constraint.
- **Edge threshold tuning:** Evaluate whether filtering to games where `|model_prob − implied_prob| > threshold` improves bet selection before Kelly sizing.
- **Calibration monitoring:** Log ECE on live predictions weekly during the season; alert if ECE exceeds 0.04 (2× current levels).
- **Phase 9 (deferred):** Stacked ensemble and decomposed micro-services model (home/away runs scored separately) deferred pending evidence that the edge trend reverses.

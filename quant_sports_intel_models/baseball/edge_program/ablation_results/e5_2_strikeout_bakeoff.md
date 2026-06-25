# E5.2 — Pitcher-strikeout model-class × feature bake-off

_Fit 2026-06-25 · 26,062 starts · purged walk-forward CV · primary = CRPS (lower better) · market-blind._

## Why
Closes two methodology gaps in the E5.2 first pass: (1) only one model class was tried; (2) the K-rate was a FLAT season+career average that ignores in-season stuff change. Forward CV stays (fit prior seasons / eval next = leak-honest); recency lives in the FEATURES.

## §0.5 discipline
- **One PBO over the FULL grid** — every model × feature config below is a trial the PBO deflates over (not just the model classes).
- **In-fold nuisance fitting** — the compound `s`/`λ` and the learned model fits are TRAIN-fold only; config SELECTION is on pooled OOS (what PBO deflates).
- **Pre-registered grid** — fixed axes, no reactive expansion (use `incremental_lift_eval.py` for any ADD test).
- **DSR** is the E5.4 leg (deflates a CLV/ROI Sharpe); this bake-off is calibration/CRPS, so PBO is the selection-overfit guard here.

## Full grid (model class × feature config)

| config | model | features | CRPS | coverage@80 | PIT-KS | bias | mean ECE |
|---|---|---|---|---|---|---|---|
| compound|rate=career_only | compound | rate=career_only | 1.2845 | 0.855 | 0.0823 | 0.348 | 0.0376 |
| compound|rate=season_career | compound | rate=season_career | 1.2703 | 0.8601 | 0.0918 | 0.2944 | 0.0347 |
| compound|rate=recency_30d | compound | rate=recency_30d | 1.2946 | 0.8539 | 0.0913 | 0.3009 | 0.0426 |
| compound|rate=recency_7d | compound | rate=recency_7d | 1.2892 | 0.8559 | 0.086 | 0.327 | 0.0395 |
| compound|rate=recency_blend | compound | rate=recency_blend | 1.3049 | 0.8505 | 0.0905 | 0.3012 | 0.0454 |
| compound|rate=recency_blend|no_framing | compound | rate=recency_blend|no_framing | 1.3034 | 0.8518 | 0.0929 | 0.2961 | 0.0443 |
| compound|rate=recency_blend|no_lineup | compound | rate=recency_blend|no_lineup | 1.2875 | 0.8563 | 0.1034 | 0.1477 | 0.0285 |
| lgbm_poisson_k | lgbm_poisson_k | recency(raw) | 1.2265 | 0.8696 | 0.1042 | -0.017 | 0.0069 |
| poisson_glm_k | poisson_glm_k | recency(raw) | 1.2358 | 0.8666 | 0.0813 | 0.0871 | 0.0095 |

**Winner: `poisson_glm_k`** — none well-calibrated → best PIT-KS; calibration bar unmet (the finding).
**PBO over the full grid = 0.0** (9 configs × 4 folds; full model×feature grid (not just model classes)) — overfit risk LOW (<0.2).

## Named mechanisms (paired-by-fold ΔCRPS; negative ⇒ the input helps)

| contrast | mean ΔCRPS | ±2·SEM | verdict |
|---|---|---|---|
| recency_vs_flat | +0.0337 | 0.0084 | REAL — CI excludes 0 |
| framing_effect | +0.0016 | 0.0014 | REAL — CI excludes 0 |
| lineup_log5_effect | +0.0203 | 0.0188 | REAL — CI excludes 0 |

## Read
All contrasts signed **(WITH input − WITHOUT input)** → negative ΔCRPS = the input HELPS.
- **recency_vs_flat** < 0 & CI excludes 0 ⇒ in-season recency genuinely helps (the gap the flat rate washed out); spans 0 ⇒ the flat season rate already carries it.
- **framing_effect / lineup_log5_effect** < 0 & CI excludes 0 ⇒ the input earns its place; spans 0 ⇒ orthogonal-but-inert (keep documented, not assumed).
- **Winner** = the (model × feature-config) cell, promoted into the served pricer (`fit_prop_pricing._RATE_MODE_DEFAULT`, or the learned class). Optuna-tune the WINNER only (the §0.5 exemplar `model_bakeoff → optuna_hpo`).

> best_alpha = 0 — CRPS/calibration is PRODUCT value (projections), not an edge claim. The edge verdict is E5.4 (PBO<0.2 **AND DSR>0** per market, multiple-comparison-corrected, + forward CLV).

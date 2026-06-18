# Purged-CV Re-baseline of the Champions (Epic E1.5)

Each champion recipe re-scored on identical folds under three CV regimes — only the CV changes, the recipe is fixed. **Leakage estimate = purged − standard** (positive ⇒ the standard split was optimistic). The **purged** column is the honest baseline the Edge models (E2–E4) must beat via `evaluate_promotion`.

| target | metric | standard | purged | purged+wt | leakage (purged−std) | flagged? |
|---|---|---|---|---|---|---|
| home_win | brier | 0.1983 | 0.1977 | 0.2119 | -0.0005 (floor 0.002) | no |
| run_diff | mae | 3.0682 | 3.0758 | 3.0916 | +0.0076 (floor 0.02) | no |
| total_runs | mae | 3.3522 | 3.3701 | 3.3688 | +0.0179 (floor 0.02) | no |

_`purged+wt` adds AFML sample-uniqueness weights (E1.2) on top of the purged CV. `flagged` = leakage exceeds the metric noise floor → that champion's edge story leaned on near-boundary folds; re-examine before trusting it as the Edge baseline._

## home_win

- champion recipe: `xgb_platt(champion)` · 374 features
- weight effect (purged+wt − purged): +0.0141

Purge band per fold (E1.1):

| eval year | purge days | train raw | dropped | frac |
|---|---|---|---|---|
| 2024 | 30 | 5975 | 373 | 6.2% |
| 2025 | 30 | 7977 | 355 | 4.5% |
| 2026 | 30 | 10004 | 372 | 3.7% |

Per-season pooled metric (lower = better):

| season | standard | purged | purged+wt |
|---|---|---|---|
| 2024 | 0.1937 | 0.1938 | 0.2134 |
| 2025 | 0.2020 | 0.1998 | 0.2111 |
| 2026 | 0.2003 | 0.2023 | 0.2101 |

## run_diff

- champion recipe: `ngboost-Normal(champion)` · 374 features
- weight effect (purged+wt − purged): +0.0159

Purge band per fold (E1.1):

| eval year | purge days | train raw | dropped | frac |
|---|---|---|---|---|
| 2024 | 30 | 5975 | 373 | 6.2% |
| 2025 | 30 | 7977 | 355 | 4.5% |
| 2026 | 30 | 10004 | 372 | 3.7% |

Per-season pooled metric (lower = better):

| season | standard | purged | purged+wt |
|---|---|---|---|
| 2024 | 3.0120 | 3.0150 | 3.0491 |
| 2025 | 3.1045 | 3.1162 | 3.1211 |
| 2026 | 3.1168 | 3.1253 | 3.1233 |

## total_runs

- champion recipe: `ngboost-Normal(champion)` · 367 features
- weight effect (purged+wt − purged): -0.0013

Purge band per fold (E1.1):

| eval year | purge days | train raw | dropped | frac |
|---|---|---|---|---|
| 2024 | 30 | 5975 | 373 | 6.2% |
| 2025 | 30 | 7977 | 355 | 4.5% |
| 2026 | 30 | 10004 | 372 | 3.7% |

Per-season pooled metric (lower = better):

| season | standard | purged | purged+wt |
|---|---|---|---|
| 2024 | 3.2040 | 3.2364 | 3.2490 |
| 2025 | 3.5311 | 3.5373 | 3.5256 |
| 2026 | 3.2700 | 3.2812 | 3.2719 |

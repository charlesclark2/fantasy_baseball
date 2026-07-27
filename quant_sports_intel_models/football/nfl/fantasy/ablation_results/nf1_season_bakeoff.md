# NF1 — season model §0.5 bake-off (market-blind joint re-weighting)

**Generated:** 2026-07-27T01:14:16.035190+00:00 · **base seasons:** 2017–2024 · **scored targets:** [2019, 2020, 2021, 2022, 2023, 2024, 2025] · **pool:** 2995

> Market-blind (NO ADP/ECR — orthogonal NF-D signals only). Each candidate is Optuna-tuned on the WALK-FORWARD held-out pooled within-position ρ (train on target<Y, predict Y). The SHIP criterion is beating the MVP-1 HEURISTIC NULL; the metric is oracle-floor-checked (E2.1-r). Edge-independent (projection quality, no PBO/DSR).

- **oracle metric sane:** True  ·  **winner:** `gbm`  ·  **winner beats MVP-1 null:** True (0.7318 vs 0.7182)

## Candidates — held-out within-position ρ

| learner        |   pooled_rho |    QB |    RB |    WR |    TE |   train_rho |   overfit_gap | hp                                                                                                     |
|:---------------|-------------:|------:|------:|------:|------:|------------:|--------------:|:-------------------------------------------------------------------------------------------------------|
| heuristic_null |        0.718 | 0.648 | 0.734 | 0.750 | 0.740 |       0.688 |        -0.030 | {}                                                                                                     |
| ridge          |        0.727 | 0.632 | 0.746 | 0.777 | 0.754 |       0.732 |         0.005 | {"alpha": 105.96598285567212}                                                                          |
| elasticnet     |        0.724 | 0.619 | 0.746 | 0.776 | 0.757 |       0.736 |         0.011 | {"alpha": 2.082962750710087, "l1_ratio": 0.8483599463848233}                                           |
| gbm            |        0.732 | 0.661 | 0.743 | 0.776 | 0.747 |       0.802 |         0.071 | {"n_estimators": 100, "num_leaves": 20, "learning_rate": 0.01613001271639494, "min_child_samples": 19} |

## Feature ablation on the winner (drop-one group)

> Δ vs the full feature set (negative = removing the group HURT ordering = the group carries signal).

| drop          |   pooled_rho |   rho_QB |   rho_RB |   rho_WR |   rho_TE |   delta |
|:--------------|-------------:|---------:|---------:|---------:|---------:|--------:|
| (none / full) |        0.732 |    0.661 |    0.743 |    0.776 |    0.747 |   0.000 |
| usage         |        0.728 |    0.656 |    0.736 |    0.777 |    0.741 |  -0.004 |
| mover         |        0.730 |    0.657 |    0.741 |    0.776 |    0.745 |  -0.002 |
| env           |        0.730 |    0.652 |    0.745 |    0.776 |    0.745 |  -0.002 |
| injury        |        0.730 |    0.657 |    0.743 |    0.776 |    0.745 |  -0.002 |
| age           |        0.722 |    0.656 |    0.733 |    0.755 |    0.742 |  -0.010 |
| role          |        0.731 |    0.659 |    0.743 |    0.775 |    0.746 |  -0.001 |


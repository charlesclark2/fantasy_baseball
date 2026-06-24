# E13.2 Phase 1 — PA-outcome multiclass CV (2026-06-24)

- Substrate: 1,959,513 R-season PAs, 35 features (5 categorical + 8 entering-state + 22 point-in-time).
- No-skill marginal-prior floor (Phase 0): 1.5074 nats.

## CV mean multiclass log-loss (lower = better)
- **model**:    1.4848
- log5 prior:   1.4881  (Δ model +0.0033)
- marginal:     1.5094  (Δ model +0.0246)

**Verdict:** BEATS log5 on all folds — context learning earns its place.
Beats log5 on all folds: True; beats marginal on all folds: True.

## Per-fold
| eval | n_train | n_eval | model | log5 | marginal | Δ vs log5 |
|---|---|---|---|---|---|---|
| 2018 | 521,977 | 153,223 | 1.4823 | 1.4831 | 1.5057 | +0.0008 |
| 2019 | 676,965 | 186,025 | 1.4994 | 1.4997 | 1.5258 | +0.0003 |
| 2020 | 861,326 | 66,400 | 1.5074 | 1.5093 | 1.5305 | +0.0018 |
| 2021 | 927,274 | 181,348 | 1.4850 | 1.4882 | 1.5123 | +0.0032 |
| 2022 | 1,109,691 | 181,872 | 1.4702 | 1.4730 | 1.4931 | +0.0029 |
| 2023 | 1,291,471 | 183,773 | 1.4906 | 1.4949 | 1.5151 | +0.0043 |
| 2024 | 1,475,142 | 182,175 | 1.4721 | 1.4784 | 1.4965 | +0.0062 |
| 2025 | 1,659,366 | 182,638 | 1.4712 | 1.4780 | 1.4963 | +0.0068 |
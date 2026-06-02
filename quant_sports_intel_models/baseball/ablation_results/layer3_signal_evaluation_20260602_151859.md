# Layer 3 Signal Evaluation (Story 9.2)

- env=prod · games=11661 · min_train_seasons=2 · 2026-06-02T15:18:56
- Incremental walk-forward CV; gate = held-out NLL delta (Brier for home_win).

## Target: `total_runs`  (promoted in order: run_env, offense, bullpen)

| group | verdict | Δmetric | folds won | MAEΔ | calib80Δ | self-PI cal |
|---|---|---|---|---|---|---|
| run_env | **promote** | -0.013689 | 4/4 | -0.037616 | 0.019155 | 0.8356 |
| offense | **promote** | -0.011749 | 3/4 | -0.051833 | -0.004057 | 0.829 |
| starter | **defer** | -0.002587 | 4/4 | -0.008923 | 0.002827 | n/a |
| starter_ip | **defer** | -0.000967 | 3/4 | -0.010014 | 0.00024 | n/a |
| bullpen | **promote** | -0.029174 | 4/4 | -0.08209 | 0.005981 | n/a |
| matchup | **defer** | -0.000972 | 3/4 | -0.004954 | 0.000421 | n/a |

## Target: `home_win`  (promoted in order: offense, bullpen)

| group | verdict | Δmetric | folds won | MAEΔ | calib80Δ | self-PI cal |
|---|---|---|---|---|---|---|
| run_env | **defer** | -0.000251 | 3/4 | None | None | 0.8356 |
| offense | **promote** | -0.013349 | 3/4 | None | None | 0.829 |
| starter | **defer** | -0.000697 | 4/4 | None | None | n/a |
| starter_ip | **defer** | -0.000902 | 4/4 | None | None | n/a |
| bullpen | **promote** | -0.026583 | 4/4 | None | None | n/a |
| matchup | **reject** | +7e-06 | 0/4 | None | None | n/a |


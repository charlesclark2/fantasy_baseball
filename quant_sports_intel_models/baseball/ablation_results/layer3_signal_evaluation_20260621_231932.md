# Layer 3 Signal Evaluation (Story 9.2)

- env=prod · games=11907 · min_train_seasons=2 · 2026-06-21T23:19:29
- Incremental walk-forward CV; gate = held-out NLL delta (Brier for home_win).

## Target: `total_runs`  (promoted in order: run_env, offense)

| group | verdict | Δmetric | folds won | MAEΔ | calib80Δ | self-PI cal |
|---|---|---|---|---|---|---|
| run_env | **promote** | -0.014293 | 4/4 | -0.038371 | 0.018062 | 0.8362 |
| offense | **promote** | -0.012214 | 3/4 | -0.05141 | -0.00306 | 0.8287 |
| starter | **defer** | -0.00229 | 4/4 | -0.007959 | 0.003366 | n/a |
| starter_ip | **defer** | -0.000613 | 3/4 | -0.007654 | 0.000702 | n/a |
| bullpen | **reject** | +0.00031 | 1/4 | 0.00256 | 0.001094 | n/a |
| matchup | **defer** | -0.000583 | 3/4 | -0.002499 | 0.001275 | n/a |
| defense_quality | **defer** | -0.000903 | 4/4 | -0.002805 | 0.001662 | n/a |

## Target: `home_win`  (promoted in order: offense)

| group | verdict | Δmetric | folds won | MAEΔ | calib80Δ | self-PI cal |
|---|---|---|---|---|---|---|
| run_env | **defer** | -0.000341 | 3/4 | None | None | 0.8362 |
| offense | **promote** | -0.013112 | 3/4 | None | None | 0.8287 |
| starter | **defer** | -0.000743 | 4/4 | None | None | n/a |
| starter_ip | **defer** | -0.000698 | 3/4 | None | None | n/a |
| bullpen | **reject** | +9.4e-05 | 2/4 | None | None | n/a |
| matchup | **reject** | +6e-06 | 0/4 | None | None | n/a |
| defense_quality | **defer** | -1.7e-05 | 3/4 | None | None | n/a |


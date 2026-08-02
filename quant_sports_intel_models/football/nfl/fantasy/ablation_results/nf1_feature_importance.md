# NF3.4 — NF1 feature-importance transparency

Generated: 2026-08-02T01:53:19.295112+00:00  ·  model: `nfl_fantasy_nf1_v1`  ·  pool: 2995 rows over base seasons [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

🚨 MODEL-LEVEL, NOT PER-PLAYER — see `nf1_model.feature_importance_report`'s docstring. This describes NF1 (the validated, market-blind research model over the same signal set MVP-1's served heuristic pipeline is built from), not a per-player attribution of the SERVED MVP-1 projection. `mvp1_fp` (NF1's own incumbent-prior feature) is excluded from the tables below as circular — its true share is disclosed as `baseline_pct` instead.

## Global (pooled across positions, LightGBM gain importance) — baseline (`mvp1_fp`) share: 75.1%

| Feature | Label | % |
|---|---|---|
| `pergame_fp` | Recent per-game scoring pace | 14.0% |
| `age` | Player age | 4.0% |
| `carry_share` | Carry share (rushing role) | 1.3% |
| `team_env` | Team offensive environment (Vegas win total) | 1.2% |
| `fp_sd` | Week-to-week scoring volatility | 1.2% |
| `snap_share` | Snap share (playing time) | 0.8% |

## QB (permutation importance) — baseline (`mvp1_fp`) share: 62.5%

| Feature | Label | % |
|---|---|---|
| `pergame_fp` | Recent per-game scoring pace | 21.3% |
| `age` | Player age | 5.2% |
| `team_env` | Team offensive environment (Vegas win total) | 3.4% |
| `carry_share` | Carry share (rushing role) | 2.9% |
| `snap_share` | Snap share (playing time) | 1.6% |
| `fp_sd` | Week-to-week scoring volatility | 1.6% |

## RB (permutation importance) — baseline (`mvp1_fp`) share: 73.4%

| Feature | Label | % |
|---|---|---|
| `pergame_fp` | Recent per-game scoring pace | 11.8% |
| `age` | Player age | 6.9% |
| `team_env` | Team offensive environment (Vegas win total) | 1.6% |
| `fp_sd` | Week-to-week scoring volatility | 1.6% |
| `carry_share` | Carry share (rushing role) | 1.2% |
| `depth_rank` | Depth-chart standing | 1.2% |

## WR (permutation importance) — baseline (`mvp1_fp`) share: 72.1%

| Feature | Label | % |
|---|---|---|
| `pergame_fp` | Recent per-game scoring pace | 14.7% |
| `age` | Player age | 6.6% |
| `fp_sd` | Week-to-week scoring volatility | 1.8% |
| `team_env` | Team offensive environment (Vegas win total) | 1.3% |
| `mover_scale` | Team-change opportunity | 1.2% |
| `expected_games` | Expected games this season (health/role) | 0.6% |

## TE (permutation importance) — baseline (`mvp1_fp`) share: 79.7%

| Feature | Label | % |
|---|---|---|
| `pergame_fp` | Recent per-game scoring pace | 10.0% |
| `age` | Player age | 5.3% |
| `fp_sd` | Week-to-week scoring volatility | 1.2% |
| `expected_games` | Expected games this season (health/role) | 1.1% |
| `team_env` | Team offensive environment (Vegas win total) | 0.9% |
| `target_share` | Target share (receiving role) | 0.5% |

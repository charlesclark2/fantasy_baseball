# Layer 3 Matrix Audit (Story 9.1)

- Built from `feature_pregame_sub_model_signals` (is_current) ⋈ `mart_game_results`, start_date=2021-01-01
- Grain: one row per game_pk. Games: **11661**. Feature columns: **45**.
- Targets: `total_runs`, `home_win` (derived; never features).

## Rows by season

| season | games |
|---|---|
| 2021 | 2195 |
| 2022 | 2197 |
| 2023 | 2201 |
| 2024 | 2199 |
| 2025 | 2201 |
| 2026 | 668 |

## Foundational signal coverage (must be ≥ 0.999)

| column | coverage |
|---|---|
| `run_env_mu_v4` | 1.0000 |
| `home_pred_runs_mu_v2` | 1.0000 |
| `away_pred_runs_mu_v2` | 1.0000 |

## Signal completeness (5 core groups; matchup excluded)

- mean score: **0.9922**
- fraction ≥ 0.60: **1.0**
- low-completeness games (< 0.4): **0**

## Leakage guards (structural — enforced)

- target-column leakage: **0** (validated — raises otherwise)
- raw-feature violations: **0**

_Temporal leakage-freedom is architectural (sub-models score from pre-game features
only); it is not verifiable from SCD-2 timestamps on backfilled data._

## Signal version churn (diagnostic — NOT leakage)

- games with a value-changing SCD-2 revision (run_env/bullpen/matchup): **13034** — expected for backfilled signals

## Null rates by signal column

| column | null rate |
|---|---|
| `away_bullpen_dispersion_v2` | 0.0077 |
| `away_bullpen_mu_v2` | 0.0077 |
| `away_bullpen_mu_v2_available` | 0.0077 |
| `away_bullpen_uncertainty_v2` | 0.0077 |
| `away_matchup_advantage_mu_v1` | 0.0000 |
| `away_matchup_advantage_mu_v1_available` | 0.0000 |
| `away_matchup_advantage_mu_v1_uncertainty` | 0.0000 |
| `away_matchup_advantage_sigma_v1` | 0.0000 |
| `away_pred_runs_dispersion_v2` | 0.0000 |
| `away_pred_runs_mu_v2` | 0.0000 |
| `away_pred_runs_mu_v2_available` | 0.0000 |
| `away_pred_runs_uncertainty_v2` | 0.0000 |
| `away_starter_ip_dispersion_v1` | 0.0086 |
| `away_starter_ip_mu_v1` | 0.0086 |
| `away_starter_ip_mu_v1_available` | 0.0000 |
| `away_starter_ip_uncertainty_v1` | 0.0086 |
| `away_starter_suppression_mu_v1` | 0.0006 |
| `away_starter_suppression_mu_v1_available` | 0.0000 |
| `away_starter_suppression_sigma_v1` | 0.0006 |
| `away_starter_uncertainty_v1` | 0.0006 |
| `game_year` | 0.0000 |
| `home_bullpen_dispersion_v2` | 0.0071 |
| `home_bullpen_mu_v2` | 0.0071 |
| `home_bullpen_mu_v2_available` | 0.0071 |
| `home_bullpen_uncertainty_v2` | 0.0071 |
| `home_matchup_advantage_mu_v1` | 0.0000 |
| `home_matchup_advantage_mu_v1_available` | 0.0000 |
| `home_matchup_advantage_mu_v1_uncertainty` | 0.0000 |
| `home_matchup_advantage_sigma_v1` | 0.0000 |
| `home_pred_runs_dispersion_v2` | 0.0000 |
| `home_pred_runs_mu_v2` | 0.0000 |
| `home_pred_runs_mu_v2_available` | 0.0000 |
| `home_pred_runs_uncertainty_v2` | 0.0000 |
| `home_starter_ip_dispersion_v1` | 0.0105 |
| `home_starter_ip_mu_v1` | 0.0105 |
| `home_starter_ip_mu_v1_available` | 0.0000 |
| `home_starter_ip_uncertainty_v1` | 0.0105 |
| `home_starter_suppression_mu_v1` | 0.0005 |
| `home_starter_suppression_mu_v1_available` | 0.0000 |
| `home_starter_suppression_sigma_v1` | 0.0005 |
| `home_starter_uncertainty_v1` | 0.0005 |
| `run_env_dispersion_v4` | 0.0000 |
| `run_env_mu_v4` | 0.0000 |
| `run_env_mu_v4_available` | 0.0000 |
| `run_env_mu_v4_uncertainty` | 0.0000 |

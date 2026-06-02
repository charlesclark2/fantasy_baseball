# Layer 3 Totals Dataset Audit (Story 10.1)

- Source: `load_layer3_features_for_training(target='total_runs')`, start_date=2021-01-01, completeness ≥ 0.4.
- Games (completeness-filtered): **11661**.
- Leakage guards: target columns **0**, raw-feature violations **0** (validated — raises otherwise).

## Target distribution — `total_runs`

| metric | value |
|---|---|
| n | 11661 |
| mean | 8.9215 |
| variance | 20.1631 |
| overdispersion ratio (var/mean) | **2.26** |
| NegBin justified (ratio > 1.5) | **True** |

_Variance materially exceeding the mean confirms NegBin over Poisson as the likelihood family._

## Eval-only Bovada total line coverage

- Games with a line: **8146/11661** (69.9%).
- Bovada-specific (closing snapshot): **7772**.
- Consensus fallback: **374**.

_The total line is evaluation-only (10.4/10.6) and never enters the training matrix._


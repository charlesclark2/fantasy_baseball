# Phase 8 — Advanced Feature Engineering

**Prerequisite:** Phase 7 complete (including Card 7.MB model selection evaluation).

Phase 8 focuses on the feature engineering improvements identified during Phase 7.MB
literature review. These are not incremental feature cards — each represents a
structural change to how features are constructed or a new data source that requires
its own ingestion pipeline.

Phase 8 should begin after Card 7.MB produces a definitive model selection result and
the model artifacts are stable. The 2026 regular season (ending early October 2026)
provides a natural boundary: a mid-season All-Star break retrain and an end-of-season
retrain are the planned checkpoints.

## Cards

| Card | Title | Research Source | Effort |
|---|---|---|---|
| 8.A | Percentage-Difference Feature Encoding | Cui (2020), Singh (2024) | Low |
| 8.B | ZiPS Starter FIP/xFIP Projection Features | Cui (2020) | Low |
| 8.C | Defensive Fielding Metrics (OAA / UZR) | DBS thesis (2022) | High |
| 8.D | Elo-Based Team Strength Rating | Cui (2020) | Medium |
| 8.E | Bat Tracking Per-Batter Matchup Aggregations | Phase 4 EDA deferral | Medium |
| 8.I | dbt Quality Gates (Compile + Data Diff) | Internal — CI/CD hardening | Low/Medium |

## Literature references

- Cui, A. (2020). *Forecasting Outcomes of MLB Games Using Machine Learning*.
  Wharton/Penn undergraduate thesis. Key findings: ElasticNet logistic regression
  outperforms XGBoost at ~10K MLB sample sizes; percentage-difference encoding of
  home/away stats is the best feature representation; FIP-ERA gap is a meaningful
  luck-adjustment signal; rest days and OBP differential are the highest-signal features.

- Hughes, G. (2022). *A Regression Based Approach for Prediction of MLB Game Outcomes*.
  DBS Dublin thesis. Key finding: DRS and wRC+ are the cleanest player-level inputs
  for run production/prevention models; two-stage regression (run diff → win prob)
  is theoretically grounded.

- Singh, N. (2024). Medium article. Confirms percentage-difference encoding; 100-day
  rolling windows; rest days, weather, and bullpen as highest-value missing features
  (all now in Phase 7).

- arXiv:2511.02815. Run-line P&L validated as a better model evaluation proxy than
  accuracy or Brier alone (added to 7.MB evaluation harness).

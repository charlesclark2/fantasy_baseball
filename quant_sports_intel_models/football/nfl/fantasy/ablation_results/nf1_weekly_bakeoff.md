# NF1 — matchup-aware weekly leg §0.5 ablation

**Generated:** 2026-07-27T01:28:55.326613+00:00 · **seasons:** [2021, 2022, 2023, 2024]

> Each arm projects every player-week = the leakage-safe season per-game baseline × the arm's matchup tilts (as-of defense-vs-position, the week's Vegas implied team points, home). Scored on held-out weekly within-position ρ vs realized; the full arm's posterior-predictive is checked for E2.1-r PIT flatness (a coverage number alone is biased for a discrete count total).

| arm           |   mean_weekly_rho |   n_weeks |   pit_max_decile_dev |   delta_vs_flat |
|:--------------|------------------:|----------:|---------------------:|----------------:|
| flat_baseline |             0.500 |        60 |                0.232 |           0.000 |
| +dvp          |             0.497 |        60 |                0.233 |          -0.003 |
| +env          |             0.493 |        60 |                0.232 |          -0.007 |
| +home         |             0.501 |        60 |                0.233 |           0.001 |
| full_matchup  |             0.487 |        60 |                0.237 |          -0.013 |


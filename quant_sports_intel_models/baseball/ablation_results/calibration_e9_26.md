# E9.26 — Served per-market calibration (reliability + ECE)

Window **2026-04-17 → 2026-07-16** · 852 Final games · source: serving cache (no Snowflake/lakehouse).

Factual calibration measurement of the *served* probabilities — how close each market's model probability has been to observed frequency. Not a market-advantage claim (`best_alpha = 0`).

## Moneyline (P home win) — n=852

- **Model** ECE `0.0286` · Brier `0.2514` · spread `0.0865` · base-rate `0.5188`
- _served model_prob = calibrated_win_prob (E13.6 TemperatureCalibrator T=6.30)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.0–0.1 | 1 | 0.099 | 1.000 |
| 0.1–0.2 | 11 | 0.168 | 0.455 |
| 0.2–0.3 | 14 | 0.262 | 0.714 |
| 0.3–0.4 | 21 | 0.353 | 0.333 |
| 0.4–0.5 | 316 | 0.474 | 0.462 |
| 0.5–0.6 | 440 | 0.536 | 0.548 |
| 0.6–0.7 | 24 | 0.633 | 0.667 |
| 0.7–0.8 | 14 | 0.739 | 0.571 |
| 0.8–0.9 | 10 | 0.837 | 0.700 |
| 0.9–1.0 | 1 | 0.903 | 1.000 |

## Total Runs (P over) — n=851

- **Model** ECE `0.079` · Brier `0.2568` · spread `0.0823` · base-rate `0.5006`
- _served model_prob = totals_model_prob (raw distributional P(over); not temperature/isotonic-calibrated at serving — its ECE here is the genuine served-calibration measurement)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.0–0.1 | 2 | 0.070 | 0.500 |
| 0.2–0.3 | 6 | 0.260 | 0.333 |
| 0.3–0.4 | 32 | 0.356 | 0.406 |
| 0.4–0.5 | 138 | 0.464 | 0.529 |
| 0.5–0.6 | 435 | 0.553 | 0.483 |
| 0.6–0.7 | 223 | 0.633 | 0.529 |
| 0.7–0.8 | 15 | 0.718 | 0.600 |

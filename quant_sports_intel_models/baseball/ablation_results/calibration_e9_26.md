# E9.26 — Served per-market calibration (reliability + ECE)

Window **2026-07-02 → 2026-07-16** · 150 Final games · source: serving cache (no Snowflake/lakehouse).

Factual calibration measurement of the *served* probabilities — how close each market's model probability has been to observed frequency. Not a market-advantage claim (`best_alpha = 0`).

## Moneyline (P home win) — n=150

- **Model** ECE `0.0427` · Brier `0.2469` · spread `0.0379` · base-rate `0.4867`
- _served model_prob = calibrated_win_prob (E13.6 TemperatureCalibrator T=6.30)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.4–0.5 | 79 | 0.476 | 0.418 |
| 0.5–0.6 | 68 | 0.534 | 0.559 |
| 0.6–0.7 | 3 | 0.609 | 0.667 |

## Total Runs (P over) — n=150

- **Model** ECE `0.1046` · Brier `0.2482` · spread `0.0712` · base-rate `0.4733`
- _served model_prob = totals_model_prob (raw distributional P(over); not temperature/isotonic-calibrated at serving — its ECE here is the genuine served-calibration measurement)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.2–0.3 | 1 | 0.291 | 0.000 |
| 0.3–0.4 | 8 | 0.370 | 0.625 |
| 0.4–0.5 | 35 | 0.457 | 0.343 |
| 0.5–0.6 | 83 | 0.550 | 0.458 |
| 0.6–0.7 | 23 | 0.621 | 0.696 |

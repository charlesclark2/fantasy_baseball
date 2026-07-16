# E9.26 — Served per-market calibration (reliability + ECE)

Window **2026-04-17 → 2026-07-16** · 1117 Final games · source: serving cache (no Snowflake/lakehouse).

Factual calibration measurement of the *served* probabilities — how close each market's model probability has been to observed frequency. Not a market-advantage claim (`best_alpha = 0`).

## Moneyline (P home win) — n=1117

- **Model** ECE `0.0304` · Brier `0.2501` · spread `0.0777` · base-rate `0.5103`
- _served model_prob = calibrated_win_prob (E13.6 TemperatureCalibrator T=6.30)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.0–0.1 | 1 | 0.099 | 1.000 |
| 0.1–0.2 | 11 | 0.168 | 0.455 |
| 0.2–0.3 | 14 | 0.262 | 0.714 |
| 0.3–0.4 | 21 | 0.353 | 0.333 |
| 0.4–0.5 | 446 | 0.474 | 0.448 |
| 0.5–0.6 | 572 | 0.535 | 0.547 |
| 0.6–0.7 | 27 | 0.630 | 0.667 |
| 0.7–0.8 | 14 | 0.739 | 0.571 |
| 0.8–0.9 | 10 | 0.837 | 0.700 |
| 0.9–1.0 | 1 | 0.903 | 1.000 |

## Total Runs (P over) — n=1115

- **Model** ECE `0.0609` · Brier `0.2551` · spread `0.0808` · base-rate `0.4978`
- _served model_prob = totals_model_prob (raw distributional P(over); not temperature/isotonic-calibrated at serving — its ECE here is the genuine served-calibration measurement)_

| pred bin | n | avg pred | avg actual |
|---|---|---|---|
| 0.0–0.1 | 2 | 0.070 | 0.500 |
| 0.2–0.3 | 10 | 0.269 | 0.400 |
| 0.3–0.4 | 44 | 0.360 | 0.455 |
| 0.4–0.5 | 196 | 0.463 | 0.464 |
| 0.5–0.6 | 580 | 0.552 | 0.491 |
| 0.6–0.7 | 268 | 0.631 | 0.541 |
| 0.7–0.8 | 15 | 0.718 | 0.600 |

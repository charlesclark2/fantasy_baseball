# E9.26 — Served per-market calibration (reliability + ECE)

The "how calibrated we've been" artifact the product cites and E9.43's conviction
layer consumes as its Task-1 input. This is a **factual calibration measurement of
the served probabilities** — how close each market's model probability has been to
the observed frequency. It is **not** a market-advantage or return claim
(`best_alpha = 0` holds).

## How it is produced

`scripts/compute_calibration_artifact_e9_26.py` reads settled results **only through
the serving cache** (DynamoDB → S3 game-detail blobs) — the E9.40 discipline, so it
is safe alongside the E11.20 Delta migration (no Snowflake / lakehouse / mart /
`daily_model_predictions` read). For each Final game it pairs the served per-market
model probability with the realized binary outcome:

| Market | Served `model_prob` | Binary outcome | Pushes |
|---|---|---|---|
| h2h | `calibrated_win_prob` = P(home win) | `1[home won]` | n/a (MLB has no ties) |
| totals | `totals_model_prob` = P(over) | `1[final total > closing line]` | dropped (no binary label) |

Per market it computes ECE (10 equal-width bins, `betting_ml/utils/calibration_metrics`),
Brier, log-loss, spread and a reliability table (predicted vs observed frequency).
The de-vigged market prob (`bovada_devig_prob`) is scored the same way as a benchmark.

Refresh (OFF-BOX, read-only; needs AWS creds for the serving cache):

```
uv run python scripts/compute_calibration_artifact_e9_26.py --days 90 --write-md
```

That overwrites this file's per-market tables and writes the JSON to
`betting_ml/evaluation/calibration_e9_26/served_calibration_<start>_<end>.json`.

## Current per-market calibration status (as of 2026-07-16)

Two different calibration footings — recorded here so E9.43 conditions conviction on
the right per-market reliability, not a single blended assumption:

### Moneyline — P(home win) — CALIBRATED

The served h2h probability is temperature-calibrated by the **E13.6
`TemperatureCalibrator` (T = 6.2998)**, an interim honesty measure applied to the
de-leaked v5 / post-lineup consensus. Fit on 2026 honest-OOS (`n = 1138`):

| | before | after (served) |
|---|---|---|
| ECE | 0.1541 | **0.0329** |
| Brier | 0.2761 | 0.2487 |
| spread | 0.2015 | 0.0365 |

Source: `betting_ml/models/home_win/calibrator_meta.json`. The calibrator is INTERIM
(`REFIT_GUARD`) and pinned to v5/post-lineup — a champion rebuild (E1.9 v6) or a
30.3/Epic-33 serving change requires a re-fit, at which point re-run the refresh above.
The low post-calibration spread (~0.037) is expected: it removed false precision from
an overconfident prob, so h2h picks legitimately sit near the base rate.

### Total Runs — P(over) — UNCALIBRATED AT SERVING (raw distributional CDF)

The served totals probability is the **raw distributional P(over)** from the run-total
model's NegBin/Normal CDF — **no temperature/isotonic/Platt object is applied at serve
time** (only the h2h consensus passes through `_apply_calibrator` in `predict_today`).
The retrospective Story 10.4 totals audit (`calibrate_totals_v1.py`) measured its raw
**ECE ≈ 0.0312** (`ece_pass = true`, `ece_after_platt = null` — a Platt layer did not
improve it, so none was wired in). See
`model_registry.yaml → layer3_totals.calibration_results` and
`ablation_results/totals_v1_reliability_diagram.md`.

The genuine served-calibration measurement of totals is what the refresh script
surfaces from live blobs; run it to populate the reliability table here.

## Consistency contract (the point of E9.26)

The record/win-rate the product shows and this calibration measurement use the **same
canonical pick rule** (`model_prob >= 0.5` → home/over; per market; pushes excluded) —
defined once in `app/backend/services/metric_semantics.py` (backend) and
`frontend/lib/metrics.ts` (frontend), and locked by
`betting_ml/tests/test_metric_semantics_e9_26.py`. So "correct" on the scorecard, the
Performance page win-rate, and the probability behind this reliability curve all mean
the same thing.

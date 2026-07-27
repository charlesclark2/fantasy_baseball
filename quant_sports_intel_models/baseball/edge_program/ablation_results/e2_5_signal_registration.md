# E2.5 — Signal registration + leakage-safe backfill (`totals_generative_v1`)

**Status:** code-complete + fast gate green (2026-07-26); awaiting the operator's leakage-safe
backfill run + box deploy. `best_alpha = 0` (market-blind marginal; the edge question is E2.6).

## What ships

The E2.1/E2.1-r per-side count-distribution model (`totals_perside_v1`) is registered as a served
sub-model signal `totals_generative_v1` and wired into the signal-serving path
(`feature_pregame_sub_model_signals` → `predict_today`), exactly like `offense_v2` — with a
**leakage-safe walk-forward backfill** so no season is scored in-sample.

### The two decisions that matter

1. **The learner = LightGBM Poisson mean (NOT NGBoost).** The older E2.5 prompt called the winner
   "the NGBoost per-side pricing winner" — that is **stale**. E2.1-r's actual verdict was
   `PROMOTE_MINIMAL_FIX`: NGBoost was *dropped* (under-dispersed, 3–5× slower); the trustworthy
   learner-null keeps LightGBM. We register `totals_perside_v1.pkl` (LightGBM Poisson), unchanged.

2. **The served dispersion = the E2.3 held-out-calibrated per-side `r` (home 4.0645 / away 3.3977),
   NOT the artifact's train-fit `negbin_r = 7.449`.** The train-fit `r` is the known under-dispersed
   value (calib_80 0.778 < 0.80 — the ~24 % variance deficit E2.1-r/E2.3 diagnosed). Serving it would
   re-introduce the exact bug E2.3 fixed. The generator serves the raw LightGBM **mean** with the
   E2.3 **held-out `r`** (`totals_distribution_v1.json`). No double-calibration (the mean is untouched;
   the distribution is NegBin per-side, not a bolt-on calibrator).

### Output signals (per `game_pk × side`)

| signal | meaning |
|---|---|
| `totals_perside_mu` | LightGBM Poisson mean (the E2.1-r validated learner) |
| `totals_perside_dispersion` | E2.3 calibrated per-side NegBin `r` (home 4.0645 / away 3.3977) |
| `totals_perside_raw` | alias for `μ` (offense_v2 parity) |
| `uncertainty` | 80 % NegBin PI width at `(μ, r_side)` |
| `is_oos` *(tracking)* | True ⟺ the scoring artifact did NOT train on this row's season |
| `train_through_season` *(tracking)* | last season the scoring model trained on |

## The AC — leakage-safe backfill

`generate_totals_generative_signals.py --backfill --leakage-safe` produces genuinely OOS historical
signals via **walk-forward as-of scoring**: each eval season *Y* is scored by a model trained ONLY on
seasons `< Y` (E1.1 `PurgedWalkForwardSplit` — the SAME folds `train_perside_negbin.run_cv` evaluates,
now persisted). The current partial season is scored by the champion (OOS by construction). Warm-up
seasons that are never an eval fold are champion-scored and honestly tagged in-sample.

| season class | scoring model | `is_oos` | `train_through_season` |
|---|---|---|---|
| warm-up (before the first fold) | champion | False | 2025 |
| walk-forward folds (2021–2025) | as-of model (train `< Y`) | True | `Y − 1` |
| current partial season (2026+) | champion | True | 2025 |

**Leakage invariant (enforced in code + test):** `is_oos ⟺ (train_through_season < game_year)`, and
every `is_oos` row's scoring model trained strictly before that season. Downstream OOS eval (E2.6
CLV/PBO gates) filters with a single predicate — `where is_oos`. This is the
[[project_layer3_signal_leakage]] fix applied at registration time: the in-sample-signal contamination
that inflated the 2023–2025 Layer-3 evals cannot recur for this signal.

## Verification (this session, laptop, no external IO)

- **Scoring path** — synthetic per-side frame → `(6, 308)` matrix; per-side `r` correctly assigned
  (home 4.0645 / away 3.3977); `uncertainty > 0`; `is_oos` True on 2026, False on 2025.
- **Leakage-safe backfill** — end-to-end walk-forward over a synthetic 2018–2025 frame (real
  `PurgedWalkForwardSplit` + per-fold LightGBM fits): every `(game_pk, side)` emitted once; the
  leakage invariant holds on every row; fold seasons 2021–2025 all `is_oos=True` with
  `train_through = Y−1`; warm-up 2018–2020 champion-scored `is_oos=False`.
- **Market-blind** — `find_market_columns(feature_names) == []` (the E2.1 CONTRACT-GUARD carries).
- **Tests:** `betting_ml/tests/test_totals_generative_signals.py` (8) + `test_inc25_signal_ordering.py`
  (now 9 generators). Fast gate green.

## Serving wiring (full live wiring — operator-gated at deploy)

- New store `baseball_data.betting_features.totals_generative_signals` (MERGE by `game_pk,side,model_version`).
- 9th generator `generate_totals_generative_signals_op` in `daily_ingestion_job` (fan-in →
  `export_w9_signals_to_s3_op`; INC-25 ordering preserved; guard updated to 9).
- Consumer `feature_pregame_sub_model_signals` gains the `totals_perside_*_v1` column block + LEFT JOIN
  (DuckDB branch; the Snowflake branch auto-includes via the `lakehouse_ext` `select *`).
- Mirrored to S3 by `export_w9_signals_to_s3.py`; ext-table DDL via `generate_w9_external_tables.py`;
  refresh via `refresh_w1_external_tables.py --w9`; consumer rebuild via `run_w1_lakehouse.py --sub-model-signals-only`.
- **Deliberately EXCLUDED from the `signal_freshness_check` HALT floor** (reported only, like `matchup`):
  nothing consumes the signal yet (E2.6 is the intended consumer), so it must not gate `predict_today`.
  Promote to `in_floor` once E2.6 serves from it.

## Operator run order

Both the artifact **and** the calibration JSON must be promoted to S3 for the box to serve
(`totals_perside_v1.pkl` + `totals_distribution_v1.json`). See the session handoff for the exact,
copy-pasteable command sequence.

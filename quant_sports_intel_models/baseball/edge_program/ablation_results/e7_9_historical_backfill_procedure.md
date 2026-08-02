# MLB Edge-E7.9 step 7 — historical prediction backfill: CONDITIONAL procedure

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "explicitly 'Status: NOT TRIGGERED' \u2014 a pre-agreed CONDITIONAL procedure document with no run behind it yet.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


**Status: NOT TRIGGERED.** Step 7 fires only if the E7.9 retrain bake-off PROMOTES a new champion.
As of 2026-07-27 no retrain has run (the full run is an operator job), so there is no prediction
change and nothing to backfill. This document is the pre-agreed procedure + the boundary facts,
determined from the real serving store rather than assumed — so that when a promotion happens the
decision is already made and nobody re-derives it under time pressure.

---

## 1. The tracked window — MEASURED, not assumed

The story said "back to **2023** — or the app-tracked window; DETERMINE the boundary, don't assume
2023 exists." Measured against `daily_model_predictions` in the S3 lakehouse
(`baseball/lakehouse/daily_model_predictions/`), 2026-07-27:

| fact | value |
|---|---|
| full tracked window | **2021-04-01 → 2026-07-27** (55,435 rows, 10 `model_version`s) |
| earliest date | **2021-04-01** — the story's "2023" floor is ~2 seasons too late |
| current champion `v6` (post_lineup) | 2026-03-25 → 2026-07-27, 1,670 rows |
| current champion `pre_lineup_v6` | 2026-06-24 → 2026-07-27, 1,684 rows |
| already-backfilled `v6` (`is_backfill=true`) | 2026-03-25 → 2026-07-04, **1,251 rows** |
| **genuine REAL-TIME `v6`** (`is_backfill=false`) | **2026-06-23 → 2026-07-27, 419 rows** |
| **genuine REAL-TIME `pre_lineup_v6`** | **2026-06-24 → 2026-07-27, 1,684 rows** |

⇒ **Backfill target = 2021-04-01 → the day before the new champion's promotion date**, i.e. the
whole tracked window, not 2023+. The v6 live record starts 2026-06-23 (the E13.11 promotion), which
matches `model_registry.yaml`'s `attribution_start` — the two agree, so the boundary is trustworthy.

## 2. The collision the story warned about — resolved, and structurally so

> ⚠️ "if a genuine REAL-TIME served record exists for the app-live window, PRESERVE it."

It does (the 2,103 `is_backfill=false` v6 rows above). **It cannot be overwritten**, for three
independent reasons that are now pinned by
`betting_ml/tests/test_e7_9_train_serve_consistency.py::test_backfill_writer_cannot_overwrite_the_live_served_record`:

1. `backfill_predictions.py` is **INSERT-only** — no `MERGE`, no `UPDATE`.
2. Every row it writes is stamped **`is_backfill = True`** (Story 30.7 provenance).
3. It **skips** existing `(game_pk, model_version, retrain_tag)` tuples.

And a NEW champion carries a NEW `model_version`, so it does not share a key with the v6 live rows
at all. Downstream, `mart_clv_labeled_games` / `mart_prediction_clv` already rank
`live > backfill` in their per-game dedup, so a hindsight row can never displace a live one in the
scorecards even where both exist.

## 3. 🧨 The landmine step 7 walks into

`dbt/models/mart/mart_clv_labeled_games.sql` **hardcodes** `and model_version = 'v6'`. The day a new
champion is promoted that mart returns **zero rows** and the app's model-vs-market scorecard goes
blank — no error, no HALT, just an empty panel (the same silent-empty class as E9.26b). This is not
hypothetical: it is a single unedited string.

**Mitigation shipped with E7.9:** `test_clv_scorecard_champion_pin_matches_the_registry` ties the
pin to `model_registry.yaml`'s champion `model_version`. Promote without editing the mart and the
fast gate goes red before the scorecard can zero in production.

## 4. Run order (ONLY after a promotion; every step is the OPERATOR's)

Long job → operator, per the >2-min rule. Location is stated for each.

1. **Promote** per `reference_model_promotion_runbook` — new `model_version`, registry updated,
   artifacts in S3, calibrator re-fit trigger evaluated.
2. **Update the champion pin** (LAPTOP): edit `and model_version = '<new>'` in
   `dbt/models/mart/mart_clv_labeled_games.sql`; re-run the guard test.
3. **Backfill** (BOX — reads the feature store, writes Snowflake):
   ```
   docker compose -f services/dagster/aws/docker-compose.yml exec -T \
     -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
     uv run python betting_ml/scripts/backfill_predictions.py --start-year 2021 --dry-run
   ```
   Read the dry-run row count, then re-run **without** `--dry-run`. ⏱️ multi-hour over 5 seasons —
   consider one `--start-year` per season so a failure does not lose the whole run.
4. **Re-derive the CLV / scorecard marts** (BOX):
   ```
   docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
     dbtf build --select mart_prediction_clv+ mart_clv_labeled_games+ --target prod
   ```
5. **Re-write the game-detail blobs** for the affected dates (BOX) —
   `write_serving_store.py --game-detail --date <d>` per date; nothing else re-writes a past
   slate's blob (see the `finalize_prior_slate_game_detail_op` note in CLAUDE.md).
6. **Verify** the live record survived (BOX or LAPTOP, DuckDB over S3): the
   `is_backfill=false` row counts in §1 must be **unchanged**. If any dropped, STOP and restore —
   honest live history was overwritten.

## 5. ⚠️ Honest framing — non-negotiable

A re-backfilled historical series is a **RECOMPUTE / BACKTEST**, not the record we served. The new
champion is selected using data through today, so applying it to 2021 is hindsight by construction.

- Present it as **"the current model's historical projections, and how calibrated they were"** —
  labelled a backtest.
- **Never** a real-time win-rate, ROI, or track-record claim. `best_alpha = 0`.
- The honest live number stays what `honest_live_skill.py` computes over `is_backfill=false` rows.
  That script and `serving_ceiling_diagnostic_30_6.py` already filter on the flag; a backfill must
  not change what they report, and §4 step 6 is the check that it didn't.
- The offline feature surface is **not point-in-time** (`load_features`' own warning: it reads each
  game's row as it exists NOW, post-backfill and dense). So even the leakage-safe re-score is a
  CEILING, not the achievable live number — a second, independent reason this is a backtest.

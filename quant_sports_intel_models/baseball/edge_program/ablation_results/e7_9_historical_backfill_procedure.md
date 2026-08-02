# MLB Edge-E7.9 step 7 — historical prediction backfill: CONDITIONAL procedure

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "a procedure/run-order document, not a bake-off report \u2014 it records no arms, folds or gates of its own. (Was 'Status: NOT TRIGGERED, no run behind it yet'; first executed 2026-08-02 for the MH2.1 promotion, which does not change the exemption: the gates live in the MH2.1 reports, not here.)",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


**Status: FIRST EXECUTED 2026-08-02** (MH2.1 promotion of `total_runs`/`post_lineup`). Step 7 fires
only when a retrain bake-off PROMOTES a new champion. This document was written 2026-07-27 as the
pre-agreed procedure + boundary facts, so that when a promotion happened the decisions were already
made and nobody re-derived them under time pressure. That part held up: §1's window measurements and
§2's live-record guarantees were correct when finally exercised.

> 🩹 **BUT THE PROCEDURE HAD NEVER BEEN RUN, AND `backfill_predictions.py` WAS DEAD.** Executing it
> for real on 2026-08-02 turned up **three independent breaks in the script** — all dating to the
> E13.11 champion swap (2026-06-23) — plus **three wrong commands in §4**. The script had been
> unrunnable for ~6 weeks and nothing surfaced it, because step 7 only fires on a promotion and
> there had not been one. Script fixes in PRs #505 and #508:
>
> 1. **Crash** — `feat_cols` returned the parsed sidecar JSON unconditionally. Sidecars gained
>    `_provenance` at E13.11, so it handed back the DICT and every target was scored on a 2-column
>    matrix built from the JSON KEY NAMES (`ValueError: X has 2 features, but StandardScaler is
>    expecting 21`, ~20 frames deep in sklearn, naming neither the sidecar nor the target).
> 2. **Silent wrong value** — `pd.DataFrame(transform_output, columns=numeric_cols)` SELECTS rather
>    than renames, dropping the two indicator columns `_AddIndicators` appends; the later
>    `reindex(fill_value=0.0)` then asserted "no platoon data / not a new venue" for EVERY game.
>    ⚠️ **This predates the crash — present since the script's first commit (2026-05-12), so EVERY
>    row `backfill_predictions.py` has ever written carries it**, including the ~1,251
>    `market_blind_epic1` rows in §1. A new-champion-vs-old-champion backfill comparison is therefore
>    **not apples-to-apples** until the old tag is re-run on the fixed code.
> 3. **NaN into a classifier that rejects it** — `X_hw` was built from the RAW frame with
>    `fill_value=np.nan`, under a comment describing the pre-E13.11 XGBoost champion (which consumed
>    NaN natively). E13.11's `LogisticRegression` does not.
>
> ⭐ **The generalisable lesson: a documented run order that has never been executed is untested
> code.** Its commands rot exactly like source does, and the code paths it invokes can die silently
> under an unrelated change — here a champion swap in a different subsystem. Three of the six defects
> were in this DOCUMENT, not the script, and none was visible to CI (which never runs either). If a
> conditional procedure is load-bearing, **dry-run it after any change to the models or scripts it
> invokes**, not only when you finally need it.

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
at all.

### 🔧 CORRECTION (MH2.1, 2026-08-02) — the two downstream marts behave DIFFERENTLY

The paragraph that stood here claimed "`mart_clv_labeled_games` / `mart_prediction_clv` already rank
`live > backfill` in their per-game dedup." **That is true of only one of them, and it conflates two
different backfill mechanisms.** Verified against the SQL:

| mart | filter | do `backfill_predictions.py` rows appear? |
|---|---|---|
| `mart_clv_labeled_games` | `where prediction_type in ('morning','post_lineup')` | ❌ **NO — excluded outright** |
| `mart_prediction_clv` | no `prediction_type` filter; partitions by `(game_pk, model_version, coalesce(retrain_tag,''))` | ✅ yes, in its **own partition** |

The distinction that matters:

- **`backfill_predictions.py`** stamps `prediction_type = 'backfill'` ⇒ **it never reaches the
  model-vs-market scorecard.** The `live > backfill` ranking is irrelevant to it because it is
  filtered out one step earlier.
- **`predict_today --is-backfill`** writes `prediction_type = 'morning'`/`'post_lineup'` with
  `is_backfill = TRUE` ⇒ *that* is the mechanism the `live > backfill` ranking protects against.

⇒ **Do not expect the app scorecard to change after running §4.3.** Read the result from
`mart_prediction_clv` filtered to your `--retrain-tag`. If you actually want the scorecard re-scored
on a new champion, that is the `predict_today --is-backfill` path, not this one — a different job
with a different (larger) blast radius, because those rows DO compete with live rows.

The live-record preservation guarantee in the three numbered points above is unaffected — it is
stronger than stated, since `honest_live_skill.py` independently filters `is_backfill = FALSE`.

## 3. 🧨 The landmine step 7 walks into

`dbt/models/mart/mart_clv_labeled_games.sql` **hardcodes** `and model_version = 'v6'`. The day a new
champion is promoted that mart returns **zero rows** and the app's model-vs-market scorecard goes
blank — no error, no HALT, just an empty panel (the same silent-empty class as E9.26b). This is not
hypothetical: it is a single unedited string.

**Mitigation shipped with E7.9:** `test_clv_scorecard_champion_pin_matches_the_registry` ties the
pin to `model_registry.yaml`'s champion `model_version`. Promote without editing the mart and the
fast gate goes red before the scorecard can zero in production.

### 🔧 REFINEMENT (MH2.1, 2026-08-02) — it fires on a HOME_WIN promotion, not on any promotion

The landmine above is real but **narrower than "the day a new champion is promoted"**, and getting
this wrong in the other direction is itself an outage.

`daily_model_predictions.model_version` is derived from **`registry["home_win"]["model_version"]`
ALONE** (`predict_today.py`). It is a *bundle* stamp. So:

- Promote **home_win** (or all three together, as every promotion before MH2.1 did) ⇒ the stamp
  moves, the pin must move with it, the guard fires. **The §3 landmine applies.**
- Promote **total_runs or run_differential ALONE** ⇒ the stamp does **not** move, served rows keep
  reading the old value, and the mart keeps matching them. **The pin must NOT be touched** —
  re-pinning it to the new per-target lineage (e.g. `mh2_1`) would match **zero rows** and cause
  exactly the outage §3 warns about.

MH2.1 was the first per-target promotion and hit precisely this: the same bundle-stamp coupling that
made the swap invisible in the app is what kept the scorecard alive. Pinned by
`test_mh2_1_promotion.py::test_the_clv_scorecard_pin_stays_v6_and_that_is_correct` so a reader
working through this checklist mechanically cannot "helpfully" update a pin that must stay put.

**Rule of thumb:** the pin tracks `home_win.model_version`, nothing else. Check that field, not
"did we promote something".

## 4. Run order (ONLY after a promotion; every step is the OPERATOR's)

Long job → operator, per the >2-min rule. Location is stated for each.

> 🔧 **CORRECTED 2026-08-02 (MH2.1 — first real execution of this procedure).** Steps 3 and 4 said
> BOX and used commands that do not run. Every fix below was found by running them for real:
> - **BOX → LAPTOP.** Operator directive 2026-08-01 (INC-37): a data fix defaults to the LAPTOP. The
>   box is an r6g.large (2 vCPU) and a pinned CPU can starve the Dagster daemon (the INC-32 class) —
>   actively dangerous. The laptop is also measurably faster and has the same S3/Snowflake creds.
> - **`uv run python` does not exist in the box container** (`uv: executable file not found`). It is
>   the LAPTOP convention; the box uses bare `python` (BOX_OPERATIONS.md §"Run a one-off script").
>   Moot now that these steps are laptop steps, but it is why the box form was wrong twice over.
> - **`--target prod` does not exist.** The profile's targets are `baseball_betting_and_fantasy`
>   (the DEFAULT, database `baseball_data`, schema `betting` = production), `dev`, `ci`, `duckdb`.
>   Production = **the default**, i.e. pass NO `--target` — which is exactly what
>   `.github/workflows/dbt_daily_build.yml` does.
> - **`--profiles-dir dbt` is mandatory.** There is a SECOND `~/.dbt/profiles.yml` whose `dev`
>   target writes to schema `BETTING_DBT`, not `betting`. Omit the flag and a build can silently
>   land in the wrong schema. Every CI workflow and `scripts/dbt_state.sh` pass it; so must you.

1. **Promote** per `reference_model_promotion_runbook` — new `model_version`, registry updated,
   artifacts in S3, calibrator re-fit trigger evaluated.
2. **Update the champion pin** (LAPTOP) — ⚠️ **ONLY if `home_win.model_version` changed**; see the
   §3 refinement. For a totals-only or run_diff-only promotion the pin must NOT move. If it did
   change: edit `and model_version = '<new>'` in `dbt/models/mart/mart_clv_labeled_games.sql` and
   re-run the guard test.
3. **Backfill** (LAPTOP — reads the feature store from Snowflake, writes Snowflake):
   ```
   cd <repo root>
   export AWS_DEFAULT_REGION=us-east-2
   uv run python betting_ml/scripts/backfill_predictions.py \
     --start-year 2021 --retrain-tag <new_champion>_backtest --dry-run
   ```
   Read the dry-run row count, then re-run **without** `--dry-run`. ⏱️ multi-hour over 5 seasons —
   run one `--start-year` per season so a failure does not lose the whole run.
   ⚠️ **`--retrain-tag` is REQUIRED, not optional.** The idempotency key is
   `(game_pk, model_version, retrain_tag)`, and `model_version` is the home_win-derived BUNDLE stamp
   — so on a per-target promotion it does NOT change. Reuse the default tag and every game matches
   an existing row, the run skips all of them, writes **nothing**, and **reports success**.
   It also gives the rows their own `mart_prediction_clv` partition (see §2's correction).
4. **Re-derive the CLV / scorecard marts** (LAPTOP; production = the default target):
   ```
   cd <repo root>
   dbtf build --select mart_prediction_clv+ mart_clv_labeled_games+ \
     --project-dir dbt --profiles-dir dbt
   ```
   ⚠️ Per §2's correction, `mart_clv_labeled_games` will NOT pick up step-3 rows (it filters
   `prediction_type in ('morning','post_lineup')`; these are `'backfill'`). This step exists for
   `mart_prediction_clv`. Expect the app scorecard to be unchanged.
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

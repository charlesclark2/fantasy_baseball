# Epic DEV: Making Sure Experiments Never Break Live Data

## What Epic DEV Was About

Before this epic, there was no safety net separating experimental work from the live production system. If a developer ran a script locally — even by accident — it could overwrite live predictions or corrupt the production database tables that power the dashboards and daily scoring.

Epic DEV established a **strict wall between development and production**. The rule after this epic: only scheduled automated jobs running on the main branch can ever write to production. Everything else — local runs, test runs, pull request checks — writes to isolated copies that are completely separate from the live system.

Think of it like a construction company that builds an exact replica of a building in a warehouse before making any changes to the real one. The replica can be smashed, rebuilt, and tested freely. The real building is untouched until the change is confirmed safe.

---

## The Three Parts

### Part 1: dbt Transformation Layer Isolation

The dbt transformation layer is where raw data gets cleaned, joined, and organized into the feature tables that the models read. Every model and every report ultimately depends on these tables.

Before this epic, running `dbtf build` from a laptop would overwrite the same tables that the live system reads. We added a simple rule: **when you're running locally or in CI, write to a separate set of schemas** (`dev_betting`, `dev_betting_features`) rather than the production ones (`betting`, `betting_features`).

The switch happens automatically — you pass `--target dev` to tell dbt you're in development mode, and all outputs land in the isolated schemas. The production schemas are untouched.

| Who runs it | Where it writes |
|---|---|
| GitHub Actions daily job | `betting` / `betting_features` (production) |
| Local development | `dev_betting` / `dev_betting_features` (isolated) |
| Pull request CI check | `ci_betting` / `ci_betting_features` (torn down after check) |

### Part 2: CI Build Gate

Before this epic, the automated check on every pull request only verified that the SQL code was *syntactically valid* — it could parse without errors. It did not actually run the code against Snowflake, so a subtle data logic bug could merge silently and corrupt the production feature tables.

We added a runtime gate: **every pull request now actually builds the modified dbt models in Snowflake** against a temporary CI schema, verifies the output, then tears the schema down. If the build fails — even on a logic error that's syntactically valid SQL — the pull request is blocked.

This was harder to implement than expected. GitHub Actions required some non-obvious plumbing to download the previous day's production `manifest.json` (needed to determine which models were changed) and to correctly set up the dbt binary. Both issues were diagnosed and fixed.

### Part 3: ML Inference Layer Isolation

The prediction scripts (`predict_today.py`, `compute_model_health.py`) write their results to a Snowflake table that powers the Model Performance dashboard and tracks daily scoring. Before this epic, running either script locally — for testing or debugging — would write rows directly into the same production table.

We added a `TARGET_ENV` environment variable that controls where inference scripts write:

- **If `TARGET_ENV` is not set** (the default for any local or ad-hoc run): writes to `betting_ml_dev` — the isolated development copy
- **If `TARGET_ENV=prod`** (set explicitly by GitHub Actions prod workflows only): writes to `betting_ml` — the production table

The safe default means a local run can never accidentally pollute production. Only the automated scheduled job — which explicitly sets `TARGET_ENV=prod` — ever writes live predictions.

### Part 4: Ingestion Script Dry-Run Mode

Both ingestion scripts (`parlay_api_ingestion.py` and `odds_api_ingestion.py`) gained a `--dry-run` flag. When passed, the script makes the API calls and logs everything it *would* insert, but skips all Snowflake writes. This is useful for verifying the API is returning expected data before committing rows.

A `--target dev` option was also added, which redirects writes to isolated dev schema copies of the raw tables — useful when you want to test real ingestion behavior without touching production raw data.

---

## Why This Matters

The discipline enforced by Epic DEV doesn't slow down development — it makes it safer. The practical effect:

- Developers can run any script, any dbt build, or any test locally without fear of breaking live data
- Pull requests get a real runtime check, not just a syntax check
- The production system can only be updated through the controlled, automated pathway

Every Epic that comes after this one benefits from the isolation. Sub-model training scripts, signal generation scripts, and new feature engineering all run in dev by default, and only graduate to production through the same safe pathway.

---

*Epic DEV completed 2026-05-10. All three isolation layers verified. Required as a prerequisite before any model retrains (Epic 1) or sub-model work (Epics 2+).*

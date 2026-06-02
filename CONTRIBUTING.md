# Contributing

Conventions and checklists for working in this repo. See
`quant_sports_intel_models/baseball/implementation_guide.md` for the canonical
development workflow (environment isolation, dbt model checklist, champion
selection policy) and the epic/story roadmap.

---

## Signal generation script conventions

Every sub-model **signal generation** script
(`betting_ml/scripts/**/generate_*_signals.py`) follows one flag contract so it
can be driven identically by hand and by the Dagster `daily_ingestion_job`
(Epic O). When adding a new signal generator, copy this contract exactly.

### Required flags

| Flag | Behavior |
|---|---|
| `--date YYYY-MM-DD` | Score only that date's games. The fast daily path — a single date's read + write, seconds not minutes. |
| `--backfill` | Score every game from the model's training start through today. The one-time / re-promotion path. |
| `--dry-run` | Compute signals and run sanity checks, then print the row count that **would** be written and skip the Snowflake write entirely. |
| `--env {prod,dev}` | Choose the write target: `prod` → `betting_features`, `dev` → `dev_betting_features`. Defaults to `prod`. |

### Rules

- **`--date` and `--backfill` are mutually exclusive and one is required.**
  Implement with `parser.add_mutually_exclusive_group(required=True)`. This
  prevents a 20-minute full backfill from being triggered by accident in the
  daily pipeline, and prevents a no-arg run from doing something unexpected.
- **`--dry-run` writes nothing.** It must be safe to run against `--env prod`
  without touching any table. It prints the row count per signal so the daily
  op can be smoke-tested (`--date <today> --env dev --dry-run`). Expect
  **2 rows per game** (home + away) for a date with ≥ 1 scheduled game.
- **Reads always come from prod feature tables.** Only the *write* target
  switches with `--env`. Mirror the established pattern: the SELECT queries are
  fully qualified to `baseball_data.betting_features.*` (and `baseball_data.betting.*`)
  regardless of env; only the target table (and the temp-table schema) move to
  `dev_betting_features` under `--env dev`.
- **Writes are idempotent.** Use a `MERGE` (or the SCD-2 writer,
  `betting_ml/scripts/scd2_writer.py`) keyed on `(game_pk, side, model_version)`
  so re-running a date is safe.
- **Champion artifact comes from S3** via `sub_model_registry.yaml` /
  `betting_ml/utils/artifact_store.py` when AWS creds are present, falling back
  to the local `betting_ml/models/sub_models/...` path otherwise.

### Reference implementations

`generate_run_env_signals.py` and `generate_bullpen_signals.py` (SCD-2 writer to
`mart_sub_model_signals`); `offense_v2/generate_offense_signals.py`,
`starter_v1/generate_starter_signals.py`, and
`starter_v1/generate_starter_ip_signals.py` (dedicated `*_signals` table +
`MERGE`). All five support the full flag contract above.

### Checklist for a new signal generator

1. Add `--date`, `--backfill`, `--dry-run`, `--env` per the contract above.
2. Add a Dagster op in `pipeline/ops/daily_ingestion_ops.py` (Epic O canonical
   pattern) and wire it into the `daily_ingestion_job` graph.
3. Add it to the `dbt_sub_model_signals_rebuild` fan-in inputs.
4. Add it to the `signal_freshness_check_op` completeness check.
5. Document it in `quant_sports_intel_models/baseball/runbooks/sub_model_signal_ops.md`
   (Epic O.7).

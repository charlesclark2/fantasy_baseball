# Runbook — Sub-Model Signal Pipeline (Epic O)

Operational procedures for the sub-model signal generators and their Dagster
orchestration. Companion to the [Implementation Guide](../implementation_guide.md)
Epic O and the [signal generation conventions](../../../CONTRIBUTING.md).

**Key semantics (read first):** The signal generators are anchored on
`mart_game_results`, which is **pitch-derived** — it contains *completed* games
only. The daily ops therefore score the **recently-completed game window**, not
today's upcoming slate. These signals are the **Layer-3 training feed**;
`predict_today` does **not** consume `feature_pregame_sub_model_signals` yet
(that link is Epic 9). So "fresh signals" means *current through the latest
completed slate*, not *covering today's games*.

---

## 1. Daily signal pipeline

Runs inside `daily_ingestion_job` (Dagster Cloud, ~08:00 ET / 12:00 UTC),
between `dbt_daily_build` and the existing market-SCD-2 → `predict_today` chain.

**Op order** (`pipeline/ops/daily_ingestion_ops.py`, wired in
`pipeline/jobs/daily_ingestion_job.py`):

```
dbt_daily_build
  ├── generate_run_env_signals_op
  ├── generate_offense_signals_op
  ├── generate_starter_signals_op
  ├── generate_matchup_signals_op
  └── generate_starter_ip_signals_op
        └── generate_bullpen_signals_op      (reads starter_ip_signals → runs after)
        ↓ (all six fan in)
  dbt_sub_model_signals_rebuild              (rebuilds the wide PIVOT)
        ↓
  signal_freshness_check                     (non-blocking)
        ↓
  update_market_features_scd2 → … → predict_today_morning
```

Each generator op scores `_recent_completed_dates()` (a 2-day completed window —
day-2 and day-1) with `--env $TARGET_ENV`. The window mirrors the SCD-2 ops'
2-day lookback: robust to ingestion lag / a missed run, and idempotent
(MERGE / SCD-2 skip unchanged rows). `in_process_executor` runs the ops
sequentially in topological order; the `dagster/concurrency_key:
"snowflake_write"` tag is for forward-compatibility with a multiprocess executor.

**Tables written:**

| Op | Champion | Target table |
|---|---|---|
| `generate_run_env_signals_op` | run_env_v4 | `baseball_data.betting.mart_sub_model_signals` (SCD-2) |
| `generate_offense_signals_op` | offense_v2 | `baseball_data.betting_features.offense_v2_signals` |
| `generate_starter_signals_op` | starter_v1 | `baseball_data.betting_features.starter_suppression_signals` |
| `generate_starter_ip_signals_op` | starter_ip_v1 | `baseball_data.betting_features.starter_ip_signals` |
| `generate_bullpen_signals_op` | bullpen_v2 (`--v2-only`) | `baseball_data.betting.mart_sub_model_signals` (SCD-2) |
| `generate_matchup_signals_op` | matchup_v1 | `baseball_data.betting.mart_sub_model_signals` (SCD-2) |
| `dbt_sub_model_signals_rebuild` | — | `baseball_data.betting_features.feature_pregame_sub_model_signals` (PIVOT) |

**Expected runtime:** each generator op is seconds (2 dates × ~15 games);
the PIVOT rebuild ~2–3 s; the freshness check ~1–2 s. The whole signal phase is
a couple of minutes at most.

`--env`: the prod deployment sets `TARGET_ENV=prod` (writes to `betting_features`
/ `betting`); branch/local default to `dev` (`dev_betting_features` / `dev_betting`).
Reads always come from prod feature tables regardless of env.

---

## 2. How to tell if signals are stale

Quick check — run the freshness script against the latest completed slate
(this is exactly what the daily `signal_freshness_check` op runs):

```bash
uv run python scripts/check_signal_freshness.py --env prod
```

It prints per-group coverage on the latest completed slate and exits non-zero
only on catastrophic loss (every game-side below the 40% completeness floor over
the five core groups; matchup is reported but excluded from the floor).

Direct SQL — max signal date per group vs. the latest completed game. If any
core group's `max_signal_date` lags `max_completed_game` by more than ~1 day,
it's stale (a daily op probably failed):

```sql
-- Latest completed regular-season slate (the freshest the generators can score)
select max(game_date) as max_completed_game
from baseball_data.betting.mart_game_results
where game_type = 'R' and home_final_score is not null;

-- mart_sub_model_signals groups (run_env / bullpen / matchup)
select s.sub_model_name, s.sub_model_version, max(g.game_date) as max_signal_date
from baseball_data.betting.mart_sub_model_signals s
join baseball_data.betting.mart_game_results g on g.game_pk = s.game_pk
where s.is_current = true
  and s.sub_model_name in ('run_env_v4','bullpen_v2','matchup_v1')
group by 1, 2;

-- Dedicated betting_features tables (offense / starter / starter_ip)
select 'offense_v2'    as grp, max(game_date) from baseball_data.betting_features.offense_v2_signals;
select 'starter_v1'    as grp, max(game_date) from baseball_data.betting_features.starter_suppression_signals;
select 'starter_ip_v1' as grp, max(game_date) from baseball_data.betting_features.starter_ip_signals;
```

(For `dev`, swap `betting` → `dev_betting` and `betting_features` → `dev_betting_features`.)

---

## 3. Manual re-run (after a Dagster op failure)

1. Open the failed `daily_ingestion_job` run in Dagster Cloud; read the failed
   op's logs (the generator prints its Snowflake write counts and sanity checks).
2. Re-run the affected generator for the missing date(s) directly:

```bash
uv run python -m betting_ml.scripts.generate_run_env_signals               --date YYYY-MM-DD --env prod
uv run python -m betting_ml.scripts.offense_v2.generate_offense_signals     --date YYYY-MM-DD --env prod
uv run python -m betting_ml.scripts.starter_v1.generate_starter_signals     --date YYYY-MM-DD --env prod
uv run python -m betting_ml.scripts.starter_v1.generate_starter_ip_signals  --date YYYY-MM-DD --env prod
uv run python -m betting_ml.scripts.generate_bullpen_signals                --date YYYY-MM-DD --env prod --v2-only
uv run python -m betting_ml.scripts.eb_priors.generate_matchup_signals      --date YYYY-MM-DD --env prod
```

   Add `--dry-run` first to preview row counts without writing. Re-runs are
   idempotent (MERGE / SCD-2). `generate_bullpen_signals` reads
   `starter_ip_signals`, so run `generate_starter_ip_signals` first if both lag.
3. Refresh the PIVOT so downstream sees the new rows:

```bash
dbtf build --select feature_pregame_sub_model_signals --target baseball_betting_and_fantasy
```

4. Confirm with `scripts/check_signal_freshness.py --env prod`.

---

## 4. Adding a new signal generator

Follow the [signal generation conventions](../../../CONTRIBUTING.md) checklist:

1. Implement `--date` / `--backfill` (mutually exclusive, required), `--dry-run`,
   `--env {prod,dev}` per the flag contract. Reads from prod features; only the
   write target switches by env; writes idempotent (MERGE / SCD-2).
2. Add a `generate_<signal>_signals_op` to `pipeline/ops/daily_ingestion_ops.py`
   (loop `_recent_completed_dates()`, pass `--env _target_env()`, tag
   `_SUB_MODEL_OP_TAGS`).
3. Wire it into `pipeline/jobs/daily_ingestion_job.py`: fan out from
   `dbt_daily_build` (or from an upstream signal op if there's a data
   dependency, e.g. bullpen ← starter_ip), and add an `In(Nothing)` input to
   `dbt_sub_model_signals_rebuild`'s fan-in.
4. Add the signal's primary `_mu` column to `signal_freshness_check`
   (`scripts/check_signal_freshness.py` `_SIGNAL_GROUPS`) — mark `in_floor=True`
   only if it has near-complete coverage; availability-gated signals (like
   matchup) should be reported but excluded from the floor.
5. Document the new generator in this runbook (tables, op, runtime).

This is exactly what was done for the five core generators and matchup.

---

## 5. Backfill procedure (new champion promoted mid-season)

When a new champion is promoted, populate historical rows once, then let the
daily op handle new completed dates going forward:

```bash
uv run python -m betting_ml.scripts.<module> --backfill --env prod
dbtf build --select feature_pregame_sub_model_signals --target baseball_betting_and_fantasy
```

For a small, bounded gap (e.g. a few missed days), prefer a per-date loop over
the missing window instead of a full `--backfill` — cheaper and idempotent:

```bash
for d in 2026-05-28 2026-05-29 2026-05-30 2026-05-31; do
  uv run python -m betting_ml.scripts.<module> --date "$d" --env prod
done
```

Always re-run `dbtf build --select feature_pregame_sub_model_signals` afterward
so the PIVOT reflects the new rows.

---

## 6. Concurrency and cost

- All generator ops carry `dagster/concurrency_key: "snowflake_write"`. Under the
  current `in_process_executor` they run sequentially anyway; the tag caps
  concurrency if the job moves to a multiprocess executor (configure the pool
  limit in Dagster Cloud → Deployment → Concurrency).
- **Daily cost is negligible.** Each op reads/writes ~2 dates × ~15 games × 2
  sides on an X-Small warehouse (`COMPUTE_WH`, 60 s auto-suspend); the PIVOT
  rebuild is a single small `table` materialization. This is a rounding error
  next to `dbt_daily_build`.
- **Backfills are the expensive path.** A full `--backfill` re-scores all history
  (offense ~1,900 dates). Run backfills deliberately (champion promotion only),
  and watch the `BASEBALL_MONTHLY_CAP` resource monitor — see the Implementation
  Guide's *Cost discipline* section. Revisit warehouse sizing only if backfills
  become frequent; daily operation does not warrant it.

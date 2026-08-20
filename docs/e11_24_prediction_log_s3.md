# E11.24 P1 — `prediction_log` moves to S3

**Status:** code complete, CI-green. The cutover (the one-time migration) and the 🟥 runtime
gate are **post-merge operator steps** — see the runbook at the bottom.
**Risk class:** monitoring substrate only. `best_alpha = 0`; nothing user-facing; no changelog.

---

## 1. What moved, and why there is no serving blast radius

`baseball_data.config.prediction_log` now lives at

```
s3://baseball-betting-ml-artifacts/baseball/lakehouse/prediction_log/dt=YYYY-MM-DD/part-<uuid>.parquet
```

`daily_model_predictions` — the **serving** artifact — is untouched.

The consumer audit that made this safe (grep across `dbt/`, `app/backend/`, `frontend/`,
`scripts/`, `pipeline/`):

| Reader | Status |
|---|---|
| `scripts/compute_model_health.py` | the only LIVE reader → repointed to S3 |
| `app/pages/4_Model_Performance.py`, `app/home.py` | deprecated Streamlit — not deployed, not edited |
| dbt / backend / frontend | **no references at all** |

`closing_market_prob` in particular has no reader anywhere.

## 2. The three burns this deletes

1. **The `DELETE FROM ... WHERE prediction_date = <date>` — the #2 COMPUTE_WH waker.**
   Irreducible *in place*: the lineup sensor fires one scoped `predict_today --game-pks`
   per completing lineup, so a slate issues ~8–14 of them. It is gone because the table is.
2. **`predict_today._backfill_outcomes()` — 36% of all billable COMPUTE_WH elapsed.**
   Six unbounded `UPDATE` sweeps re-run on *every* predict invocation, entirely redundant
   with the nightly op. Deleted.
3. **`compute_model_health`'s daily Snowflake read.** Now DuckDB-over-S3.

### ⚠️ The residual, stated plainly

`compute_model_health` still **writes** `model_health_log` to Snowflake, so the op still
resumes COMPUTE_WH once a day. Wake is a queue (#679) — removing one waker promotes the
next — so **P1 alone will not make the band suspend**. Measured while migrating:
`model_health_log` has **zero readers anywhere in the repo** (its own writer and its DDL,
nothing else), so flipping it to S3 is nearly free. It is a *second table migration*, which
is a decision, not something this story took on its own authority. Carded as the obvious
next flip; `test_e11_24_prediction_log_wiring.py` pins the residual so it can't be quietly
mis-reported as already handled.

## 3. A data-quality defect this fixes (measured, not inferred)

`_backfill_outcomes()` ran **mid-slate** and its sweeps only fill NULLs. The
"closing" price filter (`ingestion_ts < commence_time`) is satisfied by a *morning*
snapshot too — so a game's `closing_market_prob` was frozen hours before the close, and
stuck.

Game **822859** (2026-08-18), measured:

| reading | value |
|---|---|
| stored in Snowflake | 0.605935 |
| snapshot at 17:30 UTC | 0.606963 |
| snapshot at 21:30 UTC | 0.603283 |
| **true last pre-game (00:00:06 UTC)** | **0.592235** |

The stored value corresponds to an ~18:00–21:00 UTC snapshot. The new enrichment is bounded
to `dt < current_game_date()`, so every row it touches belongs to a game already played;
re-run on a scratch prefix it produced **0.592235**. `actual_outcome` reached **exact
parity** with Snowflake on every checked row.

That bound is load-bearing twice: it is also what keeps the nightly compaction away from
the only partition an overlapping `predict_today` can append to.

## 4. Why append-and-dedup, not read-modify-write

`services/dagster/dagster.yaml` caps each `concurrency_group` at one run but allows
`max_concurrent_runs: 5` **across** groups, so `daily_ingestion_job` (morning predict) and
`lineup_monitor_job` (the scoped re-scores) can overlap. A read-modify-write of a shared
date object would silently lose one of two overlapping writes. Every writer only ever
creates its own object; the read view collapses part multiplicity.

**The #885 overwrite semantics are preserved exactly**, and they are the whole reason the
log holds a slate instead of 1–2 games:

| shape | Snowflake | S3 |
|---|---|---|
| full-slate run | date-wide `DELETE` + `INSERT` | put the new part, then delete the parts listed before it |
| scoped `--game-pks` run | `DELETE ... game_pk IN (...)` + `INSERT` | append a batch that OWNS those games |
| scoped run that logged nothing | the `DELETE` still fired | an **ownership marker** row (`market IS NULL`) |

The view resolves each `(prediction_date, game_pk)` to the **latest batch that owned it**,
then drops markers — so a batch replaces every row of its games, *including replacing them
with nothing*. That last case is the one append-only cannot express with data rows alone.

`loaded_at` is a fixed-width ISO **VARCHAR** (the standing cure for Snowflake misreading
binary parquet timestamps); fixed width matters because lexicographic order is the dedup's
ordering.

## 5. INC-25 — an ordering defect fixed on the way past

`compute_model_health` (the READER) ran **before** `backfill_prediction_log` (its own
PRODUCER) in `daily_ingestion_job`, so the health metric was permanently one enrichment
cycle behind. Swapped. Both are monitoring-only terminal leaves, so the swap cannot reach
the serving path. Pinned as a dependency **edge** (AST), never as source-line order — the
executor runs the graph topologically, so a line-order test would be vacuous (INC-40).

## 6. Tier change (deliberate)

The prediction_log write is now **WARN-tier**. It used to be able to take the slate down:
an exception propagated out of `main()`, and `predict_today` is HALT-tier — a
monitoring-substrate write could withhold every prediction. That is a mis-tiering (E11.7:
peripheral monitoring is WARN) and not one this migration should inherit. A failure prints
a loud `[ALERT]` to stderr and emits `[METRIC] prediction_log_write_ok=0`, never a silent
pass.

## 7. Guards

| file | what it pins |
|---|---|
| `test_e11_24_prediction_log_s3.py` | the #885 semantics, **re-anchored** onto the new writer — real parquet, real DuckDB, real view (20 clauses) |
| `test_e11_24_prediction_log_wiring.py` | the call sites: the INC-25 edge, the S3 read, the `dt < today` bound, the reconstruction (20 clauses) |
| `test_predict_today_write.py` | the pure projection + "the Snowflake statements are gone" |
| `e11_24_prediction_log_red_proof.py` | **24/24 deliberate breaks go RED** |

Three clauses were **vacuous on their first cut** and were found by the RED proof, not by a
green run: an absence scan satisfied by the migration's own explanatory prose (so the source
view now strips docstrings *and* comments — structurally, via AST, so SQL constants survive),
and a `sys.path.insert` scan that stayed green with the insert wrapped in a dead branch (now
measured by effect).

## 8. What is NOT covered by CI

CI mocks all IO. `predict_today` is HALT-tier and this is box/DuckDB/boto3 code, so
**CI-green is necessary-not-sufficient**. Validated on the laptop against real S3 and the
real marts (scratch prefix, cleaned up): the writer round-trips, the dedup resolves, the
enrichment reproduces Snowflake's `actual_outcome` exactly and corrects the frozen CLV. The
box has **no static AWS keys** — `make_s3_client()` passes none, so boto3 resolves the
instance role — and that path can only be proven by a real box run.

---

## 9. Operator runbook (post-merge)

### Step 1 — dry-run the migration (**LAPTOP**)

Prints the per-date game-count parity table (`prediction_log` vs `daily_model_predictions`),
before and after the repair. Writes nothing.

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy && \
uv run python scripts/migrate_prediction_log_to_s3.py --dry-run
```

Expected: 30 dates carry the #885 signature (≤2 games logged against ≥5 scheduled); the
default window (2026-08-02..08-15) repairs 14 of them to full parity.

**The defect actually starts 2026-07-17, not 08-02.** The remaining 16 dates are
07-17..08-01. Repairing them costs nothing and makes the migrated table correct, so the
recommended window is wider than the card's:

```bash
uv run python scripts/migrate_prediction_log_to_s3.py --dry-run --repair-start 2026-07-17
```

### Step 2 — run the migration + verify (**LAPTOP**, ~1–2 min)

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy && \
uv run python scripts/migrate_prediction_log_to_s3.py --repair-start 2026-07-17 --verify
```

⚠️ This writes **PRODUCTION** S3 keys. It writes **nothing** to Snowflake. `--verify`
re-reads the written parquet through the real `prediction_log` view and diffs it against
Snowflake row-for-row; it exits non-zero on any row that fails to round-trip.

### Step 3 — enrich (**LAPTOP**)

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy && \
uv run python scripts/backfill_prediction_log.py --all --dry-run
```

then, if it looks right:

```bash
uv run python scripts/backfill_prediction_log.py --all
```

Reconstructed rows land with NULL `actual_outcome` / `closing_market_prob`; this fills them
from the marts. (The nightly op would do it too, over its 45-day default window.)

Optional, and a judgement call: `--recompute-clv` re-derives `closing_market_prob` even
where it is already set. The historical values were frozen mid-slate by the removed sweeps
and are therefore wrong (§3), but rewriting history is the operator's call. No reader is
affected either way.

### Step 4 — 🟥 RUNTIME GATE (**EC2 BOX**, after the deploy)

Three things must be proven on the box, because CI cannot see any of them.

**(a) the boto3 writer works under the instance role (no AKID)**

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
  python -c "
import sys; sys.path.insert(0,'/app')
from scripts.utils import prediction_log_store as S
S.KEY_PREFIX='baseball/lakehouse_scratch/e11_24_p1_boxsmoke/prediction_log'
S.LOC=f's3://{S.BUCKET}/{S.KEY_PREFIX}'
print(S.write_rows([{'game_pk':1,'market':'h2h','model_prob':0.5}], '2026-08-16'))
c=S.connect(); print(c.execute('select * from prediction_log').fetchall())
s3=S.make_s3_client()
[s3.delete_object(Bucket=S.BUCKET,Key=k) for k in S.list_partition_keys('2026-08-16')]
print('cleaned')
"
```

**(b) `predict_today` still produces correct output** — the next real
`predict_today_morning` run. Confirm in the Dagster step log:

* `Wrote N rows to prediction_log (S3) for <date> (full-slate overwrite) ... -> baseball/lakehouse/prediction_log/dt=<date>/part-...`
* `[METRIC] prediction_log_write_ok=1`
* `daily_model_predictions` row counts unchanged for the slate.

Then, after the lineup sensor has fired a few scoped re-scores, that the date holds the
**whole slate** (this is the #885 property, now on the new mechanism):

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
  python -c "
import sys; sys.path.insert(0,'/app')
from scripts.utils import prediction_log_store as S
c=S.connect()
print(c.execute('select prediction_date, count(distinct game_pk), count(*) from prediction_log group by 1 order by 1 desc limit 5').fetchall())
"
```

**(c) `compute_model_health` reads its columns from S3** — the same daily run:

```
INFO  Fetched N prediction_log rows with outcomes
INFO  ECE=... Brier=... n=N
```

`N` should be in the ~150–200 range for a healthy 14-day h2h window (it was 18 while the
#885 defect was live).

### Step 5 — the success metric (**LAPTOP**, after ≥1 clean day)

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy && \
uv run python scripts/report_e11_24_wake_census.py --days 12
```

Read it **PER DAY**, never off an aggregate straddling the flip — an aggregate over a window
containing the flip measures residue. The `'8 model-health/pred_log'` family should fall to
~0 (its surviving `model_health_log` INSERT does not mention `prediction_log`, so it lands
in a different bucket). Judge the *lever* on that family; judge the *bill* on whether
COMPUTE_WH actually **suspends** across 14:00–03:00 UTC, which needs the rest of the band
cleared too.

### Step 6 — retire the Snowflake table

Only after (a)–(c) are green and a day or two of clean runs. `baseball_data.config.prediction_log`
has no writer left in live code (the only remaining statements are in the
Streamlit-only `betting_ml/scripts/predict_today.py` twin, marked dead in place). Leave it
frozen as a rollback, then drop it — and when you do, run the INC-27 sweep first
(`grep -rIn "config\.prediction_log"`), because a raw-SQL string consumer is invisible to
any DAG.

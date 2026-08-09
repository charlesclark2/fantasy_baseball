# E11.24 — `player_sequential_posteriors` re-export ordering (INC-25)

**Branch** `e11.24-posterior` · **2026-08-09** · ⛔ **CODE-READY, DEPLOY HELD** until the target-6
soak closes (Sun 2026-08-09 T+3). A pipeline-ordering change alters `COMPUTE_WH` activity, so
deploying mid-census would contaminate that reading.

---

## The defect

`lakehouse_w8a_feature_layer_op` mirrors `player_sequential_posteriors` to S3 at graph position
**lk9**, near the top of `daily_ingestion_job`. `update_player_posteriors_op` writes the Snowflake
table **~40 minutes later** (measured writer timestamps cluster at ~13:02 UTC against a 12:00 UTC
job start). Nothing re-exported it afterwards, so the S3 parquet was permanently one writer-cycle
behind — the INC-25 shape: *a consumer reads an S3 mirror that is built upstream of its own
refresh.*

**Measured 2026-08-09 03:45 UTC** (laptop; Snowflake side on `MONITOR_WH` so the live target-6
`COMPUTE_WH` soak was untouched):

| source | `max(update_ts)` | `max(game_date)` | rows | lag |
|---|---|---|---|---|
| Snowflake | 2026-08-08 13:02:18.671140 | 2026-08-07 | 400,193 | 14.72 h |
| S3 mirror | 2026-08-07 13:02:08.375345 | 2026-08-06 | 399,759 | **38.72 h** |
| delta | **+24.00 h** | one slate | +434 | — |

The +434 rows are exactly the 08-08 writer batch. **38.72 h already breaches the entry's own 36 h
freshness threshold** — so E11.24 target 3's estimate of "~12 h of headroom" was optimistic; the
mirror was over the line, not near it. Target 3 was right to hold the flip.

### Why the lag was invisible at the obvious measuring point

`check_data_freshness.py` has **two callers** — the INC-38 *every-caller* lesson, applied to the
**read** side:

1. the in-job `check_data_freshness` op at **s15**, and
2. a host cron at `30 12,17 * * *` UTC (`services/dagster/aws/capture.crontab`).

At **s15** the Snowflake writer has not run yet either, so Snowflake and S3 return the *same*
value and the gap is structurally invisible. Only the off-cycle reads see it: the 17:30 cron reads
Snowflake at ~4.5 h and the mirror at ~28.5 h, and any read past ~01:00 UTC breaches 36 h outright.
There is also a race at the 12:30 cron — if it beats lk9 on a slow morning, the mirror is *two*
cycles behind (~47.5 h).

> **Durable lesson.** Measure a mirror's lag at the reader's **worst** moment, not an arbitrary
> one. A single reading taken at the one instant both sources agree reports a healthy mirror.

---

## The fix

`reexport_player_seq_posteriors_op` — re-mirrors the table **downstream of its writer**, in
**both** jobs that run that writer:

| job | wiring |
|---|---|
| `daily_ingestion_job` | `reexport_player_seq_posteriors_op(start=p_player)` |
| `statcast_catchup_job` | `reexport_player_seq_posteriors_op(start=pp)` |

Design points, each pinned by a RED-proven guard:

- **Fan-out leaf.** Its output is never bound, so nothing can chain off it. A mirror failure is
  structurally incapable of blocking `p_team` / `p_matchup` / `predict`.
- **ALERT tier, and it really pages.** `send_alert(..., severity="ERROR",
  dedup_key="player_seq_mirror_reexport")`, never re-raises. E11.30's finding was that several
  ops labelled ALERT only ever reached `context.log.warning`; a tier enforced by a docstring is
  not enforced.
- **Both callers.** Wiring only the daily job would let a late-Statcast catch-up advance Snowflake
  while the parquet froze until morning (INC-38).
- **Not gated on `W8A_LAKEHOUSE_S3`.** The export is a plain `SELECT *` → S3 with no dependency on
  the `--w8a` DuckDB build. Gating it would freeze the mirror silently if the flag ever lapsed
  (the documented-but-never-set class), and a new flag means a box `.env` edit that fails the next
  deploy until the operator makes it.
- **The lk9 export stays.** It is what guarantees the mirror exists *before* the `--w8a` DuckDB
  build reads it. Keeping both costs one extra `SELECT *` of a ~400 k-row table on a warehouse the
  writer immediately above has already resumed — **added active-time, not an added wake** (#679:
  wake is a queue). Retiring the lk9 copy is a possible follow-up: the two schemes carry identical
  content at lk9, but only lk9 picks up an out-of-band write (a hand-run backfill) between writer
  runs.

### The freshness entry

`check_data_freshness.py`'s `player_sequential_posteriors` entry flips `snowflake` → **`s3`**,
clearing the third of target 3's five blockers.

⚠️ **The flip and the ordering fix must deploy together.** An S3-sourced entry on a box still
running the un-reordered graph is a guaranteed daily false STALE. Pinned by
`test_reading_s3_requires_the_reexport_to_be_wired_in_every_writer_job`.

---

## What this does *not* buy: the #675 wake question, answered honestly

PR #675 notes that repointing the EB reads "is not itself a wake reduction" because the op keeps a
Snowflake connection for the `player_sequential_posteriors` SCD-2 read/write. The question this
story was asked to settle is whether a **fresh mirror** lets that read move too.

Complete residual Snowflake surface of `update_player_posteriors.py --catchup --s3`, **after**
#675 and after this change:

| # | statement | site | occupies `COMPUTE_WH`? | moveable to the mirror? |
|---|---|---|---|---|
| 1 | `CREATE TABLE IF NOT EXISTS …` | `_ensure_table` | **No** — metadata-only DDL (cloud-services billed, #679) | n/a |
| 2 | `SELECT MAX(game_date) … WHERE season=` (catch-up frontier) | `catchup.run_catchup` | Yes | **Yes — newly, because of this change** |
| 3 | `SELECT DISTINCT game_date FROM mart_game_results …` | `catchup.run_catchup` | Yes | Yes, but shared by all three sequential writers → a separate change |
| 4 | `SELECT … WHERE is_current` (1,577 rows, season 2026) | `_load_current_seq`, per date | Yes | **No** |
| 5 | `UPDATE … SET is_current=FALSE` + `INSERT` + `COMMIT` | `_write_updates`, per date | Yes (DML) | **No** |

**#4 cannot move, and the reason is not freshness — it is read-your-own-write.** `run_catchup`
calls `update_for_date` once per missing date in chronological order, and date *k+1*'s
`_load_current_seq` must observe date *k*'s `_write_updates` from the **same process**. A snapshot
mirror (re-exported once, after the script finishes) cannot serve that. It would appear to work on
a one-date advance — the common case — and silently corrupt the chain on a ≥2-date catch-up, which
is precisely the self-healing case `--catchup` exists for. That is the E9.53 non-idempotency class
in a new costume.

**#5 is irreducible** short of moving the store itself off Snowflake.

⇒ **The op remains a `COMPUTE_WH` waker, and this change does not convert #675 into a wake
reduction for it.** Even moving #2 and #3 buys nothing: wake is a queue, so #5's DML simply pays
the resume that #2 would have paid, and #4's payload is 1,577 rows — the residual reads are
active-time noise, not a cost target. Reporting otherwise would be the "we ran fewer arms"
under-explanation one domain over.

What this change *is* worth:

1. It clears target 3's third blocker (the freshness entry now reads S3).
2. It fixes a live 38.72 h staleness defect that was already breaching its own threshold.
3. It removes the 12:30-cron-vs-lk9 race that could show ~47.5 h.
4. It is the precursor for the EB finding below.

---

## Side finding (measured, **not** acted on): the served EB as-of seq prior is one game stale

`eb_starter_posteriors` / `eb_batter_posteriors_raw` join `player_sequential_posteriors` as-of
(`sp.game_date < s.game_date`) and publish `prior_age_days`. Their DuckDB branch is built at lk9
off the mirror; their Snowflake branch "MERGEs from the lakehouse_ext external table" (the model's
own comment), so the served values come from that lk9 build.

Batters play nearly every day, so on a current chain the minimum `prior_age_days` over a slate is
**1**. Measured on Snowflake (`MONITOR_WH`), `eb_batter_posteriors_raw`:

| game_date | n_batters | min age | median age |
|---|---|---|---|
| **2026-08-08 (the live slate)** | 276 | **2** | **2** |
| 2026-08-07 | 268 | 1 | 1 |
| 2026-08-06 | 197 | 1 | 1 |
| 2026-08-05 | 269 | 1 | 1 |

The pattern is fully explained by the lag: the DuckDB branch is a **full** rebuild each run, so
every historical slate is recomputed the next morning off a mirror that by then includes the
missing day — **history self-heals, and only the current slate is stale**. That is why nobody saw
it. The daily job's own comment ("the sequential update ops run first *so their as-of sequential
column is fresh*") describes the pre-W8a-cutover world and is no longer true of the served path.

**Not fixed here, deliberately.** The fix is to rebuild `--eb-batter-only` / `--eb-starter-only`
(plus the `--w8a` ext refresh) *after* the writers — a serving-path graph reorder, and this repo
allows one serving flip per soak (`update_team_posteriors.py`'s own note). This change is its
precursor: the reorder is only correct once the mirror is re-exported post-writer. Card it as a
follow-up. Impact is small and systematic, on a `best_alpha = 0` program.

---

## Operator steps (POST-SOAK)

Land in the **same** post-soak window as #682 (target 3) and #675 (EB repoint) — all three touch
this surface. See the PR handoff for the exact merge order and the 🟥 runtime-gate checks.

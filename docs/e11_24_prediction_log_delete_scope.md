# E11.24 — the `prediction_log` per-date DELETE: scope finding + the defect it was hiding

**Branch** `e11-24-prediction-log-delete` · **Relates** E11.24, #882, #675/#662 · `best_alpha=0`

---

## TL;DR

The card asked for a **ranged DELETE to collapse ~8 resumes/day → 1**. That fix is **not
available**, and the reason is measured, not argued: there is **no per-date loop**. The
8 daily DELETEs are **8 separate OS processes** all deleting the **same single date**.
There is nothing to range over, and nothing to merge.

**Reported as a null on the wake lever.** No wake credit is claimed.

But scoping the statement surfaced a live, measured defect in it: that date-wide DELETE
is **destroying ~90% of `prediction_log` every day**. That is fixed here.

---

## 1. Why the ranged DELETE cannot exist (the STOP-and-report)

`_write_prediction_log` is called **once per `predict_today` process**, with that
process's single `target_date` (`scripts/predict_today.py`, driver at the bottom of the
file). A multi-date loop exists **only** in `--start/--end` range mode — the Story 30.7
backfill — and E13.11 already batched that path's `daily_model_predictions` write, while
the documented backfill invocations pass `--no-log-snowflake`, so `_write_prediction_log`
never runs there at all.

The live cadence is: **1 morning run + N lineup-sensor runs**, each a separate process
(`lineup_predict` → `predict_today --game-pks <newly confirmed>`, `pipeline/ops/sensor_ops.py`).

Measured on `snowflake.account_usage.query_history`, COMPUTE_WH, 10 days
(read on the MONITORING warehouse, so the measurement did not wake the thing measured):

| day | DELETEs | distinct sessions | waits | DELETE is its session's FIRST occupying stmt |
|---|---|---|---|---|
| 08-16 | 8 | **8** | 7 | **8/8** |
| 08-15 | 14 | **14** | 12 | **14/14** |
| 08-14 | 9 | **9** | 6 | **9/9** |
| 08-13 | 9 | **9** | 7 | **9/9** |
| 08-12 | 10 | **10** | 7 | **10/10** |
| 08-11 | 7 | **7** | 6 | **7/7** |
| 08-10 | 9 | **9** | 7 | **9/9** |

Three facts settle it:

1. **sessions == DELETEs, 1:1.** Every DELETE is in its own session, i.e. its own process.
   Statements in different processes cannot be combined into one statement.
2. **All of a day's DELETEs carry the SAME date literal.** `query_history` returns exactly
   one distinct DELETE text per calendar day
   (`... WHERE prediction_date = '2026-08-12'`, ×66 rows in retention). A
   `WHERE prediction_date IN (…)` / `BETWEEN` has **nothing to range over** — there is
   only ever one date in flight.
3. **The DELETE is the session's first warehouse-occupying statement in 100% of cases**
   (65/65 over 7 days), which is why it inherited the waker role after #675/#662 moved
   the surrounding reads to S3. Correct attribution — wrong remedy.

### …and removing it would not remove the wake either

The wake-is-a-queue caveat (#679) is usually a hedge. Here it is **measured and total**.
Restricting `query_history` to the sessions that contain a `prediction_log` DELETE, the
**entire** warehouse-occupying content of those sessions is:

| statement | n (3d) | waits |
|---|---|---|
| `DELETE FROM …prediction_log WHERE prediction_date …` | 31 | **25** |
| `INSERT INTO …prediction_log (…)` | 31 | 0 |

**Two statements. Nothing else.** So a MERGE collapsing DELETE+INSERT into one statement
saves **zero resumes** — the MERGE simply becomes the first occupying statement and pays
the same wake. And deleting the write outright would promote the next Snowflake statement
in the process (`_backfill_outcomes`'s UPDATEs, then the `daily_model_predictions` write —
each on its own connection, all currently at **0 waits** precisely because this DELETE
already woke the warehouse) into the waker role.

**8 → 1 is unreachable from this statement.** The only levers that would move it are
reducing the number of `predict_today` invocations, or moving `prediction_log` off
Snowflake entirely. Neither is this card.

---

## 2. What scoping the statement actually found

`prediction_log` is keyed `(prediction_date, game_pk, market)`. The lineup sensor scopes
each re-score to newly-confirmed games (`--game-pks`), and `main()` filters `df_today`
to that subset — but `_write_prediction_log` issued a **date-wide** DELETE and then
inserted only **its own** games. So each scoped run wiped every previous run's rows.

The A1.12 fix for exactly this shape already exists in the same file
(`_post_lineup_delete_sql`, whose docstring describes the bug verbatim) — it was applied
to `daily_model_predictions` and **never to `prediction_log`**.

### Measured (2026-08-16, prod)

`prediction_log` vs the slate it is supposed to log:

| date | games in `daily_model_predictions` | games in `prediction_log` |
|---|---|---|
| 08-16 | 15 | **1** |
| 08-15 | 15 | **1** |
| 08-14 | 14 | **2** |
| 08-13 | 9 | **2** |
| 08-12 | 15 | **1** |
| 08-11 | 15 | **1** |
| 08-10 | 10 | **2** |

The survivor count equals the size of the **last** sensor batch of the day — the
fingerprint of a date-wide overwrite followed by a partial insert.

**Onset** (avg games/date in `prediction_log`, by month):

| … | 2026-05 | 2026-06 | 2026-07 | 2026-08 |
|---|---|---|---|---|
| avg games/date | 12.80 | 12.63 | **7.14** | **1.25** |

Healthy at ~10/date from 2024 through 2026-06, degrading through July, collapsed in
August. That trajectory tracks the lineup monitor becoming progressively more per-game
(the INC-32 per-game readiness gate, 2026-07-19), which is what turned one full-slate
post_lineup run into ~8-14 scoped ones.

### Blast radius — stated precisely, and it is NOT user-facing

The only live consumer is `scripts/compute_model_health.py`, which reads a 14-day window
of `prediction_log` and writes `model_health_log`. Its sample **today** is:

```
sample_n = 18   (14 dates, 18 games)   ← should be ~180
```

So the calibration monitor has been running on ~10% of its intended sample.

Not user-facing: `model_health` appears nowhere in `frontend/` or `app/backend/`, and
`model_health_alert_sensor` reads the S3 `daily_model_predictions` path, not this table.
The other reader is `app/pages/4_Model_Performance.py` — **legacy Streamlit, not deployed**.
⇒ **no `frontend/data/changelog.json` entry** (nothing user-facing changed).

Also note what is **not** affected: `daily_model_predictions` — the actual serving
artifact — was always correct here (A1.12 scoped its DELETE in 2026). Nothing a user
sees was ever wrong. This is a **monitoring-substrate** defect.

---

## 3. The change

`scripts/predict_today.py`:

- **New `_prediction_log_delete_sql(scoped_game_pks)`** — mirrors `_post_lineup_delete_sql`.
  Scoped run → `AND game_pk IN (…)`; full-slate run → date-wide, **unchanged**.
- **`main()` computes `prediction_log_scope`** — the final scored game set, set whenever
  the slate was narrowed by *either* filter (`--game-pks`, or the `--lineup-confirmed`
  filter actually dropping games). Owned by the caller, not derived from `output_rows`,
  so a scored game that produced no loggable row still has its stale prior row cleared.
- **The date is now a BOUND parameter** (`%(d)s`), not an f-string literal. Two real
  consequences: it closes an injection surface on a serving write, and it collapses the
  one-distinct-`query_text`-per-date fragmentation that hid this statement from the wake
  census in the first place.
- **The chosen path is logged** (`(scoped overwrite)` / `(full-slate overwrite)` + the
  cleared row count), so a wrong pick is visible in the run log.

⚠️ **This is a deliberate SEMANTICS CHANGE, not the card's "identical semantics" refactor.**
A scoped run now deletes strictly fewer rows. That is the fix. The full-slate morning
path is byte-identical in behaviour.

### Guards

`betting_ml/tests/test_predict_today_write.py` (+15 clauses, `serving-ops` shard). The
load-bearing one is a **behavioural replay** against an in-memory table that actually
applies the emitted SQL: morning full slate → six one-game sensor runs → assert the log
still holds all 15 games. A source-substring assertion could not have shown that.

Each clause is **independently RED-proven** — four deliberate breaks, each verified to
land on disk *and* to move the asserted predicate before pytest is invoked (#682/#815):

| break | result |
|---|---|
| B1 helper ignores the scope (the pre-fix date-wide DELETE) | **RED** (7 clauses) |
| B2 `main()` stops passing the scope (wired-but-not-invoked) | **RED** |
| B3 the date reverts to an inlined literal | **RED** (3 clauses) |
| B4 the lineup-confirmed filter stops marking the slate narrowed | **RED** |

Two harness defects were caught by the harness's own checks and are worth carrying:

- The first `vanishing_token` check tested the **whole file**, and `game_pk IN` survives
  in the new **docstring** → the check fired. Assert the mutation moves the predicate in
  the **replaced region**, and that its count in comment/docstring-stripped code drops.
- **B1's anchor was ambiguous.** `_post_lineup_delete_sql` and `_prediction_log_delete_sql`
  have **byte-identical tails**, and A1.12's comes first, so `replace(old, new, 1)`
  mutated the *wrong function* — and the run came back GREEN, reading as "the guard is
  vacuous" when the guard was fine and the *break* had missed. A RED proof must assert
  **its anchor is unique**, or a false vacuity report is the result.
  (The duplication is real; a shared helper was **not** extracted — that would edit
  A1.12's HALT-tier path for cosmetics, and this change already owes a runtime gate.)

---

## 4. Verification

- **CI** — fast+slow gates on the PR. Local smoke: `serving-ops` shard, 1607 passed.
- 🟥 **RUNTIME GATE (operator, required).** `predict_today.py` is HALT-tier serving code
  and CI mocks all IO, so CI-green is necessary-not-sufficient. See the closeout for the
  box commands: one full-slate run then one `--game-pks` scoped run, asserting the
  scoped run **preserves** the rest of the slate's log rows and leaves
  `daily_model_predictions` unchanged.
- **Post-deploy census** — ⛔ do **not** expect the DELETE family's wait count to move.
  The expected reading is **wait count unchanged (~8/day)** and **`prediction_log` games
  per date rising from 1-2 to match `daily_model_predictions`**. A per-day cut is the
  only quotable form (an aggregate straddling the deploy measures the residue).

---

## 5. Honest framing

- **The wake lever is a NULL.** No resumes are removed; the queue simply keeps its head.
  The bill only moves when COMPUTE_WH suspends for longer stretches, which this cannot
  cause. Book **zero** credit on wait-count.
- **The value delivered is correctness** — restoring ~90% of a monitoring table — plus
  code quality (bound parameter, logged path). ⚠️ The claim that the bind "closed the
  census fragmentation" is **retracted** — see §6.3; it did the opposite.
- **The card's premise was wrong**, and cheaply checkable: "a per-date loop" was a
  reading of the source, and one `query_history` cut (sessions vs DELETEs) refuted it.
  Pre-flighting a card against the running system stays the cheapest step in the story.


---

## 6. Post-soak verification (2026-08-19, measured on `MONITOR_WH`)

PR #885 merged to `dev` 2026-08-17 (`f2b89612`) and reached the box with the `dev→main`
promotion. Three post-deploy slates are now in retention. All reads below ran on
**`MONITOR_WH`**, so the measurement did not wake the warehouse being measured.

### 6.1 The wake lever — the predicted NULL is CONFIRMED

Per-day (never aggregated across the deploy date), COMPUTE_WH, `warehouse_size is not null`:

| UTC day | execs | sessions | waits | scoped-form stmts |
|---|---|---|---|---|
| 08-10 | 9 | 9 | 7 | 0 |
| 08-11 | 7 | 7 | 6 | 0 |
| 08-12 | 9 | 9 | 6 | 0 |
| 08-13 | 10 | 10 | 8 | 0 |
| 08-14 | 9 | 9 | 6 | 0 |
| 08-15 | 14 | 14 | 12 | 0 |
| 08-16 | 8 | 8 | 7 | 0 |
| **08-17** (deploy) | 10 | 10 | **9** | **7** |
| **08-18** | 8 | 8 | **7** | **6** |

Pre-deploy waits 6-12 (mean ~7.4); post-deploy **9 and 7**. **Executions HOLD and waits
HOLD** — the working-gate signature does not apply here because there was never a gate to
work: this was pre-registered as a null and it read as a null. ⛔ Book zero wake credit.

Both measurement days were structurally normal (08-17 an 11-game slate, 08-18 a 15-game
slate; execution counts inside the pre-deploy 7-14 range), so this is not an outage day
faking a volume delta.

**Why no `n` of soak days could change this** — the DELETE is its session's **first
warehouse-occupying statement on 100% of days, before and after** (65/65 pre, 18/18 post).
Every DELETE is its own OS process, so removing or merging the statement only promotes its
own INSERT to pay the resume. The null is structural, not underpowered. (Note 08-05..08-09
show `waits = 0` on 7-12 executions: before #675/#662 moved the surrounding reads to S3,
something else in the process paid the resume. The DELETE *inherited* the waker role — the
queue thesis, #679, visible in the data.)

### 6.2 The real fix — CONFIRMED in production over a 3-day soak

`prediction_log` distinct games per date vs `daily_model_predictions`:

| date | dmp games | log games | log rows | retained |
|---|---|---|---|---|
| 08-11 | 15 | 1 | 2 | 6.7% |
| 08-12 | 15 | 1 | 2 | 6.7% |
| 08-13 | 9 | 2 | 4 | 22.2% |
| 08-14 | 14 | 2 | 4 | 14.3% |
| 08-15 | 15 | 1 | 2 | 6.7% |
| **08-16** | 15 | **15** | 30 | **100%** |
| **08-17** | 11 | **11** | 22 | **100%** |
| **08-18** | 15 | **15** | 30 | **100%** |

Pre-fix retention 6.7-25%; post-fix **100% on every slate**, at the full 2 rows/game.
The scoped and full-slate paths are both visible in `query_history` as designed — a
date-wide DELETE for the full-slate morning run, `AND game_pk IN (...)` for each sensor
re-score.

### 6.3 ⚠️ Retraction — the bind did NOT close the census fragmentation

§5 originally credited the fix with "the census fragmentation closed". **Measured false.**
The Snowflake Python connector defaults to `paramstyle='pyformat'` = **client-side**
binding, so the value is escaped and interpolated into the text before it is sent, and
`query_history` still shows a date **literal**:

```
DELETE FROM baseball_data.config.prediction_log WHERE prediction_date = '2026-08-17'
DELETE FROM baseball_data.config.prediction_log WHERE prediction_date = '2026-08-17' AND game_pk IN (823589, 824478)
```

The injection half of the claim stands (the connector escapes the value; an f-string did
not). The census half is the reverse of what was written: distinct `query_text` per day
went **1 → 7-9**, because the scoped form inlines its game_pk list. ⇒ a future waker board
over this family **must** normalise date *and number* literals before `GROUP BY
query_text` — the scoped fix makes that normalisation more load-bearing, not less. The
guards (`test_date_is_a_bound_parameter_not_an_inlined_literal`,
`test_the_writer_no_longer_inlines_the_date`) are unaffected: they assert the API-level
bind, which is real.

### 6.4 Still open (not this story)

- ⛔ **History is forward-only.** 08-02..08-15 still hold 1-2 games/date. As of 08-19,
  `compute_model_health`'s 14-day window (08-05..08-18) contains **3 good days of 14**;
  it self-heals ~2026-08-30. A backfill from `daily_model_predictions` is feasible and
  separately carded.
- **`_backfill_outcomes()`** remains the live lever in this file — 36% of billable
  COMPUTE_WH elapsed, 0 waits (an ACTIVE-MINUTES lever, not a wake lever), and verbatim
  duplicated by the daily `backfill_prediction_log` op. Separate card.

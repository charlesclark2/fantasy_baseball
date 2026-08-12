# INC-42 — `--w3pre-only` HALTed at the timestamp-stringify DESCRIBE (transient, self-healed)

**Date:** 2026-08-11 (alert), diagnosed 2026-08-12 02:55–03:30 UTC
**Severity:** P3 — contained. **No prediction loss.** Served game-state (`stg_statsapi_games`) went
stale for at most one intraday tick.
**Status:** system healthy; **root cause NOT yet confirmed** — the DuckDB error text is only on the
box and is the one missing piece (see *What is still open*).

---

## TL;DR

`run_w1_lakehouse.py --w3pre-only` raised at `_string_timestamp_wrap` L583 (the
`DESCRIBE SELECT * FROM (mart_sql)`). That is the INC-23 cure behaving **exactly as designed** —
it refuses to COPY unwrapped when it cannot bind the plan.

The failure was **transient**. It is **not** a SQL defect at a use-site, and it is **not** caused by
the E11.24 view flips. There is **nothing to fix by casting** — the same SQL binds cleanly against
the same S3 today. The open question is *which* transient condition broke the bind, and the answer
is one line of the box error text.

⚠️ **The premise in the alert overstates the blast radius.** "The lineup monitor sees no newly
confirmed lineups → post_lineup stops for the rest of the slate (3 games unscored, 6.5h, no page)"
is a **verbatim description of the ORIGINAL INC-41 incident of 2026-08-06**, quoted from the code
comment at `pipeline/ops/intraday_ops.py:179-186`. INC-41's fix landed and **worked here**: the
`--w3pre-only` and `--w7b-only` legs now fail independently, so the lineups rebuild still ran, the
monitor was never blind, and the op paged (E11.30). Measured consequence below.

---

## Measured facts

### 1. The E11.24 flip is RULED OUT

| Check | Result |
|---|---|
| `git diff --stat origin/main HEAD -- scripts/run_w1_lakehouse.py` | **empty** — identical |
| Last commits touching the four w3pre marts | `3e3cefa9`, `f9f9f61c` — **INC-41**, not #662/#675 |
| Does w3pre read anything the flip changed? | **No.** w3pre flattens `lakehouse_raw/` JSON directly (no W1/W2 view dependency, by design); the flipped models (`feature_pregame_game_features(_raw)`, `eb_*_posteriors`) are strictly **downstream** |
| Flip still intact on `main` (b68b1a97) | ✅ Snowflake branch is `{{ config(materialized='view') }}` |

⇒ **Not a rollback trigger.** Step E is not indicated.

### 2. It is not a static SQL / schema defect — the same SQL binds today

Laptop, 2026-08-12 03:00 UTC, same prod S3, `--dry-run` (the DESCRIBE runs **before** the dry-run
branch, so this exercises the exact failing call with no S3 write):

```
stg_oddsapi_odds:     6,600,088 rows   bind OK
stg_oddsapi_events:      10,629 rows   bind OK
stg_derivative_odds:  8,090,095 rows   bind OK
stg_statsapi_games:      27,273 rows   bind OK
```

A schema/column change in an upstream source (hypothesis *c*) would **persist**; this did not.
An INC-23 VARCHAR-timestamp use-site error (hypothesis *b*) would also persist. Both are excluded.

### 3. It self-healed; the path is fully healthy

Full w3pre pass completed in one sweep, and the sibling `--w7b-only` leg immediately after:

| object | LastModified (UTC) |
|---|---|
| `lakehouse/stg_oddsapi_odds/data.parquet` | 2026-08-12T03:04:22 |
| `lakehouse/stg_oddsapi_events/data.parquet` | 2026-08-12T03:04:28 |
| `lakehouse/stg_derivative_odds/data.parquet` | 2026-08-12T03:07:26 |
| `lakehouse/stg_statsapi_games/data.parquet` | 2026-08-12T03:07:38 |
| `lakehouse/stg_statsapi_probable_pitchers/data.parquet` | 2026-08-12T03:08:39 |
| `lakehouse/stg_statsapi_lineups_wide/data.parquet` | 2026-08-12T03:08:40 |

### 4. Serving consequence — none for predictions

`baseball_data.betting_ml.daily_model_predictions`:

| score_date | tier | games | rows | intraday_fallback | window (UTC) |
|---|---|---|---|---|---|
| 2026-08-09 | morning | 15 | 30 | 0 | 10:40 → 13:11 |
| 2026-08-09 | post_lineup | 15 | 15 | 0 | 15:16 → 22:17 |
| 2026-08-10 | morning | 10 | 20 | 0 | 10:12 → 13:08 |
| 2026-08-10 | post_lineup | 10 | 10 | 0 | 19:50 → 23:21 |
| **2026-08-11** | **morning** | **15** | **15** | **0** | **13:09 only** |
| **2026-08-11** | **post_lineup** | **15** | **15** | **0** | 19:44 → 23:44 |

- **post_lineup covered the full 15-game slate with zero fallback.** The monitor was never blind —
  INC-41's per-leg isolation did its job.
- **One anomaly worth an operator confirm:** every other day shows **two** morning runs
  (~10:1x–10:4x and ~13:0x UTC); 2026-08-11 has only the 13:09 one. The earlier morning run is
  absent. Whether that is causally linked to this HALT (i.e. a *daily*-path w3pre failure, which is
  gate-tiered HALT) is **unconfirmed** — it needs the Dagit run history.

---

## Leading hypothesis (corroborated, NOT confirmed)

**A concurrent raw-partition DELETE landing inside the bind's list→open window ⇒ HTTP 404 at
DESCRIBE.**

`read_parquet(..., union_by_name=true)` (all four w3pre models use it) **lists** the glob, then
**opens every file's footer** to compute the union schema. If a key is deleted between the list and
the open, the bind raises.

**Reproduced fingerprint** (bind over a list containing one absent key):

```
HTTPException: HTTP Error: HTTP GET error reading
's3://baseball-betting-ml-artifacts/baseball/lakehouse_raw/mlb_events_raw/dt=.../part-<uuid>.parquet'
in region 'us-east-2' (HTTP 404 Not Found)
```

**Who deletes, and how wide is the window:**

| raw source | write mode | deletes? | files | bind time |
|---|---|---|---|---|
| `monthly_schedule` | `overwrite_partition` **+ `prune_same_month_partitions`** | **YES — every capture** | 5 | 0.4 s |
| `mlb_odds_raw` | append (1 part / 30 min) | no | 1,820 | 21.8 s |
| `derivative_odds_raw` | append (1 part / 30 min) | no | 1,206 | 23.0 s |
| `mlb_events_raw` | append | no | 39 | 0.6 s |

`monthly_schedule` is the **only** raw source under active deletion —
`ingest_statsapi.py:481` (`write_raw_rows_s3(..., mode="overwrite_partition")` → `_delete_partition`)
and `:484` (`prune_same_month_partitions("monthly_schedule", today_dt)`), fired by
`intraday_schedule_capture_*` (`*/30 14-23` + `0,30 0-3` UTC) and by the daily
`ingest_statsapi_schedule` op. Corroborating: `dt=2026-08-11` is **already gone** from
`lakehouse_raw/monthly_schedule/` (pruned); only `2026-05-31, 06-30, 07-31, 08-12, __nullts__`
remain.

That collides with `stg_statsapi_games` — the **last** model in the w3pre loop and the
serving-critical one (game universe → the lineup monitor's Preview gate → the alert's symptom).
The odds sources are append-only, so they have no delete race despite the much wider window.

**Competing candidates the error text discriminates in one line:**

| error text contains | verdict |
|---|---|
| `HTTP 404 Not Found` on a `lakehouse_raw/**/part-*.parquet` key | ✅ concurrent-delete race — **confirmed** |
| `HTTP 503` / `500` / `SlowDown` / timeout | transient S3 throttle — retry is the cure, writer is innocent |
| `Binder Error` / `Could not convert` / type mismatch | genuine schema conflict — but then it would still be failing today, so this is very unlikely |

---

## What is still open (the one thing that needs the box)

The DuckDB error text. `_string_timestamp_wrap` embeds it in the raised `RuntimeError`
(`… Underlying DuckDB binder error: {exc}`), so it exists — the alert's traceback was truncated
before it. `ssm:*` is denied for `baseball-access-user`, so this is an **operator** step. See the
handoff commands.

---

## Recommended fix (contingent on the error confirming the 404 race)

⛔ **No use-site cast is warranted** — there is no bad expression to cast. Do not "fix" the SQL.

**Option 1 — reader-side bounded retry (recommended).** Retry the DESCRIBE (and the COPY) once or
twice, with a short backoff, **only** on a transient S3 read signature (404/5xx on a
`lakehouse_raw/` key). The glob is re-listed on retry, so a benign concurrent-writer race resolves
itself. This preserves the INC-23 contract exactly: a genuine binder error fails every attempt and
still HALTs. It is source-agnostic, so it also covers the S3-throttle candidate.

**Option 2 — writer-side ordering: put-then-delete.** Write the new `part-<uuid>.parquet` **first**,
then delete the previously-listed keys. Filenames are uuid-unique so there is never a collision, and
it additionally closes a real data-loss window (today a crash between `_delete_partition` and
`put_object` leaves the partition **empty**).
⚠️ **Do not apply this blanket-wide.** During the window both old and new files exist, so any
staging model that does **not** dedup would transiently double-count — a *silent wrong answer*,
strictly worse than a loud HALT (the E9.52 class). It is safe for `monthly_schedule` specifically,
because `stg_statsapi_games` collapses to one row per `game_pk`; it is **not** obviously safe for
the other `overwrite_partition` callers (`export_odds_raw_to_s3.py`, `export_w11_raw_to_s3.py`).

Suggested: **Option 1 now**; Option 2 scoped to `monthly_schedule` only, if at all.

🟥 **Runtime gate applies.** CI mocks all IO, so neither option is verifiable in CI — the merge bar
is a real box run of the intraday tick.

---

## Cheap standing detector (offered, not built)

The intraday tick rebuilds `stg_statsapi_games` (w3pre leg) and `stg_statsapi_lineups_wide` (w7b
leg) within ~60 s of each other. **A divergence between those two objects' in-parquet build times is
exactly the signature of one leg failing while the other succeeds.** Today they sit at 03:07:38 vs
03:08:40 — healthy. This is a natural registry entry for INC-41's `artifact_freshness` monitor
(⛔ read the timestamp from inside the parquet, never `LastModified`, per INC-41).

---

## Why this recurs and why it stayed invisible

- The bind is a **read** racing a **writer** on a shared prefix; nothing in the code coordinates them.
- It is **data-independent**, so it never reproduces after the fact — the classic "green on re-run"
  that reads as a fluke.
- CI mocks all IO, so no gate can see it (🟥 runtime-gate class).
- It was **loud** only because E11.30 wired `send_alert` into this op and INC-41 split the legs.
  Both fixes did their job here; this incident is what "contained" looks like.

# INC-42 — `--w3pre-only` HALTed at the timestamp-stringify DESCRIBE (transient, self-healed)

**Date:** 2026-08-11 (alert), diagnosed 2026-08-12 02:55–03:30 UTC
**Severity:** P3 — contained. **No prediction loss.** Served game-state (`stg_statsapi_games`) went
stale for at most one intraday tick.
**Status:** root cause **CONFIRMED 2026-08-12** — `RequestTimeTooSkewed`: the box's clock drifted
past S3's SigV4 ~15-minute tolerance, so every DuckDB-over-S3 read 403'd while boto3 (which
auto-corrects for skew) kept working. System currently healthy. Remaining action is operator-side
NTP + a detection gap.

---

## TL;DR

`run_w1_lakehouse.py --w3pre-only` raised at `_string_timestamp_wrap` L583 (the
`DESCRIBE SELECT * FROM (mart_sql)`). That is the INC-23 cure behaving **exactly as designed** —
it refuses to COPY unwrapped when it cannot bind the plan.

The failure was **transient**. It is **not** a SQL defect at a use-site, and it is **not** caused by
the E11.24 view flips. There is **nothing to fix by casting**. The bind failed because the S3 GET it
issues was **rejected for clock skew** (`RequestTimeTooSkewed`, HTTP 403) — an infrastructure fault
on the box, surfacing through the INC-23 guard because that guard is simply the first thing in the
build that touches S3.

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

## ✅ ROOT CAUSE — CONFIRMED 2026-08-12: the box's clock drifted past S3's SigV4 tolerance

Retrieved from the Dagster Postgres event log (runs `bc60b651…` and `28432dfb…`, both of which the
run list reports as **SUCCESS**):

```
_duckdb.HTTPException: HTTP Error: HTTP GET error reading
'https://baseball-betting-ml-artifacts.s3.us-east-2.amazonaws.com/baseball/lakehouse_raw/
 mlb_odds_raw/dt%3D2026-08-05/part-4f973f642fb5.parquet' in region 'us-east-2' (HTTP 403 Forbidden)

RequestTimeTooSkewed: The difference between the request time and the current time is too large.
```

**AWS SigV4 signatures carry a timestamp, and S3 rejects any request signed more than ~15 minutes
from its own clock with `RequestTimeTooSkewed` (HTTP 403).** The host clock on the Dagster box
drifted past that bound. The objects named in the errors (`dt=2026-08-05`, `dt=2026-08-01`) are
irrelevant — they are simply whichever file the bind happened to open first. Nothing is wrong with
the data, the SQL, or the partitions.

### ⚠️ The hypothesis in the previous revision of this doc is REFUTED

The earlier leading hypothesis — a concurrent raw-partition DELETE inside the `union_by_name`
list→open window producing an HTTP **404** — was wrong. It was circumstantially corroborated
(`monthly_schedule` really is the only raw source under active deletion; the bind windows really
are 20+ s) and it was labelled unconfirmed, but the measured error is a **403 on authentication**,
not a 404 on a missing key. The delete-race mechanism plays no part in this incident, and the
`monthly_schedule` write ordering needs no change. Recorded here rather than deleted, because the
corroboration looked strong and the next reader should know it did not survive contact with the
error text.

### Why it presented as intermittent, and only in the DuckDB reads

This is the discriminating detail, and it explains every observation:

| client | skew handling | observed |
|---|---|---|
| **botocore/boto3** | auto-corrects: on a skew error it reads S3's `Date` header, caches the offset and retries | the odds/derivative captures kept writing **every 30 min, unbroken** through the incident |
| **DuckDB `httpfs`** | no correction — signs with the local clock and hard-fails | the w3pre binds HALTed |

So the writers stayed perfectly healthy while the readers died — which is exactly the pattern in
the S3 listings (an unbroken `mlb_odds_raw` part file at every 30-minute mark on 08-11) and is why
this looked like a reader-side or data-side defect. It self-healed when the clock came back inside
tolerance. ⚠️ **delta-rs / `object_store` (the Rust S3 client used by `scripts/utils/delta_lake.py`)
is in the same category as DuckDB, not boto3** — a future skew episode should be expected to break
Delta reads/writes too.

### The immediate fix is operator-side (no code can substitute)

Diagnose and correct NTP on the box; see the handoff commands. Contributing factor worth checking:
the box is an `r6g.large` (2 vCPU) and INC-37 already documents that a pinned CPU starves the
Dagster daemon — sustained CPU saturation degrades timekeeping too, so check CloudWatch CPU around
the failure window.

### Detection gap — CLOSED (follow-up PR, branch `inc42-clock-skew`)

There was **no clock/NTP check anywhere in the repo** (verified by grep). `healthcheck.sh` runs
every 5 minutes on the host and already owns paging, a fail-threshold and a cooldown — it probed
containers and HTTP endpoints, never the clock. A drift that breaks every DuckDB-over-S3 read while
leaving boto3 healthy was invisible to every existing monitor.

Added as check (3) in `services/dagster/aws/healthcheck.sh`: it reads the `Date` header from
`s3.us-east-2.amazonaws.com` — **S3's own clock is the one that decides whether a signature is
accepted**, so this measures the quantity that actually matters rather than a local NTP daemon's
estimate of itself. No credentials needed. Pages at `CLOCK_SKEW_MAX_S` (default **300 s**), leaving
runway below the ~900 s hard bound; an unreadable or unparseable header reports **UNEVALUABLE and
pages**, never healthy (NF1.7(a)).

Three traps found while building it, each of which would have made the probe useless:

- ⛔ **no `-f`** — it suppresses output on ≥400, discarding the header the moment S3 answers 403.
- ⛔ **no `-L`** — the root endpoint answers **307** to `aws.amazon.com`; following it would measure
  a different host's clock. (Found by dumping the real response, not assumed.)
- ⛔ **no awk `IGNORECASE`** — a GNU-awk extension. The first cut used it and **returned an empty
  string when tested live**; under BSD/mawk it matches nothing, so the probe would report
  UNEVALUABLE every 5 minutes and the monitor would get muted. `tolower($0) ~ /^date:/` is portable.

Guard: `betting_ml/tests/test_inc42_clock_skew_probe.py` — 8 clauses, each pinned in its own test so
one deleted clause fails exactly one test (NF-D17). All 7 deliberate mutations proven red: `-f`,
`-L`, `IGNORECASE`, a silently-passing unevaluable branch, a threshold at the hard bound, a dropped
absolute value, and deleting the stanza. ⚠️ Note on the harness: the stanza-deletion mutation first
*looked* green because the runner counted only `FAILED` and pytest reports a failing fixture as
`ERROR` — the guard was fine, the red-proof's reporting was not.

⏭️ **Unverified on the box:** GNU `date -u -d "Wed, 12 Aug 2026 06:04:37 GMT"` (docker was
unavailable locally to prove it). The format is RFC 1123 and coreutils parses it, but confirm with
the one-liner in the handoff. It fails safe either way — an unparseable header pages UNEVALUABLE.

## Remediation runbook (operator, on the box)

```bash
date -u; chronyc tracking; chronyc sources -v; systemctl status chronyd
curl -sS -o /dev/null -D - https://s3.us-east-2.amazonaws.com | grep -i '^date:'   # the clock that matters
sudo systemctl enable --now chronyd && sudo chronyc makestep && chronyc tracking
grep -n '169.254.169.123' /etc/chrony.conf   # the Amazon Time Sync Service should be configured
```

Contributing factor worth ruling in/out: the box is an `r6g.large` (2 vCPU) and INC-37 already
documents that sustained CPU saturation starves the Dagster daemon — it degrades timekeeping too.
Check CloudWatch CPU around the failure window.


## ⭐ ROOT CAUSE OF THE MISDIAGNOSIS — the page structurally could not carry the error (FIXED)

Confirmed on the box 2026-08-12: `--w3pre-only --dry-run` binds all four models there too, and
**every recent `intraday_schedule_job` run reports SUCCESS** — the op catches each leg
(ALERT-loud-but-continue), so the job never fails and the failing run cannot be found by status.

The page itself is why this stalled. `intraday_ops` recorded each failed leg as `str(exc)[:300]`,
but `_run_script` raises

```python
Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")
```

— the exception carries the child's **entire traceback**, and a Python traceback puts its payload
(the exception type and message) at the **TAIL**. A head slice keeps
`Traceback (most recent call last):` plus the first frames and discards the diagnosis.

**Measured:**

| quantity | value |
|---|---|
| `_string_timestamp_wrap` boilerplate preamble | **420 chars** |
| index of its `Underlying DuckDB binder error:` marker | **388** |
| chars of the real DuckDB error surviving `[:300]` | **0** |

The 300-char page ended mid-sentence inside the *generic* hint — "Most common cause: a date
function or interval arithmetic applied to a column" — so the alert's own hedged boilerplate read
as the diagnosis, which is exactly how this incident came to be framed as an INC-23 use-site cast.
That is the **INC-40 lesson verbatim** ("an alert's own SUGGESTED-CAUSE banner is diagnostic
anchoring"), and it means a transient S3 404, a throttle and a genuine binder error all produced a
**byte-identical page** — the same non-discriminating-output class as the `curl -f`/301
healthcheck. A truncation that yields the same text for every cause is not a short diagnosis; it is
no diagnosis.

**FIX (shipped in this PR):** `betting_ml/monitoring/alert_text.exc_digest` keeps the head (script
+ exit code) *and* the tail (the exception), naming how much was elided. Both call sites in
`intraday_ops.py` use it; the pure logic lives in `betting_ml/` per the E11.23 fast-gate rule.
Guard: `betting_ml/tests/test_inc42_alert_carries_the_real_error.py` — the load-bearing case is
`test_two_different_causes_do_not_page_identically` (a length assertion alone would pass on a
truncation that is short *and* useless). RED-proven both ways: reverting `intraday_ops.py` to
`str(exc)[:300]` fails the source guard; reverting `exc_digest` to a head slice fails 3 of 6.

## Retrieval note (how the error was finally obtained)

⚠️ The failing run **cannot be found by run status** — the op catches each leg, so
`intraday_schedule_job` reports SUCCESS. It was recovered by grepping the Dagster **Postgres event
log** (which survives container recreation, unlike stdout) for `FAILED — continuing to the next
leg`. `ssm:*` is denied for `baseball-access-user`, so this was an operator step.

Once the `exc_digest` fix above deploys, the next occurrence pages `RequestTimeTooSkewed` directly
and needs no box dig at all — the fix is validated by this incident: the one string that mattered
sat at the very tail of the message, exactly where `[:300]` was discarding it.

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

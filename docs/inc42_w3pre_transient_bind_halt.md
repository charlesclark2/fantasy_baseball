# INC-42 — `--w3pre-only` HALTed at the timestamp-stringify DESCRIBE (transient, self-healed)

**Date:** 2026-08-11 (alert), diagnosed 2026-08-12 02:55–03:30 UTC
**Severity:** P3 — contained. **No prediction loss.** Served game-state (`stg_statsapi_games`) went
stale for at most one intraday tick.
**Status:** S3 rejected the request with `RequestTimeTooSkewed`, so the **signature DuckDB sent
carried a stale timestamp** — but the **host clock is EXONERATED** (chrony RMS offset 2.9 µs; see
§ *The host clock is not the cause*). A skewed signature and a skewed clock are not the same thing.
**Root cause is NOT established**; the mechanism is under investigation. System currently healthy.

---

## TL;DR

`run_w1_lakehouse.py --w3pre-only` raised at `_string_timestamp_wrap` L583 (the
`DESCRIBE SELECT * FROM (mart_sql)`). That is the INC-23 cure behaving **exactly as designed** —
it refuses to COPY unwrapped when it cannot bind the plan.

The failure was **transient**. It is **not** a SQL defect at a use-site, and it is **not** caused by
the E11.24 view flips. There is **nothing to fix by casting**. The bind failed because the S3 GET it
issues was **rejected for a stale signature timestamp** (`RequestTimeTooSkewed`, HTTP 403). It
surfaces through the INC-23 guard only because that guard is the first thing in the build to touch
S3. ⚠️ **The host clock has since been measured and is exonerated** — so the remaining question is
why DuckDB signed with an out-of-bounds timestamp on a correct clock.

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

## The error S3 actually returned (confirmed 2026-08-12)

Retrieved from the Dagster Postgres event log (runs `bc60b651…` and `28432dfb…`, both of which the
run list reports as **SUCCESS**):

```
_duckdb.HTTPException: HTTP Error: HTTP GET error reading
'https://baseball-betting-ml-artifacts.s3.us-east-2.amazonaws.com/baseball/lakehouse_raw/
 mlb_odds_raw/dt%3D2026-08-05/part-4f973f642fb5.parquet' in region 'us-east-2' (HTTP 403 Forbidden)

RequestTimeTooSkewed: The difference between the request time and the current time is too large.
```

**AWS SigV4 signatures carry a timestamp, and S3 rejects any request signed more than ~15 minutes
from its own clock with `RequestTimeTooSkewed` (HTTP 403).** The objects named in the errors
(`dt=2026-08-05`, `dt=2026-08-01`) are irrelevant — they are simply whichever file the bind happened
to open first. Nothing is wrong with the data, the SQL, or the partitions.

⚠️ **This says the SIGNATURE's timestamp was out of bounds. It does NOT, on its own, say the host
clock was wrong** — and the clock evidence below says it was not.

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
this looked like a reader-side or data-side defect. ⚠️ This asymmetry holds for a stale *signature*
just as it does for a wrong *clock*: botocore re-signs per request and self-corrects, DuckDB does
not. It therefore does **not** discriminate between the two, and reading it as proof of clock drift
is what produced the wrong conclusion in the previous revision. ⚠️ **delta-rs / `object_store` (the Rust S3 client used by `scripts/utils/delta_lake.py`)
is in the same category as DuckDB, not boto3** — a future skew episode should be expected to break
Delta reads/writes too.

### ⚠️ This section previously prescribed an NTP fix — that was wrong

An earlier revision concluded the box clock had drifted and sent the operator to `chronyc makestep`.
The clock was measured immediately afterwards and is healthy (see *The host clock is NOT the
cause*), so that step was a no-op. The correct reading of this asymmetry is below.

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

✅ **Verified on the box 2026-08-12:** GNU `date -u -d` parsed the live S3 header and returned
`1786515532`. The one open item on the probe is closed.

⭐ **Its value here was the opposite of what it was built for, and worth recording.** The probe was
added to catch clock drift; on this incident it reads **GREEN**, and that is precisely what redirects
the investigation — it separates "the clock is wrong" from "the signature is stale" in five minutes
rather than a day. A monitor that cheaply **exonerates** a suspect is doing real work; the first
revision of this doc concluded "the clock drifted" for want of exactly that reading.

## The host clock is NOT the cause (measured on the box, 2026-08-12 06:18 UTC)

```
System time     : 0.000000891 seconds slow of NTP time
RMS offset      : 0.000002901 seconds          <-- 2.9 microseconds
Reference ID    : A9FEA97B (169.254.169.123)   <-- Amazon Time Sync, reach 377
chronyd.service : active (running) since 2026-06-30    <-- never restarted
host `date -u` 06:18:44   vs   S3 `Date:` 06:18:51     <-- 7 s, i.e. command sequencing
```

⭐ **The decisive figure is `RMS offset = 2.9 µs`, a LONG-TERM average.** A ≥900 s excursion anywhere
in the recent past would leave that number enormous, and because chronyd has not restarted since
30 June, its statistics were never reset. Natural drift cannot do it either: `Frequency 24.554 ppm`
is ~2.1 s/day, so reaching 900 s of skew unaided would take well over a year.

⇒ **The host clock was accurate. S3 rejected a signature whose timestamp was stale, which is a
different fault.** The `chronyc makestep` in the original runbook was a no-op and is not the fix.

## Root cause: two candidates REFUTED by measurement, one strong lead remains

### ✗ (3) "the failures are older than the current clock state" — REFUTED

The failing runs are **recent**, not historical:

| run | started (UTC) |
|---|---|
| `28432dfb` | **2026-08-11 23:00:37** |
| `bc60b651` | **2026-08-12 01:00:30** |

Both sit well inside the window over which chrony reports a 2.9 µs RMS offset, so they cannot be
explained by the 2026-08-01 `Can't synchronise: no majority` episode.

### ✗ (1) "DuckDB captures the signing timestamp at secret creation" — REFUTED

Laptop, DuckDB 1.5.3 (the version `uv.lock` pins), one connection + one secret, re-probed over time.
⚠️ The run is only partly valid: the laptop **suspended** mid-experiment (wall clock 06:22 → 22:34
while `time.monotonic()` advanced just 35 min), so the +16 and +24 probes failed on
`Could not resolve hostname` — DNS after wake, not a signing fault. Those two points carry no
information.

The **final probe is informative, and is a stronger test than the one designed**: a secret and
connection that were **35 monotonic-minutes and ~16 wall-clock hours old** still produced a
signature S3 accepted (`OK, 2,881 rows`). ⇒ **DuckDB signs each request against the current clock**;
a stale secret does not yield a stale signature.

### ⭐ The remaining lead: a long bind under peak contention, on a glob that grows without bound

Two patterns in the failures, neither of which is a coincidence:

**(a) Both failed on `mlb_odds_raw` — the largest glob**, and it is the first model in the w3pre
loop (`stg_oddsapi_odds`). Measured bind cost on an *idle* laptop: **21.8 s across 1,820 files**,
versus 0.4–0.6 s for the small sources.

**(b) Both fired at `:00` past the hour, and `:00` is the peak-contention minute.** From
`capture.crontab`, at `:30` only the two odds captures run; at `:00` three more jobs start —
`weather-capture`, and `backfill_multisport_props_to_s3.py --mode live` (`0 13-23,0-4`, so **23:00
and 01:00 are both inside that window**), which runs **inside `dagster-codeloc` itself** — the same
container as the failing subprocess — pulling 8 markets × 2 regions. All of this on an `r6g.large`
with **2 vCPU**, the box INC-37 already documents as starving under load. `00:00` is in the same
window and did *not* fail, so this is a race, not a determinism.

⭐ **And the exposure is growing on a clock.** `mlb_odds_raw` is written **append-only** — one part
file per 30-minute capture, **48/day, with no compaction and no retention**:

| | |
|---|---|
| partitions | **97** (`dt=2026-04-23` … `dt=2026-08-12`) |
| files/day | **48** (measured: 07-20 = 48, 08-10 = 48, 08-11 = 48) |
| total files | ~**1,820** |
| onset | `dt=2026-07-05` holds **1** file — the S3-native flip (CLAUDE.md dates it 2026-07-05) |

38 days × 48 ≈ 1,824, which matches the observed count. So the bind's cost — and the number of
signed S3 requests in flight during it — **has been rising linearly since 2026-07-05 and will keep
rising**. That is a coherent explanation for why this class of failure is appearing *now*.

The precise mechanism linking a long, heavily-contended bind to a signature aged past 900 s is
**not yet established** (a retry that reuses the original `Authorization` header is the usual shape,
but that is a hypothesis, not a measurement — and this incident has already burned two).

### ⭐ Recommended fix — mechanism-independent

**Compact / retain `lakehouse_raw/mlb_odds_raw/`.** It removes the exposure regardless of which
signing mechanism is at fault, and it fixes an unbounded-growth problem that is a defect in its own
right: every consumer of that glob pays the 48-files-per-day tax forever. The repo already owns
this pattern (`prune_same_month_partitions` for `monthly_schedule`; INC-20 latest-per-month
retention). Cutting 1,820 files to a few dozen takes the bind from 21.8 s to ~1 s.

Cheap complementary mitigation: **de-conflict the schedule** — move
`backfill_multisport_props_to_s3.py --mode live` off `:00` (e.g. `20 13-23,0-4`), so the heaviest
in-container job stops colliding with the intraday w3pre bind.

⚠️ Neither should be presented as "the fix" until the mechanism is confirmed — but the compaction
is worth doing on its own merits either way.

### ✅ SHIPPED (2026-08-12) — compaction, and what it measured

`scripts/compact_lakehouse_raw.py` + a daily `40 8 * * *` UTC line in `capture.crontab`.

| | before | after |
|---|---|---|
| files in the glob | **1,859** | **98** |
| `describe select * from read_parquet(**/*.parquet, union_by_name=true)` | **21.8 s** | **1.57 s** |
| rows | — | **preserved** (see below) |

⛔ **Row-preserving, NOT retention.** Nothing is deleted. The odds snapshot *trajectory* is the
signal (`mart_odds_line_movement`, `mart_bookmaker_disagreement`), so dropping old snapshots would
destroy data the program uses. Compaction only collapses many files into one.

**Row preservation, verified two ways.** (1) The script re-reads each compacted object *from S3* and
checks row count, column set and per-column non-null counts *before* deleting a single original — a
verification failure deletes the new object and raises, leaving the partition as found. (2)
Independently afterwards: partitions `dt <= 2026-07-27` now hold **263,336** rows against the
**263,060** `parity_check_w3pre` recorded on 2026-07-27 — *above*, not below, by the captures that
landed later that day. The live partition kept all 47 of its captures, and the real
`stg_oddsapi_odds` flatten reads **6,681,590** rows with a fresh `max(ingestion_ts)`.

**Why the write order is promote-then-delete, and why that was measured rather than reasoned.**
Mutating a glob-backed store beside live readers admits two orders: promote-then-delete opens a
window where rows are visible **twice**; delete-then-promote opens one where they are visible
**zero** times. Which is safe is a property of the *readers*, so all three were read:
`stg_oddsapi_odds` qualifies `row_number()=1` per
`(load_id, event_id, bookmaker_key, market_key, outcome_name)`; `mart_bookmaker_disagreement`
group-bys + qualifies (and filters its historical path to commence years 2021–2025, excluding every
partition in scope); the freshness sensor reads `MAX(ingestion_ts)` / `ORDER BY … LIMIT 1`. All
three are duplicate-idempotent and none is missing-row-idempotent ⇒ the dup window is a no-op and
the empty window would silently drop a day of odds. That argument is **per-source**, so
`COMPACTABLE_SOURCES` is an allowlist and an unvetted source is refused rather than compacted by
analogy. `scripts/tests/test_compact_lakehouse_raw.py` pins the claim against the real reader files
(23 tests; 9 deliberate source breaks each verified to go RED).

### ⚠️ A self-inflicted production mutation while building this (2026-08-12)

The RED-proof harness for those guards **executed two real `--apply` runs against production S3**.
Two tests drive `main(..., "--apply")` to prove a *refusal* (an unvetted source; `--min-age-days 0`),
relying on `main()` returning before it builds an S3 client. That holds for the shipped source — but
a RED-proof deletes exactly those refusals, so with the guard removed each test ran a real
compaction: `mlb_odds_raw` at `--min-age-days 0` (including the live partition) and one
`catcher_framing_raw` partition.

**No data was lost** — `compact_partition` was unmutated, so every partition went through the
verified promote-then-delete, and the row checks above are the confirmation. The live-partition race
was harmless because the script deletes only the keys it read, so the capture that landed mid-run
was untouched (47 captures still present). `catcher_framing_raw`'s only reader
(`mart_catcher_framing`) also dedups (`row_number() … where rn = 1`) and its compacted partition
holds 208 rows, exactly 2× its weekly neighbours — but that was **luck, not design**: it is not on
the allowlist and its readers had not been vetted at the time.

**Fix:** an autouse fixture in the test module replaces `make_s3_client` with a raising stub, so no
test in it can reach AWS. A removed guard still fails the test — `main()` hits the stub — which is
the RED the proof wants, without a network call. **The lesson generalises: a test that drives a
destructive CLI to prove a refusal is one deleted `if` away from performing the action, and a
RED-proof is precisely the thing that deletes it. Stub the destructive dependency at the module
boundary, not at the entry point being tested.**

## Diagnostics

**Done — dating the failures (2026-08-12).** This was the discriminator, and it excluded candidate
(3): the two failures are `28432dfb` at 2026-08-11 23:00:37 UTC and `bc60b651` at
2026-08-12 01:00:30 UTC. ⚠️ Note they are **not findable by run status** — the intraday op catches
each leg, so the runs report SUCCESS; the query greps the Postgres event log instead:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python -c "
from dagster import DagsterInstance; import datetime as dt
i=DagsterInstance.get()
for rec in i.get_run_records(limit=400):
    r=rec.dagster_run
    if r.job_name!='intraday_schedule_job': continue
    if any('RequestTimeTooSkewed' in (getattr(e,'user_message','') or '') for e in i.all_logs(r.run_id)):
        ts=rec.start_time or rec.create_timestamp.timestamp()
        print(dt.datetime.fromtimestamp(ts, dt.UTC).isoformat(), r.run_id[:8])
"
```

**Still open, both cheap.** Rule out a container-vs-host clock difference — the one thing the host
chrony reading structurally cannot cover:

```bash
date -u; docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc date -u
```

And check CloudWatch CPU on the box for 2026-08-11 23:00 and 2026-08-12 01:00 UTC. The contention
hypothesis predicts a spike at both; a flat CPU trace would weaken it substantially.

## Status of the record

| claim | state |
|---|---|
| E11.24 #662/#675 flip caused it | **refuted** — not a rollback trigger |
| An INC-23 use-site cast is needed | **refuted** — binds clean on laptop *and* box |
| A concurrent raw-partition DELETE → 404 race | **refuted** — the error is a 403 |
| The box clock drifted | **refuted** — chrony RMS offset 2.9 µs |
| The failures predate the current clock state | **refuted** — 2026-08-11 23:00 / 08-12 01:00 UTC |
| DuckDB signs at secret-creation time | **refuted** — a 16-h-old secret signed an accepted request |
| A long bind under `:00` contention, on a glob growing 48 files/day | **open — the standing lead** |
| …its exposure | **REMOVED 2026-08-12** — 1,859 files → 98, bind 21.8 s → 1.57 s (compaction shipped) |

⚠️ Removing the exposure is not the same as confirming the mechanism. If `RequestTimeTooSkewed`
recurs on a 98-file glob, the contention lead is refuted too and the hunt moves to the signing path
itself.

Three of my own conclusions on this incident were retracted after measurement. They are left in the
record rather than deleted, because each looked well-corroborated at the time and the pattern —
inferring a mechanism from a suggestive correlation instead of measuring it — is the transferable
lesson.

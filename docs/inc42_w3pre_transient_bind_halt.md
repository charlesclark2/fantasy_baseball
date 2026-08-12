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

## Root cause: OPEN — what remains, and how to settle it

1. **DuckDB signs with a stale timestamp on a long-lived connection/secret.** If the signing time is
   captured at secret creation rather than per request, any S3 GET issued >15 min into a long build
   fails on a perfectly correct clock. This fits every observation, including why a short
   `--w3pre-only` run passes while the same code inside a 40-minute job does not.
   **Under test** (laptop, DuckDB 1.5.3 — the same version `uv.lock` pins for the box): one
   connection + secret, probed at +0/+8/+16/+24/+35 min. Laptop credentials are long-lived IAM user
   keys, so credential expiry is excluded by construction and this isolates the timestamp question.
2. **Instance-role credential refresh.** The box authenticates via the EC2 instance role (IMDS
   temporary credentials); DuckDB's `credential_chain` resolves them once at secret creation. This
   usually surfaces as `ExpiredToken`, not `RequestTimeTooSkewed`, so it ranks below (1) — but the
   laptop cannot test it, since the laptop has no instance role.
3. **The failures are older than the current clock state.** Not yet excluded, because **the failing
   runs' timestamps were never retrieved** — the run IDs alone do not date them. chronyd logged
   `Can't synchronise: no majority` on **2026-08-01 12:13**, so a genuine (brief) clock excursion in
   an older window remains possible. This is the cheapest thing to settle and should be done first.

## Diagnostics (operator, on the box)

Date the failures — this is the discriminator between (1)/(2) and (3), and it decides everything:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python -c "
from dagster import DagsterInstance; import datetime as dt
i=DagsterInstance.get()
for rec in i.get_run_records(limit=400):
    r=rec.dagster_run
    if r.job_name!='intraday_schedule_job': continue
    if any('RequestTimeTooSkewed' in (getattr(e,'user_message','') or '') for e in i.all_logs(r.run_id)):
        ts=rec.start_time or rec.create_timestamp.timestamp()
        print(dt.datetime.utcfromtimestamp(ts).isoformat(), r.run_id[:8])
"
```

Rule out a container-vs-host clock difference (cheap, and it is the one thing the host reading
above cannot cover):

```bash
date -u; docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc date -u
```

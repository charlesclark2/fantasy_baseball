# NF-INFRA1 — persist `sports.duckdb` on the box

**Status:** code landed; **the cure is not complete until the operator runs the box steps at the
end of this doc.** Two launch-critical things were blocked by one missing piece of box
infrastructure, and both are unblocked by the same fix.

| | |
|---|---|
| Blocked #1 | `sports_nfl_board_publish_schedule` (NF-FRESH2) could not be turned on — so the operator ran the whole board-publish loop **by hand, every morning, through draft season** |
| Blocked #2 | the Sleeper injury feed had been dark since 2026-07-26 — **19+ consecutive green runs over one 19-day-old Delta commit** |
| Root cause | one file with no durable home and no authoritative path |
| Runtime gate | 🟥 a real BOX run. CI mocks all IO; **a green run is exactly what was lying**, so the proof is a NEW Delta commit + a board that publishes |

---

## 1. The root cause, stated precisely

`dagster-codeloc` had **no persistent volume** — only `dagster_pg_data` and `caddy_*` existed. The
whole NFL build chain and the Sleeper ingest open a **gitignored** `sports.duckdb`, so:

* it is absent from the `COPY . .` image,
* `/tmp` is wiped by every deploy,
* `/app` is replaced by the new image.

⇒ `duckdb.connect(read_only=True)` raised in ~114ms, and the Sleeper op's bare
`except Exception` turned that into **SUCCESS**.

Compounding it, `SPORTS_DUCKDB_PATH` was **not in `env.required`**, so it was simply unset on the
box and **four owners each fell back to a different default**:

| Owner | Its own default |
|---|---|
| `sports_nfl_sleeper_injuries_job` | `quant_sports_intel_models/sports_dbt/sports.duckdb` |
| `sports_dbt_job._run_sports_dbt` | `/tmp/sports_ncaaf.duckdb` |
| `sports_dbt_schedules` (game-day gates) | `/tmp/sports_ncaaf.duckdb` **and** `/tmp/sports_nfl.duckdb` |
| `sports_dbt/profiles.yml` | `sports.duckdb` (relative to the project dir) |

⭐ **The NFL game-day gate read a file nothing ever wrote**, so it had been permanently
**fail-open** since it shipped — and that presented as a gate that simply never skipped, never as an
error. This is the repo's recurring *one logical thing, many execution owners* shape: INC-30
(crontab installed under two users), INC-36 (a deploy "lock" that wasn't), INC-38 (a per-caller flag
applied to 2 of 4 callers).

---

## 2. What changed

### 2.1 A named volume (`docker-compose.yml`)

`sports_duckdb` → **`/var/lib/credence/sports`** on `dagster-codeloc`. A named volume is the only
thing here that outlives `docker compose up -d`.

Mounted on **that service only**, deliberately: codeloc is *both* the gRPC code server (where
schedule evaluation runs — including the game-day gate's DuckDB read) *and* the run worker
(`DefaultRunLauncher` subprocesses). The daemon and webserver only proxy over gRPC and never open
the file, so mounting it there would add a second writer for nothing.

⛔ **Never `docker compose down -v` on the box** — that now deletes run history, every schedule's
on/off state, the TLS cert **and** the sports database in one command.

### 2.2 One authoritative path (`betting_ml/utils/sports_duckdb.py`)

Every owner resolves through this module. One env var, one default:

* **on the box** `SPORTS_DUCKDB_PATH` is in **`env.required`** ⇒ `deploy.sh` fails the deploy if it
  is missing or empty (an empty value shadows a code default — the documented `CACHE_BUCKET` trap);
* **off the box** it falls back to `REPO_DEFAULT`, the path every `run_*.py --duckdb` already uses,
  so laptop research is unchanged;
* `sports_duckdb_env()` pins the **resolved absolute** path into every subprocess env, because
  `_run_sports_dbt` runs dbt with `cwd=SPORTS_DBT_DIR` where a relative default binds elsewhere.

NCAAF and NFL share one file on purpose: dbt materializes each sport into its own **schema**, which
is why both gate relations are schema-qualified. Two paths never bought isolation — they only ever
produced a gate reading a file nothing wrote.

`profiles.yml` cannot import Python, so it is pinned by a guard to read the same env var.

### 2.3 The Sleeper feed fails loud (`sports_nfl_sleeper_injuries_job.py`)

Three layers, because fixing any one alone leaves the bug:

1. **A run that produced nothing is RED.** The bare `except` is gone. The reasoning that put it
   there conflated *the consumer degrades gracefully* (true — the projection falls back to
   nflverse-only) with *nobody needs to know* (false). The job is standalone in its own namespace:
   raising fails **its own** run, blocks nothing MLB-serving, and leaves the previous snapshot
   serving. A RED run that left the good snapshot alone beats a green run that wrote nothing.
2. **A degraded land is REFUSED, not written.** ⛔ The tempting shortcut — *make the DuckDB optional
   and land Sleeper's native `gsis_id` rows* — was **measured** in NF-FRESH1 at 16.7% of rostered /
   22.1% of flagged: it would drop **95 of 122 flagged players** (Waddle, Pacheco among them),
   **overwrite the good Delta partition** (the write is a whole-partition overwrite), and report
   SUCCESS daily. Strictly worse than a loud break. So the crosswalk stays **required**, and this
   story makes its source reliably present instead of routing around it.
   * The measurement that makes this visible is new: `coverage()` on the **landed** frame reports
     `pct_matched = 100.0` **by construction** (the drop already removed every unresolved row), so
     it cannot tell a healthy crosswalk from a dead one. `load_sleeper_injuries_with_coverage`
     measures **before** the drop; `classify_land` gates the write on it.
   * The floor (50%) is derived from the two **measured regimes** — native-only ~17–22% vs
     crosswalked ~89–100% — not reverse-engineered from a run's answer (NF1.8). It is deliberately
     loose: the pre-drop rate had never been recorded, and a tight floor would be a guess that can
     only fail toward falsely refusing a healthy feed. Every run now logs `pct_resolved`, so it can
     be tightened against real observations.
   * A **partial** land (zero flagged players) still writes, and **reports its magnitude**.
3. **The artifact is asserted, not the producer** (INC-41) — `betting_ml/monitoring/sports_delta_freshness.py`.
   Everything else in this job watches the producer, and the producer reported success for 19 days.
   The freshness op reads the commit timestamp from **inside `_delta_log`**.
   ⛔ **Never an S3 `LastModified`**: `aws s3 ls` prints shell-local time, and an mtime is refreshed
   by any server-side rewrite (compaction, a re-copy) that changes no data — it would have read
   GREEN straight through this outage. `≤2×` the SLA is one missed cycle (WARN); beyond it the feed
   is dead (CRITICAL). An unreadable log is `UNKNOWN`/WARN, **never healthy** (NF1.7(a)).

---

## 3. Guards

`betting_ml/tests/test_nf_infra1_sports_duckdb_path.py` (20) ·
`betting_ml/tests/test_nf_infra1_sleeper_hardening.py` (28)

**All 16 falsifiability claims RED-proven** — `uv run python betting_ml/tests/nf_infra1_red_proof.py`
(applies each break in-process, asserts the mutation landed, requires the named test to go RED).

⭐ **The harness earned its keep twice, and both are worth reading:**

* `test_a_zero_row_write_is_an_error_not_a_log_line` first asserted
  `"raise Exception" in ast.unparse(op)` — satisfied by the op's **other** raises, so deleting the
  one it named changed nothing. It now asserts structurally, on the `if not n:` branch.
* `test_the_missing_duckdb_page_names_the_volume…` first asserted `BOX_VOLUME_DIR in remedy` —
  satisfied incidentally because `BOX_DUCKDB_PATH` **contains** that directory as a substring. It
  now asserts the volume NAME.

Both are the NF-D17 mode: a clause satisfied by something other than the thing it names. **Neither
was findable from a green suite**; only a mutation run finds them.

⚠️ And a third, methodological: an ad-hoc RED check run under a bare `python3` (no pytest in that
interpreter) returned a non-zero exit and read as **RED for the wrong reason** — a false pass of the
proof itself. Run the committed harness (`uv run python …`), not a one-off.

---

## 4. ⏭️ Operator — the box steps, in order

All on the **EC2 BOX**. Steps 1–3 are the deploy; 4 materializes the database; 5 turns the cadence
on. ⚠️ Step 1 is the one a `git pull` can never do for you.

**1. Add the key to the box's LIVE `.env`** (`${APP_DIR}/services/dagster/aws/.env` — the file
`deploy.sh` validates, **not** `~/app/.env`). A `git pull` never touches it, and the next deploy
**FAILS** until it is there (that gate is the point):

```bash
cd ~/app && grep -q '^SPORTS_DUCKDB_PATH=' services/dagster/aws/.env \
  || echo 'SPORTS_DUCKDB_PATH=/var/lib/credence/sports/sports.duckdb' >> services/dagster/aws/.env
grep '^SPORTS_DUCKDB_PATH=' services/dagster/aws/.env
```

**2. Pull + redeploy** (creates the volume and recreates `dagster-codeloc` with the mount):

```bash
cd ~/app && git pull origin main \
  && docker compose -f services/dagster/aws/docker-compose.yml up -d --build
```

**3. Verify the volume and the env var are live IN THE CONTAINER THAT RUNS JOBS** (the FU-1 lesson:
an env flip only takes effect once the *executing* container is recreated — a throwaway `exec`
proves nothing about the container that ran this morning's jobs, so do this after the `up -d`):

```bash
docker volume ls | grep sports_duckdb
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  sh -lc 'printenv SPORTS_DUCKDB_PATH && ls -la /var/lib/credence/sports'
```

**4. Materialize the sports DuckDB — ONCE.** ⏱️ ~2–5 min, so launch it from Dagit rather than
blocking a shell: **Dagit → Jobs → `sports_nfl_dbt_build_job` → Launch Run**. Then confirm the file
now exists on the volume (this is the artifact, not the run status):

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  sh -lc 'ls -la /var/lib/credence/sports/sports.duckdb'
```

**5. Turn the two schedules on** — Dagit → Automation:
* `sports_nfl_board_publish_schedule` → **ON** (this is what retires the manual daily loop)
* `sports_nfl_sleeper_injuries_schedule` → confirm **ON** (it already is)

### Verification — ⛔ NOT a green run

**(a) The Sleeper feed lands a NEW Delta commit.** Note the `version=` first, launch the job, then
re-read and require it to have INCREASED:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T \
  -e SPORTS_LAKE_REGION=us-east-2 dagster-codeloc \
  python scripts/check_sports_delta_freshness.py --strict
```
Expect `[METRIC] nfl_sleeper_injuries_freshness=OK lag_hours=<small> version=<N>` and exit 0.
A `STALE`/`UNKNOWN` verdict names its own first action.

**(b) A board actually publishes.** Launch `sports_nfl_board_publish_job` from Dagit once by hand
before trusting the cron. The publish op **verifies the artifact it shipped** (a `generated_at`
predating the run, or a null `adp_as_of`, fails the run) — so a green run here does mean something,
unlike the Sleeper case. Confirm the served board's `freshness.adp_as_of` moved.

**(c) If step 4's job fails**, the sports DuckDB does not exist yet and both schedules will page
CRITICAL daily — that is the intended, visible state, and the page names the remedy.

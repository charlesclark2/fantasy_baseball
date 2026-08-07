# INC-41 — the dbt-test pager

**Page when a SERVING-CRITICAL dbt test goes red.** Observability only (`best_alpha=0`); the
backend half of the INC-41 reliability pair (the freshness-SLA guard is its sibling).

## Why

The daily dbt test step is deliberately WARN-tier and non-blocking, and that is **correct**:
INC-6 (2026-06-21) had one bad StatsAPI bio row exit-1 the Sunday build and block every
prediction, so `dbt_daily_build` splits the model `run` (HALT) from the `test` suite
(WARN-continue).

The cost of that split is that a `not_null` failure on a serving-critical contract surfaces
**days later in CI**, to whoever opens the next PR. In INC-41 the test **worked** — it went red on
the nulled odds price — and nobody was notified. The detection existed; the page did not. That is
the E11.30 finding one layer over: here the detector is not even an op, it is a dbt test whose
non-zero exit is caught and logged by design.

## The signal already exists

The repo already encodes "which failure matters" in the dbt project itself (the E11.7 contract):
serving-critical model contracts are `severity: error`, peripheral data-quality checks are
`severity: warn` — today **17 error / ~69 warn**. So the pager needs no new registry to keep in
sync, which would be one more documented-but-drifting surface (the `W7B_LAKEHOUSE_S3` class).

## 🪤 Why status is NOT the key

It is tempting to key on `status`, since dbt reports a warn-severity failure as `warn` and an
error-severity failure as `fail`. **Measured** against dbt-fusion 2.0.0-preview.204:

| case | `status` | `failures` |
|---|---|---|
| `severity: error`, failing rows | `fail` | 1 |
| `severity: warn`, failing rows | `warn` | 1 |
| passing test | `pass` | 0 |
| model | `success` | `null` |
| **test that cannot EXECUTE** (binder error, renamed column) | **`error`** | `null` |

That last row is the problem: a test that cannot execute reports `status: "error"` **regardless of
its configured severity** — measured on a test explicitly configured `severity='warn'`. A
status-only pager would therefore page CRITICAL every time a *peripheral* test broke, which is the
alert-fatigue failure mode that gets a monitor muted (E11.27). **Severity is read from the
manifest**, which resolves that case; status is only a fallback when no manifest is available, and
even then `error` is left UNKNOWN (reported WARN) rather than inferred as serving-critical.

Note `config.severity` is stored **UPPERCASE** in the fusion manifest (`"ERROR"` / `"WARN"`) while
dbt-core writes it lowercase, so it is normalised rather than compared verbatim — a `.lower()`
mismatch is the silent-NULL class this repo has hit through Snowflake `VALUE:` case-sensitivity.

Also measured: **`dbt test` exits 1 on an error-severity failure and 0 on a warn-severity
failure.** So the error case raises out of `_run_dbt` and the warn case does not — the results are
captured in a `finally` for exactly that reason.

## 🔌 How the artifact reaches the op (the non-obvious part)

`run_results.json` is **not** where you would expect it. On the box `DBT_RUNNER_URL` is always set
(compose: `http://dbt-runner:8080`), so dbt executes in the **dbt-runner container**, which shares
**no volume** with `dagster-codeloc`. `/app/dbt/target/run_results.json` in the op's own filesystem
is therefore *not* the daily suite's output and would be silently stale forever.

So the runner grew a read-only `GET /run_results/{run_id}`:

- **Captured at run time, not request time.** dbtf overwrites `target/run_results.json` on its next
  invocation, so a read-at-request-time endpoint would hand back whichever run finished last — the
  stale-on-disk-artifact class this repo keeps getting burned by (the board exporter's legacy CSV;
  the query-range cache). Capturing into a `run_id`-keyed slot makes serving another run's results
  *structurally* impossible.
- **Not folded into `/status`**, which is polled every 15s for the life of a run.
- **404, never `{}`**, when a run wrote no artifact — an empty object would classify as a clean suite.

`_run_dbt` gained an optional `run_ref` **out-parameter** to hand back the run id. It is not a
return value because `_run_dbt` *raises* on a failed dbt run, and a failed run is exactly when the
results matter. Omitting `run_ref` is the default, so the other 15 callers of this HALT-tier helper
are untouched.

`capture_dbt_results` then verifies provenance before persisting — the INC-39 lesson that a monitor
parsing another process's output must be able to verify **which invocation** the numbers describe:

1. the artifact's `args.command` must be a test-bearing command (`test` / `build`); a `dbt run`
   artifact contains zero test nodes, and "0 failures" from a command that tested nothing is the
   most dangerous possible false green;
2. its `metadata.generated_at` must not predate this invocation (a previous day's leftover).

Either check failing yields UNVERIFIED (WARN), never a clean bill of health.

## Verdicts

| state | when | page |
|---|---|---|
| `FAILURES` w/ error-severity | a `severity: error` contract is `fail` or `error` | **CRITICAL** |
| `FAILURES` w/ unresolved severity | failing, but no manifest to classify it | WARN |
| `UNAVAILABLE` | the suite ran, results unreadable | WARN |
| `FAILURES` w/ warn-severity only | peripheral checks red | silent (step-log digest) |
| `CLEAN` | nothing red | silent |
| `NOT_RUN` | the invocation executed no tests | silent |

**`NOT_RUN` vs `UNAVAILABLE` is what keeps this quiet enough to be trusted.** `dbt_daily_build`
runs the full suite only on build days (Sunday + every 3rd midweek); other days run a state-aware
build the runner rewrites to `source_status:fresher+`, which *does* execute the selected models'
tests but may select none. Reporting a no-test day as "unverified" would WARN on a routine cadence
and train the operator to ignore this pager — the same carve-out `artifact_freshness` makes for a
writer's declared inactive hours. `UNAVAILABLE` (the suite ran, results unreadable) is the
genuinely unverified state and stays WARN, because a check that did not run is not a pass
(NF1.7 (a)).

## What it does NOT do

- ⛔ **Does not re-run the tests.** It reads the artifact the suite already produced. Re-running
  would double the suite *and* resume `COMPUTE_WH` — a new waker, on a warehouse where ~80% of the
  credit burn is wake/idle (E11.20-COST) and the E11.24 soak is live. The op touches no warehouse:
  an HTTP GET against the in-cluster runner plus a manifest read from the image. **SF-free.**
- ⛔ **Does not gate predictions.** ALERT-tier (E11.7): page loud, continue, always; no strict
  escalation. It fans out from `dbt_daily_build` and **nothing depends on it** (proven on the
  compiled Dagster graph, with a positive control), so it cannot fail the job or withhold a slate.
  Regressing INC-6 to fix INC-41 would be a bad trade.
- Not added to `check_monitors_healthy_op`'s set: that heartbeat watches **sensors and schedules**
  that can be manually STOPPED. This is an op inside the daily job — if the daily job runs, it runs.

## Fixtures — regenerating them

The test fixtures under `betting_ml/tests/fixtures/inc41_dbt_run_results/` are **real dbt-fusion
output**, not hand-written JSON. A hand-authored fixture encodes the test author's *belief* about
dbt's output format, so the suite would stay green if that belief were wrong — which is the NF-C0e
lesson, and the reason the `status: "error"` case above was found at all.

They were produced by running a real `dbt build` against a throwaway DuckDB project whose schema
mirrors this repo's contract split (a serving-critical `not_null` at `severity: error` beside a
peripheral `unique` at `severity: warn`), across four scenarios: `all_pass`,
`error_severity_failure`, `warn_severity_failure`, and `warn_severity_errored`.
`manifest_severities.json` is a real extract of the real manifest, preserving fusion's genuine
UPPERCASE values.

The generator is committed beside them. To regenerate (LAPTOP; needs `dbtf` + the dbt-duckdb
adapter, ~10s, no warehouse):

```bash
bash betting_ml/tests/fixtures/inc41_dbt_run_results/generate_fixtures.sh
```

The fixtures are stable output of a fixed dbt version; regenerate them only when upgrading
dbt-fusion, and **re-read the four statuses** when you do — the whole classifier rests on that
encoding, and `TestTheFixturesAreRealDbtOutput` fails loudly if the casing or shape moves.

## Runtime gate

`send_alert` hits SNS and CI mocks all IO, so the unit tests prove the **decision logic** only.
A live smoke on the box is required before trusting the page path — see the operator handoff.

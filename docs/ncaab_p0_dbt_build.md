# Building the NCAAB dbt models — and why `dbt build --select ncaab` does not work

**Measured 2026-09-14 during the NCAAB-P0 runtime gate, on dbt-fusion `2.0.0-preview.218`.**

## The short version

```bash
cd <repo> && set -a && source .env && set +a
A="--project-dir quant_sports_intel_models/sports_dbt --profiles-dir quant_sports_intel_models/sports_dbt --target dev --threads 1"

for m in stg_ncaab_schedule stg_ncaab_team_box stg_ncaab_team_crosswalk \
         dim_ncaab_team dim_ncaab_conference fact_ncaab_team_game; do
  echo "--- $m"; dbtf run --select $m ${=A} || break
done
dbtf test --select ncaab ${=A}
```

Expected: 6 models succeed, then `23 total | 22 success | 1 warn`. The warn is
`not_null_stg_ncaab_team_crosswalk_conference_name` — West Florida, a D-I reclassifying school
with genuinely no conference, held at `warn` on purpose.

⚠️ **Order matters.** `dim_ncaab_conference` refs `dim_ncaab_team`; building it first fails with
`Table with name dim_ncaab_team does not exist`, which looks like a model defect and is not.
⚠️ **`${=A}`, not `$A`** — zsh does not word-split, so `$A` arrives as one argument.

## Why not the obvious single command

`dbt build --select ncaab` **crashes the fusion binary**, at `Analyzing`, with no error output:

```
 Analyzing [━━─    ] 3/29 2 succeeded
zsh: segmentation fault  dbt build --select ncaab ...
```

It is **NOT our SQL and NOT the lake data**, and all three legs of that were measured:

| Check | Result |
|---|---|
| `dbt compile --select ncaab`, targets `ci` **and** `dev` | **29/29 success**, deterministic |
| The *exact compiled SQL*, one python DuckDB 1.5.3 connection, same S3 Delta tables | **3/3 clean**, correct counts (32,732 / 62,020 / 362) |
| `dbt run --select ncaab.staging` in fusion | **SIGSEGV (139) / SIGTRAP (133)** |

So the crashing component is fusion's own bundled DuckDB, on a workload our SQL and our data
both survive elsewhere.

## Two "fixes" that are not fixes — do not re-derive them

- **`--threads 1` does not help.** Staging still segfaults. (It *is* still passed above, matching
  the NFL/NCAAF jobs' convention, but it is not what makes this work.)
- ⭐ **`memory_limit` is not the lever, and it looks like one.** A single run at
  `SPORTS_DUCKDB_MEMORY=2GB` passed while 4GB and 8GB crashed, which reads as a clean OOM story.
  Re-run three times each: **2GB crashed 2 of 3; 4GB passed 1 of 3.** The crash is
  NONDETERMINISTIC, so any single green run "proves" whatever knob you happened to turn. This is
  the repo's recurring coin-flip trap (NF-C0e / E9.66 "measure the distribution, not one
  observation") and it nearly shipped here as a recommendation.

Building one model per invocation is deterministic — **2 of 2 full trials identical**, and a
third confirming run by the operator. Each invocation gets a fresh connection, so whatever state
accumulates across models in one fusion process never builds up.

## What is NOT solved

- **There is no NCAAB Dagster dbt job.** NFL and NCAAF have `sports_nfl_dbt_build_job` /
  `sports_ncaaf_dbt_build_job`; NCAAB has none, so the marts do not rebuild on the box at all —
  the daily ingest advances the lake while the marts stay at whatever was last built by hand.
  That is acceptable for P0 (P1 owns the modelling surface and its cadence) but it must be
  **wired before anything serves off these marts**.
- **A future NCAAB dbt job cannot use a single `dbt build`.** It needs per-model invocations, or
  a runner proven not to crash on this workload.
- ⚠️ **The box's dbt has NOT been checked against this.** The box runs dbt through the
  `dbt-runner` container, which may be a different build or version from the laptop's
  `~/.local/bin/dbt`. Whether it crashes on NCAAB is **unknown and untested** — establish that
  before a scheduled job depends on it, rather than assuming either way.
- The upstream fusion bug is not reported. The reproduction is cheap if anyone wants to file it:
  `dbt run --select ncaab.staging --target dev` against the NCAAB Delta lake.

## A likely provocation (unconfirmed)

`ncaab/raw/schedules` has **heterogeneous partition schemas** — hoopR's own column set drifts
season to season (76 → 85 → 84 → 87 → 86 → 83 columns, with columns both added *and dropped*),
and `schema_mode="merge"` is additive-only, so the Delta schema is the union and each parquet
file carries a different subset. That is a demanding read. It is **not confirmed as the cause**:
DuckDB 1.5.3 handles the identical table without complaint, so at most it is the workload that
provokes fusion's build. Recorded because it is the first thing to test if anyone picks this up.

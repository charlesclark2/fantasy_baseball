# `stg_ref_players` — a dimension nothing wrote, over a source nothing writes

**Status:** fixed (code); artifact repaired by the post-merge operator run.
**Relates:** E5.10 (found it), INC-27 (raw-SQL consumers the DAG can't see), INC-41 (freshness on the
derived artifact), NF-INFRA1 (a table with no scheduled writer), INC-25 (build ordering).
`best_alpha = 0` — nothing user-facing changes in behaviour.

## What was wrong

`scripts/export_ref_players_to_s3.py` wrote `baseball/lakehouse/stg_ref_players/`. Its own docstring
said *"Run ONCE … re-run when ref_players changes (new players added — infrequent)"*, and it was
referenced by **no op, no schedule, no workflow**. So nothing ever re-ran it.

E5.10 measured the consequences: the parquet was 53 days stale and held **zero** players with
`mlb_played_last = 2026`, so the batter-TB serving writer silently skipped 34 batters. E5.10 fixed
that one writer by repointing it at the posted-lineup feed; ~11 other consumers still read the frozen
prefix.

## The measurement that changed the fix

The card proposed "give the export a scheduled writer + an INC-41 freshness SLA." That would not
have worked, and the reason is the whole point of this note.

**The Snowflake source is itself dead.** `baseball_data.savant.ref_players`:

| | |
|---|---|
| `last_altered` | **2025-10-13** (~308 days, not 53) |
| `max(mlb_played_last)` | **2025** |
| writers found in a whole-repo grep | **none** — no ingest, no dbt model, no op |

The S3 parquet was a *faithful mirror of a dead table*. Scheduling the export would have re-copied
the same 25,900 rows on a timer — refreshing the object's mtime while the content stayed 2025 — and
an INC-41 SLA laid on top would then have read **green forever**. That is precisely the false-green
INC-41 exists to prevent ("a re-copied object carries a fresh mtime even when the DATA is
unchanged"), reached from the writer side instead of the reader side.

> **A scheduled writer only fixes staleness when it has something live to write.** Check that the
> source advances before scheduling a mirror of it.

## What the sources actually contain

Distinct players appearing in `stg_batter_pitches` as a batter or pitcher, by debut era, counting
how many each candidate source **misses** (measured 2026-08-17):

| debut era | players | frozen `ref_players` misses | live `player_profiles_raw` misses |
|---|---|---|---|
| 2020+ | 1,751 | **208** | **4** |
| pre-2020 | 2,475 | **0** | **471** |

They are **complementary**, and that is the design:

* the frozen export is a *complete historical archive* that stopped advancing;
* `player_profiles_raw` is *live* (weekly `ingest_player_profiles.py update` + the E11.24 Bundle's
  daily S3 mirror leaf) but only covers 2020+ — its backfill was seeded from
  `mart_pitch_play_event WHERE game_year >= 2020`.

On the 2026 slate specifically, **204 of the 208** players the archive misses (98.1%) are in live
profiles.

## The fix

`scripts/build_ref_players_dimension.py` publishes the `stg_ref_players/` prefix by layering the
live feed over the frozen archive (relocated to `stg_ref_players_archive/`, a name that declares
what it is). `mlb_played_first/last` are derived from the Statcast appearances themselves — which is
what those columns *mean*, and what makes `mlb_played_last = 2026` true again.

**Why rebuild the artifact rather than repoint ~11 consumers.** Most consumers do not read the dbt
model; they read the S3 prefix directly as a raw string from a clustering script, a prop-substrate
builder, a zone-overlay writer. Fixing the dimension *at its prefix* repairs all of them with zero
consumer edits and one column contract, instead of 11 independent name resolutions each free to
drift (the E9.61 "two renderers of one field are two rule sets" lesson). The column contract is
unchanged; `built_at` is the only addition.

**Names are never split from a full name.** `player_profiles_raw` carries `full_name`; deriving
`last_name` by splitting it is wrong for "Vladimir Guerrero Jr." and every multi-word surname (the
NF-C0e / E9.61 name-mangling class). `ingest_player_profiles.py` now captures `firstName`/`lastName`
from the StatsAPI `/people` payload it was already fetching and discarding. Until the one-time
backfill runs, recent debutants carry a correct `full_name`-derived display name and NULL parts —
strictly better than being absent entirely, and the builder detects which columns exist rather than
assuming.

### Measured locally against real S3, before any write

| | before | after |
|---|---|---|
| players with `mlb_played_last = 2026` | **0** | **1,384** |
| 2026 players with no name | **208** | **4** |

Newly resolved include Travis Bazzana, Braden Montgomery, Juan Brito, Tommy Troy — real 2026
debutants.

## Why it can't rot again

1. **A scheduled writer.** `build_ref_players_dimension_op`, an unbound fan-out leaf of the daily
   job, ALERT tier (never HALTs a slate — this is a peripheral identity dimension), ungated, finite
   `timeout=` (INC-32), and it really pages via `send_alert` (E11.30: a tier enforced only by a
   docstring is not enforced at all).
2. **Ordering (INC-25).** Transitively downstream of `lakehouse_w1_pitch_marts_op`, so the
   `stg_batter_pitches` it derives appearances from is *this run's* build. Pinned as reachability
   over the dependency edges, not source-line order — the job runs under `in_process_executor`,
   which orders topologically, so a line-order test pins nothing (INC-40).
3. **An INC-41 freshness contract** reading `built_at` from *inside* the parquet — never an S3
   `LastModified`.
4. **A publish guard.** The builder refuses to publish a dimension carrying fewer than 200
   current-season players. Per NF-K1, this counts the rows that *carry the value*: a plain row-count
   check is satisfied by an archive-only rebuild (25,900 rows, zero current players), which is
   exactly the broken artifact.
5. **A consumer registry** (`betting_ml/tests/test_stg_ref_players_consumers.py`) re-derived from
   source on every run, so a new reader cannot ship unregistered (INC-27 / INC-38).

## Deliberate non-decisions, recorded

* **The builder is NOT wired into `weekly_player_profiles_job`.** Chaining it off
  `reexport_player_profiles_op` is the obvious move, but binding that leaf's output destroys the
  unbound-fan-out-leaf invariant E11.24 defends; wiring it off the ingest instead leaves the two
  unordered under a topological executor — the INC-25 hazard itself. The daily job runs ~2h later
  and rebuilds from the fresh mirror anyway, so neither compromise is needed. A guard clause pins
  the absence so a future session does not "helpfully" add it back.
* **The Snowflake branch of `stg_ref_players` still reads the dead source.** Both consuming marts
  are `enabled=(target.name == 'duckdb')` (E11.20 phase 1.5) and no other dbt model refs it, so that
  branch has no consumer. It must not gain one without being repointed; the model header says so.

## Two things the guards caught during the build

* The consumer-exhaustiveness scan matched this story's own **docstrings**. A Python docstring is an
  expression statement, not a `#` comment, so stripping it needs the AST — the INC-38
  "prose satisfies the guard" class in a costume `#`-stripping doesn't cover.
* The RED proof found the "has a scheduled writer" clause accepted wiring into *either* job, so
  unwiring the daily pass — the cadence that keeps `mlb_played_last` current — stayed green. The
  clause was strengthened to the invariant it actually names.

## Verification status

Locally verified: the merge SQL against real S3, the coverage numbers above, `dbt compile`
(1,516/1,516), the guards and serving-ops shards, and all 9 guard clauses RED-proven with unique
anchors and non-vacuity baselines.

**Not yet verified — the runtime gate.** CI mocks all IO, so the writer and the op only prove out on
a real box run. The merge bar is CI-green **and** the archive seed → builder → consumer chain run
once on the box with 2026 players confirmed at the consumer. See the operator steps in the PR.

# E11.24 Bundle — the last three `check_data_freshness` blockers

**Branch** `e1124-bundle-freshness` · 2026-08-14 · `best_alpha=0` · deploy-held · 🟥 runtime gate OPEN

Closes follow-ups 1, 2 and 4 of `docs/e11_24_check_guard_s3_repoint.md` (follow-up 3 was PR #693).
With PR #772's two cheap flips merged, `check_data_freshness.py` has **no Snowflake-sourced entry
left**, `needs_snowflake()` returns `False`, and `run()` opens no Snowflake connection at all.

---

## Why one PR and not three

`check_data_freshness` stops resuming `COMPUTE_WH` only when **every** read is off Snowflake.
Wake is a **queue**, not a sum (#679): on an auto-suspending warehouse only the first occupying
statement after a suspend pays the resume, so repointing any single entry merely promotes the next
one to pay it. Three blockers remained; clearing two of them buys exactly nothing. Hence a bundle,
and hence a single soak.

⛔ **This clears THIS SCRIPT only.** The other named wakers — the `feature_pregame_team_features`
view, the `lineup_state` SCD-2 writes, CI_WH, CREDENCE_API — are untouched, and the queue simply
moves to whichever of them fires first. Literal-zero resume needs all of them.

---

## Three defects wearing one costume

They all present as "the S3 mirror is stale". They are not the same problem, and treating them as
one is how a fix ends up wrong for two of them.

### 1. `team_sequential_posteriors` — an INC-25 **ordering trail**

`lakehouse_w8b_aggregator_op` mirrors the table at graph position **lk10**;
`update_team_posteriors_op` writes Snowflake **~40 min later**. Nothing re-exported it afterwards.
This is the #693 defect one table over, on a table that story did not sweep up.

Measured 2026-08-14 (laptop; Snowflake side on `MONITOR_WH`):

| source | `max(update_ts)` | rows | trail |
|---|---|---|---|
| SF | 13:03:04 | 83,636 | — |
| S3 | 10:16:26 | 83,619 | **2.78 h / 17 rows behind** |

⚠️ The inherited 2026-08-08 reading said **"parity EXACT"**, which is what made this look like a
safe cheap flip in PR #772's card. That reading was taken *in-job*, at exactly the moment
`check_data_freshness`'s own module docstring already warned is **blind** — before either side has
advanced, both return the same value. #772 re-measured, found the trail, and **refused the flip**,
carding the op instead. That refusal is the reason this PR exists.

⛔ **The order cannot simply be swapped** — that is a genuine cycle, already documented at
`sensor_ops.lineup_intraday_s3_feature_rebuild` (E9.53): `update_team_posteriors_op` reads the
Snowflake `eb_bullpen_posteriors` copy → which needs `refresh_w1_external_tables` → which runs
*after* lk10. So the lk10 mirror stays (the `--w8b` build reads it) and the cure is **additive**.

**Cure** — `reexport_team_seq_posteriors_op`, a fan-out leaf downstream of the writer in **both**
jobs that run it (`daily_ingestion_job`, `statcast_catchup_job`).

### 2. `player_profiles_raw` — a **writer gap**, not a trail

`ingest_player_profiles.py` writes **only Snowflake**. The mirror's sole writer,
`export_w4_raw_to_s3.py`, is a hand-run W4 build precursor that **no job schedules**. So it froze
at whenever someone last ran it: **2026-06-28**, i.e. ~41 days at the 08-08 census and **~1,133 h
by 08-14**, against this entry's own **192 h** threshold.

**Why it hid for a month and a half:** nothing *loud* reads the mirror. Its only consumer is the
`duckdb` branch of `stg_statsapi_player_profiles`, and a stale profile snapshot does not error — it
silently omits recent call-ups from `mart_player_profile_identity` (NULL birth_date / height /
weight for a player who does not exist in a 47-day-old table). The freshness monitor is the loud
reader, and it could not be pointed here until the writer gap closed.

**Cure** — `reexport_player_profiles_op` in `weekly_player_profiles_job`, the only job that runs
the writer (the whole INC-38 caller set, pinned). It mirrors **one** table, not the whole W4 raw
set: a bare `export_w4_raw_to_s3.py` would also re-export `savant_park_factors_raw` and both ZiPS
tables — three needless Snowflake `SELECT *`s.

**Cadence, stated because it bounds what the flip promises:** the writer is weekly
(`0 10 * * 0` UTC), so a healthy mirror reads ≤ ~168 h against 192 h — ~24 h of margin, and
`last_fetched_at` only advances when a week's `people/changes` call actually writes rows. That is
identical to what the Snowflake side already reported; the flip makes the two sides **agree**, it
does not tighten or loosen the entry.

### 3. `matchup_cell_sequential_posteriors` — **no mirror at all**

Verified 2026-08-08: a DuckDB `IOException`, not a stale read. There was no
`baseball/lakehouse/matchup_cell_sequential_posteriors/` prefix, so the export had to be **built**.

**Cure** — a new entry in `export_w8b_precursors_to_s3.py` (same schema, same SCD-2 full-table
`SELECT *` shape as its sibling `team_sequential_posteriors`, so it reuses that exporter rather
than growing a fourth near-identical script) plus `reexport_matchup_cell_posteriors_op`, wired
downstream of its writer in both jobs.

⭐ **And it is `ON_DEMAND_ONLY` — deliberately, and this is the point of building it inside this
bundle.** The one-line-cheaper alternative was to drop it into that exporter's default set, which
lk10 already invokes. That would have **created the mirror with the INC-25 trail pre-installed** —
lk10 runs ~40 min before this writer — making it the fourth member of the family this bundle
exists to close, and it would have put a second writer on the same S3 key racing the on-demand one
(the INC-31 two-writers-one-key shape). `team_sequential_posteriors` legitimately *stays* in the
default set, because the `--w8b` build reads it and the mirror must exist before that build runs;
a guard asserts that too, so `ON_DEMAND_ONLY` cannot quietly swallow everything.

**No S3 consumer today**, stated rather than implied: `generate_matchup_signals.py` reads this
table straight from Snowflake (`_SEQ_POSTERIORS_TABLE`). The mirror exists for the freshness
monitor and as the precursor a future read-repoint needs.

---

## ⭐ What the team-seq fix does NOT do — the honest scope

The trail is **not** purely a monitoring artifact: the served sequential block does carry a
one-game-stale prior on the **morning** tier, because the `--w8b` build runs at lk10 off a
Snowflake table not yet advanced for the previous slate.

**This op does not heal that, and claiming it would be false.** Nothing rebuilds `--w8b` after it
in either job, and the *next* day's lk10 re-mirror would have picked up the same rows anyway. What
it fixes is every read of the mirror taken **between the writer and the next lk10**:

* the freshness monitor (which is precisely why #772 could not flip the entry),
* an operator hand-run `--w8b-only` / `--w8a-only`,
* any future consumer repointed at this parquet.

The **post_lineup** tier already gets the fresh chain, because
`lineup_intraday_s3_feature_rebuild` re-mirrors this table itself and then rebuilds `--w8b-only`.
Healing the **morning** served block needs a second `--w8b` build after the sequential writers
(~minutes, all-history) and is deliberately **not** bundled here — a separate change with its own
runtime cost argument.

⚠️ This session could not take live measurements (no box/SSM access, Snowflake MCP unauthenticated
in this environment). Every figure above is inherited from the PR #693 / #772 / target-3 records
and is cited as such; the structural claims (graph positions, single-writer sets, caller sets) are
derived from the code and are what the guards pin.

---

## ⭐ A latent defect this bundle surfaced — registration was not isolated

Reasoning about hazard 2 below turned up a real bug, unrelated to any flip but triggered by them:

**DuckDB binds a parquet view at `CREATE` time, not lazily.** Measured on duckdb 1.5.3,
`CREATE OR REPLACE VIEW … read_parquet('<missing prefix>/**/*.parquet')` raises
`IOException: No files found that match the pattern` **immediately**. `_duck_connection` used the
batch `register_lakehouse_views` helper, which registers every view in one loop — so **a single
absent or unreadable S3 prefix aborted the connection before the first entry was read and blinded
EVERY freshness check**.

That is precisely the `savant.batter_pitches` decommission failure of 2026-07-06 — "one dead table
blinded every other freshness check" — reproduced **one layer earlier**, where the per-table
`try/except` added to `run()` in response to that incident structurally cannot reach it.

It is a live risk for this bundle specifically: a mirror written by a re-export leaf **does not
exist until that leaf's job first runs**, so `matchup_cell_sequential_posteriors`' absent prefix
would have taken the whole monitor down on the first post-deploy run — materially worse than the
false STALE the prime step was meant to avoid.

**Fix:** registration is per-table. A failure logs loud, leaves that view unregistered, and the
existing per-table read reports **QUERY ERROR for that entry alone** — never a silent OK (a check
that did not run is not a pass, NF1.7 (a)). `stg_statsapi_games` is deliberately **not**
special-cased: if the game-day probe cannot register, the run fails loudly, because every
`game_day_only` entry would otherwise be silently `SKIP`ped and the monitor would go quietly blind.

Both guards drive the **real** `_duck_connection` against **real** DuckDB over local parquet — a
mocked connection would only restate the loop's own structure. The create-time-binding premise is
*measured* rather than assumed, so a future DuckDB that goes lazy shows up as a failing test rather
than as silently redundant code.

## Deploy hazards

1. **The flips and the ops must ship together.** An S3-sourced entry on a box still running the
   un-reordered graph is a guaranteed daily false STALE. Guarded
   (`test_reading_s3_requires_the_reexport_in_every_writer_job`).
2. ⚠️ **The mirrors need PRIMING.** A re-export leaf only heals a mirror when its job next *runs*.
   `team_sequential_posteriors` and `matchup_cell_sequential_posteriors` heal at the next daily
   run; `matchup_cell` does not exist at all until then, and **`player_profiles_raw` would report
   a false STALE for up to SEVEN DAYS**, because its writer is weekly. ⇒ the deploy is accompanied
   by a **one-time operator prime** of all three exports (see the handoff). The isolation fix above
   means a missed prime now costs one `QUERY ERROR` line instead of the whole check, but the prime
   is still the point — a blind entry is not a monitored one.
3. ✅ **PR #772 is MERGED INTO THIS BRANCH** (2026-08-14), so this hazard is discharged. It was
   originally "#772 must be in `dev` first, or `needs_snowflake()` stays `True` and the dividend
   does not land". Test-merging the four open E11.24 PRs surfaced two collisions that made
   folding it in the right call rather than a convenience:

   * **The textual conflict resolves dangerously.** The two PRs collide in 2 **prose** hunks of
     `check_data_freshness.py`. Resolving it the reflex way — `git checkout --theirs` — takes the
     **whole file** from one side and silently reverts #772's `eb_bullpen_team_posteriors` and
     `eb_park_factors_raw` flips back to `snowflake`. Nothing catches it: no test fails (the
     bundle's own guard *permitted* exactly those two), `needs_snowflake()` just stays `True`,
     and the wake credit the whole bundle exists for never lands. Measured, not hypothesised —
     the first resolution attempt did exactly this.
   * **Two of #772's own guards go RED on the union**, so both PRs landing independently leaves
     `dev` red: `test_team_seq_is_held_back_from_the_flip` (asserts `team_seq` is still
     Snowflake — its own failure message prescribes *"Wire that first, then update this test"*,
     and the bundle wired it) and `test_the_flip_buys_no_wake_credit_while_any_blocker_remains`
     (asserts some entry is still Snowflake-resident). Both **re-anchored, not deleted** — the
     first is still the non-vacuity anchor for the coupling test below it, now proving that
     test's antecedent TRUE instead of FALSE; the second still pins that the credit belongs to
     the whole set and to no individual flip.

   The bundle's own two guards were tightened in the same pass, for the same reason: their
   "⊆ PR #772's two entries" allowance was written for a base without #772 and would now quietly
   permit exactly the entries the merge just flipped. And
   `test_the_union_with_pr_772_leaves_no_snowflake_read` — which had to *simulate* the end state
   — is replaced by a direct reading, because the merge makes one possible.

   ⇒ **all 7 entries read S3 and `needs_snowflake()` returns `False`, executed rather than
   simulated.** Either merge order is now safe; git dedupes the commits. Same reasoning PR #693
   used when it merged `e11.24-target-3` for this same file.

---

## Files

* `pipeline/ops/daily_ingestion_ops.py` — `reexport_team_seq_posteriors_op`,
  `reexport_matchup_cell_posteriors_op`, `reexport_player_profiles_op`. Each: unbound fan-out leaf,
  ALERT-tier that really pages (`send_alert`, distinct `dedup_key` per INC-39), **ungated**, finite
  `timeout=900` (INC-32 — a leaf still stalls the topological queue behind it under
  `in_process_executor`).
* `pipeline/jobs/daily_ingestion_job.py`, `pipeline/jobs/sensor_jobs.py`,
  `pipeline/jobs/weekly_player_profiles_job.py` — the wiring, one leaf per (table, writer job).
* `scripts/export_w8b_precursors_to_s3.py` — `matchup_cell_sequential_posteriors` added;
  `ON_DEMAND_ONLY` / `DEFAULT_NAMES` split so the lk10 bare invocation is unchanged.
* `scripts/check_data_freshness.py` — the three entries flip to `source="s3"`; the module docstring
  rewritten (the blocked-entry list is discharged; the retained Snowflake escape hatch is now an
  explicit, guarded decision rather than a leftover).
* `betting_ml/tests/test_e11_24_bundle_freshness_reexports.py` — 59 guards, **20 deliberate breaks
  RED-proven in-process with each mutation asserted to land** (E11.24 #682), including a stripper
  control and two-sided controls for `ON_DEMAND_ONLY` and `needs_snowflake()`.
* `betting_ml/tests/test_e11_24_check_guard_s3_repoint.py` — two guards **re-anchored** (not
  weakened, not deleted): the `needs_snowflake() is True` assertion encoded a world this PR
  retires, and the Snowflake-detector's positive control had prose instructing a deletion that was
  reconsidered.

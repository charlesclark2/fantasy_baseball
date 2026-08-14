# E11.24 target 3 — the `check_*` guard cluster off Snowflake

*2026-08-08 · branch `e11.24-target-3` · CODE-READY, deploy HELD until the target-6 soak closes*

The three daily data-quality guards each ran at **~100 % wake** — essentially every execution
RESUMED `COMPUTE_WH`, which on an X-Small warehouse is where ~80 % of the bill lives
(E11.20-COST). Combined census attribution ≈ **4.5 resumes/day**.

| script | tier | census | outcome |
|---|---|---|---|
| `check_odds_coverage.py` | ALERT → HALT under `ODDS_COVERAGE_STRICT=1` | ~1.1/day | **fully S3** |
| `check_prediction_coverage.py` | **HALT, unconditional** (no strict gate, no `try/except` in its op) | ~1.1/day | **fully S3** |
| `check_data_freshness.py` | WARN | ~2.3/day | **partial** — see below |

None of these is a change of underlying artifact. On the Snowflake target every table read here
is already a thin **view over a `lakehouse_ext` external table over the same S3 parquet**, so the
repoint removes a warehouse hop, not a source.

## The bar was verdict parity, and both halves were proven

A repointed guard fails in two silent directions: a **false PASS** misses a real outage, a **false
FAIL** HALTs the daily job on a healthy slate. So:

**Positive half — measured live, SF vs S3, on real slates.** The Snowflake side ran on
`MONITOR_WH` (`get_monitoring_connection`) so the open target-6 `COMPUTE_WH` census was untouched.
Run twice: once against draft SQL, then again driving the **shipped functions** (`fetch_coverage_rows`,
`check_prediction_coverage.run`, `_is_game_day`) — because the first run proves the *data* agrees,
not that the *code that ships* does.

* odds coverage — 8 anchors × a 3-day horizon = 24 date-verdicts, identical counts and identical
  classification on every one (`OK` / `NO_ODDS_YET` both represented).
* prediction coverage — 8 consecutive slates (2026-08-01..08-08), identical expected/scored counts,
  identical verdict, identical `feature_coverage_score` and `data_source` breakdown — **including
  08-01**, the INC-37 month-boundary slate, where both sides agree `n_feature_store = 2 of 15`.
* `_is_game_day` — 14 consecutive dates, identical booleans; plus the 2026 All-Star break
  (07-13..07-15), where both sides return **False**. That matters: in-season every date is a game
  day, so without the break dates the live check would only ever have exercised `True`.

**Negative half — CI, because live data cannot provide it.** No slate in the last two months is
degraded (0 below the 90 % coverage gate, 0 FREEZE/PARTIAL), so a live parity run structurally
*cannot* show these guards failing. `betting_ml/tests/test_e11_24_check_guard_s3_repoint.py` drives
the real query text through seeded in-memory DuckDB fixtures and proves each guard still trips:
FREEZE, PARTIAL, an under-covered slate (8/15) exiting 1, a zero-prediction slate exiting 1, an
off-day skipping rather than failing. A guard that can only pass has been defeated (NF1.7 (a)).

All 24 tests plus 7 deliberate source breaks were RED-proven: dropping the `::date` casts ·
`if coverage < min_coverage:` → `if False:` · reverting the archetype entry to Snowflake · dropping
`game_type` from the game-day probe · dropping an entry's `source` · re-adding a Snowflake import ·
dropping the UTC labelling. Each break turned exactly the intended test red.

> A note on the RED-proof itself: the first harness reported two guards "green on broken source"
> — a shell-quoting bug meant those mutations never landed. The re-run applies mutations
> in-process and asserts the source actually changed before running pytest. A RED-proof that can
> silently no-op its own mutation is the vacuous-guard failure one level up.

## The defect a naive repoint ships

`mart_game_spine.game_date` and `mart_game_odds_bridge.game_date` are **VARCHAR** in the parquet
(the INC-23 string-wrapped-timestamp cure); `mart_odds_outcomes.commence_date` is a real DATE. The
Snowflake query's `game_date <= '2026-08-08'` therefore becomes a **string** compare against
`'2026-08-08 00:00:00'`, which is lexicographically greater — so the window's last day disappears
**with no error at all** (the E9.52 silent-empty class).

Measured on the live parquet over `2026-08-06..08-08`: un-cast **26** spine rows / 26 bridge rows
where the cast form returns **41** / 41. In a FREEZE detector that is a 15-game hole that reads as
normal. Every predicate on those two columns now casts explicitly, and the cast is pinned by a
test that goes red if any one is removed.

## `check_data_freshness` — partial, and the wake credit is **zero**

Each entry now carries an explicit `source` (`"snowflake"` | `"s3"`), and the Snowflake connection
is opened **lazily** — so the day the last entry flips, the script becomes Snowflake-free with no
further edit (`needs_snowflake()`; proven both ways by test).

**Two reads flipped, and neither was flipped for credit.** Per E11.24 #679, wake is a **queue**:
only the first occupying statement after a suspend pays the resume. The census attributed
~2.3 resumes/day to `_is_game_day` simply because it runs first — repointing it *promotes* the next
Snowflake `MAX()` to pay the same resume. This script stops waking `COMPUTE_WH` only when **all**
its reads leave, which is why `story_prompts` calls it "a DIVIDEND of target 6, not a precursor".

* `_is_game_day` → S3 (the named target; parity above).
* `mart_player_archetype_posteriors` → S3, **a live bug fix**. Its Snowflake table has been frozen
  at **2026-07-05** because `update_archetype_posteriors_op` went S3-only at W7a — CLAUDE.md's
  op→tier table already records that "the W7a S3-only write means the SF-watching freshness monitor
  cannot see it fail", which is why that op was promoted WARN→ALERT on **2026-07-06, the day after
  the freeze**. So this entry had been printing `STALE (~800h > 48h)` on **every game day for a
  month**. It is the **fourth** instance of the retired-Snowflake-writer class this file already
  documents three times (`mlb_odds_raw` 07-05, `monthly_schedule` 07-23, `derivative_odds_raw`
  07-29). Those three were *removed* because their data left Snowflake entirely; this one is
  *repointed*, because the data is alive and current on S3 — repointing restores the monitor where
  removing it would delete coverage.

  ⚠️ **THRESHOLD CORRECTED 48h → 72h (2026-08-13), and the original figure was wrong.** This PR
  first claimed "at the 12:00/12:30/17:30 UTC run times the lag is 12.5–36.5h, ≥11.5h of headroom."
  A live run of the repointed script against real S3 — the runtime gate, which CI structurally
  cannot perform — refuted it:

  | measured | value |
  |---|---|
  | `max(run_timestamp)` | **2026-08-12 13:11 UTC** (the writer is healthy) |
  | `max(as_of_date)` | **2026-08-11** — an EVENT date, so D−1 by construction |
  | this check's cron | **12:30 + 17:30 UTC** (`30 12,17` in `capture.crontab`) |

  ⇒ at **17:30** (after the 13:11 write) as_of = D−1 → **41.5h**; at **12:30** (before it) as_of =
  D−2 → **60.5h**. The healthy band is **41.5–60.5h**, so a 48h threshold reads STALE at *every*
  12:30 run — the repoint would have swapped a false `STALE ~800h` for a new daily false STALE.
  ⭐ The original figure assumed the write lands BEFORE the 12:30 check; measured, it lands **41
  minutes after**. The verdict turned on a race nobody had timed. 72h clears the structural worst
  case with ~11.5h of real margin and still catches a two-day writer outage (≥84h).
  ⛔ Do not lower it without re-measuring `run_timestamp` against the cron times — the number is a
  property of that race, not of the data.

**The five that stayed, measured 2026-08-08 (`max(ts_col)`, each side):**

| table | SF | S3 | why it stayed |
|---|---|---|---|
| `matchup_cell_sequential_posteriors` | 08-08 13:03 | **no S3 table** | no lakehouse prefix exists — an export is the precursor |
| `player_profiles_raw` | 08-02 10:00 | **2026-06-28** | mirror 41 d behind → repointing = false `STALE 990h > 192h` on a healthy feed |
| `player_sequential_posteriors` | 08-08 13:02:18 | 08-07 13:02:08 | **structural 24 h lag** — mirrored at `lk9` (top of the daily) while the writer runs much later; only ~12 h headroom on a 36 h threshold. INC-25 shape: fix the export order, don't repoint the reader |
| `team_sequential_posteriors` | 08-08 13:02:31 | identical | parity exact — a safe *future* flip, held because flipping it alone buys zero credit |
| `eb_bullpen_team_posteriors` | 2026-08-08 | identical | ditto |
| `eb_park_factors_raw` | 2026-05-27 | identical | ditto |

## Follow-ups this opens

1. **Export `matchup_cell_sequential_posteriors` to S3** — the hard blocker.
2. **Fix the `player_profiles_raw` S3 mirror** (41 d stale; nothing else appears to read it, so the
   staleness is currently invisible).
3. **Re-export `player_sequential_posteriors` after its writer**, not at `lk9` — an INC-25
   build-ordering fix that also makes the mirror honest for any future consumer.
4. Then flip the remaining five together; `needs_snowflake()` turns the script Snowflake-free
   automatically, and **that** is when the ~2.3 resumes/day are actually deleted.

## Deploy + runtime gate (operator)

⛔ Held until the target-6 soak closes (Sun 2026-08-09 T+3) — removing these `COMPUTE_WH` wakes
mid-census would contaminate that reading.

🟥 CI mocks all IO, so CI-green is necessary-not-sufficient. After merge + deploy, a real box run
must show each guard producing the same verdict on a live slate — especially
`check_prediction_coverage`, whose verdict *is* the daily job's exit status.

## Files

* `scripts/check_odds_coverage.py` — fully S3; `fetch_coverage_rows(anchor, end, conn=None)`.
* `scripts/check_prediction_coverage.py` — fully S3; `run(..., conn=None)`; a zero-coverage banner
  that names the S3 predictions mirror as a candidate cause (diagnostic only — the verdict and
  exit code are unchanged, so it cannot affect parity).
* `scripts/check_data_freshness.py` — per-entry `source`, lazy Snowflake connection,
  `_max_ingestion_timestamp_s3`, `_is_game_day` on DuckDB.
* `betting_ml/tests/test_e11_24_check_guard_s3_repoint.py` — 24 guards, all RED-proven.
* `betting_ml/tests/test_odds_coverage_guard.py` — injection point moved to `fetch_coverage_rows`;
  every assertion unchanged.

---

# 2026-08-14 — the "cheap config-flip": TWO of three entries move, the third is REFUTED

Branch `e11.24-aug-14`. Read from the LAPTOP; the Snowflake side on **`MONITOR_WH`** so nothing
here touches the `COMPUTE_WH` census. `best_alpha = 0`.

## Gate — STEP D has settled, so stacking was allowed

The story's own precondition (one flip per soak) was to confirm #693's player-seq re-export left
its predicted transitional `[s3] STALE 37h`. Measured 2026-08-14 15:03 UTC, SF-free:

```
player_sequential_posteriors   s3   update_ts   2026-08-14 13:02:42    2.09h / 36h    OK
```

The S3 mirror carries **today's 13:02 writer batch**, which is the direct evidence that
`reexport_player_seq_posteriors_op` is running downstream of `update_player_posteriors_op` as
designed — stronger than the acceptance criterion (`[s3] OK`) asked for.

## ⛔ TWO PREMISES IN THE STORY CARD ARE WRONG, AND ONE OF THEM IS THE HEADLINE

**1. This is not a `table→view` flip, and could not have been.** The three targets are
`check_data_freshness.py` FRESHNESS ENTRIES, not dbt materializations. Two of the three are not
dbt models at all — `eb_park_factors_raw` is MERGE-written by `fit_park_priors.py:188` and
`team_sequential_posteriors` by `update_team_posteriors.py`'s SCD-2 write — so a table→view flip
is structurally impossible for them, which is the card's own "a merge target can't be a view"
warning turned on itself. The change that *was* available is a per-entry `source` flip, which is
genuinely config-only and carries no serving artifact at all.

⇒ the card's inherited #675/#693 diligence (ghost rows in a merge-incremental, history-spanning
readers, writer greps) mostly **does not apply**: a freshness monitor reads `MAX(ts_col)` and
serves nothing. The diligence that *does* apply is the INC-25 one — whether the S3 mirror this
monitor would now trust is guaranteed to keep up with its writer.

**2. "A real resume reducer, not just a wake-move" is FALSE, and this file already said so.**
`needs_snowflake()` is True while ANY entry is Snowflake-resident. Both remaining blockers were
re-confirmed live today:

```
player_profiles_raw                 s3 max 2026-06-28   1133h / 192h   STALE   (mirror ~47d behind)
matchup_cell_sequential_posteriors  s3 read FAILED: no files match the lakehouse prefix
```

So `run()` still opens a Snowflake connection on every fire and still pays the resume. **This
flip deletes ZERO resumes** — wake is a QUEUE (#679); it shortens the queue. That is exactly what
this module's own `DATA SOURCE` block already recorded ("flipping them buys ZERO wake credit
while the blockers remain … flip them in the SAME change that clears the blockers"), and the card
reversed that documented decision without new evidence. The flip was still made, because each
flipped entry is **individually correct** — not because it buys credit.

## The parity re-measurement — 2 exact, 1 refuted

`MAX(ts_col)` **and row count**, both sides, both directions (#693: a net row-count is not a diff):

| entry | SF | S3 | verdict |
|---|---|---|---|
| `eb_bullpen_team_posteriors` | 2026-08-14 / 48,932 | 2026-08-14 / 48,932 | **EXACT** → flipped |
| `eb_park_factors_raw` | 2026-05-27 / 362 | 2026-05-27 / 362 | **EXACT** → flipped |
| `team_sequential_posteriors` | 08-14 **13:03:04** / **83,636** | 08-14 **10:16:26** / **83,619** | **trails 2.78h, 17 rows** → HELD |

### Why the two that moved are safe STRUCTURALLY, not by a lucky reading

This is the distinction that made the set separable, and it is the reason a single "parity is
exact" reading was not accepted as sufficient for any of the three:

* **`eb_bullpen_team_posteriors`** — since the W8a ownership transfer (2026-06-29) the S3 parquet
  is **built** by `run_w1_lakehouse --w8a` and the Snowflake table is a MERGE copy *from*
  `lakehouse_ext` over that same parquet. **S3 leads Snowflake by construction** and can never be
  the staler side, so the monitor cannot regress by reading it.
* **`eb_park_factors_raw`** — an ANNUAL hand-run fit (last 2026-05-27) read against a **180-day**
  threshold. Measured lag at flip time 1,911h of an allowed 4,320h: the mirror could freeze for a
  further ~100 days before the verdict changed. The margin is a design quantity, not a reading.

Both are additionally the **right side to watch**: `mart_eb_park_factors`' DuckDB branch reads
`read_parquet(lakehouse_loc("eb_park_factors_raw"))` and eb_bullpen's S3 parquet *is* the built
artifact, so the monitor now watches what the served path actually reads rather than a warehouse
copy of it — the same argument target 3 made for `check_prediction_coverage`.

## 🚨 `team_sequential_posteriors` — the finding, and why it is NOT flipped

**It carries the identical INC-25 defect PR #693 fixed for its sibling, and #693 did not sweep it
up.** In `pipeline/jobs/daily_ingestion_job.py`:

```
line 136   lk10    = lakehouse_w8b_aggregator_op(start=lk9)     ← mirrors team_seq to S3
line 256   reexport_player_seq_posteriors_op(start=p_player)    ← #693's fix, player_seq ONLY
line 257   p_team  = update_team_posteriors_op(start=p_player)  ← the team_seq WRITER, ~40min later
```

The mirror is written near the top of the graph, the writer runs later, and nothing re-mirrors
afterwards — so within any run the S3 copy is one writer-cycle behind. The 08-08 "parity EXACT"
reading that the card inherited was taken at exactly the moment this module's docstring warns is
structurally blind ("at s15 the writer has not run yet either, so Snowflake and S3 return the
SAME value and the lag is INVISIBLE").

⛔ **It was deliberately not flipped on a margin argument.** The reasoned worst case (~23.5–26h
against a 36h threshold) looks survivable — and that is precisely the arithmetic that was WRONG
for player_seq, where target 3 recorded "~12h of headroom" and the true figure was a **38.72h
breach**. Twice-burned on the same table family, the precondition is the one already written here
for player_seq: **the re-export ordering fix and the source flip land together.**

The fix is a `reexport_team_seq_posteriors_op` modelled exactly on
`reexport_player_seq_posteriors_op` (fan-out leaf so it can never block `p_matchup`/predict, ALERT
tier with a real `send_alert`, finite subprocess timeout per INC-32, wired into **both** jobs that
run the writer per INC-38). That is a pipeline-graph change with its own runtime gate, not a
config flip — which is why it is not bundled into this change.

### ⚠️ And it may not only be a monitoring question

`feature_pregame_game_features_raw`'s **DuckDB (served) branch** reads this same mirror. If the
mirror is a writer-cycle behind, the served sequential-posterior block may carry that staleness —
the same shape #693 recorded as its own side finding ("the served EB as-of seq prior is one game
stale"). That is a **serving** question, needs its own measurement, and must not be folded into a
monitor change. Not chased here; flagged.

## Guards — `betting_ml/tests/test_e11_24_check_guard_s3_repoint.py` (+7, 40 total)

All five deliberate breaks were **RED-proven**, with the harness asserting the mutation actually
landed on disk before invoking pytest (E11.24 #682: a RED-proof that can silently no-op reports a
false "the guard caught it"):

| break | goes red |
|---|---|
| revert `eb_bullpen` to snowflake | `test_the_structurally_safe_entries_read_s3` |
| revert `eb_park_factors` to snowflake | `test_the_structurally_safe_entries_read_s3` |
| **sweep `team_seq` into the flip** | `test_team_seq_is_held_back_from_the_flip` **+ the coupling test** |
| `eb_bullpen` threshold 48→24h | `test_the_eb_bullpen_threshold_clears_its_structural_worst_case` |
| `eb_bullpen` threshold 48→200h | `test_the_eb_bullpen_threshold_still_catches_a_real_build_outage` |

⭐ The third break is the load-bearing one. `test_flipping_team_seq_to_s3_requires_its_mirror_to_be_
reordered_first` is **vacuous by design today** (its antecedent — the entry being s3 — is false),
which is the NF1.7(a) trap; it is paired with `test_team_seq_is_held_back_from_the_flip` as an
explicit non-vacuity anchor, and break 3 proves the coupling clause really does fire the moment
the antecedent becomes true. Neither test can be passing on nothing.

`test_the_flip_buys_no_wake_credit_while_any_blocker_remains` pins the honest reading against
re-narration, and names the three remaining blockers so a future census can tell a REMAINING
blocker from a REGRESSION.

## Deploy + runtime gate (operator)

`dev→main` **is** the deploy (`orchestration_cd.yml` `COPY . .`) — no `deploy.sh`, no env var.
⭐ Promote in the **03:35–03:55 UTC** quiet window (**not** the 03:30 tick — INC-36 deploy-drain
race). 🟥 CI mocks all IO, so CI-green is necessary-not-sufficient: the gate is a real box run of
`check_data_freshness.py` showing `eb_bullpen_team_posteriors` and `eb_park_factors_raw` reading
`[s3] OK` (not STALE, not NO DATA) on a live slate, with every other entry's verdict unchanged.
Rollback = `git revert` the merge; the change is monitor-only and touches no serving artifact.

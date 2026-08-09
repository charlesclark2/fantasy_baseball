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
  removing it would delete coverage. The 48h threshold was re-checked before flipping (S3 cadence
  is unbroken daily; at the 12:00/12:30/17:30 UTC run times the lag is 12.5–36.5h, ≥11.5h of
  headroom) so the restored monitor does not simply cry wolf for a new reason.

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

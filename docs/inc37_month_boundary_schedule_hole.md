# INC-37 — the month-boundary schedule hole (P1 serving-degrade, 2026-08-01)

**Status:** root cause identified and fixed forward in code; box remediation + verification is the
operator step (see the handoff). **Severity:** P1 — the entire 08-01 morning tier (15/15 games)
served on an amputated feature vector. **Prior occurrences: 2026-06-01 and 2026-07-01, both
undetected at the time.**

---

## 1. What paged

Three `send_alert` pages fired on 2026-08-01. They are **one incident**:

| Page | Signal |
|---|---|
| `check_intraday_fallback_op` | `morning: feature_store=0 of 15` — the whole tier fell through, `intraday_fallback=15 (100%)` |
| `check_served_prediction_integrity_op` | 4 problems: feature-store share 0% · `home_win` spread 0.021 < 0.025 (FLAT) · `run_differential` spread 0.394 < 0.5 (FLAT) · target book (Bovada) moneyline missing on **all 15** games |
| `check_feature_block_coverage_op` | 1 whole-slate date outage on a served feature block |

The two FLAT verdicts and the blank target-book price are **consequences** of the first, not
independent defects. In particular the Bovada blank is **not** an E9.52 recurrence: the E9.52
`game_date::date` cast is present and the query returns **15/15 priced** for 08-01 when run today —
it wrote NULL only because `mart_game_odds_bridge` had **zero 08-01 rows at predict time**, for the
same root cause as everything else.

## 2. Root cause

`ingest_statsapi.py schedule` fetches **whole calendar months** (`iter_months` expands any date
range to month boundaries). The last schedule capture of July ran at **2026-07-31T23:30:15Z** and
carried `2026-07-01..2026-07-31` — **zero games for 2026-08-01** (verified directly on the raw
partition).

`daily_ingestion_job` ran at 12:00 UTC and executed the **entire S3 lakehouse chain**
(`lakehouse_schedule_export_op` → W1 → W2 → W3 → W3pre flatten → W6 → W7b → spine/odds-bridge →
**W8a feature layer** → W8b aggregator, ops `lk1`..`lk10`) **before** `ingest_statsapi_schedule`,
which sat at `s6`. So the build flattened the July-only capture and produced a game universe that
**stopped at 07-31**:

```
feature_pregame_odds_features   max game_date = 2026-07-31   n(08-01) = 0
feature_pregame_park_features   max game_date = 2026-07-31   n(08-01) = 0
feature_pregame_team_features   max game_date = 2026-07-31   n(08-01) = 0
eb_starter_posteriors                                        n(08-01) = 0
mart_batter_rolling_stats / mart_bullpen_workload /
mart_odds_line_movement         max game_date = 2026-07-31   n(08-01) = 0
```

`ingest_statsapi_schedule` (12:1x UTC) *did* then fetch July **and** August (`--start-date
yesterday`, so `iter_months` spans both) — but every consumer had already run. The first capture
that could contain August landed after the intraday window opened (14:00 UTC), and the intraday
lineup rebuild at 16:39–16:42 UTC refreshed `mart_game_spine` + `feature_pregame_lineup_state` +
`eb_batter_posteriors_raw` + `--w8b-only`. That is why the store now holds **15 rows for 08-01 that
are almost entirely NULL**: the aggregator rebuilt against a fresh spine but LEFT JOINed a W8a layer
still frozen at 07-31.

Measured coverage of the served feature store (the exact blocks
`data_loader._FEATURE_STORE_COVERAGE_BLOCKS` gates on):

| date | n | mean cov | lineup | starter | team_rolling | bullpen_eb | sequential | odds |
|---|---|---|---|---|---|---|---|---|
| 07-29 | 16 | 1.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 07-30 | 10 | 1.000 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 07-31 | 15 | 0.833 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 |
| **08-01** | **15** | **0.178** | **0.07** | **0.00** | **0.00** | **0.00** | 1.0 | **0.00** |

`0.178 < 0.70` (`_MIN_FEATURE_STORE_COVERAGE`) → `load_todays_features` fell through to the intraday
assembly → `data_source='intraday_fallback'` on all 15 games, with no HALT and no error. 442 of 789
feature columns that were ≥80% populated on 07-30 read <20% on 08-01.

**So: on 363 days a year the mis-ordering is invisible (yesterday's capture already covers today);
on the 1st of a month it removes the whole slate.** Deterministic, not a race.

Confirmed recurring — same `feature_store=0` morning signature:

| date | morning tier | post_lineup tier |
|---|---|---|
| 2026-06-01 | `feature_store=0/9` (all `intraday_assembly`) | recovered, 9/9 feature_store |
| 2026-07-01 | `feature_store=0/14` (all `intraday_fallback`) | recovered, 14/14 feature_store |
| 2026-08-01 | `feature_store=0/15` (all `intraday_fallback`) | **1 row only at time of triage** |

## 2b. ONE ordering bug, THREE independent downstream victims

The stale flatten was not consumed by one thing. Anything that read the game universe during that
window scoped itself to July. Found in this order, each only after the previous was fixed:

1. **The feature build** — `mart_game_spine`, the W1–W6 marts, the odds bridge and the entire W8a
   layer missed 08-01 → the whole morning tier fell to `intraday_fallback` (§2).
2. **`ingest_weather`** — reads its game list from the same flattened schedule, found no 08-01
   games, and **never captured a `forecast_pregame` observation for the slate at all**. Measured:
   `weather_raw` held 0 `forecast_pregame` rows for 08-01 vs 9 on 07-30 and 14 on 07-31 (the
   intraday capture kept working — it writes `forecast_intraday`, which
   `stg_weather_raw_snapshots` rejects by design, `where weather_observation_type =
   'forecast_pregame'`). This is the INC-34 shape rather than a build-ordering one: an **INGEST**
   silently scoped to a stale universe. **Partly UNRECOVERABLE** — the pregame forecast window had
   closed for games already underway by the time it was found.
3. **The W11 serving tail** — W11b umpire / W11c weather / W11d public betting built on the July
   universe and produced ZERO 08-01 rows, leaving front-end panels blank
   (`feature_pregame_public_betting_features` 0/15, `feature_pregame_weather_features` 0/15).

⚠️ **Victim 3 was invisible to every gate, INCLUDING during the remediation.**
`_FEATURE_STORE_COVERAGE_BLOCKS` covers only lineup/starter/team_rolling/bullpen_eb/sequential/odds
— umpire, weather and public betting are NOT in it. So the coverage gate read a healthy **0.878**
while two whole blocks were empty and a front-end table had no rows at all. **RULE: after any
targeted lakehouse rebuild, verify the tiers the coverage gate does NOT measure (the W11 tail) —
"the gate is green" is not "the slate is complete".**

## 3. Why nothing caught it

- **`check_feature_block_coverage_op` is structurally blind to it.** It excludes the anchor date
  (recent window ends at anchor−1) and asserts only over dates already in the store, so today's
  collapsed slate cannot be in scope. It is a *store-history* guard, not a *today* guard.
- **`schedule_freshness_alert_sensor` opens at 14:30 UTC** — after the intraday capture has landed
  August, so both its gates read healthy. It is a feed-death backstop, and it fires far too late to
  protect the 12:00 UTC build anyway. (Its comment "ingest_statsapi_schedule is step 3, typically
  done by 12:05–12:10" is stale — the op had drifted to step ~20.)
- **`_alert_stale_game_spine` DID detect it** — it has existed since 2026-07-02 and asserts exactly
  "the spine does not reach today". It wrote a stderr `WARNING` into a Dagster step log and nothing
  else. This is the **E11.30 finding verbatim**: a detector that was never wired to notify. It
  almost certainly fired on 06-01, 07-01 and 08-01 and nobody saw any of them.
- CI is blind by construction (all IO mocked); parity is blind (both branches agree on the same
  short universe); every freshness check is blind (the *feed* was fresh — the *derived universe*
  was not, the INC-34/E9.48 shape).

**✅ Silver lining, recorded as required:** all three monitors **paged via `send_alert`** rather than
logging silently. This is the first real-incident validation of E11.30, and it is the only reason
the 08-01 occurrence was caught on the day while 06-01 and 07-01 were not.

## 4. Fixes

Two independent cures — either alone would have prevented this, and they fail differently, which is
why both ship:

1. **Ordering (`pipeline/jobs/daily_ingestion_job.py`).** `ingest_statsapi_schedule` moves to `s6`,
   **before** `lakehouse_schedule_export_op`, and the lakehouse chain now takes it as its `start`
   handle (a graph edge, not just source order). This is the INC-25 rule applied to the schedule: a
   consumer reading an S3 mirror must be rebuilt downstream of the refresh that feeds it, in the
   same run. Protects against a stale capture generally, not just at a month boundary.
   *Tier note:* `ingest_statsapi_schedule` was already HALT-tier, so the blast radius of a Stats API
   outage is unchanged (the job failed and predictions were skipped either way) — it now fails
   sooner, and no longer builds a feature universe from a schedule it could not refresh.
2. **Lookahead (`scripts/ingest_statsapi.py` + both callers).** New `--lookahead-days N` (pure
   helper `apply_lookahead`, default 0 so backfills are unchanged) extends the month range so the
   last N captures of every month also fetch the next month. Both recurring callers pass `3`.
   Verified: a 07-31 capture now expands to `[2026-07-01..07-31, 2026-08-01..08-31]`, while a 07-15
   capture still expands to July only — **no extra Stats API cost on 28 of 31 days**. All months of
   one fire land in a single `dt=` partition and `prune_same_month_partitions` keeps retention flat.

## 5. Guard

**`_alert_stale_game_spine` is promoted from a log line to a page** (the E11.30 rule: an ALERT-tier
detector must actually call `send_alert`). It now emits `[METRIC] spine_covers_today=<1|0|-1>` on
stdout beside its existing banner; `lakehouse_spine_odds_bridge_op` parses it and pages CRITICAL on
`0`. Keyed on the **same condition** the banner already computed, so this adds **zero new
false-positive surface**.

Three-valued on purpose: `-1` (the read raised) and an **absent** metric line are reported at WARN,
never scored as healthy — a guard whose evaluation failed must not make its assertion vacuously true
(the NF1.7 (a) lesson).

Decision logic lives in `betting_ml/monitoring/spine_horizon.py` (pure, `betting_ml`-side so the
fast gate can import it — `pipeline/__init__.py` reads the dbt manifest and would crash collection,
per E11.23).

`betting_ml/tests/test_schedule_build_ordering_guard.py` (12 tests, fast gate, `core` shard) pins
all of it. **All 7 structural invariants were verified to FIRE against the pre-fix source** — the
ordering check, the graph edge, both callers' lookahead, the lookahead wiring, the metric emission,
and the page itself.

## 6. Op → tier assignment (E11.7)

| Op / script | Tier | Reason |
|---|---|---|
| `ingest_statsapi_schedule` (moved to `s6`, before the lakehouse chain) | **HALT** (unchanged) | The whole daily feature build now reads the schedule it captures. A failed capture must stop the build rather than let it construct a universe from a stale schedule — which is exactly INC-37. Job failure pages CRITICAL via `run_failure_alert_sensor`. |
| `_alert_on_stale_spine` (inside `lakehouse_spine_odds_bridge_op`) | **ALERT-loud-but-continue** | Pages CRITICAL on a confirmed stale spine, WARN when the check could not be evaluated. Never raises: a stale spine is a loud page, not a reason to take the slate down, and a monitor must never be the thing that fails the op it watches. The host op keeps its existing W8a-mirror tier. |
| `check_w11_tail_coverage_op` (fans out from predict) | **ALERT-loud-but-continue** (no strict escalation) | Victim 3's guard (§6c). CRITICAL on BUILD_GAP, WARN on PARTIAL, silent on FEED_PENDING/OK/NO_SLATE, WARN on unevaluable. Never HALTs: a blank transparency panel must not withhold a slate's predictions, and it fans out from predict so it cannot gate the serving writes. Finite subprocess `timeout=` per INC-32. |

## 6b. Remediation record (2026-08-01)

Final state — full slate correct:

| tier | n | data_source | is_degraded |
|---|---|---|---|
| morning | 15 | `feature_store` | 0 |
| post_lineup | 4 | `feature_store` | 0 |

Feature-store mean block coverage went **0.178 → 0.878** (gate 0.70); the discriminative core
(`elo`, `bp_eb`, `park_run_factor`, `team_sequential`) went from ~2/3 imputed to fully served.
The 11 later games (22:40 UTC+) were left to the lineup-monitor sensor, which scores them on the
corrected features as their lineups post.

**Three things went wrong during the remediation itself. All three are process, not code:**

1. **`--lineup-confirmed` on the MORNING tier deleted 11 games' predictions.** The flag was reached
   for purely to get its delete-then-insert semantics, but it *also* filters the scored set to
   games with both lineups confirmed ([predict_today.py:2225-2238]) — and with no `--game-pks` the
   DELETE is an **unscoped full-slate wipe**. Result: 15 morning rows deleted, only the 4
   lineup-confirmed games re-inserted. The flag is explicitly post_lineup-only ("Gated on
   --lineup-confirmed so the morning (projected-lineup) run is unaffected"). **RULE: to re-score
   the morning tier, run `--prediction-type morning --s3` with NO `--lineup-confirmed` — it appends
   and every consumer dedupes to the latest `inserted_at`. Use `--lineup-confirmed` only with
   `--game-pks`, which scopes the DELETE.**

2. **🕳️ THE TIER GUARDS ABSTAIN AT n<5 AND REPORT `problem_count=0` — A VACUOUS PASS.** With only 4
   rows on the slate, `check_intraday_fallback` and `check_served_prediction_integrity` both hit
   `MIN_GAMES_FOR_CHECK = 5`, skipped assessment, and printed
   `intraday_fallback_alert_count=0` / `served_integrity_problem_count=0` — which reads as GREEN
   while 11 games sat unserved. The `*_tiers_assessed=0` metric was the only tell, and **no op
   pages on it**. This is the same "an anchor that fails to evaluate makes its assertion vacuously
   true" class as NF1.7 (a) — and it bites hardest during an incident, which is exactly when a
   slate is small. See follow-up (3) below.

3. **⏳ THE LINEUP SENSOR KEEPS WRITING ONE-AND-DONE ROWS BEHIND YOU WHILE YOU REMEDIATE.** Game
   824405 (first pitch 23:15) was scored by `lineup_monitor` at **19:44:13** — mid-remediation,
   after the W8a fix but BEFORE the weather rebuild landed at 19:46:31. Because `post_lineup` is
   one-and-done (INC-32: step 2b only re-fires games *missing* a row), that degraded row would
   never have self-healed, and it was invisible to the "which games still need a re-run" reasoning
   because it did not exist when the remediation started. **RULE: a remediation spanning the
   lineup-posting window must RE-CHECK for newly-written post_lineup rows after every stage, not
   once at the start** — and the check must compare each row's `inserted_at` against the feature
   store's actual rebuild time, not merely "is pre-game and has a row" (the first version of the
   triage query omitted that and re-flagged already-fixed games forever). Cutoff comes from the S3
   `LastModified` of the served feature parquet read via **boto3** (true UTC) — never `aws s3 ls`,
   which prints shell-local time.
4. **A slow serving write was chained behind `export_w6_raw_to_s3.py` with `&&`.** That script ends
   by printing `Next: uv run python ...` advice lines that look like the chain returned to a
   prompt, so the interrupt was ambiguous and the serving step was killed. **RULE: give a serving
   write as its own command, never chained behind a script that prints trailing next-step hints.**

Also verified and closed during remediation: the `[SERVING-GUARD] 13/15 abstained` line is NOT
rebuild residue — the morning tier's actionable-edge abstain rate is **1.00 on 7 of the 8 prior
days** (0.93 on 7/28); 8/1's 0.87 is the lowest in the window. Pre-lineup rows are previews and
`best_alpha=0` suppresses actionable edges regardless.

## 6c. The W11-tail guard is now a daily paging op (2026-08-01, follow-up session)

`scripts/check_w11_tail_coverage.py` (written during this incident) was a MANUAL post-rebuild
step, so victim 3's blind spot was still open in prod — nothing ran it daily and nothing paged on
it. That is the E11.30 shape ("detected, nobody notified") one story later.
`check_w11_tail_coverage_op` now runs it in `daily_ingestion_job`, fanned out from predict
(ALERT-tier, never HALTs — a blank transparency panel must not withhold a slate), and pages via
`send_alert`: **CRITICAL on BUILD_GAP**, **WARN on PARTIAL**, **silent on FEED_PENDING/OK/NO_SLATE**,
**WARN on unevaluable** (an anchor that fails to evaluate is never scored healthy). The paging
policy is `betting_ml/monitoring/w11_tail_coverage.py`.

⭐ **Wiring it surfaced a second, separate cadence defect — and it would have made the monitor
useless if shipped naively.** A BUILD_GAP ("the raw feed HAS the slate, the built table does not")
is a defect only for a block whose feed lands BEFORE the build that consumes it. Measured on the
live lakehouse (UTC):

| block | feed lands | W11 build (`lakehouse_w11_nightly_op`, s5c) | same-day assertable? |
|---|---|---|---|
| public_betting | 12:00 `ingest_action_network` (s4) | ~12:40 | **yes** |
| weather | 12:50 `ingest_weather` (s7) writes `forecast_pregame` | ~12:40 | no — +1 build cycle |
| umpire | 12:0x–16:39 `ingest_umpires.py --date today` (s8/s17) | ~12:40 | no — +1 build cycle |

So umpire and weather populate the current slate one build cycle late **by design**, and a monitor
paging on all three same-day would fire CRITICAL every single morning. Each block is judged on the
newest slate its build could actually have reached: `public_betting` on TODAY (the same-day INC-37
detector — on 08-01 it held 240 raw rows for the slate against 0 built rows), `umpire`/`weather` on
the PRIOR slate. This is the exemption `check_feature_block_coverage._DATE_OUTAGE_SKIP_NEWEST`
already documents for the identical reason, and it costs a genuine outage one day of latency —
which those outages always survive.

Second defect fixed in the same pass: the weather block's RAW side counted rows its own build
rejects. `stg_weather_raw_snapshots` selects `weather_observation_type='forecast_pregame'` only,
but the check counted any `weather_raw` row including the 00:00–02:00 UTC `forecast_intraday`
capture — a permanent false PARTIAL/BUILD_GAP against a table that was never going to contain
them. **In a two-sided raw-vs-built read the raw predicate must match what the build consumes.**

**Box smoke, 2026-08-01 — the negative half is done; the positive half has no production date.**
The current-slate box run reproduced the laptop exactly (umpire 5/15 PARTIAL, weather 14/15,
public_betting 15/15), and that stdout through `classify` returns severity **None** — the op is
silent on live production data even though the script itself reports `problem_count=1`. That is
the anti-alert-fatigue discrimination working, measured rather than asserted.

⭐ **No production date can prove the positive half.** A scan of all 1,039 slate dates
2021-04-01 → 2026-08-01 found **zero** BUILD_GAPs on any block (`public_betting_raw` present on
495 dates, features present on the same 495; weather/umpire likewise). The W11 tail is fully
healed, and the guard has no false-positive surface across five seasons. This is why
`--date 2026-06-01 --strict` returned OK — that gap was remediated, not a script failure.

⚠️ Runtime gate therefore still open on the page PATH only: `send_alert` hits SNS and CI mocks all
IO. Prove it post-deploy with a data-free command that feeds a crafted BUILD_GAP stdout through
the deployed `classify` into the real `send_alert` (throwaway `dedup_key`, and **no**
`AWS_DEFAULT_REGION=us-east-2` — SNS is us-east-1; that override is lakehouse-bucket-only).
Note `docker compose exec` runs the **baked image**, so any pre-deploy box run exercises the old
script.

## 7. Follow-ups (not done here)

- **The `mart_derivative_closes` `UnicodeDecodeError` (blocked the remediation) — 3 hypotheses
  ELIMINATED, 1 remaining. Recorded so the next occurrence does not re-walk them:**
  - ❌ *Data corruption* — built CLEAN on the laptop against the identical S3 inputs
    (2,038,349 rows, COPY OK); `stg_derivative_odds` scans fine (6,570,059 rows, no invalid UTF-8
    in any string column); no truncated objects in `derivative_odds_raw`.
  - ❌ *Disk / spill exhaustion* — 5.6G free on the overlay, `/tmp/duckdb_lakehouse_spill` empty.
  - ❌ *DuckDB version drift* — measured: **box 1.5.5, laptop 1.5.3**. Patch-level, and the box is
    NEWER. This was the leading hypothesis and it is refuted.
  - ⏳ *Memory pressure in a shared container stack* — the one that survives.
    `_safe_memory_limit_gb()` computes 0.6 × **host** RAM (~9GB of the 16GB r6g.large) with no
    account of the co-resident Dagster daemon / webserver / postgres / dbt-runner / Byparr.
    `mart_derivative_closes` runs the heaviest sort in W6 (`row_number()` over a 6-column
    partition across 6.5M rows) and this was a SECOND W6 build layered on the box's normal work —
    which fits "fine every other day, failed the one day we doubled up". Same family as INC-22,
    one level up: that fix sized the limit to physical RAM but still assumes DuckDB is the only
    tenant. NOT chased further on the available evidence.
- ⛔ **Pin DuckDB — DECLINED by the operator (2026-08-01). Do NOT re-open as a TODO without
  asking.** Kept here only so a future session does not re-derive it: the drift hypothesis was
  REFUTED (box 1.5.5 / laptop 1.5.3, patch-level, box newer), so the remaining case was
  diagnosability only, and that did not justify touching the lockfile every build depends on.
  Original reasoning follows.
- **Pin DuckDB — for DIAGNOSABILITY, not because drift caused INC-37.** `duckdb>=1.1.0` is
  unbounded, so laptop and box drifted to 1.5.3 vs 1.5.5 with nobody choosing either. That did not
  cause this incident, but it did mean the local reproduction ran on a different engine than prod,
  which had to be checked before it could be ruled out — mid-P1. Pin to the box's version (align
  the laptop UP to prod, never prod down to a laptop). Same class as the serving-pickle pin
  already applied to sklearn/ngboost/lightgbm. Low priority.
- **Stop `_build_marts` destroying its own error message.** `conn.execute` is unwrapped there, so a
  DuckDB error whose message isn't valid UTF-8 surfaces as `UnicodeDecodeError` and the real
  diagnostic is lost. Catch, re-decode with `errors="replace"`, re-raise with the model name.
- **Make a non-assessed tier guard visible.** Per 6b(2): when `*_tiers_assessed=0` but predictions
  exist for the served date, the op should page WARN ("could not verify") rather than let
  `problem_count=0` read as healthy — the same three-valued treatment `spine_horizon.classify`
  already applies to an absent/unevaluable metric.
- `schedule_freshness_alert_sensor`'s docstring still claims `ingest_statsapi_schedule` is "step 3,
  typically done by 12:05–12:10". True again after this fix, but the 14:30 UTC window still makes it
  a feed-death backstop only — it cannot protect the 12:00 UTC build.
- The exact `(block, date)` that `check_feature_block_coverage_op` named on the box is **not
  recoverable from data** — the store state it read has since been overwritten by the 16:42 UTC
  intraday aggregator rebuild, and the Dagster GraphQL endpoint needs `DAGIT_BASIC_AUTH_*` which was
  not available off-box. The two visible candidates in the current store are `bullpen_eb` at 0.0 on
  07-31 (the documented one-build-cycle lag, normally exempt as the newest played date) and the five
  blocks at 0.0 on 08-01. Pull it with
  `python3 scripts/ops/dagster_steplog.py <runId> check_feature_block_coverage_op` if the exact
  attribution matters; it does not change the root cause or either fix.

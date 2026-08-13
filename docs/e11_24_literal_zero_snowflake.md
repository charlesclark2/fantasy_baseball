# E11.24 — LITERAL-ZERO SNOWFLAKE (the August-bill lever)

Status: **stage 1 COMPLETE AND VERIFIED — 1b measured live on its first post-flip window
(2026-08-01)**. Target 6 is code-complete with both levers still OFF, awaiting a quiet-window
flip. Stages 2–4 scoped below.

## 2026-08-04 — FU-1 (8/2) + FU-2 (8/3) post-flip wake census — ⛔ 6a SOAK **NOT CLOSED**, FU-3 **NOT CLEAR**

Read from the laptop at 04:35–04:55 UTC 8/4 via `scripts/report_e11_24_wake_census.py --days 10`
(MONITOR_WH) plus a MONITOR_WH serving read and two SF-free `check_w11_tail_coverage.py` runs.
`account_usage` lag at read time: query_history **27 min**, warehouse_events **143 min** ⇒ both
target days' 14–23 bands are fully settled. Nothing in this session connected on COMPUTE_WH.

### The headline number — and why it does NOT close the soak

| 14–23 band (6a's window) | 7/28 ref | 7/30 ref | 8/1 | **8/2** | **8/3** |
|---|---|---|---|---|---|
| umpire-chain **executions / waits** | 49 / **11** | 49 / **13** | 80 / **13** | 49 / **9** | 36 / **9** |
| `lineup_monitor` audit-INSERT fires (invocation proxy) | 7 | 7 | 10 | 7 | **4** |
| waits per monitor fire | 1.57 | 1.86 | 1.30 | 1.29 | **2.25** |
| whole-day resumes / active-min / executions | 44 / 167 / 3518 | 43 / 141 / 4172 | 55 / 159 / 2565 | 44 / 145 / 3629 | **34 / 109 / 1536** |

Both post-flip days land on **9 waits** — a **−25.0%** cut against the clean reference mean of 12.0
(−30.8% vs 7/30 alone, −18.2% vs 7/28 alone), i.e. squarely inside the pre-registered **~7–9** band
and nowhere near the **>~40%** figure that would have meant the writer model needs re-deriving.
**On the number alone this reads as the predicted ~30% pass. It must not be recorded as one**,
because on neither day is the number attributable to the gate:

- **8/2 — the gate was provably OFF for the entire band.** Per the FU-1 verification record, the
  persistent `dagster-codeloc` container `DefaultRunLauncher` executes job subprocesses in was
  created **20:52:24 UTC 8/2**, ~15h after the 05:29 flip, while all **7** of that day's
  confirmed-lineup `lineup_monitor_job` rebuilds ran **14:42–19:44 UTC** — before it. Both
  bracketing runs' Postgres event logs carry **0 `umpire-gate` lines**, so `umpire_gate_on()` was
  False in the container that actually ran them, and the job has not fired since 19:44. ⇒ **8/2 is a
  PRE-flip day.** Its value is calibration, and it is the single most important line here:
  **9 waits is reachable with the gate OFF.** The gate-off band ranges 8–14 across the census
  (7/27=8, 7/28=11, 7/30=13, 8/1=13, 8/2=9), so a lone 9 is not outside pre-flip noise.
- **8/3 — the gate was armed, but the day cannot carry the measurement.** It is the only day with
  the flag durably live (container recreated 20:52 UTC 8/2, redeployed again 01:11 UTC 8/3), and it
  is structurally unrepresentative: an **8-game** slate (vs 15) whose first pitches are **22:40,
  23:05, 23:40, 00:05, 00:05, 00:10, 00:40 and 01:40 UTC** — six of eight *after* 00:00 UTC. Whole-day
  executions 1536 vs 3629, active-min 109 vs 145, resumes 34 vs 44. **`lineup_monitor` fired 4×
  vs 7× on each reference day (−43%), a larger drop than the −31% in umpire waits it is supposed to
  explain.** Normalised per monitor fire, 8/3 is the **highest** reading in the whole window (2.25 vs
  1.57/1.86 pre-flip) — the opposite of a 30% cut.

⭐ **THE MEASUREMENT PROBLEM, STATED PLAINLY: on 8/3 the gate firing and the slate collapsing
predict the SAME signature.** A skipped rebuild removes its CTAS *execution* along with its wait, so
"the gate skipped one fire in three" and "the slate was half-size and started ~8h late" both yield
executions↓, waits↓, wait-rate flat (25.0% on 8/3 vs 22.4%/26.5% on the references). The instrument
cannot separate them on this day, and the story's own sizing was deliberately done in
**INVOCATIONS** for exactly this reason (the lever-1b lesson: an outage fakes every volume metric —
here a *late, small slate* does). ⇒ **the 8/3 read is UNINTERPRETABLE as a lever measurement: it
neither confirms the ~30% prediction nor triggers the >40% re-derive.**

**⇒ VERDICT — the soak has produced ZERO valid post-flip observations.** One day was gate-off, the
other was structurally unusable. This is a *measurement gap, not a gate defect*: nothing here
suggests the gate logic is wrong, and no rollback is warranted.

### Per-day verdicts (the required two lines)

- **8/2 (FU-1)** — (a) umpire band **9 waits, −25.0%** vs the 12.0 reference mean, inside the ~7–9
  prediction — but supports **NEITHER** reading: the gate was off all band, so this is a pre-flip
  data point proving 9 is attainable ungated. (b) serving no-regression: **YES**.
- **8/3 (FU-2)** — (a) umpire band **9 waits, −25.0%**, inside ~7–9 with the gate armed — but
  **NOT MEASURED**: the drop is fully absorbed by a 43% fall in monitor invocations and per-fire
  waits *rose* to the window high. Neither the ~30% pass nor the >40% re-derive is supported.
  (b) serving no-regression: **YES** on the discriminating signals; W11-tail caveat below.

### Serving no-regression — YES on both days

Deduped to the currently-serving row per (tier, game_pk) — aggregating raw rows fakes an
`intraday_fallback` collapse. Read on MONITOR_WH against `baseball_data.betting_ml`.

| signal | 7/31 | 8/1 | **8/2** | **8/3** |
|---|---|---|---|---|
| post_lineup `h2h_edge is not null` | 13/15 | 13/15 | **14/15** | **7/7** |
| morning `h2h_edge is not null` | 0/15 | 3/15 | 0/15 | 0/8 |
| post_lineup avg `feature_coverage_score` | 0.944 | 0.989 | 0.978 | 0.952 |
| morning avg `feature_coverage_score` | 0.800 | 0.889 | 0.822 | 0.771 |
| `data_source='feature_store'` | 15/15 | 15/15 | 15/15 | 8/8 |
| `intraday_fallback` | 0 | 0 | **0** | **0** |

`abstain_reason` MIX carries **no new category** on either day: 8/2 post_lineup is 14×
`edge_to_sigma=0.000<threshold=0.25` + 1× `ci_width_unavailable` (vs 13+2 pre-flip — one *more*
game with a computable edge), 8/3 post_lineup is 7× `edge_to_sigma` + 0× `ci_width_unavailable`.
Morning is 100% `ci_width_unavailable` on both, as pre-flip. Zero intraday fallback on every tier
every day. Per the pre-registered traps, `sigma_tier='abstain'` (saturated at 100% under
`best_alpha=0`) and the chronic `total_runs` FLAT finding were **not** used as signals.

Two sub-reference readings, both checked and neither attributable to 6a: morning coverage 0.771 on
8/3 is the window low but umpire/weather are **not** members of `_FEATURE_STORE_COVERAGE_BLOCKS`, so
the W11-tail gap cannot be its cause; and 8/3 has 7 post_lineup rows against 8 morning rows because
game **825095** (first pitch **01:40 UTC 8/4**) was still `Live / In Progress` at read time — 6a
gates a Snowflake CTAS inside the rebuild and cannot suppress a scoring row.

### W11 tail — 8/2 better than reference; 8/3 pending the next nightly, and NOT 6a

```
8/2   umpire 15/15 OK    weather 14/15 OK   public_betting 15/15 OK     (ref 8/1: umpire 5/15 PARTIAL)
8/3   umpire  0/8  BUILD_GAP  weather 0/8 BUILD_GAP   public_betting 8/8 OK
```

**8/2 is no worse — it is better** than the 8/1 pre-flip reference, which is the direct evidence
that the pipeline heals umpire to full coverage one build cycle later *with the flag present*.

**8/3's BUILD_GAP is not 6a, on two independent grounds.** (1) **`public_betting` is 8/8**, so the
~12:40 build's game universe was *not* stale — the INC-37 fingerprint would have zeroed all three
blocks; what is left is the documented feed-cadence lag, and umpire/weather are precisely the two
blocks whose feeds land *after* that build (and later still for a slate first-pitching 22:40–01:40).
The 8/4 nightly had not run at read time. (2) **6a is umpire-only and gates only a Snowflake CTAS;
it cannot touch weather.** Weather co-moving with umpire proves a shared cause upstream of 6a.
⏭️ Operator: re-run `check_w11_tail_coverage.py --date 2026-08-03` after the 8/4 nightly to confirm
it heals to OK as 8/2 did.

### Incidental — a provisioning stall on 8/3 worth an operator glance (not 6a)

The 8/3 14–23 band shows `avg_wait_s` **474.7** against ~0.2–1.0 on every other day. It is **11
outliers, not a systemic stall**: median wait 0.2s, max **2402.8s (40 min)**, 11 of 33 over 600s.
The long waiters are monitoring/guard statements — a failures-count guard (6× @ 1184.8s avg), an
`information_schema.columns` read (3× @ 2172.0s), a `feature_pregame_ga…` count and an `ump_ac`
query — **not** the umpire CTAS, so the primary metric is unaffected. Flagged only because a
40-minute provisioning queue is not normal for an X-Small.

### Corrections to the pre-flip reference table

8/1's umpire row was recorded as **38/5** from a read truncated at 20:09 UTC; the now-complete day
is **80/13**. Use 80/13. This does not change the 7/28 + 7/30 reference choice.

### ⛔ FU-3 is NOT clear to deploy

FU-3 (the writer-idempotency fix) **moves this same skip rate**, and the whole reason FU-1/FU-2 run
first is to bank a valid pre-FU-3 post-flip baseline. No such baseline exists yet. Deploying FU-3
now would permanently confound 6a's effect with FU-3's — neither could be attributed afterwards.

**What unblocks it: ONE valid gate-armed observation day.** The gate has been durably live since
20:52 UTC 8/2, so no flip or redeploy is needed — this needs a *normal* slate (≈13–15 games with
first pitches back inside the 14–23 UTC band, giving ~7+ `lineup_monitor` fires), then re-run this
same census and compare in-band umpire waits against 7/28 (11) and 7/30 (13) at matched invocation
count. ⭐ **Report the per-fire figure alongside the raw count** — this session's whole finding is
that the raw count alone cannot tell the gate from the slate. Also worth pulling once, since it
settles attribution directly rather than statistically: the next `lineup_monitor_job` run's
`umpire-gate` REBUILDING/SKIPPING lines from the Postgres event log
(`DagsterInstance.all_logs(run_id)` inside the container — survives container recreation, unlike
`docker compose logs`), which is an operator step (`ssm:*` is denied to the laptop role).

## 2026-08-01 — lever 1b VERIFIED (the first lever to move RESUMES), and 6a's pre-flip baseline

Session scope was deliberately narrow: it was **15:11 CDT with a live 15-game slate** and the box
had just recovered from INC-37 that morning, so the safe READ was done and the **6a flip was NOT
attempted** (BOX_OPERATIONS §10b: flip outside a live slate; INC-36 made mid-slate deploys the
risk window). No box access this session either — the laptop IAM user still has no `ssm:*`
(`ssm:DescribeInstanceInformation` → AccessDenied), so every flip/box command is in the handoff.

### The instrument is now a script, not a paste-buffer of SQL

`scripts/report_e11_24_wake_census.py` (laptop, read-only, runs on `MONITOR_WH`) emits all three
instruments **cut by UTC band** — resumes, distinct active-minutes, and
`queued_provisioning_time > 0` waits — plus a per-shape table that carries **executions beside
waits** so "the lever fired" stays separable from "the caller stopped". Re-run it for the 6a
verification; it is the same instrument on both sides of the flip.

### ✅ 1b fired. Read it in the 08–13 band, and read FIRES, not executions

| 08–13 band (1b's window) | 7/28 | 7/30 | 7/31 | **8/1** |
|---|---|---|---|---|
| **RESUMES** | 22 | 17 | 16 | **11** |
| provisioning waits | 24 | 21 | 22 | **15** |
| active minutes | 86 | 59 | 60 | **37** |
| executions | 2,568 | 2,868 | 1,455 | **877** |
| **distinct catch-up FIRES** (hours containing `int_bullpen_ali`) | **6** | **5** | **6** | **2** |

⭐ **The discriminating statistic is the FIRE COUNT, not the execution count**, and this is the
lesson worth carrying. 8/1 was an INC-37 day: total `COMPUTE_WH` executions were ~1,820 against a
typical 4,000–6,000, so *every* volume metric fell and a volume-based reading would have credited
1b with an outage's work. The fire count cannot be faked that way — the chain either ran in an
hour or it did not. Pre-flip the chain ran in **5–6 distinct hours every morning for nine
consecutive days**; on 8/1 it ran in **two** (hours 10 and 12), with hours **09 and 11 completely
silent on `COMPUTE_WH`** where each had carried ~190 executions on 7/30 *and* 7/31. That is the
gate's exact fingerprint — a fire that lands no pitches yields no output, Dagster skips the chain.

⚠️ **Honest limit: this is one day, and the confound is real.** "Savant published later, so the
sensor stopped re-requesting" produces a similar shape. What argues against it is that the ~190-
execution hourly blocks were present at hours 8–13 on *every* pre-flip day — i.e. the chain
re-fired on a fixed hourly cadence regardless of when Savant actually published — and on 8/1 the
no-op hours *before* the one real chain (hour 10) are the ones that went quiet. **Re-read the
08–13 band on 8/2 and 8/3 before booking 1b as closed.**

⭐ **1b is the FIRST lever in this story to move RESUMES** (22 → 11 in-band, −50% vs the clean 7/28
reference), which is exactly the predicted asymmetry: 1b removes a **burst**, the weather lever
removed an **evenly-spread poller**, and each is legible in a different instrument. Reporting only
one of the two would have under-credited one of the two levers. ⛔ Wake↓ still does not imply
credit↓ — the credit line only moves once the warehouse stays suspended for long stretches.

### 6a's pre-flip reference (14–23 band) — and 8/1 is NOT usable as one

| 14–23 band (6a's window) | 7/28 | 7/30 | 7/31 | 8/1 |
|---|---|---|---|---|
| resumes | 16 | 15 | 35 | 24 |
| provisioning waits | 27 | 28 | 49 | 32 |
| umpire-chain executions / waits | 49 / 11 | 49 / 13 | 71 / 13 | 38 / 5 |

**Use 7/28 and 7/30.** 7/31 carries the prior session's `dbtf test` runs and two `--reset`
backfills; **8/1's afternoon is INC-37 remediation** (a visible burst at UTC 17–19) *and* the day
is truncated at the 20:09 UTC read. Post-flip, compare **8/3+ against 7/28 and 7/30**, in-band.

### 🔎 6a's blast radius is smaller than the story assumed — the served umpire block does not move

Worth stating before the flip, because it changes what "no regression" means. `lineup_dbt_feature_-
rebuild` — the op 6a gates — **copies the Snowflake external table**; it does not regenerate the S3
parquet. The served umpire block comes from `run_w1_lakehouse --w11b`, which runs **only in the
nightly W11 op** (`W11B_UMPIRE_NIGHTLY`). Measured on the live 8/1 slate: the raw umpire feed had
rows landing **16:39 → 20:20 UTC** covering 10 of 15 games, while both the built stg *and* the
built feature table held **5** — i.e. the served umpire table is a once-nightly artifact today,
and 6a cannot make it worse. ⇒ the post-flip acceptance test is "no NEW abstain / no NEW
absent|all-null contract, and the W11 tail no worse than the pre-flip reading", not "umpire
coverage is complete".

### 🕳️ The blind spot INC-37 named now has an instrument — `scripts/check_w11_tail_coverage.py`

The six-block coverage gate does not measure umpire, weather or public betting, and
`check_feature_block_coverage.py` excludes the anchor date, so it is a store-HISTORY guard and
structurally cannot see a collapsed TODAY. The new check reads each block **two-sided** — raw feed
vs built feature table, against the non-postponed slate — so it discriminates the case that
matters from the case that must stay silent:

- **BUILD_GAP** (raw has the slate, the built table has 0) = the INC-37 fingerprint → problem.
- **FEED_PENDING** (neither has it) = a normal morning before the HP assignment posts → silent. A
  naive "umpire 0/15 ⇒ page" would fire every single day and get muted.

ALERT tier, never exits non-zero without `--strict`. **Live reading, 2026-08-01 (the pre-flip
reference to compare against after the 6a flip):**

```
  block             slate    raw  feature   verdict
  umpire               15     10        5   PARTIAL      ← nightly --w11b lag, pre-existing
  weather              15     14       14   OK
  public_betting       15     15       15   OK
```

Serving itself was healthy at the same moment (`check_intraday_fallback`: morning 15/15 and
post_lineup 5/5 both 100% `feature_store`), i.e. INC-37's remediation held.

⏭️ Not wired into the daily job as an op this session — that is a pipeline change on a day the box
was already recovering, and it belongs with the ALERT-tier `send_alert` family (E11.30) rather than
bolted on mid-incident. Recorded as the obvious follow-up.

## 2026-07-31 re-census — what is actually live

Levers 1, 2 and 3 were flipped on the box between 7/29 evening and 7/30. **1b is still OFF and is the
only stage-1 lever left**; the E11.20 close (7/31) removed its blocker.

Verified without box access (the laptop IAM user has no `ssm:*`) by reading **query shapes that stop**
in `query_history` — stronger evidence than an env var, since it proves image + flag + code path at
once. Each was cross-checked against **total executions**, because a shape falling to zero is also
what a dead job looks like:

| Lever | Evidence | Verdict |
|---|---|---|
| 2 weather slate/venue | executions 103 (7/27) → 103 (7/28) → **0** (7/30) → **0** (7/31); capture still running | ✅ live |
| 1 `compute_elo` bulk games read | last seen **2026-07-29 13:17**, gone after | ✅ live |
| 3 admin cost dashboard | 19 (7/27) → 0 (7/28) → 0 (7/30) | ✅ live |
| **1b statcast catch-up gate** | `int_bullpen_ali_by_season` still **10×/hour, UTC 08–13**, identical on 7/28 / 7/30 / 7/31 | ❌ **still OFF** |

### Measured response: resumes flat, awake-time −16%

`COMPUTE_WH` resumes/day: **7/28 = 44** (clean baseline) → 7/29 = 62 (dirty, skip) → **7/30 = 43** →
7/31 = 20 (partial; `account_usage` lagged 121 min). Resumes alone say stage 1 bought nothing.

**It did.** Distinct active minutes — minutes containing ≥1 query, the closest proxy to awake-time
under `AUTO_SUSPEND=60s` — went **167 (7/28) → 141 (7/30), −16%**.

⭐ **Method note for the next census: a lever that removes an evenly-spread 24/7 poller (weather) deletes
awake-MINUTES without deleting RESUMES**, because the remaining bursty pipeline work re-wakes the
warehouse regardless. Report both, or you will systematically under-credit exactly the levers this
story is built on. (Sum-of-elapsed still moved the *wrong* way, 62.9 → 79.9 min — it remains the wrong
instrument, per E11.20-COST.)

### 🚨 ROOT-CAUSED — `--backfill` IS NOT IDEMPOTENT AND SILENTLY DOUBLE-APPLIES ON A POPULATED TABLE

Not E11.24 (found while censusing); **a live serving-data defect, own story required.**

`team_sequential_posteriors` has absorbed **2.72–2.75× more game-outcomes than games played**, on
every team. `win_prob` takes exactly one observation per team per game, so `n_cumulative` MUST equal
games played — an identity, not an estimate. Measured 2026-07-31 19:50 UTC: **PHI claims 151 wins in
109 games played; TEX 148 in 109; KC ratio 2.75.** Physically impossible.

**The mechanism, read straight off the SCD-2 history (`n_cumulative` per `update_ts`, team NYY):**

| Event | What happened | `n_cumulative` |
|---|---|---|
| 2026-06-03 06:37–06:40 | first `--backfill --season 2026`, table empty | 1 → **59** ✅ correct |
| 2026-06-04 09:54–09:58 | **backfill re-run on the POPULATED table** | 61 → **120** 🚨 1st doubling |
| 06-04 → 07-31 | daily `--catchup`, correct +1/game on an inflated base | 120 → 186 |
| 2026-07-30 06:00 | backfill **dry-run** (125 per-date reads, zero writes) | — |
| **2026-07-31 19:40–19:46** | **backfill re-run for real** | 186 → **295** 🚨 2nd doubling |

⭐ **`run_backfill` has no reset and no guard.** `_prep` only ensures DDL; `_load_current_seq` reads the
existing `is_current` posterior as the PRIOR and then replays every game date on top. So running
`--backfill` against a populated table adds a full extra season of observations. The 6/4 instance went
**undetected for two months** — nothing asserts `n_cumulative == games played`.

📉 **Impact: the MEAN survives, the VARIANCE does not.** Duplicates are replays of the same games, so
`posterior_mu` ≈ the true record (NYY μ=0.5619). But `posterior_sigma2 ∝ 1/(a+b)`, so the served
posterior is now **~2.7× overconfident**. This feeds `feature_pregame_game_features_raw` via
`source('betting','team_sequential_posteriors')` — an unconditional-core discriminative family.

🔧 **Two corrections to my own earlier reads in this doc**, both worth keeping as worked examples:
1. I first blamed the backfills, then talked myself out of it ("`n_cumulative` was already 172 on 7/18,
   so it predates them"). **Both halves were wrong in an instructive way** — the inflation *did* come
   from backfills, just from the **6/4** one, not the 7/30–7/31 pair I had in view. A defect can be
   caused by the mechanism you suspect and still not by the *instance* you are looking at.
2. The duplication hypothesis is **refuted**: `mart_game_results` 2026 is clean (1,637 rows = 1,637
   distinct `game_pk`, 0 dupes). Not the glob-dup class, and not the double-invocation path either —
   the daily `--catchup` increments are correct.

**Remediation (operator):** the chain is non-idempotent, so the only correct repair is a clean rebuild —
delete `season=2026` rows, then run `--backfill --season 2026` **exactly once**. And `run_backfill`
needs a guard that refuses a populated table without an explicit `--reset`. ⚠️ Check the two sibling
writers (`update_player_posteriors.py`, `update_matchup_cell_posteriors.py`) — same shape, same risk.

## Why this story exists

E11.20 cut COMPUTE_WH resumes **177 → 44/day (−75%)** and the credit line barely moved (<15%).
That is not a failed measurement — it is what the E11.20-COST thesis predicts: ~80% of the bill is
**wake/idle burn**, and 44 resumes still spread across enough of the day that an X-Small warehouse
never sleeps in long stretches. **Reducing wakes ≠ killing wakes.** The warehouse only stops
metering when the resume count on a quiet window reaches ~zero, so every remaining waker has to go.

## The measured target list (7/29 census, 44 resumes on 7/28)

Resumes attributed by joining each `RESUME_WAREHOUSE` event to the first query at/after it.

| # | Waker | Share | Stage | State |
|---|-------|-------|-------|-------|
| 1 | Hourly `CREATE TABLE IF NOT EXISTS … team_elo_history` (a no-op DDL) | 14% | 1 | ✅ **LIVE on the box** (verified 7/31), `E11_24_ELO_SF_FREE` |
| 1b | **Root cause of #1** — `statcast_catchup_job` re-fires hourly and runs the whole chain on ~5 fires that land nothing | (multiplies 1, 4 and part of "daily one-offs") | 1 | ⚠️ **shipped but STILL OFF** (verified 7/31) — `E11_24_STATCAST_CATCHUP_GATE`, now unblocked |
| 2 | 24/7 hourly weather slate/venue `SELECT` | 14% | 1 | ✅ **LIVE on the box** (verified 7/31), `E11_24_WEATHER_SF_FREE` |
| 3 | `CREDENCE_API` metering query "waking the warehouse it measures" | ~5%/day (see the methodology correction) | 1 | ✅ **LIVE on the box** (verified 7/31), `SNOWFLAKE_MONITOR_WAREHOUSE` |
| 4 | Raw-SQL stragglers: the 3 sequential-posterior state writers | part of daily one-offs | 2 | scoped below |
| 4b | `check_data_freshness.py` (host cron, 2×/day, 24/7) | ~2 resumes/day | 2 | scoped below |
| 5 | The dead `predict_today` Snowflake freshness branch | 0 (it is a read, not a waker) | 3 | **soak-blocked** |
| 6 | Intraday EB/lineup dbt rebuild chain | **41%** | 4 | **soak-blocked** |
| 7 | Drop the ext tables / `lakehouse_ext` mirrors → suspend/drop the warehouse | — | 5 | after 1–6 |

### The finding that reframes #1

The census flagged the hourly `team_elo_history` DDL as "NOT the daily `compute_elo` op — identify
the caller". The caller is **`statcast_catchup_job`, re-fired by `statcast_freshness_sensor` on an
hourly `run_key` from 04:00 ET until Savant publishes** (`statcast_freshness_sensor.py:160`). On a
normal morning that is ~6 fires, and ~5 of them land **no pitches** — yet each still runs two
`refresh_w1_external_tables.py` passes (an `ALTER EXTERNAL TABLE … REFRESH` storm), the bullpen
posterior dbt build, the three sequential-posterior writers, `compute_elo`, the umpire feature
rebuild, `predict_today_morning` and a serving write.

So the DDL was the *visible symptom*; the redundant re-fire is the cause, and it multiplies **every
Snowflake touch in the morning chain by ~6**. That is why the gate (1b) is shipped alongside the
Elo repoint (1) — repointing Elo alone would have moved the attribution, not the resume count.

## Stage 1 — what shipped (all default-OFF)

### 1. `compute_elo` → Snowflake-free (`E11_24_ELO_SF_FREE=1`)

Reads `mart_game_results` from the S3 lakehouse via DuckDB (through `register_lakehouse_views`, not
a hardcoded glob — the 2026-07-20 phase-1.5 P0 lesson) and writes `team_elo_history` straight to
`baseball/lakehouse/team_elo_history/data.parquet`. No Snowflake session at all.

**Parity verified 2026-07-29 (laptop, real S3):** 26,796 games → 53,592 rows.
Every row matches the current Snowflake-produced parquet to **5e-5** (the SF MERGE stored
`%.4f`-rounded values), **0** date mismatches, **0** rows only-in-new.

⭐ The overwrite additionally **deletes 135 stale 2018 `OAK` rows** the Snowflake MERGE could never
remove: `mart_game_results` now emits `ATH` for those games after the Athletics rebrand, so game
531832 carries three rows (`ATH`, `LAA`, and a dead `OAK`). A MERGE-only writer cannot delete, so an
upstream identity remap orphans rows forever; the full-overwrite native writer is self-correcting.
The orphans are inert today (nothing joins on `OAK`), so this is a cleanup, not a behaviour change.

🚨 **Same-flip consequence (INC-31 writer-uniqueness).** Two `SELECT *` mirrors wrote that same S3
key — `export_w8a_precursors_to_s3.py` and `export_features_to_s3.py`. Both now **skip**
`team_elo_history` under the lever. Leaving either live would publish a *frozen* Snowflake snapshot
over fresh Elo on every daily run (worse than INC-31's case, which only flipped column case). The
parquet columns stay **UPPERCASE** for the same reason — the Snowflake external table addresses
`VALUE:<KEY>` case-sensitively, so a lowercase write reads ALL-NULL through Snowflake while DuckDB
stays green. `team_elo_history` is `export_features_to_s3.py`'s only remaining table, so under the
lever that whole mirror becomes a loud no-op (its full retirement).

**No Snowflake consumer is stranded.** `feature_pregame_team_features`'s DuckDB branch reads the S3
view; its Snowflake branch is `select * from lakehouse_ext.feature_pregame_team_features` (i.e. also
over S3). `team_elo_history` is not in `W8A_TABLES`, so no ext table over it goes stale. The only
Snowflake reader left is `write_serving_store.py`'s non-`--s3` fallback, and `W7B_LAKEHOUSE_S3=1` is
live on the box.

### 1b. The statcast catch-up no-op gate (`E11_24_STATCAST_CATCHUP_GATE=1`)

`catchup_ingest_statcast` becomes a conditional output (`Out(Nothing, is_required=False)`): it always
runs the ingest, then yields no output when yesterday's pitches are *still* absent, so Dagster
**SKIPS** the rest of the chain. Verified against a real Dagster job (1.13.5): the run **succeeds**
in both branches and only the downstream step is skipped — a skip is not a failure, and the sensor
retries on the next hourly `run_key`.

- **Fail-OPEN by construction.** Any lakehouse read problem resolves to "run the chain". A transient
  S3 blip must never suppress the self-heal (the "silently never runs" outage class).
- **Same predicate as the sensor** (`lh_year('stg_batter_pitches', …)` + `game_date = ?`), so the
  gate cannot skip work the sensor would immediately re-request — that would be an infinite no-op loop.
- ⚠️ The chain contains `predict_today_morning`, so this flips **after** the E11.20 W8b soak closes.

### 2. Weather capture → Snowflake-free (`E11_24_WEATHER_SF_FREE=1`)

The hourly `weather-capture` cron invokes `ingest_weather.py` **five times per fire** (T-24/6/3/1h +
observed + the intraday series), and every one opened a Snowflake session just to ask "which outdoor
parks are on the slate?". All four slate reads now route through one `_slate_games()` helper, and the
dedup read (`_already_fetched`) resolves from the S3 `weather_raw` mirror.

- `ref_venues` is a **dbt seed** with no parquet, so the image now COPYs `dbt/seeds/ref_venues.csv`
  and reads it with DuckDB. The seed is the source of truth for the Snowflake table too.
- **INC-23:** `stg_statsapi_games.game_date` is an ISO VARCHAR in the lakehouse. It is cast at the
  use site (`::timestamptz AT TIME ZONE 'UTC'`) so callers get the same *naive UTC datetime*
  Snowflake's `TIMESTAMP_NTZ` returned — rather than leaking a string to four call sites.
- **Lean-image rule:** the reader comes from `utils.lakehouse_read` (guard-tested betting_ml-free),
  never `betting_ml.utils.lakehouse_monitor`. `duckdb` added to the image.
- ✅ **RESOLVED ON THE LIVE BOX 2026-07-29 — the write leg was ALREADY `W11_RAW_WRITE_MODE=s3`.**
  So every one of the 73 measured weather wakes came from the slate/venue READ alone:
  `ingest_weather.py` called `get_snowflake_conn()` UNCONDITIONALLY, regardless of write mode.
  `E11_24_WEATHER_SF_FREE=1` is the whole fix; no compose/write-leg change is required.
- ⚠️ The half-flip hazard still stands for anyone on a box where the write leg is `snowflake`
  or `both`: the INSERT would keep opening a session until the write leg is S3-only. 🚨 **The var is `W11_RAW_WRITE_MODE`, NOT `LAKEHOUSE_RAW_WRITE_MODE`** —
  `ingest_weather.py` calls `w11_write_mode()` (`W11_WRITE_MODE_ENV = "W11_RAW_WRITE_MODE"`; the W11
  Tier-A wave has its own switch, independent of the odds one). Setting the odds var here is a
  SILENT NO-OP — the W6_ODDS_SF_FREE class of bite, caught 2026-07-29 before it shipped. `needs_snowflake =
  do_sf or not weather_sf_free()` — so a half-flip degrades to "same as today", never to a lost write.
  Safe to flip the write: `stg_weather_raw_snapshots`' DuckDB branch already reads the S3 mirror and
  its Snowflake branch is a view over `lakehouse_ext`, so freezing native `statsapi.weather_raw`
  strands no consumer.

**Verified 2026-07-29 (laptop, real S3):** 15 outdoor games for 7/29, 14 completed outdoor for 7/28,
dedup sets non-empty (9 observed, 10 at T-6), `game_datetime_utc` returned as `datetime`, not `str`.

### 3. Metering queries stop waking the warehouse they measure

`get_monitoring_connection()` (and a `warehouse=` param on both loaders) routes every
`snowflake.account_usage` read onto `SNOWFLAKE_MONITOR_WAREHOUSE` (default `MONITOR_WH`).
This is also what makes the E11.24 proof itself trustworthy: the 7/29 census had to **discard its own
UTC day** because the audit queries landed on it.

Operator DDL (once, ACCOUNTADMIN):

```sql
CREATE WAREHOUSE IF NOT EXISTS MONITOR_WH WITH WAREHOUSE_SIZE='XSMALL'
  AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
GRANT USAGE ON WAREHOUSE MONITOR_WH TO ROLE ACCOUNTADMIN;
```

### ✅ The `CREDENCE_API` caller — FOUND, and the story's framing of it is WRONG (2026-07-29)

It is **your own admin cost dashboard**: `app/backend/routers/admin.py::snowflake_credits` and
`app/backend/routers/finances.py::_snowflake_costs_by_month`, both reading
`SNOWFLAKE.ACCOUNT_USAGE.**METERING_DAILY_HISTORY**`. The first search missed them because it
grepped `warehouse_metering_history` — a different view. 88 executions since 7/17, still firing.

🚨 **But measured against RESUMES it is not a waker at all: 0 of 636 resumes over 8 days had a
`METERING_DAILY_HISTORY` query first-after-resume, and on 7/28 — the census day — `CREDENCE_API`
caused 0 resumes.** The dashboard is a **passenger**: it only ever runs while the warehouse is
already awake for pipeline work. The story's "self-inflicted wake" and the roadmap's "26 → 6 wakes"
came from the hour-bucket proxy the census itself flagged as upper-bounded, not from resume events.

⇒ **Target 3 is not a cost lever today. Do not book a saving for it.** Two things are still true
and are why it shipped anyway:

1. **It becomes a waker the moment the story succeeds.** Once targets 1/2/6 quiet the warehouse
   enough that it genuinely sleeps, "open the admin cost page" *is* the first query after a resume
   — the page that displays the Snowflake bill starts billing for the privilege. Fixing it now is
   cheap; fixing it after the fact means re-opening a solved question.
2. **The real observer effect is ours, not the app's** — 15 resumes in 8 days came from
   `DBT_RW`/`ACCOUNTADMIN` audit sessions (the cost scripts + interactive MCP sessions) reading
   `ACCOUNT_USAGE`. That is what `get_monitoring_connection()` removes, and it is why the 7/29
   census had to discard its own UTC day.

Re-run this after any change to confirm the class stays dead:

```sql
select user_name, role_name, warehouse_name, count(*) n,
       min(start_time) first_seen, max(start_time) last_seen
from snowflake.account_usage.query_history
where start_time >= dateadd(day, -7, current_timestamp())
  and query_text ilike '%ACCOUNT_USAGE%'
group by 1,2,3 order by n desc;
```

### 4. The dead derivative-odds export bridge — RETIRED (2026-07-29)

Not on the original target list; found by sweeping the monitoring/DQ family. `export_odds_raw_to_s3.py`
was still listing two tables as **live** sources while the daily `lakehouse_w3pre_flatten_op` invoked
the derivative one on every run. Both writers were long retired:

| Table | SF `max(ingestion_ts)` | Days stale | Rows in the 7-day export window |
|---|---|---|---|
| `oddsapi.derivative_odds_raw` | 2026-07-07 00:00:07 | 22 | **0** |
| `oddsapi.mlb_events_raw` | 2026-06-04 23:25:12 | 55 | **0** |

Derivative capture reads `W11_RAW_WRITE_MODE`, which the box has at `s3`, so its Snowflake writer
stopped and the `--since <7d>` export had been selecting zero rows and writing nothing. Its only
remaining effect was resuming `COMPUTE_WH` (~5 provisioning waits / 8 days). **This is the 4th instance
of the retired-writer-bridge class** (after `mlb_odds_raw` 7/05, `monthly_schedule` 7/23, and
`derivative_odds_raw`'s own stale entry in `check_data_freshness.py`).

Safety checks before removal — the class has caused one P0, so none were assumed:
- **No clobber.** Zero rows selected ⇒ no frozen-over-fresh overwrite.
- **No prune.** `prune_partitions()` is `monthly_schedule`-only and only when `--since` is absent ⇒ *not*
  the partition-deleting variant that starved probable pitchers in July.
- **No stranded consumer.** No dbt `source()` reader; a repo-wide `grep -rIn` (the INC-27 rule — the dbt
  DAG cannot see raw-SQL string consumers) found only comments, the parity script, and the writer's own
  DDL. `stg_derivative_odds`' Snowflake branch already reads `lakehouse_ext`.
- The writer's `CREATE TABLE IF NOT EXISTS` is correctly gated inside `if do_sf:` ⇒ unlike
  `team_elo_history` it was *not* additionally a no-op-DDL waker.

Shipped: `SOURCES` is now **empty** (both tables moved to `RETIRED_SOURCES` with the evidence); the
bridge call removed from `lakehouse_w3pre_flatten_op` (the `--w3pre-only` flatten stays — that is the
real work and it reads S3); both registered in `RETIRED_NATIVE_SOURCES` so a 5th instance cannot merge;
`mlb_events_raw` added to `parity_check_w3pre.py`'s `FROZEN_SOURCES` — that one matters, because with S3
correctly *ahead* of a frozen Snowflake the pre-flight reads the gap as a doubled partition and advises
`aws s3 rm` on live capture data. Host cron line 35 was already commented out (verified, not assumed),
so nothing was left calling a now-erroring `--source`.

## Stage 2 — ⛔ THERE IS NO INDEPENDENT STAGE 2. Everything left is gated on target 6 (2026-07-29)

A full sweep of every **automatically-invoked** Snowflake toucher (the ~200 files that import a SF
connector are mostly hand-run research scripts and cost nothing — the population that matters is the
`_run_script` set in `pipeline/ops/`, the host `capture.crontab` lines, the sensors, and the API)
overturns this section's original premise. **The remaining writers cannot leave Snowflake
independently, because their OUTPUT tables are read by Snowflake-executing dbt models.**

**The coupling, concretely:**

| Residual writer | Read leg | Write leg | What pins the write to Snowflake |
|---|---|---|---|
| `update_{player,team,matchup_cell}_posteriors.py` (3) | partly `--s3` already | SF stateful read-modify-write | `feature_pregame_game_features_raw.sql` reads `{{ source('betting','team_sequential_posteriors') }}`; the `eb_posteriors/*.sql` family (5 models) reads `player_sequential_posteriors` |
| The 8 signal generators | ✅ **already DuckDB/S3** | SF SCD-2 via `scd2_writer.scd2_upsert` | `feature_pregame_sub_model_signals.sql` selects `from mart_sub_model_signals` on Snowflake |

So the wake is unavoidable while the reader is a SF-native dbt model: you cannot move the write
without moving the read, and the read *is* target 6.

**🔧 CORRECTION to 4b (my own earlier claim, wrong).** I described `check_data_freshness.py` as "a pure
DuckDB repoint, the cheapest remaining item." It is not. Only `_is_game_day` reads `lakehouse_ext`;
**7 of its 8 monitored tables are `baseball_data.betting.*` Snowflake-resident tables** — and they are
precisely the outputs of the writers in the table above (`player_/team_/matchup_cell_sequential_posteriors`,
`eb_bullpen_team_posteriors`, `mart_player_archetype_posteriors`, `eb_park_factors_raw`,
`player_profiles_raw`). A monitor cannot be repointed off a store its subjects still live in. 4b is a
**dividend of target 6, not a precursor to it.**

**✅ The store decision is already made — and the code comments saying otherwise are STALE.** All 8
generators carry a variant of *"re-implementing SCD-2 accumulate in DuckDB is the W7a-wipe class the W9
design forbids."* True but obsolete: `deltalake==1.6.1` is pinned and **`scripts/utils/delta_lake.py`
already ships `merge_upsert()`** — a partition-pinned `when_matched_update_all / when_not_matched_insert_all`
MERGE (delta-rs writes Delta; DuckDB still cannot, per the E11.20a spike). History-preserving accumulate
outside Snowflake is therefore a solved problem as of the E11.20 rollout. **The blocker was never the
store — it is the dbt readers.**

⭐ **The leverage when target 6 unblocks:** `betting_ml/scripts/scd2_writer.py::scd2_upsert` is a *single
shared function* behind all 8 generators. One Delta port there migrates 8 daily writers at once — do not
migrate them one-by-one.

📉 **And the marginal prize is small anyway:** these writers run inside `statcast_catchup_job`, so stage
1's gate (1b) already removes ~5 of their ~6 daily executions. Post-1b they are a literal-zero
housekeeping item, not a credit lever.

**Conclusion: target 6 is not one target among several — it is the gate on 4, 4b and 7.** That is the
same conclusion the provisioning-wait census reached from the other direction (target 6 = 67.7% of
waits, not the 41% the first census estimated). Two independent instruments, one answer. Correct order
is therefore **6 → 4 → 4b → 7**, and nothing in 4/4b should be attempted before 6 lands.

### 🔧 CORRECTION to the heading above — "everything" was too strong. One family IS independent.

The coupling argument is sound for the **writers** (posteriors + generators). I over-generalized it to the
whole residual. A by-user attribution shows a family that has nothing to do with the dbt chain:

| User | Provisioning waits (8d) | Distinct query shapes |
|---|---|---|
| `DBT_RW` | 713 | 114 ← target 6 + the pipeline |
| **`CREDENCE_API`** | **56 (7.1%)** | **4** |
| `CCL1196` (operator Snowsight) | 24 | 8 |

**56 wakes from 4 queries, and the live API is the caller — which is also a CLAUDE.md violation
("Snowflake … never on a request path").** 42 of the 56 are one shape: the
`ACCOUNT_USAGE.METERING_DAILY_HISTORY` roll-up behind `/admin/snowflake-credits` and `/admin/finances`.

⭐ **The mechanism, nailed:** it fires **2× per hour around the clock** (7/27: hours 01–09 unbroken).
That is not a human opening a page — both endpoints carried `staleTime: 3_600_000` in
`frontend/app/admin/page.tsx`, so **an admin tab left OPEN refetched both hourly, forever.** The page
that displays the bill was 5.3% of the wakes that produce it. Fixed on both sides:
- **server:** both queries routed to `MONITOR_WH` (already shipped) ⇒ they can never wake the warehouse
  they measure;
- **client:** `staleTime` → **12h**, because the payloads are MONTH-grained *and* `account_usage`
  metering latency is ~12h+ (E11.20-COST lesson-1) ⇒ an hourly refetch was mathematically guaranteed to
  return identical numbers.

⚠️ **Both fixes are committed but NOT deployed** — the metering shape's `last_seen` is **7/29, today**, on
`COMPUTE_WH`. This family only stops on the next **Lambda + Vercel** deploy. It is the third time target 3
flipped verdict (refuted → un-refuted → mechanism identified); the story's framing was right each time.

The remaining ~24 waits are the operator's own Snowsight browsing (`POLICY_REFERENCES` 9,
`COST_INSIGHTS`/`ACCOUNT_ROOT_BUDGET`/metering 8). **Behavioural, not code** — worth knowing that opening
Snowsight cost pages wakes `COMPUTE_WH`, so audit from `MONITOR_WH` (`use warehouse MONITOR_WH` first).

### ✅ VERIFIED LIVE 2026-07-29 15:17 — the metering repoint works

`information_schema.query_history()` (near-real-time; **not** `account_usage`, which lags 45–90 min and
made the first check ambiguous) after loading the admin page post-deploy:

| Time | Warehouse | Shape |
|---|---|---|
| 15:17:33 | **MONITOR_WH** | `SUM(CREDITS_USED_COMPUTE)…` ✅ (prov 219ms — woke MONITOR_WH, exactly the intent) |
| 15:17:34 | **MONITOR_WH** | `SUM(CREDITS_USED_COMPUTE)…` ✅ |
| 15:17:29/31/34 | COMPUTE_WH | the 3 non-metering shapes (see below) — by design, not a miss |

⚠️ **Instrument note:** the first post-deploy check looked like a failure because a `dateadd(hour,-6)`
window still contained a PRE-deploy row — identified by its identical millisecond (`.827`). **For "did the
thing I just did work", use `information_schema.query_history()`; reserve `account_usage` for trends.**

### 🚩 The 3 remaining `CREDENCE_API` shapes — a TARGET-7 BLOCKER and a LATENCY defect, not a cost lever

Measured over 8 days. **Executions, not provisioning waits** — waits undercount a request-time read badly,
since only the call that happens to wake the warehouse is counted:

| Endpoint | Executions | Waits | avg ms | **max ms** |
|---|---|---|---|---|
| admin cost panel (fixed above) | 86 | 43 | 2,652 | **24,344** |
| **`/pipeline/status`** — the PUBLIC dashboard status dot | 75 | 3 | 423 | **19,015** |
| admin model freshness (`model_registry`) | 46 | 5 | 658 | **19,894** |
| admin live served version (`daily_model_predictions`) | 46 | 7 | 364 | 999 |

⇒ the residual cost is only ~14 waits, **but a request-time Snowflake read that occasionally takes 19–24
SECONDS is a serving-latency defect.** When the warehouse is asleep the dashboard dot blocks for ~19s. This
is exactly what CLAUDE.md's "Snowflake … never on a request path" rule exists to prevent.

**Why this is NOT a safe drive-by fix** (do it as a scoped story, with a parity check):
- 🧨 **E9.26b landmine:** the obvious repoint — read `daily_model_predictions` from the lakehouse — is the
  read that **reliably FAILS inside the API Lambda** while working everywhere else, and `lakehouse_query`
  **catches-and-returns `[]`**, so it would fail *silently*. The narrowest-mart rule applies: a
  single-column `DISTINCT model_version` may be fine where the 94-col join was not, but that must be
  proven **in the Lambda**, not locally.
- `/pipeline/status` is **user-facing** (the dot's green/amber/red semantics), and the serving store is
  **not** a drop-in mirror: `write_api_cache.py` / `write_serving_store.py` derive their own
  `pipeline_status` from prediction AGE, they do not copy the 9-column `betting_ml.pipeline_status` row.
  A repoint changes the derivation ⇒ needs a semantics parity assertion before it ships.

⇒ **Ordering: this belongs with target 7 (every `COMPUTE_WH` caller must be gone before the warehouse can
be dropped), not with the cost stages.** Do not attempt it during the W8b soak.

### ✅ The retired-writer-bridge family is now fully closed — verified in the wake data

Each removal is visible as a hard stop, which is the cleanest possible confirmation the bridges are dead:

| Frozen-table `DISTINCT ingestion_ts` scan | Waits (14d) | Last seen | Status |
|---|---|---|---|
| `statsapi.monthly_schedule` | 15 | 2026-07-25 | already dead |
| `oddsapi.mlb_odds_raw` | 14 | 2026-07-27 | already dead (removed 7/27) |
| `oddsapi.derivative_odds_raw` | 11 | **2026-07-29** | the one retired today — stops at next deploy |

`export_w11_raw_to_s3.py` still lists 4 sources but has **no live caller** (no non-comment reference in
`pipeline/` or the crontab), so it contributes nothing.

📉 **Total waits are already trending down hard** — 215 (7/19) → 130 → 95 → 132 → 113 → 100 → 111 → 88 →
78 → 69 (7/28), i.e. roughly **−68% since 7/19** off the E11.20 phase-2a/2b flips. ⚠️ Do not read 7/29 as
a data point; the day is partial and `account_usage` lags.

### ✅ PRE-VERIFIED FOR 8/1 — the umpire idempotency-gate premise is CONFIRMED, and more strongly than claimed

I had asserted the umpire chain is "an idempotent no-op on nearly every tick" from code reading. Measured
2026-07-29 (on `MONITOR_WH`, so the audit did not contaminate):

| Evidence | Value |
|---|---|
| Umpire-chain query executions | **~100–165 / day** (the 117 figure was only the subset that had to *wake* the warehouse) |
| Rows ever produced by the live assignment feed (`data_source='statsapi'`) | **30**, across **6 dates**, since 2026-05-18 |
| `min(loaded_at)` vs `max(loaded_at)` per game_date | **IDENTICAL on all 6 dates** ⇒ the assignment is written in **exactly ONE load stamp** and never re-written |

⇒ **essentially every umpire-chain fire after the slate's single write is a pure no-op.** A per-slate
idempotency gate is justified, and it is structurally the same gate as the shipped 1b. **Gate key:** "is
there an assignment row for this slate whose `loaded_at` is newer than the last rebuild?" — because the
feed writes once, that fires exactly once per slate instead of ~100×.

⚠️ **Design caution for whoever builds it:** the gate must key on *assignment newer than last rebuild*,
not on "already rebuilt today" — and it must not entrench the lateness documented below.

### 🚩 SEPARATE FINDING (not E11.24 — flagging, not chasing): the HP-umpire assignment lands AFTER first pitch for ~half the slate

Found while verifying the above; it is a **serving-quality** issue, not a cost one, and it deserves its
own story rather than a drive-by fix.

- The assignment feed **only started working on 2026-07-27** (before that: 1 row on 4 scattered dates;
  7/27 and 7/28 have 11 and 15 rows = exactly their game counts).
- It lands at **23:16 UTC (7/27)** and **23:09 UTC (7/28)** — and **6 of 11 (55%) and 6 of 15 (40%) games
  had ALREADY STARTED** by then.

That is precisely the window story 30.5 exists to beat ("ingest the HP umpire on the afternoon lineup path
so it is available BEFORE the re-score, the actionable bet"). ⚠️ **Do not read the 1.000 historical
coverage as health:** 30 assignment rows cannot cover ~150 games — past-date coverage comes from the
`umpscorecards` **post-game tendency** feed backfilling (26,657 rows), not from the pregame assignment. The
two feeds share a table and only `data_source` distinguishes them, so a naive coverage check on this block
looks perfect while the pregame path is missing ~half the slate.
📉 Note this makes the cost case *stronger*, not weaker: the chain re-runs ~100×/day to serve a feed that
writes once, late.

### ✅ CORRECTION (E2.14 Phase 1, 2026-07-31) — this finding was a METHODOLOGY ARTIFACT, not a real gap

The claim above was built from `min(loaded_at)`/`max(loaded_at)` **read from Snowflake**, where
`ingest_umpires.py` DELETE+INSERTs every game_pk it currently sees on EVERY call — so the LAST run of the
day (the ~23:xx UTC late op) silently **overwrites `loaded_at` for every game_pk it re-touches**, erasing
the evidence of when the assignment first actually appeared. Re-measured off the **append-only S3 raw
mirror** (`lakehouse_raw/umpire_game_log/`, never overwritten — each `lineup_monitor` tick appends a new
snapshot row) joined against `stg_statsapi_games.game_date` for the true first-pitch instant:

**207 games, 2026-07-17→07-31: 100% ever got a live (`data_source='statsapi'`) assignment; 206/207 (99.5%)
had it BEFORE first pitch, average lead 150–265 min/day, worst case (excluding one outlier) 82 min lead.**
The single miss was a split-doubleheader game 1 with an unusually early first pitch (17:35 UTC) — its
assignment landed ~3h05m late, a 0.5%-of-sample edge case, not a systemic pattern.

⇒ **the live feed reliably beats first pitch; the served umpire feature is NOT stale-at-serve.** E2.14
closed on this measurement (null recorded) — no Opus follow-up spawned. Full methodology + numbers in
[[project_e2_14_umpire_timeliness]] (session memory). Lesson for future timeliness audits on this table:
**a DELETE+INSERT-then-overwrite write pattern destroys "when did it first arrive" history — read the
append-only raw mirror, never the deduped/overwritten table, when the question is about ARRIVAL time.**

## Stages 3–4 — SOAK-BLOCKED until the E11.20 W8b soak exits (2026-07-31)

The E11.20 guardrail is **one serving-flip per soak**, and the 7/30 no-false-abstain attribution must
stay clean. Nothing in stage 1 touches the predict/serving path.

**5. Remove the dead `predict_today` Snowflake freshness branch.** `W8B_FRESHNESS_S3` flipped
2026-07-29, so the Snowflake leg is dead weight — and it is the leg that carried the 7-hour
`TIMESTAMP_LTZ`→`::timestamp_ntz` bug that false-abstained every slate 7/24→7/29. Removal must land
**with a branch-parity assertion**: score the SAME slate through both branches and assert they agree,
because a single-branch unit test structurally cannot catch a SQL timezone bug. This moves **zero**
wakes (the gate is a read inside `predict_today`, not a waker) — it is a correctness/decommission
item, so do not expect it in the credit series.

**6. The intraday EB/lineup dbt rebuild chain — 41%, the single biggest remaining waker.** On the
serving/predict path, highest regression risk, and the place a false-abstain would recur. Do it last,
alone, with the full runtime gate: repoint → real box run → measure resumes before/after.

**7. Drop the ext tables / `lakehouse_ext` mirrors, then suspend/drop the warehouse.** Before deleting
**any** S3 layout or Snowflake object: `grep -rIn` the repo for the **PATH string** (the prefix/glob),
not just the table name. A Snowflake `access_history` zero-reader check **cannot see DuckDB/S3 path
readers** — that is exactly how phase-1.5 served a zero-prediction slate.

## Measuring each cutover (do not assume)

Before/after, on the **laptop**, per the E11.20-COST methodology — resumes, not elapsed-seconds:

⚠️ The column is **`TIMESTAMP`** (not `timestamp_start`), and you must filter
`event_state = 'STARTED'` — `RESUME_WAREHOUSE` and `RESUME_CLUSTER` are separate event rows, so an
unfiltered count roughly doubles. Verified against the live view 2026-07-29.

```sql
select to_char(convert_timezone('UTC', timestamp)::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
       count(*) as resumes
from snowflake.account_usage.warehouse_events_history
where event_name = 'RESUME_WAREHOUSE' and event_state = 'STARTED'
  and warehouse_name = 'COMPUTE_WH'
  and timestamp >= dateadd(day, -14, current_timestamp())
group by 1 order by 1;
```

Attribution (which family owns each resume) joins each resume to the first query at/after it:
`qualify row_number() over (partition by resume_ts order by start_time) = 1`.
**Run it on `MONITOR_WH`** (`use warehouse MONITOR_WH;`) or the audit becomes a line in its own
results — measured below at 15 resumes in 8 days.

### 🔧🔧 METHODOLOGY CORRECTION — use `queued_provisioning_time`, NOT first-query-after-resume

**"First query at/after the resume event" systematically misattributes**, and it is the method both
the E11.20 census and this doc's first draft used. The query that *causes* a resume starts
**before** the resume event is recorded, so `start_time >= resume_ts` filters the true cause out and
credits whatever ran next. Applied here it ranked
`GRANT SELECT … TO ROLE CREDENCE_API_RO` as the **#1 residual waker at 111 resumes** — a
metadata-only statement that does not need a warehouse at all, and which does not appear anywhere in
the provisioning data. It also left a 53% unclassifiable "other" bucket.

⭐ **The right instrument is `query_history.queued_provisioning_time > 0`** — a query only queues on
provisioning if it *waited for the warehouse to start*, so it names the waker directly. It leaves
**3.7%** unclassified instead of 53%.

```sql
select left(regexp_replace(query_text,'\s+',' '),95) as waker_query,
       count(*) as provisioning_waits,
       round(avg(queued_provisioning_time)/1000,1) as avg_wait_s
from snowflake.account_usage.query_history
where warehouse_name = 'COMPUTE_WH'
  and start_time >= dateadd(day, -8, current_timestamp())
  and queued_provisioning_time > 0
group by 1 order by provisioning_waits desc;
```

### Measured baseline — 8 days to 2026-07-29, 802 provisioning waits

| Waker | Waits | Share | Status |
|---|---|---|---|
| **6. intraday EB/lineup + feature dbt chain** | 543 | **67.7%** | soak-blocked |
| 2. weather slate/venue | 74 | 9.2% | ✅ shipped |
| `pipeline_run_log` INSERT (lineup monitor audit) | 62 | 7.7% | see caveat |
| 3. admin/finances cost dashboard | 43 | 5.4% | ✅ shipped |
| 1. `compute_elo` games read | 34 | 4.2% | ✅ shipped |
| still unclassified | 30 | 3.7% | — |
| audit/metering (our own sessions) | 16 | 2.0% | ✅ shipped |

**🚨 This REVERSES the "target 3 is refuted" finding above.** The cost dashboard *does* wake the
warehouse — **43 provisioning waits in 8 days (~5/day)**. The "0 of 636 resumes" reading was an
artifact of the broken heuristic, not evidence. Target 3 as the story specified it was correct, and
shipping it was the right call for the stated reason and not only the forward-looking one.

**Target 6 is 68%, not the census's 41% — it is not one target among several, it is the story.**
Everything else combined is under a third of it.

⚠️ **`pipeline_run_log` (62) is NOT the free win it looks like.** `lineup_monitor.py` already skips
that INSERT on a *quiet* tick (the phase-2a guard); the 62 are *triggering* ticks, and the
`lineup_monitor_job` they fire does Snowflake work moments later — so removing the INSERT most
likely **shifts** the resume to the dbt step rather than removing it. Do not book it as a saving
without measuring after target 6 lands.

### Sub-family decomposition (what to fix, in order)

| Sub-family | Waits | UTC hours | Owner |
|---|---|---|---|
| **umpire chain** (`stg_statsapi_umpire_game_log` 52 + `feature_pregame_umpire_features` 60) | **116** | **13–23** | lineup_monitor tick |
| `stg_statsapi_lineups_wide` CTAS | 78 | slate hours | lineup_monitor tick |
| `stg_statsapi_probable_pitchers` CTAS | 65 | slate hours | lineup_monitor tick |
| `int_bullpen_ali_by_season` | 39 | **08–13** | statcast catch-up |
| `compute_elo` | 34 | **08–13** | statcast catch-up |
| `feature_pregame_lineup_features` / `_starter_features` | 55 | slate hours | lineup_monitor tick |

Two things fall straight out of the hour distribution:

1. **The shipped catch-up gate (1b) is worth ~2× what target 1 alone was.** `compute_elo` (34) and
   `int_bullpen_ali` (39) are **both** confined to 08:00–13:00 UTC — exactly the catch-up re-fire
   window — confirming from data what the code review predicted. The gate takes **~73 waits (9%)**,
   not 34.
2. ⭐ **The umpire chain is the largest single sub-family in target 6 (116, ~14.5/day, hours 13–23)
   and it is the SAME no-op-re-fire pattern.** `lineup_ingest_umpires` is the *first* op of
   `lineup_monitor_job`, which ticks every ~10 min through the slate — but the HP-umpire assignment
   is posted once per afternoon and does not change. So the ingest + `stg_statsapi_umpire_game_log`
   + `feature_pregame_umpire_features` rebuild are idempotent no-ops on nearly every tick. **A
   per-slate idempotency gate there is the highest-value item in target 6, and it is structurally
   the same fix as 1b** — do it first when the soak lifts.

⛔ **Do not assume wake↓ ⇒ credit↓** (the E11.20 lesson). The win is legible in RESUMES; the credit
line only moves once the warehouse actually stays suspended for long stretches.
🚨 **Clean-baseline caveat:** use **≤7/28** as the pre-flip reference. 7/29 is contaminated by the
census's own audit queries — which is what stage 1's `MONITOR_WH` change permanently fixes.

## TARGET 6 — the intraday EB/lineup + feature dbt chain (2026-07-31, code-complete, UNFLIPPED)

### Fresh census first — the attribution MOVED, and it changes what is worth doing

8 days to 2026-07-31, `queued_provisioning_time > 0`, run on `MONITOR_WH`. **662 total waits, down
from 802** on the previous window (−17%) with no target-6 work done — the E11.20 phase-2a/2b flips
are still landing.

| Sub-family | Waits (8d) | Last seen | Verdict |
|---|---|---|---|
| **umpire chain** (`stg_statsapi_umpire_game_log` 57 + `feature_pregame_umpire_features` 54) | **111 (16.8%)** | **7/31** | ⬅ the target |
| `pipeline_run_log` INSERT | 47 | 7/31 | live (see the standing caveat) |
| `player_sequential_posteriors` reads | 48 | 7/31 | live |
| `int_bullpen_ali_by_season` | 38 | 7/31 | 1b flipped 19:45 UTC 7/31 — verify 8/1 |
| `feature_pregame_lineup_features` + `_starter_features` | 47 | 7/31 | live |
| `stg_statsapi_lineups_wide` + `stg_statsapi_probable_pitchers` CTAS | 69 | **7/25** | ✅ **already dead** |
| weather slate (lever 2) / metering (lever 3) / `compute_elo` (lever 1) | 45 / 27 / 29 | **7/29** | ✅ stage 1 confirmed live |

Two things fall out that were not true when this story was written:

1. ⭐ **The `lineups_wide` / `probable_pitchers` CTAS sub-family — 69 waits, the census's #2 and #3
   items — went to ZERO after 7/25.** `TICK_SF_FREE` took them. A large slice of "target 6" was
   already won by phase-2a; only the umpire chain and the lineup/starter feature CTAS remain.
2. 🚨 **Target 6's own #2 item, the SCD-2 signal writers, is measurably NOT WORTH A SERVING FLIP.**
   Classified by query shape over the same 662 waits:

   | Family | Waits | Share |
   |---|---|---|
   | scd2 signal writers (`mart_sub_model_signals` / `tmp_scd2_incoming`) | **5** | **0.8%** |
   | `feature_pregame_sub_model_signals` consumer | 7 | 1.1% |

   The whole "port `scd2_upsert` once + repoint the dbt readers" item is worth **~12 waits / 8 days
   (1.8%)** while requiring a cutover on `feature_pregame_game_features_raw` and the
   `eb_posteriors/*` family — the highest-regression-risk surface in the program. This is exactly
   what the stage-2 section predicted ("post-1b they are a literal-zero housekeeping item, not a
   credit lever"); the measurement now confirms it. **Sequenced AFTER the umpire-gate soak, and
   only after a re-measure post-1b.** See "What was deliberately NOT done" below.

### 1. The per-slate umpire idempotency gate — `E11_24_UMPIRE_REBUILD_GATE` (default OFF)

`betting_ml/monitoring/umpire_rebuild_gate.py` + a selector change in
`pipeline/ops/sensor_ops.py::lineup_dbt_feature_rebuild`. On the Snowflake target both umpire
models are literally `select * from lakehouse_ext.<model>`, so every intraday tick re-copied an
unchanged external table.

**Gate key = "an assignment newer than the last rebuild", NOT "already rebuilt today."** The
watermark is `MAX(loaded_at)` over `lakehouse_raw/umpire_game_log/` for the slate, compared against
a small S3 marker (`baseball/lakehouse_state/umpire_rebuild_watermark.json`). That choice is what
keeps the gate from entrenching the separate late-assignment defect: the ~23:10 UTC write bumps the
watermark, so it still triggers exactly one rebuild. A date-keyed gate would have latched in the
afternoon and suppressed precisely the rebuild that matters.

- **Fail-OPEN everywhere** — connect error, read error, missing marker, and "no umpire row yet" all
  resolve to "rebuild". This block has an incident history (INC-31, F2) of silently zeroing.
- **The marker advances only after the dbt run succeeds, and only to the watermark read BEFORE it
  ran**, so an assignment landing mid-rebuild is not swallowed.
- **Safety floor:** only the intraday rebuild is gated. The once-daily `dbt_umpire_feature_rebuild`
  stays ungated, so a wedged marker can cost at most one slate's intraday freshness.
- `ingest_umpires.py` still runs every tick (S3 write, no Snowflake) — the gate removes the dbt
  CTAS only, leaving story 30.5's lateness fix independent.
- 16 tests in `betting_ml/tests/test_umpire_rebuild_gate.py`, weighted toward the must-not-skip
  paths.

#### 🚨 PRE-FLIP RE-MEASUREMENT (2026-08-02, quiet window) — the premise is FALSE, the saving is ~0

Before flipping, the gate's own stated premise was re-checked against live S3. It does not hold.

**Premise as written:** "the assignment is written once per slate and never re-written —
`min(loaded_at) == max(loaded_at)` on all 6 dates the feed had produced."
**Measured** over `lakehouse_raw/umpire_game_log/`, DISTINCT same-day `loaded_at` instants per
slate, 13 slates 2026-07-20..08-01:

```
10, 7, 20, 8, 7, 8, 11, 7, 7, 9, 7, 9, 10      median 8, range 7-20
```

On 2026-07-31 those instants are `16:14, 19:14, 19:44, 20:14, 20:46, 21:16, 22:16, 22:46, 23:16`
UTC — one per tick from the moment MLB posts the assignment to the end of the slate.

**MECHANISM (established, not inferred).** `lineup_ingest_umpires` runs `ingest_umpires.py --date
today --skip-if-exists` one op earlier in the same job, and that guard exists precisely to make the
repeated fires no-ops. It is gated:

```python
if args.skip_if_exists and not args.dry_run and do_sf:   # ← SF-leg-only
```

The box runs `W11_RAW_WRITE_MODE=s3` ⇒ `lakehouse_write_legs('s3')` ⇒ `do_sf=False` ⇒ **the guard
never executes.** Every post-assignment tick re-fetches the Stats API and re-writes the S3 mirror,
re-stamping `loaded_at` on content that did not change. (Two side-notes: the guard is also an
ANY-ROW check, so even when live it would skip once the FIRST game's umpire lands and swallow
later-announced ones; and it costs a Snowflake connect per tick purely to decide — itself a
`COMPUTE_WH` waker 6a does not remove.)

**⇒ WHAT 6a IS NOW EXPECTED TO DO.** Correctness is unaffected. The saving is a THIRD, not a tenth.

Sized by counting **INVOCATIONS, not executions** — the lever-1b lesson from this same story
(executions inflate with per-model/metadata queries, and an outage fakes every volume metric). A
umpire-rebuild FIRE = a distinct 5-minute window in the 14–23 UTC band containing an umpire CTAS.

| UTC day | 07-22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 08-01 | median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rebuild **fires** (5-min windows) | 31 | 12 | 11 | 11 | 16 | 13 | 7 | 9 | 11 | 16 | 19 | **12** |
| watermark **bumps** (same-day instants) | 20 | 8 | 7 | 8 | 11 | 7 | 7 | 9 | 7 | 9 | 10 | **8** |

Median ratio **≈ 1.5** ⇒ roughly **one fire in three is not preceded by a fresh watermark**, and
that is exactly what the gate removes. Against the clean pre-flip band references — **11 waits
(7/28) and 13 waits (7/30)** — expect **~7–9 waits post-flip, a ~30–35% cut in the band**.

⚠️ **Read that honestly in BOTH directions on 8/3.** A ~30% cut is the PREDICTION, so it neither
vindicates the "written once per slate" premise (which would have implied ~90%) nor indicates a
broken flip. A cut materially larger than ~40% means the model of the writer above is wrong and
should be re-derived, not celebrated.

**⭐ WHY FLIPPING IS NEVERTHELESS SAFE (the bound worth keeping).** `refresh_w1_external_tables.py
--w11b` is an early-return path called only by the nightly W11b mirror op; the W11B tables are NOT
in the default no-arg daily refresh. So across a slate `lakehouse_ext.stg_statsapi_umpire_game_log`
and `lakehouse_ext.feature_pregame_umpire_features` are **frozen**, and the CTAS the gate skips is
byte-identical *by construction* — independent of what the raw watermark did. The blast radius is
the Snowflake copy only; the SERVED umpire parquet comes from the nightly `--w11b`.

**PRECURSOR that would actually unlock this gate (a SEPARATE story, deliberately not bundled):**
make `--skip-if-exists` work on the S3 leg AND per-game rather than any-row. Until then 6a is a
correct, safe, inert flag. → **built as FU-3, see below; it unlocks ~28%, not "the rest".**

#### FU-3 / 6a-PRE (2026-08-02) — the precursor, and the MEASURED CEILING it runs into

`scripts/ingest_umpires.py --skip-if-exists` is now **per-game AND content-aware**: it reads the
latest `data_source='statsapi'` row per `game_pk` from the append-only S3 mirror (via `lh_raw()` +
DuckDB) and writes only the games whose `(umpire_id, umpire_name)` is absent or **changed**.
Content-awareness is free — the Stats API returns the whole slate in one request either way — and
it buys a mid-slate **reassignment** still being ingested, which a per-game *existence* check would
silently pin stale for the rest of the day (the daily early/late ops run in the MORNING, hours
before assignments post, so nothing else would correct it in time).

⚠️ **THE PRE-REGISTERED TARGET ("instants fall to ~1–2") IS ARITHMETICALLY UNREACHABLE, AND
REACHING IT WOULD REQUIRE THE REGRESSION THE STORY FORBIDS.** Replaying all 14 slates
(07-20..08-02) of the real mirror through this exact filter — for each recorded write instant, was
the fetched `{game_pk: umpire}` map different from the accumulated state?

| slate | 07-20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 08-01 | 02 | **total** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| instants **now** | 10 | 7 | 20 | 8 | 7 | 8 | 11 | 7 | 7 | 9 | 7 | 9 | 10 | 6 | **126** |
| instants **with FU-3** | 9 | 5 | 11 | 4 | 5 | 6 | 8 | 5 | 7 | 8 | 4 | 8 | 5 | 6 | **91** |

**−28% of write-instants; median 8 → 6.** Every one of the 91 surviving writes carries at least one
**genuinely new game assignment**, so the residual is **IRREDUCIBLE**: MLB announces HP umpires in
waves across the afternoon (07-31: 1→5→7→9→10→11→13→15 games over seven hours), and each wave is a
real content change that must be written. Two slates (07-28, 08-02) cut to **ZERO** because every
tick on them brought a new game. ⇒ **the only way to drive instants toward ~1–2 is to swallow a
late-announced assignment — i.e. the any-row form this change exists to remove.** A one-sided
"fewer instants is better" reading of this lever is therefore wrong; the correct floor is *the
number of announcement waves*, and FU-3 attains it exactly.

⇒ **RE-SIZED EXPECTATION FOR 6a.** Watermark bumps drop from a median of 8 to ~6 (−28%), so 6a's
skip rate rises but nothing like to the "written once per slate" premise. Post-FU-2 the fires-vs-
bumps ratio should be re-derived on fresh data rather than re-using the ≈1.5 above.

**On the "per-tick Snowflake connect" this was also meant to remove:** ⚠️ measured, it was **not a
live waker**. Under `W11_RAW_WRITE_MODE=s3` the guard's `and do_sf` conjunct short-circuited before
the connect, so `main()` opened **no** Snowflake connection on any tick — the same conjunct that
disabled the guard also suppressed its cost. Deleting the connect is therefore **prophylactic**: it
removes a **latent** waker that would have fired the moment the write mode went back to
`snowflake`/`both`, and the honest wake-census credit for it today is **zero**. (`import
snowflake.connector`, dead at module scope, was removed in the same change.)

#### Monitor policy — 6a does NOT decouple umpire from the nightly `--w11b`, so nothing changes

Checked explicitly (the INC-37-W11GUARD flag on this story). `check_w11_tail_coverage.py` reads
`feature_pregame_umpire_features` through `register_lakehouse_views` — i.e. **the S3 parquet built
by the nightly `--w11b`**, not the Snowflake CTAS copy that 6a gates. And
`lineup_intraday_s3_feature_rebuild`'s step list contains `--game-spine-only`, `--eb-batter-only`,
`--w8b-only` and `refresh_w1_external_tables --w8b` — **no `--w11b`**, so nothing rebuilds the
umpire parquet intraday either. ⇒ umpire's build cadence is unchanged by 6a, it stays
**BUILD_LAGGED**, and `SAME_DAY_BLOCKS` / `BUILD_LAGGED_BLOCKS` in
`betting_ml/monitoring/w11_tail_coverage.py` need **no edit** in this change.

#### Pre-flip reference state (2026-08-02 ~05:0x UTC, slate 2026-08-01 complete)

All read SF-free from the laptop except where noted.

| check | 2026-07-31 | 2026-08-01 |
|---|---|---|
| W11 tail umpire | **15/15 OK** ⬅ the prior-slate comparison for 6a | 5/15 PARTIAL (build-lagged, expected) |
| W11 tail weather / public_betting | 14/15 OK / 15/15 OK | 14/15 OK / 15/15 OK |
| intraday_fallback | — | morning + post_lineup **100% feature_store, 0 fallback** |
| served integrity, morning | cov 0.80, total_runs spread 0.473 **FLAT** | cov 0.89, spread 0.351 **FLAT** |
| served integrity, post_lineup | cov 0.94, spread 0.473 **FLAT** | cov 0.99, spread 0.79 OK |
| bovada_ml coverage | 15/15 | 15/15 |
| post_lineup `h2h_edge is not null` | 13/15 | 13/15 |
| morning `h2h_edge is not null` | 0/15 | 3/15 |
| `abstain_reason` post_lineup | 13× `edge_to_sigma=0.000<0.25`, 2× `ci_width_unavailable` | identical |

⚠️ **Two traps in reading that table post-flip.** (1) `sigma_tier='abstain'` is **100% on every tier
every day** (the `best_alpha=0` regime) — it is saturated and therefore useless as a "new abstain"
signal; use `h2h_edge is not null`, `feature_coverage_score` and the `abstain_reason` MIX instead.
(2) The `total_runs` FLAT finding is **CHRONIC and pre-existing** (both tiers on 7/31, morning on
8/1) — it must not be attributed to 6a. Also: running
`check_served_prediction_integrity.py --date <a past date>` falsely reports "N rows dated AFTER
<date>" because the DATE check compares against today's baseball date; that check is only
meaningful on the current slate.

⚠️ **Self-contamination recorded:** `check_served_prediction_integrity.py` connects on
`COMPUTE_WH` (`SNOWFLAKE_WAREHOUSE` default), so the two pre-flip runs above **resumed COMPUTE_WH
twice at ~05:05 UTC on 2026-08-02**. Outside the 14–23 UTC measurement band, so 6a's read is
unaffected — but do not count those as pipeline wakes.

### 2. INC-25 durable fix — `E11_24_BULLPEN_S3_READ` (default OFF)

⚠️ **CORRECTION to this story's own specification.** The story said "have the bullpen branch read
`lakehouse_ext.eb_bullpen_posteriors` DIRECTLY". **That would not have broken the cycle.** The
daily order is

```
lk9 (--w8a → S3 EB parquet) → lk10 (--w8b aggregator, mirrors team_sequential_posteriors)
  → s5c → s5d (refresh_w1_external_tables) → … → dbt_build_bullpen_posteriors_op
  → update_player/team/matchup_posteriors_op
```

The **external table is only refreshed at s5d, which is also after lk10** — so repointing to it
swaps one post-lk10 dependency for another. The only artifact fresh at lk9 is the **S3 parquet
itself**, so `update_team_posteriors._BULLPEN_S3_SQL` reads it through DuckDB
(`register_lakehouse_views`, never a hardcoded glob — the 2026-07-20 phase-1.5 P0). That is also
strictly better for E11.24: it removes a Snowflake read that dragged a full `stg_batter_pitches`
scan with it.

⛔ **Deliberately NOT fail-open.** Unlike a monitoring gate this feeds a non-idempotent,
strictly-ordered chain: silently returning `[]` would make `run_catchup_loop` read the date as
"source not ready" and stall the metric. A read error raises; an honest empty still stalls, exactly
as the Snowflake path does.

⏭️ **Follow-on (a separate flip):** once this soaks, `update_team_posteriors_op` can move BEFORE
lk10, and E9.53's intraday `team_sequential_posteriors` re-mirror becomes unnecessary.

### 3. The sibling posterior stores — AUDITED, and BOTH ARE DIRTY

E9.53 flagged `player_sequential_posteriors` and `matchup_cell_sequential_posteriors` as
"guarded but unaudited". Audited 2026-07-31:

| Store | Seasons 2021-25 | Season 2026 | Consumed columns |
|---|---|---|---|
| `player_sequential_posteriors` | **exactly 1.0000**, 0 violations | **1,010 / 1,513 chains inflated**, median 1.147, max 4.0 | `posterior_mu` only |
| `matchup_cell_sequential_posteriors` | n/a (2026 only) | **25 / 25 cells inflated**, avg 1.158 | `posterior_mu`, **`posterior_sigma`, `n_pa_cumulative`** |

🔧 **A DIFFERENT MECHANISM FROM E9.53 — not a backfill.** Read off the SCD-2 history, player
679358 / `xwoba_against` / game 823692 was written **three times on 2026-06-23** (10:21, 12:13,
13:52 UTC), each re-absorbing the same 3 PA: `n_cumulative` 182 → 185 → 188. That is the **hourly
`statcast_catchup_job` re-fire** (this story's own lever-1b finding) hitting writers that then ran
`--date yesterday` unconditionally. **Duplicates stop at 2026-07-19**, when the `--catchup` frontier
landed — so the ongoing defect is already closed and only the corrupted 2026 state remains.

⭐ **The team store's identity does not transfer, so the guards use a different one.** `win_prob`
absorbs one observation per team per game, so `n_cumulative == games played` works there; a
player's observations are PA counts. What *is* exact — and needs no external truth table — is a
**conservation identity**:

```
n_cumulative (at is_current)  ==  Σ n_obs over DISTINCT (chain, game_pk)
```

Validated two-sided before shipping: **exactly 1.0000 on all five clean seasons, up to 4.0 on the
dirty one.** Shipped as `dbt/tests/assert_{player,matchup_cell}_sequential_no_double_apply.sql`,
with both tables added to `sources.yml`. Executed live: the repaired **team guard PASSES** while the
two new ones fail 1,006 and 25 rows — a clean three-way control.

📉 **Scope the consumed quantity before escalating (the E9.53 lesson), and it splits the two:**
- **player** — both consumers (`eb_batter_posteriors_raw`, `eb_starter_posteriors`) select
  `sp.posterior_mu` ONLY. The corrupted second moment is **not served**. The mean *does* drift here
  (unlike team), but slightly: median |Δ| **0.0022** xwoba, max 0.0436, on a ~0.31 scale.
- **matchup — the argument does NOT hold.** `generate_matchup_signals._load_seq_cell_posteriors`
  selects `posterior_sigma` and `n_pa_cumulative` and assigns
  `active_cell_sigmas[bi, pi] = posterior_sigma`. Since σ ∝ 1/√n, a 1.158× inflation makes the
  served cell sigma **~7.1% too small** — a serving-path calibration defect, not just a store one.
  ⇒ this one warrants the repair, not merely a note.

### ✅ BOTH STORES REPAIRED AND VERIFIED (2026-07-31)

| Store | Rows 2026 (before → after) | versions/key-game | Conservation identity |
|---|---|---|---|
| `player_sequential_posteriors` | 52,300 → **47,160** | 1.1784 → **1.0000** | 0 violations, max ratio **1.0000 on all 6 seasons** |
| `matchup_cell_sequential_posteriors` | 3,556 → **3,095** | 1.2022 → **1.0000** | 0 violations, max ratio **1.0000** |

Frontier intact (`max(game_date) = 2026-07-30`, i.e. yesterday's completed slate). All three dbt
guards now PASS. The served matchup `posterior_sigma` rose to **0.00007387**; the pre-repair value
was only captured to 6 dp (`0.00007`), so this is **consistent with** the predicted ~7.1% widening
rather than a precise confirmation of it.

### 🚨 A SECOND DEFECT, CREATED BY THE FIRST FIX — a `--reset` that DELETES before validating its source

The first live `--reset` **deleted 52,300 rows and then RAISED**, leaving the store EMPTY: the
backfill's PA substrate `mart_pitch_play_event` no longer exists in Snowflake (dropped by E11.20
phase-1.5) and the handed-off command omitted `--s3`. All three writers called
`guard_or_reset_backfill` — which DELETEs — *before* reading their game-date source.

⭐ **A guard that makes a repair safe against one failure mode and unsafe against another has just
MOVED the failure** — and here to a strictly worse place: a silently inflated store degrades
calibration, an empty one breaks the consumers' join outright.

**CURE (shipped):** all three writers are now **LOAD-THEN-DELETE**, with
`catchup.require_source_before_reset()` refusing the reset on a zero-date source and naming both
missing preconditions in the error text. Pinned by `betting_ml/tests/test_backfill_reset_ordering.py`
(8 tests, asserting the game-date read precedes the guard in each writer).

⚠️ **Two preconditions the operator command MUST carry** for the player and matchup backfills —
either one missing is a hard failure, and the second fails *silently* into the deleted legacy path:
- **`--s3`** — the SF `mart_pitch_*` family is gone (phase-1.5). The daily op already passes it via
  `_w7a_s3_args()`; a hand-run backfill does not inherit that.
- **`LAKEHOUSE_DELTA_W1=cutover`** — `lakehouse_view_sql` routes to `delta_scan` only in cutover
  mode; unset, it falls back to the `lakehouse/<table>/**/*.parquet` glob that phase-1.5 DELETED.

```
AWS_DEFAULT_REGION=us-east-2 LAKEHOUSE_DELTA_W1=cutover \
uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py \
  --backfill --season <yr> --reset --s3
```

`update_team_posteriors` is unaffected — it reads `mart_game_results`, not the pitch mart, and has
no `--s3` flag.

### What was deliberately NOT done, and why

- **The `scd2_upsert` Delta port + dbt-reader repoint (story item 2) and the remaining intraday
  repoints (item 5).** Measured at 1.8% of waits (above) against a cutover on
  `feature_pregame_game_features_raw` + `eb_posteriors/*`. This repo's guardrail is **one
  serving-flip per soak**, and the umpire gate + bullpen read already occupy this one. Re-measure
  after 1b's 8/1 window before spending a flip here.
- **No ext table dropped, no warehouse suspended** — that is target 7, explicitly out of scope.

### Expected wake response and how to verify it

Baseline to compare against (this doc's methodology: **resumes AND active-minutes**, never
sum-of-elapsed; ⛔ do not read the credit line for a single lever — `account_usage` lags ≥12h):

| UTC day | Resumes | Active min | Waits |
|---|---|---|---|
| 7/28 (clean pre-stage-1 reference) | 44 | 167 | 58 |
| 7/30 (post stage-1 levers 1/2/3) | 43 | 141 | 60 |
| 7/31 (partial) | 28 | 135 | 48 |

Because 6a removes a **bursty** sub-family rather than an evenly-spread poller, expect it in **waits
and resumes** — the mirror image of the weather lever, which moved active-minutes and left resumes
flat.

#### 🔧 ATTRIBUTION CORRECTION — 6a is worth ~11.5 waits/day, NOT the 14 the 111-wait headline implies

The umpire chain's 111 waits are **not all 6a's to claim.** Broken out by UTC hour over the same
8 days:

| Hours | Umpire waits | Driver | Gated by |
|---|---|---|---|
| **14-23** | **92 (~11.5/day)** | `lineup_dbt_feature_rebuild` — the 10-min lineup-monitor tick | **6a** |
| 08-13 | 17 | the daily job + the statcast catch-up chain's own umpire rebuild | **1b** (and deliberately NOT 6a) |
| 03 | 2 | the monitor's overnight tail (the tick self-guards 14:00-03:00 UTC) | 6a |

The 08-13 slice is exactly the window `int_bullpen_ali_by_season` occupies (40 waits, hours 08-13),
because the catch-up chain contains the umpire rebuild too. So **1b will reduce umpire-chain waits
as well** — and crediting all 111 to 6a would double-count 1b's win. This is the same
"classify a waker by what it READS, not the job it belongs to" hygiene the 7/29 census needed,
applied one level finer.

⭐ **The two levers ARE independently attributable even if both are live**, because they act in
disjoint hour bands. **Measure per band, not per day:**

```sql
select convert_timezone('UTC', start_time)::date as d,
       case when hour(convert_timezone('UTC', start_time)) between 8 and 13 then '08-13 (1b)'
            else '14-23 (6a)' end as band,
       count(*) as waits
from snowflake.account_usage.query_history
where warehouse_name = 'COMPUTE_WH' and queued_provisioning_time > 0
  and start_time >= dateadd(day, -6, current_timestamp())
group by 1, 2 order by 1, 2;
```

⚠️ **2026-07-31 is UNUSABLE as a baseline** — it carries this session's `dbtf test` runs *and* the
two `--reset` backfills (5,815 executions vs a typical ~4,000, and the queries ran as `DBT_RW`, the
same user as the pipeline, so they cannot be filtered out by user). Use **7/30** as the pre-flip
reference and **8/2+** as the post-flip one.

### ✅ RUNTIME PRE-VERIFICATION FROM THE LAPTOP (2026-07-31) — both read paths proven on real S3

CI mocks all IO, so both levers were exercised against live S3/Snowflake before any flip:

- **6b bullpen parity — EXACT.** `fetch_bullpen_obs_s3` vs the Snowflake `_BULLPEN_SQL` on two
  completed slates: **7/30 → 20 vs 20 rows, 7/28 → 30 vs 30**, zero rows only-in-S3, zero
  only-in-SF, **zero value differences** (`obs_mean` to 9 dp, `n_obs` exact).
- **6a gate state machine — all three branches correct on the live watermark** (today's assignment
  read as `2026-07-31 21:16:15 UTC`): no marker ⇒ REBUILD (fail-open); marker == watermark ⇒ SKIP;
  marker older ⇒ REBUILD. The last is the one that matters — it is what keeps a late assignment
  from being suppressed.
- 🔎 **Incidental finding:** for PAST dates the watermark returns *today's* `13:03 UTC` stamp,
  because the `umpscorecards` post-game feed re-stamps historical rows on every daily run. Harmless
  — the gate only ever keys on the current slate — but it means a naive "has this date's umpire
  data changed?" check over history would be true every day.

⚠️ Still required and **not** substitutable by the above: a real box run of the gated ops, plus the
`predict_today` no-new-abstain / no-new-null-contract comparison. The laptop can prove the *reads*;
only the box can prove the *ops*.

## Exit criterion

`warehouse_events_history` shows near-zero `RESUME_WAREHOUSE` on a **zero-game window**, the warehouse
stays suspended, and August metering trends to ~$0. The Bedrock narrative path is unaffected (SF
Cortex is already retired).

---

# Wake attribution memo — 2026-08-03 (analysis-only session, no fix applied)

Instrument added this session: **Table 4b, the PER-DAY × FAMILY cut** in
`scripts/report_e11_24_wake_census.py` (executions AND waits per UTC day per family).
Read-only, MONITOR_WH, finite statement timeout. **No COMPUTE_WH query was run this session**,
so the operator's 08-04 after-measurement baseline is clean.

## Why the instrument was needed

The aggregate family table (Table 4) sums a family over the whole window, so a lever flipped
mid-window still shows a large total. It cannot separate three different states, and it
misled the story in **both** directions:

| reading | executions | waits | meaning |
|---|---|---|---|
| gate fired | **hold** | → 0 | lever already dead; remaining total is PRE-FLIP RESIDUE |
| repoint fired | → 0 | → 0 | the query left this warehouse entirely — also a win |
| caller stopped | → 0 | → 0 | a dead job / outage — **NOT** a lever, take no credit (the 1b lesson) |
| still firing | hold | hold | a real waker |

⚠️ The middle two are **the same signature**. Distinguish them by whether the work still
happens elsewhere (a repoint) or stopped altogether (an outage) — the census cannot tell you;
the flag/PR history can.

## Target verdicts (Task 2)

**TARGET 2 (weather-venue) — ✅ ALREADY DEAD. No work.**
Per-day execs/waits: `12/2 103/13 114/7 108/1 103/5 79/2` (07-24…07-29) → `5/0 · · 5/0 ·`
(07-30 onward). Both collapse at **07-30** = the `E11_24_WEATHER_SF_FREE` repoint. All 30 waits
in the aggregate are pre-flip residue.

**TARGET 3 (CREDENCE_API metering) — ✅ ALREADY DEAD. No work.**
The `CREDITS_USED_COMPUTE` statement under user `CREDENCE_API` on COMPUTE_WH, per day:
`07-25 22/9 · 07-26 6/4 · 07-27 16/7 · 07-29 2/2` — and **nothing at all from 07-30 onward**.
The `SNOWFLAKE_MONITOR_WAREHOUSE` repoint worked.
⚠️ The `3 metering/audit` family still shows ~12 execs/day post-flip. Those are **NOT** target 3:
they are `CCL1196` (the Snowsight cost UI — a human opening the cost dashboard resumes the
warehouse) plus `DBT_RW` audit queries from *previous E11.24 sessions*. Neither is an automated
waker to fix.

🪤 **A process finding worth keeping: I initially read target 3 as STILL FIRING off a
band-aggregated table, and the per-day cut overturned it.** The very landmine this session was
created to close bit the session itself while it was still using the old instrument.

## The 'other' mass (Task 3)

Statement-level attribution moved three real families out of `other`, taking it from
**254 → 199 waits**. All three are now named in `FAMILY_CASE`:

| new family | waits | executions | state |
|---|---|---|---|
| `8 model-health/pred_log` | 19 | 100–180/day, holding | **STILL FIRING** — `compute_model_health.py`, `backfill_prediction_log.py` |
| `4b scd2 signal writers` (widened) | 25 | 72–135/day, **rising** | **STILL FIRING** — per-row `INSERT INTO tmp_*_incoming VALUES (…)`, incl. overnight |
| `CI on the prod WH` | 12 | bursty | **STILL FIRING** — `ci_betting*` builds resuming the PROD warehouse (4 overnight) |

⚠️ **Instrument bug found and fixed while doing this:** an ad-hoc attribution truncated
`query_text` to 110 chars *before* classifying, which dumped all 30 weather waits into `other`
because `ref_venues` sits past char 110 — inventing a phantom `other` waker and hiding a real
family. **Always classify over the same 400-char window `FAMILY_CASE` uses**, and cross-check
that the two `other` totals agree. Now documented in the script.

Remaining top `other` wakers, owner attributed by **grepping the repo, not the DAG** (INC-27):

| waits | band | statement | owner |
|---|---|---|---|
| 10 | 08-13 | `COUNT(DISTINCT game_pk) AS expected_games` | `scripts/check_prediction_coverage.py` |
| 9 | 08-13 | `SELECT * FROM …feature_pregame_market_features` | `scripts/backfill_market_features_scd2.py` |
| 9 | 08-13 | `with spine as (… mart_game_spine …)` | `scripts/check_odds_coverage.py` |
| 7 | 08-13 | `SELECT * FROM …daily_model_predictions` | `scripts/parity_check_w7b.py` |
| 5 | 14-23 | `select lower(column_name) … information_schema.columns` | `scripts/check_feature_block_coverage.py` |
| ~18 | all | Snowsight cost UI (`COST_INSIGHTS`, `ACCOUNT_ROOT_BUDGET`, `POLICY_REFERENCES`) | human browsing — **not fixable in code** |
| 3 each | mixed | integrity / intraday-fallback / odds-raw date scans | `check_served_prediction_integrity.py`, `check_intraday_fallback.py` |

⭐ **The dominant coherent cluster in `other` is the daily job's own `check_*` guard ops.**
Collectively they are a top waker. Most are already S3-capable in sibling code; each is an
INC-27-class **straggler repoint**, off the predict path, individually cheap.

## Recommended next-target order for the FIX session

1. **`6 lineup/starter CTAS` — 66 waits, the single best lever left.**
   `feature_pregame_lineup_features` / `feature_pregame_starter_features` are materialized as
   **tables** on Snowflake whose entire body is `select * from baseball_data.lakehouse_ext.<model>`
   — pure copies of an external table, rebuilt on every tick. A **view** over that ext table is
   semantically identical and metadata-only: *structurally the same flip as the shipped item-1
   win, with the proof already in hand.* ⚠️ **These are on the serving/predict path → target-6
   session, its own soak.** Do not stack.
2. **`lineup_monitor audit INSERT` — 64 waits, the highest wake-efficiency on the board.**
   Executions ≈ waits (e.g. `10/10`, `9/8`, `8/7`): *almost every execution is the statement that
   resumes the warehouse.* Repoint the audit write off SF — but only after proving it has no
   serving reader (else defer to target 6).
3. **The `check_*` straggler cluster** (~35+ waits combined) — repoint each to S3/DuckDB.
   Cheapest, off the predict path, no soak; good filler between serving flips.
4. **`4b scd2 signal writers` — 25 waits and rising.** Per-row `INSERT … VALUES` is both a waker
   and an inefficiency; batch it or move the SCD-2 write off SF (`scd2_upsert` is one shared
   function behind all 8 generators — port once).
5. **`CI on the prod WH` — 12 waits.** CI should not resume the production warehouse at all;
   point CI at its own warehouse. Config change, no serving risk.
6. `8 model-health/pred_log` — 19 waits, straggler repoint.
7. ⛔ `6a umpire chain` (147 waits) remains the dominant waker overall — target 6a, already owned.

⛔ Not fixable in code: the Snowsight cost-UI waits. Opening the Snowflake cost dashboard on
COMPUTE_WH resumes it. If the account defaults a UI session to COMPUTE_WH, switching that
default to MONITOR_WH removes them — an operator/console setting, not a repo change.

---

# FU-3 VERIFICATION — the combined 6a+FU-3 read (2026-08-04)

**VERDICT: 6a NOT CLOSED · FU-3 NOT CLOSED · target-6 STILL BLOCKED.** Two independent
blockers, neither of which a re-run of the measurement can clear. What the session *did*
settle is a **correction to 6a's own sizing** that changes how the combined read should be
interpreted, and a **CI fix that was blocking the FU-3 deploy itself**.

## Blocker 1 — FU-3 IS NOT DEPLOYED (the story's premise is false)

The story opens "FU-3 (PR #493) is deployed to main and live on the box." It is not. After a
fresh `git fetch` (INC-39: never assert deploy state off a possibly-stale ref):

| check | result |
|---|---|
| `git merge-base --is-ancestor c181e1fa origin/main` | **FU3 NOT ON MAIN** |
| `origin/main` tip | `7f05656a`, 2026-08-03 21:49 CDT |
| PR #493 merge commit | `c181e1fa`, 2026-08-04 00:03 CDT — **into `dev`** |
| `git show origin/main:scripts/ingest_umpires.py` | still the pre-FU-3 `if args.skip_if_exists and not args.dry_run and do_sf:` — the SF-leg-only guard that never executes under `W11_RAW_WRITE_MODE=s3` |

Per **FINDING #5** (recorded in `story_prompts.md`), **merging to `dev` is deploy-inert; the
deploy IS the `dev`→`main` promotion** (`orchestration_cd.yml` fires on push to `main` for
`scripts/**` + `betting_ml/**`). FU-3 merged to `dev` and stopped there. ⇒ every slate to date,
including 08-03, ran the **pre-FU-3** ingest, so no measurement taken so far can contain a
FU-3 effect. This is the *documented-state ≠ actual-state* class (cf. `W7B_LAKEHOUSE_S3`)
arriving one layer up: not a flag that was never set, but a **merge that was never promoted**.

## Blocker 1b — and the promotion was RED (fixed here)

The `dev`→`main` PR was failing `Unit Tests (fast gate) / serving-ops`, i.e. the deploy could
not have proceeded even once noticed. Two tests in `test_ingest_umpires_per_game_skip.py::TestTheActualLakehouseRead`:

```
[FU-3] skip-guard read failed (Secret Validation Failure: during `create` using the
following: Credential Chain: 'config') — writing every assignment.
assert None == {101: ('999', 'New Ump'), 102: ('222', 'Ump Two')}
```

**Root cause — an accidentally credential-dependent test.** `duck()` builds the S3 secret
unconditionally (`CREATE OR REPLACE SECRET … PROVIDER credential_chain`) and DuckDB
**validates the chain at create time**, raising when it resolves to nothing.
`existing_statsapi_assignments` then correctly **fails OPEN** and returns `None`, so both
assertions fail. It passed on a laptop for a reason that has nothing to do with the code under
test: `scripts/ingest_umpires.py:82` calls `load_dotenv(.env)` at import, and the repo `.env`
carries `AWS_ACCESS_KEY_ID` — **the test was reading the developer's real credentials.** CI has
no `.env`, so it went red there and only there.

Reproduced locally by stripping every credential source (`env -u AWS_* AWS_SHARED_CREDENTIALS_FILE=/dev/null
AWS_CONFIG_FILE=/dev/null HOME=…`) → identical failure. **Fix:** an autouse fixture pins dummy
`AWS_*` values for that class only. The read under test is a LOCAL parquet, so no credential is
ever used; production `duck()` semantics are untouched (a monitoring read that silently loses
its S3 creds must still fail loudly). Post-fix, credential-less: **25 passed** in the file,
**974 passed / 7 skipped** in the whole `serving-ops` shard (CI had 972 passed + 2 failed).

⭐ **The durable lesson: `load_dotenv()` at import turns any test that touches a credentialed
helper into a test of the developer's machine.** It is green locally *because* it is reading
real secrets, and red on a clean runner — the inverse of the usual flake, and it points the
blame at the feature rather than at the fixture.

## Blocker 2 — 08-03 FAILS GATE 0, exactly as the FU-2 lesson predicts

GATE 0 requires ~13–15 games, first pitches in 14–23 UTC, ~7+ monitor fires. Measured from
`stg_statsapi_games`:

| slate | games | earliest first pitch (UTC) | 6a armed? | GATE 0 |
|---|---|---|---|---|
| 2026-07-28 | 15 | 17:40 | no (reference) | ✅ |
| 2026-07-30 | 10 | 16:10 | no (reference) | ⚠️ small |
| 2026-08-02 | 15 | 17:35 | **only from 20:52**, after the slate's last pre-game | ❌ no opportunity |
| **2026-08-03** | **8** | **22:40** | yes | ❌ **short AND late** |
| 2026-08-04 | 15 | 22:35 | yes | (had not run — 05:14 UTC at read time) |

08-03 is the degenerate case GATE 0 exists to refuse. It is worse than "small": the umpire
assignment's **first write of the day was 20:38 UTC**, so nearly every monitor invocation
landed in the gate's *fail-open* "no umpire row yet" path, and the few that followed each had a
genuinely fresh watermark. **0 skips on 08-03 is therefore consistent with a perfectly correct
gate and proves nothing about it** — the measurement is uninformative, not negative.

## ⭐ THE CORRECTION THAT MATTERS — 6a's fires-per-bump ratio is ~1.0, NOT ~1.5

Re-derived on fresh data, and the re-derivation **changes 6a's expected saving**.

**The original instrument over-counted.** The ~1.5 ratio counted "fires" as *distinct 5-minute
windows in the 14–23 band containing an umpire CTAS*. A rebuild that spans a window boundary is
counted **more than once**, and because the umpire models run early in the selector the later
windows hold a lineup CTAS with **no** umpire CTAS — manufacturing phantom "gate skips". On
08-02 that method reported **10 skips on a day the gate was provably not armed** (FU-1: the
executing container was not recreated until 20:52 UTC).

**A second, subtler over-count:** matching `%stg_statsapi_umpire_game_log%` also matches the
trailing `GRANT SELECT ON TABLE …` statement dbt emits, doubling that model's count.

The clean, duration-independent instrument is **executions of `feature_pregame_umpire_features`**
(built exactly once per un-gated invocation). It validates against an independent record: it
gives **7 for 08-02**, matching FU-1's separately-recorded "all 7 of the 08-02 rebuilds".

Invocations vs same-day watermark bumps (write-instants), 14–23 UTC band, **07-25 onward** —
07-21..07-24 sit before a tick-chain change on 07-25 (`6 tick CTAS (dead 7/25)`) and are not
comparable:

| day | invocations | bumps | ratio |
|---|---|---|---|
| 07-25 | 8 | 8 | 1.00 |
| 07-26 | 16 | 11 | 1.45 |
| 07-27 | 7 | 7 | 1.00 |
| 07-28 | 7 | 7 | 1.00 |
| 07-29 | 9 | 9 | 1.00 |
| 07-30 | 7 | 7 | 1.00 |
| 07-31 | 9 | 9 | 1.00 |
| 08-01 | 11 | 10 | 1.10 |
| 08-02 | 7 | 7 | 1.00 |
| | | | **median 1.00** |

⇒ **essentially every umpire rebuild is preceded by a fresh watermark bump, so 6a alone has
~ZERO headroom** — not the ~30–35% the 1.5 ratio implied. And the mechanism is exactly the one
FU-3 exists to remove: with the pre-FU-3 ingest, *every* tick re-writes the mirror and bumps the
watermark, so the gate's key ("assignment newer than the last rebuild") is *always* satisfied.

**This is a stronger statement than "6a-alone is a crippled measurement": 6a-alone is ~INERT,
and 6a's entire saving is contingent on FU-3.** The ship-forward decision to measure them
together was right; the reason is firmer than when it was taken.

### Direct skip count (available today, and it agrees)

Because the gate drops **both** models (`UMPIRE_MODELS = ("stg_statsapi_umpire_game_log",
"feature_pregame_umpire_features")`), a skip removes the umpire CTAS while the never-gated
lineup/starter CTAS remains. Comparing the two, **umpire builds equal invocations on every day
including armed 08-03 ⇒ ZERO gate skips have been observed to date.** Consistent with the
ratio above and with 08-03's degenerate shape; not evidence of a defect.

### Census cross-check, normalized (waits-per-fire)

`report_e11_24_wake_census.py --days 10`, umpire chain, **14–23 band** (MONITOR_WH):

| day | waits | executions | invocations | **waits/fire** |
|---|---|---|---|---|
| 07-28 (ref) | 11 | 49 | 7 | 1.57 |
| 07-30 (ref) | 13 | 49 | 7 | 1.86 |
| 08-02 | 9 | 49 | 7 | 1.29 |
| **08-03 (armed)** | **9** | 36 | 5 | **1.80** |

08-03's raw count (9 vs 11/13) looks like a cut and **is not one** — normalized per fire it sits
on top of the 07-30 reference. This is precisely the confound GATE 0 warns about, and it is why
the raw count alone must never be reported.

## Wave-floor + late-assignment legs — BASELINE established, acceptance unchanged

Fresh replay of the real mirror through FU-3's exact per-game content-aware filter, all 15
slates 07-20..08-03 (`existing_statsapi_assignments` semantics: latest `loaded_at` per game,
`data_source='statsapi'`):

* **write-instants 131 → 95 (−27%), median 8 → 6** — reproducing the pre-merge estimate
  (126→91, −28%, median 8→6) on data that now includes two further slates.
* **the floor is the announcement-wave count**: per-slate distinct *first-seen* instants have
  median 6 (range 3–11), and the replayed survivors sit at or one above that count on every
  slate — i.e. every surviving write carries a genuinely new assignment. Driving below it would
  mean **swallowing a late announcement**.
* **leg 2 is satisfiable**: every slate in the window has **≥3 distinct first-seen instants**
  (min 3, on the 8-game 08-03), so the "≥2 distinct `first_seen`" late-assignment requirement is
  a live test on any normal slate, not a formality.

⇒ **Acceptance is unchanged and both legs remain required.** On the post-deploy slate expect
write-instants ≈ that slate's wave count (~6 on a normal 15-game slate), **not ~1–2**; below the
wave floor is a REGRESSION, not a better result.

## Serving no-regression — CLEAN on the armed slate

SF-free (DuckDB over S3; deliberately **not** `check_served_prediction_integrity.py`, which
connects on COMPUTE_WH and would put the audit inside its own measurement). Deduped to the
currently-serving row per `(prediction_type, game_pk)`:

| slate | tier | games | h2h_edge not null | mean coverage | intraday_fallback | feature_store |
|---|---|---|---|---|---|---|
| 07-31 | post_lineup | 15 | 13 | 0.944 | 0 | 15 |
| 08-01 | post_lineup | 15 | 13 | 0.989 | 0 | 15 |
| 08-02 | post_lineup | 15 | 14 | 0.978 | 0 | 15 |
| **08-03** | **post_lineup** | **7** | **7 (100%)** | **0.952** | **0** | **7** |
| 08-03 | morning | 8 | 0 | 0.771 | 0 | 8 |

No regression: `intraday_fallback` 0 everywhere, every served row `data_source='feature_store'`,
coverage in band. Per the stated traps, `sigma_tier='abstain'` (saturated) and a flat
`total_runs` (chronic) are not read as gate effects. `best_alpha=0`, so nothing rode on this.

⚠️ **`check_w11_tail_coverage.py --date 2026-08-03` returned umpire 0/8 and weather 0/8
BUILD_GAP — DO NOT read this as a 6a regression, and re-check it after the 08-04 nightly.** Two
reasons: (i) it was run at ~05:30 UTC on 08-04, *before* the ~12:40 UTC W11 nightly that
populates the prior slate's umpire/weather — the documented one-cycle lag (those two feeds land
*after* the build that consumes them); (ii) 6a gates only the **intraday copy**, while the
served umpire parquet comes from the nightly `--w11b`, which 6a does not touch.

## FU-3 DEPLOYED + VERIFIED IN THE EXECUTING CONTAINER (2026-08-04 06:04 UTC)

Blocker 1 and 1b are CLEARED. PR #579 merged to `dev` (06:00 UTC), `dev`→`main` promoted, and
`orchestration_cd.yml` deployed the box at **06:04 UTC** (`✅ Box deploy Success`).

Verified the FU-1 way — in the **persistent `dagster-codeloc` container that `DefaultRunLauncher`
actually runs job subprocesses in**, not a throwaway exec:

| check | result |
|---|---|
| `grep "args.skip_if_exists and not args.dry_run" /app/scripts/ingest_umpires.py` | lines 341 + 366, **neither carrying `and do_sf`** ⇒ FU-3's per-game form is live (line 23 is the docstring quoting the OLD form — expected prose, not code) |
| `docker inspect .State.StartedAt` | **2026-08-04T06:04:38Z** — recreated BY this deploy, not merely restarted |
| `docker inspect .Image` | `sha256:11daaaf0a231…` — **byte-identical** to the digest the deploy log wrote (`writing image sha256:11daaaf0a231…`) |
| `printenv E11_24_UMPIRE_REBUILD_GATE` | `1` |

⇒ **6a and FU-3 are both live and armed in the container that will run the 08-04 slate.**

### ⚠️ REFINEMENT TO THE INC-36 `COPY . .` TELL (a false alarm this session raised)

The deploy log showed `#69 [dagster-codeloc 14/15] COPY . . → CACHED` on a build whose context
**did** include a changed `scripts/ingest_umpires.py` (48-file diff from the previously-deployed
`7f05656a`; `.dockerignore` excludes only `*.duckdb`). Read against INC-36's signature —
*"`COPY . . → CACHED` on a commit that changed 10 files — impossible on a first build"* — that
looks like a concurrent-build race, and it was flagged as one. **It was not.**

The compose stack builds **several services from the SAME image** (`dagster-codeloc`, the daemon,
the webserver). The first service performs the real `COPY . .`; its siblings legitimately report
`CACHED` **within the same invocation**. ⇒ **`COPY . . → CACHED` is the INC-36 tell only for the
FIRST service built from a given context; a sibling sharing the image is expected to be cached.**

**The discriminating check is not the cache line at all — it is whether the RUNNING container's
image digest equals the digest the deploy log wrote** (plus `.State.StartedAt` ≥ the deploy).
That is a two-command, read-only test that converts the suspicion into a fact in either
direction, and it is what should be run before trusting *any* deploy that a soak depends on.
Cheap insurance against re-running the FU-1 failure (measuring a gate that cannot fire).

## WHAT IS STILL NEEDED (in order)

1. ~~**Land the CI fix**, then **promote `dev`→`main`**~~ — ✅ DONE 2026-08-04 06:04 UTC (above).
2. **Wait for a GATE-0-clean slate** (~13–15 games, first pitches 14–23 UTC, ≥7 invocations)
   that runs **entirely after** the deploy recreated `dagster-codeloc`. A same-day flip does not
   retroactively arm already-run jobs (FU-1).
   · **08-04 is the first eligible slate** — 15 games, deploy at 06:04 UTC, monitor starts
     ~17:35 UTC ⇒ the whole slate runs armed. ⚠️ But it is **uniformly late**: every first pitch
     falls 22:35–01:40 UTC, so the gate's measurable window only opens once the day's FIRST
     umpire assignment is written (on 08-03 that was 20:38 UTC). **Confirm the invocation count
     reaches ~7 and that assignments landed with slate left to run** before accepting it as the
     clean read — a late-assignment slate can leave too few post-assignment invocations for the
     gate to have any opportunity, which is the 08-03 failure in a milder form.
3. **Direct event-log verification** (below) — the primary, fact-settling leg.
4. Re-run the three measurements above on that slate: write-instants vs its wave count + ≥2
   distinct `first_seen`; waits-per-fire vs 1.57 (07-28) / 1.86 (07-30); serving no-regression.

### The box command for the direct verification

`_run_script` forwards the subprocess's stdout to `context.log.info` and stderr to
`context.log.warning`, and `ingest_umpires.py` logs via `logging` (→ stderr). So **both**
markers persist in **Postgres**, and one command verifies FU-3 *and* 6a. This survives
container recreation; `docker compose logs` does not (`LocalComputeLogManager` is wiped).

```bash
# ON THE EC2 BOX — read-only. Set DAY to the GATE-0-clean, post-deploy slate.
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python - <<'PY'
import datetime as dt
from dagster import DagsterInstance
from dagster._core.storage.dagster_run import RunsFilter

DAY = "2026-08-05"          # <-- the slate under audit (UTC date)

inst = DagsterInstance.get()
recs = inst.get_run_records(filters=RunsFilter(job_name="lineup_monitor_job"), limit=300)
sel = [r for r in recs
       if r.create_timestamp.astimezone(dt.timezone.utc).date().isoformat() == DAY]
print(f"{len(sel)} lineup_monitor_job runs on {DAY}\n")

reb = skip = 0
for r in sorted(sel, key=lambda x: x.create_timestamp):
    rid = r.dagster_run.run_id
    when = r.create_timestamp.astimezone(dt.timezone.utc).strftime("%H:%M:%S")
    for e in inst.all_logs(rid):
        m = (e.user_message or "")
        for marker in ("[E11.24 umpire-gate]", "[FU-3]"):
            if marker in m:
                for line in m.splitlines():
                    if marker in line:
                        print(f"{when}  {rid[:8]}  {line.strip()[:220]}")
                if marker == "[E11.24 umpire-gate]":
                    if "REBUILDING" in m:
                        reb += 1
                    else:
                        skip += 1
print(f"\nGATE: REBUILDING={reb}  SKIPPING={skip}  over {len(sel)} runs")
PY
```

**PASS** = the gate SKIPS invocations whose assignment is unchanged and REBUILDS only those
with a new/changed assignment, **and** `[FU-3] … unchanged since the last write — skipping`
appears on the ticks between announcement waves while `[FU-3] N of M … new or changed` appears
on the waves themselves. A run showing `REBUILDING: … failing OPEN` is a gate error, not a skip.

## Files

* `betting_ml/tests/test_ingest_umpires_per_game_skip.py` — hermetic-AWS-env fixture (CI fix).
* `docs/e11_24_literal_zero_snowflake.md` — this section.

---

# THE 08-04 ARMED-SLATE READ (2026-08-05) — ✅ FU-3 CONFIRMED · ⛔ 6a IS INERT, ROOT CAUSE LOCATED

**VERDICT: FU-3 PASSES · 6a does NOT close · target-6's *measurement* blocker is CLEARED.**
08-04 is the first slate that satisfies GATE 0 while armed, and it is **informative** — unlike
08-03 it gave the gate three clean opportunities to fire. It took **none of them**, and the
cause is a single missing S3 object, not a measurement artifact.

## GATE 0 — PASSED (this read counts)

| criterion | required | 08-04 | |
|---|---|---|---|
| games | ~13–15 | **15** | ✅ |
| invocations (`feature_pregame_umpire_features` CTAS, 14–23) | ≥7 | **9** | ✅ |
| first assignment written | with slate left to run | **19:11:45 UTC**, 3.4 h before the 22:35 first pitch, **6 invocations still to come** | ✅ |
| ran entirely post-deploy | yes | deploy recreated `dagster-codeloc` 06:04:38Z; slate ran 19:14→23:15Z | ✅ |

This is precisely what 08-03 lacked. The 3 post-assignment invocations with an *unchanged*
watermark are real, countable skip opportunities.

**The midnight straddle did NOT undercount.** Both censuses were run for `2026-08-04` *and*
`2026-08-05` and combined. Every umpire write for the slate landed 19:11:45–22:42:25 UTC on
08-04, and all 9 invocations landed 19:14–23:15 UTC on 08-04 — **zero in 08-05's 00–07 band.**
The straddle was a real risk and it is measured, not assumed.

## Leg (b) — ✅ PASS, both legs. FU-3 works exactly as designed.

Read from the LIVE mirror with FU-3's own semantics (`data_source='statsapi'`, latest
`loaded_at` per `game_pk`, `try_cast` at every use-site):

| slate | games | write-instants | wave floor | ratio |
|---|---|---|---|---|
| 07-28 (ref) | 15 | 7 | 7 | 1.00 |
| 07-31 (ref) | 15 | 9 | 8 | 1.12 |
| 08-01 (ref) | 15 | 10 | 5 | 2.00 |
| 08-02 (ref) | 15 | 7 | 7 | 1.00 |
| **08-04 (armed)** | **15** | **6** | **6** | **1.00** |

* **(i) write-instants = 6 = the wave floor exactly.** Median over the pre-FU-3 window is 8, so
  this is the predicted **8 → 6 (−27%)**, landing *on* the floor and **not below it** — every
  surviving write carries a genuinely new assignment; nothing was swallowed. ✅
* **(ii) 6 distinct `first_seen` instants** (19:11, 19:41, 20:12, 20:42, 21:42, 22:42) against a
  requirement of ≥2 — late assignments still land within one tick. ✅

## Leg (c) — no cut, and that is the *expected* reading given 6a is inert

Denominator = executions of `feature_pregame_umpire_features`. ⚠️ **Instrument correction worth
keeping:** `ilike '%create or replace%feature_pregame_umpire_features%'` **also matches
`create or replace temporary table …feature_pregame_game_features_raw__dbt_tmp`** — a *downstream
consumer* whose body names the umpire table — an exact **2× over-count**. Anchor on the CTAS
*target* (`ilike 'create or replace transient table …feature_pregame_umpire_features as%'`). So
corrected, the instrument **reproduces this doc's own references exactly** (07-28 → 7 invocations
/ 11 waits / 1.57; 07-30 → 7 / 13 / 1.86), which is what makes 08-04 comparable.

| day | invocations | chain waits | **waits/fire** |
|---|---|---|---|
| 07-28 (ref) | 7 | 11 | 1.57 |
| 07-30 (ref) | 7 | 13 | 1.86 |
| 08-02 | 7 | 9 | 1.29 |
| 08-03 (armed, GATE-0 fail) | 5 | 7 | 1.40 |
| **08-04 (armed, GATE-0 pass)** | **9** | **15** | **1.67** |

1.67 sits **between** the two references ⇒ **no cut**. Consistent with zero skips.

## ⛔ THE FINDING — 6a fired 0 of 3, and the marker object has NEVER EXISTED

Invocations vs mirror writes, aligned (each rebuild trails its write by ~3 min):

| tick | mirror write | rebuild | fresh watermark? | gate should | gate did |
|---|---|---|---|---|---|
| 1 | 19:11:45 | 19:14:41 | yes | rebuild | rebuild ✅ |
| 2 | 19:41:53 | 19:44:43 | yes | rebuild | rebuild ✅ |
| 3 | 20:12:00 | 20:14:54 | yes | rebuild | rebuild ✅ |
| 4 | 20:42:16 | 20:45:06 | yes | rebuild | rebuild ✅ |
| 5 | — | **21:15:01** | **no** | **SKIP** | **rebuilt** ⛔ |
| 6 | 21:42:20 | 21:45:18 | yes | rebuild | rebuild ✅ |
| 7 | — | **22:15:26** | **no** | **SKIP** | **rebuilt** ⛔ |
| 8 | 22:42:25 | 22:45:03 | yes | rebuild | rebuild ✅ |
| 9 | — | **23:15:38** | **no** | **SKIP** | **rebuilt** ⛔ |

Corroborated by the **never-gated control**: a skip drops the umpire CTAS while the lineup CTAS
remains, so `umpire_builds < lineup_builds` is the skip signature. On 08-04 they are **equal
(9 = 9)** — the same test that read zero on every prior day.

**ROOT CAUSE — the gate's marker is never persisted:**

```
s3://baseball-betting-ml-artifacts/baseball/lakehouse_state/umpire_rebuild_watermark.json
  → 404 Not Found   (and the whole `baseball/lakehouse_state/` prefix does not exist)
```

Verified rigorously: the 404 is a genuine absence, not a permission artifact (the same
credentials list `baseball/` fine, and a recursive scan of the bucket finds **no** watermark
object anywhere); deployed `origin/main` carries the **same** `_BUCKET`/`_MARKER_KEY`; and
`grep` shows the gate is the **only writer of that prefix in the repo** — nothing has ever
created it. `_today()` resolves correctly (LA game-day = 2026-08-04 at 19:14 UTC).

With the object absent, `read_rebuild_marker` raises `NoSuchKey` on **every** invocation →
`umpire_rebuild_decision` returns `(True, current, "marker read failed (…) — failing OPEN")` →
rebuild, forever. **The gate cannot skip until the first marker is written.**

⭐ **Why this finding needed FU-3 to become visible.** Pre-FU-3, fires-per-bump was ~1.00 —
every tick re-stamped the mirror, so *no* invocation had an unchanged watermark and a healthy
gate and a broken gate were **observationally identical**. FU-3 lifted 08-04 to
**9/6 = 1.50**, creating the first real headroom — and the gate took none of it. That is the
"a mechanism that cannot act is a finding" rule applied to a **gate**: 6a was never measurable
until FU-3 landed, exactly as this doc predicted, and the first measurable slate says it is
broken.

### Three candidate causes — leg (a) names which (all three yield the same verdict)

The marker write at `sensor_ops.py:441` *should* have run on tick 1 (`watermark` is non-None on
the marker-read-failed path). It did not persist. Candidates:

1. **`write_rebuild_marker` raises** — most likely, and the leading hypothesis: this is the
   **first-ever write to that bucket prefix**, i.e. the **E8.5 IAM class** (a role whose prior
   grants on a bucket are read-only or prefix-scoped). Logged as
   `[E11.24 umpire-gate] marker write FAILED (<exc>)`, which names it.
2. **The gate is OFF in the executing container** — then there are **no** `[E11.24 umpire-gate]`
   lines at all. (FU-1's check read `=1` in the persistent container at 06:04, so this is
   unlikely, but it is not excluded by anything measurable from the laptop.)
3. **The op raises inside `_run_dbt` before line 441** — argues against itself, since leg (d)
   shows the post-lineup path healthy, but the event log settles it.

**The verdict does not depend on which:** all three produce zero skips, so **6a does not close.**

### 🪤 A counter bug in the verification snippet — fix before running leg (a)

The published loop counts `if "REBUILDING" in m: reb += 1 else: skip += 1`. The
`marker write FAILED` line **also** carries the `[E11.24 umpire-gate]` marker and does **not**
contain `REBUILDING`, so it is tallied as a **SKIP** — the script would report phantom skips in
exactly the failure mode we are in. Same vacuous-counter class as INC-38/INC-39. The corrected
command below classifies on explicit markers and counts `marker write FAILED` separately.

## Leg (d) — ✅ serving CLEAN, no regression

SF-free (DuckDB over S3), deduped to the currently-serving row per `(prediction_type, game_pk)`:

| slate | tier | games | h2h_edge not null | mean coverage | intraday_fallback | feature_store |
|---|---|---|---|---|---|---|
| 08-01 | post_lineup | 15 | 13 | 0.989 | 0 | 15 |
| 08-02 | post_lineup | 15 | 14 | 0.978 | 0 | 15 |
| 08-03 | post_lineup | 7 | 7 | 0.952 | 0 | 7 |
| **08-04** | **post_lineup** | **15** | **15 (100%)** | **0.967** | **0** | **15** |
| 08-04 | morning | 15 | 0 | 0.811 | 0 | 15 |

`check_w11_tail_coverage.py --date 2026-08-04` → **umpire 15/15, weather 15/15,
public_betting 15/15, all OK** (`w11_tail_problem_count=0`) — no BUILD_GAP, so the 08-03
one-cycle-lag caveat does not recur. Morning-tier `h2h_edge=0` and coverage 0.811 match the
chronic pattern (07-31 0.800 / 08-02 0.822), not a gate effect. Per the stated traps, saturated
`sigma_tier='abstain'` and flat `total_runs` are not read as gate effects. `best_alpha=0`.

## Where this leaves the program

| item | verdict |
|---|---|
| **FU-3** | ✅ **PASS on leg (b)** — mechanism confirmed independently (write-instants at the wave floor, −27%, no swallowed assignment). Leg (a) is corroboration, not the basis. |
| **6a** | ⛔ **DOES NOT CLOSE.** Not "unmeasurable" (08-03) and not "inert by design" (the old ~1.00-ratio reading) — a **located defect**: the marker is never persisted, so the gate fails OPEN on every tick. Fix = one S3 object + whatever prevents its write. |
| **target-6** | ⭐ **The measurement blocker is CLEARED — recommend UNBLOCK.** target-6 was held only so 6a/FU-3 attribution would not be confounded. That attribution is now settled and unambiguous: **FU-3 = −27% write-instants; 6a = exactly 0**. There is nothing further to soak. Under the operator's 2026-08-03 SHIP-FORWARD reframe (per-lever measurement is no longer a gate; the end state is the proof), target-6 should proceed in its own fresh session. **This is a PM call, flagged not taken.** |
| **FU-4 (new)** | The 6a marker fix. Small and independent of target-6. |

⚠️ 6a is **correct-but-inert**, never incorrect: fail-open means the umpire block has always
rebuilt, so there is **no serving debt** to unwind — leg (d) is clean. The only cost is the
saving not being realised, which is what the op's own warning text predicted verbatim
("Persistent failures mean the saving is not being realised").

## ⏭️ Leg (a) — the OPERATOR command (SSM; `baseball-access-user` cannot `SendCommand`)

**WHERE: the EC2 BOX.** Read-only. Runs BOTH UTC dates and separates the three causes above.

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python - <<'PY'
import datetime as dt
from dagster import DagsterInstance
from dagster._core.storage.dagster_run import RunsFilter

DAYS = ("2026-08-04", "2026-08-05")   # the slate straddles midnight UTC — read BOTH

inst = DagsterInstance.get()
recs = inst.get_run_records(filters=RunsFilter(job_name="lineup_monitor_job"), limit=400)
sel = [r for r in recs
       if r.create_timestamp.astimezone(dt.timezone.utc).date().isoformat() in DAYS]
print(f"{len(sel)} lineup_monitor_job runs over {DAYS}\n")

reb = skip = openfail = markerfail = 0
gate_lines = 0
for r in sorted(sel, key=lambda x: x.create_timestamp):
    rid = r.dagster_run.run_id
    when = r.create_timestamp.astimezone(dt.timezone.utc).strftime("%m-%d %H:%M:%S")
    for e in inst.all_logs(rid):
        m = (e.user_message or "")
        for marker in ("[E11.24 umpire-gate]", "[FU-3]"):
            if marker not in m:
                continue
            for line in m.splitlines():
                if marker in line:
                    print(f"{when}  {rid[:8]}  {line.strip()[:240]}")
            if marker == "[E11.24 umpire-gate]":
                gate_lines += 1
                # classify on EXPLICIT markers — "marker write FAILED" is neither a
                # rebuild nor a skip, and the old `else: skip += 1` counted it as one.
                if "marker write FAILED" in m:
                    markerfail += 1
                elif "REBUILDING" in m:
                    reb += 1
                    if "failing OPEN" in m:
                        openfail += 1
                elif "SKIPPING" in m:
                    skip += 1

print(f"\nGATE over {len(sel)} runs: REBUILDING={reb} (of which failing-OPEN={openfail})  "
      f"SKIPPING={skip}  marker-write-FAILED={markerfail}")
if gate_lines == 0:
    print("⚠️ NO [E11.24 umpire-gate] lines at all ⇒ the gate was OFF in the executing "
          "container (cause 2), not merely failing open.")
PY
```

**How to read it**
* `SKIPPING=0` with `REBUILDING=9` and `failing-OPEN=9` ⇒ confirms the marker-absent diagnosis.
* `marker-write-FAILED>0` ⇒ **cause 1**; the exception text names it (expect an S3
  `AccessDenied`/`PutObject` ⇒ the E8.5 IAM grant).
* `gate_lines == 0` ⇒ **cause 2** (flag off in the executing container).
* Neither, and no gate lines after the dbt step ⇒ **cause 3**.

## Files

* `docs/e11_24_literal_zero_snowflake.md` — this section. No code changed; this is a
  verification record.

---

# TARGET 6 — THE EXT-TABLE-COPY → VIEW FLIP (2026-08-05, code-complete, UNDEPLOYED)

Branch `target-6`. `best_alpha=0` — no bet rides on any of this.

## The lever, in one sentence

Four models in the intraday tick selector are, on the Snowflake target, literally
`select * from baseball_data.lakehouse_ext.<model>` — a COPY of an external table — and they were
`materialized='table'`, so **every intraday lineup tick ran a full CTAS over each of them**. A CTAS
RESUMES `COMPUTE_WH`; `create or replace view` is metadata-only and never does. Flipping the four
to `materialized='view'` removes those provisioning waits **for every caller at once**.

```
stg_statsapi_umpire_game_log        57 waits / 8d  ┐ the "umpire chain" band
feature_pregame_umpire_features     54 waits / 8d  ┘ = 111 / 662 (16.8%), the largest single band
feature_pregame_starter_features    ┐ the "6 lineup/starter CTAS" band
feature_pregame_lineup_features     ┘ = 66 waits / 8d
```

Fired by `lineup_dbt_feature_rebuild` (~9 fires/slate, sensor-driven) and once by
`dbt_umpire_feature_rebuild`.

## Why this is safe — the four load-bearing facts

**1. Content-neutral BY CONSTRUCTION.** The CTAS's own source is this same external table, so a
view returns byte-identical rows at read time. It cannot be *staler* than the copy; if anything it
is fresher, because a copy taken before an ext-table `REFRESH` lags until the next CTAS. That also
**removes an INC-25-class ordering constraint** — there is no longer a "the rebuild must run after
the ext refresh" edge to get wrong.

**2. No Snowflake consumer needs them materialized.** Verified two ways, per INC-27 (grep the repo,
not the DAG):

* *dbt graph:* every `ref()` to these four sits **inside the DuckDB branch** of its consumer.
  `feature_pregame_game_features_raw` refs lineup/starter/umpire at lines 78–140, but its
  `{% else %}` starts at line 2277 — on Snowflake it reads its **own** ext table and never touches
  them. Same for `feature_pregame_bullpen_state_features` (refs at 70–83, `{% else %}` at 189).
  ⇒ **on the Snowflake target, nothing in dbt reads these four at all.**
* *raw SQL:* `betting_ml/utils/data_loader.py` `_TODAY_LINEUP_QUERY` / `_TODAY_STARTER_QUERY` filter
  `WHERE game_date = '<date>'` **and are dead in serving today** (both run only when `_S3_MODE` is
  False; `predict_today --s3` sets it True, and `W7B_LAKEHOUSE_S3` / `W7B_INTRADAY_S3` are both in
  the §10a enforced set). `app/backend/routers/picks.py::_UMPIRE_QUERY` runs through
  `lakehouse_query` = **DuckDB/S3, not Snowflake**. `generate_run_env_signals.py` key-joins
  starter+umpire — the one live recurring Snowflake reader, once/day, per-date, inside the
  already-awake daily-build window. The rest (`ablate_*`, `train_run_env*`) are offline research.

**3. The pattern is already PROVEN in production on this exact shape.** `stg_statsapi_games`,
`stg_statsapi_probable_pitchers`, `stg_statsapi_lineups`, `mart_odds_outcomes`,
`mart_game_odds_bridge`, `mart_closing_line_value` and ~14 more are **already** ext-copy VIEWs on
the Snowflake branch — several with `unique` / `severity: error` tests. These four were the
outliers, not the pioneers. This is why no bespoke mitigation was added: a special case here would
be less safe than matching the convention.

**4. Not type-contract-relevant.** None of the four is in `dbt/type_contracts/` (the INC-19
registry covers `feature_pregame_game_features_raw` and the four EB models — all **incrementals**,
which is exactly why they are NOT flippable and are untouched here).

## The 8 tick models, and why only 4 moved

| model | SF materialization | flipped? |
|---|---|---|
| `stg_statsapi_umpire_game_log` | `table` → **`view`** | ✅ |
| `feature_pregame_umpire_features` | `table` → **`view`** | ✅ |
| `feature_pregame_starter_features` | `table` → **`view`** | ✅ |
| `feature_pregame_lineup_features` | `table` → **`view`** | ✅ |
| `eb_starter_posteriors` | `incremental` (merge, 7d) | ⛔ not a copy-in-place |
| `eb_batter_posteriors_raw` | `incremental` (merge, 7d) | ⛔ |
| `feature_pregame_game_features_raw` | `incremental` (delete+insert, 7d) | ⛔ INC-19 type-pinned |
| `feature_pregame_game_features` | `incremental` (delete+insert, 7d) | ⛔ |

The four incrementals MERGE a bounded window rather than replacing the object, so they are not
free to re-run and cannot become views. **They are the residual target-6 wake and the reason this
lever is a large cut, not a total one** — say so when reading the soak: a band that falls but does
not vanish is the PREDICTED outcome, not a half-working flip.

## ⚠️ TWO PREDICTED SIDE EFFECTS — name them before the soak, or they read as regressions

**(a) The four models JOIN the run-day daily-build selection, tests included.** The state-aware
daily build rewrites its args to
`build --select "source_status:fresher+ config.materialized:view"` (`pipeline/ops/_dbt_exec.py`
L165 and `services/dbt_runner/server.py` L259 — INC-13 unions views so they are always rebuilt).
Today these four are **not** selected on run days: their Snowflake branch has no `source()`, so
`source_status:fresher+` never reaches them. As views they will be — bringing **~50 dbt tests**
with them (`unique_combination_of_columns`, `not_null` × ~45, `accepted_values`).

* **Cost sign:** those tests scan an ext-table-backed view instead of a table, ~once/day, **inside
  the already-awake daily-build window** ⇒ expect a small **active-minutes** rise, **not** new
  resumes. Judge this lever on **resumes**; read active-minutes as the control.
* **Risk:** the run-day path is un-wrapped (`daily_ingestion_ops.py` L1427, no try/except) and
  `dbt_daily_build` is HALT-tier, so an `error`-severity test failure there fails the daily job —
  the INC-6 shape. This exposure is **pre-existing and already accepted** for every view listed in
  fact 3 above (`stg_statsapi_probable_pitchers` carries explicit `severity: error`), so this is a
  marginal increase, not a new class. **Fallback if it bites:** exclude the four by tag from the
  view union in BOTH selector sites (they are still created by `dbt_umpire_feature_rebuild`'s
  explicit `dbt run` daily, so INC-13's "unbuilt view" concern does not apply to them).
* 🐞 **Incidental finding, not fixed here:** that rewrite **drops `--exclude tag:w1_lakehouse`** —
  `effective_args` replaces `args` wholesale, keeping only `target_args`. So the run-day build does
  not honour the exclusion `_dbt_daily_build_args()` computes. Recorded, not chased.

**(b) The first post-deploy run DROPs each table and CREATEs a view.** dbt drops an existing
relation whose type differs from the target materialization. It is sub-second metadata, but there
is a window where the object does not exist — **which is precisely why the `dev`→`main` promotion
must land in a QUIET post-slate window** (INC-36), not mid-slate.

## ⛔ 6a IS REMOVED, NOT REPAIRED

`E11_24_UMPIRE_REBUILD_GATE` + `betting_ml/monitoring/umpire_rebuild_gate.py` are **deleted**.

Rationale, and it is not merely "6a was broken": **a conditional SKIP of a free operation saves
nothing.** Even a perfectly-working 6a could only ever skip the ~1-in-3 ticks whose watermark was
unchanged; the view removes the wake from **all** of them, for **every** caller, with no flag, no
S3 marker, no four-owner flag ceremony and no soak. That 6a was *also* verified INERT on the
2026-08-04 armed slate (0 skips of 3 real opportunities — its marker object had never existed, so
every tick took the fail-OPEN path) makes the removal free of any lost, banked saving. 6a was
**correct-but-inert, never incorrect** (fail-open ⇒ the block always rebuilt ⇒ no serving debt).

⇒ **FU-4 (the marker/IAM fix) is CLOSED as WONTFIX.** It existed only to capture 6a's ~10% before
this flip; the flip subsumes it.

## Explicitly NOT done in this session, and why

The story's remaining target-6 items are **deliberately deferred**, not forgotten — the
one-serving-flip-per-soak rule is the whole reason this session exists:

* **The per-slate umpire idempotency gate** — **SUPERSEDED**. Its entire purpose was to stop the
  umpire CTAS re-firing; the view flip deletes that CTAS. There is nothing left to gate. (The
  *ingest*-side half already shipped as FU-3, −27% write-instants, verified 2026-08-04.)
* **Porting `scd2_writer.scd2_upsert` to the Delta/DuckDB write path** — a real, still-valid lever
  (one shared fn behind 5 generators: run_env, offense/bullpen, defense_quality, env_state,
  matchup). It is a **serving-path WRITE change into a non-idempotent ordered chain**, so bundling
  it here would put two serving flips in one soak and make the census un-attributable. Next session.
* **The `lineup_monitor` audit INSERT** (64 waits/8d, 100% wake-efficiency) — needs the INC-27
  repo-grep proving it has NO serving reader before it can be touched. Next session.

## Verification plan (the runtime gate — CI mocks all IO, so CI-green is necessary-not-sufficient)

Deploy = the `dev`→`main` promotion (auto-SSM), in a QUIET window. Then, per FU-1's binding rules,
evidence comes from the **Postgres event log**, dated against `.State.StartedAt` — never an
`exec`-based `printenv`. Full commands are in the session handoff. Read the census **PER-DAY**,
never off a window aggregate straddling the flip date (executions HOLDING while waits → 0 is the
working shape; both collapsing is a dead job or an outage day).

## Files

* `dbt/models/staging/statsapi/stg_statsapi_umpire_game_log.sql`,
  `dbt/models/feature/feature_pregame_{umpire,starter,lineup}_features.sql` — the flip.
* `pipeline/ops/sensor_ops.py` — 6a gate branch removed; selector restored to unconditional.
* `betting_ml/monitoring/umpire_rebuild_gate.py`, `betting_ml/tests/test_umpire_rebuild_gate.py` — deleted.
* `services/dagster/aws/env.required`, `.env.example`, `BOX_OPERATIONS.md` §10 — flag deregistered;
  §10 self-contradiction reconciled + three table-hygiene rules added.
* `betting_ml/tests/test_e11_24_target6_ext_copy_views.py` — new, 12 tests, all RED-proven.

---

# E11.24 — the `lineup_monitor` audit-INSERT lever (2026-08-06)

**Status: CODE-READY, NOT DEPLOYED.** Deliberately scoped that way — the `dev`→`main` deploy is
an OPERATOR step for the 8/7 quiet window, **after** the target-6 T+1 soak read confirms target 6
is clean. INC-36: never stack a second serving-adjacent deploy mid-soak. The census cuts per
FAMILY, so this lever measures independently of target 6 and building it now cannot corrupt the
target-6 reading.

## The waker

`scripts/lineup_monitor.py` wrote its audit record with an `INSERT INTO
baseball_data.config.pipeline_run_log` on every triggering tick (`:634` and `:653` pre-change —
the SUCCESS and FAILED paths). E11.20 phase-2a had already made the SUCCESS insert *conditional*
(a quiet tick skips it), on the reasoning that **"the `lineup_monitor_job` it fires runs
dbt/predict on Snowflake anyway, so the session is already being paid for."**

That reasoning had the causality backwards, and the census says so:

## Pre-merge baseline — `report_e11_24_wake_census.py --days 12`, run 2026-08-06 14:41 UTC

Family `lineup_monitor audit INSERT`, per UTC day, `executions/waits`:

| 07-25 | 07-26 | 07-27 | 07-28 | 07-29 | 07-30 | 07-31 | 08-01 | 08-02 | 08-03 | 08-04 | 08-05 | 08-06\* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 7/6 | 8/7 | 8/6 | 7/7 | 9/8 | 7/7 | 9/5 | 10/10 | 7/6 | 4/4 | 9/9 | 10/10 | 1/1 |

\*08-06 partial (`query_history` lag 13 min; the 14-23 band had barely opened).

* **Trailing 10 full days (07-27 → 08-05): 80 executions, 72 provisioning waits.** This reproduces
  the PM's cited "72 waits/10d" **exactly**.
* **Wake efficiency ≈ 90%** — essentially every audit INSERT queued on provisioning, i.e. the
  warehouse was *suspended* when it fired. The INSERT is not riding a warm warehouse; it is
  **buying the resume**.
* **Executions HOLD and waits HOLD** across the whole window ⇒ by the instrument's own reading
  rule this is *"STILL FIRING — a real waker"*, not pre-flip residue and not a dead caller.
* **All 86 waits are in the 14-23 band** — zero in 00-07, zero in 08-13. The legacy Snowflake
  task-DAG procs also write `pipeline_run_log` but contribute **no waits in this window**, so the
  family is effectively 100% this monitor.

## Does removing it just SHIFT the resume to the dbt step?

That is the standing roadmap caveat, and it deserves a real answer rather than a dismissal. The
baseline gives **suggestive evidence against it, not proof**:

The `6 lineup/starter CTAS` family — the dbt work `lineup_monitor_job` fires moments *after* the
audit INSERT — **pays its own provisioning waits on the same days** (71 waits in the 14-23 band;
6–10 on most days). If the audit INSERT's resume were covering the dbt step, that step would show
≈0 waits. It doesn't ⇒ the warehouse re-suspends in between and these are **two separate resumes**,
so deleting the first should delete a resume rather than relocate it.

⚠️ Hedged deliberately: that CTAS family also contains daily-job runs, and the 14-23 band holds
other work. **Only the post-flip per-day census settles it.** What is certain either way: a
guaranteed resume on a path that needs none is gone.

## The change

* **Sink → DynamoDB**, the same `credence-prod-serving-cache` table (`pk="ops"`) that already holds
  the monitor's state (`lineup_monitor#`) and branch-2 retry counter (`lineup_retry#`) — the
  direction `lineup_monitor_state` is headed anyway. No new bucket, **no new IAM grant** (the
  instance-profile role already has DynamoDB RW here), no new credential path. Item key
  `sk = lineup_audit#{run_date}#{run_ts}`, append-only, same columns as the old row.
* **Both** the SUCCESS and the FAILED paths move. The old failure path opened a Snowflake session
  ("a failure is worth a wake") — the wrong dependency in both directions: a diagnostic write
  should not need the warehouse, and a Snowflake outage is a plausible *cause* of the failure being
  recorded, so that path lost exactly the records that matter most.
* **The audit is unconditional again.** A Dynamo put costs no resume, so there is no longer a
  reason to drop the quiet-tick record — the log regains "every fire is accounted for", the
  property phase-2a had to trade away.
* **`_sf_cursor` deleted.** The invariant hardens from *lazy* ("a session only on a triggering
  tick") to **never** — in S3 mode `get_connection()` is now unreachable. The conditional version
  was precisely the loophole the census billed us for.
* **Explicit `conn.commit()` on the Snowflake path.** That commit used to ride along with the audit
  INSERT; without it the flag-OFF **rollback** path would silently stop recording triggers in
  `lineup_monitor_state`. A rollback lever that is itself broken is worse than no lever.

## INC-27 consumer grep — CONFIRMED (repo, not the DAG)

`baseball_data.config.pipeline_run_log` is **write-only** from this script. Every
`SELECT … FROM pipeline_run_log` in the repo is either a **human runbook query**
(`scripts/daily_run.md` ×2 — both updated by this change) or a **historical phase-5 acceptance
`COUNT(*)`** (`plan_specs/phase_5/…yaml`, `project_context.md`). Searched string literals across
`.py/.sql/.md/.yml/.yaml/.sh/.json/.ts/.tsx`, not just the dbt manifest:

* **No serving reader** — nothing in `app/backend/`.
* **No dbt model** — no hits under `dbt/`.
* **No sensor/op reader** — the single hit in `pipeline/` (`lineup_monitor_sensor.py:45`) is a
  *comment* describing the historical wake, not a read.
* The DynamoDB migration note at the top of `lineup_monitor.py` is about the **state** table
  (`lineup_monitor_state`) — a different table, a different migration. Not conflated.
### ⚠️ CORRECTION (2026-08-06, operator-run `SHOW TASKS IN ACCOUNT`)

The first draft of this section claimed *"the table stays — the legacy task-DAG procs are separate
writers — so even an unknown external reader degrades gracefully."* **That is false, and the live
task inventory says so:**

| Task | Schedule | Predecessors | State |
|---|---|---|---|
| `TASK_SAVANT_INGESTION` | `CRON 0 8 * * *` | — (**ROOT**) | **suspended** (`USER_SUSPENDED`, 2026-04-30) |
| `TASK_STATSAPI_SCHEDULE` | — | `TASK_SAVANT_INGESTION` | started |
| `TASK_ODDSAPI_EVENTS` | — | `TASK_STATSAPI_SCHEDULE` | started |
| `TASK_ODDSAPI_ODDS` | — | `TASK_ODDSAPI_EVENTS` | started |
| `TASK_GITHUB_ACTIONS_TRIGGER` | — | `TASK_ODDSAPI_ODDS` | started |
| `TASK_LINEUP_MONITOR` | `CRON 0 * * * *` | — | **suspended** (`USER_SUSPENDED`, 2026-04-30) |

The four `started` tasks carry **no schedule of their own** — they are purely predecessor-driven,
and their root has been suspended since 2026-04-30. **A child task cannot fire while its root is
suspended**, so the whole DAG is dead and none of those procs have written `pipeline_run_log` in
over three months. `scripts/lineup_monitor.py` is the **sole remaining writer**.

Two consequences, in opposite directions:

* **Safer.** A table with one writer has a far smaller plausible-reader surface than one with six,
  and post-change `pipeline_run_log` has **no writer at all**.
* **No fallback.** The graceful-degradation argument is void — the repo grep plus the operator's
  Snowflake-side reader check are now *the whole of the evidence*, not a belt beside braces.

⭐ It also **sharpens the post-flip prediction**: the census family should read a **hard zero**, and
any non-zero is a finding rather than proc residue.

*(Out of scope but worth logging: `pipeline_run_log` becomes a fully dead table after this merge —
a cleanup candidate for a later story, which would need its own INC-27 pass before a DROP.)*

### Operator reader check — results and the self-match trap

⏭️ **The one check a repo grep structurally cannot make** is a Snowflake-side reader outside the
repo (a view, a task, an external dashboard). Run 2026-08-06:

* **Tasks:** the inventory above. No task *reads* the table — every definition is a bare
  `CALL proc_*()`, and the procs write it.
* **`query_history` (30d):** one identity only — `DBT_RW / ACCOUNTADMIN`, **43 queries**.

⚠️ **Those 43 are almost certainly an instrument self-match, not readers.** The probe filtered on
`query_text ILIKE '%pipeline_run_log%' AND ILIKE '%select%'` — and **this very census script**
(plus `report_sf_cost_flips_after.py`) embeds the literal `'%pipeline_run_log%'` inside its
`FAMILY_CASE` classifier, which is a `SELECT`. `DBT_RW/ACCOUNTADMIN` is exactly the identity those
scripts connect as (`.env`), including the baseline run recorded above. A grep for a table NAME
finds the tools that *classify* the table as readily as the tools that *read* it.

**The decisive query matches the FROM clause, not the mention:**

```sql
SELECT to_char(start_time,'YYYY-MM-DD HH24:MI') AS ts, user_name, warehouse_name,
       left(regexp_replace(query_text,'\\s+',' '), 200) AS q
FROM snowflake.account_usage.query_history
WHERE start_time >= dateadd(day,-30,current_timestamp())
  AND regexp_replace(query_text,'\\s+',' ') ILIKE '%from baseball_data.config.pipeline_run_log%'
ORDER BY start_time DESC LIMIT 50;
```

**RESULT (operator-run 2026-08-06): 3 rows in 30 days — all ad-hoc, none automated. INC-27 CLOSED.**

| TS (UTC) | User | WH | Query |
|---|---|---|---|
| 07-27 12:55 | `DBT_RW` | `COMPUTE_WH` | `select task_name, convert_timezone('UTC',run_ts), status … where run_ts >= dateadd('hour',-10,current_timestamp()) order by run_ts desc limit 40` |
| 07-16 18:11 | `DBT_RW` | `COMPUTE_WH` | `select task_name, max(run_ts) as last_run, count(*) … dateadd('hour',-30,current_timestamp) group by 1 order by 2 desc` |
| 07-16 18:04 | `DBT_RW` | `COMPUTE_WH` | `select run_ts, status, rows_affected … where task_name='lineup_monitor' and run_ts >= '2026-07-16 12:00:00' order by run_ts` |

⭐ **The SHAPE is the evidence, not the count.** Four independent tells, any one of which rules out
an automated reader:

1. **A hardcoded same-day literal** — `run_ts >= '2026-07-16 12:00:00'`, run at 18:04 on 2026-07-16.
   No scheduled job hardcodes today's date. This one is decisive on its own.
2. **Three different query shapes** — different column lists, different windows (`-10h`, `-30h`, a
   literal). A scheduled reader emits *byte-identical* text every fire; that is exactly the
   property the wake census relies on to classify by query shape.
3. **Clustered, not cadenced** — 2 distinct days out of 30, two of them **7 minutes apart**. An
   automated reader produces a regular cadence; this is a human/session sitting down twice.
4. **Exploratory idioms** — `limit 40`, `group by task_name order by last_run desc` ("what has run
   lately?"). Diagnostic sweeps, not a production read.

The dates corroborate: **2026-07-16 is the E11.20-COST measurement day** (the audit that overturned
the "reads are the burn" premise) and **2026-07-27 falls in the E11.24 census window** — i.e. these
are prior cost-audit sessions running the runbook query in this very file, which is the behaviour
that produced this story. Nothing serving, nothing scheduled, nothing in an app.

**Views:** the corrected account-wide query returned **0 rows**. No view reads the table.

⚠️ **What these three rows DO establish is a live documentation risk**, and it is the reason the
`daily_run.md` note is written as loudly as it is: this query is the **natural first reach during a
cost or freshness audit**, it has been reached for twice in the last month, and after this merge it
returns an **empty result** — which a session could easily misread as "the pipeline is down". The
runbook now says plainly that an empty `pipeline_run_log` is the expected healthy state and names
both reasons (the DAG suspended 2026-04-30; the monitor's audit moved to DynamoDB).

**Views** (the original query named a non-existent `table_type` column; this is the corrected form,
and it covers every database rather than just `baseball_data`):

```sql
SELECT table_catalog, table_schema, table_name
FROM snowflake.account_usage.views
WHERE deleted IS NULL AND view_definition ILIKE '%pipeline_run_log%';
```

## Guards — `betting_ml/tests/test_lineup_monitor_s3_mode.py`

Behavioural where it can be (the script imports cleanly in the fast gate — boto3/duckdb are
imported inside functions — so the audit path runs for real against a fake Table), source-inspection
only where the property being guarded is structural.

**All 8 new/changed guards RED-proven** against deliberately-broken source: restoring the SF audit
INSERT · re-adding a lazy `_sf_cursor` · colliding the audit sk prefix with the state prefix ·
making the sk fixed-per-day · making the audit write raise instead of fail open · dropping the
SF-path commit · passing explicit AWS keys to boto3 · dropping `rows_affected`. Each break turned
exactly the intended guard red.

Two worth calling out:

* **`test_audit_sk_prefix_cannot_collide_with_the_state_query`** is a **correctness** guard, not a
  cost one. `_already_triggered_dynamo` reads state with `begins_with(_STATE_SK_PREFIX + date)` on
  the *same* `pk`. A colliding audit prefix would return every audit row as an already-triggered
  **game** — the monitor would then skip real games. Silent and slate-wide if wrong.
* **`_main_code()` strips comment lines before counting call sites.** INC-38's prose-cannot-satisfy
  lesson, and it fired for real during this build: the explanatory comment *"so `get_connection()`
  is unreachable"* made the call-site count read 2. A source-inspection assertion that reads
  comments measures the documentation, and it breaks both ways — a comment can equally make a
  deleted call site look present.

## Files

* `scripts/lineup_monitor.py` — `build_audit_item` (pure) + `_record_audit_dynamo` (fail-open);
  both SF audit INSERTs removed; `_sf_cursor` deleted; explicit SF-path commit.
* `betting_ml/tests/test_lineup_monitor_s3_mode.py` — 8 new/strengthened guards, all RED-proven.
* `scripts/daily_run.md`, `project_context.md` — the two human runbook queries repointed.
* `scripts/report_e11_24_wake_census.py` — comment only: how to read this family post-flip.

---

# Target-6 successor — the incremental family, scoped 2026-08-08

The 08-07 T+1 read found target 6's wake had **moved one statement downstream** rather than
vanished, and named five writers: the `eb_starter_posteriors` / `eb_batter_posteriors_raw` MERGEs,
the `feature_pregame_game_features(_raw)` incrementals, and the `feature_pregame_lineup_state`
SCD-2 UPDATE. This section is that family's per-writer analysis, its pre-merge baseline, and what
it changes about the plan.

## The headline: the flippable subset is not the waker

Per-statement, 14-23 UTC tick band, `COMPUTE_WH`, taken on MONITOR_WH 2026-08-08 (`execs/waits`):

| statement | 07-29 | 07-30 | 07-31 | 08-01 | 08-03 | 08-04 | 08-05 | 08-06 | 08-07 |
|---|---|---|---|---|---|---|---|---|---|
| `eb_starter_posteriors` MERGE | 24/0 | 24/0 | 159/0 | 33/0 | 24/0 | 40/0 | 32/0 | 8/1 | **24/3** |
| `eb_batter_posteriors_raw` MERGE | 24/0 | 24/0 | 34/0 | 33/0 | 24/0 | 40/0 | 32/0 | 8/1 | **24/3** |
| `feature_pregame_lineup_state` UPDATE | 15/0 | 15/0 | 20/0 | 21/0 | 15/0 | 25/0 | 20/0 | 5/1 | **15/3** |
| `feature_pregame_game_features_raw` | 38/0 | 33/0 | 44/0 | 45/0 | 33/0 | 56/1 | 44/0 | 11/0 | **33/0** |
| `feature_pregame_game_features` | 54/1 | 33/0 | 44/0 | 45/0 | 33/0 | 55/0 | 44/0 | 11/1 | **33/0** |

Read the 08-07 column — the one clean fully-post-target-6 day. All of the family's tick-band wake
sits on three writers (3 + 3 + 3), and the two `feature_pregame_game_features*` incrementals took
**zero**. Statement-level confirmation, same day:

```
MERGE   merge into baseball_data.betting.eb_starter_posteriors …        3 waits
MERGE   merge into baseball_data.betting.eb_batter_posteriors_raw …     3 waits
UPDATE  UPDATE baseball_data.betting_features.feature_pregame_lineup_state …  3 waits
INSERT  INSERT INTO tmp_starter_ip_signals_incoming …                   1 wait   (4b scd2, other family)
```

⭐ **Why the wake spreads evenly across three statements rather than landing on one.** On the
Snowflake target these models have **no `ref()` edges between them** — every `{% else %}` branch
reads its own `lakehouse_ext` table, so the whole DuckDB dependency graph disappears and dbt runs
the eight tick nodes in parallel across threads. Whichever compute statement is scheduled first
buys the resume; over nine ticks that is a race, not a fixed order. The practical consequence is
the one that matters for sequencing: **removing a subset of the compute statements does not remove
the wake, it just re-rolls which of the survivors pays it.** This family has to be flipped as a
unit or not at all — which is the same lesson the T+1 read taught one statement upstream.

⚠️ **Day-sanity caveat (INC-37).** 08-07 totalled 1,446 `COMPUTE_WH` executions, *below* the
1,536–3,480 baseline band, so the wait **magnitudes** for that day may understate. The
**composition** — which statements wait and which do not — is far more robust to a volume dip and
is what the verdict rests on. Re-read at the Sun 08-09 T+3 before quoting the magnitudes.
08-06's waits are dominated by `ci_betting.*` (the `CI on the prod WH` family) — that was the
target-6 merge-day release train, not a tick waker.

## Per-writer verdicts

| writer | wakes `COMPUTE_WH`? | SF consumer needing materialization? | verdict |
|---|---|---|---|
| `feature_pregame_game_features_raw` | measured **no** (0 waits 08-07) | no | **FLIPPABLE NOW** |
| `feature_pregame_game_features` | measured **no** (0 waits 08-07) | no | **FLIPPABLE NOW** |
| `eb_starter_posteriors` | **yes** (3) | content-divergent + live SF-only daily reader | **READER-GATED** |
| `eb_batter_posteriors_raw` | **yes** (3) | content-divergent + live SF-only daily reader | **READER-GATED** |
| `feature_pregame_lineup_state` | **yes** (3) | SF is the *master*, not a copy | **NOT FLIPPABLE** |

### Flippable: `feature_pregame_game_features` + `_raw`

Both Snowflake branches are `select * from baseball_data.lakehouse_ext.<self>` — pure ext-table
copies, all assembly in the DuckDB branch. Content-neutrality was **measured** (MONITOR_WH,
2026-08-08), not inferred from the shape:

* rows **26,969 = 26,969**, with **zero** `game_date`s differing in count, on both models;
* columns **756 = 756** and **790 = 790**, with **zero** `data_type` mismatches — so the INC-19
  NUMBER↔FLOAT surface this model is the canonical victim of has already converged, and a view
  removes it outright (no stored type left to drift, and no DROP+rebuild obligation);
* values agree on **every** game inside the 7-day incremental window; **77 of 26,969 game_pks
  (0.29%)** differ outside it — precisely the drift the model header already anticipates ("the
  weekly Sunday `dbtf build --full-refresh` net corrects any drift"). A view converges that
  permanently, toward the same parquet the served `--s3` path already reads.

INC-27 reader sweep by **grep, not the DAG**: every `ref()` to either model is in a DuckDB branch
(the wrapper and `feature_league_contact_baseline` both read their *own* ext table on Snowflake);
`app/backend/routers/picks.py` reads through `lakehouse_query` (DuckDB over S3), never Snowflake;
`predict_today`'s aux reads are dead under `W7B_LAKEHOUSE_S3` / `W7B_INTRADAY_S3`, both enforced in
`env.required`; the remaining raw-SQL readers are the offline training loaders
(`betting_ml/utils/data_loader`) and bake-off scripts. None needs materialization.

**Pre-registered control, measured rather than assumed.** A view re-evaluates the external-table
scan on every read, and `data_loader.load_features` does a `SELECT f.*` over all history. Forcing
all 756 columns across 13,924 rows (2021+, result cache off): native table **0.17–0.51s**, ext-table
view **0.73–1.04s** — ~2–4× slower but sub-second absolute. The active-minutes risk is real and
bounded; it does not change the verdict.

### Reader-gated: the EB posteriors

Same `select * from lakehouse_ext.<self>` shape, so they *look* flippable. Two reasons they are not:

1. **`incremental_strategy='merge'` never deletes**, so the Snowflake table is a permanently
   accumulating superset of the parquet. Measured 2026-08-08: `eb_starter_posteriors` 48,908 vs
   48,905 (19 divergent dates, in **both** directions — the history predates the DuckDB rebuild);
   `eb_batter_posteriors_raw` 484,934 vs 484,902 (4 divergent dates, all recent, SF-heavy). The
   extra rows are ghosts of superseded lineup snapshots. A flip therefore *changes content*, which
   is exactly the precondition target 6 relied on and this pair does not satisfy.
2. **A live Snowflake-only consumer**: `update_player_posteriors_op` runs daily and reads both
   tables from Snowflake **even under `--s3`** (its `--s3` flag routes only the PA substrate; the
   EB role reads stay on the warehouse by design). So the content change lands on a daily serving
   input.

The clean sequencing is therefore: **repoint `update_player_posteriors`'s EB reads to S3 first,
then flip the pair as its own change with its own soak.** That also removes two SF reads on its own
merit. Doing it in the other order takes serving risk for no measured benefit.

### Not flippable: `feature_pregame_lineup_state`

Not a lakehouse passthrough in either direction. **Snowflake is the master** — written by
`scripts/backfill_lineup_state_scd2.py`'s SCD-2 `UPDATE`/MERGE, invoked per tick from
`lineup_intraday_s3_feature_rebuild` — and S3 is the *downstream* mirror produced by
`export_w8b_precursors_to_s3`. There is no table→view flip available to it; four dbt models read it
via `source()`. Its lever is the already-carded `scd2_upsert` Delta port.

## What shipped, and the recommendation

Shipped code-ready (⛔ not deployed): the two `feature_pregame_game_features*` Snowflake branches
flipped `incremental` → `view`, the now-inert `is_incremental()` window removed, guard
`betting_ml/tests/test_e11_24_pregame_features_are_views.py` (9 assertions; **7 deliberate source
breaks each turned exactly the intended one red**, including a clause pinning that the reader-gated
EB pair was *not* swept into the flip).

**Recommendation: do not spend a soak slot on this flip alone.** It is measured at ~zero wake
reduction, so shipping it under one-flip-per-soak would consume the slot the real successor needs
while the tick keeps waking the warehouse — the exact shape of progress-without-movement the T+1
read just caught. Its benefits are genuine but not cost: it closes the history-drift class, retires
the INC-19 DROP+rebuild obligation on the repo's canonical victim, removes ~690 writes/10d against
a 756/790-column serving table, and removes an INC-25-class ordering constraint. Land it as a free
rider on the next flip that needs a soak anyway, and put the session budget on the EB reader
repoint, which is where the measured wake actually is.

---

# TARGET-6 SOAK — T+3 CLOSE-OUT READ (2026-08-09/10) ✅ CLEAN

Read from the LAPTOP on `MONITOR_WH` (`report_e11_24_wake_census.py --days 10 --warehouse COMPUTE_WH`
+ `check_w11_tail_coverage.py`). `best_alpha=0` — no bet rides on any of this.

## GATE 0 — volume sanity (INC-37): PASSED, no slip

Executions/day vs the 1,536–3,480 band. **No day in the window is an outage day**, so the SLIP RULE
does not fire and every composition below is trustworthy.

| | 08-03 | 08-04 | 08-05 | **08-06** ⬅ flip | 08-07 | 08-08 | 08-09 |
|---|---|---|---|---|---|---|---|
| executions | 1,536 | 1,793 | 3,480 | 2,184 | 1,712 | 3,172 | 3,163 |

Pre-flip reference = 08-03/04/05 (07-29 and 07-31 are the contaminated baselines; 08-06 is the flip
day itself and is excluded from both sides).

## THE THREE AGREEING SIGNALS — all confirmed

**(1) + (2) executions HOLD while waits → 0** (Table 4b, the per-day × family cut — the only cut a
verdict may be quoted from):

| family (execs/waits) | 08-03 | 08-04 | 08-05 | 08-06 | 08-07 | 08-08 | 08-09 |
|---|---|---|---|---|---|---|---|
| `6a umpire chain` | 34/12 | 41/14 | 71/20 | 46/**0** | 32/**0** | 62/**0** | 65/**0** |
| `6 lineup/starter CTAS` | 29/6 | 43/6 | 87/8 | 47/**0** | 29/**0** | 75/**0** | 97/**0** |

**(3) the objects ARE views** — read directly from `information_schema.tables` rather than inferred
from DDL history, which is the stronger form of the same signal (a view that got reverted would show
here and not there):

| object | type | last_altered |
|---|---|---|
| `BETTING.STG_STATSAPI_UMPIRE_GAME_LOG` | **VIEW** | 2026-08-09 15:16 |
| `BETTING_FEATURES.FEATURE_PREGAME_UMPIRE_FEATURES` | **VIEW** | 2026-08-09 15:16 |
| `BETTING_FEATURES.FEATURE_PREGAME_STARTER_FEATURES` | **VIEW** | 2026-08-09 15:16 |
| `BETTING_FEATURES.FEATURE_PREGAME_LINEUP_FEATURES` | **VIEW** | 2026-08-09 15:16 |

(The `DEV_*` schema copies are stale June base tables — that is the `dev` dbt target, not prod.)

## THE MAGNITUDE — and the honest net

**Target 6's own two families: 22.0 → 0.0 provisioning waits/day** (mean of 18/20/28 pre vs 0/0/0
post). That is the lever, and it is complete.

⚠️ **A SECOND LEVER LANDED INSIDE THIS SOAK WINDOW.** PR #637 (the `lineup_monitor` audit INSERT →
DynamoDB) merged to `main` at **2026-08-06 14:44 UTC** — the same day as target 6, not the 8/7 quiet
window its own record anticipated. It is nonetheless **separately attributable**, because the census
cuts per FAMILY:

| family (execs/waits) | 08-03 | 08-04 | 08-05 | 08-07 | 08-08 | 08-09 |
|---|---|---|---|---|---|---|
| `lineup_monitor audit INSERT` | 4/4 | 9/9 | 10/10 | — | — | — |

**7.7 → 0 waits/day.** Here executions AND waits both go to zero, which is normally the *dead-caller*
shape — but for a DELETE-the-statement lever it is the intended one (the INSERT no longer exists).
The dead-caller reading is ruled out by a control: the `6 lineup/starter CTAS` family, fired by the
**same** `lineup_monitor_job` moments later, held its executions at 47/29/75/97 across those days.
The monitor is still ticking; only its audit write is gone.

**Account-wide, the two levers together:**

| instrument | pre (08-03/04/05) | post (08-07/08/09) | Δ |
|---|---|---|---|
| provisioning waits/day | 53.3 | 45.0 | **−15.6%** |
| … excluding the 00-07 overnight band¹ | 48.7 | 34.0 | **−30.2%** |
| resumes/day | 34.0 | 30.3 | −11% |

¹ the overnight band is CI + Snowsight + the API Lambda (#679), none of it pipeline work, and it is
dev-activity-dependent — so the pipeline-band figure is the one that reflects these levers.

⭐ **WHY 30 REMOVED WAITS ONLY BOUGHT ~8:** the `other` family rose from 16.3 to 32.7 waits/day
(+16.4) across exactly the same boundary. **This is #679's wake-promotion thesis reproduced on an
independent read** — the wake was not deleted, it was inherited by the next warehouse-occupying
statement in the chain. Measured directly on the statement itself:

| statement (execs/waits) | 08-02 | 08-03 | 08-04 | 08-05 | **08-06** | 08-07 | 08-08 | 08-09 |
|---|---|---|---|---|---|---|---|---|
| `merge … eb_{starter,batter}_posteriors*` | 38/**0** | 32/**0** | 44/**0** | 52/**0** | 48/**14** | 32/**9** | 44/**13** | 38/**10** |

Six days at literally zero waits, then 9–14/day from the exact flip date with executions unchanged.
**#675 is therefore sized at ~11.5 waits/day and is the single largest waker on the board** — this
read confirms #679's upward resizing (11–13/day, not the older "9 tick-band waits") on fresh data.

## Serving no-regression — CLEAN, and SF-free

`check_prediction_coverage.py` on the three post-flip slates: **100% coverage, exit 0, and
`feature_store=15 / intraday_assembly=0 / intraday_fallback=0` on every one** (mean
`feature_coverage_score` 0.967 / 0.989 / 0.967). No degraded serving anywhere in the soak window.

## W11 tail — OK, and the one BUILD_GAP is the documented cadence, not INC-37

| slate | umpire | weather | public_betting |
|---|---|---|---|
| 08-06 | OK 11/11 | OK 11/11 | OK 11/11 |
| 08-07 | OK 15/15 | OK 15/15 | OK 15/15 |
| 08-08 | OK 15/15 | OK 15/15 | OK 15/15 |
| 08-09 | BUILD_GAP 0/15 | BUILD_GAP 0/15 | OK 15/15 |

⚠️ **Do not read 08-09 as an incident.** `ingest_weather` (s7, 12:50 UTC) and `ingest_umpires --date
today` (s8/s17, 12:0x–16:39) both land **after** the ~12:40 UTC `lakehouse_w11_nightly_op` that
consumes them, so those two blocks are only ever judged on the PRIOR slate — which is exactly why
`check_w11_tail_coverage_op` judges them that way. The 08-09 slate is filled by the 08-10 build,
which had not run at read time (04:34 UTC 08-10). The **discriminator that settles it**: 08-06/07/08
all read 15/15 today, so nothing is persistently broken — a genuine INC-37 gap would still be 0/15
on those. And `public_betting`, the one block validly judged same-day, is OK 15/15 on 08-09.

## VERDICT — the target-6 soak is CLOSED and CLEAN

Wake reduction held on all three signals; no serving regression; W11 tail healthy. **Phase 1 (#675 +
#662) is unblocked.**

## NOT VERIFIED — do not inherit these as settled

* **Wake ↓ is not credit ↓.** Every figure here is a resume/wait COUNT. The bill only moves when the
  warehouse actually stays suspended for long stretches (E11.20-COST). No credit figure is claimed.
* **Active-minutes are still measured with the polluted instrument** (109/111/123 → 91/96/126). The
  #679 `warehouse_size IS NOT NULL` correction was deliberately NOT retrofitted mid-soak to preserve
  comparability with this soak's own T+0/T+1 readings. **That block is now lifted — apply it, and
  re-check the weather-poller credit (167→141), before quoting any awake-time number again.**
* **Wake promotion remains a strong inference, not a controlled experiment** (a clean test needs an
  un-flip). Its support is unchanged and now doubly measured.
* **No box run this session.** `ssm:SendCommand` is denied to `baseball-access-user`; every box-side
  confirmation is an operator step.

---

# PHASE 1 — #675 + #662 PROMOTION PREP (2026-08-09/10)

## The parity gate — CLEAN on four dates

`parity_check_eb_reader_repoint.py --season 2026` on `MONITOR_WH` (soak-safe), with
`LAKEHOUSE_DELTA_W1=cutover`:

| structure | SF vs S3 | result |
|---|---|---|
| batter cold-start priors | 616 vs 616 | ✅ exact |
| starter cold-start priors | 330 vs 330 | ✅ exact |
| bullpen cold-start priors | 641 vs 641 | ✅ exact |
| role map 08-06 / 08-07 | 110/110, 129/129 | ✅ exact |
| role map 08-08 / 08-09 | 125/125, 27/27 | ✅ exact |

**`only_in_sf` is EMPTY on every structure** — no player loses a cold-start seed. The gate was run on
the story's two prescribed dates and then again on the two freshest slates, so the result does not
rest on one lucky pair. Pre-flip baseline for the runtime gate: `EB_STARTER_POSTERIORS` and
`EB_BATTER_POSTERIORS_RAW` are both `BASE TABLE` (transient), 48,919 / 485,444 rows.

## #675's safety analysis re-derived independently (INC-27: grep the repo, not the DAG)

Confirmed: the only `ref()`s are at `feature_pregame_lineup_features:598` and
`feature_pregame_starter_features:599`, both **before** those models' `{% else %}` (L868 / L984) —
i.e. inside the DuckDB branch, so the Snowflake target never resolves them. The `--s3` precondition
is mechanically enforced, not merely documented: `W7A_LAKEHOUSE_S3` is in **both** `env.required`
(deploy gate) and `monitor_health.REQUIRED_INTRADAY_FLAGS` (pinned `== "1"`, paged).

**One addition #675 did not list — and it is a WRITER, not a reader.**
`betting_ml/scripts/eb_priors/compute_starter_posteriors.py` and `compute_lineup_posteriors.py`
`MERGE INTO baseball_data.betting.eb_{starter,batter}_posteriors*` — the exact objects being flipped.
A `MERGE INTO` a view would fail. **They are safe: neither is referenced by any op, job, service,
crontab or workflow** (grepped across `pipeline/`, `services/`, `scripts/`, `.github/`) — they are
A2.11-superseded standalones. ⚠️ Recorded because a *hand-run* of either after the flip will now
fail, and the failure would look mysterious. Reader-side analysis is about consumption spanning the
accumulated history; **the writer side needs its own sweep, and "no reader blocks it" does not
imply "no writer does."**

## ⚠️ A FALSE PREMISE IN #675, CORRECTED — the "documented ≠ actually set" class, in a comment

`eb_starter_posteriors.sql` claimed `predict_today`'s `_FRESHNESS_QUERY` was *"already DEAD in prod
(`W8B_FRESHNESS_S3=1` routes the probe to `_FRESHNESS_QUERY_S3`) and survives only as a rollback."*

**It is not dead.** Measured on `MONITOR_WH`: that exact query shape executed on `COMPUTE_WH` on
**08-02, 08-05, 08-08 and 08-09** (1×/day, 0 waits). `W8B_FRESHNESS_S3` is absent from
`env.required` and `.env.example` documents it as `0`, so nothing forces it on and the observed
traffic says it is off. This is `W7B_LAKEHOUSE_S3`'s lesson recurring inside a *code comment*, where
it is more dangerous than in a doc: a future session reading it would conclude the last SF reader is
gone and take `enabled=false`.

**The flip is safe regardless, and for a reason that does not depend on the flag** — which is the
part worth carrying forward. The probe is date-scoped AND **ghost-immune**: its probe side is
*today's current probables*, and a ghost row by construction belongs to a **superseded** probable
that is no longer in that set, so a ghost can never satisfy the LEFT JOIN. `starter_missing` is
identical against the table and against the view. Reasoning corrected; no code change needed.

## The #662 ↔ #675 guard collision — resolved, and deliberately not the tempting way

The two PRs have **zero file overlap**, so git merges them cleanly and *then* the suite goes red.
Reproduced live here: stacking #675 on #662 turned
`test_the_reader_gated_writers_were_not_flipped_along_with_them` RED for both EB models — the guard
doing precisely its job (it exists to stop a sweep-in, and its own docstring names #675 as the
sanctioned way out).

**Deleted the `NOT_FLIPPABLE` dict AND its `@parametrize` consumer.** Emptying the dict was the
tempting edit and is the wrong one: `@parametrize` over an empty mapping collects zero cases. That is
not a hypothetical — measured during the red-proof, an emptied registry makes the file report
**"1 passed, 3 skipped"**, i.e. three guards silently stop asserting and nothing looks wrong.

⭐ **Hardening added for that exact reason:** `test_the_model_registry_is_not_empty` asserts
`EXT_COPY_VIEW_MODELS` is non-empty, so the vacuous edit cannot be made silently by the next session
(#690's "a guard that iterates matches must assert non-vacuity"). RED-proven both ways, with the
mutation asserted to land before the run (#682's false-RED-proof lesson).

## Gates

* Parity: **CLEAN**, 4 dates, zero `only_in_sf`.
* Targeted local suites: **28 passed** (`test_e11_24_eb_reader_repoint.py` 20 +
  `test_e11_24_pregame_features_are_views.py` 8).
* RED-proofs: emptied registry → red on the new clause; `eb_starter_posteriors` reverted to
  `incremental`+`merge` → red on exactly 2 clauses (narrow, not wide).
* CI: **#662 13/13 green · #675 13/13 green**, both brought current with `dev` (no conflicts on any
  code file; the one `story_prompts.md` conflict was a doc-record block `dev` already supersedes).
* ⛔ `dbt build --select state:modified+` NOT run — its CI target is `COMPUTE_WH` and it would
  contaminate the census. ⛔ `check_served_prediction_integrity.py` NOT run, same reason.

---

# PHASES 2 & 3 — SEQUENCING CORRECTED (#682 BEFORE #693)

The story's working assumption was *#693 then #682, each in its own window*. **Verified against the
PRs themselves, that order is inverted.** Two measured facts:

1. **#693 is STACKED ON #682** — `e11.24-target-3` is a git ancestor of `e11.24-posterior`
   (confirmed with `git merge-base --is-ancestor`). #693's branch already contains #682's three
   repointed scripts and its guard suite; #693's own body says *"Merge #682 first and this PR's diff
   collapses to the 6 files below."*
2. **The dependency runs #682 → #693, not the reverse.** #682 leaves the
   `player_sequential_posteriors` freshness entry on `snowflake` — it is one of its three measured
   *blockers*, because that mirror is exported at lk9 while its writer runs ~40 min later (INC-25).
   #693 is the ordering fix **and** the entry flip, which must ship together (guard-pinned). So #682
   alone is safe, and #693-before-#682 would be flipping an entry whose blocker is still in place.

**Classification (the story asked for this rather than an assumption):**

| PR | what it is | gate |
|---|---|---|
| **#682** | read-only MONITOR code — no serving artifact, no dbt model, no flag, no env var | **no soak.** But `check_prediction_coverage` is HALT-tier and unconditional ⇒ 🟥 runtime gate (a real box run) |
| **#693** | a pipeline GRAPH change (adds a fan-out leaf op to two jobs) + the freshness-entry flip | **own window + real-run gate.** Serving-adjacent: it makes the mirror fresh, which moves the served EB as-of prior from 2 days stale to 1 (its own record's side finding). Not a materialization flip, so not a full soak |

## Phase 3's explicit gate — do the repointed guards false-alarm on the S3 read? **No.**

Run from #693's worktree (the repoint is unconditional — no flag — so that checkout *is* the S3
path), SF-free, on three real slates:

* `check_odds_coverage` — 08-07/08/09 all `[OK]`, `odds_coverage_score=1.0000`, `freeze=0`. It also
  demonstrates **FINDING 1's fix working**: the window's LAST day is present and correctly
  classified (08-11 reads `NO_ODDS_YET`, not silently absent) — the un-cast VARCHAR compare would
  have dropped it.
* `check_prediction_coverage` (HALT-tier) — 08-07/08/09 all **100%, exit 0**, `feature_store=15`,
  `intraday_fallback=0`.
* `check_data_freshness` — **not run live**: it still opens Snowflake lazily for its 5 blocked
  entries, which would resume `COMPUTE_WH` and dirty the day that will serve as #675's soak baseline.
  Its verdict parity was already measured by #682's own session on `MONITOR_WH`.

**No false alarm on either fully-repointed guard.** The discrimination that keeps them from crying
wolf (`NO_ODDS_YET` vs `FREEZE`) is intact.

⚠️ **Carry #682's own measurement-interaction warning into the next census:** post-#682,
`check_data_freshness`'s first SF statement becomes `MAX(… player_sequential_posteriors)`, which the
census buckets as `4 player posteriors`. That family will rise ~2/day while `other` falls ~4.5.
**Reading that as "target 4 regressed" would be wrong** — it is the #679 queue again, one family
over.

---

# 🚨 DEPLOY LANDMINE — A STANDING `dev→main` PR CAN SHIP AN EARLIER `dev`, AND EVERY STATUS SIGNAL STAYS GREEN (2026-08-10)

Recorded because it happened during this promotion and cost a real deploy cycle.

The repo keeps a **standing `dev→main` PR open** (it is literally titled "Dev" and is recreated as
soon as `dev` moves ahead). On 2026-08-10 the open one was **#718**. It merged at **05:25:02Z** —
carrying the `dev` that existed *at that moment*, which did **NOT** include #662/#675. The
`Orchestration CD` run for it went **`completed/success`**.

**So every signal a human normally reads said the deploy worked:**

| signal | what it said | what was true |
|---|---|---|
| PR merged | ✅ merged | ✅ merged — but the *wrong* `dev` |
| `Orchestration CD` | ✅ `completed/success` | ✅ genuinely succeeded — it deployed the previous content |
| `gh pr view 718 --json mergeable` | `UNKNOWN/UNKNOWN` | reads UNKNOWN because it is **closed**, not because it is stuck |

⭐ **The `UNKNOWN/UNKNOWN` is the tell, and it is easy to misread as GitHub being slow.** GitHub
returns `UNKNOWN` for a *merged/closed* PR exactly as it does for a not-yet-computed open one. A
retry loop — the correct fix for the lazy-computation case — **spins forever** here and looks like a
GitHub outage. **Check `state` alongside `mergeable`; `MERGED` explains the `UNKNOWN` instantly.**

## THE RULE

⛔ **Never conclude a promotion shipped your change from the PR's merge status or a green CD run.**
Both are true of a promotion that shipped *someone else's* commit. **Verify the CONTENT on `main`:**

```bash
git fetch origin
git show origin/main:<the file your change edits> | grep -c "<the thing you changed>"
git rev-list --count origin/main..origin/dev      # must be 0 when the promotion is complete
```

On #718 the first command printed **0** and the second **8**. On the correct promotion (#720,
merged 05:56:34Z, sha `e348d63e`) they print **1** and **0**. That one grep is the whole difference
between "deployed" and "deployed nothing", and nothing else in the pipeline reports it.

This is the program's **"verify the published artifact, not the build log"** rule (NF-C0e) applied
to a *deploy* rather than to a data artifact — and the same shape as the `W7B_LAKEHOUSE_S3`
documented-but-never-set class: **a state everyone believed, that nobody had read.**

## Sibling: check for an in-flight CD before promoting again

#718's CD had to be `completed` before #720 could be merged safely — two concurrent `deploy.sh` is
**INC-36**, which took the Dagster daemon down for ~10 minutes. Always:

```bash
gh run list --repo charlesclark2/fantasy_baseball --workflow "Orchestration CD" --limit 3 \
  --json status,conclusion,createdAt,headSha \
  --jq '.[]|"\(.createdAt) \(.status)/\(.conclusion // "-") sha=\(.headSha[0:8])"'
```

Every row must be `completed` before merging a promotion PR.

---

# PHASE 1 — STEP A: THE #675/#662 FLIP RUNTIME GATE ✅ PASS (2026-08-10, 17:20–18:10 CDT)

Read from the LAPTOP. Snowflake reads on `MONITOR_WH`; the serving checks are SF-free.
`best_alpha=0` — no bet rides on any of this.

## A1 — all four objects read VIEW ✅

`baseball_data.information_schema.tables`, the same instrument the target-6 close used (stronger
than inferring from DDL history — a reverted view shows here and not there). Pre-flip baseline was
`BASE TABLE` on all four (2026-08-09 15:16).

| object | type |
|---|---|
| `BETTING.EB_BATTER_POSTERIORS_RAW` | **VIEW** |
| `BETTING.EB_STARTER_POSTERIORS` | **VIEW** |
| `BETTING_FEATURES.FEATURE_PREGAME_GAME_FEATURES` | **VIEW** |
| `BETTING_FEATURES.FEATURE_PREGAME_GAME_FEATURES_RAW` | **VIEW** |

## ⭐ A1b — THE FLIP IS DATED 2026-08-10, AND `last_altered` COULD NOT HAVE TOLD US

`last_altered` is refreshed by **every** `create or replace view`, so post-flip it reports the most
recent intraday rebuild (here 22:19 UTC), not the transition. The transition is only visible in the
STATEMENT history, and there it is unambiguous — the `merge` **stops existing**:

| statement (execs/waits) | 08-02 | 08-03 | 08-04 | 08-05 | 08-06 | 08-07 | 08-08 | 08-09 | **08-10** |
|---|---|---|---|---|---|---|---|---|---|
| `merge into … eb_starter_posteriors` | 9/0 | 8/0 | 11/0 | 13/0 | 12/7 | 8/4 | 10/5 | 10/6 | **· gone** |
| `merge into … eb_batter_posteriors*` | 9/0 | 8/0 | 11/0 | 13/0 | 12/7 | 8/5 | 10/6 | 10/6 | **· gone** |
| `create or replace view … eb_*` | 20/0 | 16/0 | 22/0 | 26/0 | 50/0 | 32/0 | 40/0 | 44/0 | 30/**0** |

Combined merge waits **14 / 9 / 11 / 12 per day (08-06→08-09) → 0**, which reproduces the ~11.5/day
sizing the target-6 close-out derived independently. The production transition is legible to the
minute: at UTC hour 10, `drop table if exists "BASEBALL_DATA"."BETTING"."EB_STARTER_POSTERIORS"
cascade` followed by `create or replace view …`. **Every production eb_* statement on 08-10 waited
zero.**

⭐ **This is a DELETE-the-statement lever, so it is judged on PRESENCE, not volume** — the same
shape as #637's audit INSERT, and the reason T+0 can carry a mechanism verdict on a day whose
volume gate fails (below). A merge either exists in the history or it does not; a small slate
cannot fake its absence.

## ⚠️ A1c — THE 39 WAITS THAT LOOK LIKE A REGRESSION ARE THE #720 dbt-BUILD CI

A first cut showed eb_*-touching waits jumping 0 → **39** on 08-10 and read as a serving
regression. It is not. Decomposed by user × UTC hour × schema:

| UTC hr | user | type | n | waits | what |
|---|---|---|---|---|---|
| **05** | `DBT_RW` | SELECT | 42 | **39** | `…count(*) as failures…` against **`baseball_data.ci_betting.eb_starter_posteriors`** |
| 10 | `DBT_RW` | DROP + CREATE_VIEW | 6 | 0 | **the production flip** |
| 12, 13, 19, 20, 21 | `DBT_RW` | CREATE_VIEW | 24 | 0 | intraday rebuilds, now metadata-only |

All 39 are `dbt test` failure-count queries in the **`ci_betting`** schema at 05:xx UTC — the
dbt-Build CI fired by the #720 `dev→main` promotion (merged 05:56Z). They are separable on two
independent axes at once (a different SCHEMA and a different HOUR BAND from production), and the
census's own family classifier already buckets them as `CI on the prod WH` (76/39 on 08-10).
**Production waits are zero.** ⏭️ This is the standing argument for the `CI_WH` backlog item: CI is
now the largest single wait bucket on the board (`CI on the prod WH`: 130/4, 14/1, 64/14, 207/23,
76/39 across the window).

🪤 **The decomposition query that found it initially returned ZERO ROWS** because it filtered
`start_time >= '2026-08-10'` — `start_time` is `TIMESTAMP_LTZ`, so the string boundary prunes in
the SESSION tz and cut everything before **07:00 UTC**, i.e. precisely the 05:xx band where all 39
waits live. This is the documented LTZ boundary-day landmine, and note the failure DIRECTION: it
did not produce a wrong number, it produced an **empty result that reads as "nothing to see"**.
Anchor on `dateadd`/`convert_timezone`, never a date string.

## A2 — serving intact ✅ (SF-free)

* `check_prediction_coverage.py --date 2026-08-10` → **10/10 = 100%, exit 0**,
  `feature_store=10 / intraday_assembly=0 / intraday_fallback=0`, mean
  `feature_coverage_score` **0.9165** (min 0.833).
* `check_intraday_fallback.py --date 2026-08-10` → **morning 10/10** and **post_lineup 5/5** both
  100% `feature_store`, 0 fallback, 0 chronic. (Used as the laptop-visible proxy for A3's
  "post_lineup rows exist"; the Dagit op-status half stays an operator step — `ssm:*` is denied to
  `baseball-access-user`.)
* `check_w11_tail_coverage.py --date 2026-08-09` → **umpire 15/15 OK, weather 15/15 OK,
  public_betting 15/15 OK**, `w11_tail_problem_count=0`. This also retires the target-6 close-out's
  open item — 08-09 read `BUILD_GAP 0/15` there purely because the 08-10 nightly had not yet run,
  and it healed exactly as predicted.

## STEP B, T+0 — recorded, and deliberately NOT quoted for magnitude

**GATE 0 FAILS on 08-10: 1,259 executions against the 1,536–3,480 band.** Two sufficient reasons,
neither of them a defect: `account_usage` high-water at read time was 21:21 UTC (~2.6 h of the UTC
day missing), and the slate is 10 games. Per the slip rule, **no composition figure from 08-10 is
trustworthy** — magnitude is judged at T+1 (08-11) and T+3 (08-13).

What T+0 *does* establish, because it is structural rather than volumetric: **the merge statements
no longer exist**, and production eb_* waits are 0. Whole-day bands for the record —
00-07 **40** (of which the CI 39), 08-13 **16**, 14-23 **9**; the target-6 families stayed dead
(`6a umpire chain` 29/**0**, `6 lineup/starter CTAS` 25/**0**).

### The predicted wake-promotion has not appeared yet — do not book that either

| family (execs/waits) | 08-06 | 08-07 | 08-08 | 08-09 | 08-10 |
|---|---|---|---|---|---|
| `merge eb_*` (REMOVED) | 24/14 | 16/9 | 20/11 | 20/12 | **· gone** |
| `feature_pregame_team_features` | 6/2 | 6/2 | 21/2 | 21/2 | 6/2 |
| `feature_pregame_lineup_state` | 67/1 | 45/5 | 54/7 | 60/8 | 44/4 |
| `feature_pregame_game_features` | 292/4 | 194/0 | 267/4 | 276/2 | 63/0 |

Every successor is flat or DOWN. That is **not** evidence against #679's promotion thesis — the
day is partial and the slate small, which biases exactly this way. Re-read at T+1/T+3 before
concluding anything; the prompt's prediction (~2/day inherited by `feature_pregame_team_features`,
then the `feature_pregame_lineup_state` SCD-2 UPDATE) remains the null to beat.

## STEP B, T+1/T+2 (read 2026-08-13 00:2x UTC) — ✅ #675 HOLDS

**The PRESENCE read, which is the verdict.** `merge into eb_batter_posteriors` and
`merge into eb_starter_posteriors`:

| | 08-03 → 08-09 | 08-10 (T+0) | 08-11 (T+1) | 08-12 (T+2) |
|---|---|---|---|---|
| `merge eb_batter_posteriors` | 8–13 execs/day | **absent** | **absent** | **absent** |
| `merge eb_starter_posteriors` | 8–13 execs/day | **absent** | **absent** | **absent** |
| waits those two carried | **14 / 9 / 11 / 12** (08-06…09) | — | — | — |

Gone on the flip day and gone for three consecutive days. The pre-flip waits reproduce STEP A's
recorded 14/9/11/12 exactly. ⭐ PRESENCE is immune to the volume confound that makes T+0/T+1
untrustworthy for magnitude — a statement that does not exist cannot be faked by a quiet slate,
which is precisely why the story specified it.

`ACTIVE_MIN` (billable cut): 08-10 **64**, 08-11 **47**, 08-12 **72**, against 7/28 = 167 /
7/30 = 141.

⚠️ **T+1 (08-11) is CONTAMINATED by INC-42** — the intraday w3pre leg failed twice that day and
the box ran 18.5-minute legs. Magnitude still belongs at T+3 (08-13). Nothing here quotes it.

### The predicted wake-promotion DID appear — but not on the predicted successor

`8 model-health/pred_log` waits went **1 → 8 / 7 / 7** starting *exactly* on 08-10, executions
unchanged (88 / 70 / 88, all normal). Consequently **resumes did not fall**: 32–35/day pre-flip
vs 35 / 25 / 41 post. So #679's promotion thesis is supported in kind — the wake moved rather than
vanished — but on a **different family** from the prompt's prediction
(`feature_pregame_team_features`, then the `feature_pregame_lineup_state` SCD-2 UPDATE), which
stayed flat. ⚠️ This is a FAMILY-level reading; the prompt's prediction is STATEMENT-level, so do
not treat "model-health inherited it" as established until the statement-level cut is run at T+3.

### Two other findings from the same read

⚠️ **`4b scd2 signal writers` on 08-12: 94 execs / 10 waits** against a stable 72–76 / 0–2 on every
other day in the window. New that day, and **unexplained** — 08-12 carried two box redeploys, but
that is a hypothesis, not a measurement. Re-read at T+3.

⚠️ **`CI on the prod WH` is a genuine waker**, not a rounding error: **39 waits on 08-10** (the
largest single family that day), 23 on 08-07, 14 on 08-06. The backlog item "point dbt CI off
COMPUTE_WH" is worth more than backlog status.

## 🔁 GATE-0 v2 — RE-DERIVED BUILD-DAY-AWARE (2026-08-12)

Gate-0 v1 was a fixed band on TOTAL executions (1,536–3,480). It **failed 08-12** (1,434) on a day
whose every per-family count was normal — the second such false fire after 08-10 (1,259). It is
confounded twice:

1. **BUILD-DAY BIMODALITY.** `other` runs ~1,043–1,182 on non-build days and ~2,615–2,889 on build
   days: one band spanning two populations, with the low one straddling the floor.
2. ⭐ **THE LEVERS THEMSELVES LOWER IT.** Every E11.24 lever DELETES statements, so total
   executions fall as the story succeeds. A floor derived pre-flip gets *harder* to clear the
   better the work goes — **a gate that fires because the fix worked is not a gate.**

**v2 splits the two jobs v1 was conflating.** It CLASSIFIES the day from a derived indicator, and
gates on a HEARTBEAT; volume is reported as context and is never the verdict.

- **The indicator is derived and self-validating.** `2 weather slate` is absent entirely on
  non-build days; `4b signals consumer` independently reads ~33 vs 2. Over 08-03…12 the two agreed
  on exactly the same four days (08-05, 08-08, 08-09, 08-11) — that agreement *is* the evidence the
  partition is real, so a **disagreement yields UNKNOWN / UNVERIFIED, never a pass** (NF1.7(a)).
- **The gate is a ONE-SIDED FLOOR at half the peer median.** The first cut used a two-sided
  min/max over 2–5 peers and FAILED 08-04 on a single extra invocation (`player=10` vs a `(11,11)`
  range) — the alert-fatigue mode that gets a monitor muted. An outage *suppresses* invocations
  wholesale; it does not shave one off, and a count above the peers is a catch-up. `0.5` is a
  design quantity ("at least half the expected daily invocations"), not a level tuned until the
  days we like pass.
- ⭐ **LEAVE-ONE-OUT.** The reference for judging day D excludes D. The first cut let D seed its own
  range, so a day whose heartbeat had collapsed to 3 simply became the new minimum and passed.
  Caught by its own unit test, not by inspection.
- **Heartbeat families carry no lever.** `4 matchup posteriors`, `4 player posteriors` — a family a
  lever moves on purpose cannot also be the normality signal (pinned by a parametrized test).
- **Contaminated days** (07-29, 07-31, **08-11**) are excluded from the reference but still
  reported, so the INC-42 freeze day's depressed counts cannot become the new normal.

Result on the live window: **all ten days PASS**, 08-11 flagged contaminated-and-excluded, and
08-12 passes *while its volume band is visibly violated* (1,437 against 1,504–2,184) — the design
intent, made legible. `scripts/tests/test_e11_24_gate0.py` (15 tests) is built on the real measured
counts; ⚠️ its first fixture did NOT reproduce the measured totals and silently tested a fictional
dataset (its 08-10 total came out 1,082 against a measured 1,504, which inverted the volume-band
assertion) — a fixture derived from real data must reproduce the real totals.

---

# 🔧 THE #679 AWAKE-TIME CORRECTION, APPLIED — AND IT OVERTURNS THE WEATHER-POLLER CREDIT

The target-6 close-out deferred this ("that block is now lifted — apply it, and re-check the
weather-poller credit (167→141), before quoting any awake-time number again"). Done.

`scripts/report_e11_24_wake_census.py` Table 2 now counts only minutes containing a
**warehouse-occupying** statement (`warehouse_size is not null`), and reports the legacy figure
beside it as `ACTIVE_MIN_RAW` so this soak's own earlier readings stay comparable.

| UTC day | ACTIVE_MIN (billable) | ACTIVE_MIN_RAW (legacy) | inflation |
|---|---|---|---|
| 07-27 | 145 | 219 | +51% |
| **07-28** (lever-2 pre) | **107** | 167 | +56% |
| **07-30** (lever-2 post) | **119** | 141 | +18% |
| 08-05 | 88 | 123 | +40% |
| **08-06** (target-6 flip day) | **69** | **164** | **+138%** |
| 08-09 | 73 | 126 | +73% |

08-06 is the mechanism in one row: the target-6 flip day is wall-to-wall `create or replace view`,
every one of which is metadata-only, so the legacy instrument reported 164 awake minutes on a day
that billed 69.

## ⛔ RETRACTED: "the weather lever cut awake-time 167 → 141, −16%"

On the billable cut that comparison is **107 → 119, i.e. +11%**. The −16% was an artifact of
cloud-services statements, and the day-total delta was never lever 2's to claim.

**But lever 2 is not refuted — it is re-sized, and the sub-finding is the useful part.** Cut to the
shape itself (`ref_venues`, the slate/venue read):

| | 07-26 | 07-27 | 07-28 | 07-29 | 07-30 | 07-31 | … | 08-10 |
|---|---|---|---|---|---|---|---|---|
| **cloud-services** (n / mins) | 93/18 | 101/18 | 90/17 | 72/14 | **·** | **·** | · | **·** |
| **occupies warehouse** (n / mins / waits) | 25/13/**7** | 9/5/**1** | 15/8/**5** | 9/5/**2** | 7/2/**0** | 2/1/**0** | | 2/1/**0** |

So the poller's true, billable contribution was **~5–13 awake-minutes and 1–7 provisioning waits a
day**, and lever 2 took both to **1–2 minutes and 0 waits**. Real, attributable, and roughly an
order of magnitude smaller than the retracted headline.

⭐ **THE GENERALISABLE FINDING, and it sharpens #679 rather than repeating it: a repeated identical
POLL is largely RESULT-CACHE-SERVED, and a cached query has `warehouse_size IS NULL` too.** ~85% of
this poller's executions never touched the warehouse — it asked the same question every hour and
Snowflake answered from cache. ⇒ **the poller class the raw awake-minute instrument was invented to
detect is precisely the class it most over-measures**, and a day-total awake-minute delta therefore
*cannot* credit a poller lever. Cut to the shape. (Sibling of the E11.24 rule that a gate is judged
on FIRES and a poller on ACTIVE-MINUTES — one level finer: on a poller's **billable** minutes.)

## Guards

`betting_ml/tests/test_e11_24_wake_census_perday.py` gains two clauses that point in **opposite**
directions, so each has its own isolating fixture (NF-D17 — a fixture that trips more than one
clause proves none of them):

* Table 2 **must** carry `warehouse_size is not null`;
* Tables 3 / 4 / 4b **must not** — a provisioning wait already implies the statement occupied the
  warehouse, so the filter is redundant there and a careless sweep applying it everywhere would
  silently drop true wakers.

RED-proven with the mutation asserted to land first (#682), and **proven independent**: breaking
either clause reddens only its own test. 7 passed on clean source.

🪤 **The first cut of the Table-2 guard was VACUOUS and the RED-proof reported it as a PASS.** It
anchored on the bare title `"2. ACTIVE MINUTES"`, which appears in the module DOCSTRING before it
appears at the SQL call site, so `str.find` returned the prose — a block the guard can never be
satisfied by. It was red on its deliberate break (which looked like success) *and* red on clean
source, and only the **independence** cross-check exposed it. Cure: `_sql_block()` anchors on the
`run(cur, f"…` / `run_pivot(cur, f"…` CALL SITE. This is INC-38's prose-cannot-satisfy trap and
#682's false-RED-proof lesson arriving together — **the discriminator is running the guard on CLEAN
source, which a red-proof harness by construction never does.**

---

# ⏭️ BACKLOG LANDED — dbt CI OFF THE PRODUCTION WAREHOUSE (code shipped, DDL pending)

**Why it graduated from "nice to have" to load-bearing:** `dbt Build CI` triggers on push/PR to
`main` whenever `dbt/**` changes — i.e. on **exactly the promotion days E11.24 reads its soak
baselines from**. On 2026-08-10 that produced 39 provisioning waits on `COMPUTE_WH` and they were
the *entire* apparent eb_* regression this session opened by chasing. Across the census window the
`CI on the prod WH` family reads **130/4 · 14/1 · 64/14 · 207/23 · 76/39** — the largest single
wait bucket on the board.

⚠️ **The first cut of this was a NO-OP — see the correction at the end of this doc.** What
actually ships is a change in **two places**, because dbt reads its warehouse from
`profiles.yml`, not from the shell:

```yaml
# dbt/profiles.yml — the `ci` target (the only one changed)
warehouse: "{{ env_var('SNOWFLAKE_CI_WAREHOUSE', 'COMPUTE_WH') }}"

# .github/workflows/dbt_build_ci.yml — the dbt-build-ci job (the one that runs `--target ci`)
SNOWFLAKE_CI_WAREHOUSE: ${{ secrets.SNOWFLAKE_CI_WAREHOUSE || 'COMPUTE_WH' }}
```

⭐ **The `||` fallback is the point: this is SAFE TO MERGE BEFORE THE WAREHOUSE EXISTS.** An unset
GitHub secret is the empty string, which is falsy, so with `SNOWFLAKE_CI_WAREHOUSE` absent CI keeps
today's behaviour exactly. The operator then creates the warehouse and sets the secret with **no
code change and no red-CI window** — which removes the ordering hazard that would otherwise make
this a two-step change where step one turns every dbt-Build job red.

⛔ **NOT `MONITOR_WH`** — that is the census's own read path; sharing it would make CI a line in the
instrument that measures CI (target 3's self-inflicted-wake defect, in a new costume).

**Operator DDL (once, ACCOUNTADMIN) + the secret:**

```sql
CREATE WAREHOUSE IF NOT EXISTS CI_WH WITH WAREHOUSE_SIZE='XSMALL'
  AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
GRANT USAGE ON WAREHOUSE CI_WH TO ROLE <the role behind secrets.SNOWFLAKE_ROLE>;
```
then `gh secret set SNOWFLAKE_CI_WAREHOUSE --body CI_WH --repo charlesclark2/fantasy_baseball`.

Guard: `test_ci_path_filter_semantics.py::test_dbt_ci_prefers_a_dedicated_warehouse_over_the_production_one`
— RED-proven on four breaks (revert to the prod secret · point CI at `MONITOR_WH` · and **both**
comment forms, because prose must not satisfy it).

🪤 **The trailing-comment form was a genuine hole and only the RED-proof found it.** The guard
stripped whole-line `#` comments but not trailing ones, so
`SNOWFLAKE_WAREHOUSE: ${{ secrets.SNOWFLAKE_WAREHOUSE }}  # use SNOWFLAKE_CI_WAREHOUSE` **passed** —
the exact INC-38 prose-cannot-satisfy defect, inside the strip written to prevent it. **A
comment-stripping guard must handle BOTH comment forms; testing only the whole-line form proves
only the whole-line form.**

## ✅ The one residual risk of a view flip, measured: reads did NOT get more expensive

#679's own caveat is that *"a view RE-EVALUATES on read — measure ACTIVE-MINUTES after the flip,
not just resumes; a full-history scan by a non-filtering reader could climb."* STEP B's wait-based
gates structurally cannot see that, so it needs its own instrument. Warehouse-occupying `SELECT`s
touching `feature_pregame_game_features*`:

| UTC day | n | avg s | **max s** | avg MB scanned | total s |
|---|---|---|---|---|---|
| 08-05 | 27 | 2.29 | 24.86 | 1.0 | 61.7 |
| 08-08 | 27 | 1.90 | 19.46 | 1.0 | 51.2 |
| 08-09 (last pre-flip) | 28 | 1.07 | **20.09** | 4.7 | 29.9 |
| **08-10 (post-flip)** | 25 | **0.90** | **1.41** | **0.0** | 22.5 |

Reads got **cheaper, not dearer** — the ~20 s tail vanished and bytes scanned went to ~0, which is
what #675 repointing the readers to S3 predicts (what is left on the Snowflake side is small
metadata/probe traffic). ⚠️ Elapsed-seconds is still the WRONG instrument for a COST claim
(E11.20-COST) — it is used here to answer a different question, "did a read get more expensive",
which is exactly what it *is* right for. No cost credit is claimed from this table.

*(Cross-check that the instrument is sane: 08-03 reads as avg 1070 s / max 2404 s, which reproduces
the independently-recorded 8/3 provisioning-stall outlier — "11 of 33 over 600 s, max 2402.8 s" —
to the second. The instrument agrees with a fact recorded from a different query months of context
earlier.)*

---

# 🔎 TARGET 5, RE-OPENED WITH A MEASUREMENT — AND A CORRECTION TO THE #675 CORRECTION (2026-08-10)

Found while checking whether today's flip moved a freshness ANCHOR (the INC-23/INC-34 class: *a
cutover invalidates an anchor, not the data*). `predict_today`'s `_FRESHNESS_QUERY` probes
`information_schema.tables.last_altered` for **`FEATURE_PREGAME_GAME_FEATURES_RAW`** and joins
**`eb_starter_posteriors`** — **both flipped to VIEW today**, so the question was live.

## What is measured

**1. The E11.20 phase-2b LTZ bug is STILL IN THE SOURCE.** `predict_today.py:999` reads
`date_part(epoch_second, max(last_altered)::timestamp_ntz)`. The documented cure was to take the
epoch of the LTZ value *directly*; the `::timestamp_ntz` cast is still there. Scored live, both ways,
in one statement:

| | value |
|---|---|
| as-coded (`::timestamp_ntz` cast) epoch | 1786377000 |
| correct (direct epoch of the LTZ) | 1786402200 |
| **delta** | **420.0 min** — the PT↔UTC offset, exactly |
| `lag_min` **as coded** | **400.30** → `> 180` ⇒ **STALE, slate-wide abstain** |
| `lag_min` **corrected** | **−19.70** ⇒ FRESH (the store was built ~20 min *after* the last ingest) |

Session `TIMEZONE` is `America/Los_Angeles`, and **neither `get_snowflake_connection` nor
`get_monitoring_connection` sets a session timezone** — so the box inherits the same account
default. ⇒ if the SF branch ran, it would abstain every slate.

**2. It has never abstained.** Served rows, deduped to current per (tier, game_pk), on `MONITOR_WH`:
**zero rows in 14 days** carry a freshness `abstain_reason`, and the `feature_store` tier reads
**15/15 with a non-null `h2h_edge`** on 08-04/05/07/08/09. A freshness abstain is slate-wide by
construction, so it cannot hide.

**3. The probe shape is essentially absent from the serving path.** Its distinctive fingerprint —
`information_schema.tables` **and** `FEATURE_PREGAME_GAME_FEATURES_RAW` in one statement, which
nothing else in the system emits — ran **6 times in 9 days**: five on `MONITOR_WH` (audit sessions,
**two of them this session's own probes**) and **one** on `COMPUTE_WH` (08-04 22:29). `predict_today`
runs several times a slate and would emit it on *every* SF-branch run.

## ⇒ The correction

The #675 prep record states: *"It is not dead. Measured on MONITOR_WH: that exact query shape
executed on COMPUTE_WH on 08-02, 08-05, 08-08 and 08-09 (1×/day, 0 waits)."* On the distinctive
fingerprint that does not reproduce — those days carry no such execution. The earlier match was
almost certainly on a **looser pattern** (the query's `stg_statsapi_probable_pitchers` /
`eb_starter_posteriors` subqueries, which many statements share) rather than on the
`information_schema` probe that only `_FRESHNESS_QUERY` performs.

⭐ **The measurement lesson: attribute a BRANCH from the outcome it would have produced, not from a
query shape appearing.** A shape executing proves *something* ran it; it does not prove the serving
gate took that branch — and here the served outcome (zero abstains, 15/15 edges) refutes the shape
reading outright. Sibling of E11.24's own "executions HOLD while waits → 0" discipline, one level up:
the artifact beats the query log.

⇒ **`W8B_FRESHNESS_S3=1` is live on the box** — despite `.env.example` documenting it as `0`. That
is the `W7B_LAKEHOUSE_S3` documented-≠-actual class **facing the other way**: not a flag believed on
and never set, but a flag believed off and quietly on.

## 🚨 The residual risk, and it is the real deliverable

**`W8B_FRESHNESS_S3` is load-bearing and is pinned by NOTHING.** It is absent from
`services/dagster/aws/env.required` (the deploy gate) and from
`monitor_health.REQUIRED_INTRADAY_FLAGS` (the `check_monitors_healthy_op` page). The box's `.env` is
uncommitted and **a `git pull` never touches it**, so if that key were ever lost — a box rebuild, a
hand-edit, an `.env` restored from the committed example that says `0` — the gate silently reverts
to the SF branch and **false-abstains every game of every slate, with no alarm**, exactly as it did
for six days 7/24→7/29.

**Two states are currently indistinguishable from any artifact reachable off-box:** the gate routed
correctly to S3, and the gate taking the SF branch but dying in its `except` and **failing open**
(the handler returns *not-stale* and prints only to stdout). Both yield zero abstains. **A serving
gate whose healthy state and whose silently-disabled state produce byte-identical evidence has not
been verified** — NF1.7(a), applied to a serving gate rather than a monitor.

### ⏭️ Operator — the ONE command that settles it (BOX)

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  printenv W8B_FRESHNESS_S3
```
⚠️ Must be run against the **persistent `dagster-codeloc`** container (FU-1's lesson: a throwaway
`exec` proves nothing about the container that ran this morning's jobs). `1` confirms the inference;
anything else means the gate has been failing open and the abstain-free record is a *disabled* gate,
not a healthy one — a materially worse finding.

### The fix, in the order it should ship — ⛔ NOT during this soak

1. **Pin the flag** — add `W8B_FRESHNESS_S3` to `env.required` **and** to
   `monitor_health.REQUIRED_INTRADAY_FLAGS`, the repo's standard cure for this class (already
   applied to W7A/W7B). ⛔ **Do NOT ship this now:** a newly-`env.required` key makes the **next
   deploy FAIL** until the operator adds it to the box's live `.env` — and #682/#693 have deploys
   pending. Ship it *with* an explicit "set `W8B_FRESHNESS_S3=1` in
   `services/dagster/aws/.env`" operator step.
2. **Make the branch observable** — emit `[METRIC] freshness_probe_branch=s3|snowflake|failed_open`
   so the two indistinguishable states separate in the served artifact.
3. **Then target 5 proper** — delete the SF branch (with the branch-parity assertion the stage-3
   plan already requires). Removing it retires the +420 cast with it; fixing the cast *in place* is
   the lesser cure, because the branch is dead weight either way.

⛔ Nothing here was shipped this session: `predict_today.py` is HALT-tier serving, the E11.24 rule is
one serving-flip per soak, and the #675 soak is open. This is a recorded finding plus a box command.

## Incidental — a #675 claim CONFIRMED post-flip

The same probe returns `starter_missing 0 / starter_total 20` reading `eb_starter_posteriors` **as a
view**. #675's ghost-immunity argument (the probe side is *today's current probables*, so a
superseded ghost row can never satisfy the LEFT JOIN, making `starter_missing` identical against the
table and the view) is now measured on the flipped object, not just reasoned about.

---

# 🎯 TARGET-7 CALLER INVENTORY (2026-08-10) — what stands between here and a suspended warehouse

Target 6 is closed and #675 is flipped, so target 7 ("every `COMPUTE_WH` caller must be gone before
the warehouse can be dropped") is next and needs a current list. Read on `MONITOR_WH`, 7 days,
**warehouse-occupying statements only** (the #679 filter).

⚠️ **This is an INVENTORY — an enumeration of callers — NOT a magnitude or trend claim.** The window
straddles both the 08-06 target-6 flip and the 08-10 #675 flip, so per this story's own per-day rule
nothing here may be quoted as a delta. It answers "who is left", not "how much".

| caller | execs | waits | what it is |
|---|---|---|---|
| `DBT_RW` → schema `BETTING` | 5,430 | **145** | the pipeline's remaining Snowflake materialisations — the bulk, and the real target-7 body of work |
| `DBT_RW` → no schema | 1,982 | 115 | session/DDL-adjacent traffic |
| **`DBT_RW` → `CI_BETTING`** | 269 | **74** | **the dbt-Build CI — 21.4% of all COMPUTE_WH waits in the window** |
| `DBT_RW` → `BETTING_FEATURES` | 134 | 2 | nearly gone (targets 6 + #662/#675 did this) |
| `CCL1196` (operator Snowsight) | 108 | 22 | behavioural, not code — audit from `MONITOR_WH` |
| `CREDENCE_API` | **16** | **7** | down to the 3 documented shapes |

## Three things this changes

**1. ⭐ The `CI_WH` item is not housekeeping — CI is 21.4% of the remaining waits.** 74 of 346 waits
in seven days come from the `CI_BETTING` schema, i.e. `dbt Build CI` running against the production
warehouse. That is the second-largest identified caller on the board and it does **no serving work
at all**. The fallback-safe repoint shipped this session covers it; it is **inert until the operator
creates `CI_WH` and sets `SNOWFLAKE_CI_WAREHOUSE`**, so that DDL is now the cheapest remaining wake
reduction in the story by a wide margin.

**2. `BETTING_FEATURES` is essentially done — 134 executions and 2 waits.** Targets 6, #662 and #675
between them have emptied the feature-schema of warehouse-occupying work. What remains is
concentrated in `BETTING`, which is where target 4 (the three sequential-posterior state writers)
and the residual mart materialisations live. **Target 4 is now unblocked** (it was gated on 6) and
is the natural body of work after #682/#693.

**3. `CREDENCE_API` is down to 16 executions / 7 waits and exactly the 3 shapes the story already
documented** — `DISTINCT model_version` (7), `/pipeline/status` (6), and the `model_registry`
freshness read (3). The metering repoint plus the `staleTime` fix removed the admin cost panel
entirely; these three are unchanged. They remain a **target-7 blocker and a request-path latency
defect** (a CLAUDE.md rule violation), not a cost lever — do not re-litigate them as one, and mind
the E9.26b landmine when repointing (`lakehouse_query` catches-and-returns `[]`, so the obvious fix
fails *silently* inside the Lambda).

## Recommended order from here

**#682 → #693** (already sequenced) **→ `CI_WH` DDL** (cheapest, 21.4%, zero serving risk) **→
target 4** (now unblocked) **→ target 5** (the freshness-gate finding above) **→ target 7**.


---

# 🪤 CORRECTION — THE FIRST CI_WH CUT WAS A DECLARATION WITH NO CONSUMER (2026-08-10, same session)

Recorded because the defect is this repo's most-repeated shape and it was committed, CI-green and
guarded before being caught.

**What shipped first:** `.github/workflows/dbt_build_ci.yml` set
`SNOWFLAKE_WAREHOUSE: ${{ secrets.SNOWFLAKE_CI_WAREHOUSE || secrets.SNOWFLAKE_WAREHOUSE }}` in both
jobs. **dbt never reads that variable.** `dbt/profiles.yml` hardcoded `warehouse: COMPUTE_WH` in
every target, so the change could not move a single query no matter what the secret said.

⭐ **NF-C0e's "wired ≠ invoked", and the guard reproduced the same error one level up.** The test
asserted the workflow *declared* the variable — i.e. it read the value back under the key the code
wrote, which is the INC-38/NF-C0e vacuous shape. It was green, RED-proven on four breaks, and
**proved nothing**, because every break it tested was on the declaring side. A guard on a
declaration cannot detect that the declaration has no consumer.

**What caught it:** answering the operator's plain question — *"where do we ensure the CI job uses
that warehouse?"* — by going and reading `profiles.yml` instead of restating the diff. The check
that would have caught it earlier is the mechanical one: **trace the variable to the process that
reads it, before writing the guard.**

**The corrected change, and why it is scoped this way:**

* `dbt/profiles.yml` — **only** the `ci` target becomes `env_var('SNOWFLAKE_CI_WAREHOUSE',
  'COMPUTE_WH')`. The default and `dev` targets stay hardcoded so a stray variable can never steer
  the production daily build. A guard pins that asymmetry.
* the workflow supplies the var on the **`dbt-build-ci` job only** — the one that passes
  `--target ci`. ⚠️ **`dbt-compile` runs with NO `--target`, i.e. on the DEFAULT (production)
  profile, and is therefore NOT covered by this change.** Worth knowing before reading the next
  census: the `ci_betting` traffic (269 execs / 74 waits) moves; whatever `dbt-compile` costs does
  not.
* 🪤 **the `||` fallback in the workflow is load-bearing, not decorative.** An unset GitHub secret
  interpolates to an **empty string**, and dbt's `env_var()` returns its default only for an
  **UNSET** variable — an empty one is passed through verbatim, yielding `warehouse: ""`. Same
  unset-vs-empty class as the delta-rs empty-AKID landmine. So the fallback has to live on the
  supply side; the `profiles.yml` default alone would not save it.

Guards: four clauses — consumer end, blast radius, supply end, and the empty-string trap — each
RED-proven on its own break and **verified independent** (each break reddens only its own clause).

## ⏭️ Operator, revised — the order that actually works

1. **Create the warehouse + grant** (safe any time; a suspended warehouse costs nothing):
   ```sql
   CREATE WAREHOUSE IF NOT EXISTS CI_WH WITH WAREHOUSE_SIZE='XSMALL'
     AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
   GRANT USAGE ON WAREHOUSE CI_WH TO ROLE ACCOUNTADMIN;
   ```
   (CI runs as `DBT_RW` / role `ACCOUNTADMIN` — measured, not assumed. The grant is redundant for
   ACCOUNTADMIN and is included to match MONITOR_WH's setup and survive a future role change.)
   ⛔ **Do not reuse `COMPUTE_SMALL_WH`/`COMPUTE_MEDIUM_WH`** — both exist and are idle, but Small
   is **2 credits/hr against X-Small's 1**, so CI would cost double what it does today.
2. **Set the secret:** `gh secret set SNOWFLAKE_CI_WAREHOUSE --body CI_WH --repo charlesclark2/fantasy_baseball`
3. ⚠️ **It takes effect only once the workflow file is on `main`.** `dbt Build CI` triggers on
   `push`/`pull_request` to `main`, and a `push` run uses **main's** copy of the workflow. `main`
   does not have it yet — so this lands with the next `dev→main` promotion, i.e. the #682 or #693
   deploy. Setting the secret before then is harmless and inert.
4. **Verify by measurement.** After that promotion, confirm the `ci_betting` statements moved:
   ```sql
   select warehouse_name, count(*) n
   from snowflake.account_usage.query_history
   where start_time >= dateadd(day,-2,current_timestamp()) and query_text ilike '%ci_betting%'
   group by 1;
   ```
   ⭐ **And read the census correctly afterwards:** the `CI on the prod WH` family will show
   **executions AND waits both → 0**, which this story's own rules say is the *dead-caller* shape.
   Here it is a **MOVE, not a death** — the discriminator is that the GitHub Actions runs still
   succeed and the same statements appear under `CI_WH`. Check both, exactly as #637's audit-INSERT
   removal had to.

## Honest framing — this is a STRUCTURAL prerequisite, not a credit lever

It does not delete compute; it **relocates** it. Total credits move roughly sideways (possibly a
hair worse — a cold `CI_WH` resume that previously rode an already-warm `COMPUTE_WH`). The value is
that `COMPUTE_WH`'s quiet windows become genuinely quiet, which is the **precondition for target 7**
(suspend/drop), and that CI stops contaminating every soak baseline read on a promotion day — which
cost this session an hour of chasing a phantom eb_* regression. Do **not** book a credit saving for
it; book it as removing 21.4% of the wakes standing between here and a suspendable warehouse.

## ✅ END-TO-END VERIFIED, and the empty-string trap is WORSE than asserted (measured 2026-08-10)

The corrected repoint was verified through **dbt's own profile rendering**, not by reading the diff
— the appropriate standard given the first cut was a declaration with no consumer. Four cases,
`dbt debug --target ci` (dbt-fusion 2.0.0-preview.204):

| `SNOWFLAKE_CI_WAREHOUSE` | resolved `warehouse` | verdict |
|---|---|---|
| `CI_WH` | `CI_WH` | ✅ the repoint works |
| a deliberate bogus name | that bogus name | ✅ proves the env var is genuinely read |
| **unset** | `COMPUTE_WH` | ✅ the fallback — safe to ship before the warehouse exists |
| **empty string** | **key absent entirely** | 🚨 see below |
| `CI_WH`, but `--target baseball_betting_and_fantasy` | `COMPUTE_WH` | ✅ production is unaffected |

🚨 **The empty-string case is worse than the comment I first wrote.** I asserted it would yield
`warehouse: ""`. Measured, the `warehouse` key **vanishes from the resolved connection altogether**,
so Snowflake falls back to the **user's** default warehouse — and `DBT_RW.default_warehouse` is
**`COMPUTE_WH`**. ⇒ an empty secret would leave CI billing production **silently**, with `dbt debug`
reporting *"All checks passed!"* and CI green. Nothing anywhere would say the repoint had not
happened. That is the whole justification for the workflow-side `||`: **profiles.yml's default
cannot rescue an empty value, only an absent one.**

⭐ **AND `dbt debug` IS NOT A VALID VERIFICATION OF A WAREHOUSE.** It reported `connection test: OK`
and *"All checks passed!"* against a **nonexistent** warehouse name *and* against **no warehouse at
all** — Snowflake does not validate the warehouse at connect time, only at first query. So a green
`dbt debug` (or a green CI run that selects zero models) proves the env var is *read*, never that
the warehouse is *usable* or that traffic *moved*. **The only valid proof is `query_history` showing
statements under `CI_WH`** — the "verify the published artifact, not the build log" rule, one layer
down into a tool's own self-check.

### Operator status (2026-08-10)

`CI_WH` created and verified: **X-Small, `AUTO_SUSPEND=60`, `AUTO_RESUME=true`, `USAGE →
ACCOUNTADMIN`** (the role CI actually runs as — measured). Secret set. ⏭️ Takes effect on the next
`dev→main` PR, and note **`dbt-build-ci` runs on `pull_request` only** (`dbt-compile` runs on both,
on the production target, and is deliberately not covered) — so the verification happens **on the
PR, before the merge**.

## ✅ CI_WH IS LIVE AND PROVEN — traffic moved (2026-08-10, promotion `dfdcb8c9`)

Promoted 2026-08-11 00:31 UTC (19:31 CDT). Verified in the order the deploy landmine requires —
**content on `main`, never the merge status**: all three greps (`profiles.yml` env_var, the workflow
`||`, the census billable filter) return 1, and `git rev-list --count origin/main..origin/dev` = 0.
`Orchestration CD` → **completed/success**.

**The proof that traffic actually moved** — the only one that counts, since `dbt debug` and a green
CI both report success against a warehouse that does not exist:

| warehouse | CI statements (6 h) | waits | window (UTC) |
|---|---|---|---|
| **`CI_WH`** | **8** | **0** | 23:35 → 23:42 |
| `COMPUTE_WH` | **0** | 0 | — |

The window matches the two `pull_request` dbt-Build CI runs exactly. ⭐ **And it confirms the
sequencing finding: `dbt-build-ci` is `if: github.event_name == 'pull_request'`, so the repoint was
exercised on the `dev→main` PR *before* its merge — the test preceded the deploy.** The `push` run
that follows a merge is `dbt-compile` only, on the production target, and is deliberately not
covered.

**Post-deploy serving — clean, and better than the pre-deploy reading** (SF-free, same slate):

| | 17:30 CDT (pre) | 19:40 CDT (post-deploy) |
|---|---|---|
| coverage / exit | 10/10 100%, exit 0 | 10/10 100%, exit 0 |
| `feature_coverage_score` | 0.9165 (min 0.833) | **1.000 (min 1.0)** |
| morning / post_lineup `feature_store` | 10/10 · **5/5** | 10/10 · **10/10** |
| `intraday_fallback` | 0 | 0 |

(The improvement is the slate maturing — more lineups posted — not the deploy; recorded so the next
reader does not attribute it to either.)

⚠️ **Merged outside the ~22:30–06:45 CDT quiet window**, mid-slate. It came through clean (CD green,
no INC-36 concurrency — the prior CD had been `completed` since 05:56 UTC, and the box returned
healthy on both post-deploy serving checks). Recorded as a fact, not a precedent: the content shipped
was uniquely low-risk (docs, a laptop instrument, guards, and a dbt target that production does not
use — zero serving or pipeline code), which is not true of the #682/#693 promotions still to come.

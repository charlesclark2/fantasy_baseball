# NF-FRESH1 — Draft-board data-freshness audit (Phase 1, READ-ONLY)

**Audit run:** 2026-08-15 ~04:10 UTC (2026-08-14 evening PT) · branch `nf-fresh1` (worktree off `dev`) ·
`best_alpha=0` · **no code, model, serving or publish change was made.**

**Verdict in one line:** the board is **not injury-blind in the sense the PM feared, and it is worse than
"only ADP is stale" in a way the card did not anticipate** — the market inputs are frozen *and they feed
the served RANKING*, not just a reference column. Depth charts and roster moves DO reach the board, but
only through a **weekly** ingest and a **manual** publish, so the served artifact is a static snapshot
whose freshest possible content is ~12 days old on the depth/role axis and ~20 days old on the market
axis. **Transactions have no feed at all.**

**Scope call:** this is a **launch blocker for the ADP/ECR axis** (fixable in days, and the fix is
mostly "stop reading a stale cache" + "publish on a cadence"), and a **known-and-bounded gap** on the
injury axis (no injury-report feed exists for 2026; the forward-availability channel is a coarse roster
designation that is currently frozen because its daily schedule is not firing).

---

## 0. The five headline findings

| # | Finding | Evidence |
|---|---------|----------|
| **F1** | The served board is a **STATIC, manually-published S3 JSON.** Nothing in Dagster, cron, or CI rebuilds or republishes it. Last publish **2026-08-10T05:33:28Z** (~5 days ago). | §1 |
| **F2** | **ADP *and* ECR are permanently frozen caches** — and **no code path can refresh them.** No caller passes `refresh=True`; there is no CLI flag. A board *rebuild* does **not** refresh the market. Served ADP = FFC's **2026-07-18→07-25** window; live FFC today = **2026-08-07→08-14**. | §2 |
| **F3** | ⭐ **The frozen market is an INPUT TO THE SERVED RANKING**, not merely a reference column. `market_lean` is `market-led` at QB/RB/WR and `market-blend` at TE — every skill position's served order incorporates the 3-week-old ADP/ECR. This is the finding that upgrades "stale column" to "stale product". | §2.3 |
| **F4** | **NF-INFRA1's documented state is INVERTED on both NFL rows.** `sports_nfl_roll_forward_schedule` is documented STOPPED but the lake shows it **firing weekly on cron**. `sports_nfl_sleeper_injuries_schedule` is documented "RUNNING (enabled 2026-07-26)" but has produced **exactly one commit, ever** — the hand-run at enablement. | §6 |
| **F5** | **NFL transactions are NOT INGESTED.** No transactions feed exists anywhere in the repo for NFL (the only `ingest_transactions.py` is MLB's Stats API). Trades/signings reach the board *indirectly* via the weekly roster/depth refresh; cuts and waiver claims move nothing. | §5 |

---

## 1. Axis 1 — REBUILD CADENCE (the pivotal question)

### Answer: **STATIC. Built and published by hand; no cron, no Dagster op, no CI step.**

**Build path** (all LAPTOP, SF-free):

```
run_season_projection.py           → artifacts/nfl_fantasy_season_projections_<season>.parquet   (MVP-1)
run_nf1_5.py                       → artifacts/nf1_5_season_projections_<season>.parquet         (SERVED)
run_league_board.py                → artifacts/league_boards/*.csv                               (14 boards)
export_draft_board_json.py         → artifacts/draft_board_json/  →  --publish  →  S3
```

**Publish target:** `s3://credence-prod-s3-api-cache/fantasy/nfl/2026/` — 14 `board_*.json`,
`manifest.json`, `projections.json`. The gated `/fantasy/nfl/*` Lambda routes read these blobs; the
boards are NOT queried from the lake at request time (deliberate — CLAUDE.md's wide-lakehouse-read
landmine).

**Evidence it is static — the exporter says so in its own docstring** (`export_draft_board_json.py:19-20`):

> "The data updates rarely (not intraday), so a re-export is an operator command, not a daily op."

**Evidence it is not automated:** `grep -rn "export_draft_board\|draft_board" pipeline/ services/ .github/`
returns only two *comments* in `sports_nfl_rollforward_job.py` telling the operator to re-run
`run_season_projection.py` by hand. There is no op, no schedule, no workflow.

**Evidence of the actual publish date — read from inside the payload, not from `s3 ls`:**

```
manifest.json     .generated_at = 2026-08-10T05:33:28.884688+00:00
projections.json  .generated_at = 2026-08-10T05:33:28.874993+00:00
                  .source       = 'local-artifacts'
                  .base_season  = 2025
                  .players      = 858
```

### 1.1 ⭐ The board was built *before* that same day's ingest landed

The roll-forward ingest writes at **13:15 UTC on Mondays**. The board was generated at
**2026-08-10T05:33 UTC** — **7h 42m BEFORE** that Monday's ingest committed.

⇒ **the served board reflects the 2026-08-03 roll-forward snapshot, not 2026-08-10's.** Its
depth-chart / roster view is therefore **~12 days old**, not the ~5 days the `generated_at` stamp
suggests. The two staleness clocks (build date vs. input date) do not agree, and only the build date is
visible to anyone.

### 1.2 The UI shows a build date, which makes the ADP column actively misleading

`components/fantasy/shared.tsx::ProvenanceLine` renders `built {generatedAt.toLocaleDateString()}` on
every fantasy surface — so the user sees **"built 8/10/2026"**. That stamp is true of the projection
and **false of the ADP column beside it**, which is from 7/25. A user reasonably reads one date as
covering the whole row. This is not a cosmetic issue: it is an honest-framing defect that Phase 2 must
fix regardless of what else it does.

---

## 2. Axis 2 — ADP (and ECR): **FROZEN, and un-refreshable by design**

### 2.1 Both market caches are stale by ~20 days

| Source | Cache file | Payload's own as-of stamp | Age at audit |
|---|---|---|---|
| FFC ADP (PPR/12) | `artifacts/adp_cache/ffc_ppr_12_2026.json` | `meta.start_date 2026-07-18` → `end_date 2026-07-25`, 3,091 drafts | **21 days** |
| FFC ADP (other formats) | `ffc_{standard,half-ppr,2qb}_{10,12}_2026.json` | same window | 21 days |
| FantasyPros ECR | `artifacts/ecr_cache/fp_ecr_PPR_2026.json` | `last_updated '7/26'` (ts 1785088273), 89 experts | **20 days** |

Live FFC right now returns `start_date 2026-08-07 → end_date 2026-08-14`, **6,334 drafts** — a fresher
window built on 2× the sample.

### 2.2 ⭐ The mechanism: there is no refresh path at all

`adp_source.fetch_ffc_adp(..., refresh: bool = False)` reads the on-disk JSON whenever it exists.
**Every caller in the repo omits `refresh`:**

```
run_season_projection.py:1092    A.fetch_ffc_adp(projection_season, fmt=fmt, teams=teams)
export_draft_board_json.py:577   A.fetch_ffc_adp(season, fmt=fmt, teams=teams)
```

`fantasypros_source.fetch_fp_ecr` has the identical shape and the identical omission. There is **no
`--adp-refresh` / `--refresh` CLI flag on any of the build scripts.**

⇒ **Once the cache file exists, the market is frozen forever.** A full board rebuild + republish — even
the one that ran on 2026-08-10 — re-reads the July JSON and ships it. This is stronger than
"the cache is stale": *the operator cannot refresh it without deleting the file by hand.*

### 2.3 ⭐ The frozen market feeds the served RANKING, not just a column

The served board is `nf1_5` (`projection_label: "market-aware refined (NF1.5)"`). Its per-position
provenance, read straight off the served manifest:

```
market_lean = { QB: "market-led-adaptive", RB: "market-led", WR: "market-led", TE: "market-blend" }
```

The chain is `run_nf1_5.build_pool → run_nf1_3.attach_market → _load_market_for_season →
ADP.load_adp_for_season / ECR.load_ecr_for_season → the frozen caches`. `_market_lean` labels a blend
weight `w ≥ 0.66` as *market-led*.

⇒ At **all four skill positions**, the order a drafting user sees was computed from a market snapshot
that is now three weeks old. The `MARKET_LEAN_NOTE` shipped in the payload is correct that the ranking
incorporates market consensus — it just doesn't say *which vintage*.

### 2.4 How much has actually moved (measured, served payload vs. live FFC)

199 players matched by name across both snapshots:

- mean |ADP move| **7.09 picks**, median 5.4, p90 **15.6**
- **43 of 199 (21.6%) moved ≥ a full round (12 picks)** — 20 fell, 23 rose
- inside the first ~8 rounds (served ADP ≤ 100): 102 players, **18 moved ≥1 round, 42 moved ≥ half a round**
- 33 players carry a live ADP and are absent from the served payload entirely (32 D/ST units named
  differently by FFC, plus name-alias misses such as "Deebo Samuel Sr." / "Kenneth Walker")

Largest moves the board is still pricing against the July market:

| Player | Pos | Served ADP | Live ADP | Move |
|---|---|---:|---:|---:|
| Tucker Kraft | TE | 73.3 | 105.4 | **+32.1** |
| Omar Cooper Jr. | WR | 132.9 | 164.9 | +32.0 |
| Justin Herbert | QB | 80.8 | 104.0 | +23.2 |
| Jonah Coleman | RB | 170.9 | 148.4 | −22.5 |
| Matthew Stafford | QB | 103.8 | 83.7 | −20.1 |
| Calvin Ridley | WR | 154.9 | 134.8 | −20.1 |
| Jake Ferguson | TE | 118.0 | 138.0 | +20.0 |
| Jalen Hurts | QB | 93.7 | 75.7 | −18.0 |
| Jayden Daniels | QB | 85.4 | 68.6 | −16.8 |
| Alvin Kamara | RB | 155.4 | 138.6 | −16.8 |

**Product consequence, both directions.** Where a player's stock *fell* (Kraft, Herbert), the board
still shows the old, better ADP, so the "value vs ADP" signal understates the reach. Where stock *rose*
(Hurts, Daniels, Kamara), the board shows a worse-than-real ADP, manufacturing a **phantom value** —
the user is told a player is available later than he now is. A "value" surface computed against a
three-week-old market can invert its own advice.

⚠️ **A caution for Phase 2:** the market moving is not on its own evidence that *our projection* is
wrong. It is evidence that the **reference column and the market-led half of our ordering** are stale.
Do not read §2.4 as a model-accuracy claim in either direction.

---

## 3. Axis 3 — INJURIES

### Answer: **the official injury REPORT is not ingested for 2026 and is not consumed at all. The
only availability channel is a coarse roster DESIGNATION, and its freshest source has been frozen
since 2026-07-26.**

### 3.1 Is it ingested?

| Feed | State | Evidence |
|---|---|---|
| nflverse `injuries` (report + practice status) | **INGESTED for history, ZERO rows for 2026** | `delta_scan('s3://credence-sports-lakehouse/nfl/raw/injuries')`: season 2025 = 6,068 rows, **2026 absent**. Last commit `2026-07-18T01:11:07Z`. |
| nflverse roster `status` (weekly_rosters) | ingested, refreshed weekly | 2026: ACT 2,852 · **RES 36** · E14 28 · RET 11 · CUT 3. No PUP/NFI/SUS codes at all. |
| Sleeper `v1/players/nfl` forward availability | **INGESTED ONCE, NEVER REFRESHED** | `nfl/raw/sleeper_injuries` has **exactly one Delta commit: `2026-07-26T23:20:49Z`**, 2,499 rows. Of those, **10 PUP + 4 RES = 14 flagged players**; 2,485 carry no status. |

The nflverse injury report is an **in-season-only** feed — it does not exist for an unplayed 2026, and
that is upstream behaviour, not our defect. `run_season_projection.py` says so explicitly in the report
it generates: *"the nflverse injury REPORT is in-season only and 2026 is unpublished."*

### 3.2 Is it consumed?

Yes — but only the coarse designation, through one channel:

- `run_season_projection.load_forward_roster_status` builds `proj_status` = Sleeper status **COALESCED
  OVER** nflverse roster status (Sleeper preferred, being fresher).
- `season_projection.injury_availability_games` caps expected games toward
  `_INJURY_STATUS_GAMES_CAP = {RES: 4.0, PUP: 4.0, NFI: 4.0, SUS: 7.0}` at blend 0.7.
- Expected games scales the whole per-game line ⇒ the cap moves the point projection and therefore the rank.

**What it cannot see:** an injury report, a practice designation (DNP/LP/FP), a Questionable/Doubtful/Out
tag, a "sprained MCL, 2–4 weeks" news item, or any camp injury that has not yet produced a roster
transaction. `injury_cap_ratio` appears in the served `featureLegend` but in **0 of 703** served
`contrib.drivers` blocks — it is a legend entry with no realized attribution on this board.

### 3.3 Does the board reflect a player going OUT/IR?

**Only if (a) the move produced an IR/PUP roster designation, (b) that designation landed in a Sleeper
or nflverse pull, and (c) an operator then rebuilt and republished the board.** All three currently
have gaps:

- **(a)** narrow by construction — a camp injury without a transaction is invisible.
- **(b)** Sleeper — the *preferred, fresher* source — has not been refreshed in **20 days**. nflverse
  rosters refresh weekly.
- **(c)** manual, last done 2026-08-10 off the 2026-08-03 snapshot.

Cross-checking the 858 served players against the current 2026 roster feed: **643 ACT, 4 RES, 3 RET,
1 CUT, 1 E14** — i.e. the board's live availability signal currently distinguishes **9 players**.

> ⚠️ **Measurement caveat, stated because it matters.** 174 served players do not join the current
> roster feed on `gsis_id` (81 of them rookies). That bucket **mixes** genuinely-unrostered players,
> rookies with no gsis roster row yet, and ID-join misses (Tyreek Hill and Stefon Diggs both land in
> it, which is not credible as "unrostered"). **It is not a clean measure of cuts** and is not used as
> evidence anywhere above. Phase 2 should not treat it as a defect count without first fixing the join.

**Assessment.** The PM's "the board is injury-blind" reads as **directionally right but mechanically
different from the fear**: it is not that we ingest injuries and ignore them, nor that we ignore a
star's torn ACL if it produced an IR move. It is that our **only** availability signal is a coarse
roster designation whose freshest feed has been dark for 20 days, and we have **no injury-report or
news channel at all**. In mid-August — camp injuries daily, IR designations lagging by days — that is
a real product gap, but it is a *missing-feed* gap, not a *broken-model* gap.

---

## 4. Axis 4 — DEPTH CHARTS

### Answer: **INGESTED (daily snapshots, landed weekly) and genuinely CONSUMED through three
channels — but the served board's depth view stops at ~2026-08-03.**

### 4.1 Ingest state — the healthiest axis

```
nfl/raw/depth_charts, season 2026 : 420,090 rows across 141 distinct snapshot days
max(dt)                            : 2026-08-10T08:23:54Z
Delta commits (season=2026)        : 2026-07-27T13:15:29Z · 2026-08-03T13:15:46Z · 2026-08-10T13:15:30Z
```

ESPN publishes **daily**; we land **weekly**. So the lake is 0–7 days behind the feed, and today
(2026-08-15) it is **5 days** behind.

### 4.2 Consumption — three real channels

1. **`stg_nfl_depth_charts_current`** — the NF-D1 cold-start model: latest snapshot per
   (season, player, position), deliberately bypassing the week-ASOF map (which drops every pre-Week-1
   snapshot). This is what makes a pre-season depth chart readable at all.
2. **Expected games** (`season_projection.expected_games`, L265) — a 50/50 blend of depth-chart role and
   base-season durability. Moves the point projection directly.
3. **Mover opportunity** (`_MOVER_OPP_BLEND = 0.35`, RB/WR/TE) — a player whose team changed is rescaled
   toward the **new** role's volume level at his new depth rank. This is the channel through which a
   *trade or signing* actually moves a projection.
4. Plus `depth_rank` as an explicit NF1 feature — it appears in **307 of 703** served `contrib.drivers`
   blocks, up to ±4.6 points (largest: Bhayshul Tuten +4.6, Gunnar Helm +3.8, Zach Charbonnet +3.8,
   Quinshon Judkins +3.2).

> Note: `contrib` is the `nfl_fantasy_nf1_v1` explainer's attribution, while the served projection is
> `nfl_fantasy_nf1_5_v1`. The ±4.6 figure is the *explainer's* per-feature attribution and is a
> **lower bound** on depth-chart influence — channels (2) and (3) act on expected games and the
> per-game line and are not in that attribution.

### 4.3 The staleness, precisely

| Clock | Value | Lag today |
|---|---|---|
| ESPN publishes | daily | — |
| Lake `max(dt)` | 2026-08-10 | **5 days** |
| Served board's depth view | ~2026-08-03 (built 08-10T05:33Z, before that day's 13:15Z landing) | **~12 days** |

The card flags this axis as critical *right now* because preseason charts are being sorted. That is
correct: a **12-day-old depth chart in mid-August is the single most decayed model input** on the board,
and unlike ADP it decays into the *projection*, not just a reference column.

---

## 5. Axis 5 — TRANSACTIONS

### Answer: **NOT INGESTED. No NFL transactions feed exists anywhere in the repo.**

- `grep -rni "transaction" quant_sports_intel_models/football/nfl/` → **zero code hits** (only prose in
  two markdown docs).
- The repo's `scripts/ingest_transactions.py` and `scripts/backfill_transactions.py` are **MLB** (Stats
  API roster transactions, feeding `feature_pregame_injury_status`). Nothing NFL.
- `ROLL_FORWARD_SOURCES` = `rosters, weekly_rosters, schedules, depth_charts, injuries,
  nflverse_draft_picks, nflverse_combine`. No transactions source is registered in `sources.py` at all.

### 5.1 How a transaction *does* reach the board (indirectly)

A trade or signing changes a player's **team** in `rosters`/`depth_charts`. On the next weekly
roll-forward that propagates, and the `mover_scale` channel (§4.2.3) rescales his per-game line toward
his new role's volume. So **trades and signings move stock on a weekly lag, if and only if the board is
then republished.**

**A cut or a waiver claim moves nothing directly** — there is no "player released" signal; he simply
stops appearing on a roster, and the projection's reaction is whatever the depth-chart channel infers.

### 5.2 What the served board's team assignments actually look like

Board team vs. current lake roster team, **after** normalising nflverse alt franchise codes
(`LA→LAR`, `AZ→ARI` — the NF-W3 franchise-code family; without this the naive diff reports **41**
mismatches, 39 of which are pure alias noise):

> **2 real team mismatches** out of 652 joined players (Adam Thielen PIT→MIN, Quentin Skinner BUF→NYJ).

⇒ On the *team-assignment* axis specifically, the board is **essentially current**, because the weekly
roll-forward IS running and the board was republished on 2026-08-10. Transactions are the axis with the
**worst feed coverage** but, today, the **smallest observed drift** — because the roster feed is the
transaction proxy and it is healthy.

---

## 6. NF-INFRA1 verification — **the documented state is INVERTED on both NFL rows**

The card's premise is *"the NFL ingest schedules ship STOPPED."* That is what the code's
`default_status` says and what `BOX_OPERATIONS.md §10` records. **The lake says otherwise, in both
directions.**

**Method (per the card: content-freshness, never `aws s3 ls` mtime).** `aws s3 ls` prints
*shell-local* time (this shell is CDT, UTC−5) — the documented landmine. So every timestamp below is
read from **inside the Delta transaction log** (`commitInfo.timestamp`, epoch-ms → UTC), not from an
object mtime.

### 6.1 `sports_nfl_roll_forward_schedule` — evidence says **RUNNING**

Declared cron: `NFL_ROLL_FORWARD_CRON = "15 6 * 3-8 1"` @ `America/Los_Angeles`
= **Mondays 06:15 PT = 13:15 UTC**, March–August.

Observed `WRITE season = 2026` commits:

| Table | Commit (UTC, from `_delta_log`) | Weekday |
|---|---|---|
| `rosters` | 2026-07-27T13:15:24 · 2026-08-03T13:15:37 · 2026-08-10T13:15:25 | Mon · Mon · Mon |
| `weekly_rosters` | same three fires | Mon ×3 |
| `depth_charts` | 2026-07-27T13:15:29 · 2026-08-03T13:15:46 · 2026-08-10T13:15:30 | Mon ×3 |
| `schedules` | 2026-07-27T13:15:27 · 2026-08-03T13:15:41 · 2026-08-10T13:15:29 | Mon ×3 |

Three consecutive Mondays, four tables, all landing within ~20s of **13:15:2x UTC** — a second-level
match to the declared cron. **This is a firing schedule, not hand-runs.** (Earlier commits on Jul 17/24/25
— Fri/Fri/Sat, irregular times — *are* the hand-runs from the NF-D1 build sessions, and they look
visibly different, which is what makes the Monday pattern legible.)

> **Honest limit:** this infers schedule state from ingest evidence. A weekly operator hand-run at a
> fixed minute would be indistinguishable. The pattern is strong enough to act on; **confirm in Dagit**
> (operator, §8) before amending `BOX_OPERATIONS.md`.

### 6.2 `sports_nfl_sleeper_injuries_schedule` — evidence says **NOT RUNNING**

Declared cron: `NFL_SLEEPER_INJURIES_CRON = "30 6 * 3-8 *"` = **daily 06:30 PT = 13:30 UTC**, Mar–Aug.
`BOX_OPERATIONS.md §10` records it as **"RUNNING (enabled 2026-07-26)"**.

Observed:

```
nfl/raw/sleeper_injuries/_delta_log/  →  ONE file: 00000000000000000000.json
commitInfo.timestamp                 →  2026-07-26T23:20:49Z   (= 16:20 PT, NOT the 13:30 UTC cron)
```

The ingest writes with `mode="overwrite"` per capture (`run_sleeper_injuries_ingest.py:5` — *"season-
partitioned, overwritten on each capture"*), so **every successful daily fire would produce a commit.**
There is one, at a time that does not match the cron, on the day the doc says it was enabled.

⇒ **the daily Sleeper capture has never fired successfully.** ~20 days of missed offseason PUP/IR
designations, on the source the projection explicitly *prefers* over nflverse for exactly this reason.

### 6.3 Neither NFL schedule is heartbeat-checked

`BOX_OPERATIONS.md §10` marks both **"NOT heartbeat-checked"**, and neither appears in
`betting_ml/monitoring/monitor_health.py`'s critical set. So `check_monitors_healthy_op` would **not**
have paged for §6.2 — this is the E11.23 "silently never runs" class, landing exactly where the repo
already knows it lands. It went unnoticed for 20 days and was found only by reading the artifact.

---

## 7. Consolidated per-axis diagnosis

| Axis | Ingested? | Consumed? | Refreshed? | Served staleness today | Verdict |
|---|---|---|---|---|---|
| **Rebuild cadence** | n/a | n/a | **manual only** | published 2026-08-10 (5 d); built off 08-03 inputs (12 d) | 🔴 **STATIC** |
| **ADP (FFC)** | ✅ cached | ✅ **feeds the ranking** (§2.3) | ❌ **no code path exists** | **21 d** (window ends 07-25) | 🔴 **FROZEN + un-refreshable** |
| **ECR (FantasyPros)** | ✅ cached | ✅ feeds the ranking | ❌ same mechanism | **20 d** (`last_updated 7/26`) | 🔴 **FROZEN + un-refreshable** |
| **Injuries — report/practice** | ❌ 0 rows for 2026 (upstream in-season-only) | ❌ not consumed | n/a | n/a | 🔴 **NOT INGESTED** |
| **Injuries — Sleeper forward availability** | ✅ once | ✅ (preferred source for `proj_status`) | ❌ **schedule not firing** | **20 d** | 🔴 **NOT REFRESHED** |
| **Injuries — nflverse roster status** | ✅ | ✅ (`proj_status` fallback) | ✅ weekly | 12 d as served | 🟡 coarse + weekly |
| **Depth charts** | ✅ daily snapshots | ✅ **3 channels** (§4.2) | ✅ weekly ingest, manual publish | **~12 d as served** | 🟡 **fresh feed, stale serve** |
| **Transactions** | ❌ **no feed** | 🟡 indirect via rosters/depth | weekly (proxy) | 2 real team mismatches | 🟡 **NOT INGESTED, proxied** |

---

## 8. Phase-2 plan (scoped, sequenced, dependency-flagged)

Ordered by **(product impact per unit of work)**. Items P1–P3 are the launch-blocking set.

### P1 — Unfreeze the market (**highest impact, lowest risk, ~½ day**)

The single change that fixes both §2 and §2.3.

1. Add `--market-refresh` to `run_nf1_5.py` / `run_season_projection.py` / `export_draft_board_json.py`,
   threaded to `fetch_ffc_adp(refresh=True)` and `fetch_fp_ecr(refresh=True)`.
2. **Make the current season's market refresh the DEFAULT, with historical seasons still cache-first.**
   A backtest over 2019–2024 *must* keep reading its pinned snapshot — refreshing a historical ADP
   would silently change a scored benchmark. Split on `season == current_season()`.
3. **Ship the market's own as-of stamp in the payload** (`adp_as_of`, `ecr_as_of`, from FFC's
   `meta.end_date` and FantasyPros' `last_updated`) and render it beside the ADP column, distinct from
   the board's `generated_at` (§1.2). A stale market must be *visible*, never inferred from the build date.
4. Keep the existing non-`Success` cache guard — it already prevents caching a transient FFC error.

⚠️ **Guard this, or it silently reverts:** a test asserting that a current-season build *reaches the
network / uses a refreshed payload*, RED-proven against source with the flag removed. This is the
`W7B_LAKEHOUSE_S3` documented-but-never-set class in a data path — the current bug is precisely a
default that nobody could see.

### P2 — Put the publish on a cadence (**the fix for F1**)

1. A Dagster job `nfl_fantasy_board_publish_job`: refresh market → rebuild NF1.5 projection → rebuild
   the 14 league boards → export → publish.
2. **Cadence: DAILY through draft season (roughly now → the 2026-09-09 opener), then weekly.** Daily is
   justified by §2.4 (mean 7-pick ADP drift per 3 weeks is not linear — camp news is bursty) and by
   depth charts publishing daily.
3. **Ordering is load-bearing (INC-25):** the publish job MUST run **downstream of** the roll-forward
   ingest in the same cycle, or it reproduces §1.1 exactly — a board built hours before its own inputs
   land. If they stay separate jobs, the publish must be scheduled *after* 13:15 UTC Monday, and its
   own log must state which ingest vintage it read.
4. **Tier: ALERT-loud-but-continue, never HALT.** This is a browse surface; a failed rebuild should page
   and leave the previous board served, not blank the product.
5. Retain the NF-D12 `--publish` guard. A scheduled job passes it explicitly; the operator default stays
   dry-run.
6. Stamp the **input vintage** into the payload alongside `generated_at` (e.g. `depth_chart_as_of`,
   `roster_as_of` from `max(dt)` / the Delta commit read), so §1.1 is legible in the artifact rather
   than reconstructible only by an audit like this one.

### P3 — Restart the Sleeper daily capture (**the fix for F4 / §6.2**)

1. **Operator:** confirm in Dagit whether `sports_nfl_sleeper_injuries_schedule` is STOPPED (most
   likely) or RUNNING-but-failing, and start / fix accordingly.
2. **Correct `BOX_OPERATIONS.md §10`** on both NFL rows — it is currently wrong in both directions and
   is the artifact a future session will trust.
3. **Add both NFL schedules to the `check_monitors_healthy` set.** They are currently
   "NOT heartbeat-checked", which is why 20 dark days went unnoticed. A daily capture whose only
   evidence of life is a Delta commit needs a freshness SLA, not a liveness probe — the INC-41 lesson:
   *a probe asking "is the service up" cannot see a service that is up and producing nothing.*
4. Cheapest durable detector: an **artifact-freshness SLA** on `nfl/raw/sleeper_injuries` +
   `nfl/raw/depth_charts`, read from **inside the parquet/Delta log** (⛔ never an S3 `LastModified` —
   INC-41), with a WARN on unevaluable rather than a silent pass (NF1.7(a)).

### P4 — Raise the depth-chart ingest cadence (**the fix for the most-decayed model input**)

ESPN publishes daily; we land weekly. Through camp (now → opener), move the roll-forward — or at
minimum a `depth_charts`-only slice of it — to **daily**. It is 7 unauthenticated nflverse reads,
already idempotent (`replaceWhere season=2026`), already timeout-bounded, and costs nothing. The
seasonal-window cron already gates it to Mar–Aug.

⚠️ Pair with P2: a daily ingest with a manual publish changes nothing a user can see.

### P5 — Injury information beyond the roster designation (**scoped as a real project, not a config flip**)

This is the axis with no cheap fix, and the plan should say so rather than imply one.

- **What exists:** the coarse designation channel (§3.2), which is correct as far as it goes.
- **What is missing:** report / practice status / news. nflverse's `injuries` feed **will begin
  publishing for 2026 once the season starts** — it is in-season-only upstream. So the in-season
  problem partly solves itself; the **draft-season** problem does not.
- **Options, in increasing cost:**
  1. Restart Sleeper daily (P3) — recovers the *existing* designed capability. **Do this first and
     measure what it actually surfaces** before scoping anything larger. The 2026-07-26 hand-run
     flipped nflverse-only's 8 RES / 0 PUP → 10 RES / 10 PUP, so the marginal value is real but bounded.
  2. `sports_nfl_pit_metadata_schedule` already captures injury reports with **our own**
     `capture_timestamp` (NF-W0a) — check whether its Sep–Feb window can usefully extend into camp.
  3. **NF-I0 (injury NLP)** is already on the delivery epic as story #9. That is the right home for a
     news/report channel. ⛔ Do not smuggle a Phase-2 version of it into this story.
- **Recommendation:** Phase 2 delivers (1), documents the bound honestly on the surface, and leaves
  the rest to NF-I0. Attempting a news feed inside a freshness fix is how a scoped story becomes a
  quarter.

### P6 — Transactions: **do NOT build a transactions feed in Phase 2**

§5.2 measured **2 real team mismatches out of 652**. The roster feed is already an adequate transaction
proxy *provided* P2 and P4 land. A dedicated transactions ingest would be new surface area for a defect
that currently measures near zero.

**Revisit if and only if** a measurement — not an intuition — shows roster-derived team assignment
lagging real transactions materially. **Fix the ID join first** (§3.3 caveat): 174 unjoined players make
any future transaction-drift measurement unreadable, and that is a genuine prerequisite, not a nice-to-have.

### Dependency flag (explicit, per the card)

> **Everything in P1–P4 depends on NF-INFRA1's feeds being ON.** §6 revises what that means:
> the **roll-forward is already running** (so P4 is a cadence change, not an enablement), while the
> **Sleeper daily capture is not** (so P3 is a genuine enablement). A Phase-2 build that assumes the
> card's premise — *both* STOPPED — would spend its effort on the wrong one and would still ship a board
> with a 20-day-old availability signal.

---

## 9. Honest-framing constraints Phase 2 must carry

Recorded here so Phase 2 inherits them rather than rediscovering them.

1. **Projections move on REAL information only — no manufactured precision.** A daily rebuild must not
   be allowed to *look* like daily new information. If the only thing that changed between Tuesday and
   Wednesday is the ADP window, the projection should move by exactly the amount the market moved it
   and no more. ⛔ Never add jitter, decay, or a recency tilt to make a daily board look "live".

2. **A fresher build is not a better model, and must never be presented as one.** The `MARKET_LEAN_NOTE`
   already shipped in the payload stays exactly as-is. Refreshing ADP makes the *market half* of the
   ranking current; it does not make our order more independent. ⛔ Nothing in Phase 2 may weaken or
   drop that caveat.

3. ⭐ **Backfilled / hindsight data must NEVER feed a track-record claim (the E5.9 backfill boundary).**
   `export_track_record_json.py` builds its claim ONLY from the freshly-regenerated NF-D3 scorecard and
   the NF-D17 population artifact, with a build-time `_CLAIM_DENYLIST` assert. **A daily-refresh build
   must not touch it.** Concretely:
   - **Historical seasons keep their PINNED market snapshot.** If P1's refresh reached 2019–2024, the
     track record would be regraded against an ADP that did not exist at the time — a hindsight
     benchmark. This is why P1 step 2 splits on `season == current_season()`; that split is a
     **correctness boundary, not an optimisation**.
   - The current season stays behind `LOCKED_SEASON`; the export is structurally incapable of emitting
     it and must remain so.
   - **A board republished daily accumulates versions. None of them is a forecast we made and stood
     behind unless it was published before the outcome.** If a future story wants an in-season
     "how are this year's projections doing" claim, the honest instrument is a **point-in-time capture
     of what was SERVED on each date** (the NF-W0a discipline), not a re-derivation from today's inputs.
     ⛔ Re-deriving a past date's board from current data and calling it a track record is exactly the
     boundary violation.

4. **A staleness figure must be visible, not inferable.** §1.2 is a live instance of dishonest-by-
   omission framing: the UI shows one date over a row containing inputs of three different vintages.
   Phase 2 ships per-input as-of stamps or it has not fixed the honesty problem, only the data problem.

5. **`best_alpha = 0` throughout.** This is a projection product. No edge, win-rate, or
   market-beating claim attaches to any of it.

---

## 10. Reproducing this audit

All read-only. No box access needed; no Snowflake.

```bash
# 1. What is actually SERVED (content, never `s3 ls` mtime)
aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/manifest.json    - --region us-east-1
aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/projections.json - --region us-east-1
#    → read .generated_at, .market_lean, .players[].adp

# 2. Live market vs the served snapshot
curl -s -H 'User-Agent: Mozilla/5.0' \
  'https://fantasyfootballcalculator.com/api/v1/adp/ppr?teams=12&year=2026&position=all' | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["meta"])'
#    → compare meta.start_date/end_date against the served payload's ADP values

# 3. Lake feed freshness (content timestamps inside Delta, not object mtimes)
AWS_DEFAULT_REGION=us-east-2 uv run python -c "
import duckdb,sys; sys.path.insert(0,'.')
from quant_sports_intel_models.football.nfl.ingest import s3io
con=duckdb.connect(); con.execute('install delta; load delta; install httpfs; load httpfs;')
o=s3io.storage_options(); con.execute(\"set s3_region='us-east-2';\")
con.execute(f\"set s3_access_key_id='{o['AWS_ACCESS_KEY_ID']}';\")
con.execute(f\"set s3_secret_access_key='{o['AWS_SECRET_ACCESS_KEY']}';\")
for t in ('depth_charts','injuries','sleeper_injuries','rosters','weekly_rosters'):
    u=s3io.table_uri('nfl',t)
    print(t, con.sql(f\"select season,count(*) from delta_scan('{u}') where season>=2025 group by 1 order by 1\").fetchall())
"

# 4. Schedule state, inferred from the Delta commit log's OWN UTC timestamps
aws s3 cp s3://credence-sports-lakehouse/nfl/raw/depth_charts/_delta_log/00000000000000000029.json - \
  --region us-east-2 | python3 -c "
import sys,json,datetime
for l in sys.stdin:
    d=json.loads(l)
    if 'commitInfo' in d:
        print(datetime.datetime.utcfromtimestamp(d['commitInfo']['timestamp']/1000).isoformat()+'Z',
              d['commitInfo'].get('operation'))
"
```

⚠️ **Do not** substitute `aws s3 ls` LastModified for step 3 or 4. It prints shell-local time (this
audit's shell is CDT), and a server-side copy can refresh an mtime without the data changing — the
INC-41 finding. Every timestamp in this document is read from inside the artifact.

---

## 11. Operator actions arising (Phase 1 produces no code change)

1. **Confirm in Dagit** the live status of `sports_nfl_roll_forward_schedule` (evidence: RUNNING) and
   `sports_nfl_sleeper_injuries_schedule` (evidence: not firing). Box/Dagit reads are operator-only —
   `ssm:SendCommand` is denied to `baseball-access-user`.
2. **Start the Sleeper daily schedule** if it is STOPPED (highest-value single action from this audit:
   it restores an already-built capability that has been dark 20 days).
3. **Correct `BOX_OPERATIONS.md §10`** on both NFL rows once (1) confirms — it is presently wrong in
   both directions.
4. **Decide the Phase-2 scope** against §8: P1–P3 are the launch-blocking set; P5 partially defers to
   NF-I0; P6 recommends building nothing.

**PR:** docs-only, `nf-fresh1` → `dev`. No serving, model, or pipeline change; nothing to deploy;
`deploy.sh` not required.

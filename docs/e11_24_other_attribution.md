# E11.24 — statement-level attribution of the `other` wake bucket (2026-08-08)

**Analysis only. No flip, no deploy, no serving change.** Every query ran on `MONITOR_WH` via
`get_monitoring_connection()`; `COMPUTE_WH` was never touched, so the open target-6 soak
(closes Sun 08-09, T+3) is uncontaminated by this session. `best_alpha=0` throughout.

Instrument: **`scripts/report_e11_24_other_attribution.py`** (new, this session). It imports
`FAMILY_CASE` from `report_e11_24_wake_census.py` rather than restating it, so the two scripts
cannot drift and an `other` total means the same thing in both.

Reproduce: `uv run python scripts/report_e11_24_other_attribution.py --days 9` (LAPTOP).

---

## VERDICT

**Target 6 landed, and it did not so much delete wake as MOVE it.** The four flipped models went
to zero waits with executions unchanged; the resume they used to own was inherited by the next
warehouse-occupying statement in the same chain. That statement is the **EB posterior merge pair
— exactly what the already-code-ready PR #675 repoints.**

`other` is now **91% of all provisioning waits (40 of 44 on 08-08)**, up from ~21–36% pre-flip.
That is not a new problem appearing; it is the named families being removed and their wake
landing on statements `FAMILY_CASE` has no pattern for.

| UTC day | resumes | execs | waits | `other` waits | `other` % | overnight waits |
|---|---|---|---|---|---|---|
| 08-03 | 34 | 1,536 | 56 | 20 | 36% | 3 |
| 08-04 | 33 | 1,793 | 52 | 18 | 35% | 10 |
| 08-05 | 35 | 3,480 | 52 | 11 | 21% | 1 |
| **08-06** ⬅ target 6 deployed | 32 | 2,184 | 60 | 32 | 53% | 14 |
| 08-07 | 27 | 1,712 | 51 | 24 | 47% | 23 |
| 08-08 | 28 | 3,172 | 44 | **40** | **91%** | 5 |

Resumes fell ~34/day → ~29/day (−15%). Total waits fell only modestly. **The wake is a queue:
flipping a model to a view promotes the next unflipped statement into the waker role.** Reaching
literal-zero in the build band therefore requires finishing the chain, not flipping one model.

⚠️ 08-05 (3,480 execs) and 08-08 (3,172) sit at/above the 1,536–3,480 sanity band; 08-07 (1,712)
is low-normal. No day in the post-flip window is an outage day, so the composition above is
trustworthy (INC-37 volume gate).

---

## Two instrument corrections (both bit this session before they were caught)

### 1. ⭐ `warehouse_size IS NULL` — a query can carry `warehouse_name` and never use the warehouse

Cloud-services-only statements (`SHOW OBJECTS`, `ALTER SESSION SET QUERY_TAG`,
`ALTER EXTERNAL TABLE … REFRESH`, `CALL SYSTEM$…`, and **every** `create or replace view`) are
billed to cloud services. They can neither resume the warehouse nor keep it awake, and they are
identified by `warehouse_size IS NULL` with 0 bytes scanned.

**They are 40–138% of the awake-minutes figure `report_e11_24_wake_census.py` Table 2 reports:**

| day | active_min as counted | active_min real | inflation | metadata-only execs |
|---|---|---|---|---|
| 08-03 | 109 | 73 | +49% | 1,085 / 1,536 |
| 08-05 | 123 | 88 | +40% | 1,434 / 3,480 |
| 08-06 | 164 | 69 | **+138%** | 1,618 / 2,184 |
| 08-08 | 93 | 59 | +58% | 1,235 / 3,087 |

The first cut of this session's script ranked `CALL SYSTEM$GET_RECENT_IN_APP_NOTIFICATIONS()` as
the largest awake-time consumer in the account (74 "exclusive" minutes). It is a **Snowsight
browser tab's background notification poll that never touched the warehouse.** A fix session
would have been sent at nothing.

**Waits are immune** — a metadata query cannot queue on provisioning — and Table 1 proves it:
`waits == waits_real` on all 9 days. So the provisioning-wait instrument (the headline) was
always sound; only the awake-time instrument was polluted.

⛔ **Do NOT retro-fit this filter into `report_e11_24_wake_census.py` while the soak is open** —
it would break comparability with that soak's own T+0/T+1 readings. Fix it after 08-09.
Consequence to carry until then: **awake-minute LEVELS are not trustworthy, and deltas only are
if the metadata share is stable — it is not (40%→138%).** The prior weather-poller credit
(167→141) was measured with the polluted instrument and has **not** been re-checked here.

### 2. ⭐ The aggregate lies across a flip — and it lied to this session first

A 6-day aggregate put `feature_pregame_umpire_features` at **23 waits, top of the board**. The
per-day cut shows it running as a **view with 0 waits since 08-06**; those waits are pre-flip
residue. This is the same landmine the 08-03 session recorded, stepped in again by the session
built to close it. **Only Table 6 (per-day) may be quoted for a verdict.**

---

## Target 6 is VERIFIED LANDED (and the wake it moved is measured)

Executions HOLD, waits → 0, and the DDL kind flips `transient table` → `view` on exactly 08-06.
Three independent signals agreeing rules out "the caller died":

| object | 08-03 | 08-04 | 08-05 | 08-06 | 08-07 | 08-08 |
|---|---|---|---|---|---|---|
| `stg_statsapi_umpire_game_log` | 8/5 | 11/7 | 13/9 | **12/0 v** | **8/0 v** | **9/0 v** |
| `feature_pregame_umpire_features` | 8/5 | 11/7 | 13/11 | **12/0 v** | **8/0 v** | **9/0 v** |
| `feature_pregame_lineup_features` | 8/3 | 11/4 | 13/3 | **12/0 v** | **8/0 v** | **10/0 v** |
| `feature_pregame_starter_features` | 8/3 | 11/2 | 13/5 | **12/0 v** | **8/0 v** | **10/0 v** |

*(execs/waits; `v` = created as a VIEW)*

**Mechanism proof, not assertion.** Table 5's control: across the 9-day window, **every
`create or replace view` statement — 30 distinct objects, 837 executions — shows 0 waits and
`metadata_only == execs`.** A view flip provably removes the wake. Any `view` row carrying a
wait would falsify the thesis; there are none.

### …and the wake it vacated was inherited, not deleted

The EB merges ran ~8–15×/day for six days with **zero** waits, then took **5–7 waits/day each
from the exact flip date**, with executions unchanged:

| statement | 07-31 | 08-01 | 08-02 | 08-03 | 08-04 | 08-05 | **08-06** | 08-07 | 08-08 |
|---|---|---|---|---|---|---|---|---|---|
| `merge … eb_batter_posteriors_raw` | 15/0 | 13/0 | 9/0 | 8/0 | 11/0 | 13/0 | **12/7** | **8/5** | **10/6** |
| `merge … eb_starter_posteriors` | 15/0 | 13/0 | 9/0 | 8/0 | 11/0 | 13/0 | **12/7** | **8/4** | **10/5** |
| `… game_features_raw__dbt_tmp` | 17/2 | 13/0 | 9/0 | 8/0 | 11/0 | 13/0 | **12/2** | 8/0 | **10/2** |

Total resumes fell over the same period (34→29/day), so this is not "more resumes happened" — the
same resumes are now attributed to different statements. That is wake **promotion**, and it is
the strongest possible evidence that **#675 is the correct successor**: the blocker it removes is
now the single largest waker on the board.

📌 **This also corrects #675/#662's own sizing.** The recap measured "9 tick-band waits on 08-07"
by reading only the 14–23 UTC band. The full-day figure is **11–13 waits/day on the EB pair
alone** — the pair's waits mostly land in the daily-build band, not the tick band.

---

## The overnight band (00-07, zero games) — the literal-zero blocker is NOT the pipeline

Filtered to warehouse-occupying queries, 9 days:

| waits | execs | awake min | days | identity | what |
|---|---|---|---|---|---|
| **41** | 293 | 10 | 3 | `DBT_RW` | **GitHub CI running dbt against the prod warehouse** |
| 14 | 44 | 6 | 4 | `CCL1196` | Snowsight cost-dashboard browsing |
| 5 | 8 | 4 | 4 | `CREDENCE_API` | the API Lambda reading Snowflake at request time |
| 5 | 5 | 5 | 1 | `DBT_RW` | scd2 signal writers |
| 4 | 26 | 6 | 4 | `CCL1196` | Snowsight metering/audit |
| 2 | 26 | 15 | 4 | `DBT_RW` | misc |

⭐ **Nothing in the nightly pipeline wakes `COMPUTE_WH` between 00:00 and 07:00 UTC.** The
overnight band is already pipeline-clean. What blocks literal-zero overnight is **CI, a human's
browser, and the API Lambda** — none of which is a serving-path change and none of which needs a
soak.

**Attribution of the CI mass — and a correction I made mid-session.** The query tag reads
`dbt_manual|dev`, which looks like a laptop run. It is not: `dbt_build_ci.yml` sets neither
`DBT_JOB_NAME` nor `TARGET_ENV`, so CI inherits the same fallback tag. **The run times settle
it** — every `ci_betting` burst matches a workflow run to the hour:

| `ci_betting` activity (UTC) | `dbt_build_ci.yml` runs |
|---|---|
| 08-06 05h — 64 execs, 14 waits | 05:49, 05:52 |
| 08-07 03h — 124 execs, 17 waits | 03:52, 03:53 |
| 08-07 04h — 89 execs, 6 waits | 04:26, 04:30, 04:40, 04:43 |
| 08-03 16h — 14 execs, 1 wait | 16:34, 16:38 |

Cause: **`dbt/profiles.yml` hardcodes `warehouse: COMPUTE_WH` on all three Snowflake targets**
(`baseball_betting_and_fantasy`, `dev`, **`ci`**). The workflow's `SNOWFLAKE_WAREHOUSE` secret is
never read by the profile. CI fires on `dev→main` promotion PRs, which land late-US-evening =
UTC overnight — hence the whole mass sits in the zero-game band.

⚠️ Magnitude is **dev-activity-dependent**, not a fixed nightly cost: zero on 08-04/05/08.

---

## The `other` board — every statement that woke the warehouse, with its owner

Owners attributed by grepping the repo, not the DAG (INC-27). Rates are per day over 08-06→08-08.

| waits/day | wake % | statement | owner | class |
|---|---|---|---|---|
| ~11–13 | 17% | `merge … eb_batter_posteriors_raw` / `eb_starter_posteriors` | dbt EB models | **WAKER** (promoted by target 6) |
| ~2.3 | **100%** | `SELECT COUNT(*) FROM lakehouse_ext.stg_statsapi_games` | `check_data_freshness.py::_is_game_day` | WAKER |
| ~2 | 38% | `create or replace transient table … feature_pregame_team_features` | dbt model | WAKER |
| ~2 | ~4% | `… feature_pregame_game_features{,_raw}__dbt_tmp` | dbt models (PR #662) | WAKER |
| ~1–5 | **100%** | `UPDATE … feature_pregame_lineup_state` | SCD-2 writer | WAKER |
| ~1.1 | **100%** | `with spine as (… mart_game_spine …)` | `check_odds_coverage.py` | WAKER |
| ~1.1 | **100%** | `COUNT(DISTINCT game_pk) AS expected_games` | `check_prediction_coverage.py` | WAKER |
| ~1 | 100% | `SELECT * FROM … feature_pregame_market_features` | `backfill_market_features_scd2.py` | WAKER |
| ~2–4 | 33–67% | Snowsight cost UI (`COST_INSIGHTS`, `usage_in_currency`, `anomaly_insights`, `ACCOUNT_ROOT_BUDGET`) | human browsing (`CCL1196`) | **ZOMBIE** (overnight) |
| ~1 | 60–80% | `model_registry` / `pipeline_status` / `model_version` reads | `CREDENCE_API` (API Lambda) | ZOMBIE (overnight) |
| 0 | 0% | `SELECT * FROM daily_model_predictions`, `… layer4_h2h_decision …` | `parity_check_w7b.py`, `generate_pick_narratives.py` | high-exec, low-wake |

**No genuine 24/7 poller survives in `other`.** Every candidate turned out to be
cloud-services-only (correction 1). The remaining mass is bursty wakers plus two human/API
zombies. ⇒ on the current board, resumes are the right instrument and awake-minutes adds nothing.

---

## RANKED NEXT TARGETS

### 1. PR #675 — EB reader repoint (already code-ready, already sequenced)
**~11–13 waits/day — the largest single item on the board, and newly so.**
Fix class: repoint `update_player_posteriors_op`'s SF reads to S3, then flip the EB pair
`incremental`→`view`; **#662 rides along.** No new work — this session's contribution is
**confirming the target and correcting its size upward** (11–13/day, not 9 tick-band waits).
⚠️ **#675 gate applies in full:** the EB models are `merge` incrementals, so the SF table is a
permanently accumulating superset of the S3 rebuild (ghost rows). The flip is gated on whether a
reader spans the ACCUMULATED history — already analysed in #675; nothing here changes it.
Serving path → its own soak. Sequenced for the post-soak quiet window; **do not stack.**

### 2. `feature_pregame_team_features` — `table` → `view`
**~2 waits/day, steady, and untouched by target 6** (1–2/day before the flip, 2/day after — it
is now the top *unaddressed* rebuild waker).
```sql
{% else %}
{{ config(materialized='table') }}
select * from baseball_data.lakehouse_ext.feature_pregame_team_features
```
Byte-for-byte the item-1/target-6/#662 pattern: a `table` whose entire Snowflake body is a
pass-through of the ext table.
⭐ **#675's history-spanning-reader gate DOES NOT APPLY, and that is the point.** This is a
`table` (full replace each run), **not** a `merge` incremental — so the Snowflake relation is
identical to the ext table by construction. There are no accumulated ghost rows, therefore no
"does a reader span the history" question to answer. **Strictly safer than the EB pair.**
- SF consumer: `feature_pregame_game_features_raw` (which #662 turns into a view).
- ⚠️ The one thing a fix session must bound: **view-on-view read amplification.** #662 measured
  its own flip at native 0.17–0.51s vs view 0.73–1.04s; chaining a second view compounds it. Use
  #662's control measurement as the template — measure, don't assume.
- Serving path → soak. Natural rider on #675's window **only if** the amplification is measured
  first; otherwise its own flip.

### 3. The `check_*` guard cluster — 3 statements at a **100% wake rate**, ~4.5 waits/day
Every single execution resumes the warehouse — the highest wake-efficiency on the board, and the
cheapest to remove. All three already read S3-backed data through Snowflake; each is an
INC-27-class straggler repoint to DuckDB/S3.

| statement | owner | waits/day | tier |
|---|---|---|---|
| `SELECT COUNT(*) FROM lakehouse_ext.stg_statsapi_games` | `check_data_freshness.py::_is_game_day` | 2.3 | WARN |
| `with spine as (… mart_game_spine …)` | `check_odds_coverage.py` | 1.1 | ALERT→HALT |
| `COUNT(DISTINCT game_pk) AS expected_games` | `check_prediction_coverage.py` | 1.1 | **HALT** |

⚠️ `check_data_freshness` is the safest start (WARN tier). `check_prediction_coverage` is
**HALT-tier and unconditional** — a repoint there needs the 🟥 runtime gate (a real box run), not
just CI. No soak needed for any of them (all off the predict path), so this is good filler
between serving flips.

### 4. Point dbt CI off the production warehouse — **the largest overnight waker, one line**
> ✅ **CLOSED 2026-08-17 — implemented (08-10) AND now PROVEN under load.** `CI_WH` carries a real
> occupying write (`ref_teams` INSERT, X-Small, 107 ms provisioning wait) and the last `ci_betting`
> statement on `COMPUTE_WH` was **2026-08-10 05:53:51 UTC** — zero since. Verifier:
> `uv run python scripts/verify_ci_warehouse_repoint.py --since-minutes 2900` → PROVEN. Full record
> + the false-PASS bug found in the verifier's own clause (2):
> `docs/e11_24_literal_zero_snowflake.md` → "CI_WH PROVEN UNDER LOAD".

**41 overnight waits / 3 active days.** `dbt/profiles.yml` `ci:` target → a dedicated warehouse.
No serving risk, no soak, no runtime gate.
- Recommend a **dedicated `CI_WH`** (X-Small, `auto_suspend=60`). Requires an operator
  `CREATE WAREHOUSE` + a grant.
- ⛔ **Do not simply point CI at `MONITOR_WH`** — that is the cost-audit warehouse; loading it
  with CI compute makes its own metering noisy and undermines the instrument this whole story
  depends on.
- Consider the `dev` target too (same hardcoded `COMPUTE_WH`), which is what a session running
  dbt locally would resume.

### 5. `feature_pregame_lineup_state` SCD-2 `UPDATE` — 100% wake rate, 1–5 waits/day
Already named in the #662/#675 record as "the last + largest port". Appears only from 08-06 — a
third instance of promotion. Port the SCD-2 write off Snowflake; `scd2_upsert` is one shared
function behind all 8 generators, so it is one port for many callers.

### 6. Snowsight cost UI on `COMPUTE_WH` — ~14 overnight waits / 4 days
> ✅ **CLOSED — fix applied and RECONFIRMED 2026-08-17 against behaviour, not just config.**
> `CCL1196.default_warehouse = MONITOR_WH`; its last statement that ever occupied `COMPUTE_WH` was
> **2026-08-08 07:19:50 UTC**, and 08-09 → 08-17 is **zero billable / zero waits** there (8 days).
> ⚠️ It still shows 6–48 `COMPUTE_WH` statements/day, but all are `warehouse_size IS NULL` Snowsight
> session bootstrap — cloud-services-only, cannot resume a warehouse. **Do not re-open target 6 on
> that row count** (it is correction 1 of this document presenting again). No `ALTER USER` needed.

Not a repo change: the `CCL1196` user's **default warehouse** is `COMPUTE_WH`, so opening the
cost dashboard resumes production. Switch that user's default to `MONITOR_WH` (console/operator
setting). Ironic and worth stating plainly: **reading the cost dashboard costs credits.**

### 7. `CREDENCE_API` reading Snowflake at request time — ~1 wait/day, incl. overnight
Three shapes (`model_registry`, `pipeline_status`, `model_version`). Small in wake terms but a
standing violation of the project rule that **Snowflake is never on a request path**; it also
means a user request can be blocked behind a warehouse resume. Repoint to DynamoDB / the S3
api-cache. Owner: `app/backend/routers/admin.py` and siblings.

---

## NOT VERIFIED — do not inherit these as settled

- **No box run, no flip, no deploy.** This is a read-only measurement session by construction.
- **Wake ↓ does not imply credit ↓.** Nothing here measures credits. The bill only moves when the
  warehouse actually stays suspended for long stretches (E11.20-COST). Every figure above is a
  *resume/wait* count.
- **The prior weather-poller awake-time credit (167→141) was measured with the polluted
  instrument** (correction 1) and is **not** re-validated here. Re-read it after the soak closes,
  with the `warehouse_size` filter.
- **Wake promotion is a strong inference, not a controlled experiment.** Its support: executions
  held across the boundary, waits appeared on three independent downstream statements on exactly
  the flip date, and total resumes *fell*. A controlled test would require un-flipping.
- **Target-6 credit is not this session's to award.** The T+3 read on Sun 08-09 owns that; the
  per-day table above is corroborating evidence, measured mid-soak.
- **08-08 is ~23h complete** (`query_history` lag 3 min at time of reading), not a full day.
- The `ci_betting` overnight mass is **dev-activity-dependent** — zero on three of nine days.
  Do not annualise it from this window.

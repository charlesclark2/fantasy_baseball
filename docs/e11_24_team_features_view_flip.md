# E11.24 — `feature_pregame_team_features` `table` → `view` (2026-08-15)

**One flip, one soak.** This session flips exactly one model and does **not** touch the
`feature_pregame_lineup_state` SCD-2 port — that is the chain's second flip and gets its own
session (stacking two serving flips violates one-flip-per-soak).

Target: ranked item **2** in `docs/e11_24_other_attribution.md` — *"~2 waits/day, steady, and
untouched by target 6 … the top **unaddressed** rebuild waker."*

⚠️ **`best_alpha = 0` throughout — no bet rides on any of this.**

---

## The change

```diff
  {% else %}
- {{ config(materialized='table') }}
+ {{ config(materialized='view') }}
  select * from baseball_data.lakehouse_ext.feature_pregame_team_features
  {% endif %}
```

Snowflake branch only. The DuckDB branch — which is the real assembly and produces the S3 parquet
the external table is defined over — is untouched.

---

## Pre-flight (the STOP gate) — result: **PASS**

### 1. No SF-side materialization consumer

Every reference was found by grepping the repo (`.py` string literals, `.sql`, `.yml`, `.sh`,
Dockerfiles, crontabs), **not** `dbt ls` / the DAG — INC-27, because a raw-SQL string consumer is
invisible to the manifest.

| Consumer | Path | Reads | Needs a TABLE? |
|---|---|---|---|
| `feature_pregame_game_features_raw` (`ref()` ×2) | **DuckDB branch only** | the DuckDB view | No — see §2 |
| `generate_run_env_signals.py` (2 aliases) | **daily job**, HALT-gated by `signal_freshness_check` | SF `betting_features.*` unless `--s3` | No |
| `train_run_env.py` | offline training | SF | No |
| `ablate_gb_fb_park_interaction.py`, `ablation_eb_bullpen_features.py` | offline research | SF | No |
| `parity_check_w8a.py` | operator-manual — **wired into no job** | SF vs parquet | No (see caveat) |
| `run_w1_lakehouse.py`, `refresh_w1_external_tables.py`, `export_w8a_precursors_to_s3.py` | build the parquet / ext table — **upstream** | — | No |
| `app/pages/1_Today_Picks.py` | ⛔ deprecated Streamlit, not deployed | — | No |
| `check_data_freshness.py:38` | prose comment naming the waker | — | No |

**No writers.** A repo-wide scan for `merge into` / `insert into` / `update` / `delete from` /
`create or replace table` against this relation returns nothing — so INC-27's sibling hazard ("no
reader blocks it" ≠ "no writer does"; a `MERGE INTO` a view fails outright) does not apply. This is
now a mechanical guard clause, not a one-off grep.

**No type contract.** `dbt/type_contracts/` has no entry for this model, so INC-19's TYPE-PIN
surface is untouched — and a view has no stored type to drift in the first place.

### 2. ⭐ Read amplification — bounded, and there is **no view-on-view chain**

This **corrects the premise** in `e11_24_other_attribution.md` item 2, which named
`feature_pregame_game_features_raw` as the SF consumer that would chain a second view. It is not
one: that model's two `ref('feature_pregame_team_features')` calls both sit inside its **DuckDB**
branch (source lines 122/127, between the `{% if %}` at 40 and the `{% else %}` at 2277), and its
**Snowflake** branch reads its own external table,
`lakehouse_ext.feature_pregame_game_features_raw`. Nothing chains onto this view. Pinned by clause 4
of the guard, so a future repoint of that branch cannot silently invalidate the bound.

Reads added on the Snowflake relation, per day:

| Reader | Schedule | Ext-table scans added/day |
|---|---|---|
| `generate_run_env_signals.py` | daily job, 2 aliases × `_recent_completed_dates()` (2 dates) | **4** |
| everything else | offline / operator-manual, on no schedule | 0 |

⭐ **The empirical control.** The run_env query joins its feature tables on `game_pk` with the date
filter on the *driving* table (`mart_game_results`), not on the feature side — so the join shape is
identical for all of them. Two of the five feature tables in that **same query** are already views
over `lakehouse_ext`, and one of them (`feature_pregame_starter_features`) is joined **twice**,
exactly as `team_features` is:

| joined in the run_env query | Snowflake materialization |
|---|---|
| `feature_pregame_starter_features` (×2) | **view since 2026-08-05** (`5ac709f2`, target 6) |
| `feature_pregame_umpire_features` | **view since 2026-08-05** (`5ac709f2`, target 6) |
| `feature_pregame_park_features` | table |
| `feature_pregame_weather_features` | table |
| `feature_pregame_team_features` | ← this flip |

So the precise amplification shape this flip adds has been running in production **on this exact
query for 10 days** (re-measured 2026-08-15; the first draft said "since 08-06 / 9 days" — the flip
commit is dated 08-05). Per-read scale from #662's own control: native 0.17–0.51 s vs view
0.73–1.04 s. ⇒ bounded at roughly **+2–4 s/day** of additional scan on one WARN-adjacent generator,
against ~2 provisioning waits/day removed. **Amplification accepted; no STOP.**

⭐ **And the 4-scan figure is an UPPER BOUND, not a point estimate.** `generate_run_env_signals_op`
passes `_w9_s3_read_args()`, so under `W9_LAKEHOUSE_S3_READS=1` that generator reads the S3 lakehouse
via DuckDB and touches this Snowflake relation **zero** times. That flag is not in
`services/dagster/aws/env.required`, so its live box state is unenforced — which can only make this
bound *tighter*, never looser. (See the NOT-VERIFIED list.)

### 3. Freshness is monotonically improved, not traded

As a `table` the content was the ext table's content **as of the last dbt run**; as a view it is the
ext table's content **now**. The ext table is refreshed daily via `refresh_w1_external_tables.py`
(`W8A_TABLES`, called by the `--w8a` mirror op immediately after the `--w8a` build). Last-refresh-
before-now ≥ last-refresh-before-the-last-dbt-run, so the view is always **fresher-or-equal** —
never staler.

---

## Correction to the story framing (worth carrying forward)

The card describes this as the *"intraday EB/lineup chain"* flip. Measured against the source:
`feature_pregame_team_features` is **not** in `sensor_ops.lineup_dbt_feature_rebuild` (the intraday
tick selector — 0 occurrences). It is rebuilt by the **daily** `dbt_umpire_feature_rebuild`
(HALT-tier). That matches the attribution doc's own wording ("rebuild waker", ~2/day steady) and it
means the wake removed lands in the **daily build band, not the tick band**. It does not change the
flip's safety or its ranking; it does change which band the soak read should look at.

⚠️ Consequence for the runtime gate: `dbt_umpire_feature_rebuild` is the op INC-40 identified as
building the `bullpen_eb` / `umpire` coverage blocks, and `feature_pregame_team_features` is on that
path. **The live-slate check must confirm those blocks still populate**, not merely that the view
exists.

---

## Guard

`betting_ml/tests/test_e11_24_team_features_is_a_view.py` — 7 clauses, deliberately a **separate
file** from `test_e11_24_pregame_features_are_views.py` rather than an added registry entry, because
two of that file's clauses do not fit this model and folding it in would couple unrelated stories
(the E9.60 lesson):

* its clause 3 requires an **`incremental` DuckDB branch**; this model's DuckDB branch is a `view`
  (W8a layer — `run_w1_lakehouse._build_w8a` COPYs its output to parquet).
* its clause 5 pins membership of the **intraday tick** selector, which this model has never been in.

Clauses here: (0) anti-vacuity/preconditions · (1) SF branch is a view, asserted **both ways** so a
revert goes red · (2) SF branch is still a pure ext-table copy — the precondition that makes a view
free · (3) DuckDB branch still does the real build, and is not circular · (4) no view-on-view chain
from the consumer · (5) still in the **daily** rebuild selector · (6) nothing in the repo writes to
the relation.

**RED-PROVEN.** All 8 deliberate source breaks were confirmed to turn the owning clause red before
the guard was trusted. The harness applies each mutation in-process and **asserts the mutation
actually landed** before invoking pytest (#682) — which earned its keep immediately: the first cut
of the "gut the build branch" break replaced only the *first* of two `mart_game_spine` references,
so the break never landed and the clause reported a **false GREEN**. Fixing the mutation (replace
all occurrences) turned it red.

---

## Verification done (first cut, 2026-08-15, base `df30a5cb`)

| Check | Result |
|---|---|
| `dbt compile` (fusion, Snowflake target) | ✅ 1516/1516 success |
| Compiled manifest materialization | ✅ `feature_pregame_team_features -> view` (matches its already-flipped siblings) |
| New guard + sibling guard + related guards | ✅ 423 passed |
| `serving-ops` fast-gate shard (`-n 4`) | ✅ 1539 passed, 6 skipped |
| RED proof | ✅ 8/8 breaks go red |

---

## RE-VERIFICATION against current `dev` (2026-08-15, base `c54fde0e`, +106 commits)

The claims above were made on a base **106 commits old** — predating the Stripe go-live, NF-W7c,
MH2.6 and the E11.24 Bundle. Re-verified before handing over a deploy, because a stale pre-flight is
not a pre-flight (the "a card written days before pickup can carry a false premise" rule).

### Merge

`origin/dev` merged in cleanly. `git diff --name-only origin/dev HEAD` is **exactly the 3 story
files** — no dev commit touched them, no changelog collision, nothing resolved by hand.

### Every pre-flight claim, re-measured

| Claim (as of `df30a5cb`) | Re-measured against `c54fde0e` | Verdict |
|---|---|---|
| Only scheduled SF reader is `generate_run_env_signals.py` | `git log -S"feature_pregame_team_features" 15ab3516~1..origin/dev` → **0 commits**. No dev commit added or removed *any* reference. | ✅ HOLDS |
| No writer | guard clause 6 re-run over the merged tree → 0 offenders; and no dev-changed file references the model at all | ✅ HOLDS |
| No type contract (INC-19 TYPE-PIN untouched) | `dbt/type_contracts/` has 6 entries, none for this model; `gen_type_contract.CONTRACTS` unchanged | ✅ HOLDS |
| No view-on-view chain | ⭐ now confirmed at the **manifest** level, not just by reading source: `dbt ls --select feature_pregame_team_features+ --resource-type model` on the SF target returns **only the model itself — no children**. The `{% if target.name %}` Jinja means the consumer's `ref()`s are never rendered on the SF target, so the edge does not exist in the SF graph at all. | ✅ HOLDS (stronger evidence than the first cut) |
| DuckDB branch is still a `view` (so clause 3's rationale stands) | `config(materialized='view', tags=['w8a_lakehouse'])` at line 30 — unchanged | ✅ HOLDS |
| Still on the INC-40 `bullpen_eb`/`umpire` coverage path via daily `dbt_umpire_feature_rebuild` | still in that op's selector, beside `mart_bullpen_effectiveness`; and dev's own `test_feature_block_guard_ordering.py::test_the_producer_still_builds_the_blocks_the_guard_asserts_on` independently pins that membership | ✅ HOLDS |

### Blast radius, measured rather than argued

`dbt ls --select state:modified+ --resource-type model --state <prod baseline> --defer` selects
**exactly one model** — `feature_pregame_team_features` — plus its 13 `not_null` tests. Nothing
downstream. (Prod manifest baseline pulled from the `dbt-manifest` artifact, run `31853736300`.)

⚠️ **Those 13 `not_null` tests declare no `severity`, so they default to `error`** = serving-critical
under the E11.7 contract, and **INC-41's `check_dbt_test_results_op` pages on a red error-severity
test**. They are therefore part of the runtime gate: a view over the same ext table returns the same
rows, so they must stay green — if one goes red the flip is the first suspect.

### The view DDL was actually executed (not just compiled)

Rehearsed on the **isolated `dev` target** (schema `dev_betting_features`, never prod):

```
Succeeded [ 1.18s] model dev_betting_features.feature_pregame_team_features (view)
```

dbt reports the relation type as `(view)`, so the table→view transition executes for real against the
live external table. `dbt run` only — **the 13 tests were deliberately excluded**, see below.

### Re-run gates

| Check | Result |
|---|---|
| `dbt compile` (fusion, SF target) on the merged tree | ✅ 1516 / 1516 success |
| new guard + sibling views guard + ordering guard + type-contract guard + fast-gate hygiene | ✅ **402 passed** |
| `serving-ops` shard (owns the new guard), `-n 4` | ✅ **1588 passed, 7 skipped** |
| `guards` shard, `-n 4` | ✅ **624 passed** |
| RED proof, re-run against the merged base | ✅ **11 / 11** breaks turn the *owning* clause red |

### Two defects found by the re-verification

1. **A false premise in the shipped code comment (fixed).** The model's new header said the table DDL
   ran "on every daily build **AND on every intraday lineup tick** (it sits in the
   `lineup_dbt_feature_rebuild` selector)" — which **contradicts the commit message, the guard's own
   docstring, and the source** (0 occurrences in `sensor_ops`). A false premise in a *comment* is
   worse than in a doc, because the next reader takes their reasoning off it (#675). Corrected to name
   the daily op and to state the intraday non-membership explicitly.
2. ⭐ **A RED-proof landing-assert is necessary but NOT sufficient — the mutation must also remove the
   thing the clause asserts.** Re-running the RED proof, break 3 ("gut the DuckDB build branch") came
   back **GREEN**. Not a vacuous guard: the harness appended `_XX` to the mart name, and
   `"mart_bullpen_effectiveness_XX"` still *contains* the substring clause 3 asserts, so the mutation
   landed on disk (satisfying #682) and still did not **bite**. Re-run with a substring-safe rename it
   goes red on all four directions (each of the 3 marts, plus the circular-`lakehouse_ext` direction).
   ⇒ **#682's "assert the mutation landed" catches a mutation that does not WRITE; it cannot catch one
   that writes and does not BITE. A RED proof must also assert the asserted token is GONE.**

---

## ⛔ NOT VERIFIED — do not inherit these as settled

* **No box run.** CI mocks all IO, so the 🟥 runtime gate is **open** and is an operator step.
* **No Snowflake measurement was taken by this session.** The Snowflake MCP connector is
  unauthenticated in this environment, so the read-cost bound in §2 rests on the structural argument
  + the 10-day production control + #662's measured per-read figures — **not** on a fresh query of
  this model. The operator's soak read is what confirms it.
* ⛔ **No warehouse query was run from the laptop, DELIBERATELY.** The row-identity read
  (`count(*)`/checksum, view vs ext table) would occupy `COMPUTE_WH` and inject laptop resumes into
  the very per-day census window the operator reads to judge *this* flip — the repo's own precedent
  is to keep laptop Snowflake work off `COMPUTE_WH` during a soak (the 2026-08-08 measurement was
  taken on `MONITOR_WH` for exactly this reason). Row identity is true by construction
  (`select * from <ext table>`) and its live confirmation belongs in the operator's box gate, where
  the warehouse is already awake. Same reason the `dev`-target rehearsal ran `dbt run` and **not**
  `dbt build`: a `create or replace view` / `drop table` is metadata-only and cannot resume a
  warehouse, but the 13 `not_null` tests are real queries that would.
* **No credit saving is claimed.** Wake is a QUEUE (#679): this promotes the next
  warehouse-occupying statement in the chain into the waker role. Removing ~2 waits/day of rebuild
  wake is a step toward the warehouse suspending on zero-game windows — it is **not** a standalone
  credit win, and must not be booked as one.
* **`parity_check_w8a.py` becomes tautological for this model** — it will now compare the ext table
  to the parquet the ext table is defined over. Pre-existing for every already-flipped sibling, not
  introduced here, but do not read a green parity on this model as evidence of anything.
* **`W9_LAKEHOUSE_S3_READS` is default-OFF and unregistered in `env.required`.** If it is ever set
  to `1` on the box, `generate_run_env_signals.py` stops reading Snowflake entirely and the last
  scheduled reader of this relation disappears. Worth confirming against the **live container env**
  rather than the docs (the `W7B_LAKEHOUSE_S3` documented-≠-set class) when sizing the next lever.

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
| `feature_pregame_starter_features` (×2) | **view since 2026-08-06** |
| `feature_pregame_umpire_features` | **view since 2026-08-06** |
| `feature_pregame_park_features` | table |
| `feature_pregame_weather_features` | table |
| `feature_pregame_team_features` | ← this flip |

So the precise amplification shape this flip adds has been running in production **on this exact
query for 9 days**. Per-read scale from #662's own control: native 0.17–0.51 s vs view 0.73–1.04 s.
⇒ bounded at roughly **+2–4 s/day** of additional scan on one WARN-adjacent generator, against
~2 provisioning waits/day removed. **Amplification accepted; no STOP.**

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

## Verification done

| Check | Result |
|---|---|
| `dbt compile` (fusion, Snowflake target) | ✅ 1516/1516 success |
| Compiled manifest materialization | ✅ `feature_pregame_team_features -> view` (matches its already-flipped siblings) |
| New guard + sibling guard + related guards | ✅ 423 passed |
| `serving-ops` fast-gate shard (`-n 4`) | ✅ 1539 passed, 6 skipped |
| RED proof | ✅ 8/8 breaks go red |

---

## ⛔ NOT VERIFIED — do not inherit these as settled

* **No box run.** CI mocks all IO, so the 🟥 runtime gate is **open** and is an operator step.
* **No Snowflake measurement was taken by this session.** The Snowflake MCP connector is
  unauthenticated in this environment, so the read-cost bound in §2 rests on the structural argument
  + the 9-day production control + #662's measured per-read figures — **not** on a fresh query of
  this model. The operator's soak read is what confirms it.
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

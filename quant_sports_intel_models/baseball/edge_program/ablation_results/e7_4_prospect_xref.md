# E7.4 — Prospect identity & ETA xref (`dim_player_xref`)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "an identity/ETA cross-reference BUILD status report (rows landed, tripwires clear) \u2014 no arms, no fold structure.",
 "schema": 1,
 "source_artifact": null,
 "status": "exempt",
 "verdict": null
}
-->


**Status:** ✅✅ **DONE + LANDED + VERIFIED (2026-07-27).** Operator-run; 40,449 rows landed at
`s3://baseball-betting-ml-artifacts/baseball/milb/derived/dim_player_xref`. Every tripwire clear and
every AC join verified against the LANDED table (§8).
**Deliverable:** `baseball/milb/derived/dim_player_xref` (Delta) — the MLBAM-spined prospect identity dimension.
**Builder:** `betting_ml/scripts/milb_xref/player_xref.py` (pure, tested) + `build_player_xref.py` (CLI).
**Unblocks:** E8.0's clean board join · E7.8's prospect→realized-MLB link.

---

## 1. The bridge, and why it routes the way it does

MLBAM `person.id` is **one stable id for a whole career, minors and majors** — so it is the spine.
FanGraphs is the fragmenter: a stable minor id (`minorMasterId` → `fg_minor_id`, always `sa`-prefixed)
plus a **separate numeric MLB id assigned at debut** (`fg_mlb_id`). THE BOARD carries **no MLBAM id at
all** (the column exists and is 100% NULL — confirmed live), so the prospect→MLBAM bridge routes
through the E7.7 *leaderboard* feed, which carries both ids:

```
board.fg_minor_id ─HOP1─▶ fg_leaderboards.fg_minor_id ─HOP2─▶ fg_leaderboards.mlbam_id (xMLBAMID) ─▶ MLBAM SPINE
board.fg_player_id (numeric ⇒ fg_mlb_id) ─HOP3─▶ fg_{hitting_leaderboard,stuff_plus}_raw $.playerid → $.xMLBAMID ─▶ MLBAM SPINE
```

HOP 3 is both a **fallback** (a graduate who stops appearing on MiLB leaderboards) and the **only
source of `fg_mlb_id`** — the id the story requires so a graduate's minor and major records reconcile.

---

## 2. Per-key match rates — measured on the REAL lake (2026-07-27)

Every rate below was counted against the live S3 lake, not inferred from the docs. This is the P1.2b
discipline: the documented recruit↔college key matched 7 rows where the real key matched 60,883, so a
plausible-but-wrong key ships a green-everywhere, near-empty mart.

### HOP 1 — `board.fg_minor_id` → `fg_leaderboards.fg_minor_id`

| board season | board ids | matched | rate |
|---|---|---|---|
| 2018 | 721 | 718 | **99.6%** |
| 2019 | 948 | 947 | **99.9%** |
| 2020 | 1,135 | 1,134 | **99.9%** |
| 2021 | 1,206 | 1,205 | **99.9%** |
| 2022 | 1,242 | 1,240 | **99.8%** |
| 2023 | 1,177 | 1,176 | **99.9%** |
| 2024 | 1,152 | 1,150 | **99.8%** |
| 2025 | 1,283 | 1,282 | **99.9%** |
| **2026 (current)** | **1,286** | **1,277** | **99.3%** |

⚠️ **The bridge must be season-AGNOSTIC.** A same-season join drops to **79–96%** (2020 → **0%**: the
board publishes a 2020 list, but COVID cancelled the MiLB season so no 2020 leaderboard exists). The
id pair is career-stable, so the newest observation of the pair is the correct one. A same-season join
would have looked "reasonable" and silently lost ~5% of every board.

### HOP 2 — `fg_leaderboards.mlbam_id` (`xMLBAMID`) → the MLBAM spine

* **Populated: 71,680 / 71,680 = 100.0%.** Numeric-shaped: **100.0%**. The key itself is clean.
* Landing in a spine source, by level — a miss here is **E7.1 level COVERAGE, not a bad key**
  (E7.1 ingests sportIds 11–14 = AAA/AA/A+/A only):

| level | matched / ids | rate | |
|---|---|---|---|
| AAA · AA · A+ · A, and **every multi-level combination** (`AA,AAA`, `A,A+,AA,AAA`, …) | e.g. 5,082/5,082 · 3,290/3,290 · 3,553→3,552 · 4,603→4,602 | **100.0%** | full-season affiliates |
| A− (short-season) | 624/872 | 71.6% | not an E7.1 sportId |
| CPX (complex) | 2,417/4,235 | 57.1% | not an E7.1 sportId |
| R (rookie) | 2,207/4,893 | 45.1% | not an E7.1 sportId |
| DSL | 1,771/6,533 | 27.1% | not an E7.1 sportId |

The clean split is the tell: **every level E7.1 ingests is at 100.0%, and only levels it does not
ingest fall short.** That is a coverage boundary, not a key failure. These players still get a
dimension row with a genuine MLBAM id — `in_milb_game_logs=false` tells the truth rather than dropping
them, which matters because DSL/complex/rookie players are precisely the youngest prospects a dynasty
board cares about.

### HOP 3 — `board.fg_player_id` (numeric ⇒ `fg_mlb_id`) → MLB FanGraphs `$.xMLBAMID`

**1,717 / 1,766 = 97.2%** (the graduate leg).

### CHAIN — current board snapshot → MLBAM ⭐ *the join E8.0 and E7.8 depend on*

**1,277 / 1,286 = 99.3%** (1,277 via the leaderboard leg; the graduate leg adds 0 on this snapshot
because the leaderboard leg already covers them — it earns its place as `fg_mlb_id`'s source and as
the fallback for graduates who age off the minors boards).

### Unresolved handling — 9 on the current board (0.7%); 16 across all board history

All nine current-board misses are `level=NULL` international signees / recent draftees with **no
professional record anywhere**, ETA 2026–2032:

| player | org | FV | ETA |
|---|---|---|---|
| Jose Luis Acevedo | BAL | 42 | 2032 |
| Michael Massey | DET | 40 | 2026 |
| Micah Bucknam | TOR | 40 | 2028 |
| Griffin Hugus | SEA | 40 | 2029 |
| Peyton Prescott | NYM | 37 | 2028 |
| Joshua Flores | MIL | 37 | 2031 |
| Sean Episcope | MIL | 37 | 2029 |
| Peter Kussow | NYM | 37 | 2031 |
| River Hamilton | DET | 37 | 2031 |

They are emitted honestly: `mlbam_id` NULL, `mlbam_match_method='unresolved'`,
`mlbam_match_confidence='none'`, `xref_key='fg:<fg_minor_id>'`, prospect attributes intact.

**No fuzzy name matching — deliberately.** Name-equality against the MiLB game logs produced exactly
one hit across the nine, and it was a **FALSE POSITIVE**: prospect "Michael Massey" (DET, FV 40, ETA
2032) vs. MLB second baseman Michael Massey (MLBAM 686681, Royals) — two different people. There is no
MLBAM id to find for a player who has not played a professional game, so a fuzzy leg here buys nothing
and costs a wrong identity. No match beats a wrong match. A guarded fallback can be added if a future
snapshot shows a residual with real pro records behind it; today's residual does not.

---

## 3. 🚨 Landmines found (both would have silently poisoned E8.0)

**1. `delta_scan` CANNOT read `baseball/milb/the_board`.**
Its `mlbam_id` column is 100% NULL → pyarrow inferred the arrow `null` type → the Delta schema records
`"void"` → DuckDB's Delta reader hard-errors `Unsupported Delta table type: 'void'` on the **whole
table**. The sanctioned reader is `DeltaTable(...).to_pyarrow_dataset()` (`player_xref.register_board`).
*Root cause fixed:* `ingest_fangraphs_prospects_to_s3.py` now pins its string columns to
`astype("string")` before the arrow conversion, so a future all-NULL pull can't recreate a `void`
column. The already-written partitions keep the void schema until a full re-backfill, so the
pyarrow-dataset reader stays regardless. Same class as the INC-17 nullable-int→DOUBLE mirror poisoning:
an all-null column silently picks a type nobody wants — pin it at the writer.

**2. A `read_parquet('…/the_board/**/*.parquet')` glob reads TOMBSTONED files and *fabricates* a bad
match rate.** The 2026-07-27 partition globs to **3,870 rows across three superseded ingest
generations** vs. the Delta-ACID truth of **1,290**. Worse, the superseded generation extracted
`fg_minor_id` differently (numeric MLB ids for graduates, because `minorMasterId` fell through to
`playerid`) — which drags the *measured* HOP-1 rate from **99.3% down to 84.2%**. The first pass of this
analysis used a glob and produced exactly that wrong number. Same class as the E11.20 phase-1.5
path-reader incident: **a Delta table has no valid glob reader.**

---

## 4. `dim_player_xref` — grain, columns, provenance

**Grain:** one row per **`mlbam_id`** (the spine), plus one row per board prospect the deterministic
legs could not resolve (`mlbam_id` NULL, keyed on `fg_minor_id`). `xref_key` is the non-null identity
key either way ⇒ exactly one row per person, asserted at build time.

**Universe:** every identity in E7.1's MiLB game logs ∪ the MLB player master ∪ the FanGraphs
leaderboards ∪ the resolved board. **Live build: 40,449 rows** — 40,433 resolved, 16 unresolved,
4,279 carrying prospect-board attributes.

| `mlbam_match_method` | rows |
|---|---|
| `milb_game_log_native` | 23,801 |
| `fg_leaderboard_xmlbamid` | 11,787 |
| `statsapi_profile_native` | 4,844 |
| `fg_mlb_leaderboard_playerid` | 1 |
| `unresolved` | 16 |

The graduate leg resolving only 1 identity outright is expected and **not** a reason to drop it: the
leaderboard leg already covers today's graduates, and the leg's real jobs are (a) supplying `fg_mlb_id`
— the id the story requires so a graduate's minor and major records reconcile — and (b) catching
graduates once they age off the minors leaderboards entirely.

| group | columns |
|---|---|
| identity | `xref_key`, `mlbam_id`, `fg_minor_id`, `fg_mlb_id` |
| dimension | `player_name`, `birth_date`, `age`, `position_code`, `current_level`, `org` |
| prospect (latest board) | `fv`, `risk`, `eta`, `overall_rank`, `org_rank`, `fantasy_dynasty_rank`, `fantasy_redraft_rank`, `board_season`, `board_as_of_date` |
| presence flags | `is_on_prospect_board`, `in_mlb_player_master`, `in_milb_game_logs`, `in_fg_leaderboards`, `mlb_active`, `milb_first_season`, `milb_last_season`, `milb_game_logs`, `fg_last_season` |
| provenance | `mlbam_match_method`, `mlbam_match_confidence`, `xref_version` |

`mlbam_match_method` ∈ `fg_leaderboard_xmlbamid` · `fg_mlb_leaderboard_playerid` ·
`statsapi_profile_native` · `milb_game_log_native` · `unresolved`. Confidence is `high` for every
deterministic vendor-published id pair and `none` for unresolved — so a downstream model can weight by
it rather than assume.

**`current_level` precedence:** an MLB profile ⇒ `'MLB'`; else newest MiLB game log; else the FanGraphs
leaderboard level (covers DSL/complex); else the board's own level.

**Joins:**
* to the existing MLB player xref — `dim_player_xref.mlbam_id = stg_statsapi_player_profiles.player_id`
  (a call-up links to his MLB identity; `in_mlb_player_master` flags it).
* to E7.3/E7.5 MLE output — `mle_projections.player_id` is the same MLBAM VARCHAR.
* to E8 / the E8.0 board — `fg_minor_id` (board-native) or `mlbam_id` (everything else).

---

## 5. Dead-bridge tripwires (the build FAILS LOUD, it does not ship an empty xref)

| tripwire | floor | measured |
|---|---|---|
| HOP 1 board→leaderboard, current season | 0.90 | **0.993** |
| HOP 2 `xMLBAMID` populated | 0.95 | **1.000** |
| HOP 2 `xMLBAMID` all-digits | 0.99 | **1.000** |
| end-to-end current-board resolution | 0.90 | **0.993** |

Plus hard invariants: every join key asserted unique before use, row counts asserted non-inflating
across the prospect resolution, and `xref_key` asserted unique on the final frame. Any breach raises
`XrefValidationError`. Floors sit **below** the measured rates with headroom — a floor that trips on
normal churn gets disabled, which defeats the point.

Because the Dagster op is WARN-tier, a tripwire breach fails the script loudly in the logs and **leaves
the last-good xref in place** rather than overwriting it with a near-empty crosswalk.

---

## 6. Wiring

`dim_player_xref_build_op` (WARN-tier) runs in `milb_ingest_job` as a **downstream fan-in of all four
ingest ops**, never a fifth peer. Built at job start it would crosswalk the previous cycle's board
against the previous cycle's leaderboards and silently miss every newly-listed prospect — the INC-25
"consumer parquet lags the stores" class, except silent (a stale xref still joins).

Performance: the graduate leg reads only the **newest `dt` snapshot per season** of the MLB FanGraphs
raw feeds. Those feeds re-land the full leaderboard every capture day (~230k ~10KB JSON rows), but an
id pair is career-stable — every extra snapshot re-derives the identical pair at full JSON-decode cost.

---

## 7. Tests

`betting_ml/tests/test_milb_player_xref.py` — 15 fast-gate tests, offline over local parquet fixtures
(the `XrefSources` indirection exists so the *same* join SQL is provable without a warehouse). Covers
both bridge legs, the graduate leg with the leaderboard leg removed, the `sa`-prefixed-`fg_player_id`
trap, the Michael Massey false-positive, snapshot dedupe, DSL coverage-vs-key, and every tripwire.
The happy path runs with the production tripwires **armed**.

---

## 8. Post-landing verification (against the LANDED Delta table, not the build frame)

The AC is "joins cleanly to the MLB player xref and to E8" — so it is checked on what actually
landed, by the same reader a consumer would use.

| check | result |
|---|---|
| **void-typed columns in the output** | **NONE** ✅ — the table did not reproduce the landmine it documents |
| **`delta_scan` readback** (what E8.0 will do) | **40,449 rows** ✅ — normal reader works; no special-casing needed downstream |
| **AC-1 → the existing MLB player xref** (`stg_statsapi_player_profiles`) | **6,571 / 6,571 = 100.0%** — every MLB player resolves; a call-up links to his MLB identity |
| **AC-2 → E7.3 batter MLE projections** | **6,365 / 6,365 = 100.0%** |
| **AC-2b → E7.3p pitcher MLE projections** | **7,474 / 7,474 = 100.0%** |
| **AC-3 → the E8.0 path end-to-end** | 4,279 board prospects → **4,263 carry an MLBAM id (99.6%)**, 1,812 have an MLE projection |
| identity uniqueness | 40,449 rows / **40,449 distinct `xref_key`** (zero dupes), 40,433 distinct `mlbam_id`, 40,433 stamped `high` confidence |

The 1,812-of-4,263 MLE coverage is **expected, not a gap**: an MLE projection only exists for a player
with enough MiLB plate appearances at a level E7.1 ingests, so unranked/complex-league/just-drafted
prospects have identity but no projection yet. The xref's job is the identity; the projection
coverage is E7.3's.

**`fg_mlb_id` population — a clarification on §4's provenance table.** `fg_mlb_leaderboard_playerid = 1`
counts rows *resolved by* the graduate leg (the leaderboard leg already resolves the rest). The number
of rows *carrying* a reconciled `fg_mlb_id` is **1,766 — every one of them alongside its
`fg_minor_id`**, which is the actual story requirement: a graduate's minor and major FanGraphs records
reconcile to one MLBAM person. (23,205 rows carry an `fg_minor_id`.)

Spot-check of the reconciliation, and a direct confirmation the reader fix worked: **Konnor Griffin →
`mlbam_id=804606`, `fg_minor_id=sa3065496`, `fg_mlb_id=35376`.** Under the tombstoned-glob read he
surfaced with `fg_minor_id=35376` (the numeric MLB id in the minor-id column) — the Delta-correct read
puts each id in its own column.

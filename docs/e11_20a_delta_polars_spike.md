# E11.20a — Delta Lake + Polars SPIKE (go/no-go, gotchas, patterns)

**Status:** DONE — 2026-07-02 · **Verdict: 🟢 GO** (adopt Delta-on-path + Polars for E11.20), with one **roadmap correction** and a bounded gotcha list below.
**Scope:** de-risking POC on ONE stable table. **NOT a migration. No production/serving change was made.**
This doc is the input to the full **E11.20** rollout plan (which still waits for the decommission finish → E11.22, per the roadmap sequencing).

Related: `build_roadmap.md` §V2 (E11.20/E11.21/E11.22) · `docs/e11_5_dbt_engine_decision.md` (sibling decision-doc format) · `services/dagster/aws/BOX_OPERATIONS.md`.

---

## 1. What was run

| | |
|---|---|
| **Target table** | `mart_pitch_characteristics` analogue — a **W1 pitch mart**: stable, already-S3, pitch-level high-volume, feeds the feature build but **non-serving-coupled**; **not** in W11-E scope, **not** in E1.11 scope → zero overlap, zero serving risk. |
| **Method** | Isolated venv, **local FS**, synthetic dataset whose schema + type-mix mirror the real mart (int64 PK, DATE, DOUBLE/FLOAT metrics, a `TIMESTAMP` column, partitioned by `game_year` over 2023–2026). **No prod S3 was touched.** |
| **Scale** | 1.5M rows × 15 cols (the mechanics + the 4 wins are scale-invariant; wall-clock caveats noted). |
| **Baseline** | The current `run_w1_lakehouse` pattern: DuckDB `COPY (…) TO '<model>/…' (FORMAT PARQUET)`, **full rebuild every run**. |
| **Harness** | `scripts/spikes/e11_20a_delta_poc.py` (committed; reproducible — see §8). |
| **Versions** | duckdb **1.5.4**, polars **1.42.1**, deltalake/delta-rs **1.6.1**, pyarrow **24.0.0**. ⚠️ box runs duckdb 1.5.3 — same delta-extension behavior (read-only), verify on cutover. |

---

## 2. Measured — Delta vs Parquet baseline (1.5M rows, local)

| Metric | Parquet baseline | Delta-on-path | Note |
|---|---|---|---|
| Full write | 0.37s | 0.80s | delta-rs writes a `_delta_log` + stats → ~2× write overhead (worth it for the wins). |
| Storage | 56.7 MB | **48.0 MB (85%)** | Delta **smaller** here (delta-rs default file sizing/encoding). Not a headline win but not a regression. |
| Read — count | 0.004s | 0.007s | Both trivial. |
| Read — group-by agg | 0.005s | 0.005s (DuckDB `delta_scan`) / 0.128s (`pl.scan_delta`) | DuckDB `delta_scan` is on par with `read_parquet`. |
| **Incremental update** | **0.33s (= FULL rebuild — the only option today)** | **0.40s (MERGE upsert into one partition)** | ⚠️ **wall-clock parity at POC scale** — see §4b. The win is *algorithmic*, not constant-factor. |

**Read-latency headline:** DuckDB reading Delta (`delta_scan`) is indistinguishable from `read_parquet` — the serve/feature-build read path pays **no** latency tax to move to Delta.

---

## 3. The stack works — all three read paths clean

- ✅ **Delta on-path write** via delta-rs (`write_deltalake`) — catalog-optional `_delta_log` on the path, exactly the committed design.
- ✅ **DuckDB read** via `INSTALL delta; LOAD delta; SELECT … FROM delta_scan('<path>')` — the drop-in for today's `read_parquet('…/*.parquet')`.
- ✅ **Polars read** via `pl.scan_delta` (lazy) / `pl.read_delta` (eager) — Arrow-native.
- ✅ **Arrow-native Delta → Polars → DuckDB** zero-copy handoff (`pl.read_delta(...).to_arrow()` → `con.register(...)`) — clean, no serialization.

---

## 4. The 4 wins that justify Delta — each demonstrated

### 4a. Schema evolution (the INC-19 structural cure) — ✅ WIN
`write_deltalake(..., mode="append", schema_mode="merge")` added a new `stuff_plus` column at **v1** with **no rewrite** of the 1.5M existing rows (they read back `NULL` for the new col). **This is the structural retirement of the INC-19 NUMBER↔FLOAT-drift HALT class**: an additive column change is a metadata commit, not a `sync_all_columns` incremental ALTER that Snowflake can't do → no DROP+rebuild, no TYPE-PIN block, no `gen_type_contract` guard needed for *additive* changes.
⚠️ **Caveat (still test in rollout):** a *type change* of an existing column (NUMBER→FLOAT) is **not** free in Delta either — Delta's default is column-add/reorder; a widening type change needs explicit `mergeSchema` semantics and can still be rejected. Delta kills the *additive-drift* HALT class (the common one); a genuine stored-type flip still needs a deliberate migration. Don't oversell it as "INC-19 fully gone."

### 4b. MERGE-into-partition (the 40-min-rebuild cure) — ✅ WIN (mechanism), ⚠️ honest on wall-clock
`DeltaTable(...).merge(predicate="t.pitch_id = s.pitch_id").when_matched_update_all().when_not_matched_insert_all()` upserted today's slate touching **only the 2026 partition**.
- **At POC scale wall-clock is parity** (0.40s MERGE vs 0.33s full rebuild) — because a 1.5M-row local rebuild is already sub-second. **This does NOT demonstrate the speedup, and the doc does not claim it.**
- **The win is algorithmic:** MERGE is `O(rows in touched partition)` and reads only that partition; the current pipeline is `O(all history)` every run — the ~40-min `run_w1_lakehouse` driver is dominated by **re-reading the full `stg_batter_pitches` substrate** on every daily run. The gap widens with history; a 4-year POC can't surface it. **The rollout must measure this on real box-scale history to quantify the win** (this is the acute driver, so quantifying it is a rollout AC).

### 4c. Retention / compaction / VACUUM (the INC-20 cure) — ✅ WIN
`dt.optimize.compact()` collapsed 8 → 4 files; `dt.vacuum()` removed 12 stale files. **This is the structural retirement of the INC-20 unbounded-partition/OOM class** — snapshot expiration + compaction replace the hand-rolled retention.
⚠️ **Gotcha surfaced (important):** `vacuum(retention_hours=0)` **physically deletes the files older versions point to → time-travel to those versions BREAKS** (empirically confirmed: v0 read failed post-vacuum). **Production must keep the default 168h (7-day) retention** so recent time-travel/point-in-time survives. Vacuum and time-travel are in direct tension — retention is the knob.

### 4d. Time-travel as-of (leakage-audit / point-in-time asset) — ✅ WIN
`DeltaTable(path, version=0)` read the table **as of v0** (15 cols, pre-`stuff_plus`, 1.5M rows) vs latest v2 (16 cols, 1.588M rows) — 3 commits in the log. **This is a real leakage-audit + backtest-reproducibility asset**: "what did the feature store look like as of date X" is now a first-class query, not a guess. (Must run *before* an aggressive vacuum — see 4c.)

---

## 5. Model-I/O boundary — Polars → pandas at `model.predict()`  (the E11.20 gotcha, written up)

**Rule: keep a clean Polars→pandas conversion at the model boundary. Do NOT feed a Polars frame to a trained sklearn model.** Trained sklearn/xgboost estimators expect a **pandas DataFrame** with the exact **feature names, dtypes, and column order** they were fit on (the repo's `len(contract) == model.n_features` discipline). Polars is the Arrow-native transport for the whole build/feature path; convert **once, at the last step before `predict`**:

```python
feat_pl = pl.scan_delta(delta_path).select(CONTRACT_COLS).collect()   # all feature work in Polars
X = feat_pl.to_pandas()                                                # ← the boundary, numpy-backed
preds = model.predict(X[model.feature_names_in_.tolist()])             # enforce order/names here
```

- **`.to_pandas()` default is numpy-backed** (not the pyarrow-extension dtypes) → sklearn-safe. Verified: `float64`/`int64` land clean, ~0.05s for 200k×6.
- **Enforce column order/names at the boundary** (`X[model.feature_names_in_]`) — Polars `select` order is not guaranteed to match the trained contract.
- **Adopt Polars incrementally** — new code + the Delta read/serve hot paths first; do **not** big-bang the ~180 offline training scripts (roadmap directive). The boundary shim above is what lets a Polars build path feed the *existing* pandas-trained models with no retrain.

---

## 6. 🧨 Gotcha list (ranked — the real spike output)

1. **🔴 ROADMAP CORRECTION — DuckDB does NOT write Delta (1.5.4 / 1.5.3).** The `delta` DuckDB extension is **read-only**: it exposes `delta_scan` + metadata functions, and **`COPY … (FORMAT delta)` does not exist** (`Catalog Error: Copy Function with name delta does not exist`). Empirically, DuckDB *does* write **Iceberg** (`COPY … (FORMAT iceberg)` works) — but **not Delta**. The roadmap's "DuckDB writes Delta natively since v1.5.0 / GA v1.5.2" premise is **false for the write path** as tested. **⇒ The Delta WRITE path is delta-rs (`deltalake` Python) / `pl.DataFrame.write_delta` — a NEW box dependency.** This does *not* overturn the Delta decision (delta-rs is catalog-optional too, and Polars writes via delta-rs anyway), but it changes the rollout mechanics: `run_w1_lakehouse`'s `COPY … TO parquet` becomes `build-in-DuckDB → .arrow() → write_deltalake(...)` (or build directly in Polars). Flag to operator — one stated Delta rationale ("writable from our DuckDB stack") is delivered by delta-rs, not DuckDB itself.
2. **🟠 New box dependencies to bake into the image:** `deltalake` (delta-rs, arm64 wheel — confirm it resolves on the `r6g.large`/AL2023 arm64 box) + the DuckDB `delta` extension (`INSTALL delta`) + `polars`. Pin versions — delta-rs 1.x had API churn (see #4). Add to the container build + a smoke test.
3. **🟠 VACUUM destroys time-travel.** `vacuum(retention_hours < the age of a version you want)` physically deletes that version's parquet → time-travel breaks. Keep the **default 168h** retention in prod; never run `retention_hours=0` on a table you want to audit historically. (Wins 4c and 4d are in direct tension — retention is the single knob.)
4. **🟠 delta-rs 1.x API churn — pin the version.** Between the docs and 1.6.1: `DeltaTable.files()` → **`file_uris()`**; `schema().to_pyarrow()` → **`schema().to_arrow()`**. A rollout written against an older tutorial will break. Pin `deltalake==1.6.x` and write against that API.
5. **🟡 Snowflake-ext-over-Delta is untested here and carries the SAME binary-timestamp risk.** Delta stores `TIMESTAMP` as INT64 micros — the exact surface of the **W8a "Snowflake misreads binary parquet timestamps → year ~56,000,000"** landmine. **BUT** the Cortex-only end-state removes the SF-native feature/mart reads, so a SF-ext-over-Delta read of *this* table family is likely **moot**. **Decision for rollout:** if any SF read of a Delta-converted table remains, either (a) keep the W8a ISO-VARCHAR-timestamp cure, or (b) validate Snowflake's `CREATE EXTERNAL TABLE … TABLE_FORMAT = DELTA` timestamp handling on the box with a **per-ROW fetch** (parity-over-parquet is blind to it — the standing landmine). Prefer: don't have Snowflake read Delta at all.
6. **🟡 `pl.read_delta` (eager) materializes the whole table; use `pl.scan_delta` (lazy) for large tables.** The eager full-read + agg was slower than the lazy scan+agg. Default to `scan_delta(...).<ops>.collect()` for anything mart-sized.
7. **🟡 MERGE produces small files → schedule compaction.** Each MERGE adds files (8 after one upsert); without periodic `optimize.compact()` the file count grows and read planning degrades. Compaction is a **required** companion op to the MERGE pattern, not optional.
8. **🟡 Partition strategy carries over — pick before converting.** delta-rs `partition_by=["game_year"]` mirrors today's layout; the MERGE `predicate` must be partition-aware to stay `O(touched partition)`. A bad predicate scans the whole table and forfeits win 4b.
9. **🟢 Box gotchas still apply** (`BOX_OPERATIONS.md`): DuckDB S3 region `us-east-2` for the artifacts bucket; **instance-role creds** for delta-rs S3 writes (delta-rs uses `storage_options` — must resolve the EC2 instance role, NOT `os.environ.get("AWS_ACCESS_KEY_ID")` which is unset → the AKID landmine); box-aware DuckDB memory. delta-rs S3 auth is a **new** surface — verify it picks up the instance role on the box (the boto3 AKID class in a new dress).

---

## 7. Recommended patterns (→ carry into the E11.20 rollout)

- **WRITE:** delta-rs. Build the frame in DuckDB (keep the existing SQL) → `con.execute(sql).arrow()` → `write_deltalake(path, tbl, partition_by=[…], mode="overwrite"|"append")`; **or** build in Polars → `df.write_delta(path)`. **Not** DuckDB `COPY`.
- **INCREMENTAL:** `DeltaTable(path).merge(predicate=<partition-aware PK match>).when_matched_update_all().when_not_matched_insert_all().execute()` — replaces the full `run_w1_lakehouse` rebuild for today's slate. Follow every N merges with `optimize.compact()`.
- **READ (build/feature):** DuckDB `delta_scan('<path>')` — drop-in for `read_parquet`.
- **READ (dataframe / hot path):** `pl.scan_delta('<path>')` lazy; `.to_pandas()` **only** at the model boundary (§5).
- **RETENTION:** `optimize.compact()` + `vacuum()` at the **default 168h**; never `retention_hours=0` on an auditable table.
- **SCHEMA:** additive changes via `schema_mode="merge"` (no DROP+rebuild); reserve TYPE-PIN/`gen_type_contract` discipline for genuine stored-type flips only.
- **AUTH/BOX:** delta-rs S3 writes must resolve the EC2 instance role (no inline AKID); DuckDB reads set region `us-east-2`; pin `deltalake`, `polars`, and `INSTALL delta` in the image.

---

## 8. Reproduce

```bash
# isolated env — does NOT touch repo deps or prod S3
uv venv /tmp/delta_poc_env --python 3.11 && source /tmp/delta_poc_env/bin/activate
uv pip install "polars>=1.0" "deltalake>=1.6,<1.7" "duckdb>=1.5" pyarrow pandas numpy
uv run --no-project python scripts/spikes/e11_20a_delta_poc.py   # prints the §2/§4 table + writes poc_results.json
```

The harness (`scripts/spikes/e11_20a_delta_poc.py`) generates the synthetic mart, runs the Parquet baseline, converts to Delta-on-path, exercises all 4 wins, does the Polars→pandas boundary, and probes DuckDB Delta-write support.

---

## 9. Go/no-go → E11.20 rollout

**🟢 GO.** The Delta-on-path + Polars-over-DuckDB stack works end-to-end; all 4 wins that justify the migration are demonstrated on a real pitch-mart schema. The decision to adopt (already committed by the operator) is validated with **one correction** (Delta write = delta-rs, not DuckDB) and a **bounded gotcha list** the rollout must design around.

**Rollout AC seeded by this spike (for E11.20 proper, after E11.22):**
1. Bake `deltalake` + `polars` + DuckDB `delta` into the box image; smoke-test delta-rs S3 write under the **instance role** (the AKID landmine in new dress).
2. Convert `run_w1_lakehouse`'s pitch-mart writes from `COPY … parquet` → delta-rs `write_deltalake`, then replace the full-history rebuild with a **partition-aware MERGE** + scheduled `optimize.compact()`.
3. **Quantify win 4b on real box-scale history** (the acute 40-min driver) — the POC could not; this is the headline number the rollout must produce.
4. Decide the SF-ext-over-Delta question (gotcha #5) — prefer "no Snowflake read of Delta"; if unavoidable, per-ROW-fetch validate the timestamp handling.
5. Retention policy: default 168h vacuum + compaction cadence; document the vacuum↔time-travel tension.
6. Wire time-travel into the leakage-audit / backtest-reproducibility workflow (the point-in-time asset).

**Sequencing unchanged:** full E11.20 rollout still waits for the decommission finish (W11-E + residuals) → E11.22 integrity audit → E11.20. This spike de-risks it; it does not start it.

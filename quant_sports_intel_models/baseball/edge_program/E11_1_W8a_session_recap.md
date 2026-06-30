# E11.1-W8a — Session Recap & Handoff (2026-06-30)

**Status: ✅ DONE / CUT-OVER / PROD-VERIFIED.** The independent upstream feature layer + EB
posteriors now serve from the S3 lakehouse (DuckDB build → parquet → Snowflake external-table
`else` branch). 12 of the ~19 scoped models migrated; 7 deferred → W11. One non-blocking cosmetic
follow-up remains. **This unblocks W8b** (the serving aggregator).

Audience: the PM Claude session + whoever picks up W8b / W11 / E11.20 / E11.22. Read the
"Landmines for W8b+" section before touching `feature_pregame_*` again.

---

## 1. What shipped

- **12 models cut over** to the W6 dual-branch pattern (`{% if target.name == 'duckdb' %}` real
  compute → S3 parquet `{% else %} select * from baseball_data.lakehouse_ext.<model>`):
  `park_status`, `starter_status` (+ precursor `stg_statsapi_starter_snapshots`), `park_features`,
  `team_features`, `expected_lineup`, `odds_features`, `sub_model_signals`, and the **5 EB
  incrementals** (`eb_starter_posteriors`, `eb_batter_posteriors_raw`, `eb_bullpen_posteriors`,
  `eb_bullpen_team_posteriors`, `int_bullpen_ali_by_season`).
- **`W8a_*` external tables created + GRANTed** (`baseball_data.lakehouse_ext.*`,
  AUTO_REFRESH=FALSE; refreshed daily by `refresh_w1_external_tables.py` → `W8A_TABLES`).
- **5 EB incrementals DROP+rebuilt** so they adopt FLOAT (INC-19); added to the type-contract
  guard (`gen_type_contract.py` CONTRACTS + 5 new `dbt/type_contracts/<model>.types.json`
  manifests; `--check` GREEN, 6 contracts total).
- **Durable code fix committed (`a3ca1e7`)** + deployed to the box.

### Runtime gate — PASSED (this is the real merge bar for pipeline code, not CI-green)
Verified in prod, not just locally:
- The box's **overnight `--w8a` (2026-06-30 ~01:29)** re-wrote correct parquet under the deployed
  fix, the daily build went green, and `predict_today` served 6/29 with **no EOVERFLOW** (26
  `prediction_log` rows + 13 `daily_model_predictions`, `model_version=pre_lineup_v6`).
- Live checks: `lakehouse_ext.feature_pregame_odds_features` → `odds_ingestion_ts` max
  `2026-06-30 01:29`, 26,474 rows, **reads per-row correctly** (not year-56M);
  `lakehouse_ext.feature_pregame_sub_model_signals` → 26,805 rows / 13,403 games, `game_pk`
  populated.

---

## 2. The headline incident — Snowflake misreads BINARY parquet TIMESTAMPs (24h serving outage)

**The single most important thing for any future feature-migration session.**

- **Symptom:** `predict_today → load_todays_features → cursor.fetchall()` raised
  `snowflake.connector 252005: Failed to convert current row … year 56495829 is out of range`.
  Prediction pipeline down ~24h.
- **Root cause:** Snowflake's parquet external table reads a **BINARY (INT64) parquet TIMESTAMP at
  the wrong scale per-row** — a micros value gets interpreted as seconds, so a 2026 timestamp
  (~1.78e15 micros) materializes as year ~56,000,000 → connector overflow on fetch.
- **⚠️ The trap that burned hours:** `min/max(year(col))` AND `to_varchar(min(col))` are answered
  from **parquet column statistics** (read correctly → 2020–2026), so the column looks *fine* in
  every aggregate probe. The corruption only appears when you **fetch / CTAS / dbt-materialize an
  actual ROW**. Re-casting nanos↔micros does NOT help (Snowflake misreads *any* binary parquet
  timestamp through an external table). `DATE` columns (INT32 days) read correctly.
- **Durable cure** (the documented `write_pandas` timestamp convention — store ISO VARCHAR, parse
  downstream):
  - `run_w1_lakehouse.py::_string_timestamp_wrap` casts every `TIMESTAMP*` output column to
    `::varchar` (ISO) before the `COPY … TO parquet`.
  - `generate_w8a_external_tables.py::TS_STRING_COLS` emits those columns as
    `<COL> TIMESTAMP_NTZ AS (VALUE:col::TIMESTAMP_NTZ)` — a reliable **string** parse → the dbt
    `else` branch materializes a correct native `TIMESTAMP_NTZ`.
  - Affected cols this wave: `odds_features.odds_ingestion_ts`,
    `starter_status.{valid_from,valid_to,computed_at}`, `park_status.computed_at`,
    `stg_statsapi_starter_snapshots.ingestion_ts`.
- **Immediate unblock (manual, 2026-06-30):** recast the 4 parquet ts→varchar, re-CREATE the ext
  tables, CTAS the native odds/starter/park tables + `UPDATE game_features.odds_ingestion_ts`.
  Then the durable code fix was committed + deployed so the box's nightly `--w8a` writes VARCHAR
  going forward (verified — see runtime gate above).

---

## 3. The other 4 cut-over bugs (all fixed)

1. **Missing DuckDB view `team_elo_history`** — `feature_pregame_team_features` reads it (a
   `compute_elo` Python source); parquet was already in S3 (W7b export) but not registered as a
   DuckDB view → `--w8a-only` HALTed at model 4/13. Fix: added to `W8A_PRECURSOR_VIEWS` **and**
   `export_w8a_precursors_to_s3.py::MIRROR_TABLES`.
2. **COPY comment-swallow (all 5 EB)** — `_build_marts` inlined `COPY ({sql}) TO …` on one line;
   each type-pinned model ends in a generated `-- TYPE-PIN-END` line comment → the closing `)`
   landed on the comment → `ParserException`. Fix: newline-safe wrap `COPY (\n{sql}\n) TO …`.
3. **External-table `VALUE:` case-sensitivity (SILENT, parity-blind)** — Snowflake `VALUE:<key>` is
   CASE-SENSITIVE and must match the parquet's stored field name exactly. Several W8a parquet
   inherit UPPERCASE columns from Snowflake-mirrored upstreams (a SF `SELECT *`→parquet yields
   uppercase; DuckDB preserves source case for un-aliased cols). All prior generators hard-`.lower()`ed
   the `VALUE:` path → those columns read **ALL-NULL** through the ext table. Fix: emit exact described
   case. ⚠️ **parity_check can't catch this** (it reads parquet via DuckDB, case-insensitive).
4. **`eb_bullpen_team_posteriors` glob double-count (CI uniqueness FAIL)** — its S3 dir held BOTH
   `data.parquet` (W8a) and a stale `part-0.parquet` (still mirrored by `export_w5_raw_to_s3.py`);
   the ext table's `**/*.parquet` glob unioned both → 2× rows. Fix: removed it from
   `export_w5_raw_to_s3.py` (ownership transfer to W8a), `aws s3 rm part-0.parquet`, re-CREATE ext.
   ⚠️ parity missed it too (parity reads the single `data.parquet` explicitly, not the glob).

**Cross-cutting lesson:** *parity (DuckDB-over-parquet) is necessary but NOT sufficient.* It is
blind to the entire class of **Snowflake-external-table read bugs** — case→NULL, binary-ts→garbage,
glob-dup — because it never goes through the SF ext table. Any future migration needs a **per-row
fetch through the actual `lakehouse_ext.*` table** as a cut-over gate, not just parity.

---

## 4. 🧨 Landmines for W8b+ (READ BEFORE TOUCHING `feature_pregame_*`)

W8b migrates the **serving aggregator** `feature_pregame_game_features(_raw)` + complex parents
(starter / lineup / bullpen_state) + the 3 matchup models + the W9 source-read/write-retirement
tail. These will bite:

- **🕒 BINARY-TIMESTAMP misread WILL recur in W8b.** `game_features` carries timestamp columns
  (incl. `odds_ingestion_ts`, which W8b will compute natively rather than copy). Use the **VARCHAR-
  store cure** (`_string_timestamp_wrap` already does this for every `TIMESTAMP*` col in the DuckDB
  build; add each new ts col to the generator's `TS_STRING_COLS`). Do NOT trust `min/max(year())` —
  validate with a **per-row fetch through the ext table**.
- **🔠 `VALUE:` exact-case** for any UPPERCASE-inheriting column (Snowflake-mirrored upstream).
- **🧬 INC-19 type-pin — known flip:** `home_win_rate_trailing_3yr` is `NUMBER(21,4)` native today
  and WILL flip to FLOAT when its build goes DuckDB in W8b. The guard CATCHES it. In the SAME PR:
  edit the manifest + `gen_type_contract.py --write`, and the operator DROP+rebuilds the incremental
  (`--full-refresh` MERGEs, does NOT DROP). `game_features_raw` is already TYPE-PINNED (595 `::double`).
- **🗂️ Glob-dup / export-ownership:** before W8b builds a model that another export script still
  mirrors, remove it from that export's TABLES dict and `aws s3 rm` the stray `part-0.parquet`.
- **📑 COPY comment-swallow:** any type-pinned DuckDB model must use the newline-safe `COPY` wrap
  (already general in `_build_marts`).
- **🐢 `run_w1_lakehouse.py` full-rebuilds history every run (~10 min; daily pipeline 40+ min).**
  For DOWNSTREAM debugging (feature/serving), **SKIP the W1 pitch rebuild** and run only the targeted
  chain (`--w8a-only` etc.) — the INC-21 recovery proved this is safe. This is the dominant reason
  W8a/INC-22 debugging was slow; it's the driver for the E11.20 (Delta MERGE) / E11.21 (perf) work.
- **🏗️ Build-order:** `--w8a` must run BEFORE `--w5` in a full rebuild (W5b
  `mart_bullpen_effectiveness` reads the `eb_bullpen_team_posteriors` parquet that W8a now BUILDS).
- **🔌 Box env reminders** (cost prior sessions): EC2 uses an **INLINE** Snowflake key
  (`SNOWFLAKE_PRIVATE_KEY`), NOT a key-FILE — `snowflake_loader.py` / `refresh_w1_external_tables.py`
  / `data_loader.py` fail on the box (they read `SNOWFLAKE_PRIVATE_KEY_PATH`); use the inline pattern
  or pure DuckDB/S3. boto3 writers must use the instance-role credential chain
  (`lakehouse_raw_writer.make_s3_client()`), never `aws_access_key_id=os.environ.get(...)`. DuckDB S3
  region = `us-east-2`. "Today" = the US baseball-day (`game_day.current_game_date_iso()`), never UTC.

---

## 5. Open follow-up (non-blocking)

- **`feature_pregame_sub_model_signals` stray reserved `VALUE` column.** The box `--w8a` produces a
  parquet with an extra column literally named `VALUE` → a DDL **re-CREATE** of its external table
  fails (`'VALUE' cannot be used as a column name for external tables`). **Serving is unaffected** —
  the daily `refresh_w1_external_tables.py` uses REFRESH (re-scans the stage; ignores unmapped parquet
  columns), and the existing ext table reads fine (13,403 games, `game_pk` populated). Fix at the
  **W9 source** that emits the raw `VALUE` column (likely the signal-pivot). Small ticket; can ride a
  W9-tail or W8b session.

---

## 6. Deferred → W11 (the 7 not migrated)

These were never finishable in W8a (precursor raw data not yet in S3) and are correctly routed to
**W11 (raw-ingestion → S3-native)**:
`umpire_status`, `umpire_features`, `weather_status`, `weather_features`, `injury_status`
(+ `public_betting_status/_features` which read the W8b aggregator), and `meta_model_features`
(rides the W8b/W9 aggregator tail).

---

## 7. State of the broader program (for the PM)

- **Mandatory remaining migration = W8b ONLY** (W9 output ✅, W12 ✅, W8a ✅ done). W8b is the
  CRITICAL solo session (live feature store, highest blast radius) and is now **unblocked**.
- **After W8b cutover:** run **E11.22** (post-migration feature-serving INTEGRITY audit — prove the
  models are actually FED, not just parity-green; the migration capstone), then start **E11.20**
  (Delta Lake on-path + Polars — committed; retires the INC-19/INC-20/silent-corruption classes
  structurally and is the multi-sport on-ramp). E11.21 (`daily_ingestion_job` perf audit) folds in.
- **Optional / cost-driven:** W10 (stateful builders), W11 (raw-ingestion long pole), W13
  (serving-state) — these STAY on minimal Snowflake per the operator's pragmatic Cortex-only
  decision (W14 dropped). 3-tier data-home: DynamoDB = app-read serving cache; S3 lakehouse =
  analytical/build; minimal Snowflake = Cortex I/O (`daily_model_predictions`) + stateful model-state.
- **Serving health note:** `predict_today` restored; serve 6/29 to the app with the
  `write_serving_store.py --date 2026-06-29` command (see §below). Today's (6/30) serving flows
  through the daily job. `write_api_cache.py` is `CURRENT_DATE`-bound (today-only, no `--date`).

---

## 8. Files / git (operator)

Already committed: `a3ca1e7` (the durable VARCHAR-timestamp fix — `run_w1_lakehouse.py` +
`generate_w8a_external_tables.py`), and the prior W8a batch (13 model SQLs, 5 EB manifests,
`gen_type_contract.py`, `refresh_w1_external_tables.py`, `export_w8a_precursors_to_s3.py`,
`export_w5_raw_to_s3.py`, `parity_check_w8a.py`, `pipeline/ops/daily_ingestion_ops.py`).

Close-out doc edits this session:
```bash
git add quant_sports_intel_models/baseball/edge_program/story_prompts.md \
        quant_sports_intel_models/baseball/edge_program/build_roadmap.md \
        quant_sports_intel_models/baseball/edge_program/E11_1_W8a_session_recap.md
```
EXCLUDE: `scripts/ddl/w8a_external_tables.generated.sql` (operator-generated),
`ablation_results/odds_market_inventory_2026-06-30.md` (belongs to the parallel E13.14 audit
session). `CLAUDE.md` is also modified — commit if those are the intended landmine-doc edits.

### Serve 6/29 to the application
```bash
docker compose -f services/dagster/aws/docker-compose.yml exec dagster-codeloc \
  python scripts/write_serving_store.py --date 2026-06-29 --picks --game-detail --book-odds --history --performance
```

### (Optional) the 6/29 post-lineup record (games are over → CLV/record completeness only)
```bash
docker compose -f services/dagster/aws/docker-compose.yml exec dagster-codeloc \
  python scripts/predict_today.py --date 2026-06-29 --prediction-type post_lineup --lineup-confirmed
```

---

## 9. Gates

- Fast pytest (`-m "not slow" -n auto`) GREEN; type-contract guard + boto3 lint GREEN;
  `gen_type_contract.py --check` GREEN (6 contracts); `dbtf parse` clean.
- dbt `state:modified+` build + `dbtf compile` = operator/CI (local SF SAML auth fails on the
  on-run-start hook). Use `scripts/dbt_state.sh` for local `state:modified+`.
- Runtime gate: the box ran `--w8a` + daily build + `predict_today` green overnight (the real bar
  for this pipeline-code class — CI mocks all IO and cannot see the timestamp / case / glob bugs).

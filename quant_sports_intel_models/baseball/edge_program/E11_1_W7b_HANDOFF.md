# E11.1-W7b — prediction/serving path off Snowflake (PHASED, gated, parallel-run-gated)

**Status:** CODE-COMPLETE, gated OFF, NOT cut over. Operator runs the multi-day parallel run
(`scripts/parity_check_w7b.py`) then flips the env flags. This is the **prediction-path finish,
NOT the program finish** — a long Snowflake tail remains (§3). Do **NOT** describe this as
"Snowflake decommission complete / Cortex-only."

## 0. What this is (and the W7b-1 / W7b-2 split)
W7a took the REQUEST path's matchup-consumer + cluster reads off Snowflake. W7b takes the
**prediction/serving READ path** off Snowflake: `predict_today` + `betting_ml/utils/data_loader`
(feature matrix), `write_serving_store` (served picks/blobs), and the FastAPI request-path
last-resort. The operator split is honored further: this is **W7b-1 (the READ path, via an
export-mirror)**; the **dbt feature BUILD's own DuckDB conversion is W7b-2** (deferred — it's a
~7k-line tree, the truly risky blind translation).

**Mechanism (W7b-1):** the `feature_pregame_*` tables are still BUILT by dbt on Snowflake
(reading the S3-backed `lakehouse_ext` views). A new daily **export-mirror**
(`scripts/export_features_to_s3.py`) copies the build's OUTPUT → S3 parquet (a 1:1, row-exact
copy → parity is trivially clean), so the READERS go fully Snowflake-free now and the build
conversion can land later (W7b-2) without touching the readers again.

## 1. Env flags (the cutover gate)
| Flag | Effect |
|------|--------|
| `W7B_LAKEHOUSE_PARALLEL=1` | Populate the S3 mirrors daily (feature mirror + `daily_model_predictions` re-export) so `parity_check_w7b.py` can compare S3-path vs Snowflake-path. Serving still reads Snowflake. Set this FIRST, for the multi-day parallel window. |
| `W7B_LAKEHOUSE_S3=1` | **Cutover.** `predict_today_morning` + `write_serving_store_op` read S3 directly (`--s3`). Implies the mirrors run. Flip only AFTER a clean multi-day parallel window. |
| (request path) | The backend last-resort reads S3 directly **unconditionally** once deployed (the cold path was already a fallback; direct-S3 keeps it 200 on a cache miss with zero Snowflake). Rollback = redeploy the prior bundle. |

Rollback at any time: unset `W7B_LAKEHOUSE_S3` (instant — the Snowflake read path is 100% intact).

## 2. What W7b CLEARS off Snowflake (the prediction/serving READ path)
- **`scripts/write_serving_store.py` `--s3`** — every Snowflake-FQN read repointed to direct-S3
  (DuckDB), grep-driven (not a fixed list) so concurrently-added reads (E9.37
  `_LINE_MOVEMENT_SERIES_BATCH`, E9.36 `_STARTERS_QUERY`/`_SP_LAST3_BATCH`) are covered. All
  writes already went to DynamoDB/S3 — pure read repoint.
- **`scripts/predict_today.py` + `betting_ml/utils/data_loader.py` `--s3`** — the served feature
  matrix (`feature_pregame_game/lineup/starter_features`), marts, and odds read via DuckDB.
  WRITES (`daily_model_predictions`, `config.prediction_log`) STAY on Snowflake (long tail; the
  readers read the S3 mirror).
- **Request path** (`app/backend/routers/picks.py`/`performance.py`/`bets.py`) — the Snowflake
  last-resort (+ the always-on `bets.py` game-state read) → direct-S3 DuckDB; INC-18 `stg_*`
  point-in-time reads now resolve from S3 too (the serving-mart backlog put
  `stg_statsapi_probable_pitchers`/`lineups_wide` in S3). The request path is **zero-Snowflake**
  after deploy; a cache miss still 200s from direct-S3.
- **`mart_player_profile_identity` mini-wave** — the injury chain
  (`stg_statsapi_transactions` → `stg_statsapi_player_injury_status` →
  `feature_pregame_injury_status` → `mart_player_profile_identity`) given DuckDB branches → S3.
- **Serving-mart backlog** — `stg_statsapi_probable_pitchers` + `stg_statsapi_lineups_wide`
  DuckDB branches → S3 (unblocks the request-path last-resort). Reads honor the
  `SCHEDULE_LAKEHOUSE_INTRADAY` 30-min `monthly_schedule` re-export (the glob points at the live
  path, so a fresh read re-globs — no stale daily parquet).
- **Feature export-mirror** — `feature_pregame_*` outputs Snowflake→S3 (the W7b-1 bridge).

## 3. What REMAINS on Snowflake after W7b (the W8+ tail — honest)
A parallel residual-audit session is mapping the full W8+ list; this is the prediction-path view:
1. **The dbt feature BUILD** (`feature_pregame_*`, ~7k lines) — still runs on Snowflake reading
   `lakehouse_ext` views. → **W7b-2** (the DuckDB dual-branch conversion; retires the mirror).
2. **The feature export-mirror itself** reads Snowflake (it's the W7b-1 bridge; gone after W7b-2).
3. **Prediction WRITES** — `daily_model_predictions`, `config.prediction_log` (predict_today),
   and the `_backfill_outcomes` historical path. (Readers read the S3 mirror; writes are tail.)
4. **The INTRADAY / post-lineup serving path** — `lineup_predict` + `write_serving_store_intraday`
   stay on Snowflake in W7b-1 (the daily export-mirror can't cheaply give today's lineup-driven
   feature freshness intraday; needs the W6-style `_current`-bucket split or W7b-2's build).
5. **Other sub-model signal generators** (bullpen/run_env/defense/env_state/starter/offense →
   SCD-2 `mart_sub_model_signals`).
6. **EB posterior builders** (`compute_starter`/`bullpen`/`lineup_posteriors`, `fit_park_priors`
   → MERGE `eb_*`).
7. **`compute_elo`.**
8. **Raw ingestion scripts** (write the substrate the lakehouse is built FROM → S3-native is a
   big change).
9. **Monitoring sensors.**
10. **`lakehouse_ext.*` external-table VIEWS** — still read by #1/#5/#6/#7 → NOT droppable (see §4).
11. **Cortex narrative** `generate_pick_narratives.py` — the one sanctioned Snowflake use.

## 4. Drop-view dependency analysis — NO views dropped in W7b-1
The AC's "drop the Snowflake views + residual builder writes" is the END-STATE AC; in the phased
delivery it is **DEFERRED**, not done. Reason: the `lakehouse_ext.*` external-table views are
still read by the **on-Snowflake dbt feature build** (W7b-2) and the sub-model/EB/elo builders
(§3.5–3.7). Dropping any of them now would break the morning feature build. So **W7b-1 stages no
runnable DROP**. The residual dual-write builder Snowflake writes were already addressed in W7a
(the `W7A_LAKEHOUSE_S3` flip drops the native cluster builds). The blanket view drop is gated on
W7b-2 + the §3.5–3.8 tail. (A `w7b_drop_candidates` list is deliberately NOT shipped to avoid an
operator running a build-breaking drop.)

## 5. The multi-day parallel run (the safety gate — operator-run)
1. **Create + populate S3** (one-time, then daily) — ORDER MATTERS (the DDL generator DESCRIBEs
   the parquet to infer the schema, so it must run AFTER the build):
   a. seed the precursor: `export_w7b_precursors_to_s3.py` (player_transactions → S3).
   b. build the parquet: `run_w1_lakehouse.py --w7b-only` (writes the 6 model parquets; needs the
      W2/W4/W6 precursors already in S3 — `mart_batter_rolling_stats`/`mart_starting_pitcher_game_log`
      (W2, daily), `stg_statsapi_player_profiles` (W4), `stg_statsapi_lineups` (W6)).
   c. generate the external-table DDL: `scripts/ddl/generate_w7b_external_tables.py` → review
      `w7b_external_tables.generated.sql` (all 6 tables) → run in Snowflake.
   d. mirror the feature/serving outputs: `export_features_to_s3.py` (9 tables: the 8 feature_pregame_*
      + team_elo_history. NOT mart_bankroll_state — bankroll serves from DynamoDB, the SF object is
      gone, and both readers already fall back to mart_clv_labeled_games when it's absent) +
      `export_w6_raw_to_s3.py --table daily_model_predictions`.
   e. refresh: `refresh_w1_external_tables.py`.
2. **Turn on parallel mode:** set `W7B_LAKEHOUSE_PARALLEL=1` (mirrors run daily; serving stays
   Snowflake).
3. **DAILY for ≥ a multi-day window**, after the morning cycle:
   `uv run python scripts/parity_check_w7b.py --date <today>`
   — confirm `features`, `predictions`, `picks` all ✅ (column-by-column, key-aligned, float
   rtol 1e-4). Investigate any **value** drift on a shared key (a count delta during the mirror
   window is expected, reported not failed).
4. **Cutover** only after a clean multi-day window: set `W7B_LAKEHOUSE_S3=1` (serving reads S3).
   Keep `parity_check_w7b` running a few more days as a tripwire.
5. **Request path:** deploy the backend (`infrastructure/lambda/deploy.sh` — now bundles
   `duckdb`); verify a cache-miss endpoint returns 200 from direct-S3.

## 5b. INC-19 — feature-column type consistency (W7b-2 discipline; W7b-1 is clean)
INC-19 (2026-06-29, 4th of the class after INC-15/W1d + INC-16-P0): a dual-branch migration made
an upstream column compute as FLOAT on the DuckDB/S3 side while the existing Snowflake **incremental**
table had it as `NUMBER(38,x)`; Snowflake refuses the column-type change → HALT on the next
incremental rebuild (`cannot change column … from NUMBER(38,4) to FLOAT`, in
`feature_pregame_game_features_raw.HOME_BP_K_PCT_14D`).

**W7b-1 is INC-19-clean — verified, not assumed:**
- W7b-1 did **NOT** touch `feature_pregame_game_features_raw` / `feature_pregame_game_features`
  (those are the deferred W7b-2 feature-build conversion + the operator's live INC-19 unblock) → **no
  collision** with the INC-19 commit.
- The 6 W7b dual-branch models are all `view`/`table` (none `incremental`) → CREATE-OR-REPLACE each
  run, so the "can't change an existing incremental column type" class cannot apply to them.
- Their Snowflake `else` arms are byte-unchanged (native types preserved); the DuckDB-arm `::timestamp`
  is normalized back to `TIMESTAMP_NTZ` by the external-table type-map (matches native), and the only
  numeric casts (`age ::int`, ids `::integer`) are identical on both arms → no NUMBER→FLOAT drift.
- No on-Snowflake **incremental** reads the W7B external tables in W7b-1 (the feature build still reads
  the native `ref(...)` else-arm; the `--s3` readers read parquet via DuckDB).

**W7b-2 MUST follow these rules** when converting the big feature tree (game/lineup/starter +
upstreams — full of `NUMBER(38,4)` rolling-stat columns):
1. **Cast every feature column to a consistent explicit type on BOTH branches** so DuckDB/S3 and
   Snowflake agree (e.g. `::decimal(38,x)` or `::float` on both), and so the external-table type-map
   (`scripts/ddl/generate_*_external_tables.duckdb_to_snowflake_type`, which maps DECIMAL→FLOAT) lands
   the same type the downstream incremental already has. A bare DuckDB float feeding a `NUMBER(38,4)`
   incremental = the INC-19 HALT.
2. **At cutover, DROP + rebuild each incremental table — do NOT `--full-refresh`** (dbt-fusion's
   `--full-refresh` MERGEs rather than DROP+CREATE — documented repo quirk; see [[feedback_dbtf_incremental_fullrefresh]]),
   so the table recreates with the new column types.

## 5c. Parallel-run production fixes (2026-06-29 — first day W7B_LAKEHOUSE_PARALLEL=1 on EC2)
Two bugs surfaced the first morning the mirror ops actually ran on the EC2 host; both fixed.

1. **AWS credential resolution (AKID bug).** The boto3 export-mirrors built
   `boto3.client("s3", aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"), …)`. On the EC2 host
   that env var is **unset** — S3 access is the **instance IAM role** (INC-16) — and passing
   `aws_access_key_id=None` *disables* boto3's default credential chain, so it never reaches the role
   → every upload failed with `AuthorizationHeaderMalformed: a non-empty Access Key (AKID) must be
   provided`. (The W-series writes were unaffected because `run_w1_lakehouse.py` writes via DuckDB
   `COPY` using a credential_chain secret, which *does* resolve the instance role.) **Fix:** pass
   explicit keys only when both are present (local/static-cred dev); otherwise fall back to the
   default chain. Applied to **all 7 boto3 exporters** (`export_features_to_s3`, `export_w6_raw_to_s3`,
   `export_w7b_precursors_to_s3`, `export_statcast_to_s3`, `export_w5_raw_to_s3`, `export_w4_raw_to_s3`,
   `export_ref_players_to_s3`) — not just the W7b three, since `export_statcast_to_s3` is HALT-tier in
   the same `statcast_catchup_job` and carried the identical latent bug.

2. **Mirror failure tier.** The feature/predictions/precursor mirrors were wired as **HALT** inside
   `predict_today_morning`/`run_w1_lakehouse_op`. During the *parallel* window serving still reads
   Snowflake, so a parity-only mirror failure must NOT take down the serving-critical predict op — it
   red-lined the catchup job on 2026-06-29. **Fix:** `_run_mirror()` in `daily_ingestion_ops.py` —
   HALT once `W7B_LAKEHOUSE_S3=1` (serving reads the mirror), else **ALERT-loud-but-continue** (log a
   WARNING, op succeeds; that morning's parity_check just shows the gap). Also split the build
   `--w6 --w7b` → HALT `--w6` (W6 serves live) + mirror-tier `--w7b-only`. Verified by
   `test_e11_7_failure_contract.py::test_no_silent_swallow[daily_ingestion_ops.py]`.

## 6. Cutover checklist
- [ ] W7B external tables created in Snowflake (generated SQL reviewed).
- [ ] `run_w1_lakehouse.py --w7b` build green; `refresh_w1_external_tables.py` includes W7B.
- [ ] Mirrors populate S3 (feature mirror + daily_model_predictions) on the daily path.
- [ ] `parity_check_w7b.py` clean for the full multi-day window (all three checks ✅).
- [ ] Backend deployed with duckdb bundled; cache-miss 200 from direct-S3 verified.
- [ ] `W7B_LAKEHOUSE_S3=1` flipped; served picks match the Snowflake-path; P6 watching; rollback ready.

## 7. CI gate result (session close)
- **Unit Tests (fast gate)** `uv run pytest -m "not slow" -n auto` → **718 passed, 1 skipped** (GREEN,
  post the 2026-06-29 parallel-run fixes; was 701 at first close).
  The 2 `test_intraday_assembly.py` failures the concurrent agents saw were a transient mid-edit of
  `data_loader.py`; the final integrated tree passes.
- **dbt compile** `dbtf compile` → **1771 total | 1771 success** (GREEN). (2 warnings pre-existing/env:
  old package-lock format + the dbt1203 self-managed deferral 404 — neither from this work.)
- **dbt Build (state:modified+)** → **operator-run** (`scripts/dbt_state.sh build --select state:modified+
  --target dev`): it rebuilds the 6 modified models on Snowflake (needs creds + warehouse, >1 min). The
  changes only ADD duckdb branches; the Snowflake `else` arms are byte-unchanged, so the rebuild is
  same-SQL (no schema change). Run it on a clean runner (the dbt1203 trap needs `--state`, which
  `dbt_state.sh` injects).
- Slow gate not required (no new >5s tests added; `test_lakehouse_read.py` is 0.2s).

## 8. git add / excluded
W7b files this session created/changed (NOT the pre-existing `M` files — `CLAUDE.md`,
`build_roadmap.md`, `story_prompts.md` were modified before this session by other work; and
`E11_1_snowflake_residual_audit.md` belongs to the concurrent residual-audit session — exclude all 4):
```
git add \
  scripts/utils/lakehouse_read.py \
  scripts/tests/test_lakehouse_read.py \
  scripts/export_features_to_s3.py \
  scripts/export_w7b_precursors_to_s3.py \
  scripts/export_w6_raw_to_s3.py \
  scripts/export_statcast_to_s3.py \
  scripts/export_w5_raw_to_s3.py \
  scripts/export_w4_raw_to_s3.py \
  scripts/export_ref_players_to_s3.py \
  scripts/ddl/generate_w7b_external_tables.py \
  scripts/parity_check_w7b.py \
  scripts/run_w1_lakehouse.py \
  scripts/refresh_w1_external_tables.py \
  scripts/write_serving_store.py \
  scripts/predict_today.py \
  betting_ml/utils/data_loader.py \
  pipeline/ops/daily_ingestion_ops.py \
  app/backend/services/lakehouse_read.py \
  app/backend/routers/picks.py \
  app/backend/routers/performance.py \
  app/backend/routers/bets.py \
  infrastructure/lambda/deploy.sh \
  dbt/models/staging/statsapi/stg_statsapi_transactions.sql \
  dbt/models/staging/statsapi/stg_statsapi_player_injury_status.sql \
  dbt/models/feature/feature_pregame_injury_status.sql \
  dbt/models/mart/mart_player_profile_identity.sql \
  dbt/models/staging/stg_statsapi_probable_pitchers.sql \
  dbt/models/staging/stg_statsapi_lineups_wide.sql \
  quant_sports_intel_models/baseball/edge_program/E11_1_W7b_HANDOFF.md
```
**Excluded (gitignored / operator-generated / not mine):** `scripts/ddl/w7b_external_tables.generated.sql`
(operator runs the generator after the build), any `*.parquet`/`*.pkl` (S3, gitignored), the
pre-existing `M` files above, and the concurrent `E11_1_snowflake_residual_audit.md`.

## 9. No changelog entry
W7b is infrastructure (read-path repoint + gated cutover machinery); the warm request path and all
user-facing behavior are unchanged → no `frontend/data/changelog.json` entry (per CLAUDE.md, only
user-facing changes get one).

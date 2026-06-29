# E11.1-W7a session recap — the FINISH wave, part a (the credit drop + request-path resolve)

**Status: ✅ CODE-COMPLETE, GATED, READY-TO-VALIDATE (Opus, 2026-06-29). NOT yet cut over —
operator runs parity + creates the external tables + flips the `W7A_LAKEHOUSE_S3` gate.**

W7 (the program FINISH) is genuinely multi-part with sharply different risk per part. The operator
chose a **phased** split: do the lower-risk, high-credit-drop pieces now (**W7a**), defer the live
prediction-path core (**W7b**) to a dedicated parallel-run session.

## Scope DONE this session (W7a)

### #1 — matchup-signal consumers → read S3, then DROP the native cluster Snowflake builds ⭐ (the real credit drop)
The roadmap's "where the real credit drop lands." The four matchup-signal **consumers** were
NOT themselves dual-write — they READ the dual-write builder tables (`batter_clusters`,
`pitcher_clusters`, `mart_player_archetype_posteriors`) from **native Snowflake** and write
their own serving tables. So the credit drop = move every reader of the native cluster tables
off Snowflake, then stop running the native cluster builds.

**Two reader classes had to move (both done):**
- **Python consumers** (agent-implemented, canonical `compute_archetype_posteriors.py --s3`
  pattern — `_get_duckdb`/`_register_s3_views`/`_duck_sql_for`): added an **`--s3` read mode** to
  - `betting_ml/scripts/eb_priors/generate_matchup_signals.py`
  - `betting_ml/scripts/eb_priors/build_matchup_training_data.py`
  - `betting_ml/scripts/eb_priors/fit_archetype_priors.py`
  - `betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py`
  In `--s3` mode they read `mart_pitch_play_event` / `stg_batter_pitches` / `batter_clusters` /
  `pitcher_clusters` / `mart_batter_archetype_vs_pitcher_cluster` / `mart_player_archetype_posteriors`
  / `stg_statsapi_player_profiles` from the S3 lakehouse via DuckDB. **WRITES STAY ON SNOWFLAKE**
  (the SCD-2 `mart_sub_model_signals` upsert; the `matchup_cell_sequential_posteriors` read+write —
  that table is consumer-written, not a dual-write builder, so it stays). DuckDB-compat rewrites
  applied: `YEAR(game_date)`→`year(game_date::date)`, `game_date::date` casts on the VARCHAR
  parquet date, named-param→literal substitution.
  ⚠️ **PARITY FIX (2026-06-29, during operator Phase-2 run):** the first parity run crashed —
  `generate_matchup_signals._GAMES_SQL` joins `stg_statsapi_probable_pitchers` +
  `stg_statsapi_lineups_wide`, which are **NOT in the S3 lakehouse** (verified via
  `aws s3 ls .../lakehouse/`: only `stg_statsapi_lineups`, the long flatten, exists — not the
  `_wide` form, and probable_pitchers was never migrated). FIX: dropped those two from
  `_S3_SOURCE_TABLES` and **`_GAMES_SQL` (the games spine) now stays on Snowflake even in `--s3`
  mode** (`mart_game_results` there is a lakehouse_ext view = S3-backed view scan, not a native
  CTAS). This does NOT affect the credit drop (the games spine touches no dual-write builder
  table) — but it's a residual matchup-consumer Snowflake read → **flag for the W7b long tail**
  (migrate `stg_statsapi_probable_pitchers` + `stg_statsapi_lineups_wide` to S3, then route
  `_GAMES_SQL` to DuckDB). The `games` parity check was removed (nothing to compare). Verified:
  `get_duck()` registers 7 S3 views cleanly + `batter_clusters`=5,099 rows.
- **dbt FEATURE models** (the hidden dependency that makes this a real wave, not a 4-script edit):
  `feature_pregame_lineup_features`, `feature_pregame_starter_features`,
  `feature_batter_archetype_matchups`, `feature_pitcher_cluster_matchups` read clusters via
  `source('statsapi','batter_clusters'|'pitcher_clusters')` = **native Snowflake** (6 refs). The
  marts already read clusters from S3 (`read_parquet(lakehouse_loc(...))`); only these feature
  models still hit the native table. Repointed all 6 refs to a **new `lakehouse_clusters` source**
  (`schema: lakehouse_ext`) over the S3 cluster parquet — the W2–W6 source-repoint pattern. The
  feature build stays on Snowflake (that's W7b) but now reads the S3-backed external table, so the
  native cluster table is read by **nobody**.

**Infra added for the above:**
- `scripts/ddl/generate_w7_external_tables.py` — emits `lakehouse_ext.batter_clusters` +
  `lakehouse_ext.pitcher_clusters` external tables over the `cluster_*.py --s3` parquet (mirrors
  `generate_w5b_external_tables.py`; AUTO_REFRESH=FALSE; **includes a `GRANT SELECT … TO ROLE
  CREDENCE_API_RO`** on create — INC-18 band-aid class).
- `dbt/models/sources.yml` — new `lakehouse_clusters` source group.
- `scripts/refresh_w1_external_tables.py` — `W7_TABLES = [batter_clusters, pitcher_clusters]`
  added to the daily best-effort refresh (seasonal rebuild → cheap no-op most days).
- `pipeline/ops/daily_ingestion_ops.py` — `_w7a_s3_args()` appends `--s3` to the daily
  `generate_matchup_signals` / `update_matchup_cell_posteriors` / `compute_archetype_posteriors`
  invocations **only when `W7A_LAKEHOUSE_S3=1`** (default OFF → merging is a clean no-op until the
  operator validates parity; mirrors the W6_LAKEHOUSE_INTRADAY cutover gate).
- `scripts/parity_check_w7a_matchup.py` — runs each consumer's key read both ways (Snowflake vs
  DuckDB-S3) and compares; the verification surface before cutover.

**Where the credit actually zeroes:** once `W7A_LAKEHOUSE_S3=1` AND the operator runs the seasonal
`cluster_batters.py --s3` / `cluster_pitchers.py --s3` (instead of native), the native
`baseball_data.statsapi.{batter,pitcher}_clusters` builds are read by nobody and the native
`compute_archetype_posteriors` Snowflake build is superseded by its `--s3` mode → **the W4/W5b
dual-write Snowflake builder runs finally drop.** (Prior waves were additive dual-writes; this is
where Snowflake compute zeroes for the archetype/matchup subtree.)

### #2 — request-path INC-18 fix → RESOLVED as keep+flag (no risky live-app edits)
The folded-in INC-18 root cause: `picks.py`/`bets.py` read `stg_*` at request time (4 AM cache-miss
hit the Snowflake fallback → `STG_STATSAPI_GAMES … not authorized` after a `CREATE OR REPLACE`
stripped the grant). Per the operator's explicit W7a discipline (**repoint `stg_*`→marts where a
CLEAN equivalent exists; any read with NO clean equivalent → KEEP it + flag; KEEP the Snowflake
last-resort safety net; do NOT force a bad repoint**):

- **Inventory:** `picks.py` reads `stg_statsapi_games` (×10), `stg_statsapi_probable_pitchers`,
  `stg_statsapi_lineups_wide`, `stg_batter_pitches`; `bets.py` reads `stg_statsapi_games` (auto-void).
  `performance.py` reads ONLY marts (`mart_bankroll_state`/`mart_clv_labeled_games`/
  `daily_model_predictions`) — no `stg_*`; those are the kept last-resort, not touched.
- **Finding:** every `stg_*` request read serves **pre-game / live / box-score** data
  (scheduled+in-progress game status, scores, records, probables, today's lineups, Final box
  scores). The marts are **post-game/batch** (`mart_game_results` = Final games only; no mart
  serves scheduled/live status). Repointing any of these onto a mart would DROP scheduled/live
  games → break `/picks/today`, `/picks/ev`, game-detail. That's a **bad repoint**.
- **Resolution (correct outcome):** KEEP all `stg_*` request reads behind the **committed INC-18
  band-aid** — the `+post-hook` re-grant to `CREDENCE_API_RO` on every staging rebuild
  (`dbt/dbt_project.yml:106-109`, duckdb-skipped) + the Snowflake-side `FUTURE GRANTS` (operator-
  applied). **FLAG them as the W7b/follow-up serving-mart backlog** (see below). No live-app code
  change = the lowest-risk, discipline-correct call. The Snowflake last-resort stays as the
  cache-miss safety net (it reads S3-backed views today; W7b converts it to direct-S3 so the
  request path becomes truly zero-Snowflake without ever 503-ing a miss).

## Scope DEFERRED to W7b (with rationale)

### #3 — `mart_player_profile_identity` + `feature_pregame_injury_status` → DEFER to ride W7b's parallel-run
Investigated: `mart_player_profile_identity` is blocked on `feature_pregame_injury_status`, which is
a **`feature_*` serving model** (the W6 handoff itself said profile_identity "migrates once the
feature/reader layer moves here"). Neither it, `mart_player_profile_identity`, nor the precursor
`stg_statsapi_player_injury_status` is in S3 / has a DuckDB branch yet → #3 is a **from-scratch
mini-wave** (new precursor S3 export + 3 DuckDB branches + external-table DDL + run_w1 registration
+ refresh + parity) that touches the **live serving feature build**. That is exactly the #4
feature-layer class the operator deferred. Forcing a from-scratch serving-feature migration without
local parity is higher-risk than a clean deferral. **→ folded into W7b** (it rides the same feature-
build parallel-run window). Ready-to-execute spec in `story_prompts.md` (W7b).

### #4 — feature_pregame_* DuckDB branches + predict_today/write_serving_store direct-S3 → W7b
The live prediction-generation path. Mandates PARALLEL-RUN + extended byte-identical parity before
cutover (operator-run, multi-day). Unchanged from the roadmap's original "Wsv last-mile" caution.

## CI gates (this session)
- `dbtf compile`: **GREEN 1771/1771** (validates the `lakehouse_clusters` source repoint + all 6
  feature refs). Only warnings = the benign self-managed-project deferral-404 (dbt1203, expected —
  see E11.16) + old package-lock format (pre-existing).
- `uv run pytest -m "not slow" -n auto`: **GREEN 690 passed / 1 skipped.**
- `dbtf build --select state:modified+`: **operator-gated** — the modified feature models reference
  `lakehouse_ext.{batter,pitcher}_clusters`, which don't exist until the operator runs the W7 DDL.
  CI runs this on clean runners POST-table-create (W5b/W6 pattern). Do NOT run it locally pre-cutover.

## ⏭️ Operator run-order (parity + cutover — external tables BEFORE merge; nothing here is auto)
1. Seed/refresh the cluster parquet if needed: `cluster_batters.py --seed` / `cluster_pitchers.py --seed`
   (one-time, if not already from W5b) — or just confirm the `--s3` parquet exists in S3.
2. `uv run python scripts/ddl/generate_w7_external_tables.py` → review `w7_external_tables.generated.sql`
   → run it in Snowflake (creates `lakehouse_ext.batter_clusters` + `pitcher_clusters` + their GRANTs).
3. `uv run python scripts/refresh_w1_external_tables.py` (or confirm W7_TABLES refresh).
4. **Parity BEFORE flipping the gate:** `uv run python scripts/parity_check_w7a_matchup.py --season 2025`
   and `… --date <recent> --check pa`. Verify the four consumers' S3 reads == Snowflake reads.
5. Merge dev→main (P5 CD redeploys; the feature-model source repoint goes live — feature build now
   reads `lakehouse_ext` clusters via Snowflake, value-identical).
6. **Flip the gate:** `W7A_LAKEHOUSE_S3=1` on the EC2 box → the daily consumers read S3.
7. **DROP the native cluster builds:** run the seasonal `cluster_batters.py --s3` /
   `cluster_pitchers.py --s3` (no native) going forward; `compute_archetype_posteriors` daily is
   already `--s3` via the gate. Native `statsapi.{batter,pitcher}_clusters` is now read by nobody.
8. Verify LIVE: a daily cycle runs green with `W7A_LAKEHOUSE_S3=1`; matchup signals non-null in
   `mart_sub_model_signals`; feature build's archetype columns non-null (the cluster repoint).

## git add (W7a ONLY — the working tree also has concurrent E9.37/E9.36 work; keep separate)
```
betting_ml/scripts/eb_priors/generate_matchup_signals.py
betting_ml/scripts/eb_priors/build_matchup_training_data.py
betting_ml/scripts/eb_priors/fit_archetype_priors.py
betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py
dbt/models/feature/feature_pregame_lineup_features.sql
dbt/models/feature/feature_pregame_starter_features.sql
dbt/models/feature/feature_batter_archetype_matchups.sql
dbt/models/feature/feature_pitcher_cluster_matchups.sql
dbt/models/sources.yml
scripts/ddl/generate_w7_external_tables.py
scripts/refresh_w1_external_tables.py
scripts/parity_check_w7a_matchup.py
pipeline/ops/daily_ingestion_ops.py
quant_sports_intel_models/baseball/edge_program/E11_1_W7a_session_recap.md
quant_sports_intel_models/baseball/edge_program/story_prompts.md   (W7a/W7b split — my section only)
quant_sports_intel_models/baseball/edge_program/build_roadmap.md   (W7a status — my line only)
```
⚠️ **NOT MINE — do NOT include in the W7a commit (concurrent sessions):** `CLAUDE.md`,
`app/backend/models/picks.py`, `frontend/app/picks/[game_pk]/page.tsx`, `scripts/write_serving_store.py`
(E9.37 line-movement series), and any E9.36 team-page files. Generated `w7_external_tables.generated.sql`
is gitignored-class (like `w6_external_tables.generated.sql`) — review output, don't commit.

## ⚠️ The "Cortex-only" end-state is NOT one wave away — straggler taxonomy (post-W7a)
After W7a the residual Snowflake footprint is still large. W7b + a long tail remain:
- **W7b (the deferred core):** the 10 `feature_pregame_*` DuckDB branches; `predict_today` feature
  reads + its `daily_model_predictions` WRITE; `write_serving_store` reads; `#3` profile_identity +
  injury_status; convert the request-path Snowflake last-resort to direct-S3 (then drop the
  `lakehouse_ext` views) → request path truly zero-Snowflake.
- **Long tail (beyond W7b, NOT in the current wave plan):** the OTHER sub-model signal generators
  (`generate_bullpen/run_env/defense/env_state/starter/offense_signals` → SCD-2 to
  `mart_sub_model_signals`); the EB posterior builders (`compute_starter/bullpen/lineup_posteriors`,
  `fit_park_priors` → MERGE to `eb_*`); `compute_elo` (`team_elo_history`); the raw **ingestion**
  scripts (savant/parlay/weather/oaa/umpires/transactions/framing — these WRITE the raw substrate the
  lakehouse is built FROM, so they stay until ingestion itself goes S3-first); the monitoring
  **sensors** (freshness reads). Truly "Cortex-only" (`generate_pick_narratives.py`) is several waves
  out — frame it honestly in the roadmap, not as imminent.

⇒ W7a banks the archetype/matchup credit drop + resolves INC-18 (keep+flag). W7b finishes the
prediction-path core; the long tail is a separate decommission track.

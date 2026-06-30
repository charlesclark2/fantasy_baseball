# Credence — repo guide for Claude Code sessions

## 🚨 WHICH APP TO EDIT — READ FIRST

Three things share confusingly similar paths. Two are live; one is dead.

- ✅ **UI / anything user-facing → `frontend/` ONLY** — the **Next.js** app (Vercel, auto-deploys on push to main).
- ✅ **API / backend → `app/backend/`** — the **live FastAPI** service (deployed to Lambda via `infrastructure/lambda/deploy.sh`; `app.backend.main` is the entrypoint). This is live — edit it for backend work.
- ⛔ **DEPRECATED legacy Streamlit UI → `app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`** — **not deployed, not the product. Do NOT edit** unless a task *explicitly* names "legacy Streamlit."

**Footgun (this is what bit a session on 2026-06-18):** the dead Streamlit UI files sit at the **top of `app/`, right next to the live `app/backend/`**, and Next.js has its *own* router dir at `frontend/app/`. So `app/` is **half-alive**: `app/backend/` = keep; everything else in `app/` = legacy UI = don't touch. "The app's UI" is **always `frontend/`**, never `app/home.py` / `app/pages/`.

**First action in any app/UI session:** run `cat frontend/package.json` and confirm Next.js (`"next"` in deps, `"dev": "next dev"`). If you're doing **UI** work and find yourself in `streamlit_app.py`, `st.set_page_config`, `app/home.py`, or `app/pages/*.py`, **STOP — wrong place → go to `frontend/`.**

## App quick map
- UI (Next.js): `frontend/app/**`, `frontend/components/**`, `frontend/lib/**`, `frontend/hooks/**`, `frontend/data/**`
- Backend API (live FastAPI): `app/backend/**` (`main.py`, `routers/`, `models/`, `services/`); deploy via `infrastructure/lambda/deploy.sh`
- Serving-store writers: `scripts/` (e.g. `write_serving_store.py`); dbt marts in `dbt/`
- Serving store read order: Railway PostgreSQL (primary) → S3 (fallback) → Snowflake (last resort, never at request time)
- ⛔ Legacy Streamlit (do not edit): `app/streamlit_app.py`, `app/home.py`, `app/pages/**`, `app/utils/**`
- **Changelog:** any user-facing change adds an entry to `frontend/data/changelog.json` as its final step. (Streamlit gets none — it isn't shipped.) 🗓️ Weeks are MONDAY–SUNDAY; the `week` field should be the Monday of the change's week. **As of E9.18 (2026-06-27) this is auto-enforced** — the changelog render auto-snaps any `week` date to its Monday + merges same-week blocks, and `betting_ml/tests/test_changelog_guard.py` (fast gate) fails the build on a non-Monday `week` key or duplicate Monday. So a wrong date can't ship; just add your item (Monday-of-week preferred).

## Where the plans live
- Model + application roadmap (single source of truth): `quant_sports_intel_models/baseball/edge_program/build_roadmap.md`
- Story specs: `quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md` (§0.2 = app architecture + the app-target rule)
- Per-story run prompts: `quant_sports_intel_models/baseball/edge_program/story_prompts.md`

## Conventions (see guide §0.1)
`dbtf` (not `dbt`); Snowflake via MCP, fully-qualified, no `USE`, never on a request path; `uv run python`; hand >1-min scripts to the operator; **do not `git commit`/`push`**; market-blind for non-market models; honest framing for anything user-facing (no win-rate / edge claims — `best_alpha = 0`).
- **🔬 MODELING BAKE-OFF DISCIPLINE (guide §0.5 — non-negotiable):** any story that BUILDS or SELECTS a predictive model runs a **bake-off, not a single architecture** — pre-register ≥3 candidate model classes, Optuna-tune each, feature-ablate, pick on the metric under purged/embargoed CV (per serving tier), guard the search with PBO<0.2/DSR>0. A prescribed structure is **one candidate among several**, always with a direct-learned foil. **A single architecture missing its gate is NOT a trustworthy null** — that's only earned after the whole candidate set, tuned + ablated, fails. Exemplar: E1.9 v6 (6 learner classes → Optuna → gate). Exceptions: pure registration/backfill, cheap sub-model re-eval, or explicit harness/eval stories.
- **💾 DATA SOURCE = S3/DuckDB, NOT Snowflake (guide §0.5 — HARDENED 2026-06-29 by the E11.1 lakehouse decommission):** ⚠️ **Snowflake is being DECOMMISSIONED to Cortex-only** (W1–W6 done — `mart_pitch_*`, the odds/CLV/team marts, the FanGraphs/posteriors/savant marts, `stg_batter_pitches` etc. now live as **S3 parquet**; W7 drops the remaining Snowflake views + the feature/serving readers). **So every model/data story reads training + feature data from the S3 lakehouse via DuckDB — a Snowflake pull is now a RED FLAG, not a fallback** (the table is at best a thin external-table view today and GONE after W7; the ONLY sanctioned Snowflake use is the Cortex narrative `generate_pick_narratives.py`). Use the proven lakehouse-read pattern (DuckDB over the S3 parquet, e.g. the `zone_matchup`/W-series scripts, `run_w1_lakehouse` helpers). If you believe a source is genuinely Snowflake-only, STOP and flag it (it's probably an un-migrated straggler → a precursor, not a Snowflake read). Then the cost hygiene still applies: assemble the feature matrix ONCE → parquet, and have every bake-off candidate / ablation / Optuna trial / CV fold read that cached parquet (never re-read per candidate); state the S3 source + parquet path in the handoff.
- **🧬 FEATURE-SELECTION DISCIPLINE (guide §0.5):** feature selection is required but bounded — **pre-register** a hypothesis-driven set of candidate adds/drops (not open subset search), select **in-fold** (never peek at the eval fold), and **count every config toward PBO<0.2/DSR>0** (deflation makes a wide ablation safe). Use the reproducible instruments — `derive_clustered_contract.py` (removal) + `incremental_lift_eval.py` (addition), or Optuna-tuned regularization — not hand-pruning (E1.8's stale-ranking bug). A single contract's miss is **NOT** a trustworthy null; report what was tried + the mechanism.
- **🚂 Railway MCP available:** for any Railway work (env vars, service config, redeploys, deploy logs) use the **Railway MCP** rather than hand-walking the operator through the dashboard — it sets vars, redeploys, and tails logs directly.
- **🪪 BOTO3 S3 WRITERS ON EC2 = INSTANCE-ROLE FALLBACK (W7b-1, 2026-06-29 — cost a morning):** the Dagster box authenticates to S3 via its **instance IAM role** (post-INC-16); `AWS_ACCESS_KEY_ID` is **UNSET** there. **NEVER pass `aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID")` (or `...secret...`) to `boto3.client`/`Session`** — when the env var is absent you pass `None`, which DISABLES boto3's default credential chain → `AuthorizationHeaderMalformed: a non-empty Access Key (AKID) must be provided`. Pass explicit keys ONLY when present, else omit them so the chain resolves the role (or write via DuckDB `COPY`, which already uses `credential_chain`). This bit all 7 S3 exporters at once; the parity/mirror class of op must also be **mirror-tier (ALERT-continue), NOT HALT**, until its cutover flag flips. (Note: production runs on **AWS EC2, not Railway** — the Railway MCP line above is legacy.) A CI lint now enforces this: `betting_ml/tests/test_boto3_credential_lint.py` (fast gate) FAILS if any `boto3.client`/`Session`/`resource` is constructed with `aws_access_key_id=os.environ.get(...)` (or a possibly-`None` key) — point new writers at `scripts/utils/lakehouse_raw_writer.make_s3_client()` (the shared instance-role-safe helper).

### 🧬 Type-contract guard (INC-19 — the NUMBER↔FLOAT incremental-drift cure) — ENFORCE
The recurring HALT class: a lakehouse dual-branch migration makes an upstream column compute as DuckDB DOUBLE→parquet→Snowflake FLOAT, but a downstream **`incremental` + `on_schema_change='sync_all_columns'`** table still stores it as `NUMBER(38,x)`; Snowflake can't ALTER NUMBER→FLOAT (`002108`) → the op HALTs and an operator must DROP+rebuild. Fired **5×** (INC-15 / W1d / INC-16-P0 / INC-19 / INC-19-recurrence), every victim = `feature_pregame_game_features_raw`.
- **CURE (prevention):** `feature_pregame_game_features_raw` wraps `final` in a generated `-- TYPE-PIN-START … -- TYPE-PIN-END` block that casts **every FLOAT output column to an explicit `::double`** (value-preserving 64-bit; `::float`=32-bit in DuckDB — never use it). The public wrapper `feature_pregame_game_features` casts each `_seasonnorm` column `::double`. So an upstream NUMBER↔FLOAT flip can never change the stored incremental type. The pinned set lives in `dbt/type_contracts/<model>.types.json` (**source of truth**).
- **GUARD (enforcement):** `betting_ml/tests/test_type_contract_guard.py` (fast gate) + `python3 scripts/gen_type_contract.py --check` (wired into the dbt-Build CI gate) go **RED** if a model's TYPE-PIN block drifts from its manifest.
- **🚨 CONVENTION — intended type change ⇒ update the contract in the SAME PR:** when you migrate a model / intend a type change, (1) edit the manifest (move a column in/out of `double_pinned`, or add/remove a column — re-derive truth from `information_schema.columns`), (2) `uv run python scripts/gen_type_contract.py --write` to sync the SQL, (3) commit model+manifest together (guard then passes). If a STORED type actually changed NUMBER↔FLOAT, the operator must **DROP+rebuild** the incremental (`--full-refresh` MERGEs, does NOT DROP — see [dbtf incremental note]). Add a new incremental victim to `CONTRACTS` in `scripts/gen_type_contract.py`. A new numeric column that can ever be FLOAT **must** be `::double`-pinned.

## Pipeline failure-handling contract (E11.7 — ENFORCE on every new op/test)

Three tiers govern how pipeline failures behave. Every new op, cron, sensor, and dbt test is assigned to exactly one tier:

| Tier | Behaviour | When to use |
|------|-----------|-------------|
| **HALT** | raise Exception / exit 1; fails the op/job | Serving-critical path only — `predict_today`, the feature store, serving-mart `dbt run`, the contract-guard, `write_serving_store`, signal freshness gate |
| **WARN-but-continue** | `context.log.warning(...)` + catch, op succeeds | Peripheral data-quality — non-serving ingestion (weather, OAA, bios), `dbt test` suite, user-bet settlement, narrative generation |
| **ALERT-loud-but-continue** | `context.log.warning(...)` or `echo WARNING` to stderr, then exit 0 | Any graceful skip that hides work — missing env var (DBT_RUNNER_URL unset), unreachable runner, no-op ingest; NEVER a silent `print()`/`pass` |

**Rules:**
- No in-process `dbtf` invocations anywhere — all dbt must go through `pipeline/ops/_dbt_exec._run_dbt` (enforces the remote-runner path and hard timeout).
- On `dbt build` days, the serving-critical step is always `dbt run` first (HALT on failure); the test suite is a separate non-blocking step (WARN tier). Never a single `dbt build` that gates predictions on a peripheral test failure (INC-6).
- Any `except` block in ops/sensor/cron files that does NOT call `context.log.warning()` (or write to stderr) is a contract violation.
- `dbt test` severity: serving-critical model contracts stay `error`; peripheral / non-serving data-quality checks use `severity: warn`.

**Op → tier map** (canonical; update when adding ops):

| Op / script | Tier | Reason |
|-------------|------|--------|
| `dbt_daily_build` → run step | HALT | gates feature store & mart rebuilds |
| `dbt_daily_build` → test step | WARN | peripheral data-quality; non-blocking |
| `predict_today_morning` / `lineup_predict` | HALT | primary serving output |
| `write_serving_store_op`, `write_api_cache_op` | HALT | gates Railway PG / S3 serve |
| `signal_freshness_check` | HALT | gates predict on stale inputs |
| `dbt_umpire_feature_rebuild`, `dbt_build_bullpen_posteriors_op` | HALT | rebuild critical feature blocks |
| `ingest_statcast`, `catchup_ingest_statcast`, `catchup_dbt_rebuild` | HALT | core pitch data; predictions depend |
| `ingest_weather`, `ingest_oaa`, `ingest_umpires_early/late` | WARN | non-critical; predictions run without |
| `ingest_fangraphs_stuff_plus`, `ingest_fangraphs_hitting_leaderboard` | WARN | INC-16: FanGraphs behind Cloudflare/flaresolverr (IP-bound cf_clearance); nullable LEFT JOIN → Statcast fallback; outage degrades quietly |
| `ingest_umpire_scorecards`, `settle_user_bets_op` | WARN | post-game enrichment; non-blocking |
| `generate_pick_narratives_op`, `check_data_freshness` | WARN | advisory; fallback exists |
| `ingest_statcast_to_s3_op`, `run_w1_lakehouse_op`, `refresh_w1_external_tables_op` | HALT | E11.1-W1d: mart_pitch_* served from S3 external tables; on critical path before dbt_daily_build |
| `intraday_weather_capture`, `write_book_odds_op` | WARN | supplemental; never blocks predictions |
| `schedule_capture` cron → dbt trigger | ALERT | skip must log WARNING to stderr |
| `trigger_dbt.py` when DBT_RUNNER_URL unset | ALERT | skip is loud (INC-5) |
| dbt tests on serving-critical marts | HALT (severity: error) | contract enforcement |
| dbt tests on peripheral/non-serving models | WARN (severity: warn) | data-quality advisory |

## 🟥 RUNTIME GATE — CI-green is NOT a merge gate for pipeline/serving code (added 2026-06-29 after a string of merged-then-broke runtime bugs)
**The problem this fixes:** CI mocks ALL IO (Snowflake/S3/network) by design → the fast gate + `dbtf compile` CANNOT see the bug class that keeps biting prod — AKID credential-chain, the inline-Snowflake-key gotcha, INC-19 type-drift (only HALTs on a real incremental run), INC-20 OOM, INC-21 (sensor silently not firing), INC-22 (UTC-date). Every one is a RUNTIME / box-environment bug invisible to CI. So "CI green" is necessary-NOT-sufficient and must NOT be treated as "ready to merge" for this code class.
**THE RULE:** for any change touching the **daily pipeline / serving writers / S3 exporters / sensors / ops / date-or-tz logic / boto3 / DuckDB-on-box**, the merge bar = **CI green AND the relevant op actually RAN once on the box** (a scoped run is fine — you do NOT need the full 40-min pipeline; skip the stable W1 pitch rebuild and run only the targeted chain, per the INC-21 recovery). ⚠️ flag-gated dual-branch code is safe merged-OFF (Snowflake arm stays live), but the **un-gated runtime glue runs regardless of any flag** (that's how INC-21/INC-22/AKID hit prod despite cutover flags being off) → that glue is where the real-run gate matters MOST.

### 🧨 RECURRING LANDMINES — READ FIRST before any pipeline/serving/box session (stop re-hitting the same bug across parallel sessions)
📖 **HOW THE BOX ACTUALLY WORKS → `services/dagster/aws/BOX_OPERATIONS.md`** (docker compose layout + how to exec a script, the inline Snowflake key, host crontab captures, out-of-process dbt-runner, Flaresolverr, deploy.sh/CD + baked-image drift, box facts, box-aware DuckDB memory). Read it instead of re-deriving the mechanics.
- **boto3 on the box:** NEVER `aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID")` (unset on EC2 → `None` → kills the instance-role chain → `AuthorizationHeaderMalformed`). Use `scripts/utils/lakehouse_raw_writer.make_s3_client()` / DuckDB `COPY` (credential_chain). Lint: `test_boto3_credential_lint.py`.
- **Snowflake auth on the box = INLINE key** (`SNOWFLAKE_PRIVATE_KEY`, raw/base64), NOT a key-FILE. ✅ FIXED in `snowflake_loader.py`/`data_loader.py`/`ingest_statsapi.py` (INC-22 shared PATH-if-exists→inline→password resolver); use that pattern (or `write_serving_store.py`'s) — never read `SNOWFLAKE_PRIVATE_KEY_PATH` raw, and stay pure DuckDB/S3 where possible.
- **DuckDB S3 region = `us-east-2`** for `baseball-betting-ml-artifacts` (explicit; boto3 is region-less but DuckDB needs it).
- **TZ/date = the US baseball-day, NOT UTC** (the box runs UTC → UTC "today" rolls to tomorrow after ~00:00 UTC = evening US time = INC-22, a silent empty-serve). **Use `betting_ml/utils/game_day.py::current_game_date()` (`America/Los_Angeles`, injectable clock) / `current_game_date_iso()`** — the canonical helper routed through ~22 serving/predict/ops/router sites; never `date.today()`/`utcnow().date()` in a serving path.
- **🕒 SNOWFLAKE MISREADS BINARY PARQUET TIMESTAMPS (W8a 24h outage — WILL recur in any feature/mart S3 migration):** a Snowflake external table reads an INT64 binary parquet `TIMESTAMP` at the wrong scale PER-ROW → a 2026 micros value materializes as year ~56,000,000 → connector overflow (`252005`) on fetch/CTAS/dbt-materialize. ⚠️ `min/max(year())` + `to_varchar(min())` read from parquet COLUMN STATS → look FINE → the bug only shows on a real ROW. CURE: store every `TIMESTAMP*` as ISO **VARCHAR** in the DuckDB build (`run_w1_lakehouse._string_timestamp_wrap`) + emit the ext-table col as `<COL> TIMESTAMP_NTZ AS (VALUE:col::TIMESTAMP_NTZ)` (string parse). `DATE` (INT32) reads fine.
- **🔠 Snowflake `VALUE:<key>` is CASE-SENSITIVE** — must match the parquet's stored field name EXACTLY. SF-mirrored upstreams (`SELECT *`→parquet) yield UPPERCASE cols; a hard `.lower()` in the generator → that column reads ALL-NULL through the ext table (SILENT). Emit exact described case.
- **🗂️ Glob-dup:** an ext table's `**/*.parquet` glob unions a stale `part-0.parquet` + the new `data.parquet` → 2× rows. Before a wave builds a model another export still mirrors, remove it from that export's TABLES dict + `aws s3 rm` the stray.
- **🧪 PARITY (DuckDB-over-parquet) IS NECESSARY-NOT-SUFFICIENT:** it is BLIND to the entire Snowflake-ext-table read-bug class (binary-ts→garbage, VALUE:case→NULL, glob-dup) because it never goes through the SF ext table. **The cutover gate for any feature/mart migration = a per-ROW fetch through the actual `lakehouse_ext.*` table** (+ `predict_today` green on the box), not just parity.
- **🧠 DuckDB `memory_limit` must be BOX-AWARE, never hardcoded > physical RAM** (a hardcoded 11 GB on a 4 GB box never spilled → kernel OOM-killed the HOST incl. Dagster = INC-22 #4) → `clamp(0.6×RAM, 2, 11)`. (Box is now `r6g.large` 16 GB.)
- **INC-19 type-drift:** a dual-branch migration flips NUMBER→FLOAT → a downstream `incremental` table HALTs. Intended type change ⇒ edit the manifest + `gen_type_contract.py --write` in the SAME PR; a real flip ⇒ operator DROP+rebuild (`--full-refresh` MERGEs, doesn't DROP).
- **Mirror/parity-only ops = mirror-tier (ALERT-continue), NOT HALT,** until the cutover flag flips.
- **`run_w1_lakehouse` full-rebuilds history (~10 min) every run** → for DOWNSTREAM debugging (feature/serving), SKIP it; rebuild only the targeted chain.
- **Parallel-session discipline:** when ≥2 sessions touch the same runtime surface (pipeline/serving/exporters), they WILL hit the same runtime bug independently → check this list first; if you hit a NEW landmine, tell the operator to add it here so the other sessions don't rediscover it.

## CI gates — REQUIRED before any handoff (never hand off red code)
Run the equivalent CI checks locally and confirm GREEN before the operator handoff:
- **Python → Unit Tests CI (E11.13 fast/slow split):** Run only the tests that exercise the changed modules — find the matching test file(s) under `betting_ml/tests/` or the relevant test directory and run those directly (e.g. `uv run pytest betting_ml/tests/test_derivative_odds.py`). For a cross-cutting change (shared utilities, pipeline ops, dbt-runner paths) run the **fast gate**: `uv run pytest -m "not slow" -n auto` (~15s — this mirrors CI's "Unit Tests (fast gate)" job and is what unblocks ships). If you touched anything under the `slow` marker (totals/strikeout Monte-Carlo calibration in `test_totals_distribution.py` / `test_prop_pricing.py`) **also** run `uv run pytest -m slow -n auto` (~95s — mirrors the "Unit Tests (slow)" job). **Both gates are required for merge.** The full serial `uv run pytest` is ~4.5 min and unnecessary now — prefer `-n auto`.
  - **Marker discipline (keep the suite from re-bloating):** any NEW test that takes **>5s** (heavy Monte-Carlo / large simulated fits / expensive expanding-window calibration) MUST get `@pytest.mark.slow` so it lands in the slow job, not the fast gate. Markers are registered in `pyproject.toml` under `[tool.pytest.ini_options] markers` and enforced by `--strict-markers` (an unregistered marker is a hard error). All external IO (Snowflake/S3/network) in the suite is mocked — keep it that way (extend the `test_book_odds_leakage_guard.py` text-fixture pattern); the `integration` marker is reserved for any future genuinely-networked test so it, too, stays out of the fast gate.
- **dbt → BOTH dbt-Build CI jobs:** `dbtf build --select state:modified+` **and** `dbtf compile`
  - **🩹 E11.16 — `state:modified+` MUST pass `--state` locally.** Running `dbtf … --select state:modified+` *without* `--state` makes fusion auto-download a deferral manifest from dbt Platform for the active project in `~/.dbt/dbt_cloud.yml` (`441385`). This repo is **self-managed (no dbt Platform deployment)**, so it 404s (`dbt1203`), the `state:modified` baseline is lost, and the selection is unreliable — exactly the trap that cost a W1d session. **CI is already correct** (it passes `--state dbt/state --defer` and runs on clean runners with no `dbt_cloud.yml`). For local validation use **`scripts/dbt_state.sh build --select state:modified+ --target dev`** — it fetches the same prod-manifest baseline CI uses and injects `--state … --defer`. Passing `--state` suppresses the Platform call entirely (verified).
If a check fails, fix it (or flag it as a real blocker in the handoff) — don't pass failing CI to the operator. State the result in the handoff.

## Session closeout — REQUIRED (every session, both tracks)
Because sessions don't commit, **end every session with an `⏭️ Operator handoff`** so the repo doesn't drift:
1. **CI-gate result** (Python unit tests + both dbt-Build jobs green — see above).
2. **Run-order commands** the operator must execute (Snowflake / `dbtf --select …` / `uv run …`, >1-min flagged).
3. **`git add <paths>`** — a copy-pasteable list of *every* file the session changed/created that should be committed: code, dbt models, `sub_model_registry.yaml`, `ablation_results/*.md`, and any guide/roadmap/`story_prompts.md` edits.
4. **Do NOT commit** large artifacts (`*.pkl`, `*.parquet`, model binaries) — those go to S3/registry and are gitignored; list them as excluded.
5. Model work: the validation gate result. App work: the `frontend/data/changelog.json` line + what to verify after deploy.

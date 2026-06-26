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
- **Changelog:** any user-facing change adds an entry to `frontend/data/changelog.json` as its final step. (Streamlit gets none — it isn't shipped.) **🗓️ WEEK BUCKETING (operator keeps having to fix this — get it right): weeks are MONDAY–SUNDAY. The `week` field MUST be the MONDAY of the change's week, NOT the ship date.** If a block for that Monday already exists, APPEND your item to it — do NOT create a second block for the same week. Example: a change shipped Thu **2026-06-25** goes under `"week": "2026-06-22"` (Mon) → renders "June 22 – June 28". Compute it: `monday = ship_date − ship_date.weekday()`. (E9.18 will make the render auto-snap any date to its Monday + add a CI guard so this can't be gotten wrong; until then, set the Monday by hand.)

## Where the plans live
- Model + application roadmap (single source of truth): `quant_sports_intel_models/baseball/edge_program/build_roadmap.md`
- Story specs: `quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md` (§0.2 = app architecture + the app-target rule)
- Per-story run prompts: `quant_sports_intel_models/baseball/edge_program/story_prompts.md`

## Conventions (see guide §0.1)
`dbtf` (not `dbt`); Snowflake via MCP, fully-qualified, no `USE`, never on a request path; `uv run python`; hand >1-min scripts to the operator; **do not `git commit`/`push`**; market-blind for non-market models; honest framing for anything user-facing (no win-rate / edge claims — `best_alpha = 0`).
- **🔬 MODELING BAKE-OFF DISCIPLINE (guide §0.5 — non-negotiable):** any story that BUILDS or SELECTS a predictive model runs a **bake-off, not a single architecture** — pre-register ≥3 candidate model classes, Optuna-tune each, feature-ablate, pick on the metric under purged/embargoed CV (per serving tier), guard the search with PBO<0.2/DSR>0. A prescribed structure is **one candidate among several**, always with a direct-learned foil. **A single architecture missing its gate is NOT a trustworthy null** — that's only earned after the whole candidate set, tuned + ablated, fails. Exemplar: E1.9 v6 (6 learner classes → Optuna → gate). Exceptions: pure registration/backfill, cheap sub-model re-eval, or explicit harness/eval stories.
- **💾 MODEL DATA-ACCESS COST HYGIENE (guide §0.5):** **S3-first** — if the training data is in the lakehouse (`mart_pitch_*`, the E13.12 PA substrate, E5.1/E2.0 backfills, `stg_batter_pitches`), read it from S3 via DuckDB, not Snowflake. If a Snowflake pull is unavoidable, do it **exactly once → parquet**, and have every bake-off candidate / ablation / Optuna trial / CV fold read that cached parquet — **never re-query Snowflake per candidate/trial** (a bake-off otherwise = N×K×T warehouse hits). Cache the assembled feature matrix, not raw tables; state the source + parquet path in the handoff.
- **🧬 FEATURE-SELECTION DISCIPLINE (guide §0.5):** feature selection is required but bounded — **pre-register** a hypothesis-driven set of candidate adds/drops (not open subset search), select **in-fold** (never peek at the eval fold), and **count every config toward PBO<0.2/DSR>0** (deflation makes a wide ablation safe). Use the reproducible instruments — `derive_clustered_contract.py` (removal) + `incremental_lift_eval.py` (addition), or Optuna-tuned regularization — not hand-pruning (E1.8's stale-ranking bug). A single contract's miss is **NOT** a trustworthy null; report what was tried + the mechanism.
- **🚂 Railway MCP available:** for any Railway work (env vars, service config, redeploys, deploy logs) use the **Railway MCP** rather than hand-walking the operator through the dashboard — it sets vars, redeploys, and tails logs directly.

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
| `ingest_umpire_scorecards`, `settle_user_bets_op` | WARN | post-game enrichment; non-blocking |
| `generate_pick_narratives_op`, `check_data_freshness` | WARN | advisory; fallback exists |
| `ingest_statcast_to_s3_op`, `run_w1_lakehouse_op`, `refresh_w1_external_tables_op` | HALT | E11.1-W1d: mart_pitch_* served from S3 external tables; on critical path before dbt_daily_build |
| `intraday_weather_capture`, `write_book_odds_op` | WARN | supplemental; never blocks predictions |
| `schedule_capture` cron → dbt trigger | ALERT | skip must log WARNING to stderr |
| `trigger_dbt.py` when DBT_RUNNER_URL unset | ALERT | skip is loud (INC-5) |
| dbt tests on serving-critical marts | HALT (severity: error) | contract enforcement |
| dbt tests on peripheral/non-serving models | WARN (severity: warn) | data-quality advisory |

## CI gates — REQUIRED before any handoff (never hand off red code)
Run the equivalent CI checks locally and confirm GREEN before the operator handoff:
- **Python → Unit Tests CI (E11.13 fast/slow split):** Run only the tests that exercise the changed modules — find the matching test file(s) under `betting_ml/tests/` or the relevant test directory and run those directly (e.g. `uv run pytest betting_ml/tests/test_derivative_odds.py`). For a cross-cutting change (shared utilities, pipeline ops, dbt-runner paths) run the **fast gate**: `uv run pytest -m "not slow" -n auto` (~15s — this mirrors CI's "Unit Tests (fast gate)" job and is what unblocks ships). If you touched anything under the `slow` marker (totals/strikeout Monte-Carlo calibration in `test_totals_distribution.py` / `test_prop_pricing.py`) **also** run `uv run pytest -m slow -n auto` (~95s — mirrors the "Unit Tests (slow)" job). **Both gates are required for merge.** The full serial `uv run pytest` is ~4.5 min and unnecessary now — prefer `-n auto`.
  - **Marker discipline (keep the suite from re-bloating):** any NEW test that takes **>5s** (heavy Monte-Carlo / large simulated fits / expensive expanding-window calibration) MUST get `@pytest.mark.slow` so it lands in the slow job, not the fast gate. Markers are registered in `pyproject.toml` under `[tool.pytest.ini_options] markers` and enforced by `--strict-markers` (an unregistered marker is a hard error). All external IO (Snowflake/S3/network) in the suite is mocked — keep it that way (extend the `test_book_odds_leakage_guard.py` text-fixture pattern); the `integration` marker is reserved for any future genuinely-networked test so it, too, stays out of the fast gate.
- **dbt → BOTH dbt-Build CI jobs:** `dbtf build --select state:modified+` **and** `dbtf compile`
If a check fails, fix it (or flag it as a real blocker in the handoff) — don't pass failing CI to the operator. State the result in the handoff.

## Session closeout — REQUIRED (every session, both tracks)
Because sessions don't commit, **end every session with an `⏭️ Operator handoff`** so the repo doesn't drift:
1. **CI-gate result** (Python unit tests + both dbt-Build jobs green — see above).
2. **Run-order commands** the operator must execute (Snowflake / `dbtf --select …` / `uv run …`, >1-min flagged).
3. **`git add <paths>`** — a copy-pasteable list of *every* file the session changed/created that should be committed: code, dbt models, `sub_model_registry.yaml`, `ablation_results/*.md`, and any guide/roadmap/`story_prompts.md` edits.
4. **Do NOT commit** large artifacts (`*.pkl`, `*.parquet`, model binaries) — those go to S3/registry and are gitignored; list them as excluded.
5. Model work: the validation gate result. App work: the `frontend/data/changelog.json` line + what to verify after deploy.

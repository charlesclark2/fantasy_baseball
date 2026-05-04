# Phase 8 — Card 8.H: Data & Model Engineering Infrastructure Epic

**Status:** Planning  
**Created:** 2026-05-04  
**Prerequisite for:** Phase 9 application build-out (Card 8.G), and safe execution of all other Phase 8 cards  
**Owner:** Charles Clark

---

## Motivation

Phases 1–7 built the full data pipeline, feature store, and model evaluation stack. The system works end-to-end in a single environment: one Snowflake account, one branch, one set of credentials. That is fine for research but creates real risk before building a real application on top of it:

- **Dev work directly touches prod data.** Any script run during development can corrupt the prediction log, overwrite model artifacts, or trigger Snowflake tasks prematurely.
- **CI tests exist but the dbt and scoring layers have no automated verification.** The `ci.yml` workflow added in 7.MB is the first guardrail, but it only covers pure-Python unit tests.
- **Model deploys are manual and irreversible.** There is no rollback protocol. A bad artifact deploy overwrites the only production pkl with no documented recovery path.
- **The application has no deployment home.** The Diamond Edge Streamlit app runs locally; it cannot be shared, monitored, or secured without a deploy target.
- **Operational blind spots.** If `predict_today.py` fails silently, if ECE drifts above acceptable thresholds, or if a feature group goes stale, there is no alert.

Card 8.H resolves all of these before Phase 9 builds the application.

---

## Cards

### 8.H1 — CI/CD Pipeline Hardening

**Goal:** Close the gaps identified in the 7.MB CI/CD audit.

**Gap 1: dbt-fusion re-downloads 24×/day (lineup_monitor.yml)**  
`lineup_monitor.yml` runs hourly and installs dbt-fusion from scratch on every run. At ~30s/install that is 12 minutes of network I/O per day for a binary that rarely changes.

Fix: add `actions/cache` keyed on the dbt-fusion version pinned in the workflow. Cache hit rate should be >95%. Apply the same cache to `dbt_daily_build.yml` and `dbt_staging_build.yml`.

```yaml
- name: Cache dbt-fusion
  uses: actions/cache@v4
  with:
    path: ~/.local/bin/dbtf
    key: dbtf-${{ env.DBT_FUSION_VERSION }}
```

**Gap 2: 7.S and 7.T ingestion scripts not confirmed in daily_ingestion.yml**  
Cards 7.S (starter velo trend features) and 7.T (bet tracker) introduced new scripts. Audit `daily_ingestion.yml` to confirm all scripts from these cards are present as daily steps.

**Gap 3: No model artifact smoke test in CI**  
When a pkl is changed in a PR, nothing verifies it loads correctly and produces valid probabilities.

Add a step to `ci.yml` that runs on PRs touching `betting_ml/models/`:
```python
import joblib, numpy as np
from betting_ml.utils.model_io import load_model
m = load_model('home_win')
p = m.predict_proba(np.zeros((1, m.n_features_in_)))[0, 1]
assert 0.0 < p < 1.0, f'Bad probability: {p}'
```

**Gap 4: predict_today.py has no CI home**  
Scoring runs via Snowflake Task, so a Python crash is invisible to GitHub Actions. At minimum add a syntax + import check to `ci.yml`:
```bash
uv run python -c "import scripts.predict_today"
```
Full scoring validation requires the dev Snowflake environment (8.H4 dependency).

**Gap 5: No dbt test gate on PRs touching SQL models**  
A PR that breaks a dbt model schema test is not caught until the nightly `build`. Add a `dbt-pr-check` job to `ci.yml` conditional on changed SQL files:
```bash
dbtf build --select state:modified+ --target dev --defer --state prod
```
This requires the dev target from 8.H4.

**Acceptance criteria:**
- [ ] `lineup_monitor.yml` dbt-fusion install shows cache hit on second run; same cache applied to `dbt_daily_build.yml` and `dbt_staging_build.yml`
- [ ] All 7.S/7.T ingestion scripts confirmed present in `daily_ingestion.yml`
- [ ] Pushing a corrupted pkl to a PR triggers `ci.yml` failure
- [ ] `predict_today.py` import check passes in CI
- [ ] dbt PR check runs on SQL file changes (requires 8.H4)

---

### 8.H2 — Model Deploy Protocol

**Goal:** Structured, reversible process for shipping new model artifacts to production. First use: deploy `elasticnet` as the production home-win model (pending from 7.MB).

**Problem in detail:**  
`betting_ml/models/home_win/` contains multiple pkl variants from prior experiments with no documented protocol for which is active or how to roll back. `model_registry.yaml` has no `rollback_artifact_path`.

**Deploy protocol (codified as `docs/model_deploy_runbook.md`):**

1. **Train and evaluate** — new artifact produced via eval scripts; results documented in `betting_ml/evaluation/`
2. **Write artifact** — serialize to `betting_ml/models/{target}/{model_name}_{year}.pkl`
3. **Update registry** — update `model_registry.yaml`:
   - Bump `artifact_path` to new pkl
   - Move previous `artifact_path` to new `rollback_artifact_path` field
   - Record `deployed_date`, `brier_score`, `ece_raw`
4. **Smoke test** — run `ci.yml` smoke test locally
5. **Git tag** — `git tag model/home_win/v{N}` so the exact pkl + registry state is recoverable
6. **Merge PR** — CI must pass; reviewer confirms evaluation doc is present
7. **Rollback** if needed: swap `artifact_path` ↔ `rollback_artifact_path` in registry, push, retag

**elasticnet deploy (first run of the protocol):**  
This is the pending 7.MB task. Retrain `elasticnet` on the full 2022–2026 dataset, write artifact, follow the protocol above. No calibration layer (ECE_raw=0.0202, Platt does not improve it). Update `predict_today.py` to load `LogisticRegression` instead of `XGBClassifier`.

**Acceptance criteria:**
- [ ] `model_registry.yaml` has `rollback_artifact_path` field for all three targets
- [ ] `docs/model_deploy_runbook.md` written and covers all 7 steps
- [ ] `git tag model/home_win/v2` exists and points to elasticnet deploy commit
- [ ] `predict_today.py` loads `elasticnet` pkl and applies no calibration layer
- [ ] Smoke test passes for new artifact
- [ ] Previous XGBoost pkl retained and referenced as `rollback_artifact_path`

---

### 8.H3 — Live Monitoring & Alerting

**Goal:** Detect model degradation, data staleness, and prediction coverage failures before they affect bets.

**Monitoring targets:**

**Calibration drift (ECE)**  
Current ECE_raw for elasticnet: 0.0202. Alert threshold: ECE > 0.04 (2× baseline), per model_selection_v1.md §8.

Extend `backfill_prediction_log.py` to compute rolling 14-day ECE on `prediction_log` rows where `outcome` is not null. Write to a new `model_health_log` table. Trigger alert when threshold is crossed.

**Data freshness**

| Feature group | Expected freshness | Alert if stale > |
|---|---|---|
| Statcast (batter_pitches) | Daily (yesterday) | 36h |
| Odds snapshots | 6× daily | 6h on game days |
| FanGraphs Stuff+ | Sunday | 8 days |
| Umpire assignments | Daily | 36h |
| Transactions (injury) | Daily | 36h |
| Lineup confirmations | Hourly (game days) | 2h on game days |

Implement as `scripts/check_data_freshness.py` — queries `MAX(ingestion_timestamp)` per source table, compares to threshold, exits non-zero on any failure. Add as a step in `daily_ingestion.yml` after all ingestion steps.

**Prediction coverage**  
Every scheduled game with confirmed lineups should have a row in `daily_model_predictions`. Coverage < 90% on any game day is a failure. Add a coverage check step in `daily_ingestion.yml` after `predict_today.py` runs.

**Acceptance criteria:**
- [ ] `model_health_log` table exists; ECE computed daily on rolling 14-day window
- [ ] ECE alert fires in test when threshold is exceeded (manual trigger test)
- [ ] `scripts/check_data_freshness.py` passes locally and passes in `daily_ingestion.yml`
- [ ] Prediction coverage check step present in `daily_ingestion.yml`
- [ ] All monitoring checks documented in `docs/monitoring_runbook.md`

---

### 8.H4 — Snowflake Environment Isolation

**Goal:** Dev branch work cannot read or write production schemas.

**Problem in detail:**  
Currently `SNOWFLAKE_DATABASE=baseball_data` is hardcoded everywhere. A Python script run from a dev branch writes to the same tables as production. dbt models run by a developer overwrite mart tables that `predict_today.py` reads.

**Approach — two layers:**

**Layer 1: dbt targets**  
Add a `dev` target to the Snowflake connection config that sets schema prefixes:
- `DEV_FEATURE` instead of `FEATURE`
- `DEV_MART` instead of `MART` / `BETTING`
- `DEV_STAGING` instead of `STAGING`

`dbtf build --target dev` builds into dev schemas; `dbtf build` (default `prod`) builds into prod. CI workflows for PRs use `--target dev`. Nightly scheduled runs use `--target prod`.

**Layer 2: Python env gating**  
Add `SNOWFLAKE_ENV` env var (`dev` | `prod`). When `dev`, all Python scripts read/write `DEV_*` schemas and do not invoke live Snowflake Tasks.

Implementation: `scripts/utils/snowflake_env.py` — single `get_schema(base: str) -> str` helper. All ingestion and scoring scripts call this instead of hardcoding schema names.

**GitHub Actions:**  
- Add `SNOWFLAKE_ENV=dev` + dev-credentials secrets for PR workflows
- `daily_ingestion.yml` keeps `SNOWFLAKE_ENV=prod` (explicit, not default)

**Acceptance criteria:**
- [ ] `dbtf build --target dev` produces all mart tables in `DEV_*` schemas without touching prod
- [ ] `SNOWFLAKE_ENV=dev uv run python scripts/predict_today.py` reads from `DEV_FEATURE`, writes to `DEV_MART`, and does not invoke any Snowflake Task
- [ ] PR CI workflow uses dev credentials and `--target dev`; prod schemas unchanged after PR build
- [ ] `project_context.md` updated with dev/prod environment documentation

---

### 8.H5 — Application Deployment

**Goal:** Diamond Edge Streamlit app is publicly accessible, secured, and not running on a local machine.

**Approach: Streamlit Community Cloud**

1. **Secret management** — move all credentials to Streamlit secrets (`.streamlit/secrets.toml` locally; Streamlit Cloud secrets UI for prod). No credentials in code or committed files.
2. **Dependency file** — confirm `pyproject.toml` or a `requirements.txt` satisfies Streamlit Cloud's pip-based install.
3. **Environment detection** — single `get_snowflake_connection()` helper reads `st.secrets` in prod, `.env` locally.
4. **Health indicator** — sidebar shows last pipeline run timestamp so stale data is obvious.

Note: Card 8.G (Production Web Application) is the longer-term FastAPI + React replacement. 8.H5 deploys the existing Streamlit app to a stable URL so it is usable during the 2026 season while 8.G is built.

**Acceptance criteria:**
- [ ] App is live at a stable Streamlit Cloud URL
- [ ] No credentials in any committed file; all secrets via Streamlit secrets manager
- [ ] App loads correctly with Snowflake queries running against prod schemas
- [ ] Local `streamlit run` still works with `.env` fallback
- [ ] Sidebar shows last pipeline run timestamp

---

## Card Dependencies

```
8.H1 (Gaps 1–3)   ← no upstream dependency, start here
8.H2               ← depends on 8.H1 Gap 3 (smoke test should exist before deploying)
8.H3               ← no upstream dependency, can run in parallel with 8.H2
8.H4               ← no upstream dependency, but enables 8.H1 Gaps 4–5
8.H5               ← no upstream dependency, but cleaner after 8.H4
```

Recommended sequencing: **8.H1 (Gaps 1–3) → 8.H2 → 8.H3 in parallel → 8.H4 → 8.H1 (Gaps 4–5) → 8.H5**

---

## Out of Scope for 8.H

- **Stacked ensemble / decomposed micro-services model** — Phase 9
- **Dynamic Kelly alpha (8.F2)** — separate Phase 8 epic (Dynamic Bayesian Inference Engine)
- **NGBoost distribution surfacing (8.F3)** — separate Phase 8 epic
- **Bayesian shrinkage re-derivation (8.F4)** — separate Phase 8 epic
- **Uncertainty-adjusted Kelly sizing (8.F5)** — separate Phase 8 epic
- **Production web app (FastAPI + React)** — Card 8.G, blocked on positive CLV

---

## Success Definition

8.H is complete when:

1. A developer can branch from `dev`, run `SNOWFLAKE_ENV=dev dbtf build --target dev`, and never touch a prod table.
2. A PR to `main` automatically runs unit tests, a model smoke test (if models changed), and a dbt schema check (if SQL changed) — and blocks merge on failure.
3. Deploying a new model artifact follows the documented, tagged, reversible protocol.
4. The team knows within one hour if ECE has drifted, data is stale, or prediction coverage has dropped.
5. Diamond Edge is accessible at a stable URL without running a local server.
